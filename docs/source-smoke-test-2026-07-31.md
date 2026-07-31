# Live-Quellentest – 31.07.2026

Die konfigurierten Quellen wurden mit derselben sicheren Abruf- und Normalisierungslogik getestet, die später im Tageslauf verwendet wird. Dabei wurden keine Artikelvolltexte gespeichert.

| Quelle | Ergebnis | Erkannte Kandidaten | Hinweis |
|---|---:|---:|---|
| NPR | 🟢 | 10 | RSS/XML erfolgreich |
| New York Times | 🟢 | 12 | RSS/XML erfolgreich |
| CNBC | 🟢 | 15 | RSS/XML erfolgreich |
| PBS NewsHour | 🟢 | 10 | RSS/XML erfolgreich |
| South China Morning Post | 🟢 | 18 | Kanonische HTTPS-Adresse mit abschließendem `/` erfolgreich |
| Vijesti | 🟢 | 18 | RSS/XML erfolgreich |
| Pobjeda | 🟢 | 18 | RSS/XML erfolgreich |
| Caixin Global | 🟡 | – | Aktuelle HTTPS-Seite erreichbar; kein stabiler offizieller RSS-Feed gefunden, HTML-Adapter bleibt deaktiviert |
| China Daily | 🟡 | – | Aktuelle HTTPS-Seite erreichbar; offizielle RSS-Adressen liefern veraltete HTTP-Artikel, HTML-Adapter bleibt deaktiviert |

## Korrektur aus dem Test

Die bisherige SCMP-Adresse ohne abschließenden Schrägstrich leitete auf `http` um und wurde von der Schutzlogik zu Recht blockiert. Die Konfiguration verwendet nun direkt `https://www.scmp.com/rss/4/feed/`. Ein Regressionstest sichert diese kanonische Adresse ab.

## Ergebnis

Alle sieben für den ersten Live-Betrieb aktivierten Feeds funktionieren. USA und Montenegro haben jeweils mehrere aktive Quellen; China besitzt mit SCMP zunächst eine aktive regionale Quelle. Caixin und China Daily werden erst nach einem eigenen, getesteten HTML-Adapter aktiviert. Fehlende Perspektiven muss der Bericht bis dahin transparent als Einschränkung kennzeichnen.
