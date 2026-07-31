from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .schema import validate_daily_report, validate_period_report


def _entries(directory: Path, field: str) -> list[dict]:
    if not directory.exists():
        return []
    result = []
    for path in sorted(directory.glob("*.json"), reverse=True):
        value = path.stem
        result.append({field: value, "path": f"data/{directory.name}/{path.name}"})
    return result


def rebuild_index(data_root: Path) -> dict:
    daily = _entries(data_root / "daily", "date")
    weekly = _entries(data_root / "weekly", "period")
    monthly = _entries(data_root / "monthly", "period")
    return {
        "schemaVersion": 1,
        "latestDaily": daily[0]["date"] if daily else None,
        "daily": daily,
        "weekly": weekly,
        "monthly": monthly,
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

