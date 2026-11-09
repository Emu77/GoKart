"""GoKart – welche Erfassungen ein Projekt nutzt (Arten, Fotos, Biotoptypen, Punktaufnahmen).

Reines Python, ohne QGIS – gemeinsam für Desktop-Plugin und werkzeuge/build_gokart_projekt.py.

Projektvariable gokart_module, kommagetrennt, z. B. "arten,biotope" oder "arten,punkte".
"punkte" = Artnachweise auch an GPS-Punkten ohne Fläche (Layer aufnahme_punkte, siehe punkte.py).
Fehlt die Variable (ältere Projekte), gelten alle Module – so ändert sich für bestehende Projekte nichts.
Das QField-Plugin (gokart.qml) liest dieselbe Variable und zeigt nur die passenden Knöpfe.
"""

VAR_MODULE = 'gokart_module'
ARTEN, FOTOS, BIOTOPE, PUNKTE = 'arten', 'fotos', 'biotope', 'punkte'
ALLE = (ARTEN, FOTOS, BIOTOPE, PUNKTE)
NAMEN = {ARTEN: 'Pflanzenarten', FOTOS: 'Standortfotos', BIOTOPE: 'Biotoptypen', PUNKTE: 'Punktaufnahmen (GPS)'}


def lesen(text):
    """Variablenwert -> Menge der aktiven Module. Leer/fehlend = alle bis auf Punktaufnahmen
    (ältere Projekte haben keinen Punkt-Layer)."""
    if text is None or str(text).strip() in ('', 'NULL'):
        return set(ALLE) - {PUNKTE}
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
