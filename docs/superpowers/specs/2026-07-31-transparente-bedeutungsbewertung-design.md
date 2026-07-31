# Transparente Bedeutungsbewertung für Tagesmeldungen

**Datum:** 2026-07-31  
**Status:** Vom Nutzer im Gespräch freigegeben

## Ausgangslage

Der Tagesbericht darf eine vorhandene Nachricht derzeit als `no_major_development` ausgeben, wenn das Sprachmodell sie nicht für wesentlich hält. Dadurch entscheidet das Modell implizit, welche Meldungen der Nutzer überhaupt sehen kann. Diese Entscheidung ist subjektiv und soll beim Nutzer bleiben.

## Ziel

Jede aktuelle, technisch geeignete Meldung soll sichtbar bleiben. Das Modell darf Meldungen ordnen und ihre mögliche Bedeutung nachvollziehbar bewerten, aber nicht allein wegen vermeintlich geringer Bedeutung verwerfen. Der Nutzer überprüft die Bewertungen nach einer Testwoche und lässt die Bewertungsregeln anschließend an seine Einschätzung anpassen.

## Nicht-Ziele der ersten Version

- Kein Benutzerkonto und keine serverseitige Speicherung persönlicher Bewertungen.
- Keine automatische Anpassung des Modells aus einzelnen Klicks.
- Keine Abstimmung darüber, ob eine Entwicklung positiv oder negativ ist.
- Keine Änderung der drei bestehenden Kategorien Politik und Gesellschaft, Wirtschaft und Technologie sowie Außenpolitik und Sicherheit.

## Auswahlregel

Für jedes Land und jede Kategorie wird die beste vorhandene, aktuelle und technisch geeignete Meldung veröffentlicht. Die Rangfolge darf anhand von Aktualität, Quellenqualität, Deutschland-Bezug und allgemeiner Tragweite bestimmt werden. Eine niedrige Bedeutungsbewertung ist jedoch kein Ausschlussgrund.

Der vorhandene Status `no_major_development` bleibt aus Kompatibilitätsgründen erhalten, wird aber eindeutig neu definiert: In den erfolgreich geprüften Quellen wurde für das Berichtsfenster keine technisch geeignete neue Meldung gefunden. `unavailable` bleibt technischen Fehlern vorbehalten, durch die keine verlässliche Auswahl möglich war.

Eine Meldung aus nur einer seriösen Quelle darf veröffentlicht werden. Sie erhält weiterhin den sichtbaren Hinweis `single_source`. Widersprüche, Paywalls, reine Feed-Auswertung und andere Quellenbegrenzungen bleiben unabhängig von der Bedeutungsbewertung sichtbar.

## Zwei getrennte Bewertungen

Jede veröffentlichte Meldung erhält zwei Bewertungen mit einem ganzzahligen Wert von 0 bis 3 und jeweils einer kurzen Begründung.

### Deutschland-Bezug

| Wert | Farbe | Arbeitsdefinition |
|---:|---|---|
| 0 | Grau | Kein erkennbarer Bezug zu Deutschland. |
| 1 | Grün | Indirekte Auswirkungen auf Deutschland sind möglich. |
| 2 | Gelb | Konkrete Auswirkungen auf deutsche Politik, Wirtschaft oder Sicherheit sind wahrscheinlich. |
| 3 | Rot | Unmittelbare oder weitreichende Folgen für Deutschland sind zu erwarten. |

### Allgemeine Tragweite

| Wert | Farbe | Arbeitsdefinition |
|---:|---|---|
| 0 | Grau | Routinemeldung oder sehr begrenztes Ereignis. |
| 1 | Grün | Relevante, aber räumlich oder fachlich begrenzte Entwicklung. |
| 2 | Gelb | Größere politische, wirtschaftliche oder sicherheitspolitische Entwicklung. |
| 3 | Rot | Außergewöhnliche, internationale oder möglicherweise systemische Entwicklung. |

Die Farben drücken nur die Intensität der vermuteten Bedeutung aus. Rot bedeutet weder automatisch negativ noch alarmierend. Die Definitionen sind ein erster, transparenter Bewertungsmaßstab und werden nach der Testwoche anhand des Nutzerfeedbacks angepasst.

## Datenmodell

Das bisherige boolesche Feld `germanyRelevance` wird durch zwei strukturierte Bewertungen ersetzt:

```json
{
  "germanyRelevance": {
    "score": 0,
    "reasonDe": "Kein konkreter Bezug zu Deutschland erkennbar."
  },
  "overallSignificance": {
    "score": 1,
    "reasonDe": "Die Entwicklung ist relevant, bleibt bislang aber begrenzt."
  }
}
```

Für beide Objekte gilt:

- `score` ist eine ganze Zahl von 0 bis 3.
- `reasonDe` ist ein kurzer, verständlicher deutscher Satz.
- Beide Angaben sind bei `published` verpflichtend.
- Bei `no_major_development` oder `unavailable` haben beide Bewertungsfelder den Wert `null`. Damit bleibt „nicht bewertet“ eindeutig von Stufe 0 getrennt.

Wegen der inkompatiblen Änderung von `germanyRelevance` wird `schemaVersion` von 1 auf 2 erhöht. In Version 2 sind `germanyRelevance` und `overallSignificance` verpflichtende Felder des Kategorieobjekts; jedes ist bei `published` ein Bewertungsobjekt und bei den beiden leeren Statuswerten `null`. Bereits veröffentlichte Berichte der Version 1 müssen in der Oberfläche weiterhin lesbar bleiben; ihr boolescher Deutschland-Bezug wird lediglich als alter Datenstand ohne erfundene Punktzahl dargestellt.

## Darstellung in der PWA

Direkt an jeder veröffentlichten Meldung erscheinen zwei kompakte Kennzeichnungen:

- `🇩🇪 Deutschland 0–3`
- `⚡ Tragweite 0–3`

Farbe und Zahl werden immer gemeinsam gezeigt, damit die Information nicht allein über Farbe vermittelt wird. Die kurze Begründung ist durch Aufklappen oder Antippen erreichbar. Quellenlage und Einschränkungen stehen separat; sie werden nicht mit der Bedeutungsampel vermischt.

Meldungen werden nicht allein aufgrund des Scores visuell versteckt. Die erste Version benötigt keine Bewertungsbuttons. Der Nutzer sammelt abweichende Einschätzungen während der Testwoche und teilt sie anschließend zur Anpassung der Regeln mit.

## Datenfluss

1. Feeds liefern Nachrichtenkandidaten innerhalb des Berichtsfensters.
2. Die Extraktion ordnet Kandidaten Land, Kategorie und Ereignis zu, ohne sie anhand persönlicher Bedeutung zu entfernen.
3. Die Auswahl nimmt pro Land und Kategorie den bestgeeigneten vorhandenen Kandidaten. Objektive Ausschlussgründe sind insbesondere fehlende Aktualität, ungültige oder unzulässige Quelle, Duplikat oder unpassende Zuordnung.
4. Das Modell erstellt Zusammenfassung, beide Scores und beide Begründungen.
5. Die Validierung prüft Quellenbindung, Statuslogik, Scorebereiche und Pflichtbegründungen.
6. Die PWA zeigt Meldung, Bewertungen und Quellenbegrenzungen getrennt an.

## Fehlerbehandlung

- Keine geeignete Meldung trotz erfolgreich geprüfter Quellen: leerer Abschnitt mit eindeutiger Formulierung, dass keine neue Meldung gefunden wurde.
- Quellenabruf technisch gescheitert: `unavailable` mit `technical_failure`; keine Aussage, es habe keine Meldung gegeben.
- Nur eine Quelle: Meldung veröffentlichen und `single_source` anzeigen.
- Widersprüchliche Quellen: Meldung nur mit neutral formulierter Zusammenfassung und `source_disagreement` anzeigen.
- Ungültige oder fehlende Modellbewertung: Bericht nicht ungeprüft veröffentlichen; den Modellaufruf nach bestehender Wiederholungsstrategie erneut versuchen und den Abschnitt andernfalls als technisch nicht verfügbar kennzeichnen.

## Tests und Abnahmekriterien

- Eine geeignete Meldung mit niedrigen Scores wird weiterhin als `published` ausgegeben.
- Eine geeignete Einzelquellenmeldung wird als `published` ausgegeben und trägt `single_source`.
- `no_major_development` kann nicht allein durch eine niedrige Bedeutung ausgelöst werden.
- Beide Scores akzeptieren ausschließlich ganze Zahlen von 0 bis 3.
- Veröffentlichte Meldungen benötigen zwei nicht leere Begründungen.
- Leere und technisch ausgefallene Abschnitte unterscheiden „nichts gefunden“ von „nicht prüfbar“.
- Alte Berichte mit booleschem `germanyRelevance` bleiben darstellbar.
- Die PWA zeigt Zahl und Farbe gemeinsam und macht beide Begründungen zugänglich.
- Wochen- und Monatsberichte dürfen die Scores zur Sortierung verwenden, aber nicht als alleinigen Löschfilter.

## Testwoche und spätere Anpassung

Nach etwa sieben Tagesberichten vergleicht der Nutzer seine Einschätzung mit den angezeigten Bewertungen. Besonders betrachtet werden falsch hohe oder niedrige Werte, wiederkehrend anders gewichtete Themen sowie Unterschiede zwischen Deutschland-Bezug und allgemeiner Tragweite. Erst danach werden die Arbeitsdefinitionen oder Promptregeln geändert. Ein automatisches Lernsystem bleibt bis zu einer späteren, gesonderten Designentscheidung außerhalb des Umfangs.
