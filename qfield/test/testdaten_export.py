#!/usr/bin/env python3
"""Exportiert taxon + suchnamen aus gokart.gpkg als testdaten.json für test_suche.js.
Aufruf: python3 test/testdaten_export.py qfield_projekt/gokart.gpkg testdaten.json"""
import json, sqlite3, sys
c = sqlite3.connect(sys.argv[1])
d = {'taxa': [dict(zip(['taxon_id', 'wissenschaftlicher_name', 'deutscher_name', 'rang'], r))
              for r in c.execute('SELECT taxon_id, wissenschaftlicher_name, anzeige_name, rang FROM taxon')],
     'namen': [list(r) for r in c.execute('SELECT taxon_id, name, art, schluessel FROM suchnamen')]}
json.dump(d, open(sys.argv[2], 'w'), ensure_ascii=False)
print(len(d['taxa']), 'Taxa,', len(d['namen']), 'Suchnamen')
