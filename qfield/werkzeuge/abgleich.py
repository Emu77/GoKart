#!/usr/bin/env python3
"""GoKart – gleicht Artnachweise, Fotos und eigene Synonyme zwischen PC-Projekt und Tablet-Export ab.

Aufruf:
    python3 abgleich.py <PC-Projekt (.qgs oder Ordner)> <Tablet-Export (.zip oder Ordner)>
        → zeigt nur die Unterschiede, ändert nichts
    python3 abgleich.py <PC> <Tablet> --ausfuehren
    python3 abgleich.py qfield_projekt tablet.zip --pc-projekt GoKart_Wohnung.qgz
        → bei mehreren Projekten im Ordner das richtige wählen (.qgs und .qgz gehen beide)
        → ergänzt fehlende Einträge auf BEIDEN Seiten:
          * PC-Projekt wird direkt aktualisiert (vorher Sicherung *.bak)
          * fürs Tablet entsteht ein neues Zip <Tablet>_abgleich_<Datum>.zip (Original bleibt unberührt)

Regeln:
  * Ein Nachweis ist eindeutig durch Fläche + taxon_id (eine Art je Fläche nur einmal).
  * Fehlt ein Nachweis auf einer Seite, wird er dort ergänzt (Vereinigung beider Stände).
  * Bemerkung bzw. Foto-Kommentar: ist er nur auf einer Seite gefüllt, wird er auf der anderen ergänzt.
    Sind beide gefüllt und verschieden, wird nichts überschrieben, nur gemeldet.
  * Standortfotos: Tabelle "fotos" (flaeche_id, datei, kommentar, aufgenommen_am, lon, lat) neben den
    Artnachweisen, Bilddateien im Projektordner unter fotos/. Ein Foto ist eindeutig durch seinen Dateinamen.
    Fehlt die Tabelle, wird sie angelegt (und im Tablet-Projekt als Layer eingetragen).
  * Bearbeitete Nachweise (QField-Plugin ab 0.6): Felder geaendert_am und ersetzt. Bei unterschiedlichem
    geaendert_am gewinnt der neuere Stand (bemerkung, original_eingabe, ersetzt) – auch eine geleerte Bemerkung.
    Wurde Art oder Fläche geändert, steht der alte Schlüssel in ersetzt ("Fläche:taxon_id", kommagetrennt);
    der alte Eintrag wird dann auf beiden Seiten entfernt, wenn er dasselbe erfasst_am hat (also derselbe
    Nachweis ist). Fehlen die Spalten, legt --ausfuehren sie auf beiden Seiten an.
  * Gelöschte Einträge kann das Skript nicht erkennen – sie kämen von der anderen Seite zurück.
    Dafür: --weglassen W-34:68005 (Fläche:taxon_id) bzw. --foto-weglassen fotos/<Datei>.jpg, mehrfach möglich.
  * Biotoptypen: Zuordnungen (Tabelle biotopzuordnung) sind eindeutig durch Fläche + Schlüssel + Code und werden
    wie Nachweise vereinigt (rolle, anteil, bemerkung werden ergänzt). Entfernen: --biotop-weglassen W-34:SH:WMy.
    Den Biotop-Katalog (biotoptypen, biotop_schluessel) und die Projektvariable gokart_biotop_schluessel gibt
    der PC vor – sie kommen samt Layern ins Tablet-Zip. Ebenso gokart_module, gokart_zusatz,
    gokart_punkt_genauigkeit und gokart_punkt_radius (sofern am PC gesetzt).
  * Punktaufnahmen (Tabelle aufnahme_punkte, QField-Plugin ab 0.7): eindeutig durch punkt_id, werden vereinigt;
    bei unterschiedlichem geaendert_am gewinnt der neuere Stand (auch die Position). Artnachweise an einem Punkt
    haben statt flaeche_id die punkt_id – Schlüssel "@<punkt_id>:taxon_id" (z. B. für --weglassen).
    Entfernen: --punkt-weglassen <punkt_id>. Fehlt die Tabelle auf einer Seite, wird sie angelegt (+ Layer).
  * Zusatzangaben (deckung, anzahl, phaenologie) gehen wie die Bemerkung mit; fehlende Spalten werden angelegt.
  * Das aktuelle QField-Plugin aus qfield_plugin/ kommt automatisch mit ins Tablet-Zip (abschalten: --ohne-plugin).

QGIS und QField vorher schließen bzw. das Projekt nicht geöffnet haben.
"""
import argparse
import filecmp
import shutil
import sqlite3
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'qgis_plugin' / 'gokart_desktop'))
import biotope as B  # noqa: E402
import punkte as P  # noqa: E402
import module as M  # noqa: E402
from artenliste_export import layer_suchen, projekt_lesen  # noqa: E402

INTERNE_IDS = {'fid', 'fid_1', 'ogc_fid'}   # werden nie übertragen, jede Datei vergibt eigene
FOTO_TABELLE = 'fotos'
FOTO_ORDNER = 'fotos'
FOTO_LAYER_ID = 'gokart_fotos'
FOTO_SQL = (f'CREATE TABLE "{FOTO_TABELLE}" (fid INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, '
            'flaeche_id TEXT, taxon_id INTEGER, datei TEXT, kommentar TEXT, aufgenommen_am TEXT, '
            'lon REAL, lat REAL)')   # taxon_id bleibt frei (Standortfotos), für spätere Artfotos reserviert
PLUGIN_ORDNER = Path(__file__).resolve().parents[2] / 'qfield_plugin'
PLUGIN_QML = 'GoKart_Wohnung.qml'
PLUGIN_DATEIEN = ('gokart_suche.js', 'gokart_biotop.js', 'gokart_zusatz.js', 'gokart_icon.svg', 'gokart_foto.svg',
                  'gokart_biotop.svg')
BIOTOP_FELDER = ('rolle', 'anteil', 'bemerkung')
NACHWEIS_ZUSATZSPALTEN = (('geaendert_am', 'TEXT'), ('ersetzt', 'TEXT')) + P.NACHWEIS_SPALTEN   # ab Plugin 0.6/0.7
ZUSATZ_FELDER = tuple(P.ZUSATZ)
NACHWEIS_FELDER = ('bemerkung', 'original_eingabe', 'ersetzt', 'geaendert_am') + ZUSATZ_FELDER   # "neuer gewinnt"


TEMP_PRAEFIX = '.gokart_abgleich_'   # entpackte .qgs aus einer .qgz (liegt kurz neben der .qgz)


def projekt_waehlen(pfad, tmp, name=None, rolle='PC'):
    """Projektdatei (.qgs oder .qgz) aus Datei, Ordner oder Zip bestimmen."""
    pfad = Path(pfad).expanduser().resolve()
    if pfad.suffix.lower() == '.zip':
        with zipfile.ZipFile(pfad) as z:
            z.extractall(tmp)
        pfad = Path(tmp)
    if pfad.is_file():
        if pfad.suffix.lower() not in ('.qgs', '.qgz'):
            raise SystemExit(f'{rolle}: keine Projektdatei: {pfad}')
        return pfad
    if not pfad.is_dir():
        raise SystemExit(f'{rolle}: nicht gefunden: {pfad}')
    kand = sorted(p for p in pfad.rglob('*') if p.is_file() and p.suffix.lower() in ('.qgs', '.qgz')
                  and not p.name.startswith(TEMP_PRAEFIX) and '.bak' not in p.name)
    if name:
        treffer = [p for p in kand if p.name == name]
        if not treffer:
            raise SystemExit(f'{rolle}: {name} nicht gefunden. Vorhanden: ' + ', '.join(p.name for p in kand))
        return treffer[0]
    if not kand:
        raise SystemExit(f'{rolle}: keine .qgs/.qgz in {pfad}')
    if len(kand) > 1:
        qf = [p for p in kand if p.stem.endswith('_qfield')]   # QField-Sync-Exporte
        if len(qf) == 1:
            return qf[0]
        opt = '--pc-projekt' if rolle == 'PC' else '--tablet-projekt'
        raise SystemExit(f'{rolle}: mehrere Projekte in {pfad}: ' + ', '.join(p.name for p in kand) +
                         f'\nBitte mit {opt} <Dateiname> wählen.')
    return kand[0]


class Projektdatei:
    """.qgs direkt; .qgz wird für die Dauer des Abgleichs als .qgs daneben entpackt und danach zurückgeschrieben."""
    def __init__(self, pfad):
        self.original = pfad
        self.qgz = pfad.suffix.lower() == '.qgz'
        if not self.qgz:
            self.qgs = pfad
            return
        with zipfile.ZipFile(pfad) as z:
            namen = [n for n in z.namelist() if n.lower().endswith('.qgs')]
            if not namen:
                raise SystemExit(f'{pfad.name}: keine .qgs in der .qgz')
            self.innen = namen[0]
            self.inhalt = z.read(self.innen)
        self.qgs = pfad.with_name(TEMP_PRAEFIX + pfad.stem + '.qgs')
        self.qgs.write_bytes(self.inhalt)

    @property
    def stamm(self):
        return self.original.stem

    def geaendert(self):
        return self.qgz and self.qgs.is_file() and self.qgs.read_bytes() != self.inhalt

    def zurueckschreiben(self):
        """Geänderte .qgs zurück in die .qgz (alle anderen Einträge bleiben), Temp-Datei entfernen."""
        if not self.qgz:
            return
        if self.geaendert():
            neu = self.original.with_name(self.original.name + '.neu')
            with zipfile.ZipFile(self.original) as alt, zipfile.ZipFile(neu, 'w', zipfile.ZIP_DEFLATED) as z:
                for info in alt.infolist():
                    daten = self.qgs.read_bytes() if info.filename == self.innen else alt.read(info.filename)
                    z.writestr(info, daten)
            neu.replace(self.original)
            self.inhalt = self.qgs.read_bytes()
        self.aufraeumen()

    def aufraeumen(self):
        if self.qgz and self.qgs.is_file():
            self.qgs.unlink()


class Seite:
    """Eine Projektseite (PC oder Tablet) mit Zugriff auf Artnachweise, Fotos und eigene Synonyme."""

    def __init__(self, name, datei):
        self.datei = Projektdatei(datei)
        self.name, self.qgs = name, self.datei.qgs
        layer, var = projekt_lesen(self.qgs)
        self.an = layer_suchen(layer, var.get('gokart_nachweis_layer'), 'artnachweise')
        self.es = layer_suchen(layer, None, 'eigene_synonyme')
        self.fk = var.get('gokart_nachweis_fk') or 'flaeche_id'
        if not self.an:
            raise SystemExit(f'{name}: Layer mit Artnachweisen nicht gefunden ({self.datei.original})')
        if not self.an.get('tabelle'):
            raise SystemExit(f'{name}: Tabelle des Artnachweis-Layers nicht erkennbar ({self.an["datei"]})')
        if self.es and not self.es.get('tabelle'):
            print(f'⚠ {name}: Tabelle des Layers „{self.es["name"]}“ nicht erkennbar ({self.es["datei"]}) – '
                  'eigene Synonyme werden auf dieser Seite übersprungen.')
            self.es = None
        # Fotos und Biotoptypen liegen in derselben GeoPackage wie die Artnachweise
        self.fo = {'datei': self.an['datei'], 'tabelle': FOTO_TABELLE, 'name': FOTO_TABELLE}
        self.bz = {'datei': self.an['datei'], 'tabelle': B.T_ZUORDNUNG, 'name': B.T_ZUORDNUNG}
        self.bz_cols, self.bz_pk = [], []
        self.pk_layer = {'datei': self.an['datei'], 'tabelle': P.T_PUNKTE, 'name': P.T_PUNKTE}
        self.pp_cols, self.pp_pk = [], []

    @property
    def home(self):
        return self.qgs.parent

    @staticmethod
    def _spalten(con, tabelle):
        info = list(con.execute(f'PRAGMA table_info("{tabelle}")'))
        return [r[1] for r in info], [r[1] for r in info if r[5]]   # alle, Primärschlüssel

    def _lesen(self, layer):
        con = sqlite3.connect(layer['datei'])
        cols, pk = self._spalten(con, layer['tabelle'])
        daten = [dict(zip(cols, r)) for r in con.execute(f'SELECT * FROM "{layer["tabelle"]}"')] if cols else []
        con.close()
        return cols, pk, daten

    def nachweise(self):
        cols, pk, daten = self._lesen(self.an)
        self.an_cols, self.an_pk = cols, pk
        return {(P.ort_schluessel(d, self.fk), str(d.get('taxon_id'))): d for d in daten}

    def nachweis_spalten(self, k):
        """Schlüssel (Ort, taxon_id) -> (Spalten, Werte) für SQL; Punkt-Orte beginnen mit '@'."""
        if str(k[0]).startswith('@'):
            return ('punkt_id', 'taxon_id'), (str(k[0])[1:], k[1])
        return (self.fk, 'taxon_id'), tuple(k)

    def punkte(self):
        """{punkt_id: Zeile} der Punktaufnahmen."""
        if not self.hat_tabelle(P.T_PUNKTE):
            self.pp_cols, self.pp_pk = [], []
            return {}
        cols, pk, daten = self._lesen(self.pk_layer)
        self.pp_cols, self.pp_pk = cols, pk
        return {str(d.get('punkt_id')): d for d in daten if d.get('punkt_id')}

    def punkt_srs(self):
        return P.punkt_srs(self.an['datei'])

    def fehlende_nachweisspalten(self):
        con = sqlite3.connect(self.an['datei'])
        cols, _ = self._spalten(con, self.an['tabelle'])
        con.close()
        return [(n, t) for n, t in NACHWEIS_ZUSATZSPALTEN if n not in cols]

    def nachweisspalten_ergaenzen(self):
        fehlend = self.fehlende_nachweisspalten()
        if fehlend:
            con = sqlite3.connect(self.an['datei'])
            for n, t in fehlend:
                con.execute(f'ALTER TABLE "{self.an["tabelle"]}" ADD COLUMN "{n}" {t}')
            con.commit()
            con.close()
        self.nachweise()                                   # Spaltenliste neu lesen
        return fehlend

    def synonyme(self):
        if not self.es:
            return {}
        cols, pk, daten = self._lesen(self.es)
        self.es_cols, self.es_pk = cols, pk
        return {(str(d.get('taxon_id')), str(d.get('schluessel') or d.get('synonym'))): d for d in daten}

    def hat_fototabelle(self):
        con = sqlite3.connect(self.fo['datei'])
        da = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (FOTO_TABELLE,)).fetchone()
        con.close()
        return bool(da)

    def fotos(self):
        if not self.hat_fototabelle():
            self.fo_cols, self.fo_pk = [], []
            return {}
        cols, pk, daten = self._lesen(self.fo)
        self.fo_cols, self.fo_pk = cols, pk
        return {str(d.get('datei')): d for d in daten if d.get('datei')}

    def fototabelle_anlegen(self):
        con = sqlite3.connect(self.fo['datei'])
        con.execute(FOTO_SQL)
        con.execute("INSERT INTO gpkg_contents (table_name, data_type, identifier, last_change) "
                    "VALUES (?, 'attributes', ?, strftime('%Y-%m-%dT%H:%M:%fZ','now'))", (FOTO_TABELLE, FOTO_TABELLE))
        if con.execute("SELECT 1 FROM sqlite_master WHERE name='gpkg_ogr_contents'").fetchone():
            con.execute('INSERT INTO gpkg_ogr_contents (table_name, feature_count) VALUES (?, 0)', (FOTO_TABELLE,))
        con.commit()
        con.close()

    def hat_tabelle(self, tabelle):
        con = sqlite3.connect(self.an['datei'])
        da = B.hat_tabelle(con, tabelle)
        con.close()
        return da

    def biotope(self):
        """{(flaeche_id, schluessel, code): Zeile} der Biotop-Zuordnungen."""
        if not self.hat_tabelle(B.T_ZUORDNUNG):
            self.bz_cols, self.bz_pk = [], []
            return {}
        cols, pk, daten = self._lesen(self.bz)
        self.bz_cols, self.bz_pk = cols, pk
        return {(str(d.get('flaeche_id')), str(d.get('schluessel')), str(d.get('code'))): d for d in daten}

    def katalog(self):
        """{schluessel: anzahl} des eingespielten Biotop-Katalogs."""
        return {s: n for s, _, n, _ in B.schluessel_liste(self.an['datei'])}

    def katalog_kopieren(self, quelle):
        """Biotop-Katalog (biotoptypen, biotop_schluessel) von einer anderen Seite übernehmen.
        Schlüssel, die nur hier vorkommen, bleiben erhalten."""
        B.tabellen_anlegen(self.an['datei'])
        con = sqlite3.connect(self.an['datei'])
        con.execute('ATTACH DATABASE ? AS q', (str(quelle.an['datei']),))
        for t in (B.T_TYPEN, B.T_SCHLUESSEL):
            liste = ', '.join(B.SPALTEN[t])
            con.execute(f'DELETE FROM "{t}" WHERE schluessel IN (SELECT schluessel FROM q."{t}")')
            con.execute(f'INSERT INTO "{t}" ({liste}) SELECT {liste} FROM q."{t}"')
        con.commit()
        con.execute('DETACH DATABASE q')
        for t in B.SQL:
            B._registrieren(con, t)
        con.commit()
        con.close()

    def unregistriert(self):
        """Tabellen der Projektlayer, die in gpkg_contents fehlen. Sobald eine Tabelle als 'attributes'
        registriert ist (z. B. fotos), blendet GDAL unregistrierte Tabellen aus – dann fehlen Layer."""
        fehlend = []
        for layer in (self.an, self.es):
            if not layer:
                continue
            con = sqlite3.connect(layer['datei'])
            da = con.execute('SELECT 1 FROM gpkg_contents WHERE lower(table_name) = lower(?)',
                             (layer['tabelle'],)).fetchone()
            con.close()
            if not da:
                fehlend.append(layer)
        return fehlend

    def registrieren(self, layers):
        for layer in layers:
            con = sqlite3.connect(layer['datei'])
            con.execute("INSERT INTO gpkg_contents (table_name, data_type, identifier, last_change) "
                        "VALUES (?, 'attributes', ?, strftime('%Y-%m-%dT%H:%M:%fZ','now'))",
                        (layer['tabelle'], layer['tabelle']))
            con.commit()
            con.close()

    def fotolayer_im_projekt(self):
        root = ET.parse(self.qgs).getroot()
        # Auch über den Namen: das Desktop-Plugin ("Einrichten… → Standortfotos") legt den Layer mit eigener ID an
        return any(ml.findtext('id') == FOTO_LAYER_ID or ml.findtext('layername') == FOTO_TABELLE
                   for ml in root.iter('maplayer'))

    def fotolayer_eintragen(self):
        """Trägt die Tabelle fotos als Layer ins Projekt ein, damit QField sie bearbeiten kann."""
        baum = ET.parse(self.qgs)
        root = baum.getroot()
        rel = './' + Path(self.fo['datei']).relative_to(self.home).as_posix()
        quelle = f'{rel}|layername={FOTO_TABELLE}'
        projektlayer = root.find('projectlayers')
        ml = ET.SubElement(projektlayer, 'maplayer', {
            'type': 'vector', 'geometry': 'No geometry', 'wkbType': 'NoGeometry', 'readOnly': '0'})
        for tag, text in (('id', FOTO_LAYER_ID), ('datasource', quelle), ('layername', FOTO_TABELLE)):
            ET.SubElement(ml, tag).text = text
        ET.SubElement(ml, 'provider', {'encoding': 'UTF-8'}).text = 'ogr'
        baumwurzel = root.find('layer-tree-group')
        if baumwurzel is not None:
            ET.SubElement(baumwurzel, 'layer-tree-layer', {
                'id': FOTO_LAYER_ID, 'name': FOTO_TABELLE, 'source': quelle, 'providerKey': 'ogr',
                'checked': 'Qt::Checked', 'expanded': '0'})
        baum.write(self.qgs, encoding='utf-8', xml_declaration=True)

    def schreiben(self, layer, cols, pk, neue, loeschen=(), schluessel=None):
        """Fügt Zeilen ein (gemeinsame Spalten, ohne Primärschlüssel) und löscht nach Bedingung.
        loeschen: Liste von Wert-Tupeln, schluessel: passende Spaltennamen."""
        con = sqlite3.connect(layer['datei'])
        t = layer['tabelle']
        for d in neue:
            felder = [c for c in cols if c not in pk and c not in INTERNE_IDS and c in d and d[c] is not None]
            con.execute(f'INSERT INTO "{t}" ({", ".join(chr(34) + c + chr(34) for c in felder)}) '
                        f'VALUES ({", ".join("?" * len(felder))})', [d[c] for c in felder])
        for werte in loeschen:
            bed = ' AND '.join(f'CAST("{s}" AS TEXT) = ?' for s in schluessel)
            con.execute(f'DELETE FROM "{t}" WHERE {bed}', tuple(werte))
        con.execute('UPDATE gpkg_ogr_contents SET feature_count = (SELECT count(*) FROM "%s") '
                    'WHERE table_name = ?' % t, (t,))
        con.commit()
        con.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        con.close()

    def aktualisieren(self, layer, aenderungen, schluessel):
        """aenderungen: [(Schlüsselwerte, feld, wert)]"""
        con = sqlite3.connect(layer['datei'])
        bed = ' AND '.join(f'CAST("{s}" AS TEXT) = ?' for s in schluessel)
        for werte, feld, wert in aenderungen:
            con.execute(f'UPDATE "{layer["tabelle"]}" SET "{feld}" = ? WHERE {bed}', (wert, *werte))
        con.commit()
        con.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        con.close()


def kurz(d, fk):
    name = d.get('deutscher_name') or d.get('wissenschaftlicher_name') or '?'
    am = str(d.get('erfasst_am') or '').replace('T', ' ')[:16]
    return f'{P.ort_schluessel(d, fk)} · {name} ({am})'


def ergaenzungen(a, b, felder):
    """Vergleicht gleiche Schlüssel in a und b. Liefert (für a, für b, Konflikte)."""
    fuer_a, fuer_b, konflikt = [], [], []
    for k in a:
        if k not in b:
            continue
        for feld in felder:
            wa, wb = (a[k].get(feld) or ''), (b[k].get(feld) or '')
            if wa == wb:
                continue
            if not wa:
                fuer_a.append((k, feld, wb))
            elif not wb:
                fuer_b.append((k, feld, wa))
            else:
                konflikt.append((k, feld, wa, wb))
    return fuer_a, fuer_b, konflikt


def sichern(dateien):
    stempel = datetime.now().strftime('%Y%m%d_%H%M%S')
    for p in sorted(set(dateien)):
        ziel = p.with_name(f'{p.stem}_{stempel}{p.suffix}.bak')
        shutil.copy2(p, ziel)
        print(f'  Sicherung: {ziel}')


def wal_pruefen(dateien):
    for p in set(dateien):
        wal = Path(str(p) + '-wal')
        if wal.exists() and wal.stat().st_size > 0:
            print(f'⚠ {wal.name} ist nicht leer – ist das Projekt noch in QGIS geöffnet? Bitte schließen.')
            return False
    return True


def plugin_ziele(tb):
    """[(Quelle, Ziel)] – das Plugin muss so heißen wie die .qgs des Tablet-Projekts."""
    if not (PLUGIN_ORDNER / PLUGIN_QML).is_file():
        return []
    paare = [(PLUGIN_ORDNER / PLUGIN_QML, tb.home / (tb.datei.stamm + '.qml'))]
    paare += [(PLUGIN_ORDNER / n, tb.home / n) for n in PLUGIN_DATEIEN if (PLUGIN_ORDNER / n).is_file()]
    return paare


def plugin_pruefen(tb):
    return [z.name for q, z in plugin_ziele(tb) if not z.is_file() or not filecmp.cmp(q, z, shallow=False)]


def nachweis_abgleich(a, b, felder=NACHWEIS_FELDER, ergaenzen=('bemerkung',) + ZUSATZ_FELDER):
    """Wie ergaenzungen(), aber mit geaendert_am: unterscheidet es sich, gewinnt der neuere Stand komplett
    (felder, auch leere Werte). Sonst nur Bemerkung/Zusatzangaben ergänzen bzw. Konflikt melden."""
    fuer_a, fuer_b, konflikt = [], [], []
    gleich_a, gleich_b = {}, {}
    for k in a:
        if k not in b:
            continue
        za, zb = str(a[k].get('geaendert_am') or ''), str(b[k].get('geaendert_am') or '')
        if za == zb:
            gleich_a[k], gleich_b[k] = a[k], b[k]
            continue
        gewinner, ziel = (a[k], fuer_b) if za > zb else (b[k], fuer_a)
        verlierer = b[k] if za > zb else a[k]
        for feld in felder:
            if feld in gewinner and (gewinner.get(feld) or None) != (verlierer.get(feld) or None):
                ziel.append((k, feld, gewinner.get(feld)))
    fa, fb, ko = ergaenzungen(gleich_a, gleich_b, ergaenzen)
    return fuer_a + fa, fuer_b + fb, konflikt + ko


def punkt_abgleich(a, b):
    return nachweis_abgleich(a, b, P.PUNKT_FELDER, ('bemerkung', 'flaeche_id', 'biotoptyp'))


def geom_umschreiben(d, srs_ziel):
    """Punkt-Blob auf die srs_id der Zielseite umschreiben (GeoPackages können verschiedene IDs vergeben)."""
    if srs_ziel is None or not d.get(P.GEOM):
        return d
    xy = P.punkt_xy(d[P.GEOM])
    d = dict(d)
    d[P.GEOM] = P.punkt_blob(xy[0], xy[1], srs_ziel) if xy else None
    return d


def ersetzte_nachweise(*seiten):
    """Alte Schlüssel aus dem Feld ersetzt, deren Eintrag (gleiches erfasst_am) noch irgendwo liegt."""
    alle = {}
    for n in seiten:
        for k, d in n.items():
            alle.setdefault(k, []).append(d)
    weg = {}
    for n in seiten:
        for k, d in n.items():
            for alt in str(d.get('ersetzt') or '').split(','):
                if ':' not in alt:
                    continue
                fl, tid = alt.strip().rsplit(':', 1)
                ak = (fl, tid)
                if ak == k or ak not in alle:
                    continue
                if any(str(x.get('erfasst_am') or '') == str(d.get('erfasst_am') or '') for x in alle[ak]):
                    weg[ak] = k
    return weg   # {alter Schlüssel: neuer Schlüssel}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('pc', help='PC-Projekt: .qgs oder Projektordner')
    ap.add_argument('tablet', help='Tablet-Export: .zip oder Ordner')
    ap.add_argument('--ausfuehren', action='store_true', help='Unterschiede wirklich übernehmen')
    ap.add_argument('--weglassen', action='append', default=[], metavar='FLÄCHE:TAXON_ID',
                    help='Nachweis auf beiden Seiten entfernen')
    ap.add_argument('--foto-weglassen', action='append', default=[], metavar='DATEINAME',
                    help='Fotoeintrag auf beiden Seiten entfernen (Bilddatei bleibt liegen)')
    ap.add_argument('--biotop-weglassen', action='append', default=[], metavar='FLÄCHE:SCHLÜSSEL:CODE',
                    help='Biotop-Zuordnung auf beiden Seiten entfernen')
    ap.add_argument('--punkt-weglassen', action='append', default=[], metavar='PUNKT_ID',
                    help='Punktaufnahme auf beiden Seiten entfernen (ihre Artnachweise mit --weglassen @PUNKT_ID:…)')
    ap.add_argument('--pc-projekt', metavar='DATEI', help='Projektdatei im PC-Ordner (bei mehreren .qgs/.qgz)')
    ap.add_argument('--tablet-projekt', metavar='DATEI', help='Projektdatei im Tablet-Export (bei mehreren)')
    ap.add_argument('--ohne-plugin', action='store_true', help='QField-Plugin im Tablet-Zip nicht aktualisieren')
    a = ap.parse_args()

    tablet_pfad = Path(a.tablet).expanduser().resolve()
    if Path(a.pc).suffix.lower() == '.zip':
        raise SystemExit('Das PC-Projekt muss ein Ordner oder eine .qgs sein (kein Zip).')
    with tempfile.TemporaryDirectory() as tmp:
        pc_datei = projekt_waehlen(a.pc, None, a.pc_projekt, 'PC')
        # Tablet-Stand immer in einer Arbeitskopie bearbeiten, das Original bleibt unberührt
        if tablet_pfad.is_dir():
            shutil.copytree(tablet_pfad, Path(tmp) / 'tablet')
            tb_datei = projekt_waehlen(Path(tmp) / 'tablet', None, a.tablet_projekt, 'Tablet')
        elif tablet_pfad.suffix.lower() == '.zip':
            tb_datei = projekt_waehlen(tablet_pfad, Path(tmp) / 'tablet', a.tablet_projekt, 'Tablet')
        else:
            raise SystemExit('Tablet: Ordner oder .zip angeben')
        pc = Seite('PC', pc_datei)
        try:
            tb = Seite('Tablet', tb_datei)
        except BaseException:
            pc.datei.aufraeumen()
            raise
        try:
            abgleichen(a, pc, tb, tablet_pfad)
        finally:
            pc.datei.aufraeumen()
            tb.datei.aufraeumen()


def abgleichen(a, pc, tb, tablet_pfad):
    # --- Artnachweise
    n_pc, n_tb = pc.nachweise(), tb.nachweise()
    weg = {tuple(w.split(':', 1)) for w in a.weglassen}
    ersetzt = ersetzte_nachweise(n_pc, n_tb)
    weg |= set(ersetzt)
    spalten_pc, spalten_tb = pc.fehlende_nachweisspalten(), tb.fehlende_nachweisspalten()
    nur_pc = [k for k in n_pc if k not in n_tb and k not in weg]
    nur_tb = [k for k in n_tb if k not in n_pc and k not in weg]
    beide = [k for k in n_pc if k in n_tb]
    upd_pc, upd_tb, konflikt = nachweis_abgleich(n_pc, n_tb)
    weg_pc = [k for k in weg if k in n_pc]
    weg_tb = [k for k in weg if k in n_tb]

    # --- Fotos (Tabelle + Dateien)
    f_pc, f_tb = pc.fotos(), tb.fotos()
    foto_weg = set(a.foto_weglassen)
    fnur_pc = [k for k in f_pc if k not in f_tb and k not in foto_weg]
    fnur_tb = [k for k in f_tb if k not in f_pc and k not in foto_weg]
    fupd_pc, fupd_tb, fkonflikt = ergaenzungen(f_pc, f_tb, ('kommentar',))
    fweg_pc = [k for k in foto_weg if k in f_pc]
    fweg_tb = [k for k in foto_weg if k in f_tb]
    alle_dateien = {k for k in set(f_pc) | set(f_tb) if k not in foto_weg}
    datei_zum_pc = sorted(f for f in alle_dateien if (tb.home / f).is_file() and not (pc.home / f).is_file())
    datei_zum_tb = sorted(f for f in alle_dateien if (pc.home / f).is_file() and not (tb.home / f).is_file())
    fehlt_ganz = sorted(f for f in alle_dateien if not (pc.home / f).is_file() and not (tb.home / f).is_file())
    tabelle_pc, tabelle_tb = not pc.hat_fototabelle(), not tb.hat_fototabelle()
    reg_pc, reg_tb = pc.unregistriert(), tb.unregistriert()
    layer_tb = not tb.fotolayer_im_projekt()

    # --- Eigene Synonyme
    s_pc, s_tb = pc.synonyme(), tb.synonyme()
    syn_nur_pc = [k for k in s_pc if k not in s_tb]
    syn_nur_tb = [k for k in s_tb if k not in s_pc]

    # --- Biotoptypen (Zuordnungen vereinigen, Katalog + Variable vom PC)
    b_pc, b_tb = pc.biotope(), tb.biotope()
    bweg = {tuple(w.split(':', 2)) for w in a.biotop_weglassen}
    bnur_pc = [k for k in b_pc if k not in b_tb and k not in bweg]
    bnur_tb = [k for k in b_tb if k not in b_pc and k not in bweg]
    bupd_pc, bupd_tb, bkonflikt = ergaenzungen(b_pc, b_tb, BIOTOP_FELDER)
    bweg_pc = [k for k in bweg if k in b_pc]
    bweg_tb = [k for k in bweg if k in b_tb]
    kat_pc, kat_tb = pc.katalog(), tb.katalog()
    kat_neu = bool(kat_pc) and any(kat_tb.get(s) != n for s, n in kat_pc.items())
    biotop_pc = bool(kat_pc) or pc.hat_tabelle(B.T_ZUORDNUNG)
    btab_pc = tb.hat_tabelle(B.T_ZUORDNUNG) and not pc.hat_tabelle(B.T_ZUORDNUNG)
    btab_tb = biotop_pc and not tb.hat_tabelle(B.T_ZUORDNUNG)
    blayer_tb = biotop_pc and not set(B.LAYER_IDS.values()) <= B.qgs_layer_ids(tb.qgs)
    var_pc, var_tb = B.qgs_variable(pc.qgs, B.VAR_SCHLUESSEL), B.qgs_variable(tb.qgs, B.VAR_SCHLUESSEL)
    var_neu = bool(var_pc) and var_pc != var_tb
    # Erfassungsmodule, Zusatzangaben und Punkt-Schwellwerte gibt der PC vor (nur wenn dort gesetzt)
    pvars = {}
    for name in (M.VAR_MODULE, P.VAR_ZUSATZ, P.VAR_GENAUIGKEIT, P.VAR_RADIUS):
        w_pc, w_tb = B.qgs_variable(pc.qgs, name), B.qgs_variable(tb.qgs, name)
        if w_pc not in (None, '') and w_pc != w_tb:
            pvars[name] = (w_tb, w_pc)
    # Zwei verschiedene Hauptbiotope für dieselbe Fläche und denselben Schlüssel nach dem Abgleich?
    haupt = {}
    for k, d in list(b_pc.items()) + list(b_tb.items()):
        if k not in bweg and (d.get('rolle') or '') == 'Haupt':
            haupt.setdefault(k[:2], set()).add(k[2])
    haupt_doppelt = {k: v for k, v in haupt.items() if len(v) > 1}

    # --- Punktaufnahmen (Tabelle aufnahme_punkte)
    p_pc, p_tb = pc.punkte(), tb.punkte()
    pweg = set(a.punkt_weglassen)
    pnur_pc = [k for k in p_pc if k not in p_tb and k not in pweg]
    pnur_tb = [k for k in p_tb if k not in p_pc and k not in pweg]
    pupd_pc, pupd_tb, pkonflikt = punkt_abgleich(p_pc, p_tb)
    pweg_pc = [k for k in pweg if k in p_pc]
    pweg_tb = [k for k in pweg if k in p_tb]
    ptab_pc = tb.hat_tabelle(P.T_PUNKTE) and not pc.hat_tabelle(P.T_PUNKTE)
    ptab_tb = pc.hat_tabelle(P.T_PUNKTE) and not tb.hat_tabelle(P.T_PUNKTE)
    player_pc = (pc.hat_tabelle(P.T_PUNKTE) or ptab_pc) and not P.qgs_layer_im_projekt(pc.qgs)
    player_tb = (tb.hat_tabelle(P.T_PUNKTE) or ptab_tb) and not P.qgs_layer_im_projekt(tb.qgs)
    # Nachweise an Punkten, die es auf keiner Seite (mehr) gibt
    alle_punkte = (set(p_pc) | set(p_tb)) - pweg
    verwaist = sorted({k[0] for k in list(n_pc) + list(n_tb)
                       if k[0].startswith('@') and k[0][1:] not in alle_punkte and k not in weg})

    plugin_neu = [] if a.ohne_plugin else plugin_pruefen(tb)

    # --- Bericht
    print(f'PC:     {len(n_pc)} Nachweise, {len(p_pc)} Punkte, {len(f_pc)} Fotos, {len(b_pc)} Biotope, '
          f'{len(s_pc)} eigene Synonyme  ({pc.qgs})')
    print(f'Tablet: {len(n_tb)} Nachweise, {len(p_tb)} Punkte, {len(f_tb)} Fotos, {len(b_tb)} Biotope, '
          f'{len(s_tb)} eigene Synonyme  ({tablet_pfad})')
    for seite in (pc, tb):
        quellen = [f'Nachweise {seite.an["datei"].name}:{seite.an["tabelle"]}']
        if seite.es:
            quellen.append(f'Synonyme {seite.es["datei"].name}:{seite.es["tabelle"]}')
        print(f'  {seite.name}-Dateien: ' + ', '.join(quellen))
    print(f'Gemeinsam: {len(beide)} Nachweise\n')
    for titel, keys, quelle, fk in (('Nur am PC → kommt aufs Tablet', nur_pc, n_pc, pc.fk),
                                    ('Nur auf dem Tablet → kommt auf den PC', nur_tb, n_tb, tb.fk)):
        print(f'{titel}: {len(keys)}')
        for k in sorted(keys):
            print(f'  + {kurz(quelle[k], fk)}   [--weglassen {k[0]}:{k[1]}]')
    if fnur_pc or fnur_tb:
        print(f'Fotos: {len(fnur_pc)} nur PC, {len(fnur_tb)} nur Tablet → werden ergänzt')
        for k in sorted(fnur_pc):
            print(f'  + PC → Tablet: {k}')
        for k in sorted(fnur_tb):
            print(f'  + Tablet → PC: {k}')
    if datei_zum_pc or datei_zum_tb:
        print(f'Bilddateien: {len(datei_zum_pc)} Tablet → PC, {len(datei_zum_tb)} PC → Tablet')
    for f in fehlt_ganz:
        print(f'⚠ Bilddatei fehlt auf beiden Seiten: {f}')
    if syn_nur_pc or syn_nur_tb:
        print(f'Eigene Synonyme: {len(syn_nur_pc)} nur PC, {len(syn_nur_tb)} nur Tablet → werden ergänzt')
        for k in syn_nur_pc:
            print(f'  + PC → Tablet: {s_pc[k].get("synonym")}')
        for k in syn_nur_tb:
            print(f'  + Tablet → PC: {s_tb[k].get("synonym")}')
    for titel, upd in (('PC → Tablet', upd_tb + fupd_tb), ('Tablet → PC', upd_pc + fupd_pc)):
        for k, feld, wert in upd:
            print(f'  ~ {feld} {titel}: {k}: {wert}')
    for alt, neu in sorted(ersetzt.items()):
        print(f'  ✎ in QField bearbeitet: {alt[0]}:{alt[1]} → {neu[0]}:{neu[1]} (alter Eintrag wird entfernt)')
    if spalten_pc or spalten_tb:
        print('Spalten für Bearbeitungen werden ergänzt: ' + ', '.join(
            f'{s}: {", ".join(n for n, _ in sp)}' for s, sp in (('PC', spalten_pc), ('Tablet', spalten_tb)) if sp))
    if weg_pc or weg_tb or fweg_pc or fweg_tb:
        print(f'Wird entfernt: Nachweise {len(weg_pc)} PC / {len(weg_tb)} Tablet, '
              f'Fotoeinträge {len(fweg_pc)} PC / {len(fweg_tb)} Tablet')
    for k, feld, w_pc, w_tb in konflikt + fkonflikt:
        print(f'⚠ {feld} unterschiedlich, bleibt wie es ist: {k}\n     PC: {w_pc!r}  Tablet: {w_tb!r}')
    if tabelle_pc or tabelle_tb or layer_tb:
        print(f'Fototabelle wird angelegt: PC {"ja" if tabelle_pc else "-"}, Tablet {"ja" if tabelle_tb else "-"}'
              f'{", Layer im Tablet-Projekt eintragen" if layer_tb else ""}')
    if bnur_pc or bnur_tb:
        print(f'Biotoptypen: {len(bnur_pc)} nur PC, {len(bnur_tb)} nur Tablet → werden ergänzt')
        for titel, keys, quelle in (('PC → Tablet', bnur_pc, b_pc), ('Tablet → PC', bnur_tb, b_tb)):
            for k in sorted(keys):
                d = quelle[k]
                print(f'  + {titel}: {k[0]} · {k[1]} {k[2]} {d.get("name") or ""} ({d.get("rolle") or "-"})'
                      f'   [--biotop-weglassen {k[0]}:{k[1]}:{k[2]}]')
    for titel, upd in (('PC → Tablet', bupd_tb), ('Tablet → PC', bupd_pc)):
        for k, feld, wert in upd:
            print(f'  ~ Biotop {feld} {titel}: {":".join(k)}: {wert}')
    for k, feld, w_pc, w_tb in bkonflikt:
        print(f'⚠ Biotop {feld} unterschiedlich, bleibt wie es ist: {":".join(k)}\n     PC: {w_pc!r}  Tablet: {w_tb!r}')
    for (fl, sch), codes in sorted(haupt_doppelt.items()):
        print(f'⚠ Fläche {fl}: mehrere Hauptbiotope ({sch}: {", ".join(sorted(codes))}) – eins auf Neben setzen')
    if bweg_pc or bweg_tb:
        print(f'Biotop-Zuordnungen werden entfernt: {len(bweg_pc)} PC / {len(bweg_tb)} Tablet')
    if kat_neu or btab_tb or blayer_tb:
        print('Biotop-Katalog fürs Tablet: ' + ', '.join(f'{s} ({n})' for s, n in sorted(kat_pc.items()))
              + (' + Layer im Tablet-Projekt' if blayer_tb else ''))
    if btab_pc:
        print('Biotop-Tabellen werden am PC angelegt')
    if var_neu:
        print(f'Biotoptypen-Schlüssel fürs Tablet: {var_tb or "-"} → {var_pc}')
    for name, (alt, neu) in pvars.items():
        print(f'Projektvariable fürs Tablet: {name} {alt or "-"} → {neu}')
    if pnur_pc or pnur_tb:
        print(f'Punktaufnahmen: {len(pnur_pc)} nur PC, {len(pnur_tb)} nur Tablet → werden ergänzt')
        for titel, keys, quelle in (('PC → Tablet', pnur_pc, p_pc), ('Tablet → PC', pnur_tb, p_tb)):
            for k in sorted(keys):
                d = quelle[k]
                am = str(d.get('erfasst_am') or '').replace('T', ' ')[:16]
                print(f'  + {titel}: {k} ({am}, ±{d.get("gps_genauigkeit") or "?"} m)   [--punkt-weglassen {k}]')
    for titel, upd in (('PC → Tablet', pupd_tb), ('Tablet → PC', pupd_pc)):
        for k, feld, wert in upd:
            print(f'  ~ Punkt {feld} {titel}: {k}' + ('' if feld == P.GEOM else f': {wert}'))
    for k, feld, w_pc, w_tb in pkonflikt:
        print(f'⚠ Punkt {feld} unterschiedlich, bleibt wie es ist: {k}\n     PC: {w_pc!r}  Tablet: {w_tb!r}')
    if pweg_pc or pweg_tb:
        print(f'Punktaufnahmen werden entfernt: {len(pweg_pc)} PC / {len(pweg_tb)} Tablet')
    for o in verwaist:
        print(f'⚠ Artnachweise an {o}, aber der Punkt fehlt auf beiden Seiten')
    if ptab_pc or ptab_tb or player_pc or player_tb:
        print('Punkt-Tabelle/-Layer wird angelegt: ' + ', '.join(
            t for t, ja in (('Tabelle PC', ptab_pc), ('Tabelle Tablet', ptab_tb),
                            ('Layer PC-Projekt', player_pc), ('Layer Tablet-Projekt', player_tb)) if ja))
    if plugin_neu:
        print(f'QField-Plugin wird aktualisiert: {", ".join(plugin_neu)}')
    if reg_pc or reg_tb:
        print('GeoPackage-Registrierung wird ergänzt: ' +
              ', '.join(f'{s}: {l["tabelle"]}' for s, ls in (('PC', reg_pc), ('Tablet', reg_tb)) for l in ls))

    nichts = not (nur_pc or nur_tb or upd_pc or upd_tb or weg_pc or weg_tb or fnur_pc or fnur_tb
                  or fupd_pc or fupd_tb or fweg_pc or fweg_tb or datei_zum_pc or datei_zum_tb
                  or syn_nur_pc or syn_nur_tb or tabelle_pc or tabelle_tb or layer_tb or plugin_neu
                  or reg_pc or reg_tb or bnur_pc or bnur_tb or bupd_pc or bupd_tb or bweg_pc or bweg_tb
                  or kat_neu or btab_pc or btab_tb or blayer_tb or var_neu or spalten_pc or spalten_tb
                  or pnur_pc or pnur_tb or pupd_pc or pupd_tb or pweg_pc or pweg_tb
                  or ptab_pc or ptab_tb or player_pc or player_tb or pvars)
    if nichts:
        print('\n✓ Beide Stände sind gleich.')
        return
    if not a.ausfuehren:
        print('\nNur Vorschau. Übernehmen mit --ausfuehren')
        return

    pc_dateien = [pc.an['datei']] + ([pc.es['datei']] if pc.es else [])
    if not wal_pruefen(pc_dateien):
        raise SystemExit('Abgebrochen.')

    def fuer(seite, d):
        """Fremdschlüssel-Spalte der Zielseite setzen, falls die Seiten unterschiedlich heißen."""
        d = dict(d)
        quelle_fk = tb.fk if seite is pc else pc.fk
        if quelle_fk != seite.fk:
            d[seite.fk] = d.pop(quelle_fk, None)
        return d

    def punkte_anwenden(seite, quelle, neu, upd, weg, tabelle, layer):
        if tabelle:
            srs = quelle.punkt_srs()
            authid = P.srs_info(quelle.an['datei'], srs)[0] if srs is not None else None
            P.tabelle_anlegen(seite.an['datei'], authid)
        if layer:
            P.qgs_layer_eintragen(seite.qgs, seite.an['datei'])
        seite.punkte()                                         # Spaltenliste (neu) lesen
        if not seite.pp_cols:
            return
        srs = seite.punkt_srs()
        neu = [geom_umschreiben(quelle_punkte[k], srs) for k in neu]
        upd = [(k, feld, geom_umschreiben({P.GEOM: wert}, srs)[P.GEOM] if feld == P.GEOM else wert)
               for k, feld, wert in upd]
        if neu or weg:
            seite.schreiben(seite.pk_layer, seite.pp_cols, seite.pp_pk, neu, [(k,) for k in weg], ('punkt_id',))
        seite.aktualisieren(seite.pk_layer, [((k,), feld, wert) for k, feld, wert in upd], ('punkt_id',))

    def biotope_anwenden(seite, neu, upd, weg, tabelle):
        if tabelle:
            B.tabellen_anlegen(seite.an['datei'])
        seite.biotope()                                        # Spaltenliste (neu) lesen
        if neu or weg:
            seite.schreiben(seite.bz, seite.bz_cols, seite.bz_pk, neu, weg, ('flaeche_id', 'schluessel', 'code'))
        seite.aktualisieren(seite.bz, upd, ('flaeche_id', 'schluessel', 'code'))

    def anwenden(seite, n_neu, n_upd, n_weg, f_neu, f_upd, f_weg, syn_neu, dateien, quelle_home, tabelle):
        seite.registrieren(seite.unregistriert())
        seite.nachweisspalten_ergaenzen()
        if tabelle:
            seite.fototabelle_anlegen()
        seite.fotos()                                          # Spaltenliste (neu) lesen
        seite.schreiben(seite.an, seite.an_cols, seite.an_pk, n_neu)
        for k in n_weg:
            sp, werte = seite.nachweis_spalten(k)
            seite.schreiben(seite.an, seite.an_cols, seite.an_pk, [], [werte], sp)
        for k, feld, wert in n_upd:
            sp, werte = seite.nachweis_spalten(k)
            seite.aktualisieren(seite.an, [(werte, feld, wert)], sp)
        seite.schreiben(seite.fo, seite.fo_cols, seite.fo_pk, f_neu, [(k,) for k in f_weg], ('datei',))
        seite.aktualisieren(seite.fo, [((k,), feld, wert) for k, feld, wert in f_upd], ('datei',))
        if seite.es and syn_neu:
            seite.schreiben(seite.es, seite.es_cols, seite.es_pk, syn_neu)
        for f in dateien:
            (seite.home / f).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(quelle_home / f, seite.home / f)

    print('\nPC-Projekt aktualisieren …')
    sichern(pc_dateien + ([pc.datei.original] if (btab_pc or player_pc) else []))
    anwenden(pc, [fuer(pc, n_tb[k]) for k in nur_tb], upd_pc, weg_pc,
             [f_tb[k] for k in fnur_tb], fupd_pc, fweg_pc, [s_tb[k] for k in syn_nur_tb],
             datei_zum_pc, tb.home, tabelle_pc)
    biotope_anwenden(pc, [b_tb[k] for k in bnur_tb], bupd_pc, bweg_pc, btab_pc)
    quelle_punkte = p_tb
    punkte_anwenden(pc, tb, pnur_tb, pupd_pc, pweg_pc, ptab_pc, player_pc)
    if btab_pc:
        B.qgs_layer_eintragen(pc.qgs, pc.an['datei'])
    pc.datei.zurueckschreiben()                      # .qgz: geänderte .qgs wieder einpacken

    print('Tablet-Zip erstellen …')
    anwenden(tb, [fuer(tb, n_pc[k]) for k in nur_pc], upd_tb, weg_tb,
             [f_pc[k] for k in fnur_pc], fupd_tb, fweg_tb, [s_pc[k] for k in syn_nur_pc],
             datei_zum_tb, pc.home, tabelle_tb)
    if kat_neu or btab_tb:
        tb.katalog_kopieren(pc)
    biotope_anwenden(tb, [b_pc[k] for k in bnur_pc], bupd_tb, bweg_tb, btab_tb)
    quelle_punkte = p_pc
    punkte_anwenden(tb, pc, pnur_pc, pupd_tb, pweg_tb, ptab_tb, player_tb)
    if blayer_tb:
        B.qgs_layer_eintragen(tb.qgs, tb.an['datei'])
    if var_neu:
        B.qgs_variable_setzen(tb.qgs, B.VAR_SCHLUESSEL, var_pc)
    for name, (_alt, neu) in pvars.items():
        B.qgs_variable_setzen(tb.qgs, name, neu)
    (tb.home / FOTO_ORDNER).mkdir(exist_ok=True)
    if layer_tb:
        tb.fotolayer_eintragen()
    for q, z in ([] if a.ohne_plugin else plugin_ziele(tb)):
        shutil.copy2(q, z)

    tb.datei.zurueckschreiben()
    stamm = tablet_pfad.stem if tablet_pfad.suffix.lower() == '.zip' else tablet_pfad.name
    stamm = stamm.split('_abgleich_')[0]           # nicht bei jedem Lauf verlängern
    ziel = tablet_pfad.with_name(f'{stamm}_abgleich_{datetime.now():%Y-%m-%d_%H%M}.zip')
    basis = tb.home
    with zipfile.ZipFile(ziel, 'w', zipfile.ZIP_DEFLATED) as z:
        for p in sorted(basis.rglob('*')):
            if p.is_file() and not p.name.endswith(('-wal', '-shm', '.bak', '~')):
                z.write(p, p.relative_to(basis))
        z.writestr(FOTO_ORDNER + '/', '')          # leeren Fotoordner mitnehmen
    print(f'\n✓ Fertig. PC: {len(pc.nachweise())} Nachweise / {len(pc.punkte())} Punkte / {len(pc.fotos())} Fotos / '
          f'{len(pc.biotope())} Biotope, Tablet: {len(tb.nachweise())} Nachweise / {len(tb.punkte())} Punkte / '
          f'{len(tb.fotos())} Fotos / {len(tb.biotope())} Biotope')
    print(f'→ Fürs Tablet: {ziel}')


if __name__ == '__main__':
    main()
