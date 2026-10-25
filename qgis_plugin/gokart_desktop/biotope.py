"""GoKart – Biotoptypen-Schlüssel (Bund und Länder): Kataloge, Tabellen im GeoPackage, Suche.

Reines Python (sqlite3/csv), ohne QGIS – wird vom Desktop-Plugin und von den Werkzeugen
(qfield/werkzeuge/biotope_einspielen.py, abgleich.py) gemeinsam genutzt.

Tabellen im GeoPackage der Artnachweise:
  biotop_schluessel  Welche Schlüssel eingespielt sind (BUND, SH, NI, …) mit Quelle/Stand
  biotoptypen        Katalog: schluessel, code, name, nr, obercode, ebene, bund_code, ffh_lrt (Referenz)
  biotopzuordnung    Erfassung: flaeche_id, schluessel, code, name, rolle (Haupt/Neben), anteil, … (wird bearbeitet)

Projektvariable gokart_biotop_schluessel legt fest, welcher Schlüssel im Projekt gilt.
"""
import csv
import difflib
import re
import sqlite3
import unicodedata
from pathlib import Path

KATALOG_ORDNER = Path(__file__).resolve().parent / 'biotope_kataloge'
ZUORDNUNG_BUND = 'zuordnung_bund.csv'
VAR_SCHLUESSEL = 'gokart_biotop_schluessel'

T_SCHLUESSEL, T_TYPEN, T_ZUORDNUNG = 'biotop_schluessel', 'biotoptypen', 'biotopzuordnung'
LAYER_IDS = {T_TYPEN: 'gokart_biotoptypen', T_ZUORDNUNG: 'gokart_biotopzuordnung', T_SCHLUESSEL: 'gokart_biotop_schluessel'}
ROLLEN = ('Haupt', 'Neben')

KATALOG_SPALTEN = ('code', 'name', 'nr', 'obercode', 'ebene', 'bund_code', 'ffh_lrt')
META_FELDER = ('schluessel', 'name', 'land', 'stand', 'quelle', 'url', 'vollstaendig', 'hinweis')

SQL = {
    T_SCHLUESSEL: f'''CREATE TABLE "{T_SCHLUESSEL}" (fid INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
        schluessel TEXT UNIQUE, name TEXT, land TEXT, stand TEXT, quelle TEXT, url TEXT,
        vollstaendig INTEGER, hinweis TEXT, anzahl INTEGER)''',
    T_TYPEN: f'''CREATE TABLE "{T_TYPEN}" (fid INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
        schluessel TEXT, code TEXT, name TEXT, nr TEXT, obercode TEXT, ebene INTEGER,
        bund_code TEXT, ffh_lrt TEXT, anzeige TEXT)''',
    T_ZUORDNUNG: f'''CREATE TABLE "{T_ZUORDNUNG}" (fid INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
        flaeche_id TEXT, schluessel TEXT, code TEXT, name TEXT, rolle TEXT, anteil INTEGER,
        bund_code TEXT, original_eingabe TEXT, erfasst_am TEXT, bemerkung TEXT)''',
}
SPALTEN = {   # ohne fid
    T_SCHLUESSEL: ('schluessel', 'name', 'land', 'stand', 'quelle', 'url', 'vollstaendig', 'hinweis', 'anzahl'),
    T_TYPEN: ('schluessel', 'code', 'name', 'nr', 'obercode', 'ebene', 'bund_code', 'ffh_lrt', 'anzeige'),
    T_ZUORDNUNG: ('flaeche_id', 'schluessel', 'code', 'name', 'rolle', 'anteil', 'bund_code', 'original_eingabe',
                  'erfasst_am', 'bemerkung'),
}
INDEX_SQL = (
    f'CREATE INDEX IF NOT EXISTS idx_biotoptypen_schluessel ON "{T_TYPEN}"(schluessel, code)',
    f'CREATE INDEX IF NOT EXISTS idx_biotopzuordnung_flaeche ON "{T_ZUORDNUNG}"(flaeche_id)',
)


# ---------------------------------------------------------------- Kataloge (CSV)
def katalog_lesen(pfad):
    """CSV mit Kopfzeilen '# feld: wert' und Spalten code;name;nr;obercode;ebene;bund_code;ffh_lrt."""
    meta, zeilen = {}, []
    with open(pfad, encoding='utf-8-sig', newline='') as f:
        daten = []
        for z in f:
            if z.startswith('#'):
                k, _, v = z[1:].partition(':')
                if v:
                    meta[k.strip()] = v.strip()
            elif z.strip():
                daten.append(z)
    for r in csv.DictReader(daten, delimiter=';'):
        r = {k: (r.get(k) or '').strip() for k in KATALOG_SPALTEN}
        if r['code'] and r['name']:
            r['ebene'] = int(r['ebene']) if r['ebene'].isdigit() else None
            zeilen.append(r)
    meta.setdefault('schluessel', Path(pfad).stem.upper())
    return meta, zeilen


def katalog_schreiben(pfad, meta, zeilen):
    with open(pfad, 'w', encoding='utf-8', newline='') as f:
        for k in META_FELDER:
            if meta.get(k) not in (None, ''):
                f.write(f'# {k}: {meta[k]}\n')
        w = csv.writer(f, delimiter=';', lineterminator='\n')
        w.writerow(KATALOG_SPALTEN)
        for r in zeilen:
            w.writerow(['' if r.get(k) is None else r.get(k) for k in KATALOG_SPALTEN])


def kataloge_finden(ordner=None):
    ordner = Path(ordner or KATALOG_ORDNER)
    return sorted(p for p in ordner.glob('*.csv') if p.name != ZUORDNUNG_BUND)


def zuordnung_bund_lesen(ordner=None):
    """{(schluessel, code): bund_code} aus zuordnung_bund.csv (Spalten schluessel;code;bund_code)."""
    pfad = Path(ordner or KATALOG_ORDNER) / ZUORDNUNG_BUND
    if not pfad.is_file():
        return {}
    with open(pfad, encoding='utf-8-sig', newline='') as f:
        zeilen = [z for z in f if z.strip() and not z.startswith('#')]
    return {(r['schluessel'].strip().upper(), r['code'].strip()): r['bund_code'].strip()
            for r in csv.DictReader(zeilen, delimiter=';') if r.get('bund_code', '').strip()}


def hierarchie_ergaenzen(zeilen):
    """obercode/ebene aus nr (1.7.1 → 1.7) bzw. aus dem Code (WMy → WM → W) ableiten, wo leer."""
    nach_nr = {r['nr']: r['code'] for r in zeilen if r.get('nr')}
    codes = {r['code'] for r in zeilen}
    for r in zeilen:
        if r.get('nr'):
            teile = r['nr'].split('.')
            r['ebene'] = r.get('ebene') or len(teile)
            if not r.get('obercode') and len(teile) > 1:
                r['obercode'] = nach_nr.get('.'.join(teile[:-1]), '')
        elif not r.get('obercode'):
            c = r['code']
            for n in range(len(c) - 1, 0, -1):
                if c[:n] in codes:
                    r['obercode'] = c[:n]
                    break
            r['ebene'] = r.get('ebene') or (1 + _tiefe(r['code'], {z['code']: z for z in zeilen}))
    return zeilen


def _tiefe(code, alle, n=0):
    for k in range(len(code) - 1, 0, -1):
        if code[:k] in alle:
            return _tiefe(code[:k], alle, n + 1)
    return n


def pruefen(zeilen):
    """Liefert Hinweise: doppelte Codes (auch nur in Groß-/Kleinschreibung verschieden), fehlende Oberbegriffe."""
    hinweise, gesehen = [], {}
    codes = {r['code'] for r in zeilen}
    for r in zeilen:
        k = r['code'].casefold()
        if k in gesehen:
            hinweise.append(f"Code doppelt: {r['code']} ({r['name']}) / {gesehen[k]}")
        gesehen[k] = r['code']
        if r.get('obercode') and r['obercode'] not in codes:
            hinweise.append(f"Oberbegriff {r['obercode']} zu {r['code']} fehlt")
    return hinweise


# ---------------------------------------------------------------- GeoPackage
def _registrieren(con, tabelle):
    if not con.execute("SELECT 1 FROM sqlite_master WHERE name='gpkg_contents'").fetchone():
        return
    if not con.execute('SELECT 1 FROM gpkg_contents WHERE lower(table_name)=lower(?)', (tabelle,)).fetchone():
        con.execute("INSERT INTO gpkg_contents (table_name, data_type, identifier, last_change) "
                    "VALUES (?, 'attributes', ?, strftime('%Y-%m-%dT%H:%M:%fZ','now'))", (tabelle, tabelle))
    if con.execute("SELECT 1 FROM sqlite_master WHERE name='gpkg_ogr_contents'").fetchone():
        n = con.execute(f'SELECT count(*) FROM "{tabelle}"').fetchone()[0]
        if con.execute('SELECT 1 FROM gpkg_ogr_contents WHERE lower(table_name)=lower(?)', (tabelle,)).fetchone():
            con.execute('UPDATE gpkg_ogr_contents SET feature_count=? WHERE lower(table_name)=lower(?)', (n, tabelle))
        else:
            con.execute('INSERT INTO gpkg_ogr_contents (table_name, feature_count) VALUES (?, ?)', (tabelle, n))


def hat_tabelle(con, tabelle):
    return bool(con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (tabelle,)).fetchone())


def tabellen_anlegen(gpkg):
    """Legt fehlende Biotop-Tabellen an. Gibt die Namen der neu angelegten zurück."""
    con = sqlite3.connect(str(gpkg))
    neu = []
    for t, sql in SQL.items():
        if not hat_tabelle(con, t):
            con.execute(sql)
            neu.append(t)
        _registrieren(con, t)
    for s in INDEX_SQL:
        con.execute(s)
    con.commit()
    con.close()
    return neu


def anzeige(r):
    return f"{r['code']} – {r['name']}"


def kataloge_einspielen(gpkg, pfade=None, nur=None, ordner=None):
    """Ersetzt die Katalogeinträge der gegebenen Schlüssel. Erfassungen (biotopzuordnung) bleiben unberührt.
    Gibt {schluessel: (anzahl, vollständig, hinweise)} zurück."""
    tabellen_anlegen(gpkg)
    bund = zuordnung_bund_lesen(ordner)
    ergebnis = {}
    con = sqlite3.connect(str(gpkg))
    for pfad in (pfade or kataloge_finden(ordner)):
        meta, zeilen = katalog_lesen(pfad)
        s = meta['schluessel'].upper()
        if nur and s not in nur:
            continue
        hierarchie_ergaenzen(zeilen)
        for r in zeilen:
            r['bund_code'] = r.get('bund_code') or bund.get((s, r['code']), '')
        con.execute(f'DELETE FROM "{T_TYPEN}" WHERE schluessel=?', (s,))
        con.executemany(
            f'INSERT INTO "{T_TYPEN}" (schluessel, code, name, nr, obercode, ebene, bund_code, ffh_lrt, anzeige) '
            'VALUES (?,?,?,?,?,?,?,?,?)',
            [(s, r['code'], r['name'], r['nr'] or None, r['obercode'] or None, r['ebene'],
              r['bund_code'] or None, r['ffh_lrt'] or None, anzeige(r)) for r in zeilen])
        voll = 1 if str(meta.get('vollstaendig', '')).lower() in ('1', 'ja', 'true') else 0
        con.execute(f'DELETE FROM "{T_SCHLUESSEL}" WHERE schluessel=?', (s,))
        con.execute(f'INSERT INTO "{T_SCHLUESSEL}" (schluessel, name, land, stand, quelle, url, vollstaendig, hinweis, '
                    'anzahl) VALUES (?,?,?,?,?,?,?,?,?)',
                    (s, meta.get('name'), meta.get('land'), meta.get('stand'), meta.get('quelle'), meta.get('url'),
                     voll, meta.get('hinweis'), len(zeilen)))
        ergebnis[s] = (len(zeilen), bool(voll), pruefen(zeilen))
    for t in SQL:
        _registrieren(con, t)
    con.commit()
    con.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    con.close()
    return ergebnis


def schluessel_liste(gpkg):
    """[(schluessel, name, anzahl, vollständig)] der eingespielten Schlüssel."""
    con = sqlite3.connect(str(gpkg))
    try:
        if not hat_tabelle(con, T_SCHLUESSEL):
            return []
        return [(r[0], r[1] or r[0], r[2] or 0, bool(r[3])) for r in con.execute(
            f'SELECT schluessel, name, anzahl, vollstaendig FROM "{T_SCHLUESSEL}" ORDER BY schluessel')]
    finally:
        con.close()


# ---------------------------------------------------------------- Suche (gleiche Regeln wie gokart_biotop.js)
BUCHSTABEN = {
    'a': 'a', 'ah': 'a', 'be': 'b', 'b': 'b', 'ce': 'c', 'c': 'c', 'zeh': 'c', 'de': 'd', 'd': 'd', 'e': 'e',
    'eh': 'e', 'ef': 'f', 'eff': 'f', 'f': 'f', 'ge': 'g', 'g': 'g', 'ha': 'h', 'h': 'h', 'i': 'i', 'ih': 'i',
    'jot': 'j', 'j': 'j', 'ka': 'k', 'k': 'k', 'el': 'l', 'l': 'l', 'em': 'm', 'm': 'm', 'en': 'n', 'n': 'n',
    'o': 'o', 'oh': 'o', 'pe': 'p', 'p': 'p', 'ku': 'q', 'q': 'q', 'er': 'r', 'r': 'r', 'es': 's', 's': 's',
    'te': 't', 't': 't', 'u': 'u', 'uh': 'u', 'vau': 'v', 'v': 'v', 'we': 'w', 'w': 'w', 'ix': 'x', 'x': 'x',
    'ypsilon': 'y', 'y': 'y', 'zett': 'z', 'zet': 'z', 'z': 'z',
}


def norm(s):
    s = unicodedata.normalize('NFKD', str(s or '').casefold().replace('ß', 'ss'))
    return ''.join(c for c in s if not unicodedata.combining(c))


def kompakt(s):
    return re.sub(r'[^a-z0-9]', '', norm(s))


def code_aus_sprache(text):
    """'W M Ypsilon' / 'we em ypsilon' / 'WMY' → 'wmy'; sonst None."""
    t = [w for w in re.split(r'[\s,.\-]+', norm(text)) if w]
    if not t or len(t) > 5:
        return None
    if len(t) == 1 and len(t[0]) <= 4:
        return t[0]
    b = [BUCHSTABEN.get(w) for w in t]
    if all(b):
        return ''.join(b)
    if all(len(w) == 1 or w.replace('.', '').isdigit() for w in t):   # z. B. "34 07 01"
        return ''.join(t)
    return None


def bewerten(eingabe, typ):
    """0..1 – Code exakt > Name exakt > Code-Anfang > Name-Anfang > alle Wörter enthalten > ähnlich."""
    q, qk = norm(eingabe).strip(), kompakt(eingabe)
    if not qk:
        return 0.0
    code = kompakt(typ['code'])
    sprach = code_aus_sprache(eingabe)
    if qk == code or (sprach and sprach == code):
        return 1.0
    name, nk = norm(typ['name']), kompakt(typ['name'])
    if qk == nk:
        return 0.97
    if len(qk) >= 2 and len(qk) <= 4 and code.startswith(qk):
        return 0.9 - 0.02 * (len(code) - len(qk))
    if nk.startswith(qk):
        return 0.88
    woerter = [kompakt(w) for w in q.split() if kompakt(w)]
    if woerter and all(w in nk for w in woerter):
        return 0.8 + 0.05 * min(1.0, len(qk) / max(1, len(nk)))
    teile = re.split(r'[\s\-,()/]+', name)
    best = max([difflib.SequenceMatcher(None, qk, kompakt(t)).ratio() for t in teile if t] + [0])
    gesamt = difflib.SequenceMatcher(None, qk, nk).ratio()
    return 0.7 * max(best if len(woerter) == 1 else 0, gesamt)


def suchen(typen, eingabe, anzahl=6, schwelle=0.5):
    """typen: [{'code','name','ebene',…}]. Tiefere Ebene (eigentlicher Biotoptyp) vor Obergruppe bei Gleichstand."""
    if not kompakt(eingabe):
        return []
    werte = [(bewerten(eingabe, t), t) for t in typen]
    werte = [w for w in werte if w[0] >= schwelle]
    werte.sort(key=lambda w: (-round(w[0], 3), -(w[1].get('ebene') or 0), w[1]['code']))
    return [t for _, t in werte[:anzahl]]


# ---------------------------------------------------------------- QGIS-Projektdatei (.qgs als XML, ohne QGIS)
def qgs_layer_ids(qgs):
    import xml.etree.ElementTree as ET
    return {ml.findtext('id') for ml in ET.parse(qgs).getroot().iter('maplayer')}


def qgs_layer_eintragen(qgs, gpkg, tabellen=None):
    """Trägt fehlende Biotop-Tabellen als Layer (ohne Geometrie) ins Projekt ein, Katalog schreibgeschützt.
    Gibt die eingetragenen Tabellen zurück."""
    import xml.etree.ElementTree as ET
    qgs, gpkg = Path(qgs), Path(gpkg)
    baum = ET.parse(qgs)
    root = baum.getroot()
    vorhanden = {ml.findtext('id') for ml in root.iter('maplayer')}
    try:
        rel = './' + gpkg.resolve().relative_to(qgs.parent.resolve()).as_posix()
    except ValueError:
        rel = str(gpkg.resolve())
    projektlayer = root.find('projectlayers')
    baumwurzel = root.find('layer-tree-group')
    neu = []
    for t in (tabellen or (T_ZUORDNUNG, T_TYPEN, T_SCHLUESSEL)):
        lid = LAYER_IDS[t]
        if lid in vorhanden:
            continue
        quelle = f'{rel}|layername={t}'
        nur_lesen = '0' if t == T_ZUORDNUNG else '1'
        ml = ET.SubElement(projektlayer, 'maplayer', {
            'type': 'vector', 'geometry': 'No geometry', 'wkbType': 'NoGeometry', 'readOnly': nur_lesen})
        for tag, text in (('id', lid), ('datasource', quelle), ('layername', t)):
            ET.SubElement(ml, tag).text = text
        ET.SubElement(ml, 'provider', {'encoding': 'UTF-8'}).text = 'ogr'
        if baumwurzel is not None:
            ET.SubElement(baumwurzel, 'layer-tree-layer', {
                'id': lid, 'name': t, 'source': quelle, 'providerKey': 'ogr',
                'checked': 'Qt::Checked', 'expanded': '0'})
        neu.append(t)
    if neu:
        baum.write(qgs, encoding='utf-8', xml_declaration=True)
    return neu


def qgs_variable(qgs, name):
    import xml.etree.ElementTree as ET
    v = ET.parse(qgs).getroot().find('properties/Variables')
    if v is None:
        return None
    namen = [e.text for e in v.findall('variableNames/value')]
    werte = [e.text for e in v.findall('variableValues/value')]
    return dict(zip(namen, werte)).get(name)


def qgs_variable_setzen(qgs, name, wert):
    """Projektvariable in der .qgs setzen (wie Projekt → Eigenschaften → Variablen)."""
    import xml.etree.ElementTree as ET
    baum = ET.parse(qgs)
    root = baum.getroot()
    props = root.find('properties')
    if props is None:
        props = ET.SubElement(root, 'properties')
    v = props.find('Variables')
    if v is None:
        v = ET.SubElement(props, 'Variables')
    namen = v.find('variableNames')
    werte = v.find('variableValues')
    if namen is None:
        namen = ET.SubElement(v, 'variableNames', {'type': 'QStringList'})
    if werte is None:
        werte = ET.SubElement(v, 'variableValues', {'type': 'QStringList'})
    nl, wl = namen.findall('value'), werte.findall('value')
    for n, w in zip(nl, wl):
        if n.text == name:
            w.text = wert
            break
    else:
        ET.SubElement(namen, 'value').text = name
        ET.SubElement(werte, 'value').text = wert
    baum.write(qgs, encoding='utf-8', xml_declaration=True)
