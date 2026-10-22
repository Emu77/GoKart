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
    QVBoxLayout, QWidget)
from qgis.core import (QgsCoordinateTransform, QgsFeature, QgsGeometry,
    QgsPointXY, QgsProject, QgsMapLayerType)


def norm(s):
    s = unicodedata.normalize('NFKD', str(s or '').casefold())
    return ''.join(c for c in s if not unicodedata.combining(c)).strip()


def val(f, field):
    try:
        x = f[field]
        return '' if x is None or str(x) == 'NULL' else str(x)
    except (KeyError, IndexError):
        return ''


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
        row.addWidget(self.reload_btn)
        row.addWidget(self.pick_btn)
        layout.addLayout(row)
        layout.addWidget(QLabel('Pflanzenart suchen / einsprechen'))
        row = QHBoxLayout()
        self.query = QLineEdit()
        self.query.setPlaceholderText('z. B. Grünlilie')
        self.mic = QPushButton('🎤 Sprechen')
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
        self.reload()

    def layer(self, name):
        layers = QgsProject.instance().mapLayersByName(name)
        return layers[0] if layers else None

    def message(self, text):
        self.status.setText(text)
        self.iface.messageBar().pushInfo('GoKart', text)

    def polygon_layer(self):
        layer = self.iface.activeLayer()
        if (layer is not None and layer.isValid()
                and layer.type() == QgsMapLayerType.VectorLayer
                and layer.geometryType() == 2):
            return layer
        return None

    def on_layer_changed(self, layer):
        if self.polygon_layer() is not None:
            self.reload()

    def on_project_layers_changed(self, *args):
        self.reload()

    def area_key(self, layer, feature):
        # Persistenter Quellbezug + fid; keine Änderung am Polygon erforderlich.
        # Nur auf stabilen Dateiquellen sinnvoll (GPKG, SHP etc.).
        source = layer.source().split('|', 1)[0]
        digest = hashlib.sha1((source + '|' + layer.name()).encode('utf-8')).hexdigest()[:8]
        return 'G-' + digest + '-' + format(feature.id(), 'x')

    def reload(self):
        fl = self.polygon_layer()
        tx = self.layer('taxon')
        old = self.area.currentData()
        self.area.blockSignals(True)
        self.area.clear()
        self.area_lookup = {}
        self.area_source = fl.id() if fl else None
        if fl:
            names = fl.fields().names()
            label_field = next((n for n in ('Raum', 'raum', 'name', 'Name', 'bezeichnung', 'Bezeichnung')
                                if n in names), None)
            for f in fl.getFeatures():
                key = self.area_key(fl, f)
                title = val(f, label_field).strip() if label_field else ''
                if not title and not self.show_unnamed.isChecked():
                    continue
                title = title or 'Fläche'
                self.area.addItem(f'{title} (ID {f.id()})', key)
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
                german = val(f, 'anzeige_name') or val(f, 'deutscher_name')
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
        self.message(f'{self.area.count()} Flächen aus aktivem Polygonlayer, {len(self.taxa)} Taxa geladen.')

    def area_id(self):
        return self.area.currentData() or ''

    def pick_selected(self):
        fl = self.polygon_layer()
        if fl is None:
            self.message('Bitte zuerst einen Polygonlayer aktivieren.')
            return
        selected = fl.selectedFeatures()
        if not selected:
            self.message('Im aktiven Polygonlayer zuerst eine Fläche auswählen.')
            return
        key = self.area_key(fl, selected[0])
        i = self.area.findData(key)
        if i < 0:
            # Auch unbenannte Polygone aus der Karte auswählen können.
            title_field = next((n for n in ('Raum', 'raum', 'name', 'Name', 'bezeichnung', 'Bezeichnung')
                                if n in fl.fields().names()), None)
            title = val(selected[0], title_field).strip() if title_field else ''
            self.area.addItem(f'{title or "Fläche"} (ID {selected[0].id()})', key)
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
        layer = self.layer('artnachweise')
        fid = self.area_id()
        if not layer or not fid:
            return
        count = 0
        for f in layer.getFeatures():
            if val(f, 'flaeche_id') == fid:
                self.existing.addItem(val(f, 'deutscher_name') or val(f, 'wissenschaftlicher_name'))
                count += 1
        self.existing.setToolTip(f'{count} Artnachweise auf {fid}')

    def save(self):
        layer = self.layer('artnachweise')
        fid = self.area_id()
        idx = self.results.currentRow()
        if not layer or not fid or idx < 0 or idx >= len(self.matches):
            self.message('Fläche und Art auswählen; Layer "artnachweise" muss geladen sein.')
            return
        taxon = self.matches[idx]
        for f in layer.getFeatures():
            if val(f, 'flaeche_id') == fid and val(f, 'taxon_id') == taxon['id']:
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
            'flaeche_id': fid, 'taxon_id': int(taxon['id']) if taxon['id'].isdigit() else taxon['id'],
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
        layer = self.layer('artnachweise')
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
        self.message('🎤 Bitte Art einsprechen (max. 8 Sekunden).')
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
            except (TypeError, RuntimeError):
                pass
        if self.action:
            self.iface.removePluginMenu('GoKart', self.action)
            self.iface.removeToolBarIcon(self.action)
        if self.dock:
            self.iface.removeDockWidget(self.dock)
            self.dock.deleteLater()
