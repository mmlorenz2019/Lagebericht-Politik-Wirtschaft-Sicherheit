import re
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from lagebericht.schedule import due_periods, is_daily_time


ROOT = Path(__file__).parents[1]


class WorkflowContractTests(unittest.TestCase):
    def test_berlin_guard_and_period_schedule(self):
        berlin = timezone(timedelta(hours=2), "Europe/Berlin")
        sunday_month_end = datetime(2026, 5, 31, 6, 30, tzinfo=berlin)
        self.assertTrue(is_daily_time(sunday_month_end))
        self.assertEqual(due_periods(sunday_month_end.date()), {"week", "month"})
        self.assertFalse(is_daily_time(datetime(2026, 5, 31, 5, 30, tzinfo=berlin)))
    def test_test_workflow_has_read_only_permissions_and_runs_tests(self):
        text = (ROOT / ".github" / "workflows" / "test.yml").read_text(encoding="utf-8")
        self.assertIn("contents: read", text)
        self.assertIn("python -m unittest discover -s tests -v", text)
        self.assertIn("pull_request:", text)

    def test_daily_workflow_uses_anthropic_secret_models_and_two_dst_crons(self):
        text = (ROOT / ".github" / "workflows" / "daily-report.yml").read_text(encoding="utf-8")
        self.assertIn("secrets.ANTHROPIC_API_KEY", text)
        self.assertIn("ANTHROPIC_EXTRACTION_MODEL: claude-haiku-4-5-20251001", text)
        self.assertIn("ANTHROPIC_SUMMARY_MODEL: claude-sonnet-4-6", text)
        self.assertNotIn("OPENAI_", text)
        self.assertIn("30 4 * * *", text)
        self.assertIn("30 5 * * *", text)
        self.assertIn("Europe/Berlin", text)
        self.assertNotIn("pull_request:", text)

    def test_all_actions_are_pinned_to_full_commit_sha(self):
        for name in ("test.yml", "daily-report.yml", "pages.yml"):
            text = (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
            uses = re.findall(r"uses:\s*[^@\s]+@([^\s#]+)", text)
            self.assertTrue(uses)
            self.assertTrue(all(re.fullmatch(r"[0-9a-f]{40}", ref) for ref in uses), f"unpinned action in {name}: {uses}")

    def test_daily_workflow_grants_only_contents_write(self):
        text = (ROOT / ".github" / "workflows" / "daily-report.yml").read_text(encoding="utf-8")
        permission_lines = re.findall(r"^\s{6}([a-z-]+):\s+(read|write)$", text, flags=re.MULTILINE)
        self.assertEqual(permission_lines, [("contents", "write")])

    def test_pages_workflow_uses_minimal_deployment_permissions(self):
        path = ROOT / ".github" / "workflows" / "pages.yml"
        self.assertTrue(path.exists(), "pages workflow is missing")
        text = path.read_text(encoding="utf-8")
        self.assertIn("branches: [main]", text)
        self.assertIn("workflow_run:", text)
        self.assertIn('workflows: ["Täglicher Lagebericht"]', text)
        self.assertIn("types: [completed]", text)
        self.assertIn("github.event.workflow_run.conclusion == 'success'", text)
        self.assertIn("ref: main", text)
        self.assertIn("contents: read", text)
        self.assertIn("pages: write", text)
        self.assertIn("id-token: write", text)
        self.assertIn("actions/configure-pages", text)
        self.assertIn("actions/upload-pages-artifact", text)
        self.assertIn("actions/deploy-pages", text)
        self.assertIn("name: github-pages", text)


if __name__ == "__main__":
    unittest.main()
