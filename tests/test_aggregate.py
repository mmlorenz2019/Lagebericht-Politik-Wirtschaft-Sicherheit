import copy
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from lagebericht.aggregate import PeriodAggregator, load_period_reports
from lagebericht.publish import Publisher
from tests.test_schema import ALLOWED_DOMAINS, category, daily_report


class ContentAI:
    def __init__(self):
        self.models = []

    def generate_json(self, model, instructions, input_text, schema_name, schema):
        self.models.append(model)
        return {
            "overallSummary": ["Der Zeitraum war durch mehrere wichtige Entscheidungen geprägt."],
            "countries": [
                {"id": "usa", "label": "USA", "sections": [category("politics_society")]},
                {"id": "china", "label": "China", "sections": [category("economy_technology")]},
                {"id": "montenegro", "label": "Montenegro", "sections": [category("foreign_security")]},
            ],
        }


class AggregateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.publisher = Publisher(self.root, ALLOWED_DOMAINS)

    def publish_days(self, start: date, count: int):
        for offset in range(count):
            current = start + timedelta(days=offset)
            report = copy.deepcopy(daily_report())
            report["reportDate"] = current.isoformat()
            report["generatedAt"] = f"{current.isoformat()}T04:31:00Z"
            self.publisher.publish_daily(report)

    def test_load_period_reports_lists_missing_dates(self):
        self.publish_days(date(2026, 7, 27), 4)
        reports, missing = load_period_reports(self.root, date(2026, 7, 27), date(2026, 8, 2), ALLOWED_DOMAINS)
        self.assertEqual(len(reports), 4)
        self.assertEqual(missing, ["2026-07-31", "2026-08-01", "2026-08-02"])

    def test_builds_partial_week_with_four_days(self):
        self.publish_days(date(2026, 7, 27), 4)
        ai = ContentAI()
        report = PeriodAggregator(self.root, ai, ALLOWED_DOMAINS).build_week(date(2026, 8, 2))
        self.assertEqual(report["periodStart"], "2026-07-27")
        self.assertEqual(report["periodEnd"], "2026-08-02")
        self.assertEqual(report["status"], "partial")
        self.assertEqual(len(report["sourceReportDates"]), 4)
        self.assertEqual(ai.models, ["claude-sonnet-4-6"])

    def test_returns_none_when_week_has_fewer_than_four_days(self):
        self.publish_days(date(2026, 7, 27), 3)
        self.assertIsNone(PeriodAggregator(self.root, ContentAI(), ALLOWED_DOMAINS).build_week(date(2026, 8, 2)))

    def test_builds_leap_month_with_twenty_days(self):
        self.publish_days(date(2028, 2, 1), 20)
        report = PeriodAggregator(self.root, ContentAI(), ALLOWED_DOMAINS).build_month(2028, 2)
        self.assertEqual(report["periodEnd"], "2028-02-29")
        self.assertEqual(len(report["missingReportDates"]), 9)


if __name__ == "__main__":
    unittest.main()
