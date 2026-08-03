import copy
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from lagebericht.aggregate import PeriodAggregator, load_period_reports
from lagebericht.publish import Publisher
from tests.test_schema import ALLOWED_DOMAINS, daily_report, legacy_daily_report, period_category


class ContentAI:
    def __init__(self):
        self.models = []

    def generate_json(self, model, instructions, input_text, schema_name, schema):
        self.models.append(model)
        count = schema["properties"]["overallSummary"]["minItems"]
        return {
            "overallSummary": [f"Satz {index + 1}." for index in range(count)],
            "countries": [
                {"id": "usa", "label": "USA", "sections": [period_category("politics_society")]},
                {"id": "china", "label": "China", "sections": [period_category("economy_technology")]},
                {"id": "montenegro", "label": "Montenegro", "sections": [period_category("foreign_security")]},
            ],
        }


class OverlongSectionAI(ContentAI):
    def generate_json(self, model, instructions, input_text, schema_name, schema):
        content = super().generate_json(model, instructions, input_text, schema_name, schema)
        content["countries"][1]["sections"][0]["summaryDe"] = [
            f"Abschnittssatz {index + 1}." for index in range(7)
        ]
        return content


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
        self.assertEqual(report["schemaVersion"], 3)
        self.assertEqual(len(report["overallSummary"]), 8)
        section = report["countries"][0]["sections"][0]
        self.assertEqual(section["germanyRelevance"]["score"], 1)
        self.assertEqual(section["overallSignificance"]["score"], 2)

    def test_builds_version_two_week_from_legacy_daily_reports(self):
        for offset in range(4):
            current = date(2026, 7, 27) + timedelta(days=offset)
            report = legacy_daily_report()
            report["reportDate"] = current.isoformat()
            report["generatedAt"] = f"{current.isoformat()}T04:31:00Z"
            self.publisher.publish_daily(report)

        result = PeriodAggregator(self.root, ContentAI(), ALLOWED_DOMAINS).build_week(date(2026, 8, 2))

        self.assertEqual(result["schemaVersion"], 3)
        self.assertEqual(result["sourceReportDates"], [
            "2026-07-27", "2026-07-28", "2026-07-29", "2026-07-30",
        ])

    def test_builds_snapshot_week_from_one_day(self):
        self.publish_days(date(2026, 8, 2), 1)
        report = PeriodAggregator(self.root, ContentAI(), ALLOWED_DOMAINS).build_week(date(2026, 8, 2))
        self.assertEqual(report["schemaVersion"], 3)
        self.assertEqual(report["sourceReportDates"], ["2026-08-02"])
        self.assertEqual(len(report["overallSummary"]), 8)
        self.assertEqual(len(report["countries"][0]["sections"][0]["contextDe"]), 2)

    def test_truncates_model_section_that_exceeds_the_six_sentence_contract(self):
        self.publish_days(date(2026, 8, 2), 1)

        report = PeriodAggregator(self.root, OverlongSectionAI(), ALLOWED_DOMAINS).build_week(date(2026, 8, 2))

        self.assertEqual(len(report["countries"][1]["sections"][0]["summaryDe"]), 6)

    def test_returns_none_without_calling_ai_when_period_has_no_days(self):
        ai = ContentAI()
        self.assertIsNone(PeriodAggregator(self.root, ai, ALLOWED_DOMAINS).build_week(date(2026, 8, 2)))
        self.assertEqual(ai.models, [])

    def test_three_and_seven_days_produce_partial_and_complete_weeks(self):
        for count, expected_status, expected_missing in ((3, "partial", 4), (7, "complete", 0)):
            with self.subTest(count=count):
                with tempfile.TemporaryDirectory() as folder:
                    root = Path(folder)
                    publisher = Publisher(root, ALLOWED_DOMAINS)
                    for offset in range(count):
                        current = date(2026, 7, 27) + timedelta(days=offset)
                        report = copy.deepcopy(daily_report())
                        report["reportDate"] = current.isoformat()
                        report["generatedAt"] = f"{current.isoformat()}T04:31:00Z"
                        publisher.publish_daily(report)
                    result = PeriodAggregator(root, ContentAI(), ALLOWED_DOMAINS).build_week(date(2026, 8, 2))
                    self.assertEqual(result["status"], expected_status)
                    self.assertEqual(len(result["missingReportDates"]), expected_missing)

    def test_builds_leap_month_with_twenty_days(self):
        self.publish_days(date(2028, 2, 1), 20)
        report = PeriodAggregator(self.root, ContentAI(), ALLOWED_DOMAINS).build_month(2028, 2)
        self.assertEqual(report["periodEnd"], "2028-02-29")
        self.assertEqual(len(report["missingReportDates"]), 9)

    def test_month_requests_twelve_to_fifteen_summary_sentences(self):
        self.publish_days(date(2026, 7, 31), 1)
        report = PeriodAggregator(self.root, ContentAI(), ALLOWED_DOMAINS).build_month(2026, 7)
        self.assertEqual(len(report["overallSummary"]), 12)

    def test_complete_leap_month_has_no_missing_days(self):
        self.publish_days(date(2028, 2, 1), 29)
        report = PeriodAggregator(self.root, ContentAI(), ALLOWED_DOMAINS).build_month(2028, 2)
        self.assertEqual(report["status"], "complete")
        self.assertEqual(len(report["sourceReportDates"]), 29)
        self.assertEqual(report["missingReportDates"], [])


if __name__ == "__main__":
    unittest.main()
