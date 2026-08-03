# Persönlicher Lagebericht

Installierbare, statische PWA für einen täglichen Überblick über USA, China und Montenegro. Die Seite enthält keine Anmeldung, keine Analytics und keine Secrets. Eine getrennte GitHub Action ruft fest konfigurierte Quellen ab, erzeugt validierte Tagesberichte und verdichtet abgeschlossene Wochen und Monate.

**Web-App:** https://mmlorenz2019.github.io/Lagebericht-Politik-Wirtschaft-Sicherheit/

## Lokaler Test

Voraussetzung ist Python 3.12 oder neuer. Zusätzliche Python-Pakete sind nicht erforderlich.

```powershell
$env:PYTHONPATH='src'
python -m unittest discover -s tests -v
python -m http.server 8000
```

Danach `http://localhost:8000` öffnen. Die mitgelieferten Berichte sind klar gekennzeichnete Beispieldaten.

## Lokaler KI-Testlauf

Vor dem ersten echten Lauf in der Anthropic Console ein monatliches Kostenlimit setzen. Der Schlüssel darf nur als Umgebungsvariable verwendet werden:

```powershell
$env:ANTHROPIC_API_KEY='...'
$env:PYTHONPATH='src'
python scripts/run_daily.py --date 2026-07-31 --dry-run
```

Standardmodelle sind `claude-haiku-4-5-20251001` für Extraktion und `claude-sonnet-4-6` für Auswahl, Formulierung und Rückblicke. Sie können über `ANTHROPIC_EXTRACTION_MODEL` und `ANTHROPIC_SUMMARY_MODEL` überschrieben werden. Die Anthropic Messages API wird direkt mit strukturierten JSON-Ausgaben über `output_config.format` und ohne Werkzeuge aufgerufen. Modellantworten werden zusätzlich lokal gegen die vollständigen Berichtsregeln geprüft.

## GitHub-Einrichtung

1. Leeres Repository anlegen und dieses lokale Repository dorthin pushen.
2. In der Anthropic Console ein Ausgabenlimit setzen und einen eigenen Projektschlüssel nur für diese App erzeugen.
3. Unter **Settings → Secrets and variables → Actions** ausschließlich das Secret `ANTHROPIC_API_KEY` hinterlegen. Den Schlüssel niemals in den Chat oder in Repository-Dateien kopieren.
4. Unter **Settings → Pages** die Veröffentlichung aus dem Standardbranch und dem Stammverzeichnis aktivieren.
5. Den Workflow **Täglicher Lagebericht** einmal manuell starten und die erzeugten Daten prüfen.

Der Zeitplan arbeitet ausdrücklich in `Europe/Berlin` und berücksichtigt Sommer- und Winterzeit automatisch. Er startet um 05:47 Uhr sowie ersatzweise um 07:17, 09:37 und 11:53 Uhr. Die bewusst verteilten Minuten verringern das Risiko, dass GitHub geplante Läufe bei hoher Auslastung verwirft. Vor jedem automatischen Claude-Aufruf wird geprüft, ob der Tagesbericht bereits vorhanden ist; dadurch verursacht höchstens einer dieser Läufe Kosten. Fällige Wochen- und Monatsberichte werden unabhängig geprüft und können von einem Ersatzlauf nachgeholt werden. Eine manuelle Workflow-Ausführung bleibt eine bewusste Neuausführung.

## Wochen- und Monatsberichte

Der Wochenbericht wird montags für die vollständig abgeschlossene Kalenderwoche von Montag bis Sonntag erzeugt. Der Monatsbericht wird am ersten Tag des Folgemonats für den abgeschlossenen Kalendermonat erzeugt. Bereits ein gültiger Tagesbericht genügt für einen Teilbericht; ohne gültigen Tagesbericht wird Claude für den Rückblick nicht aufgerufen.

Die App zeigt die Datenbasis direkt am Bericht, beispielsweise **Datenbasis: 3 von 7 Tagen · Teilüberblick**. Beruht ein Rückblick nur auf einem Tag, heißt er ausdrücklich **Momentaufnahme** und wird nicht als Trend formuliert. Wochenberichte enthalten 8 bis 10 Sätze zur Gesamtlage, Monatsberichte 12 bis 15. Jede veröffentlichte Entwicklung enthält zusätzlich eine sichtbare **Einordnung** mit Hintergrund und möglicher Bedeutung.

Fehlt ein fälliger Rückblick, versuchen die Ersatzläufe um 07:17, 09:37 und 11:53 Uhr ihn erneut zu erzeugen. Ein gültiger Tagesbericht wird trotzdem versioniert und veröffentlicht; der fehlende Rückblick bleibt im Workflow als Fehler sichtbar. Auch ein fehlgeschlagener oder wiederholter API-Aufruf kann bereits Tokenkosten verursacht haben. Deshalb wird ein vorhandener, vollständiger oder transparenter Teilbericht vor jedem Ersatzlauf erkannt und nicht erneut erzeugt.

## PWA-Installation

In Edge oder Chrome die GitHub-Pages-Seite öffnen und **App installieren** beziehungsweise **Zum Startbildschirm hinzufügen** auswählen. Der zuletzt geöffnete Bericht bleibt offline lesbar; Originalquellen benötigen eine Internetverbindung. Fehlt der Bericht für den aktuellen Berliner Kalendertag, weist die App sichtbar auf den älteren Stand hin. Beim erneuten Öffnen oder Zurückkehren in die App wird das Archiv ohne Browser-Cache neu geprüft.

## Daten und Grenzen

- `data/daily/` enthält Tagesberichte.
- `data/weekly/` enthält Wochenberichte von Montag bis Sonntag.
- `data/monthly/` enthält Monatsberichte.
- `data/index.json` bildet das sichtbare Archiv.
- Artikelvolltexte werden nicht gespeichert.
- Alle sieben aktiven RSS/XML-Feeds wurden am 31.07.2026 live mit der sicheren Pipeline geprüft. Das Ergebnis steht unter `docs/source-smoke-test-2026-07-31.md`.
- Die aktuellen HTTPS-Seiten von Caixin und China Daily sind erreichbar. Ihre HTML-Quellenadapter bleiben deaktiviert, bis robuste Parser mit echten Abrufproben vorliegen; die offiziellen China-Daily-RSS-Adressen lieferten beim Test veraltete HTTP-Artikel. Die Pipeline erfindet bei fehlenden Quellen keine Ersatzmeldungen.

## Transparente Bedeutungsbewertung

Neue Berichte zeigen für jede veröffentlichte Meldung zwei getrennte Einschätzungen von 0 bis 3: **Deutschland-Bezug** und **allgemeine Tragweite**. Grau steht für 0, Grün für 1, Gelb für 2 und Rot für 3. Die Farbe beschreibt nur die Stärke der möglichen Bedeutung, nicht ob eine Entwicklung positiv oder negativ ist. Jede Zahl besitzt eine aufklappbare Begründung.

Eine niedrige Bewertung ist kein Grund, eine Meldung auszublenden. Auch eine Meldung aus nur einer seriösen Quelle darf erscheinen und wird dann sichtbar als **Nur eine Quelle** gekennzeichnet. `no_major_development` bedeutet ausschließlich, dass in den geprüften Quellen keine technisch geeignete neue Meldung für die Kategorie gefunden wurde; technische Ausfälle werden getrennt als `unavailable` ausgewiesen.

Vorhandene Berichte der Datenversion 1 bleiben lesbar, erhalten aber keine nachträglich erfundenen Punktwerte. Die erste Version speichert keine persönlichen Korrekturen und lernt nicht automatisch. Nach sieben Tagesläufen werden die angezeigten Bewertungen mit der persönlichen Einschätzung des Nutzers verglichen und die Regeln bei Bedarf bewusst angepasst.

Siehe [SECURITY.md](SECURITY.md) für Sicherheitsgrenzen und Meldung von Problemen.
