from __future__ import annotations

import calendar
import copy
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .prompts import build_period_prompt
from .schema import validate_daily_report, validate_period_report


RATING_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["score", "reasonDe"],
    "properties": {
        "score": {"type": "integer", "minimum": 0, "maximum": 3},
        "reasonDe": {"type": "string", "minLength": 1, "maxLength": 300},
    },
}

SECTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["id", "status", "headlineDe", "summaryDe", "contextDe", "additionalImportant", "germanyRelevance", "overallSignificance", "sourceBasis", "limitations", "sources"],
    "properties": {
        "id": {"enum": ["politics_society", "economy_technology", "foreign_security"]},
        "status": {"enum": ["published", "no_major_development", "unavailable"]},
        "headlineDe": {"type": "string", "maxLength": 180},
        "summaryDe": {"type": "array", "maxItems": 6, "items": {"type": "string", "maxLength": 500}},
        "contextDe": {"type": "array", "minItems": 0, "maxItems": 3, "items": {"type": "string", "maxLength": 500}},
        "additionalImportant": {"type": ["string", "null"], "maxLength": 500},
        "germanyRelevance": {"anyOf": [RATING_SCHEMA, {"type": "null"}]},
        "overallSignificance": {"anyOf": [RATING_SCHEMA, {"type": "null"}]},
        "sourceBasis": {"enum": ["multiple", "single", "none"]},
        "limitations": {"type": "array", "items": {"enum": ["paywall", "feed_only", "single_source", "source_disagreement", "technical_failure"]}},
        "sources": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "type", "titleOriginal", "url", "publishedAt"],
                "properties": {
                    "name": {"type": "string"}, "type": {"type": "string"}, "titleOriginal": {"type": "string"},
                    "url": {"type": "string"}, "publishedAt": {"type": "string"},
                },
            },
        },
    },
}


def period_content_schema(period_type: str) -> dict:
    if period_type == "week":
        minimum, maximum = 8, 10
    elif period_type == "month":
        minimum, maximum = 12, 15
    else:
        raise ValueError("period_type must be week or month")
    schema = copy.deepcopy(PERIOD_CONTENT_SCHEMA)
    summary = schema["properties"]["overallSummary"]
    summary["minItems"] = minimum
    summary["maxItems"] = maximum
    return schema


def normalize_period_content(content: dict) -> dict:
    normalized = copy.deepcopy(content)
    for country in normalized.get("countries", []):
        for section in country.get("sections", []):
            summary = section.get("summaryDe")
            if isinstance(summary, list):
                section["summaryDe"] = summary[:6]
    return normalized

PERIOD_CONTENT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["overallSummary", "countries"],
    "properties": {
        "overallSummary": {"type": "array", "minItems": 1, "maxItems": 8, "items": {"type": "string", "maxLength": 500}},
        "countries": {
            "type": "array", "minItems": 3, "maxItems": 3,
            "items": {
                "type": "object", "additionalProperties": False,
                "required": ["id", "label", "sections"],
                "properties": {
                    "id": {"enum": ["usa", "china", "montenegro"]},
                    "label": {"type": "string"},
                    "sections": {"type": "array", "minItems": 1, "maxItems": 3, "items": SECTION_SCHEMA},
                },
            },
        },
    },
}


def load_period_reports(data_root: Path, start: date, end: date, allowed_domains: set[str]) -> tuple[list[dict], list[str]]:
    reports: list[dict] = []
    missing: list[str] = []
    current = start
    while current <= end:
        path = data_root / "daily" / f"{current.isoformat()}.json"
        if not path.exists():
            missing.append(current.isoformat())
        else:
            report = json.loads(path.read_text(encoding="utf-8"))
            validate_daily_report(report, allowed_domains)
            if report["reportDate"] != current.isoformat():
                raise ValueError(f"report date mismatch in {path}")
            reports.append(report)
        current += timedelta(days=1)
    return reports, missing


class PeriodAggregator:
    def __init__(self, data_root: Path, ai_client, allowed_domains: set[str], *, model: str = "claude-sonnet-4-6"):
        self.data_root = data_root
        self.ai_client = ai_client
        self.allowed_domains = allowed_domains
        self.model = model

    def _build(self, period_type: str, start: date, end: date, minimum: int) -> dict | None:
        reports, missing = load_period_reports(self.data_root, start, end, self.allowed_domains)
        if len(reports) < minimum:
            return None
        instructions, input_text = build_period_prompt(reports, period_type)
        schema = period_content_schema(period_type)
        content = normalize_period_content(
            self.ai_client.generate_json(self.model, instructions, input_text, "period_content", schema)
        )
        report = {
            "schemaVersion": 3,
            "periodType": period_type,
            "periodStart": start.isoformat(),
            "periodEnd": end.isoformat(),
            "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "status": "partial" if missing else "complete",
            "overallSummary": content["overallSummary"],
            "countries": content["countries"],
            "sourceReportDates": [item["reportDate"] for item in reports],
            "missingReportDates": missing,
        }
        validate_period_report(report, self.allowed_domains)
        return report

    def build_week(self, end_date: date) -> dict | None:
        return self._build("week", end_date - timedelta(days=6), end_date, 1)

    def build_month(self, year: int, month: int) -> dict | None:
        start = date(year, month, 1)
        end = date(year, month, calendar.monthrange(year, month)[1])
        return self._build("month", start, end, 1)
