# gokart_qfield – QField-Projekt (eigene Kartierflächen)

Fertiges QField-Projekt, erzeugt mit `qfield/werkzeuge/build_gokart_projekt.py --flaechen …`.

| Datei | Im Repo | Herkunft |
|---|---|---|
| `gokart.qgs` | ja | Build-Skript |
| `gokart.gpkg` | **nein** (`*.gpkg` in `.gitignore`) | Build-Skript – enthält Flächen und Erfassungen |
| `gokart.qml`, `gokart_suche.js`, `gokart_icon.svg` | ja, **nur Kopie** | Quelle ist `qfield/plugin/` |

## Wichtig

- **`gokart.gpkg` fehlt nach dem Klonen.** Ohne die Datei öffnet sich das Projekt ohne Layer.
  Das GeoPackage liegt nur lokal bzw. auf dem Gerät, weil es eigene Kartierflächen und Erfassungen enthält.
- **Plugin nie hier bearbeiten**, sondern in `qfield/plugin/`. Danach Kopie aktualisieren:
  ```bash
  python3 qfield/werkzeuge/plugin_aktualisieren.py gokart_qfield            # kopieren
  python3 qfield/werkzeuge/plugin_aktualisieren.py gokart_qfield --pruefen  # nur vergleichen
  ```
  `gokart.gpkg` und `gokart.qgs` bleiben dabei unverändert.
- **Koordinatensystem: EPSG:25832** (ETRS89 / UTM 32N). Das Build-Skript übernimmt das System der Flächen-Quelldatei;
  Standard ohne `--flaechen` wäre EPSG:25833. Berlin/Brandenburg liegt in Zone 33 – bei Flächen dort prüfen,
  ob die Quelldatei wirklich 25832 hat.

## Neu bauen

Achtung: Ein Neubau mit `--ziel gokart_qfield` überschreibt auch `gokart.qgs`, mit `--neu` zusätzlich `gokart.gpkg`
(Sicherung `.gpkg.bak` wird angelegt). Erfassungen vorher vom Gerät zurückholen.
Details: [`qfield/README.md`](../qfield/README.md).

## Aufs Gerät

Ordner inklusive `gokart.gpkg` als ZIP packen, aufs Gerät kopieren, in QField importieren und
das Laden des Projekt-Plugins bestätigen.
