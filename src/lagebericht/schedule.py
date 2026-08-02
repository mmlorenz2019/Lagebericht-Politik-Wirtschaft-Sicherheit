from __future__ import annotations

import calendar
import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path


def _last_sunday(year: int, month: int) -> date:
    final = date(year, month, calendar.monthrange(year, month)[1])
    return final - timedelta(days=(final.weekday() + 1) % 7)


def to_berlin(now: datetime) -> datetime:
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    utc = now.astimezone(timezone.utc)
    start = datetime.combine(_last_sunday(utc.year, 3), time(1), timezone.utc)
    end = datetime.combine(_last_sunday(utc.year, 10), time(1), timezone.utc)
    offset = timedelta(hours=2 if start <= utc < end else 1)
    return utc.astimezone(timezone(offset, "Europe/Berlin"))


def berlin_now() -> datetime:
    return to_berlin(datetime.now(timezone.utc))


@dataclass(frozen=True, slots=True)
class PeriodTargets:
    week_end: date | None
    month_id: str | None


def period_targets(day: date) -> PeriodTargets:
    week_end = day - timedelta(days=1) if day.weekday() == 0 else None
    previous = day - timedelta(days=1)
    month_id = previous.strftime("%Y-%m") if day.day == 1 else None
    return PeriodTargets(week_end=week_end, month_id=month_id)


def period_artifact_complete(path: Path, expected_end: date, data_root: Path) -> bool:
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False

    expected = expected_end.isoformat()
    sources = report.get("sourceReportDates")
    missing = report.get("missingReportDates")
    if report.get("periodEnd") != expected or not isinstance(sources, list) or not sources:
        return False
    if len(sources) != len(set(sources)) or not isinstance(missing, list):
        return False
    if set(sources) & set(missing):
        return False
    for value in sources:
        try:
            date.fromisoformat(value)
        except (TypeError, ValueError):
            return False
        if not (data_root / "daily" / f"{value}.json").exists():
            return False
    return True


def due_outputs(day: date, data_root: Path) -> dict[str, bool]:
    targets = period_targets(day)
    week_due = False
    if targets.week_end is not None:
        iso = targets.week_end.isocalendar()
        week_path = data_root / "weekly" / f"{iso.year}-W{iso.week:02d}.json"
        week_due = not period_artifact_complete(week_path, targets.week_end, data_root)

    month_due = False
    if targets.month_id is not None:
        year, month = (int(value) for value in targets.month_id.split("-"))
        month_end = date(year, month, calendar.monthrange(year, month)[1])
        month_path = data_root / "monthly" / f"{targets.month_id}.json"
        month_due = not period_artifact_complete(month_path, month_end, data_root)

    return {
        "daily": not (data_root / "daily" / f"{day.isoformat()}.json").exists(),
        "week": week_due,
        "month": month_due,
    }


def main() -> None:
    now = berlin_now()
    day = now.date()
    targets = period_targets(day)
    outputs = due_outputs(day, Path("data"))
    print(f"daily={str(outputs['daily']).lower()}")
    print(f"week={str(outputs['week']).lower()}")
    print(f"month={str(outputs['month']).lower()}")
    print(f"date={day.isoformat()}")
    print(f"week_end={targets.week_end.isoformat() if targets.week_end else ''}")
    print(f"month_id={targets.month_id or ''}")


if __name__ == "__main__":
    main()
