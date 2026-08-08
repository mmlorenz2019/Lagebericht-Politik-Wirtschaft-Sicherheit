from __future__ import annotations

import copy
import json
from pathlib import Path

from .anthropic_client import AnthropicError
from .prompts import _safe_json
from .publish import Publisher
from .schema import ReportValidationError, validate_daily_report, validate_period_report


class TranslationError(RuntimeError):
    """Raised when a validated German report cannot be safely translated to English."""


TRANSLATION_INSTRUCTIONS = (
    "Du übersetzt einen bereits validierten deutschen Nachrichtenbericht ins Englische. "
    "Übersetze ausschließlich headlineDe, summaryDe, contextDe (falls vorhanden), additionalImportant, "
    "germanyRelevance.reasonDe, overallSignificance.reasonDe, overallSummary (falls vorhanden) sowie "
    "sources[].type in natürliches, verständliches Englisch. Gib alle anderen Felder unverändert in der "
    "Antwort zurück: id-Werte, Zahlen, sources[].name, sources[].url, sources[].titleOriginal, "
    "sources[].publishedAt, Datumsangaben und Statuswerte. Erfinde keine neuen Fakten, ändere keine "
    "inhaltliche Aussage und ändere keine Bewertungszahl."
)


def build_translation_prompt(report: dict) -> tuple[str, str]:
    return TRANSLATION_INSTRUCTIONS, f"<trusted_report>{_safe_json(report)}</trusted_report>"


def _merge_rating(original: dict | None, translated) -> dict | None:
    if original is None:
        return None
    reason = original["reasonDe"]
    if isinstance(translated, dict) and isinstance(translated.get("reasonDe"), str) and translated["reasonDe"].strip():
        reason = translated["reasonDe"]
    return {"score": original["score"], "reasonDe": reason}


def _merge_sources(original: list[dict], translated) -> list[dict]:
    if not isinstance(translated, list) or len(translated) != len(original):
        return copy.deepcopy(original)
    merged = []
    for source, translated_source in zip(original, translated):
        if isinstance(translated_source, dict) and isinstance(translated_source.get("type"), str) and translated_source["type"].strip():
            merged.append({**copy.deepcopy(source), "type": translated_source["type"]})
        else:
            merged.append(copy.deepcopy(source))
    return merged


def _merge_category(original: dict, translated) -> dict:
    merged = copy.deepcopy(original)
    if not isinstance(translated, dict):
        return merged
    if isinstance(translated.get("headlineDe"), str) and translated["headlineDe"].strip():
        merged["headlineDe"] = translated["headlineDe"]
    if isinstance(translated.get("summaryDe"), list) and all(isinstance(s, str) for s in translated["summaryDe"]) and len(translated["summaryDe"]) == len(original["summaryDe"]):
        merged["summaryDe"] = translated["summaryDe"]
    if "contextDe" in original:
        translated_context = translated.get("contextDe")
        if isinstance(translated_context, list) and all(isinstance(s, str) for s in translated_context) and len(translated_context) == len(original["contextDe"]):
            merged["contextDe"] = translated_context
    if original.get("additionalImportant") is not None:
        translated_additional = translated.get("additionalImportant")
        if isinstance(translated_additional, str) and translated_additional.strip():
            merged["additionalImportant"] = translated_additional
    else:
        merged["additionalImportant"] = None
    merged["germanyRelevance"] = _merge_rating(original.get("germanyRelevance"), translated.get("germanyRelevance"))
    merged["overallSignificance"] = _merge_rating(original.get("overallSignificance"), translated.get("overallSignificance"))
    merged["sources"] = _merge_sources(original["sources"], translated.get("sources"))
    return merged


def _merge_country(original: dict, translated, section_key: str) -> dict:
    merged = copy.deepcopy(original)
    translated_sections = translated.get(section_key) if isinstance(translated, dict) else None
    translated_by_id = {
        item["id"]: item
        for item in (translated_sections or [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    merged[section_key] = [
        _merge_category(category, translated_by_id.get(category["id"]))
        for category in original[section_key]
    ]
    return merged


def _merge_report(original: dict, translated, is_daily: bool) -> dict:
    merged = copy.deepcopy(original)
    section_key = "categories" if is_daily else "sections"
    translated_countries = translated.get("countries") if isinstance(translated, dict) else None
    translated_by_id = {
        item["id"]: item
        for item in (translated_countries or [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    merged["countries"] = [
        _merge_country(country, translated_by_id.get(country["id"]), section_key)
        for country in original["countries"]
    ]
    if not is_daily:
        translated_overall = translated.get("overallSummary") if isinstance(translated, dict) else None
        if (
            isinstance(translated_overall, list)
            and all(isinstance(s, str) for s in translated_overall)
            and len(translated_overall) == len(original["overallSummary"])
        ):
            merged["overallSummary"] = translated_overall
    return merged


def translate_report(
    report: dict,
    ai_client,
    allowed_domains: set[str],
    schema_path: Path,
    *,
    model: str = "claude-haiku-4-5-20251001",
) -> dict:
    is_daily = "reportDate" in report
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TranslationError(f"cannot load report schema: {exc}") from exc
    instructions, input_text = build_translation_prompt(report)
    try:
        translated = ai_client.generate_json(model, instructions, input_text, "translated_report", schema)
    except AnthropicError as exc:
        raise TranslationError(f"translation call failed: {exc}") from exc
    merged = _merge_report(report, translated, is_daily)
    try:
        if is_daily:
            validate_daily_report(merged, allowed_domains)
        else:
            validate_period_report(merged, allowed_domains)
    except ReportValidationError as exc:
        raise TranslationError(f"translated report failed validation: {exc}") from exc
    return merged


def publish_translation(
    report: dict,
    ai_client,
    allowed_domains: set[str],
    schema_path: Path,
    data_root: Path,
    publish_method_name: str,
    *,
    model: str = "claude-haiku-4-5-20251001",
):
    """Translate `report` and publish it under `data_root / "en"`.

    Raises TranslationError (never publishes anything) if translation,
    validation, or publishing fails; the caller decides what a failure means for its own
    exit code and messaging. `publish_method_name` is `"publish_daily"` or
    `"publish_period"` — kept as a string so this single helper serves both
    scripts/run_daily.py and scripts/run_period.py without importing either.
    """
    translated = translate_report(report, ai_client, allowed_domains, schema_path, model=model)
    en_publisher = Publisher(
        data_root / "en", allowed_domains, url_prefix=f"{data_root.as_posix()}/en"
    )
    try:
        return getattr(en_publisher, publish_method_name)(translated)
    except OSError as exc:
        raise TranslationError(f"failed to publish translated report: {exc}") from exc
