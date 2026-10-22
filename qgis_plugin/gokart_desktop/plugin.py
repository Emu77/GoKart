"""GoKart Desktop: QGIS 3.x, Linux/Windows, optional Vosk.

Alle Schreiboperationen gehen an den geladenen artnachweise-Layer.
Keine Änderung am Quellprojekt oder den Layerdefinitionen.
"""

# GoKart: Python-Umgebung einbinden
import site
site.addsitedir('/home/emu/gokart-venv/lib/python3.12/site-packages')

import csv
import hashlib
import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path

from qgis.PyQt.QtCore import Qt, QThread, pyqtSignal, QSettings, QTimer
from qgis.PyQt.QtWidgets import (QAction, QComboBox, QDockWidget, QFileDialog,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QMessageBox, QPushButton, QCheckBox,
    QVBoxLayout, QWidget, QDialog, QDialogButtonBox, QFormLayout)
from qgis.core import (QgsCoordinateTransform, QgsFeature, QgsGeometry,
    QgsPointXY, QgsProject, QgsMapLayerType, QgsExpression, QgsFeatureRequest,
    QgsRelation, QgsExpressionContextUtils as ECU)
from qgis.gui import QgsMapLayerComboBox, QgsFieldComboBox

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

        form.addRow(QLabel('<b>Flächen</b>'))
        form.addRow('Layer', self.area_layer)
        form.addRow('Schlüsselfeld', self.area_key)
        form.addRow('Anzeigefeld', self.area_label)
        form.addRow(QLabel('<b>Artnachweise</b>'))
        form.addRow('Layer', self.obs_layer)
        form.addRow('Verweis auf Fläche', self.obs_fk)
        form.addRow(self.make_relation)
        form.addRow(self.info)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.apply)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

        self.area_layer.layerChanged.connect(self.on_area_layer)
        self.obs_layer.layerChanged.connect(lambda l: self.obs_fk.setLayer(l))
        self.area_key.fieldChanged.connect(self.check)
        self.obs_fk.fieldChanged.connect(self.check)
        self.prefill()

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
        if self.make_relation.isChecked() and not self.write_relation(fl, key, nl, fk):
            return
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


class VoiceThread(QThread):
    result = pyqtSignal(str)
    failure = pyqtSignal(str)

    def __init__(self, model_path, parent=None):
        super().__init__(parent)
        self.model_path = model_path

    def run(self):
        try:
            import sounddevice as sd
            from vosk import Model, KaldiRecognizer
            import queue
            q = queue.Queue()
            model = Model(self.model_path)
            rate = 16000
            recognizer = KaldiRecognizer(model, rate)
            def callback(indata, frames, time_info, status):
                q.put(bytes(indata))
            # Maximal 8 Sekunden; Aufnahme läuft bis zur ersten längeren Pause
            # Logitech-Webcam anhand ihrer USB-Kennung auswählen
            devices = sd.query_devices()
            webcam = next(
                (i for i, d in enumerate(devices)
                 if '0x46d:0x825' in d['name']
                 and d['max_input_channels'] > 0),
                None
            )
            if webcam is None:
                raise RuntimeError('Webcam-Mikrofon nicht gefunden.')

            with sd.RawInputStream(samplerate=rate, blocksize=8000, dtype='int16',
                                   channels=1, device=webcam, callback=callback):
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
        self.export_btn = QPushButton('Export (CSV)')
        layout.addWidget(self.export_btn)
        self.status = QLabel('QGIS-Projekt mit gokart.gpkg öffnen.')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.setWidget(body)
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
        self.export_btn.clicked.connect(self.export_csv)
        self.mic.clicked.connect(self.record)
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
            self.existing.addItem(val(f, 'deutscher_name') or val(f, 'wissenschaftlicher_name'))
            count += 1
        self.existing.setToolTip(f'{count} Artnachweise auf {fid}')

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
        names = layer.fields().names()
        try:
            with open(filename, 'w', newline='', encoding='utf-8-sig') as file:
                writer = csv.writer(file, delimiter=';')
                writer.writerow(names)
                for f in layer.getFeatures():
                    writer.writerow([val(f, n) for n in names])
            self.message('CSV exportiert: ' + filename)
        except Exception as e:
            self.message('Export fehlgeschlagen: ' + str(e))

    def record(self):
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
        self.message('● Bitte Art einsprechen (max. 8 Sekunden).')
        self.voice = VoiceThread(model, self)
        self.voice.result.connect(self.voice_result)
        self.voice.failure.connect(lambda err: self.message('Spracherkennung: ' + err))
        self.voice.finished.connect(lambda: self.mic.setEnabled(True))
        self.voice.start()

    def voice_result(self, text):
        self.query.setText(text)
        self.message('Erkannt: ' + (text or '(nichts)') + ' – Art bestätigen und speichern.')


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
