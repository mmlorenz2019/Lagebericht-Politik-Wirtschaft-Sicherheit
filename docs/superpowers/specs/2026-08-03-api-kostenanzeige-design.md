---
title: Öffentliche API-Kostenanzeige
date: 2026-08-03
status: zur Prüfung
---

# Ziel

Die App zeigt öffentlich und dezent, wie viel des monatlichen Claude-Budgets voraussichtlich verbraucht wurde. Eine kleine Transparenz-Karte visualisiert den aktuellen Monat als Balken von 0 bis 100 Prozent. Das Monatsbudget beträgt zunächst 5 Euro.

Die Anzeige ist eine nachvollziehbare Schätzung aus den von Anthropic gemeldeten Tokenzahlen. Sie ist keine Rechnung und wird deshalb ausdrücklich als „Geschätzte API-Kosten“ bezeichnet.

# Freigegebene Darstellung

Verwendet wird die ausgewählte Variante B, eine kleine Transparenz-Karte am unteren Rand der App im Umfeld von Quellen- und Transparenzhinweisen.

Die Karte enthält:

- den aktuellen Monat,
- einen gut erkennbaren Prozentwert,
- einen segmentierten Fortschrittsbalken,
- Markierungen bei 0, 25, 50, 75 und 100 Prozent,
- die zugehörigen Budgetwerte 0, 1,25, 2,50, 3,75 und 5 Euro,
- einen kurzen Hinweis, dass es sich um eine Schätzung handelt.

Die gefüllte Breite berechnet sich als `geschätzte Monatskosten / 5 Euro × 100`. Bei 0,84 Euro ergibt sich beispielsweise ein Stand von 16,8 Prozent. Bis 75 Prozent bleibt der Balken grün, ab 75 Prozent wird er bernsteinfarben und ab 100 Prozent rot. Der sichtbare Balken endet bei 100 Prozent; der numerische Prozentwert darf bei einer Budgetüberschreitung über 100 Prozent steigen.

Die Karte zeigt zunächst ausschließlich den aktuellen Kalendermonat in der Zeitzone `Europe/Berlin`. Vergangene Monatsdateien bleiben gespeichert, erhalten in dieser Ausbaustufe aber noch keine Auswahloberfläche.

# Erfassungsprinzip

Der vorhandene Anthropic-Client liest bereits vollständige API-Antworten. Künftig übergibt er die darin enthaltenen Nutzungsdaten zusätzlich an einen eigenständigen Kostenrekorder. Berichtsinhalte, Prompts, API-Schlüssel und vollständige Provider-Antworten werden nicht in der öffentlichen Kostendatei gespeichert.

Erfasst werden pro Claude-Aufruf:

- UTC-Zeitpunkt,
- Berliner Abrechnungsmonat,
- Berichtstyp `daily`, `week` oder `month`,
- betroffener Berichtstag beziehungsweise Zeitraum,
- Modellkennung,
- Ergebnisstatus,
- Eingabe- und Ausgabetoken,
- vorhandene Cache-Erstellungs- und Cache-Lesetoken,
- verwendete Preisversion,
- geschätzte Kosten in US-Dollar und Euro.

Antworten, die erst nach dem Verbrauch von Tokens wegen eines Tokenlimits, einer Ablehnung oder einer lokalen Inhaltsvalidierung scheitern, werden mit ihrem gemeldeten Verbrauch mitgerechnet. Bei einem vollständigen Netzwerk- oder Lesetimeout liegt dagegen möglicherweise keine Anthropic-Antwort und damit keine verlässliche Tokenzahl vor. Ein solcher Aufruf wird als `unmeasuredCall` gezählt, erhält aber keinen erfundenen Kostenbetrag. Die Oberfläche weist deshalb auf eine Mindestschätzung hin, sobald im Monat nicht messbare Aufrufe vorkamen.

# Preise und Währungsumrechnung

Die Modellpreise liegen versioniert in einer nicht geheimen Konfigurationsdatei. Für die derzeit eingesetzten Modelle gelten laut [offizieller Anthropic-Preisseite](https://platform.claude.com/docs/en/about-claude/pricing) zum Entwurfszeitpunkt:

- Claude Haiku 4.5: 1 US-Dollar pro Million Eingabetoken und 5 US-Dollar pro Million Ausgabetoken,
- Claude Sonnet 4.6: 3 US-Dollar pro Million Eingabetoken und 15 US-Dollar pro Million Ausgabetoken.

Cache-Token werden nur berechnet, wenn Anthropic sie tatsächlich meldet. Preisänderungen verändern bereits gespeicherte Ereignisse nicht: Jedes Ereignis behält Preisversion und berechneten Betrag.

Da Anthropic in US-Dollar abrechnet, enthält die Preisdatei zusätzlich einen dokumentierten, manuell aktualisierbaren USD-EUR-Umrechnungskurs mit Stichtag. Eine externe Wechselkurs-API wird zunächst nicht eingebunden. Dadurch bleibt der tägliche Lauf unabhängig von einem zusätzlichen Dienst. Die Oberfläche bezeichnet den Eurobetrag weiterhin als Schätzung.

# Öffentliche Datenstruktur

Für jeden Monat entsteht eine Datei `data/costs/YYYY-MM.json`. Sie enthält eine kompakte öffentliche Zusammenfassung und die einzelnen Nutzungsereignisse. Ein schematisches Beispiel:

```json
{
  "schemaVersion": 1,
  "month": "2026-08",
  "timezone": "Europe/Berlin",
  "budgetEur": 5.0,
  "estimatedCostEur": 0.84,
  "budgetPercent": 16.8,
  "unmeasuredCalls": 0,
  "rate": {"usdToEur": 0.92, "effectiveDate": "2026-08-03"},
  "events": []
}
```

Die konkrete Ereignisstruktur erhält eine eigene JSON-Schema-Prüfung. Beträge werden intern mit ausreichender Genauigkeit berechnet und erst für die Anzeige auf Cent beziehungsweise eine Nachkommastelle beim Prozentwert gerundet.

Der öffentliche `data/index.json` verweist auf die aktuelle Kostendatei. Fehlt diese Datei oder ist sie ungültig, bleibt die App benutzbar und zeigt statt eines falschen Balkens einen kleinen Hinweis „Kosten derzeit nicht verfügbar“.

# Speicherung und Ablauf

Der Kostenrekorder sammelt Nutzungsereignisse während eines GitHub-Action-Laufs. Am Ende werden sie atomar in die Monatsdatei übernommen. Die bestehende Workflow-`concurrency` verhindert gleichzeitig schreibende Tagesläufe. Wiederholte Ereignisse erhalten eine stabile Ereigniskennung, damit ein erneutes Veröffentlichen desselben Laufs nicht doppelt gezählt wird.

Die Kostendatei wird gemeinsam mit neu erzeugten Berichten unter `data/` versioniert und über GitHub Pages veröffentlicht. Der vorhandene API-Schlüssel bleibt ausschließlich als GitHub Secret im Cloud-Lauf.

Die automatische Erfassung beginnt mit der Bereitstellung dieser Funktion. Frühere Tokenverbräuche werden nicht geschätzt oder rückwirkend erfunden. Die erste Karte trägt deshalb bei Bedarf den Hinweis „Erfassung seit 03.08.2026“.

# Fehler- und Sicherheitsverhalten

- Unbekannte Modelle lösen keine stillschweigende Null-Euro-Buchung aus. Das Ereignis wird als nicht berechenbar markiert.
- Negative, boolesche oder unplausibel große Tokenwerte werden verworfen und protokolliert.
- Ein Fehler der Kostenaufzeichnung darf einen ansonsten gültigen Tagesbericht nicht verhindern.
- Eine ungültige Kostendatei wird nicht veröffentlicht.
- In der öffentlichen Datei stehen weder Prompts noch Nachrichteninhalte, API-Schlüssel, HTTP-Header, Provider-Request-IDs oder GitHub-Zugangsdaten.
- Die PWA liest ausschließlich die veröffentlichte Monatszusammenfassung; sie ruft Anthropic niemals direkt auf.

# Barrierefreiheit und responsive Darstellung

Der Prozentstand wird nicht nur durch Farbe vermittelt. Die Karte erhält einen zugänglichen Namen wie „Geschätzte API-Kosten im August: 16,8 Prozent des Monatsbudgets“. Markierungen und Eurostufen bleiben auch auf kleinen Bildschirmen lesbar. Bei sehr schmaler Darstellung dürfen die inneren Eurobeschriftungen verkürzt werden, während 0 und 5 Euro erhalten bleiben.

Die bestehende reduzierte Bewegungsdarstellung wird respektiert. Der Balken benötigt keine Animation, um verständlich zu sein.

# Tests und Abnahmekriterien

Automatisierte Tests decken mindestens ab:

- Kostenberechnung für Haiku 4.5 und Sonnet 4.6,
- Eingabe-, Ausgabe- und vorhandene Cache-Token,
- Umrechnung von US-Dollar in Euro,
- Prozentwerte unter, bei und über 100 Prozent,
- Monatsgrenze in `Europe/Berlin`,
- erfolgreiche, fehlgeschlagene und nicht messbare Aufrufe,
- Deduplizierung wiederholter Ereignisse,
- atomare Veröffentlichung und Schema-Validierung,
- fehlende oder beschädigte Kostendateien,
- öffentliche Darstellung ohne sensible Felder,
- responsive und zugängliche Beschriftung der Variante B.

Die Funktion gilt als abgenommen, wenn ein simulierter Cloud-Lauf eine gültige Monatsdatei erzeugt, die PWA daraus den richtigen Prozentstand zeichnet, vorhandene Berichte bei einem Kostenfehler weiterhin angezeigt werden und die vollständige Testsuite erfolgreich bleibt.

# Nicht enthalten

- Abruf der tatsächlichen Anthropic-Rechnung über einen Admin-API-Schlüssel,
- automatische Wechselkursabfrage,
- Auswahl und Vergleich vergangener Monate in der Oberfläche,
- individuelle Budgets pro Berichtstyp,
- Benachrichtigungen beim Erreichen einer Budgetstufe,
- rückwirkende Schätzung früherer Aufrufe.
