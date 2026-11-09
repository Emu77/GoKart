#!/usr/bin/env python3
"""GoKart – spielt zusatztaxa.csv in ein VORHANDENES GoKart-GeoPackage ein (ohne Neubau, Erfassungen bleiben).

Aufruf:
    python3 zusatztaxa_einspielen.py <projekt.gpkg> [zusatztaxa.csv]

Ergänzt Tabelle taxon und suchnamen. Bereits vorhandene taxon_id oder wissenschaftliche Namen werden
übersprungen, das Skript kann also beliebig oft laufen. Vorher wird eine Sicherung angelegt.
QGIS/QField dabei geschlossen halten.
"""
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gokart_namen import normalisieren, varianten  # noqa: E402


def lesen(pfad):
    # gleiche Logik wie zusatz_taxa() in build_gokart_projekt.py, aber ohne QGIS-Abhängigkeit
    import csv
    with open(pfad, encoding='utf-8') as fh:
        for zeile in csv.DictReader((l for l in fh if not l.startswith('#')), delimiter=';'):
            wiss = (zeile.get('wissenschaftlicher_name') or '').strip()
            if not wiss:
                continue
            yield (int(zeile['taxon_id']), wiss, (zeile.get('deutscher_name') or '').strip() or None,
                   (zeile.get('rang') or 'SPE').strip(), (zeile.get('autor_name') or '').strip() or None,
                   [n.strip() for n in (zeile.get('weitere_namen') or '').split('|') if n.strip()])


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    gpkg = Path(sys.argv[1])
    csv_pfad = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).resolve().parent / 'zusatztaxa.csv'
    if not gpkg.is_file():
        raise SystemExit(f'Nicht gefunden: {gpkg}')

    sicherung = gpkg.with_name(f'{gpkg.stem}_{datetime.now():%Y%m%d_%H%M%S}.gpkg.bak')
    shutil.copy2(gpkg, sicherung)
    print(f'Sicherung: {sicherung}')

    con = sqlite3.connect(gpkg)
    ids = {r[0] for r in con.execute('SELECT taxon_id FROM taxon')}
    namen = {r[0] for r in con.execute('SELECT wissenschaftlicher_name FROM taxon')}
    neu = sn = 0
    for tid, wiss, deutsch, rang, autor, weitere in lesen(csv_pfad):
        if tid in ids or wiss in namen:
            print(f'  übersprungen (schon vorhanden): {wiss}')
            continue
        anzeige, var = varianten(deutsch)
        con.execute('INSERT INTO taxon (taxon_id, wissenschaftlicher_name, deutscher_name, anzeige_name, rang, '
                    'autor_name) VALUES (?,?,?,?,?,?)', (tid, wiss, deutsch, anzeige or wiss, rang, autor))
        neu += 1
        such = [(v, 'deutsch') for v in var] + [(wiss, 'wissenschaftlich')] + [(n, 'zusatz') for n in weitere]
        gesehen = set()
        for name, art in such:
            k = normalisieren(name)
            if k and k not in gesehen:
                gesehen.add(k)
                con.execute('INSERT INTO suchnamen (taxon_id, name, schluessel, art) VALUES (?,?,?,?)',
                            (tid, name, k, art))
                sn += 1
    # Objektzähler für QGIS aktuell halten
    for t in ('taxon', 'suchnamen'):
        con.execute('UPDATE gpkg_ogr_contents SET feature_count = (SELECT count(*) FROM "%s") '
                    'WHERE lower(table_name) = ?' % t, (t,))
    con.commit()
    con.close()
    print(f'Fertig: {neu} Taxa und {sn} Suchnamen ergänzt in {gpkg}')


if __name__ == '__main__':
    main()
