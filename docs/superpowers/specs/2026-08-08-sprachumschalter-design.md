---
title: Sprachumschalter Deutsch/Englisch
date: 2026-08-08
status: umgesetzt (autonom, ohne Zwischen-Freigabe des Spec-Dokuments – Nutzer hat explizit "komplett selbständig umsetzen" angewiesen)
---

# Ziel

Ein Umschalter neben dem bereits vorhandenen Hell/Dunkel-Umschalter, der die **Berichtsinhalte selbst** auf Englisch zeigt, nicht nur die Bedienoberfläche. Grund: Nur die Oberfläche zu übersetzen, während die eigentlichen Nachrichten deutsch bleiben, wäre unstimmig.

# Kostenentscheidung

Eine zweite vollständige Generierung auf Englisch (nochmal Auswahl + Formulierung mit Sonnet) würde die Kosten pro Lauf ungefähr verdoppeln – bei einem knapp bemessenen 5-€-Monatsbudget ein zu großer Eingriff, um ihn ohne Rückfrage zu treffen. Stattdessen: **ein zusätzlicher, günstiger Übersetzungsschritt mit Haiku** direkt nach der bereits validierten deutschen Fassung. Haiku übernimmt in dieser App bereits die "mechanischen" Aufgaben (Vorverarbeitung/Extraktion), Übersetzung passt strukturell in dieselbe Rolle – die teure inhaltliche Auswahl mit Sonnet läuft nur einmal.

# Umfang

Enthalten:
- Ein neues Modul `src/lagebericht/translate.py` mit einer Funktion, die einen bereits validierten deutschen Tages- oder Zeitraumbericht als Eingabe nimmt und einen strukturell identischen Bericht mit englischen Inhalten zurückgibt
- Aufruf dieses Schritts in `scripts/run_daily.py` und `scripts/run_period.py` direkt nach dem deutschen Publish, mit eigenem `Publisher`-Objekt auf einem gespiegelten Datenpfad `data/en/…`
- Übersetzungsfehler dürfen den deutschen Publish niemals verhindern oder rückgängig machen (gleiches Resilienz-Prinzip wie bei der Kostenerfassung)
- Frontend: Umschalter-Knopf neben dem Hell/Dunkel-Umschalter, der zwischen `data/` und `data/en/` als aktivem Datenpfad wechselt, persistiert in `localStorage`
- Übersetzung der **statischen Oberflächentexte**, die direkt in `index.html`/`assets/app.js` stehen (Buttons, Überschriften, Leerzustände, Aria-Label)

Nicht enthalten (bewusst zurückgestellt, siehe unten):
- Übersetzung der Texte, die aus `rating-model.js`, `freshness-model.js`, `period-model.js`, `cost-model.js` als bereits fertig formatierte deutsche Strings zurückkommen (z. B. "Datenbasis: 3 von 7 Tagen · Teilüberblick", "Deutschland-Bezug", Kosten-Hinweistext). Diese vier Dateien haben eigene, bereits gut getestete Rückgabeverträge (`tests/test_frontend_contract.py` prüft ihre exakten String-Ausgaben per Node-Subprozess). Sie auf sprachneutrale Rückgabewerte umzustellen und die Formatierung nach `app.js` zu verschieben ist ein eigener, nicht-trivialer Umbau – für heute Nacht bewusst ausgeklammert, um das Gesamtrisiko nicht zu sprengen. Ergebnis: In der englischen Ansicht bleiben diese wenigen dynamisch berechneten Mikrotexte vorerst deutsch. Das wird dem Nutzer nicht verschwiegen, sondern hier dokumentiert als klar umrissene Folgearbeit.
- Rückwirkende Übersetzung bereits bestehender deutscher Berichte (nur neue Läufe ab Umsetzung erzeugen eine englische Fassung)
- Eine eigene Kostenanzeige für die englische Fassung – die Kostenanzeige bleibt sprachunabhängig eine einzige, zeigt weiterhin die Gesamtkosten unabhängig von der gewählten Sprache

# Datenmodell

Bewusst **keine Schema-Änderung**. Die englische Fassung verwendet exakt dasselbe JSON-Schema wie die deutsche (`schemas/daily-report.schema.json`, `schemas/period-report.schema.json`) – Schema-Validierung prüft nur Struktur/Typen, nicht die tatsächliche Sprache des Inhalts. Das ist eine bewusste Vereinfachung: Feldnamen wie `headlineDe`, `summaryDe`, `reasonDe`, `contextDe` behalten ihr "De"-Suffix auch in der englischen Fassung – inhaltlich ungenau, aber folgenlos, weil kein Code und keine Person jemals den rohen Feldnamen zu Gesicht bekommt (das Frontend rendert nur die Werte). Eine Umbenennung hätte eine sechste und siebte Kopie der ohnehin schon fünffach redundanten Länder-Enums nach sich gezogen (siehe EU-Block-Spec) – nicht gerechtfertigt für eine rein kosmetische Korrektheit.

Ablage: `data/en/daily/YYYY-MM-DD.json`, `data/en/weekly/YYYY-Www.json`, `data/en/monthly/YYYY-MM.json`, `data/en/index.json` (eigener Indexbaum, erzeugt über `Publisher(data_root=Path("data/en"), ...)` – die bestehende `Publisher`-Klasse ist bereits generisch über `data_root` parametrisiert, keine Änderung an `publish.py` nötig).

# Welche Felder werden übersetzt

Der Übersetzungs-Prompt bekommt eine explizite Liste, was zu übersetzen ist und was **unverändert** übernommen werden muss:

**Übersetzen:** `headlineDe`, `summaryDe[]`, `additionalImportant`, `germanyRelevance.reasonDe`, `overallSignificance.reasonDe`, `contextDe[]` (falls vorhanden), `overallSummary[]` (Zeitraumberichte), `sources[].type` (z. B. "öffentlich-rechtlich" → "public broadcaster").

**Unverändert übernehmen:** alle Enum-Werte (`status`, `sourceBasis`, `limitations`, Kategorie-`id`, Land-`id`), alle Zahlen (`score`-Werte, `schemaVersion`), `sources[].name`, `sources[].url`, `sources[].titleOriginal` (das ist die tatsächliche Originalüberschrift der Quelle und darf nie verändert werden), `sources[].publishedAt`, `reportDate`/`generatedAt`/`periodStart`/`periodEnd`.

Die Wiederverwendung desselben Schemas als Struktur-Constraint für den Übersetzungsaufruf validiert diese Vorgabe größtenteils automatisch mit: Wenn Haiku versehentlich eine URL verändert oder ein Enum-Feld übersetzt, schlägt entweder die Schema-Validierung fehl (bei Enums) oder die URL-Prüfung beim Publish (bei domain-validierten Feldern) – Übersetzungsfehler werden also nicht blind durchgereicht.

# Frontend

- Neuer Umschalter-Knopf im Header, gleiche Bauweise wie der Hell/Dunkel-Umschalter (`localStorage`-Schlüssel `lagebericht-language`, Werte `de`/`en`)
- Bei `en`: alle `fetch()`-Aufrufe (Index, Tages-/Zeitraumbericht) verwenden `data/en/…` statt `data/…` als Pfadpräfix
- Statische Texte über eine kleine `STRINGS`-Tabelle in `assets/app.js` (Label je Sprache), angewendet auf: Segmented-Buttons ("Tage/Wochen/Monate"), Zeitraum-Label, "Land oder Region auswählen", "Gesamtlage"/"Der Zeitraum im Überblick", Berichtsart-Kicker ("Tagesbericht"/"Wochenbericht"/"Monatsbericht"), Vollständigkeits-Text ("Vollständig"/"Teilbericht"), Leer-/Fehlerzustände der einzelnen Meldungen, "Außerdem wichtig:", "Einordnung", Quellen-Zusammenfassung ("X Originalquelle(n) anzeigen"), Footer-Hinweistext, Cost-Meter-Überschriften ("Transparenz"/"Geschätzte API-Kosten")
- Fällt bei fehlendem `data/en/…` (z. B. für einen Tag vor Einführung des Umschalters) transparent auf den vorhandenen Hinweis-Mechanismus zurück ("Für diese Archivart ist noch kein Bericht vorhanden." – bereits vorhandene Logik in `loadSelectedReport`, keine Änderung nötig, weil englische Einträge dann einfach nicht in `data/en/index.json` auftauchen)

# Kosten

Ein zusätzlicher Haiku-Aufruf pro Tageslauf sowie je einer pro fälligem Wochen-/Monatsbericht. Haiku ist deutlich günstiger als Sonnet; realistisch < 20 % Aufschlag auf die bisherigen Gesamtkosten, nicht ~100 % wie bei einer zweiten Vollgenerierung. Wird über den bereits vorhandenen `CostRecorder` automatisch mit erfasst (gleicher Mechanismus, gleiche Kostenanzeige).

# Tests

Neues `tests/test_translate.py`: Übersetzungsfunktion mit simulierter Antwort, prüft dass Enum-/URL-/Zahlenfelder unverändert bleiben und Text-Felder ersetzt werden, prüft dass eine fehlschlagende Übersetzung eine eigene, abfangbare Ausnahme wirft statt den Aufrufer abstürzen zu lassen. Anpassung `tests/test_workflow_contract.py`/Integrationstest, dass ein Übersetzungsfehler den Rückgabewert von `run_daily.main()` nicht auf einen Fehlercode setzt, solange der deutsche Publish erfolgreich war.
