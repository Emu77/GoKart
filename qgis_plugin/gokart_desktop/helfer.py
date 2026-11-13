"""GoKart Desktop – Pfade und Hilfen für die eingebauten Werkzeuge.

Im Plugin-ZIP (werkzeuge/plugin_zip.py) liegen neben dem Plugin:
    qfield_plugin/   das QField-Projekt-Plugin (gokart.qml + js/svg)
    werkzeuge/       abgleich.py, build_gokart_projekt.py, artenliste_export.py, gokart_namen.py
    vorlage/         gokart.gpkg (Artenliste, leere Erfassungstabellen)
Beim Entwickeln (Plugin als Link aufs Repo) werden dieselben Ordner im Repo gefunden.
"""
import contextlib
import importlib
import io
import sys
import traceback
from pathlib import Path

PLUGIN_ORDNER = Path(__file__).resolve().parent
REPO = PLUGIN_ORDNER.parents[1]          # nur beim Entwickeln sinnvoll


def _ordner(name):
    for p in (PLUGIN_ORDNER / name, REPO / name):
        if p.is_dir():
            return p
    return None


def werkzeuge_ordner():
    return _ordner('werkzeuge')


def qfield_plugin_ordner():
    return _ordner('qfield_plugin')


def vorlage_im_plugin():
    p = PLUGIN_ORDNER / 'vorlage' / 'gokart.gpkg'
    return p if p.is_file() else None


def daten_ordner():
    """Benutzerordner für Vosk-Pakete und -Modelle (bleibt bei Plugin-Updates erhalten)."""
    try:
        from qgis.core import QgsApplication
        basis = Path(QgsApplication.qgisSettingsDirPath())
    except Exception:  # außerhalb von QGIS (Tests)
        basis = Path.home() / '.gokart'
    p = basis / 'gokart'
    p.mkdir(parents=True, exist_ok=True)
    return p


def python_pakete_ordner():
    return daten_ordner() / 'python'


def werkzeug(name):
    """Modul aus werkzeuge/ laden (abgleich, build_gokart_projekt …)."""
    ordner = werkzeuge_ordner()
    if ordner is None:
        raise RuntimeError('Ordner „werkzeuge“ fehlt im Plugin – bitte das vollständige GoKart-Plugin-ZIP installieren.')
    if str(ordner) not in sys.path:
        sys.path.insert(0, str(ordner))
    return importlib.import_module(name)


def ausfuehren(funktion, *args, **kwargs):
    """Ruft funktion auf und fängt Bildschirmausgabe und Abbrüche (SystemExit) ab.
    Gibt (ok, ergebnis, text) zurück."""
    puffer = io.StringIO()
    ok, ergebnis = True, None
    with contextlib.redirect_stdout(puffer), contextlib.redirect_stderr(puffer):
        try:
            ergebnis = funktion(*args, **kwargs)
        except SystemExit as e:
            if e.code not in (None, 0):
                ok = False
                if not isinstance(e.code, int):
                    print(e.code)
        except Exception:
            ok = False
            traceback.print_exc()
    return ok, ergebnis, puffer.getvalue().strip()


def qfield_plugin_dateien(projektdatei):
    """[(Quelle, Name im Projektordner)] – gokart.qml heißt wie die Projektdatei, sonst lädt QField es nicht."""
    ordner = qfield_plugin_ordner()
    if ordner is None or not (ordner / 'gokart.qml').is_file():
        raise RuntimeError('QField-Plugin (qfield_plugin/gokart.qml) fehlt im GoKart-Plugin.')
    paare = []
    for p in sorted(ordner.iterdir()):
        if not p.is_file() or p.name.startswith('.') or p.suffix.lower() not in ('.qml', '.js', '.svg', '.png'):
            continue
        paare.append((p, Path(projektdatei).stem + '.qml' if p.name == 'gokart.qml' else p.name))
    return paare
