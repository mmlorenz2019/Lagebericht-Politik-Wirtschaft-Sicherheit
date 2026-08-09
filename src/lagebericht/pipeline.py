from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from .config import SourceConfig
from .events import build_event_input, deduplicate_candidates
from .fetch import FetchError
from .normalize import FeedNormalizationError, normalize_feed
from .prompts import build_daily_prompt, build_daily_repair_prompt, build_extraction_prompt
from .schema import COUNTRIES, ReportValidationError, validate_daily_report


class PipelineError(RuntimeError):
    """Raised when no safe report can be produced."""


def _attach_source_metadata(
    events: list[dict], candidates: list[dict], sources: list[SourceConfig]
) -> list[dict]:
    source_by_id = {source.id: source for source in sources}
    enriched_events = []
    for event in events:
        enriched = dict(event)
        source_candidates = []
        seen_indexes = set()
        indexes = event.get("candidateIndexes", [])
        if isinstance(indexes, list):
            for index in indexes:
                if (
                    not isinstance(index, int)
                    or isinstance(index, bool)
                    or index in seen_indexes
                    or not 0 <= index < len(candidates)
                ):
                    continue
                seen_indexes.add(index)
                candidate = candidates[index]
                source = source_by_id.get(candidate.get("sourceId"))
                if source is None:
                    continue
                source_candidates.append({
                    "name": source.name,
                    "type": source.type,
                    "titleOriginal": candidate.get("title"),
                    "url": candidate.get("url"),
                    "publishedAt": candidate.get("publishedAt"),
                })
        enriched["sourceCandidates"] = source_candidates
        enriched_events.append(enriched)
    return enriched_events


def _normalize_empty_categories(report: dict) -> None:
    countries = report.get("countries", [])
    if not isinstance(countries, list):
        return
    for country in countries:
        if not isinstance(country, dict):
            continue
        categories = country.get("categories", [])
        if not isinstance(categories, list):
            continue
        for category in categories:
            if not isinstance(category, dict) or category.get("status") == "published":
                continue
            category["headlineDe"] = ""
            category["summaryDe"] = []
            category["additionalImportant"] = None
            category["germanyRelevance"] = None
            category["overallSignificance"] = None
            category["sourceBasis"] = "none"
            category["sources"] = []


def _missing_countries(report: dict) -> list[str]:
    present = {
        country.get("id")
        for country in report.get("countries", [])
        if isinstance(country, dict)
    }
    return [country_id for country_id in COUNTRIES if country_id not in present]


def _missing_published_slots(report: dict, events: list[dict]) -> list[tuple[str, str]]:
    eligible = {
        (event.get("country"), event.get("category"))
        for event in events
        if isinstance(event, dict) and event.get("sourceCandidates")
    }
    published = {
        (country.get("id"), category.get("id"))
        for country in report.get("countries", [])
        if isinstance(country, dict)
        for category in country.get("categories", [])
        if isinstance(category, dict) and category.get("status") == "published"
    }
    return sorted(eligible - published)


EVENT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["events"],
    "properties": {
        "events": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "country", "category", "summary", "candidateIndexes", "contradictions"],
                "properties": {
                    "id": {"type": "string"},
                    "country": {"enum": list(COUNTRIES)},
                    "category": {"enum": ["politics_society", "economy_technology", "foreign_security"]},
                    "summary": {"type": "string"},
                    "candidateIndexes": {"type": "array", "items": {"type": "integer", "minimum": 0}},
                    "contradictions": {"type": "boolean"},
                },
            },
        }
    },
}


class DailyPipeline:
    def __init__(
        self,
        sources: list[SourceConfig],
        fetcher,
        ai_client,
        allowed_domains: set[str],
        *,
        extraction_model: str = "claude-haiku-4-5-20251001",
        summary_model: str = "claude-sonnet-4-6",
        daily_schema_path: Path | None = None,
    ):
        self.sources = sources
        self.fetcher = fetcher
        self.ai_client = ai_client
        self.allowed_domains = allowed_domains
        self.extraction_model = extraction_model
        self.summary_model = summary_model
        self.daily_schema_path = daily_schema_path or Path("schemas/daily-report.schema.json")

    def run(self, report_date: date) -> dict:
        candidates = []
        failures: list[str] = []
        for source in self.sources:
            if source.retrieval == "html":
                failures.append(f"{source.id}: html adapter unavailable")
                continue
            try:
                result = self.fetcher.fetch(source.feed_url, source.allowed_domains)
                candidates.extend(normalize_feed(source, result.body))
            except (FetchError, FeedNormalizationError) as exc:
                failures.append(f"{source.id}: {exc}")
        candidates = deduplicate_candidates(candidates)
        if not candidates:
            raise PipelineError(f"no source candidates available ({'; '.join(failures)})")
        event_input = build_event_input(candidates)
        extract_instructions, extract_text = build_extraction_prompt(event_input)
        event_result = self.ai_client.generate_json(
            self.extraction_model, extract_instructions, extract_text, "news_events", EVENT_SCHEMA
        )
        enriched_events = _attach_source_metadata(
            event_result.get("events", []), event_input, self.sources
        )
        daily_instructions, daily_text = build_daily_prompt(enriched_events, [])
        try:
            daily_schema = json.loads(self.daily_schema_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PipelineError(f"cannot load daily report schema: {exc}") from exc
        report = self.ai_client.generate_json(
            self.summary_model, daily_instructions, daily_text, "daily_report", daily_schema
        )
        report["reportDate"] = report_date.isoformat()
        _normalize_empty_categories(report)
        missing_slots = _missing_published_slots(report, enriched_events)
        missing_countries = _missing_countries(report)
        validation_error = None
        try:
            validate_daily_report(report, self.allowed_domains)
        except ReportValidationError as exc:
            validation_error = str(exc)
        if missing_slots or missing_countries or validation_error:
            repair_instructions, repair_text = build_daily_repair_prompt(
                enriched_events, report, missing_slots, validation_error, missing_countries
            )
            report = self.ai_client.generate_json(
                self.summary_model, repair_instructions, repair_text, "daily_report", daily_schema
            )
            report["reportDate"] = report_date.isoformat()
            _normalize_empty_categories(report)
            missing_slots = _missing_published_slots(report, enriched_events)
            if missing_slots:
                formatted = ", ".join(f"{country}/{category}" for country, category in missing_slots)
                raise PipelineError(f"summary omitted sourced slots: {formatted}")
            missing_countries = _missing_countries(report)
            if missing_countries:
                raise PipelineError(f"summary omitted entire countries: {', '.join(missing_countries)}")
            try:
                validate_daily_report(report, self.allowed_domains)
            except ReportValidationError as exc:
                raise PipelineError(f"summary produced invalid report after repair: {exc}") from exc
        return report
