# Zuverlässiger Morgenbericht Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Jeden Berliner Kalendertag mit drei abgesicherten Morgenläufen höchstens einmal kostenpflichtig erzeugen und einen fehlenden beziehungsweise inzwischen erschienenen Tagesbericht in der PWA sichtbar behandeln.

**Architecture:** `lagebericht.schedule` entscheidet ausschließlich anhand des Berliner Datums und der bereits vorhandenen Artefakte, welche Ausgaben fehlen; die tatsächliche Startuhrzeit eines verzögerten GitHub-Jobs ist kein Ausschlusskriterium mehr. Der Workflow nutzt drei zeitzonenbewusste Cron-Einträge und serialisiert sie. Ein kleines, separat testbares Frontend-Modul bewertet die Aktualität des Archivs; `app.js` lädt den Index beim Start und bei Rückkehr in die App neu.

**Tech Stack:** Python 3.12, `unittest`, GitHub Actions YAML, statisches JavaScript ohne Abhängigkeiten, Service Worker, GitHub Pages.

## Global Constraints

- Zielzeit ist 06:30 Uhr in `Europe/Berlin`; geplante Auslöser liegen bei 05:45, 06:05 und 06:25 Uhr.
- Automatische Ersatzläufe dürfen pro Tagesdatum höchstens einen Claude-Tageslauf verursachen.
- Wochen- und Monatsberichte werden unabhängig anhand ihrer Zieldatei nachgeholt.
- `workflow_dispatch` bleibt eine bewusste manuelle Neuausführung.
- Keine neuen Laufzeitabhängigkeiten und keine externen Ressourcen in der PWA.
- EU, mehrere Meldungen je Kategorie und vollständige Artikelseiten sind nicht Teil dieses Plans.

---

## File Map

- `src/lagebericht/schedule.py`: Berliner Datum, Fälligkeit und Existenzprüfung für Tages-, Wochen- und Monatsartefakte.
- `tests/test_workflow_contract.py`: Verhaltens- und YAML-Vertrag der abgesicherten Zeitplanung.
- `.github/workflows/daily-report.yml`: drei Berliner Auslöser und getrennte Bedingungen für fehlende Artefakte.
- `assets/freshness-model.js`: reine Datums- und Aktualitätslogik für Browser und Node-Tests.
- `assets/app.js`: Index-Aktualisierung, Hinweiszustand und Aktualisierung bei Rückkehr in die PWA.
- `index.html`: lädt das Aktualitätsmodul vor `app.js`.
- `service-worker.js`: neue Shell-Version und Cache-Eintrag für das Aktualitätsmodul.
- `tests/test_frontend_contract.py`: Node-basierte Aktualitätstests und statische PWA-Verträge.
- `README.md`: dokumentiert Morgenplan, Kostenbremse und Aktualisierungsverhalten.

### Task 1: Artefaktbasierte Berliner Fälligkeit

**Files:**
- Modify: `src/lagebericht/schedule.py`
- Modify: `tests/test_workflow_contract.py`

**Interfaces:**
- Produces: `due_outputs(day: date, data_root: Path) -> dict[str, bool]` mit den Schlüsseln `daily`, `week`, `month`.
- Produces: CLI-Ausgaben `daily=`, `week=`, `month=`, `date=` und `month_id=` für `$GITHUB_OUTPUT`.
- Consumes: bestehendes `due_periods(day: date) -> set[str]` und die Dateikonventionen aus `Publisher`.

- [ ] **Step 1: Failing tests für fehlende und vorhandene Artefakte schreiben**

```python
def test_due_outputs_are_idempotent_per_artifact(self):
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        day = date(2026, 8, 2)  # Sonntag
        result = due_outputs(day, root)
        self.assertEqual(result, {"daily": True, "week": True, "month": False})
        (root / "daily").mkdir()
        (root / "daily" / "2026-08-02.json").write_text("{}", encoding="utf-8")
        result = due_outputs(day, root)
        self.assertEqual(result, {"daily": False, "week": True, "month": False})

def test_month_end_outputs_use_existing_period_files_independently(self):
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        (root / "weekly").mkdir()
        (root / "weekly" / "2026-W22.json").write_text("{}", encoding="utf-8")
        result = due_outputs(date(2026, 5, 31), root)
        self.assertEqual(result, {"daily": True, "week": False, "month": True})
```

- [ ] **Step 2: Tests ausführen und erwartetes RED bestätigen**

Run: `$env:PYTHONPATH='src'; python -m unittest tests.test_workflow_contract.WorkflowContractTests.test_due_outputs_are_idempotent_per_artifact tests.test_workflow_contract.WorkflowContractTests.test_month_end_outputs_use_existing_period_files_independently`

Expected: ERROR, weil `due_outputs` noch nicht importierbar ist.

- [ ] **Step 3: Minimale Artefaktprüfung implementieren**

```python
from pathlib import Path

def due_outputs(day: date, data_root: Path) -> dict[str, bool]:
    iso = day.isocalendar()
    week_id = f"{iso.year}-W{iso.week:02d}"
    periods = due_periods(day)
    return {
        "daily": not (data_root / "daily" / f"{day.isoformat()}.json").exists(),
        "week": "week" in periods and not (data_root / "weekly" / f"{week_id}.json").exists(),
        "month": "month" in periods and not (data_root / "monthly" / f"{day:%Y-%m}.json").exists(),
    }
```

`main()` nutzt `due_outputs(now.date(), Path("data"))`, gibt die drei booleschen Werte klein geschrieben aus und entfernt die exakte Uhrzeitprüfung aus der Laufentscheidung. `is_daily_time()` wird entfernt, sobald kein Aufrufer mehr existiert.

- [ ] **Step 4: Gezielte und vollständige Schedule-Tests ausführen**

Run: `$env:PYTHONPATH='src'; python -m unittest tests.test_workflow_contract -v`

Expected: PASS für Artefaktlogik; der alte Cron-Vertrag darf bis Task 2 noch fehlschlagen und wird dort ersetzt.

- [ ] **Step 5: Task committen**

```powershell
git add src/lagebericht/schedule.py tests/test_workflow_contract.py
git commit -m "fix: make scheduled outputs idempotent"
```

### Task 2: Drei abgesicherte GitHub-Auslöser

**Files:**
- Modify: `.github/workflows/daily-report.yml`
- Modify: `tests/test_workflow_contract.py`

**Interfaces:**
- Consumes: Task 1 CLI-Ausgaben `daily`, `week`, `month`, `date`, `month_id`.
- Produces: automatische Läufe um 05:45, 06:05 und 06:25 `Europe/Berlin` sowie manuelle Neuausführung.

- [ ] **Step 1: Alten Cron-Test durch den neuen Workflow-Vertrag ersetzen**

```python
def test_daily_workflow_has_three_berlin_recovery_slots(self):
    text = (ROOT / ".github" / "workflows" / "daily-report.yml").read_text(encoding="utf-8")
    self.assertEqual(text.count('timezone: "Europe/Berlin"'), 3)
    for cron in ("45 5 * * *", "5 6 * * *", "25 6 * * *"):
        self.assertIn(f"cron: '{cron}'", text)
    self.assertIn("steps.schedule.outputs.daily == 'true'", text)
    self.assertNotIn("steps.schedule.outputs.run", text)
    self.assertIn("ref: main", text)
```

Zusätzlich statisch prüfen, dass Tages-, Wochen- und Monatsbedingungen jeweils ihren eigenen Output verwenden und `github.event_name == 'workflow_dispatch'` nur die bewusste manuelle Ausführung freigibt.

- [ ] **Step 2: Workflow-Vertrag ausführen und erwartetes RED bestätigen**

Run: `$env:PYTHONPATH='src'; python -m unittest tests.test_workflow_contract.WorkflowContractTests.test_daily_workflow_has_three_berlin_recovery_slots`

Expected: FAIL, weil noch zwei UTC-Crons und `outputs.run` vorhanden sind.

- [ ] **Step 3: Workflow auf Berliner Slots und getrennte Bedingungen umstellen**

```yaml
on:
  schedule:
    - cron: '45 5 * * *'
      timezone: "Europe/Berlin"
    - cron: '5 6 * * *'
      timezone: "Europe/Berlin"
    - cron: '25 6 * * *'
      timezone: "Europe/Berlin"
  workflow_dispatch:
```

Die Bedingungen werden exakt getrennt:

```yaml
if: steps.schedule.outputs.daily == 'true' || github.event_name == 'workflow_dispatch'
```

für den Tagesbericht,

```yaml
if: steps.schedule.outputs.week == 'true'
```

für den Wochenbericht und entsprechend `month` für den Monatsbericht. Der Commit-Schritt läuft, wenn mindestens ein Artefakt fällig war oder manuell ausgelöst wurde. Die bestehende Concurrency bleibt unverändert.

`actions/checkout` erhält `ref: main`. Damit prüft auch ein lange verzögerter Ersatzlauf den bei seinem tatsächlichen Start aktuellen Stand von `main` und nicht den möglicherweise alten Commit des ursprünglich eingeplanten Events. Das verhindert doppelte Claude-Aufrufe, wenn ein früherer Lauf den Tagesbericht zwischenzeitlich committed hat.

- [ ] **Step 4: Workflow-Verträge und gesamte Testsuite ausführen**

Run: `$env:PYTHONPATH='src'; python -m unittest tests.test_workflow_contract -v; python -m unittest discover -s tests`

Expected: alle Tests PASS und kein automatischer Pfad referenziert `outputs.run`.

- [ ] **Step 5: Task committen**

```powershell
git add .github/workflows/daily-report.yml tests/test_workflow_contract.py
git commit -m "fix: add redundant Berlin morning schedules"
```

### Task 3: Fehlenden heutigen Bericht in der PWA erkennen

**Files:**
- Create: `assets/freshness-model.js`
- Modify: `tests/test_frontend_contract.py`

**Interfaces:**
- Produces: `FreshnessModel.berlinDateKey(now: Date) -> string`.
- Produces: `FreshnessModel.dailyNotice(index: object, now: Date) -> string`.
- `dailyNotice` liefert einen leeren String bei aktuellem Bericht und andernfalls `Der heutige Bericht vom DD.MM.YYYY ist noch nicht verfügbar. Angezeigt wird der Stand vom DD.MM.YYYY.`

- [ ] **Step 1: Node-basierte RED-Tests für Sommerzeit und fehlenden Bericht schreiben**

```python
def run_freshness(index, now):
    script = (
        "const model=require(process.argv[1]);"
        "const index=JSON.parse(process.argv[2]);"
        "process.stdout.write(JSON.stringify({date:model.berlinDateKey(new Date(process.argv[3])),"
        "notice:model.dailyNotice(index,new Date(process.argv[3]))}));"
    )
    result = subprocess.run(
        ["node", "-e", script, str(ROOT / "assets" / "freshness-model.js"), json.dumps(index), now],
        check=True, capture_output=True, text=True, encoding="utf-8",
    )
    return json.loads(result.stdout)

def test_freshness_uses_berlin_date_and_reports_missing_today(self):
    result = run_freshness({"latestDaily": "2026-08-01"}, "2026-08-02T21:30:00Z")
    self.assertEqual(result["date"], "2026-08-02")
    self.assertIn("02.08.2026", result["notice"])
    self.assertIn("01.08.2026", result["notice"])

def test_freshness_is_quiet_for_current_report(self):
    result = run_freshness({"latestDaily": "2026-08-02"}, "2026-08-02T04:40:00Z")
    self.assertEqual(result["notice"], "")
```

- [ ] **Step 2: Tests ausführen und erwartetes RED bestätigen**

Run: `python -m unittest tests.test_frontend_contract.FrontendContractTests.test_freshness_uses_berlin_date_and_reports_missing_today tests.test_frontend_contract.FrontendContractTests.test_freshness_is_quiet_for_current_report`

Expected: ERROR, weil `assets/freshness-model.js` fehlt.

- [ ] **Step 3: Reines Aktualitätsmodul implementieren**

Das Modul folgt dem vorhandenen UMD-Muster aus `rating-model.js`, exportiert die zwei Funktionen und verwendet `Intl.DateTimeFormat(..., {timeZone: 'Europe/Berlin'})`. Es greift weder auf DOM noch Netzwerk zu und formatiert beide Datumsangaben selbst als `DD.MM.YYYY`.

- [ ] **Step 4: Aktualitätstests ausführen**

Run: `python -m unittest tests.test_frontend_contract.FrontendContractTests.test_freshness_uses_berlin_date_and_reports_missing_today tests.test_frontend_contract.FrontendContractTests.test_freshness_is_quiet_for_current_report`

Expected: beide Tests PASS.

- [ ] **Step 5: Task committen**

```powershell
git add assets/freshness-model.js tests/test_frontend_contract.py
git commit -m "feat: detect missing current briefing"
```

### Task 4: PWA bei Rückkehr aktualisieren

**Files:**
- Modify: `assets/app.js`
- Modify: `index.html`
- Modify: `service-worker.js`
- Modify: `tests/test_frontend_contract.py`

**Interfaces:**
- Consumes: `FreshnessModel.dailyNotice(state.index, new Date())` aus Task 3.
- Produces: `refreshIndex({preferLatest: boolean}) -> Promise<void>` in `app.js`.
- Produces: sichtbarer Hinweis über das bestehende Element `#notice`.

- [ ] **Step 1: RED-Verträge für Laden, Sichtbarkeitswechsel und Cache-Version schreiben**

```python
def test_app_refreshes_index_when_pwa_becomes_visible(self):
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    app = (ROOT / "assets" / "app.js").read_text(encoding="utf-8")
    worker = (ROOT / "service-worker.js").read_text(encoding="utf-8")
    self.assertLess(html.index("assets/freshness-model.js?v=7"), html.index("assets/app.js?v=7"))
    self.assertIn("visibilitychange", app)
    self.assertIn("document.visibilityState === 'visible'", app)
    self.assertIn("FreshnessModel.dailyNotice", app)
    self.assertIn("lagebericht-shell-v7", worker)
    self.assertIn("./assets/freshness-model.js?v=7", worker)
```

- [ ] **Step 2: Vertragstest ausführen und erwartetes RED bestätigen**

Run: `python -m unittest tests.test_frontend_contract.FrontendContractTests.test_app_refreshes_index_when_pwa_becomes_visible`

Expected: FAIL wegen fehlender Modulreferenz, Listener und Shell-Version 7.

- [ ] **Step 3: Index-Aktualisierung und getrennte Hinweise implementieren**

`state` erhält `freshnessNotice` und `reportNotice`. `renderNotice()` zeigt beide nichtleeren Texte mit einem Leerzeichen getrennt. `refreshIndex({preferLatest})` lädt `data/index.json` mit `{cache: 'no-store'}`, ersetzt `state.index`, aktualisiert die Auswahlliste und lädt bei einem neuen `latestDaily` den neuesten Bericht, sofern die Archivart `daily` aktiv ist. `start()` ruft diese Funktion mit `preferLatest: true` auf. Ein `visibilitychange`-Listener ruft sie erneut auf, sobald `document.visibilityState === 'visible'` gilt. Fehler setzen wie bisher einen technischen Hinweis, ohne einen bereits angezeigten Bericht zu löschen.

- [ ] **Step 4: HTML und Service Worker gemeinsam auf Version 7 anheben**

`index.html` lädt `freshness-model.js?v=7`, `rating-model.js?v=7` und `app.js?v=7` in dieser Reihenfolge. `app.js` registriert `service-worker.js?v=7`. `service-worker.js` verwendet `lagebericht-shell-v7` und cached die drei versionierten Skripte für Offline-Betrieb.

- [ ] **Step 5: Frontend-Verträge und Syntax prüfen**

Run: `python -m unittest tests.test_frontend_contract -v; node --check assets/freshness-model.js; node --check assets/rating-model.js; node --check assets/app.js; node --check service-worker.js`

Expected: alle Tests und Syntaxprüfungen PASS.

- [ ] **Step 6: Task committen**

```powershell
git add assets/app.js assets/freshness-model.js index.html service-worker.js tests/test_frontend_contract.py
git commit -m "fix: refresh installed PWA briefing state"
```

### Task 5: Dokumentation, Gesamtprüfung und Veröffentlichung

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-08-02-zuverlaessiger-morgenbericht-design.md`

**Interfaces:**
- Consumes: alle vorherigen Tasks.
- Produces: dokumentierter und vollständig geprüfter Stand auf `main`.

- [ ] **Step 1: README um Betriebsverhalten ergänzen**

Dokumentieren: Zielzeit 06:30 Berlin, drei Ersatztermine, Artefaktprüfung vor API-Aufruf, manuelle Neuausführung und sichtbarer PWA-Hinweis bei fehlendem Tagesbericht. Den Spec-Status auf `umgesetzt` setzen.

- [ ] **Step 2: Vollständige lokale Verifikation ausführen**

Run: `$env:PYTHONPATH='src'; python -m unittest discover -s tests -v; node --check assets/freshness-model.js; node --check assets/rating-model.js; node --check assets/app.js; node --check service-worker.js; git diff --check`

Expected: alle Tests PASS, alle Syntaxprüfungen Exit 0 und kein Whitespace-Fehler.

- [ ] **Step 3: Dokumentation committen**

```powershell
git add README.md docs/superpowers/specs/2026-08-02-zuverlaessiger-morgenbericht-design.md
git commit -m "docs: document reliable morning briefing"
```

- [ ] **Step 4: `main` pushen und kostenlose GitHub-Prüfungen beobachten**

Run: `git push origin main`

Expected: `Tests` und `GitHub Pages veröffentlichen` sind grün. Den kostenpflichtigen Tagesworkflow nicht manuell starten, bevor die kostenlosen Prüfungen abgeschlossen sind.

- [ ] **Step 5: Live-PWA prüfen**

Die veröffentlichte Seite ohne Cache-Buster öffnen. Prüfen: aktueller beziehungsweise fehlender Tageshinweis, Archiv-Auswahl, Rückkehr-Aktualisierung, USA/China/Montenegro und keine Browser-Konsolenfehler.
