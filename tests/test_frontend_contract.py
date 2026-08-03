import json
import re
import subprocess
import unittest
from pathlib import Path

from lagebericht.schema import validate_daily_report, validate_period_report
from lagebericht.config import all_allowed_domains, load_sources


ROOT = Path(__file__).parents[1]
RATING_MODEL = ROOT / "assets" / "rating-model.js"
FRESHNESS_MODEL = ROOT / "assets" / "freshness-model.js"
PERIOD_MODEL = ROOT / "assets" / "period-model.js"
COST_MODEL = ROOT / "assets" / "cost-model.js"


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


def run_freshness(index, now):
    script = (
        "const model=require(process.argv[1]);"
        "const index=JSON.parse(process.argv[2]);"
        "process.stdout.write(JSON.stringify({"
        "date:model.berlinDateKey(new Date(process.argv[3])),"
        "notice:model.dailyNotice(index,new Date(process.argv[3]))}));"
    )
    result = subprocess.run(
        ["node", "-e", script, str(FRESHNESS_MODEL), json.dumps(index), now],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(result.stdout)


def run_period_model(report):
    script = (
        "const model=require(process.argv[1]);"
        "const report=JSON.parse(process.argv[2]);"
        "process.stdout.write(JSON.stringify(model.coverage(report)));"
    )
    result = subprocess.run(
        ["node", "-e", script, str(PERIOD_MODEL), json.dumps(report)],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(result.stdout)


def cost_report(**changes):
    value = {
        "schemaVersion": 1,
        "month": "2026-08",
        "budgetEur": 5.0,
        "estimatedCostEur": 0.84,
        "budgetPercent": 16.8,
        "unmeasuredCalls": 0,
        "collectionStartedAt": "2026-08-03T00:00:00+02:00",
    }
    value.update(changes)
    return value


def run_cost_model(report, now):
    script = (
        "const model=require(process.argv[1]);"
        "const report=JSON.parse(process.argv[2]);"
        "process.stdout.write(JSON.stringify(model.presentation(report,new Date(process.argv[3]))));"
    )
    result = subprocess.run(
        ["node", "-e", script, str(COST_MODEL), json.dumps(report), now],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(result.stdout)


def run_cost_path_check(path):
    script = (
        "const model=require(process.argv[1]);"
        "process.stdout.write(JSON.stringify(model.isAllowedCostPath(process.argv[2])));"
    )
    result = subprocess.run(
        ["node", "-e", script, str(COST_MODEL), path],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(result.stdout)


class FrontendContractTests(unittest.TestCase):
    def test_cost_model_presents_budget_percentage_and_caps_only_width(self):
        result = run_cost_model(cost_report(), "2026-08-03T12:00:00+02:00")

        self.assertEqual(result["percentLabel"], "16,8 %")
        self.assertEqual(result["widthPercent"], 16.8)
        self.assertEqual(result["tone"], "normal")
        self.assertIn("0,84", result["accessibleLabel"])
        self.assertEqual(result["tickLabels"], ["0 €", "1,25 €", "2,50 €", "3,75 €", "5 €"])

    def test_cost_model_marks_minimum_estimate_and_over_budget(self):
        result = run_cost_model(
            cost_report(estimatedCostEur=6.0, budgetPercent=120.0, unmeasuredCalls=2),
            "2026-08-03T12:00:00+02:00",
        )

        self.assertEqual(result["widthPercent"], 100)
        self.assertEqual(result["percentLabel"], "120,0 %")
        self.assertEqual(result["tone"], "over")
        self.assertIn("mindestens", result["estimateNote"])

    def test_cost_model_uses_warning_at_seventy_five_percent(self):
        result = run_cost_model(
            cost_report(estimatedCostEur=3.75, budgetPercent=75.0),
            "2026-08-03T12:00:00+02:00",
        )
        self.assertEqual(result["tone"], "warning")

    def test_cost_model_rejects_malformed_past_month_and_invalid_clock_data(self):
        malformed = cost_report(estimatedCostEur=-1, budgetPercent=-20)
        self.assertFalse(run_cost_model(malformed, "2026-08-03T12:00:00+02:00")["available"])
        self.assertFalse(run_cost_model(cost_report(month="2026-07"), "2026-08-03T12:00:00+02:00")["available"])
        self.assertFalse(run_cost_model(cost_report(), "not-a-date")["available"])

    def test_cost_model_uses_the_berlin_month_at_utc_boundary(self):
        result = run_cost_model(cost_report(), "2026-07-31T22:30:00Z")
        self.assertTrue(result["available"])
        self.assertEqual(result["monthLabel"], "August 2026")

    def test_cost_model_allows_only_strict_relative_monthly_cost_paths(self):
        self.assertTrue(run_cost_path_check("data/costs/2026-08.json"))
        for path in (
            "/data/costs/2026-08.json",
            "data/costs/2026-8.json",
            "data/costs/2026-08.json?x=1",
            "../data/costs/2026-08.json",
            "https://example.test/data/costs/2026-08.json",
        ):
            with self.subTest(path=path):
                self.assertFalse(run_cost_path_check(path))

    def test_cost_card_has_semantic_meter_and_safe_independent_rendering_contract(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        app = (ROOT / "assets" / "app.js").read_text(encoding="utf-8")
        model = COST_MODEL.read_text(encoding="utf-8")

        self.assertRegex(html, r'<section id="cost-meter"[^>]+aria-labelledby="cost-title"')
        self.assertRegex(html, r'<div id="cost-track"[^>]+role="meter"[^>]+aria-valuemin="0"[^>]+aria-valuemax="100"')
        self.assertLess(html.index("assets/cost-model.js"), html.index("assets/app.js"))
        self.assertIn("CostModel.isAllowedCostPath", app)
        self.assertIn("Kosten derzeit nicht verfügbar", model)
        self.assertIn("loadCurrentCosts", app)
        self.assertNotRegex(app, r"\.innerHTML\s*=")
        self.assertNotIn("document.write", app)

    def test_period_coverage_labels_partial_complete_and_snapshot_reports(self):
        cases = [
            ({"periodStart": "2026-07-27", "periodEnd": "2026-08-02", "sourceReportDates": ["2026-07-31", "2026-08-01", "2026-08-02"]},
             {"available": 3, "total": 7, "partial": True, "snapshot": False, "label": "Datenbasis: 3 von 7 Tagen · Teilüberblick"}),
            ({"periodStart": "2028-02-01", "periodEnd": "2028-02-29", "sourceReportDates": [f"2028-02-{day:02d}" for day in range(1, 30)]},
             {"available": 29, "total": 29, "partial": False, "snapshot": False, "label": "Datenbasis: 29 von 29 Tagen · Vollständig"}),
            ({"periodStart": "2026-07-27", "periodEnd": "2026-08-02", "sourceReportDates": ["2026-08-02"]},
             {"available": 1, "total": 7, "partial": True, "snapshot": True, "label": "Datenbasis: 1 von 7 Tagen · Momentaufnahme"}),
        ]
        for report, expected in cases:
            with self.subTest(expected=expected["label"]):
                self.assertEqual(run_period_model(report), expected)

    def test_period_model_and_context_are_loaded_and_rendered_safely(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        app = (ROOT / "assets" / "app.js").read_text(encoding="utf-8")
        worker = (ROOT / "service-worker.js").read_text(encoding="utf-8")
        self.assertLess(html.index("assets/period-model.js?v=8"), html.index("assets/app.js?v=8"))
        self.assertIn("PeriodModel.coverage(report)", app)
        self.assertIn("Einordnung", app)
        self.assertIn("item.contextDe || []", app)
        self.assertNotRegex(app, r"\.innerHTML\s*=")
        self.assertIn("lagebericht-shell-v8", worker)
        self.assertIn("./assets/period-model.js?v=8", worker)
    def test_freshness_uses_berlin_date_and_reports_missing_today(self):
        result = run_freshness({"latestDaily": "2026-08-01"}, "2026-08-02T21:30:00Z")

        self.assertEqual(result["date"], "2026-08-02")
        self.assertIn("02.08.2026", result["notice"])
        self.assertIn("01.08.2026", result["notice"])

    def test_freshness_is_quiet_for_current_report(self):
        result = run_freshness({"latestDaily": "2026-08-02"}, "2026-08-02T04:40:00Z")

        self.assertEqual(result["notice"], "")

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

    def test_app_refreshes_index_when_pwa_becomes_visible(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        app = (ROOT / "assets" / "app.js").read_text(encoding="utf-8")
        worker = (ROOT / "service-worker.js").read_text(encoding="utf-8")

        self.assertLess(html.index("assets/freshness-model.js?v=8"), html.index("assets/app.js?v=8"))
        self.assertIn("visibilitychange", app)
        self.assertIn("document.visibilityState === 'visible'", app)
        self.assertIn("FreshnessModel.dailyNotice", app)
        self.assertIn("lagebericht-shell-v8", worker)
        self.assertIn("./assets/freshness-model.js?v=8", worker)

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
        self.assertIn("lagebericht-shell-v8", worker)
        self.assertIn("./assets/rating-model.js", worker)
        self.assertIn('assets/rating-model.js?v=8', html)
        self.assertIn('assets/app.js?v=8', html)
        self.assertIn("service-worker.js?v=8", app)
        self.assertIn("request.mode === 'navigate'", worker)
        self.assertIn("fetch(request)", worker)


if __name__ == "__main__":
    unittest.main()
