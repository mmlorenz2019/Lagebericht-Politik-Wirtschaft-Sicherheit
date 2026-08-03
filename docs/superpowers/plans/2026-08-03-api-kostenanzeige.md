# Public API Cost Meter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Erfasse den von Anthropic gemeldeten Tokenverbrauch automatisch und zeige den aktuellen Verbrauch eines öffentlichen 5-Euro-Monatsbudgets als kleine Transparenz-Karte in der PWA.

**Architecture:** Ein eigenständiges Python-Kostenmodul berechnet Beträge mit `Decimal`, schreibt pro API-Aufruf ein dedupliziertes Ereignis in `data/costs/YYYY-MM.json` und aktualisiert den Datenindex. Der Anthropic-Client meldet Nutzungsdaten über einen fehlertoleranten Observer; die CLI-Skripte liefern Berichtskontext. Ein reines JavaScript-Modell validiert die öffentliche Monatszusammenfassung und versorgt die ausgewählte Karte B mit sicheren Darstellungswerten.

**Tech Stack:** Python 3.12 Standardbibliothek, `unittest`, JSON/JSON Schema, Vanilla JavaScript, HTML/CSS, GitHub Actions, GitHub Pages/PWA.

## Global Constraints

- Monatsbudget: exakt 5,00 Euro.
- Abrechnungsmonat und Monatswechsel verwenden `Europe/Berlin`.
- Öffentlich angezeigt wird nur der aktuelle Monat; ältere Monatsdateien bleiben erhalten.
- Die Anzeige heißt „Geschätzte API-Kosten“ und darf nicht als Rechnung bezeichnet werden.
- Modellpreise laut [Anthropic](https://platform.claude.com/docs/en/about-claude/pricing): Haiku 4.5 = 1 USD/MTok Input und 5 USD/MTok Output; Sonnet 4.6 = 3 USD/MTok Input und 15 USD/MTok Output.
- Initialer manueller Umrechnungskurs: 1 USD = 0,8780 EUR, abgeleitet aus dem letzten geprüften [EZB-Referenzwert](https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.de.html) 1 EUR = 1,1389 USD vom 27.07.2026.
- Erfassung beginnt am Bereitstellungstag; frühere Aufrufe werden nicht rückwirkend erfunden.
- Bei einer API-Antwort werden auch fehlgeschlagene `refusal`- und `max_tokens`-Aufrufe mit gemeldeter Nutzung berechnet.
- Transportfehler ohne Nutzungsantwort erhöhen `unmeasuredCalls`, aber niemals den geschätzten Betrag.
- Kostenfehler dürfen einen gültigen Bericht nicht verhindern.
- Öffentliche Dateien enthalten keine Prompts, Nachrichteninhalte, API-Schlüssel, Header, Provider-Request-IDs oder GitHub-Zugangsdaten.
- Keine neue Laufzeitabhängigkeit; nur Python- und Browser-Standardfunktionen verwenden.
- Vorhandene fremde Änderungen in `00 Übersicht.md`, `01 Designspezifikation.md` und `docs/2026-07-31-implementierungsplan.md` nicht verändern oder committen.

---

## File Map

- Create `config/api-pricing.json`: versionierte Modellpreise, Monatsbudget, USD-EUR-Kurs und Erfassungsbeginn.
- Create `schemas/cost-report.schema.json`: öffentlicher Vertrag für Monatsdateien.
- Create `src/lagebericht/costs.py`: Preisvalidierung, `Decimal`-Berechnung, Monatszuordnung, Ereignisdeduplizierung und atomische Speicherung.
- Create `tests/test_costs.py`: fokussierte Tests für Mathematik, Grenzen, Speicherung und Datenschutz.
- Modify `src/lagebericht/anthropic_client.py`: fehlertoleranter Usage-Observer.
- Modify `tests/test_anthropic_client.py`: Observer-Vertrag für Erfolg, Providerfehler, Timeout und fehlerhaften Observer.
- Modify `scripts/run_daily.py`: Tageskontext und Kostenrekorder injizieren.
- Modify `scripts/run_period.py`: Wochen-/Monatskontext und Kostenrekorder injizieren.
- Modify `tests/test_cli.py`: Observer-Verdrahtung und Kostenfehler-Isolation prüfen.
- Modify `src/lagebericht/publish.py`: aktuelle Kostendatei in `data/index.json` aufnehmen.
- Modify `tests/test_publish.py`: Indexvertrag und beschädigte Kostendateien prüfen.
- Create `assets/cost-model.js`: reine Validierung und Darstellungslogik der Karte.
- Modify `assets/app.js`: Kostendatei unabhängig laden und Karte sicher befüllen.
- Modify `assets/app.css`: Variante B, Schwellenfarben, Dark Mode und mobile Beschriftung.
- Modify `index.html`: semantische Transparenz-Karte und versionierte Assets.
- Modify `tests/test_frontend_contract.py`: JavaScript-Modell, DOM-Vertrag, Sicherheit und Barrierefreiheit testen.
- Modify `service-worker.js`: Shell-Cache auf v9 anheben und `cost-model.js` aufnehmen.
- Create `data/costs/2026-08.json`: gültiger Nullstand mit sichtbarem Erfassungsbeginn.
- Modify `data/index.json`: `currentCosts` auf die August-Datei setzen.
- Modify `README.md`: Kostenschätzung, Preisquelle, Grenzen und Aktualisierung dokumentieren.

---

### Task 1: Pricing and cost calculation domain

**Files:**
- Create: `config/api-pricing.json`
- Create: `schemas/cost-report.schema.json`
- Create: `src/lagebericht/costs.py`
- Create: `tests/test_costs.py`

**Interfaces:**
- Produces: `CostDataError`, `load_pricing(path: Path) -> dict`, `estimate_cost(model: str, usage: dict, pricing: dict) -> tuple[Decimal, Decimal]`, `berlin_month(moment: datetime) -> str`.
- Consumes: Python `Decimal`, `ZoneInfo("Europe/Berlin")`, JSON files only.

- [ ] **Step 1: Write failing pricing and calculation tests**

Create `tests/test_costs.py` with fixtures that use temporary files and these core assertions:

```python
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import json
import tempfile
import unittest

from lagebericht.costs import CostDataError, berlin_month, estimate_cost, load_pricing


ROOT = Path(__file__).parents[1]


class CostCalculationTests(unittest.TestCase):
    def setUp(self):
        self.pricing = load_pricing(ROOT / "config" / "api-pricing.json")

    def test_estimates_haiku_input_and_output_in_usd_and_eur(self):
        usd, eur = estimate_cost(
            "claude-haiku-4-5-20251001",
            {"input_tokens": 1_000_000, "output_tokens": 1_000_000},
            self.pricing,
        )
        self.assertEqual(usd, Decimal("6"))
        self.assertEqual(eur, Decimal("5.2680"))

    def test_estimates_sonnet_and_cache_tokens(self):
        usd, eur = estimate_cost(
            "claude-sonnet-4-6",
            {
                "input_tokens": 1_000_000,
                "output_tokens": 1_000_000,
                "cache_creation_input_tokens": 1_000_000,
                "cache_read_input_tokens": 1_000_000,
            },
            self.pricing,
        )
        self.assertEqual(usd, Decimal("22.05"))
        self.assertEqual(eur, Decimal("19.359900"))

    def test_rejects_unknown_model_and_invalid_tokens(self):
        with self.assertRaises(CostDataError):
            estimate_cost("unknown", {"input_tokens": 1, "output_tokens": 1}, self.pricing)
        for value in (-1, True, "10"):
            with self.subTest(value=value), self.assertRaises(CostDataError):
                estimate_cost(
                    "claude-sonnet-4-6",
                    {"input_tokens": value, "output_tokens": 1},
                    self.pricing,
                )

    def test_berlin_month_uses_local_midnight(self):
        self.assertEqual(berlin_month(datetime(2026, 7, 31, 22, 30, tzinfo=timezone.utc)), "2026-08")
```

- [ ] **Step 2: Run the focused test to verify RED**

Run:

```powershell
$env:PYTHONPATH='src'; python -m unittest tests.test_costs.CostCalculationTests -v
```

Expected: import failure because `lagebericht.costs` does not exist.

- [ ] **Step 3: Add the exact pricing configuration**

Create `config/api-pricing.json`:

```json
{
  "schemaVersion": 1,
  "priceVersion": "anthropic-2026-08-03",
  "budgetEur": "5.00",
  "usdToEur": "0.8780",
  "rateEffectiveDate": "2026-07-27",
  "collectionStartedAt": "2026-08-03T00:00:00+02:00",
  "models": {
    "claude-haiku-4-5-20251001": {
      "inputUsdPerMTok": "1.00",
      "outputUsdPerMTok": "5.00",
      "cacheWriteUsdPerMTok": "1.25",
      "cacheReadUsdPerMTok": "0.10"
    },
    "claude-sonnet-4-6": {
      "inputUsdPerMTok": "3.00",
      "outputUsdPerMTok": "15.00",
      "cacheWriteUsdPerMTok": "3.75",
      "cacheReadUsdPerMTok": "0.30"
    }
  }
}
```

- [ ] **Step 4: Implement strict Decimal calculation**

Create `src/lagebericht/costs.py`. Parse all monetary values from strings into `Decimal`; reject bools, negative values, token values above `1_000_000_000`, missing fields and unknown models. Use this formula:

```python
MILLION = Decimal(1_000_000)

usd = (
    Decimal(input_tokens) * model_prices["inputUsdPerMTok"]
    + Decimal(output_tokens) * model_prices["outputUsdPerMTok"]
    + Decimal(cache_creation_tokens) * model_prices["cacheWriteUsdPerMTok"]
    + Decimal(cache_read_tokens) * model_prices["cacheReadUsdPerMTok"]
) / MILLION
eur = usd * pricing["usdToEur"]
```

`berlin_month()` must reject naive datetimes and return `moment.astimezone(ZoneInfo("Europe/Berlin")).strftime("%Y-%m")`.

- [ ] **Step 5: Add the complete monthly JSON Schema**

Create `schemas/cost-report.schema.json` with `additionalProperties: false`. Require top-level fields `schemaVersion`, `month`, `timezone`, `budgetEur`, `estimatedCostUsd`, `estimatedCostEur`, `budgetPercent`, `unmeasuredCalls`, `collectionStartedAt`, `priceVersion`, `rate`, and `events`. Each event requires `eventId`, `occurredAt`, `reportType`, `reportId`, `model`, `outcome`, `measured`, `usage`, `estimatedCostUsd`, and `estimatedCostEur`. Allow cost fields to be `null` only when `measured` is false. Permit report types `daily`, `week`, `month`; outcomes `end_turn`, `max_tokens`, `refusal`, `transport_error`, `invalid_response`.

- [ ] **Step 6: Run focused tests and commit**

Run:

```powershell
$env:PYTHONPATH='src'; python -m unittest tests.test_costs.CostCalculationTests -v
git diff --check
```

Expected: all calculation tests pass.

Commit:

```powershell
git add config/api-pricing.json schemas/cost-report.schema.json src/lagebericht/costs.py tests/test_costs.py
git commit -m "feat: add API cost calculation model"
```

---

### Task 2: Atomic monthly ledger and data index

**Files:**
- Modify: `src/lagebericht/costs.py`
- Modify: `src/lagebericht/publish.py`
- Modify: `tests/test_costs.py`
- Modify: `tests/test_publish.py`

**Interfaces:**
- Consumes: `load_pricing`, `estimate_cost`, `berlin_month` from Task 1.
- Produces: `CostContext(report_type: str, report_id: str, run_id: str, run_attempt: str)`, `context_from_environment(report_type: str, report_id: str, environ: Mapping[str, str] | None = None) -> CostContext`, `CostRecorder(data_root: Path, pricing_path: Path, context: CostContext, now=None)`, `CostRecorder.observe(model: str, usage: dict | None, outcome: str) -> None`, and `rebuild_index(...)["currentCosts"]`.

- [ ] **Step 1: Write failing ledger tests**

Extend `tests/test_costs.py` with tests that construct a recorder under `TemporaryDirectory`:

```python
class CostRecorderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.pricing_path = ROOT / "config" / "api-pricing.json"
        self.model = "claude-haiku-4-5-20251001"
        self.moment = datetime(2026, 8, 3, 10, 0, tzinfo=timezone.utc)
        self.now = lambda: self.moment

    def test_context_uses_github_environment_or_local_defaults(self):
        self.assertEqual(
            context_from_environment("daily", "2026-08-03", {}),
            CostContext("daily", "2026-08-03", "local", "1"),
        )
        self.assertEqual(
            context_from_environment(
                "week", "2026-W31", {"GITHUB_RUN_ID": "77", "GITHUB_RUN_ATTEMPT": "2"}
            ),
            CostContext("week", "2026-W31", "77", "2"),
        )

    def test_recorder_writes_measured_and_unmeasured_events_atomically(self):
        context = CostContext("daily", "2026-08-03", "run-7", "1")
        recorder = CostRecorder(self.root, self.pricing_path, context, now=self.now)
        recorder.observe(
            self.model,
            {"input_tokens": 1000, "output_tokens": 200},
            "end_turn",
        )
        recorder.observe("claude-sonnet-4-6", None, "transport_error")
        report = json.loads((self.root / "costs" / "2026-08.json").read_text(encoding="utf-8"))
        self.assertEqual(report["unmeasuredCalls"], 1)
        self.assertEqual(len(report["events"]), 2)
        self.assertTrue(report["events"][0]["measured"])
        self.assertFalse(report["events"][1]["measured"])
        self.assertNotIn("prompt", json.dumps(report))

    def test_recorder_deduplicates_same_run_attempt_and_call_number(self):
        context = CostContext("daily", "2026-08-03", "run-7", "1")
        first = CostRecorder(self.root, self.pricing_path, context, now=self.now)
        first.observe(self.model, {"input_tokens": 10, "output_tokens": 5}, "end_turn")
        repeated = CostRecorder(self.root, self.pricing_path, context, now=self.now)
        repeated.observe(self.model, {"input_tokens": 10, "output_tokens": 5}, "end_turn")
        report = json.loads((self.root / "costs" / "2026-08.json").read_text(encoding="utf-8"))
        self.assertEqual(len(report["events"]), 1)
```

Add a `tests/test_publish.py` case asserting:

```python
def test_rebuild_index_exposes_latest_valid_cost_month(self):
    costs = self.root / "costs" / "2026-08.json"
    costs.parent.mkdir(parents=True)
    costs.write_text(json.dumps({"schemaVersion": 1, "month": "2026-08"}), encoding="utf-8")
    index = rebuild_index(self.root)
    self.assertEqual(index["currentCosts"], {
        "month": "2026-08",
        "path": "data/costs/2026-08.json",
    })
```

- [ ] **Step 2: Run ledger and index tests to verify RED**

Run:

```powershell
$env:PYTHONPATH='src'; python -m unittest tests.test_costs tests.test_publish -v
```

Expected: failures for missing `CostContext`, `CostRecorder`, and `currentCosts`.

- [ ] **Step 3: Implement event identity and monthly aggregation**

In `src/lagebericht/costs.py`:

- implement `context_from_environment()` with the passed mapping or `os.environ`, defaulting to `run_id="local"` and `run_attempt="1"`;
- use a per-recorder zero-based call counter;
- form `eventId` as SHA-256 of `run_id|run_attempt|report_type|report_id|call_index|model`;
- accept only the five documented outcomes;
- store raw token counts only, never request text;
- sort events by `(occurredAt, eventId)`;
- recompute totals from all measured events after deduplication;
- compute `budgetPercent = estimatedCostEur / budgetEur * 100` without clamping;
- serialize monetary totals as JSON numbers rounded to six decimals and `budgetPercent` to one decimal;
- atomically replace the monthly file using a sibling `.tmp` file, `flush`, `fsync`, and `os.replace`;
- after a successful cost write, atomically rebuild `data/index.json`.

When `usage` is missing, malformed, unpriced or out of bounds, store an unmeasured event with `usage: null` and both event cost fields `null`. Never substitute zero for an unknown amount.

- [ ] **Step 4: Add the current cost pointer to the index**

Modify `rebuild_index()` in `src/lagebericht/publish.py` to scan `data/costs/*.json` in reverse filename order. Include only a JSON object whose `month` equals the filename stem and whose `schemaVersion` is `1`. Return `currentCosts: null` when none is valid; otherwise return the newest `{month, path}` object. Raise the index `schemaVersion` from 1 to 2.

- [ ] **Step 5: Run focused tests and commit**

Run:

```powershell
$env:PYTHONPATH='src'; python -m unittest tests.test_costs tests.test_publish -v
git diff --check
```

Commit:

```powershell
git add src/lagebericht/costs.py src/lagebericht/publish.py tests/test_costs.py tests/test_publish.py
git commit -m "feat: persist monthly API cost ledger"
```

---

### Task 3: Anthropic usage observer

**Files:**
- Modify: `src/lagebericht/anthropic_client.py`
- Modify: `tests/test_anthropic_client.py`

**Interfaces:**
- Consumes: a callback compatible with `CostRecorder.observe(model, usage, outcome)`.
- Produces: optional constructor argument `usage_observer: Callable[[str, dict | None, str], None] | None = None`.

- [ ] **Step 1: Write failing observer tests**

Add tests covering these exact cases:

```python
def test_reports_usage_before_returning_structured_content(self):
    client_class = load_client_class()
    observed = []
    response = {
        "content": [{"type": "text", "text": '{"ok": true}'}],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 10, "output_tokens": 4},
    }
    client = client_class(
        "secret",
        transport=RecordingTransport(response),
        usage_observer=lambda model, usage, outcome: observed.append((model, usage, outcome)),
    )
    self.assertEqual(client.generate_json("model", "Rules", "Input", "example", {}), {"ok": True})
    self.assertEqual(observed, [("model", response["usage"], "end_turn")])

def test_reports_max_tokens_usage_before_raising(self):
    client_class = load_client_class()
    error_class = load_error_class()
    observed = []
    response = {
        "content": [{"type": "text", "text": '{"ok": false}'}],
        "stop_reason": "max_tokens",
        "usage": {"input_tokens": 10, "output_tokens": 8192},
    }
    client = client_class(
        "secret",
        transport=RecordingTransport(response),
        usage_observer=lambda model, usage, outcome: observed.append((model, usage, outcome)),
    )
    with self.assertRaisesRegex(error_class, "token limit"):
        client.generate_json("model", "Rules", "Input", "example", {})
    self.assertEqual(observed[0][2], "max_tokens")

def test_reports_unmeasured_transport_error(self):
    client_class = load_client_class()
    error_class = load_error_class()
    observed = []
    def transport(url, headers, payload, timeout):
        raise TimeoutError("late")
    client = client_class(
        "secret",
        transport=transport,
        usage_observer=lambda model, usage, outcome: observed.append((model, usage, outcome)),
    )
    with self.assertRaises(error_class):
        client.generate_json("model", "Rules", "Input", "example", {})
    self.assertEqual(observed, [("model", None, "transport_error")])

def test_broken_observer_never_breaks_valid_model_output(self):
    client_class = load_client_class()
    response = {
        "content": [{"type": "text", "text": '{"ok": true}'}],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 10, "output_tokens": 4},
    }
    def broken_observer(model, usage, outcome):
        raise OSError("disk")
    client = client_class(
        "secret",
        transport=RecordingTransport(response),
        usage_observer=broken_observer,
    )
    self.assertEqual(client.generate_json("model", "Rules", "Input", "example", {}), {"ok": True})
```

- [ ] **Step 2: Run observer tests to verify RED**

Run:

```powershell
$env:PYTHONPATH='src'; python -m unittest tests.test_anthropic_client -v
```

Expected: constructor rejects `usage_observer`.

- [ ] **Step 3: Implement exactly-once observation**

Add `usage_observer` to the constructor and a private `_observe(model, usage, outcome)` method that catches `Exception` from the observer. Wrap only the transport call so transport exceptions emit `(model, None, "transport_error")` once. As soon as a dictionary response exists, emit its `usage` and normalized stop reason before any refusal, token-limit, text or JSON validation raises. Map missing/unknown stop reasons to `invalid_response`.

- [ ] **Step 4: Run client tests and commit**

Run:

```powershell
$env:PYTHONPATH='src'; python -m unittest tests.test_anthropic_client -v
```

Commit:

```powershell
git add src/lagebericht/anthropic_client.py tests/test_anthropic_client.py
git commit -m "feat: expose Anthropic usage events"
```

---

### Task 4: Daily, weekly and monthly CLI wiring

**Files:**
- Modify: `scripts/run_daily.py`
- Modify: `scripts/run_period.py`
- Modify: `tests/test_cli.py`

**Interfaces:**
- Consumes: `CostContext`, `CostRecorder`, and `AnthropicMessagesClient(..., usage_observer=...)`.
- Produces: `build_daily_client(api_key: str, data_root: Path, report_date: date, *, transport=None, environ=None) -> AnthropicMessagesClient`; every paid CLI call has `reportType`, `reportId`, `GITHUB_RUN_ID`, and `GITHUB_RUN_ATTEMPT` context.

- [ ] **Step 1: Write failing CLI construction tests**

Extend `tests/test_cli.py` with a real temporary-ledger test:

```python
import json
from datetime import date

def test_daily_client_records_usage_with_local_context(self):
    import scripts.run_daily as run_daily

    def transport(url, headers, payload, timeout):
        return {
            "content": [{"type": "text", "text": '{"ok": true}'}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 4},
        }

    with tempfile.TemporaryDirectory() as folder:
        client = run_daily.build_daily_client(
            "test-key",
            Path(folder),
            date(2026, 8, 3),
            transport=transport,
            environ={},
        )
        self.assertEqual(client.generate_json("model", "rules", "input", "schema", {}), {"ok": True})
        ledger = json.loads((Path(folder) / "costs" / "2026-08.json").read_text(encoding="utf-8"))
        self.assertEqual(ledger["events"][0]["reportType"], "daily")
        self.assertEqual(ledger["events"][0]["reportId"], "2026-08-03")
```

Extend the existing period-client test to call:

```python
client = run_period.build_period_client("test-key", usage_observer=observer, transport=transport)
self.assertIs(client.usage_observer, observer)
```

Add this source-contract assertion. The observer-failure isolation itself remains covered at the Anthropic-client boundary in Task 3.

```python
def test_period_cli_wires_week_and_month_cost_contexts(self):
    source = (ROOT / "scripts" / "run_period.py").read_text(encoding="utf-8")
    self.assertIn('context_from_environment("week", week_id)', source)
    self.assertIn('context_from_environment("month", month_id)', source)
    self.assertIn("usage_observer=recorder.observe", source)
```

- [ ] **Step 2: Run CLI tests to verify RED**

Run:

```powershell
$env:PYTHONPATH='src'; python -m unittest tests.test_cli -v
```

- [ ] **Step 3: Wire daily context before client creation**

In `scripts/run_daily.py`, determine `report_date` before constructing the client. Implement:

```python
def build_daily_client(api_key, data_root, report_date, *, transport=None, environ=None):
    context = context_from_environment("daily", report_date.isoformat(), environ)
    recorder = CostRecorder(data_root, Path("config/api-pricing.json"), context)
    options = {"usage_observer": recorder.observe}
    if transport is not None:
        options["transport"] = transport
    return AnthropicMessagesClient(api_key, **options)
```

Cost recording remains active for `--dry-run`, because a dry run still consumes tokens.

- [ ] **Step 4: Wire period context and preserve test injection**

Change the period factory signature to:

```python
def build_period_client(api_key: str, *, usage_observer=None, transport=None) -> AnthropicMessagesClient:
```

Determine the canonical week ID from the requested Sunday using `isocalendar()` and the month ID before client creation. Build a recorder with `context_from_environment("week", week_id)` or `context_from_environment("month", month_id)` and pass its observer to `build_period_client`. A recorder may exist for a no-data period, but it writes no event because no Anthropic call occurs.

- [ ] **Step 5: Run CLI tests and commit**

Run:

```powershell
$env:PYTHONPATH='src'; python -m unittest tests.test_cli tests.test_aggregate -v
git diff --check
```

Commit:

```powershell
git add scripts/run_daily.py scripts/run_period.py tests/test_cli.py
git commit -m "feat: record report API usage"
```

---

### Task 5: Cost presentation model and selected card B

**Files:**
- Create: `assets/cost-model.js`
- Modify: `assets/app.js`
- Modify: `assets/app.css`
- Modify: `index.html`
- Modify: `tests/test_frontend_contract.py`

**Interfaces:**
- Consumes: `state.index.currentCosts.path` and the monthly cost JSON from Task 2.
- Produces: global/CommonJS `CostModel.presentation(report, now)` returning `{available, monthLabel, percentLabel, widthPercent, tone, accessibleLabel, estimateNote, tickLabels}`.

- [ ] **Step 1: Write failing pure JavaScript model tests**

Add `COST_MODEL = ROOT / "assets" / "cost-model.js"` and a Node helper patterned after `run_period_model`. Test:

```python
def test_cost_model_presents_budget_percentage_and_caps_only_width(self):
    report = {
        "schemaVersion": 1,
        "month": "2026-08",
        "budgetEur": 5.0,
        "estimatedCostEur": 0.84,
        "budgetPercent": 16.8,
        "unmeasuredCalls": 0,
        "collectionStartedAt": "2026-08-03T00:00:00+02:00",
    }
    result = run_cost_model(report, "2026-08-03T12:00:00+02:00")
    self.assertEqual(result["percentLabel"], "16,8 %")
    self.assertEqual(result["widthPercent"], 16.8)
    self.assertEqual(result["tone"], "normal")
    self.assertIn("0,84", result["accessibleLabel"])

def test_cost_model_marks_minimum_estimate_and_over_budget(self):
    report = {
        "schemaVersion": 1,
        "month": "2026-08",
        "budgetEur": 5.0,
        "estimatedCostEur": 6.0,
        "budgetPercent": 120.0,
        "unmeasuredCalls": 2,
        "collectionStartedAt": "2026-08-03T00:00:00+02:00",
    }
    result = run_cost_model(report, "2026-08-03T12:00:00+02:00")
    self.assertEqual(result["widthPercent"], 100)
    self.assertEqual(result["percentLabel"], "120,0 %")
    self.assertEqual(result["tone"], "over")
    self.assertIn("mindestens", result["estimateNote"])
```

Add the boundary and invalid-input cases explicitly:

```python
def test_cost_model_uses_warning_at_seventy_five_percent(self):
    report = cost_report(estimatedCostEur=3.75, budgetPercent=75.0)
    self.assertEqual(run_cost_model(report, "2026-08-03T12:00:00+02:00")["tone"], "warning")

def test_cost_model_rejects_malformed_and_past_month_data(self):
    malformed = cost_report(estimatedCostEur=-1, budgetPercent=-20)
    self.assertFalse(run_cost_model(malformed, "2026-08-03T12:00:00+02:00")["available"])
    past = cost_report(month="2026-07")
    self.assertFalse(run_cost_model(past, "2026-08-03T12:00:00+02:00")["available"])
```

Define `cost_report(**changes)` beside `run_cost_model` so it returns the same complete valid base object used in the first test and applies `value.update(changes)`.

- [ ] **Step 2: Run the frontend model tests to verify RED**

Run:

```powershell
$env:PYTHONPATH='src'; python -m unittest tests.test_frontend_contract.FrontendContractTests.test_cost_model_presents_budget_percentage_and_caps_only_width -v
```

- [ ] **Step 3: Implement the pure model**

Follow the existing UMD pattern in `assets/period-model.js`. Validate finite nonnegative values, exact month format, `budgetEur === 5`, and `schemaVersion === 1`. Use `Intl.NumberFormat("de-DE", {minimumFractionDigits: 1, maximumFractionDigits: 1})` for percentages and two fraction digits for euros. Return tick labels `['0 €', '1,25 €', '2,50 €', '3,75 €', '5 €']`. Tone thresholds are `<75 normal`, `>=75 warning`, `>=100 over`.

- [ ] **Step 4: Add semantic card markup**

Insert before the existing footer paragraph:

```html
<section id="cost-meter" class="cost-meter" aria-labelledby="cost-title" hidden>
  <div class="cost-heading">
    <div>
      <p class="eyebrow">Transparenz</p>
      <h2 id="cost-title">Geschätzte API-Kosten</h2>
    </div>
    <strong id="cost-percent">0,0 %</strong>
  </div>
  <div id="cost-track" class="cost-track" role="meter" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0">
    <span id="cost-fill" class="cost-fill"></span>
    <i class="cost-mark mark-25" aria-hidden="true"></i>
    <i class="cost-mark mark-50" aria-hidden="true"></i>
    <i class="cost-mark mark-75" aria-hidden="true"></i>
  </div>
  <div id="cost-ticks" class="cost-ticks" aria-hidden="true"></div>
  <p id="cost-note" class="cost-note"></p>
</section>
```

If cost data is absent or invalid, show the card with the note „Kosten derzeit nicht verfügbar“ and no fabricated percentage.

- [ ] **Step 5: Fetch and render costs independently**

Add `costs: null` to state and element references. Implement `loadCurrentCosts()` after index loading. Fetch only the same-origin path supplied by `currentCosts`; require it to match `^data/costs/[0-9]{4}-[0-9]{2}\.json$`. Use `textContent`, `style.width`, and ARIA attributes only; never `innerHTML`. A cost fetch failure must update only the card note and must not enter the main report notice.

- [ ] **Step 6: Style variant B**

Add compact card styles with the existing CSS variables, a 15px segmented track, visible quarter marks, five tick labels, green normal fill, amber warning fill and red over-budget fill. Add dark-mode equivalents. Under 440px, keep `0 €`, `2,50 €`, and `5 €` visible and visually hide the 25/75 percent euro labels while retaining the meter accessible label. Do not animate the bar.

- [ ] **Step 7: Run frontend tests and commit**

Run:

```powershell
$env:PYTHONPATH='src'; python -m unittest tests.test_frontend_contract -v
node --check assets/cost-model.js
node --check assets/app.js
git diff --check
```

Commit:

```powershell
git add assets/cost-model.js assets/app.js assets/app.css index.html tests/test_frontend_contract.py
git commit -m "feat: show public monthly API cost meter"
```

---

### Task 6: PWA version, initial data, documentation and full verification

**Files:**
- Modify: `service-worker.js`
- Modify: `index.html`
- Modify: `assets/app.js`
- Create: `data/costs/2026-08.json`
- Modify: `data/index.json`
- Modify: `README.md`
- Modify: `tests/test_frontend_contract.py`
- Modify: `tests/test_workflow_contract.py`

**Interfaces:**
- Consumes: stable contracts from Tasks 1–5.
- Produces: installable v9 PWA with a zero-based cost ledger ready for the next paid cloud call.

- [ ] **Step 1: Write failing cache and public-data contract tests**

Require:

```python
self.assertIn("lagebericht-shell-v9", worker)
self.assertIn("./assets/cost-model.js?v=9", worker)
self.assertLess(html.index("assets/cost-model.js?v=9"), html.index("assets/app.js?v=9"))
self.assertIn("service-worker.js?v=9", app)
```

Load `data/costs/2026-08.json`, validate its public fields, assert `events == []`, `estimatedCostEur == 0`, `budgetPercent == 0`, and recursively assert no key contains `key`, `secret`, `prompt`, `message`, `header`, or `requestId` (case-insensitive).

Use this recursive key check:

```python
def public_keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from public_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from public_keys(child)

for key in public_keys(cost_report):
    lowered = key.lower()
    self.assertFalse(any(forbidden in lowered for forbidden in (
        "key", "secret", "prompt", "message", "header", "requestid",
    )))
```

- [ ] **Step 2: Run contract tests to verify RED**

Run:

```powershell
$env:PYTHONPATH='src'; python -m unittest tests.test_frontend_contract tests.test_workflow_contract -v
```

- [ ] **Step 3: Seed the transparent collection start**

Create `data/costs/2026-08.json` with `schemaVersion: 1`, month `2026-08`, timezone `Europe/Berlin`, budget 5, zero USD/EUR totals, zero percent, zero unmeasured calls, `collectionStartedAt: 2026-08-03T00:00:00+02:00`, price version `anthropic-2026-08-03`, rate 0.8780 effective 2026-07-27, and an empty events array. Rebuild `data/index.json` through production code so it receives schema version 2 and `currentCosts`.

- [ ] **Step 4: Bump every PWA shell reference to v9**

Update all model/app query strings in `index.html`, the service-worker registration in `assets/app.js`, `SHELL_CACHE`, and every matching shell URL in `service-worker.js`. Add `cost-model.js?v=9` before `app.js?v=9`. Do not change `DATA_CACHE`; data remains network-first.

- [ ] **Step 5: Document estimation boundaries**

Add a README section that states:

- collection starts on 03.08.2026;
- the public bar is a token-based estimate, not an invoice;
- complete timeouts may make the displayed value a minimum estimate;
- prices and `usdToEur` live in `config/api-pricing.json` and must be updated manually when providers change them;
- no secret or prompt data is published.

- [ ] **Step 6: Run full verification**

Run:

```powershell
$env:PYTHONPATH='src'; python -m unittest discover -s tests
node --check assets/cost-model.js
node --check assets/freshness-model.js
node --check assets/rating-model.js
node --check assets/period-model.js
node --check assets/app.js
node --check service-worker.js
git diff --check
git status --short
```

Expected: every test passes; only intended feature files plus the user’s pre-existing unrelated changes appear.

- [ ] **Step 7: Review security and live behavior**

Verify with repository searches:

```powershell
rg -n "sk-ant|x-api-key|ANTHROPIC_API_KEY" data index.html assets
rg -n "innerHTML|document.write" assets/app.js assets/cost-model.js
```

Expected: no secret value or API-key reference in public files; no dynamic HTML sinks. Start the local static server and inspect normal, warning, over-budget, unavailable, dark-mode and 320px-wide states.

- [ ] **Step 8: Commit the integrated feature**

```powershell
git add service-worker.js index.html assets/app.js assets/app.css assets/cost-model.js data/costs/2026-08.json data/index.json README.md tests/test_frontend_contract.py tests/test_workflow_contract.py
git commit -m "feat: publish transparent API cost budget"
```

- [ ] **Step 9: Push and verify GitHub Pages**

```powershell
git push origin main
```

Confirm the Tests and GitHub Pages workflows pass, then verify the live `data/index.json`, `data/costs/2026-08.json`, and public card. Do not trigger a paid daily report merely to populate the meter; the next scheduled paid call will update it automatically.

---

## Final Acceptance Checklist

- [ ] The bar shows 0–100 percent against exactly 5 euros with quarter marks.
- [ ] The numeric percentage may exceed 100 while visual width remains capped.
- [ ] Current-month data only is displayed; historic files remain published.
- [ ] Successful and provider-failed responses with usage are costed.
- [ ] Timeouts without usage are counted as unmeasured, not as zero-cost calls.
- [ ] Haiku, Sonnet and cache pricing calculations match the versioned configuration.
- [ ] A recording failure never prevents a report.
- [ ] Public artifacts contain no secret, prompt, content or request-identifying data.
- [ ] Invalid/missing cost data does not break report reading.
- [ ] PWA v9 updates reliably and remains offline-capable.
- [ ] The complete Python and JavaScript verification suite passes.
