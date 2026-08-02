from __future__ import annotations

import calendar
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


def due_periods(day: date) -> set[str]:
    result = set()
    if day.weekday() == 6:
        result.add("week")
    if day.day == calendar.monthrange(day.year, day.month)[1]:
        result.add("month")
    return result


def due_outputs(day: date, data_root: Path) -> dict[str, bool]:
    iso = day.isocalendar()
    week_id = f"{iso.year}-W{iso.week:02d}"
    periods = due_periods(day)
    return {
        "daily": not (data_root / "daily" / f"{day.isoformat()}.json").exists(),
        "week": "week" in periods and not (data_root / "weekly" / f"{week_id}.json").exists(),
        "month": "month" in periods and not (data_root / "monthly" / f"{day:%Y-%m}.json").exists(),
    }


def main() -> None:
    now = berlin_now()
    outputs = due_outputs(now.date(), Path("data"))
    print(f"daily={str(outputs['daily']).lower()}")
    print(f"week={str(outputs['week']).lower()}")
    print(f"month={str(outputs['month']).lower()}")
    print(f"date={now.date().isoformat()}")
    print(f"month_id={now.strftime('%Y-%m')}")


if __name__ == "__main__":
    main()
