from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from .config import SourceConfig
from .events import build_event_input, deduplicate_candidates
from .fetch import FetchError
from .normalize import FeedNormalizationError, normalize_feed
from .prompts import build_daily_prompt, build_extraction_prompt
from .schema import validate_daily_report


class PipelineError(RuntimeError):
    """Raised when no safe report can be produced."""


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
                    "country": {"enum": ["usa", "china", "montenegro"]},
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
        daily_instructions, daily_text = build_daily_prompt(event_result.get("events", []), [])
        try:
            daily_schema = json.loads(self.daily_schema_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PipelineError(f"cannot load daily report schema: {exc}") from exc
        report = self.ai_client.generate_json(
            self.summary_model, daily_instructions, daily_text, "daily_report", daily_schema
        )
        if report.get("reportDate") != report_date.isoformat():
            raise PipelineError("model report date does not match requested date")
        validate_daily_report(report, self.allowed_domains)
        return report
