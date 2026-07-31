import unittest
from pathlib import Path

from lagebericht.config import SourceConfig
from lagebericht.normalize import FeedNormalizationError, normalize_feed


FIXTURES = Path(__file__).parent / "fixtures"


def config(feed_url="https://feeds.npr.org/1001/rss.xml"):
    return SourceConfig(
        id="npr", name="NPR", country="usa",
        categories=("politics_society",), feed_url=feed_url,
        allowed_domains=frozenset({"feeds.npr.org", "www.npr.org", "www.cnbc.com"}),
        type="öffentlich-rechtlich", language="en", retrieval="rss",
        paywall=False, max_candidates=12,
    )


class NormalizeTests(unittest.TestCase):
    def test_normalizes_rss_and_removes_url_duplicate(self):
        articles = normalize_feed(config(), (FIXTURES / "sample-rss.xml").read_bytes())
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].title, "Politics & society update")
        self.assertEqual(articles[0].url, "https://www.npr.org/2026/07/31/example")
        self.assertEqual(articles[0].excerpt, "Important & verified.")
        self.assertEqual(articles[0].retrieval, "full")

    def test_normalizes_atom(self):
        articles = normalize_feed(config(), (FIXTURES / "sample-atom.xml").read_bytes())
        self.assertEqual(articles[0].title, "Economic update")
        self.assertEqual(articles[0].published_at, "2026-07-31T04:15:00Z")

    def test_rejects_doctype(self):
        payload = b'<?xml version="1.0"?><!DOCTYPE rss SYSTEM "file:///etc/passwd"><rss />'
        with self.assertRaisesRegex(FeedNormalizationError, "DOCTYPE"):
            normalize_feed(config(), payload)

    def test_ignores_article_on_foreign_domain(self):
        payload = b'<rss><channel><item><title>Bad</title><link>https://evil.example/a</link></item></channel></rss>'
        self.assertEqual(normalize_feed(config(), payload), [])


if __name__ == "__main__":
    unittest.main()
