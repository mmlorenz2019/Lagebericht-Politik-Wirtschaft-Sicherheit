# Persönlicher Lagebericht

Installierbare, statische PWA für einen täglichen Überblick über USA, China und Montenegro. Die Seite enthält keine Anmeldung, keine Analytics und keine Secrets. Eine getrennte GitHub Action ruft fest konfigurierte Quellen ab, erzeugt validierte Tagesberichte und verdichtet sie sonntags beziehungsweise am Monatsende.

## Lokaler Test

Voraussetzung ist Python 3.12 oder neuer. Zusätzliche Python-Pakete sind nicht erforderlich.

```powershell
$env:PYTHONPATH='src'
python -m unittest discover -s tests -v
python -m http.server 8000
```

Danach `http://localhost:8000` öffnen. Die mitgelieferten Berichte sind klar gekennzeichnete Beispieldaten.

## Lokaler KI-Testlauf

Vor dem ersten echten Lauf im OpenAI-Projekt ein monatliches Kostenlimit setzen. Der Schlüssel darf nur als Umgebungsvariable verwendet werden:

```powershell
$env:OPENAI_API_KEY='...'
$env:PYTHONPATH='src'
python scripts/run_daily.py --date 2026-07-31 --dry-run
```

Standardmodelle sind `gpt-5.6-luna` für Extraktion und `gpt-5.6-terra` für Auswahl, Formulierung und Rückblicke. Sie können über `OPENAI_EXTRACTION_MODEL` und `OPENAI_SUMMARY_MODEL` überschrieben werden. Die Responses API wird mit strukturierten JSON-Ausgaben, `store: false` und ohne Werkzeuge aufgerufen.

## GitHub-Einrichtung

1. Leeres Repository anlegen und dieses lokale Repository dorthin pushen.
2. Im OpenAI-Projekt ein Ausgabenlimit setzen und einen eigenen Schlüssel nur für diese App erzeugen.
3. Unter **Settings → Secrets and variables → Actions** das Secret `OPENAI_API_KEY` hinterlegen.
4. Unter **Settings → Pages** die Veröffentlichung aus dem Standardbranch und dem Stammverzeichnis aktivieren.
5. Den Workflow **Täglicher Lagebericht** einmal manuell starten und die erzeugten Daten prüfen.

Der Zeitplan startet um 04:30 und 05:30 UTC. Eine zusätzliche Prüfung der Zeitzone `Europe/Berlin` sorgt dafür, dass ganzjährig nur der Lauf um 06:30 Uhr Ortszeit arbeitet.

## PWA-Installation

In Edge oder Chrome die GitHub-Pages-Seite öffnen und **App installieren** beziehungsweise **Zum Startbildschirm hinzufügen** auswählen. Der zuletzt geöffnete Bericht bleibt offline lesbar; Originalquellen benötigen eine Internetverbindung.

## Daten und Grenzen

- `data/daily/` enthält Tagesberichte.
- `data/weekly/` enthält Wochenberichte von Montag bis Sonntag.
- `data/monthly/` enthält Monatsberichte.
- `data/index.json` bildet das sichtbare Archiv.
- Artikelvolltexte werden nicht gespeichert.
- HTML-Quellenadapter für Caixin und China Daily sind vorbereitet, aber deaktiviert, bis robuste Parser mit echten Abrufproben vorliegen. Die Pipeline erfindet bei fehlenden Quellen keine Ersatzmeldungen.

Siehe [SECURITY.md](SECURITY.md) für Sicherheitsgrenzen und Meldung von Problemen.

