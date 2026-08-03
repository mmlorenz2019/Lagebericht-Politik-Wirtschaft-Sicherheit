from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest

from lagebericht.costs import (
    CostContext,
    CostDataError,
    CostRecorder,
    berlin_month,
    context_from_environment,
    estimate_cost,
    load_pricing,
    normalize_usage,
    validate_cost_report,
)


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

    def test_normalizes_usage_to_exactly_four_persistable_token_fields(self):
        normalized = normalize_usage(
            {
                "input_tokens": 12,
                "output_tokens": 4,
                "service_tier": "standard_only",
            }
        )

        self.assertEqual(
            normalized,
            {
                "input_tokens": 12,
                "output_tokens": 4,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
            },
        )

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

    def test_load_pricing_rejects_budget_other_than_five_euros(self):
        value = json.loads(
            (ROOT / "config" / "api-pricing.json").read_text(encoding="utf-8")
        )
        value["budgetEur"] = "6.00"

        with self.assertRaisesRegex(CostDataError, "budgetEur"):
            load_pricing(self.write_pricing(value))

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

    def test_load_pricing_wraps_invalid_utf8_as_cost_data_error(self):
        handle = tempfile.NamedTemporaryFile("wb", suffix=".json", delete=False)
        with handle:
            handle.write(b"\xff")
        path = Path(handle.name)
        self.addCleanup(path.unlink)

        with self.assertRaisesRegex(CostDataError, "cannot read pricing config"):
            load_pricing(path)

    def test_load_pricing_rejects_extreme_decimal_values(self):
        for extreme in (
            "1e1000000",
            "0.000000001",
            "00.10",
            "9" * 1000,
        ):
            with self.subTest(extreme=extreme[:20]):
                value = json.loads(
                    (ROOT / "config" / "api-pricing.json").read_text(
                        encoding="utf-8"
                    )
                )
                value["models"]["claude-haiku-4-5-20251001"][
                    "inputUsdPerMTok"
                ] = extreme
                with self.assertRaisesRegex(CostDataError, "inputUsdPerMTok"):
                    load_pricing(self.write_pricing(value))

    def test_load_pricing_rejects_exchange_rate_that_can_underflow_to_zero(self):
        value = json.loads(
            (ROOT / "config" / "api-pricing.json").read_text(encoding="utf-8")
        )
        value["usdToEur"] = "1e-999999999"

        with self.assertRaisesRegex(CostDataError, "usdToEur"):
            load_pricing(self.write_pricing(value))

    def test_estimate_cost_wraps_decimal_overflow_as_cost_data_error(self):
        extreme_pricing = {
            "models": {
                "model": {
                    "inputUsdPerMTok": Decimal("1e999999"),
                    "outputUsdPerMTok": Decimal("0"),
                    "cacheWriteUsdPerMTok": Decimal("0"),
                    "cacheReadUsdPerMTok": Decimal("0"),
                }
            },
            "usdToEur": Decimal("1"),
        }

        with self.assertRaisesRegex(CostDataError, "pricing"):
            estimate_cost(
                "model",
                {"input_tokens": 1_000_000_000, "output_tokens": 0},
                extreme_pricing,
            )

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

    def test_berlin_month_changes_at_summer_and_winter_local_midnight(self):
        cases = (
            (datetime(2026, 7, 31, 21, 59, tzinfo=timezone.utc), "2026-07"),
            (datetime(2026, 7, 31, 22, 0, tzinfo=timezone.utc), "2026-08"),
            (datetime(2026, 10, 31, 22, 59, tzinfo=timezone.utc), "2026-10"),
            (datetime(2026, 10, 31, 23, 0, tzinfo=timezone.utc), "2026-11"),
        )
        for moment, expected in cases:
            with self.subTest(moment=moment):
                self.assertEqual(berlin_month(moment), expected)

    def test_berlin_month_rejects_naive_datetime(self):
        with self.assertRaisesRegex(CostDataError, "timezone-aware"):
            berlin_month(datetime(2026, 8, 1, 0, 0))


class CostReportSchemaTests(unittest.TestCase):
    def setUp(self):
        self.schema = json.loads(
            (ROOT / "schemas" / "cost-report.schema.json").read_text(
                encoding="utf-8"
            )
        )

    def test_schema_requires_the_complete_normalized_usage_shape(self):
        usage = self.schema["$defs"]["usage"]
        expected = {
            "input_tokens",
            "output_tokens",
            "cache_creation_input_tokens",
            "cache_read_input_tokens",
        }

        self.assertFalse(usage["additionalProperties"])
        self.assertEqual(set(usage["required"]), expected)
        self.assertEqual(set(usage["properties"]), expected)

    def test_schema_conditions_cost_and_usage_fields_on_measured_state(self):
        event = self.schema["$defs"]["event"]
        condition = event["allOf"][0]

        self.assertIn("usage", event["required"])
        self.assertEqual(
            condition["if"]["properties"]["measured"], {"const": True}
        )
        self.assertEqual(
            condition["then"]["properties"]["usage"],
            {"$ref": "#/$defs/usage"},
        )
        for field in ("estimatedCostUsd", "estimatedCostEur"):
            self.assertEqual(
                condition["then"]["properties"][field]["type"], "number"
            )
            self.assertEqual(
                condition["else"]["properties"][field]["type"], "null"
            )
        self.assertEqual(
            condition["else"]["properties"]["usage"], {"type": "null"}
        )


class CostRecorderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.pricing_path = ROOT / "config" / "api-pricing.json"
        self.model = "claude-haiku-4-5-20251001"
        self.moment = datetime(2026, 8, 3, 10, 0, tzinfo=timezone.utc)
        self.now = lambda: self.moment

    def read_report(self):
        return json.loads(
            (self.root / "costs" / "2026-08.json").read_text(encoding="utf-8")
        )

    def write_pricing(self, **changes):
        value = json.loads(
            (ROOT / "config" / "api-pricing.json").read_text(encoding="utf-8")
        )
        value.update(changes)
        path = self.root / "pricing.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def test_context_uses_github_environment_or_local_defaults(self):
        self.assertEqual(
            context_from_environment("daily", "2026-08-03", {}),
            CostContext("daily", "2026-08-03", "local", "1"),
        )
        self.assertEqual(
            context_from_environment(
                "week",
                "2026-W31",
                {"GITHUB_RUN_ID": "77", "GITHUB_RUN_ATTEMPT": "2"},
            ),
            CostContext("week", "2026-W31", "77", "2"),
        )

    def test_recorder_writes_measured_and_unmeasured_events_and_rebuilds_index(self):
        recorder = CostRecorder(
            self.root,
            self.pricing_path,
            CostContext("daily", "2026-08-03", "run-7", "1"),
            now=self.now,
        )

        recorder.observe(
            self.model,
            {"input_tokens": 1000, "output_tokens": 200, "prompt": "private"},
            "end_turn",
        )
        recorder.observe("claude-sonnet-4-6", None, "transport_error")

        report = self.read_report()
        self.assertEqual(report["unmeasuredCalls"], 1)
        self.assertEqual(len(report["events"]), 2)
        self.assertTrue(report["events"][0]["measured"])
        self.assertFalse(report["events"][1]["measured"])
        self.assertEqual(
            set(report["events"][0]["usage"]),
            {
                "input_tokens",
                "output_tokens",
                "cache_creation_input_tokens",
                "cache_read_input_tokens",
            },
        )
        self.assertNotIn("private", json.dumps(report))
        self.assertTrue(validate_cost_report(report, expected_month="2026-08"))
        index = json.loads((self.root / "index.json").read_text(encoding="utf-8"))
        self.assertEqual(
            index["currentCosts"],
            {"month": "2026-08", "path": "data/costs/2026-08.json"},
        )

    def test_recorder_deduplicates_same_run_attempt_and_call_number(self):
        context = CostContext("daily", "2026-08-03", "run-7", "1")
        first = CostRecorder(self.root, self.pricing_path, context, now=self.now)
        first.observe(self.model, {"input_tokens": 10, "output_tokens": 5}, "end_turn")
        repeated = CostRecorder(self.root, self.pricing_path, context, now=self.now)
        repeated.observe(self.model, {"input_tokens": 10, "output_tokens": 5}, "end_turn")

        self.assertEqual(len(self.read_report()["events"]), 1)

    def test_recorder_marks_malformed_or_unpriced_usage_unmeasured(self):
        recorder = CostRecorder(
            self.root,
            self.pricing_path,
            CostContext("month", "2026-08", "run-8", "1"),
            now=self.now,
        )

        recorder.observe(
            self.model, {"input_tokens": -1, "output_tokens": 2}, "end_turn"
        )
        recorder.observe(
            "unknown-model", {"input_tokens": 1, "output_tokens": 2}, "refusal"
        )

        report = self.read_report()
        self.assertEqual(report["unmeasuredCalls"], 2)
        for event in report["events"]:
            self.assertFalse(event["measured"])
            self.assertIsNone(event["usage"])
            self.assertIsNone(event["estimatedCostUsd"])
            self.assertIsNone(event["estimatedCostEur"])

    def test_recorder_recomputes_totals_and_keeps_percentage_above_one_hundred(self):
        recorder = CostRecorder(
            self.root,
            self.pricing_path,
            CostContext("daily", "2026-08-03", "run-9", "1"),
            now=self.now,
        )

        recorder.observe(
            self.model,
            {"input_tokens": 1_000_000, "output_tokens": 1_000_000},
            "max_tokens",
        )

        report = self.read_report()
        self.assertEqual(report["estimatedCostUsd"], 6.0)
        self.assertEqual(report["estimatedCostEur"], 5.268)
        self.assertEqual(report["budgetPercent"], 105.4)

    def test_recorder_rejects_unknown_outcome_without_creating_a_ledger(self):
        recorder = CostRecorder(
            self.root,
            self.pricing_path,
            CostContext("daily", "2026-08-03", "run-10", "1"),
            now=self.now,
        )

        with self.assertRaisesRegex(CostDataError, "outcome"):
            recorder.observe(self.model, None, "other")

        self.assertFalse((self.root / "costs" / "2026-08.json").exists())

    def test_validator_rejects_sensitive_or_inconsistent_public_artifacts(self):
        recorder = CostRecorder(
            self.root,
            self.pricing_path,
            CostContext("daily", "2026-08-03", "run-11", "1"),
            now=self.now,
        )
        recorder.observe(self.model, {"input_tokens": 1, "output_tokens": 1}, "end_turn")
        valid = self.read_report()

        leaked = json.loads(json.dumps(valid))
        leaked["events"][0]["requestId"] = "provider-id"
        inconsistent = json.loads(json.dumps(valid))
        inconsistent["events"][0]["measured"] = False

        with self.assertRaises(CostDataError):
            validate_cost_report(leaked, expected_month="2026-08")
        with self.assertRaises(CostDataError):
            validate_cost_report(inconsistent, expected_month="2026-08")

    def test_recorder_rejects_changed_month_pricing_without_touching_existing_file(self):
        context = CostContext("daily", "2026-08-03", "run-12", "1")
        first = CostRecorder(self.root, self.pricing_path, context, now=self.now)
        first.observe(self.model, {"input_tokens": 1, "output_tokens": 1}, "end_turn")
        ledger = self.root / "costs" / "2026-08.json"
        original = ledger.read_bytes()

        changed_path = self.write_pricing(
            priceVersion="new-prices",
            usdToEur="0.9000",
            rateEffectiveDate="2026-08-01",
            collectionStartedAt="2026-08-04T00:00:00+02:00",
        )
        changed = CostRecorder(self.root, changed_path, context, now=self.now)

        with self.assertRaisesRegex(CostDataError, "pricing contract"):
            changed.observe(
                self.model, {"input_tokens": 2, "output_tokens": 2}, "end_turn"
            )
        self.assertEqual(ledger.read_bytes(), original)

    def test_validator_rejects_event_outside_its_berlin_month(self):
        recorder = CostRecorder(
            self.root,
            self.pricing_path,
            CostContext("daily", "2026-08-03", "run-13", "1"),
            now=self.now,
        )
        recorder.observe(self.model, {"input_tokens": 1, "output_tokens": 1}, "end_turn")
        report = self.read_report()
        report["events"][0]["occurredAt"] = "2026-08-31T22:00:00+00:00"

        with self.assertRaisesRegex(CostDataError, "occurredAt"):
            validate_cost_report(report, expected_month="2026-08")


if __name__ == "__main__":
    unittest.main()
