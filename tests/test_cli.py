import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from lagebericht.costs import berlin_month


ROOT = Path(__file__).parents[1]


class DailyCliTests(unittest.TestCase):
    def test_daily_client_records_usage_with_local_context(self):
        import scripts.run_daily as run_daily

        def transport(url, headers, payload, timeout):
            return {
                "content": [{"type": "text", "text": '{"ok": true}'}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 10, "output_tokens": 4},
            }

        with tempfile.TemporaryDirectory() as folder:
            client = run_daily.build_daily_client(
                "test-key",
                Path(folder),
                date(2026, 8, 3),
                transport=transport,
                environ={},
            )
            self.assertEqual(
                client.generate_json(
                    "claude-haiku-4-5-20251001", "rules", "input", "schema", {}
                ),
                {"ok": True},
            )
            # The cost ledger files under the CURRENT Berlin billing month
            # (when the call actually happens), not the report_date passed
            # above - those are intentionally independent. Deriving the
            # expected filename the same way the production code does keeps
            # this test correct across every future month boundary, instead
            # of hardcoding the month the test happened to be written in.
            current_month = berlin_month(datetime.now(timezone.utc))
            ledger = json.loads(
                (Path(folder) / "costs" / f"{current_month}.json").read_text(encoding="utf-8")
            )

        self.assertEqual(ledger["events"][0]["reportType"], "daily")
        self.assertEqual(ledger["events"][0]["reportId"], "2026-08-03")

    def test_daily_client_still_works_when_cost_recorder_initialization_fails(self):
        import scripts.run_daily as run_daily

        original = run_daily.CostRecorder

        class BrokenRecorder:
            def __init__(self, *args, **kwargs):
                raise OSError("disk unavailable")

        def transport(url, headers, payload, timeout):
            return {
                "content": [{"type": "text", "text": '{"ok": true}'}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 10, "output_tokens": 4},
            }

        run_daily.CostRecorder = BrokenRecorder
        self.addCleanup(setattr, run_daily, "CostRecorder", original)
        client = run_daily.build_daily_client(
            "test-key", Path("unused"), date(2026, 8, 3), transport=transport, environ={}
        )

        self.assertEqual(
            client.generate_json("model", "rules", "input", "schema", {}),
            {"ok": True},
        )

    def test_period_client_allows_larger_structured_reports(self):
        import scripts.run_period as run_period

        self.assertTrue(hasattr(run_period, "build_period_client"))
        captured = {}

        def transport(url, headers, payload, timeout):
            captured.update(payload)
            captured["timeout"] = timeout
            return {
                "content": [{"type": "text", "text": '{"ok": true}'}],
                "stop_reason": "end_turn",
            }

        client = run_period.build_period_client("test-key", transport=transport)
        self.assertEqual(client.generate_json("model", "rules", "input", "schema", {}), {"ok": True})
        self.assertEqual(captured["max_tokens"], 16384)
        self.assertEqual(captured["timeout"], 1200.0)

    def test_period_client_preserves_usage_observer_injection(self):
        import scripts.run_period as run_period

        observer = lambda model, usage, outcome: None
        client = run_period.build_period_client("test-key", usage_observer=observer)

        self.assertIs(client.usage_observer, observer)

    def test_period_observers_record_canonical_week_and_month_contexts(self):
        import scripts.run_period as run_period

        def transport(url, headers, payload, timeout):
            return {
                "content": [{"type": "text", "text": '{"ok": true}'}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 10, "output_tokens": 4},
            }

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            week_observer = run_period.build_period_usage_observer(
                root,
                "week",
                run_period.week_report_id(date(2021, 1, 3)),
                environ={},
            )
            month_observer = run_period.build_period_usage_observer(
                root, "month", run_period.month_report_id(2021, 1), environ={}
            )
            for observer in (week_observer, month_observer):
                client = run_period.build_period_client(
                    "test-key", usage_observer=observer, transport=transport
                )
                self.assertEqual(
                    client.generate_json(
                        "claude-haiku-4-5-20251001", "rules", "input", "schema", {}
                    ),
                    {"ok": True},
                )
            ledger_path, = (root / "costs").glob("*.json")
            ledger = json.loads(ledger_path.read_text(encoding="utf-8"))

        self.assertEqual(
            [(event["reportType"], event["reportId"]) for event in ledger["events"]],
            [("week", "2020-W53"), ("month", "2021-01")],
        )

    def test_period_observer_falls_back_when_cost_configuration_is_unavailable(self):
        import scripts.run_period as run_period

        original = run_period.CostRecorder

        class BrokenRecorder:
            def __init__(self, *args, **kwargs):
                raise ValueError("bad pricing")

        run_period.CostRecorder = BrokenRecorder
        self.addCleanup(setattr, run_period, "CostRecorder", original)

        self.assertIsNone(
            run_period.build_period_usage_observer(
                Path("unused"), "week", "2026-W32", environ={}
            )
        )

    def test_help_lists_dry_run_and_date(self):
        env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
        result = subprocess.run([sys.executable, "scripts/run_daily.py", "--help"], cwd=ROOT, env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn("--dry-run", result.stdout)
        self.assertIn("--date", result.stdout)

    def test_missing_api_key_fails_without_publishing(self):
        env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
        env.pop("ANTHROPIC_API_KEY", None)
        result = subprocess.run([sys.executable, "scripts/run_daily.py", "--date", "2026-07-31"], cwd=ROOT, env=env, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ANTHROPIC_API_KEY", result.stderr)

    def test_period_help_lists_week_and_month_modes(self):
        env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
        result = subprocess.run([sys.executable, "scripts/run_period.py", "--help"], cwd=ROOT, env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn("week", result.stdout)
        self.assertIn("month", result.stdout)

    def test_period_without_daily_reports_does_not_call_claude(self):
        env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "ANTHROPIC_API_KEY": "test-key"}
        with tempfile.TemporaryDirectory() as folder:
            result = subprocess.run(
                [sys.executable, "scripts/run_period.py", "week", "--end-date", "2026-08-02", "--data-root", folder],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
            )
        self.assertEqual(result.returncode, 3)
        self.assertIn("Keine gültigen Tagesberichte für diesen Zeitraum; Claude wurde nicht aufgerufen.", result.stderr)

    def test_daily_main_exit_code_is_unaffected_by_a_translation_failure(self):
        import inspect
        import scripts.run_daily as run_daily
        from lagebericht.translate import TranslationError
        from tests.test_schema import ALLOWED_DOMAINS, daily_report

        # Still confirm the wiring shape exists (spec compliance), then
        # verify the actual behavioral guarantee below.
        source = inspect.getsource(run_daily.main)
        self.assertIn("publish_translation", source)
        self.assertIn("except TranslationError", source)

        class FakePipeline:
            def __init__(self, *args, **kwargs):
                pass

            def run(self, report_date):
                report = daily_report()
                report["reportDate"] = report_date.isoformat()
                return report

        def fake_publish_translation(*args, **kwargs):
            raise TranslationError("simulated translation failure")

        original_pipeline = run_daily.DailyPipeline
        original_publish_translation = run_daily.publish_translation
        run_daily.DailyPipeline = FakePipeline
        run_daily.publish_translation = fake_publish_translation
        self.addCleanup(setattr, run_daily, "DailyPipeline", original_pipeline)
        self.addCleanup(setattr, run_daily, "publish_translation", original_publish_translation)

        # test_cli.py has no ambient ANTHROPIC_API_KEY (subprocess tests set it
        # per-call via an env dict); main() reads it from os.environ directly
        # since we call it in-process here, so set/restore it manually.
        original_api_key = os.environ.get("ANTHROPIC_API_KEY")
        os.environ["ANTHROPIC_API_KEY"] = "test-key"
        if original_api_key is None:
            self.addCleanup(os.environ.pop, "ANTHROPIC_API_KEY", None)
        else:
            self.addCleanup(os.environ.__setitem__, "ANTHROPIC_API_KEY", original_api_key)

        with tempfile.TemporaryDirectory() as folder:
            exit_code = run_daily.main([
                "--date", "2026-08-03", "--data-root", folder,
            ])

            self.assertEqual(exit_code, 0)
            self.assertTrue((Path(folder) / "daily" / "2026-08-03.json").exists())

    def test_period_main_exit_code_is_unaffected_by_a_translation_failure(self):
        import inspect
        import scripts.run_period as run_period
        from lagebericht.translate import TranslationError
        from tests.test_translate import _valid_period_report

        source = inspect.getsource(run_period.main)
        self.assertIn("publish_translation", source)
        self.assertIn("except TranslationError", source)

        class FakeAggregator:
            def __init__(self, *args, **kwargs):
                pass

            def build_week(self, period_end):
                return _valid_period_report("week")

            def build_month(self, year, month):
                return _valid_period_report("month")

        def fake_publish_translation(*args, **kwargs):
            raise TranslationError("simulated translation failure")

        original_aggregator = run_period.PeriodAggregator
        original_publish_translation = run_period.publish_translation
        run_period.PeriodAggregator = FakeAggregator
        run_period.publish_translation = fake_publish_translation
        self.addCleanup(setattr, run_period, "PeriodAggregator", original_aggregator)
        self.addCleanup(setattr, run_period, "publish_translation", original_publish_translation)

        original_api_key = os.environ.get("ANTHROPIC_API_KEY")
        os.environ["ANTHROPIC_API_KEY"] = "test-key"
        if original_api_key is None:
            self.addCleanup(os.environ.pop, "ANTHROPIC_API_KEY", None)
        else:
            self.addCleanup(os.environ.__setitem__, "ANTHROPIC_API_KEY", original_api_key)

        with tempfile.TemporaryDirectory() as folder:
            exit_code = run_period.main([
                "week", "--end-date", "2026-08-02", "--data-root", folder,
            ])

            self.assertEqual(exit_code, 0)
            self.assertTrue((Path(folder) / "weekly" / "2026-W31.json").exists())


if __name__ == "__main__":
    unittest.main()
