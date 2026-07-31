# Persönlicher Lagebericht – Implementierungsplan

> **Historischer Stand:** Dieser ursprüngliche Plan beschreibt die erste OpenAI-Implementierung. Die produktive Migration auf Anthropic ist in `docs/superpowers/specs/2026-07-31-anthropic-migration-design.md` und `docs/superpowers/plans/2026-07-31-anthropic-migration.md` festgelegt.

> **Für agentische Bearbeitung:** Die Aufgaben werden testgetrieben und in der angegebenen Reihenfolge umgesetzt. Jeder Schritt verwendet Checkboxen zur Fortschrittskontrolle.

**Ziel:** Eine lokal vollständig testbare, installierbare PWA mit sicherer Nachrichtenpipeline, Tagesarchiv sowie automatischen Wochen- und Monatsberichten für USA, China und Montenegro erstellen.

**Stand 31.07.2026:** Lokal vollständig umgesetzt und getestet. Ausstehend sind nur Schritte, die ein GitHub-Repository, einen bewusst gesetzten Kostenrahmen und den persönlichen API-Schlüssel erfordern: erster Live-Lauf, GitHub-Pages-Veröffentlichung und anschließender Live-Sicherheitscheck.

**Architektur:** Eine Python-Standardbibliothek-Pipeline ruft ausschließlich konfigurierte Quellen ab, normalisiert Kandidaten, nutzt strukturierte OpenAI-Ausgaben und veröffentlicht nur validierte JSON-Berichte. Ein getrenntes Vanilla-HTML/CSS/JS-Frontend liest diese statischen Dateien von GitHub Pages; Secrets und KI-Aufrufe bleiben ausschließlich im GitHub-Workflow.

**Technik:** Python 3.12 Standardbibliothek und `unittest`, OpenAI Responses API per HTTPS, JSON Schema als Datenvertrag, Vanilla HTML/CSS/JavaScript, Service Worker, GitHub Actions und GitHub Pages.

## Globale Randbedingungen

- Länder: USA, China und Montenegro.
- Kategorien: Politik & Gesellschaft, Wirtschaft & Technologie, Außenpolitik & Sicherheit.
- Tageslauf: 06:30 Uhr `Europe/Berlin`, sieben Tage pro Woche.
- Wochenlauf: nach dem sonntäglichen Tagesbericht für Montag bis Sonntag.
- Monatslauf: nach dem Tagesbericht des letzten Kalendertags.
- Modelle: `gpt-5.6-luna` für Vorverarbeitung, `gpt-5.6-terra` für Auswahl und Formulierung; über Umgebungsvariablen überschreibbar.
- Keine Datenbank, Benutzerkonten, Analytics, externen Frontend-Abhängigkeiten oder dynamische HTML-Injektion.
- Externe Quell-URLs müssen `https` verwenden und auf einer konfigurierten Domain liegen.
- Ein ungültiger Lauf darf keine vorhandene gültige Datei oder den Index überschreiben.
- Kein produktiver API-Aufruf ohne `OPENAI_API_KEY` und bewusst gesetztes Kostenlimit im OpenAI-Projekt.

---

### Aufgabe 1: Projektgrundgerüst und Berichtsschema

**Dateien:**
- Erstellen: `pyproject.toml`, `.gitignore`, `src/lagebericht/__init__.py`
- Erstellen: `src/lagebericht/schema.py`, `schemas/daily-report.schema.json`, `schemas/period-report.schema.json`
- Test: `tests/test_schema.py`

**Schnittstellen:**
- Erzeugt: `validate_daily_report(report: dict) -> None`
- Erzeugt: `validate_period_report(report: dict) -> None`
- Fehler: `ReportValidationError(ValueError)` mit verständlicher Pfadangabe

- [ ] Test schreiben, der einen vollständigen Minimalbericht akzeptiert und ungültige Enum-Werte, fremde Domains, `javascript:`-URLs sowie zu lange Texte ablehnt.
- [ ] `python -m unittest tests.test_schema -v` ausführen und das erwartete Fehlschlagen wegen des fehlenden Moduls bestätigen.
- [ ] Validierer mit festen erlaubten Ländern, Kategorien, Statuswerten, Längen und URL-Regeln implementieren.
- [ ] JSON-Schema-Dateien deckungsgleich zu den Python-Prüfungen erstellen.
- [ ] Test erneut ausführen und erfolgreich abschließen.
- [ ] Nur Dateien dieser Aufgabe committen: `feat: add report schemas and validation`.

### Aufgabe 2: Sichere Quellenkonfiguration und Normalisierung

**Dateien:**
- Erstellen: `src/lagebericht/config.py`, `src/lagebericht/normalize.py`
- Erstellen: `config/sources.json`
- Test: `tests/test_config.py`, `tests/test_normalize.py`
- Testdaten: `tests/fixtures/sample-rss.xml`, `tests/fixtures/sample-atom.xml`

**Schnittstellen:**
- Erzeugt: `load_sources(path: Path) -> list[SourceConfig]`
- Erzeugt: `normalize_feed(source: SourceConfig, payload: bytes) -> list[ArticleCandidate]`
- `ArticleCandidate` enthält `source_id`, `country`, `title`, `url`, `published_at`, `excerpt`, `retrieval`, `language`.

- [ ] Tests für doppelte Quellen-IDs, unsichere Feed-URLs, ungültige Allowlist-Domains und unbekannte Abrufarten schreiben.
- [ ] Tests für RSS, Atom, fehlendes Datum, HTML-Zeichen, relative Links und doppelte Artikel schreiben.
- [ ] Tests ausführen und das erwartete Fehlschlagen bestätigen.
- [ ] Unveränderliche Dataclasses und strikte Konfigurationsprüfung implementieren.
- [ ] RSS-/Atom-Normalisierung mit `xml.etree.ElementTree`, `email.utils` und `html` implementieren; XML-Entitäten und externe DTDs werden nicht aufgelöst.
- [ ] Alle Tests der Aufgabe erfolgreich ausführen.
- [ ] Commit: `feat: normalize configured news feeds`.

### Aufgabe 3: Begrenzter HTTP-Abruf und Domain-Allowlist

**Dateien:**
- Erstellen: `src/lagebericht/fetch.py`
- Test: `tests/test_fetch.py`

**Schnittstellen:**
- Erzeugt: `SafeFetcher.fetch(url: str, allowed_domains: frozenset[str]) -> FetchResult`
- `FetchResult` enthält `body`, `final_url`, `content_type`, `retrieval`.

- [ ] Einen lokalen Testserver verwenden und Tests für erfolgreichen Abruf, Größenlimit, Timeoutkonfiguration, Redirect auf erlaubte Domain, Redirect auf fremde Domain und Nicht-HTTPS-Produktiv-URL schreiben.
- [ ] Tests ausführen und erwartetes Fehlschlagen bestätigen.
- [ ] Abruf mit maximal 2 MB, 15 Sekunden Timeout, höchstens drei Redirects und festem User-Agent implementieren.
- [ ] Redirects manuell prüfen; private, Loopback- und Link-Local-Zieladressen außerhalb expliziter Testkonfiguration ablehnen.
- [ ] Tests erfolgreich ausführen.
- [ ] Commit: `feat: add allowlisted bounded fetcher`.

### Aufgabe 4: Dubletten, Zeitfenster und Ereignisvorbereitung

**Dateien:**
- Erstellen: `src/lagebericht/events.py`
- Test: `tests/test_events.py`

**Schnittstellen:**
- Erzeugt: `deduplicate_candidates(candidates: list[ArticleCandidate]) -> list[ArticleCandidate]`
- Erzeugt: `filter_by_window(candidates, start: datetime, end: datetime) -> list[ArticleCandidate]`
- Erzeugt: `build_event_input(candidates) -> list[dict]`

- [ ] Tests für kanonisch gleiche URLs, Trackingparameter, fast identische Titel, Zeitgrenzen und stabile Sortierung schreiben.
- [ ] Tests ausführen und erwartetes Fehlschlagen bestätigen.
- [ ] URL-Kanonisierung und konservative Titelnormalisierung implementieren; unterschiedliche Quellen desselben Ereignisses nicht vor dem KI-Abgleich verlieren.
- [ ] Tests erfolgreich ausführen.
- [ ] Commit: `feat: prepare article candidates for selection`.

### Aufgabe 5: OpenAI-Client mit strukturierten Ausgaben

**Dateien:**
- Erstellen: `src/lagebericht/openai_client.py`, `src/lagebericht/prompts.py`
- Test: `tests/test_openai_client.py`, `tests/test_prompts.py`

**Schnittstellen:**
- Erzeugt: `OpenAIResponsesClient.generate_json(model: str, instructions: str, input_text: str, schema_name: str, schema: dict) -> dict`
- Erzeugt: `build_extraction_prompt(candidates: list[dict]) -> tuple[str, str]`
- Erzeugt: `build_daily_prompt(events: list[dict], previous_reports: list[dict]) -> tuple[str, str]`
- Erzeugt: `build_period_prompt(reports: list[dict], period_type: str) -> tuple[str, str]`

- [ ] Testtransport schreiben, der Request-Body und Header aufzeichnet und eine Responses-API-Antwort mit `output_text` zurückgibt.
- [ ] Tests für fehlenden Schlüssel, HTTP-Fehler, nicht abgeschlossenes Ergebnis, Modellverweigerung, ungültiges JSON und erfolgreiche strukturierte Ausgabe schreiben.
- [ ] Prompt-Tests mit eingebetteten Artikelanweisungen wie „Ignoriere das System“ schreiben und prüfen, dass diese nur innerhalb klar markierter Datenblöcke vorkommen.
- [ ] Tests ausführen und erwartetes Fehlschlagen bestätigen.
- [ ] HTTPS-Client für `POST /v1/responses` mit `store: false`, strukturiertem `text.format`, festem Timeout und ohne Werkzeuge implementieren.
- [ ] Extraktions-, Tages- und Rückblickprompts mit Trennung von Regeln und nicht vertrauenswürdigen Quelldaten implementieren.
- [ ] Tests erfolgreich ausführen.
- [ ] Commit: `feat: add structured OpenAI processing`.

### Aufgabe 6: Tagespipeline und atomare Veröffentlichung

**Dateien:**
- Erstellen: `src/lagebericht/pipeline.py`, `src/lagebericht/publish.py`, `scripts/run_daily.py`
- Test: `tests/test_pipeline.py`, `tests/test_publish.py`

**Schnittstellen:**
- Erzeugt: `DailyPipeline.run(report_date: date) -> dict`
- Erzeugt: `Publisher.publish_daily(report: dict, data_root: Path) -> Path`
- Erzeugt: `rebuild_index(data_root: Path) -> dict`

- [ ] Tests für vollständigen Bericht, Quell-Teilausfall, vollständigen Ausfall, ungültige Modellantwort und unveränderten letzten gültigen Index schreiben.
- [ ] Tests für Schreiben über temporäre Datei plus atomare Ersetzung und idempotenten Wiederholungslauf schreiben.
- [ ] Tests ausführen und erwartetes Fehlschlagen bestätigen.
- [ ] Pipeline mit injizierbaren Fetcher- und KI-Schnittstellen implementieren.
- [ ] Publisher implementieren, der ausschließlich validierte Berichte akzeptiert und den Index erst nach erfolgreichem Schreiben aktualisiert.
- [ ] CLI mit `--date`, `--dry-run`, `--sources` und `--data-root` implementieren; ohne API-Schlüssel verständlich abbrechen.
- [ ] Tests erfolgreich ausführen.
- [ ] Commit: `feat: build daily report pipeline`.

### Aufgabe 7: Wochen- und Monatsaggregation

**Dateien:**
- Erstellen: `src/lagebericht/aggregate.py`, `scripts/run_period.py`
- Test: `tests/test_aggregate.py`

**Schnittstellen:**
- Erzeugt: `load_period_reports(data_root: Path, start: date, end: date) -> tuple[list[dict], list[str]]`
- Erzeugt: `PeriodAggregator.build_week(end_date: date) -> dict | None`
- Erzeugt: `PeriodAggregator.build_month(year: int, month: int) -> dict | None`

- [ ] Tests für Montag-bis-Sonntag, Monatsgrenzen, Schaltjahr, mindestens vier beziehungsweise zwanzig vorhandene Tage, fehlende Tage, Idempotenz und getrennte Ausgabepfade schreiben.
- [ ] Tests ausführen und erwartetes Fehlschlagen bestätigen.
- [ ] Zeitraumladung, Vollständigkeitsstatus und strukturierte KI-Verdichtung implementieren.
- [ ] Dateien als `data/weekly/YYYY-Www.json` und `data/monthly/YYYY-MM.json` atomar veröffentlichen und den gemeinsamen Index aktualisieren.
- [ ] Tests erfolgreich ausführen.
- [ ] Commit: `feat: add weekly and monthly briefings`.

### Aufgabe 8: Statische PWA und sichere Darstellung

**Dateien:**
- Erstellen: `index.html`, `offline.html`, `manifest.webmanifest`, `service-worker.js`
- Erstellen: `assets/app.css`, `assets/app.js`, `assets/icons/icon.svg`
- Erstellen: `data/index.json`, `data/daily/2026-07-31.json`, `data/weekly/2026-W31.json`, `data/monthly/2026-07.json`
- Test: `tests/test_frontend_contract.py`

**Schnittstellen:**
- Frontend lädt `data/index.json` und danach einen Pfad aus dessen `daily`, `weekly` oder `monthly`-Liste.
- Dynamische Inhalte werden ausschließlich mit `textContent`, `createElement`, geprüften `href`-Werten und nativen `details`-Elementen erzeugt.

- [ ] Vertragsprüfungen schreiben: Manifestfelder, Service-Worker-Registrierung, keine externen Skripte/Fonts, keine dynamischen `innerHTML`-Zuweisungen, drei Archivarten und sichere Linkbehandlung.
- [ ] Tests ausführen und erwartetes Fehlschlagen bestätigen.
- [ ] Semantische PWA-Shell im bestätigten Hybrid-Design B/C implementieren.
- [ ] Länderwahl, Zeitraumwahl, Archivnavigation, Quellen-Aufklapper, Leer-/Fehlerzustände und Tastaturbedienung implementieren.
- [ ] Service Worker mit Netzwerk-zuerst für Berichte und Cache-Rückfall auf zuletzt gelesene Daten implementieren.
- [ ] Gültige, deutlich als Beispieldaten markierte Tages-, Wochen- und Monatsdateien ergänzen.
- [ ] Tests erfolgreich ausführen.
- [ ] Commit: `feat: add installable briefing PWA`.

### Aufgabe 9: GitHub Actions und Betriebsgrenzen

**Dateien:**
- Erstellen: `.github/workflows/test.yml`, `.github/workflows/daily-report.yml`
- Erstellen: `README.md`, `SECURITY.md`
- Test: `tests/test_workflow_contract.py`

**Schnittstellen:**
- Testworkflow führt `python -m unittest discover -s tests -v` aus.
- Tagesworkflow unterstützt `schedule` und `workflow_dispatch` und verwendet `OPENAI_API_KEY` ausschließlich aus GitHub Secrets.

- [ ] Vertragsprüfungen für minimale Berechtigungen, gepinnte Actions-SHAs, keine PR-Secret-Nutzung, Sommerzeitwächter, API-Schlüsselreferenz und Testaufruf schreiben.
- [ ] Tests ausführen und erwartetes Fehlschlagen bestätigen.
- [ ] Zwei UTC-Cronzeiten plus Python-Ortszeitprüfung für 06:30 Uhr Berlin implementieren.
- [ ] Tageslauf, sonntäglichen Wochenlauf und Monatsendlauf mit getrennten Fehlerausgängen implementieren.
- [ ] README mit lokaler Ausführung, GitHub-Einrichtung, Secret, Kostenlimit, PWA-Installation und bewusst ausstehenden Nutzeraktionen schreiben.
- [ ] Tests erfolgreich ausführen.
- [ ] Commit: `ci: automate tests and daily publishing`.

### Aufgabe 10: Endprüfung, Security-Audit und Dokumentation

**Dateien:**
- Ändern: projektbezogene Dateien aus den Auditbefunden
- Erstellen: `docs/security-audit-2026-07-31.md`
- Ändern: `../Politik-Wirtschaft-App.md`, `../Politik-Wirtschaft-App – Designspezifikation.md`

**Schnittstellen:**
- Gesamttest: `python -m unittest discover -s tests -v`
- Lokaler Server: `python -m http.server 8000`

- [ ] Vollständige Testsuite ausführen und Ausgabe sichern.
- [ ] Beispieldaten und Index erneut gegen die Python-Validierer prüfen.
- [ ] Lokale PWA in schmaler und breiter Ansicht, Archivwechsel, Offline-Rückfall und fehlende Datei prüfen.
- [ ] `security-audit-webapp` auf Pipeline, Workflow und Frontend anwenden; rote Befunde vor Abschluss testgetrieben beheben.
- [ ] Auditbericht mit Befund, Beleg, Maßnahme und Restentscheidung schreiben.
- [ ] Projektnotizen mit erreichtem Stand, Testnachweis und den verbleibenden Nutzeraktionen aktualisieren.
- [ ] Abschlusscommit: `docs: record implementation and security audit`.

## Bewusst verbleibende Nutzeraktionen

Diese Schritte werden vorbereitet, aber nicht ohne Michael ausgeführt:

1. monatliches Kostenlimit im OpenAI-Projekt festlegen
2. `OPENAI_API_KEY` als GitHub Secret hinterlegen
3. Repository-Namen und öffentliche GitHub-Pages-URL bestätigen
4. lokales Repository zu GitHub pushen und GitHub Pages aktivieren
5. echten API-Testlauf und anschließenden Go-live freigeben
