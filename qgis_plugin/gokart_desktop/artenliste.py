"""GoKart – Artenliste je Fläche (Gutachten-Tabelle) als HTML und CSV.

Reines Python ohne QGIS-Abhängigkeit, damit es sowohl vom Desktop-Plugin als auch
vom Kommandozeilen-Werkzeug qfield/werkzeuge/artenliste_export.py genutzt werden kann.

Eingabe ist eine Liste von Nachweisen (dicts) mit den Schlüsseln:
    flaeche_id, flaeche_name, flaeche_m2, taxon_id, wiss, autor, deutsch, rang, eingabe, erfasst_am
Fehlende Werte dürfen None oder '' sein.
"""
import csv
import html
from collections import OrderedDict
from datetime import datetime

RANG_TEXT = {'GAT': 'Gattung', 'AGG': 'Artengruppe', 'SSP': 'Unterart', 'VAR': 'Varietät', 'SEC': 'Sektion'}


def _txt(v):
    return '' if v is None or str(v) == 'NULL' else str(v).strip()


def _flaeche_sortkey(fid):
    """W-2 vor W-10: Zahlenanteile numerisch sortieren."""
    import re
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r'(\d+)', _txt(fid))]


def _datum(v):
    s = _txt(v).replace('T', ' ')
    try:
        return datetime.fromisoformat(s).strftime('%d.%m.%Y')
    except ValueError:
        return s[:10]


def _m2(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return ''
    return f'{x:.2f} m²'.replace('.', ',') if x > 0 else ''


def gruppieren(nachweise):
    """{flaeche_id: {'name', 'm2', 'arten': [nachweis, …] (eindeutig je Taxon, alphabetisch)}}"""
    flaechen = {}
    for n in nachweise:
        fid = _txt(n.get('flaeche_id')) or '(ohne Fläche)'
        f = flaechen.setdefault(fid, {'name': _txt(n.get('flaeche_name')), 'm2': n.get('flaeche_m2'), 'arten': {}})
        key = n.get('taxon_id') or _txt(n.get('wiss')) or _txt(n.get('deutsch'))
        alt = f['arten'].get(key)
        # bei Doppelerfassung das früheste Datum behalten
        if alt is None or _txt(n.get('erfasst_am')) < _txt(alt.get('erfasst_am')):
            f['arten'][key] = n
    ergebnis = OrderedDict()
    for fid in sorted(flaechen, key=_flaeche_sortkey):
        f = flaechen[fid]
        f['arten'] = sorted(f['arten'].values(), key=lambda a: (_txt(a.get('wiss')) or _txt(a.get('deutsch'))).lower())
        ergebnis[fid] = f
    return ergebnis


def gesamtliste(gruppen):
    """[(nachweis, [flaeche_ids])] alphabetisch – Grundlage für Stetigkeit / Tabelle Art × Fläche."""
    arten = {}
    for fid, f in gruppen.items():
        for a in f['arten']:
            key = a.get('taxon_id') or _txt(a.get('wiss')) or _txt(a.get('deutsch'))
            arten.setdefault(key, [a, []])[1].append(fid)
    return sorted(arten.values(), key=lambda x: (_txt(x[0].get('wiss')) or _txt(x[0].get('deutsch'))).lower())


def _flaechen_titel(fid, f):
    teile = [fid]
    if f['name']:
        teile.append(f['name'])
    titel = ' – '.join(teile)
    m2 = _m2(f['m2'])
    return titel + (f' ({m2})' if m2 else '')


def _autor(a):
    """Autorkürzel; in der Taxon-Tabelle steht teils der volle Name inkl. Autor."""
    wiss, autor = _txt(a.get('wiss')), _txt(a.get('autor'))
    return autor[len(wiss):].strip() if wiss and autor.startswith(wiss) else autor


def _wiss_html(a):
    wiss, autor, rang = _txt(a.get('wiss')), _autor(a), _txt(a.get('rang'))
    s = f'<i>{html.escape(wiss)}</i>'
    if autor:
        s += f' <span class="autor">{html.escape(autor)}</span>'
    if rang in RANG_TEXT:
        s += f' <span class="rang">({RANG_TEXT[rang]})</span>'
    return s


def html_schreiben(pfad, nachweise, titel='GoKart – Artenliste je Fläche', projekt=''):
    gruppen = gruppieren(nachweise)
    gesamt = gesamtliste(gruppen)
    stand = datetime.now().strftime('%d.%m.%Y %H:%M')
    o = []
    o.append(f'''<!doctype html><html lang="de"><head><meta charset="utf-8">
<title>{html.escape(titel)}</title>
<style>
 body{{font-family:"DejaVu Sans",Arial,sans-serif;font-size:10.5pt;color:#1b1b1b;margin:2cm;max-width:21cm}}
 h1{{font-size:16pt;margin:0 0 .2em;color:#167d50}} h2{{font-size:12pt;margin:1.6em 0 .4em;border-bottom:1px solid #167d50;page-break-after:avoid}}
 .meta{{color:#555;margin-bottom:1.2em}} table{{border-collapse:collapse;width:100%;margin-bottom:.4em}}
 th,td{{border-bottom:1px solid #ddd;padding:3px 6px;text-align:left;vertical-align:top}}
 th{{background:#eef5f0;font-weight:600}} td.nr,th.nr{{width:2.2em;text-align:right;color:#666}}
 td.dat{{white-space:nowrap;color:#555;width:6.5em}} .autor{{color:#666;font-size:9pt}} .rang{{color:#888;font-size:9pt}}
 .summe{{color:#555;font-size:9.5pt}} td.x{{text-align:center}} th.v{{writing-mode:vertical-rl;transform:rotate(180deg);font-weight:400;font-size:8.5pt;white-space:nowrap}}
 @media print{{body{{margin:0}} h2{{break-after:avoid}} tr{{break-inside:avoid}}}}
</style></head><body>
<h1>{html.escape(titel)}</h1>
<div class="meta">{html.escape(projekt) + ' · ' if projekt else ''}Stand {stand} · {len(gruppen)} Flächen · {len(gesamt)} Taxa · {sum(len(f["arten"]) for f in gruppen.values())} Nachweise</div>''')

    for fid, f in gruppen.items():
        o.append(f'<h2>{html.escape(_flaechen_titel(fid, f))}</h2><table>'
                 '<tr><th class="nr">Nr.</th><th>Wissenschaftlicher Name</th><th>Deutscher Name</th><th>Erfasst</th></tr>')
        for i, a in enumerate(f['arten'], 1):
            o.append(f'<tr><td class="nr">{i}</td><td>{_wiss_html(a)}</td>'
                     f'<td>{html.escape(_txt(a.get("deutsch")))}</td><td class="dat">{_datum(a.get("erfasst_am"))}</td></tr>')
        n = len(f['arten'])
        o.append(f'</table><div class="summe">{n} {"Taxon" if n == 1 else "Taxa"}</div>')

    # Gesamtartenliste mit Stetigkeit (Anzahl Flächen) – wie Anhang einer Kartierung
    o.append('<h2>Gesamtartenliste</h2><table><tr><th class="nr">Nr.</th><th>Wissenschaftlicher Name</th>'
             '<th>Deutscher Name</th><th>Flächen</th><th>Stetigkeit</th></tr>')
    for i, (a, fids) in enumerate(gesamt, 1):
        stet = f'{100 * len(fids) / len(gruppen):.0f} %' if gruppen else ''
        o.append(f'<tr><td class="nr">{i}</td><td>{_wiss_html(a)}</td><td>{html.escape(_txt(a.get("deutsch")))}</td>'
                 f'<td>{len(fids)}</td><td>{stet}</td></tr>')
    o.append('</table>')

    # Tabelle Art × Fläche (Vegetationstabelle, nur Präsenz)
    if 1 < len(gruppen) <= 40:
        o.append('<h2>Tabelle Art × Fläche</h2><table><tr><th>Taxon</th>'
                 + ''.join(f'<th class="v">{html.escape(fid)}</th>' for fid in gruppen) + '</tr>')
        for a, fids in gesamt:
            name = _txt(a.get('deutsch')) or _txt(a.get('wiss'))
            o.append(f'<tr><td>{html.escape(name)}</td>'
                     + ''.join(f'<td class="x">{"●" if fid in fids else ""}</td>' for fid in gruppen) + '</tr>')
        o.append('</table>')

    o.append('</body></html>')
    with open(pfad, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(o))
    return len(gruppen), len(gesamt)


def csv_schreiben(pfad, nachweise):
    """Eine Zeile je Art und Fläche – zum Weiterverarbeiten in LibreOffice."""
    gruppen = gruppieren(nachweise)
    with open(pfad, 'w', newline='', encoding='utf-8-sig') as fh:
        w = csv.writer(fh, delimiter=';')
        w.writerow(['Flächen-ID', 'Fläche', 'Fläche m²', 'Nr.', 'Wissenschaftlicher Name', 'Autor',
                    'Deutscher Name', 'Rang', 'Erfasst am'])
        for fid, f in gruppen.items():
            for i, a in enumerate(f['arten'], 1):
                w.writerow([fid, f['name'], _txt(f['m2']).replace('.', ','), i, _txt(a.get('wiss')), _autor(a),
                            _txt(a.get('deutsch')), _txt(a.get('rang')),
                            _txt(a.get('erfasst_am')).replace('T', ' ')])
