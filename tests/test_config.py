import json
import tempfile
import unittest
from pathlib import Path

from lagebericht.config import ConfigError, load_sources


def source(source_id="npr"):
    return {
        "id": source_id,
        "name": "NPR",
        "country": "usa",
        "categories": ["politics_society"],
        "feedUrl": "https://feeds.npr.org/1001/rss.xml",
        "allowedDomains": ["feeds.npr.org", "www.npr.org"],
        "type": "öffentlich-rechtlich",
        "language": "en",
        "retrieval": "rss",
        "paywall": False,
        "maxCandidates": 12,
    }


class ConfigTests(unittest.TestCase):
    def write_config(self, value):
        handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        with handle:
            json.dump(value, handle)
        self.addCleanup(Path(handle.name).unlink)
        return Path(handle.name)

    def test_loads_valid_source(self):
        result = load_sources(self.write_config({"sources": [source()]}))
        self.assertEqual(result[0].id, "npr")
        self.assertEqual(result[0].allowed_domains, frozenset({"feeds.npr.org", "www.npr.org"}))

    def test_rejects_duplicate_ids(self):
        with self.assertRaisesRegex(ConfigError, "duplicate source id"):
            load_sources(self.write_config({"sources": [source(), source()]}))

    def test_rejects_http_feed(self):
        item = source()
        item["feedUrl"] = "http://feeds.npr.org/1001/rss.xml"
        with self.assertRaisesRegex(ConfigError, "https"):
            load_sources(self.write_config({"sources": [item]}))

    def test_rejects_unknown_retrieval(self):
        item = source()
        item["retrieval"] = "browser"
        with self.assertRaisesRegex(ConfigError, "retrieval"):
            load_sources(self.write_config({"sources": [item]}))

    def test_scmp_uses_canonical_https_feed_without_insecure_redirect(self):
        config_path = Path(__file__).resolve().parents[1] / "config" / "sources.json"
        sources = load_sources(config_path)
        scmp = next(item for item in sources if item.id == "scmp-china")
        self.assertEqual(scmp.feed_url, "https://www.scmp.com/rss/4/feed/")

    def test_loads_eu_sources_covering_all_three_categories(self):
        config_path = Path(__file__).resolve().parents[1] / "config" / "sources.json"
        sources = load_sources(config_path)
        eu_sources = [item for item in sources if item.country == "eu"]
        self.assertGreaterEqual(len(eu_sources), 1)
        covered = {category for item in eu_sources for category in item.categories}
        self.assertEqual(covered, {"politics_society", "economy_technology", "foreign_security"})
        for item in eu_sources:
            self.assertEqual(item.retrieval, "rss")


if __name__ == "__main__":
    unittest.main()
