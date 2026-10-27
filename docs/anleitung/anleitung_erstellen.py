#!/usr/bin/env python3
"""GoKart – erzeugt docs/GoKart_QField_Anleitung.pdf (ReportLab).

Aufruf (aus dem Repo-Hauptordner):
    pip install reportlab          # bzw. sudo apt install python3-reportlab
    python3 docs/anleitung/anleitung_erstellen.py

Inhalt steht direkt in diesem Skript (Abschnitte als Funktionen). Nach Änderungen an Plugin/Werkzeugen
hier anpassen, STAND/VERSIONEN oben aktualisieren und neu erzeugen.
"""
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, CondPageBreak, Flowable, Frame, KeepTogether, NextPageTemplate,
                                PageBreak, PageTemplate, Paragraph, Preformatted, Spacer, Table, TableStyle)
from reportlab.platypus.tableofcontents import TableOfContents

# ---------------------------------------------------------------- Stand
STAND = '27.10.2026'
QFIELD_PLUGIN = 'v0.5'
DESKTOP = '0.6.0'
ZIEL = Path(__file__).resolve().parents[1] / 'GoKart_QField_Anleitung.pdf'

# ---------------------------------------------------------------- Schrift & Farben
FONTS = Path('/usr/share/fonts/truetype/dejavu')
for name, datei in (('DV', 'DejaVuSans.ttf'), ('DV-B', 'DejaVuSans-Bold.ttf'),
                    ('DV-I', 'DejaVuSans-Oblique.ttf'), ('DV-BI', 'DejaVuSans-BoldOblique.ttf'),
                    ('DVM', 'DejaVuSansMono.ttf')):
    pdfmetrics.registerFont(TTFont(name, str(FONTS / datei)))
pdfmetrics.registerFontFamily('DV', normal='DV', bold='DV-B', italic='DV-I', boldItalic='DV-BI')

GRUEN = colors.HexColor('#167d50')
GRUEN_D = colors.HexColor('#0f5c3a')
HELL = colors.HexColor('#e6f6eb')
GRAU = colors.HexColor('#53645a')
LINIE = colors.HexColor('#c9d8ce')
ROT = colors.HexColor('#b3261e')
ROT_H = colors.HexColor('#fdecea')
GELB_H = colors.HexColor('#fff6dc')
GELB = colors.HexColor('#a86b00')

S = {}
S['body'] = ParagraphStyle('body', fontName='DV', fontSize=9.2, leading=13.2, spaceAfter=4, alignment=TA_LEFT)
S['h1'] = ParagraphStyle('h1', fontName='DV-B', fontSize=16, leading=20, textColor=GRUEN, spaceBefore=4, spaceAfter=8)
S['h2'] = ParagraphStyle('h2', fontName='DV-B', fontSize=11.2, leading=15, spaceBefore=9, spaceAfter=4)
S['h3'] = ParagraphStyle('h3', fontName='DV-B', fontSize=9.6, leading=13, spaceBefore=6, spaceAfter=2, textColor=GRUEN_D)
S['li'] = ParagraphStyle('li', parent=S['body'], leftIndent=13, bulletIndent=3, spaceAfter=2)
S['ol'] = ParagraphStyle('ol', parent=S['body'], leftIndent=15, bulletIndent=2, spaceAfter=2)
S['cell'] = ParagraphStyle('cell', fontName='DV', fontSize=8.1, leading=10.6)
S['cellb'] = ParagraphStyle('cellb', parent=S['cell'], fontName='DV-B', textColor=colors.white)
S['code'] = ParagraphStyle('code', fontName='DVM', fontSize=7.9, leading=10.4, leftIndent=6, rightIndent=6,
                           backColor=colors.HexColor('#f3f5f4'), borderPadding=(5, 6, 5, 6), spaceBefore=4, spaceAfter=8)
S['box'] = ParagraphStyle('box', parent=S['body'], fontSize=8.8, leading=12.4, spaceAfter=0)
S['klein'] = ParagraphStyle('klein', parent=S['body'], fontSize=7.8, leading=10.5, textColor=GRAU)
S['toc1'] = ParagraphStyle('toc1', fontName='DV', fontSize=10.5, leading=19, leftIndent=8)


def P(t, st='body'):
    return Paragraph(t, S[st])


def UL(*punkte):
    return [Paragraph(p, S['li'], bulletText='•') for p in punkte]


def OL(*punkte):
    return [Paragraph(p, S['ol'], bulletText=f'{i}.') for i, p in enumerate(punkte, 1)]


def CODE(t):
    return Preformatted(t.strip('\n'), S['code'])


def c(t):
    """Inline-Code."""
    return f'<font name="DVM" size="8.2">{t}</font>'


def BOX(art, text):
    farbe, grund, titel = {'hinweis': (GRUEN, HELL, 'Hinweis'), 'tipp': (GRUEN, HELL, 'Tipp'),
                           'achtung': (ROT, ROT_H, 'Achtung'), 'neu': (GELB, GELB_H, 'Neu')}[art]
    t = Table([[Paragraph(f'<b><font color="{farbe.hexval()}">{titel}:</font></b> {text}', S['box'])]],
              colWidths=[170 * mm])
    t.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), grund), ('LINEBEFORE', (0, 0), (0, -1), 3, farbe),
                           ('LEFTPADDING', (0, 0), (-1, -1), 8), ('RIGHTPADDING', (0, 0), (-1, -1), 8),
                           ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 6)]))
    return [Spacer(1, 3), t, Spacer(1, 6)]


def TAB(kopf, zeilen, breiten, gruen_spalte=None):
    daten = [[Paragraph(k, S['cellb']) for k in kopf]]
    for z in zeilen:
        daten.append([Paragraph(str(x), S['cell']) for x in z])
    t = Table(daten, colWidths=[b * mm for b in breiten], repeatRows=1)
    st = [('BACKGROUND', (0, 0), (-1, 0), GRUEN), ('VALIGN', (0, 0), (-1, -1), 'TOP'),
          ('LINEBELOW', (0, 1), (-1, -1), 0.4, LINIE), ('BOX', (0, 0), (-1, -1), 0.5, LINIE),
          ('TOPPADDING', (0, 0), (-1, -1), 3.5), ('BOTTOMPADDING', (0, 0), (-1, -1), 3.5),
          ('LEFTPADDING', (0, 0), (-1, -1), 4), ('RIGHTPADDING', (0, 0), (-1, -1), 4)]
    for i in range(2, len(daten), 2):
        st.append(('BACKGROUND', (0, i), (-1, i), colors.HexColor('#f6faf7')))
    t.setStyle(TableStyle(st))
    return [Spacer(1, 2), t, Spacer(1, 7)]


# ---------------------------------------------------------------- Grafiken
class Ablauf(Flowable):
    """Gesamtablauf als vier Kästen mit Pfeilen."""

    def __init__(self, schritte, breite=170 * mm, hoehe=34 * mm, hervor=2):
        super().__init__()
        self.schritte, self.width, self.height, self.hervor = schritte, breite, hoehe, hervor

    def draw(self):
        cv, n = self.canv, len(self.schritte)
        luecke = 7 * mm
        w = (self.width - (n - 1) * luecke) / n
        for i, (titel, zeilen) in enumerate(self.schritte):
            x = i * (w + luecke)
            voll = i == self.hervor
            cv.setFillColor(GRUEN if voll else HELL)
            cv.setStrokeColor(GRUEN)
            cv.roundRect(x, 0, w, self.height, 4, stroke=1, fill=1)
            cv.setFillColor(colors.white if voll else GRUEN_D)
            cv.setFont('DV-B', 8.6)
            cv.drawCentredString(x + w / 2, self.height - 6.5 * mm, f'{i + 1}  {titel}')
            cv.setFont('DV', 7.4)
            for k, z in enumerate(zeilen):
                cv.drawCentredString(x + w / 2, self.height - 12.5 * mm - k * 4.3 * mm, z)
            if i < n - 1:
                cv.setFillColor(GRUEN)
                ax, ay = x + w + 1.2 * mm, self.height / 2
                p = cv.beginPath()
                p.moveTo(ax, ay - 2.2 * mm)
                p.lineTo(ax + 4.4 * mm, ay)
                p.lineTo(ax, ay + 2.2 * mm)
                p.close()
                cv.drawPath(p, stroke=0, fill=1)


class Mockup(Flowable):
    """Vereinfachte Bildschirmskizze: Liste von Elementen links, nummerierte Erklärungen rechts.

    Elemente: ('titel', text, rechts) | ('label', text) | ('feld', text, knoepfe) | ('check', text, an)
              ('liste', [(fett, klein, ausgewaehlt)]) | ('knopf', text) | ('klein', text) | ('zeile', links, rechts)
    Jedes Element darf als letztes Tupel-Glied eine Nummer (int) tragen.
    """

    def __init__(self, elemente, erklaerungen, breite=170 * mm, fensterbreite=112 * mm):
        super().__init__()
        self.el, self.erkl, self.width, self.fb = elemente, erklaerungen, breite, fensterbreite
        self.height = self._hoehe() + 6 * mm

    H = {'titel': 9, 'label': 5.6, 'feld': 8, 'check': 5.6, 'knopf': 8.4, 'klein': 5, 'zeile': 5.4, 'trenn': 3}

    def _h(self, e):
        if e[0] == 'liste':
            return len(e[1]) * 8.6 + 1.5
        return self.H[e[0]]

    def _hoehe(self):
        return sum(self._h(e) for e in self.el) * mm + 6 * mm

    def nummer(self, x, y, n):
        cv = self.canv
        cv.setFillColor(GRUEN)
        cv.roundRect(x, y - 2.3 * mm, 4.6 * mm, 4.6 * mm, 1, stroke=0, fill=1)
        cv.setFillColor(colors.white)
        cv.setFont('DV-B', 7)
        cv.drawCentredString(x + 2.3 * mm, y - 1.1 * mm, str(n))

    def draw(self):
        cv = self.canv
        fb, h = self.fb, self.height - 4 * mm
        cv.setStrokeColor(LINIE)
        cv.setFillColor(colors.white)
        cv.roundRect(0, 2 * mm, fb, h, 4, stroke=1, fill=1)
        y = 2 * mm + h - 4 * mm
        x0, x1 = 4 * mm, fb - 4 * mm
        for e in self.el:
            art, hh = e[0], self._h(e) * mm
            num = e[-1] if isinstance(e[-1], int) and not isinstance(e[-1], bool) else None
            mitte = y - hh / 2
            if art == 'titel':
                cv.setFillColor(GRUEN)
                cv.setFont('DV-B', 9.5)
                cv.drawString(x0, mitte - 1.2 * mm, e[1])
                if e[2]:
                    cv.setFont('DV', 7.5)
                    cv.drawRightString(x1, mitte - 1 * mm, e[2])
            elif art == 'label':
                cv.setFillColor(colors.black)
                cv.setFont('DV-B', 7.6)
                cv.drawString(x0, mitte - 1 * mm, e[1])
            elif art == 'klein':
                cv.setFillColor(GRAU)
                cv.setFont('DV', 6.6)
                cv.drawString(x0, mitte - 0.8 * mm, e[1])
            elif art == 'zeile':
                cv.setFillColor(colors.black)
                cv.setFont('DV', 7.2)
                cv.drawString(x0, mitte - 0.9 * mm, e[1])
                cv.setFillColor(GRUEN)
                cv.drawRightString(x1, mitte - 0.9 * mm, e[2])
            elif art == 'check':
                an = e[2]
                cv.setStrokeColor(GRAU)
                cv.setFillColor(GRUEN if an else colors.white)
                cv.rect(x0, mitte - 1.6 * mm, 3.2 * mm, 3.2 * mm, stroke=1, fill=1)
                cv.setFillColor(colors.black)
                cv.setFont('DV', 7.2)
                cv.drawString(x0 + 5 * mm, mitte - 0.9 * mm, e[1])
            elif art == 'feld':
                knoepfe = e[2] if len(e) > 2 and isinstance(e[2], (list, tuple)) else []
                kb = 15 * mm
                fx1 = x1 - len(knoepfe) * (kb + 2 * mm)
                if not e[1] and knoepfe:          # nur Knöpfe: volle Breite aufteilen
                    kb = (x1 - x0 - 2 * mm * (len(knoepfe) - 1)) / len(knoepfe)
                    fx1 = x0 - 2 * mm
                if e[1]:
                    cv.setStrokeColor(GRAU)
                    cv.setFillColor(colors.white)
                    cv.roundRect(x0, mitte - 3 * mm, fx1 - x0, 6 * mm, 2, stroke=1, fill=1)
                    cv.setFillColor(colors.black)
                    cv.setFont('DV', 7.6)
                    cv.drawString(x0 + 2 * mm, mitte - 1 * mm, e[1])
                for k, t in enumerate(knoepfe):
                    bx = fx1 + 2 * mm + k * (kb + 2 * mm)
                    cv.setFillColor(HELL)
                    cv.setStrokeColor(GRUEN)
                    cv.roundRect(bx, mitte - 3 * mm, kb, 6 * mm, 2, stroke=1, fill=1)
                    cv.setFillColor(GRUEN_D)
                    cv.setFont('DV-B', 6.8)
                    cv.drawCentredString(bx + kb / 2, mitte - 0.9 * mm, t)
            elif art == 'liste':
                yy = y - 0.5 * mm
                for fett, klein, sel in e[1]:
                    cv.setFillColor(HELL if sel else colors.HexColor('#f4f6f5'))
                    cv.setStrokeColor(GRUEN if sel else LINIE)
                    cv.setLineWidth(1.2 if sel else 0.5)
                    cv.roundRect(x0, yy - 7.8 * mm, x1 - x0, 7.4 * mm, 2, stroke=1, fill=1)
                    cv.setLineWidth(1)
                    cv.setFillColor(colors.black)
                    cv.setFont('DV-B', 7.4)
                    cv.drawString(x0 + 2 * mm, yy - 3.4 * mm, fett)
                    cv.setFillColor(GRAU)
                    cv.setFont('DV-I', 6.4)
                    cv.drawString(x0 + 2 * mm, yy - 6.6 * mm, klein)
                    yy -= 8.6 * mm
            elif art == 'knopf':
                cv.setFillColor(GRUEN)
                cv.roundRect(x0, mitte - 3.2 * mm, x1 - x0, 6.4 * mm, 3, stroke=0, fill=1)
                cv.setFillColor(colors.white)
                cv.setFont('DV-B', 7.8)
                cv.drawCentredString((x0 + x1) / 2, mitte - 1.1 * mm, e[1])
            elif art == 'trenn':
                cv.setStrokeColor(LINIE)
                cv.line(x0, mitte, x1, mitte)
            if num:
                self.nummer(fb - 1.5 * mm + 3 * mm, mitte, num)
            y -= hh
        # Erklärungen rechts
        ex = fb + 10 * mm
        ey = 2 * mm + h - 6 * mm
        for n, t in self.erkl:
            self.nummer(ex, ey, n)
            p = Paragraph(t, ParagraphStyle('e', fontName='DV', fontSize=7.5, leading=9.6))
            w, hh = p.wrap(self.width - fb - 17 * mm, 40 * mm)
            p.drawOn(cv, ex + 6.5 * mm, ey - hh + 2.6 * mm)
            ey -= max(hh, 4.6 * mm) + 3.2 * mm


class Blatt(Flowable):
    """Großes Blatt-Symbol für die Titelseite."""

    def __init__(self, gr=58 * mm):
        super().__init__()
        self.width = self.height = gr

    def draw(self):
        cv, g = self.canv, self.width
        cv.setFillColor(colors.HexColor('#2fa36b'))
        p = cv.beginPath()
        p.moveTo(g / 2, 0)
        p.curveTo(-g * 0.05, g * 0.3, g * 0.1, g * 0.85, g / 2, g)
        p.curveTo(g * 0.9, g * 0.85, g * 1.05, g * 0.3, g / 2, 0)
        cv.drawPath(p, stroke=0, fill=1)
        cv.setStrokeColor(GRUEN)
        cv.setLineWidth(2)
        cv.line(g / 2, g * 0.04, g / 2, g * 0.9)


# ---------------------------------------------------------------- Dokument
class Doc(BaseDocTemplate):
    def __init__(self, ziel):
        super().__init__(str(ziel), pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=22 * mm,
                         bottomMargin=20 * mm, title='GoKart – Anleitung', author='Emu (kronisoft.net)',
                         subject='QField-Plugin und GoKart Desktop')
        rahmen = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id='f')
        titel = Frame(20 * mm, 20 * mm, 170 * mm, 150 * mm, id='t')
        self.addPageTemplates([PageTemplate('titel', [titel], onPage=self.titelseite),
                               PageTemplate('inhalt', [rahmen], onPage=self.kopf)])

    def afterFlowable(self, f):
        if isinstance(f, Paragraph) and f.style.name == 'h1' and f.getPlainText() != 'Inhalt':
            self.notify('TOCEntry', (0, f.getPlainText(), self.page))

    @staticmethod
    def titelseite(cv, doc):
        w, h = A4
        cv.saveState()
        cv.setFillColor(GRUEN)
        cv.rect(0, h - 118 * mm, w, 118 * mm, stroke=0, fill=1)
        cv.translate(w - 76 * mm, h - 104 * mm)
        Blatt(62 * mm).drawOn(cv, 0, 0)
        cv.restoreState()
        cv.saveState()
        cv.setFillColor(colors.white)
        cv.setFont('DV-B', 34)
        cv.drawString(22 * mm, h - 52 * mm, 'GoKart')
        cv.setFont('DV', 14)
        cv.drawString(22 * mm, h - 64 * mm, 'Pflanzen- und Biotoptypen-Kartierung')
        cv.drawString(22 * mm, h - 71 * mm, 'mit QField und QGIS')
        cv.setFont('DV', 9.6)
        cv.drawString(22 * mm, h - 86 * mm, 'Anleitung: Einrichtung, Erfassungsmodule, Geländearbeit,')
        cv.drawString(22 * mm, h - 92 * mm, 'Biotoptypen, Standortfotos, Übertragung, Abgleich, Fehlerbehebung')
        cv.restoreState()

    @staticmethod
    def kopf(cv, doc):
        w, h = A4
        cv.saveState()
        cv.setFont('DV', 7.2)
        cv.setFillColor(GRAU)
        cv.drawString(20 * mm, h - 13 * mm, 'GoKart · Anleitung QField-Plugin & GoKart Desktop')
        cv.drawRightString(w - 20 * mm, h - 13 * mm, f'Stand: {STAND}')
        cv.setStrokeColor(LINIE)
        cv.line(20 * mm, h - 15 * mm, w - 20 * mm, h - 15 * mm)
        cv.drawCentredString(w / 2, 11 * mm, f'Seite {doc.page}')
        cv.restoreState()


def H1(t):
    return [CondPageBreak(60 * mm), Paragraph(t, S['h1'])]


def H2(t):
    return [CondPageBreak(30 * mm), Paragraph(t, S['h2'])]


# ---------------------------------------------------------------- Inhalt
def titel():
    zeilen = [
        f'QField-Plugin: <b>{QFIELD_PLUGIN}</b> ({c("qfield_plugin/GoKart_Wohnung.qml")})',
        f'Desktop: QGIS ≥ 3.22 mit Plugin „GoKart Desktop“ <b>{DESKTOP}</b>',
        'Zielplattform: QField 4.x auf Android und iPad (QField 3.x per Fallback, ungetestet)',
        'Repository: github.com/Emu77/GoKart',
        f'Stand der Anleitung: {STAND}',
    ]
    neu = ('Seit der Fassung vom 25.10.2026: <b>Biotoptypen</b> (Haupt-/Nebenbiotop, Bundes- und Landesschlüssel, '
           'historische Schlüssel), <b>Erfassungsmodule je Projekt</b> (Arten / Fotos / Biotoptypen wählbar), '
           'Übertragung per <b>QField Sync</b> und <b>qfield_paket.py</b> (Zip für Telegram/USB), '
           'erweiterte Fehlerbehebung.')
    return ([Spacer(1, 4 * mm)] + [P(z) for z in zeilen] + [Spacer(1, 8 * mm)] + BOX('neu', neu) +
            [NextPageTemplate('inhalt'), PageBreak()])


def inhalt():
    toc = TableOfContents()
    toc.levelStyles = [S['toc1']]
    toc.dotsMinLevel = 0
    return [Paragraph('Inhalt', S['h1']), toc, PageBreak()]


def k1_ueberblick():
    f = H1('1 Überblick')
    f += [P('GoKart ist ein Projekt-Plugin für <b>QField</b> und ein Plugin für <b>QGIS</b> („GoKart Desktop“). '
            'Im Gelände werden je Kartierfläche (Biotop-, Vegetations- oder Teilfläche) erfasst:'),
          *UL('<b>Pflanzenarten</b> – per Spracheingabe oder Tastatur, fehlertolerante Suche (Kölner Phonetik + '
              'Levenshtein), max. 5 Vorschläge, eigene Synonyme werden gelernt.',
              '<b>Biotoptypen</b> – Haupt- und Nebenbiotop nach Bundes- oder Landesschlüssel (z. B. SH, NI, SH_2003), '
              'Codes auch buchstabiert diktierbar („we em ypsilon“ → WMy).',
              '<b>Standortfotos</b> – mit Kommentar, Zeitpunkt und GPS-Position.'),
          P('Welche dieser drei <b>Erfassungsmodule</b> ein Projekt nutzt, legt man am PC fest (Kapitel 5). '
            'QField zeigt dann nur die passenden Knöpfe.')]
    f += H2('Gesamtablauf')
    f += [Ablauf([('PC / QGIS', ['Flächen + gokart.gpkg', '„Einrichten…“', 'Module wählen, Strg+S']),
                  ('Übertragen', ['QField Sync verpacken', 'qfield_paket.py → Zip', 'aufs Gerät']),
                  ('Gelände', ['Fläche wählen', 'Arten / Biotope', 'Fotos']),
                  ('Zurück an PC', ['Export holen', 'abgleich.py', 'Artenliste'])]), Spacer(1, 8)]
    f += H2('Bestandteile')
    f += TAB(['Komponente', 'Ort im Repository', 'Aufgabe'], [
        ['QField-Plugin', c('qfield_plugin/GoKart_Wohnung.qml') + ' + ' + c('gokart_suche.js') + ', ' +
         c('gokart_biotop.js') + ', Icons', 'Erfassung im Gelände: Arten, Fotos, Biotoptypen; Konfiguration über '
         'Projektvariablen'],
        ['GoKart Desktop', c('qgis_plugin/gokart_desktop/'), 'QGIS-Plugin: Projekt einrichten, Module wählen, am PC '
         'erfassen, Export, Biotop-Kataloge einspielen'],
        ['Biotop-Kataloge', c('qgis_plugin/gokart_desktop/biotope_kataloge/*.csv'), 'Schlüssel Bund/Länder als CSV'],
        ['Werkzeuge', c('qfield/werkzeuge/'), 'Projekt bauen, Zip fürs Tablet, Plugin kopieren, Abgleich, '
         'Artenliste, Biotope einspielen, Zusatztaxa'],
        ['Tests', c('qfield/test/'), 'Suchtest (Node) und QField-Simulation (PySide6)'],
        ['Alte Basisversion', c('qfield/plugin/'), '<i>nicht mehr verwenden</i> (v0.1, nur Arten, feste Layernamen)'],
    ], [32, 64, 74])
    f += BOX('hinweis', 'Die QML-Datei des Plugins <b>muss genauso heißen wie die Projektdatei</b> und daneben liegen: '
             f'{c("gokart.qgs")} → {c("gokart.qml")}, {c("kobm_qfield.qgs")} → {c("kobm_qfield.qml")}. Nur dann '
             f'erkennt QField sie als Projekt-Plugin. {c("qfield_paket.py")} und {c("plugin_aktualisieren.py")} '
             'benennen sie automatisch richtig.')
    return f


def k2_voraussetzungen():
    f = H1('2 Voraussetzungen')
    f += H2('Mobilgerät (Android oder iPad)')
    f += UL('QField 4.x (getestet auf Android). Für QField 3.x gibt es einen API-Fallback (ungetestet).',
            'Tastatur mit Offline-Diktat – das Plugin nutzt die Spracheingabe der Bildschirmtastatur: z. B. FUTO '
            'Keyboard oder Gboard mit deutschem Offline-Sprachpaket; auf dem iPad die Diktierfunktion.',
            'Standortfreigabe für QField (Fläche per GPS), Kamerafreigabe (Standortfotos).',
            'Das Plugin braucht kein Internet; nur eine Online-Hintergrundkarte (OSM) wird geladen.')
    f += H2('PC (Ubuntu oder Windows)')
    f += UL('QGIS ≥ 3.22 mit den Erweiterungen <b>GoKart Desktop</b> und <b>QField Sync</b>.',
            f'Python 3 für die Werkzeuge; für {c("build_gokart_projekt.py")} unter Ubuntu zusätzlich '
            f'{c("python3-qgis")} und {c("qgis-providers")}. Alle anderen Werkzeuge brauchen kein QGIS.',
            f'Referenzdaten: {c("GoKart_Pflanzen.sqlite")} (BfN-Skript 519), optional {c("germansl.sqlite")} '
            '(GermanSL 1.5) – nur zum Bauen eines neuen GeoPackages nötig.',
            'Optional: Vosk + Modell für Spracheingabe am PC (Kapitel 12), Node.js/PySide6 für Tests.')
    f += [CODE('sudo apt install python3-qgis qgis-providers')]
    f += H2('GoKart Desktop installieren')
    f += OL('QGIS → <b>Erweiterungen → Erweiterungen verwalten und installieren → Aus ZIP installieren</b>.',
            f'{c(f"GoKart_Desktop_{DESKTOP}.zip")} wählen → <b>Erweiterung installieren</b>.',
            'QGIS neu starten. Kontrolle: in der Liste „Installiert“ auf den <b>Namen</b> „GoKart Desktop“ klicken '
            '(nicht aufs Häkchen) – rechts steht die Version.')
    f += [P(f'Das Zip entsteht aus dem Repo mit: {c("cd qgis_plugin && zip -r GoKart_Desktop_x.y.z.zip gokart_desktop")}')]
    return f


def k3_datenmodell():
    f = H1('3 Datenmodell')
    f += [P(f'Alle GoKart-Daten liegen in <b>einem GeoPackage</b> (Vorlage {c("gokart.gpkg")}, im Projekt evtl. '
            f'anders benannt, z. B. {c("kobm.gpkg")}). Die Flächen dürfen in einer eigenen Datei liegen (Shape, '
            'GeoPackage …).')]
    f += TAB(['Tabelle', 'Typ', 'Wichtige Felder', 'Bemerkung'], [
        ['Flächen', 'Polygon', 'eindeutiges Schlüsselfeld, optional Anzeigefeld', 'beliebiger Polygon-Layer; '
         'Schlüssel am besten als <b>Text</b>'],
        ['artnachweise', 'Tabelle', 'flaeche_id, taxon_id, wissenschaftlicher_name, deutscher_name, '
         'original_eingabe, erfasst_am, bemerkung', 'Modul Arten; eine Art je Fläche nur einmal'],
        ['eigene_synonyme', 'Tabelle', 'taxon_id, synonym, schluessel, angelegt_am', 'entsteht beim Erfassen'],
        ['taxon', 'Tabelle', 'taxon_id, wissenschaftlicher_name, deutscher_name, rang, autor_name',
         'Referenz, schreibgeschützt (ca. 6.100 Taxa)'],
        ['suchnamen', 'Tabelle', 'taxon_id, name, art, schluessel', 'Referenz (ca. 15.600 Suchnamen)'],
        ['fotos', 'Tabelle', 'flaeche_id, datei, kommentar, aufgenommen_am, lon, lat', 'Modul Fotos; Bilder im '
         'Projektordner unter ' + c('fotos/')],
        ['biotop_schluessel', 'Tabelle', 'schluessel, name, land, stand, quelle, vollstaendig, anzahl',
         'welche Kataloge eingespielt sind'],
        ['biotoptypen', 'Tabelle', 'schluessel, code, name, nr, obercode, ebene, bund_code, ffh_lrt',
         'Katalog, schreibgeschützt'],
        ['biotopzuordnung', 'Tabelle', 'flaeche_id, schluessel, code, name, rolle (Haupt/Neben), anteil, '
         'bund_code, original_eingabe, erfasst_am, bemerkung', 'Modul Biotoptypen; je Fläche und Schlüssel '
         'ein Hauptbiotop'],
    ], [30, 16, 70, 54])
    f += [P('Zwischen Fläche und Artnachweisen bzw. Biotop-Zuordnungen besteht je eine 1:n-Beziehung '
            f'({c("gokart_flaeche_nachweise")}, {c("gokart_flaeche_biotope")}). Dadurch zeigt das Flächenformular in '
            'QField die zugehörigen Einträge.')]
    f += H2('Koordinatensystem')
    f += [P('Das Projekt-KBS ist frei wählbar (z. B. EPSG:25832 für Norddeutschland, EPSG:31467 für Gauß-Krüger-'
            'Altdaten). GPS-Positionen und die Kartenmitte werden vor der Flächenabfrage automatisch ins KBS des '
            'Flächenlayers transformiert. Wichtig ist nur, dass <b>jeder Layer sein KBS kennt</b> – ein „?“ neben '
            'dem Layer in QGIS bedeutet: kein KBS gesetzt.')]
    f += BOX('achtung', '<b>GeoPackage auf NTFS unter Linux</b> (Dual-Boot-Datenpartition): QGIS nutzt den SQLite-'
             'WAL-Modus, der dort nicht zuverlässig ist – Änderungen können verloren gehen. Abhilfe: Projekt auf ext4 '
             f'legen oder in QGIS unter <i>Einstellungen → Optionen → Erweitert</i> {c("walForSqlite3")} = '
             f'{c("false")} setzen und QGIS neu starten. Prüfen mit {c("findmnt -no FSTYPE /pfad")}.')
    return f


def k4_vorbereiten():
    f = H1('4 Projekt am PC vorbereiten')
    f += [P('Zwei Wege: ein vorhandenes QGIS-Projekt mit GoKart Desktop einrichten (<b>Weg A</b>, der Normalfall) oder '
            'ein komplettes Projekt mit dem Build-Skript erzeugen (<b>Weg B</b>).')]
    f += H2('Weg A – Vorhandenes Projekt mit „GoKart Desktop“ einrichten')
    f += OL('Projekt mit den eigenen Flächen in QGIS öffnen.',
            f'Das GoKart-GeoPackage per Drag &amp; Drop laden; mindestens {c("taxon")}, {c("suchnamen")}, '
            f'{c("eigene_synonyme")} und {c("artnachweise")} übernehmen (Layernamen nicht ändern). Biotop-Layer und '
            'Fototabelle legt das Plugin beim Einrichten selbst an.',
            '<b>Erweiterungen → GoKart → Projekt einrichten…</b> oder im GoKart-Panel <b>Einrichten…</b>.',
            'Dialog ausfüllen (siehe unten), <b>OK</b>.',
            '<b>Projekt speichern (Strg+S)</b> – erst dann stehen die Einstellungen in der Projektdatei und kommen in '
            'QField an. Ein „*“ im Fenstertitel heißt: noch nicht gespeichert.')
    f += [Spacer(1, 4), Mockup([
        ('titel', 'GoKart – Projekt einrichten', ''),
        ('label', 'Erfassen'),
        ('check', 'Pflanzenarten      ☑ Standortfotos      ☑ Biotoptypen', True, 1),
        ('trenn',),
        ('label', 'Flächen'),
        ('feld', 'Layer:  biotope', 2),
        ('feld', 'Schlüsselfeld:  flaeche_id'),
        ('feld', 'Anzeigefeld:  LEGENDE'),
        ('label', 'Artnachweise'),
        ('feld', 'Layer:  artnachweise', 3),
        ('feld', 'Verweis auf Fläche:  flaeche_id'),
        ('check', 'QGIS-Beziehung anlegen/aktualisieren', True),
        ('klein', '184 Flächen, 0 ohne Schlüssel, 0 doppelte Schlüssel.', 4),
        ('label', 'Biotoptypen'),
        ('feld', 'Schlüssel:  SH_2003 – Standardliste … (396 Typen)', 5),
        ('knopf', 'Kataloge einspielen / aktualisieren'),
    ], [
        (1, '<b>Erfassen</b>: welche Module das Projekt nutzt (Kapitel 5). Nur diese Knöpfe erscheinen in QField.'),
        (2, '<b>Flächen</b>: Polygon-Layer, eindeutiges <b>Schlüsselfeld</b> und lesbares <b>Anzeigefeld</b> '
            '(z. B. LEGENDE → „6-GFy (10)“).'),
        (3, '<b>Artnachweise</b>: Layer artnachweise; <b>Verweis auf Fläche</b> immer flaeche_id. Ist das Modul '
            'Arten aus, bestimmt der Layer nur die GeoPackage-Datei.'),
        (4, '<b>Prüfung</b>: Anzahl Flächen, fehlende/doppelte Schlüssel, unpassende Feldtypen (⚠).'),
        (5, '<b>Biotoptypen</b>: Kataloge in die GeoPackage einspielen, dann den geltenden Schlüssel wählen.'),
    ])]
    f += H2('Das Schlüsselfeld richtig wählen')
    f += UL('Muss je Fläche <b>eindeutig</b> und gefüllt sein – der Dialog zählt Lücken und Doppelte.',
            f'Der Verweis {c("flaeche_id")} in artnachweise/biotopzuordnung ist <b>Text</b>. Ist das Schlüsselfeld '
            f'eine Zahl (z. B. {c("AUFN_NR")}), meldet der Dialog <i>⚠ Feldtypen passen nicht (integer64 ↔ string)</i>. '
            'Erfassen klappt trotzdem, aber die Beziehungslisten in QField-Formularen können leer bleiben.',
            '<b>Abhilfe</b>: im Flächenlayer ein Textfeld anlegen und als Schlüssel nehmen (Kasten unten).')
    f += [KeepTogether(BOX('tipp', 'Flächenlayer → <b>Feldrechner</b> → <i>Neues Feld anlegen</i>: Name '
                       f'{c("flaeche_id")}, Typ <b>Text (string)</b>, Länge 10, Ausdruck {c("to_string(&quot;AUFN_NR&quot;)")} '
                       '→ OK → Bearbeitung speichern (Bleistift aus → Speichern). Dann <b>Dialog neu öffnen</b> – '
                       'die Feldliste wird nur beim Öffnen geladen. Shapefile: Feldnamen max. 10 Zeichen.'))]
    f += BOX('achtung', 'Nur <b>einen</b> Flächenlayer im Projekt haben. Liegen z. B. „biotope“ und „kobm — biotope“ '
             'nebeneinander, landet ein neues Feld leicht im falschen Layer und fehlt dann im Dropdown.')
    f += H2('Projektvariablen')
    f += [P('Der Dialog speichert alles als Projektvariablen (<i>Projekt → Eigenschaften → Variablen</i>). '
            'QField-Plugin und Werkzeuge lesen sie von dort.')]
    f += TAB(['Projektvariable', 'Inhalt'], [
        [c('gokart_module'), 'aktive Module, z. B. ' + c('arten,biotope') + ' – fehlt sie, gilt alles'],
        [c('gokart_flaechen_layer'), 'Layer-ID der Flächen'],
        [c('gokart_flaechen_key'), 'Schlüsselfeld der Flächen'],
        [c('gokart_flaechen_label'), 'Anzeigefeld (optional)'],
        [c('gokart_nachweis_layer'), 'Layer-ID der Artnachweise (zugleich: welche GeoPackage)'],
        [c('gokart_nachweis_fk'), 'Fremdschlüssel in den Artnachweisen (flaeche_id)'],
        [c('gokart_relation'), 'ID der Beziehung Fläche → Artnachweise'],
        [c('gokart_biotop_schluessel'), 'geltender Biotoptypen-Schlüssel, z. B. SH, NI, SH_2003'],
    ], [55, 115])
    f += [P('Fehlen die Variablen, sucht das QField-Plugin nach Layern namens „flaechen“ bzw. „Wohnung – Teilflächen“ '
            'und „artnachweise“ mit dem Feld flaeche_id (Fallback). Die Diagnosezeile zeigt, welche Quelle galt.')]
    f += H2('Weg B – Projekt mit build_gokart_projekt.py bauen')
    f += [P('Erzeugt GeoPackage und QGIS-Projekt (Beziehungen, Auswahllisten, Biotop-Kataloge, Fototabelle) und legt das '
            'aktuelle Plugin dazu. Braucht PyQGIS.')]
    f += [CODE('''cd GoKart/qfield/werkzeuge
python3 build_gokart_projekt.py \\
  --db …/GoKart_Pflanzen_Datenbank/GoKart_Pflanzen.sqlite \\
  --germansl ".../GermanSL 1.5/germansl.sqlite" \\
  --ziel /media/emu/daten/gpb/GoKart/qfield_projekt \\
  --flaechen /pfad/biotope.shp --id-feld BIOTOP_NR --name-feld BT_TEXT \\
  --biotop-schluessel SH --module arten,fotos,biotope''')]
    f += TAB(['Option', 'Bedeutung'], [
        ['--db', 'GoKart_Pflanzen.sqlite (Pflicht)'],
        ['--ziel', 'Zielordner des QField-Projekts (Pflicht)'],
        ['--germansl', 'germansl.sqlite für zusätzliche deutsche Namen'],
        ['--flaechen / --flaechen-layer', 'eigene Polygone (GPKG, SHP …) statt Testflächen; Layername bei GPKG'],
        ['--id-feld / --name-feld', 'eindeutige Flächen-ID / optionale Bezeichnung (ohne --id-feld: Felder anzeigen)'],
        ['--id-auto PRÄFIX', 'fortlaufende IDs (K6-001 …) in Reihenfolge der Quelldatei'],
        ['--leer --crs EPSG:25832', 'Vorlage ohne Flächen zur Weitergabe; KBS des leeren Flächenlayers'],
        ['--module LISTE', 'Erfassungsmodule aus arten, fotos, biotope (Standard: alle)'],
        ['--biotop-schluessel S', 'geltender Schlüssel, z. B. SH, NI, SH_2003'],
        ['--ohne-biotope', 'keine Biotop-Kataloge einspielen (automatisch, wenn biotope nicht in --module)'],
        ['--zusatz / --zusatztaxa', 'eigene CSV-Dateien (Standard: zusatznamen.csv, zusatztaxa.csv)'],
        ['--neu', 'vorhandenes gokart.gpkg überschreiben (vorher automatische Sicherung)'],
    ], [50, 120])
    f += BOX('achtung', 'Mit <b>--neu</b> gehen alle Erfassungen im alten GeoPackage verloren. Vorher die Daten vom '
             'Gerät zurückholen und abgleichen!')
    return f


def k5_module():
    f = H1('5 Erfassungsmodule wählen')
    f += [P('Nicht jede Kartierung braucht alles: eine reine Biotoptypenkartierung braucht keine Artensuche, eine '
            'Florenliste keine Biotopcodes. Mit den Modulen bleibt die Oberfläche im Gelände schlank.')]
    f += TAB(['Modul', 'Knopf in QField', 'Bereich in GoKart Desktop', 'Tabellen'], [
        ['<b>Pflanzenarten</b> (' + c('arten') + ')', 'Blatt – „GoKart · Arterfassung“', 'Artensuche, erfasste Arten',
         'artnachweise, eigene_synonyme, taxon, suchnamen'],
        ['<b>Standortfotos</b> (' + c('fotos') + ')', 'Kamera – „GoKart · Standortfotos“', 'Fotoleiste mit Kommentar',
         'fotos + Ordner fotos/'],
        ['<b>Biotoptypen</b> (' + c('biotope') + ')', 'Biotop – „GoKart · Biotoptyp“', 'Biotoptypen dieser Fläche',
         'biotoptypen, biotop_schluessel, biotopzuordnung'],
    ], [36, 42, 42, 50])
    f += H2('So geht es')
    f += OL('Am PC: <b>Einrichten…</b> → Abschnitt <b>Erfassen</b> → Häkchen setzen → <b>OK</b> → <b>Strg+S</b>.',
            'Das GoKart-Panel blendet nicht gewählte Bereiche sofort aus.',
            'Projekt neu verpacken und aufs Gerät bringen (Kapitel 6). QField zeigt nur die Knöpfe der gewählten Module.')
    f += UL('Mindestens ein Modul muss gewählt sein.',
            'Bei <b>Fotos</b> legt der Dialog die Tabelle ' + c('fotos') + ' an und lädt sie als Layer; bei '
            '<b>Biotoptypen</b> werden die Biotop-Layer geladen.',
            'Ist <b>Arten</b> aus, entfallen Verweisfeld und Beziehung Fläche → Artnachweise. Der Layer artnachweise '
            'bestimmt dann nur, in welcher GeoPackage Fotos und Biotope liegen.',
            'Ältere Projekte ohne ' + c('gokart_module') + ' verhalten sich wie bisher: alle drei Knöpfe.',
            'Daten bleiben erhalten: Wer ein Modul abwählt, löscht nichts – es wird nur nicht mehr angezeigt.')
    f += BOX('tipp', f'Prüfen, ob die Einstellung im verpackten Projekt steckt: {c("grep -o gokart_module …/kobm_qfield.qgs")} '
             '– erscheint der Name, ist alles gespeichert.')
    return f


def k6_uebertragen():
    f = H1('6 Projekt aufs Gerät bringen')
    f += H2('Weg 1 – QField Sync + qfield_paket.py (empfohlen)')
    f += OL('In QGIS <b>Strg+S</b> (kein „*“ mehr im Fenstertitel).',
            'Werkzeugleiste <b>QField Sync</b> (Reihe mit zwei Wolken, dann zwei grün-gelben Würfeln und einem '
            'Werkzeug-Symbol): den <b>ersten Würfel „Für QField verpacken“</b> anklicken – oder <i>Erweiterungen → '
            'QField Sync → Für QField verpacken…</i>. Das Fenster öffnet sich manchmal hinter QGIS (Alt+Tab).',
            f'Exportordner wählen (Standard {c("~/QField/export/&lt;Projekt&gt;")}) → Erstellen. QGIS meldet „Finished '
            'creating the project …“.',
            'Plugin dazulegen und zippen – ein Befehl:')
    f += [CODE('''cd /media/emu/daten/gpb/GoKart
python3 qfield/werkzeuge/qfield_paket.py ~/QField/export/kobm
#  Projekt: kobm_qfield.qgs
#  ✔ /home/emu/QField/export/kobm.zip  (27 Dateien, 0.9 MB)''')]
    f += UL(f'Legt das aktuelle Plugin aus {c("qfield_plugin/")} passend benannt dazu ({c("kobm_qfield.qml")} + js/svg).',
            f'Lässt Sicherungen ({c("*~")}, {c("*.bak")}) und SQLite-Hilfsdateien ({c("-wal")}, {c("-shm")}) weg.',
            'Warnt, wenn eine GeoPackage noch in QGIS geöffnet ist, und wenn das Zip über 50 MB wird (Fotos).',
            f'{c("--datum")} → {c("kobm_2026-10-27.zip")}; {c("--zip &lt;Datei&gt;")} → anderer Zielname.')
    f += H2('Weg 2 – Projektordner direkt (gokart_qfield, Build-Ergebnis)')
    f += [P('Ein mit dem Build-Skript erzeugter Ordner ist schon QField-fertig. Auch hier macht ' +
            c('qfield_paket.py &lt;Ordner&gt;') + ' das Zip. Nur das Plugin aktualisieren, ohne zu zippen:')]
    f += [CODE('''python3 qfield/werkzeuge/plugin_aktualisieren.py gokart_qfield            # kopieren
python3 qfield/werkzeuge/plugin_aktualisieren.py gokart_qfield --pruefen  # nur vergleichen''')]
    f += H2('Auf dem Gerät')
    f += TAB(['Weg', 'Vorgehen'], [
        ['Zip per Telegram / Mail', 'Zip auf dem Gerät öffnen bzw. speichern → in QField <b>Projekt aus ZIP '
         'importieren</b> (QField-Menü → Projekte öffnen → „+“).'],
        ['Android per USB', 'Ordner nach ' + c('Android/data/ch.opengis.qfield/files/Imported Projects/') + ' kopieren.'],
        ['iPad', 'Finder (macOS) bzw. Dateien-App → QField → Ordner bzw. Zip hineinlegen.'],
    ], [40, 130])
    f += OL('In QField das Projekt öffnen (bei QField-Sync-Exporten ' + c('kobm_qfield') + ').',
            'Frage nach dem Projekt-Plugin mit <b>Erlauben</b> beantworten (optional „immer“).',
            'In der Plugin-Leiste rechts erscheinen grüne Rundknöpfe – je nach Modulen <b>Blatt</b> (Arten), '
            '<b>Kamera</b> (Fotos) und <b>Biotop</b> (Biotoptypen). Die grüne Lupe darüber gehört zu QField selbst.')
    f += BOX('hinweis', 'Beim ersten Öffnen der Arterfassung werden die Pflanzendaten geladen; danach meldet ein '
             'Hinweis z. B. „GoKart: 6101 Taxa geladen (… ms)“. Der Index bleibt bis zum Schließen im Speicher.')
    return f


def k7_arten():
    f = H1('7 Arten im Gelände erfassen')
    f[-1] = KeepTogether([f[-1], P('Den grünen <b>Blatt-Knopf</b> antippen. Es öffnet sich „GoKart · Arterfassung“:'),
                          Spacer(1, 4), Mockup([
        ('titel', 'GoKart · Arterfassung', 'Schließen'),
        ('label', 'Fläche'),
        ('feld', '6-GFy (10)  ▾', ['GPS', 'Karte'], 1),
        ('check', 'Unbenannte Flächen anzeigen', False),
        ('label', 'Pflanzenname'),
        ('feld', 'stil eiche', 2),
        ('liste', [('Stiel-Eiche', 'Quercus robur L. · Art', True), ('Trauben-Eiche', 'Quercus petraea (Matt.) '
                   'Liebl. · Art', False), ('Stiel-Eiche (Aggregat)', 'Quercus robur agg. · Aggregat', False)], 3),
        ('check', '„stil eiche“ als eigenes Synonym merken', True, 4),
        ('knopf', 'Zu 6-GFy hinzufügen: Stiel-Eiche', 5),
        ('klein', 'Diagnose: artnachweise: start=true, hinzufügen=true, speichern=true …', 6),
        ('label', 'Erfasst auf 6-GFy: 2 Arten', 7),
        ('zeile', 'Sumpf-Dotterblume   Caltha palustris', 'Löschen'),
        ('zeile', 'Kuckucks-Lichtnelke   Silene flos-cuculi', 'Löschen'),
    ], [(1, 'Fläche wählen: Liste, GPS oder Kartenmitte'), (2, 'Namensfeld: Tastatur-Mikrofon oder tippen'),
        (3, 'Vorschläge (max. 5), Auswahl grün umrandet'), (4, 'eigenes Synonym lernen (optional)'),
        (5, 'Speichern – auch per Enter-Taste'), (6, 'Diagnose des letzten Speicherns'),
        (7, 'erfasste Arten, Löschen mit Rückfrage')])])
    f += H2('Schritt 1 – Fläche wählen')
    f += UL('<b>Liste</b>: Anzeige „Anzeigename (Schlüssel)“, sortiert nach Name. Gibt es nur eine Fläche, ist sie aktiv.',
            '<b>GPS</b>: Fläche unter der aktuellen Position (gültige Position in QField nötig).',
            '<b>Karte</b>: Fläche unter der Kartenmitte – gut bei ungenauem GPS.',
            'Überlappen sich Flächen, gilt die <b>kleinste</b> am Punkt (Teilfläche statt Gesamtgebiet).',
            'Flächen ohne Anzeigename sind ausgeblendet; <b>Unbenannte Flächen anzeigen</b> holt sie zurück.',
            'Die aktive Fläche ist in allen drei Dialogen (Arten, Fotos, Biotoptypen) dieselbe.')
    f += H2('Schritt 2 bis 5 – Name, Vorschlag, Synonym, Speichern')
    f += UL('Ins Feld tippen oder das Mikrofon der Tastatur nutzen. Deutsche und wissenschaftliche Namen, botanische '
            'und eigene Synonyme werden gefunden; die Suche startet 250 ms nach der letzten Eingabe.',
            'Bei genau einem exakten Treffer ist er schon gewählt – sonst antippen. Bei gleichen wissenschaftlichen '
            'Namen (s. l. / s. str.) hilft der volle Name mit Autor.',
            'War die Eingabe kein bekannter Name, erscheint „… als eigenes Synonym merken“. Gemerkte Synonyme haben '
            'künftig die höchste Priorität.',
            '<b>Speichern</b> mit dem grünen Knopf oder <b>Enter</b> – Ablauf beim Diktieren: sprechen → Enter. '
            'Gespeichert werden Fläche, taxon_id, Namen, Originaleingabe und Zeitpunkt, sofort dauerhaft.',
            'Schon erfasste Art → Meldung „… ist auf … bereits erfasst.“ (kein Duplikat).',
            'Löschen: <b>Löschen</b> → Knopf wird zu „Sicher?“ → innerhalb von 3 s erneut antippen.')
    f += BOX('hinweis', 'Die Diagnosezeile zeigt nach jedem Speichern die Einzelschritte (start, hinzufügen, '
             'speichern). Bei Fehlern ist sie rot und enthält die Meldung des Layers. Hängende ungespeicherte '
             'Änderungen werden beim Öffnen des Dialogs nachgespeichert.')
    return f


def k8_biotope():
    f = H1('8 Biotoptypen erfassen')
    f[-1] = KeepTogether([f[-1], P('Den <b>Biotop-Knopf</b> antippen. Es öffnet sich „GoKart · Biotoptyp“. Je Fläche '
            'gibt es pro Schlüssel ein <b>Hauptbiotop</b> und beliebig viele <b>Nebenbiotope</b>.'), Spacer(1, 4), Mockup([
        ('titel', 'GoKart · Biotoptyp', 'Schließen'),
        ('label', 'Fläche'),
        ('feld', '6-GFy (10)  ▾', ['GPS', 'Karte'], 1),
        ('zeile', 'Schlüssel   SH_2003 – Standardliste der Biotoptypen in S-H, 2. Fassung', '', 2),
        ('feld', 'we em ypsilon', 3),
        ('liste', [('WMy – Sonstiger Mischwald', 'Nr. 1.7.4 · Ebene 3 · BfN 43.07', True),
                   ('WM – Mischwälder', 'Nr. 1.7 · Ebene 2', False)], 4),
        ('feld', '', ['Hauptbiotop', 'Nebenbiotop'], 5),
        ('klein', 'Diagnose: biotopzuordnung: start=true, hinzufügen=true, speichern=true'),
        ('label', 'Biotoptypen von 6-GFy: 2', 6),
        ('zeile', '●  GFy – Sonstige wechselfeuchte Wiese', '→ Neben   Löschen'),
        ('zeile', '○  WMy – Sonstiger Mischwald', '→ Haupt   Löschen'),
    ], [(1, 'Fläche wählen – wie bei den Arten'),
        (2, 'geltender Schlüssel (am PC festgelegt); ohne Festlegung hier auswählbar'),
        (3, 'Code oder Name tippen bzw. diktieren, auch buchstabiert'),
        (4, 'Treffer mit Nr., Ebene, BfN-Code, ggf. FFH-LRT'), (5, 'als Haupt- oder Nebenbiotop speichern'),
        (6, '● Haupt / ○ Neben – Rolle tauschen oder löschen')])])
    f += H2('Suchen')
    f += UL('Reihenfolge: Code exakt > Name exakt > Code-Anfang > Name-Anfang > alle Wörter im Namen > ähnlich '
            '(Tipp-/Hörfehler).',
            'Codes lassen sich <b>buchstabieren</b>: „we em ypsilon“ → WMy, „ge ef ypsilon“ → GFy, auch „zwo“, '
            '„eins“ … für Ziffern. Groß-/Kleinschreibung ist egal.',
            'Name-Suche: z. B. „Knick“, „wechselfeuchte Wiese“, „Birken Stadium“.')
    f += H2('Speichern und Regeln')
    f += UL('<b>Hauptbiotop</b>: ein vorhandenes Hauptbiotop desselben Schlüssels wird automatisch zum Nebenbiotop.',
            'Gleicher Code nochmals → Meldung „… bereits als Haupt-/Nebenbiotop erfasst“; mit der anderen Rolle wird '
            'nur die Rolle geändert.',
            'Gespeichert werden Fläche, Schlüssel, Code, Name, Rolle, BfN-Code (falls bekannt), Originaleingabe, Zeitpunkt.',
            'In der Liste: <b>→ Haupt / → Neben</b> tauscht die Rolle, <b>Löschen</b> mit „Sicher?“-Rückfrage.')
    f += H2('Schlüssel und Kataloge')
    f += [P('Welcher Schlüssel gilt, steht in ' + c('gokart_biotop_schluessel') + ' (Einrichten… → Biotoptypen). '
            'Mitgelieferte Kataloge:')]
    f += TAB(['Schlüssel', 'Quelle / Stand', 'Umfang'], [
        ['SH', 'LfU S-H, Kartieranleitung und Biotoptypenschlüssel, V 2.2.1 (08/2024)', '545, ohne Hauptgruppe S '
         '(unvollständig)'],
        ['NI', 'NLWKN, v. Drachenfels, Kartierschlüssel Niedersachsen 03/2021', 'nur Wälder (123)'],
        ['SH_2003', 'LANU S-H, Standardliste der Biotoptypen, 2. Fassung (05/2003)', '396, vollständig – für Altdaten'],
        ['HH_1999', 'Naturschutzamt Hamburg, Biotoptypenschlüssel 1999', '514, vollständig'],
        ['BE_2002 / BB_2002', 'Biotoptypenlisten Berlin / Brandenburg 2002', '945 / 950'],
        ['SN_2003', 'LfUG Sachsen, Liste der Biotoptypen 10/2003', '98, nur selektive Kartierung'],
    ], [28, 92, 50])
    f += BOX('tipp', 'Vorhandene Biotop-Shapes nutzen oft einen <b>älteren</b> Schlüssel. Codes wie GFy, GMm, HWr, '
             'MSb passen zu <b>SH_2003</b>, nicht zur aktuellen SH-Liste – dann SH_2003 wählen.')
    f += [P('Kataloge einspielen: im Einrichten-Dialog <b>Kataloge einspielen / aktualisieren</b> – oder ohne QGIS:')]
    f += [CODE('''python3 qfield/werkzeuge/biotope_einspielen.py <Projekt> --schluessel SH
python3 qfield/werkzeuge/biotope_einspielen.py <Projekt> --liste      # was ist wo vorhanden?''')]
    f += [P('Weitere Länder aus Original-PDF/Excel: ' + c('qfield/werkzeuge/biotope_katalog_import.py') +
            ' (Anleitung in ' + c('biotope_kataloge/README.md') + ').')]
    f += BOX('hinweis', 'Die Listen stammen aus den veröffentlichten Kartieranleitungen. Vor einer Weitergabe prüfen, '
             'ob die Herausgeber der Weiterverbreitung zustimmen.')
    return f


def k9_fotos():
    f = H1('9 Standortfotos')
    f += [P('Über den <b>Kamera-Knopf</b> öffnet sich „GoKart · Standortfotos“.')]
    f += OL('Fläche (Standort) wählen – Liste, GPS oder Karte.',
            '„<b>Foto aufnehmen – &lt;Fläche&gt;</b>“ antippen; die Kamera-App öffnet sich.',
            'Das Bild landet unter ' + c('fotos/gokart_&lt;Fläche&gt;_&lt;Datum_Uhrzeit&gt;.jpg') + ' im Projektordner, '
            'wird auf max. 1600 px (längste Seite) verkleinert und mit Zeitpunkt und – falls verfügbar – GPS-Position '
            'eingetragen.',
            'Kommentar tippen oder diktieren → <b>Kommentar speichern</b> (oder Enter).',
            '<b>Foto entfernen</b> (mit „Sicher?“) löscht nur den Eintrag; die Datei bleibt in ' + c('fotos/') + '.')
    f += [P('Am PC zeigt GoKart Desktop die Fotos der aktiven Fläche als Leiste: anklicken = Vorschau und Kommentar '
            '(auch per Sprache), Doppelklick = Bild in voller Größe.')]
    f += BOX('hinweis', 'Die Tabelle ' + c('fotos') + ' legt der Einrichten-Dialog an, sobald das Modul '
             '<b>Standortfotos</b> gewählt ist (ebenso das Build-Skript und abgleich.py). Meldet QField „Fototabelle '
             'fehlt“, am PC einrichten, speichern und neu verpacken.')
    return f


def k10_suche():
    f = H1('10 So funktioniert die Artensuche')
    f += OL('<b>Normalisieren</b>: Kleinschreibung, ä→a, ß→ss, Leer- und Bindestriche entfernen – „Stiel Eiche“ = '
            '„Stiel-Eiche“.',
            '<b>Stufen</b>: exakt → Wortanfang → enthalten.',
            '<b>Kölner Phonetik</b> gegen Hör- und Erkennungsfehler („kwerkus robur“ → Quercus robur).',
            '<b>Levenshtein-Distanz</b> bei Tippfehlern.',
            '<b>Gewichtung</b>: eigenes Synonym > deutscher Name > wissenschaftlicher Name > botanisches Synonym; '
            'bei Gleichstand Art vor Unterart vor Aggregat vor Gattung.')
    f += H2('Namensbestand erweitern')
    f += UL(c('zusatznamen.csv') + ' – zusätzliche Namen (' + c('wissenschaftlicher_name;name') + '), beim Bauen übernommen.',
            c('zusatztaxa.csv') + ' – fehlende Taxa (z. B. Moose), taxon_id ab 90001 fest vergeben.',
            'In ein bestehendes GeoPackage einspielen (Erfassungen bleiben, Sicherung wird angelegt):')
    f += [CODE('python3 qfield/werkzeuge/zusatztaxa_einspielen.py <projekt.gpkg> [zusatztaxa.csv]')]
    return f


def k11_zurueck():
    f = H1('11 Daten zurück an den PC')
    f += [P('Erfasst wird auf dem Gerät in die GeoPackage im Projektordner. Für den Rückweg den Projektordner bzw. ein '
            'Zip vom Gerät holen (USB, Telegram, QField „Projektordner teilen/exportieren“).')]
    f += H2('Abgleich PC ↔ Tablet (abgleich.py)')
    f += [P('Gleicht Artnachweise, Biotop-Zuordnungen, Fotos und eigene Synonyme ab. QGIS und QField vorher schließen.')]
    f += [CODE('''# nur Unterschiede anzeigen
python3 qfield/werkzeuge/abgleich.py <PC-Projekt .qgs|Ordner> <Tablet-Export .zip|Ordner>
# fehlende Einträge auf BEIDEN Seiten ergänzen
python3 qfield/werkzeuge/abgleich.py <PC> <Tablet> --ausfuehren''')]
    f += UL('PC-Projekt wird direkt aktualisiert (vorher Sicherung ' + c('*.bak') + '); fürs Tablet entsteht ' +
            c('&lt;Tablet&gt;_abgleich_&lt;Datum&gt;.zip') + ' samt aktuellem Plugin (abschalten: ' +
            c('--ohne-plugin') + ').',
            'Eindeutig sind: Nachweis = Fläche + taxon_id; Biotop = Fläche + Schlüssel + Code; Foto = Dateiname.',
            'Bemerkungen/Kommentare/Rolle werden nur ergänzt, nie überschrieben; Konflikte werden gemeldet.',
            'Gelöschte Einträge erkennt das Skript nicht – ausschließen mit ' + c('--weglassen W-34:68005') + ', ' +
            c('--biotop-weglassen W-34:SH:WMy') + ', ' + c('--foto-weglassen fotos/&lt;Datei&gt;.jpg') + '.',
            'Biotop-Katalog und geltender Schlüssel kommen immer vom PC.')
    f += BOX('achtung', f'abgleich.py liest <b>.qgs</b>-Projekte. Ein PC-Projekt im Format <b>.qgz</b> (z. B. '
             f'{c("kobm.qgz")}) einmal über <i>Projekt → Speichern unter…</i> zusätzlich als .qgs ablegen und dieses '
             'angeben – oder den Rückweg über QField Sync nehmen (unten).')
    f += H2('Rückweg mit QField Sync')
    f += [P('Bei Projekten, die mit „Für QField verpacken“ erzeugt wurden: den Projektordner vom Gerät zurück auf den PC '
            'kopieren, in QGIS das <b>Originalprojekt</b> öffnen und den <b>zweiten Würfel „Von QField '
            'synchronisieren“</b> wählen, dann den zurückgeholten Ordner angeben. Welche Layer dabei zurückgeschrieben '
            'werden, steuert die Layer-Einstellung in QField Sync (Werkzeug-Symbol „Projekt konfigurieren“).')]
    f += BOX('hinweis', 'Der Rückweg über QField Sync ist mit den GoKart-Tabellen (artnachweise, biotopzuordnung, fotos) '
             'noch nicht systematisch getestet. Vor dem ersten echten Einsatz einmal mit einer Testerfassung '
             'ausprobieren und das Ergebnis im GoKart-Panel prüfen.')
    f += H2('Artenliste je Fläche (artenliste_export.py)')
    f += [CODE('''python3 qfield/werkzeuge/artenliste_export.py ~/Dokumente/kobm_2026-10-27.zip
python3 qfield/werkzeuge/artenliste_export.py <Projekt> -o ~/Gutachten/artenliste -t "Artenliste je Fläche"''')]
    f += [P('Erzeugt eine druckbare HTML-Datei (im Browser als PDF speicherbar) und eine CSV; liest nur, braucht kein '
            'QGIS. Im Desktop-Plugin: <b>Export (CSV)</b> und <b>Artenliste je Fläche</b>.')]
    return f


def k12_desktop():
    f = H1('12 GoKart Desktop im Überblick')
    f += [P('Das Panel „GoKart – Pflanzenkartierung“ (rechts in QGIS) zeigt – je nach Modulen – von oben nach unten:')]
    f += TAB(['Bereich', 'Funktion'], [
        ['Aktive Fläche', 'Auswahlliste; <b>Flächen laden</b>, <b>Auswahl aus Karte</b> (markierte Fläche '
         'übernehmen), <b>Einrichten…</b>'],
        ['Pflanzenart suchen / einsprechen', 'Suche wie in QField, <b>● Sprechen</b> (Vosk), <b>Art speichern</b>, '
         'erfasste Arten, markierte Art löschen'],
        ['Biotoptypen dieser Fläche', 'Code/Name suchen oder sprechen, <b>Als Hauptbiotop</b> / <b>Als Nebenbiotop</b>, '
         'Haupt ↔ Neben, Entfernen'],
        ['Standortfotos', 'Fotoleiste der Fläche, Vorschau, Kommentar tippen/sprechen'],
        ['Export', '<b>Export (CSV)</b> der Artnachweise, <b>Artenliste je Fläche</b> (HTML/CSV)'],
    ], [48, 122])
    f += H2('Spracheingabe am PC (optional, offline)')
    f += UL('Linux: ' + c('python3 -m venv ~/gokart-venv &amp;&amp; ~/gokart-venv/bin/pip install vosk sounddevice'),
            'Windows: OSGeo4W-Shell als Administrator → ' + c('python -m pip install vosk sounddevice'),
            'Deutsches Vosk-Modell (z. B. vosk-model-small-de-0.15) entpacken; beim ersten Klick auf <b>● Sprechen</b> '
            'den Ordner wählen.')
    f += H2('Weitergabe an Kartierer/innen')
    f += UL(c(f'GoKart_Desktop_{DESKTOP}.zip') + ' (Plugin) und eine leere Vorlage ' + c('gokart.gpkg') +
            ' (Build mit ' + c('--leer --crs EPSG:25832') + ') weitergeben; die Flächen bringt jede/r selbst mit.',
            'Kurzanleitung für Empfänger: ' + c('qgis_plugin/gokart_desktop/LIESMICH.txt') + '.')
    return f


def k13_fehler():
    f = H1('13 Fehlerbehebung')
    f += H2('Am PC (QGIS)')
    f += TAB(['Symptom / Meldung', 'Ursache', 'Lösung'], [
        ['⚠ Feldtypen passen nicht (integer64 ↔ string)', 'Schlüsselfeld ist eine Zahl, Verweis flaeche_id ist Text',
         'Textfeld per Feldrechner anlegen (' + c('to_string(…)') + ') und als Schlüssel wählen (Kapitel 4)'],
        ['Neues Feld fehlt im Dropdown „Schlüsselfeld“', 'Bearbeitung nicht gespeichert, Feld im <b>anderen</b> '
         'Flächenlayer angelegt, oder Dialog war schon offen', 'Bearbeitung speichern; richtigen Layer im Dialog wählen '
         '(Layereigenschaften → Felder prüfen); Dialog neu öffnen'],
        ['„Verweis auf Fläche“ steht auf einem Artnamen-Feld', 'Feld versehentlich umgestellt', 'immer '
         + c('flaeche_id') + ' wählen'],
        ['„Bitte mindestens eine Erfassung wählen“', 'alle Module abgewählt', 'mind. ein Häkchen unter „Erfassen“'],
        ['„Fotos und Biotoptypen brauchen eine GeoPackage“', 'Artnachweis-Layer liegt nicht in einer .gpkg',
         'GoKart-GeoPackage einbinden und deren artnachweise wählen'],
        ['Biotop: „Katalog … fehlt“ / Schlüssel leer', 'Kataloge nicht eingespielt', '<b>Kataloge einspielen / '
         'aktualisieren</b>, dann Schlüssel wählen'],
        ['Einstellungen kommen in QField nicht an', 'Projekt nicht gespeichert („*“ im Titel)', 'Strg+S, neu '
         'verpacken'],
        ['„?“ neben Layern in der Layerliste', 'Layer ohne KBS', 'KBS setzen (Rechtsklick → Layer-KBS)'],
        ['Erfassungen nach Neustart von QGIS weg', 'GeoPackage auf NTFS unter Linux (WAL)', 'ext4 nutzen oder '
         + c('walForSqlite3') + ' = false'],
        ['QField-Sync-Fenster erscheint nicht', 'Fenster hinter QGIS', 'Alt+Tab bzw. QGIS minimieren'],
    ], [50, 52, 68])
    f += H2('Im Gelände (QField)')
    f += TAB(['Symptom / Meldung', 'Ursache', 'Lösung'], [
        ['Kein GoKart-Knopf', 'QML-Name passt nicht zur .qgs, Plugin abgelehnt, Dateien fehlen',
         c('qfield_paket.py') + ' benutzen (benennt richtig); Projekt neu öffnen, Plugin erlauben'],
        ['Ein Knopf fehlt (z. B. Arten)', 'Modul im Projekt abgewählt (' + c('gokart_module') + ')',
         'gewollt – sonst am PC unter „Erfassen“ anhaken, speichern, neu übertragen'],
        ['„gokart_module enthält keine bekannte Erfassung“', 'Variable von Hand falsch gesetzt',
         'nur ' + c('arten') + ', ' + c('fotos') + ', ' + c('biotope') + ' verwenden – am besten per Einrichten…'],
        ['„QField-API nicht gefunden – Plugin inaktiv“', 'QField zu alt', 'QField 4.x installieren'],
        ['Diagnose: „Flächen=FEHLT“ / „Nachweise=FEHLT“', 'Projektvariablen fehlen, Layer umbenannt',
         'am PC Einrichten…, speichern, neu übertragen'],
        ['„Biotop-Tabellen fehlen …“', 'biotoptypen/biotopzuordnung nicht im Projekt', 'am PC Modul Biotoptypen '
         'wählen bzw. Kataloge einspielen, neu verpacken'],
        ['„Fototabelle fehlt …“', 'Tabelle fotos nicht im Projekt', 'am PC Modul Standortfotos wählen, neu verpacken'],
        ['„Keine gültige GPS-Position“', 'kein Fix oder Standort nicht freigegeben', 'Positionierung in QField '
         'aktivieren; ersatzweise Karte oder Liste'],
        ['„Keine Fläche per GPS gefunden“', 'Position außerhalb aller Flächen oder KBS falsch', 'KBS der Flächen '
         'prüfen; Fläche aus der Liste wählen'],
        ['Fläche nicht in der Liste', 'kein Schlüsselwert / kein Anzeigename', 'Schlüssel pflegen; „Unbenannte '
         'Flächen anzeigen“'],
        ['„Speichern fehlgeschlagen – Details unten“', 'Layer schreibgeschützt, Datei gesperrt, Feldtyp unpassend',
         'Diagnosezeile lesen; Schlüssel ↔ Verweis prüfen (Text ↔ Zahl)'],
        ['„… bereits erfasst“', 'gleiche Art / gleicher Biotoptyp schon auf der Fläche', 'kein Fehler – Duplikatschutz'],
        ['Diktat erkennt Namen schlecht', 'Spracherkennung der Tastatur', 'deutschen Namen sprechen, Fehlhörungen als '
         'Synonym merken; Biotopcodes buchstabieren'],
        ['Gelöschtes kommt nach Abgleich wieder', 'Abgleich ist eine Vereinigung', c('--weglassen') + ', ' +
         c('--biotop-weglassen') + ', ' + c('--foto-weglassen')],
        ['Dialog bei Tastatur zu eng', 'kleines Display', 'Gerät quer halten oder Tablet nutzen'],
    ], [50, 52, 68])
    f += H2('Tests am PC')
    f += [CODE('''python3 qfield/test/testdaten_export.py qfield_projekt/gokart.gpkg testdaten.json
node qfield/test/test_suche.js testdaten.json
node qfield/test/test_biotop.js
QT_QPA_PLATFORM=offscreen python3 qfield/test/qml_harness.py qfield_projekt_kopie''')]
    f += BOX('achtung', 'Die qml_harness-Skripte simulieren QField und schreiben ins GeoPackage – nur mit einer Kopie.')
    f += H2('Offene Punkte')
    f += UL('QField 3.x-Fallback ungetestet; iPad-Betrieb noch zu bestätigen.',
            'Rückweg über QField Sync mit den GoKart-Tabellen testen; abgleich.py für .qgz-Projekte.',
            'Kataloge SH (Hauptgruppe S), NI (außer Wälder), HH, HB, MV und BUND ergänzen.',
            'Übernahme vorhandener Biotopcodes aus Flächen-Shapes (z. B. Feld CODE) als Hauptbiotop.',
            'Dialoghöhe bei eingeblendeter Bildschirmtastatur auf kleinen Displays.')
    return f


def kurzreferenz():
    f = H1('Kurzreferenz')
    f += H2('Am PC – einmal je Projekt')
    f += TAB(['#', 'Aktion'], [
        ['1', 'Flächenlayer + GoKart-GeoPackage im Projekt; nur <b>ein</b> Flächenlayer, Schlüssel als Text'],
        ['2', '<b>Einrichten…</b> → Module anhaken → Flächen, Schlüssel, Anzeigefeld → Biotop-Schlüssel → OK'],
        ['3', '<b>Strg+S</b>'],
        ['4', 'QField Sync → <b>Für QField verpacken</b>'],
        ['5', c('python3 qfield/werkzeuge/qfield_paket.py ~/QField/export/&lt;Projekt&gt;') + ' → Zip aufs Gerät'],
    ], [10, 160])
    f += H2('Im Gelände')
    f += TAB(['#', 'Aktion'], [
        ['1', 'Projekt öffnen, Plugin erlauben'],
        ['2', 'Knopf antippen → Fläche per GPS / Karte / Liste'],
        ['3', '<b>Arten</b>: Name sprechen → Vorschlag prüfen → Enter; Fehlhörung als Synonym merken'],
        ['4', '<b>Biotop</b>: Code/Name sprechen (auch buchstabiert) → Hauptbiotop / Nebenbiotop'],
        ['5', '<b>Kamera</b>: Foto → Kommentar diktieren → speichern'],
        ['6', 'Zu Hause: Export holen → abgleich.py bzw. QField Sync → Artenliste'],
    ], [10, 160])
    return f


def main():
    doc = Doc(ZIEL)
    story = titel() + inhalt()
    for k in (k1_ueberblick, k2_voraussetzungen, k3_datenmodell, k4_vorbereiten, k5_module, k6_uebertragen,
              k7_arten, k8_biotope, k9_fotos, k10_suche, k11_zurueck, k12_desktop, k13_fehler, kurzreferenz):
        story += k()
    doc.multiBuild(story)
    print(f'✔ {ZIEL}')


if __name__ == '__main__':
    main()
