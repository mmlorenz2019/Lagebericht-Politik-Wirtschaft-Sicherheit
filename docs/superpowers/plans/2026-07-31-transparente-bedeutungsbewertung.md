# Transparente Bedeutungsbewertung – Implementierungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Jede technisch geeignete Tagesmeldung wird veröffentlicht und erhält zwei nachvollziehbare Bewertungen von 0 bis 3 für Deutschland-Bezug und allgemeine Tragweite.

**Architecture:** Das öffentliche JSON-Format wird als Version 2 erweitert, während Validator und Oberfläche vorhandene Version-1-Berichte weiter lesen. Die Pipeline fordert vollständige Auswahl und Bewertungen vom Modell an, prüft alle mit Quellen belegten Land-Kategorie-Slots und startet bei einer unbegründeten Auslassung genau einen gezielten Reparaturlauf. Die PWA stellt Bewertung, Begründung und Quellenunsicherheit als getrennte Informationen dar.

**Tech Stack:** Python 3.12, `unittest`, JSON Schema, Anthropic Messages API mit strukturiertem JSON, Vanilla JavaScript/CSS, GitHub Actions und GitHub Pages.

## Global Constraints

- Das Modell darf Meldungen nach Bedeutung ordnen, aber nicht allein wegen niedriger Bedeutung verwerfen.
- Eine Meldung aus einer einzigen seriösen Quelle darf veröffentlicht werden und trägt `single_source`.
- Deutschland-Bezug und allgemeine Tragweite sind getrennte ganzzahlige Bewertungen von 0 bis 3 mit je einer deutschen Begründung.
- Grau steht für 0, Grün für 1, Gelb für 2 und Rot für 3; die Farbe bezeichnet Intensität, nicht positive oder negative Wirkung.
- `no_major_development` bedeutet ausschließlich, dass keine technisch geeignete neue Meldung gefunden wurde.
- `unavailable` bedeutet, dass die Auswahl technisch nicht verlässlich möglich war.
- Version-1-Berichte bleiben ohne erfundene Punktwerte lesbar.
- Bei leeren Version-2-Abschnitten sind beide Bewertungsfelder `null`.
- Keine Benutzerkonten, Bewertungsbuttons oder automatische Lernfunktion in dieser Ausbaustufe.
- Keine neuen Laufzeitabhängigkeiten und keine externen Ressourcen in der PWA.

---

## Dateistruktur und Verantwortlichkeiten

- `schemas/daily-report.schema.json`: Von Anthropic erzeugter und öffentlich gespeicherter Tagesbericht Version 2.
- `schemas/period-report.schema.json`: Öffentlich gespeicherter Wochen- und Monatsbericht Version 2.
- `src/lagebericht/schema.py`: Vertrauensgrenze für Version-1- und Version-2-Berichte, einschließlich Score- und Statusregeln.
- `src/lagebericht/prompts.py`: Auswahlregeln, Bewertungsrubrik und gezielter Reparaturprompt.
- `src/lagebericht/pipeline.py`: Quellenslots ermitteln, Auslassungen erkennen, einmal reparieren und erst danach veröffentlichen.
- `src/lagebericht/aggregate.py`: Version-2-Vertrag für Zeitraumberichte und Nutzung der Bewertungen ohne Löschfilter.
- `assets/app.js`: Rückwärtskompatible Darstellung der Bewertungen und Begründungen.
- `assets/app.css`: Zugängliche Intensitätskennzeichnungen für helle und dunkle Darstellung.
- `service-worker.js`: Neue Cache-Version, damit die geänderte Oberfläche sofort ausgeliefert wird.
- `tests/test_schema.py`: Gemeinsame Version-2-Testdaten sowie gezielte Version-1-Kompatibilitätstests.
- `tests/test_prompts.py`, `tests/test_pipeline.py`: Verhalten der Auswahl, Einquellenregel und Reparatur des Modelloutputs.
- `tests/test_aggregate.py`: Version-2-Zeitraumberichte und Scoreerhalt.
- `tests/test_frontend_contract.py`: Statischer UI-, Sicherheits- und Rückwärtskompatibilitätsvertrag.
- `data/daily/2026-07-31.json`, `data/weekly/2026-W31.json`, `data/monthly/2026-07.json`: Vorhandene Version-1-Daten bleiben unverändert als Kompatibilitätsbelege.

---

### Task 1: Berichtsschema Version 2 und rückwärtskompatible Validierung

**Files:**
- Modify: `schemas/daily-report.schema.json`
- Modify: `schemas/period-report.schema.json`
- Modify: `src/lagebericht/schema.py`
- Modify: `tests/test_schema.py`

**Interfaces:**
- Consumes: Version-1-Kategorien mit `germanyRelevance: bool`.
- Produces: `validate_daily_report(report: dict, allowed_domains: set[str]) -> None` für Version 1 und 2.
- Produces: `validate_period_report(report: dict, allowed_domains: set[str]) -> None` für Version 1 und 2.
- Produces: Version-2-Bewertung `{score: int, reasonDe: str} | None`.

- [ ] **Step 1: Version-2-Testdaten und fehlschlagende Validierungstests schreiben**

In `tests/test_schema.py` die Standardhelfer auf Version 2 umstellen und eine unveränderte Version-1-Variante ergänzen:

```python
def rating(score=1, reason="Die mögliche Bedeutung ist derzeit begrenzt."):
    return {"score": score, "reasonDe": reason}


def category(category_id="politics_society"):
    return {
        "id": category_id,
        "status": "published",
        "headlineDe": "Eine wichtige Entwicklung",
        "summaryDe": [
            "Der erste Satz ordnet die Entwicklung ein.",
            "Der zweite Satz beschreibt die Entscheidung.",
            "Der dritte Satz erklärt die möglichen Folgen.",
            "Der vierte Satz nennt den aktuellen Stand.",
        ],
        "additionalImportant": None,
        "germanyRelevance": rating(1, "Indirekte Folgen für Deutschland sind möglich."),
        "overallSignificance": rating(2, "Die Entwicklung betrifft einen größeren politischen Bereich."),
        "sourceBasis": "single",
        "limitations": ["single_source"],
        "sources": [{
            "name": "NPR",
            "type": "öffentlich-rechtlich",
            "titleOriginal": "An important development",
            "url": "https://www.npr.org/example",
            "publishedAt": "2026-07-31T03:50:00Z",
        }],
    }
```

Leere Kategorien setzen beide Bewertungsfelder auf `None`. Tests hinzufügen für: gültige Scores 0 und 3, Ablehnung von `-1`, `4`, `True`, leerer Begründung und Bewertung bei leerem Status. Einen expliziten `legacy_daily_report()`-Test mit `schemaVersion: 1`, booleschem `germanyRelevance` und ohne `overallSignificance` ergänzen.

- [ ] **Step 2: Die neuen Tests ausführen und das erwartete Fehlschlagen bestätigen**

Run: `python -m unittest tests.test_schema -v`  
Expected: FAIL, weil Version 2 und `overallSignificance` noch unbekannt sind.

- [ ] **Step 3: JSON-Schemas auf Version 2 erweitern**

In beiden JSON-Schemas eine gemeinsame Bewertungsform verwenden:

```json
"rating": {
  "type": "object",
  "additionalProperties": false,
  "required": ["score", "reasonDe"],
  "properties": {
    "score": {"type": "integer", "minimum": 0, "maximum": 3},
    "reasonDe": {"type": "string", "minLength": 1, "maxLength": 300}
  }
}
```

`schemaVersion` erhält `const: 2`. `germanyRelevance` und `overallSignificance` werden Pflichtfelder mit `anyOf: [{"$ref": "#/$defs/rating"}, {"type": "null"}]`. Das Periodenschema definiert seine Abschnitte vollständig analog zum Tagesbericht, statt `countries` nur als unbeschränktes Array zu behandeln.

- [ ] **Step 4: Versionsabhängige Python-Validierung implementieren**

In `src/lagebericht/schema.py` ergänzen:

```python
def _rating(value, path: str) -> None:
    _object(value, path, {"score", "reasonDe"}, {"score", "reasonDe"})
    score = value["score"]
    if isinstance(score, bool) or not isinstance(score, int) or not 0 <= score <= 3:
        _fail(f"{path}.score", "must be an integer from 0 to 3")
    _string(value["reasonDe"], f"{path}.reasonDe", 300)
```

`_category` erhält `schema_version: int`. Bei Version 1 bleibt der bisherige boolesche Vertrag bestehen. Bei Version 2 sind beide neuen Felder erlaubt und erforderlich; bei `published` müssen beide Objekte `_rating` bestehen, bei `no_major_development` und `unavailable` müssen beide `None` sein. Die beiden Top-Level-Validatoren akzeptieren ausschließlich Version 1 oder 2 und reichen die Version an `_category` weiter.

- [ ] **Step 5: Schema-Tests ausführen**

Run: `python -m unittest tests.test_schema -v`  
Expected: PASS für Version 2 sowie den expliziten Version-1-Kompatibilitätstest.

- [ ] **Step 6: Vertrag separat committen**

```powershell
git add schemas/daily-report.schema.json schemas/period-report.schema.json src/lagebericht/schema.py tests/test_schema.py
git commit -m "feat: add versioned significance rating contract"
```

---

### Task 2: Vollständige Auswahl, Bewertungsrubrik und einmalige Reparatur

**Files:**
- Modify: `src/lagebericht/prompts.py`
- Modify: `src/lagebericht/pipeline.py`
- Modify: `tests/test_prompts.py`
- Modify: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: angereicherte Ereignisse mit `country`, `category` und nicht leeren `sourceCandidates`.
- Produces: `build_daily_repair_prompt(events: list[dict], rejected_report: dict, missing_slots: list[tuple[str, str]]) -> tuple[str, str]`.
- Produces: `_missing_published_slots(report: dict, events: list[dict]) -> list[tuple[str, str]]`.
- Produces: höchstens zwei Sonnet-Aufrufe pro Tageslauf; der zweite erfolgt nur bei unbegründet leer gebliebenen Slots.

- [ ] **Step 1: Prompt- und Pipeline-Tests für die neue Auswahlregel schreiben**

In `tests/test_prompts.py` prüfen, dass der Tagesprompt die Sätze `Eine niedrige Bewertung ist kein Ausschlussgrund`, `Einzelquelle darf veröffentlicht werden` und die beiden Skalen 0–3 enthält. Außerdem prüfen, dass der Reparaturprompt die fehlenden Slots und den verworfenen Bericht nur im Datenblock enthält.

In `tests/test_pipeline.py` drei Tests ergänzen:

```python
def complete_event():
    return {
        "id": "event-1",
        "country": "usa",
        "category": "politics_society",
        "summary": "A decision was announced.",
        "candidateIndexes": [0],
        "contradictions": False,
    }


def daily_report_with_empty_usa_politics():
    report = daily_report()
    report["countries"][0]["categories"][0].update({
        "status": "no_major_development",
        "headlineDe": "",
        "summaryDe": [],
        "additionalImportant": None,
        "germanyRelevance": None,
        "overallSignificance": None,
        "sourceBasis": "none",
        "limitations": [],
        "sources": [],
    })
    return report


def test_retries_when_model_hides_an_event_with_sources(self):
    hidden = daily_report_with_empty_usa_politics()
    ai = QueueAI([{"events": [complete_event()]}, hidden, daily_report()])
    result = DailyPipeline([SOURCE], FakeFetcher(), ai, ALLOWED_DOMAINS).run(date(2026, 7, 31))
    self.assertEqual(result["countries"][0]["categories"][0]["status"], "published")
    self.assertEqual(ai.models.count("claude-sonnet-4-6"), 2)


def test_does_not_retry_when_no_sourced_event_exists_for_empty_slot(self):
    ai = QueueAI([{"events": []}, daily_report_with_empty_usa_politics()])
    DailyPipeline([SOURCE], FakeFetcher(), ai, ALLOWED_DOMAINS).run(date(2026, 7, 31))
    self.assertEqual(ai.models.count("claude-sonnet-4-6"), 1)


def test_fails_when_repair_still_hides_a_sourced_event(self):
    hidden = daily_report_with_empty_usa_politics()
    ai = QueueAI([{"events": [complete_event()]}, hidden, daily_report_with_empty_usa_politics()])
    with self.assertRaisesRegex(PipelineError, "omitted sourced slots"):
        DailyPipeline([SOURCE], FakeFetcher(), ai, ALLOWED_DOMAINS).run(date(2026, 7, 31))
```

`complete_event()` verweist mit `candidateIndexes: [0]` auf den vorhandenen NPR-Testkandidaten; dadurch hängt der Test nicht von frei erfundenen Quellen ab.

- [ ] **Step 2: Die neuen Tests ausführen und das erwartete Fehlschlagen bestätigen**

Run: `python -m unittest tests.test_prompts tests.test_pipeline -v`  
Expected: FAIL wegen fehlendem Reparaturprompt, Version-2-Normalisierung und fehlender Slotprüfung.

- [ ] **Step 3: Tages- und Reparaturprompt implementieren**

`build_daily_prompt` ersetzt „wesentliches Hauptthema“ durch: pro Land und Kategorie das bestgeeignete vorhandene Ereignis auswählen; niedrige Bedeutung und Einzelquelle sind keine Ausschlussgründe. Die zwei Tabellen aus der Spezifikation werden als feste Bewertungsrubrik in die Systemanweisung aufgenommen. `no_major_development` ist nur erlaubt, wenn für den Slot kein Ereignis mit `sourceCandidates` vorhanden ist.

Der Reparaturprompt verwendet dieselben vertrauensgrenzen:

```python
def build_daily_repair_prompt(events, rejected_report, missing_slots):
    instructions = DAILY_RULES + (
        " Der erste Entwurf ließ belegte Kategorien aus. Erstelle den vollständigen Bericht neu. "
        "Veröffentliche für jeden genannten Slot ein Ereignis aus sourceCandidates."
    )
    payload = {
        "events": events,
        "rejectedReport": rejected_report,
        "missingSlots": [list(slot) for slot in missing_slots],
    }
    return instructions, f"<untrusted_repair_data>{_safe_json(payload)}</untrusted_repair_data>"
```

`DAILY_RULES` ist eine private Konstante, damit Erst- und Reparaturprompt garantiert dieselbe Rubrik nutzen.

- [ ] **Step 4: Slotprüfung und genau einen Reparaturlauf implementieren**

In `src/lagebericht/pipeline.py` ergänzen:

```python
def _missing_published_slots(report: dict, events: list[dict]) -> list[tuple[str, str]]:
    eligible = {
        (event.get("country"), event.get("category"))
        for event in events
        if isinstance(event, dict) and event.get("sourceCandidates")
    }
    published = {
        (country.get("id"), category.get("id"))
        for country in report.get("countries", []) if isinstance(country, dict)
        for category in country.get("categories", []) if isinstance(category, dict)
        if category.get("status") == "published"
    }
    return sorted(eligible - published)
```

`_normalize_empty_categories` setzt in Version 2 `germanyRelevance` und `overallSignificance` auf `None`. Nach dem ersten Sonnet-Aufruf berechnet `run()` die fehlenden Slots. Nur falls die Liste nicht leer ist, wird einmal `build_daily_repair_prompt` aufgerufen. Bleiben danach Slots offen, wirft die Pipeline `PipelineError("summary omitted sourced slots: ...")`; es wird kein irreführender leerer Bericht veröffentlicht.

- [ ] **Step 5: Prompt- und Pipeline-Tests ausführen**

Run: `python -m unittest tests.test_prompts tests.test_pipeline -v`  
Expected: PASS; der normale Pfad nutzt einen Sonnet-Aufruf, der Reparaturpfad genau zwei.

- [ ] **Step 6: Auswahlverhalten separat committen**

```powershell
git add src/lagebericht/prompts.py src/lagebericht/pipeline.py tests/test_prompts.py tests/test_pipeline.py
git commit -m "feat: publish sourced stories with transparent ratings"
```

---

### Task 3: Wochen- und Monatsberichte auf Version 2 umstellen

**Files:**
- Modify: `src/lagebericht/aggregate.py`
- Modify: `src/lagebericht/prompts.py`
- Modify: `tests/test_aggregate.py`

**Interfaces:**
- Consumes: validierte Tagesberichte Version 1 oder 2.
- Produces: neue Zeitraumberichte mit `schemaVersion: 2` und denselben zwei Bewertungsobjekten je veröffentlichtem Abschnitt.

- [ ] **Step 1: Fehlschlagende Aggregationstests schreiben**

`ContentAI.generate_json()` liefert Version-2-Abschnitte aus dem aktualisierten `category()`-Helfer. Ergänzen:

```python
def test_builds_version_two_period_with_ratings(self):
    self.publish_days(date(2026, 7, 27), 4)
    report = PeriodAggregator(self.root, ContentAI(), ALLOWED_DOMAINS).build_week(date(2026, 8, 2))
    self.assertEqual(report["schemaVersion"], 2)
    section = report["countries"][0]["sections"][0]
    self.assertEqual(section["germanyRelevance"]["score"], 1)
    self.assertEqual(section["overallSignificance"]["score"], 2)
```

Einen Test ergänzen, der vier gespeicherte Version-1-Tagesberichte lädt und daraus erfolgreich einen Version-2-Wochenbericht erzeugt.

- [ ] **Step 2: Aggregationstests ausführen und das erwartete Fehlschlagen bestätigen**

Run: `python -m unittest tests.test_aggregate -v`  
Expected: FAIL, weil Aggregator und `SECTION_SCHEMA` noch Version-1-Bewertungen verwenden.

- [ ] **Step 3: Zeitraumschema und Prompt aktualisieren**

In `SECTION_SCHEMA` beide Bewertungsfelder als Objekt oder `null` definieren und `overallSignificance` verpflichtend ergänzen. `PeriodAggregator._build()` setzt `schemaVersion` auf 2. `build_period_prompt` erhält ausdrücklich: Scores dürfen Entwicklungslinien sortieren, sind aber kein alleiniger Grund, eine belegte Entwicklung wegzulassen; neue Zeitraum-Scores beziehen sich auf die Bedeutung im gesamten Zeitraum.

- [ ] **Step 4: Aggregationstests ausführen**

Run: `python -m unittest tests.test_aggregate -v`  
Expected: PASS für gemischte historische Tagesdaten und neue Version-2-Ausgabe.

- [ ] **Step 5: Zeitraumberichte separat committen**

```powershell
git add src/lagebericht/aggregate.py src/lagebericht/prompts.py tests/test_aggregate.py
git commit -m "feat: carry significance ratings into period reports"
```

---

### Task 4: Zugängliche Doppelbewertung in der PWA darstellen

**Files:**
- Modify: `assets/app.js`
- Modify: `assets/app.css`
- Modify: `tests/test_frontend_contract.py`

**Interfaces:**
- Consumes: Version-2-Bewertungen sowie boolesches `germanyRelevance` aus Version 1.
- Produces: `renderRatings(item, article) -> void` und `ratingLevel(score: number) -> string`.

- [ ] **Step 1: Fehlschlagende Frontend-Vertragstests schreiben**

In `tests/test_frontend_contract.py` statisch prüfen:

```python
def test_frontend_renders_both_rating_dimensions_accessibly(self):
    app = (ROOT / "assets" / "app.js").read_text(encoding="utf-8")
    css = (ROOT / "assets" / "app.css").read_text(encoding="utf-8")
    self.assertIn("Deutschland-Bezug", app)
    self.assertIn("Allgemeine Tragweite", app)
    self.assertIn("rating.score", app)
    self.assertIn("rating.reasonDe", app)
    self.assertIn("rating-0", css)
    self.assertIn("rating-3", css)


def test_empty_copy_does_not_call_news_unimportant(self):
    app = (ROOT / "assets" / "app.js").read_text(encoding="utf-8")
    self.assertNotIn("belanglose Meldung", app)
    self.assertNotIn("keine wesentliche neue Entwicklung", app.lower())
    self.assertIn("Keine neue Meldung in den geprüften Quellen", app)
```

- [ ] **Step 2: Frontend-Vertragstests ausführen und das erwartete Fehlschlagen bestätigen**

Run: `python -m unittest tests.test_frontend_contract -v`  
Expected: FAIL, weil Doppelbewertung und neue Leertextformulierung fehlen.

- [ ] **Step 3: Rückwärtskompatible Bewertungsdarstellung implementieren**

In `assets/app.js` ergänzen:

```javascript
function ratingLevel(score) {
  return Number.isInteger(score) && score >= 0 && score <= 3 ? `rating-${score}` : 'rating-legacy';
}

function renderRating(label, icon, rating) {
  if (!rating || !Number.isInteger(rating.score)) return null;
  const details = node('details', null, `rating ${ratingLevel(rating.score)}`);
  details.append(node('summary', `${icon} ${label}: ${rating.score} von 3`));
  details.append(node('p', rating.reasonDe, 'rating-reason'));
  return details;
}

function renderRatings(item, article) {
  const group = node('div', null, 'ratings');
  const germany = renderRating('Deutschland-Bezug', 'DE', item.germanyRelevance);
  const overall = renderRating('Allgemeine Tragweite', '⚡', item.overallSignificance);
  if (germany) group.append(germany);
  if (overall) group.append(overall);
  if (group.childElementCount) article.append(group);
}
```

`renderStory()` ruft `renderRatings` nur bei `published` auf. Für Version 1 wird der bisherige boolesche Wert ausschließlich als Kennzeichnung `Deutschland-Bezug · alter Datenstand` gezeigt; es wird kein Score berechnet. Die leere Kategorie erhält Überschrift `Keine neue Meldung in den geprüften Quellen` und den Erklärungstext `Für diesen Bereich wurde im Berichtsfenster keine technisch geeignete neue Meldung gefunden.`

- [ ] **Step 4: Intensitätsfarben und responsive Darstellung ergänzen**

In `assets/app.css` `.ratings` als flexiblen, umbrechenden Container gestalten. Jede `.rating` zeigt Zahl und Text und nutzt eine linke Farbkante. Kontrastreiche Variablen für 0–3 sowohl im hellen als auch dunklen Farbschema definieren. `summary` bleibt per Tastatur bedienbar; keine Information darf ausschließlich aus der Farbe hervorgehen.

- [ ] **Step 5: Frontend-Vertragstests ausführen**

Run: `python -m unittest tests.test_frontend_contract -v`  
Expected: PASS ohne `innerHTML`, externe Ressourcen oder unsichere Quellenlinks.

- [ ] **Step 6: PWA-Darstellung separat committen**

```powershell
git add assets/app.js assets/app.css tests/test_frontend_contract.py
git commit -m "feat: show transparent significance ratings"
```

---

### Task 5: Gesamtabnahme, Cache-Aktualisierung und Produktionslauf vorbereiten

**Files:**
- Modify: `service-worker.js`
- Modify: `README.md`
- Test: `tests/test_frontend_contract.py`
- Test: gesamte Suite unter `tests/`

**Interfaces:**
- Consumes: vollständige Version-2-Pipeline und rückwärtskompatible PWA.
- Produces: auslieferbares PWA-Shell-Update und dokumentierte Testwoche.

- [ ] **Step 1: Cache-Vertrag fehlschlagend auf Version 4 setzen**

In `tests/test_frontend_contract.py` die erwartete Cachekennung von `lagebericht-shell-v3` auf `lagebericht-shell-v4` ändern.

- [ ] **Step 2: Den einzelnen Cache-Test ausführen und das erwartete Fehlschlagen bestätigen**

Run: `python -m unittest tests.test_frontend_contract.FrontendContractTests.test_service_worker_does_not_cache_cross_origin_requests -v`  
Expected: FAIL, weil `service-worker.js` noch Version 3 verwendet.

- [ ] **Step 3: Cache und Betriebsdokumentation aktualisieren**

In `service-worker.js` ausschließlich den Shell-Cache auf `lagebericht-shell-v4` erhöhen. In `README.md` dokumentieren: zwei sichtbare 0–3-Bewertungen, Bedeutung der Farben, Einzelquellenregel, neue Semantik von `no_major_development`, keine automatische Personalisierung und Auswertung nach sieben Tagesläufen.

- [ ] **Step 4: Vollständige lokale Test-Suite ausführen**

Run: `$env:PYTHONPATH='src'; python -m unittest discover -s tests -v`  
Expected: Alle Tests PASS; insbesondere Schema, Pipeline, Aggregation, Veröffentlichung, Frontend-, Workflow- und Sicherheitsverträge.

- [ ] **Step 5: Öffentliche Beispieldaten ausdrücklich unverändert validieren**

Run: `$env:PYTHONPATH='src'; python -m unittest tests.test_frontend_contract.FrontendContractTests.test_example_reports_satisfy_data_contracts -v`  
Expected: PASS für die vorhandenen Version-1-Dateien. `git status --short data` bleibt leer; historische Bewertungen wurden nicht erfunden.

- [ ] **Step 6: Abschlussänderungen committen**

```powershell
git add service-worker.js README.md tests/test_frontend_contract.py
git commit -m "docs: prepare significance rating test week"
```

- [ ] **Step 7: Produktionsänderungen pushen und GitHub Actions prüfen**

Run: `git push origin main`  
Expected: Push erfolgreich; die Workflows `Tests` und `GitHub Pages veröffentlichen` enden grün. Noch keinen manuellen Tageslauf starten, solange der Nutzer nicht ausdrücklich neue API-Kosten für einen Testlauf freigibt.

- [ ] **Step 8: Nach Freigabe genau einen manuellen Tageslauf ausführen**

In GitHub unter **Actions → Täglicher Lagebericht → Run workflow** starten. Erwartung: Der Lauf veröffentlicht Version 2; vorhandene Einzelquellenmeldungen bleiben sichtbar; jeder veröffentlichte Abschnitt zeigt beide Scores und Begründungen. Danach die Live-Seite mit einem Cache-Buster wie `?v=<commit>` öffnen und USA, China sowie Montenegro auf Mobil- und Desktopbreite prüfen.

---

## Definition of Done

- Alle lokalen Tests und GitHub-Actions-Tests laufen erfolgreich.
- Kein geeigneter, mit einer erlaubten Quelle belegter Slot wird aufgrund niedriger Modellbewertung still ausgeblendet.
- Einquellenmeldungen erscheinen mit sichtbarer Einschränkung.
- Jede neue veröffentlichte Meldung enthält zwei gültige Scores und zwei verständliche Begründungen.
- Leere Abschnitte behaupten nur, dass keine geeignete Meldung gefunden wurde; technische Ausfälle bleiben davon unterscheidbar.
- Die PWA zeigt Zahl, Text und Farbe, funktioniert mit Tastatur und Dark Mode und liest historische Version-1-Berichte.
- Nach sieben erfolgreichen Tagesläufen kann der Nutzer konkrete Abweichungen melden, ohne dass zuvor ein automatisches Lern- oder Speicherverfahren eingeführt wurde.
