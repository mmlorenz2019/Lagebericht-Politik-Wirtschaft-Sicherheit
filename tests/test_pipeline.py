import unittest
from dataclasses import replace
from datetime import date

from lagebericht.config import SourceConfig
from lagebericht.fetch import FetchError, FetchResult
from lagebericht.pipeline import DailyPipeline, PipelineError
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

    def generate_json(self, model, instructions, input_text, schema_name, schema):
        self.models.append(model)
        return self.values.pop(0)


class PipelineTests(unittest.TestCase):
    def test_builds_and_validates_daily_report_with_two_models(self):
        report = daily_report()
        ai = QueueAI([{"events": [{"id": "event-1"}]}, report])
        pipeline = DailyPipeline([SOURCE], FakeFetcher(), ai, ALLOWED_DOMAINS)
        result = pipeline.run(date(2026, 7, 31))
        self.assertEqual(result["reportDate"], "2026-07-31")
        self.assertEqual(ai.models, ["gpt-5.6-luna", "gpt-5.6-terra"])

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
