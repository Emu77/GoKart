#!/usr/bin/env python3
"""GoKart – baut das installierbare Plugin-ZIP für QGIS („Erweiterungen → Aus ZIP installieren“).

Das ZIP enthält alles, was Kartierer/innen brauchen – ohne Repo, ohne Kommandozeile:
    gokart_desktop/                 QGIS-Plugin (qgis_plugin/gokart_desktop)
    gokart_desktop/qfield_plugin/   QField-Plugin (kommt beim Verpacken automatisch ins Tablet-ZIP)
    gokart_desktop/werkzeuge/       abgleich.py, build_gokart_projekt.py, artenliste_export.py, gokart_namen.py
    gokart_desktop/vorlage/         gokart.gpkg (Artenliste; Erfassungen werden geleert)

Aufruf (aus dem Repo-Hauptordner):
    python3 werkzeuge/plugin_zip.py --vorlage /pfad/zur/gokart.gpkg
    python3 werkzeuge/plugin_zip.py --vorlage … --ziel ~/Schreibtisch
    python3 werkzeuge/plugin_zip.py                    # ohne Vorlage: der Assistent fragt dann nach einer gokart.gpkg

Eine Vorlage entsteht z. B. mit
    python3 werkzeuge/build_gokart_projekt.py --db …/GoKart_Pflanzen.sqlite --germansl … --ziel /tmp/vorlage --leer
Die Vorlage enthält die Artenliste (BfN/GermanSL) – das ZIP deshalb nicht öffentlich ins Repo stellen.
"""
import argparse
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PLUGIN = REPO / 'qgis_plugin' / 'gokart_desktop'
QFIELD = REPO / 'qfield_plugin'
WERKZEUGE = ('abgleich.py', 'build_gokart_projekt.py', 'artenliste_export.py', 'gokart_namen.py',
             'zusatznamen.csv', 'zusatztaxa.csv')
WEGLASSEN = ('__pycache__', '.pyc', '~', '.bak', '-wal', '-shm', '.gpkg')

sys.path.insert(0, str(PLUGIN))
import vorlage as V  # noqa: E402


def version():
    for z in (PLUGIN / 'metadata.txt').read_text(encoding='utf-8').splitlines():
        if z.startswith('version='):
            return z.split('=', 1)[1].strip()
    return '0'


def weglassen(p):
    return any(p.name.endswith(e) or e in p.parts for e in WEGLASSEN)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0], epilog=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--vorlage', type=Path, help='gokart.gpkg mit Artenliste (z. B. aus build_gokart_projekt.py --leer)')
    ap.add_argument('--ziel', type=Path, default=REPO, help='Ordner für das ZIP (Standard: Repo-Hauptordner)')
    a = ap.parse_args(argv)

    if a.vorlage:
        fehlt = V.pruefen(a.vorlage) if a.vorlage.is_file() else ['Datei']
        if fehlt:
            raise SystemExit(f'Keine GoKart-Vorlage: {a.vorlage} (fehlt: {", ".join(fehlt)})')
    name = f'GoKart_Desktop_{version()}.zip'
    ziel = a.ziel.expanduser().resolve() / name
    with tempfile.TemporaryDirectory() as tmp:
        basis = Path(tmp) / 'gokart_desktop'
        shutil.copytree(PLUGIN, basis, ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*~', '*.bak',
                                                                     'qfield_plugin', 'werkzeuge', 'vorlage'))
        (basis / 'qfield_plugin').mkdir()
        for p in QFIELD.iterdir():
            if p.is_file() and not weglassen(p):
                shutil.copy2(p, basis / 'qfield_plugin' / p.name)
        (basis / 'werkzeuge').mkdir()
        for n in WERKZEUGE:
            if (REPO / 'werkzeuge' / n).is_file():
                shutil.copy2(REPO / 'werkzeuge' / n, basis / 'werkzeuge' / n)
        if a.vorlage:
            (basis / 'vorlage').mkdir()
            gpkg = V.kopie_sichern(a.vorlage, basis / 'vorlage' / 'gokart.gpkg')
            geleert = {t: n for t, n in V.erfassungen_leeren(gpkg, vacuum=True).items() if n}
            print(f'Vorlage: {a.vorlage.name} ({gpkg.stat().st_size / 1e6:.1f} MB)'
                  + (', geleert: ' + ', '.join(f'{t} ({n})' for t, n in geleert.items()) if geleert else ''))
        else:
            print('Hinweis: ohne --vorlage – der Assistent „Neues Projekt“ fragt dann nach einer gokart.gpkg.')
        tmpzip = ziel.with_name(ziel.name + '.tmp')
        with zipfile.ZipFile(tmpzip, 'w', zipfile.ZIP_DEFLATED) as z:
            for p in sorted(basis.rglob('*')):
                if p.is_file():
                    z.write(p, p.relative_to(Path(tmp)).as_posix())
        tmpzip.replace(ziel)
    print(f'✔ {ziel}  ({ziel.stat().st_size / 1e6:.1f} MB)')
    print('Installieren: QGIS → Erweiterungen → Erweiterungen verwalten und installieren → Aus ZIP installieren')
    return ziel


if __name__ == '__main__':
    main()
