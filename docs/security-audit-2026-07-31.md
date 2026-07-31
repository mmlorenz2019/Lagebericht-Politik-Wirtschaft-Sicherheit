# Sicherheits- und Datenschutzprüfung – 31.07.2026

## Gesamtampel: 🟡 Gelb

Die veröffentlichte App hat keine kritischen oder hohen Befunde. Der Live-Test bestätigt HTTPS mit HSTS, korrekte Inhaltstypen, funktionierendes Manifest und Service Worker sowie eine Browser-Konsole ohne Fehler oder Warnungen. Gelb bleibt bestehen, weil GitHub Pages keine frei konfigurierbaren zusätzlichen Antwortheader ausliefert und der produktive KI-Lauf erst nach Einrichtung des API-Secrets geprüft werden kann.

| Bereich | Ampel | Kurzbegründung |
|---|---|---|
| Sicherheit | 🟢 Grün | Keine Zugangsdaten im Repository, keine dynamische HTML-Injektion, keine Fremdskripte; Quellenabrufe sind allowlist-basiert, zeitlich und mengenmäßig begrenzt. |
| DSGVO/Datenschutz | 🟢 Grün | Keine Konten, Formulare, Tracker, Cookies, personenbezogenen Profile oder Browser-Speicherung; die App zeigt nur öffentliche Nachrichteninhalte. |
| Best Practice | 🟡 Gelb | HTTPS/HSTS und GitHub-Workflows sind live geprüft; zusätzliche Hosting-Header fehlen und zwei HTML-Quellen sind bewusst noch deaktiviert. |

## Geprüfte Schutzmaßnahmen

- Der Anthropic-Schlüssel wird ausschließlich als GitHub-Actions-Secret erwartet und nie an den Browser ausgeliefert.
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

**Problem:** Der Live-Test bestätigt HTTPS und `Strict-Transport-Security`. Die CSP ist als HTML-Meta-Tag gesetzt; GitHub Pages liefert jedoch keine zusätzlichen Antwortheader wie `X-Content-Type-Options`, `Permissions-Policy` oder eine serverseitige `frame-ancestors`-Regel aus.

**Behebung:** Für die aktuelle unpersönliche, rein statische App ist die Meta-CSP ein vertretbarer Schutz. Falls später Nutzereingaben oder sensible Daten hinzukommen, einen vorgeschalteten Dienst oder ein Hosting mit eigener Header-Konfiguration verwenden.

### 2. GitHub-Rechte und Secret erst im Ziel-Repository prüfbar

**Stelle:** `.github/workflows/daily-report.yml:16` und `.github/workflows/daily-report.yml:39`

**Problem:** Pages-Deployment und Tests wurden im öffentlichen Repository erfolgreich ausgeführt. Der Tagesworkflow braucht `contents: write`, um neue Berichte zu speichern; das persönliche Anthropic-Secret ist noch nicht eingerichtet und der produktive Lauf daher noch nicht geprüft.

**Behebung:** Beim Go-live nur das Secret `ANTHROPIC_API_KEY` anlegen, Actions auf erlaubte Workflows begrenzen und den ersten Lauf beaufsichtigen. Optional kann später Erzeugung und Veröffentlichung in getrennte Jobs mit engeren Rechten aufgeteilt werden.

### 3. Zwei China-Quellen noch ohne robusten HTML-Adapter

**Stelle:** `config/sources.json:43`, `config/sources.json:50` und `src/lagebericht/pipeline.py:68`

**Problem:** Caixin und China Daily sind als Perspektiven erfasst, werden im laufenden Abruf aber kontrolliert übersprungen. Das ist kein Sicherheitsleck, kann jedoch die Quellenvielfalt des China-Berichts verringern.

**Behebung:** Nach einem Live-Quellentest robuste, eng begrenzte Adapter ergänzen oder stabile offizielle Feeds hinterlegen. Bis dahin bleibt SCMP die aktive China-Quelle; fehlende Quellen werden transparent als Einschränkung ausgewiesen.

## Ergebnis

Die öffentlich bereitgestellte statische App ist vertretbar. Vor der Aktivierung automatisch erzeugter Echtberichte bleiben das Kostenlimit, die Einrichtung des GitHub-Secrets und ein beaufsichtigter erster Nachrichtenabruf Pflicht.
