from __future__ import annotations

import re
from datetime import datetime, timezone

from .normalize import ArticleCandidate, canonical_url


_SPACE = re.compile(r"\s+")


def deduplicate_candidates(candidates: list[ArticleCandidate]) -> list[ArticleCandidate]:
    result: list[ArticleCandidate] = []
    seen: set[tuple[str, str]] = set()
    for item in candidates:
        key = (item.source_id, canonical_url(item.url))
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _parse(value: str | None) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def filter_by_window(candidates: list[ArticleCandidate], start: datetime, end: datetime) -> list[ArticleCandidate]:
    start = start.astimezone(timezone.utc)
    end = end.astimezone(timezone.utc)
    return [item for item in candidates if (published := _parse(item.published_at)) is not None and start <= published < end]


def build_event_input(candidates: list[ArticleCandidate]) -> list[dict]:
    ordered = sorted(candidates, key=lambda item: (item.country, item.published_at or "", item.source_id, item.url))
    return [
        {
            "sourceId": item.source_id,
            "country": item.country,
            "title": _SPACE.sub(" ", item.title).strip(),
            "url": item.url,
            "publishedAt": item.published_at,
            "excerpt": _SPACE.sub(" ", item.excerpt).strip(),
            "retrieval": item.retrieval,
            "language": item.language,
        }
        for item in ordered
    ]

