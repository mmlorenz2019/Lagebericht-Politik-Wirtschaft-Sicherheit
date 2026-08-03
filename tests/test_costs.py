from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest

from lagebericht.costs import CostDataError, berlin_month, estimate_cost, load_pricing


ROOT = Path(__file__).parents[1]


class CostCalculationTests(unittest.TestCase):
    def setUp(self):
        self.pricing = load_pricing(ROOT / "config" / "api-pricing.json")

    def write_pricing(self, value):
        handle = tempfile.NamedTemporaryFile(
            "w", suffix=".json", delete=False, encoding="utf-8"
        )
        with handle:
            json.dump(value, handle)
        path = Path(handle.name)
        self.addCleanup(path.unlink)
        return path

    def test_estimates_haiku_input_and_output_in_usd_and_eur(self):
        usd, eur = estimate_cost(
            "claude-haiku-4-5-20251001",
            {"input_tokens": 1_000_000, "output_tokens": 1_000_000},
            self.pricing,
        )

        self.assertEqual(usd, Decimal("6"))
        self.assertEqual(eur, Decimal("5.2680"))

    def test_estimates_sonnet_and_cache_tokens(self):
        usd, eur = estimate_cost(
            "claude-sonnet-4-6",
            {
                "input_tokens": 1_000_000,
                "output_tokens": 1_000_000,
                "cache_creation_input_tokens": 1_000_000,
                "cache_read_input_tokens": 1_000_000,
            },
            self.pricing,
        )

        self.assertEqual(usd, Decimal("22.05"))
        self.assertEqual(eur, Decimal("19.359900"))

    def test_missing_cache_counts_as_zero_without_losing_decimal_precision(self):
        usd, eur = estimate_cost(
            "claude-haiku-4-5-20251001",
            {"input_tokens": 1, "output_tokens": 1},
            self.pricing,
        )

        self.assertEqual(usd, Decimal("0.000006"))
        self.assertEqual(eur, Decimal("0.0000052680"))

    def test_rejects_unknown_model(self):
        with self.assertRaisesRegex(CostDataError, "unknown model"):
            estimate_cost(
                "unknown",
                {"input_tokens": 1, "output_tokens": 1},
                self.pricing,
            )

    def test_rejects_invalid_required_and_cache_token_values(self):
        invalid_values = (-1, True, "10", 1_000_000_001)
        for field in (
            "input_tokens",
            "output_tokens",
            "cache_creation_input_tokens",
            "cache_read_input_tokens",
        ):
            for value in invalid_values:
                with self.subTest(field=field, value=value):
                    usage = {"input_tokens": 1, "output_tokens": 1, field: value}
                    with self.assertRaisesRegex(CostDataError, field):
                        estimate_cost("claude-sonnet-4-6", usage, self.pricing)

    def test_rejects_missing_required_token_fields(self):
        for missing in ("input_tokens", "output_tokens"):
            with self.subTest(missing=missing):
                usage = {"input_tokens": 1, "output_tokens": 1}
                del usage[missing]
                with self.assertRaisesRegex(CostDataError, missing):
                    estimate_cost("claude-sonnet-4-6", usage, self.pricing)

    def test_load_pricing_parses_all_monetary_values_as_decimals(self):
        self.assertEqual(self.pricing["budgetEur"], Decimal("5.00"))
        self.assertEqual(self.pricing["usdToEur"], Decimal("0.8780"))
        self.assertEqual(
            self.pricing["models"]["claude-sonnet-4-6"]["cacheReadUsdPerMTok"],
            Decimal("0.30"),
        )

    def test_load_pricing_rejects_missing_and_non_string_monetary_fields(self):
        valid = {
            "schemaVersion": 1,
            "priceVersion": "test-v1",
            "budgetEur": "5.00",
            "usdToEur": "0.8780",
            "rateEffectiveDate": "2026-07-27",
            "collectionStartedAt": "2026-08-03T00:00:00+02:00",
            "models": {
                "model": {
                    "inputUsdPerMTok": "1.00",
                    "outputUsdPerMTok": "5.00",
                    "cacheWriteUsdPerMTok": "1.25",
                    "cacheReadUsdPerMTok": "0.10",
                }
            },
        }
        missing = json.loads(json.dumps(valid))
        del missing["models"]["model"]["outputUsdPerMTok"]
        numeric = json.loads(json.dumps(valid))
        numeric["usdToEur"] = 0.878

        for case in (missing, numeric):
            with self.subTest(case=case), self.assertRaises(CostDataError):
                load_pricing(self.write_pricing(case))

    def test_berlin_month_uses_local_midnight(self):
        self.assertEqual(
            berlin_month(datetime(2026, 7, 31, 22, 30, tzinfo=timezone.utc)),
            "2026-08",
        )

    def test_berlin_month_uses_winter_offset(self):
        self.assertEqual(
            berlin_month(datetime(2026, 1, 31, 22, 30, tzinfo=timezone.utc)),
            "2026-01",
        )

    def test_berlin_month_rejects_naive_datetime(self):
        with self.assertRaisesRegex(CostDataError, "timezone-aware"):
            berlin_month(datetime(2026, 8, 1, 0, 0))


if __name__ == "__main__":
    unittest.main()
