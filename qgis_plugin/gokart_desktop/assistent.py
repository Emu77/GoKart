"""GoKart Desktop – Assistent „Neues GoKart-Projekt“.

Legt einen Projektordner an, der so wie er ist aufs Tablet kann:
    <Ordner>/gokart.gpkg   Kopie der Vorlage (Artenliste) + eigene Flächen + Erfassungstabellen
    <Ordner>/gokart.qgs    QGIS-/QField-Projekt (Formulare, Beziehungen, relative Pfade)
Die Logik ist dieselbe wie in werkzeuge/build_gokart_projekt.py (wird von dort geladen).
"""
import shutil
import sqlite3
from pathlib import Path

from qgis.PyQt.QtCore import QSettings, Qt
from qgis.PyQt.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
                                 QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPlainTextEdit,
                                 QPushButton, QSpinBox, QVBoxLayout, QWidget)
from qgis.core import QgsCoordinateReferenceSystem, QgsProject, QgsVectorLayer, QgsWkbTypes
from qgis.PyQt.QtCore import QVariant
from qgis.gui import QgsProjectionSelectionWidget

from . import biotope as B
from . import helfer as H
from . import module as M
from . import punkte as P
from . import vorlage as V

STANDARD_CRS = 'EPSG:25832'          # ETRS89 / UTM 32N – Norddeutschland
AUTO = '__auto__'
KEINS = ''


def sublayer_namen(pfad):
    """Layernamen in einer Datei (GeoPackage kann mehrere enthalten)."""
    lyr = QgsVectorLayer(str(pfad), 'probe', 'ogr')
    if not lyr.isValid():
        return []
    namen = []
    for s in lyr.dataProvider().subLayers():
        teile = s.split('!!::!!')
        if len(teile) > 1 and teile[1]:
            namen.append(teile[1])
    return namen


def flaechen_layer(pfad, layername=None):
    uri = str(pfad) + (f'|layername={layername}' if layername else '')
    lyr = QgsVectorLayer(uri, Path(pfad).stem, 'ogr')
    if not lyr.isValid():
        return None
    if QgsWkbTypes.geometryType(lyr.wkbType()) != QgsWkbTypes.PolygonGeometry:
        return None
    return lyr


def katalog_auswahl():
    """[(schluessel, anzeigename)] der im Plugin mitgelieferten Biotop-Kataloge (aktuelle zuerst)."""
    liste = []
    for pfad in B.kataloge_finden():
        try:
            meta, _ = B.katalog_lesen(pfad)
        except Exception:
            continue
        s = meta['schluessel'].upper()
        liste.append((s, f'{s} – {meta.get("name") or s}'))
    return sorted(liste, key=lambda x: ('_' in x[0], x[0]))


def ogr_layer_loeschen(gpkg, name):
    """Layer per GDAL entfernen (inkl. Registrierung in gpkg_contents usw.)."""
    import warnings
    try:
        from osgeo import ogr
    except ImportError:
        return False
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', FutureWarning)
        ds = ogr.Open(str(gpkg), 1)
    if ds is None:
        return False
    try:
        for i in range(ds.GetLayerCount()):
            if ds.GetLayerByIndex(i).GetName() == name:
                return ds.DeleteLayer(i) == 0
        return False
    finally:
        ds = None


def projekt_anlegen(e, vorlage):
    """e: dict mit ordner, titel, quelle (Polygon-Layer oder None), id_feld, id_auto, name_feld, crs,
    module, zusatz, biotop_schluessel, punkt_genau, punkt_radius. Gibt den Pfad der .qgs zurück."""
    build = H.werkzeug('build_gokart_projekt')
    ordner = Path(e['ordner'])
    ordner.mkdir(parents=True, exist_ok=True)
    gpkg = ordner / 'gokart.gpkg'
    qgs = ordner / 'gokart.qgs'
    module = set(e['module'])

    print(f'Vorlage: {vorlage}')
    V.kopie_sichern(vorlage, gpkg)
    for t, n in V.erfassungen_leeren(gpkg).items():
        if n:
            print(f'  Vorlage geleert: {t} ({n})')
    ogr_layer_loeschen(gpkg, P.T_PUNKTE)       # wird unten im Koordinatensystem der Flächen neu angelegt

    # Flächen (eigene Datei oder leer) – ersetzt den Layer "flaechen" der Vorlage
    quelle = e.get('quelle')
    crs = (quelle.crs() if quelle is not None and quelle.crs().isValid()
           else QgsCoordinateReferenceSystem(e.get('crs') or STANDARD_CRS))
    build.CRS = crs.authid() or ('wkt:' + crs.toWkt())     # Flächen bestimmen das Koordinatensystem
    fl = build.speicher_layer('flaechen', [build.feld('flaeche_id', QVariant.String, 40),
                                           build.feld('name', QVariant.String, 200),
                                           build.feld('bemerkung', QVariant.String, 500)], 'MultiPolygon')
    fl.setCrs(crs)
    if quelle is not None:
        build.flaechen_importieren(fl, quelle, e.get('id_feld') or None, e.get('name_feld') or None,
                                   e.get('id_auto'))
    else:
        print('Flächen: leer (in QGIS zeichnen/einfügen oder nur Punktaufnahmen)')
    build.schreiben(fl, gpkg, False)
    con = sqlite3.connect(str(gpkg))
    con.execute('CREATE INDEX IF NOT EXISTS idx_flaechen_id ON flaechen(flaeche_id)')
    con.commit()
    con.close()
    print(f'Koordinatensystem: {crs.authid() or crs.description()}')

    # Projekt (Formulare, Beziehung, relative Pfade) – lädt es in QgsProject, danach wieder freigeben
    build.projekt_erzeugen(ordner, gpkg)
    p = QgsProject.instance()
    p.setTitle(e.get('titel') or ordner.name)
    p.write(str(qgs))
    p.clear()
    QApplication.processEvents()

    # Ergänzungen direkt in Datei/Projekt (wie build_gokart_projekt.py)
    if M.BIOTOPE in module:
        erg = B.kataloge_einspielen(gpkg)
        print('Biotoptypen-Kataloge: ' + ', '.join(sorted(erg)))
        B.qgs_layer_eintragen(qgs, gpkg)
        if e.get('biotop_schluessel'):
            B.qgs_variable_setzen(qgs, B.VAR_SCHLUESSEL, e['biotop_schluessel'])
    if M.FOTOS in module:
        A = H.werkzeug('abgleich')
        seite = A.Seite('Projekt', qgs)
        if not seite.hat_fototabelle():
            seite.fototabelle_anlegen()
        if not seite.fotolayer_im_projekt():
            seite.fotolayer_eintragen()
        (ordner / 'fotos').mkdir(exist_ok=True)
    P.nachweisspalten_ergaenzen(str(gpkg))
    if M.PUNKTE in module:
        for t in P.einrichten(str(gpkg), qgs, build.CRS):
            print(f'Punktaufnahmen: {t}')
        B.qgs_variable_setzen(qgs, P.VAR_GENAUIGKEIT, str(e.get('punkt_genau', P.STANDARD_GENAUIGKEIT)))
        B.qgs_variable_setzen(qgs, P.VAR_RADIUS, str(e.get('punkt_radius', P.STANDARD_RADIUS)))
    B.qgs_variable_setzen(qgs, P.VAR_ZUSATZ, ','.join(e.get('zusatz') or []))
    B.qgs_variable_setzen(qgs, M.VAR_MODULE, M.als_text(module))

    # QField-Plugin gleich mit in den Ordner (QField lädt es nur, wenn es wie die .qgs heißt)
    for q, name in H.qfield_plugin_dateien(qgs):
        shutil.copy2(q, ordner / name)
    print('Erfassung in QField: ' + ', '.join(M.NAMEN[m] for m in M.ALLE if m in module))
    return qgs


class NeuesProjektDialog(QDialog):
    """Fragt alles ab, was build_gokart_projekt.py sonst als Parameter bekommt."""

    def __init__(self, parent=None, start_layer=None):
        super().__init__(parent)
        self.setWindowTitle('GoKart – Neues Projekt')
        self.setMinimumWidth(520)
        self.settings = QSettings()
        self.quelle = None
        self.ergebnis = None
        form = QFormLayout(self)

        self.titel = QLineEdit()
        self.titel.setPlaceholderText('z. B. Moor Nord 2027')
        self.titel.textChanged.connect(self.ordner_vorschlagen)
        self.basis = QLineEdit(self.settings.value('GoKart/projekt_basis', str(Path.home()), type=str))
        basis_btn = QPushButton('…')
        basis_btn.setFixedWidth(32)
        basis_btn.clicked.connect(self.basis_waehlen)
        zeile = QHBoxLayout()
        zeile.addWidget(self.basis)
        zeile.addWidget(basis_btn)
        self.ordner_info = QLabel()
        self.ordner_info.setWordWrap(True)

        self.datei = QLineEdit()
        self.datei.setPlaceholderText('leer lassen = ohne Flächen (zeichnen oder nur Punktaufnahmen)')
        self.datei.editingFinished.connect(self.datei_geaendert)
        datei_btn = QPushButton('…')
        datei_btn.setFixedWidth(32)
        datei_btn.clicked.connect(self.datei_waehlen)
        dzeile = QHBoxLayout()
        dzeile.addWidget(self.datei)
        dzeile.addWidget(datei_btn)
        self.layername = QComboBox()
        self.layername.currentIndexChanged.connect(self.layer_geaendert)
        self.id_feld = QComboBox()
        self.id_feld.currentIndexChanged.connect(self.pruefen)
        self.praefix = QLineEdit('F-')
        self.praefix.setMaximumWidth(80)
        izeile = QHBoxLayout()
        izeile.addWidget(self.id_feld, 1)
        self.praefix_label = QLabel('Präfix')
        izeile.addWidget(self.praefix_label)
        izeile.addWidget(self.praefix)
        self.name_feld = QComboBox()
        self.crs = QgsProjectionSelectionWidget()
        self.crs.setCrs(QgsCoordinateReferenceSystem(STANDARD_CRS))
        self.flaechen_info = QLabel()
        self.flaechen_info.setWordWrap(True)

        self.mod = {m: QCheckBox(M.NAMEN[m]) for m in M.ALLE}
        for m, cb in self.mod.items():
            cb.setChecked(m != M.PUNKTE)
            cb.toggled.connect(self.module_umschalten)
        mzeile = QHBoxLayout()
        for cb in self.mod.values():
            mzeile.addWidget(cb)
        mzeile.addStretch(1)
        self.zusatz = {z: QCheckBox(name) for z, (name, _w) in P.ZUSATZ.items()}
        zzeile = QHBoxLayout()
        for cb in self.zusatz.values():
            zzeile.addWidget(cb)
        zzeile.addStretch(1)
        self.schluessel = QComboBox()
        self.schluessel.addItem('– später wählen –', '')
        for s, name in katalog_auswahl():
            self.schluessel.addItem(name, s)
        i = self.schluessel.findData(self.settings.value('GoKart/biotop_schluessel', 'SH', type=str))
        self.schluessel.setCurrentIndex(max(i, 0))
        self.punkt_genau = QSpinBox()
        self.punkt_genau.setRange(1, 100)
        self.punkt_genau.setSuffix(' m')
        self.punkt_genau.setValue(int(P.STANDARD_GENAUIGKEIT))
        self.punkt_radius = QSpinBox()
        self.punkt_radius.setRange(5, 1000)
        self.punkt_radius.setSuffix(' m')
        self.punkt_radius.setValue(int(P.STANDARD_RADIUS))
        pzeile = QHBoxLayout()
        pzeile.addWidget(QLabel('GPS-Warnung ab'))
        pzeile.addWidget(self.punkt_genau)
        pzeile.addWidget(QLabel('„Neue Aufnahme?“ ab'))
        pzeile.addWidget(self.punkt_radius)
        pzeile.addStretch(1)
        self.punkt_zeile = QWidget()
        self.punkt_zeile.setLayout(pzeile)

        self.vorlage = H.vorlage_im_plugin()
        self.vorlage_zeile = QWidget()
        vz = QHBoxLayout(self.vorlage_zeile)
        vz.setContentsMargins(0, 0, 0, 0)
        self.vorlage_edit = QLineEdit(self.settings.value('GoKart/vorlage', '', type=str))
        self.vorlage_edit.setPlaceholderText('gokart.gpkg (Vorlage mit Artenliste)')
        vbtn = QPushButton('…')
        vbtn.setFixedWidth(32)
        vbtn.clicked.connect(self.vorlage_waehlen)
        vz.addWidget(self.vorlage_edit)
        vz.addWidget(vbtn)

        form.addRow(QLabel('<b>Projekt</b>'))
        form.addRow('Name', self.titel)
        form.addRow('Speichern unter', zeile)
        form.addRow(self.ordner_info)
        form.addRow(QLabel('<b>Kartierflächen</b> (Shape, GeoPackage …, Polygone)'))
        form.addRow('Datei', dzeile)
        self.layer_label = QLabel('Layer')
        form.addRow(self.layer_label, self.layername)
        form.addRow('Flächen-ID', izeile)
        form.addRow('Bezeichnung', self.name_feld)
        self.crs_label = QLabel('Koordinatensystem')
        form.addRow(self.crs_label, self.crs)
        form.addRow(self.flaechen_info)
        form.addRow(QLabel('<b>Im Gelände erfassen</b>'))
        form.addRow(mzeile)
        self.zusatz_label = QLabel('Zusatzangaben je Art')
        form.addRow(self.zusatz_label, zzeile)
        self.schluessel_label = QLabel('Biotop-Schlüssel')
        form.addRow(self.schluessel_label, self.schluessel)
        form.addRow(self.punkt_zeile)
        if self.vorlage is None:
            form.addRow(QLabel('<b>Vorlage</b> – im Plugin nicht enthalten, bitte Datei wählen'))
            form.addRow('GeoPackage', self.vorlage_zeile)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText('Projekt anlegen')
        buttons.accepted.connect(self.anlegen)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

        if start_layer is not None:
            pfad = start_layer.source().split('|', 1)[0]
            if Path(pfad).is_file():
                self.datei.setText(pfad)
        self.datei_geaendert()
        self.module_umschalten()
        self.ordner_vorschlagen()

    # ------------------------------------------------------------------ Eingaben
    def ordner(self):
        roh = self.titel.text().strip().translate(str.maketrans({'ä': 'ae', 'ö': 'oe', 'ü': 'ue', 'Ä': 'Ae', 'Ö': 'Oe',
                                                                'Ü': 'Ue', 'ß': 'ss', ' ': '_'}))
        name = ''.join(c if (c.isascii() and c.isalnum()) or c in '-_' else '_' for c in roh).strip('_')
        return Path(self.basis.text().strip() or Path.home()) / (name or 'GoKart_Projekt')

    def ordner_vorschlagen(self, *args):
        o = self.ordner()
        frei = not o.exists() or (o.is_dir() and not any(o.iterdir()))
        self.ordner_info.setText(f'Projektordner: {o}' + ('' if frei else '  ⚠ existiert schon und ist nicht leer'))

    def basis_waehlen(self):
        p = QFileDialog.getExistingDirectory(self, 'Wo soll der Projektordner angelegt werden?', self.basis.text())
        if p:
            self.basis.setText(p)
            self.ordner_vorschlagen()

    def datei_waehlen(self):
        p, _ = QFileDialog.getOpenFileName(self, 'Kartierflächen wählen', self.datei.text() or str(Path.home()),
                                           'Vektordaten (*.shp *.gpkg *.geojson *.json *.kml *.sqlite *.gml);;'
                                           'Alle Dateien (*)')
        if p:
            self.datei.setText(p)
            self.datei_geaendert()

    def vorlage_waehlen(self):
        p, _ = QFileDialog.getOpenFileName(self, 'Vorlage gokart.gpkg wählen', self.vorlage_edit.text(),
                                           'GeoPackage (*.gpkg)')
        if p:
            self.vorlage_edit.setText(p)

    def datei_geaendert(self):
        self.layername.blockSignals(True)
        self.layername.clear()
        pfad = self.datei.text().strip()
        if pfad and Path(pfad).is_file():
            namen = sublayer_namen(pfad)
            for n in namen:
                self.layername.addItem(n, n)
        self.layername.blockSignals(False)
        mehrere = self.layername.count() > 1
        self.layername.setVisible(mehrere)
        self.layer_label.setVisible(mehrere)
        self.layer_geaendert()

    def layer_geaendert(self, *args):
        pfad = self.datei.text().strip()
        self.quelle = None
        self.id_feld.blockSignals(True)
        self.id_feld.clear()
        self.name_feld.clear()
        if pfad:
            name = self.layername.currentData() if self.layername.count() > 1 else None
            self.quelle = flaechen_layer(pfad, name) if Path(pfad).is_file() else None
        ohne = self.quelle is None
        if not ohne:
            felder = self.quelle.fields().names()
            for f in felder:
                self.id_feld.addItem(f, f)
            self.id_feld.addItem('(fortlaufend nummerieren)', AUTO)
            self.name_feld.addItem('(keine)', KEINS)
            for f in felder:
                self.name_feld.addItem(f, f)
            tipp = next((f for f in felder if f.lower() in ('flaeche_id', 'id', 'nr', 'biotop_nr', 'flaechen_nr')), None)
            if tipp:
                self.id_feld.setCurrentIndex(self.id_feld.findData(tipp))
            name_tipp = next((f for f in felder if f.lower() in ('name', 'bezeichnung', 'bt_text', 'raum')), None)
            if name_tipp:
                self.name_feld.setCurrentIndex(self.name_feld.findData(name_tipp))
        self.id_feld.blockSignals(False)
        for w in (self.id_feld, self.name_feld):
            w.setEnabled(not ohne)
        crs_fehlt = ohne or not self.quelle.crs().isValid()
        self.crs.setVisible(crs_fehlt)
        self.crs_label.setVisible(crs_fehlt)
        self.pruefen()

    def pruefen(self, *args):
        auto = self.id_feld.currentData() == AUTO
        self.praefix.setVisible(auto)
        self.praefix_label.setVisible(auto)
        pfad = self.datei.text().strip()
        if not pfad:
            self.flaechen_info.setText('Ohne Flächen: Projekt bekommt einen leeren Flächen-Layer.')
            return
        if self.quelle is None:
            self.flaechen_info.setText('⚠ Datei nicht lesbar oder enthält keine Polygone.')
            return
        c = self.quelle.crs()
        text = f'{self.quelle.featureCount()} Flächen, ' + (
            f'{c.authid() or c.description()}.' if c.isValid() else '⚠ ohne Koordinatensystem – oben wählen.')
        feld = self.id_feld.currentData()
        if feld and feld != AUTO:
            werte = [f[feld] for f in self.quelle.getFeatures()]
            leer = sum(1 for v in werte if v is None or str(v).strip() in ('', 'NULL'))
            gefuellt = [str(v) for v in werte if not (v is None or str(v).strip() in ('', 'NULL'))]
            doppelt = len(gefuellt) - len(set(gefuellt))
            if leer or doppelt:
                text += f' ⚠ {leer} ohne ID, {doppelt} doppelt – werden ergänzt (OHNE-ID-…, Suffix -2).'
            else:
                text += ' IDs eindeutig ✓'
        self.flaechen_info.setText(text)

    def module_umschalten(self, *args):
        arten = self.mod[M.ARTEN].isChecked()
        for cb in self.zusatz.values():
            cb.setEnabled(arten)
        self.zusatz_label.setEnabled(arten)
        self.schluessel.setEnabled(self.mod[M.BIOTOPE].isChecked())
        self.schluessel_label.setEnabled(self.mod[M.BIOTOPE].isChecked())
        self.punkt_zeile.setEnabled(self.mod[M.PUNKTE].isChecked())

    # ------------------------------------------------------------------ Anlegen
    def anlegen(self):
        ordner = self.ordner()
        module = {m for m, cb in self.mod.items() if cb.isChecked()}
        vorlage = self.vorlage or (Path(self.vorlage_edit.text().strip()) if self.vorlage_edit.text().strip() else None)
        fehler = []
        if not self.titel.text().strip():
            fehler.append('Projektnamen eingeben.')
        if ordner.exists() and (not ordner.is_dir() or any(ordner.iterdir())):
            fehler.append(f'{ordner} existiert schon und ist nicht leer.')
        if self.datei.text().strip() and self.quelle is None:
            fehler.append('Flächen-Datei ist nicht lesbar oder hat keine Polygone.')
        if not module:
            fehler.append('Mindestens eine Erfassung wählen.')
        if M.PUNKTE in module and M.ARTEN not in module:
            fehler.append('Punktaufnahmen brauchen „Pflanzenarten“.')
        if vorlage is None or not vorlage.is_file():
            fehler.append('Vorlage gokart.gpkg fehlt.')
        elif V.pruefen(vorlage):
            fehler.append(f'{vorlage.name} ist keine GoKart-Vorlage (fehlt: {", ".join(V.pruefen(vorlage))}).')
        if fehler:
            QMessageBox.warning(self, 'GoKart', '\n'.join(fehler))
            return
        p = QgsProject.instance()
        if p.isDirty() and QMessageBox.question(
                self, 'GoKart', 'Das aktuelle QGIS-Projekt hat ungespeicherte Änderungen. Trotzdem schließen?',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        e = {'ordner': ordner, 'titel': self.titel.text().strip(), 'quelle': self.quelle,
             'id_feld': None if self.id_feld.currentData() == AUTO else self.id_feld.currentData(),
             'id_auto': self.praefix.text() if self.id_feld.currentData() == AUTO else None,
             'name_feld': self.name_feld.currentData() or None,
             'crs': self.crs.crs().authid() or STANDARD_CRS, 'module': module,
             'zusatz': [z for z, cb in self.zusatz.items() if cb.isChecked() and cb.isEnabled()],
             'biotop_schluessel': self.schluessel.currentData() if M.BIOTOPE in module else '',
             'punkt_genau': self.punkt_genau.value(), 'punkt_radius': self.punkt_radius.value()}
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            ok, qgs, text = H.ausfuehren(projekt_anlegen, e, vorlage)
        finally:
            QApplication.restoreOverrideCursor()
        if not ok:
            ausgabe_zeigen(self, 'GoKart – Projekt konnte nicht angelegt werden', text)
            QgsProject.instance().clear()
            shutil.rmtree(ordner, ignore_errors=True)      # war vorher leer bzw. nicht vorhanden
            return
        self.settings.setValue('GoKart/projekt_basis', self.basis.text().strip())
        self.settings.setValue('GoKart/biotop_schluessel', self.schluessel.currentData() or '')
        if self.vorlage is None:
            self.settings.setValue('GoKart/vorlage', str(vorlage))
        self.ergebnis = (qgs, text)
        self.accept()


def ausgabe_zeigen(parent, titel, text, knoepfe=QDialogButtonBox.Close):
    """Längere Ausgabe (Protokoll) in einem Fenster; gibt True zurück, wenn mit OK/Ja bestätigt."""
    dlg = QDialog(parent)
    dlg.setWindowTitle(titel)
    dlg.resize(680, 440)
    lay = QVBoxLayout(dlg)
    feld = QPlainTextEdit(text or '(keine Ausgabe)')
    feld.setReadOnly(True)
    lay.addWidget(feld)
    bb = QDialogButtonBox(knoepfe)
    bb.accepted.connect(dlg.accept)
    bb.rejected.connect(dlg.reject)
    bb.clicked.connect(lambda b: dlg.done(1 if bb.buttonRole(b) in (QDialogButtonBox.AcceptRole,
                                                                    QDialogButtonBox.YesRole) else 0))
    lay.addWidget(bb)
    return dlg.exec_() == 1
