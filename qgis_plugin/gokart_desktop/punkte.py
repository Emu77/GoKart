"""GoKart – Punktaufnahmen (GPS-Standorte ohne Flächen-Shape) und Zusatzangaben zu Artnachweisen.

Reines Python (sqlite3 + XML), ohne QGIS – gemeinsam für Desktop-Plugin, build_gokart_projekt.py und abgleich.py.

Datenmodell
  aufnahme_punkte (Punkt-Layer, KBS wie die Flächen)
      punkt_id        eindeutige ID, z. B. P-20261107-141233-k7x2 (vergibt das QField-Plugin)
      erfasst_am, geaendert_am, bearbeiter
      gps_genauigkeit horizontale Genauigkeit [m] laut Positionsquelle
      hoehe           [m], falls bekannt
      pos_quelle      gps | manuell (Kartenmitte) | korrigiert (verschoben)
      biotoptyp       optional, Code im geltenden Schlüssel
      flaeche_id      optional, nachträglich per „Punkte Flächen zuordnen“
      bemerkung
  artnachweise bekommt zusätzlich
      punkt_id        Verweis auf aufnahme_punkte – genau eins von flaeche_id / punkt_id ist gesetzt
      deckung, anzahl, phaenologie   Zusatzangaben (alle optional, siehe ZUSATZ)

Projektvariablen
  gokart_punkt_genauigkeit   Warnschwelle GPS-Genauigkeit [m] (Standard 10)
  gokart_punkt_radius        Hinweis „neue Aufnahme?“ ab dieser Entfernung zum aktiven Punkt [m] (Standard 25)
  gokart_zusatz              welche Zusatzangaben QField abfragt, z. B. "deckung,phaenologie" (leer = keine)
"""
import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path

T_PUNKTE = 'aufnahme_punkte'
LAYER_ID = 'gokart_aufnahme_punkte'
GEOM = 'geom'
VAR_GENAUIGKEIT, VAR_RADIUS, VAR_ZUSATZ = 'gokart_punkt_genauigkeit', 'gokart_punkt_radius', 'gokart_zusatz'
STANDARD_GENAUIGKEIT, STANDARD_RADIUS = 10, 25
QUELLEN = ('gps', 'manuell', 'korrigiert')

PUNKT_SPALTEN = (('punkt_id', 'TEXT'), ('erfasst_am', 'TEXT'), ('geaendert_am', 'TEXT'), ('bearbeiter', 'TEXT'),
                 ('gps_genauigkeit', 'REAL'), ('hoehe', 'REAL'), ('pos_quelle', 'TEXT'), ('biotoptyp', 'TEXT'),
                 ('flaeche_id', 'TEXT'), ('bemerkung', 'TEXT'))
# Beim Abgleich: bei unterschiedlichem geaendert_am gewinnt der neuere Stand (auch die Geometrie)
PUNKT_FELDER = ('geom', 'gps_genauigkeit', 'hoehe', 'pos_quelle', 'biotoptyp', 'flaeche_id', 'bemerkung',
                'bearbeiter', 'geaendert_am')

# Zusatzangaben je Artnachweis: Feld -> (Anzeigename, erlaubte Werte; leer = frei)
DECKUNG = ('r', '+', '1', '2m', '2a', '2b', '3', '4', '5')            # Braun-Blanquet (Wilmanns)
ANZAHL = ('1', '2–5', '6–25', '26–100', '>100')                       # Klassen; Ganzzahlen sind auch erlaubt
PHAENOLOGIE = ('vegetativ', 'Knospe', 'blühend', 'fruchtend', 'abgestorben')
ZUSATZ = {'deckung': ('Deckung', DECKUNG), 'anzahl': ('Anzahl', ANZAHL), 'phaenologie': ('Phänologie', PHAENOLOGIE)}
NACHWEIS_SPALTEN = (('punkt_id', 'TEXT'), ('deckung', 'TEXT'), ('anzahl', 'TEXT'), ('phaenologie', 'TEXT'))


def zusatz_lesen(text):
    """Variablenwert -> Liste der aktiven Zusatzangaben in fester Reihenfolge. Leer = keine."""
    teile = {t.strip().lower() for t in str(text or '').replace(';', ',').split(',')}
    return [z for z in ZUSATZ if z in teile]


def zusatz_pruefen(text):
    teile = [t.strip().lower() for t in str(text or '').replace(';', ',').split(',') if t.strip()]
    falsch = [t for t in teile if t not in ZUSATZ]
    if falsch:
        raise ValueError(f'Unbekannte Zusatzangaben: {", ".join(falsch)} (erlaubt: {", ".join(ZUSATZ)})')
    return [z for z in ZUSATZ if z in teile]


def ort_schluessel(d, fk='flaeche_id'):
    """Ort eines Artnachweises als Text: Flächen-ID oder '@' + punkt_id (für Abgleich-Schlüssel und 'ersetzt')."""
    fl = d.get(fk)
    if fl not in (None, ''):
        return str(fl)
    p = d.get('punkt_id')
    return '@' + str(p) if p not in (None, '') else ''


# ------------------------------------------------------------------ GeoPackage
def hat_tabelle(con, tabelle):
    return bool(con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (tabelle,)).fetchone())


def spalten(con, tabelle):
    return [r[1] for r in con.execute(f'PRAGMA table_info("{tabelle}")')]


def srs_finden(con, crs=None):
    """srs_id für die Punkt-Tabelle: wie die Flächen, sonst die erste Geometrie-Tabelle, sonst crs (EPSG:…)."""
    for sql, arg in (("SELECT srs_id FROM gpkg_geometry_columns WHERE table_name = 'flaechen'", ()),
                     ('SELECT srs_id FROM gpkg_geometry_columns WHERE srs_id > 0 ORDER BY table_name', ())):
        r = con.execute(sql, arg).fetchone()
        if r:
            return r[0]
    if crs and ':' in crs:
        org, code = crs.split(':', 1)
        r = con.execute('SELECT srs_id FROM gpkg_spatial_ref_sys WHERE upper(organization) = ? AND '
                        'organization_coordsys_id = ?', (org.upper(), int(code))).fetchone()
        if r:
            return r[0]
    raise ValueError('Kein Koordinatensystem in der GeoPackage gefunden (keine Flächen-Tabelle).')


def srs_info(gpkg_oder_con, srs_id):
    """(authid, wkt) eines srs_id."""
    con = sqlite3.connect(gpkg_oder_con) if not isinstance(gpkg_oder_con, sqlite3.Connection) else gpkg_oder_con
    try:
        r = con.execute('SELECT organization, organization_coordsys_id, definition FROM gpkg_spatial_ref_sys '
                        'WHERE srs_id = ?', (srs_id,)).fetchone()
    finally:
        if con is not gpkg_oder_con:
            con.close()
    return (f'{r[0].upper()}:{r[1]}', r[2]) if r else ('', '')


def punkt_srs(gpkg):
    con = sqlite3.connect(gpkg)
    try:
        r = con.execute('SELECT srs_id FROM gpkg_geometry_columns WHERE table_name = ?', (T_PUNKTE,)).fetchone()
        return r[0] if r else None
    finally:
        con.close()


def tabelle_anlegen(gpkg, crs=None):
    """Legt aufnahme_punkte als Punkt-Feature-Tabelle an (falls fehlend). Gibt True zurück, wenn neu angelegt."""
    con = sqlite3.connect(gpkg)
    try:
        if hat_tabelle(con, T_PUNKTE):
            return False
        srs = srs_finden(con, crs)
        felder = ', '.join(f'"{n}" {t}' for n, t in PUNKT_SPALTEN)
        con.execute(f'CREATE TABLE "{T_PUNKTE}" (fid INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, '
                    f'"{GEOM}" POINT, {felder})')
        con.execute(f'CREATE UNIQUE INDEX IF NOT EXISTS idx_{T_PUNKTE}_id ON "{T_PUNKTE}"(punkt_id)')
        con.execute("INSERT INTO gpkg_contents (table_name, data_type, identifier, last_change, srs_id) "
                    "VALUES (?, 'features', ?, strftime('%Y-%m-%dT%H:%M:%fZ','now'), ?)", (T_PUNKTE, T_PUNKTE, srs))
        con.execute('INSERT INTO gpkg_geometry_columns (table_name, column_name, geometry_type_name, srs_id, z, m) '
                    "VALUES (?, ?, 'POINT', ?, 0, 0)", (T_PUNKTE, GEOM, srs))
        if hat_tabelle(con, 'gpkg_ogr_contents'):
            con.execute('INSERT INTO gpkg_ogr_contents (table_name, feature_count) VALUES (?, 0)', (T_PUNKTE,))
        con.commit()
        return True
    finally:
        con.close()


def nachweis_tabelle(con):
    """Tabellenname der Artnachweise (Standard: artnachweise)."""
    return 'artnachweise' if hat_tabelle(con, 'artnachweise') else None


def fehlende_nachweisspalten(gpkg, tabelle='artnachweise'):
    con = sqlite3.connect(gpkg)
    try:
        if not hat_tabelle(con, tabelle):
            return []
        da = spalten(con, tabelle)
        return [(n, t) for n, t in NACHWEIS_SPALTEN if n not in da]
    finally:
        con.close()


def nachweisspalten_ergaenzen(gpkg, tabelle='artnachweise'):
    fehlend = fehlende_nachweisspalten(gpkg, tabelle)
    if fehlend:
        con = sqlite3.connect(gpkg)
        for n, t in fehlend:
            con.execute(f'ALTER TABLE "{tabelle}" ADD COLUMN "{n}" {t}')
        con.execute(f'CREATE INDEX IF NOT EXISTS idx_{tabelle}_punkt ON "{tabelle}"(punkt_id)')
        con.commit()
        con.close()
    return fehlend


# ------------------------------------------------------------------ Geometrie (GeoPackage-Blob, nur Punkte)
def punkt_xy(blob):
    """(x, y) aus einem GeoPackage-Geometrie-Blob mit Punkt; None bei leerer/anderer Geometrie."""
    import struct
    if not blob or bytes(blob[:2]) != b'GP':
        return None
    flags = blob[3]
    env = (flags >> 1) & 0x07
    off = 8 + {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}.get(env, 0)
    if flags & 0x10:                      # leere Geometrie
        return None
    wkb = bytes(blob[off:])
    e = '<' if wkb[0] == 1 else '>'
    typ = struct.unpack(e + 'I', wkb[1:5])[0] % 1000
    if typ != 1:
        return None
    return struct.unpack(e + 'dd', wkb[5:21])


def punkt_blob(x, y, srs_id):
    """GeoPackage-Blob für einen 2D-Punkt (ohne Envelope)."""
    import struct
    return b'GP' + bytes([0, 0b00000001]) + struct.pack('<i', srs_id) + struct.pack('<BIdd', 1, 1, x, y)


# ------------------------------------------------------------------ QGIS-Projekt (.qgs, XML)
def qgs_layer_im_projekt(qgs):
    root = ET.parse(qgs).getroot()
    return any(ml.findtext('id') == LAYER_ID or ml.findtext('layername') == T_PUNKTE for ml in root.iter('maplayer'))


def qgs_layer_eintragen(qgs, gpkg):
    """Trägt aufnahme_punkte als Punkt-Layer ins Projekt ein (oberster Layer im Baum). True, wenn neu."""
    qgs, gpkg = Path(qgs), Path(gpkg)
    if qgs_layer_im_projekt(qgs):
        return False
    srs = punkt_srs(gpkg)
    authid, wkt = srs_info(gpkg, srs) if srs is not None else ('', '')
    baum = ET.parse(qgs)
    root = baum.getroot()
    try:
        rel = './' + gpkg.resolve().relative_to(qgs.parent.resolve()).as_posix()
    except ValueError:
        rel = str(gpkg.resolve())
    quelle = f'{rel}|layername={T_PUNKTE}'
    ml = ET.SubElement(root.find('projectlayers'), 'maplayer', {
        'type': 'vector', 'geometry': 'Point', 'wkbType': 'Point', 'readOnly': '0'})
    for tag, text in (('id', LAYER_ID), ('datasource', quelle), ('layername', T_PUNKTE)):
        ET.SubElement(ml, tag).text = text
    if authid:
        sr = ET.SubElement(ET.SubElement(ml, 'srs'), 'spatialrefsys')
        ET.SubElement(sr, 'wkt').text = wkt
        ET.SubElement(sr, 'authid').text = authid
    ET.SubElement(ml, 'provider', {'encoding': 'UTF-8'}).text = 'ogr'
    ET.SubElement(ml, 'previewExpression').text = '"punkt_id"'
    wurzel = root.find('layer-tree-group')
    if wurzel is not None:
        knoten = ET.Element('layer-tree-layer', {
            'id': LAYER_ID, 'name': T_PUNKTE, 'source': quelle, 'providerKey': 'ogr',
            'checked': 'Qt::Checked', 'expanded': '0'})
        kinder = list(wurzel)
        pos = next((i for i, k in enumerate(kinder) if k.tag in ('layer-tree-layer', 'layer-tree-group')), len(kinder))
        wurzel.insert(pos, knoten)
    baum.write(qgs, encoding='utf-8', xml_declaration=True)
    return True


def einrichten(gpkg, qgs=None, crs=None):
    """Tabelle, Nachweis-Spalten und (optional) Layer im Projekt. Gibt eine Liste der Änderungen zurück."""
    neu = []
    if tabelle_anlegen(gpkg, crs):
        neu.append(f'Tabelle {T_PUNKTE}')
    sp = nachweisspalten_ergaenzen(gpkg)
    if sp:
        neu.append('Spalten artnachweise: ' + ', '.join(n for n, _ in sp))
    if qgs and qgs_layer_eintragen(qgs, gpkg):
        neu.append(f'Layer {T_PUNKTE} im Projekt')
    return neu
