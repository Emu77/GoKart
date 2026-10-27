"""GoKart – welche Erfassungen ein Projekt nutzt (Arten, Fotos, Biotoptypen).

Reines Python, ohne QGIS – gemeinsam für Desktop-Plugin und qfield/werkzeuge/build_gokart_projekt.py.

Projektvariable gokart_module, kommagetrennt, z. B. "arten,biotope".
Fehlt die Variable (ältere Projekte), gelten alle Module – so ändert sich für bestehende Projekte nichts.
Das QField-Plugin (GoKart_Wohnung.qml) liest dieselbe Variable und zeigt nur die passenden Knöpfe.
"""

VAR_MODULE = 'gokart_module'
ARTEN, FOTOS, BIOTOPE = 'arten', 'fotos', 'biotope'
ALLE = (ARTEN, FOTOS, BIOTOPE)
NAMEN = {ARTEN: 'Pflanzenarten', FOTOS: 'Standortfotos', BIOTOPE: 'Biotoptypen'}


def lesen(text):
    """Variablenwert -> Menge der aktiven Module. Leer/fehlend = alle."""
    if text is None or str(text).strip() in ('', 'NULL'):
        return set(ALLE)
    teile = {t.strip().lower() for t in str(text).replace(';', ',').split(',')}
    return {m for m in ALLE if m in teile}


def als_text(module):
    """Menge -> Variablenwert in fester Reihenfolge."""
    return ','.join(m for m in ALLE if m in module)


def pruefen(text):
    """Für Kommandozeilen: unbekannte Namen melden, leere Auswahl ablehnen."""
    teile = [t.strip().lower() for t in str(text).replace(';', ',').split(',') if t.strip()]
    falsch = [t for t in teile if t not in ALLE]
    if falsch:
        raise ValueError(f'Unbekannte Module: {", ".join(falsch)} (erlaubt: {", ".join(ALLE)})')
    if not teile:
        raise ValueError('Mindestens ein Modul angeben.')
    return set(teile)
