#!/usr/bin/env python3
"""GoKart – erzeugt das QField-Projekt (GeoPackage + QGIS-Projekt) aus GoKart_Pflanzen.sqlite.

Aufruf (Ubuntu mit installiertem QGIS):
    python3 build_gokart_projekt.py \
        --db /media/emu/daten/gpb/GoKart/pflanzen/GoKart_Pflanzen_Datenbank/GoKart_Pflanzen.sqlite \
        --ziel /media/emu/daten/gpb/GoKart/qfield_projekt

Ergebnis im Zielordner:
    gokart.gpkg   Flächen, Taxa, Suchnamen, eigene Synonyme, Artnachweise
    gokart.qgs    QGIS-/QField-Projekt (Relation Fläche -> Artnachweise, Auswahllisten)
    gokart.qml    Projekt-Plugin (wird separat aus plugin/ kopiert, gleicher Name wie .qgs!)

Vorhandene Daten werden NICHT überschrieben, außer mit --neu.
"""
import argparse
import os
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gokart_namen import normalisieren, varianten  # noqa: E402

from qgis.core import (  # noqa: E402
    QgsApplication, QgsCoordinateReferenceSystem, QgsDefaultValue, QgsEditFormConfig,
    QgsEditorWidgetSetup, QgsFeature, QgsField, QgsFieldConstraints, QgsFields,
    QgsGeometry, QgsProject, QgsRasterLayer, QgsRelation, QgsVectorFileWriter,
    QgsVectorLayer, QgsWkbTypes, QgsAttributeEditorContainer, QgsAttributeEditorField,
    QgsAttributeEditorRelation, QgsPalLayerSettings, QgsVectorLayerSimpleLabeling,
    QgsFillSymbol, QgsSingleSymbolRenderer, QgsCoordinateTransformContext,
)
from qgis.PyQt.QtCore import QVariant  # noqa: E402

CRS = 'EPSG:25833'   # ETRS89 / UTM 33N – Berlin/Brandenburg

# Drei Testflächen im Großen Tiergarten (Berlin), Rechteck: Mittelpunkt E/N, Breite, Höhe [m]
TESTFLAECHEN = [
    ('F-001', 'Testfläche Tiergarten Ost', 388400, 5819380, 60, 40),
    ('F-002', 'Testfläche Tiergarten Süd', 387150, 5819300, 80, 50),
    ('F-003', 'Testfläche Tiergarten West', 386650, 5820030, 70, 70),
]


def feld(name, typ, laenge=0):
    return QgsField(name, typ, len=laenge)


def schreiben(layer, gpkg, neu_datei):
    opt = QgsVectorFileWriter.SaveVectorOptions()
    opt.driverName = 'GPKG'
    opt.layerName = layer.name()
    opt.fileEncoding = 'UTF-8'
    opt.actionOnExistingFile = (QgsVectorFileWriter.CreateOrOverwriteFile if neu_datei
                                else QgsVectorFileWriter.CreateOrOverwriteLayer)
    err = QgsVectorFileWriter.writeAsVectorFormatV3(layer, str(gpkg), QgsCoordinateTransformContext(), opt)
    if err[0] != QgsVectorFileWriter.NoError:
        raise SystemExit(f'Fehler beim Schreiben von {layer.name()}: {err}')


def speicher_layer(name, felder, geom='None'):
    uri = f'{geom}?crs={CRS}' if geom != 'None' else 'None'
    lyr = QgsVectorLayer(uri, name, 'memory')
    lyr.dataProvider().addAttributes(felder)
    lyr.updateFields()
    return lyr


def germansl_namen(pfad):
    """{wissenschaftlicher Name: [Volksnamen]} aus GermanSL (nur akzeptierte Namen)."""
    if not pfad or not Path(pfad).is_file():
        return {}
    g = sqlite3.connect(f'file:{pfad}?mode=ro', uri=True)
    d = {}
    for name, vn in g.execute('SELECT TaxonName, VernacularName FROM GermanSL '
                              'WHERE SYNONYM = 0 AND VernacularName IS NOT NULL AND VernacularName <> \'\''):
        d.setdefault(name.strip(), []).append(vn.strip())
    g.close()
    return d


def zusatz_namen(pfad):
    """{wissenschaftlicher Name: [Namen]} aus zusatznamen.csv (Spalten: wissenschaftlicher_name;name)."""
    d = {}
    if pfad and Path(pfad).is_file():
        import csv
        with open(pfad, encoding='utf-8') as fh:
            for zeile in csv.DictReader((l for l in fh if not l.startswith('#')), delimiter=';'):
                w, n = (zeile.get('wissenschaftlicher_name') or '').strip(), (zeile.get('name') or '').strip()
                if w and n:
                    d.setdefault(w, []).append(n)
    return d


def zusatz_taxa(pfad):
    """Zusätzliche Taxa aus zusatztaxa.csv (z. B. Moose, die in der Quell-DB fehlen).
    Spalten: taxon_id;wissenschaftlicher_name;deutscher_name;rang;autor_name;weitere_namen (mit | getrennt)
    Liefert [(taxon_id, wiss, deutsch, rang, autor, [weitere_namen])]."""
    liste = []
    if not pfad or not Path(pfad).is_file():
        return liste
    import csv
    gesehen = set()
    with open(pfad, encoding='utf-8') as fh:
        for nr, zeile in enumerate(csv.DictReader((l for l in fh if not l.startswith('#')), delimiter=';'), 1):
            wiss = (zeile.get('wissenschaftlicher_name') or '').strip()
            tid = (zeile.get('taxon_id') or '').strip()
            if not wiss:
                continue
            if not tid.isdigit():
                raise SystemExit(f'{pfad}: Zeile {nr} ({wiss}) hat keine gültige taxon_id')
            if int(tid) in gesehen:
                raise SystemExit(f'{pfad}: taxon_id {tid} doppelt vergeben')
            gesehen.add(int(tid))
            weitere = [n.strip() for n in (zeile.get('weitere_namen') or '').split('|') if n.strip()]
            liste.append((int(tid), wiss, (zeile.get('deutscher_name') or '').strip() or None,
                          (zeile.get('rang') or 'SPE').strip(), (zeile.get('autor_name') or '').strip() or None,
                          weitere))
    return liste


def flaechen_quelle(pfad, layername=None):
    uri = str(pfad) + (f'|layername={layername}' if layername else '')
    src = QgsVectorLayer(uri, Path(pfad).name + (f' ({layername})' if layername else ''), 'ogr')
    if not src.isValid():
        raise SystemExit(f'Flächen-Datei nicht lesbar: {uri}')
    if QgsWkbTypes.geometryType(src.wkbType()) != QgsWkbTypes.PolygonGeometry:
        raise SystemExit(f'{uri} enthält keine Polygone.')
    return src


def felder_anzeigen(src):
    print(f'\nFelder in {src.source()}  ({src.featureCount()} Flächen, {src.crs().authid()}):')
    beispiel = next(src.getFeatures(), None)
    for f in src.fields():
        wert = beispiel[f.name()] if beispiel else ''
        print(f'  {f.name():30} {f.typeName():12} z. B. {wert}')


def id_text(wert):
    """Feldwert als ID-Text; 2773.0 -> '2773'."""
    if wert is None or str(wert) == 'NULL':
        return ''
    if isinstance(wert, float) and wert.is_integer():
        return str(int(wert))
    return str(wert).strip()


def flaechen_importieren(fl, src, id_feld=None, name_feld=None, id_auto=None):
    """Übernimmt Polygone aus src nach fl.
    flaeche_id = Wert aus id_feld (eindeutig gemacht) oder bei id_auto fortlaufend: <Präfix>0001 …"""
    namen = src.fields().names()
    for n in (id_feld, name_feld):
        if n and n not in namen:
            felder_anzeigen(src)
            raise SystemExit(f'\nFeld "{n}" gibt es nicht. Bitte eines der obigen Felder angeben.')
    gesehen, feats, doppelt, leer = {}, [], 0, 0
    breite = max(3, len(str(src.featureCount())))
    nummer = 0
    for q in sorted(src.getFeatures(), key=lambda x: x.id()):
        if not q.hasGeometry():
            continue
        nummer += 1
        fid = f'{id_auto}{nummer:0{breite}d}' if id_auto is not None else id_text(q[id_feld])
        if not fid:
            leer += 1
            fid = f'OHNE-ID-{q.id()}'
        if fid in gesehen:
            doppelt += 1
            gesehen[fid] += 1
            fid = f'{fid}-{gesehen[fid]}'
        else:
            gesehen[fid] = 1
        f = QgsFeature(fl.fields())
        name = q[name_feld] if name_feld else None
        f.setAttributes([fid, id_text(name) or None, None])
        g = q.geometry()
        g.convertToMultiType()
        f.setGeometry(g)
        feats.append(f)
    fl.dataProvider().addFeatures(feats)
    print(f'Flächen: {len(feats)} übernommen aus {src.name()}'
          + (f', {doppelt} doppelte IDs mit Suffix -2, -3 …' if doppelt else '')
          + (f', {leer} ohne ID (OHNE-ID-…)' if leer else ''))


def gpkg_erzeugen(db, gpkg, germansl=None, zusatz=None, flaechen=None, zusatztaxa=None):
    global CRS
    gsl = germansl_namen(germansl)
    zus = zusatz_namen(zusatz)
    ztx = zusatz_taxa(zusatztaxa)
    quelle = sqlite3.connect(f'file:{db}?mode=ro', uri=True)
    taxa = quelle.execute('SELECT taxon_id, wissenschaftlicher_name, deutscher_name, rang, akzeptierter_name FROM taxon').fetchall()
    namen = quelle.execute('SELECT taxon_id, wissenschaftlicher_name, synonym_status FROM namen').fetchall()
    eigene = quelle.execute('SELECT taxon_id, synonym, angelegt_am FROM eigene_synonyme').fetchall()
    erfasst = quelle.execute('SELECT flaeche_id, taxon_id, erfasst_am, bemerkung, original_spracheingabe FROM flaechen_arten').fetchall()
    quelle.close()

    # --- Flächen (eigene Kartierflächen oder Testflächen)
    if flaechen:
        CRS = flaechen['quelle'].crs().authid() or CRS
    fl = speicher_layer('flaechen', [feld('flaeche_id', QVariant.String, 40), feld('name', QVariant.String, 200),
                                     feld('bemerkung', QVariant.String, 500)],
                        'MultiPolygon' if flaechen else 'Polygon')
    if flaechen:
        flaechen_importieren(fl, flaechen['quelle'], flaechen.get('id_feld'), flaechen.get('name_feld'),
                             flaechen.get('id_auto'))
    feats = []
    for fid, name, e, n, b, h in ([] if flaechen else TESTFLAECHEN):
        f = QgsFeature(fl.fields())
        f.setAttributes([fid, name, 'Testfläche – durch echte Kartierflächen ersetzen'])
        f.setGeometry(QgsGeometry.fromWkt(
            f'POLYGON(({e-b/2} {n-h/2},{e+b/2} {n-h/2},{e+b/2} {n+h/2},{e-b/2} {n+h/2},{e-b/2} {n-h/2}))'))
        feats.append(f)
    fl.dataProvider().addFeatures(feats)
    schreiben(fl, gpkg, True)

    # --- Taxa + Suchnamen
    tx = speicher_layer('taxon', [feld('taxon_id', QVariant.Int), feld('wissenschaftlicher_name', QVariant.String),
                                  feld('deutscher_name', QVariant.String), feld('anzeige_name', QVariant.String),
                                  feld('rang', QVariant.String, 5), feld('autor_name', QVariant.String)])
    sn = speicher_layer('suchnamen', [feld('taxon_id', QVariant.Int), feld('name', QVariant.String),
                                      feld('schluessel', QVariant.String), feld('art', QVariant.String, 20)])
    tx_feats, sn_feats, ids = [], [], set()
    stat = {'deutsch': 0, 'wissenschaftlich': 0, 'synonym': 0, 'zusatz': 0}
    ergaenzt = 0

    def suchname(tid, name, art):
        k = normalisieren(name)
        if not k:
            return
        f = QgsFeature(sn.fields())
        f.setAttributes([tid, name, k, art])
        sn_feats.append(f)
        stat[art] += 1

    for tid, wiss, deutsch, rang, voll in taxa:
        anzeige, var = varianten(deutsch)
        # GermanSL-Volksnamen ergänzen (füllt Lücken der BfN-Liste, z. B. Feld-Ahorn)
        for vn in gsl.get(wiss, []):
            a2, v2 = varianten(vn)
            if not anzeige and a2:
                anzeige = a2
                ergaenzt += 1
            var += [v for v in v2 if v not in var]
        f = QgsFeature(tx.fields())
        f.setAttributes([tid, wiss, deutsch, anzeige or wiss, rang, voll])
        tx_feats.append(f)
        ids.add(tid)
        for v in var:
            suchname(tid, v, 'deutsch')
        for n in zus.get(wiss, []):
            suchname(tid, n, 'zusatz')

    # --- Zusätzliche Taxa (zusatztaxa.csv), z. B. Moose
    vorhandene_namen = {t[1] for t in taxa}
    neu_taxa = 0
    for tid, wiss, deutsch, rang, autor, weitere in ztx:
        if wiss in vorhandene_namen:
            print(f'Zusatztaxon übersprungen (schon in der Datenbank): {wiss}')
            continue
        if tid in ids:
            raise SystemExit(f'zusatztaxa.csv: taxon_id {tid} ({wiss}) ist in der Datenbank schon vergeben')
        anzeige, var = varianten(deutsch)
        f = QgsFeature(tx.fields())
        f.setAttributes([tid, wiss, deutsch, anzeige or wiss, rang, autor])
        tx_feats.append(f)
        ids.add(tid)
        taxa.append((tid, wiss, anzeige or deutsch, rang, autor))   # für Artnachweise-Zuordnung unten
        neu_taxa += 1
        for v in var:
            suchname(tid, v, 'deutsch')
        suchname(tid, wiss, 'wissenschaftlich')
        for n in weitere + zus.get(wiss, []):
            suchname(tid, n, 'zusatz')
    gesehen = set()
    for tid, wiss, status in namen:
        if tid not in ids or not wiss:
            continue
        art = 'wissenschaftlich' if str(status) == '1' else 'synonym'
        k = (tid, normalisieren(wiss))
        if k in gesehen:
            continue
        gesehen.add(k)
        suchname(tid, wiss, art)
    tx.dataProvider().addFeatures(tx_feats)
    sn.dataProvider().addFeatures(sn_feats)
    schreiben(tx, gpkg, False)
    schreiben(sn, gpkg, False)

    # --- Eigene Synonyme (werden in QField vom Plugin ergänzt)
    es = speicher_layer('eigene_synonyme', [feld('taxon_id', QVariant.Int), feld('synonym', QVariant.String),
                                            feld('schluessel', QVariant.String), feld('angelegt_am', QVariant.String)])
    ef = []
    for tid, syn, am in eigene:
        f = QgsFeature(es.fields())
        f.setAttributes([tid, syn, normalisieren(syn), am])
        ef.append(f)
    es.dataProvider().addFeatures(ef)
    schreiben(es, gpkg, False)

    # --- Artnachweise (Erfassungen je Fläche)
    an = speicher_layer('artnachweise', [
        feld('flaeche_id', QVariant.String, 20), feld('taxon_id', QVariant.Int),
        feld('wissenschaftlicher_name', QVariant.String), feld('deutscher_name', QVariant.String),
        feld('original_eingabe', QVariant.String), feld('erfasst_am', QVariant.String),
        feld('bemerkung', QVariant.String, 500)])
    af = []
    tx_map = {t[0]: t for t in taxa}
    for flid, tid, am, bem, orig in erfasst:
        t = tx_map.get(tid)
        f = QgsFeature(an.fields())
        f.setAttributes([flid, tid, t[1] if t else None, t[2] if t else None, orig, am, bem])
        af.append(f)
    an.dataProvider().addFeatures(af)
    schreiben(an, gpkg, False)

    # Indizes für schnelle Abfragen in QField
    con = sqlite3.connect(gpkg)
    con.executescript('''
        CREATE INDEX IF NOT EXISTS idx_suchnamen_schluessel ON suchnamen(schluessel);
        CREATE INDEX IF NOT EXISTS idx_taxon_id ON taxon(taxon_id);
        CREATE INDEX IF NOT EXISTS idx_artnachweise_flaeche ON artnachweise(flaeche_id);
        CREATE INDEX IF NOT EXISTS idx_flaechen_id ON flaechen(flaeche_id);
    ''')
    con.commit()
    con.close()
    print(f'GermanSL: {ergaenzt} fehlende deutsche Namen ergänzt')
    print(f'Zusatztaxa: {neu_taxa} Taxa ergänzt')
    print(f'GeoPackage: {len(tx_feats)} Taxa, Suchnamen {stat}, {len(ef)} eigene Synonyme, {len(af)} Artnachweise')


def value_relation(layer, feldname, ziel, schluessel, wert, filter_ausdruck=''):
    layer.setEditorWidgetSetup(layer.fields().indexFromName(feldname), QgsEditorWidgetSetup('ValueRelation', {
        'Layer': ziel.id(), 'LayerName': ziel.name(), 'LayerSource': ziel.source(), 'LayerProviderName': 'ogr',
        'Key': schluessel, 'Value': wert, 'AllowNull': False, 'OrderByValue': True,
        'UseCompleter': True, 'AllowMulti': False, 'FilterExpression': filter_ausdruck}))


def ausblenden(layer, *felder):
    for f in felder:
        layer.setEditorWidgetSetup(layer.fields().indexFromName(f), QgsEditorWidgetSetup('Hidden', {}))


def projekt_erzeugen(ziel, gpkg):
    p = QgsProject.instance()
    p.clear()
    p.setCrs(QgsCoordinateReferenceSystem(CRS))
    p.setTitle('GoKart – Pflanzenkartierung')

    def lade(name):
        lyr = QgsVectorLayer(f'{gpkg}|layername={name}', name, 'ogr')
        if not lyr.isValid():
            raise SystemExit(f'Layer {name} ungültig')
        return lyr

    fl, an, es, tx, sn = (lade(n) for n in ('flaechen', 'artnachweise', 'eigene_synonyme', 'taxon', 'suchnamen'))

    root = p.layerTreeRoot()
    osm = QgsRasterLayer('type=xyz&url=https://tile.openstreetmap.org/{z}/{x}/{y}.png&zmax=19&zmin=0',
                         'OpenStreetMap (online)', 'wms')
    for lyr in (fl, an, es):
        p.addMapLayer(lyr)
    ref = root.addGroup('Referenz (nicht bearbeiten)')
    for lyr in (tx, sn):
        p.addMapLayer(lyr, False)
        ref.addLayer(lyr)
        lyr.setReadOnly(True)
    ref.setExpanded(False)
    if osm.isValid():
        p.addMapLayer(osm, False)
        root.addLayer(osm)

    # Darstellung Flächen
    fl.setRenderer(QgsSingleSymbolRenderer(QgsFillSymbol.createSimple(
        {'color': '22,125,80,50', 'outline_color': '22,125,80,255', 'outline_width': '0.8'})))
    lab = QgsPalLayerSettings()
    lab.fieldName = 'flaeche_id'
    fl.setLabeling(QgsVectorLayerSimpleLabeling(lab))
    fl.setLabelsEnabled(True)
    fl.setDisplayExpression('"flaeche_id" || \' – \' || coalesce("name", \'\')')

    # Pflichtfeld + eindeutige Flächen-ID
    i = fl.fields().indexFromName('flaeche_id')
    fl.setConstraintExpression(i, '"flaeche_id" IS NOT NULL AND length("flaeche_id") > 0', 'Flächen-ID fehlt')
    fl.setFieldConstraint(i, QgsFieldConstraints.ConstraintUnique, QgsFieldConstraints.ConstraintStrengthHard)
    ausblenden(fl, 'fid')

    # Artnachweise-Formular
    value_relation(an, 'flaeche_id', fl, 'flaeche_id', 'flaeche_id')
    value_relation(an, 'taxon_id', tx, 'taxon_id', 'anzeige_name')
    ausblenden(an, 'fid')
    an.setDefaultValueDefinition(an.fields().indexFromName('erfasst_am'),
                                 QgsDefaultValue("format_date(now(), 'yyyy-MM-ddTHH:mm:ss')"))
    # Namen automatisch aus der Taxon-Tabelle übernehmen, falls im Formular erfasst
    an.setDefaultValueDefinition(an.fields().indexFromName('wissenschaftlicher_name'), QgsDefaultValue(
        "attribute(get_feature('taxon','taxon_id',\"taxon_id\"),'wissenschaftlicher_name')", True))
    an.setDefaultValueDefinition(an.fields().indexFromName('deutscher_name'), QgsDefaultValue(
        "attribute(get_feature('taxon','taxon_id',\"taxon_id\"),'anzeige_name')", True))
    an.setDisplayExpression('coalesce("deutscher_name", "wissenschaftlicher_name") || \' (\' || "flaeche_id" || \')\'')
    value_relation(es, 'taxon_id', tx, 'taxon_id', 'anzeige_name')
    ausblenden(es, 'fid', 'schluessel')
    es.setDisplayExpression('"synonym"')

    tx.setDisplayExpression('coalesce("anzeige_name", "wissenschaftlicher_name")')

    # Relation Fläche 1:n Artnachweise
    rel = QgsRelation()
    rel.setId('flaeche_artnachweise')
    rel.setName('Artnachweise')
    rel.setReferencedLayer(fl.id())
    rel.setReferencingLayer(an.id())
    rel.addFieldPair('flaeche_id', 'flaeche_id')
    if not rel.isValid():
        raise SystemExit('Relation ungültig: ' + rel.validationError())
    p.relationManager().addRelation(rel)

    # Drag&Drop-Formular der Fläche mit eingebetteter Artenliste
    cfg = fl.editFormConfig()
    cfg.setLayout(QgsEditFormConfig.TabLayout)
    cfg.clearTabs()
    tab = QgsAttributeEditorContainer('Fläche', cfg.invisibleRootContainer())
    tab.setIsGroupBox(False)
    for n in ('flaeche_id', 'name', 'bemerkung'):
        tab.addChildElement(QgsAttributeEditorField(n, fl.fields().indexFromName(n), tab))
    cfg.addTab(tab)
    tab2 = QgsAttributeEditorContainer('Arten', cfg.invisibleRootContainer())
    tab2.setIsGroupBox(False)
    tab2.addChildElement(QgsAttributeEditorRelation(rel, tab2))
    cfg.addTab(tab2)
    fl.setEditFormConfig(cfg)

    # Relative Pfade, damit der Ordner aufs Gerät kopiert werden kann
    p.writeEntry('Paths', 'Absolute', False)
    out = ziel / 'gokart.qgs'
    if not p.write(str(out)):
        raise SystemExit('Projekt konnte nicht gespeichert werden')
    print(f'Projekt: {out}')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--db', required=True, type=Path)
    ap.add_argument('--ziel', required=True, type=Path)
    ap.add_argument('--germansl', type=Path, help='germansl.sqlite (GermanSL 1.5) für zusätzliche deutsche Namen')
    ap.add_argument('--zusatz', type=Path, default=Path(__file__).resolve().parent / 'zusatznamen.csv',
                    help='CSV mit eigenen Zusatznamen (wissenschaftlicher_name;name)')
    ap.add_argument('--zusatztaxa', type=Path, default=Path(__file__).resolve().parent / 'zusatztaxa.csv',
                    help='CSV mit Taxa, die in der Quell-DB fehlen, z. B. Moose (siehe Kopf der Datei)')
    ap.add_argument('--plugin', type=Path, default=Path(__file__).resolve().parent.parent / 'plugin')
    ap.add_argument('--flaechen', type=Path, help='eigene Kartierflächen (GPKG/SHP/…, Polygone) statt Testflächen')
    ap.add_argument('--flaechen-layer', help='Layername innerhalb der Datei (bei GeoPackage mit mehreren Layern)')
    ap.add_argument('--id-feld', help='Feld mit der eindeutigen Flächen-ID; ohne Angabe werden die Felder angezeigt')
    ap.add_argument('--id-auto', metavar='PRÄFIX',
                    help='Flächen fortlaufend nummerieren statt --id-feld, z. B. --id-auto K6- ergibt K6-001, K6-002 …')
    ap.add_argument('--name-feld', help='optionales Feld für eine Flächenbezeichnung')
    ap.add_argument('--neu', action='store_true', help='vorhandenes gokart.gpkg überschreiben (Erfassungen gehen verloren!)')
    a = ap.parse_args()
    if not a.db.is_file():
        raise SystemExit(f'Datenbank nicht gefunden: {a.db}')
    if a.flaechen and not a.flaechen.is_file():
        raise SystemExit(f'Flächen-Datei nicht gefunden: {a.flaechen}')
    a.ziel.mkdir(parents=True, exist_ok=True)
    gpkg = a.ziel / 'gokart.gpkg'

    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    app = QgsApplication([], False)
    app.initQgis()
    flaechen = src = None
    try:
        if a.flaechen:
            src = flaechen_quelle(a.flaechen, a.flaechen_layer)
            if not a.id_feld and a.id_auto is None:
                felder_anzeigen(src)
                raise SystemExit('\nBitte mit --id-feld <Feldname> oder --id-auto <Präfix> (und optional --name-feld) '
                                 'erneut aufrufen.')
            flaechen = {'quelle': src, 'id_feld': a.id_feld, 'name_feld': a.name_feld, 'id_auto': a.id_auto}
        if gpkg.exists() and not a.neu:
            raise SystemExit(f'{gpkg} existiert bereits. Mit --neu überschreiben (vorher sichern!).')
        if gpkg.exists():
            sicherung = gpkg.with_name(f'gokart_{datetime.now():%Y%m%d_%H%M%S}.gpkg.bak')
            shutil.copy2(gpkg, sicherung)
            print(f'Sicherung: {sicherung}')
        gpkg_erzeugen(a.db, gpkg, a.germansl, a.zusatz, flaechen, a.zusatztaxa)
        projekt_erzeugen(a.ziel, gpkg)
    finally:
        flaechen = src = None          # Layer vor exitQgis freigeben, sonst Absturz beim Beenden
        import gc
        gc.collect()
        QgsProject.instance().clear()
        app.exitQgis()

    # Plugin neben das Projekt legen (Name muss dem .qgs entsprechen)
    if a.plugin.is_dir():
        shutil.copy2(a.plugin / 'gokart.qml', a.ziel / 'gokart.qml')
        shutil.copy2(a.plugin / 'gokart_suche.js', a.ziel / 'gokart_suche.js')
        if (a.plugin / 'gokart_icon.svg').exists():
            shutil.copy2(a.plugin / 'gokart_icon.svg', a.ziel / 'gokart_icon.svg')
        print('Plugin kopiert: gokart.qml, gokart_suche.js')


if __name__ == '__main__':
    main()
