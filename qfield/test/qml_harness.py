#!/usr/bin/env python3
"""GoKart – Testumgebung für das QField-Plugin ohne QField.

Simuliert iface, qgisProject, QfLayerUtils/QfFeatureUtils (QField 4.x) mit Daten aus gokart.gpkg
und spielt einen Erfassungsablauf durch. Aufruf:
    QT_QPA_PLATFORM=offscreen python3 test/qml_harness.py qfield_projekt [screenshot.png]
"""
import re
import sqlite3
import sys
from pathlib import Path

from PySide6.QtCore import QObject, Property, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6 import QtQuick  # noqa: F401 (registriert QQuickItem*-Konverter)

PROJEKT = Path(sys.argv[1]).resolve()
GPKG = PROJEKT / 'gokart.gpkg'
FEHLER = []
BEHALTEN = []   # an QML übergebene Python-Objekte am Leben halten (sonst Segfault)


class Feature(QObject):
    def __init__(self, fields, werte, fid=None):
        super().__init__()
        self._fields, self._w, self._fid = fields, dict(werte), fid

    @Slot(str, result='QVariant')
    def attribute(self, name):
        return self._w.get(name)

    @Slot(int, 'QVariant')
    def setAttribute(self, i, v):
        self._w[self._fields.names[i]] = v

    @Property('QVariant', constant=True)
    def id(self):
        return self._fid


class Fields(QObject):
    def __init__(self, names):
        super().__init__()
        self.names = names

    @Slot(str, result=int)
    def indexFromName(self, n):
        return self.names.index(n) if n in self.names else -1


class Crs(QObject):
    @Property(str, constant=True)
    def authid(self):
        return 'EPSG:25833'


class Iterator(QObject):
    def __init__(self, feats):
        super().__init__()
        self._f, self._i = feats, 0

    @Slot(result=bool)
    def hasNext(self):
        return self._i < len(self._f)

    @Slot(result=QObject)
    def next(self):
        self._i += 1
        return self._f[self._i - 1]

    @Slot()
    def close(self):
        pass


class Layer(QObject):
    def __init__(self, name):
        super().__init__()
        self._name = name
        con = sqlite3.connect(GPKG)
        cur = con.execute(f'SELECT * FROM "{name}"')
        self._fields = Fields([d[0] for d in cur.description if d[0] != 'geom'])
        self.rows = [dict(zip([d[0] for d in cur.description], r)) for r in cur.fetchall()]
        con.close()
        self.puffer, self.loeschen, self.edit = [], [], False
        self._crs = Crs()

    @Property(QObject, constant=True)
    def fields(self):
        return self._fields

    @Property(QObject, constant=True)
    def crs(self):
        return self._crs

    @Slot(result=bool)
    def startEditing(self):
        self.edit = True
        return True

    @Slot(result=bool)
    def commitChanges(self):
        con = sqlite3.connect(GPKG)
        for w in self.puffer:
            w = {k: v for k, v in w.items() if k != 'fid' and v is not None}
            con.execute(f'INSERT INTO "{self._name}" ({",".join(w)}) VALUES ({",".join("?" * len(w))})', list(w.values()))
        for fid in self.loeschen:
            con.execute(f'DELETE FROM "{self._name}" WHERE fid=?', (fid,))
        con.commit()
        cur = con.execute(f'SELECT * FROM "{self._name}"')
        self.rows = [dict(zip([d[0] for d in cur.description], r)) for r in cur.fetchall()]
        con.close()
        self.puffer, self.loeschen, self.edit = [], [], False
        return True

    @Slot(result=bool)
    def rollBack(self):
        self.puffer, self.loeschen, self.edit = [], [], False
        return True

    def features(self, ausdruck=None):
        rows = self.rows
        if ausdruck:
            if ausdruck.startswith('intersects('):
                rows = [r for r in rows if r.get('flaeche_id') == 'F-002']   # Simulation: Punkt liegt in F-002
            else:
                for feld, wert in re.findall(r'"(\w+)" = (\'(?:[^\']|\'\')*\'|[\d.]+)', ausdruck):
                    wert = wert[1:-1].replace("''", "'") if wert.startswith("'") else float(wert)
                    rows = [r for r in rows if r.get(feld) == wert]
        fs = [Feature(self._fields, r, r.get('fid')) for r in rows]; BEHALTEN.extend(fs); return fs


class Utils(QObject):
    @Slot(QObject, result=QObject)
    def createFeatureIterator(self, layer):
        it = Iterator(layer.features()); BEHALTEN.append(it); return it

    @Slot(QObject, str, result=QObject)
    def createFeatureIteratorFromExpression(self, layer, expr):
        it = Iterator(layer.features(expr)); BEHALTEN.append(it); return it

    @Slot(QObject, QObject, result=bool)
    def addFeature(self, layer, f):
        if not layer.edit:
            FEHLER.append('addFeature ohne Bearbeitungsmodus')
            return False
        layer.puffer.append(f._w)
        return True

    @Slot(QObject, QObject, 'QVariant', bool, result=bool)
    def deleteFeature(self, project, layer, fid, flush):
        layer.loeschen.append(fid)
        return True

    @Slot(QObject, result=QObject)
    def createFeature(self, layer):
        f = Feature(layer.fields, {n: None for n in layer.fields.names}); BEHALTEN.append(f); return f


class Project(QObject):
    def __init__(self):
        super().__init__()
        self.layers = {n: Layer(n) for n in ('flaechen', 'taxon', 'suchnamen', 'eigene_synonyme', 'artnachweise')}

    @Slot(str, result='QVariantList')
    def mapLayersByName(self, n):
        return [self.layers[n]] if n in self.layers else []


class Pos(QObject):
    @Property(bool, constant=True)
    def latitudeValid(self): return True
    @Property(bool, constant=True)
    def longitudeValid(self): return True
    @Property(float, constant=True)
    def latitude(self): return 52.512
    @Property(float, constant=True)
    def longitude(self): return 13.337


class Positioning(QObject):
    def __init__(self):
        super().__init__()
        self._p = Pos()

    @Property(QObject, constant=True)
    def positionInformation(self):
        return self._p


class Iface(QObject):
    def __init__(self, win):
        super().__init__()
        self.win, self.toasts, self.toolbar = win, [], []
        self._pos = Positioning()

    @Slot(result=QObject)
    def mainWindow(self):
        return self.win

    @Slot(QObject)   # Slot(QQuickItem) löst in PySide6 6.12 einen QML-Typfehler aus
    def addItemToPluginsToolbar(self, item):
        self.toolbar.append(item)
        item.setProperty('parent', self.win.property('contentItem'))

    @Slot(result=QObject)
    def positioning(self):
        return self._pos

    @Slot(str, result=QObject)
    def findItemByObjectName(self, n):
        return None


app = QGuiApplication(sys.argv)
engine = QQmlEngine()
engine.warnings.connect(lambda ws: [FEHLER.append(w.toString()) for w in ws])
utils = Utils()
# qmlRegisterSingletonInstance ist in PySide6 6.12 fehlerhaft -> Mock-Modul als QML-Singleton
modul = Path(__file__).resolve().parent / 'mock_qml' / 'org' / 'qfield' / 'core'
modul.mkdir(parents=True, exist_ok=True)
(modul / 'qmldir').write_text('module org.qfield.core\nsingleton QfLayerUtils 1.0 QfLayerUtils.qml\nsingleton QfFeatureUtils 1.0 QfLayerUtils.qml\n')
(modul / 'QfLayerUtils.qml').write_text('''pragma Singleton
import QtQuick
QtObject {
  function createFeatureIterator(l) { return _utils.createFeatureIterator(l) }
  function createFeatureIteratorFromExpression(l, e) { return _utils.createFeatureIteratorFromExpression(l, e) }
  function addFeature(l, f) { return _utils.addFeature(l, f) }
  function deleteFeature(p, l, fid, flush) { return _utils.deleteFeature(p, l, fid, flush) }
  function createFeature(l) { return _utils.createFeature(l) }
}
''')
engine.addImportPath(str(modul.parent.parent.parent))
engine.rootContext().setContextProperty('_utils', utils)

# Hauptfenster mit displayToast() wie in QField
fenster_qml = b'''
import QtQuick
import QtQuick.Window
Window { width: 420; height: 860; visible: true; color: "#ddd"
  property var toasts: []
  function displayToast(t) { toasts.push(t); console.log("TOAST: " + t) } }
'''
wc = QQmlComponent(engine)
wc.setData(fenster_qml, QUrl('fenster.qml'))
win = wc.create()
if win is None:
    sys.exit('Fenster: ' + str(wc.errors()))

projekt = Project()
iface = Iface(win)
ctx = engine.rootContext()
ctx.setContextProperty('iface', iface)
ctx.setContextProperty('qgisProject', projekt)

comp = QQmlComponent(engine, QUrl.fromLocalFile(str(PROJEKT / 'gokart.qml')))
plugin = comp.create(ctx)
if plugin is None:
    sys.exit('Plugin-Fehler: ' + '\n'.join(e.toString() for e in comp.errors()))
plugin.setProperty('parent', win.property('contentItem'))


def prop(name):
    x = plugin.property(name)
    return x.toVariant() if hasattr(x, 'toVariant') else x


def schritt(n):
    print(f"Schritt {n}", flush=True)
    try:
        _schritt(n)
    except Exception as e:  # Test abbrechen statt hängen
        import traceback
        traceback.print_exc()
        app.exit(2)


def _schritt(n):
    p = plugin
    if n == 0:
        assert len(iface.toolbar) == 1, 'Toolbar-Knopf fehlt'
        p.oeffnen()
    elif n == 1:
        assert p.property('index') is not None, 'Index nicht geladen'
        p.flaecheAusGps()
        assert p.property('aktiveFlaeche') == 'F-002', p.property('aktiveFlaeche')
        feld = win.findChild(QObject, '') and None
        p.setProperty('letzteMeldung', '')
        sf = finde('sucheFeld')
        sf.setProperty('text', 'Stil Eiche')
    elif n == 2:
        tr = prop('treffer')
        print('Treffer:', [t['taxon']['deutscher_name'] for t in tr])
        assert tr and tr[0]['taxon']['wissenschaftlicher_name'] == 'Quercus robur'
        p.setProperty('auswahlIndex', 0)
        cb = finde('synonymMerken')
        print('Synonym-Checkbox sichtbar:', cb.property('visible'))
        cb.setProperty('checked', True)
        if len(sys.argv) > 2:
            win.grabWindow().save(sys.argv[2].replace('.png', '_treffer.png'))
        p.speichern()
    elif n == 3:
        arten = prop('artenDerFlaeche')
        print('Arten auf F-002:', [a['name'] for a in arten])
        assert len(arten) == 1
        finde('sucheFeld').setProperty('text', 'stil eiche')
    elif n == 4:
        tr = prop('treffer')
        print('Nach Synonym:', [(t['taxon']['deutscher_name'], t['trefferart'], t['exakt']) for t in tr][:2])
        assert tr[0]['exakt'] and tr[0]['trefferart'] == 'eigen'
        p.speichern()     # Duplikat -> Hinweis, kein zweiter Eintrag
    elif n == 5:
        assert len(prop('artenDerFlaeche')) == 1, 'Duplikat wurde gespeichert'
        finde('sucheFeld').setProperty('text', 'Spitzwegerich')
    elif n == 6:
        p.speichern()
    elif n == 7:
        print('Arten auf F-002:', [a['name'] for a in prop('artenDerFlaeche')])
        assert len(prop('artenDerFlaeche')) == 2
        if len(sys.argv) > 2:
            win.grabWindow().save(sys.argv[2])
        fid = prop('artenDerFlaeche')[0]['fid']
        p.eintragLoeschen(fid)
    elif n == 8:
        assert len(prop('artenDerFlaeche')) == 1
        t = win.property('toasts'); print('Toasts:', t.toVariant() if hasattr(t, 'toVariant') else t)
        warn = [f for f in FEHLER if 'gokart' in f.lower() or 'addFeature' in f]
        print('QML-Warnungen:', warn or 'keine')
        app.exit(1 if warn else 0)
        return
    QTimer.singleShot(400, lambda: schritt(n + 1))


def finde(name):
    on = {'sucheFeld': 'gokartSucheFeld', 'synonymMerken': 'gokartSynonymMerken'}[name]
    for wurzel in (plugin, win):
        for o in wurzel.findChildren(QObject):
            if o.objectName() == on:
                return o
    raise AssertionError(f'{name} nicht gefunden')


QTimer.singleShot(300, lambda: schritt(0))
code = app.exec()
print('ERGEBNIS:', 'OK' if code == 0 else 'FEHLER')
sys.exit(code)
