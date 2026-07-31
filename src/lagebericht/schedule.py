from __future__ import annotations

import calendar
from datetime import date, datetime, time, timedelta, timezone


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


def is_daily_time(now: datetime) -> bool:
    local = to_berlin(now)
    return local.hour == 6 and local.minute == 30


def due_periods(day: date) -> set[str]:
    result = set()
    if day.weekday() == 6:
        result.add("week")
    if day.day == calendar.monthrange(day.year, day.month)[1]:
        result.add("month")
    return result


def main() -> None:
    now = berlin_now()
    periods = due_periods(now.date())
    print(f"run={'true' if is_daily_time(now) else 'false'}")
    print(f"week={'true' if 'week' in periods else 'false'}")
    print(f"month={'true' if 'month' in periods else 'false'}")
    print(f"date={now.date().isoformat()}")
    print(f"month_id={now.strftime('%Y-%m')}")


if __name__ == "__main__":
    main()
