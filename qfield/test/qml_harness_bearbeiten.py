#!/usr/bin/env python3
"""GoKart – Testumgebung für das Bearbeiten von Artnachweisen im QField-Plugin (ohne QField).

Legt in einem Temp-Ordner ein Mini-Projekt an (3 Taxa, 2 Flächen, 2 Nachweise), lädt das Plugin aus
qfield_plugin/ und spielt durch: letzte Art korrigieren (Art tauschen + Bemerkung), Duplikat abweisen,
Fläche ändern, Bemerkung leeren. Prüft jeweils den Inhalt der Datenbank.

Aufruf (aus dem Repo-Hauptordner):
    QT_QPA_PLATFORM=offscreen python3 qfield/test/qml_harness_bearbeiten.py [screenshot.png]
"""
import re
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QObject, Property, QTimer, QUrl, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6 import QtQuick  # noqa: F401 (registriert QQuickItem*-Konverter)

REPO = Path(__file__).resolve().parents[2]
PLUGIN = REPO / 'qfield_plugin'
TMP = Path(tempfile.mkdtemp(prefix='gokart_bearbeiten_'))
GPKG = TMP / 'gokart.gpkg'
SCREENSHOT = sys.argv[1] if len(sys.argv) > 1 else None
FEHLER = []
BEHALTEN = []   # an QML übergebene Python-Objekte am Leben halten (sonst Segfault)


def projekt_anlegen():
    shutil.copy2(PLUGIN / 'GoKart_Wohnung.qml', TMP / 'gokart.qml')
    for f in PLUGIN.iterdir():
        if f.suffix in ('.js', '.svg'):
            shutil.copy2(f, TMP / f.name)
    con = sqlite3.connect(GPKG)
    con.executescript('''
        CREATE TABLE taxon (fid INTEGER PRIMARY KEY, taxon_id INTEGER, wissenschaftlicher_name TEXT,
            deutscher_name TEXT, anzeige_name TEXT, rang TEXT, autor_name TEXT);
        CREATE TABLE suchnamen (fid INTEGER PRIMARY KEY, taxon_id INTEGER, name TEXT, art TEXT, schluessel TEXT);
        CREATE TABLE eigene_synonyme (fid INTEGER PRIMARY KEY, taxon_id INTEGER, synonym TEXT, schluessel TEXT,
            angelegt_am TEXT);
        CREATE TABLE flaechen (fid INTEGER PRIMARY KEY, flaeche_id TEXT, name TEXT, bemerkung TEXT);
        CREATE TABLE artnachweise (fid INTEGER PRIMARY KEY, flaeche_id TEXT, taxon_id INTEGER,
            wissenschaftlicher_name TEXT, deutscher_name TEXT, original_eingabe TEXT, erfasst_am TEXT,
            bemerkung TEXT, geaendert_am TEXT, ersetzt TEXT);
    ''')
    taxa = [(1, 'Quercus robur', 'Stiel-Eiche'), (2, 'Quercus petraea', 'Trauben-Eiche'),
            (3, 'Plantago lanceolata', 'Spitz-Wegerich')]
    for tid, wiss, de in taxa:
        con.execute('INSERT INTO taxon (taxon_id, wissenschaftlicher_name, deutscher_name, anzeige_name, rang) '
                    'VALUES (?,?,?,?,?)', (tid, wiss, de, de, 'SPE'))
        con.execute('INSERT INTO suchnamen (taxon_id, name, art) VALUES (?,?,?)', (tid, de, 'deutsch'))
        con.execute('INSERT INTO suchnamen (taxon_id, name, art) VALUES (?,?,?)', (tid, wiss, 'wissenschaftlich'))
    con.executemany('INSERT INTO flaechen (flaeche_id, name) VALUES (?,?)', [('F-001', 'Wiese'), ('F-002', 'Waldrand')])
    con.executemany('INSERT INTO artnachweise (flaeche_id, taxon_id, wissenschaftlicher_name, deutscher_name, '
                    'original_eingabe, erfasst_am) VALUES (?,?,?,?,?,?)',
                    [('F-001', 1, 'Quercus robur', 'Stiel-Eiche', 'stieleiche', '2026-10-01T10:00:00'),
                     ('F-001', 3, 'Plantago lanceolata', 'Spitz-Wegerich', 'spitz wegerich', '2026-10-01T10:05:00')])
    con.commit()
    con.close()


def db(fid):
    con = sqlite3.connect(GPKG)
    con.row_factory = sqlite3.Row
    r = con.execute('SELECT * FROM artnachweise WHERE fid=?', (fid,)).fetchone()
    con.close()
    return dict(r) if r else None


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
        return 'EPSG:25832'


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
        self._fields = None
        self.laden()
        self.puffer, self.loeschen, self.aendern, self.edit = [], [], [], False
        self._crs = Crs()

    def laden(self):
        con = sqlite3.connect(GPKG)
        cur = con.execute(f'SELECT * FROM "{self._name}"')
        if self._fields is None:
            self._fields = Fields([d[0] for d in cur.description])
        self.rows = [dict(zip([d[0] for d in cur.description], r)) for r in cur.fetchall()]
        con.close()

    @Property(QObject, constant=True)
    def fields(self):
        return self._fields

    @Property(QObject, constant=True)
    def crs(self):
        return self._crs

    @Property(str, constant=True)
    def name(self):
        return self._name

    @Slot(result=bool)
    def isEditable(self):
        return self.edit

    @Slot(result='QStringList')
    def commitErrors(self):
        return []

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
        for fid, i, v in self.aendern:
            con.execute(f'UPDATE "{self._name}" SET "{self._fields.names[i]}"=? WHERE fid=?', (v, fid))
        for fid in self.loeschen:
            con.execute(f'DELETE FROM "{self._name}" WHERE fid=?', (fid,))
        con.commit()
        con.close()
        self.laden()
        self.puffer, self.loeschen, self.aendern, self.edit = [], [], [], False
        return True

    @Slot('QVariant', int, 'QVariant', result=bool)
    def changeAttributeValue(self, fid, i, v):
        if not self.edit:
            FEHLER.append('changeAttributeValue ohne Bearbeitungsmodus')
            return False
        self.aendern.append((int(fid), i, v))
        return True

    @Slot(result=bool)
    def rollBack(self):
        self.puffer, self.loeschen, self.aendern, self.edit = [], [], [], False
        return True

    def features(self, ausdruck=None):
        rows = self.rows
        if ausdruck:
            for feld, wert in re.findall(r'"(\w+)" = (\'(?:[^\']|\'\')*\'|[\d.]+)', ausdruck):
                wert = wert[1:-1].replace("''", "'") if wert.startswith("'") else float(wert)
                rows = [r for r in rows if r.get(feld) == wert]
        fs = [Feature(self._fields, r, r.get('fid')) for r in rows]
        BEHALTEN.extend(fs)
        return fs


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

    @Slot(str, result=QObject)
    def mapLayer(self, ref):
        return None

    @Property(str, constant=True)
    def homePath(self):
        return str(TMP)


class Iface(QObject):
    def __init__(self, win):
        super().__init__()
        self.win, self.toolbar = win, []

    @Slot(result=QObject)
    def mainWindow(self):
        return self.win

    @Slot(QObject)
    def addItemToPluginsToolbar(self, item):
        self.toolbar.append(item)
        item.setProperty('parent', self.win.property('contentItem'))

    @Slot(str)
    def logMessage(self, t):
        pass

    @Slot(result=QObject)
    def positioning(self):
        return None

    @Slot(str, result=QObject)
    def findItemByObjectName(self, n):
        return None


projekt_anlegen()
app = QGuiApplication(sys.argv)
engine = QQmlEngine()
engine.warnings.connect(lambda ws: [FEHLER.append(w.toString()) for w in ws])
utils = Utils()
modul = TMP / 'mock_qml' / 'org' / 'qfield' / 'core'
modul.mkdir(parents=True, exist_ok=True)
(modul / 'qmldir').write_text('module org.qfield.core\nsingleton QfLayerUtils 1.0 QfLayerUtils.qml\n'
                              'singleton QfFeatureUtils 1.0 QfLayerUtils.qml\n')
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
engine.addImportPath(str(TMP / 'mock_qml'))
engine.rootContext().setContextProperty('_utils', utils)

wc = QQmlComponent(engine)
wc.setData(b'''
import QtQuick
import QtQuick.Window
Window { width: 420; height: 860; visible: true; color: "#ddd"
  property var toasts: []
  function displayToast(t) { toasts.push(t); console.log("TOAST: " + t) } }
''', QUrl('fenster.qml'))
win = wc.create()
if win is None:
    sys.exit('Fenster: ' + str(wc.errors()))

projekt = Project()
iface = Iface(win)
ctx = engine.rootContext()
ctx.setContextProperty('iface', iface)
ctx.setContextProperty('qgisProject', projekt)
ctx.setContextProperty('platformUtilities', None)

comp = QQmlComponent(engine, QUrl.fromLocalFile(str(TMP / 'gokart.qml')))
plugin = comp.create(ctx)
if plugin is None:
    sys.exit('Plugin-Fehler: ' + '\n'.join(e.toString() for e in comp.errors()))
plugin.setProperty('parent', win.property('contentItem'))


def prop(name):
    x = plugin.property(name)
    return x.toVariant() if hasattr(x, 'toVariant') else x


def finde(objekt_name):
    for wurzel in (plugin, win):
        for o in wurzel.findChildren(QObject):
            if o.objectName() == objekt_name:
                return o
    raise AssertionError(f'{objekt_name} nicht gefunden')


def letzte_meldung():
    return str(prop('letzteMeldung'))


def schritt(n):
    print(f'Schritt {n}', flush=True)
    try:
        weiter = _schritt(n)
    except Exception:
        import traceback
        traceback.print_exc()
        app.exit(2)
        return
    if weiter:
        QTimer.singleShot(800 if weiter == 'warten' else 400, lambda: schritt(n + 1))


def _schritt(n):
    p = plugin
    if n == 0:
        p.oeffnen()
    elif n == 1:
        assert p.property('index') is not None, 'Index nicht geladen'
        p.flaecheWaehlen('F-001', 'Test')
        assert len(prop('artenDerFlaeche')) == 2
        p.letzteKorrigieren()
        b = prop('bearbeitung')
        assert b and b['name'] == 'Spitz-Wegerich', b
        assert prop('bearbeitFlaeche') == 'F-001'
        finde('gokartSucheFeld').setProperty('text', 'Trauben Eiche')
    elif n == 2:
        tr = prop('treffer')
        print('Treffer:', [t['taxon']['deutscher_name'] for t in tr])
        assert tr and tr[0]['taxon']['wissenschaftlicher_name'] == 'Quercus petraea'
        p.setProperty('auswahlIndex', 0)
        finde('gokartBemerkungFeld').setProperty('text', 'blühend')
        text = p.aenderungText()
        print('Knopf:', text)
        assert 'Trauben-Eiche' in text and 'Bemerkung' in text
        k = finde('gokartAenderKnopf')
        print('Änderungsknopf:', k.property('visible'), k.property('enabled'), k.property('text'), k.property('height'))
        assert k.property('visible') and k.property('enabled')
        if SCREENSHOT:
            QTimer.singleShot(300, lambda: (win.grabWindow().save(SCREENSHOT), p.aenderungSpeichern()))
            return 'warten'
        p.aenderungSpeichern()
    elif n == 3:
        r = db(2)
        print('DB nach Art-Tausch:', r)
        assert r['taxon_id'] == 2 and r['deutscher_name'] == 'Trauben-Eiche'
        assert r['bemerkung'] == 'blühend' and r['ersetzt'] == 'F-001:3' and r['geaendert_am']
        assert r['original_eingabe'] == 'Trauben Eiche' and r['erfasst_am'] == '2026-10-01T10:05:00'
        assert prop('bearbeitung') is None
        # Duplikat: Trauben-Eiche -> Stiel-Eiche (gibt es auf F-001 schon)
        eintrag = [a for a in prop('artenDerFlaeche') if a['fid'] == 2][0]
        assert eintrag['bemerkung'] == 'blühend'
        p.bearbeitenStarten(eintrag)
        finde('gokartSucheFeld').setProperty('text', 'Stiel-Eiche')
    elif n == 4:
        p.setProperty('auswahlIndex', 0)
        p.aenderungSpeichern()
        print('Meldung:', letzte_meldung())
        assert 'bereits erfasst' in letzte_meldung()
        assert db(2)['taxon_id'] == 2, 'Duplikat wurde gespeichert'
        p.bearbeitenBeenden()
        # Fläche ändern: Stiel-Eiche F-001 -> F-002
        eintrag = [a for a in prop('artenDerFlaeche') if a['fid'] == 1][0]
        p.bearbeitenStarten(eintrag)
        p.setProperty('bearbeitFlaeche', 'F-002')
        print('Knopf:', p.aenderungText())
        p.aenderungSpeichern()
    elif n == 5:
        r = db(1)
        print('DB nach Flächenwechsel:', r)
        assert r['flaeche_id'] == 'F-002' and r['ersetzt'] == 'F-001:1' and r['taxon_id'] == 1
        assert [a['fid'] for a in prop('artenDerFlaeche')] == [2]
        # Bemerkung leeren
        p.bearbeitenStarten(prop('artenDerFlaeche')[0])
        finde('gokartBemerkungFeld').setProperty('text', '')
        print('Knopf:', p.aenderungText())
        p.aenderungSpeichern()
    elif n == 6:
        r = db(2)
        print('DB nach Bemerkung leeren:', r)
        assert r['bemerkung'] is None and r['ersetzt'] == 'F-001:3'
        # optionale APIs (QfFileUtils, QfExpressionContextUtils) bildet der Mock nicht nach -> erwartet
        warn = [f for f in FEHLER if ('gokart' in f.lower() or 'ohne Bearbeitungsmodus' in f)
                and 'is not defined' not in f]
        print('QML-Warnungen:', warn or 'keine')
        app.exit(1 if warn else 0)
        return False
    return True


QTimer.singleShot(300, lambda: schritt(0))
code = app.exec()
shutil.rmtree(TMP, ignore_errors=True)
print('ERGEBNIS:', 'OK' if code == 0 else 'FEHLER')
sys.exit(code)
