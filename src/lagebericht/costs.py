from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, DecimalException
import json
from pathlib import Path

from .schedule import to_berlin


MILLION = Decimal(1_000_000)
MAX_TOKENS = 1_000_000_000
MAX_DECIMAL_TEXT_LENGTH = 64
MAX_MONETARY_VALUE = Decimal("1000000")
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
    if len(value) > MAX_DECIMAL_TEXT_LENGTH:
        raise CostDataError(f"{path}: decimal string is too long")
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
