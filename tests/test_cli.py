import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class DailyCliTests(unittest.TestCase):
    def test_period_client_allows_larger_structured_reports(self):
        import scripts.run_period as run_period

        self.assertTrue(hasattr(run_period, "build_period_client"))
        captured = {}

        def transport(url, headers, payload, timeout):
            captured.update(payload)
            return {
                "content": [{"type": "text", "text": '{"ok": true}'}],
                "stop_reason": "end_turn",
            }

        client = run_period.build_period_client("test-key", transport=transport)
        self.assertEqual(client.generate_json("model", "rules", "input", "schema", {}), {"ok": True})
        self.assertEqual(captured["max_tokens"], 16384)

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


if __name__ == "__main__":
    unittest.main()
