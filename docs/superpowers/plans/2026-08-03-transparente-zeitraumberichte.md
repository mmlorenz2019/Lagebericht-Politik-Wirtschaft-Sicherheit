# Transparente Wochen- und Monatsberichte Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wochen- und Monatsberichte werden nach Abschluss ihres Zeitraums bereits ab einem gültigen Tagesbericht erzeugt und zeigen Datenabdeckung, ausführliche Gesamtlage und Einordnung transparent an.

**Architecture:** `schedule.py` bestimmt abgeschlossene Zeiträume und prüft Artefakte idempotent. `aggregate.py` erzeugt Schema-v3-Zeitraumberichte aus validierten Tagesberichten; ein kleines, reines Frontend-Modell berechnet Abdeckung und Darstellungszustand. Die GitHub-Workflows committen gültige Tagesdaten auch bei Rückblickfehlern, veröffentlichen diesen Stand und versuchen fehlende Rückblicke in den bestehenden Ersatzfenstern erneut.

**Tech Stack:** Python 3.12 Standardbibliothek, `unittest`, JavaScript ohne Framework, Node.js für reine Frontend-Modelltests, GitHub Actions, statische GitHub Pages/PWA.

## Global Constraints

- Alle Zeitentscheidungen verwenden `Europe/Berlin`.
- Woche: Montag bis Sonntag; Erzeugung am folgenden Montag.
- Monat: Kalendermonat; Erzeugung am ersten Tag des Folgemonats.
- Ein gültiger Tagesbericht genügt; null Tagesberichte lösen keinen Claude-Aufruf aus.
- Woche: 8–10 Sätze Gesamtlage; Monat: 12–15 Sätze Gesamtlage.
- Veröffentlichte Entwicklung: 3–6 Sätze Verlauf und 2–3 Sätze `contextDe`.
- Ein einzelner Berichtstag wird als `Momentaufnahme`, nicht als Trend bezeichnet.
- Alte Schema-v1/v2-Zeitraumberichte bleiben validierbar und lesbar.
- Keine externen Frontend-Abhängigkeiten, Tracker oder CSP-Lockerungen.
- Kein Rückblick darf unvalidiert oder nicht atomar veröffentlicht werden.
- Die tägliche Zahl der Hauptmeldungen bleibt unverändert.

---

## File Map

- `src/lagebericht/schedule.py`: abgeschlossene Zielzeiträume, Artefakt-Idempotenz und GitHub-Ausgaben.
- `src/lagebericht/aggregate.py`: Laden der Tagesberichte, Teilbericht-Erzeugung und Schema-v3-Modellausgabe.
- `src/lagebericht/prompts.py`: verbindliche Längen, Momentaufnahme-Regel und Verdichtungsregeln.
- `src/lagebericht/schema.py`: manuelle Validierung von Schema v1/v2/v3.
- `schemas/period-report.schema.json`: öffentlicher JSON-Vertrag für neu erzeugte Schema-v3-Berichte.
- `scripts/run_period.py`: eindeutige Behandlung eines Zeitraums ohne Tagesdaten.
- `scripts/verify_periods.py`: abschließende Workflow-Prüfung fälliger Rückblick-Artefakte.
- `assets/period-model.js`: reine Berechnung von Abdeckung, Statusbezeichnung und Momentaufnahme.
- `assets/app.js`: Darstellung von Abdeckung und `contextDe`.
- `assets/app.css`: visuelle Abgrenzung von Datenbasis und Einordnung.
- `index.html`, `service-worker.js`: Laden und Offline-Caching des neuen Frontend-Modells mit neuer Cache-Version.
- `.github/workflows/daily-report.yml`: richtige Zielparameter, unabhängiger Commit und sichtbare Rückblickfehler.
- `.github/workflows/pages.yml`: Veröffentlichung des atomar committed Stands auch nach einem Rückblickfehler.
- `tests/test_workflow_contract.py`: Termin-, Idempotenz- und Workflow-Verträge.
- `tests/test_aggregate.py`: Teilberichte, Satzvorgaben und Null-Daten-Verhalten.
- `tests/test_schema.py`: Schema-v3- und Legacy-Validierung.
- `tests/test_publish.py`: Aufnahme valider Teilberichte in den Archivindex.
- `tests/test_frontend_contract.py`: Abdeckungsmodell, Einordnung und PWA-Verträge.
- `tests/test_cli.py`: CLI-Verhalten ohne Tagesdaten.
- `README.md`: Benutzerbeschreibung der neuen Termine und Teilberichte.

---

### Task 1: Abgeschlossene Zeiträume und idempotente Artefakte

**Files:**
- Modify: `src/lagebericht/schedule.py`
- Modify: `tests/test_workflow_contract.py`

**Interfaces:**
- Produces: `PeriodTargets(week_end: date | None, month_id: str | None)`
- Produces: `period_targets(day: date) -> PeriodTargets`
- Produces: `period_artifact_complete(path: Path, expected_end: date, data_root: Path) -> bool`
- Preserves: `due_outputs(day: date, data_root: Path) -> dict[str, bool]`
- CLI outputs: `daily`, `week`, `month`, `date`, `week_end`, `month_id`

- [ ] **Step 1: Replace Sunday/month-end tests with completed-period tests**

Add tests equivalent to:

```python
from lagebericht.schedule import due_outputs, period_targets, to_berlin

def test_monday_targets_previous_calendar_week(self):
    targets = period_targets(date(2026, 8, 3))
    self.assertEqual(targets.week_end, date(2026, 8, 2))
    self.assertIsNone(targets.month_id)

def test_first_day_targets_previous_month_across_year_boundary(self):
    targets = period_targets(date(2027, 1, 1))
    self.assertIsNone(targets.week_end)
    self.assertEqual(targets.month_id, "2026-12")

def test_first_day_on_monday_targets_week_and_month(self):
    targets = period_targets(date(2027, 2, 1))
    self.assertEqual(targets.week_end, date(2027, 1, 31))
    self.assertEqual(targets.month_id, "2027-01")
```

Add an idempotency fixture with real backing daily files:

```python
def test_existing_partial_week_is_complete_for_recovery_slots(self):
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        for value in ("2026-07-31", "2026-08-01", "2026-08-02"):
            path = root / "daily" / f"{value}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}", encoding="utf-8")
        weekly = root / "weekly" / "2026-W31.json"
        weekly.parent.mkdir(parents=True)
        weekly.write_text(json.dumps({
            "periodEnd": "2026-08-02",
            "sourceReportDates": ["2026-07-31", "2026-08-01", "2026-08-02"],
            "missingReportDates": ["2026-07-27", "2026-07-28", "2026-07-29", "2026-07-30"],
        }), encoding="utf-8")
        self.assertEqual(
            due_outputs(date(2026, 8, 3), root),
            {"daily": True, "week": False, "month": False},
        )
```

Keep a counterexample whose `sourceReportDates` reference missing backing files; it must remain due.

- [ ] **Step 2: Run the focused tests and verify the old behavior fails**

Run:

```powershell
$env:PYTHONPATH='src'
python -m unittest tests.test_workflow_contract.WorkflowContractTests -v
```

Expected: failures show Sunday/month-end targeting and the old requirement that the period end itself be a source date.

- [ ] **Step 3: Implement completed-period targeting**

Implement the focused API:

```python
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class PeriodTargets:
    week_end: date | None
    month_id: str | None

def period_targets(day: date) -> PeriodTargets:
    week_end = day - timedelta(days=1) if day.weekday() == 0 else None
    if day.day == 1:
        previous = day - timedelta(days=1)
        month_id = previous.strftime("%Y-%m")
    else:
        month_id = None
    return PeriodTargets(week_end, month_id)
```

Change artifact completion so a partial report is complete when:

- `periodEnd` equals the target end,
- `sourceReportDates` is a non-empty list of unique ISO dates,
- every listed source date has a backing `data/daily/YYYY-MM-DD.json`,
- `missingReportDates` is a list,
- no source date also appears in `missingReportDates`.

Use `week_end.isocalendar()` for the weekly filename and the previous month ID for the monthly filename. `main()` prints an empty `week_end=` or `month_id=` when that period is not due.

- [ ] **Step 4: Run focused and full scheduling tests**

Run:

```powershell
$env:PYTHONPATH='src'
python -m unittest tests.test_workflow_contract -v
python -m lagebericht.schedule
```

Expected on Monday 2026-08-03: `week_end=2026-08-02`, `month_id=` and a weekly due flag determined by the current artifacts.

- [ ] **Step 5: Commit Task 1**

```powershell
git add src/lagebericht/schedule.py tests/test_workflow_contract.py
git commit -m "fix: schedule completed reporting periods"
```

---

### Task 2: Schema-v3-Teilberichte und ausführliche Verdichtung

**Files:**
- Modify: `src/lagebericht/aggregate.py`
- Modify: `src/lagebericht/prompts.py`
- Modify: `src/lagebericht/schema.py`
- Modify: `schemas/period-report.schema.json`
- Modify: `scripts/run_period.py`
- Modify: `tests/test_aggregate.py`
- Modify: `tests/test_prompts.py`
- Modify: `tests/test_schema.py`
- Modify: `tests/test_cli.py`

**Interfaces:**
- Produces: `period_content_schema(period_type: str) -> dict`
- Changes: `PeriodAggregator.build_week(end_date: date) -> dict | None` requires one report instead of four.
- Changes: `PeriodAggregator.build_month(year: int, month: int) -> dict | None` requires one report instead of 20.
- Schema v3 published section: required `contextDe: list[str]` with 2–3 items for `published`, empty for other statuses.
- Preserves: validation of period schema versions 1 and 2.

- [ ] **Step 1: Write failing aggregator tests for one-day reports and exact summary sizes**

Make `ContentAI` derive the requested item count from the supplied schema and include `contextDe`:

```python
class ContentAI:
    def generate_json(self, model, instructions, input_text, schema_name, schema):
        count = schema["properties"]["overallSummary"]["minItems"]
        return {
            "overallSummary": [f"Satz {index + 1}." for index in range(count)],
            "countries": [
                {"id": "usa", "label": "USA", "sections": [period_category("politics_society")]},
                {"id": "china", "label": "China", "sections": [period_category("economy_technology")]},
                {"id": "montenegro", "label": "Montenegro", "sections": [period_category("foreign_security")]},
            ],
        }
```

Add:

```python
def test_builds_snapshot_week_from_one_day(self):
    self.publish_days(date(2026, 8, 2), 1)
    report = PeriodAggregator(self.root, ContentAI(), ALLOWED_DOMAINS).build_week(date(2026, 8, 2))
    self.assertEqual(report["schemaVersion"], 3)
    self.assertEqual(report["sourceReportDates"], ["2026-08-02"])
    self.assertEqual(len(report["overallSummary"]), 8)
    self.assertEqual(len(report["countries"][0]["sections"][0]["contextDe"]), 2)

def test_month_requests_twelve_to_fifteen_summary_sentences(self):
    self.publish_days(date(2026, 7, 31), 1)
    ai = ContentAI()
    report = PeriodAggregator(self.root, ai, ALLOWED_DOMAINS).build_month(2026, 7)
    self.assertEqual(len(report["overallSummary"]), 12)
```

Retain a zero-day test and assert `ContentAI.models == []`.

- [ ] **Step 2: Write failing schema-v3 and legacy tests**

Add `period_category()` without changing the daily fixture:

```python
def period_category(category_id="politics_society"):
    value = category(category_id)
    value["contextDe"] = [
        "Der Hintergrund erklärt die Ausgangslage.",
        "Die Bedeutung ergibt sich aus den möglichen Folgen.",
    ]
    return value
```

Create `valid_period_v3(period_type="week")` with 8 overall sentences for week and 12 for month. Test rejection of 7/11 and 11/16 overall sentences, rejection of a one-sentence `contextDe`, and acceptance of the unchanged schema-v2 fixture.

- [ ] **Step 3: Run the new tests and verify they fail**

```powershell
$env:PYTHONPATH='src'
python -m unittest tests.test_aggregate tests.test_schema tests.test_prompts tests.test_cli -v
```

Expected: the old minimums return `None`, schema version 3 is rejected, and `contextDe` is unknown.

- [ ] **Step 4: Implement the period-specific model contract**

In `aggregate.py`, create a fresh schema per call so shared constants are not mutated:

```python
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
```

Require `contextDe` in `SECTION_SCHEMA`, publish `schemaVersion: 3`, and change both aggregator minimums to `1`. When no reports exist, return `None` before constructing a prompt or calling the client.

In `prompts.py`, require:

- week overall summary 8–10 sentences,
- month overall summary 12–15 sentences,
- section flow 3–6 sentences,
- `contextDe` 2–3 sentences,
- `Momentaufnahme` wording when exactly one source report exists,
- no invented trend from a single day.

- [ ] **Step 5: Implement schema-v3 validation and the public JSON schema**

Extend `_category()` so `contextDe` is allowed only for schema version 3. For a published v3 section require 2–3 non-empty strings of at most 500 characters. For an empty v3 section require `contextDe == []`.

In `validate_period_report()`:

```python
if schema_version not in {1, 2, 3} or isinstance(schema_version, bool):
    _fail("schemaVersion", "must be 1, 2 or 3")
if schema_version == 3:
    limits = (8, 10) if report["periodType"] == "week" else (12, 15)
else:
    limits = (1, 8)
if not isinstance(summary, list) or not limits[0] <= len(summary) <= limits[1]:
    _fail("overallSummary", f"must contain {limits[0]}-{limits[1]} sentences")
```

Update `schemas/period-report.schema.json` to `schemaVersion: 3`, the 15-item physical maximum, and required `contextDe`. Runtime Python validation remains the authority for period-specific counts and legacy versions.

- [ ] **Step 6: Clarify the no-data CLI result**

Change the exit-3 message in `scripts/run_period.py` to:

```text
Keine gültigen Tagesberichte für diesen Zeitraum; Claude wurde nicht aufgerufen.
```

Run the CLI as a subprocess with a temporary empty `--data-root` and a dummy, non-empty `ANTHROPIC_API_KEY`. Assert exit code 3 and that exact message. The client may be constructed, but `generate_json` must never be reached because no daily reports exist.

- [ ] **Step 7: Run focused and full backend tests**

```powershell
$env:PYTHONPATH='src'
python -m unittest tests.test_aggregate tests.test_schema tests.test_prompts tests.test_cli -v
python -m unittest discover -s tests -v
```

Expected: all tests pass; legacy sample reports continue to validate.

- [ ] **Step 8: Commit Task 2**

```powershell
git add src/lagebericht/aggregate.py src/lagebericht/prompts.py src/lagebericht/schema.py schemas/period-report.schema.json scripts/run_period.py tests/test_aggregate.py tests/test_prompts.py tests/test_schema.py tests/test_cli.py
git commit -m "feat: generate transparent partial period reports"
```

---

### Task 3: Abdeckungsmodell und PWA-Darstellung

**Files:**
- Create: `assets/period-model.js`
- Modify: `assets/app.js`
- Modify: `assets/app.css`
- Modify: `index.html`
- Modify: `service-worker.js`
- Modify: `tests/test_frontend_contract.py`

**Interfaces:**
- Produces: `PeriodModel.coverage(report) -> { available: number, total: number, partial: boolean, snapshot: boolean, label: string }`
- Consumes: v3 `contextDe`; treats missing `contextDe` in v1/v2 as an empty list.

- [ ] **Step 1: Write failing pure-model tests through Node**

Add a Python helper matching the existing `run_freshness()` style:

```python
PERIOD_MODEL = ROOT / "assets" / "period-model.js"

def run_period_model(report):
    script = (
        "const model=require(process.argv[1]);"
        "const report=JSON.parse(process.argv[2]);"
        "process.stdout.write(JSON.stringify(model.coverage(report)));"
    )
    result = subprocess.run(
        ["node", "-e", script, str(PERIOD_MODEL), json.dumps(report)],
        check=True, capture_output=True, text=True, encoding="utf-8",
    )
    return json.loads(result.stdout)
```

Test a week with three source dates, a complete leap-month with 29 source dates, and a one-day snapshot. Expected labels:

```text
Datenbasis: 3 von 7 Tagen · Teilüberblick
Datenbasis: 29 von 29 Tagen · Vollständig
Datenbasis: 1 von 7 Tagen · Momentaufnahme
```

- [ ] **Step 2: Write failing rendering contract tests**

Assert that:

- `index.html` loads `assets/period-model.js?v=8` before `assets/app.js?v=8`,
- `app.js` calls `PeriodModel.coverage(report)`,
- `app.js` creates the heading `Einordnung`,
- `app.js` reads `item.contextDe || []`,
- no `innerHTML` assignment is introduced,
- the service worker cache is `lagebericht-shell-v8` and includes the new model.

- [ ] **Step 3: Run frontend tests and verify they fail**

```powershell
$env:PYTHONPATH='src'
python -m unittest tests.test_frontend_contract -v
```

Expected: missing `period-model.js`, missing coverage label, and stale v7 asset contracts.

- [ ] **Step 4: Implement the pure period model**

Use UTC date arithmetic to avoid daylight-saving errors:

```javascript
function dayNumber(value) {
  const [year, month, day] = value.split('-').map(Number);
  return Date.UTC(year, month - 1, day) / 86400000;
}

function coverage(report) {
  const total = dayNumber(report.periodEnd) - dayNumber(report.periodStart) + 1;
  const available = new Set(report.sourceReportDates || []).size;
  const snapshot = available === 1;
  const partial = available < total;
  const suffix = snapshot ? 'Momentaufnahme' : partial ? 'Teilüberblick' : 'Vollständig';
  return { available, total, partial, snapshot, label: `Datenbasis: ${available} von ${total} Tagen · ${suffix}` };
}
```

Export with the same browser/CommonJS wrapper pattern as `rating-model.js` and `freshness-model.js`.

- [ ] **Step 5: Render coverage and context without dynamic HTML**

In `renderReport()`, compute coverage only for period reports and place its label in `elements.completeness`. The notice names missing days but does not replace the compact coverage label.

In `renderStory()` after `.summary`, render v3 context:

```javascript
const contextSentences = item.contextDe || [];
if (contextSentences.length) {
  const context = node('section', null, 'context');
  context.append(node('h4', 'Einordnung'));
  contextSentences.forEach((sentence) => context.append(node('p', sentence)));
  article.append(context);
}
```

Add accessible CSS for `.context` and `.period-coverage`; preserve dark mode. Bump `index.html`, service-worker registration, shell cache and cached asset URLs from v7 to v8.

- [ ] **Step 6: Run syntax and frontend tests**

```powershell
node --check assets/period-model.js
node --check assets/app.js
node --check service-worker.js
$env:PYTHONPATH='src'
python -m unittest tests.test_frontend_contract -v
```

Expected: all commands succeed and all frontend contract tests pass.

- [ ] **Step 7: Commit Task 3**

```powershell
git add assets/period-model.js assets/app.js assets/app.css index.html service-worker.js tests/test_frontend_contract.py
git commit -m "feat: show period coverage and context"
```

---

### Task 4: Workflow-Wiederholung, Veröffentlichung und sichtbare Fehler

**Files:**
- Create: `scripts/verify_periods.py`
- Modify: `.github/workflows/daily-report.yml`
- Modify: `.github/workflows/pages.yml`
- Modify: `tests/test_workflow_contract.py`

**Interfaces:**
- Consumes: `period_targets(run_day)` and `period_artifact_complete(...)` from Task 1.
- CLI: `python scripts/verify_periods.py --run-date YYYY-MM-DD --data-root data`
- Exit 0: every fällige period artifact exists and is complete for recovery purposes.
- Exit 1: at least one fällige period artifact is missing or references missing backing daily files.

- [ ] **Step 1: Write failing verifier and workflow contract tests**

Test the verifier with a Monday fixture whose daily report exists but weekly artifact does not; expect exit 1 and `Fehlender Wochenbericht: 2026-W31`. Add the partial artifact and expect exit 0.

Update workflow assertions to require:

```python
self.assertIn('steps.schedule.outputs.week_end', daily_text)
self.assertIn('if: always()', daily_text)
self.assertIn('python scripts/verify_periods.py', daily_text)
self.assertEqual(daily_text.count("continue-on-error: true"), 2)
self.assertRegex(
    daily_text,
    r"(?s)- name: Wochenbericht erzeugen.*?continue-on-error: true",
)
self.assertRegex(
    daily_text,
    r"(?s)- name: Monatsbericht erzeugen.*?continue-on-error: true",
)
self.assertIn("github.event.workflow_run.conclusion", pages_text)
self.assertNotIn("github.event.workflow_run.conclusion == 'success'", pages_text)
```

The Pages job must still restrict `workflow_run` execution to the named workflow and check out `main`.

- [ ] **Step 2: Run workflow tests and verify they fail**

```powershell
$env:PYTHONPATH='src'
python -m unittest tests.test_workflow_contract -v
```

Expected: missing verifier, wrong period arguments, commit step not unconditional after failures, and Pages restricted to successful runs.

- [ ] **Step 3: Implement `scripts/verify_periods.py`**

Parse `--run-date` and `--data-root`. For each target due on that date, construct the same weekly/monthly path as `due_outputs()` and call `period_artifact_complete()`. Print one German error per missing artifact to stderr and return 1; otherwise return 0. Do not check the daily artifact in this script.

- [ ] **Step 4: Pass completed target identifiers to period commands**

In `daily-report.yml`:

```yaml
- name: Wochenbericht erzeugen
  id: weekly
  if: steps.schedule.outputs.week == 'true'
  continue-on-error: true
  run: python scripts/run_period.py week --end-date "${{ steps.schedule.outputs.week_end }}"

- name: Monatsbericht erzeugen
  id: monthly
  if: steps.schedule.outputs.month == 'true'
  continue-on-error: true
  run: python scripts/run_period.py month --month "${{ steps.schedule.outputs.month_id }}"
```

Keep `continue-on-error` on these two generation steps so the commit step can preserve a valid daily report. Change the commit step to `if: always()` plus the existing due/manual condition. After the commit/push step, add an `if: always()` verifier step that exits nonzero when a due period is still missing. This final verifier makes the run visibly red while preserving committed valid data.

The contract test should reject `continue-on-error` everywhere except the two named period generation steps, rather than rejecting the string globally.

- [ ] **Step 5: Deploy committed data after completed daily workflows**

Change `pages.yml` so a completed `Täglicher Lagebericht` workflow deploys `main` regardless of its conclusion. Preserve minimal permissions, pinned actions and the explicit workflow-name filter. This ensures an atomically committed daily report becomes visible even when the final period verifier reports failure.

- [ ] **Step 6: Run workflow and full test suites**

```powershell
$env:PYTHONPATH='src'
python -m unittest tests.test_workflow_contract -v
python -m unittest discover -s tests -v
git diff --check
```

Expected: all tests pass and no whitespace errors are reported.

- [ ] **Step 7: Commit Task 4**

```powershell
git add scripts/verify_periods.py .github/workflows/daily-report.yml .github/workflows/pages.yml tests/test_workflow_contract.py
git commit -m "fix: retry and surface missing period reports"
```

---

### Task 5: Archivvertrag, Dokumentation und vollständige Freigabe

**Files:**
- Modify: `tests/test_publish.py`
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-08-03-teilberichte-und-abschlusszeitpunkte-design.md`

**Interfaces:**
- Preserves: `rebuild_index(data_root: Path) -> dict`
- Acceptance: a partial period appears only when every `sourceReportDates` value has a backing daily file.

- [ ] **Step 1: Add the final archive acceptance test**

Create three backing daily files, a partial W31 report with those three dates plus four missing dates, and assert:

```python
index = rebuild_index(self.root)
self.assertEqual(index["weekly"], [{
    "period": "2026-W31",
    "path": "data/weekly/2026-W31.json",
}])
```

Keep the existing rejection test for a period report that cites a missing backing daily file.

- [ ] **Step 2: Run the publish tests**

```powershell
$env:PYTHONPATH='src'
python -m unittest tests.test_publish -v
```

Expected: both partial inclusion and unsupported-date exclusion pass without production changes; if not, make the smallest correction in `_period_entries()` while retaining both tests.

- [ ] **Step 3: Document user-visible behavior**

Update `README.md` with:

- weekly report on Monday for the previous Monday–Sunday period,
- monthly report on the first for the previous calendar month,
- part reports from one valid day,
- exact data-basis label and Momentaufnahme wording,
- 8–10 weekly and 12–15 monthly overall sentences,
- recovery slots and the fact that failed API responses can still incur token costs.

Set the design spec frontmatter from `status: review` to `status: umgesetzt` only after all verification commands pass.

- [ ] **Step 4: Run the complete verification matrix**

Run each command with an explicit exit check:

```powershell
node --check assets/app.js
node --check assets/freshness-model.js
node --check assets/rating-model.js
node --check assets/period-model.js
node --check service-worker.js
$env:PYTHONPATH='src'
python -m unittest discover -s tests -v
python -m lagebericht.schedule
git diff --check
git status --short
```

Expected:

- every Node syntax check exits 0,
- all Python tests pass,
- the schedule prints completed-period identifiers appropriate for the current Berlin date,
- `git diff --check` is silent,
- only the intended README/spec/test changes remain before the final commit.

- [ ] **Step 5: Commit Task 5**

```powershell
git add tests/test_publish.py README.md docs/superpowers/specs/2026-08-03-teilberichte-und-abschlusszeitpunkte-design.md
git commit -m "docs: complete transparent period reports"
```

- [ ] **Step 6: Push and verify GitHub**

```powershell
git push origin main
```

Verify through the GitHub Actions API that `Tests` and `GitHub Pages veröffentlichen` succeed for the pushed SHA. Do not manually dispatch a paid Claude workflow during this verification. Confirm the public page serves the new v8 assets; a real weekly/monthly artifact is verified only after an explicitly authorized paid generation or the next scheduled due date.

---

## Deferred Follow-up Specs

After this plan is complete and stable:

1. Hybrid full-article retrieval and daily `Einordnung`, with RSS fallback and one-event-per-card enforcement.
2. EU institutions as the fourth report area.

Neither follow-up is bundled into this implementation plan.
