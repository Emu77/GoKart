#!/usr/bin/env python3
"""GoKart – gleicht Artnachweise, Fotos und eigene Synonyme zwischen PC-Projekt und Tablet-Export ab.

Aufruf:
    python3 abgleich.py <PC-Projekt (.qgs oder Ordner)> <Tablet-Export (.zip oder Ordner)>
        → zeigt nur die Unterschiede, ändert nichts
    python3 abgleich.py <PC> <Tablet> --ausfuehren
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
  * Gelöschte Einträge kann das Skript nicht erkennen – sie kämen von der anderen Seite zurück.
    Dafür: --weglassen W-34:68005 (Fläche:taxon_id) bzw. --foto-weglassen fotos/<Datei>.jpg, mehrfach möglich.
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
from artenliste_export import layer_suchen, projekt_finden, projekt_lesen  # noqa: E402

INTERNE_IDS = {'fid', 'fid_1', 'ogc_fid'}   # werden nie übertragen, jede Datei vergibt eigene
FOTO_TABELLE = 'fotos'
FOTO_ORDNER = 'fotos'
FOTO_LAYER_ID = 'gokart_fotos'
FOTO_SQL = (f'CREATE TABLE "{FOTO_TABELLE}" (fid INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, '
            'flaeche_id TEXT, taxon_id INTEGER, datei TEXT, kommentar TEXT, aufgenommen_am TEXT, '
            'lon REAL, lat REAL)')   # taxon_id bleibt frei (Standortfotos), für spätere Artfotos reserviert
PLUGIN_ORDNER = Path(__file__).resolve().parents[2] / 'qfield_plugin'
PLUGIN_QML = 'GoKart_Wohnung.qml'
PLUGIN_DATEIEN = ('gokart_suche.js', 'gokart_icon.svg', 'gokart_foto.svg')


class Seite:
    """Eine Projektseite (PC oder Tablet) mit Zugriff auf Artnachweise, Fotos und eigene Synonyme."""

    def __init__(self, name, qgs):
        self.name, self.qgs = name, qgs
        layer, var = projekt_lesen(qgs)
        self.an = layer_suchen(layer, var.get('gokart_nachweis_layer'), 'artnachweise')
        self.es = layer_suchen(layer, None, 'eigene_synonyme')
        self.fk = var.get('gokart_nachweis_fk') or 'flaeche_id'
        if not self.an:
            raise SystemExit(f'{name}: Layer mit Artnachweisen nicht gefunden ({qgs})')
        # Fotos liegen in derselben GeoPackage wie die Artnachweise
        self.fo = {'datei': self.an['datei'], 'tabelle': FOTO_TABELLE, 'name': FOTO_TABELLE}

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
        return {(str(d.get(self.fk)), str(d.get('taxon_id'))): d for d in daten}

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

    def fotolayer_im_projekt(self):
        root = ET.parse(self.qgs).getroot()
        return any(ml.findtext('id') == FOTO_LAYER_ID for ml in root.iter('maplayer'))

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
    return f'{d.get(fk)} · {name} ({am})'


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
    paare = [(PLUGIN_ORDNER / PLUGIN_QML, tb.home / (tb.qgs.stem + '.qml'))]
    paare += [(PLUGIN_ORDNER / n, tb.home / n) for n in PLUGIN_DATEIEN if (PLUGIN_ORDNER / n).is_file()]
    return paare


def plugin_pruefen(tb):
    return [z.name for q, z in plugin_ziele(tb) if not z.is_file() or not filecmp.cmp(q, z, shallow=False)]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('pc', help='PC-Projekt: .qgs oder Projektordner')
    ap.add_argument('tablet', help='Tablet-Export: .zip oder Ordner')
    ap.add_argument('--ausfuehren', action='store_true', help='Unterschiede wirklich übernehmen')
    ap.add_argument('--weglassen', action='append', default=[], metavar='FLÄCHE:TAXON_ID',
                    help='Nachweis auf beiden Seiten entfernen')
    ap.add_argument('--foto-weglassen', action='append', default=[], metavar='DATEINAME',
                    help='Fotoeintrag auf beiden Seiten entfernen (Bilddatei bleibt liegen)')
    ap.add_argument('--ohne-plugin', action='store_true', help='QField-Plugin im Tablet-Zip nicht aktualisieren')
    a = ap.parse_args()

    tablet_pfad = Path(a.tablet).expanduser().resolve()
    if Path(a.pc).suffix.lower() == '.zip':
        raise SystemExit('Das PC-Projekt muss ein Ordner oder eine .qgs sein (kein Zip).')
    with tempfile.TemporaryDirectory() as tmp:
        pc = Seite('PC', projekt_finden(a.pc, None))
        # Tablet-Stand immer in einer Arbeitskopie bearbeiten, das Original bleibt unberührt
        if tablet_pfad.is_dir():
            shutil.copytree(tablet_pfad, Path(tmp) / 'tablet')
            tb = Seite('Tablet', projekt_finden(Path(tmp) / 'tablet', None))
        else:
            tb = Seite('Tablet', projekt_finden(tablet_pfad, tmp))

        # --- Artnachweise
        n_pc, n_tb = pc.nachweise(), tb.nachweise()
        weg = {tuple(w.split(':', 1)) for w in a.weglassen}
        nur_pc = [k for k in n_pc if k not in n_tb and k not in weg]
        nur_tb = [k for k in n_tb if k not in n_pc and k not in weg]
        beide = [k for k in n_pc if k in n_tb]
        upd_pc, upd_tb, konflikt = ergaenzungen(n_pc, n_tb, ('bemerkung',))
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
        layer_tb = not tb.fotolayer_im_projekt()

        # --- Eigene Synonyme
        s_pc, s_tb = pc.synonyme(), tb.synonyme()
        syn_nur_pc = [k for k in s_pc if k not in s_tb]
        syn_nur_tb = [k for k in s_tb if k not in s_pc]

        plugin_neu = [] if a.ohne_plugin else plugin_pruefen(tb)

        # --- Bericht
        print(f'PC:     {len(n_pc)} Nachweise, {len(f_pc)} Fotos, {len(s_pc)} eigene Synonyme  ({pc.qgs})')
        print(f'Tablet: {len(n_tb)} Nachweise, {len(f_tb)} Fotos, {len(s_tb)} eigene Synonyme  ({tablet_pfad})')
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
        if weg_pc or weg_tb or fweg_pc or fweg_tb:
            print(f'Wird entfernt: Nachweise {len(weg_pc)} PC / {len(weg_tb)} Tablet, '
                  f'Fotoeinträge {len(fweg_pc)} PC / {len(fweg_tb)} Tablet')
        for k, feld, w_pc, w_tb in konflikt + fkonflikt:
            print(f'⚠ {feld} unterschiedlich, bleibt wie es ist: {k}\n     PC: {w_pc!r}  Tablet: {w_tb!r}')
        if tabelle_pc or tabelle_tb or layer_tb:
            print(f'Fototabelle wird angelegt: PC {"ja" if tabelle_pc else "-"}, Tablet {"ja" if tabelle_tb else "-"}'
                  f'{", Layer im Tablet-Projekt eintragen" if layer_tb else ""}')
        if plugin_neu:
            print(f'QField-Plugin wird aktualisiert: {", ".join(plugin_neu)}')

        nichts = not (nur_pc or nur_tb or upd_pc or upd_tb or weg_pc or weg_tb or fnur_pc or fnur_tb
                      or fupd_pc or fupd_tb or fweg_pc or fweg_tb or datei_zum_pc or datei_zum_tb
                      or syn_nur_pc or syn_nur_tb or tabelle_pc or tabelle_tb or layer_tb or plugin_neu)
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

        def anwenden(seite, n_neu, n_upd, n_weg, f_neu, f_upd, f_weg, syn_neu, dateien, quelle_home, tabelle):
            if tabelle:
                seite.fototabelle_anlegen()
            seite.fotos()                                          # Spaltenliste (neu) lesen
            seite.schreiben(seite.an, seite.an_cols, seite.an_pk, n_neu, n_weg, (seite.fk, 'taxon_id'))
            seite.aktualisieren(seite.an, n_upd, (seite.fk, 'taxon_id'))
            seite.schreiben(seite.fo, seite.fo_cols, seite.fo_pk, f_neu, [(k,) for k in f_weg], ('datei',))
            seite.aktualisieren(seite.fo, [((k,), feld, wert) for k, feld, wert in f_upd], ('datei',))
            if seite.es and syn_neu:
                seite.schreiben(seite.es, seite.es_cols, seite.es_pk, syn_neu)
            for f in dateien:
                (seite.home / f).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(quelle_home / f, seite.home / f)

        print('\nPC-Projekt aktualisieren …')
        sichern(pc_dateien)
        anwenden(pc, [fuer(pc, n_tb[k]) for k in nur_tb], upd_pc, weg_pc,
                 [f_tb[k] for k in fnur_tb], fupd_pc, fweg_pc, [s_tb[k] for k in syn_nur_tb],
                 datei_zum_pc, tb.home, tabelle_pc)

        print('Tablet-Zip erstellen …')
        anwenden(tb, [fuer(tb, n_pc[k]) for k in nur_pc], upd_tb, weg_tb,
                 [f_pc[k] for k in fnur_pc], fupd_tb, fweg_tb, [s_pc[k] for k in syn_nur_pc],
                 datei_zum_tb, pc.home, tabelle_tb)
        (tb.home / FOTO_ORDNER).mkdir(exist_ok=True)
        if layer_tb:
            tb.fotolayer_eintragen()
        for q, z in ([] if a.ohne_plugin else plugin_ziele(tb)):
            shutil.copy2(q, z)

        stamm = tablet_pfad.stem if tablet_pfad.suffix.lower() == '.zip' else tablet_pfad.name
        stamm = stamm.split('_abgleich_')[0]           # nicht bei jedem Lauf verlängern
        ziel = tablet_pfad.with_name(f'{stamm}_abgleich_{datetime.now():%Y-%m-%d_%H%M}.zip')
        basis = tb.home
        with zipfile.ZipFile(ziel, 'w', zipfile.ZIP_DEFLATED) as z:
            for p in sorted(basis.rglob('*')):
                if p.is_file() and not p.name.endswith(('-wal', '-shm', '.bak', '~')):
                    z.write(p, p.relative_to(basis))
            z.writestr(FOTO_ORDNER + '/', '')          # leeren Fotoordner mitnehmen
        print(f'\n✓ Fertig. PC: {len(pc.nachweise())} Nachweise / {len(pc.fotos())} Fotos, '
              f'Tablet: {len(tb.nachweise())} Nachweise / {len(tb.fotos())} Fotos')
        print(f'→ Fürs Tablet: {ziel}')


if __name__ == '__main__':
    main()
