#!/usr/bin/env python3
"""GoKart – kopiert das aktuelle QField-Plugin (qfield_plugin/) in einen QField-Projektordner.

Quelle ist immer qfield_plugin/ (Arten, Fotos, Biotoptypen). Die QML-Datei wird so benannt wie die
Projektdatei im Ordner (kobm_qfield.qgs -> kobm_qfield.qml), sonst lädt QField das Plugin nicht.
Projektdaten (.gpkg, .qgs) bleiben unangetastet – keine Erfassung geht verloren.

Aufruf (aus dem Repo-Hauptordner):
    python3 qfield/werkzeuge/plugin_aktualisieren.py gokart_qfield                 # kopieren
    python3 qfield/werkzeuge/plugin_aktualisieren.py ~/QField/export/kobm          # QField-Sync-Export
    python3 qfield/werkzeuge/plugin_aktualisieren.py gokart_qfield --pruefen       # nur vergleichen, Exit 1 bei Abweichung
"""
import argparse
import filecmp
import shutil
import sys
from pathlib import Path

PLUGIN_ORDNER = Path(__file__).resolve().parents[2] / 'qfield_plugin'
PLUGIN_QML = 'GoKart_Wohnung.qml'
PLUGIN_DATEIEN = ('gokart_suche.js', 'gokart_biotop.js', 'gokart_icon.svg', 'gokart_foto.svg', 'gokart_biotop.svg')


def projektdatei(ordner, name=None):
    """Die .qgs/.qgz im Ordner finden (Sicherungen wie *.qgs~ zählen nicht)."""
    ordner = Path(ordner).expanduser()
    if name:
        p = ordner / name
        if not p.is_file():
            raise SystemExit(f'Projektdatei nicht gefunden: {p}')
        return p
    if not ordner.is_dir():
        raise SystemExit(f'Ordner nicht gefunden: {ordner}')
    kandidaten = sorted(p for p in ordner.iterdir() if p.is_file() and p.suffix.lower() in ('.qgs', '.qgz'))
    if not kandidaten:
        raise SystemExit(f'Keine .qgs/.qgz in {ordner}')
    if len(kandidaten) > 1:
        # QField-Sync-Exporte heißen *_qfield.qgs – die bevorzugen
        qf = [p for p in kandidaten if p.stem.endswith('_qfield')]
        if len(qf) == 1:
            return qf[0]
        raise SystemExit('Mehrere Projektdateien: ' + ', '.join(p.name for p in kandidaten) +
                         '\nBitte mit --projekt <Datei> angeben.')
    return kandidaten[0]


def plugin_paare(qgs):
    """[(Quelle, Ziel)] für das Plugin neben der Projektdatei."""
    if not (PLUGIN_ORDNER / PLUGIN_QML).is_file():
        raise SystemExit(f'Plugin fehlt: {PLUGIN_ORDNER / PLUGIN_QML}')
    paare = [(PLUGIN_ORDNER / PLUGIN_QML, qgs.with_suffix('.qml'))]
    paare += [(PLUGIN_ORDNER / n, qgs.parent / n) for n in PLUGIN_DATEIEN if (PLUGIN_ORDNER / n).is_file()]
    return paare


def plugin_kopieren(qgs, pruefen=False, still=False):
    """Kopiert abweichende Dateien; gibt die Liste der abweichenden Zielnamen zurück."""
    abweichend = []
    for quelle, ziel in plugin_paare(qgs):
        if ziel.is_file() and filecmp.cmp(quelle, ziel, shallow=False):
            if not still:
                print(f'  aktuell     {ziel.name}')
            continue
        abweichend.append(ziel.name)
        if pruefen:
            print(f'  VERALTET    {ziel.name}' if ziel.is_file() else f'  FEHLT       {ziel.name}')
        else:
            shutil.copy2(quelle, ziel)
            print(f'  kopiert     {ziel.name}')
    return abweichend


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('ziel', type=Path, help='QField-Projektordner (mit .qgs/.qgz)')
    ap.add_argument('--projekt', help='Name der Projektdatei, falls mehrere im Ordner liegen')
    ap.add_argument('--pruefen', action='store_true', help='nur vergleichen, nichts kopieren')
    a = ap.parse_args()

    qgs = projektdatei(a.ziel, a.projekt)
    print(f'Projekt: {qgs.name}  →  Plugin: {qgs.with_suffix(".qml").name}')
    abweichend = plugin_kopieren(qgs, a.pruefen)
    if a.pruefen and abweichend:
        print(f'\n{len(abweichend)} Datei(en) weichen von qfield_plugin/ ab. '
              f'Aktualisieren: python3 qfield/werkzeuge/{Path(__file__).name} {a.ziel}')
        sys.exit(1)


if __name__ == '__main__':
    main()
