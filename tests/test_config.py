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


if __name__ == "__main__":
    unittest.main()

