from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from .schema import CATEGORY_IDS, COUNTRIES


class ConfigError(ValueError):
    """Raised for unsafe or inconsistent source configuration."""


@dataclass(frozen=True, slots=True)
class SourceConfig:
    id: str
    name: str
    country: str
    categories: tuple[str, ...]
    feed_url: str
    allowed_domains: frozenset[str]
    type: str
    language: str
    retrieval: str
    paywall: bool
    max_candidates: int


def _domain(value: str, path: str) -> str:
    normalized = value.strip().lower().rstrip(".")
    if not normalized or "/" in normalized or ":" in normalized or normalized.startswith("."):
        raise ConfigError(f"{path}: invalid domain")
    return normalized


def load_sources(path: Path) -> list[SourceConfig]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"cannot read source config: {exc}") from exc
    if not isinstance(raw, dict) or set(raw) != {"sources"} or not isinstance(raw["sources"], list):
        raise ConfigError("config must contain exactly one sources array")
    result: list[SourceConfig] = []
    seen: set[str] = set()
    required = {
        "id", "name", "country", "categories", "feedUrl", "allowedDomains",
        "type", "language", "retrieval", "paywall", "maxCandidates",
    }
    for index, item in enumerate(raw["sources"]):
        prefix = f"sources[{index}]"
        if not isinstance(item, dict) or set(item) != required:
            raise ConfigError(f"{prefix}: fields do not match the source contract")
        source_id = item["id"]
        if not isinstance(source_id, str) or not source_id or source_id in seen:
            raise ConfigError(f"{prefix}: duplicate source id {source_id!r}")
        seen.add(source_id)
        if item["country"] not in COUNTRIES:
            raise ConfigError(f"{prefix}.country: unknown country")
        categories = item["categories"]
        if not isinstance(categories, list) or not categories or any(x not in CATEGORY_IDS for x in categories):
            raise ConfigError(f"{prefix}.categories: unknown or empty categories")
        feed_url = item["feedUrl"]
        parsed = urlsplit(feed_url) if isinstance(feed_url, str) else None
        if not parsed or parsed.scheme != "https" or not parsed.hostname:
            raise ConfigError(f"{prefix}.feedUrl: must be an absolute https URL")
        if item["retrieval"] not in {"rss", "html", "feed_only"}:
            raise ConfigError(f"{prefix}.retrieval: unknown retrieval mode")
        domains = item["allowedDomains"]
        if not isinstance(domains, list) or not domains:
            raise ConfigError(f"{prefix}.allowedDomains: must not be empty")
        allowed_domains = frozenset(_domain(x, f"{prefix}.allowedDomains") for x in domains)
        if parsed.hostname.lower() not in allowed_domains:
            raise ConfigError(f"{prefix}.feedUrl: host must be allowlisted")
        if not isinstance(item["paywall"], bool):
            raise ConfigError(f"{prefix}.paywall: must be boolean")
        if not isinstance(item["maxCandidates"], int) or not 1 <= item["maxCandidates"] <= 50:
            raise ConfigError(f"{prefix}.maxCandidates: must be 1-50")
        for field in ("name", "type", "language"):
            if not isinstance(item[field], str) or not item[field].strip():
                raise ConfigError(f"{prefix}.{field}: must be a non-empty string")
        result.append(SourceConfig(
            id=source_id,
            name=item["name"].strip(),
            country=item["country"],
            categories=tuple(dict.fromkeys(categories)),
            feed_url=feed_url,
            allowed_domains=allowed_domains,
            type=item["type"].strip(),
            language=item["language"].strip(),
            retrieval=item["retrieval"],
            paywall=item["paywall"],
            max_candidates=item["maxCandidates"],
        ))
    return result


def all_allowed_domains(sources: list[SourceConfig]) -> set[str]:
    return {domain for source in sources for domain in source.allowed_domains}

