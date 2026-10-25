#!/usr/bin/env python3
"""GoKart – Biotoptypen-Schlüssel (Bund/Länder) in ein vorhandenes GoKart-Projekt einspielen.

Aufruf:
    python3 biotope_einspielen.py <Projekt (.qgs oder Ordner)> --schluessel SH
    python3 biotope_einspielen.py <Projekt> --nur SH,NI           # nur diese Kataloge (neu) einspielen
    python3 biotope_einspielen.py <Projekt> --liste               # zeigt, was im Projekt und im Katalogordner ist

Was passiert:
  * In der GeoPackage der Artnachweise entstehen/aktualisieren sich die Tabellen
    biotop_schluessel, biotoptypen (Katalog, wird ersetzt) und biotopzuordnung (Erfassungen, bleiben erhalten).
  * Die Tabellen werden als Layer ins Projekt eingetragen (fürs QField-Plugin nötig).
  * --schluessel setzt die Projektvariable gokart_biotop_schluessel (welcher Schlüssel im Projekt gilt).
  * Vorher wird von GeoPackage und .qgs eine Sicherung *.bak angelegt.

Kataloge liegen in qgis_plugin/gokart_desktop/biotope_kataloge/*.csv (ergänzen mit biotope_katalog_import.py).
Fürs Tablet anschließend abgleich.py laufen lassen – das bringt Katalog, Layer und Variable mit ins Zip.
QGIS vorher schließen bzw. das Projekt nicht geöffnet haben.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'qgis_plugin' / 'gokart_desktop'))
import biotope as B  # noqa: E402
from abgleich import sichern, wal_pruefen  # noqa: E402
from artenliste_export import layer_suchen, projekt_finden, projekt_lesen  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('projekt', help='.qgs oder Projektordner (kein Zip)')
    ap.add_argument('--schluessel', help='im Projekt geltender Schlüssel, z. B. SH, NI, BUND')
    ap.add_argument('--nur', help='nur diese Kataloge einspielen, kommagetrennt (Standard: alle)')
    ap.add_argument('--kataloge', type=Path, default=B.KATALOG_ORDNER, help='Ordner mit Katalog-CSVs')
    ap.add_argument('--liste', action='store_true', help='nur anzeigen, nichts ändern')
    a = ap.parse_args()

    if Path(a.projekt).suffix.lower() == '.zip':
        raise SystemExit('Bitte einen Ordner oder eine .qgs angeben. Fürs Tablet abgleich.py verwenden.')
    qgs = projekt_finden(a.projekt, None)
    layer, var = projekt_lesen(qgs)
    an = layer_suchen(layer, var.get('gokart_nachweis_layer'), 'artnachweise')
    if not an:
        raise SystemExit(f'Layer mit Artnachweisen nicht gefunden ({qgs}) – Biotop-Tabellen kommen in dieselbe GeoPackage.')
    gpkg = an['datei']

    kataloge = B.kataloge_finden(a.kataloge)
    print(f'Projekt: {qgs}\nGeoPackage: {gpkg}')
    print('Kataloge im Ordner: ' + ', '.join(
        f"{B.katalog_lesen(p)[0]['schluessel']} ({len(B.katalog_lesen(p)[1])})" for p in kataloge))
    im_projekt = B.schluessel_liste(gpkg)
    print('Im Projekt: ' + (', '.join(f'{s} ({n}{"" if v else ", unvollständig"})' for s, _, n, v in im_projekt)
                            or 'noch keine'))
    print(f'Projektvariable {B.VAR_SCHLUESSEL}: {B.qgs_variable(qgs, B.VAR_SCHLUESSEL) or "-"}')
    if a.liste:
        return

    nur = {s.strip().upper() for s in a.nur.split(',')} if a.nur else None
    verfuegbar = {B.katalog_lesen(p)[0]['schluessel'].upper() for p in kataloge}
    if a.schluessel and a.schluessel.upper() not in verfuegbar | {s for s, *_ in im_projekt}:
        raise SystemExit(f'Schlüssel {a.schluessel} gibt es nicht. Verfügbar: {", ".join(sorted(verfuegbar))}')
    if not wal_pruefen([gpkg]):
        raise SystemExit('Abgebrochen.')
    sichern([gpkg, qgs])

    ergebnis = B.kataloge_einspielen(gpkg, kataloge, nur)
    for s, (n, voll, hinweise) in sorted(ergebnis.items()):
        print(f'  {s}: {n} Biotoptypen{"" if voll else " (Katalog als unvollständig markiert)"}')
        for h in hinweise[:10]:
            print(f'    ⚠ {h}')
    neu = B.qgs_layer_eintragen(qgs, gpkg)
    if neu:
        print('Layer eingetragen: ' + ', '.join(neu))
    if a.schluessel:
        B.qgs_variable_setzen(qgs, B.VAR_SCHLUESSEL, a.schluessel.upper())
        print(f'{B.VAR_SCHLUESSEL} = {a.schluessel.upper()}')
    elif not B.qgs_variable(qgs, B.VAR_SCHLUESSEL):
        print('Hinweis: Noch kein Schlüssel gewählt – mit --schluessel <X> oder in QGIS über „Einrichten…“.')
    print('✓ Fertig.')


if __name__ == '__main__':
    main()
