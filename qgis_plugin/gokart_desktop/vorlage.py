"""GoKart – Vorlage-GeoPackage (gokart.gpkg) für neue Projekte vorbereiten.

Reines Python (sqlite3), ohne QGIS – genutzt vom Projekt-Assistenten im Plugin und von werkzeuge/plugin_zip.py.
Die Vorlage enthält die Artenliste (taxon, suchnamen), eigene Synonyme und ggf. Biotop-Kataloge.
Erfassungen (Artnachweise, Fotos, Punkte, Biotop-Zuordnungen, Flächen) werden geleert.
"""
import sqlite3
from pathlib import Path

ERFASSUNGEN = ('artnachweise', 'fotos', 'aufnahme_punkte', 'biotopzuordnung', 'flaechen')
PFLICHT = ('taxon', 'suchnamen', 'eigene_synonyme', 'artnachweise')


def tabellen(gpkg):
    con = sqlite3.connect(str(gpkg))
    try:
        return {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        con.close()


def pruefen(gpkg):
    """Fehlende Pflichttabellen (leer = brauchbare Vorlage)."""
    try:
        da = tabellen(gpkg)
    except sqlite3.DatabaseError:
        return list(PFLICHT)
    return [t for t in PFLICHT if t not in da]


def erfassungen_leeren(gpkg, vacuum=False):
    """Alle Erfassungen löschen; gibt {tabelle: gelöschte Zeilen} zurück."""
    con = sqlite3.connect(str(gpkg))
    geloescht = {}
    try:
        da = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for t in ERFASSUNGEN:
            if t in da:
                geloescht[t] = con.execute(f'DELETE FROM "{t}"').rowcount
                if 'gpkg_ogr_contents' in da:
                    con.execute('UPDATE gpkg_ogr_contents SET feature_count = 0 WHERE table_name = ?', (t,))
        con.commit()
        con.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        con.execute('PRAGMA journal_mode=DELETE')     # keine -wal-Datei in der Vorlage
        if vacuum:
            con.execute('VACUUM')
    finally:
        con.close()
    return geloescht


def kopie_sichern(quelle, ziel):
    """Konsistente Kopie einer (evtl. gerade in QGIS geöffneten) GeoPackage – über die SQLite-Backup-API,
    die auch noch nicht übernommene Änderungen aus der -wal-Datei mitnimmt."""
    ziel = Path(ziel)
    if ziel.exists():
        ziel.unlink()
    q = sqlite3.connect(Path(quelle).resolve().as_uri() + '?mode=ro', uri=True)
    z = sqlite3.connect(str(ziel))
    try:
        q.backup(z)
        z.execute('PRAGMA journal_mode=DELETE')
    finally:
        z.close()
        q.close()
    return ziel
