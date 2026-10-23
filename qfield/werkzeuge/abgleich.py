#!/usr/bin/env python3
"""GoKart – gleicht Artnachweise und eigene Synonyme zwischen PC-Projekt und Tablet-Export ab.

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
  * Gibt es ihn auf beiden Seiten mit abweichender Bemerkung, wird nichts überschrieben, nur gemeldet.
  * Gelöschte Einträge kann das Skript nicht erkennen – sie kämen von der anderen Seite zurück.
    Dafür: --weglassen W-34:68005 (Fläche:taxon_id, mehrfach möglich) – wird dann auf beiden Seiten entfernt.

QGIS und QField vorher schließen bzw. das Projekt nicht geöffnet haben.
"""
import argparse
import shutil
import sqlite3
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from artenliste_export import layer_suchen, projekt_finden, projekt_lesen  # noqa: E402


INTERNE_IDS = {'fid', 'fid_1', 'ogc_fid'}   # werden nie übertragen, jede Datei vergibt eigene


class Seite:
    """Eine Projektseite (PC oder Tablet) mit Zugriff auf Artnachweise und eigene Synonyme."""

    def __init__(self, name, qgs):
        self.name, self.qgs = name, qgs
        layer, var = projekt_lesen(qgs)
        self.an = layer_suchen(layer, var.get('gokart_nachweis_layer'), 'artnachweise')
        self.es = layer_suchen(layer, None, 'eigene_synonyme')
        self.fk = var.get('gokart_nachweis_fk') or 'flaeche_id'
        if not self.an:
            raise SystemExit(f'{name}: Layer mit Artnachweisen nicht gefunden ({qgs})')

    @staticmethod
    def _spalten(con, tabelle):
        info = list(con.execute(f'PRAGMA table_info("{tabelle}")'))
        return [r[1] for r in info], [r[1] for r in info if r[5]]   # alle, Primärschlüssel

    def _lesen(self, layer):
        con = sqlite3.connect(layer['datei'])
        cols, pk = self._spalten(con, layer['tabelle'])
        daten = [dict(zip(cols, r)) for r in con.execute(f'SELECT * FROM "{layer["tabelle"]}"')]
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

    def schreiben(self, layer, cols, pk, neue, loeschen=(), fk=None):
        """Fügt Zeilen ein (gemeinsame Spalten, ohne Primärschlüssel) und löscht (fk, taxon_id)-Paare."""
        con = sqlite3.connect(layer['datei'])
        t = layer['tabelle']
        for d in neue:
            felder = [c for c in cols if c not in pk and c not in INTERNE_IDS and c in d and d[c] is not None]
            con.execute(f'INSERT INTO "{t}" ({", ".join(chr(34) + c + chr(34) for c in felder)}) '
                        f'VALUES ({", ".join("?" * len(felder))})', [d[c] for c in felder])
        for fl, tid in loeschen:
            con.execute(f'DELETE FROM "{t}" WHERE CAST("{fk}" AS TEXT) = ? AND CAST(taxon_id AS TEXT) = ?', (fl, tid))
        con.execute('UPDATE gpkg_ogr_contents SET feature_count = (SELECT count(*) FROM "%s") '
                    'WHERE table_name = ?' % t, (t,))
        con.commit()
        con.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        con.close()


def kurz(d, fk):
    name = d.get('deutscher_name') or d.get('wissenschaftlicher_name') or '?'
    am = str(d.get('erfasst_am') or '').replace('T', ' ')[:16]
    return f'{d.get(fk)} · {name} ({am})'


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


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('pc', help='PC-Projekt: .qgs oder Projektordner')
    ap.add_argument('tablet', help='Tablet-Export: .zip oder Ordner')
    ap.add_argument('--ausfuehren', action='store_true', help='Unterschiede wirklich übernehmen')
    ap.add_argument('--weglassen', action='append', default=[], metavar='FLÄCHE:TAXON_ID',
                    help='Nachweis auf beiden Seiten entfernen (z. B. versehentlich erfasst)')
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

        n_pc, n_tb = pc.nachweise(), tb.nachweise()
        weg = {tuple(w.split(':', 1)) for w in a.weglassen}
        nur_pc = [k for k in n_pc if k not in n_tb and k not in weg]
        nur_tb = [k for k in n_tb if k not in n_pc and k not in weg]
        beide = [k for k in n_pc if k in n_tb]
        konflikt = [k for k in beide if (n_pc[k].get('bemerkung') or '') != (n_tb[k].get('bemerkung') or '')]
        weg_pc = [k for k in weg if k in n_pc]
        weg_tb = [k for k in weg if k in n_tb]

        s_pc, s_tb = pc.synonyme(), tb.synonyme()
        syn_nur_pc = [k for k in s_pc if k not in s_tb]
        syn_nur_tb = [k for k in s_tb if k not in s_pc]

        print(f'PC:     {len(n_pc)} Nachweise, {len(s_pc)} eigene Synonyme  ({pc.qgs})')
        print(f'Tablet: {len(n_tb)} Nachweise, {len(s_tb)} eigene Synonyme  ({tablet_pfad})')
        print(f'Gemeinsam: {len(beide)}\n')
        for titel, keys, quelle, fk in (('Nur am PC → kommt aufs Tablet', nur_pc, n_pc, pc.fk),
                                        ('Nur auf dem Tablet → kommt auf den PC', nur_tb, n_tb, tb.fk)):
            print(f'{titel}: {len(keys)}')
            for k in sorted(keys):
                print(f'  + {kurz(quelle[k], fk)}   [--weglassen {k[0]}:{k[1]}]')
        if syn_nur_pc or syn_nur_tb:
            print(f'Eigene Synonyme: {len(syn_nur_pc)} nur PC, {len(syn_nur_tb)} nur Tablet → werden ergänzt')
            for k in syn_nur_pc:
                print(f'  + PC → Tablet: {s_pc[k].get("synonym")}')
            for k in syn_nur_tb:
                print(f'  + Tablet → PC: {s_tb[k].get("synonym")}')
        if weg_pc or weg_tb:
            print(f'Wird entfernt (--weglassen): {len(weg_pc)} am PC, {len(weg_tb)} auf dem Tablet')
        for k in konflikt:
            print(f'⚠ Bemerkung unterschiedlich, bleibt wie sie ist: {kurz(n_pc[k], pc.fk)}\n'
                  f'     PC: {n_pc[k].get("bemerkung")!r}  Tablet: {n_tb[k].get("bemerkung")!r}')

        nichts = not (nur_pc or nur_tb or syn_nur_pc or syn_nur_tb or weg_pc or weg_tb)
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

        print('\nPC-Projekt aktualisieren …')
        sichern(pc_dateien)
        pc.schreiben(pc.an, pc.an_cols, pc.an_pk, [fuer(pc, n_tb[k]) for k in nur_tb], weg_pc, pc.fk)
        if pc.es and syn_nur_tb:
            pc.schreiben(pc.es, pc.es_cols, pc.es_pk, [s_tb[k] for k in syn_nur_tb])

        print('Tablet-Zip erstellen …')
        tb.schreiben(tb.an, tb.an_cols, tb.an_pk, [fuer(tb, n_pc[k]) for k in nur_pc], weg_tb, tb.fk)
        if tb.es and syn_nur_pc:
            tb.schreiben(tb.es, tb.es_cols, tb.es_pk, [s_pc[k] for k in syn_nur_pc])
        stamm = tablet_pfad.stem if tablet_pfad.suffix.lower() == '.zip' else tablet_pfad.name
        stamm = stamm.split('_abgleich_')[0]           # nicht bei jedem Lauf verlängern
        ziel = tablet_pfad.with_name(f'{stamm}_abgleich_{datetime.now():%Y-%m-%d_%H%M}.zip')
        basis = tb.qgs.parent
        with zipfile.ZipFile(ziel, 'w', zipfile.ZIP_DEFLATED) as z:
            for p in sorted(basis.rglob('*')):
                if p.is_file() and not p.name.endswith(('-wal', '-shm', '.bak', '~')):
                    z.write(p, p.relative_to(basis))
        print(f'\n✓ Fertig. PC: {len(n_pc) + len(nur_tb) - len(weg_pc)} Nachweise, '
              f'Tablet: {len(n_tb) + len(nur_pc) - len(weg_tb)} Nachweise')
        print(f'→ Fürs Tablet: {ziel}')


if __name__ == '__main__':
    main()
