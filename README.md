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

### QField-Prototyp (`qfield/`)
- QField-Projekt-Plugin (QML): Fläche wählen → Name sprechen/tippen → max. 5 Vorschläge → speichern
- Fehlertolerante Suche mit Kölner Phonetik (z. B. „kwerkus robur“ → *Quercus robur*)
- Eigene Synonyme werden beim Erfassen gelernt
- GeoPackage-Datenmodell: Flächen, Artnachweise, eigene Synonyme, Taxa, Suchnamen
- Build-Skript (PyQGIS) erzeugt GeoPackage + QGIS-Projekt aus der SQLite-Datenbank und GermanSL

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
- `qfield/plugin/` – QField-Projekt-Plugin (`gokart.qml`, Suchlogik `gokart_suche.js`)
- `qfield/werkzeuge/` – Projekt-Build (GeoPackage + QGIS-Projekt), Namensaufbereitung
- `qfield/test/` – Suchtest (Node) und QField-Simulation (PySide6)
- `gokart_qfield/` – fertiges QField-Projekt mit eigenen Flächen (`gokart.gpkg` nicht im Repo, Plugin nur Kopie – siehe dortige README)

## Anleitung

Detaillierte Anleitung zum QField-Plugin (PDF):
[docs/GoKart_QField_Anleitung.pdf](docs/GoKart_QField_Anleitung.pdf)

Inhalt: Voraussetzungen, Datenmodell, Projekt bauen/einrichten,
Übertragung aufs Gerät, Arterfassung im Gelände, Standortfotos,
Abgleich PC ↔ Tablet, Artenliste-Export, Fehlerbehebung.

## Technologien

- JavaScript / QML
- HTML5 / CSS3
- Python
- SQLite
- Vosk
- QGIS / QField

## Status

Das Projekt befindet sich in der Entwicklung.

Ein QField-Prototyp ist vorhanden und in einer Simulation getestet;
der Test auf echten Geräten (Android-Smartphone, Tablet) steht aus.
Die Offline-Spracherkennung läuft vorerst über das Diktat der Tastatur.

## GitHub

https://github.com/Emu77/GoKart
