from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from xml.etree import ElementTree

from .config import SourceConfig


class FeedNormalizationError(ValueError):
    """Raised when a feed cannot be parsed safely."""


@dataclass(frozen=True, slots=True)
class ArticleCandidate:
    source_id: str
    country: str
    title: str
    url: str
    published_at: str | None
    excerpt: str
    retrieval: str
    language: str


_TAGS = re.compile(r"<[^>]+>")
_TRACKING = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "gclid", "fbclid"}


def canonical_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    query = urlencode([(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if k.lower() not in _TRACKING])
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, query, ""))


def _text(value: str | None) -> str:
    return " ".join(html.unescape(_TAGS.sub(" ", value or "")).split())


def _date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child_text(node, *names: str) -> str | None:
    wanted = set(names)
    for child in node:
        if _local_name(child.tag) in wanted:
            return "".join(child.itertext())
    return None


def normalize_feed(source: SourceConfig, payload: bytes) -> list[ArticleCandidate]:
    prefix = payload[:4096].upper()
    if b"<!DOCTYPE" in prefix or b"<!ENTITY" in prefix:
        raise FeedNormalizationError("DOCTYPE and ENTITY declarations are forbidden")
    try:
        root = ElementTree.fromstring(payload)
    except ElementTree.ParseError as exc:
        raise FeedNormalizationError(f"invalid XML: {exc}") from exc
    nodes = [node for node in root.iter() if _local_name(node.tag) in {"item", "entry"}]
    articles: list[ArticleCandidate] = []
    seen_urls: set[str] = set()
    for node in nodes:
        title = _text(_child_text(node, "title"))
        raw_url = _child_text(node, "link")
        if not raw_url:
            for child in node:
                if _local_name(child.tag) == "link" and child.attrib.get("href"):
                    raw_url = child.attrib["href"]
                    break
        if not title or not raw_url:
            continue
        url = canonical_url(raw_url)
        parsed = urlsplit(url)
        if parsed.scheme != "https" or (parsed.hostname or "").lower() not in source.allowed_domains:
            continue
        if url in seen_urls:
            continue
        seen_urls.add(url)
        published = _child_text(node, "pubDate", "published", "updated", "date")
        excerpt = _text(_child_text(node, "description", "summary", "content"))
        articles.append(ArticleCandidate(
            source_id=source.id,
            country=source.country,
            title=title[:300],
            url=url,
            published_at=_date(published),
            excerpt=excerpt[:2000],
            retrieval="feed_only" if source.paywall or source.retrieval == "feed_only" else "full",
            language=source.language,
        ))
        if len(articles) >= source.max_candidates:
            break
    return articles

