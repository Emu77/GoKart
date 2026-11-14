"""GoKart Desktop – Offline-Spracherkennung (Vosk) per Knopfdruck einrichten.

1. Python-Pakete vosk + sounddevice: pip install --target <QGIS-Profil>/gokart/python
   (kein Administrator nötig, keine Änderung an der QGIS-Installation; fehlt pip, wird pip.pyz geladen)
2. Deutsches Sprachmodell (vosk-model-small-de-0.15, ca. 45 MB) herunterladen und entpacken
"""
import importlib
import os
import shutil
import site
import subprocess
import sys
import zipfile
from pathlib import Path

from qgis.PyQt.QtCore import QSettings, QThread, QUrl, Qt, pyqtSignal
from qgis.PyQt.QtWidgets import (QApplication, QDialog, QDialogButtonBox, QFileDialog, QGridLayout, QLabel,
                                 QPlainTextEdit, QProgressBar, QPushButton, QVBoxLayout)

from . import helfer as H

MODELL_NAME = 'vosk-model-small-de-0.15'
MODELL_URL = f'https://alphacephei.com/vosk/models/{MODELL_NAME}.zip'
PIP_PYZ_URL = 'https://bootstrap.pypa.io/pip/pip.pyz'
PAKETE = ('vosk', 'sounddevice')
EINSTELLUNG_MODELL = 'GoKart/vosk_model'


def pakete_einbinden():
    """Paketordner (und das ältere ~/gokart-venv unter Linux) in sys.path aufnehmen."""
    try:
        ordner = H.python_pakete_ordner()
    except Exception:
        return
    if ordner.is_dir() and str(ordner) not in sys.path:
        site.addsitedir(str(ordner))
    importlib.invalidate_caches()


def modell_gueltig(pfad):
    p = Path(pfad or '')
    return p.is_dir() and (p / 'am').is_dir() and (p / 'conf').is_dir()


def modell_pfad():
    pfad = QSettings().value(EINSTELLUNG_MODELL, '', type=str)
    return pfad if modell_gueltig(pfad) else ''


def status():
    """{'vosk': (ok, Text), 'sounddevice': (ok, Text), 'modell': (ok, Text)}"""
    pakete_einbinden()
    erg = {}
    for name in PAKETE:
        try:
            importlib.import_module(name)
            erg[name] = (True, 'installiert')
        except ImportError:
            erg[name] = (False, 'fehlt')
        except OSError as e:                      # sounddevice ohne PortAudio-Bibliothek
            hinweis = ' – Linux: sudo apt install libportaudio2' if sys.platform.startswith('linux') else ''
            erg[name] = (False, f'{e}{hinweis}')
        except Exception as e:
            erg[name] = (False, str(e))
    m = modell_pfad()
    erg['modell'] = (bool(m), m or 'kein Sprachmodell gewählt')
    return erg


def bereit():
    s = status()
    return all(ok for ok, _ in s.values())


def python_finden():
    """Python-Programm mit derselben Version wie QGIS (für pip). None, wenn keins passt."""
    v = f'{sys.version_info.major}.{sys.version_info.minor}'
    kandidaten = []
    if Path(sys.executable).name.lower().startswith('python'):
        kandidaten.append(sys.executable)
    for basis in {sys.prefix, sys.exec_prefix, sys.base_prefix}:
        kandidaten += [str(Path(basis) / 'python.exe'), str(Path(basis) / 'python3.exe'),
                       str(Path(basis) / 'bin' / f'python{v}'), str(Path(basis) / 'bin' / 'python3')]
    kandidaten += [shutil.which(n) or '' for n in (f'python{v}', 'python3', 'python')]
    gesehen = set()
    for k in kandidaten:
        if not k or k in gesehen or not Path(k).is_file():
            continue
        gesehen.add(k)
        try:
            aus = subprocess.run([k, '-c', 'import sys; print("%d.%d" % sys.version_info[:2])'],
                                 capture_output=True, text=True, timeout=20, **_ohne_fenster())
        except Exception:
            continue
        if aus.returncode == 0 and aus.stdout.strip() == v:
            return k
    return None


def _ohne_fenster():
    if sys.platform == 'win32':
        return {'creationflags': 0x08000000}      # CREATE_NO_WINDOW
    return {}


def _umgebung():
    env = dict(os.environ)
    for k in ('PYTHONPATH', 'PYTHONHOME'):
        if sys.platform != 'win32':               # unter Windows (OSGeo4W) wird PYTHONHOME gebraucht
            env.pop(k, None)
    env['PIP_DISABLE_PIP_VERSION_CHECK'] = '1'
    return env


class PipThread(QThread):
    zeile = pyqtSignal(str)
    fertig = pyqtSignal(bool)

    def __init__(self, befehl, parent=None):
        super().__init__(parent)
        self.befehl = befehl

    def run(self):
        try:
            self.zeile.emit('$ ' + ' '.join(self.befehl))
            proc = subprocess.Popen(self.befehl, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                    env=_umgebung(), **_ohne_fenster())
            for z in proc.stdout:
                self.zeile.emit(z.rstrip())
            self.fertig.emit(proc.wait() == 0)
        except Exception as e:
            self.zeile.emit(f'Fehler: {e}')
            self.fertig.emit(False)


class VoskDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('GoKart – Spracherkennung einrichten')
        self.resize(640, 460)
        self.thread = None
        self.downloader = None
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel('Offline-Spracherkennung mit Vosk. Beides wird nur einmal gebraucht und bleibt\n'
                             'bei Plugin-Updates erhalten. Ohne Spracherkennung funktioniert GoKart Desktop trotzdem.'))
        g = QGridLayout()
        self.p_status = QLabel()
        self.m_status = QLabel()
        for l in (self.p_status, self.m_status):
            l.setWordWrap(True)
            l.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.p_btn = QPushButton('Pakete installieren')
        self.m_btn = QPushButton('Modell herunterladen (≈ 45 MB)')
        self.m_wahl = QPushButton('Vorhandenes Modell wählen…')
        g.addWidget(QLabel('<b>1. Python-Pakete</b>'), 0, 0)
        g.addWidget(self.p_status, 0, 1)
        g.addWidget(self.p_btn, 0, 2)
        g.addWidget(QLabel('<b>2. Sprachmodell</b>'), 1, 0)
        g.addWidget(self.m_status, 1, 1)
        g.addWidget(self.m_btn, 1, 2)
        g.addWidget(self.m_wahl, 2, 2)
        g.setColumnStretch(1, 1)
        lay.addLayout(g)
        self.fortschritt = QProgressBar()
        self.fortschritt.setVisible(False)
        lay.addWidget(self.fortschritt)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        lay.addWidget(self.log)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.p_btn.clicked.connect(self.pakete_installieren)
        self.m_btn.clicked.connect(self.modell_laden)
        self.m_wahl.clicked.connect(self.modell_waehlen)
        self.aktualisieren()

    def schreiben(self, text):
        self.log.appendPlainText(text)

    def aktualisieren(self):
        s = status()
        p_ok = s['vosk'][0] and s['sounddevice'][0]
        self.p_status.setText(('✓ ' if p_ok else '✗ ') + f"vosk: {s['vosk'][1]}, sounddevice: {s['sounddevice'][1]}")
        self.m_status.setText(('✓ ' if s['modell'][0] else '✗ ') + s['modell'][1])
        self.p_btn.setText('Pakete neu installieren' if p_ok else 'Pakete installieren')
        return s

    def beschaeftigt(self, ja):
        for b in (self.p_btn, self.m_btn, self.m_wahl):
            b.setEnabled(not ja)

    # ------------------------------------------------------------------ Pakete
    def pakete_installieren(self):
        py = python_finden()
        if py is None:
            v = f'{sys.version_info.major}.{sys.version_info.minor}'
            self.schreiben(f'Kein Python {v} gefunden, das zu QGIS passt.\n'
                           'Windows: OSGeo4W-Shell öffnen und eingeben:  python -m pip install vosk sounddevice\n'
                           f'Linux: sudo apt install python{v}  (bzw. python3)')
            return
        ziel = H.python_pakete_ordner()
        ziel.mkdir(parents=True, exist_ok=True)
        hat_pip = subprocess.run([py, '-m', 'pip', '--version'], capture_output=True, env=_umgebung(),
                                 **_ohne_fenster()).returncode == 0
        if hat_pip:
            self._pip_starten([py, '-m', 'pip'])
            return
        pyz = H.daten_ordner() / 'pip.pyz'
        if pyz.is_file():
            self._pip_starten([py, str(pyz)])
            return
        self.schreiben('pip fehlt – lade pip.pyz …')
        self._laden(PIP_PYZ_URL, pyz, lambda: self._pip_starten([py, str(pyz)]))

    def _pip_starten(self, pip):
        befehl = pip + ['install', '--upgrade', '--no-warn-script-location', '--target',
                        str(H.python_pakete_ordner())] + list(PAKETE)
        self.beschaeftigt(True)
        self.thread = PipThread(befehl, self)
        self.thread.zeile.connect(self.schreiben)
        self.thread.fertig.connect(self._pip_fertig)
        self.thread.start()

    def _pip_fertig(self, ok):
        self.beschaeftigt(False)
        s = self.aktualisieren()
        if ok and s['vosk'][0] and s['sounddevice'][0]:
            self.schreiben('✓ Pakete installiert.')
        elif ok:
            self.schreiben('Installiert, aber noch nicht ladbar – siehe Hinweis oben; ggf. QGIS neu starten.')
        else:
            self.schreiben('✗ Installation fehlgeschlagen (Ausgabe oben). Alternative: OSGeo4W-Shell bzw. Terminal:\n'
                           '   python -m pip install vosk sounddevice')

    # ------------------------------------------------------------------ Modell
    def modell_waehlen(self):
        p = QFileDialog.getExistingDirectory(self, 'Vosk-Modellordner wählen (enthält am/ und conf/)')
        if not p:
            return
        if not modell_gueltig(p):
            self.schreiben(f'{p} ist kein Vosk-Modell (Unterordner am/ und conf/ fehlen).')
            return
        QSettings().setValue(EINSTELLUNG_MODELL, p)
        self.aktualisieren()

    def modell_laden(self):
        ordner = H.daten_ordner() / 'vosk'
        ordner.mkdir(parents=True, exist_ok=True)
        if modell_gueltig(ordner / MODELL_NAME):
            QSettings().setValue(EINSTELLUNG_MODELL, str(ordner / MODELL_NAME))
            self.schreiben('Modell war schon heruntergeladen.')
            self.aktualisieren()
            return
        datei = ordner / (MODELL_NAME + '.zip')
        self._laden(MODELL_URL, datei, lambda: self._entpacken(datei, ordner))

    def _entpacken(self, datei, ordner):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            with zipfile.ZipFile(datei) as z:
                z.extractall(ordner)
            datei.unlink()
        except Exception as e:
            self.schreiben(f'Entpacken fehlgeschlagen: {e}')
            return
        finally:
            QApplication.restoreOverrideCursor()
        ziel = ordner / MODELL_NAME
        if modell_gueltig(ziel):
            QSettings().setValue(EINSTELLUNG_MODELL, str(ziel))
            self.schreiben(f'✓ Sprachmodell bereit: {ziel}')
        else:
            self.schreiben(f'Entpackt, aber kein Modell in {ziel} gefunden.')
        self.aktualisieren()

    def _laden(self, url, datei, danach):
        """Download über QGIS (berücksichtigt Proxy-Einstellungen)."""
        from qgis.core import QgsFileDownloader
        self.beschaeftigt(True)
        self.fortschritt.setVisible(True)
        self.fortschritt.setRange(0, 0)
        self.schreiben(f'Lade {url} …')
        tmp = Path(str(datei) + '.part')
        self.downloader = QgsFileDownloader(QUrl(url), str(tmp), '', True)

        def fortschritt(empfangen, gesamt):
            if gesamt > 0:
                self.fortschritt.setRange(0, 100)
                self.fortschritt.setValue(int(empfangen * 100 / gesamt))

        def fehler(meldungen):
            self.schreiben('Download fehlgeschlagen: ' + '; '.join(meldungen) +
                           f'\nAlternative: {url} im Browser laden und „Vorhandenes Modell wählen…“.')

        def fertig():
            tmp.replace(datei)
            self.schreiben('Download fertig.')
            danach()

        def ende():
            self.beschaeftigt(self.thread is not None and self.thread.isRunning())
            self.fortschritt.setVisible(False)

        self.downloader.downloadProgress.connect(fortschritt)
        self.downloader.downloadError.connect(fehler)
        self.downloader.downloadCompleted.connect(lambda *_a: fertig())
        self.downloader.downloadExited.connect(ende)
        self.downloader.startDownload()
