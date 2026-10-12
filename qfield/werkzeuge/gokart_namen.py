"""GoKart – Aufbereitung deutscher Pflanzennamen zu Suchvarianten.

normalisieren() MUSS identisch zu normalisieren() in plugin/gokart_suche.js bleiben.
"""
import html
import re

# Gleiche Tabelle wie in gokart_suche.js
ZEICHEN = {
    'ä': 'a', 'ö': 'o', 'ü': 'u', 'ß': 'ss', 'é': 'e', 'è': 'e', 'ê': 'e', 'ë': 'e',
    'á': 'a', 'à': 'a', 'â': 'a', 'å': 'a', 'í': 'i', 'ì': 'i', 'î': 'i', 'ï': 'i',
    'ó': 'o', 'ò': 'o', 'ô': 'o', 'ú': 'u', 'ù': 'u', 'û': 'u', 'ç': 'c', 'ñ': 'n',
    'ø': 'o', 'æ': 'ae', 'œ': 'oe', '×': 'x',
}


def normalisieren(text):
    s = str(text or '').lower()
    s = ''.join(ZEICHEN.get(ch, ch) for ch in s)
    return re.sub(r'[^a-z0-9]', '', s)


_ZUSATZ = re.compile(r'\s*\b(i\.\s*e\.\s*S\.|i\.\s*w\.\s*S\.|s\.\s*str\.|s\.\s*l\.|agg\.)', re.I)


def _bereinigen(teil):
    teil = html.unescape(teil).replace('\t', ' ')
    teil = re.sub(r'^\s*Artengruppe\s*', '', teil)
    teil = re.sub(r'\((Unterart|Varietät|Sektion|Artengruppe|Gattung)\)', '', teil)
    teil = _ZUSATZ.sub('', teil)
    return re.sub(r'\s+', ' ', teil).strip(' ,;')


def varianten(deutscher_name):
    """Liefert (anzeige_name, [suchvarianten]) für einen BfN-Namenseintrag.

    Beispiele:
      'Eiche (Unterart), Stiel-'       -> 'Stiel-Eiche'
      'Herbstaster, Glatte'            -> 'Glatte Herbstaster'
      'Holz-Apfel, Wild-Apfel'         -> 'Holz-Apfel', 'Wild-Apfel'
      '(Dolden-) Spurre'               -> 'Spurre', 'Dolden-Spurre'
    """
    if not deutscher_name:
        return None, []
    roh = _bereinigen(deutscher_name)
    teile = [t.strip() for t in roh.split(',') if t.strip()]
    if not teile:
        return None, []
    basis = re.sub(r'\([^)]*\)', '', teile[0]).strip()
    ergebnis, umgedreht = [], False
    for i, teil in enumerate(teile):
        if i > 0 and teil.endswith('-') and ' ' not in teil:
            ergebnis.append(teil + basis)                      # "Stiel-" + "Eiche"
            umgedreht = True
        elif (i > 0 and len(teile) == 2 and ' ' not in teil and '-' not in teil
              and ' ' not in basis and teil[:1].isupper()
              and re.search(r'(e|er|es|en)$', teil)):
            ergebnis.append(f'{teil} {basis}')                  # "Glatte Herbstaster"
            umgedreht = True
        else:
            ergebnis.append(teil)
    if umgedreht and len(teile) == 2:
        ergebnis = [ergebnis[1]]        # nur vollständigen Namen; Basis ("Eiche") wäre irreführend
    # Klammerzusätze: "(Dolden-) Spurre" -> "Spurre" und "Dolden-Spurre"
    final = []
    for v in ergebnis:
        m = re.match(r'^\(([^)]*)\)\s*(.+)$', v)
        if m:
            final += [m.group(2).strip(), m.group(1).strip() + m.group(2).strip()]
        else:
            final.append(re.sub(r'\s*\([^)]*\)\s*', ' ', v).strip())
    anzeige = final[0]
    gesehen, eindeutig = set(), []
    for v in final:
        k = normalisieren(v)
        if k and k not in gesehen:
            gesehen.add(k)
            eindeutig.append(v)
    return anzeige, eindeutig


if __name__ == '__main__':
    for t in ['Eiche (Unterart), Stiel-', 'Herbstaster, Glatte', 'Holz-Apfel, Wild-Apfel',
              '(Dolden-) Spurre', 'Gewöhnlicher Dost i.e.S.', 'Artengruppe &#9;Frühlings-Hungerblümchen',
              'Strand-Aster, Salz-Aster, Pannonien-Salzaster', 'Stiel-Eiche', 'Bärenklau, Grünblühende',
              "Ziz' Habichtskraut", 'Wachsblume (Unterart), Alpen-']:
        print(f'{t!r:50} -> {varianten(t)}')
