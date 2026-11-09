#!/usr/bin/env python3
"""GoKart – Testumgebung für Punktaufnahmen und Zusatzangaben im QField-Plugin (ohne QField).

Mini-Projekt mit Flächen, Punkt-Layer aufnahme_punkte und Artnachweisen (punkt_id, deckung, …). Spielt durch:
ungenaue Position abweisen, Punkt per GPS anlegen, Art mit Sprach-Nachsatz („…, Deckung zwei a, blühend“)
speichern, Schnellleiste, Duplikat, Abstandshinweis, Flächen-Modus, Bearbeiten („Deckung vier“),
Punkt per Fadenkreuz verschieben und neu setzen.
Geometrie-Funktionen sind vereinfacht nachgebildet (Koordinaten = Meter im Layer-KBS, keine Umrechnung).

Aufruf (aus dem Repo-Hauptordner):
    QT_QPA_PLATFORM=offscreen python3 qfield/test/qml_harness_punkte.py [screenshot.png]
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
TMP = Path(tempfile.mkdtemp(prefix='gokart_punkte_'))
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
            bemerkung TEXT, geaendert_am TEXT, ersetzt TEXT, punkt_id TEXT, deckung TEXT, anzahl TEXT,
            phaenologie TEXT);
        CREATE TABLE aufnahme_punkte (fid INTEGER PRIMARY KEY, geom TEXT, punkt_id TEXT, erfasst_am TEXT,
            geaendert_am TEXT, bearbeiter TEXT, gps_genauigkeit REAL, hoehe REAL, pos_quelle TEXT, biotoptyp TEXT,
            flaeche_id TEXT, bemerkung TEXT);
    ''')
    taxa = [(1, 'Quercus robur', 'Stiel-Eiche'), (2, 'Quercus petraea', 'Trauben-Eiche'),
            (3, 'Plantago lanceolata', 'Spitz-Wegerich')]
    for tid, wiss, de in taxa:
        con.execute('INSERT INTO taxon (taxon_id, wissenschaftlicher_name, deutscher_name, anzeige_name, rang) '
                    'VALUES (?,?,?,?,?)', (tid, wiss, de, de, 'SPE'))
        con.execute('INSERT INTO suchnamen (taxon_id, name, art) VALUES (?,?,?)', (tid, de, 'deutsch'))
        con.execute('INSERT INTO suchnamen (taxon_id, name, art) VALUES (?,?,?)', (tid, wiss, 'wissenschaftlich'))
    con.executemany('INSERT INTO flaechen (flaeche_id, name) VALUES (?,?)', [('F-001', 'Wiese'), ('F-002', 'Waldrand')])
    con.commit()
    con.close()


def zeilen(tabelle):
    con = sqlite3.connect(GPKG)
    con.row_factory = sqlite3.Row
    r = [dict(x) for x in con.execute(f'SELECT * FROM {tabelle} ORDER BY fid')]
    con.close()
    return r


class Geometry(QObject):
    def __init__(self, wkt):
        super().__init__()
        self.wkt = wkt

    @Slot(result=bool)
    def isNull(self):
        return not self.wkt

    @Slot(result=bool)
    def isEmpty(self):
        return not self.wkt


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

    @Slot(result=QObject)
    def geometry(self):
        g = Geometry(self._w.get('geom')); BEHALTEN.append(g); return g


class Fields(QObject):
    def __init__(self, names):
        super().__init__()
        self._n = list(names)

    @Property('QStringList', constant=True)
    def names(self):
        return self._n

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

    @Slot(QObject, 'QVariant', result=QObject)
    def createFeature(self, layer, geom):
        f = Feature(layer.fields, {n: None for n in layer.fields.names}); BEHALTEN.append(f)
        if isinstance(geom, Geometry):
            f._w['geom'] = geom.wkt
        return f

    @Slot(str, result=QObject)
    def geometrieAusWkt(self, wkt):
        g = Geometry(wkt); BEHALTEN.append(g); return g

    @Slot(QObject, result='QVariantMap')
    def mittelpunkt(self, g):
        x, y = re.findall(r'[-\d.]+', g.wkt)[:2]
        return {'x': float(x), 'y': float(y)}


class Project(QObject):
    def __init__(self):
        super().__init__()
        self.layers = {n: Layer(n) for n in ('flaechen', 'taxon', 'suchnamen', 'eigene_synonyme', 'artnachweise',
                                             'aufnahme_punkte')}

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
        return GPS

    @Slot(result=QObject)
    def mapCanvas(self):
        return KARTE

    @Slot(str, result=QObject)
    def findItemByObjectName(self, n):
        return LOCATOR if n == 'coordinateLocator' else None


class Positioning(QObject):
    def __init__(self):
        super().__init__()
        self.info = {}
        self.setzen(500000.0, 6000000.0, 25.0)

    def setzen(self, x, y, hacc):
        self.info = {'latitudeValid': True, 'longitudeValid': True, 'longitude': x, 'latitude': y,
                     'haccValid': True, 'hacc': hacc, 'elevationValid': True, 'elevation': 12.34}

    @Property('QVariantMap')
    def positionInformation(self):
        return self.info


class Karte(QObject):
    @Property('QVariantMap', constant=True)
    def mapSettings(self):
        return {'center': {'x': 500100.0, 'y': 6000100.0}, 'destinationCrs': 'EPSG:25832'}


class Locator(QObject):
    """QField-Fadenkreuz: currentCoordinate im Karten-KBS (hier = Layer-KBS)."""
    def __init__(self):
        super().__init__()
        self.c = {'x': 500200.0, 'y': 6000150.0}

    @Property('QVariantMap')
    def currentCoordinate(self):
        return self.c


GPS, KARTE, LOCATOR = Positioning(), Karte(), Locator()
from PySide6.QtQml import QQmlEngine  # noqa: E402
for _o in (GPS, KARTE, LOCATOR):       # nicht vom JS-Garbage-Collector einsammeln lassen
    QQmlEngine.setObjectOwnership(_o, QQmlEngine.CppOwnership)
projekt_anlegen()
app = QGuiApplication(sys.argv)
engine = QQmlEngine()
engine.warnings.connect(lambda ws: [FEHLER.append(w.toString()) for w in ws])
utils = Utils()
modul = TMP / 'mock_qml' / 'org' / 'qfield' / 'core'
modul.mkdir(parents=True, exist_ok=True)
(modul / 'qmldir').write_text('module org.qfield.core\nsingleton QfLayerUtils 1.0 QfLayerUtils.qml\n'
                              'singleton QfFeatureUtils 1.0 QfFeatureUtils.qml\n'
                              'singleton QfExpressionContextUtils 1.0 QfExpressionContextUtils.qml\n'
                              'singleton QfGeometryUtils 1.0 QfGeometryUtils.qml\n'
                              'singleton QfCoordinateReferenceSystemUtils 1.0 QfCoordinateReferenceSystemUtils.qml\n')
(modul / 'QfFeatureUtils.qml').write_text("""pragma Singleton
import QtQuick
QtObject { function createFeature(l, g) { return _utils.createFeature(l, g === undefined ? null : g) } }
""")
(modul / 'QfExpressionContextUtils.qml').write_text("""pragma Singleton
import QtQuick
QtObject { function projectVariables(p) { return { gokart_module: 'arten,punkte', gokart_zusatz: 'deckung,phaenologie',
                                                  gokart_punkt_genauigkeit: '10', gokart_punkt_radius: '25' } } }
""")
(modul / 'QfGeometryUtils.qml').write_text("""pragma Singleton
import QtQuick
QtObject {
  function point(x, y) { return { x: x, y: y } }
  function reprojectPoint(p, a, b) { return p }          // Test: Koordinaten sind schon im Layer-KBS
  function createGeometryFromWkt(w) { return _utils.geometrieAusWkt(w) }
  function centroid(g) { return _utils.mittelpunkt(g) }
}
""")
(modul / 'QfCoordinateReferenceSystemUtils.qml').write_text("""pragma Singleton
import QtQuick
QtObject { function fromDescription(d) { return d } }
""")
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
    # Repeater-Delegates hängen nur im Item-Baum (nicht im QObject-Baum) -> über childItems() suchen
    stapel = [win.property('contentItem')]
    try:
        stapel.append(win.contentItem().parentItem())
    except Exception:
        pass
    while stapel:
        it = stapel.pop()
        if it is None:
            continue
        if it.objectName() == objekt_name:
            return it
        stapel.extend(it.childItems())
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
        assert p.punkteVerfuegbar(), 'Punkt-Layer/Modul nicht erkannt'
        assert prop('zusatzFelder') == ['deckung', 'phaenologie'], prop('zusatzFelder')
        p.ortWechseln('punkt')
        assert prop('ortArt') == 'punkt'
        p.punktAnlegen('gps')                                   # ±25 m > 10 m -> Warnung, nichts angelegt
        assert prop('punktTrotzdem') is True, 'ungenaue Position nicht abgefangen'
        assert zeilen('aufnahme_punkte') == [], 'Punkt trotz Warnung angelegt'
        print('Meldung:', letzte_meldung())
        GPS.setzen(500000.0, 6000000.0, 4.2)
        p.setProperty('punktTrotzdem', False)
        p.punktAnlegen('gps')
    elif n == 2:
        pt = zeilen('aufnahme_punkte')
        print('Punkt:', pt)
        assert len(pt) == 1 and pt[0]['geom'] == 'POINT(500000 6000000)' and pt[0]['gps_genauigkeit'] == 4.2
        assert pt[0]['pos_quelle'] == 'gps' and pt[0]['hoehe'] == 12.3 and pt[0]['punkt_id'].startswith('P-')
        assert prop('aktiverPunkt') == pt[0]['punkt_id']
        finde('gokartSucheFeld').setProperty('text', 'Spitz Wegerich, Deckung zwei a, blühend')
    elif n == 3:
        tr = prop('treffer')
        assert tr and tr[0]['taxon']['wissenschaftlicher_name'] == 'Plantago lanceolata', tr
        p.setProperty('auswahlIndex', 0)
        p.speichern()
    elif n == 4:
        an = zeilen('artnachweise')
        print('Nachweis:', an)
        pid = zeilen('aufnahme_punkte')[0]['punkt_id']
        assert len(an) == 1 and an[0]['punkt_id'] == pid and an[0]['flaeche_id'] is None
        assert an[0]['deckung'] == '2a' and an[0]['phaenologie'] == 'blühend' and an[0]['taxon_id'] == 3
        assert an[0]['original_eingabe'] == 'Spitz Wegerich, Deckung zwei a, blühend'
        assert prop('letzterNachweis')['fid'] == an[0]['fid']
        k = finde('gokartZusatz_deckung_3')
        assert k.property('visible'), 'Schnellleiste nicht sichtbar'
        assert finde('gokartZusatz_deckung_2a').property('an'), 'aktueller Wert nicht markiert'
        if SCREENSHOT:
            QTimer.singleShot(300, lambda: (win.grabWindow().save(SCREENSHOT), p.zusatzSetzen('deckung', '3')))
            return 'warten'
        p.zusatzSetzen('deckung', '3')
    elif n == 5:
        r = zeilen('artnachweise')[0]
        assert r['deckung'] == '3' and r['geaendert_am'], r
        p.zusatzSetzen('phaenologie', 'blühend')                # gleicher Wert -> leeren
        r = zeilen('artnachweise')[0]
        assert r['phaenologie'] is None, r
        finde('gokartSucheFeld').setProperty('text', 'Spitz-Wegerich')
    elif n == 6:
        p.setProperty('auswahlIndex', 0)
        p.speichern()
        assert 'bereits erfasst' in letzte_meldung(), letzte_meldung()
        assert len(zeilen('artnachweise')) == 1
        GPS.setzen(500030.0, 6000030.0, 3.0)                    # ~42 m entfernt
        p.gpsAktualisieren()
        st = prop('gpsStand')
        print('GPS-Stand:', st)
        assert 41 < st['abstand'] < 43 and st['hacc'] == 3.0
        # Flächen-Modus: Art auf F-001
        p.ortWechseln('flaeche')
        p.flaecheWaehlen('F-001', 'Test')
        assert prop('artenDerFlaeche') == []
        finde('gokartSucheFeld').setProperty('text', 'Stiel-Eiche')
    elif n == 7:
        p.setProperty('auswahlIndex', 0)
        p.speichern()
        an = zeilen('artnachweise')
        assert len(an) == 2 and an[1]['flaeche_id'] == 'F-001' and an[1]['punkt_id'] is None, an
        assert prop('letzterNachweis')['flaeche'] == 'F-001'
        # Bearbeiten am Punkt: nur Zusatzangabe sprechen
        p.ortWechseln('punkt')
        eintraege = prop('artenDerFlaeche')
        assert len(eintraege) == 1 and eintraege[0]['flaeche'].startswith('@P-'), eintraege
        p.bearbeitenStarten(eintraege[0])
        finde('gokartSucheFeld').setProperty('text', 'Deckung vier')
    elif n == 8:
        text = p.aenderungText()
        print('Knopf:', text)
        assert 'D 4' in text, text
        p.aenderungSpeichern()
        r = zeilen('artnachweise')[0]
        assert r['deckung'] == '4' and r['taxon_id'] == 3 and r['punkt_id'], r
        # Verschieben per Fadenkreuz: Punkt bekommt neue Lage, punkt_id und Artnachweise bleiben
        alt = zeilen('aufnahme_punkte')[0]
        p.fadenkreuzStarten('verschieben')
        assert prop('fadenkreuz') == 'verschieben' and finde('gokartFadenkreuzLeiste').property('visible')
        assert finde('gokartFadenkreuzMarke').property('visible'), 'Fadenkreuz-Marke fehlt'

        info = prop('fadenkreuzInfo')
        print('Fadenkreuz:', info)
        if SCREENSHOT:
            win.grabWindow().save(SCREENSHOT.replace('.png', '_fadenkreuz.png'))
        assert 'R 500200' in info and 'H 6000150' in info and 'vom bisherigen Punkt' in info, info
        p.fadenkreuzUebernehmen()
        pt = zeilen('aufnahme_punkte')
        print('Verschoben:', pt)
        assert len(pt) == 1 and pt[0]['punkt_id'] == alt['punkt_id'] and pt[0]['geom'] == 'POINT(500200 6000150)'
        assert pt[0]['pos_quelle'] == 'korrigiert' and pt[0]['gps_genauigkeit'] is None and pt[0]['geaendert_am']
        assert pt[0]['erfasst_am'] == alt['erfasst_am'] and pt[0]['hoehe'] == alt['hoehe']
        assert len(prop('artenDerFlaeche')) == 1, 'Artnachweis hängt nicht mehr am Punkt'
        assert prop('fadenkreuz') == ''
        # Neuer Punkt per Fadenkreuz
        LOCATOR.c = {'x': 500300.0, 'y': 6000400.0}
        p.fadenkreuzStarten('neu')
        p.fadenkreuzUebernehmen()
    elif n == 9:
        pt = zeilen('aufnahme_punkte')
        print('Punkte:', [(x['punkt_id'], x['geom'], x['pos_quelle']) for x in pt])
        assert len(pt) == 2 and pt[1]['pos_quelle'] == 'manuell' and pt[1]['geom'] == 'POINT(500300 6000400)'
        assert prop('aktiverPunkt') == pt[1]['punkt_id'] and prop('artenDerFlaeche') == []
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
