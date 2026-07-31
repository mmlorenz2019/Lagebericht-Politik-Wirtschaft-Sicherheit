# Sicherheit

## Unterstützte Version

Bis zum öffentlichen Go-live gilt ausschließlich der aktuelle Stand des Standardbranches als unterstützt.

## Schutzmaßnahmen

- Der Anthropic-Schlüssel existiert nur als GitHub Actions Secret.
- Das Frontend führt keine KI-Aufrufe aus und enthält keine persönlichen Daten.
- Quellen und Weiterleitungen sind auf feste HTTPS-Domains beschränkt.
- Abrufe besitzen Größen-, Zeit- und Redirect-Limits und blockieren private Netzwerkziele.
- Artikeltexte gelten als nicht vertrauenswürdige Daten und werden von Promptregeln getrennt.
- Modellantworten müssen einen festen Datenvertrag erfüllen, bevor sie atomar veröffentlicht werden.
- Dynamische Nachrichtentexte werden mit sicheren DOM-APIs statt `innerHTML` dargestellt.
- Fremde Quell-Links werden im Browser erneut gegen eine feste Hostliste geprüft.
- GitHub Actions sind auf vollständige Commit-SHAs festgelegt.

## Secrets und Logs

Niemals API-Schlüssel in Dateien, Issues, Screenshots, Workflow-Ausgaben oder Beispieldaten einfügen. Bei einem vermuteten Schlüsselabfluss den Schlüssel sofort in der Anthropic Console sperren und durch einen neuen projektbezogenen Schlüssel ersetzen.

## Sicherheitsprobleme

Vor einem öffentlichen Repository eine private GitHub-Sicherheitsmeldung aktivieren. Bis dahin Probleme nicht öffentlich dokumentieren, sondern lokal festhalten und vor dem Push beheben.
