---
title: EU als vierter Länderblock
date: 2026-08-08
status: umgesetzt (autonom, ohne Zwischen-Freigabe des Spec-Dokuments – Nutzer hat explizit "komplett selbständig umsetzen" angewiesen)
---

# Ziel

Die App erhält einen vierten Block neben USA, China und Montenegro: die EU-Institutionen (Kommission, Rat, Parlament, EU-weite Politik). Gleiche drei Kategorien, gleiche Struktur, gleiche Qualitätsansprüche wie die bestehenden Länder – kein Sonderfall im Datenmodell.

# Ausgangslage

Das war bereits am 03.08.2026 als "die EU als vierter Bereich" in einer Design-Spec explizit als zurückgestellt vermerkt (`docs/superpowers/specs/2026-08-03-teilberichte-und-abschlusszeitpunkte-design.md`). Die Struktur des Codes ist an fünf unabhängigen Stellen auf genau drei Länder festgelegt (Aufzählungen, keine Ableitung von der Länderanzahl) – alle fünf müssen im Gleichschritt erweitert werden, sonst driften Validierung und tatsächliche Daten auseinander.

# Quellenrecherche (live geprüft am 08.08.2026)

| Quelle | Status | Ergebnis |
|---|---|---|
| Politico Europe (`politico.eu/feed`) | ✅ 200, gültiges RSS | breite EU-Politik/Policy-Abdeckung, deckt auch Wirtschaft/Tech-Kategorien ab (Financial Services, Trade, Tech als Kategorien im Feed sichtbar) |
| EUobserver (`euobserver.com/feed/`) | ✅ 200, gültiges RSS (nach Redirect auf trailing slash) | unabhängiger EU-Journalismus, finanziell/redaktionell unabhängig von den EU-Institutionen |
| EU-Kommission Pressestelle (`ec.europa.eu/commission/presscorner/api/rss`) | ✅ 200, gültiges RSS | offizielle institutionelle Perspektive, analog zur Rolle von China Daily bei China – muss entsprechend als "institutionelle Perspektive" gekennzeichnet werden, keine Formulierung als neutrale Tatsache übernehmen |
| Euractiv (`euractiv.com/feed`) | ❌ 403 Forbidden | blockiert automatisierte Abrufe, verworfen |
| Reuters Europe | ❌ 401 Forbidden | blockiert, verworfen |
| Euronews | ⚠️ erreichbar, aber zu global/undifferenziert (erste Meldung im Test: USA/Kolumbien) | verworfen zugunsten von Präzision statt Breite |

Alle drei gewählten Quellen liefern `retrieval: "rss"` – keine der (im Code ohnehin deaktivierten) HTML-Adapter nötig. Damit ist die EU strukturell näher an Montenegro (alle Quellen aktiv nutzbar) als an China (2 von 3 Quellen deaktiviert).

# Umfang

Enthalten:
- 3 neue Quellen in `config/sources.json`, alle drei Kategorien abdeckend
- `"eu"` als vierter Wert überall dort, wo `COUNTRIES`/Länder-Enums existieren (5 Stellen, siehe unten)
- Frontend: vierter Button in der Länderauswahl, Grid auf 4 Spalten
- Prompt-Anpassung: Zähler "drei Länder" → "vier Länder"; Klarstellung, dass die bestehende EU-Bezug-Zusatzregel sich auf die anderen drei Länder bezieht, nicht auf den EU-Block selbst
- Alle betroffenen Tests (Fixtures, Zähler, Länge-Assertions)

Nicht enthalten:
- Eine fünfte Kategorie oder Sonderbehandlung für EU-Inhalte – exakt die gleichen drei Kategorien wie überall
- Rückwirkende Neuerzeugung vergangener Wochen-/Monatsberichte mit EU-Daten (die begannen ohne EU, bleiben unvollständig für den EU-Teil rückwirkend – wie bei jedem neuen Land, das mitten im Monat hinzukommt)
- Eine vierte/fünfte Quelle "für den Notfall" – drei aktive, geprüfte Quellen genügen, analog zu China

# Die fünf Stellen, die im Gleichschritt geändert werden müssen

1. `src/lagebericht/schema.py`: `COUNTRIES = ("usa", "china", "montenegro")` → `+ "eu"`. Zusätzlich die hartkodierten `len(...) != 3`-Prüfungen (Zeilen ~147, 157, 163, 193, 207) auf die tatsächliche Länge von `COUNTRIES` beziehen (`len(COUNTRIES)`) statt erneut die Zahl 3 zu hartcodieren – das verhindert genau diese Art von Drift beim nächsten Land.
2. `src/lagebericht/aggregate.py`: `COUNTRY_ORDER` erweitern; `PERIOD_CONTENT_SCHEMA`s `enum`- und `minItems`/`maxItems`-Werte auf `COUNTRIES`/`len(COUNTRIES)` umstellen statt erneut hartzukodieren.
3. `src/lagebericht/pipeline.py`: `EVENT_SCHEMA`s `country`-Enum ebenfalls von `schema.COUNTRIES` ableiten statt eigener Literalliste.
4. `schemas/daily-report.schema.json` und `schemas/period-report.schema.json`: `enum` und `minItems`/`maxItems` manuell auf 4 Werte/4 anpassen (JSON-Schema-Dateien können nicht aus Python-Code ableiten, müssen synchron von Hand gepflegt werden – das war schon vorher so, keine Verschlechterung).
5. `assets/app.js` (`COUNTRY_LABELS`), `index.html` (vierter `<button data-country="eu">` mit `country-code`-Badge "EU"), `assets/app.css` (`.country-nav` von `repeat(3, 1fr)` auf `repeat(4, 1fr)`, bei schmalen Bildschirmen ggf. 2×2-Umbruch prüfen).

# Prompt-Anpassungen

In `src/lagebericht/prompts.py`:
- `build_period_prompt`: "gliedere danach USA, China und Montenegro" → "gliedere danach USA, China, Montenegro und EU".
- `DAILY_RULES`: Ergänzung, dass für den EU-Block "Deutschland-Bezug" weiterhin die tatsächliche Betroffenheit Deutschlands als EU-Mitgliedstaat misst (0 = rein verfahrenstechnisch/andere Mitgliedstaaten betreffend, bis 3 = unmittelbare Auswirkung auf Deutschland), nicht automatisch hochgesetzt nur weil es EU-Themen sind.
- Klarstellung: Die bestehende Regel "Ein Deutschland- oder EU-Bezug ist ein Zusatzkriterium" (in der ursprünglichen Auswahl-Logik-Beschreibung, nicht wörtlich im Prompt-Code, aber sinngemäß in `DAILY_RULES`) gilt für die Auswahl innerhalb USA/China/Montenegro – für den EU-Block selbst ist das kein zusätzliches Kriterium, weil es dort keinen Unterschied macht (jede EU-Meldung hat per Definition EU-Bezug).

# Wording: "Land" vs. "Region"

Die EU ist kein Land. Wo die Oberfläche das Wort "Land" explizit verwendet (`aria-label="Land auswählen"` in `index.html`), wird das auf "Land oder Region auswählen" präzisiert. Das Datenmodell selbst nennt es weiterhin `country.id`/`country.label` (Umbenennen auf `region` würde unnötig viel anfassen für einen rein sprachlichen Unterschied – YAGNI).

# Kostenauswirkung

Ein viertes Land bedeutet grob ein Drittel mehr Instanzen der Kategorisierungs-/Extraktions- und Formulierungsaufrufe pro Lauf (Haiku für Vorverarbeitung, Sonnet für die finale Formulierung). Bei den bisher beobachteten ca. 0,21 € für einen einzelnen Tageslauf mit drei Ländern ist auch mit vier Ländern und dem bestehenden 5-€-Monatsbudget ausreichend Spielraum vorhanden – wird aber in der Kostenanzeige ohnehin transparent sichtbar, keine Vorabbegrenzung nötig.

# Tests

Betroffen: `tests/test_schema.py` (Fixtures um vierten Ländereintrag ergänzen), `tests/test_aggregate.py` (KI-Antwort-Fixtures + Reihenfolge-Assertion), `tests/test_workflow_contract.py` (3-Länder-Fixture), `tests/test_frontend_contract.py` (`country-code`-Zähler 3→4). Neue, gezielte Tests: `COUNTRIES` enthält "eu"; `config/sources.json` hat mindestens eine aktive Quelle pro neuer Kategorie für "eu"; die Live-Quellen-URLs sind in `ALLOWED_HOSTS` in `assets/app.js` hinterlegt.
