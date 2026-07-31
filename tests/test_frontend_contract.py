import json
import re
import unittest
from pathlib import Path

from lagebericht.schema import validate_daily_report, validate_period_report
from lagebericht.config import all_allowed_domains, load_sources


ROOT = Path(__file__).parents[1]


class FrontendContractTests(unittest.TestCase):
    def test_manifest_is_installable_and_local_only(self):
        manifest = json.loads((ROOT / "manifest.webmanifest").read_text(encoding="utf-8"))
        self.assertEqual(manifest["display"], "standalone")
        self.assertEqual(manifest["start_url"], "./")
        self.assertTrue(manifest["icons"])
        self.assertTrue(all(not icon["src"].startswith("http") for icon in manifest["icons"]))

    def test_html_registers_manifest_and_has_archive_controls(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn('rel="manifest"', html)
        self.assertIn('data-archive-type="daily"', html)
        self.assertIn('data-archive-type="weekly"', html)
        self.assertIn('data-archive-type="monthly"', html)
        self.assertIn("serviceWorker.register", (ROOT / "assets" / "app.js").read_text(encoding="utf-8"))

    def test_frontend_has_no_external_resources_or_dynamic_inner_html(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        script = (ROOT / "assets" / "app.js").read_text(encoding="utf-8")
        self.assertNotRegex(html, r'(src|href)="https?://')
        self.assertNotRegex(script, r"\.innerHTML\s*=")
        self.assertNotIn("document.write", script)
        self.assertIn("new URL(source.url)", script)

    def test_example_reports_satisfy_data_contracts(self):
        domains = all_allowed_domains(load_sources(ROOT / "config" / "sources.json"))
        daily = json.loads((ROOT / "data" / "daily" / "2026-07-31.json").read_text(encoding="utf-8"))
        weekly = json.loads((ROOT / "data" / "weekly" / "2026-W31.json").read_text(encoding="utf-8"))
        monthly = json.loads((ROOT / "data" / "monthly" / "2026-07.json").read_text(encoding="utf-8"))
        validate_daily_report(daily, domains)
        validate_period_report(weekly, domains)
        validate_period_report(monthly, domains)

    def test_service_worker_does_not_cache_cross_origin_requests(self):
        worker = (ROOT / "service-worker.js").read_text(encoding="utf-8")
        self.assertIn("url.origin !== self.location.origin", worker)
        self.assertIn("request.method !== 'GET'", worker)


if __name__ == "__main__":
    unittest.main()
