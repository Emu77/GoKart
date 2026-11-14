"""GoKart Desktop – Projekt fürs Tablet verpacken (ZIP für QField: „Projekt aus ZIP importieren“).

Ins ZIP kommen nur die Projektdatei, die Dateien der Layer (GeoPackage, Shape samt Begleitdateien …),
Fotos (fotos/, DCIM/) und das aktuelle QField-Plugin. GeoPackages werden über die SQLite-Backup-API
kopiert – so sind auch noch offene Änderungen (-wal) dabei und QGIS muss nicht geschlossen werden.
"""
import tempfile
import zipfile
from datetime import date
from pathlib import Path

from . import vorlage as V

FOTO_ORDNER = ('fotos', 'DCIM')
SQLITE_ENDUNGEN = ('.gpkg', '.sqlite', '.db')
WEGLASSEN_ENDUNGEN = ('~', '.bak', '-wal', '-shm', '-journal')
WARNUNG_MB = 50


def layer_quellen(projekt=None):
    """[(Layername, Dateipfad)] aller dateibasierten Layer des Projekts (online-Dienste fehlen)."""
    from qgis.core import QgsProject, QgsProviderRegistry
    projekt = projekt or QgsProject.instance()
    reg = QgsProviderRegistry.instance()
    quellen = []
    for lyr in projekt.mapLayers().values():
        try:
            teile = reg.decodeUri(lyr.providerType(), lyr.source())
        except Exception:
            teile = {}
        pfad = teile.get('path') or ''
        if pfad and Path(pfad).exists():
            quellen.append((lyr.name(), Path(pfad)))
    return quellen


def innerhalb(pfad, home):
    try:
        Path(pfad).resolve().relative_to(Path(home).resolve())
        return True
    except ValueError:
        return False


def dateien_sammeln(home, projektdatei, quellen):
    """Gibt (dateien, aussen) zurück: dateien = sortierte Pfade relativ zu home,
    aussen = [(Layername, Pfad)] der Layer außerhalb des Projektordners."""
    home = Path(home).resolve()
    gefunden, aussen = set(), []

    def dazu(p):
        p = Path(p).resolve()
        if p.is_file() and not p.name.endswith(WEGLASSEN_ENDUNGEN) and innerhalb(p, home):
            gefunden.add(p.relative_to(home))

    projektdatei = Path(projektdatei).resolve()
    dazu(projektdatei)
    anhang = projektdatei.with_name(projektdatei.stem + '_attachments.zip')
    if anhang.is_file():
        dazu(anhang)
    for name, pfad in quellen:
        pfad = Path(pfad).resolve()
        if not innerhalb(pfad, home):
            aussen.append((name, pfad))
            continue
        if pfad.is_dir():                       # z. B. Ordner mit Shapes
            for q in pfad.rglob('*'):
                dazu(q)
        elif pfad.suffix.lower() == '.shp':     # Begleitdateien .shx .dbf .prj .cpg .qix …
            for q in pfad.parent.glob(pfad.stem + '.*'):
                dazu(q)
        else:
            dazu(pfad)
    for ordner in FOTO_ORDNER:
        if (home / ordner).is_dir():
            for q in (home / ordner).rglob('*'):
                dazu(q)
    aussen = sorted(set(aussen), key=lambda x: x[0].lower())
    return sorted(gefunden, key=lambda p: p.as_posix()), aussen


def zip_name(home):
    return Path(home).resolve().parent / f'{Path(home).name}_{date.today():%Y-%m-%d}.zip'


def zip_schreiben(home, dateien, ziel, plugin_paare=()):
    """dateien relativ zu home; plugin_paare = [(Quelle, Name im ZIP)] (ersetzt gleichnamige Dateien).
    Gibt (Anzahl Dateien, Größe in MB) zurück."""
    home, ziel = Path(home), Path(ziel)
    plugin_namen = {name for _q, name in plugin_paare}
    tmp = ziel.with_name(ziel.name + '.tmp')
    n = 0
    with tempfile.TemporaryDirectory() as arbeit, zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as z:
        for rel in dateien:
            rel = Path(rel)
            if rel.as_posix() in plugin_namen or (home / rel).resolve() == ziel.resolve():
                continue
            quelle = home / rel
            if quelle.suffix.lower() in SQLITE_ENDUNGEN:
                kopie = Path(arbeit) / f'{n}_{quelle.name}'
                V.kopie_sichern(quelle, kopie)
                quelle = kopie
            z.write(quelle, rel.as_posix())
            n += 1
        for q, name in plugin_paare:
            z.write(q, name)
            n += 1
        if not any(Path(d).parts[0] == 'fotos' for d in dateien if Path(d).parts):
            z.writestr('fotos/', '')            # QField legt Fotos dort ab (Pfad im Plugin)
    tmp.replace(ziel)
    return n, ziel.stat().st_size / 1e6
