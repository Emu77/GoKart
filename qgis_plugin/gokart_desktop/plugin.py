"""GoKart Desktop: QGIS 3.x, Linux/Windows, optional Vosk.

Alle Schreiboperationen gehen an den geladenen artnachweise-Layer.
Keine Änderung am Quellprojekt oder den Layerdefinitionen.
"""

# GoKart: optionale Python-Umgebung (Linux: ~/gokart-venv) für vosk/sounddevice einbinden.
# Unter Windows stattdessen in der OSGeo4W-Shell: python -m pip install vosk sounddevice
import site
import sys as _sys
from pathlib import Path as _Path
for _sp in (_Path.home() / 'gokart-venv' / 'lib').glob('python3*/site-packages'):
    if _sp.is_dir() and _sys.platform != 'win32':
        site.addsitedir(str(_sp))

import csv
import hashlib
import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path

from qgis.PyQt.QtCore import Qt, QThread, pyqtSignal, QSettings, QTimer, QSize, QUrl, QBuffer, QIODevice
from qgis.PyQt.QtGui import QDesktopServices, QIcon, QImage, QPixmap
from qgis.PyQt.QtWidgets import (QAction, QComboBox, QDockWidget, QFileDialog, QScrollArea, QFrame,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QCheckBox,
    QVBoxLayout, QWidget, QDialog, QDialogButtonBox, QFormLayout)
from qgis.core import (QgsCoordinateTransform, QgsFeature, QgsGeometry,
    QgsPointXY, QgsProject, QgsMapLayerType, QgsExpression, QgsFeatureRequest,
    QgsRelation, QgsVectorLayer, QgsExpressionContextUtils as ECU)
from qgis.gui import QgsMapLayerComboBox, QgsFieldComboBox

from . import biotope as B

try:  # QGIS >= 3.34
    from qgis.core import Qgis
    F_POLY, F_VECTOR = Qgis.LayerFilter.PolygonLayer, Qgis.LayerFilter.VectorLayer
except AttributeError:  # ältere QGIS-Versionen
    from qgis.core import QgsMapLayerProxyModel
    F_POLY, F_VECTOR = QgsMapLayerProxyModel.PolygonLayer, QgsMapLayerProxyModel.VectorLayer

# GoKart: Projektvariablen für die Verknüpfung Fläche ↔ Artnachweis
VAR_AREA_LAYER = 'gokart_flaechen_layer'    # Layer-ID der Flächen
VAR_AREA_KEY = 'gokart_flaechen_key'        # Schlüsselfeld der Flächen
VAR_AREA_LABEL = 'gokart_flaechen_label'    # Anzeigefeld (optional)
VAR_OBS_LAYER = 'gokart_nachweis_layer'     # Layer-ID der Artnachweise
VAR_OBS_FK = 'gokart_nachweis_fk'           # Fremdschlüssel in den Artnachweisen
VAR_RELATION = 'gokart_relation'
RELATION_ID = 'gokart_flaeche_nachweise'
BIOTOP_RELATION_ID = 'gokart_flaeche_biotope'
LABEL_FIELDS = ('Raum', 'raum', 'name', 'Name', 'bezeichnung', 'Bezeichnung')


def norm(s):
    s = unicodedata.normalize('NFKD', str(s or '').casefold())
    return ''.join(c for c in s if not unicodedata.combining(c)).strip()


def val(f, field):
    try:
        x = f[field]
        return '' if x is None or str(x) == 'NULL' else str(x)
    except (KeyError, IndexError):
        return ''


def project_var(name):
    """Projektvariable immer frisch lesen (projectScope ist eine Momentaufnahme)."""
    scope = ECU.projectScope(QgsProject.instance())
    if not scope.hasVariable(name):
        return ''
    v = scope.variable(name)
    return '' if v is None else str(v)


def find_layer(ref):
    """Layer über ID, ersatzweise über Namen finden."""
    if not ref:
        return None
    p = QgsProject.instance()
    layer = p.mapLayer(ref)
    if layer is None:
        found = p.mapLayersByName(ref)
        layer = found[0] if found else None
    return layer if layer is not None and layer.isValid() else None


def is_polygon_layer(layer):
    return (layer is not None and layer.isValid()
            and layer.type() == QgsMapLayerType.VectorLayer
            and layer.geometryType() == 2)


def is_empty(v):
    return v is None or str(v) in ('', 'NULL')


def biotop_layer_laden(gpkg):
    """Biotop-Tabellen als Layer ins Projekt holen (falls noch nicht da), Katalog schreibgeschützt."""
    p = QgsProject.instance()
    for t in (B.T_ZUORDNUNG, B.T_TYPEN, B.T_SCHLUESSEL):
        if p.mapLayersByName(t):
            continue
        lyr = QgsVectorLayer(f'{gpkg}|layername={t}', t, 'ogr')
        if lyr.isValid():
            lyr.setReadOnly(t != B.T_ZUORDNUNG)
            p.addMapLayer(lyr)


class GoKartSetupDialog(QDialog):
    """Legt fest, über welche Felder Fläche und Artnachweis verknüpft sind."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('GoKart – Projekt einrichten')
        self.setMinimumWidth(460)
        form = QFormLayout(self)

        self.area_layer = QgsMapLayerComboBox()
        self.area_layer.setFilters(F_POLY)
        self.area_key = QgsFieldComboBox()
        self.area_label = QgsFieldComboBox()
        self.area_label.setAllowEmptyFieldName(True)
        self.obs_layer = QgsMapLayerComboBox()
        self.obs_layer.setFilters(F_VECTOR)
        self.obs_fk = QgsFieldComboBox()
        self.make_relation = QCheckBox('QGIS-Beziehung anlegen/aktualisieren (für QField-Formulare)')
        self.make_relation.setChecked(True)
        self.info = QLabel()
        self.info.setWordWrap(True)
        self.biotop_key = QComboBox()
        self.biotop_import = QPushButton('Kataloge einspielen / aktualisieren')
        self.biotop_import.setToolTip('Biotoptypen-Kataloge (Bund/Länder) aus dem Plugin-Ordner biotope_kataloge '
                                      'in die GeoPackage der Artnachweise übernehmen und als Layer laden')
        self.biotop_info = QLabel()
        self.biotop_info.setWordWrap(True)

        form.addRow(QLabel('<b>Flächen</b>'))
        form.addRow('Layer', self.area_layer)
        form.addRow('Schlüsselfeld', self.area_key)
        form.addRow('Anzeigefeld', self.area_label)
        form.addRow(QLabel('<b>Artnachweise</b>'))
        form.addRow('Layer', self.obs_layer)
        form.addRow('Verweis auf Fläche', self.obs_fk)
        form.addRow(self.make_relation)
        form.addRow(self.info)
        form.addRow(QLabel('<b>Biotoptypen</b>'))
        form.addRow('Schlüssel', self.biotop_key)
        form.addRow(self.biotop_import)
        form.addRow(self.biotop_info)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.apply)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

        self.area_layer.layerChanged.connect(self.on_area_layer)
        self.obs_layer.layerChanged.connect(lambda l: self.obs_fk.setLayer(l))
        self.area_key.fieldChanged.connect(self.check)
        self.obs_fk.fieldChanged.connect(self.check)
        self.obs_layer.layerChanged.connect(lambda _l: self.fill_biotop_keys())
        self.biotop_import.clicked.connect(self.import_catalogs)
        self.prefill()
        self.fill_biotop_keys()

    def prefill(self):
        fl = find_layer(project_var(VAR_AREA_LAYER))
        nl = find_layer(project_var(VAR_OBS_LAYER)) or find_layer('artnachweise')
        if fl is not None:
            self.area_layer.setLayer(fl)
        self.on_area_layer(self.area_layer.currentLayer())
        if project_var(VAR_AREA_KEY):
            self.area_key.setField(project_var(VAR_AREA_KEY))
        label = project_var(VAR_AREA_LABEL)
        if not label and self.area_layer.currentLayer() is not None:
            names = self.area_layer.currentLayer().fields().names()
            label = next((n for n in LABEL_FIELDS if n in names), '')
        self.area_label.setField(label)
        if nl is not None:
            self.obs_layer.setLayer(nl)
        self.obs_fk.setLayer(self.obs_layer.currentLayer())
        self.obs_fk.setField(project_var(VAR_OBS_FK) or 'flaeche_id')
        self.check()

    def obs_gpkg(self):
        nl = self.obs_layer.currentLayer()
        if nl is None:
            return None
        datei = nl.source().split('|', 1)[0]
        return datei if datei.lower().endswith('.gpkg') else None

    def fill_biotop_keys(self):
        """Schlüssel aus der GeoPackage der Artnachweise anbieten (biotop_schluessel)."""
        aktuell = self.biotop_key.currentData() or project_var(B.VAR_SCHLUESSEL)
        self.biotop_key.clear()
        self.biotop_key.addItem('– keiner –', '')
        gpkg = self.obs_gpkg()
        liste = B.schluessel_liste(gpkg) if gpkg else []
        for s, name, n, voll in liste:
            self.biotop_key.addItem(f'{s} – {name} ({n} Typen{"" if voll else ", unvollständig"})', s)
        i = self.biotop_key.findData(aktuell)
        self.biotop_key.setCurrentIndex(i if i >= 0 else (1 if len(liste) == 1 else 0))
        if not gpkg:
            self.biotop_info.setText('Artnachweise liegen nicht in einer GeoPackage – Biotoptypen nicht möglich.')
        elif not liste:
            self.biotop_info.setText('Noch keine Kataloge in der GeoPackage – „Kataloge einspielen“.')
        else:
            self.biotop_info.setText(f'{len(liste)} Schlüssel in {Path(gpkg).name}. '
                                     f'Weitere Länder: biotope_katalog_import.py, dann erneut einspielen.')
        self.biotop_import.setEnabled(bool(gpkg))

    def import_catalogs(self):
        gpkg = self.obs_gpkg()
        if not gpkg:
            return
        try:
            erg = B.kataloge_einspielen(gpkg)
        except Exception as e:
            QMessageBox.warning(self, 'GoKart', f'Einspielen fehlgeschlagen: {e}')
            return
        biotop_layer_laden(gpkg)
        self.fill_biotop_keys()
        self.biotop_info.setText('Eingespielt: ' + ', '.join(
            f'{s} ({n}{"" if v else ", unvollständig"})' for s, (n, v, _) in sorted(erg.items())))

    def on_area_layer(self, layer):
        self.area_key.setLayer(layer)
        self.area_label.setLayer(layer)
        self.check()

    def check(self, *args):
        """Schlüssel prüfen: vorhanden, eindeutig, Typ passend zum Fremdschlüssel."""
        fl, key = self.area_layer.currentLayer(), self.area_key.currentField()
        nl, fk = self.obs_layer.currentLayer(), self.obs_fk.currentField()
        notes = []
        if fl is not None and key:
            values = [f[key] for f in fl.getFeatures()]
            empty = sum(1 for v in values if is_empty(v))
            filled = [v for v in values if not is_empty(v)]
            dupes = len(filled) - len(set(filled))
            notes.append(f'{len(values)} Flächen, {empty} ohne Schlüssel, {dupes} doppelte Schlüssel.')
            if empty:
                notes.append('⚠ Flächen ohne Schlüssel sind nicht zuordenbar.')
            if dupes:
                notes.append('⚠ Schlüssel ist nicht eindeutig!')
            if nl is not None and fk:
                kt = fl.fields().field(key).typeName().lower()
                ft = nl.fields().field(fk).typeName().lower()
                text = ('char', 'text', 'string')
                if any(t in kt for t in text) != any(t in ft for t in text):
                    notes.append(f'⚠ Feldtypen passen nicht ({kt} ↔ {ft}).')
        self.info.setText('\n'.join(notes))

    def apply(self):
        fl, key = self.area_layer.currentLayer(), self.area_key.currentField()
        nl, fk = self.obs_layer.currentLayer(), self.obs_fk.currentField()
        if fl is None or nl is None or not key or not fk:
            QMessageBox.warning(self, 'GoKart', 'Bitte beide Layer und Felder wählen.')
            return
        p = QgsProject.instance()
        ECU.setProjectVariable(p, VAR_AREA_LAYER, fl.id())
        ECU.setProjectVariable(p, VAR_AREA_KEY, key)
        ECU.setProjectVariable(p, VAR_AREA_LABEL, self.area_label.currentField() or '')
        ECU.setProjectVariable(p, VAR_OBS_LAYER, nl.id())
        ECU.setProjectVariable(p, VAR_OBS_FK, fk)
        ECU.setProjectVariable(p, B.VAR_SCHLUESSEL, self.biotop_key.currentData() or '')
        if self.make_relation.isChecked() and not self.write_relation(fl, key, nl, fk):
            return
        if self.make_relation.isChecked():
            self.write_biotop_relation(fl, key)
        p.setDirty(True)
        self.accept()

    def write_relation(self, fl, key, nl, fk):
        rm = QgsProject.instance().relationManager()
        # Andere Beziehungen auf dasselbe Fremdschlüsselfeld machen die Zuordnung mehrdeutig.
        others = [r for r in rm.relations().values()
                  if r.id() != RELATION_ID and r.referencingLayerId() == nl.id()
                  and fk in r.fieldPairs()]
        if others:
            names = ', '.join(r.name() for r in others)
            answer = QMessageBox.question(
                self, 'GoKart',
                f'Weitere Beziehungen nutzen "{fk}" bereits:\n{names}\n\n'
                'Diese entfernen? (Sonst ist die Zuordnung mehrdeutig.)')
            if answer == QMessageBox.Yes:
                for r in others:
                    rm.removeRelation(r.id())
        rel = QgsRelation()
        rel.setId(RELATION_ID)
        rel.setName('Fläche → Artnachweise')
        rel.setReferencedLayer(fl.id())
        rel.setReferencingLayer(nl.id())
        rel.addFieldPair(fk, key)
        if not rel.isValid():
            err = rel.validationError() if hasattr(rel, 'validationError') else ''
            QMessageBox.warning(self, 'GoKart', 'Beziehung ungültig. ' + err)
            return False
        rm.removeRelation(RELATION_ID)
        rm.addRelation(rel)
        ECU.setProjectVariable(QgsProject.instance(), VAR_RELATION, RELATION_ID)
        return True

    def write_biotop_relation(self, fl, key):
        """Fläche 1:n Biotop-Zuordnungen – damit QField sie im Flächenformular zeigt."""
        zl = next(iter(QgsProject.instance().mapLayersByName(B.T_ZUORDNUNG)), None)
        if zl is None:
            return
        rm = QgsProject.instance().relationManager()
        rel = QgsRelation()
        rel.setId(BIOTOP_RELATION_ID)
        rel.setName('Fläche → Biotoptypen')
        rel.setReferencedLayer(fl.id())
        rel.setReferencingLayer(zl.id())
        rel.addFieldPair('flaeche_id', key)
        if rel.isValid():
            rm.removeRelation(BIOTOP_RELATION_ID)
            rm.addRelation(rel)


_VOSK_MODELS = {}  # Modell nur einmal laden (große Modelle brauchen viele Sekunden)


class VoiceThread(QThread):
    result = pyqtSignal(str)
    failure = pyqtSignal(str)
    ready = pyqtSignal()          # Mikrofon offen -> jetzt sprechen
    status = pyqtSignal(str)

    def __init__(self, model_path, parent=None):
        super().__init__(parent)
        self.model_path = model_path

    def run(self):
        try:
            import sounddevice as sd
            from vosk import Model, KaldiRecognizer
            import queue
            model = _VOSK_MODELS.get(self.model_path)
            if model is None:
                self.status.emit('Sprachmodell wird geladen …')
                model = Model(self.model_path)
                _VOSK_MODELS[self.model_path] = model
            # Bevorzugt die Logitech-Webcam (USB-Kennung steht nur unter Linux im Namen),
            # sonst das Standard-Mikrofon des Systems (Windows)
            devices = sd.query_devices()
            webcam = next(
                (i for i, d in enumerate(devices)
                 if '0x46d:0x825' in d['name']
                 and d['max_input_channels'] > 0),
                None
            )
            if webcam is None and not any(d['max_input_channels'] > 0 for d in devices):
                raise RuntimeError('Kein Mikrofon gefunden.')
            rate = 16000
            recognizer = KaldiRecognizer(model, rate)
            q = queue.Queue()

            def callback(indata, frames, time_info, status):
                q.put(bytes(indata))

            # Max. 8 Sekunden; Ende bei erster längerer Pause NACH erkanntem Text
            with sd.RawInputStream(samplerate=rate, blocksize=8000, dtype='int16',
                                   channels=1, device=webcam, callback=callback):
                self.ready.emit()
                for _ in range(16):
                    if recognizer.AcceptWaveform(q.get(timeout=3)):
                        t = json.loads(recognizer.Result()).get('text', '').strip()
                        if t:
                            self.result.emit(t)
                            return
                self.result.emit(json.loads(recognizer.FinalResult()).get('text', '').strip())
        except Exception as e:
            self.failure.emit(str(e))


class GoKartDock(QDockWidget):
    def __init__(self, iface):
        super().__init__('GoKart – Pflanzenkartierung', iface.mainWindow())
        self.iface = iface
        self.setObjectName('GoKartDesktopDock')
        self.taxa = []
        self.matches = []
        self.fl_ids = []
        self.area_source = None
        self.area_lookup = {}
        self.voice = None
        self.voice_ziel = 'suche'
        self.biotop_typen = []
        self.biotop_matches = []
        self.biotop_zuordnungen = []
        self.settings = QSettings()
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.addWidget(QLabel('Aktive Fläche'))
        self.area = QComboBox()
        layout.addWidget(self.area)
        self.show_unnamed = QCheckBox('Unbenannte Flächen anzeigen')
        self.show_unnamed.setChecked(False)
        layout.addWidget(self.show_unnamed)
        row = QHBoxLayout()
        self.reload_btn = QPushButton('↻ Flächen laden')
        self.pick_btn = QPushButton('Auswahl aus Karte')
        self.setup_btn = QPushButton('Einrichten…')
        row.addWidget(self.reload_btn)
        row.addWidget(self.pick_btn)
        row.addWidget(self.setup_btn)
        layout.addLayout(row)
        layout.addWidget(QLabel('Pflanzenart suchen / einsprechen'))
        row = QHBoxLayout()
        self.query = QLineEdit()
        self.query.setPlaceholderText('z. B. Grünlilie')
        self.mic = QPushButton('● Sprechen')  # Emoji fehlt in Ubuntu-Schriften
        row.addWidget(self.query)
        row.addWidget(self.mic)
        layout.addLayout(row)
        self.results = QListWidget()
        # GoKart: Fünf Vorschläge gleichzeitig anzeigen
        self.results.setMinimumHeight(135)
        self.results.setMinimumWidth(320)
        layout.addWidget(self.results)
        self.save_btn = QPushButton('Art speichern')
        layout.addWidget(self.save_btn)
        layout.addWidget(QLabel('Bereits erfasste Arten dieser Fläche'))
        self.existing = QListWidget()
        layout.addWidget(self.existing)
        self.delete_btn = QPushButton('Markierte Art löschen')
        self.delete_btn.setEnabled(False)
        layout.addWidget(self.delete_btn)
        # --- Biotoptypen der aktiven Fläche (Schlüssel aus Projektvariable gokart_biotop_schluessel)
        self.biotop_box = QWidget()
        bb = QVBoxLayout(self.biotop_box)
        bb.setContentsMargins(0, 6, 0, 0)
        self.biotop_titel = QLabel('Biotoptyp')
        bb.addWidget(self.biotop_titel)
        row = QHBoxLayout()
        self.biotop_query = QLineEdit()
        self.biotop_query.setPlaceholderText('Code oder Name, z. B. WMy / Knick')
        self.biotop_mic = QPushButton('● Sprechen')
        row.addWidget(self.biotop_query)
        row.addWidget(self.biotop_mic)
        bb.addLayout(row)
        self.biotop_results = QListWidget()
        self.biotop_results.setMinimumHeight(110)
        bb.addWidget(self.biotop_results)
        row = QHBoxLayout()
        self.biotop_haupt = QPushButton('Als Hauptbiotop')
        self.biotop_neben = QPushButton('Als Nebenbiotop')
        row.addWidget(self.biotop_haupt)
        row.addWidget(self.biotop_neben)
        bb.addLayout(row)
        self.biotop_liste = QListWidget()
        self.biotop_liste.setMaximumHeight(110)
        bb.addWidget(self.biotop_liste)
        row = QHBoxLayout()
        self.biotop_rolle = QPushButton('Haupt ↔ Neben')
        self.biotop_weg = QPushButton('Entfernen')
        self.biotop_rolle.setEnabled(False)
        self.biotop_weg.setEnabled(False)
        row.addWidget(self.biotop_rolle)
        row.addWidget(self.biotop_weg)
        bb.addLayout(row)
        self.biotop_box.setVisible(False)
        layout.addWidget(self.biotop_box)
        self.foto_info = QLabel('')
        self.foto_info.setWordWrap(True)
        layout.addWidget(self.foto_info)
        self.foto_list = QListWidget()      # Standortfotos der aktiven Fläche (Doppelklick öffnet)
        self.foto_list.setViewMode(QListWidget.IconMode)
        self.foto_list.setIconSize(QSize(80, 80))
        self.foto_list.setResizeMode(QListWidget.Adjust)
        self.foto_list.setMovement(QListWidget.Static)
        self.foto_list.setFixedHeight(112)
        self.foto_list.setVisible(False)
        layout.addWidget(self.foto_list)
        # Markiertes Foto: große Vorschau + Kommentar (tippen oder einsprechen)
        self.foto_box = QWidget()
        fb = QVBoxLayout(self.foto_box)
        fb.setContentsMargins(0, 0, 0, 0)
        self.foto_gross = QLabel()
        self.foto_gross.setAlignment(Qt.AlignCenter)
        self.foto_gross.setMinimumHeight(160)
        self.foto_gross.setToolTip('Doppelklick in der Fotoleiste öffnet das Bild in voller Größe')
        fb.addWidget(self.foto_gross)
        row = QHBoxLayout()
        self.foto_kommentar = QLineEdit()
        self.foto_kommentar.setPlaceholderText('Kommentar zum Standort …')
        fb.addWidget(QLabel('Kommentar zum Foto (tippen oder einsprechen):'))
        self.foto_mic = QPushButton('● Kommentar sprechen')
        row.addWidget(self.foto_kommentar)
        row.addWidget(self.foto_mic)
        fb.addLayout(row)
        self.foto_save = QPushButton('Kommentar speichern')
        fb.addWidget(self.foto_save)
        self.foto_box.setVisible(False)
        layout.addWidget(self.foto_box)
        row = QHBoxLayout()
        self.export_btn = QPushButton('Export (CSV)')
        self.liste_btn = QPushButton('Artenliste je Fläche')
        self.liste_btn.setToolTip('Gutachten-Tabelle aller Flächen als HTML (druckbar/PDF) und CSV')
        row.addWidget(self.export_btn)
        row.addWidget(self.liste_btn)
        layout.addLayout(row)
        self.status = QLabel('QGIS-Projekt mit gokart.gpkg öffnen.')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(body)
        self.setWidget(scroll)
        self.reload_btn.clicked.connect(self.reload)
        self.show_unnamed.toggled.connect(self.reload)
        self.pick_btn.clicked.connect(self.pick_selected)
        self.setup_btn.clicked.connect(self.open_setup)
        self.area.currentIndexChanged.connect(self.refresh_existing)
        # GoKart: Suche mit 300 ms Verzögerung
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(300)
        self.search_timer.timeout.connect(self.search)
        self.query.textChanged.connect(
            lambda: self.search_timer.start()
        )
        self.save_btn.clicked.connect(self.save)
        self.delete_btn.clicked.connect(self.delete_selected)
        self.existing.currentRowChanged.connect(
            lambda r: self.delete_btn.setEnabled(r >= 0))
        self.foto_list.currentItemChanged.connect(lambda it, _alt: self.foto_waehlen(it))
        self.foto_save.clicked.connect(self.foto_kommentar_speichern)
        self.foto_kommentar.returnPressed.connect(self.foto_kommentar_speichern)
        self.foto_mic.clicked.connect(lambda: self.record(ziel='kommentar'))
        self.foto_list.itemDoubleClicked.connect(
            lambda it: QDesktopServices.openUrl(QUrl.fromLocalFile(it.data(Qt.UserRole))))
        self.export_btn.clicked.connect(self.export_csv)
        self.liste_btn.clicked.connect(self.export_artenliste)
        self.mic.clicked.connect(self.record)
        self.biotop_timer = QTimer(self)
        self.biotop_timer.setSingleShot(True)
        self.biotop_timer.setInterval(250)
        self.biotop_timer.timeout.connect(self.biotop_search)
        self.biotop_query.textChanged.connect(lambda: self.biotop_timer.start())
        self.biotop_query.returnPressed.connect(self.biotop_enter)
        self.biotop_mic.clicked.connect(lambda: self.record(ziel='biotop'))
        self.biotop_haupt.clicked.connect(lambda: self.biotop_save('Haupt'))
        self.biotop_neben.clicked.connect(lambda: self.biotop_save('Neben'))
        self.biotop_rolle.clicked.connect(self.biotop_toggle)
        self.biotop_weg.clicked.connect(self.biotop_delete)
        self.biotop_liste.currentRowChanged.connect(
            lambda r: (self.biotop_rolle.setEnabled(r >= 0), self.biotop_weg.setEnabled(r >= 0)))
        self.iface.currentLayerChanged.connect(self.on_layer_changed)
        QgsProject.instance().layersAdded.connect(self.on_project_layers_changed)
        QgsProject.instance().layersRemoved.connect(self.on_project_layers_changed)
        QgsProject.instance().readProject.connect(self.on_project_layers_changed)
        self.reload()

    def layer(self, name):
        layers = QgsProject.instance().mapLayersByName(name)
        return layers[0] if layers else None

    def message(self, text):
        self.status.setText(text)
        self.iface.messageBar().pushInfo('GoKart', text)

    def configured(self):
        return bool(project_var(VAR_AREA_LAYER))

    def polygon_layer(self):
        """Konfigurierter Flächenlayer; ohne Einrichtung wie bisher der aktive Layer."""
        if self.configured():
            layer = find_layer(project_var(VAR_AREA_LAYER))
            return layer if is_polygon_layer(layer) else None
        layer = self.iface.activeLayer()
        return layer if is_polygon_layer(layer) else None

    def obs_layer(self):
        return find_layer(project_var(VAR_OBS_LAYER)) or self.layer('artnachweise')

    def obs_fk(self):
        return project_var(VAR_OBS_FK) or 'flaeche_id'

    def key_field(self, layer):
        key = project_var(VAR_AREA_KEY) if self.configured() else ''
        return key if layer is not None and key in layer.fields().names() else ''

    def label_field(self, layer):
        names = layer.fields().names()
        label = project_var(VAR_AREA_LABEL)
        if label in names:
            return label
        return next((n for n in LABEL_FIELDS if n in names), None)

    def on_layer_changed(self, layer):
        # Mit Einrichtung ist der aktive Layer egal.
        if not self.configured() and self.polygon_layer() is not None:
            self.reload()

    def on_project_layers_changed(self, *args):
        self.reload()

    def open_setup(self):
        dlg = GoKartSetupDialog(self)
        if dlg.exec_():
            self.reload()
            self.message('Einrichtung gespeichert – Projekt speichern (Strg+S), damit QField sie erhält.')

    def area_key(self, layer, feature):
        key = self.key_field(layer)
        if key:
            v = feature[key]
            return None if is_empty(v) else v
        # Altes Verfahren ohne Einrichtung: Quellpfad + Layername + fid.
        source = layer.source().split('|', 1)[0]
        digest = hashlib.sha1((source + '|' + layer.name()).encode('utf-8')).hexdigest()[:8]
        return 'G-' + digest + '-' + format(feature.id(), 'x')

    def obs_request(self, fk_value, taxon_id=None):
        expr = QgsExpression.createFieldEqualityExpression(self.obs_fk(), fk_value)
        if taxon_id is not None:
            expr += ' AND ' + QgsExpression.createFieldEqualityExpression('taxon_id', taxon_id)
        return QgsFeatureRequest().setFilterExpression(expr)

    def reload(self):
        fl = self.polygon_layer()
        tx = self.layer('taxon')
        old = self.area.currentData()
        self.area.blockSignals(True)
        self.area.clear()
        self.area_lookup = {}
        self.area_source = fl.id() if fl else None
        problem = ''
        skipped = 0
        if self.configured() and fl is None:
            problem = 'Eingerichteter Flächenlayer fehlt – „Einrichten…“ prüfen.'
        elif self.configured() and not self.key_field(fl):
            problem = f'Schlüsselfeld "{project_var(VAR_AREA_KEY)}" fehlt in {fl.name()}.'
            fl = None
        if fl:
            label_field = self.label_field(fl)
            for f in fl.getFeatures():
                key = self.area_key(fl, f)
                if key is None:
                    skipped += 1
                    continue
                title = val(f, label_field).strip() if label_field else ''
                if not title and not self.show_unnamed.isChecked():
                    continue
                title = title or 'Fläche'
                shown = key if self.configured() else f'ID {f.id()}'
                self.area.addItem(f'{title} ({shown})', key)
                self.area_lookup[key] = f.id()
            self.area.model().sort(0)
            i = self.area.findData(old)
            if i >= 0:
                self.area.setCurrentIndex(i)
        self.area.blockSignals(False)
        self.taxa = []
        if tx:
            for f in tx.getFeatures():
                tid = val(f, 'taxon_id')
                if not tid:
                    continue
                german = val(f, 'deutscher_name') or val(f, 'anzeige_name')
                scientific = val(f, 'wissenschaftlicher_name')
                self.taxa.append({'id': tid, 'de': german, 'scientific': scientific,
                                  'terms': norm(german) + ' | ' + norm(scientific)})
        by_id = {t['id']: t for t in self.taxa}
        for table, fields in [('suchnamen', ['name']), ('eigene_synonyme', ['synonym'])]:
            layer = self.layer(table)
            if layer:
                for f in layer.getFeatures():
                    item = by_id.get(val(f, 'taxon_id'))
                    if item:
                        for field in fields:
                            item['terms'] += ' | ' + norm(val(f, field))
        self.biotope_laden()
        self.refresh_existing()
        self.search()
        if problem:
            self.message(problem)
        elif self.configured():
            extra = f', {skipped} ohne Schlüssel übersprungen' if skipped else ''
            self.message(f'{self.area.count()} Flächen aus „{fl.name()}“{extra}, {len(self.taxa)} Taxa geladen.')
        else:
            self.message(f'{self.area.count()} Flächen aus aktivem Polygonlayer (nicht eingerichtet), '
                         f'{len(self.taxa)} Taxa geladen.')

    def area_id(self):
        v = self.area.currentData()
        return None if is_empty(v) else v

    def pick_selected(self):
        fl = self.polygon_layer()
        if fl is None:
            self.message('Bitte zuerst einen Polygonlayer aktivieren bzw. „Einrichten…“ prüfen.')
            return
        selected = fl.selectedFeatures()
        if not selected:
            self.message(f'In „{fl.name()}“ zuerst eine Fläche auswählen.')
            return
        key = self.area_key(fl, selected[0])
        if key is None:
            self.message('Diese Fläche hat keinen Schlüsselwert.')
            return
        i = self.area.findData(key)
        if i < 0:
            # Auch unbenannte Polygone aus der Karte auswählen können.
            title_field = self.label_field(fl)
            title = val(selected[0], title_field).strip() if title_field else ''
            shown = key if self.configured() else f'ID {selected[0].id()}'
            self.area.addItem(f'{title or "Fläche"} ({shown})', key)
            self.area_lookup[key] = selected[0].id()
            i = self.area.findData(key)
        if i >= 0:
            self.area.setCurrentIndex(i)
            self.message('Fläche gewählt: ' + self.area.currentText())

    def search(self):
        self.results.clear()
        q = norm(self.query.text())
        self.matches = []
        if not q:
            return
        # GoKart: Verbesserte Suche mit fünf Vorschlägen
        from difflib import SequenceMatcher
        import re

        def vereinfachen(s):
            s = norm(str(s or ""))
            return re.sub(r"[^a-z0-9]", "", s)

        # Häufige Fehler der Spracherkennung
        korrekturen = {
            "bogenhans": "bogenhanf",
            "bogenhand": "bogenhanf",
            "bogenhahn": "bogenhanf",
            "gruenlilie": "grunlilie",
        }

        suche = vereinfachen(q)
        suche = korrekturen.get(suche, suche)



        def bewertung(t):
            begriffe = [
                t.get("de") or "",
                t.get("scientific") or ""
            ]
            begriffe += [n.strip() for n in t.get("terms", "").split(" | ") if n.strip()]

            punkte = []

            for begriff in begriffe:
                name = vereinfachen(begriff)

                if not name:
                    continue

                if name == suche:
                    score = 1.0
                elif name.startswith(suche):
                    score = 0.95
                elif suche in name:
                    score = 0.85
                else:
                    score = SequenceMatcher(
                        None, suche, name
                    ).ratio()

                punkte.append(score)

            return max(punkte, default=0)

        kandidaten = [
            (bewertung(t), t)
            for t in self.taxa
        ]

        kandidaten = [
            (score, t)
            for score, t in kandidaten
            if score >= 0.45
        ]

        # GoKart: Exakte Synonyme und Artnamen bevorzugen
        def exakter_treffer(t):
            namen = [
                t.get('de') or '',
                t.get('scientific') or ''
            ]
            namen += [n.strip() for n in t.get('terms', '').split(' | ') if n.strip()]

            return any(
                vereinfachen(name) == suche
                for name in namen
            )

        kandidaten.sort(
            key=lambda x: (
                not exakter_treffer(x[1]),
                -x[0]
            )
        )

        self.matches = [
            t for score, t in kandidaten[:5]
        ]
        for t in self.matches:
            self.results.addItem(f"{t['de'] or t['scientific']}  ({t['scientific']})")
        if len(self.matches) == 1:
            self.results.setCurrentRow(0)

    def refresh_existing(self):
        self.existing.clear()
        layer = self.obs_layer()
        fid = self.area_id()
        if not layer or fid is None:
            return
        count = 0
        for f in layer.getFeatures(self.obs_request(fid)):
            item = QListWidgetItem(val(f, 'deutscher_name') or val(f, 'wissenschaftlicher_name'))
            item.setData(Qt.UserRole, f.id())          # Feature-ID zum Löschen merken
            self.existing.addItem(item)
            count += 1
        self.existing.setToolTip(f'{count} Artnachweise auf {fid}')
        self.show_fotos()
        self.biotope_anzeigen()

    # ---------------------------------------------------------------- Biotoptypen
    def biotop_layer(self, tabelle):
        """Projektlayer, sonst direkt aus der GeoPackage der Artnachweise (muss nicht im Projekt sein)."""
        lyr = self.layer(tabelle)
        if lyr is not None and lyr.isValid():
            return lyr
        an = self.obs_layer()
        if an is None:
            return None
        gpkg = an.source().split('|', 1)[0]
        lyr = QgsVectorLayer(f'{gpkg}|layername={tabelle}', 'gokart_' + tabelle, 'ogr')
        return lyr if lyr.isValid() and 'code' in lyr.fields().names() else None

    def biotop_schluessel(self):
        return project_var(B.VAR_SCHLUESSEL).upper()

    def biotope_laden(self):
        """Katalog des geltenden Schlüssels für die Suche laden."""
        self.biotop_typen = []
        s = self.biotop_schluessel()
        kat = self.biotop_layer(B.T_TYPEN)
        if kat is not None and s:
            req = QgsFeatureRequest().setFilterExpression(QgsExpression.createFieldEqualityExpression('schluessel', s))
            for f in kat.getFeatures(req):
                e = val(f, 'ebene')
                self.biotop_typen.append({'code': val(f, 'code'), 'name': val(f, 'name'), 'nr': val(f, 'nr'),
                                          'ebene': int(float(e)) if e else 0, 'bund_code': val(f, 'bund_code'),
                                          'ffh_lrt': val(f, 'ffh_lrt')})
        bereit = bool(self.biotop_typen) and self.biotop_layer(B.T_ZUORDNUNG) is not None
        self.biotop_box.setVisible(bereit or bool(s) or kat is not None)
        if not s:
            self.biotop_titel.setText('Biotoptyp: Schlüssel unter „Einrichten…“ wählen')
        elif not self.biotop_typen:
            self.biotop_titel.setText(f'Biotoptyp: Katalog {s} fehlt – „Einrichten…“ → „Kataloge einspielen“')
        else:
            self.biotop_titel.setText(f'Biotoptypen dieser Fläche (Schlüssel {s})')
        for w in (self.biotop_query, self.biotop_mic, self.biotop_haupt, self.biotop_neben):
            w.setEnabled(bereit)
        self.biotop_search()

    def biotop_search(self):
        self.biotop_results.clear()
        self.biotop_matches = B.suchen(self.biotop_typen, self.biotop_query.text(), 6)
        for t in self.biotop_matches:
            extra = ' · '.join(x for x in (f"FFH {t['ffh_lrt']}" if t['ffh_lrt'] else '',
                                           f"Bund {t['bund_code']}" if t['bund_code'] else '') if x)
            self.biotop_results.addItem(f"{t['code']} – {t['name']}" + (f'  ({extra})' if extra else ''))
        if self.biotop_matches and B.bewerten(self.biotop_query.text(), self.biotop_matches[0]) >= 0.97:
            self.biotop_results.setCurrentRow(0)

    def biotop_enter(self):
        self.biotop_timer.stop()
        self.biotop_search()
        if self.biotop_results.currentRow() >= 0:
            hat_haupt = any(z['rolle'] == 'Haupt' and z['schluessel'] == self.biotop_schluessel()
                            for z in self.biotop_zuordnungen)
            self.biotop_save('Neben' if hat_haupt else 'Haupt')

    def biotope_anzeigen(self):
        self.biotop_liste.clear()
        self.biotop_zuordnungen = []
        zl, flaeche = self.biotop_layer(B.T_ZUORDNUNG), self.area_id()
        if zl is None or flaeche is None:
            return
        expr = QgsExpression.createFieldEqualityExpression('flaeche_id', str(flaeche))
        for f in zl.getFeatures(QgsFeatureRequest().setFilterExpression(expr)):
            self.biotop_zuordnungen.append({'fid': f.id(), 'schluessel': val(f, 'schluessel'), 'code': val(f, 'code'),
                                            'name': val(f, 'name'), 'rolle': val(f, 'rolle') or 'Neben'})
        self.biotop_zuordnungen.sort(key=lambda z: (z['rolle'] != 'Haupt', z['code']))
        for z in self.biotop_zuordnungen:
            fremd = f"  [{z['schluessel']}]" if z['schluessel'] != self.biotop_schluessel() else ''
            it = QListWidgetItem(('● ' if z['rolle'] == 'Haupt' else '○ ') + f"{z['code']} – {z['name']}{fremd}")
            if z['rolle'] == 'Haupt':
                schrift = it.font()
                schrift.setBold(True)
                it.setFont(schrift)
            self.biotop_liste.addItem(it)

    def biotop_aendern(self, aktion):
        """aktion(layer) im Bearbeitungsmodus ausführen und sofort speichern."""
        zl = self.biotop_layer(B.T_ZUORDNUNG)
        if zl is None:
            self.message('Tabelle biotopzuordnung fehlt – „Einrichten…“ → „Kataloge einspielen“.')
            return False
        if zl.isEditable():
            self.message('Biotop-Zuordnungen sind im Bearbeitungsmodus. Bitte erst speichern oder verwerfen.')
            return False
        if not zl.startEditing():
            self.message('Layer kann nicht bearbeitet werden.')
            return False
        if not aktion(zl) or not zl.commitChanges():
            fehler = '; '.join(zl.commitErrors())
            zl.rollBack()
            self.message('Speichern fehlgeschlagen: ' + fehler)
            return False
        return True

    @staticmethod
    def _rolle(zl, fid, rolle):
        return zl.changeAttributeValue(fid, zl.fields().indexFromName('rolle'), rolle)

    def biotop_save(self, rolle):
        flaeche = self.area_id()
        i = self.biotop_results.currentRow()
        if flaeche is None or i < 0 or i >= len(self.biotop_matches):
            self.message('Fläche und Biotoptyp auswählen.')
            return
        t, s = self.biotop_matches[i], self.biotop_schluessel()
        vorhanden = next((z for z in self.biotop_zuordnungen if z['schluessel'] == s and z['code'] == t['code']), None)
        if vorhanden and vorhanden['rolle'] == rolle:
            self.message(f"{t['code']} ist bereits als {rolle}biotop erfasst.")
            return
        alte = [z for z in self.biotop_zuordnungen if rolle == 'Haupt' and z['rolle'] == 'Haupt'
                and z['schluessel'] == s and z is not vorhanden]
        eingabe = self.biotop_query.text()

        def aktion(zl):
            if not all(self._rolle(zl, z['fid'], 'Neben') for z in alte):
                return False
            if vorhanden:
                return self._rolle(zl, vorhanden['fid'], rolle)
            f = QgsFeature(zl.fields())
            werte = {'flaeche_id': str(flaeche), 'schluessel': s, 'code': t['code'], 'name': t['name'],
                     'rolle': rolle, 'bund_code': t['bund_code'] or None, 'original_eingabe': eingabe,
                     'erfasst_am': datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}
            for k, v in werte.items():
                if k in zl.fields().names():
                    f.setAttribute(k, v)
            return zl.addFeature(f)
        if self.biotop_aendern(aktion):
            self.biotope_anzeigen()
            self.message(f"Gespeichert: {t['code']} ({rolle}) → {flaeche}"
                         + (' · ' + ', '.join(z['code'] for z in alte) + ' jetzt Neben' if alte else ''))
            self.biotop_query.clear()

    def biotop_toggle(self):
        r = self.biotop_liste.currentRow()
        if r < 0:
            return
        z = self.biotop_zuordnungen[r]
        neu = 'Neben' if z['rolle'] == 'Haupt' else 'Haupt'
        alte = [x for x in self.biotop_zuordnungen if neu == 'Haupt' and x['rolle'] == 'Haupt'
                and x['schluessel'] == z['schluessel'] and x is not z]
        if self.biotop_aendern(lambda zl: all(self._rolle(zl, x['fid'], 'Neben') for x in alte)
                               and self._rolle(zl, z['fid'], neu)):
            self.biotope_anzeigen()
            self.message(f"{z['code']} ist jetzt {neu}biotop.")

    def biotop_delete(self):
        r = self.biotop_liste.currentRow()
        if r < 0:
            return
        z = self.biotop_zuordnungen[r]
        if QMessageBox.question(self, 'Biotoptyp entfernen', f"{z['code']} – {z['name']} von dieser Fläche entfernen?",
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        if self.biotop_aendern(lambda zl: zl.deleteFeature(z['fid'])):
            self.biotope_anzeigen()
            self.message(f"Entfernt: {z['code']}")

    # ---------------------------------------------------------------- Standortfotos (Tabelle "fotos", Dateien unter fotos/)
    def foto_layer(self):
        """Tabelle fotos aus derselben GeoPackage wie die Artnachweise (muss nicht im Projekt sein)."""
        an = self.obs_layer()
        if an is None:
            return None
        gpkg = an.source().split('|', 1)[0]
        lyr = QgsVectorLayer(f'{gpkg}|layername=fotos', 'gokart_fotos', 'ogr')
        return lyr if lyr.isValid() and 'datei' in lyr.fields().names() else None

    def fotos_fuer(self, flaeche, lyr=None):
        lyr = lyr or self.foto_layer()
        if lyr is None or flaeche is None:
            return []
        expr = QgsExpression.createFieldEqualityExpression('flaeche_id', str(flaeche))
        fotos = [{'fid': f.id(), 'datei': val(f, 'datei'), 'kommentar': val(f, 'kommentar'),
                  'am': val(f, 'aufgenommen_am'), 'lon': val(f, 'lon'), 'lat': val(f, 'lat')}
                 for f in lyr.getFeatures(QgsFeatureRequest().setFilterExpression(expr))]
        return sorted(fotos, key=lambda x: x['am'])

    @staticmethod
    def foto_pfad(datei):
        return Path(QgsProject.instance().homePath()) / datei

    def show_fotos(self, auswahl_fid=None):
        self.foto_list.blockSignals(True)
        self.foto_list.clear()
        self.foto_list.blockSignals(False)
        self.foto_box.setVisible(False)
        flaeche = self.area_id()
        fotos = self.fotos_fuer(flaeche) if flaeche is not None else []
        self.foto_list.setVisible(bool(fotos))
        if flaeche is None:
            self.foto_info.setText('')
            return
        if not fotos:
            self.foto_info.setText('Keine Standortfotos zu dieser Fläche (Aufnahme in QField über den Kamera-Knopf).')
            return
        texte = []
        for i, ft in enumerate(fotos, 1):
            pfad = self.foto_pfad(ft['datei'])
            bild = QPixmap(str(pfad))
            symbol = QIcon(bild.scaled(220, 220, Qt.KeepAspectRatio, Qt.SmoothTransformation)) if not bild.isNull() else QIcon()
            it = QListWidgetItem(symbol, str(i) if not bild.isNull() else f'{i}: Datei fehlt')
            it.setData(Qt.UserRole, str(pfad))
            it.setData(Qt.UserRole + 1, ft['fid'])
            it.setData(Qt.UserRole + 2, ft['kommentar'])
            gps = f"\nGPS {ft['lat']}, {ft['lon']}" if ft['lat'] else ''
            it.setToolTip(f"{ft['datei']}\n{ft['am'].replace('T', ' ')}{gps}\n{ft['kommentar']}")
            self.foto_list.addItem(it)
            if ft['kommentar']:
                texte.append(f"{i}: {ft['kommentar']}")
        for i in range(self.foto_list.count()):
            if auswahl_fid is not None and self.foto_list.item(i).data(Qt.UserRole + 1) == auswahl_fid:
                self.foto_list.setCurrentRow(i)
        self.foto_info.setText(f'Standortfotos: {len(fotos)} – anklicken für Vorschau/Kommentar, Doppelklick öffnet' + ('\n' + '\n'.join(texte) if texte else ''))

    def foto_waehlen(self, it):
        self.foto_box.setVisible(it is not None)
        if it is None:
            return
        bild = QPixmap(it.data(Qt.UserRole))
        breite = max(240, self.foto_list.width() - 10)
        self.foto_gross.setPixmap(bild.scaled(breite, 240, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                                  if not bild.isNull() else QPixmap())
        if bild.isNull():
            self.foto_gross.setText('Bilddatei nicht gefunden')
        self.foto_kommentar.setText(it.data(Qt.UserRole + 2) or '')

    def foto_kommentar_speichern(self):
        it = self.foto_list.currentItem()
        fl = self.foto_layer()
        if it is None or fl is None:
            return
        fid = it.data(Qt.UserRole + 1)
        text = self.foto_kommentar.text().strip()
        idx = fl.fields().indexFromName('kommentar')
        if not fl.startEditing() or not fl.changeAttributeValue(fid, idx, text or None) or not fl.commitChanges():
            errors = '; '.join(fl.commitErrors())
            fl.rollBack()
            self.message('Kommentar nicht gespeichert: ' + errors)
            return
        self.message('Kommentar gespeichert.')
        self.show_fotos(auswahl_fid=fid)

    @staticmethod
    def vorschau_uri(pfad, groesse=240):
        """Kleines JPEG als data:-URI für die HTML-Artenliste."""
        bild = QImage(str(pfad))
        if bild.isNull():
            return ''
        bild = bild.scaled(groesse, groesse, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        puffer = QBuffer()
        puffer.open(QIODevice.WriteOnly)
        bild.save(puffer, 'JPG', 80)
        return 'data:image/jpeg;base64,' + bytes(puffer.data().toBase64()).decode('ascii')

    def delete_selected(self):
        """Markierten Artnachweis der aktiven Fläche nach Rückfrage löschen."""
        layer = self.obs_layer()
        item = self.existing.currentItem()
        if not layer or item is None:
            return
        if layer.isEditable():
            self.message('Artnachweise sind im Bearbeitungsmodus. Bitte erst speichern oder verwerfen.')
            return
        name = item.text()
        if QMessageBox.question(self, 'Artnachweis löschen',
                                f'„{name}“ von dieser Fläche löschen?',
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        if not layer.startEditing():
            self.message('Layer kann nicht bearbeitet werden.')
            return
        if not layer.deleteFeature(item.data(Qt.UserRole)) or not layer.commitChanges():
            errors = '; '.join(layer.commitErrors())
            layer.rollBack()
            self.message('Löschen fehlgeschlagen: ' + errors)
            return
        self.refresh_existing()
        self.message(f'Gelöscht: {name}')

    def save(self):
        layer = self.obs_layer()
        fid = self.area_id()
        idx = self.results.currentRow()
        if not layer or fid is None or idx < 0 or idx >= len(self.matches):
            self.message('Fläche und Art auswählen; Artnachweis-Layer muss geladen sein.')
            return
        taxon = self.matches[idx]
        tid = int(taxon['id']) if taxon['id'].isdigit() else taxon['id']
        if next(layer.getFeatures(self.obs_request(fid, tid)), None) is not None:
            self.message('Art ist auf dieser Fläche bereits erfasst.')
            return
        was_editable = layer.isEditable()
        if was_editable:
            self.message('Artnachweise sind bereits im Bearbeitungsmodus. Bitte Änderungen erst speichern oder verwerfen.')
            return
        if not layer.startEditing():
            self.message('Layer kann nicht bearbeitet werden.')
            return
        feature = QgsFeature(layer.fields())
        fields = {
            self.obs_fk(): fid, 'taxon_id': tid,
            'wissenschaftlicher_name': taxon['scientific'], 'deutscher_name': taxon['de'],
            'original_eingabe': self.query.text(),
            'erfasst_am': datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}
        names = layer.fields().names()
        for key, value in fields.items():
            if key in names:
                feature.setAttribute(key, value)
        if not layer.addFeature(feature):
            if not was_editable:
                layer.rollBack()
            self.message('Art konnte nicht hinzugefügt werden.')
            return
        # Sofort speichern, auch wenn der Layer zuvor schon im Bearbeitungsmodus war.
        if not layer.commitChanges():
            errors = '; '.join(layer.commitErrors())
            self.message('Speichern fehlgeschlagen: ' + errors)
            return
        self.refresh_existing()
        self.message(f"Gespeichert: {taxon['de'] or taxon['scientific']} → {fid}")
        self.query.clear()

    def export_csv(self):
        layer = self.obs_layer()
        if not layer:
            self.message('Layer "artnachweise" fehlt.')
            return
        filename, _ = QFileDialog.getSaveFileName(self, 'Artnachweise exportieren',
                                                   'gokart_artnachweise.csv', 'CSV (*.csv)')
        if not filename:
            return
        # Lesbare Liste ohne interne Felder (fid, taxon_id, original_eingabe)
        flaechen = self.flaechen_info()
        fk = self.obs_fk()
        try:
            with open(filename, 'w', newline='', encoding='utf-8-sig') as file:
                writer = csv.writer(file, delimiter=';')
                writer.writerow(['Flächen-ID', 'Fläche', 'Wissenschaftlicher Name', 'Deutscher Name',
                                 'Erfasst am', 'Bemerkung'])
                zeilen = []
                for f in layer.getFeatures():
                    fid = val(f, fk)
                    zeilen.append([fid, flaechen.get(fid, ('', None))[0], val(f, 'wissenschaftlicher_name'),
                                   val(f, 'deutscher_name'), val(f, 'erfasst_am').replace('T', ' '),
                                   val(f, 'bemerkung')])
                zeilen.sort(key=lambda z: (z[0], z[2].lower()))
                writer.writerows(zeilen)
            self.message('CSV exportiert: ' + filename)
        except Exception as e:
            self.message('Export fehlgeschlagen: ' + str(e))

    def flaechen_info(self):
        """{Flächen-Schlüssel: (Bezeichnung, Größe m²)} über die eingerichtete Verknüpfung."""
        flaechen = {}
        fl = self.polygon_layer()
        if fl is not None:
            key = self.key_field(fl)
            label = self.label_field(fl)
            names = fl.fields().names()
            m2 = next((n for n in ('flaeche_m2', 'Flaeche_m2', 'flaeche', 'Flaeche') if n in names), None)
            for f in fl.getFeatures():
                k = self.area_key(fl, f) if not key else (None if is_empty(f[key]) else f[key])
                if k is None:
                    continue
                groesse = (f[m2] if m2 and not is_empty(f[m2])
                           else None if fl.crs().isGeographic() else f.geometry().area())
                flaechen[str(k)] = (val(f, label) if label else '', groesse)
        return flaechen

    def export_artenliste(self):
        """Artenliste je Fläche (HTML + CSV) über alle Flächen – Logik in artenliste.py."""
        from .artenliste import csv_schreiben, html_schreiben
        layer = self.obs_layer()
        if not layer:
            self.message('Layer "artnachweise" fehlt.')
            return
        filename, _ = QFileDialog.getSaveFileName(self, 'Artenliste je Fläche speichern',
                                                   'gokart_artenliste.html', 'HTML (*.html)')
        if not filename:
            return
        flaechen = self.flaechen_info()
        taxa = {}
        tx = self.layer('taxon')
        if tx is not None:
            for f in tx.getFeatures():
                taxa[val(f, 'taxon_id')] = (val(f, 'autor_name'), val(f, 'rang'))
        fk = self.obs_fk()
        fotos_je_flaeche = {}
        fl = self.foto_layer()
        if fl is not None:
            for f in fl.getFeatures():
                fotos_je_flaeche.setdefault(val(f, 'flaeche_id'), []).append({
                    'datei': val(f, 'datei'), 'kommentar': val(f, 'kommentar'), 'am': val(f, 'aufgenommen_am'),
                    'src': self.vorschau_uri(self.foto_pfad(val(f, 'datei')))})
        nachweise = []
        for f in layer.getFeatures():
            fid = val(f, fk)
            name, groesse = flaechen.get(fid, ('', None))
            autor, rang = taxa.get(val(f, 'taxon_id'), ('', ''))
            nachweise.append({'flaeche_id': fid, 'flaeche_name': name, 'flaeche_m2': groesse,
                              'taxon_id': val(f, 'taxon_id'), 'wiss': val(f, 'wissenschaftlicher_name'),
                              'autor': autor, 'deutsch': val(f, 'deutscher_name'), 'rang': rang,
                              'eingabe': val(f, 'original_eingabe'), 'erfasst_am': val(f, 'erfasst_am'),
                              'bemerkung': val(f, 'bemerkung')})
        try:
            ziel = Path(filename).with_suffix('.html')
            projekt = QgsProject.instance().title() or Path(QgsProject.instance().fileName()).stem
            n_fl, n_tx = html_schreiben(ziel, nachweise, 'Artenliste je Fläche', projekt,
                                        fotos_je_flaeche=fotos_je_flaeche, flaechen_info=flaechen)
            csv_schreiben(ziel.with_suffix('.csv'), nachweise)
            self.message(f'Artenliste: {n_fl} Flächen, {n_tx} Taxa → {ziel} (+ .csv)')
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(ziel)))
        except Exception as e:
            self.message('Artenliste fehlgeschlagen: ' + str(e))

    def record(self, *_args, ziel='suche'):
        """Vosk-Spracheingabe; ziel='suche' (Pflanzenname), 'kommentar' (Fotokommentar) oder 'biotop'."""
        self.voice_ziel = ziel
        if self.voice and self.voice.isRunning():
            self.message('Aufnahme läuft bereits.')
            return
        model = self.settings.value('GoKart/vosk_model', '', type=str)
        if not model or not Path(model).is_dir():
            path = QFileDialog.getExistingDirectory(self, 'Vosk-Modellordner auswählen')
            if not path:
                return
            self.settings.setValue('GoKart/vosk_model', path)
            model = path
        self.mic.setEnabled(False)
        self.foto_mic.setEnabled(False)
        self.biotop_mic.setEnabled(False)
        self.message('Mikrofon wird vorbereitet … noch nicht sprechen.')
        self.voice = VoiceThread(model, self)
        self.voice.status.connect(self.message)
        self.voice.ready.connect(lambda: self.message('● JETZT sprechen (max. 8 Sekunden).'))
        self.voice.result.connect(lambda text, z=ziel: self.voice_result(text, z))
        self.voice.failure.connect(lambda err: self.message('Spracherkennung: ' + err))
        self.voice.finished.connect(lambda: (self.mic.setEnabled(True), self.foto_mic.setEnabled(True),
                                             self.biotop_mic.setEnabled(bool(self.biotop_typen))))
        self.voice.start()

    def voice_result(self, text, ziel='suche'):
        if ziel == 'biotop':
            self.biotop_query.setText(text)
            self.message(('Erkannt: ' + text + ' – Biotoptyp bestätigen.') if text
                         else 'Nichts erkannt – nach „JETZT sprechen“ deutlich einsprechen.')
            return
        if ziel == 'kommentar':
            if text:
                alt = self.foto_kommentar.text().strip()
                self.foto_kommentar.setText((alt + ' ' if alt else '') + text)
                self.message('Erkannt: ' + text + ' – prüfen und „Kommentar speichern“.')
            else:
                self.message('Nichts erkannt – nach „JETZT sprechen“ deutlich einsprechen.')
            return
        self.query.setText(text)
        if text:
            self.message('Erkannt: ' + text + ' – Art bestätigen und speichern.')
        else:
            self.message('Nichts erkannt – nach „JETZT sprechen“ deutlich einsprechen.')


class GoKartPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self.dock = None

    def initGui(self):
        self.action = QAction('GoKart Desktop', self.iface.mainWindow())
        self.action.triggered.connect(self.show)
        self.iface.addPluginToMenu('GoKart', self.action)
        self.iface.addToolBarIcon(self.action)
        self.setup_action = QAction('GoKart: Projekt einrichten…', self.iface.mainWindow())
        self.setup_action.triggered.connect(self.setup)
        self.iface.addPluginToMenu('GoKart', self.setup_action)

    def setup(self):
        self.show()
        self.dock.open_setup()

    def show(self):
        if self.dock is None:
            self.dock = GoKartDock(self.iface)
            self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dock)
        self.dock.show()
        self.dock.raise_()

    def unload(self):
        if self.dock is not None:
            try:
                self.iface.currentLayerChanged.disconnect(self.dock.on_layer_changed)
                QgsProject.instance().layersAdded.disconnect(self.dock.on_project_layers_changed)
                QgsProject.instance().layersRemoved.disconnect(self.dock.on_project_layers_changed)
                QgsProject.instance().readProject.disconnect(self.dock.on_project_layers_changed)
            except (TypeError, RuntimeError):
                pass
        if self.action:
            self.iface.removePluginMenu('GoKart', self.action)
            self.iface.removeToolBarIcon(self.action)
        if getattr(self, 'setup_action', None):
            self.iface.removePluginMenu('GoKart', self.setup_action)
        if self.dock:
            self.iface.removeDockWidget(self.dock)
            self.dock.deleteLater()
