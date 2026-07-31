import json
import re
import subprocess
import unittest
from pathlib import Path

from lagebericht.schema import validate_daily_report, validate_period_report
from lagebericht.config import all_allowed_domains, load_sources


ROOT = Path(__file__).parents[1]
RATING_MODEL = ROOT / "assets" / "rating-model.js"


def run_rating_model(item):
    script = (
        "const model=require(process.argv[1]);"
        "const item=JSON.parse(process.argv[2]);"
        "process.stdout.write(JSON.stringify(model.ratingsForItem(item)));"
    )
    result = subprocess.run(
        ["node", "-e", script, str(RATING_MODEL), json.dumps(item, ensure_ascii=False)],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(result.stdout)


def run_story_badge(item):
    script = (
        "const model=require(process.argv[1]);"
        "const item=JSON.parse(process.argv[2]);"
        "const result=typeof model.badgeForItem==='function'?model.badgeForItem(item):null;"
        "process.stdout.write(JSON.stringify(result));"
    )
    result = subprocess.run(
        ["node", "-e", script, str(RATING_MODEL), json.dumps(item, ensure_ascii=False)],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(result.stdout)


class FrontendContractTests(unittest.TestCase):
    def test_version_two_ratings_keep_both_scores_and_reasons(self):
        self.assertTrue(RATING_MODEL.exists())
        result = run_rating_model({
            "germanyRelevance": {"score": 0, "reasonDe": "Kein direkter Bezug."},
            "overallSignificance": {"score": 3, "reasonDe": "Internationale Tragweite."},
        })
        self.assertEqual(result, [
            {
                "key": "germany", "label": "Deutschland-Bezug", "icon": "DE",
                "score": 0, "reasonDe": "Kein direkter Bezug.", "className": "rating-0",
                "legacy": False,
            },
            {
                "key": "overall", "label": "Allgemeine Tragweite", "icon": "⚡",
                "score": 3, "reasonDe": "Internationale Tragweite.", "className": "rating-3",
                "legacy": False,
            },
        ])

    def test_version_one_boolean_is_shown_without_invented_score(self):
        self.assertTrue(RATING_MODEL.exists())
        result = run_rating_model({"germanyRelevance": True})
        self.assertEqual(result, [{
            "key": "germany", "label": "Deutschland-Bezug", "icon": "DE",
            "score": None, "reasonDe": "Alter Datenstand ohne Punktbewertung.",
            "className": "rating-legacy", "legacy": True,
        }])

    def test_version_one_false_boolean_does_not_invent_a_rating(self):
        self.assertTrue(RATING_MODEL.exists())
        self.assertEqual(run_rating_model({"germanyRelevance": False}), [])

    def test_empty_category_ignores_stale_story_limitations(self):
        result = run_story_badge({
            "status": "no_major_development",
            "limitations": ["single_source", "source_disagreement"],
            "sourceBasis": "none",
        })
        self.assertEqual(result, "Keine neue Meldung")

    def test_manifest_is_installable_and_local_only(self):
        manifest = json.loads((ROOT / "manifest.webmanifest").read_text(encoding="utf-8"))
        self.assertEqual(manifest["display"], "standalone")
        self.assertEqual(manifest["start_url"], "./")
        self.assertTrue(manifest["icons"])
        self.assertTrue(all(not icon["src"].startswith("http") for icon in manifest["icons"]))
        sizes = {icon["sizes"] for icon in manifest["icons"] if icon["type"] == "image/png"}
        self.assertTrue({"192x192", "512x512"}.issubset(sizes))
        self.assertTrue((ROOT / "assets" / "icons" / "icon-192.png").exists())
        self.assertTrue((ROOT / "assets" / "icons" / "icon-512.png").exists())

    def test_html_registers_manifest_and_has_archive_controls(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn('rel="manifest"', html)
        self.assertIn('data-archive-type="daily"', html)
        self.assertIn('data-archive-type="weekly"', html)
        self.assertIn('data-archive-type="monthly"', html)
        self.assertNotIn("Beispieldaten", html)
        self.assertLess(html.index("assets/rating-model.js"), html.index("assets/app.js"))
        self.assertIn("serviceWorker.register", (ROOT / "assets" / "app.js").read_text(encoding="utf-8"))

    def test_empty_categories_do_not_claim_multiple_verification(self):
        app = (ROOT / "assets" / "app.js").read_text(encoding="utf-8")
        self.assertIn("Keine neue Meldung in den geprüften Quellen", app)
        self.assertNotIn("belanglose Meldung", app)

    def test_country_symbols_do_not_depend_on_emoji_flag_fonts(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("🇺🇸", html)
        self.assertEqual(html.count('class="country-code"'), 3)

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
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        app = (ROOT / "assets" / "app.js").read_text(encoding="utf-8")
        self.assertIn("url.origin !== self.location.origin", worker)
        self.assertIn("request.method !== 'GET'", worker)
        self.assertIn("lagebericht-shell-v6", worker)
        self.assertIn("./assets/rating-model.js", worker)
        self.assertIn('assets/rating-model.js?v=6', html)
        self.assertIn('assets/app.js?v=6', html)
        self.assertIn("service-worker.js?v=6", app)
        self.assertIn("request.mode === 'navigate'", worker)
        self.assertIn("fetch(request)", worker)


if __name__ == "__main__":
    unittest.main()
