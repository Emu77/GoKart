# GoKart – QField-Prototyp (Stand 12.10.2026)

Durchgängiger Ablauf in QField: **Fläche wählen → Pflanzennamen sprechen oder tippen → aus max. 5 Vorschlägen wählen → speichern.**

## Inhalt

| Ordner / Datei | Zweck |
|---|---|
| `qfield_projekt/` | *wird erzeugt* (nicht im Repo): `gokart.qgs`, `gokart.gpkg`, Plugin `gokart.qml` + `gokart_suche.js` + Icon |
| `plugin/` | Quellcode des QField-Projekt-Plugins |
| `werkzeuge/build_gokart_projekt.py` | Erzeugt GeoPackage + QGIS-Projekt aus `GoKart_Pflanzen.sqlite` (+ GermanSL) |
| `werkzeuge/gokart_namen.py` | Aufbereitung der deutschen Namen (z. B. „Eiche (Unterart), Stiel-“ → „Stiel-Eiche“) |
| `werkzeuge/zusatznamen.csv` | Eigene gebräuchliche Namen, z. B. Rot-Klee → *Trifolium pratense* |
| `test/test_suche.js` | Suchtest mit Echtdaten (32 Fälle, alle bestanden) |
| `test/qml_harness.py` | Simuliert QField und spielt den kompletten Ablauf mit dem Plugin durch |

## Datenmodell (`gokart.gpkg`, EPSG:25833)

- `flaechen` (Polygon): `flaeche_id` (eindeutig), `name`, `bemerkung` – 3 Testflächen im Tiergarten
- `artnachweise`: `flaeche_id`, `taxon_id`, Namen, `original_eingabe`, `erfasst_am`, `bemerkung`
- `eigene_synonyme`: `taxon_id`, `synonym`, `schluessel` (entsteht beim Erfassen)
- `taxon` (6.101) und `suchnamen` (15.649): Referenz, schreibgeschützt
- Relation: Fläche 1:n Artnachweise → im Flächenformular gibt es den Reiter „Arten“

## Auf dem Gerät nutzen (SHIFTphone / Tablet)

1. Projekt bauen (siehe unten), den Ordner `qfield_projekt` als ZIP packen, aufs Gerät kopieren und in QField als Projekt importieren (oder den Ordner direkt in den QField-Projektordner kopieren).
2. `gokart.qgs` öffnen und die Nachfrage, ob das **Projekt-Plugin** geladen werden darf, bestätigen.
3. Den grünen Blatt-Knopf in der Plugin-Leiste antippen.
4. Fläche wählen: Liste, **📍 GPS** (Position liegt in der Fläche) oder **⌖ Karte** (Kartenmitte – praktisch im Emulator).
5. Ins Namensfeld tippen und das **Mikrofon der Tastatur** nutzen. Bei genau einem eindeutigen Treffer ist dieser schon ausgewählt, dann reicht **Enter**.
6. Wenn die Eingabe kein bekannter Name war (z. B. „Stil Eiche“), kannst du sie per Häkchen als **eigenes Synonym** speichern. Danach wird sie exakt erkannt.

**Spracheingabe offline:** Die Tastatur muss offline diktieren können, z. B. mit FUTO Keyboard (FUTO Voice Input) oder Gboard mit heruntergeladenem Offline-Sprachpaket Deutsch. Das Plugin selbst braucht keine Internetverbindung, nur die OSM-Hintergrundkarte.

## Projekt neu bauen (Ubuntu 24.04)

```bash
sudo apt install python3-qgis qgis-providers
cd GoKart/qfield/werkzeuge
python3 build_gokart_projekt.py \
  --db /media/emu/daten/gpb/GoKart/pflanzen/GoKart_Pflanzen_Datenbank/GoKart_Pflanzen.sqlite \
  --germansl "/media/emu/daten/gpb/GoKart/pflanzen/germansl/GermanSL 1.5/germansl.sqlite" \
  --ziel /media/emu/daten/gpb/GoKart/qfield_projekt
```
Ein vorhandenes `gokart.gpkg` wird nur mit `--neu` überschrieben, vorher wird automatisch eine `.bak`-Sicherung angelegt.
**Achtung:** Dabei gehen Erfassungen aus dem alten GeoPackage verloren. Vorher vom Gerät zurückholen!

### Eigene Kartierflächen übernehmen

Statt der Tiergarten-Testflächen kann ein vorhandener Polygon-Layer (Shapefile, GeoPackage …) übernommen werden.
Das Koordinatensystem der Quelle (z. B. EPSG:25832) wird für Flächen und Projekt übernommen.

```bash
# 1. Felder anzeigen lassen
python3 build_gokart_projekt.py --db … --ziel … --flaechen /pfad/biotope.shp
# 2. mit ID-Feld (und optional Namensfeld) bauen
python3 build_gokart_projekt.py --db … --germansl … --ziel … \
  --flaechen /pfad/biotope.shp --id-feld BIOTOP_NR --name-feld BT_TEXT --neu
```
Bei GeoPackages mit mehreren Layern zusätzlich `--flaechen-layer <name>` angeben.
Doppelte IDs bekommen ein Suffix (`-2`, `-3`), Flächen ohne ID heißen `OHNE-ID-<fid>`. Beides meldet das Skript.

Alternativ in QGIS den Layer `flaechen` direkt bearbeiten. Jede Fläche braucht eine eindeutige `flaeche_id`.

## Tests

```bash
python3 test/testdaten_export.py qfield_projekt/gokart.gpkg testdaten.json
node test/test_suche.js testdaten.json
QT_QPA_PLATFORM=offscreen python3 test/qml_harness.py qfield_projekt_kopie
```
`qml_harness.py` schreibt in das GeoPackage, deshalb nur mit einer **Kopie** ausführen. Benötigt: `pip install PySide6-Essentials`.

## Suche – wie sie funktioniert

1. Normalisieren: Kleinschreibung, ä→a, ß→ss, Leer- und Bindestriche entfernen („Stiel Eiche“ = „Stiel-Eiche“)
2. Exakt → Wortanfang → enthalten
3. **Kölner Phonetik** gegen Hör- und Erkennungsfehler („kwerkus robur“ → *Quercus robur*, „Spitzwegerisch“ → Spitz-Wegerich)
4. Levenshtein bei Tippfehlern
5. Gewichtung: eigenes Synonym > deutscher Name > wissenschaftlich > botanisches Synonym; bei Gleichstand Art vor Unterart vor Aggregat vor Gattung

Etwa 30 ms pro Suche am PC.

## Datenkorrekturen in diesem Schritt

- **499 fehlende deutsche Namen** aus GermanSL ergänzt (z. B. Feld-Ahorn, Sumpfdotterblume, Breitblättriger Wegerich)
- Umgedrehte BfN-Namen aufgelöst: „Herbstaster, Glatte“ → „Glatte Herbstaster“, „Eiche (Unterart), Stiel-“ → „Stiel-Eiche“
- 42 wissenschaftliche Namen kommen doppelt vor (s. l. / s. str., z. B. *Urtica dioica*). Damit man sie unterscheiden kann, zeigt die Trefferliste den vollen Namen mit Autor.

## Offen / nächste Schritte

1. **Test in echtem QField (4.x)**. Die Plugin-API ist gegen den QField-Quellcode geprüft und der Ablauf in einer Simulation getestet, aber noch nicht auf dem Gerät gelaufen. Für QField 3.x ist ein Fallback eingebaut, der aber ungetestet ist.
2. Dialoghöhe bei eingeblendeter Bildschirmtastatur auf kleinen Displays prüfen
3. Rückweg: Erfassungen aus `gokart.gpkg` auswerten oder exportieren (z. B. Artenliste je Fläche als CSV)
4. Optional eigene Offline-Erkennung mit Vosk, falls das Tastatur-Diktat bei botanischen Namen nicht reicht
5. Echte Kartierflächen und Flächen-IDs übernehmen
