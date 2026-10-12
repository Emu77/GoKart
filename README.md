# GoKart

GoKart ist ein Open-Source-Projekt zur digitalen Pflanzenkartierung
mit QGIS und QField.

## Projektziel

Entwicklung einer plattformübergreifenden Lösung zur Erfassung
von Pflanzenarten im Gelände.

Geplante Funktionen:

- Pflanzenarten suchen und auswählen
- Spracheingabe zur Pflanzenerfassung
- Automatische Vorschläge bei der Artnamensuche
- Eigene Synonyme für Pflanzenarten
- Zuordnung von Pflanzenarten zu Kartierungsflächen
- Integration in QGIS und QField
- Nutzung auf Android, iOS und Desktop

## Aktueller Entwicklungsstand

### Pflanzensuche
- HTML-, CSS- und JavaScript-Anwendung
- Pflanzenartendatenbank
- Suchfunktion mit Vorschlagsliste

### Spracheingabe
- JavaScript-Spracheingabe
- Experimentelle Offline-Spracherkennung mit Vosk
- Deutsches Vosk-Sprachmodell

### Datenhaltung
- SQLite-Datenbank
- JavaScript-Pflanzendaten
- Python-Skripte zur Datenverarbeitung

## Projektstruktur

- `docs/` – Projektdokumentation
- `pflanzen/app/` – Webanwendung
- `pflanzen/GoKart_Pflanzen_Datenbank/` – SQLite-Datenbank
- `pflanzen/originaldaten/` – Ausgangsdaten
- `pflanzen/sprachtest.py` – Test der Spracherkennung

## Technologien

- JavaScript
- HTML5 / CSS3
- Python
- SQLite
- Vosk
- QGIS / QField

## Status

Das Projekt befindet sich in der Entwicklung.

Die QField-Integration und die Offline-Spracherkennung
werden schrittweise umgesetzt.

## GitHub

https://github.com/Emu77/GoKart
