from __future__ import annotations

import argparse
import calendar
import sys
from datetime import date
from pathlib import Path

from lagebericht.schedule import period_artifact_complete, period_targets


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Prüft fällige Wochen- und Monatsberichte.")
    parser.add_argument("--run-date", required=True, type=date.fromisoformat)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    targets = period_targets(args.run_date)
    failures: list[str] = []

    if targets.week_end is not None:
        iso = targets.week_end.isocalendar()
        period_id = f"{iso.year}-W{iso.week:02d}"
        path = args.data_root / "weekly" / f"{period_id}.json"
        if not period_artifact_complete(path, targets.week_end, args.data_root):
            failures.append(f"Fehlender Wochenbericht: {period_id}")

    if targets.month_id is not None:
        year, month = (int(value) for value in targets.month_id.split("-"))
        end = date(year, month, calendar.monthrange(year, month)[1])
        path = args.data_root / "monthly" / f"{targets.month_id}.json"
        if not period_artifact_complete(path, end, args.data_root):
            failures.append(f"Fehlender Monatsbericht: {targets.month_id}")

    for message in failures:
        print(message, file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
