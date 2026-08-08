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
            "type": "array", "maxItems": 8,
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


COUNTRY_ORDER = ("usa", "china", "montenegro", "eu")


def _daily_snapshot_country(reports: list[dict], country_id: str) -> dict | None:
    for report in reversed(reports):
        for country in report.get("countries", []):
            if country.get("id") != country_id:
                continue
            sections = copy.deepcopy(country.get("categories", []))
            warning = (
                f"Dieser Länderabschnitt ist eine Momentaufnahme aus dem Tagesbericht vom "
                f"{date.fromisoformat(report['reportDate']).strftime('%d.%m.%Y')}, weil die automatische "
                "Wochenverdichtung für dieses Land unvollständig war."
            )
            for section in sections:
                limitations = section.get("limitations")
                if isinstance(limitations, list) and "technical_failure" not in limitations:
                    limitations.append("technical_failure")
                if section.get("status") == "published":
                    context = section.get("contextDe")
                    if not isinstance(context, list):
                        context = []
                    if not context:
                        context.append("Die Entwicklung entspricht dem Stand des genannten Tagesberichts.")
                    section["contextDe"] = context[:2] + [warning]
                else:
                    section["contextDe"] = []
                if "overallSignificance" not in section:
                    section["overallSignificance"] = {
                        "score": 0,
                        "reasonDe": "Eine eigenständige Zeitraum-Bewertung war technisch nicht verfügbar.",
                    } if section.get("status") == "published" else None
                if isinstance(section.get("germanyRelevance"), bool):
                    section["germanyRelevance"] = {
                        "score": 1 if section["germanyRelevance"] else 0,
                        "reasonDe": "Die Bewertung wurde aus dem älteren Tagesbericht übernommen.",
                    } if section.get("status") == "published" else None
            return {"id": country_id, "label": country.get("label", country_id), "sections": sections}
    return None


def normalize_period_content(content: dict, period_type: str, reports: list[dict]) -> dict:
    normalized = copy.deepcopy(content)
    overall_summary = normalized.get("overallSummary")
    if isinstance(overall_summary, list):
        normalized["overallSummary"] = overall_summary[:10 if period_type == "week" else 15]
    countries_by_id = {}
    for country in normalized.get("countries", []):
        country_id = country.get("id") if isinstance(country, dict) else None
        if country_id in COUNTRY_ORDER and country_id not in countries_by_id:
            countries_by_id[country_id] = country
    canonical_countries = []
    for country_id in COUNTRY_ORDER:
        country = countries_by_id.get(country_id) or _daily_snapshot_country(reports, country_id)
        if country is not None:
            canonical_countries.append(country)
    normalized["countries"] = canonical_countries
    for country in normalized.get("countries", []):
        for section in country.get("sections", []):
            summary = section.get("summaryDe")
            if isinstance(summary, list):
                section["summaryDe"] = summary[:6]
            context = section.get("contextDe")
            if isinstance(context, list):
                section["contextDe"] = context[:3]
            sources = section.get("sources")
            if isinstance(sources, list):
                section["sources"] = sources[:8]
            for rating_name in ("germanyRelevance", "overallSignificance"):
                rating = section.get(rating_name)
                if not isinstance(rating, dict):
                    continue
                score = rating.get("score")
                if isinstance(score, bool):
                    continue
                if isinstance(score, float) and score.is_integer():
                    score = int(score)
                elif isinstance(score, str):
                    try:
                        score = int(score.strip())
                    except ValueError:
                        continue
                if isinstance(score, int):
                    rating["score"] = max(0, min(3, score))
    return normalized

PERIOD_CONTENT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["overallSummary", "countries"],
    "properties": {
        "overallSummary": {"type": "array", "minItems": 1, "maxItems": 8, "items": {"type": "string", "maxLength": 500}},
        "countries": {
            "type": "array", "minItems": len(COUNTRY_ORDER), "maxItems": len(COUNTRY_ORDER),
            "items": {
                "type": "object", "additionalProperties": False,
                "required": ["id", "label", "sections"],
                "properties": {
                    "id": {"enum": list(COUNTRY_ORDER)},
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
            self.ai_client.generate_json(self.model, instructions, input_text, "period_content", schema),
            period_type,
            reports,
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
