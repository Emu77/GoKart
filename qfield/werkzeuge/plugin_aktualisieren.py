#!/usr/bin/env python3
"""GoKart – kopiert das Projekt-Plugin aus qfield/plugin/ in ein vorhandenes QField-Projekt.

Quelle des Plugins ist immer qfield/plugin/. Projektordner (z. B. gokart_qfield/) enthalten nur Kopien.
Anders als build_gokart_projekt.py bleiben gokart.gpkg und gokart.qgs unangetastet – keine Erfassung geht verloren.

Aufruf (aus dem Repo-Hauptordner):
    python3 qfield/werkzeuge/plugin_aktualisieren.py gokart_qfield            # kopieren
    python3 qfield/werkzeuge/plugin_aktualisieren.py gokart_qfield --pruefen  # nur vergleichen, Exit-Code 1 bei Abweichung
"""
import argparse
import filecmp
import shutil
import sys
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent / 'plugin'
DATEIEN = ('gokart.qml', 'gokart_suche.js', 'gokart_icon.svg')


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('ziel', type=Path, help='Projektordner mit gokart.qgs')
    ap.add_argument('--pruefen', action='store_true', help='nur vergleichen, nichts kopieren')
    a = ap.parse_args()

    if not (a.ziel / 'gokart.qgs').is_file():
        raise SystemExit(f'Kein QField-Projekt: {a.ziel / "gokart.qgs"} fehlt.')

    abweichend = []
    for name in DATEIEN:
        quelle, kopie = PLUGIN / name, a.ziel / name
        if not quelle.is_file():
            continue
        gleich = kopie.is_file() and filecmp.cmp(quelle, kopie, shallow=False)
        if gleich:
            print(f'  aktuell     {name}')
            continue
        abweichend.append(name)
        if a.pruefen:
            print(f'  VERALTET    {name}' if kopie.is_file() else f'  FEHLT       {name}')
        else:
            shutil.copy2(quelle, kopie)
            print(f'  kopiert     {name}')

    if a.pruefen and abweichend:
        print(f'\n{len(abweichend)} Datei(en) weichen von qfield/plugin/ ab. '
              f'Aktualisieren: python3 qfield/werkzeuge/{Path(__file__).name} {a.ziel}')
        sys.exit(1)


if __name__ == '__main__':
    main()
