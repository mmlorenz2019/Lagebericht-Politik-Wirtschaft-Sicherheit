import unittest

from lagebericht.schema import (
    ReportValidationError,
    validate_daily_report,
    validate_period_report,
)


ALLOWED_DOMAINS = {
    "npr.org",
    "www.npr.org",
    "nytimes.com",
    "www.nytimes.com",
    "cnbc.com",
    "www.cnbc.com",
    "pbs.org",
    "www.pbs.org",
    "caixinglobal.com",
    "www.caixinglobal.com",
    "scmp.com",
    "www.scmp.com",
    "chinadaily.com.cn",
    "www.chinadaily.com.cn",
    "vijesti.me",
    "www.vijesti.me",
    "pobjeda.me",
    "www.pobjeda.me",
}


def category(category_id="politics_society"):
    return {
        "id": category_id,
        "status": "published",
        "headlineDe": "Eine wichtige Entwicklung",
        "summaryDe": [
            "Der erste Satz ordnet die Entwicklung ein.",
            "Der zweite Satz beschreibt die Entscheidung.",
            "Der dritte Satz erklärt die möglichen Folgen.",
            "Der vierte Satz nennt den aktuellen Stand.",
        ],
        "additionalImportant": None,
        "germanyRelevance": False,
        "sourceBasis": "single",
        "limitations": ["single_source"],
        "sources": [
            {
                "name": "NPR",
                "type": "öffentlich-rechtlich",
                "titleOriginal": "An important development",
                "url": "https://www.npr.org/example",
                "publishedAt": "2026-07-31T03:50:00Z",
            }
        ],
    }


def daily_report():
    return {
        "schemaVersion": 1,
        "reportDate": "2026-07-31",
        "generatedAt": "2026-07-31T04:31:00Z",
        "status": "partial",
        "countries": [
            {
                "id": "usa",
                "label": "USA",
                "categories": [
                    category("politics_society"),
                    {**category("economy_technology"), "status": "no_major_development", "headlineDe": "", "summaryDe": [], "sourceBasis": "none", "limitations": [], "sources": []},
                    {**category("foreign_security"), "status": "unavailable", "headlineDe": "", "summaryDe": [], "sourceBasis": "none", "limitations": ["technical_failure"], "sources": []},
                ],
            },
            {"id": "china", "label": "China", "categories": [category("politics_society"), category("economy_technology"), category("foreign_security")]},
            {"id": "montenegro", "label": "Montenegro", "categories": [category("politics_society"), category("economy_technology"), category("foreign_security")]},
        ],
    }


class DailyReportValidationTests(unittest.TestCase):
    def test_accepts_valid_daily_report(self):
        validate_daily_report(daily_report(), ALLOWED_DOMAINS)

    def test_rejects_unknown_country(self):
        report = daily_report()
        report["countries"][0]["id"] = "germany"
        with self.assertRaisesRegex(ReportValidationError, "countries\\[0\\].id"):
            validate_daily_report(report, ALLOWED_DOMAINS)

    def test_rejects_javascript_source_url(self):
        report = daily_report()
        report["countries"][0]["categories"][0]["sources"][0]["url"] = "javascript:alert(1)"
        with self.assertRaisesRegex(ReportValidationError, "sources\\[0\\].url"):
            validate_daily_report(report, ALLOWED_DOMAINS)

    def test_rejects_source_outside_allowlist(self):
        report = daily_report()
        report["countries"][0]["categories"][0]["sources"][0]["url"] = "https://attacker.example/news"
        with self.assertRaisesRegex(ReportValidationError, "not allowlisted"):
            validate_daily_report(report, ALLOWED_DOMAINS)

    def test_rejects_too_long_headline(self):
        report = daily_report()
        report["countries"][0]["categories"][0]["headlineDe"] = "x" * 181
        with self.assertRaisesRegex(ReportValidationError, "headlineDe"):
            validate_daily_report(report, ALLOWED_DOMAINS)

    def test_rejects_unknown_top_level_field(self):
        report = daily_report()
        report["debug"] = True
        with self.assertRaisesRegex(ReportValidationError, "unknown field"):
            validate_daily_report(report, ALLOWED_DOMAINS)


class PeriodReportValidationTests(unittest.TestCase):
    def test_accepts_valid_weekly_report(self):
        report = {
            "schemaVersion": 1,
            "periodType": "week",
            "periodStart": "2026-07-27",
            "periodEnd": "2026-08-02",
            "generatedAt": "2026-08-02T05:00:00Z",
            "status": "partial",
            "overallSummary": ["Die Woche war von mehreren politischen und wirtschaftlichen Entscheidungen geprägt."],
            "countries": [
                {"id": "usa", "label": "USA", "sections": [category("politics_society")]},
                {"id": "china", "label": "China", "sections": [category("economy_technology")]},
                {"id": "montenegro", "label": "Montenegro", "sections": [category("foreign_security")]},
            ],
            "sourceReportDates": ["2026-07-27", "2026-07-28", "2026-07-30", "2026-08-02"],
            "missingReportDates": ["2026-07-29", "2026-07-31", "2026-08-01"],
        }
        validate_period_report(report, ALLOWED_DOMAINS)

    def test_rejects_unknown_period_type(self):
        report = {
            "schemaVersion": 1,
            "periodType": "quarter",
            "periodStart": "2026-07-01",
            "periodEnd": "2026-09-30",
            "generatedAt": "2026-09-30T05:00:00Z",
            "status": "complete",
            "overallSummary": ["Zusammenfassung."],
            "countries": [],
            "sourceReportDates": [],
            "missingReportDates": [],
        }
        with self.assertRaisesRegex(ReportValidationError, "periodType"):
            validate_period_report(report, ALLOWED_DOMAINS)


if __name__ == "__main__":
    unittest.main()
