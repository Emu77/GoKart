# GoKart – Punktaufnahmen (GPS ohne Flächen-Shape) und Zusatzangaben

Stand: 07.11.2026 · umgesetzt in QField-Plugin 0.7 / GoKart Desktop 0.7.0

GoKart erfasst Artnachweise auch ohne Kartierfläche: Der Standort kommt aus der GPS-Position (oder der
Kartenmitte). Flächen bleiben möglich, sind aber nicht mehr Pflicht. Jeder Artnachweis kann zusätzlich
Deckung, Anzahl und Phänologie tragen – auf Flächen genauso wie an Punkten.

## Anwendungsfälle

- Einzelfunde seltener oder geschützter Arten, Neophyten-Standorte
- Transekte/Begehungen mit fortlaufenden Fundpunkten
- Vorkartierung: erst im Gelände erfassen, Flächen später digitalisieren
- Weitergabe an Kartierer ohne eigene Shapes

## Datenmodell

**`aufnahme_punkte`** (Punkt-Layer, KBS wie die Flächen; ein Standort mit beliebig vielen Arten)

| Feld | Typ | Inhalt |
| --- | --- | --- |
| `punkt_id` | TEXT, eindeutig | z. B. `P-20261107-141233-k7x2` (Zeitstempel + Zufall, konfliktfrei über Geräte) |
| `erfasst_am`, `geaendert_am` | TEXT | ISO-Zeitstempel; `geaendert_am` entscheidet beim Abgleich |
| `bearbeiter` | TEXT | Kartierer |
| `gps_genauigkeit` | REAL | horizontale Genauigkeit [m] laut Positionsquelle |
| `hoehe` | REAL | [m], falls verfügbar |
| `pos_quelle` | TEXT | `gps`, `manuell` (Kartenmitte), `korrigiert` |
| `biotoptyp` | TEXT | optional, Code im geltenden Schlüssel |
| `flaeche_id` | TEXT | optional, per „Punkte Flächen zuordnen“ |
| `bemerkung` | TEXT | Freitext |

**`artnachweise`** zusätzlich: `punkt_id` (statt `flaeche_id` – genau eins von beiden ist gesetzt),
`deckung` (r, +, 1, 2m, 2a, 2b, 3, 4, 5), `anzahl` (Zahl oder Klasse 1, 2–5, 6–25, 26–100, >100),
`phaenologie` (vegetativ, Knospe, blühend, fruchtend, abgestorben).

Fotos bleiben unabhängig von Punkten und Artnachweisen (Tabelle `fotos` wie bisher).

**Projektvariablen**

| Variable | Standard | Wirkung |
| --- | --- | --- |
| `gokart_module` | – | `punkte` schaltet Punktaufnahmen frei (braucht `arten`) |
| `gokart_punkt_genauigkeit` | 10 | Warnung bei schlechterer GPS-Genauigkeit [m] |
| `gokart_punkt_radius` | 25 | Hinweis „neue Aufnahme?“ ab dieser Entfernung zum aktiven Punkt [m] |
| `gokart_zusatz` | leer | welche Zusatzangaben die Schnellleiste anbietet, z. B. `deckung,phaenologie` |

## QField

1. Umschalter **Fläche / Punkt (GPS)** oben im Erfassungsdialog (nur mit Modul `punkte`).
2. **Neue Aufnahme hier** übernimmt die GPS-Position. Ist die Genauigkeit schlechter als die Schwelle,
   kommt eine Warnung; zweites Antippen übernimmt trotzdem.
   **⌖ Fadenkreuz** setzt den Punkt von Hand: Der Dialog geht zur Seite, über der Karte erscheint eine Leiste
   mit der Koordinate unter dem QField-Fadenkreuz (Rechts-/Hochwert im Layer-KBS) und der Fläche, in der es
   liegt. Karte verschieben, dann **Hier setzen** (`pos_quelle = manuell`). Ist in QField das Einrasten an,
   rastet das Fadenkreuz auf Kanten und Ecken der Flächen-Shapes ein.
   **Punkt verschieben** korrigiert die Lage des aktiven Punkts auf dieselbe Weise (`pos_quelle = korrigiert`,
   `gps_genauigkeit` wird geleert, `punkt_id` und Artnachweise bleiben).
3. Arten sprechen/tippen wie bisher; Zusatzangaben direkt hinterher:
   „Calluna, Deckung drei, blühend“, „Orchis mascula zwölf Stück“, „Rot-Klee Deckung plus“.
   „Deckung zwei“ allein ist mehrdeutig (2m/2a/2b) und wird als „nicht erkannt“ gemeldet.
4. Nach dem Speichern zeigt die **Schnellleiste** die aktiven Zusatzangaben als Knöpfe; Antippen speichert
   sofort, nochmal Antippen leert. Beim Bearbeiten wirkt die Leiste auf den bearbeiteten Eintrag; dort reicht
   auch „Deckung vier“ ohne Artnamen.
5. Unter den Knöpfen: aktuelle GPS-Genauigkeit und Abstand zum aktiven Punkt; ab dem Radius erscheint
   „neue Aufnahme?“. Die Aufnahme endet nicht automatisch.

## Desktop und Werkzeuge

- **GoKart Desktop → Einrichten…**: Erfassung „Punktaufnahmen (GPS)“, Schwellwerte, Zusatzangaben; legt
  Tabelle, Layer, Felder und die Beziehung Punkt → Artnachweise an. **Punkte Flächen zuordnen** setzt
  `flaeche_id` per Punkt-in-Fläche und meldet Punkte, die näher am Rand liegen als ihre GPS-Genauigkeit.
- **build_gokart_projekt.py** `--module arten,punkte --zusatzangaben deckung,phaenologie
  --punkt-genauigkeit 10 --punkt-radius 25`
- **abgleich.py** vereinigt Punktaufnahmen (Schlüssel `punkt_id`, neuerer Stand gewinnt inkl. Position),
  legt fehlende Tabelle/Spalten/Layer an und gibt die Projektvariablen vom PC vor. Artnachweise an Punkten:
  Schlüssel `@<punkt_id>:taxon_id`; Entfernen mit `--punkt-weglassen <punkt_id>`.
- **Artenliste** (Desktop und `artenliste_export.py`): Punkte erscheinen als eigene Gruppe „Punkt …“
  bzw. unter ihrer zugeordneten Fläche; Zusatzangaben stehen unter der Art und in eigenen CSV-Spalten.

## Offen

- Biotoptyp am Punkt: Feld vorhanden, Erfassung in QField noch nicht.
- Soll eine Aufnahme automatisch enden, wenn man sich weiter als den Radius entfernt? (derzeit nur Hinweis)
- Eigene, projektspezifische Zusatzangaben statt der festen Liste?
- Desktop-Dock zeigt Artnachweise weiterhin nur je Fläche.
