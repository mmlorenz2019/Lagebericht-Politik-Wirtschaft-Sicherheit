import os
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class DailyCliTests(unittest.TestCase):
    def test_help_lists_dry_run_and_date(self):
        env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
        result = subprocess.run([sys.executable, "scripts/run_daily.py", "--help"], cwd=ROOT, env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn("--dry-run", result.stdout)
        self.assertIn("--date", result.stdout)

    def test_missing_api_key_fails_without_publishing(self):
        env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
        env.pop("OPENAI_API_KEY", None)
        result = subprocess.run([sys.executable, "scripts/run_daily.py", "--date", "2026-07-31"], cwd=ROOT, env=env, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("OPENAI_API_KEY", result.stderr)

    def test_period_help_lists_week_and_month_modes(self):
        env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
        result = subprocess.run([sys.executable, "scripts/run_period.py", "--help"], cwd=ROOT, env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn("week", result.stdout)
        self.assertIn("month", result.stdout)


if __name__ == "__main__":
    unittest.main()
