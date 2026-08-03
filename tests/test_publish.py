import json
import tempfile
import unittest
from pathlib import Path

from lagebericht.publish import Publisher, rebuild_index
from lagebericht.schema import ReportValidationError
from tests.test_schema import ALLOWED_DOMAINS, daily_report


def valid_cost_report(month="2026-08"):
    return {
        "schemaVersion": 1,
        "month": month,
        "timezone": "Europe/Berlin",
        "budgetEur": 5.0,
        "estimatedCostUsd": 0.0,
        "estimatedCostEur": 0.0,
        "budgetPercent": 0.0,
        "unmeasuredCalls": 0,
        "collectionStartedAt": "2026-08-03T00:00:00+02:00",
        "priceVersion": "anthropic-2026-08-03",
        "rate": {"usdToEur": 0.878, "effectiveDate": "2026-07-27"},
        "events": [],
    }


class PublishTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.publisher = Publisher(self.root, ALLOWED_DOMAINS)

    def test_publishes_valid_daily_report_and_index(self):
        path = self.publisher.publish_daily(daily_report())
        self.assertEqual(path, self.root / "daily" / "2026-07-31.json")
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["reportDate"], "2026-07-31")
        index = json.loads((self.root / "index.json").read_text(encoding="utf-8"))
        self.assertEqual(index["latestDaily"], "2026-07-31")
        self.assertEqual(index["daily"], [{"date": "2026-07-31", "path": "data/daily/2026-07-31.json"}])

    def test_rejects_invalid_report_without_changing_existing_file(self):
        path = self.publisher.publish_daily(daily_report())
        original = path.read_bytes()
        invalid = daily_report()
        invalid["countries"][0]["id"] = "bad"
        with self.assertRaises(ReportValidationError):
            self.publisher.publish_daily(invalid)
        self.assertEqual(path.read_bytes(), original)

    def test_rebuild_index_discovers_all_archive_types(self):
        for relative in ("daily/2026-07-30.json", "daily/2026-07-31.json"):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}", encoding="utf-8")
        for relative in ("weekly/2026-W31.json", "monthly/2026-07.json"):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps({"sourceReportDates": ["2026-07-30", "2026-07-31"]}),
                encoding="utf-8",
            )
        index = rebuild_index(self.root)
        self.assertEqual(index["latestDaily"], "2026-07-31")
        self.assertEqual(index["weekly"][0]["period"], "2026-W31")
        self.assertEqual(index["monthly"][0]["period"], "2026-07")

    def test_rebuild_index_hides_periods_without_backing_daily_reports(self):
        daily = self.root / "daily" / "2026-07-31.json"
        daily.parent.mkdir(parents=True)
        daily.write_text("{}", encoding="utf-8")
        weekly = self.root / "weekly" / "2026-W31.json"
        weekly.parent.mkdir(parents=True)
        weekly.write_text(
            json.dumps({"sourceReportDates": ["2026-07-30", "2026-07-31"]}),
            encoding="utf-8",
        )

        index = rebuild_index(self.root)

        self.assertEqual(index["weekly"], [])

    def test_rebuild_index_includes_partial_period_with_all_backing_daily_reports(self):
        source_dates = ["2026-07-31", "2026-08-01", "2026-08-02"]
        for value in source_dates:
            daily = self.root / "daily" / f"{value}.json"
            daily.parent.mkdir(parents=True, exist_ok=True)
            daily.write_text("{}", encoding="utf-8")
        weekly = self.root / "weekly" / "2026-W31.json"
        weekly.parent.mkdir(parents=True)
        weekly.write_text(json.dumps({
            "sourceReportDates": source_dates,
            "missingReportDates": [
                "2026-07-27", "2026-07-28", "2026-07-29", "2026-07-30",
            ],
        }), encoding="utf-8")

        index = rebuild_index(self.root)

        self.assertEqual(index["weekly"], [{
            "period": "2026-W31",
            "path": "data/weekly/2026-W31.json",
        }])

    def test_rebuild_index_exposes_latest_valid_cost_month(self):
        costs = self.root / "costs" / "2026-08.json"
        costs.parent.mkdir(parents=True)
        costs.write_text(json.dumps(valid_cost_report()), encoding="utf-8")

        index = rebuild_index(self.root)

        self.assertEqual(index["schemaVersion"], 2)
        self.assertEqual(
            index["currentCosts"],
            {"month": "2026-08", "path": "data/costs/2026-08.json"},
        )

    def test_rebuild_index_skips_newer_invalid_or_mismatched_cost_artifacts(self):
        costs = self.root / "costs"
        costs.mkdir(parents=True)
        (costs / "2026-08.json").write_text(
            json.dumps(valid_cost_report("2026-08")), encoding="utf-8"
        )
        incomplete = {"schemaVersion": 1, "month": "2026-10"}
        (costs / "2026-10.json").write_text(json.dumps(incomplete), encoding="utf-8")
        (costs / "2026-09.json").write_text(
            json.dumps(valid_cost_report("2026-07")), encoding="utf-8"
        )

        index = rebuild_index(self.root)

        self.assertEqual(
            index["currentCosts"],
            {"month": "2026-08", "path": "data/costs/2026-08.json"},
        )

    def test_rebuild_index_returns_null_when_no_cost_artifact_is_valid(self):
        costs = self.root / "costs" / "2026-08.json"
        costs.parent.mkdir(parents=True)
        costs.write_text("not json", encoding="utf-8")

        index = rebuild_index(self.root)

        self.assertIsNone(index["currentCosts"])

    def test_rebuild_index_controls_extreme_decimal_data_in_cost_artifact(self):
        costs = self.root / "costs" / "2026-08.json"
        costs.parent.mkdir(parents=True)
        report = valid_cost_report()
        report["estimatedCostUsd"] = 1e300
        report["estimatedCostEur"] = 1e300
        report["events"] = [{
            "eventId": "a" * 64,
            "occurredAt": "2026-08-03T10:00:00+00:00",
            "reportType": "daily",
            "reportId": "2026-08-03",
            "model": "claude-haiku-4-5-20251001",
            "outcome": "end_turn",
            "measured": True,
            "usage": {
                "input_tokens": 0,
                "output_tokens": 0,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
            },
            "estimatedCostUsd": 1e300,
            "estimatedCostEur": 1e300,
        }]
        costs.write_text(json.dumps(report), encoding="utf-8")

        index = rebuild_index(self.root)

        self.assertIsNone(index["currentCosts"])


if __name__ == "__main__":
    unittest.main()
