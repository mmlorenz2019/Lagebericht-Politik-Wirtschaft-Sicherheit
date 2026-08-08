import unittest
from dataclasses import replace
from datetime import date

from lagebericht.config import SourceConfig
from lagebericht.fetch import FetchError, FetchResult
from lagebericht.pipeline import DailyPipeline, PipelineError
from lagebericht.schema import COUNTRIES
from tests.test_schema import ALLOWED_DOMAINS, daily_report


SOURCE = SourceConfig(
    id="npr", name="NPR", country="usa", categories=("politics_society",),
    feed_url="https://feeds.npr.org/test.xml", allowed_domains=frozenset({"feeds.npr.org", "www.npr.org"}),
    type="öffentlich-rechtlich", language="en", retrieval="rss", paywall=False, max_candidates=10,
)
RSS = b'<rss><channel><item><title>Vote</title><link>https://www.npr.org/vote</link><pubDate>Fri, 31 Jul 2026 04:00:00 GMT</pubDate><description>Decision</description></item></channel></rss>'


class FakeFetcher:
    def __init__(self, fail=False):
        self.fail = fail

    def fetch(self, url, allowed_domains):
        if self.fail:
            raise FetchError("offline")
        return FetchResult(RSS, url, "application/rss+xml", "full")


class QueueAI:
    def __init__(self, values):
        self.values = list(values)
        self.models = []
        self.input_texts = []
        self.schema_names = []
        self.schemas = []

    def generate_json(self, model, instructions, input_text, schema_name, schema):
        self.models.append(model)
        self.input_texts.append(input_text)
        self.schema_names.append(schema_name)
        self.schemas.append(schema)
        return self.values.pop(0)


def complete_event():
    return {
        "id": "event-1",
        "country": "usa",
        "category": "politics_society",
        "summary": "A decision was announced.",
        "candidateIndexes": [0],
        "contradictions": False,
    }


def daily_report_with_empty_usa_politics():
    report = daily_report()
    report["countries"][0]["categories"][0].update({
        "status": "no_major_development",
        "headlineDe": "",
        "summaryDe": [],
        "additionalImportant": None,
        "germanyRelevance": None,
        "overallSignificance": None,
        "sourceBasis": "none",
        "limitations": [],
        "sources": [],
    })
    return report


class PipelineTests(unittest.TestCase):
    def test_retries_when_model_hides_an_event_with_sources(self):
        ai = QueueAI([
            {"events": [complete_event()]},
            daily_report_with_empty_usa_politics(),
            daily_report(),
        ])

        result = DailyPipeline([SOURCE], FakeFetcher(), ai, ALLOWED_DOMAINS).run(date(2026, 7, 31))

        self.assertEqual(result["countries"][0]["categories"][0]["status"], "published")
        self.assertEqual(ai.models.count("claude-sonnet-4-6"), 2)

    def test_retries_when_published_category_is_incomplete(self):
        invalid_report = daily_report()
        invalid_report["countries"][0]["categories"][0]["headlineDe"] = ""
        ai = QueueAI([
            {"events": [complete_event()]},
            invalid_report,
            daily_report(),
        ])

        result = DailyPipeline([SOURCE], FakeFetcher(), ai, ALLOWED_DOMAINS).run(date(2026, 8, 1))

        self.assertTrue(result["countries"][0]["categories"][0]["headlineDe"])
        self.assertEqual(ai.models.count("claude-sonnet-4-6"), 2)
        self.assertIn("published categories require", ai.input_texts[2])

    def test_does_not_retry_when_no_sourced_event_exists_for_empty_slot(self):
        ai = QueueAI([{"events": []}, daily_report_with_empty_usa_politics()])

        DailyPipeline([SOURCE], FakeFetcher(), ai, ALLOWED_DOMAINS).run(date(2026, 7, 31))

        self.assertEqual(ai.models.count("claude-sonnet-4-6"), 1)

    def test_fails_when_repair_still_hides_a_sourced_event(self):
        ai = QueueAI([
            {"events": [complete_event()]},
            daily_report_with_empty_usa_politics(),
            daily_report_with_empty_usa_politics(),
        ])

        with self.assertRaisesRegex(PipelineError, "omitted sourced slots"):
            DailyPipeline([SOURCE], FakeFetcher(), ai, ALLOWED_DOMAINS).run(date(2026, 7, 31))

    def test_publishes_a_low_scored_single_source_event_without_retry(self):
        report = daily_report()
        item = report["countries"][0]["categories"][0]
        item["germanyRelevance"] = {"score": 0, "reasonDe": "Kein direkter Bezug zu Deutschland."}
        item["overallSignificance"] = {"score": 0, "reasonDe": "Die Entwicklung ist bislang begrenzt."}
        ai = QueueAI([{"events": [complete_event()]}, report])

        result = DailyPipeline([SOURCE], FakeFetcher(), ai, ALLOWED_DOMAINS).run(date(2026, 7, 31))

        published = result["countries"][0]["categories"][0]
        self.assertEqual(published["status"], "published")
        self.assertEqual(published["sourceBasis"], "single")
        self.assertEqual(ai.models.count("claude-sonnet-4-6"), 1)
    def test_builds_and_validates_daily_report_with_two_models(self):
        report = daily_report()
        ai = QueueAI([{"events": [{"id": "event-1"}]}, report])
        pipeline = DailyPipeline([SOURCE], FakeFetcher(), ai, ALLOWED_DOMAINS)
        result = pipeline.run(date(2026, 7, 31))
        self.assertEqual(result["reportDate"], "2026-07-31")
        self.assertEqual(ai.models, ["claude-haiku-4-5-20251001", "claude-sonnet-4-6"])

    def test_live_daily_report_schema_requires_every_configured_country(self):
        report = daily_report()
        ai = QueueAI([{"events": [{"id": "event-1"}]}, report])
        pipeline = DailyPipeline([SOURCE], FakeFetcher(), ai, ALLOWED_DOMAINS)

        pipeline.run(date(2026, 7, 31))

        daily_report_schemas = [
            schema for schema_name, schema in zip(ai.schema_names, ai.schemas)
            if schema_name == "daily_report"
        ]
        self.assertTrue(daily_report_schemas)
        for schema in daily_report_schemas:
            countries_schema = schema["properties"]["countries"]
            self.assertEqual(countries_schema["minItems"], len(COUNTRIES))
            self.assertEqual(countries_schema["maxItems"], len(COUNTRIES))

    def test_uses_requested_date_for_report_metadata(self):
        report = daily_report()
        report["reportDate"] = "2026-07-30"
        ai = QueueAI([{"events": [{"id": "event-1"}]}, report])
        pipeline = DailyPipeline([SOURCE], FakeFetcher(), ai, ALLOWED_DOMAINS)

        try:
            result = pipeline.run(date(2026, 7, 31))
        except PipelineError as exc:
            self.fail(f"requested report date was rejected: {exc}")

        self.assertEqual(result["reportDate"], "2026-07-31")

    def test_passes_original_source_metadata_to_summary_model(self):
        event = {
            "id": "event-1",
            "country": "usa",
            "category": "politics_society",
            "summary": "A decision was announced.",
            "candidateIndexes": [0],
            "contradictions": False,
        }
        ai = QueueAI([{"events": [event]}, daily_report()])
        pipeline = DailyPipeline([SOURCE], FakeFetcher(), ai, ALLOWED_DOMAINS)

        pipeline.run(date(2026, 7, 31))

        self.assertIn('"url": "https://www.npr.org/vote"', ai.input_texts[1])
        self.assertIn('"name": "NPR"', ai.input_texts[1])

    def test_clears_story_content_from_empty_categories(self):
        report = daily_report()
        category = report["countries"][0]["categories"][0]
        category["status"] = "no_major_development"
        category["additionalImportant"] = "Weitere Einzelheit"
        category["germanyRelevance"] = {"score": 3, "reasonDe": "Diese Angabe muss entfernt werden."}
        category["overallSignificance"] = {"score": 3, "reasonDe": "Diese Angabe muss entfernt werden."}
        ai = QueueAI([{"events": []}, report])
        pipeline = DailyPipeline([SOURCE], FakeFetcher(), ai, ALLOWED_DOMAINS)

        try:
            result = pipeline.run(date(2026, 7, 31))
        except ValueError as exc:
            self.fail(f"empty category was not normalized: {exc}")

        normalized = result["countries"][0]["categories"][0]
        self.assertEqual(normalized["headlineDe"], "")
        self.assertEqual(normalized["summaryDe"], [])
        self.assertIsNone(normalized["additionalImportant"])
        self.assertIsNone(normalized["germanyRelevance"])
        self.assertIsNone(normalized["overallSignificance"])
        self.assertEqual(normalized["sourceBasis"], "none")
        self.assertEqual(normalized["sources"], [])

    def test_fails_without_any_candidates(self):
        pipeline = DailyPipeline([SOURCE], FakeFetcher(fail=True), QueueAI([]), ALLOWED_DOMAINS)
        with self.assertRaisesRegex(PipelineError, "no source candidates"):
            pipeline.run(date(2026, 7, 31))

    def test_skips_html_sources_until_adapter_is_available(self):
        html_source = replace(SOURCE, id="caixin", retrieval="html")
        pipeline = DailyPipeline([html_source], FakeFetcher(), QueueAI([]), ALLOWED_DOMAINS)
        with self.assertRaisesRegex(PipelineError, "no source candidates"):
            pipeline.run(date(2026, 7, 31))


if __name__ == "__main__":
    unittest.main()
