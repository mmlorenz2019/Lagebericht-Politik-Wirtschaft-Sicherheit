import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfoNotFoundError

from lagebericht.schedule import due_outputs, period_targets, to_berlin
from tests.test_schema import category


ROOT = Path(__file__).parents[1]


def valid_week_report(source_dates):
    all_dates = [
        "2026-07-27", "2026-07-28", "2026-07-29", "2026-07-30",
        "2026-07-31", "2026-08-01", "2026-08-02",
    ]
    missing = [value for value in all_dates if value not in source_dates]
    return {
        "schemaVersion": 2,
        "periodType": "week",
        "periodStart": "2026-07-27",
        "periodEnd": "2026-08-02",
        "generatedAt": "2026-08-03T04:00:00Z",
        "status": "partial" if missing else "complete",
        "overallSummary": ["Die Woche wird anhand der vorhandenen Tagesberichte zusammengefasst."],
        "countries": [
            {"id": "usa", "label": "USA", "sections": [category("politics_society")]},
            {"id": "china", "label": "China", "sections": [category("economy_technology")]},
            {"id": "montenegro", "label": "Montenegro", "sections": [category("foreign_security")]},
        ],
        "sourceReportDates": list(source_dates),
        "missingReportDates": missing,
    }


class WorkflowContractTests(unittest.TestCase):
    def test_period_verifier_reports_missing_week_and_accepts_partial_artifact(self):
        env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            daily = root / "daily" / "2026-08-02.json"
            daily.parent.mkdir(parents=True)
            daily.write_text("{}", encoding="utf-8")
            command = [
                sys.executable,
                "scripts/verify_periods.py",
                "--run-date",
                "2026-08-03",
                "--data-root",
                str(root),
            ]
            missing = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True)
            self.assertEqual(missing.returncode, 1)
            self.assertIn("Fehlender Wochenbericht: 2026-W31", missing.stderr)

            weekly = root / "weekly" / "2026-W31.json"
            weekly.parent.mkdir(parents=True)
            weekly.write_text(json.dumps(valid_week_report(["2026-08-02"])), encoding="utf-8")
            complete = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True)
            self.assertEqual(complete.returncode, 0)
    def test_monday_targets_previous_calendar_week(self):
        targets = period_targets(date(2026, 8, 3))
        self.assertEqual(targets.week_end, date(2026, 8, 2))
        self.assertIsNone(targets.month_id)

    def test_first_day_targets_previous_month_across_year_boundary(self):
        targets = period_targets(date(2027, 1, 1))
        self.assertIsNone(targets.week_end)
        self.assertEqual(targets.month_id, "2026-12")

    def test_first_day_on_monday_targets_week_and_month(self):
        targets = period_targets(date(2027, 2, 1))
        self.assertEqual(targets.week_end, date(2027, 1, 31))
        self.assertEqual(targets.month_id, "2027-01")

    def test_due_outputs_are_idempotent_per_artifact(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            day = date(2026, 8, 3)

            self.assertEqual(
                due_outputs(day, root),
                {"daily": True, "week": True, "month": False},
            )

            (root / "daily").mkdir()
            (root / "daily" / "2026-08-03.json").write_text("{}", encoding="utf-8")

            self.assertEqual(
                due_outputs(day, root),
                {"daily": False, "week": True, "month": False},
            )

    def test_existing_partial_week_is_complete_for_recovery_slots(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for value in ("2026-07-31", "2026-08-01", "2026-08-02"):
                path = root / "daily" / f"{value}.json"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("{}", encoding="utf-8")
            (root / "weekly").mkdir()
            (root / "weekly" / "2026-W31.json").write_text(
                json.dumps(valid_week_report(["2026-07-31", "2026-08-01", "2026-08-02"])),
                encoding="utf-8",
            )

            self.assertEqual(
                due_outputs(date(2026, 8, 3), root),
                {"daily": True, "week": False, "month": False},
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

            self.assertEqual(due_outputs(date(2026, 8, 3), root), {"daily": True, "week": True, "month": False})

    def test_structurally_invalid_or_malformed_period_file_remains_due(self):
        for report in (
            {"periodEnd": "2026-08-02", "sourceReportDates": ["2026-08-02"], "missingReportDates": []},
            {"periodEnd": "2026-08-02", "sourceReportDates": [{}], "missingReportDates": []},
        ):
            with self.subTest(report=report), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                daily = root / "daily" / "2026-08-02.json"
                daily.parent.mkdir(parents=True)
                daily.write_text("{}", encoding="utf-8")
                weekly = root / "weekly" / "2026-W31.json"
                weekly.parent.mkdir(parents=True)
                weekly.write_text(json.dumps(report), encoding="utf-8")
                self.assertTrue(due_outputs(date(2026, 8, 3), root)["week"])

    def test_shortened_week_and_month_artifacts_remain_due(self):
        cases = [
            (date(2026, 8, 3), "weekly/2026-W31.json", {
                **valid_week_report(["2026-08-02"]),
                "periodStart": "2026-08-02",
                "missingReportDates": [],
                "status": "complete",
            }, "2026-08-02", "week"),
            (date(2026, 8, 1), "monthly/2026-07.json", {
                **valid_week_report(["2026-07-31"]),
                "periodType": "month",
                "periodStart": "2026-07-31",
                "periodEnd": "2026-07-31",
                "missingReportDates": [],
                "status": "complete",
            }, "2026-07-31", "month"),
        ]
        for run_date, relative, report, source_date, key in cases:
            with self.subTest(key=key), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                daily = root / "daily" / f"{source_date}.json"
                daily.parent.mkdir(parents=True)
                daily.write_text("{}", encoding="utf-8")
                artifact = root / relative
                artifact.parent.mkdir(parents=True)
                artifact.write_text(json.dumps(report), encoding="utf-8")
                self.assertTrue(due_outputs(run_date, root)[key])

    def test_monday_after_new_year_uses_previous_iso_week_filename(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            daily = root / "daily" / "2027-01-03.json"
            daily.parent.mkdir(parents=True)
            daily.write_text("{}", encoding="utf-8")
            report = valid_week_report(["2026-08-02"])
            report.update({
                "periodStart": "2026-12-28",
                "periodEnd": "2027-01-03",
                "sourceReportDates": ["2027-01-03"],
                "missingReportDates": [
                    "2026-12-28", "2026-12-29", "2026-12-30",
                    "2026-12-31", "2027-01-01", "2027-01-02",
                ],
            })
            weekly = root / "weekly" / "2026-W53.json"
            weekly.parent.mkdir(parents=True)
            weekly.write_text(json.dumps(report), encoding="utf-8")
            self.assertFalse(due_outputs(date(2027, 1, 4), root)["week"])

    def test_berlin_guard_preserves_local_date(self):
        berlin = timezone(timedelta(hours=2), "Europe/Berlin")
        sunday_month_end = datetime(2026, 5, 31, 6, 30, tzinfo=berlin)
        self.assertEqual(to_berlin(sunday_month_end).date(), date(2026, 5, 31))

    def test_to_berlin_prefers_europe_berlin_zoneinfo_when_available(self):
        def available_zone(key):
            if key != "Europe/Berlin":
                raise AssertionError(f"unexpected zone key: {key}")
            return timezone(timedelta(hours=3), "zoneinfo-test")

        with patch(
            "lagebericht.schedule.ZoneInfo", side_effect=available_zone, create=True
        ):
            converted = to_berlin(
                datetime(2026, 7, 1, 0, 0, tzinfo=timezone.utc)
            )

        self.assertEqual(converted.utcoffset(), timedelta(hours=3))
        self.assertEqual(converted.hour, 3)

    def test_to_berlin_falls_back_when_zoneinfo_is_unavailable(self):
        with patch(
            "lagebericht.schedule.ZoneInfo",
            side_effect=ZoneInfoNotFoundError("missing"),
            create=True,
        ):
            summer = to_berlin(
                datetime(2026, 7, 1, 0, 0, tzinfo=timezone.utc)
            )
            winter = to_berlin(
                datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
            )

        self.assertEqual(summer.utcoffset(), timedelta(hours=2))
        self.assertEqual(winter.utcoffset(), timedelta(hours=1))

    def test_test_workflow_has_read_only_permissions_and_runs_tests(self):
        text = (ROOT / ".github" / "workflows" / "test.yml").read_text(encoding="utf-8")
        self.assertIn("contents: read", text)
        self.assertIn("python -m unittest discover -s tests -v", text)
        self.assertIn("pull_request:", text)

    def test_daily_workflow_uses_anthropic_models_and_four_spaced_berlin_recovery_slots(self):
        text = (ROOT / ".github" / "workflows" / "daily-report.yml").read_text(encoding="utf-8")
        self.assertIn("secrets.ANTHROPIC_API_KEY", text)
        self.assertIn("ANTHROPIC_EXTRACTION_MODEL: claude-haiku-4-5-20251001", text)
        self.assertIn("ANTHROPIC_SUMMARY_MODEL: claude-sonnet-4-6", text)
        self.assertNotIn("OPENAI_", text)
        self.assertEqual(text.count('timezone: "Europe/Berlin"'), 4)
        for cron in ("47 5 * * *", "17 7 * * *", "37 9 * * *", "53 11 * * *"):
            self.assertIn(f"cron: '{cron}'", text)
        self.assertIn("steps.schedule.outputs.daily == 'true'", text)
        self.assertNotIn(
            "steps.schedule.outputs.daily == 'true' || github.event_name == 'workflow_dispatch'",
            text,
        )
        self.assertIn("steps.schedule.outputs.week == 'true'", text)
        self.assertIn("steps.schedule.outputs.month == 'true'", text)
        self.assertIn("steps.schedule.outputs.week_end", text)
        self.assertIn("if: always()", text)
        self.assertIn("python scripts/verify_periods.py", text)
        self.assertEqual(text.count("continue-on-error: true"), 2)
        self.assertRegex(text, r"(?s)- name: Wochenbericht erzeugen.*?continue-on-error: true")
        self.assertRegex(text, r"(?s)- name: Monatsbericht erzeugen.*?continue-on-error: true")
        self.assertIn("if: ${{ !cancelled() && steps.schedule.outputs.week == 'true' }}", text)
        self.assertIn("if: ${{ !cancelled() && steps.schedule.outputs.month == 'true' }}", text)
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
        self.assertIn("github.event.workflow_run.conclusion", text)
        self.assertNotIn("github.event.workflow_run.conclusion == 'success'", text)
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
