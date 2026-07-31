import json
import tempfile
import unittest
from pathlib import Path

from lagebericht.publish import Publisher, rebuild_index
from lagebericht.schema import ReportValidationError
from tests.test_schema import ALLOWED_DOMAINS, daily_report


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


if __name__ == "__main__":
    unittest.main()
