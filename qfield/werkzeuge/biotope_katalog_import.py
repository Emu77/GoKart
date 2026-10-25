#!/usr/bin/env python3
"""GoKart – Biotoptypen-Katalog aus einer Quelldatei erzeugen bzw. ergänzen.

Ergebnis ist eine Katalog-CSV für qgis_plugin/gokart_desktop/biotope_kataloge/ (Spalten
code;name;nr;obercode;ebene;bund_code;ffh_lrt, Kopfzeilen '# feld: wert'). Danach mit
biotope_einspielen.py ins Projekt übernehmen.

Quellen:
  --pdf DATEI      Kartierschlüssel als PDF (braucht pdftotext: sudo apt install poppler-utils)
                   --muster klammer      Zeilen "1.7.1 Name (WCN)"      (Niedersachsen, Hamburg, Bremen)
                   --muster code-zuerst  Zeilen "WMy Name" / "1.1.1 WNR Name" (Schleswig-Holstein, M-V)
                   --muster bund         Zeilen "34.07.01.01 Name"     (BfN Rote Liste)
                   --seiten 5-20         nur diese PDF-Seiten (Übersicht/Inhaltsverzeichnis) – dringend empfohlen
  --tabelle DATEI  Excel (.xlsx, braucht openpyxl) oder CSV; --code-spalte/--name-spalte (Spaltenüberschrift
                   oder Buchstabe A, B …), optional --nr-spalte, --ffh-spalte, --bund-spalte, --blatt
  --text DATEI     Zeilen "code;name" oder "nr;code;name"

Beispiele:
  python3 biotope_katalog_import.py --pdf Kartierschluessel_NI_2021.pdf --muster klammer --seiten 3-14 \\
      --schluessel NI --name "Kartierschlüssel für Biotoptypen in Niedersachsen" --stand "03/2021, Korr. 03/2023" \\
      --aus ../../qgis_plugin/gokart_desktop/biotope_kataloge/NI.csv --zusammenfuehren
  python3 biotope_katalog_import.py --tabelle Standardliste_SH.xlsx --code-spalte A --name-spalte B \\
      --aus ../../qgis_plugin/gokart_desktop/biotope_kataloge/SH.csv --zusammenfuehren --vollstaendig ja

Ohne --aus wird nur eine Vorschau ausgegeben. Immer die Vorschau mit dem Original vergleichen!
"""
import argparse
import csv
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'qgis_plugin' / 'gokart_desktop'))
import biotope as B  # noqa: E402

LEADER = re.compile(r'\s*(?:\.\s*){3,}\s*\d*\s*$|\s{3,}\d{1,3}\s*$')    # Punktlinie + Seitenzahl am Zeilenende
NR = r'(\d{1,2}(?:\.\d{1,2}){0,3})'


def pdf_text(pfad, seiten=None):
    if not shutil.which('pdftotext'):
        raise SystemExit('pdftotext fehlt: sudo apt install poppler-utils')
    cmd = ['pdftotext', '-layout', '-enc', 'UTF-8']
    if seiten:
        von, _, bis = seiten.partition('-')
        cmd += ['-f', von, '-l', bis or von]
    cmd += [str(pfad), '-']
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout


def sauber(s):
    s = LEADER.sub('', s)
    return re.sub(r'\s+', ' ', s).strip(' .')


def verbinden(a, b):
    """Zeilenumbruch zusammenfügen: 'Hainbuchen-' + 'mischwald' → 'Hainbuchenmischwald',
    'Erlen-' + 'Bruchwald' → 'Erlen-Bruchwald', 'Eichen-' + 'und …' → 'Eichen- und …'."""
    if a.endswith('-') and b:
        erstes = b.split()[0]
        if erstes in ('und', 'oder', 'bzw', 'bzw.', 'sowie'):
            return a + ' ' + b
        return a[:-1] + b if b[0].islower() else a + b
    return a + ' ' + b


def parse_klammer(text):
    """'1.7.1 Eichen- und Hainbuchenmischwald nasser, … Standorte (WCN) …… 52', auch über mehrere Zeilen.
    Obergruppen ohne Code ('1 WÄLDER') bekommen den Code '01' usw."""
    zeilen, puffer = [], None
    start = re.compile(r'^\s*' + NR + r'\s+(\S.*)$')
    # hinter dem Code können Schutz-/FFH-Markierungen stehen: "(WCN) §", "(WCN) ß" (Symbolschrift), "(WCN) (§) FFH"
    ende = re.compile(r'^(.*?)\s*\(([A-ZÄÖÜ][A-ZÄÖÜ0-9]{1,3})\)(?:\s*(?:§|ß|\(§\)|\(ß\)|\*|FFH|\d{4}\*?|[•●○]))*\s*$')
    def obergruppe(p):
        # '1 WÄLDER' / '13 GEBÄUDE, VERKEHRS- UND INDUSTRIEFLÄCHEN' (ohne Code, in Großbuchstaben)
        if p and '.' not in p[0] and p[1].upper() == p[1] and re.search('[A-ZÄÖÜ]{3}', p[1]):
            zeilen.append({'nr': p[0], 'code': p[0].zfill(2), 'name': p[1]})   # Schreibweise wie im Original

    for roh in text.splitlines():
        z = sauber(roh)
        if not z:
            continue
        m = start.match(z)
        if m:
            obergruppe(puffer)                 # offene Zeile ohne Code: nur Obergruppen übernehmen
            puffer = [m.group(1), m.group(2)]
        elif puffer:
            puffer[1] = verbinden(puffer[1], z)
        else:
            continue
        e = ende.match(puffer[1])
        if e:
            zeilen.append({'nr': puffer[0], 'code': e.group(2), 'name': sauber(e.group(1))})
            puffer = None
        elif len(puffer[1]) > 250:            # kein Code gefunden → verwerfen
            puffer = None
    return zeilen


def parse_code_zuerst(text):
    """'WMy Sonstiger Laubwald …' (SH: Großbuchstabe + optional Großbuchstabe + optional Kleinbuchstabe)
    oder '1.1.1 WNR Name' (Nummer vor dem Code)."""
    zeilen = []
    m1 = re.compile(r'^\s*(?:' + NR + r'\s+)?([A-ZÄÖÜ](?:[A-ZÄÖÜ]{1,3}[a-z]?)?)\s+([A-ZÄÖÜ(][^\s].*)$')
    for roh in text.splitlines():
        m = m1.match(sauber(roh))
        if m:
            zeilen.append({'nr': m.group(1) or '', 'code': m.group(2), 'name': sauber(m.group(3))})
    return zeilen


def parse_bund(text):
    m1 = re.compile(r'^\s*(\d{2}(?:\.\d{2}){0,4}[a-z]?)\s+([A-ZÄÖÜ(].*)$')
    return [{'nr': '', 'code': m.group(1), 'name': sauber(m.group(2))}
            for m in (m1.match(sauber(z)) for z in text.splitlines()) if m]


def spalte(kopf, angabe):
    if angabe is None:
        return None
    if angabe in kopf:
        return kopf.index(angabe)
    if re.fullmatch(r'[A-Za-z]{1,2}', angabe):
        n = 0
        for c in angabe.upper():
            n = n * 26 + ord(c) - 64
        return n - 1
    raise SystemExit(f'Spalte "{angabe}" nicht gefunden. Vorhanden: {", ".join(map(str, kopf))}')


def lies_tabelle(pfad, a):
    if pfad.suffix.lower() in ('.xlsx', '.xlsm'):
        try:
            import openpyxl
        except ImportError:
            raise SystemExit('openpyxl fehlt: pip install --user openpyxl (oder als CSV speichern)')
        wb = openpyxl.load_workbook(pfad, read_only=True, data_only=True)
        ws = wb[a.blatt] if a.blatt else wb.active
        reihen = [['' if v is None else str(v).strip() for v in r] for r in ws.iter_rows(values_only=True)]
    else:
        with open(pfad, encoding='utf-8-sig', newline='') as f:
            probe = f.read(4096)
            f.seek(0)
            reihen = [[c.strip() for c in r] for r in csv.reader(f, csv.Sniffer().sniff(probe, ';,\t'))]
    kopf = reihen[0]
    ic, iname = spalte(kopf, a.code_spalte), spalte(kopf, a.name_spalte)
    inr, iffh, ibund = spalte(kopf, a.nr_spalte), spalte(kopf, a.ffh_spalte), spalte(kopf, a.bund_spalte)
    daten = reihen[1:] if a.code_spalte in kopf or a.name_spalte in kopf else reihen

    def w(r, i):
        return r[i] if i is not None and i < len(r) else ''
    return [{'code': w(r, ic), 'name': w(r, iname), 'nr': w(r, inr), 'ffh_lrt': w(r, iffh), 'bund_code': w(r, ibund)}
            for r in daten if w(r, ic) and w(r, iname)]


def lies_text(pfad):
    zeilen = []
    for z in Path(pfad).read_text(encoding='utf-8-sig').splitlines():
        t = [x.strip() for x in z.split(';')]
        if len(t) >= 3:
            nr, code, name = t[:3]
            zeilen.append({'nr': nr, 'code': code or nr.zfill(2), 'name': name})
        elif len(t) == 2:
            zeilen.append({'nr': '', 'code': t[0], 'name': t[1]})
    return zeilen


def eindeutig(zeilen):
    """Erstes Vorkommen eines Codes behalten (Übersicht steht vor dem Textteil)."""
    gesehen, aus = set(), []
    for r in zeilen:
        if r['code'] not in gesehen:
            gesehen.add(r['code'])
            aus.append({k: r.get(k, '') or '' for k in B.KATALOG_SPALTEN})
    return aus


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    q = ap.add_mutually_exclusive_group(required=True)
    q.add_argument('--pdf', type=Path)
    q.add_argument('--tabelle', type=Path)
    q.add_argument('--text', type=Path)
    ap.add_argument('--muster', choices=('klammer', 'code-zuerst', 'bund'), default='klammer')
    ap.add_argument('--seiten', help='PDF-Seiten, z. B. 3-14')
    for s in ('code', 'name', 'nr', 'ffh', 'bund'):
        ap.add_argument(f'--{s}-spalte', default={'code': 'A', 'name': 'B'}.get(s))
    ap.add_argument('--blatt', help='Tabellenblatt (Excel)')
    ap.add_argument('--aus', type=Path, help='Katalog-CSV schreiben (sonst nur Vorschau)')
    ap.add_argument('--zusammenfuehren', action='store_true',
                    help='vorhandene --aus-Datei ergänzen: neue Codes hinzu, bund_code/ffh_lrt bleiben erhalten')
    for m in B.META_FELDER:
        ap.add_argument(f'--{m}')
    a = ap.parse_args()

    if a.pdf:
        text = pdf_text(a.pdf, a.seiten)
        zeilen = {'klammer': parse_klammer, 'code-zuerst': parse_code_zuerst, 'bund': parse_bund}[a.muster](text)
    elif a.tabelle:
        zeilen = lies_tabelle(a.tabelle, a)
    else:
        zeilen = lies_text(a.text)
    zeilen = B.hierarchie_ergaenzen(eindeutig(zeilen))
    print(f'{len(zeilen)} Biotoptypen gelesen')
    for r in zeilen[:8] + ([{'code': '…', 'name': ''}] if len(zeilen) > 16 else []) + zeilen[-8:]:
        print(f"  {r.get('nr', ''):8} {r['code']:7} {r['name']}")
    for h in B.pruefen(zeilen)[:30]:
        print('  ⚠ ' + h)
    if not a.aus:
        print('\nNur Vorschau. Schreiben mit --aus <datei.csv>')
        return

    meta = {}
    if a.aus.exists() and a.zusammenfuehren:
        meta, alt = B.katalog_lesen(a.aus)
        nach_code = {r['code']: r for r in alt}
        neu = 0
        for r in zeilen:
            if r['code'] in nach_code:
                vorh = nach_code[r['code']]
                if vorh['name'] != r['name']:
                    print(f"  ~ {r['code']}: „{vorh['name']}“ → „{r['name']}“")
                for k in ('bund_code', 'ffh_lrt'):
                    r[k] = r.get(k) or vorh.get(k, '')
            else:
                neu += 1
        bekannt = {r['code'] for r in zeilen}
        weg = [r for r in alt if r['code'] not in bekannt]
        zeilen += weg      # nichts verlieren, was nur im alten Katalog steht
        print(f'Zusammengeführt: {neu} neu, {len(weg)} nur im alten Katalog (bleiben erhalten)')
    elif a.aus.exists():
        raise SystemExit(f'{a.aus} existiert – mit --zusammenfuehren ergänzen oder andere Datei wählen.')
    for m in B.META_FELDER:
        if getattr(a, m):
            meta[m] = getattr(a, m)
    meta.setdefault('schluessel', a.aus.stem.upper())
    B.katalog_schreiben(a.aus, meta, B.hierarchie_ergaenzen(zeilen))
    print(f'Geschrieben: {a.aus} ({len(zeilen)} Einträge)')


if __name__ == '__main__':
    main()
