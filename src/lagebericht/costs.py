from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, DecimalException
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile

from .schedule import to_berlin


MILLION = Decimal(1_000_000)
MAX_TOKENS = 1_000_000_000
MAX_DECIMAL_TEXT_LENGTH = 16
MAX_MONETARY_VALUE = Decimal("1000000")
_DECIMAL_PATTERN = re.compile(r"(?:0|[1-9][0-9]{0,6})(?:\.[0-9]{1,8})?")
_TOP_LEVEL_FIELDS = {
    "schemaVersion",
    "priceVersion",
    "budgetEur",
    "usdToEur",
    "rateEffectiveDate",
    "collectionStartedAt",
    "models",
}
_MODEL_PRICE_FIELDS = {
    "inputUsdPerMTok",
    "outputUsdPerMTok",
    "cacheWriteUsdPerMTok",
    "cacheReadUsdPerMTok",
}
_REPORT_TYPES = {"daily", "week", "month"}
_OUTCOMES = {
    "end_turn",
    "max_tokens",
    "refusal",
    "transport_error",
    "invalid_response",
}
_REPORT_FIELDS = {
    "schemaVersion",
    "month",
    "timezone",
    "budgetEur",
    "estimatedCostUsd",
    "estimatedCostEur",
    "budgetPercent",
    "unmeasuredCalls",
    "collectionStartedAt",
    "priceVersion",
    "rate",
    "events",
}
_EVENT_FIELDS = {
    "eventId",
    "occurredAt",
    "reportType",
    "reportId",
    "model",
    "outcome",
    "measured",
    "usage",
    "estimatedCostUsd",
    "estimatedCostEur",
}
_USAGE_FIELDS = {
    "input_tokens",
    "output_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
}
_MONTH_PATTERN = re.compile(r"[0-9]{4}-(?:0[1-9]|1[0-2])")
_EVENT_ID_PATTERN = re.compile(r"[0-9a-f]{64}")


class CostDataError(ValueError):
    """Raised when pricing or usage data cannot be costed safely."""


@dataclass(frozen=True)
class CostContext:
    report_type: str
    report_id: str
    run_id: str
    run_attempt: str


def _decimal_string(value, path: str, *, positive: bool = False) -> Decimal:
    if not isinstance(value, str):
        raise CostDataError(f"{path}: must be a decimal string")
    if len(value) > MAX_DECIMAL_TEXT_LENGTH or _DECIMAL_PATTERN.fullmatch(value) is None:
        raise CostDataError(f"{path}: must be a canonical decimal string")
    try:
        result = Decimal(value)
    except DecimalException as exc:
        raise CostDataError(f"{path}: must be a decimal string") from exc
    if (
        not result.is_finite()
        or result < 0
        or result > MAX_MONETARY_VALUE
        or (positive and result == 0)
    ):
        qualifier = "positive" if positive else "non-negative"
        raise CostDataError(
            f"{path}: must be a finite {qualifier} decimal up to {MAX_MONETARY_VALUE}"
        )
    return result


def _non_empty_string(value, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CostDataError(f"{path}: must be a non-empty string")
    return value


def load_pricing(path: Path) -> dict:
    """Load and validate a versioned pricing file using exact decimals."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CostDataError(f"cannot read pricing config: {exc}") from exc

    if not isinstance(raw, dict) or set(raw) != _TOP_LEVEL_FIELDS:
        raise CostDataError("pricing config fields do not match the contract")
    if isinstance(raw["schemaVersion"], bool) or raw["schemaVersion"] != 1:
        raise CostDataError("schemaVersion: must be 1")
    _non_empty_string(raw["priceVersion"], "priceVersion")

    try:
        date.fromisoformat(raw["rateEffectiveDate"])
    except (TypeError, ValueError) as exc:
        raise CostDataError("rateEffectiveDate: must be an ISO date") from exc
    try:
        collection_start = datetime.fromisoformat(raw["collectionStartedAt"])
    except (TypeError, ValueError) as exc:
        raise CostDataError("collectionStartedAt: must be an ISO datetime") from exc
    if collection_start.tzinfo is None or collection_start.utcoffset() is None:
        raise CostDataError("collectionStartedAt: must include a timezone")

    models = raw["models"]
    if not isinstance(models, dict) or not models:
        raise CostDataError("models: must be a non-empty object")

    parsed_models = {}
    for model, prices in models.items():
        _non_empty_string(model, "models key")
        if not isinstance(prices, dict) or set(prices) != _MODEL_PRICE_FIELDS:
            raise CostDataError(f"models.{model}: price fields do not match the contract")
        parsed_models[model] = {
            field: _decimal_string(value, f"models.{model}.{field}")
            for field, value in prices.items()
        }

    budget_eur = _decimal_string(raw["budgetEur"], "budgetEur", positive=True)
    if budget_eur != Decimal("5.00"):
        raise CostDataError("budgetEur: must be exactly 5.00")
    return {
        **raw,
        "budgetEur": budget_eur,
        "usdToEur": _decimal_string(raw["usdToEur"], "usdToEur", positive=True),
        "models": parsed_models,
    }


def _tokens(usage: dict, field: str, *, default=None) -> int:
    if field not in usage:
        if default is not None:
            return default
        raise CostDataError(f"{field}: missing token count")
    value = usage[field]
    if isinstance(value, bool) or not isinstance(value, int):
        raise CostDataError(f"{field}: must be an integer")
    if not 0 <= value <= MAX_TOKENS:
        raise CostDataError(f"{field}: must be between 0 and {MAX_TOKENS}")
    return value


def normalize_usage(usage: dict) -> dict[str, int]:
    """Return the four safe token counts persisted by the cost ledger."""
    if not isinstance(usage, dict):
        raise CostDataError("usage: must be an object")
    return {
        "input_tokens": _tokens(usage, "input_tokens"),
        "output_tokens": _tokens(usage, "output_tokens"),
        "cache_creation_input_tokens": _tokens(
            usage, "cache_creation_input_tokens", default=0
        ),
        "cache_read_input_tokens": _tokens(usage, "cache_read_input_tokens", default=0),
    }


def estimate_cost(model: str, usage: dict, pricing: dict) -> tuple[Decimal, Decimal]:
    """Estimate one Anthropic call in USD and EUR without float rounding."""
    try:
        model_prices = pricing["models"][model]
    except (KeyError, TypeError) as exc:
        raise CostDataError(f"unknown model: {model!r}") from exc
    normalized = normalize_usage(usage)

    try:
        usd = (
            Decimal(normalized["input_tokens"]) * model_prices["inputUsdPerMTok"]
            + Decimal(normalized["output_tokens"]) * model_prices["outputUsdPerMTok"]
            + Decimal(normalized["cache_creation_input_tokens"])
            * model_prices["cacheWriteUsdPerMTok"]
            + Decimal(normalized["cache_read_input_tokens"])
            * model_prices["cacheReadUsdPerMTok"]
        ) / MILLION
        eur = usd * pricing["usdToEur"]
    except (KeyError, TypeError, DecimalException) as exc:
        raise CostDataError("pricing: invalid parsed price data") from exc
    return usd, eur


def berlin_month(moment: datetime) -> str:
    """Return the calendar month containing an aware moment in Berlin."""
    if not isinstance(moment, datetime) or moment.tzinfo is None or moment.utcoffset() is None:
        raise CostDataError("moment: must be a timezone-aware datetime")
    return to_berlin(moment).strftime("%Y-%m")


def context_from_environment(
    report_type: str,
    report_id: str,
    environ: Mapping[str, str] | None = None,
) -> CostContext:
    """Build a stable event context from GitHub Actions or local defaults."""
    values = os.environ if environ is None else environ
    return CostContext(
        report_type,
        report_id,
        values.get("GITHUB_RUN_ID") or "local",
        values.get("GITHUB_RUN_ATTEMPT") or "1",
    )


def _json_number(value, path: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CostDataError(f"{path}: must be a number")
    if isinstance(value, float) and not math.isfinite(value):
        raise CostDataError(f"{path}: must be finite")
    result = Decimal(str(value))
    if result < 0:
        raise CostDataError(f"{path}: must be non-negative")
    return result


def _iso_datetime(value, path: str) -> None:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise CostDataError(f"{path}: must be an ISO datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CostDataError(f"{path}: must include a timezone")


def validate_cost_report(report: dict, *, expected_month: str | None = None) -> bool:
    """Validate the public ledger contract without an external JSON Schema runtime."""
    if not isinstance(report, dict) or set(report) != _REPORT_FIELDS:
        raise CostDataError("cost report fields do not match the contract")
    month = report["month"]
    if not isinstance(month, str) or _MONTH_PATTERN.fullmatch(month) is None:
        raise CostDataError("month: must be YYYY-MM")
    if expected_month is not None and month != expected_month:
        raise CostDataError("month: does not match its artifact name")
    if report["schemaVersion"] != 1 or isinstance(report["schemaVersion"], bool):
        raise CostDataError("schemaVersion: must be 1")
    if report["timezone"] != "Europe/Berlin":
        raise CostDataError("timezone: must be Europe/Berlin")
    if _json_number(report["budgetEur"], "budgetEur") != Decimal("5"):
        raise CostDataError("budgetEur: must be exactly 5")
    total_usd = _json_number(report["estimatedCostUsd"], "estimatedCostUsd")
    total_eur = _json_number(report["estimatedCostEur"], "estimatedCostEur")
    percent = _json_number(report["budgetPercent"], "budgetPercent")
    unmeasured = report["unmeasuredCalls"]
    if isinstance(unmeasured, bool) or not isinstance(unmeasured, int) or unmeasured < 0:
        raise CostDataError("unmeasuredCalls: must be a non-negative integer")
    _iso_datetime(report["collectionStartedAt"], "collectionStartedAt")
    _non_empty_string(report["priceVersion"], "priceVersion")

    rate = report["rate"]
    if not isinstance(rate, dict) or set(rate) != {"usdToEur", "effectiveDate"}:
        raise CostDataError("rate fields do not match the contract")
    if _json_number(rate["usdToEur"], "rate.usdToEur") <= 0:
        raise CostDataError("rate.usdToEur: must be positive")
    try:
        date.fromisoformat(rate["effectiveDate"])
    except (TypeError, ValueError) as exc:
        raise CostDataError("rate.effectiveDate: must be an ISO date") from exc

    events = report["events"]
    if not isinstance(events, list):
        raise CostDataError("events: must be an array")
    ids = set()
    sum_usd = Decimal(0)
    sum_eur = Decimal(0)
    counted_unmeasured = 0
    for index, event in enumerate(events):
        path = f"events[{index}]"
        if not isinstance(event, dict) or set(event) != _EVENT_FIELDS:
            raise CostDataError(f"{path}: fields do not match the contract")
        event_id = event["eventId"]
        if not isinstance(event_id, str) or _EVENT_ID_PATTERN.fullmatch(event_id) is None:
            raise CostDataError(f"{path}.eventId: invalid")
        if event_id in ids:
            raise CostDataError(f"{path}.eventId: duplicate")
        ids.add(event_id)
        _iso_datetime(event["occurredAt"], f"{path}.occurredAt")
        if event["reportType"] not in _REPORT_TYPES:
            raise CostDataError(f"{path}.reportType: invalid")
        for field in ("reportId", "model"):
            _non_empty_string(event[field], f"{path}.{field}")
        if event["outcome"] not in _OUTCOMES:
            raise CostDataError(f"{path}.outcome: invalid")
        measured = event["measured"]
        if not isinstance(measured, bool):
            raise CostDataError(f"{path}.measured: must be boolean")
        if measured:
            usage = event["usage"]
            if not isinstance(usage, dict) or set(usage) != _USAGE_FIELDS:
                raise CostDataError(f"{path}.usage: invalid measured usage")
            normalize_usage(usage)
            sum_usd += _json_number(event["estimatedCostUsd"], f"{path}.estimatedCostUsd")
            sum_eur += _json_number(event["estimatedCostEur"], f"{path}.estimatedCostEur")
        else:
            counted_unmeasured += 1
            if any(event[field] is not None for field in ("usage", "estimatedCostUsd", "estimatedCostEur")):
                raise CostDataError(f"{path}: unmeasured event must contain null usage and costs")

    if unmeasured != counted_unmeasured:
        raise CostDataError("unmeasuredCalls: inconsistent with events")
    if total_usd != sum_usd or total_eur != sum_eur:
        raise CostDataError("estimated totals: inconsistent with events")
    try:
        expected_percent = (total_eur / Decimal("5") * 100).quantize(
            Decimal("0.1")
        )
    except DecimalException as exc:
        raise CostDataError("budgetPercent: cannot be represented safely") from exc
    if percent != expected_percent:
        raise CostDataError("budgetPercent: inconsistent with estimatedCostEur")
    if events != sorted(events, key=lambda event: (event["occurredAt"], event["eventId"])):
        raise CostDataError("events: must be sorted")
    return True


def _rounded_number(value: Decimal, places: str = "0.000001") -> float:
    return float(value.quantize(Decimal(places)))


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        delete=False,
        suffix=".tmp",
        newline="\n",
    )
    temporary = Path(handle.name)
    try:
        with handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


class CostRecorder:
    """Persist deduplicated, aggregate-only public cost events by Berlin month."""

    def __init__(
        self,
        data_root: Path,
        pricing_path: Path,
        context: CostContext,
        now=None,
    ):
        if context.report_type not in _REPORT_TYPES:
            raise CostDataError("report_type: invalid")
        for field in ("report_id", "run_id", "run_attempt"):
            _non_empty_string(getattr(context, field), field)
        self.data_root = Path(data_root)
        self.pricing = load_pricing(Path(pricing_path))
        self.context = context
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.call_index = 0

    def observe(self, model: str, usage: dict | None, outcome: str) -> None:
        if outcome not in _OUTCOMES:
            raise CostDataError("outcome: invalid")
        _non_empty_string(model, "model")
        moment = self.now()
        month = berlin_month(moment)
        identity = "|".join(
            (
                self.context.run_id,
                self.context.run_attempt,
                self.context.report_type,
                self.context.report_id,
                str(self.call_index),
                model,
            )
        )
        self.call_index += 1
        event_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()

        measured = False
        normalized = None
        usd_number = None
        eur_number = None
        if usage is not None:
            try:
                normalized = normalize_usage(usage)
                usd, eur = estimate_cost(model, normalized, self.pricing)
            except CostDataError:
                normalized = None
            else:
                measured = True
                usd_number = _rounded_number(usd)
                eur_number = _rounded_number(eur)

        event = {
            "eventId": event_id,
            "occurredAt": moment.isoformat(),
            "reportType": self.context.report_type,
            "reportId": self.context.report_id,
            "model": model,
            "outcome": outcome,
            "measured": measured,
            "usage": normalized,
            "estimatedCostUsd": usd_number,
            "estimatedCostEur": eur_number,
        }
        path = self.data_root / "costs" / f"{month}.json"
        events = []
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                raise CostDataError(f"cannot read existing cost report: {exc}") from exc
            validate_cost_report(existing, expected_month=month)
            events = existing["events"]
        if not any(item["eventId"] == event_id for item in events):
            events.append(event)
        events.sort(key=lambda item: (item["occurredAt"], item["eventId"]))
        total_usd = sum(
            (Decimal(str(item["estimatedCostUsd"])) for item in events if item["measured"]),
            Decimal(0),
        )
        total_eur = sum(
            (Decimal(str(item["estimatedCostEur"])) for item in events if item["measured"]),
            Decimal(0),
        )
        report = {
            "schemaVersion": 1,
            "month": month,
            "timezone": "Europe/Berlin",
            "budgetEur": 5.0,
            "estimatedCostUsd": _rounded_number(total_usd),
            "estimatedCostEur": _rounded_number(total_eur),
            "budgetPercent": _rounded_number(
                total_eur / self.pricing["budgetEur"] * 100, "0.1"
            ),
            "unmeasuredCalls": sum(not item["measured"] for item in events),
            "collectionStartedAt": self.pricing["collectionStartedAt"],
            "priceVersion": self.pricing["priceVersion"],
            "rate": {
                "usdToEur": float(self.pricing["usdToEur"]),
                "effectiveDate": self.pricing["rateEffectiveDate"],
            },
            "events": events,
        }
        validate_cost_report(report, expected_month=month)
        _atomic_json(path, report)

        from .publish import rebuild_index

        _atomic_json(self.data_root / "index.json", rebuild_index(self.data_root))
