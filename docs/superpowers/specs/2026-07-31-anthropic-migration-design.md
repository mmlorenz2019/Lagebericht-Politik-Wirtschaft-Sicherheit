# Migration auf die Claude-API – Designspezifikation

**Datum:** 31.07.2026  
**Status:** Zur schriftlichen Freigabe

## Ziel

Der persönliche Lagebericht soll künftig das bereits vorhandene Anthropic-Guthaben nutzen. Die produktive Abhängigkeit von der OpenAI-API wird vollständig entfernt. Darstellung, Quellenlogik, Datenformate, Tagesberichte sowie Wochen- und Monatszusammenfassungen bleiben fachlich unverändert.

## Entscheidung und Umfang

- Die Anwendung spricht die Anthropic Messages API direkt an.
- Es wird kein Mehranbieter-Modus und kein Umschalter zwischen OpenAI und Anthropic gebaut. Das hält Konfiguration, Tests und Fehlerbilder übersichtlich.
- Frontend, Quellensammlung, bestehende JSON-Schemata, Archiv sowie Wochen- und Monatsansichten bleiben bestehen.
- Der API-Schlüssel liegt ausschließlich als GitHub-Actions-Secret `ANTHROPIC_API_KEY` vor. Er wird weder in Git eingecheckt noch im Browser ausgeliefert.

## Modelle und Aufgabenverteilung

- `claude-haiku-4-5-20251001` übernimmt Extraktion und Vorauswahl der Meldungen.
- `claude-sonnet-4-6` übernimmt endgültige Auswahl, Einordnung und verständliche Zusammenfassungen.
- Die Modellnamen werden über `ANTHROPIC_EXTRACTION_MODEL` und `ANTHROPIC_SUMMARY_MODEL` konfigurierbar gemacht.
- Standardmäßig werden feste Modell-IDs verwendet, damit ein später veränderter Alias nicht unbemerkt Verhalten oder Kosten verändert.

## Technische Architektur

Ein neuer `AnthropicMessagesClient` ersetzt den bisherigen `OpenAIResponsesClient`. Die interne Schnittstelle `generate_json(...)` bleibt erhalten, damit Pipeline und Aggregation nur geringfügig angepasst werden müssen.

Der Client sendet `POST`-Anfragen an `https://api.anthropic.com/v1/messages` mit:

- `x-api-key: <ANTHROPIC_API_KEY>`
- `anthropic-version: 2023-06-01`
- `content-type: application/json`

Die festen Systemregeln werden als System-Prompt übertragen. Artikeltexte und andere externe Inhalte bleiben klar als nicht vertrauenswürdige Nutzdaten getrennt. Der Client aktiviert keine Tools, Websuche oder sonstigen Aktionen.

Für strukturierte Antworten wird das bestehende JSON-Schema über `output_config.format` an Claude übergeben. Zeitlimits sowie Eingabe- und Ausgabegrenzen bleiben gesetzt. Akzeptiert wird nur eine regulär abgeschlossene Textantwort. Antworten mit `max_tokens`, einer Ablehnung, fehlendem Textblock oder ungültigem JSON gelten als Fehler. Anschließend greifen weiterhin die lokale Schema- und Fachvalidierung.

## Datenfluss

1. Die bestehende Quellensammlung erzeugt Kandidaten für USA, China und Montenegro.
2. Haiku extrahiert und bewertet die Kandidaten vor.
3. Sonnet wählt die Hauptthemen und erstellt die gegliederten Zusammenfassungen.
4. Lokale Prüfungen validieren Schema, Länder, Kategorien, Quellen und Textgrenzen.
5. Nur vollständig gültige Ergebnisse werden veröffentlicht.

Wochen- und Monatsberichte verwenden Sonnet und basieren ausschließlich auf bereits validierten Tagesberichten. Sie starten keine zusätzliche offene Websuche.

## Fehlerbehandlung und sichere Veröffentlichung

- Ein fehlender API-Schlüssel stoppt den Lauf vor dem ersten Netzwerkzugriff.
- HTTP-Fehler und Zeitüberschreitungen führen zu einem fehlgeschlagenen Lauf; es wird kein unvollständiger Bericht veröffentlicht.
- Ablehnung, `max_tokens`, fehlender Antworttext und ungültiges JSON werden ausdrücklich erkannt.
- Schema- oder Fachfehler verhindern ebenfalls die Veröffentlichung.
- Ein Fehler bei einem Wochen- oder Monatsbericht beschädigt keine vorhandenen Tagesberichte.
- Fehlermeldungen dürfen niemals API-Schlüssel oder vollständige sensible Request-Header ausgeben.

## GitHub-Actions-Konfiguration

Der Workflow erhält nur noch:

- Secret `ANTHROPIC_API_KEY`
- Variable beziehungsweise Standardwert `ANTHROPIC_EXTRACTION_MODEL`
- Variable beziehungsweise Standardwert `ANTHROPIC_SUMMARY_MODEL`

Aktive Verweise auf `OPENAI_API_KEY` und OpenAI-Modellvariablen werden aus Workflow, Laufzeitcode, Tests, README und Sicherheitsdokumentation entfernt oder auf Anthropic umgestellt. Historische Planungsunterlagen dürfen zur Nachvollziehbarkeit erhalten bleiben, erhalten bei Bedarf aber einen Hinweis auf die spätere Migration.

Michael erstellt den Anthropic-Schlüssel selbst und fügt ihn direkt unter **GitHub → Settings → Secrets and variables → Actions** ein. Der Schlüssel wird nicht im Chat geteilt.

## Tests und Abnahme

Die Umstellung wird testgetrieben umgesetzt. Geprüft werden mindestens:

- korrekte URL, Header und Anthropic-Payloads;
- Übertragung des JSON-Schemas ohne lokale Hilfsfelder;
- erfolgreiche strukturierte Antwort;
- fehlender Schlüssel, HTTP-Fehler und Zeitüberschreitung;
- Ablehnung, `max_tokens`, fehlender Text und ungültiges JSON;
- CLI- und Workflow-Konfiguration ausschließlich mit Anthropic;
- richtige Modellrollen in Tages-, Wochen- und Monats-Pipeline;
- vollständige bestehende Testsuite;
- Secret-Scan des Repositorys;
- ein manuell gestarteter GitHub-Actions-Lauf mit anschließendem Sichttest der veröffentlichten Seite.

## Kostenkontrolle

Die Migration nutzt zunächst das vorhandene Anthropic-Guthaben. Der erste vollständige Tageslauf dient als reale Kostenmessung. Kandidatenzahl, Textlänge und Ausgabelimits bleiben begrenzt; eine offene KI-Websuche wird nicht ergänzt. Dadurch bleiben die wiederkehrenden Kosten nachvollziehbar und steuerbar.

## Erfolgskriterien

Die Migration ist abgeschlossen, wenn:

1. alle automatisierten Tests erfolgreich sind;
2. keine aktive OpenAI-Konfiguration mehr vorhanden ist;
3. GitHub Actions ausschließlich `ANTHROPIC_API_KEY` benötigt;
4. ein manueller Lauf einen fachlich und technisch gültigen Bericht erzeugt;
5. der Schlüssel weder im Repository noch im Browser oder in Protokollen sichtbar ist.
