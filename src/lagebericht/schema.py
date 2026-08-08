from __future__ import annotations

from datetime import date, datetime
from urllib.parse import urlsplit


COUNTRIES = ("usa", "china", "montenegro", "eu")
CATEGORY_IDS = ("politics_society", "economy_technology", "foreign_security")
CATEGORY_STATUS = {"published", "no_major_development", "unavailable"}
REPORT_STATUS = {"complete", "partial"}
SOURCE_BASIS = {"multiple", "single", "none"}
LIMITATIONS = {"paywall", "feed_only", "single_source", "source_disagreement", "technical_failure"}


class ReportValidationError(ValueError):
    """Raised when a generated report violates the public data contract."""


def _fail(path: str, message: str) -> None:
    raise ReportValidationError(f"{path}: {message}")


def _object(value, path: str, allowed: set[str], required: set[str]) -> dict:
    if not isinstance(value, dict):
        _fail(path, "must be an object")
    unknown = set(value) - allowed
    if unknown:
        _fail(path, f"unknown field: {sorted(unknown)[0]}")
    missing = required - set(value)
    if missing:
        _fail(path, f"missing field: {sorted(missing)[0]}")
    return value


def _string(value, path: str, maximum: int, *, empty: bool = False) -> str:
    if not isinstance(value, str) or (not empty and not value.strip()):
        _fail(path, "must be a non-empty string")
    if len(value) > maximum:
        _fail(path, f"must contain at most {maximum} characters")
    return value


def _iso_date(value, path: str) -> str:
    _string(value, path, 10)
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        _fail(path, f"invalid ISO date ({exc})")
    return value


def _iso_datetime(value, path: str) -> str:
    _string(value, path, 40)
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        _fail(path, f"invalid ISO datetime ({exc})")
    return value


def _source(source: dict, path: str, allowed_domains: set[str]) -> None:
    allowed = {"name", "type", "titleOriginal", "url", "publishedAt"}
    _object(source, path, allowed, allowed)
    _string(source["name"], f"{path}.name", 100)
    _string(source["type"], f"{path}.type", 100)
    _string(source["titleOriginal"], f"{path}.titleOriginal", 300)
    _iso_datetime(source["publishedAt"], f"{path}.publishedAt")
    url = _string(source["url"], f"{path}.url", 2048)
    parsed = urlsplit(url)
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not hostname:
        _fail(f"{path}.url", "must be an absolute https URL")
    if hostname not in {domain.lower() for domain in allowed_domains}:
        _fail(f"{path}.url", f"host {hostname!r} is not allowlisted")


def _rating(value, path: str) -> None:
    _object(value, path, {"score", "reasonDe"}, {"score", "reasonDe"})
    score = value["score"]
    if isinstance(score, bool) or not isinstance(score, int) or not 0 <= score <= 3:
        _fail(f"{path}.score", "must be an integer from 0 to 3")
    _string(value["reasonDe"], f"{path}.reasonDe", 300)


def _category(item: dict, path: str, allowed_domains: set[str], schema_version: int) -> None:
    allowed = {
        "id", "status", "headlineDe", "summaryDe", "additionalImportant",
        "germanyRelevance", "sourceBasis", "limitations", "sources",
    }
    if schema_version >= 2:
        allowed.add("overallSignificance")
    if schema_version == 3:
        allowed.add("contextDe")
    _object(item, path, allowed, allowed)
    if item["id"] not in CATEGORY_IDS:
        _fail(f"{path}.id", "unknown category")
    if item["status"] not in CATEGORY_STATUS:
        _fail(f"{path}.status", "unknown category status")
    _string(item["headlineDe"], f"{path}.headlineDe", 180, empty=True)
    if not isinstance(item["summaryDe"], list) or len(item["summaryDe"]) > 6:
        _fail(f"{path}.summaryDe", "must be an array with at most 6 sentences")
    for index, sentence in enumerate(item["summaryDe"]):
        _string(sentence, f"{path}.summaryDe[{index}]", 500)
    if schema_version == 3:
        context = item["contextDe"]
        if not isinstance(context, list) or len(context) > 3:
            _fail(f"{path}.contextDe", "must be an array with at most 3 sentences")
        for index, sentence in enumerate(context):
            _string(sentence, f"{path}.contextDe[{index}]", 500)
    if item["additionalImportant"] is not None:
        _string(item["additionalImportant"], f"{path}.additionalImportant", 500)
    if schema_version == 1:
        if not isinstance(item["germanyRelevance"], bool):
            _fail(f"{path}.germanyRelevance", "must be boolean")
    elif item["status"] == "published":
        _rating(item["germanyRelevance"], f"{path}.germanyRelevance")
        _rating(item["overallSignificance"], f"{path}.overallSignificance")
    elif item["germanyRelevance"] is not None or item["overallSignificance"] is not None:
        _fail(path, "ratings must be null for an empty category status")
    if item["sourceBasis"] not in SOURCE_BASIS:
        _fail(f"{path}.sourceBasis", "unknown source basis")
    if not isinstance(item["limitations"], list) or any(x not in LIMITATIONS for x in item["limitations"]):
        _fail(f"{path}.limitations", "contains an unknown limitation")
    if not isinstance(item["sources"], list) or len(item["sources"]) > 8:
        _fail(f"{path}.sources", "must be an array with at most 8 sources")
    for index, source in enumerate(item["sources"]):
        _source(source, f"{path}.sources[{index}]", allowed_domains)
    if item["status"] == "published":
        if not item["headlineDe"] or not (3 <= len(item["summaryDe"]) <= 6) or not item["sources"]:
            _fail(path, "published categories require headline, 3-6 sentences and sources")
        if schema_version == 3 and not (2 <= len(item["contextDe"]) <= 3):
            _fail(f"{path}.contextDe", "published categories require 2-3 context sentences")
    elif item["headlineDe"] or item["summaryDe"] or item["sources"] or item["sourceBasis"] != "none" or (schema_version == 3 and item["contextDe"]):
        _fail(path, "empty category status must not contain story content")


def validate_daily_report(report: dict, allowed_domains: set[str]) -> None:
    top = {"schemaVersion", "reportDate", "generatedAt", "status", "countries"}
    _object(report, "report", top, top)
    schema_version = report["schemaVersion"]
    if schema_version not in {1, 2} or isinstance(schema_version, bool):
        _fail("schemaVersion", "must be 1 or 2")
    _iso_date(report["reportDate"], "reportDate")
    _iso_datetime(report["generatedAt"], "generatedAt")
    if report["status"] not in REPORT_STATUS:
        _fail("status", "unknown report status")
    if not isinstance(report["countries"], list) or len(report["countries"]) != len(COUNTRIES):
        _fail("countries", "must contain exactly one entry per country")
    seen = []
    for country_index, country in enumerate(report["countries"]):
        path = f"countries[{country_index}]"
        _object(country, path, {"id", "label", "categories"}, {"id", "label", "categories"})
        if country["id"] not in COUNTRIES:
            _fail(f"{path}.id", "unknown country")
        seen.append(country["id"])
        _string(country["label"], f"{path}.label", 30)
        if not isinstance(country["categories"], list) or len(country["categories"]) != 3:
            _fail(f"{path}.categories", "must contain exactly three categories")
        for category_index, item in enumerate(country["categories"]):
            _category(item, f"{path}.categories[{category_index}]", allowed_domains, schema_version)
        if set(x["id"] for x in country["categories"]) != set(CATEGORY_IDS):
            _fail(f"{path}.categories", "must contain every category exactly once")
    if set(seen) != set(COUNTRIES) or len(set(seen)) != len(COUNTRIES):
        _fail("countries", "must contain every country exactly once")


def validate_period_report(report: dict, allowed_domains: set[str]) -> None:
    top = {
        "schemaVersion", "periodType", "periodStart", "periodEnd", "generatedAt",
        "status", "overallSummary", "countries", "sourceReportDates", "missingReportDates",
    }
    _object(report, "report", top, top)
    schema_version = report["schemaVersion"]
    if schema_version not in {1, 2, 3} or isinstance(schema_version, bool):
        _fail("schemaVersion", "must be 1, 2 or 3")
    if report["periodType"] not in {"week", "month"}:
        _fail("periodType", "must be week or month")
    start = date.fromisoformat(_iso_date(report["periodStart"], "periodStart"))
    end = date.fromisoformat(_iso_date(report["periodEnd"], "periodEnd"))
    if end < start:
        _fail("periodEnd", "must not be before periodStart")
    _iso_datetime(report["generatedAt"], "generatedAt")
    if report["status"] not in REPORT_STATUS:
        _fail("status", "unknown report status")
    if schema_version == 3:
        limits = (8, 10) if report["periodType"] == "week" else (12, 15)
    else:
        limits = (1, 8)
    if not isinstance(report["overallSummary"], list) or not (limits[0] <= len(report["overallSummary"]) <= limits[1]):
        _fail("overallSummary", f"must contain {limits[0]}-{limits[1]} sentences")
    for index, sentence in enumerate(report["overallSummary"]):
        _string(sentence, f"overallSummary[{index}]", 500)
    if not isinstance(report["countries"], list) or len(report["countries"]) != len(COUNTRIES):
        _fail("countries", "must contain every country exactly once")
    seen = []
    for country_index, country in enumerate(report["countries"]):
        path = f"countries[{country_index}]"
        _object(country, path, {"id", "label", "sections"}, {"id", "label", "sections"})
        if country["id"] not in COUNTRIES:
            _fail(f"{path}.id", "unknown country")
        seen.append(country["id"])
        _string(country["label"], f"{path}.label", 30)
        if not isinstance(country["sections"], list) or not (1 <= len(country["sections"]) <= 3):
            _fail(f"{path}.sections", "must contain 1-3 sections")
        for section_index, section in enumerate(country["sections"]):
            _category(section, f"{path}.sections[{section_index}]", allowed_domains, schema_version)
    if set(seen) != set(COUNTRIES) or len(set(seen)) != len(COUNTRIES):
        _fail("countries", "must contain every country exactly once")
    for field in ("sourceReportDates", "missingReportDates"):
        if not isinstance(report[field], list):
            _fail(field, "must be an array")
        for index, value in enumerate(report[field]):
            parsed = date.fromisoformat(_iso_date(value, f"{field}[{index}]"))
            if not start <= parsed <= end:
                _fail(f"{field}[{index}]", "date lies outside the period")
