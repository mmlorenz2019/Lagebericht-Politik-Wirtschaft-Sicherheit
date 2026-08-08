# Sprachumschalter (DE/EN) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a German/English language toggle to the "Persönlicher Lagebericht" PWA. New daily/weekly/monthly runs additionally produce an English translation of the already-validated German report via a cheap Haiku translation pass, published to a mirrored `data/en/` tree; the frontend gets a toggle (next to the existing theme toggle) that switches which data root it reads from and swaps all static UI copy.

**Architecture:** A new `src/lagebericht/translate.py` module takes an already-validated German report and an AI client, asks Haiku to translate only the designated text fields, then **deterministically merges** the translated text back onto a deep copy of the original report — every non-text field (ids, scores, URLs, dates, source names) is copied from the original, never trusted from the model's output. This is stricter than the schema-only validation the design spec originally proposed: schema constraints alone can't stop a model from silently changing a `score` from 2 to 1 while staying schema-valid, so the merge step removes that risk entirely for anything not explicitly marked "translate". `scripts/run_daily.py`/`scripts/run_period.py` call this after a successful German publish, publishing the English result via a second `Publisher` instance; a translation failure is caught locally and never affects the German publish or the script's exit code. The frontend adds a `state.language` field, a `STRINGS` lookup table for static copy, and switches its data-fetch prefix between `data` and `data/en`.

**Tech Stack:** Python 3.12 stdlib (no new dependencies), vanilla JS, JSON Schema (draft 2020-12) reused as-is for the translation call's structural constraint.

## Global Constraints

- Every task ends with `PYTHONPATH=src python -m unittest discover -s tests -v` reported green (the suite is currently at 187 tests after the EU-block plan; new tests add to that count). One pre-existing, already-investigated, unrelated flaky failure is possible in `test_cli.py` (Windows console-encoding issue with German umlauts in subprocess stderr) — not something this plan introduces.
- No `.innerHTML =` in `assets/app.js`, no `document.write`.
- `index.html` must not gain any `src=`/`href=` starting with `http://`/`https://` (CSP `default-src 'self'`).
- Do not trigger a real, paid Anthropic API call as part of verifying this plan. All existing tests use fake/mocked AI clients — follow that pattern.
- A translation failure must never prevent, delay, or roll back the German publish, and must never change `scripts/run_daily.py`/`scripts/run_period.py`'s exit code away from what a successful German-only run would return.
- The English tree (`data/en/`) must never be treated as authoritative for anything the German tree already owns: cost data always comes from the German root's `data/index.json`, regardless of the active UI language.
- Never commit or push without running the full suite first. Do not push to `origin/main` — local commits only, the controller asks the user before the final push.

## ⚠️ Correction discovered while planning (read before Task 1)

The design spec (`docs/superpowers/specs/2026-08-08-sprachumschalter-design.md`) states: *"die bestehende `Publisher`-Klasse ist bereits generisch über `data_root` parametrisiert, keine Änderung an `publish.py` nötig."* This is only half true. `Publisher.publish_daily`/`publish_period` themselves need no changes, but `rebuild_index` (and its helpers `_entries`/`_period_entries`) **hardcode the URL prefix `"data/"` as a string literal**, independent of the actual `data_root` passed in:

```python
result.append({field: value, "path": f"data/{directory.name}/{path.name}"})
```

For the German tree (`data_root = Path("data")`) this happens to be correct by coincidence. For an English tree (`data_root = Path("data/en")`), it would still emit paths like `"data/daily/2026-08-08.json"` — missing the `en/` segment — so `data/en/index.json` would point at the **German** daily files. The frontend would then silently show German content while the language toggle claims English is active. This is a real bug in the reused-Publisher assumption, not a hypothetical: confirmed by reading `_entries`'s implementation and cross-checking `tests/test_publish.py`'s fixtures (which use arbitrary temp directories, not literally named `data`, yet already assert the hardcoded `"data/..."` prefix — proving the prefix has never actually been derived from `data_root`). Task 1 below fixes this with a minimal, backward-compatible `url_prefix` parameter before any translation code is written.

---

### Task 1: Fix `publish.py`'s hardcoded URL prefix so a second data root works correctly

**Files:**
- Modify: `src/lagebericht/publish.py`
- Test: `tests/test_publish.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `Publisher(data_root, allowed_domains, url_prefix="data")` — an optional keyword argument, defaulting to `"data"` so every existing call site and every existing test keeps working unchanged. Task 3/4 will instantiate a second `Publisher` with `url_prefix` set to the English root's own relative path.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_publish.py`, inside `class PublishTests` (after `test_publishes_valid_daily_report_and_index`):

```python
    def test_uses_a_custom_url_prefix_for_index_paths(self):
        publisher = Publisher(self.root / "en", ALLOWED_DOMAINS, url_prefix="data/en")
        publisher.publish_daily(daily_report())
        index = json.loads((self.root / "en" / "index.json").read_text(encoding="utf-8"))
        self.assertEqual(index["daily"], [{"date": "2026-07-31", "path": "data/en/daily/2026-07-31.json"}])
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd "06 Privat/App-Ideen/Persönlicher Lagebericht" && PYTHONPATH=src python -m unittest tests.test_publish.PublishTests.test_uses_a_custom_url_prefix_for_index_paths -v`

Expected: FAIL — `Publisher.__init__()` does not accept an `url_prefix` keyword argument (`TypeError`).

- [ ] **Step 3: Thread `url_prefix` through `Publisher`, `rebuild_index`, `_entries`, `_period_entries`**

In `src/lagebericht/publish.py`, replace:
```python
def _entries(directory: Path, field: str) -> list[dict]:
    if not directory.exists():
        return []
    result = []
    for path in sorted(directory.glob("*.json"), reverse=True):
        value = path.stem
        result.append({field: value, "path": f"data/{directory.name}/{path.name}"})
    return result


def _period_entries(directory: Path, field: str, daily_dates: set[str]) -> list[dict]:
    if not directory.exists():
        return []
    result = []
    for path in sorted(directory.glob("*.json"), reverse=True):
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        source_dates = report.get("sourceReportDates") if isinstance(report, dict) else None
        if (
            not isinstance(source_dates, list)
            or not source_dates
            or any(not isinstance(value, str) or value not in daily_dates for value in source_dates)
        ):
            continue
        result.append({field: path.stem, "path": f"data/{directory.name}/{path.name}"})
    return result


def rebuild_index(data_root: Path) -> dict:
    daily = _entries(data_root / "daily", "date")
    daily_dates = {entry["date"] for entry in daily}
    weekly = _period_entries(data_root / "weekly", "period", daily_dates)
    monthly = _period_entries(data_root / "monthly", "period", daily_dates)
```
with:
```python
def _entries(directory: Path, field: str, url_prefix: str) -> list[dict]:
    if not directory.exists():
        return []
    result = []
    for path in sorted(directory.glob("*.json"), reverse=True):
        value = path.stem
        result.append({field: value, "path": f"{url_prefix}/{directory.name}/{path.name}"})
    return result


def _period_entries(directory: Path, field: str, daily_dates: set[str], url_prefix: str) -> list[dict]:
    if not directory.exists():
        return []
    result = []
    for path in sorted(directory.glob("*.json"), reverse=True):
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        source_dates = report.get("sourceReportDates") if isinstance(report, dict) else None
        if (
            not isinstance(source_dates, list)
            or not source_dates
            or any(not isinstance(value, str) or value not in daily_dates for value in source_dates)
        ):
            continue
        result.append({field: path.stem, "path": f"{url_prefix}/{directory.name}/{path.name}"})
    return result


def rebuild_index(data_root: Path, url_prefix: str = "data") -> dict:
    daily = _entries(data_root / "daily", "date", url_prefix)
    daily_dates = {entry["date"] for entry in daily}
    weekly = _period_entries(data_root / "weekly", "period", daily_dates, url_prefix)
    monthly = _period_entries(data_root / "monthly", "period", daily_dates, url_prefix)
```

Leave the `costs_directory`/`current_costs` block untouched — it still hardcodes `"data/costs/..."`. This is intentional, not an oversight: per the Global Constraints above, cost data is only ever meaningful from the German root, and `rebuild_index(Path("data/en"))` will simply find no `data/en/costs` directory and correctly return `currentCosts: None` for the English index either way (the frontend, per Task 5, never reads `currentCosts` from the English index at all).

- [ ] **Step 4: Thread `url_prefix` through `Publisher.__init__`**

Replace:
```python
class Publisher:
    def __init__(self, data_root: Path, allowed_domains: set[str]):
        self.data_root = data_root
        self.allowed_domains = allowed_domains

    def _index(self) -> None:
        _atomic_json(self.data_root / "index.json", rebuild_index(self.data_root))
```
with:
```python
class Publisher:
    def __init__(self, data_root: Path, allowed_domains: set[str], *, url_prefix: str = "data"):
        self.data_root = data_root
        self.allowed_domains = allowed_domains
        self.url_prefix = url_prefix

    def _index(self) -> None:
        _atomic_json(self.data_root / "index.json", rebuild_index(self.data_root, self.url_prefix))
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd "06 Privat/App-Ideen/Persönlicher Lagebericht" && PYTHONPATH=src python -m unittest tests.test_publish -v`
Expected: all PASS, including the new test and every pre-existing test in the file (they all rely on the default `url_prefix="data"`, unchanged behavior).

- [ ] **Step 6: Run the full suite**

Run: `cd "06 Privat/App-Ideen/Persönlicher Lagebericht" && PYTHONPATH=src python -m unittest discover -s tests -v`
Expected: all PASS (188 tests: 187 existing + 1 new).

- [ ] **Step 7: Commit**

```bash
git add src/lagebericht/publish.py tests/test_publish.py
git commit -m "fix: derive published index paths from the actual data root instead of a hardcoded prefix"
```

---

### Task 2: `translate.py` — translate a validated report, merge deterministically, never trust the model for non-text fields

**Files:**
- Create: `src/lagebericht/translate.py`
- Test: `tests/test_translate.py`

**Interfaces:**
- Consumes: `AnthropicError` from `.anthropic_client`; `ReportValidationError`, `validate_daily_report`, `validate_period_report` from `.schema`; `_safe_json` from `.prompts` (already used by every other prompt builder in that module, same untrusted-vs-trusted wrapping convention); `Publisher` from `.publish` (Task 1's `url_prefix` parameter, used by `publish_translation`).
- Produces: `TranslationError` (exception class), `translate_report(report, ai_client, allowed_domains, schema_path, *, model=...) -> dict`, and `publish_translation(report, ai_client, allowed_domains, schema_path, data_root, publish_method_name, *, model=...) -> Path` — Tasks 3 and 4 call `publish_translation` directly after a successful German publish; it is the single piece of logic those two tasks add to `scripts/run_daily.py`/`scripts/run_period.py`, fully unit-tested here so those tasks stay thin wiring with nothing new to mock.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_translate.py`:

```python
import copy
import json
import tempfile
import unittest
from pathlib import Path

from lagebericht.anthropic_client import AnthropicError
from lagebericht.translate import TranslationError, publish_translation, translate_report
from tests.test_schema import ALLOWED_DOMAINS, daily_report, period_category

ROOT = Path(__file__).resolve().parents[1]
DAILY_SCHEMA_PATH = ROOT / "schemas" / "daily-report.schema.json"
PERIOD_SCHEMA_PATH = ROOT / "schemas" / "period-report.schema.json"


class RecordingAI:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def generate_json(self, model, instructions, input_text, schema_name, schema):
        self.calls.append({"model": model, "input_text": input_text, "schema": schema})
        if self.error is not None:
            raise self.error
        return copy.deepcopy(self.response)


def english_daily_translation(report):
    translated = copy.deepcopy(report)
    for country in translated["countries"]:
        for cat in country["categories"]:
            if cat["status"] != "published":
                continue
            cat["headlineDe"] = f"EN: {cat['headlineDe']}"
            cat["summaryDe"] = [f"EN sentence {i + 1}." for i in range(len(cat["summaryDe"]))]
            if cat["germanyRelevance"] is not None:
                cat["germanyRelevance"] = {"score": 0, "reasonDe": "EN reason (and a corrupted score)"}
            if cat["overallSignificance"] is not None:
                cat["overallSignificance"] = {"score": 0, "reasonDe": "EN reason (and a corrupted score)"}
            for source in cat["sources"]:
                source["type"] = f"EN {source['type']}"
                source["url"] = "https://example.invalid/tampered"  # must never survive the merge
    return translated


class TranslateDailyReportTests(unittest.TestCase):
    def test_translates_text_fields_and_ignores_tampered_preserve_fields(self):
        report = daily_report()
        ai = RecordingAI(response=english_daily_translation(report))
        result = translate_report(report, ai, ALLOWED_DOMAINS, DAILY_SCHEMA_PATH)

        translated_category = result["countries"][0]["categories"][0]
        original_category = report["countries"][0]["categories"][0]
        self.assertTrue(translated_category["headlineDe"].startswith("EN: "))
        self.assertEqual(translated_category["summaryDe"][0], "EN sentence 1.")
        # Preserved: the score must come from the ORIGINAL report, not the (corrupted) translation.
        self.assertEqual(translated_category["germanyRelevance"]["score"], original_category["germanyRelevance"]["score"])
        self.assertEqual(translated_category["germanyRelevance"]["reasonDe"], "EN reason (and a corrupted score)")
        # Preserved: the URL must come from the ORIGINAL report, never the model's output.
        self.assertEqual(translated_category["sources"][0]["url"], original_category["sources"][0]["url"])
        self.assertEqual(translated_category["sources"][0]["name"], original_category["sources"][0]["name"])
        self.assertEqual(translated_category["sources"][0]["type"], "EN öffentlich-rechtlich")

    def test_preserves_ids_and_report_metadata_unchanged(self):
        report = daily_report()
        ai = RecordingAI(response=english_daily_translation(report))
        result = translate_report(report, ai, ALLOWED_DOMAINS, DAILY_SCHEMA_PATH)
        self.assertEqual(result["reportDate"], report["reportDate"])
        self.assertEqual(result["schemaVersion"], report["schemaVersion"])
        self.assertEqual([c["id"] for c in result["countries"]], [c["id"] for c in report["countries"]])

    def test_raises_translation_error_when_the_ai_call_fails(self):
        report = daily_report()
        ai = RecordingAI(error=AnthropicError("boom"))
        with self.assertRaises(TranslationError):
            translate_report(report, ai, ALLOWED_DOMAINS, DAILY_SCHEMA_PATH)

    def test_raises_translation_error_when_merged_result_fails_validation(self):
        report = daily_report()
        broken = english_daily_translation(report)
        broken["countries"][0]["categories"][0]["headlineDe"] = "x" * 500  # exceeds maxLength 180
        ai = RecordingAI(response=broken)
        with self.assertRaises(TranslationError):
            translate_report(report, ai, ALLOWED_DOMAINS, DAILY_SCHEMA_PATH)

    def test_never_invents_additional_important_that_was_null(self):
        report = daily_report()
        self.assertIsNone(report["countries"][0]["categories"][0]["additionalImportant"])
        translated = english_daily_translation(report)
        translated["countries"][0]["categories"][0]["additionalImportant"] = "EN: invented text"
        ai = RecordingAI(response=translated)
        result = translate_report(report, ai, ALLOWED_DOMAINS, DAILY_SCHEMA_PATH)
        self.assertIsNone(result["countries"][0]["categories"][0]["additionalImportant"])

    def test_passes_the_daily_schema_to_the_ai_call(self):
        report = daily_report()
        ai = RecordingAI(response=english_daily_translation(report))
        translate_report(report, ai, ALLOWED_DOMAINS, DAILY_SCHEMA_PATH, model="claude-haiku-4-5-20251001")
        self.assertEqual(ai.calls[0]["model"], "claude-haiku-4-5-20251001")
        self.assertEqual(ai.calls[0]["schema"], json.loads(DAILY_SCHEMA_PATH.read_text(encoding="utf-8")))


def _valid_period_report(period_type="week"):
    # Standalone equivalent of PeriodReportValidationTests.valid_period_v3() in
    # tests/test_schema.py, which is an instance method and not importable
    # directly. Kept in lockstep with that method's shape (schemaVersion 3,
    # period_category() sections including contextDe) since it is what the
    # real schemas/period-report.schema.json requires.
    report = {
        "schemaVersion": 3,
        "periodType": period_type,
        "periodStart": "2026-07-27" if period_type == "week" else "2026-07-01",
        "periodEnd": "2026-08-02" if period_type == "week" else "2026-07-31",
        "generatedAt": "2026-08-02T05:00:00Z",
        "status": "partial",
        "overallSummary": [f"Satz {index + 1}." for index in range(8 if period_type == "week" else 12)],
        "countries": [
            {"id": "usa", "label": "USA", "sections": [period_category("politics_society")]},
            {"id": "china", "label": "China", "sections": [period_category("economy_technology")]},
            {"id": "montenegro", "label": "Montenegro", "sections": [period_category("foreign_security")]},
            {"id": "eu", "label": "EU", "sections": [period_category("politics_society")]},
        ],
        "sourceReportDates": (
            ["2026-07-27", "2026-07-28", "2026-07-30", "2026-08-02"]
            if period_type == "week"
            else ["2026-07-27", "2026-07-28", "2026-07-30", "2026-07-31"]
        ),
        "missingReportDates": (
            ["2026-07-29", "2026-07-31", "2026-08-01"] if period_type == "week" else ["2026-07-29"]
        ),
    }
    return report


class TranslatePeriodReportTests(unittest.TestCase):
    def _period_report(self):
        return _valid_period_report()

    def _english_period_translation(self, report):
        translated = copy.deepcopy(report)
        translated["overallSummary"] = [f"EN overall {i + 1}." for i in range(len(report["overallSummary"]))]
        for country in translated["countries"]:
            for section in country["sections"]:
                if section["status"] != "published":
                    continue
                section["headlineDe"] = f"EN: {section['headlineDe']}"
                section["summaryDe"] = [f"EN sentence {i + 1}." for i in range(len(section["summaryDe"]))]
                section["contextDe"] = [f"EN context {i + 1}." for i in range(len(section.get("contextDe") or []))]
        return translated

    def test_translates_overall_summary_and_context_de(self):
        report = self._period_report()
        ai = RecordingAI(response=self._english_period_translation(report))
        result = translate_report(report, ai, ALLOWED_DOMAINS, PERIOD_SCHEMA_PATH)
        self.assertTrue(result["overallSummary"][0].startswith("EN overall"))
        section = result["countries"][0]["sections"][0]
        if report["countries"][0]["sections"][0].get("contextDe"):
            self.assertTrue(section["contextDe"][0].startswith("EN context"))

    def test_falls_back_to_original_overall_summary_on_length_mismatch(self):
        report = self._period_report()
        translated = self._english_period_translation(report)
        translated["overallSummary"] = translated["overallSummary"][:1]
        ai = RecordingAI(response=translated)
        result = translate_report(report, ai, ALLOWED_DOMAINS, PERIOD_SCHEMA_PATH)
        self.assertEqual(result["overallSummary"], report["overallSummary"])


class PublishTranslationTests(unittest.TestCase):
    def test_publishes_an_english_mirror_with_a_correctly_prefixed_index_path(self):
        report = daily_report()
        ai = RecordingAI(response=english_daily_translation(report))
        with tempfile.TemporaryDirectory() as folder:
            data_root = Path(folder)
            path = publish_translation(
                report, ai, ALLOWED_DOMAINS, DAILY_SCHEMA_PATH, data_root, "publish_daily"
            )
            self.assertEqual(path, data_root / "en" / "daily" / "2026-07-31.json")
            index = json.loads((data_root / "en" / "index.json").read_text(encoding="utf-8"))
            self.assertEqual(
                index["daily"][0]["path"], f"{data_root.as_posix()}/en/daily/2026-07-31.json"
            )

    def test_propagates_translation_error_without_publishing_anything(self):
        report = daily_report()
        ai = RecordingAI(error=AnthropicError("boom"))
        with tempfile.TemporaryDirectory() as folder:
            data_root = Path(folder)
            with self.assertRaises(TranslationError):
                publish_translation(
                    report, ai, ALLOWED_DOMAINS, DAILY_SCHEMA_PATH, data_root, "publish_daily"
                )
            self.assertFalse((data_root / "en").exists())

    def test_works_for_period_reports_via_publish_period(self):
        report = _valid_period_report()
        translated = copy.deepcopy(report)
        translated["overallSummary"] = [f"EN {i + 1}." for i in range(len(report["overallSummary"]))]
        ai = RecordingAI(response=translated)
        with tempfile.TemporaryDirectory() as folder:
            data_root = Path(folder)
            path = publish_translation(
                report, ai, ALLOWED_DOMAINS, PERIOD_SCHEMA_PATH, data_root, "publish_period"
            )
            self.assertTrue(path.exists())
            self.assertIn("weekly", path.parts)
```

`_valid_period_report` is a plain function defined in this file (not imported), because `tests/test_schema.py`'s equivalent `valid_period_v3()` is an instance method on `PeriodReportValidationTests`, not a standalone importable function.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd "06 Privat/App-Ideen/Persönlicher Lagebericht" && PYTHONPATH=src python -m unittest tests.test_translate -v`
Expected: FAIL / ERROR on every test — `lagebericht.translate` does not exist yet.

- [ ] **Step 3: Create `src/lagebericht/translate.py`**

```python
from __future__ import annotations

import copy
import json
from pathlib import Path

from .anthropic_client import AnthropicError
from .prompts import _safe_json
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

    Raises TranslationError (never publishes anything) if translation or
    validation fails; the caller decides what a failure means for its own
    exit code and messaging. `publish_method_name` is `"publish_daily"` or
    `"publish_period"` — kept as a string so this single helper serves both
    scripts/run_daily.py and scripts/run_period.py without importing either.
    """
    translated = translate_report(report, ai_client, allowed_domains, schema_path, model=model)
    en_publisher = Publisher(
        data_root / "en", allowed_domains, url_prefix=f"{data_root.as_posix()}/en"
    )
    return getattr(en_publisher, publish_method_name)(translated)
```

Add `from .publish import Publisher` to the imports at the top of the file, alongside the existing `from .anthropic_client import AnthropicError` / `from .prompts import _safe_json` / `from .schema import ...` lines.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd "06 Privat/App-Ideen/Persönlicher Lagebericht" && PYTHONPATH=src python -m unittest tests.test_translate -v`
Expected: all PASS.

- [ ] **Step 5: Run the full suite**

Run: `cd "06 Privat/App-Ideen/Persönlicher Lagebericht" && PYTHONPATH=src python -m unittest discover -s tests -v`
Expected: all PASS (199 tests: 188 from Task 1 + 11 new).

- [ ] **Step 6: Commit**

```bash
git add src/lagebericht/translate.py tests/test_translate.py
git commit -m "feat: add translate_report with a deterministic merge for non-text fields"
```

---

### Task 3: Wire translation into `scripts/run_daily.py`

**Files:**
- Modify: `scripts/run_daily.py`
- Test: `tests/test_cli.py` (the existing home for `run_daily`/`run_period` wiring-level tests — see `DailyCliTests`, which already tests `build_daily_client` and CLI argument handling for both scripts; there is currently no full end-to-end `main()` test in this codebase, and this task does not add one — `publish_translation` (Task 2) already carries the real behavioral coverage; this task's test only needs to confirm the wiring is present and structured correctly, which a source-level assertion does directly and honestly, without the added complexity of also faking `SafeFetcher`'s network calls just to reach this one `try`/`except` block).

**Interfaces:**
- Consumes: `publish_translation`, `TranslationError` from `.translate` (Task 2).
- Produces: after a successful non-dry-run German publish, a best-effort English publish at `args.data_root / "en"`, via `publish_translation`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_cli.py`, inside `class DailyCliTests`:

```python
    def test_daily_main_wires_translation_after_a_successful_german_publish(self):
        import inspect
        import scripts.run_daily as run_daily

        source = inspect.getsource(run_daily.main)
        self.assertIn("publish_translation", source)
        self.assertIn("except TranslationError", source)
        # The translation call must be nested inside the `else` branch that
        # only runs on a successful (non-dry-run) German publish, and must
        # not be able to change main()'s final `return 0` for that branch.
        publish_index = source.index("Publisher(args.data_root, allowed_domains).publish_daily(report)")
        translation_index = source.index("publish_translation(")
        self.assertLess(publish_index, translation_index)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd "06 Privat/App-Ideen/Persönlicher Lagebericht" && PYTHONPATH=src python -m unittest tests.test_cli.DailyCliTests.test_daily_main_wires_translation_after_a_successful_german_publish -v`
Expected: FAIL — `run_daily.main`'s source contains none of this yet.

- [ ] **Step 3: Wire the translation call into `run_daily.py`**

In `scripts/run_daily.py`, add to the imports:
```python
from lagebericht.translate import TranslationError, publish_translation
```

Replace:
```python
        if args.dry_run:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            path = Publisher(args.data_root, allowed_domains).publish_daily(report)
            print(path)
        return 0
```
with:
```python
        if args.dry_run:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            path = Publisher(args.data_root, allowed_domains).publish_daily(report)
            print(path)
            try:
                en_path = publish_translation(
                    report,
                    client,
                    allowed_domains,
                    ROOT / "schemas" / "daily-report.schema.json",
                    args.data_root,
                    "publish_daily",
                    model=os.environ.get("ANTHROPIC_TRANSLATION_MODEL", "claude-haiku-4-5-20251001"),
                )
                print(en_path)
            except TranslationError as exc:
                print(f"Übersetzung fehlgeschlagen, deutscher Bericht bleibt veröffentlicht: {exc}", file=sys.stderr)
        return 0
```

`publish_translation` reuses the same `client` already built a few lines above by `build_daily_client(...)` — its cost observer is already wired, so a translation call is recorded by the existing `CostRecorder` with no extra setup. Because the `try`/`except TranslationError` is nested *inside* the `else` branch, and `TranslationError` is not part of the outer `except (AnthropicError, PipelineError, ValueError, OSError)` tuple a few lines further down, a translation failure cannot escape into the outer handler or change the `return 0` immediately below it — the German publish and the script's success are already final by the time translation is attempted.

- [ ] **Step 4: Run the test to verify it passes**

Run the same test from Step 2. Expected: PASS.

- [ ] **Step 5: Run the full suite**

Run: `cd "06 Privat/App-Ideen/Persönlicher Lagebericht" && PYTHONPATH=src python -m unittest discover -s tests -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add scripts/run_daily.py tests/test_cli.py
git commit -m "feat: publish an English translation after every successful daily run"
```

---

### Task 4: Wire translation into `scripts/run_period.py`

**Files:**
- Modify: `scripts/run_period.py`
- Test: `tests/test_cli.py` (same rationale as Task 3).

**Interfaces:**
- Consumes: `publish_translation`, `TranslationError` from `.translate`.
- Produces: after a successful non-dry-run German period publish, a best-effort English publish at `args.data_root / "en"`, via `publish_translation`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_cli.py`, inside `class DailyCliTests` (the class name is a slight misnomer already covering `run_period` tests too — follow the existing file's convention, do not create a new class):

```python
    def test_period_main_wires_translation_after_a_successful_german_publish(self):
        import inspect
        import scripts.run_period as run_period

        source = inspect.getsource(run_period.main)
        self.assertIn("publish_translation", source)
        self.assertIn("except TranslationError", source)
        publish_index = source.index("Publisher(args.data_root, domains).publish_period(report)")
        translation_index = source.index("publish_translation(")
        self.assertLess(publish_index, translation_index)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd "06 Privat/App-Ideen/Persönlicher Lagebericht" && PYTHONPATH=src python -m unittest tests.test_cli.DailyCliTests.test_period_main_wires_translation_after_a_successful_german_publish -v`
Expected: FAIL.

- [ ] **Step 3: Wire the translation call into `run_period.py`**

Add to the imports:
```python
from lagebericht.translate import TranslationError, publish_translation
```

Replace:
```python
        observer = build_period_usage_observer(
            args.data_root, args.mode, report_id
        )
        aggregator = PeriodAggregator(
            args.data_root,
            build_period_client(api_key, usage_observer=observer),
            domains,
            model=os.environ.get("ANTHROPIC_SUMMARY_MODEL", "claude-sonnet-4-6"),
        )
```
with:
```python
        observer = build_period_usage_observer(
            args.data_root, args.mode, report_id
        )
        client = build_period_client(api_key, usage_observer=observer)
        aggregator = PeriodAggregator(
            args.data_root,
            client,
            domains,
            model=os.environ.get("ANTHROPIC_SUMMARY_MODEL", "claude-sonnet-4-6"),
        )
```

(pulling the client into a named variable so it can be reused for translation below, without changing what `PeriodAggregator` receives).

Then replace:
```python
        if args.dry_run:
            import json
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print(Publisher(args.data_root, domains).publish_period(report))
        return 0
```
with:
```python
        if args.dry_run:
            import json
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print(Publisher(args.data_root, domains).publish_period(report))
            try:
                en_path = publish_translation(
                    report,
                    client,
                    domains,
                    ROOT / "schemas" / "period-report.schema.json",
                    args.data_root,
                    "publish_period",
                    model=os.environ.get("ANTHROPIC_TRANSLATION_MODEL", "claude-haiku-4-5-20251001"),
                )
                print(en_path)
            except TranslationError as exc:
                print(f"Übersetzung fehlgeschlagen, Rückblick bleibt veröffentlicht: {exc}", file=sys.stderr)
        return 0
```

- [ ] **Step 4: Run the test to verify it passes**

Run the same test from Step 2. Expected: PASS.

- [ ] **Step 5: Run the full suite**

Run: `cd "06 Privat/App-Ideen/Persönlicher Lagebericht" && PYTHONPATH=src python -m unittest discover -s tests -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add scripts/run_period.py tests/test_cli.py
git commit -m "feat: publish an English translation after every successful weekly/monthly run"
```

---

### Task 5: Frontend — language toggle, static-copy translation, language-aware data root

**Files:**
- Modify: `index.html`
- Modify: `assets/app.css`
- Modify: `assets/app.js`
- Test: `tests/test_frontend_contract.py`

**Interfaces:**
- Consumes: nothing from earlier tasks directly (the frontend only reads whatever `data/index.json` / `data/en/index.json` already contain — Task 1 already guarantees the paths inside each are self-consistent).
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Add the missing `id` attributes and the language-toggle button to `index.html`**

Replace:
```html
  <a class="skip-link" href="#report">Zum Bericht springen</a>
  <header class="site-header">
    <div>
      <p class="eyebrow">Politik · Wirtschaft · Sicherheit</p>
      <h1>Persönlicher Lagebericht</h1>
      <p id="updated" class="muted">Bericht wird geladen …</p>
    </div>
    <button type="button" id="theme-toggle" class="theme-toggle"></button>
  </header>
```
with:
```html
  <a class="skip-link" id="skip-link" href="#report">Zum Bericht springen</a>
  <header class="site-header">
    <div>
      <p class="eyebrow">Politik · Wirtschaft · Sicherheit</p>
      <h1>Persönlicher Lagebericht</h1>
      <p id="updated" class="muted">Bericht wird geladen …</p>
    </div>
    <div class="header-actions">
      <button type="button" id="language-toggle" class="theme-toggle"></button>
      <button type="button" id="theme-toggle" class="theme-toggle"></button>
    </div>
  </header>
```

Replace:
```html
      <label for="period-select">Zeitraum</label>
```
with:
```html
      <label for="period-select" id="period-label">Zeitraum</label>
```

Replace:
```html
    <section id="overall" class="overall" hidden aria-labelledby="overall-title">
      <p class="eyebrow">Gesamtlage</p>
```
with:
```html
    <section id="overall" class="overall" hidden aria-labelledby="overall-title">
      <p class="eyebrow" id="overall-eyebrow">Gesamtlage</p>
```

Replace:
```html
        <div>
          <p class="eyebrow">Transparenz</p>
          <h2 id="cost-title">Geschätzte API-Kosten</h2>
        </div>
```
with:
```html
        <div>
          <p class="eyebrow" id="cost-eyebrow">Transparenz</p>
          <h2 id="cost-title">Geschätzte API-Kosten</h2>
        </div>
```

Replace:
```html
    <p>Keine Anmeldung, kein Tracking und keine Werbung. Originalquellen öffnen sich online in einem neuen Tab.</p>
```
with:
```html
    <p id="footer-note">Keine Anmeldung, kein Tracking und keine Werbung. Originalquellen öffnen sich online in einem neuen Tab.</p>
```

- [ ] **Step 2: Add a `.header-actions` rule to `assets/app.css`**

Find:
```css
.site-header, main, footer { width: min(760px, calc(100% - 2rem)); margin-inline: auto; }
.site-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; padding: 2.2rem 0 1.4rem; border-bottom: 1px solid var(--line); }
```
Replace with:
```css
.site-header, main, footer { width: min(760px, calc(100% - 2rem)); margin-inline: auto; }
.site-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; padding: 2.2rem 0 1.4rem; border-bottom: 1px solid var(--line); }
.header-actions { display: flex; gap: .5rem; }
```

- [ ] **Step 3: Write the failing frontend-contract tests**

Add to `tests/test_frontend_contract.py`, inside `class FrontendContractTests` (near the existing `country-code`/`ALLOWED_HOSTS` tests):

```python
    def test_language_toggle_button_exists_in_markup(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="language-toggle"', html)
        self.assertIn('id="skip-link"', html)
        self.assertIn('id="period-label"', html)
        self.assertIn('id="overall-eyebrow"', html)
        self.assertIn('id="cost-eyebrow"', html)
        self.assertIn('id="footer-note"', html)

    def test_app_js_defines_a_strings_table_for_both_languages(self):
        app = (ROOT / "assets" / "app.js").read_text(encoding="utf-8")
        self.assertIn("const STRINGS", app)
        self.assertIn("de:", app)
        self.assertIn("en:", app)
        self.assertIn("function dataRoot", app)
        self.assertIn("data/en", app)

    def test_language_toggle_never_uses_a_synchronous_alert_or_confirm(self):
        app = (ROOT / "assets" / "app.js").read_text(encoding="utf-8")
        self.assertNotIn("alert(", app)
        self.assertNotIn("confirm(", app)

    def test_cost_meter_always_reads_the_german_index_regardless_of_language(self):
        app = (ROOT / "assets" / "app.js").read_text(encoding="utf-8")
        load_costs_start = app.index("async function loadCurrentCosts")
        load_costs_body = app[load_costs_start:app.index("\n}\n", load_costs_start)]
        self.assertIn("'data/index.json'", load_costs_body)
        self.assertNotIn("dataRoot()", load_costs_body)
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `cd "06 Privat/App-Ideen/Persönlicher Lagebericht" && PYTHONPATH=src python -m unittest tests.test_frontend_contract.FrontendContractTests.test_language_toggle_button_exists_in_markup tests.test_frontend_contract.FrontendContractTests.test_app_js_defines_a_strings_table_for_both_languages tests.test_frontend_contract.FrontendContractTests.test_cost_meter_always_reads_the_german_index_regardless_of_language -v`
Expected: FAIL — none of this exists in `app.js`/`index.html` yet.

- [ ] **Step 5: Add the `STRINGS` table to `assets/app.js`**

Find:
```js
const CATEGORY_LABELS = {
  politics_society: 'Politik & Gesellschaft',
  economy_technology: 'Wirtschaft & Technologie',
  foreign_security: 'Außenpolitik & Sicherheit'
};
const COUNTRY_LABELS = { usa: 'USA', china: 'China', montenegro: 'Montenegro', eu: 'EU' };
const state = {
  index: null, archiveType: 'daily', country: 'usa', report: null,
  costs: null, freshnessNotice: '', reportNotice: ''
};
```
Replace with:
```js
const COUNTRY_LABELS = { usa: 'USA', china: 'China', montenegro: 'Montenegro', eu: 'EU' };
const STRINGS = {
  de: {
    skipLink: 'Zum Bericht springen',
    archive: { daily: 'Tage', weekly: 'Wochen', monthly: 'Monate' },
    periodLabel: 'Zeitraum', periodSelectAriaLabel: 'Zeitraum auswählen',
    countryNavAriaLabel: 'Land oder Region auswählen',
    overallEyebrow: 'Gesamtlage', overallTitle: 'Der Zeitraum im Überblick',
    kicker: { daily: 'Tagesbericht', week: 'Wochenbericht', month: 'Monatsbericht' },
    completeness: { complete: 'Vollständig', partial: 'Teilbericht · Einschränkungen sichtbar' },
    noMajorDevelopment: {
      title: 'Keine neue Meldung in den geprüften Quellen',
      body: 'Für diesen Bereich wurde im Berichtsfenster keine technisch geeignete neue Meldung gefunden.'
    },
    unavailable: {
      title: 'Heute technisch nicht vollständig prüfbar',
      body: 'Mindestens eine benötigte Quelle oder Verarbeitung war nicht verfügbar.'
    },
    additionalImportantPrefix: 'Außerdem wichtig: ',
    contextHeading: 'Einordnung',
    sourcesSummary: (count) => `${count} Originalquelle${count === 1 ? '' : 'n'} anzeigen`,
    sourceLinkBlocked: (name) => `${name} · Link nicht freigegeben`,
    footerNote: 'Keine Anmeldung, kein Tracking und keine Werbung. Originalquellen öffnen sich online in einem neuen Tab.',
    costEyebrow: 'Transparenz', costHeading: 'Geschätzte API-Kosten',
    noArchiveNotice: 'Für diese Archivart ist noch kein Bericht vorhanden.',
    reportLoadError: (message) => `Bericht konnte nicht geladen werden. Ein zuvor gelesener Bericht ist offline möglicherweise weiterhin verfügbar. (${message})`,
    archiveLoadError: (message) => `Das Archiv konnte nicht geladen werden. (${message})`,
    missingReportsNotice: (count, list) => `Für diesen Rückblick fehlen ${count} Tagesberichte: ${list}.`,
    categoryLabels: {
      politics_society: 'Politik & Gesellschaft',
      economy_technology: 'Wirtschaft & Technologie',
      foreign_security: 'Außenpolitik & Sicherheit'
    },
    ratingsAriaLabel: 'Bedeutungsbewertung',
    legacyNote: 'alter Datenstand',
    languageToggleLabel: 'Sprache: Deutsch'
  },
  en: {
    skipLink: 'Skip to report',
    archive: { daily: 'Days', weekly: 'Weeks', monthly: 'Months' },
    periodLabel: 'Period', periodSelectAriaLabel: 'Select period',
    countryNavAriaLabel: 'Select country or region',
    overallEyebrow: 'Overview', overallTitle: 'The period at a glance',
    kicker: { daily: 'Daily report', week: 'Weekly report', month: 'Monthly report' },
    completeness: { complete: 'Complete', partial: 'Partial report · limitations shown' },
    noMajorDevelopment: {
      title: 'No new story in the reviewed sources',
      body: 'No technically suitable new story was found for this section in the reporting window.'
    },
    unavailable: {
      title: 'Not fully checkable today',
      body: 'At least one required source or processing step was unavailable.'
    },
    additionalImportantPrefix: 'Also notable: ',
    contextHeading: 'Context',
    sourcesSummary: (count) => `Show ${count} original source${count === 1 ? '' : 's'}`,
    sourceLinkBlocked: (name) => `${name} · link not approved`,
    footerNote: 'No login, no tracking and no ads. Original sources open online in a new tab.',
    costEyebrow: 'Transparency', costHeading: 'Estimated API costs',
    noArchiveNotice: 'No report is available yet for this archive type.',
    reportLoadError: (message) => `The report could not be loaded. A previously read report may still be available offline. (${message})`,
    archiveLoadError: (message) => `The archive could not be loaded. (${message})`,
    missingReportsNotice: (count, list) => `This review is missing ${count} daily reports: ${list}.`,
    categoryLabels: {
      politics_society: 'Politics & Society',
      economy_technology: 'Economy & Technology',
      foreign_security: 'Foreign Affairs & Security'
    },
    ratingsAriaLabel: 'Significance rating',
    legacyNote: 'legacy data',
    languageToggleLabel: 'Language: English'
  }
};
const state = {
  index: null, archiveType: 'daily', country: 'usa', report: null,
  costs: null, freshnessNotice: '', reportNotice: '', language: 'de'
};
```

`CATEGORY_LABELS` as a bare top-level constant is removed — every former use becomes `strings().categoryLabels`, added in later steps.

- [ ] **Step 6: Add `elements` entries, language state helpers, and wiring**

Find:
```js
const elements = {
  updated: document.getElementById('updated'), notice: document.getElementById('notice'),
  select: document.getElementById('period-select'), overall: document.getElementById('overall'),
  overallCopy: document.getElementById('overall-copy'), report: document.getElementById('report'),
  kicker: document.getElementById('report-kicker'), countryTitle: document.getElementById('country-title'),
  completeness: document.getElementById('completeness'), stories: document.getElementById('stories'),
  costMeter: document.getElementById('cost-meter'), costMonth: document.getElementById('cost-month'),
  costPercent: document.getElementById('cost-percent'), costTrack: document.getElementById('cost-track'),
  costFill: document.getElementById('cost-fill'), costTicks: document.getElementById('cost-ticks'),
  costNote: document.getElementById('cost-note'), themeToggle: document.getElementById('theme-toggle')
};
```
Replace with:
```js
const elements = {
  updated: document.getElementById('updated'), notice: document.getElementById('notice'),
  select: document.getElementById('period-select'), overall: document.getElementById('overall'),
  overallCopy: document.getElementById('overall-copy'), report: document.getElementById('report'),
  kicker: document.getElementById('report-kicker'), countryTitle: document.getElementById('country-title'),
  completeness: document.getElementById('completeness'), stories: document.getElementById('stories'),
  costMeter: document.getElementById('cost-meter'), costMonth: document.getElementById('cost-month'),
  costPercent: document.getElementById('cost-percent'), costTrack: document.getElementById('cost-track'),
  costFill: document.getElementById('cost-fill'), costTicks: document.getElementById('cost-ticks'),
  costNote: document.getElementById('cost-note'), themeToggle: document.getElementById('theme-toggle'),
  languageToggle: document.getElementById('language-toggle'), skipLink: document.getElementById('skip-link'),
  periodLabel: document.getElementById('period-label'), overallEyebrow: document.getElementById('overall-eyebrow'),
  costEyebrow: document.getElementById('cost-eyebrow'), footerNote: document.getElementById('footer-note'),
  countryNav: document.querySelector('.country-nav'), overallTitle: document.getElementById('overall-title'),
  costTitle: document.getElementById('cost-title')
};

const LANGUAGE_STORAGE_KEY = 'lagebericht-language';

function readStoredLanguage() {
  let stored = null;
  try { stored = localStorage.getItem(LANGUAGE_STORAGE_KEY); } catch (_) { stored = null; }
  return stored === 'en' ? 'en' : 'de';
}

function strings() {
  return STRINGS[state.language];
}

function dataRoot() {
  return state.language === 'en' ? 'data/en' : 'data';
}

function applyLanguage(language) {
  state.language = language;
  const s = strings();
  document.documentElement.lang = language;
  elements.skipLink.textContent = s.skipLink;
  elements.languageToggle.textContent = s.languageToggleLabel;
  document.querySelectorAll('[data-archive-type]').forEach((button) => {
    button.textContent = s.archive[button.dataset.archiveType];
  });
  elements.periodLabel.textContent = s.periodLabel;
  elements.select.setAttribute('aria-label', s.periodSelectAriaLabel);
  elements.countryNav.setAttribute('aria-label', s.countryNavAriaLabel);
  elements.overallEyebrow.textContent = s.overallEyebrow;
  elements.overallTitle.textContent = s.overallTitle;
  elements.costEyebrow.textContent = s.costEyebrow;
  elements.costTitle.textContent = s.costHeading;
  elements.footerNote.textContent = s.footerNote;
}

function cycleLanguage() {
  const next = state.language === 'de' ? 'en' : 'de';
  try { localStorage.setItem(LANGUAGE_STORAGE_KEY, next); } catch (_) { /* storage unavailable, language just won't persist */ }
  applyLanguage(next);
  refreshIndex({ preferLatest: state.archiveType === 'daily' });
}
```

- [ ] **Step 7: Apply the language on startup and wire the toggle's click handler**

Find:
```js
applyTheme(readStoredTheme());
elements.themeToggle.addEventListener('click', cycleTheme);
```
Replace with:
```js
applyTheme(readStoredTheme());
elements.themeToggle.addEventListener('click', cycleTheme);
applyLanguage(readStoredLanguage());
elements.languageToggle.addEventListener('click', cycleLanguage);
```

- [ ] **Step 8: Make `loadCurrentCosts` always read the German root, independent of `state.language`**

Replace:
```js
async function loadCurrentCosts() {
  const reference = state.index && state.index.currentCosts;
  const path = reference && reference.path;
  if (!CostModel.isAllowedCostPath(path)) {
    state.costs = null;
    renderCosts(null);
    return;
  }
  try {
    const response = await fetch(path, { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    state.costs = await response.json();
    renderCosts(state.costs);
  } catch (_) {
    state.costs = null;
    renderCosts(null);
  }
}
```
with:
```js
async function loadCurrentCosts() {
  try {
    const indexResponse = await fetch('data/index.json', { cache: 'no-store' });
    if (!indexResponse.ok) throw new Error(`HTTP ${indexResponse.status}`);
    const germanIndex = await indexResponse.json();
    const reference = germanIndex.currentCosts;
    const path = reference && reference.path;
    if (!CostModel.isAllowedCostPath(path)) {
      state.costs = null;
      renderCosts(null);
      return;
    }
    const response = await fetch(path, { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    state.costs = await response.json();
    renderCosts(state.costs);
  } catch (_) {
    state.costs = null;
    renderCosts(null);
  }
}
```

This deliberately always fetches `'data/index.json'` (the German root, literal string, never `dataRoot()`) — the cost meter shows total API spend regardless of the active UI language, per the Global Constraints above.

- [ ] **Step 9: Translate the per-story rendering functions**

Replace:
```js
function renderSources(item, article) {
  if (!item.sources || !item.sources.length) return;
  const details = node('details', null, 'sources');
  details.append(node('summary', `${item.sources.length} Originalquelle${item.sources.length === 1 ? '' : 'n'} anzeigen`));
  const list = node('ul');
  item.sources.forEach((source) => {
    const row = node('li');
    const link = safeSourceLink(source);
    row.append(link || node('span', `${source.name} · Link nicht freigegeben`));
    row.append(node('span', `${source.type} · ${source.titleOriginal}`, 'source-type'));
    list.append(row);
  });
  details.append(list);
  article.append(details);
}

function renderRatings(item, article) {
  const ratings = RatingModel.ratingsForItem(item);
  if (!ratings.length) return;
  const group = node('div', null, 'ratings');
  group.setAttribute('aria-label', 'Bedeutungsbewertung');
  ratings.forEach((rating) => {
    const details = node('details', null, `rating rating-${rating.key}`);
    const summary = document.createElement('summary');
    if (rating.legacy) {
      summary.append(node('span', rating.label, 'rating-label'), node('span', 'alter Datenstand', 'rating-legacy-note'));
    } else {
      summary.append(leafRow(rating.score, 'currentColor'), node('span', rating.label, 'rating-label'));
    }
    details.append(summary);
    details.append(node('p', rating.reasonDe, 'rating-reason'));
    group.append(details);
  });
  article.append(group);
}

function renderStory(item, index) {
  const article = node('article', null, 'story');
  const label = CATEGORY_LABELS[item.id] || item.id;
  const chip = node('div', null, 'story-num');
  chip.append(leafIcon(true, 'currentColor'), document.createTextNode(` No. ${String(index + 1).padStart(3, '0')} — ${label}`));
  article.append(chip);
  const top = node('div', null, 'story-top');
  top.append(node('span', RatingModel.badgeForItem(item), 'badge'));
  article.append(top);
  if (item.status === 'no_major_development') {
    article.append(node('h3', 'Keine neue Meldung in den geprüften Quellen'));
    article.append(node('p', 'Für diesen Bereich wurde im Berichtsfenster keine technisch geeignete neue Meldung gefunden.', 'empty'));
    return article;
  }
  if (item.status === 'unavailable') {
    article.append(node('h3', 'Heute technisch nicht vollständig prüfbar'));
    article.append(node('p', 'Mindestens eine benötigte Quelle oder Verarbeitung war nicht verfügbar.', 'empty'));
    return article;
  }
  article.append(node('h3', item.headlineDe));
  const summary = node('div', null, 'summary');
  (item.summaryDe || []).forEach((sentence) => summary.append(node('p', sentence)));
  article.append(summary);
  const contextSentences = item.contextDe || [];
  if (contextSentences.length) {
    const context = node('section', null, 'context');
    context.append(node('h4', 'Einordnung'));
    contextSentences.forEach((sentence) => context.append(node('p', sentence)));
    article.append(context);
  }
  renderRatings(item, article);
  if (item.additionalImportant) article.append(node('p', `Außerdem wichtig: ${item.additionalImportant}`, 'additional'));
  renderSources(item, article);
  return article;
}
```
with:
```js
function renderSources(item, article) {
  if (!item.sources || !item.sources.length) return;
  const s = strings();
  const details = node('details', null, 'sources');
  details.append(node('summary', s.sourcesSummary(item.sources.length)));
  const list = node('ul');
  item.sources.forEach((source) => {
    const row = node('li');
    const link = safeSourceLink(source);
    row.append(link || node('span', s.sourceLinkBlocked(source.name)));
    row.append(node('span', `${source.type} · ${source.titleOriginal}`, 'source-type'));
    list.append(row);
  });
  details.append(list);
  article.append(details);
}

function renderRatings(item, article) {
  const ratings = RatingModel.ratingsForItem(item);
  if (!ratings.length) return;
  const s = strings();
  const group = node('div', null, 'ratings');
  group.setAttribute('aria-label', s.ratingsAriaLabel);
  ratings.forEach((rating) => {
    const details = node('details', null, `rating rating-${rating.key}`);
    const summary = document.createElement('summary');
    if (rating.legacy) {
      summary.append(node('span', rating.label, 'rating-label'), node('span', s.legacyNote, 'rating-legacy-note'));
    } else {
      summary.append(leafRow(rating.score, 'currentColor'), node('span', rating.label, 'rating-label'));
    }
    details.append(summary);
    details.append(node('p', rating.reasonDe, 'rating-reason'));
    group.append(details);
  });
  article.append(group);
}

function renderStory(item, index) {
  const s = strings();
  const article = node('article', null, 'story');
  const label = s.categoryLabels[item.id] || item.id;
  const chip = node('div', null, 'story-num');
  chip.append(leafIcon(true, 'currentColor'), document.createTextNode(` No. ${String(index + 1).padStart(3, '0')} — ${label}`));
  article.append(chip);
  const top = node('div', null, 'story-top');
  top.append(node('span', RatingModel.badgeForItem(item), 'badge'));
  article.append(top);
  if (item.status === 'no_major_development') {
    article.append(node('h3', s.noMajorDevelopment.title));
    article.append(node('p', s.noMajorDevelopment.body, 'empty'));
    return article;
  }
  if (item.status === 'unavailable') {
    article.append(node('h3', s.unavailable.title));
    article.append(node('p', s.unavailable.body, 'empty'));
    return article;
  }
  article.append(node('h3', item.headlineDe));
  const summary = node('div', null, 'summary');
  (item.summaryDe || []).forEach((sentence) => summary.append(node('p', sentence)));
  article.append(summary);
  const contextSentences = item.contextDe || [];
  if (contextSentences.length) {
    const context = node('section', null, 'context');
    context.append(node('h4', s.contextHeading));
    contextSentences.forEach((sentence) => context.append(node('p', sentence)));
    article.append(context);
  }
  renderRatings(item, article);
  if (item.additionalImportant) article.append(node('p', `${s.additionalImportantPrefix}${item.additionalImportant}`, 'additional'));
  renderSources(item, article);
  return article;
}
```

Field names on `item` (`headlineDe`, `summaryDe`, `contextDe`, `additionalImportant`) stay unchanged in both languages — these are the actual report content, already translated at the data level by Task 2/3/4; only the *labels around* that content come from `STRINGS`.

- [ ] **Step 10: Translate `renderReport`, `loadSelectedReport`, `refreshIndex`**

Replace:
```js
function renderReport() {
  const report = state.report;
  if (!report) return;
  const isDaily = Object.hasOwn(report, 'reportDate');
  const countries = report.countries || [];
  const country = countries.find((item) => item.id === state.country) || countries[0];
  if (!country) throw new Error('Bericht enthält keine Länderansicht.');
  state.country = country.id;
  document.querySelectorAll('[data-country]').forEach((button) => button.setAttribute('aria-pressed', String(button.dataset.country === state.country)));
  elements.countryTitle.textContent = country.label || COUNTRY_LABELS[country.id];
  elements.kicker.textContent = isDaily ? 'Tagesbericht' : report.periodType === 'week' ? 'Wochenbericht' : 'Monatsbericht';
  if (isDaily) {
    elements.completeness.className = 'muted';
    elements.completeness.textContent = report.status === 'complete' ? 'Vollständig' : 'Teilbericht · Einschränkungen sichtbar';
  } else {
    const coverage = PeriodModel.coverage(report);
    elements.completeness.className = 'muted period-coverage';
    elements.completeness.textContent = coverage.label;
  }
  elements.updated.textContent = isDaily ? `Bericht vom ${report.reportDate} · erzeugt ${new Date(report.generatedAt).toLocaleString('de-DE')}` : `${report.periodStart} bis ${report.periodEnd} · erzeugt ${new Date(report.generatedAt).toLocaleString('de-DE')}`;
  elements.stories.replaceChildren(...(country.categories || country.sections || []).map((item, index) => renderStory(item, index)));
  elements.overall.hidden = isDaily;
  elements.overallCopy.replaceChildren();
  if (!isDaily) (report.overallSummary || []).forEach((sentence) => elements.overallCopy.append(node('p', sentence)));
  const missing = report.missingReportDates || [];
  showNotice(missing.length ? `Für diesen Rückblick fehlen ${missing.length} Tagesberichte: ${missing.join(', ')}.` : '');
  elements.report.setAttribute('aria-busy', 'false');
}

async function loadSelectedReport() {
  const path = elements.select.value;
  if (!path) {
    showNotice('Für diese Archivart ist noch kein Bericht vorhanden.');
    return;
  }
  elements.report.setAttribute('aria-busy', 'true');
  try {
    const response = await fetch(path, { cache: 'no-cache' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    state.report = await response.json();
    renderReport();
  } catch (error) {
    elements.report.setAttribute('aria-busy', 'false');
    showNotice(`Bericht konnte nicht geladen werden. Ein zuvor gelesener Bericht ist offline möglicherweise weiterhin verfügbar. (${error.message})`);
  }
}

async function start() {
  await refreshIndex({ preferLatest: true });
}

async function refreshIndex({ preferLatest = false } = {}) {
  const previousPath = elements.select.value;
  const previousLatest = state.index && state.index.latestDaily;
  try {
    const response = await fetch('data/index.json', { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    state.index = await response.json();
    void loadCurrentCosts();
    state.freshnessNotice = FreshnessModel.dailyNotice(state.index, new Date());
    renderNotice();
    fillPeriodSelect();
    const entries = archiveEntries();
    if (!entries.length) {
      showNotice('Für diese Archivart ist noch kein Bericht vorhanden.');
      return;
    }
    const hasPreviousPath = entries.some((entry) => entry.path === previousPath);
    const hasNewDaily = state.archiveType === 'daily' && state.index.latestDaily !== previousLatest;
    if (!preferLatest && !hasNewDaily && hasPreviousPath) elements.select.value = previousPath;
    await loadSelectedReport();
  } catch (error) {
    renderCosts(null);
    showNotice(`Das Archiv konnte nicht geladen werden. (${error.message})`);
    elements.report.setAttribute('aria-busy', 'false');
  }
}
```
with:
```js
function renderReport() {
  const report = state.report;
  if (!report) return;
  const s = strings();
  const isDaily = Object.hasOwn(report, 'reportDate');
  const countries = report.countries || [];
  const country = countries.find((item) => item.id === state.country) || countries[0];
  if (!country) throw new Error('Bericht enthält keine Länderansicht.');
  state.country = country.id;
  document.querySelectorAll('[data-country]').forEach((button) => button.setAttribute('aria-pressed', String(button.dataset.country === state.country)));
  elements.countryTitle.textContent = country.label || COUNTRY_LABELS[country.id];
  elements.kicker.textContent = isDaily ? s.kicker.daily : s.kicker[report.periodType];
  if (isDaily) {
    elements.completeness.className = 'muted';
    elements.completeness.textContent = report.status === 'complete' ? s.completeness.complete : s.completeness.partial;
  } else {
    const coverage = PeriodModel.coverage(report);
    elements.completeness.className = 'muted period-coverage';
    elements.completeness.textContent = coverage.label;
  }
  elements.updated.textContent = isDaily ? `Bericht vom ${report.reportDate} · erzeugt ${new Date(report.generatedAt).toLocaleString('de-DE')}` : `${report.periodStart} bis ${report.periodEnd} · erzeugt ${new Date(report.generatedAt).toLocaleString('de-DE')}`;
  elements.stories.replaceChildren(...(country.categories || country.sections || []).map((item, index) => renderStory(item, index)));
  elements.overall.hidden = isDaily;
  elements.overallCopy.replaceChildren();
  if (!isDaily) (report.overallSummary || []).forEach((sentence) => elements.overallCopy.append(node('p', sentence)));
  const missing = report.missingReportDates || [];
  showNotice(missing.length ? s.missingReportsNotice(missing.length, missing.join(', ')) : '');
  elements.report.setAttribute('aria-busy', 'false');
}

async function loadSelectedReport() {
  const path = elements.select.value;
  if (!path) {
    showNotice(strings().noArchiveNotice);
    return;
  }
  elements.report.setAttribute('aria-busy', 'true');
  try {
    const response = await fetch(path, { cache: 'no-cache' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    state.report = await response.json();
    renderReport();
  } catch (error) {
    elements.report.setAttribute('aria-busy', 'false');
    showNotice(strings().reportLoadError(error.message));
  }
}

async function start() {
  await refreshIndex({ preferLatest: true });
}

async function refreshIndex({ preferLatest = false } = {}) {
  const previousPath = elements.select.value;
  const previousLatest = state.index && state.index.latestDaily;
  try {
    const response = await fetch(`${dataRoot()}/index.json`, { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    state.index = await response.json();
    void loadCurrentCosts();
    state.freshnessNotice = FreshnessModel.dailyNotice(state.index, new Date());
    renderNotice();
    fillPeriodSelect();
    const entries = archiveEntries();
    if (!entries.length) {
      showNotice(strings().noArchiveNotice);
      return;
    }
    const hasPreviousPath = entries.some((entry) => entry.path === previousPath);
    const hasNewDaily = state.archiveType === 'daily' && state.index.latestDaily !== previousLatest;
    if (!preferLatest && !hasNewDaily && hasPreviousPath) elements.select.value = previousPath;
    await loadSelectedReport();
  } catch (error) {
    renderCosts(null);
    showNotice(strings().archiveLoadError(error.message));
    elements.report.setAttribute('aria-busy', 'false');
  }
}
```

Note `elements.updated`'s date/time formatting intentionally stays `'de-DE'`/German wording (`Bericht vom …`/`erzeugt …`) in both languages — this line was not in the design spec's translate list, and the report content itself (`headlineDe` etc.) already carries language-appropriate text; leave this as a known, documented gap for a future pass rather than guessing at scope the spec didn't define.

- [ ] **Step 11: Run the frontend-contract tests to verify they pass**

Run: `cd "06 Privat/App-Ideen/Persönlicher Lagebericht" && PYTHONPATH=src python -m unittest tests.test_frontend_contract -v`
Expected: all PASS.

- [ ] **Step 12: Run the full suite**

Run: `cd "06 Privat/App-Ideen/Persönlicher Lagebericht" && PYTHONPATH=src python -m unittest discover -s tests -v`
Expected: all PASS.

- [ ] **Step 13: Bump the PWA shell cache version**

This project has hit the "changed `app.js`/`app.css` without bumping the service worker cache" bug twice already (see `00 Übersicht.md`'s "Stand vom 08.08.2026" entries). Bump every `v12`/`v=12` reference to `v13` in `service-worker.js` (the `SHELL_CACHE` const and all five `?v=12` entries in `SHELL`), `index.html` (five script tags), and `assets/app.js`'s own service-worker registration URL — then update the matching pinned literals in `tests/test_frontend_contract.py`. Run `PYTHONPATH=src python -m unittest tests.test_frontend_contract -v` again to confirm.

- [ ] **Step 14: Manual verification in the browser**

Start a local static server from the project root and load the app (the controller has a `lagebericht-static` entry already configured in the vault-root `.claude/launch.json` from the EU-block work; reuse it, or start a fresh `python -m http.server` if that port is in use). Because no real `data/en/` tree exists yet (only created by the next real scheduled run against the live API, which this plan deliberately does not trigger), toggling to English will fail to fetch `data/en/index.json` (404) — confirm this fails *gracefully*: the archive-load error notice appears in English (`strings().archiveLoadError` already switched before the fetch failure, since `applyLanguage` runs synchronously before `refreshIndex`'s fetch), no unhandled JS exception in the console, and toggling back to German immediately restores the working German view. Confirm the language toggle button is visible next to the theme toggle, keyboard-reachable, and does not overflow the header at 375px width.

- [ ] **Step 15: Commit**

```bash
git add index.html assets/app.css assets/app.js service-worker.js tests/test_frontend_contract.py
git commit -m "feat: add a DE/EN language toggle with a language-aware data root and translated UI copy"
```

---

### Task 6: Update project documentation

**Files:**
- Modify: `06 Privat/App-Ideen/Persönlicher Lagebericht/00 Übersicht.md` (vault file, not part of the git repo — same convention as the EU-block plan's Task 6)

**Interfaces:** none — documentation only, no code.

- [ ] **Step 1: Update the vault project overview**

In `00 Übersicht.md`, add a dated "Stand" entry documenting that the DE/EN language toggle was added: the Haiku-translation-plus-deterministic-merge architecture (and why merge-not-trust was chosen over the spec's original schema-only validation), the `data/en/` mirrored tree, the `publish.py` URL-prefix bug found and fixed during planning, and that the first real English report only appears after the next scheduled automated run (this plan does not trigger a paid API call). Link to `docs/superpowers/plans/2026-08-08-sprachumschalter.md` and `docs/superpowers/specs/2026-08-08-sprachumschalter-design.md` in the app repo. Also note the explicitly deferred scope from the design spec: the four JS model files' (`rating-model.js`, `freshness-model.js`, `period-model.js`, `cost-model.js`) hardcoded German return strings stay German-only in the English view for now.

- [ ] **Step 2: No test/commit for this task**

This file is outside the git repository this plan's other tasks commit to. Edit it directly with the Edit tool; do not run `git add`/`git commit` against the app repo for this task's file.
