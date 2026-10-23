#!/usr/bin/env python3
"""GoKart – Artenliste je Fläche aus einem QField-Projekt (Ordner, .qgs oder Tablet-Export-Zip).

Aufruf:
    python3 artenliste_export.py ~/Dokumente/GoKart_Wohnung_2026-10-23_moose.zip
    python3 artenliste_export.py ~/QField/export/GoKart_Wohnung_QField -o ~/Gutachten/artenliste

Erzeugt <name>.html (druckbar, im Browser als PDF speichern) und <name>.csv.
Liest nur, verändert nichts. Benötigt kein QGIS.

Welche Layer Flächen und Artnachweise sind, steht in den GoKart-Projektvariablen
(gokart_flaechen_layer, gokart_flaechen_key, gokart_flaechen_label, gokart_nachweis_layer,
gokart_nachweis_fk). Ohne Variablen gelten die Standardnamen flaechen / artnachweise / flaeche_id.
"""
import argparse
import sqlite3
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'qgis_plugin' / 'gokart_desktop'))
from artenliste import csv_schreiben, html_schreiben  # noqa: E402

M2_FELDER = ('flaeche_m2', 'Flaeche_m2', 'flaeche', 'Flaeche', 'area', 'flaeche_qm')


def projekt_finden(pfad, tmp):
    pfad = Path(pfad).expanduser()
    if pfad.suffix.lower() == '.zip':
        with zipfile.ZipFile(pfad) as z:
            z.extractall(tmp)
        pfad = Path(tmp)
    if pfad.is_dir():
        qgs = sorted(pfad.rglob('*.qgs'))
        if not qgs:
            raise SystemExit(f'Keine .qgs-Datei in {pfad}')
        if len(qgs) > 1:
            print(f'Mehrere Projekte gefunden, nehme {qgs[0].name}: ' + ', '.join(q.name for q in qgs))
        return qgs[0]
    if pfad.suffix.lower() == '.qgs' and pfad.is_file():
        return pfad
    raise SystemExit(f'Nicht gefunden oder kein Projekt: {pfad}')


def projekt_lesen(qgs):
    root = ET.parse(qgs).getroot()
    layer = {}
    for ml in root.iter('maplayer'):
        lid, src, name = ml.findtext('id'), ml.findtext('datasource') or '', ml.findtext('layername')
        if not lid or '.gpkg' not in src:
            continue
        datei, _, rest = src.partition('|')
        tabelle = next((t.split('=', 1)[1] for t in rest.split('|') if t.startswith('layername=')), None)
        layer[lid] = {'datei': (qgs.parent / datei).resolve(), 'tabelle': tabelle, 'name': name}
    var = {}
    v = root.find('.//properties/Variables')
    if v is not None:
        namen = [e.text for e in v.findall('variableNames/value')]
        werte = [e.text for e in v.findall('variableValues/value')]
        var = dict(zip(namen, werte))
    return layer, var


def layer_suchen(layer, ref, standard):
    if ref and ref in layer:
        return layer[ref]
    for lid, l in layer.items():
        if l['name'] in (ref, standard) or l['tabelle'] in (ref, standard):
            return l
    return None


def spalten(con, tabelle):
    return [r[1] for r in con.execute(f'PRAGMA table_info("{tabelle}")')]


def daten_lesen(qgs):
    layer, var = projekt_lesen(qgs)
    an = layer_suchen(layer, var.get('gokart_nachweis_layer'), 'artnachweise')
    fl = layer_suchen(layer, var.get('gokart_flaechen_layer'), 'flaechen')
    tx = layer_suchen(layer, None, 'taxon')
    if not an:
        raise SystemExit('Layer mit Artnachweisen nicht gefunden.')
    fk = var.get('gokart_nachweis_fk') or 'flaeche_id'

    flaechen = {}
    if fl:
        con = sqlite3.connect(f'file:{fl["datei"]}?mode=ro', uri=True)
        cols = spalten(con, fl['tabelle'])
        key = var.get('gokart_flaechen_key') or 'flaeche_id'
        label = next((c for c in (var.get('gokart_flaechen_label'), 'name', 'Raum', 'Name') if c and c in cols), None)
        m2 = next((c for c in M2_FELDER if c in cols), None)
        if key in cols:
            sel = ', '.join(f'"{c}"' if c else 'NULL' for c in (key, label, m2))
            for k, n, a in con.execute(f'SELECT {sel} FROM "{fl["tabelle"]}"'):
                flaechen[str(k)] = (n, a)
        con.close()

    taxa = {}
    if tx:
        con = sqlite3.connect(f'file:{tx["datei"]}?mode=ro', uri=True)
        for tid, autor, rang in con.execute(f'SELECT taxon_id, autor_name, rang FROM "{tx["tabelle"]}"'):
            taxa[tid] = (autor, rang)
        con.close()

    con = sqlite3.connect(f'file:{an["datei"]}?mode=ro', uri=True)
    cols = spalten(con, an['tabelle'])
    eingabe = 'original_eingabe' if 'original_eingabe' in cols else 'NULL'
    nachweise = []
    for fid, tid, wiss, deutsch, ein, am in con.execute(
            f'SELECT "{fk}", taxon_id, wissenschaftlicher_name, deutscher_name, {eingabe}, erfasst_am '
            f'FROM "{an["tabelle"]}"'):
        name, m2 = flaechen.get(str(fid), (None, None))
        autor, rang = taxa.get(tid, (None, None))
        nachweise.append({'flaeche_id': fid, 'flaeche_name': name, 'flaeche_m2': m2, 'taxon_id': tid,
                          'wiss': wiss, 'autor': autor, 'deutsch': deutsch, 'rang': rang,
                          'eingabe': ein, 'erfasst_am': am})
    con.close()
    return nachweise


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('projekt', help='Projektordner, .qgs oder Tablet-Export (.zip)')
    ap.add_argument('-o', '--ausgabe', help='Ausgabe ohne Endung (Standard: artenliste_<Projekt> im aktuellen Ordner)')
    ap.add_argument('-t', '--titel', default='Artenliste je Fläche')
    a = ap.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        qgs = projekt_finden(a.projekt, tmp)
        nachweise = daten_lesen(qgs)
        ziel = Path(a.ausgabe).expanduser() if a.ausgabe else Path.cwd() / f'artenliste_{Path(a.projekt).stem}'
        ziel.parent.mkdir(parents=True, exist_ok=True)
        n_fl, n_tx = html_schreiben(ziel.with_suffix('.html'), nachweise, a.titel, Path(a.projekt).stem)
        csv_schreiben(ziel.with_suffix('.csv'), nachweise)
    print(f'{len(nachweise)} Nachweise, {n_fl} Flächen, {n_tx} Taxa')
    print(f'→ {ziel.with_suffix(".html")}\n→ {ziel.with_suffix(".csv")}')


if __name__ == '__main__':
    main()
