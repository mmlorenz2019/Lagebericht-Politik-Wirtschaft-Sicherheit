import json
import re
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from lagebericht.schedule import due_outputs, due_periods, to_berlin


ROOT = Path(__file__).parents[1]


class WorkflowContractTests(unittest.TestCase):
    def test_due_outputs_are_idempotent_per_artifact(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            day = date(2026, 8, 2)

            self.assertEqual(
                due_outputs(day, root),
                {"daily": True, "week": True, "month": False},
            )

            (root / "daily").mkdir()
            (root / "daily" / "2026-08-02.json").write_text("{}", encoding="utf-8")

            self.assertEqual(
                due_outputs(day, root),
                {"daily": False, "week": True, "month": False},
            )

    def test_month_end_outputs_use_existing_period_files_independently(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "weekly").mkdir()
            (root / "weekly" / "2026-W22.json").write_text(
                json.dumps(
                    {
                        "periodEnd": "2026-05-31",
                        "sourceReportDates": ["2026-05-31"],
                        "missingReportDates": [],
                    }
                ),
                encoding="utf-8",
            )

            self.assertEqual(
                due_outputs(date(2026, 5, 31), root),
                {"daily": True, "week": False, "month": True},
            )

    def test_incomplete_period_file_remains_due(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "weekly").mkdir()
            (root / "weekly" / "2026-W31.json").write_text(
                json.dumps(
                    {
                        "periodEnd": "2026-08-02",
                        "sourceReportDates": ["2026-07-31"],
                        "missingReportDates": ["2026-08-01", "2026-08-02"],
                    }
                ),
                encoding="utf-8",
            )

            self.assertEqual(
                due_outputs(date(2026, 8, 2), root),
                {"daily": True, "week": True, "month": False},
            )

    def test_berlin_guard_and_period_schedule(self):
        berlin = timezone(timedelta(hours=2), "Europe/Berlin")
        sunday_month_end = datetime(2026, 5, 31, 6, 30, tzinfo=berlin)
        self.assertEqual(to_berlin(sunday_month_end).date(), date(2026, 5, 31))
        self.assertEqual(due_periods(sunday_month_end.date()), {"week", "month"})
    def test_test_workflow_has_read_only_permissions_and_runs_tests(self):
        text = (ROOT / ".github" / "workflows" / "test.yml").read_text(encoding="utf-8")
        self.assertIn("contents: read", text)
        self.assertIn("python -m unittest discover -s tests -v", text)
        self.assertIn("pull_request:", text)

    def test_daily_workflow_uses_anthropic_models_and_three_berlin_recovery_slots(self):
        text = (ROOT / ".github" / "workflows" / "daily-report.yml").read_text(encoding="utf-8")
        self.assertIn("secrets.ANTHROPIC_API_KEY", text)
        self.assertIn("ANTHROPIC_EXTRACTION_MODEL: claude-haiku-4-5-20251001", text)
        self.assertIn("ANTHROPIC_SUMMARY_MODEL: claude-sonnet-4-6", text)
        self.assertNotIn("OPENAI_", text)
        self.assertEqual(text.count('timezone: "Europe/Berlin"'), 3)
        for cron in ("45 5 * * *", "5 6 * * *", "25 6 * * *"):
            self.assertIn(f"cron: '{cron}'", text)
        self.assertIn("steps.schedule.outputs.daily == 'true'", text)
        self.assertIn("steps.schedule.outputs.week == 'true'", text)
        self.assertIn("steps.schedule.outputs.month == 'true'", text)
        self.assertNotIn("steps.schedule.outputs.run", text)
        self.assertIn("ref: main", text)
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
