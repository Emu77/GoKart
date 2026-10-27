#!/usr/bin/env python3
"""GoKart – macht aus einem QField-Projektordner ein Zip fürs Tablet (Telegram, Mail, USB).

1. aktuelles Plugin aus qfield_plugin/ neben die Projektdatei legen (passend benannt)
2. Ordner zippen – ohne Sicherungen (*~, *.bak) und ohne SQLite-Hilfsdateien (-wal, -shm)

Ablauf:
    QGIS → QField Sync → „Für QField verpacken“ (z. B. nach ~/QField/export/kobm)
    python3 qfield/werkzeuge/qfield_paket.py ~/QField/export/kobm
    → ~/QField/export/kobm.zip, in QField über „Projekt aus ZIP importieren“ öffnen

Optionen:
    --zip <Datei>     anderer Zielname (Standard: <Ordner>.zip daneben)
    --datum           Datum im Namen, z. B. kobm_2026-10-27.zip
    --projekt <Datei> falls mehrere .qgs/.qgz im Ordner liegen
"""
import argparse
import zipfile
from datetime import date
from pathlib import Path

from plugin_aktualisieren import plugin_kopieren, projektdatei

WEGLASSEN_ENDUNGEN = ('~', '.bak', '-wal', '-shm', '-journal')
WEGLASSEN_ORDNER = ('__pycache__', '.git')


def weglassen(p):
    return p.name.endswith(WEGLASSEN_ENDUNGEN) or any(t in WEGLASSEN_ORDNER for t in p.parts)


def wal_pruefen(ordner):
    """Nicht leere -wal-Dateien: GeoPackage noch in QGIS offen, letzte Änderungen fehlen sonst im Zip."""
    offen = [p for p in ordner.rglob('*-wal') if p.stat().st_size > 0]
    if offen:
        print('⚠ Noch offene GeoPackages (nicht leere -wal): ' + ', '.join(p.name for p in offen))
        print('  Projekt in QGIS schließen und erneut starten, sonst fehlen evtl. letzte Änderungen.')
    return not offen


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument('ordner', type=Path, help='QField-Projektordner (Export von QField Sync)')
    ap.add_argument('--zip', type=Path, help='Ziel-Zip (Standard: <Ordner>.zip daneben)')
    ap.add_argument('--datum', action='store_true', help='Datum an den Zip-Namen hängen')
    ap.add_argument('--projekt', help='Projektdatei, falls mehrere im Ordner liegen')
    a = ap.parse_args()

    ordner = a.ordner.expanduser().resolve()
    if not ordner.is_dir():
        raise SystemExit(f'Ordner nicht gefunden: {ordner}')
    qgs = projektdatei(ordner, a.projekt)

    print(f'Projekt: {qgs.name}')
    plugin_kopieren(qgs, still=True)
    wal_pruefen(ordner)

    name = ordner.name + (f'_{date.today():%Y-%m-%d}' if a.datum else '')
    ziel = (a.zip.expanduser() if a.zip else ordner.parent / f'{name}.zip').resolve()
    if ziel.is_relative_to(ordner):
        raise SystemExit('Das Zip darf nicht im Projektordner selbst liegen.')

    dateien = sorted(p for p in ordner.rglob('*') if p.is_file() and not weglassen(p.relative_to(ordner)))
    tmp = ziel.with_name(ziel.name + '.tmp')
    with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as z:
        for p in dateien:
            z.write(p, p.relative_to(ordner).as_posix())   # Dateien direkt im Zip-Wurzelverzeichnis
    tmp.replace(ziel)

    mb = ziel.stat().st_size / 1e6
    print(f'✔ {ziel}  ({len(dateien)} Dateien, {mb:.1f} MB)')
    if mb > 50:
        print('  Hinweis: über 50 MB – für Telegram/Mail evtl. zu groß (Fotos verkleinern oder USB nutzen).')


if __name__ == '__main__':
    main()
