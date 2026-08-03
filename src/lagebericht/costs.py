from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


MILLION = Decimal(1_000_000)
MAX_TOKENS = 1_000_000_000
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


class CostDataError(ValueError):
    """Raised when pricing or usage data cannot be costed safely."""


def _decimal_string(value, path: str, *, positive: bool = False) -> Decimal:
    if not isinstance(value, str):
        raise CostDataError(f"{path}: must be a decimal string")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise CostDataError(f"{path}: must be a decimal string") from exc
    if not result.is_finite() or result < 0 or (positive and result == 0):
        qualifier = "positive" if positive else "non-negative"
        raise CostDataError(f"{path}: must be a finite {qualifier} decimal")
    return result


def _non_empty_string(value, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CostDataError(f"{path}: must be a non-empty string")
    return value


def load_pricing(path: Path) -> dict:
    """Load and validate a versioned pricing file using exact decimals."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
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

    return {
        **raw,
        "budgetEur": _decimal_string(raw["budgetEur"], "budgetEur", positive=True),
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


def estimate_cost(model: str, usage: dict, pricing: dict) -> tuple[Decimal, Decimal]:
    """Estimate one Anthropic call in USD and EUR without float rounding."""
    try:
        model_prices = pricing["models"][model]
    except (KeyError, TypeError) as exc:
        raise CostDataError(f"unknown model: {model!r}") from exc
    if not isinstance(usage, dict):
        raise CostDataError("usage: must be an object")

    input_tokens = _tokens(usage, "input_tokens")
    output_tokens = _tokens(usage, "output_tokens")
    cache_creation_tokens = _tokens(usage, "cache_creation_input_tokens", default=0)
    cache_read_tokens = _tokens(usage, "cache_read_input_tokens", default=0)

    try:
        usd = (
            Decimal(input_tokens) * model_prices["inputUsdPerMTok"]
            + Decimal(output_tokens) * model_prices["outputUsdPerMTok"]
            + Decimal(cache_creation_tokens) * model_prices["cacheWriteUsdPerMTok"]
            + Decimal(cache_read_tokens) * model_prices["cacheReadUsdPerMTok"]
        ) / MILLION
        eur = usd * pricing["usdToEur"]
    except (KeyError, TypeError, InvalidOperation) as exc:
        raise CostDataError("pricing: invalid parsed price data") from exc
    return usd, eur


def berlin_month(moment: datetime) -> str:
    """Return the calendar month containing an aware moment in Berlin."""
    if not isinstance(moment, datetime) or moment.tzinfo is None or moment.utcoffset() is None:
        raise CostDataError("moment: must be a timezone-aware datetime")
    try:
        berlin = moment.astimezone(ZoneInfo("Europe/Berlin"))
    except ZoneInfoNotFoundError:
        utc = moment.astimezone(timezone.utc)
        march_day = monthrange(utc.year, 3)[1]
        october_day = monthrange(utc.year, 10)[1]
        summer_start = datetime(utc.year, 3, march_day, 1, tzinfo=timezone.utc)
        summer_end = datetime(utc.year, 10, october_day, 1, tzinfo=timezone.utc)
        summer_start -= timedelta(days=(summer_start.weekday() + 1) % 7)
        summer_end -= timedelta(days=(summer_end.weekday() + 1) % 7)
        berlin = utc + timedelta(hours=2 if summer_start <= utc < summer_end else 1)
    return berlin.strftime("%Y-%m")
