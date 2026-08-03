from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .costs import CostDataError, validate_cost_report
from .schema import validate_daily_report, validate_period_report


def _entries(directory: Path, field: str) -> list[dict]:
    if not directory.exists():
        return []
    result = []
    for path in sorted(directory.glob("*.json"), reverse=True):
        value = path.stem
        result.append({field: value, "path": f"data/{directory.name}/{path.name}"})
    return result


def _period_entries(directory: Path, field: str, daily_dates: set[str]) -> list[dict]:
    if not directory.exists():
        return []
    result = []
    for path in sorted(directory.glob("*.json"), reverse=True):
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        source_dates = report.get("sourceReportDates") if isinstance(report, dict) else None
        if (
            not isinstance(source_dates, list)
            or not source_dates
            or any(not isinstance(value, str) or value not in daily_dates for value in source_dates)
        ):
            continue
        result.append({field: path.stem, "path": f"data/{directory.name}/{path.name}"})
    return result


def rebuild_index(data_root: Path) -> dict:
    daily = _entries(data_root / "daily", "date")
    daily_dates = {entry["date"] for entry in daily}
    weekly = _period_entries(data_root / "weekly", "period", daily_dates)
    monthly = _period_entries(data_root / "monthly", "period", daily_dates)
    current_costs = None
    costs_directory = data_root / "costs"
    if costs_directory.exists():
        for path in sorted(costs_directory.glob("*.json"), reverse=True):
            try:
                report = json.loads(path.read_text(encoding="utf-8"))
                validate_cost_report(report, expected_month=path.stem)
            except (OSError, UnicodeError, json.JSONDecodeError, CostDataError):
                continue
            current_costs = {
                "month": path.stem,
                "path": f"data/costs/{path.name}",
            }
            break
    return {
        "schemaVersion": 2,
        "latestDaily": daily[0]["date"] if daily else None,
        "daily": daily,
        "weekly": weekly,
        "monthly": monthly,
        "currentCosts": current_costs,
    }


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp", newline="\n")
    temporary = Path(handle.name)
    try:
        with handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


class Publisher:
    def __init__(self, data_root: Path, allowed_domains: set[str]):
        self.data_root = data_root
        self.allowed_domains = allowed_domains

    def _index(self) -> None:
        _atomic_json(self.data_root / "index.json", rebuild_index(self.data_root))

    def publish_daily(self, report: dict) -> Path:
        validate_daily_report(report, self.allowed_domains)
        path = self.data_root / "daily" / f"{report['reportDate']}.json"
        _atomic_json(path, report)
        self._index()
        return path

    def publish_period(self, report: dict) -> Path:
        validate_period_report(report, self.allowed_domains)
        if report["periodType"] == "week":
            from datetime import date
            end = date.fromisoformat(report["periodEnd"])
            period = f"{end.isocalendar().year}-W{end.isocalendar().week:02d}"
            directory = "weekly"
        else:
            period = report["periodStart"][:7]
            directory = "monthly"
        path = self.data_root / directory / f"{period}.json"
        _atomic_json(path, report)
        self._index()
        return path
