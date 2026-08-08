import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path


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
            ledger = json.loads(
                (Path(folder) / "costs" / "2026-08.json").read_text(encoding="utf-8")
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
        self.assertEqual(captured["timeout"], 600.0)

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

    def test_daily_main_wires_translation_after_a_successful_german_publish(self):
        import inspect
        import scripts.run_daily as run_daily

        source = inspect.getsource(run_daily.main)
        self.assertIn("publish_translation", source)
        self.assertIn("except TranslationError", source)
        # The translation call must be nested inside the `else` branch that
        # only runs on a successful (non-dry-run) German publish, and must
        # not be able to change main()'s final `return 0` for that branch.
        publish_index = source.index("Publisher(args.data_root, allowed_domains).publish_daily(report)")
        translation_index = source.index("publish_translation(")
        self.assertLess(publish_index, translation_index)

    def test_period_main_wires_translation_after_a_successful_german_publish(self):
        import inspect
        import scripts.run_period as run_period

        source = inspect.getsource(run_period.main)
        self.assertIn("publish_translation", source)
        self.assertIn("except TranslationError", source)
        publish_index = source.index("Publisher(args.data_root, domains).publish_period(report)")
        translation_index = source.index("publish_translation(")
        self.assertLess(publish_index, translation_index)


if __name__ == "__main__":
    unittest.main()
