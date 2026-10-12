#!/usr/bin/env python3
"""Einmaliger Export der bestehenden SQLite-Datenbank für die Offline-Websuche."""
import json
import sqlite3
from pathlib import Path

root = Path(__file__).resolve().parent
source = root.parent / 'GoKart_Pflanzen_Datenbank' / 'GoKart_Pflanzen.sqlite'
if not source.is_file():
    raise SystemExit(f'Datenbank fehlt: {source}\nBitte app/ neben GoKart_Pflanzen_Datenbank/ ablegen.')
con = sqlite3.connect(f'file:{source}?mode=ro', uri=True)
con.row_factory = sqlite3.Row
try:
    taxa = [dict(r) for r in con.execute('SELECT taxon_id, wissenschaftlicher_name, deutscher_name, rang FROM taxon')]
    namen = [dict(r) for r in con.execute('SELECT taxon_id, wissenschaftlicher_name, synonym_status FROM namen')]
    aliases = [dict(r) for r in con.execute('SELECT taxon_id, synonym FROM eigene_synonyme')]
finally:
    con.close()
data = {'taxa': taxa, 'namen': namen, 'aliases': aliases}
output = root / 'pflanzendaten.js'
output.write_text('window.GOKART_DATEN = ' + json.dumps(data, ensure_ascii=False, separators=(',', ':')) + ';\n', encoding='utf-8')
print(f'Fertig: {output}')
print(f'{len(taxa)} Taxa, {sum(bool(x["deutscher_name"]) for x in taxa)} deutsche Namen, {len(namen)} Namensdatensätze')
