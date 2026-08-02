---
title: Zuverlässiger Morgenbericht in Berliner Ortszeit
date: 2026-08-02
status: umgesetzt
---

# Ziel

Der persönliche Lagebericht soll täglich morgens für den aktuellen Berliner Kalendertag bereitstehen. Zielzeit ist 06:30 Uhr in `Europe/Berlin`; nach der üblichen Laufzeit soll der Bericht ungefähr bis 06:35 Uhr live sein. Sommer- und Winterzeit werden automatisch berücksichtigt.

GitHub Actions garantiert keine minutengenaue Ausführung und kann geplante Läufe verzögern oder verwerfen. Die Lösung senkt dieses Risiko durch mehrere zeitlich versetzte Auslöser und verhindert zugleich mehrfache kostenpflichtige Claude-Aufrufe.

# Zeitplanung

Der Workflow erhält drei tägliche Zeitpunkte mit der IANA-Zeitzone `Europe/Berlin`:

- 05:45 Uhr: regulärer Vorlauf,
- 06:05 Uhr: erster Ersatzlauf,
- 06:25 Uhr: zweiter Ersatzlauf.

Ein verspätet gestarteter geplanter Workflow darf nicht mehr anhand seiner tatsächlichen Uhrzeit übersprungen werden. Jeder geplante Lauf prüft stattdessen den vorhandenen Datenstand.

# Idempotenz und Kostenkontrolle

Vor einem Claude-Aufruf bestimmt der Workflow das aktuelle Datum in Berliner Ortszeit und prüft, ob `data/daily/YYYY-MM-DD.json` bereits existiert.

- Fehlt der Tagesbericht, darf genau dieser Lauf ihn erzeugen.
- Existiert er, wird die Tageserzeugung ohne API-Aufruf übersprungen.
- Die bestehende Workflow-Concurrency bleibt aktiv und serialisiert gleichzeitig eintreffende Ersatzläufe.
- Ein manueller `workflow_dispatch` bleibt als bewusste Neuausführung verfügbar.

Wochen- und Monatsberichte werden getrennt idempotent behandelt. Ein Ersatzlauf darf einen fehlenden fälligen Rückblick nachholen, ohne den bereits vorhandenen Tagesbericht erneut kostenpflichtig zu erzeugen.

# Fehlerverhalten

Scheitert der erste Lauf vor dem erfolgreichen Commit, kann der nächste geplante Lauf erneut versuchen, den fehlenden Bericht zu erzeugen. Ein ungültiger Bericht wird weiterhin nicht veröffentlicht. Es gibt keine Endlosschleife innerhalb eines einzelnen Workflows.

GitHub Actions bleibt ein Dienst ohne harte Zustellgarantie. Wenn trotz der drei Zeitpunkte regelmäßig starke Verzögerungen auftreten, ist ein externer Zeitdienst der nächste Eskalationsschritt; er gehört nicht zu dieser Umsetzung.

# Anzeige in der PWA

Die App vergleicht den neuesten Bericht mit dem aktuellen Berliner Datum. Fehlt der heutige Bericht, zeigt sie einen klaren Hinweis, dass bislang nur der Bericht des Vortags verfügbar ist. Beim erneuten Öffnen beziehungsweise Zurückkehren in die App wird der Index ohne Cache neu geprüft, damit ein inzwischen veröffentlichter Bericht ohne Neuinstallation erscheint.

# Tests und Abnahme

- Tests für Berliner Datum sowie fällige Tages-, Wochen- und Monatsartefakte.
- Vertragstest für drei Zeitpunkte mit `Europe/Berlin`.
- Test, dass ein vorhandener Tagesbericht keinen erneuten automatischen API-Lauf auslöst.
- Test, dass ein fehlender fälliger Wochen- oder Monatsbericht unabhängig nachgeholt werden kann.
- Frontend-Test für den sichtbaren Hinweis bei einem fehlenden heutigen Bericht.
- Vollständige lokale Tests sowie kostenlose GitHub-Tests vor einem neuen kostenpflichtigen Tageslauf.

# Nicht Bestandteil

EU-Nachrichten, mehrere Meldungen je Kategorie und das vollständige Scannen von Artikelseiten werden in einer eigenen Spezifikation behandelt. Diese Erweiterungen verändern Datenmodell, Quellenabruf, Kosten und Oberfläche und sollen den Zeitplan-Fix nicht verzögern.
