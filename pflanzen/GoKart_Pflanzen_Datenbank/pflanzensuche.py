#!/usr/bin/env python3
"""GoKart: Offline-Pflanzensuche für FloraWeb/GoKart SQLite.

Benötigt nur die Python-Standardbibliothek.
"""
import argparse
import difflib
import re
import sqlite3
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent / 'GoKart_Pflanzen.sqlite'


def norm(value):
    """Umlaute, Leerzeichen, Bindestriche und Satzzeichen vereinheitlichen."""
    s = str(value or '').casefold().replace('ß', 'ss')
    s = s.replace('ä', 'ae').replace('ö', 'oe').replace('ü', 'ue')
    s = ''.join(ch for ch in unicodedata.normalize('NFKD', s)
                if not unicodedata.combining(ch))
    return ''.join(ch for ch in s if ch.isalnum())


def words(value):
    s = str(value or '').casefold().replace('ß', 'ss')
    s = re.sub(r'[^\w]+', ' ', s, flags=re.UNICODE)
    return [w for w in s.split() if w]


def rank(query, candidate, kind):
    q, c = norm(query), norm(candidate)
    if not q or not c:
        return 0.0
    if q == c:
        return 1.0
    base = difflib.SequenceMatcher(None, q, c).ratio()
    # Besonders wertvoll: kompletter Gattungs-/Namensbestandteil, z. B. "Eiche".
    if len(q) >= 4 and c.endswith(q):
        base = max(base, 0.88)
    if len(q) >= 4 and c.startswith(q):
        base = max(base, 0.86)
    # Gleiches letztes Wort, z. B. Stiel-Eiche / Rot-Eiche.
    qwords, cwords = words(query), words(candidate)
    if len(qwords) > 1 and len(cwords) > 1 and qwords[-1] == cwords[-1]:
        base = max(base, 0.74)
    # Sehr schwache Treffer unterdrücken.
    return base


def read_candidates(con):
    taxa = {}
    for tid, sci, german in con.execute(
        'SELECT taxon_id, wissenschaftlicher_name, deutscher_name FROM taxon'
    ):
        taxa[tid] = (sci or '', german or '')
    candidates = defaultdict(list)
    seen = set()

    def add(tid, label, kind):
        if tid not in taxa or not label or not str(label).strip():
            return
        key = (tid, norm(label))
        if not key[1] or key in seen:
            return
        seen.add(key)
        candidates[tid].append((str(label).strip(), kind))

    for tid, (sci, german) in taxa.items():
        add(tid, german, 'deutsch')
        add(tid, sci, 'wissenschaftlich')
    for tid, label in con.execute(
        'SELECT taxon_id, wissenschaftlicher_name FROM namen'
    ):
        add(tid, label, 'Synonym')
    for tid, label in con.execute(
        'SELECT taxon_id, synonym FROM eigene_synonyme'
    ):
        add(tid, label, 'eigener Suchbegriff')
    return taxa, candidates


def search(con, query, limit=5):
    taxa, candidates = read_candidates(con)
    results = []
    for tid, entries in candidates.items():
        scored = [(rank(query, label, kind), label, kind)
                  for label, kind in entries]
        if not scored:
            continue
        score, label, kind = max(scored, key=lambda x: x[0])
        if score < 0.35:
            continue
        sci, german = taxa[tid]
        results.append({'taxon_id': tid, 'wissenschaftlich': sci,
                        'deutsch': german, 'score': score,
                        'treffer': label, 'typ': kind})
    results.sort(key=lambda r: (-r['score'], r['deutsch'] or r['wissenschaftlich'], r['taxon_id']))
    return results[:limit]


def add_alias(con, taxon_id, alias):
    if not norm(alias):
        raise ValueError('Der Suchbegriff darf nicht leer sein.')
    if not con.execute('SELECT 1 FROM taxon WHERE taxon_id=?', (taxon_id,)).fetchone():
        raise ValueError(f'Taxon-ID {taxon_id} ist nicht vorhanden.')
    exists = con.execute(
        'SELECT 1 FROM eigene_synonyme WHERE taxon_id=? AND synonym=? COLLATE NOCASE',
        (taxon_id, alias)
    ).fetchone()
    if exists:
        return False
    with con:
        con.execute('INSERT INTO eigene_synonyme(taxon_id, synonym) VALUES (?, ?)',
                    (taxon_id, alias.strip()))
    return True


def print_results(query, results):
    print(f'\nSuche: {query}')
    if not results:
        print('Keine passenden Pflanzen gefunden.')
        return
    for i, r in enumerate(results, 1):
        display = r['deutsch'] or '(kein deutscher Name)'
        print(f"{i}. {display} — {r['wissenschaftlich']} "
              f"| Taxon-ID {r['taxon_id']} | {r['score']:.0%}")
        if r['typ'] not in ('deutsch', 'wissenschaftlich'):
            print(f"   Treffer über {r['typ']}: {r['treffer']}")


def main():
    parser = argparse.ArgumentParser(description='Offline-Pflanzensuche für GoKart')
    parser.add_argument('suchbegriff', nargs='*', help='Pflanzenname; ohne Angabe interaktive Suche')
    parser.add_argument('--db', type=Path, default=DEFAULT_DB, help='Pfad zur GoKart_Pflanzen.sqlite')
    parser.add_argument('--anzahl', type=int, default=5, help='Anzahl Vorschläge (Standard: 5)')
    parser.add_argument('--alias', nargs=2, metavar=('TAXON_ID', 'SUCHBEGRIFF'),
                        help='Eigenen Suchbegriff für eine Taxon-ID speichern')
    args = parser.parse_args()
    if not args.db.is_file():
        parser.error(f'Datenbank nicht gefunden: {args.db}\n'
                     'Lege pflanzensuche.py neben GoKart_Pflanzen.sqlite oder verwende --db.')
    try:
        con = sqlite3.connect(str(args.db))
        if args.alias:
            tid = int(args.alias[0])
            added = add_alias(con, tid, args.alias[1])
            print('Suchbegriff gespeichert.' if added else 'Suchbegriff war bereits vorhanden.')
        elif args.suchbegriff:
            query = ' '.join(args.suchbegriff)
            print_results(query, search(con, query, max(1, args.anzahl)))
        else:
            print('GoKart-Pflanzensuche (Ende mit Enter oder Strg+C)')
            while True:
                try:
                    query = input('\nPflanzenname: ').strip()
                except (EOFError, KeyboardInterrupt):
                    print()
                    break
                if not query:
                    break
                print_results(query, search(con, query, max(1, args.anzahl)))
    except (sqlite3.Error, ValueError) as e:
        print(f'Fehler: {e}', file=sys.stderr)
        return 1
    finally:
        con.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
