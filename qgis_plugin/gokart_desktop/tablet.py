"""GoKart Desktop – Austausch mit dem Tablet: Projekt für QField verpacken, Tablet-Stand einspielen."""
import sqlite3
from pathlib import Path

from qgis.PyQt.QtCore import Qt, QUrl
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import QApplication, QDialogButtonBox, QFileDialog, QMessageBox
from qgis.core import QgsProject

from . import helfer as H
from . import paket as PK
from .assistent import ausgabe_zeigen


def _ordner_oeffnen_frage(parent, titel, text, pfad):
    box = QMessageBox(QMessageBox.Information, titel, text, QMessageBox.Ok, parent)
    oeffnen = box.addButton('Ordner öffnen', QMessageBox.ActionRole)
    box.exec_()
    if box.clickedButton() is oeffnen:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(pfad).parent)))


def _offene_bearbeitung(projekt):
    return [l.name() for l in projekt.mapLayers().values()
            if hasattr(l, 'isModified') and l.isEditable() and l.isModified()]


def _projekt_bereit(parent):
    """Projekt muss gespeichert und ohne offene Bearbeitung sein. Gibt den Pfad der Projektdatei zurück."""
    p = QgsProject.instance()
    if not p.fileName():
        QMessageBox.information(parent, 'GoKart', 'Bitte zuerst ein GoKart-Projekt öffnen oder anlegen '
                                                  '(„Neues Projekt…“) und speichern.')
        return None
    offen = _offene_bearbeitung(p)
    if offen:
        QMessageBox.warning(parent, 'GoKart', 'Ungespeicherte Bearbeitung in: ' + ', '.join(offen) +
                            '\nBitte erst speichern oder verwerfen (Bearbeitungsmodus beenden).')
        return None
    return Path(p.fileName())


def _relative_pfade(p):
    """QField braucht relative Pfade. True, wenn geändert."""
    try:
        from qgis.core import Qgis
        if p.filePathStorage() != Qgis.FilePathType.Relative:
            p.setFilePathStorage(Qgis.FilePathType.Relative)
            return True
        return False
    except AttributeError:   # QGIS < 3.22
        if p.readBoolEntry('Paths', '/Absolute', False)[0]:
            p.writeEntry('Paths', '/Absolute', False)
            return True
        return False


def verpacken(iface, parent):
    pfad = _projekt_bereit(parent)
    if pfad is None:
        return
    p = QgsProject.instance()
    home = pfad.parent
    dateien, aussen = PK.dateien_sammeln(home, pfad, PK.layer_quellen(p))
    if aussen:
        liste = '\n'.join(f'• {n}: {q}' for n, q in aussen[:12]) + ('\n…' if len(aussen) > 12 else '')
        if QMessageBox.question(
                parent, 'GoKart – Für QField verpacken',
                'Diese Layer liegen außerhalb des Projektordners und fehlen auf dem Tablet:\n\n' + liste +
                '\n\nTipp: Neue Projekte mit „Neues Projekt…“ anlegen – dann liegt alles im Projektordner.'
                '\n\nTrotzdem verpacken?', QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
    if _relative_pfade(p) or p.isDirty():
        if not p.write():
            QMessageBox.warning(parent, 'GoKart', 'Projekt konnte nicht gespeichert werden.')
            return
    ziel, _ = QFileDialog.getSaveFileName(parent, 'ZIP fürs Tablet speichern', str(PK.zip_name(home)), 'ZIP (*.zip)')
    if not ziel:
        return
    ziel = Path(ziel).with_suffix('.zip')
    QApplication.setOverrideCursor(Qt.WaitCursor)
    try:
        ok, erg, text = H.ausfuehren(lambda: PK.zip_schreiben(home, dateien, ziel, H.qfield_plugin_dateien(pfad)))
    finally:
        QApplication.restoreOverrideCursor()
    if not ok:
        ausgabe_zeigen(parent, 'GoKart – Verpacken fehlgeschlagen', text)
        return
    n, mb = erg
    hinweis = (f'\n\n⚠ Über {PK.WARNUNG_MB} MB – für Mail/Messenger evtl. zu groß (USB-Kabel oder Cloud nutzen).'
               if mb > PK.WARNUNG_MB else '')
    _ordner_oeffnen_frage(
        parent, 'GoKart – Für QField verpackt',
        f'{ziel.name}  ({n} Dateien, {mb:.1f} MB){hinweis}\n\n'
        'Aufs Tablet kopieren (USB, Mail, Messenger, Cloud) und in QField öffnen:\n'
        '„Projekt aus ZIP importieren“ → ZIP wählen → Projekt öffnen → dem GoKart-Plugin vertrauen.', ziel)


def _checkpoint(gpkgs):
    """Offene Änderungen aus -wal-Dateien in die GeoPackage schreiben (sonst bricht der Abgleich ab)."""
    for g in gpkgs:
        try:
            con = sqlite3.connect(str(g), timeout=5)
            con.execute('PRAGMA wal_checkpoint(TRUNCATE)')
            con.close()
        except sqlite3.Error:
            pass


def einspielen(iface, parent):
    pfad = _projekt_bereit(parent)
    if pfad is None:
        return
    p = QgsProject.instance()
    box = QMessageBox(QMessageBox.Question, 'GoKart – Tablet-Stand einspielen',
                      'Was kommt vom Tablet?\n\nIn QField: Projektordner teilen/senden (als ZIP) oder per USB '
                      'kopieren. Erfassungen werden in beide Richtungen ergänzt; zuerst gibt es eine Vorschau.',
                      QMessageBox.Cancel, parent)
    zip_btn = box.addButton('ZIP-Datei…', QMessageBox.AcceptRole)
    ordner_btn = box.addButton('Ordner…', QMessageBox.AcceptRole)
    box.exec_()
    if box.clickedButton() is zip_btn:
        tablet, _ = QFileDialog.getOpenFileName(parent, 'Tablet-Export (ZIP) wählen', str(pfad.parent.parent),
                                                'ZIP (*.zip)')
    elif box.clickedButton() is ordner_btn:
        tablet = QFileDialog.getExistingDirectory(parent, 'Tablet-Projektordner wählen', str(pfad.parent.parent))
    else:
        return
    if not tablet:
        return
    if Path(tablet).resolve() == pfad.parent.resolve():
        QMessageBox.warning(parent, 'GoKart', 'Das ist der Ordner des PC-Projekts selbst – bitte den Tablet-Stand wählen.')
        return
    if p.isDirty() and not p.write():
        QMessageBox.warning(parent, 'GoKart', 'Projekt konnte nicht gespeichert werden.')
        return

    gpkgs = {q for _n, q in PK.layer_quellen(p) if q.suffix.lower() == '.gpkg'}
    # Projekt für den Abgleich schließen (abgleich.py schreibt direkt in GeoPackage und Projektdatei)
    p.clear()
    QApplication.processEvents()
    _checkpoint(gpkgs)
    try:
        A = H.werkzeug('abgleich')
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            ok, _z, text = H.ausfuehren(A.main, [str(pfad), str(tablet)])
        finally:
            QApplication.restoreOverrideCursor()
        if not ok:
            ausgabe_zeigen(parent, 'GoKart – Abgleich nicht möglich', text)
            return
        if 'Beide Stände sind gleich' in text:
            QMessageBox.information(parent, 'GoKart', 'PC und Tablet sind auf demselben Stand – nichts zu tun.')
            return
        text = text.replace('Nur Vorschau. Übernehmen mit --ausfuehren', '').rstrip()
        if not ausgabe_zeigen(parent, 'GoKart – Vorschau: das würde übernommen',
                              text + '\n\n„Ja“ übernimmt: PC-Projekt wird aktualisiert (Sicherung *.bak), '
                                     'fürs Tablet entsteht ein neues ZIP.',
                              QDialogButtonBox.Yes | QDialogButtonBox.No):
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            ok, ziel, text = H.ausfuehren(A.main, [str(pfad), str(tablet), '--ausfuehren'])
        finally:
            QApplication.restoreOverrideCursor()
        if not ok or ziel is None:
            ausgabe_zeigen(parent, 'GoKart – Abgleich fehlgeschlagen', text)
            return
        _ordner_oeffnen_frage(parent, 'GoKart – Abgleich fertig',
                              text.split('\n✓ Fertig.')[-1].strip() +
                              '\n\nDas neue ZIP in QField wieder über „Projekt aus ZIP importieren“ öffnen '
                              'und den alten Stand auf dem Tablet danach löschen, damit nicht versehentlich '
                              'darin weiter erfasst wird.', ziel)
    finally:
        iface.addProject(str(pfad))
