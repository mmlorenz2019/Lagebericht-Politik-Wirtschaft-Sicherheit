import copy
import json
import tempfile
import unittest
from pathlib import Path

from lagebericht.anthropic_client import AnthropicError
from lagebericht.translate import TranslationError, publish_translation, translate_report
from tests.test_schema import ALLOWED_DOMAINS, daily_report, period_category

ROOT = Path(__file__).resolve().parents[1]
DAILY_SCHEMA_PATH = ROOT / "schemas" / "daily-report.schema.json"
PERIOD_SCHEMA_PATH = ROOT / "schemas" / "period-report.schema.json"


class RecordingAI:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def generate_json(self, model, instructions, input_text, schema_name, schema):
        self.calls.append({"model": model, "input_text": input_text, "schema": schema})
        if self.error is not None:
            raise self.error
        return copy.deepcopy(self.response)


def english_daily_translation(report):
    translated = copy.deepcopy(report)
    for country in translated["countries"]:
        for cat in country["categories"]:
            if cat["status"] != "published":
                continue
            cat["headlineDe"] = f"EN: {cat['headlineDe']}"
            cat["summaryDe"] = [f"EN sentence {i + 1}." for i in range(len(cat["summaryDe"]))]
            if cat["germanyRelevance"] is not None:
                cat["germanyRelevance"] = {"score": 0, "reasonDe": "EN reason (and a corrupted score)"}
            if cat["overallSignificance"] is not None:
                cat["overallSignificance"] = {"score": 0, "reasonDe": "EN reason (and a corrupted score)"}
            for source in cat["sources"]:
                source["type"] = f"EN {source['type']}"
                source["url"] = "https://example.invalid/tampered"  # must never survive the merge
    return translated


class TranslateDailyReportTests(unittest.TestCase):
    def test_translates_text_fields_and_ignores_tampered_preserve_fields(self):
        report = daily_report()
        ai = RecordingAI(response=english_daily_translation(report))
        result = translate_report(report, ai, ALLOWED_DOMAINS, DAILY_SCHEMA_PATH)

        translated_category = result["countries"][0]["categories"][0]
        original_category = report["countries"][0]["categories"][0]
        self.assertTrue(translated_category["headlineDe"].startswith("EN: "))
        self.assertEqual(translated_category["summaryDe"][0], "EN sentence 1.")
        # Preserved: the score must come from the ORIGINAL report, not the (corrupted) translation.
        self.assertEqual(translated_category["germanyRelevance"]["score"], original_category["germanyRelevance"]["score"])
        self.assertEqual(translated_category["germanyRelevance"]["reasonDe"], "EN reason (and a corrupted score)")
        # Preserved: the URL must come from the ORIGINAL report, never the model's output.
        self.assertEqual(translated_category["sources"][0]["url"], original_category["sources"][0]["url"])
        self.assertEqual(translated_category["sources"][0]["name"], original_category["sources"][0]["name"])
        self.assertEqual(translated_category["sources"][0]["type"], "EN öffentlich-rechtlich")

    def test_preserves_ids_and_report_metadata_unchanged(self):
        report = daily_report()
        ai = RecordingAI(response=english_daily_translation(report))
        result = translate_report(report, ai, ALLOWED_DOMAINS, DAILY_SCHEMA_PATH)
        self.assertEqual(result["reportDate"], report["reportDate"])
        self.assertEqual(result["schemaVersion"], report["schemaVersion"])
        self.assertEqual([c["id"] for c in result["countries"]], [c["id"] for c in report["countries"]])

    def test_raises_translation_error_when_the_ai_call_fails(self):
        report = daily_report()
        ai = RecordingAI(error=AnthropicError("boom"))
        with self.assertRaises(TranslationError):
            translate_report(report, ai, ALLOWED_DOMAINS, DAILY_SCHEMA_PATH)

    def test_raises_translation_error_when_merged_result_fails_validation(self):
        report = daily_report()
        broken = english_daily_translation(report)
        broken["countries"][0]["categories"][0]["headlineDe"] = "x" * 500  # exceeds maxLength 180
        ai = RecordingAI(response=broken)
        with self.assertRaises(TranslationError):
            translate_report(report, ai, ALLOWED_DOMAINS, DAILY_SCHEMA_PATH)

    def test_never_invents_additional_important_that_was_null(self):
        report = daily_report()
        self.assertIsNone(report["countries"][0]["categories"][0]["additionalImportant"])
        translated = english_daily_translation(report)
        translated["countries"][0]["categories"][0]["additionalImportant"] = "EN: invented text"
        ai = RecordingAI(response=translated)
        result = translate_report(report, ai, ALLOWED_DOMAINS, DAILY_SCHEMA_PATH)
        self.assertIsNone(result["countries"][0]["categories"][0]["additionalImportant"])

    def test_passes_the_daily_schema_to_the_ai_call(self):
        report = daily_report()
        ai = RecordingAI(response=english_daily_translation(report))
        translate_report(report, ai, ALLOWED_DOMAINS, DAILY_SCHEMA_PATH, model="claude-haiku-4-5-20251001")
        self.assertEqual(ai.calls[0]["model"], "claude-haiku-4-5-20251001")
        self.assertEqual(ai.calls[0]["schema"], json.loads(DAILY_SCHEMA_PATH.read_text(encoding="utf-8")))


def _valid_period_report(period_type="week"):
    # Standalone equivalent of PeriodReportValidationTests.valid_period_v3() in
    # tests/test_schema.py, which is an instance method and not importable
    # directly. Kept in lockstep with that method's shape (schemaVersion 3,
    # period_category() sections including contextDe) since it is what the
    # real schemas/period-report.schema.json requires.
    report = {
        "schemaVersion": 3,
        "periodType": period_type,
        "periodStart": "2026-07-27" if period_type == "week" else "2026-07-01",
        "periodEnd": "2026-08-02" if period_type == "week" else "2026-07-31",
        "generatedAt": "2026-08-02T05:00:00Z",
        "status": "partial",
        "overallSummary": [f"Satz {index + 1}." for index in range(8 if period_type == "week" else 12)],
        "countries": [
            {"id": "usa", "label": "USA", "sections": [period_category("politics_society")]},
            {"id": "china", "label": "China", "sections": [period_category("economy_technology")]},
            {"id": "montenegro", "label": "Montenegro", "sections": [period_category("foreign_security")]},
            {"id": "eu", "label": "EU", "sections": [period_category("politics_society")]},
        ],
        "sourceReportDates": (
            ["2026-07-27", "2026-07-28", "2026-07-30", "2026-08-02"]
            if period_type == "week"
            else ["2026-07-27", "2026-07-28", "2026-07-30", "2026-07-31"]
        ),
        "missingReportDates": (
            ["2026-07-29", "2026-07-31", "2026-08-01"] if period_type == "week" else ["2026-07-29"]
        ),
    }
    return report


class TranslatePeriodReportTests(unittest.TestCase):
    def _period_report(self):
        return _valid_period_report()

    def _english_period_translation(self, report):
        translated = copy.deepcopy(report)
        translated["overallSummary"] = [f"EN overall {i + 1}." for i in range(len(report["overallSummary"]))]
        for country in translated["countries"]:
            for section in country["sections"]:
                if section["status"] != "published":
                    continue
                section["headlineDe"] = f"EN: {section['headlineDe']}"
                section["summaryDe"] = [f"EN sentence {i + 1}." for i in range(len(section["summaryDe"]))]
                section["contextDe"] = [f"EN context {i + 1}." for i in range(len(section.get("contextDe") or []))]
        return translated

    def test_translates_overall_summary_and_context_de(self):
        report = self._period_report()
        ai = RecordingAI(response=self._english_period_translation(report))
        result = translate_report(report, ai, ALLOWED_DOMAINS, PERIOD_SCHEMA_PATH)
        self.assertTrue(result["overallSummary"][0].startswith("EN overall"))
        section = result["countries"][0]["sections"][0]
        if report["countries"][0]["sections"][0].get("contextDe"):
            self.assertTrue(section["contextDe"][0].startswith("EN context"))

    def test_falls_back_to_original_overall_summary_on_length_mismatch(self):
        report = self._period_report()
        translated = self._english_period_translation(report)
        translated["overallSummary"] = translated["overallSummary"][:1]
        ai = RecordingAI(response=translated)
        result = translate_report(report, ai, ALLOWED_DOMAINS, PERIOD_SCHEMA_PATH)
        self.assertEqual(result["overallSummary"], report["overallSummary"])


class PublishTranslationTests(unittest.TestCase):
    def test_publishes_an_english_mirror_with_a_correctly_prefixed_index_path(self):
        report = daily_report()
        ai = RecordingAI(response=english_daily_translation(report))
        with tempfile.TemporaryDirectory() as folder:
            data_root = Path(folder)
            path = publish_translation(
                report, ai, ALLOWED_DOMAINS, DAILY_SCHEMA_PATH, data_root, "publish_daily"
            )
            self.assertEqual(path, data_root / "en" / "daily" / "2026-07-31.json")
            index = json.loads((data_root / "en" / "index.json").read_text(encoding="utf-8"))
            self.assertEqual(
                index["daily"][0]["path"], f"{data_root.as_posix()}/en/daily/2026-07-31.json"
            )

    def test_propagates_translation_error_without_publishing_anything(self):
        report = daily_report()
        ai = RecordingAI(error=AnthropicError("boom"))
        with tempfile.TemporaryDirectory() as folder:
            data_root = Path(folder)
            with self.assertRaises(TranslationError):
                publish_translation(
                    report, ai, ALLOWED_DOMAINS, DAILY_SCHEMA_PATH, data_root, "publish_daily"
                )
            self.assertFalse((data_root / "en").exists())

    def test_works_for_period_reports_via_publish_period(self):
        report = _valid_period_report()
        translated = copy.deepcopy(report)
        translated["overallSummary"] = [f"EN {i + 1}." for i in range(len(report["overallSummary"]))]
        ai = RecordingAI(response=translated)
        with tempfile.TemporaryDirectory() as folder:
            data_root = Path(folder)
            path = publish_translation(
                report, ai, ALLOWED_DOMAINS, PERIOD_SCHEMA_PATH, data_root, "publish_period"
            )
            self.assertTrue(path.exists())
            self.assertIn("weekly", path.parts)
