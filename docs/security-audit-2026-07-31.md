# Sicherheits- und Datenschutzprüfung – 31.07.2026

## Gesamtampel: 🟡 Gelb

Die lokal gebaute App hat keine kritischen oder hohen Befunde. Gelb bleibt bis zum ersten echten GitHub-Pages-Deployment und einem kontrollierten Live-Lauf stehen, weil ausgelieferte HTTP-Header, Repository-Einstellungen und das Verhalten der externen Nachrichtenquellen erst dann vollständig prüfbar sind.

| Bereich | Ampel | Kurzbegründung |
|---|---|---|
| Sicherheit | 🟢 Grün | Keine Zugangsdaten im Repository, keine dynamische HTML-Injektion, keine Fremdskripte; Quellenabrufe sind allowlist-basiert, zeitlich und mengenmäßig begrenzt. |
| DSGVO/Datenschutz | 🟢 Grün | Keine Konten, Formulare, Tracker, Cookies, personenbezogenen Profile oder Browser-Speicherung; die App zeigt nur öffentliche Nachrichteninhalte. |
| Best Practice | 🟡 Gelb | Live-Header und GitHub-Berechtigungen sind vor dem Deployment nicht abschließend verifizierbar; zwei HTML-Quellen sind bewusst noch deaktiviert. |

## Geprüfte Schutzmaßnahmen

- Der OpenAI-Schlüssel wird ausschließlich als GitHub-Actions-Secret erwartet und nie an den Browser ausgeliefert.
- Die statische Oberfläche verwendet keine externen JavaScript-, CSS-, Schrift- oder Analyse-Dienste.
- Die Content Security Policy in `index.html:9` sperrt Fremdinhalte, Plugins, Formulare und fremde Verbindungen.
- Es gibt keine Verwendung von `innerHTML`, `document.write`, `eval`, Local Storage oder Session Storage.
- Externe Artikel-URLs werden gegen die konfigurierte Domain-Allowlist geprüft. Abrufe haben Zeit-, Größen- und Weiterleitungsgrenzen.
- Modellantworten werden gegen feste Schemas validiert; ungültige Ergebnisse werden nicht veröffentlicht.
- GitHub Actions sind auf vollständige Commit-SHAs festgelegt. Schreibrecht ist nur im Veröffentlichungsworkflow vorhanden.
- Der bisherige Git-Verlauf und die Arbeitskopie wurden auf typische Secret-Muster kontrolliert; es wurde kein Secret gefunden.

## Offene gelbe Punkte

### 1. Sicherheitsheader erst live messbar

**Stelle:** `index.html:9`

**Problem:** Die CSP ist als HTML-Meta-Tag gesetzt. Zusätzliche Antwortheader wie `X-Content-Type-Options`, `Permissions-Policy` und eine serverseitige `frame-ancestors`-Regel lassen sich bei GitHub Pages erst an der veröffentlichten Adresse kontrollieren.

**Behebung:** Nach dem ersten Deployment die ausgelieferten Header prüfen. Falls strengere, frei konfigurierbare Header benötigt werden, einen vorgeschalteten Dienst oder ein Hosting mit eigener Header-Konfiguration verwenden.

### 2. GitHub-Rechte und Secret erst im Ziel-Repository prüfbar

**Stelle:** `.github/workflows/daily-report.yml:16` und `.github/workflows/daily-report.yml:39`

**Problem:** Der Workflow braucht `contents: write`, um neue Berichte zu speichern. Ob Branch-Schutz, Actions-Berechtigungen und das Secret im künftigen Repository korrekt eingerichtet sind, ist lokal nicht feststellbar.

**Behebung:** Beim Go-live nur das Secret `OPENAI_API_KEY` anlegen, Actions auf erlaubte Workflows begrenzen und den ersten Lauf beaufsichtigen. Optional kann später Erzeugung und Veröffentlichung in getrennte Jobs mit engeren Rechten aufgeteilt werden.

### 3. Zwei China-Quellen noch ohne robusten HTML-Adapter

**Stelle:** `config/sources.json:43`, `config/sources.json:50` und `src/lagebericht/pipeline.py:68`

**Problem:** Caixin und China Daily sind als Perspektiven erfasst, werden im laufenden Abruf aber kontrolliert übersprungen. Das ist kein Sicherheitsleck, kann jedoch die Quellenvielfalt des China-Berichts verringern.

**Behebung:** Nach einem Live-Quellentest robuste, eng begrenzte Adapter ergänzen oder stabile offizielle Feeds hinterlegen. Bis dahin bleibt SCMP die aktive China-Quelle; fehlende Quellen werden transparent als Einschränkung ausgewiesen.

## Ergebnis

Ein lokaler Betrieb und ein kontrollierter Testlauf sind vertretbar. Vor einer öffentlichen Freigabe bleiben der Live-Header-Test, die Kontrolle der GitHub-Einstellungen und ein beaufsichtigter erster Nachrichtenabruf Pflicht.
