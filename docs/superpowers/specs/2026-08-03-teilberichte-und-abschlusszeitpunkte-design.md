---
title: Transparente Wochen- und Monatsberichte
date: 2026-08-03
status: review
---

# Ziel

Die App veröffentlicht Wochen- und Monatsberichte nach Abschluss des jeweiligen Zeitraums. Auch beim Start mitten in einer Woche oder einem Monat bleiben vorhandene Informationen sichtbar. Ein deutlicher Abdeckungshinweis verhindert, dass ein Teilbericht wie ein vollständiger Rückblick wirkt.

# Ausgangslage

Der bisherige Wochenbericht benötigt mindestens vier gültige Tagesberichte, der Monatsbericht mindestens 20. Diese Grenzen sollten künstliche Trends aus wenigen Einzeltagen und unnötige Claude-Kosten verhindern. In der Startphase führten sie jedoch dazu, dass drei vorhandene Berichtstage vollständig verborgen blieben. Zudem wurden Rückblicke bereits am letzten Tag des laufenden Zeitraums statt nach dessen Abschluss eingeplant.

# Umfang dieser Ausbaustufe

Enthalten sind:

- neue Abschlusszeitpunkte für Kalenderwoche und Kalendermonat,
- transparente Teilberichte ab einem gültigen Tagesbericht,
- ein klarer Abdeckungsstatus in Datenmodell und Oberfläche,
- der freigegebene Umfang von Gesamt- und Länderabschnitten,
- unabhängige Wiederholung und sichtbare Fehlerzustände,
- Abwärtskompatibilität vorhandener Berichte.

Nicht enthalten sind:

- das vollständige Einlesen ausgewählter Artikel für Tagesmeldungen,
- die neue tägliche Einordnung mit Hintergrund und offenen Punkten,
- die EU als vierter Bereich,
- eine automatische Nacherzeugung vergangener Rückblicke.

Diese Punkte folgen als getrennte Ausbaustufen. Eine kostenpflichtige Nacherzeugung alter Zeiträume benötigt eine eigene Freigabe.

# Zeiträume und Ausführung

Alle Datumsentscheidungen verwenden `Europe/Berlin`.

## Woche

- Eine Kalenderwoche läuft von Montag bis Sonntag.
- Der Rückblick wird am Montagmorgen für die unmittelbar vorherige Kalenderwoche fällig.
- Die bestehenden drei Morgenfenster 05:45, 06:05 und 06:25 Uhr bleiben erhalten.
- Der Montagstagesbericht und der Rückblick sind unabhängige Artefakte. Ein Fehler des einen darf das andere nicht verwerfen.

## Monat

- Der Rückblick wird am ersten Kalendertag des neuen Monats für den vollständig abgeschlossenen Vormonat fällig.
- Fällt der erste Tag auf einen Montag, werden Wochen- und Monatsbericht unabhängig geprüft und erzeugt.
- Der Tagesbericht des ersten Tages gehört ausschließlich zum neuen Monat.

# Datenbasis und Teilberichte

- Ab einem gültigen Tagesbericht wird ein Rückblick erzeugt.
- Ohne gültigen Tagesbericht wird kein Claude-Aufruf durchgeführt und kein leeres Artefakt veröffentlicht.
- `sourceReportDates` enthält ausschließlich tatsächlich vorhandene und validierte Tagesberichte.
- `missingReportDates` enthält alle fehlenden Kalendertage des Zeitraums.
- `status` ist nur bei lückenloser Datenbasis `complete`, ansonsten `partial`.
- Ein erfolgreich erzeugter Teilbericht gilt für die drei Wiederholungsfenster als erledigt. Er wird nicht am selben Morgen erneut kostenpflichtig erzeugt.

Die Abdeckung wird aus den Datumslisten berechnet und nicht aus frei formuliertem Modelltext. Beispiele:

- `Datenbasis: 3 von 7 Tagen · Teilüberblick`
- `Datenbasis: 31 von 31 Tagen · Vollständiger Monatsbericht`

# Inhalt und Darstellung

## Wochenbericht

Der Wochenbericht beginnt mit einer Gesamtlage aus 8 bis 10 vollständigen Sätzen. Sie verbindet Entwicklungen über Länder und Kategorien, benennt Unsicherheiten und endet mit einem kurzen Ausblick. Sie wiederholt Tagesmeldungen nicht bloß hintereinander.

Danach folgen USA, China und Montenegro in der bestehenden Ländernavigation. Je Land erscheinen belegte Entwicklungslinien für Politik und Gesellschaft, Wirtschaft und Technologie sowie Außenpolitik und Sicherheit. Jede Entwicklung enthält:

- eine Wochenüberschrift,
- Ausgangslage, Veränderung und Stand am Periodenende,
- eine verständliche Einordnung von Bedeutung und möglichen Folgen,
- Deutschland-Bezug und allgemeine Tragweite,
- offene Punkte und Einschränkungen,
- verwendete Originalquellen und Berichtstage.

Der Verlauf umfasst 3 bis 6 Sätze, die getrennte Einordnung 2 bis 3 Sätze. Beruht ein Teilbericht nur auf einem vorhandenen Tag, bezeichnet die Oberfläche den Inhalt als `Momentaufnahme` und nicht als Trend oder Entwicklung.

Bei einer unvollständigen Woche steht der Abdeckungshinweis oberhalb der Gesamtlage. Erwartete Lesezeit: ungefähr 5 bis 10 Minuten.

## Monatsbericht

Der Monatsbericht verwendet denselben Grundaufbau, verdichtet aber größere Trends und Wendepunkte. Die Gesamtlage umfasst 12 bis 15 vollständige Sätze. Länderabschnitte beschreiben Ausgangslage, wesentliche Veränderungen, Stand am Monatsende und einen Ausblick. Wochenberichte werden nicht aneinandergereiht oder kopiert.

# Datenvertrag und Abwärtskompatibilität

Der neue Zeitraumbericht erhält eine neue Schemafassung. Der Vertrag unterscheidet die Satzvorgaben nach `periodType`:

- Woche: 8 bis 10 Sätze in `overallSummary`,
- Monat: 12 bis 15 Sätze in `overallSummary`.

Die Einordnung einer Entwicklung wird im neuen Feld `contextDe` als eigener, klar benannter Inhalt gespeichert, damit die Oberfläche sie zuverlässig getrennt darstellen kann. Bestehende Zeitraumberichte der bisherigen Schemafassungen bleiben validierbar und lesbar. Die Oberfläche zeigt bei alten Berichten die bisher vorhandenen Inhalte, ohne neue Einordnungen zu erfinden.

# Ablauf und Komponenten

1. Die Zeitplanung bestimmt am Montag die vorherige Woche und am Monatsersten den Vormonat.
2. Die Artefaktprüfung entscheidet für Tages-, Wochen- und Monatsbericht unabhängig, was fehlt.
3. Der Aggregator lädt ausschließlich validierte Tagesberichte des abgeschlossenen Zeitraums.
4. Bei mindestens einem Tagesbericht erstellt Sonnet genau einen Rückblick für den fälligen Zeitraum.
5. Der Publisher validiert und schreibt atomar, danach wird der Archivindex neu aufgebaut.
6. Die PWA lädt den neuen Index ohne Cache und zeigt Abdeckung, Gesamtlage und Länderabschnitte.

# Kostenkontrolle und Wiederholung

- Pro abgeschlossenem Zeitraum wird höchstens ein erfolgreich erzeugter automatischer Rückblick veröffentlicht.
- Ein bereits vorhandener gültiger Teil- oder Vollbericht wird in den Ersatzfenstern nicht erneut erzeugt.
- Ein Rückblick ohne Tagesdaten wird vor dem API-Aufruf beendet.
- Wochen- und Monatsbericht bleiben getrennt wiederholbar.
- Ein manueller Lauf bleibt eine bewusste kostenpflichtige Neuausführung.

Fehlgeschlagene oder ungültige Claude-Antworten können trotz ausbleibender Veröffentlichung Tokens verbrauchen. Die Ersatzfenster dürfen solche Fehler erneut versuchen; eine absolute Kostenobergrenze pro Zeitraum kann deshalb nicht garantiert werden.

# Fehlerbehandlung

- Scheitert ein Rückblick, wird ein erfolgreich erzeugter Tagesbericht trotzdem committed und veröffentlicht.
- Das Fehlen des fälligen Rückblick-Artefakts lässt den betreffenden Workflow sichtbar fehlschlagen; der Fehler wird nicht dauerhaft als Erfolg maskiert.
- Das nächste Morgenfenster prüft den aktuellen Stand von `main` und versucht nur das fehlende Artefakt erneut.
- Ein partieller Bericht ist kein Fehler, sofern Abdeckung und fehlende Tage korrekt ausgewiesen sind.
- Ungültige Modellantworten werden niemals veröffentlicht.

# Tests und Abnahmekriterien

Automatisierte Tests decken mindestens ab:

- Montag berechnet exakt die vorherige Kalenderwoche, auch über Jahresgrenzen.
- Der Monatserste berechnet exakt den Vormonat, auch im Januar.
- Ein, drei und sieben Tagesberichte erzeugen korrekte Wochenabdeckungen.
- Ein und alle Monatstage erzeugen korrekte Monatsabdeckungen, einschließlich Schaltjahren.
- Null Tagesberichte lösen keinen Modellaufruf aus.
- Teilberichte werden in Ersatzfenstern nicht doppelt erzeugt.
- Woche und Monat bleiben am selben Tag unabhängig fällig.
- Satzgrenzen 8–10 beziehungsweise 12–15 werden validiert.
- Alte Zeitraumberichte bleiben lesbar.
- Der Archivindex veröffentlicht valide Teilberichte mit vorhandenen Quelldaten.
- Die PWA zeigt Teil- und Vollständigkeitsstatus verständlich und barrierearm.
- Ein fehlgeschlagener Rückblick verwirft keinen gültigen Tagesbericht.

# Nichtfunktionale Anforderungen

- Keine zusätzlichen externen Skripte oder Tracker.
- Keine Lockerung der bestehenden Content-Security-Policy.
- Keine Veröffentlichung unvalidierter oder nur teilweise geschriebener JSON-Dateien.
- Keine Änderung an der täglichen Anzahl der Hauptmeldungen in dieser Ausbaustufe.
