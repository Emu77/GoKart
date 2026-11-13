// GoKart – QField-Projekt-Plugin: Pflanzenarten per Sprache/Tastatur suchen und einer Fläche zuordnen
// Datei MUSS so heißen wie das Projekt (GoKart_Wohnung_qfield.qgs -> GoKart_Wohnung_qfield.qml) und daneben liegen.
// Version 0.2: Layer/Felder kommen aus den Projektvariablen, die das Desktop-Plugin ("Einrichten…") setzt:
//   gokart_flaechen_layer (Layer-ID), gokart_flaechen_key, gokart_flaechen_label,
//   gokart_nachweis_layer (Layer-ID), gokart_nachweis_fk
// Version 0.3: Standortfotos über einen zweiten Knopf (Kamera) – Bilddateien unter fotos/, Einträge in der
//   Tabelle "fotos" (flaeche_id, datei, kommentar, aufgenommen_am, lon, lat). Tabelle/Layer legt abgleich.py an.
// Version 0.4: Biotoptypen über einen dritten Knopf – Schlüssel (Bund/Land) aus der Projektvariablen
//   gokart_biotop_schluessel, Katalog im Layer "biotoptypen", Erfassung im Layer "biotopzuordnung"
//   (flaeche_id, schluessel, code, name, rolle Haupt/Neben, …). Tabellen/Layer legt biotope_einspielen.py an.
// Version 0.5: Projektvariable gokart_module (z. B. "arten,biotope") legt fest, welche Knöpfe erscheinen –
//   gesetzt im Desktop-Plugin unter "Einrichten… → Erfassen". Fehlt sie, erscheinen alle drei (ältere Projekte).
// Version 0.6: Artnachweise mobil bearbeiten – Eintrag antippen bzw. "Bearbeiten" oder "Letzte Art korrigieren":
//   Art tauschen (gleiche Suche/Spracheingabe wie beim Erfassen), Fläche ändern, Bemerkung (auch per Diktat).
//   Gesetzt werden geaendert_am und – bei neuer Art oder Fläche – ersetzt (alte Schlüssel "Fläche:taxon_id",
//   kommagetrennt), damit abgleich.py den alten Eintrag auf der anderen Seite entfernt statt ihn zurückzuholen.
//   Fehlen die Felder (ältere Projekte), funktioniert das Bearbeiten trotzdem; abgleich.py legt sie an.
// Version 0.7: Punktaufnahmen – Arten an GPS-Punkten ohne Fläche (Modul "punkte" in gokart_module, Layer
//   aufnahme_punkte; Artnachweis bekommt punkt_id statt flaeche_id). Warnung bei schlechter GPS-Genauigkeit
//   (gokart_punkt_genauigkeit, Standard 10 m), Hinweis ab gokart_punkt_radius (Standard 25 m) Abstand zum Punkt.
//   Zusatzangaben je Art (deckung, anzahl, phaenologie): per Sprache („Calluna, Deckung drei, blühend“) und über
//   eine Schnellleiste nach dem Speichern – welche, legt gokart_zusatz fest (z. B. "deckung,phaenologie").
//   Tabelle/Spalten/Layer legen build_gokart_projekt.py, abgleich.py oder GoKart Desktop („Einrichten…“) an.
// Getestet gegen die API von QField 4.x; QField 3.x wird über einen Fallback unterstützt.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Controls.Material
import "gokart_suche.js" as Suche
import "gokart_biotop.js" as Biotop
import "gokart_zusatz.js" as Zusatz

Item {
    id: plugin

    // --- Zustand
    property var lu: null              // LayerUtils / QfLayerUtils
    property var fu: null              // FeatureUtils / QfFeatureUtils
    property var ecu: null             // ExpressionContextUtils (Projektvariablen)
    property var cfg: ({})             // Verknüpfung Fläche <-> Artnachweis
    property var index: null
    property bool laedt: false
    property var treffer: []
    property int auswahlIndex: -1
    property var flaechen: []          // [{ id, name }]
    property string aktiveFlaeche: ''
    property var artenDerFlaeche: []   // [{ fid, name, wiss, taxon_id, am, bemerkung, eingabe, ersetzt, geaendert }]
    property var bearbeitung: null     // Eintrag aus artenDerFlaeche, der gerade bearbeitet wird
    property string bearbeitFlaeche: ''   // Zielfläche beim Bearbeiten
    property string letzteMeldung: ''
    property string diagnose: ''         // letzter Speicher-Ablauf, wird im Dialog angezeigt
    property bool diagnoseFehler: false
    property var dateiUtils: null        // FileUtils / QfFileUtils (Bildgröße begrenzen)
    property var fotoQuelle: null        // laufende Kameraanfrage (Referenz halten!)
    property var fotoFuer: null          // { flaeche, lon, lat } des nächsten Fotos
    property var fotosDerFlaeche: []     // [{ fid, datei, kommentar, am, lon, lat }]
    readonly property int fotoMaxPixel: 1600   // längste Bildseite, hält Zips klein
    property var biotopIndex: null       // Suchindex des geltenden Schlüssels
    property string biotopSchluessel: '' // z. B. SH, NI, BUND
    property var biotopSchluesselListe: []   // [{ schluessel, name, anzahl, vollstaendig }]
    property var biotopTreffer: []
    property int biotopAuswahl: -1
    property var biotopeDerFlaeche: []   // [{ fid, schluessel, code, name, rolle }]
    property var erfassung: ({ arten: true, fotos: true, biotope: true, punkte: false })   // aus gokart_module
    property var gu: null                // GeometryUtils / QfGeometryUtils (Punktgeometrie)
    property var crsu: null              // CoordinateReferenceSystemUtils / QfCoordinateReferenceSystemUtils
    property string ortArt: 'flaeche'    // 'flaeche' oder 'punkt' – wo die nächste Art landet
    property string aktiverPunkt: ''     // punkt_id der aktiven Punktaufnahme
    property var punkte: []              // [{ id, am, hacc, quelle, x, y }] neueste zuerst
    property var punktCfg: ({ genauigkeit: 10, radius: 25 })
    property bool punktTrotzdem: false   // zweites Antippen übernimmt eine ungenaue Position
    property var gpsStand: ({ ok: false, hacc: -1, abstand: -1 })   // für die Anzeige im Punkt-Modus
    property var zusatzFelder: []        // aktive Zusatzangaben aus gokart_zusatz
    property var letzterNachweis: null   // zuletzt gespeicherter Eintrag – Ziel der Schnellleiste
    property string fadenkreuz: ''       // '' | 'neu' | 'verschieben' – Punkt per Fadenkreuz auf der Karte
    property string fadenkreuzInfo: ''   // Koordinate + Fläche unter dem Fadenkreuz (Anzeige)
    property string punktStatus: ''      // Ergebnis der letzten Punkt-Aktion (bleibt im Dialog stehen)
    property bool punktStatusFehler: false

    readonly property color gruen: '#167d50'
    readonly property color gruenHell: '#e6f6eb'

    // Umschalt-/Auswahlknopf mit eigenen Farben (unabhängig vom QField-Theme gut lesbar)
    component Chip: Button {
        id: chip
        property bool an: false
        font.pixelSize: 14
        leftPadding: 10; rightPadding: 10; topPadding: 4; bottomPadding: 4
        implicitHeight: 38
        implicitWidth: Math.max(44, chipText.implicitWidth + leftPadding + rightPadding)
        contentItem: Label {
            id: chipText
            text: chip.text; font: chip.font
            color: chip.an ? 'white' : (chip.enabled ? '#1c2934' : '#9aa59f')
            horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
        }
        background: Rectangle {
            radius: 8
            color: chip.an ? (chip.down ? '#0f5c3a' : plugin.gruen) : (chip.down ? '#d8e4da' : '#eef3ef')
            border.color: chip.an ? plugin.gruen : '#c9d6cc'
        }
    }

    Component.onCompleted: {
        if (!apiLaden()) {
            meldung('GoKart: QField-API nicht gefunden – Plugin inaktiv.');
            return;
        }
        moduleLaden();
        var knoepfe = [[erfassung.arten, gokartKnopf], [erfassung.fotos, fotoKnopf], [erfassung.biotope, biotopKnopf]];
        for (var i = 0; i < knoepfe.length; i++) {
            if (knoepfe[i][0]) iface.addItemToPluginsToolbar(knoepfe[i][1]);
            else knoepfe[i][1].visible = false;     // nicht eingehängt -> nirgends sichtbar
        }
        if (!erfassung.arten && !erfassung.fotos && !erfassung.biotope)
            meldung('GoKart: gokart_module enthält keine bekannte Erfassung (arten, fotos, biotope, punkte).');
        else if (erfassung.punkte && !erfassung.arten)
            meldung('GoKart: Punktaufnahmen brauchen das Modul „arten“ (gokart_module).');
    }

    // ---------------------------------------------------------------- Hilfsfunktionen
    function meldung(text) {
        letzteMeldung = text;
        try { iface.mainWindow().displayToast(text); } catch (e) { console.log(text); }
    }

    // QField 4.x: org.qfield.core / QfLayerUtils – QField 3.x: org.qfield / LayerUtils
    function apiLaden() {
        var varianten = [
            'import QtQuick; import org.qfield.core; QtObject { property var lu: QfLayerUtils; property var fu: QfFeatureUtils }',
            'import QtQuick; import org.qfield; QtObject { property var lu: LayerUtils; property var fu: FeatureUtils }'
        ];
        var ok = false;
        for (var i = 0; i < varianten.length && !ok; i++) {
            try {
                var o = Qt.createQmlObject(varianten[i], plugin, 'gokartApi' + i);
                if (o && o.lu && o.fu) { lu = o.lu; fu = o.fu; ok = true; }
            } catch (e) { /* nächste Variante */ }
        }
        // Projektvariablen lesen können (optional – sonst Fallback auf Layernamen)
        var ecuVarianten = [
            'import QtQuick; import org.qfield.core; QtObject { property var e: QfExpressionContextUtils }',
            'import QtQuick; import org.qfield; QtObject { property var e: ExpressionContextUtils }'
        ];
        for (var k = 0; k < ecuVarianten.length && !ecu; k++) {
            try {
                var q = Qt.createQmlObject(ecuVarianten[k], plugin, 'gokartEcu' + k);
                if (q && q.e) ecu = q.e;
            } catch (e2) { /* nächste Variante */ }
        }
        var fuVarianten = [
            'import QtQuick; import org.qfield.core; QtObject { property var f: QfFileUtils }',
            'import QtQuick; import org.qfield; QtObject { property var f: FileUtils }'
        ];
        for (var m = 0; m < fuVarianten.length && !dateiUtils; m++) {
            try {
                var d = Qt.createQmlObject(fuVarianten[m], plugin, 'gokartFu' + m);
                if (d && d.f) dateiUtils = d.f;
            } catch (e3) { /* nächste Variante */ }
        }
        var guVarianten = [
            'import QtQuick; import org.qfield.core; QtObject { property var g: QfGeometryUtils; property var c: QfCoordinateReferenceSystemUtils }',
            'import QtQuick; import org.qfield; QtObject { property var g: GeometryUtils; property var c: CoordinateReferenceSystemUtils }'
        ];
        for (var n = 0; n < guVarianten.length && !gu; n++) {
            try {
                var g = Qt.createQmlObject(guVarianten[n], plugin, 'gokartGu' + n);
                if (g && g.g) { gu = g.g; crsu = g.c || null; }
            } catch (e4) { /* nächste Variante */ }
        }
        return ok;
    }

    // ---------------------------------------------------------------- Konfiguration
    function projektVariablen() {
        try { if (ecu) return ecu.projectVariables(qgisProject) || {}; } catch (e) {}
        return {};
    }

    function layerAusRef(ref) {
        if (!ref) return null;
        try { var l = qgisProject.mapLayer(String(ref)); if (l) return l; } catch (e) {}
        return ebene(String(ref));
    }

    // gokart_module: kommagetrennt (arten, fotos, biotope, punkte); leer/fehlend = alle außer punkte
    function moduleLaden() {
        var roh = String(projektVariablen().gokart_module || '').toLowerCase().trim();
        if (!roh || roh === 'null') { erfassung = { arten: true, fotos: true, biotope: true, punkte: false }; return; }
        var teile = roh.split(/[,;]/).map(function (t) { return t.trim(); });
        erfassung = { arten: teile.indexOf('arten') >= 0, fotos: teile.indexOf('fotos') >= 0,
                   biotope: teile.indexOf('biotope') >= 0, punkte: teile.indexOf('punkte') >= 0 };
    }

    // Liest gokart_*-Variablen; ohne Variablen wird nach bekannten Layernamen gesucht.
    function konfigLaden() {
        var v = projektVariablen();
        var c = {
            flaechen: layerAusRef(v.gokart_flaechen_layer) || ebene('Wohnung – Teilflächen') || ebene('flaechen'),
            key: v.gokart_flaechen_key || 'flaeche_id',
            label: v.gokart_flaechen_label || '',
            nachweise: layerAusRef(v.gokart_nachweis_layer) || ebene('artnachweise'),
            fk: v.gokart_nachweis_fk || 'flaeche_id',
            biotopSchluessel: String(v.gokart_biotop_schluessel || '').toUpperCase(),
            punkte: erfassung.punkte ? ebene('aufnahme_punkte') : null,
            quelle: v.gokart_flaechen_layer ? 'Projektvariablen' : 'Layernamen (Fallback)'
        };
        punktCfg = { genauigkeit: Zusatz.zahlOder(v.gokart_punkt_genauigkeit, 10),
                     radius: Zusatz.zahlOder(v.gokart_punkt_radius, 25) };
        zusatzFelder = Zusatz.aktiveFelder(v.gokart_zusatz);
        if (!c.punkte && ortArt === 'punkt') ortArt = 'flaeche';
        if (c.punkte && !c.flaechen) ortArt = 'punkt';
        if (c.flaechen && !c.label) {
            var kand = ['Raum', 'raum', 'name', 'Name', 'bezeichnung', 'Bezeichnung'];
            for (var i = 0; i < kand.length; i++)
                if (c.flaechen.fields.indexFromName(kand[i]) >= 0) { c.label = kand[i]; break; }
        }
        cfg = c;
        protokoll('Konfiguration aus ' + c.quelle + ': Flächen=' + (c.flaechen ? c.flaechen.name : 'FEHLT') +
                  ' [' + c.key + '], Nachweise=' + (c.nachweise ? c.nachweise.name : 'FEHLT') + ' [' + c.fk + ']' +
                  (erfassung.punkte ? ', Punkte=' + (c.punkte ? c.punkte.name : 'FEHLT') : ''),
                  !(c.flaechen || c.punkte) || (erfassung.arten && !c.nachweise) || (erfassung.punkte && !c.punkte));
        return !!((c.flaechen || c.punkte) && (c.nachweise || !erfassung.arten));
    }

    function ebene(name) {
        var l = qgisProject.mapLayersByName(name);
        return (l && l.length) ? l[0] : null;
    }

    function textSql(s) { return "'" + String(s).replace(/'/g, "''") + "'"; }

    function jetzt() {
        var d = new Date();
        function z(n) { return (n < 10 ? '0' : '') + n; }
        return d.getFullYear() + '-' + z(d.getMonth() + 1) + '-' + z(d.getDate()) + 'T' +
               z(d.getHours()) + ':' + z(d.getMinutes()) + ':' + z(d.getSeconds());
    }

    function attr(f, name) {
        var v = f.attribute(name);
        return (v === undefined || v === null || String(v) === 'NULL') ? null : v;
    }

    function setze(f, lyr, name, wert) {
        var i = lyr.fields.indexFromName(name);
        if (i >= 0) f.setAttribute(i, wert);
    }

    function alleFeatures(lyr, ausdruck, je) {
        var it = ausdruck ? lu.createFeatureIteratorFromExpression(lyr, ausdruck) : lu.createFeatureIterator(lyr);
        var n = 0;
        while (it.hasNext()) { je(it.next()); n++; }
        it.close();
        return n;
    }

    function protokoll(text, fehler) {
        diagnose = text;
        diagnoseFehler = !!fehler;
        console.log('GoKart: ' + text);
        try { iface.logMessage('GoKart: ' + text); } catch (e) {}
    }

    function istEditierbar(lyr) {
        try { return (typeof lyr.isEditable === 'function') ? lyr.isEditable() : !!lyr.isEditable; }
        catch (e) { return false; }
    }

    function commitFehler(lyr) {
        try { var f = lyr.commitErrors(); return f && f.length ? f.join(' | ') : '-'; }
        catch (e) { return 'nicht abrufbar'; }
    }

    // Startet Bearbeitung, führt aktion() aus, speichert dauerhaft und protokolliert jeden Schritt
    function inBearbeitung(lyr, aktion) {
        var schritte = [];
        if (istEditierbar(lyr)) schritte.push('war schon im Bearbeitungsmodus');
        var ok = false;
        try { schritte.push('start=' + lyr.startEditing()); } catch (e0) { schritte.push('start-Fehler: ' + e0); }
        try { ok = !!aktion(); schritte.push('hinzufügen=' + ok); }
        catch (e) { schritte.push('Fehler: ' + e); ok = false; }
        if (ok) {
            try { ok = !!lyr.commitChanges(); schritte.push('speichern=' + ok); }
            catch (e3) { schritte.push('speichern-Fehler: ' + e3); ok = false; }
        }
        if (!ok) {
            schritte.push('Meldung: ' + commitFehler(lyr));
            try {
                if (typeof lyr.rollBack === 'function') lyr.rollBack();
                else schritte.push('rollBack nicht verfügbar');
            } catch (e2) { schritte.push('rollBack-Fehler: ' + e2); }
        }
        schritte.push('danach im Bearbeitungsmodus=' + istEditierbar(lyr));
        protokoll(lyr.name + ': ' + schritte.join(', '), !ok);
        return ok;
    }

    // Hängen ungespeicherte Änderungen im Layer (z. B. nach einem Fehler)? Dann jetzt speichern.
    function offeneAenderungenSpeichern(lyr) {
        if (!lyr || !istEditierbar(lyr)) return;
        var ok = false;
        try { ok = !!lyr.commitChanges(); } catch (e) {}
        protokoll(lyr.name + ': offene Änderungen gefunden, gespeichert=' + ok + (ok ? '' : ', Meldung: ' + commitFehler(lyr)), !ok);
    }

    // ---------------------------------------------------------------- Daten laden
    function indexLaden() {
        var tx = ebene('taxon'), sn = ebene('suchnamen'), es = ebene('eigene_synonyme');
        if (!tx || !sn) { meldung('GoKart: Layer "taxon"/"suchnamen" fehlen im Projekt.'); return false; }
        var idx = Suche.neuerIndex();
        alleFeatures(tx, null, function (f) {
            Suche.taxonHinzufuegen(idx, {
                taxon_id: attr(f, 'taxon_id'),
                wissenschaftlicher_name: attr(f, 'wissenschaftlicher_name'),
                deutscher_name: attr(f, 'deutscher_name') || attr(f, 'anzeige_name'),
                rang: attr(f, 'rang'),
                voller_name: attr(f, 'autor_name')
            });
        });
        alleFeatures(sn, null, function (f) {
            Suche.nameHinzufuegen(idx, attr(f, 'taxon_id'), attr(f, 'name'), attr(f, 'art'), attr(f, 'schluessel'));
        });
        if (es) alleFeatures(es, null, function (f) {
            Suche.nameHinzufuegen(idx, attr(f, 'taxon_id'), attr(f, 'synonym'), 'eigen');
        });
        index = idx;
        return true;
    }

    function flaechenLaden() {
        var fl = cfg.flaechen;
        var liste = [];
        if (fl) alleFeatures(fl, null, function (f) {
            var id = attr(f, cfg.key);
            if (id === null) return;                       // ohne Schlüssel nicht zuordenbar
            var name = cfg.label ? (attr(f, cfg.label) || '') : '';
            if (!name && !unbenannteZeigen.checked) return;
            liste.push({ id: String(id), name: String(name) });
        });
        liste.sort(function (a, b) {
            return (a.name || a.id).localeCompare(b.name || b.id);
        });
        flaechen = liste;
        if (!aktiveFlaeche && liste.length === 1) aktiveFlaeche = liste[0].id;
    }

    // ---------------------------------------------------------------- Ort: Fläche oder Punktaufnahme
    // Ort-Schlüssel wie in abgleich.py: Flächen-ID oder '@' + punkt_id
    function punktModus() { return ortArt === 'punkt'; }
    function ortSchluessel() { return punktModus() ? (aktiverPunkt ? '@' + aktiverPunkt : '') : aktiveFlaeche; }
    function ortFilter(ort) {
        ort = String(ort);
        return ort.charAt(0) === '@' ? '"punkt_id" = ' + textSql(ort.substring(1)) : '"' + cfg.fk + '" = ' + textSql(ort);
    }
    function ortName(ort) {
        ort = String(ort || '');
        return ort.charAt(0) === '@' ? punktName(ort.substring(1)) : flaechenName(ort);
    }
    function ortAus(f) {
        var fl = attr(f, cfg.fk);
        if (fl !== null && String(fl) !== '') return String(fl);
        var p = attr(f, 'punkt_id');
        return p !== null && String(p) !== '' ? '@' + p : '';
    }
    function punkteVerfuegbar() { return !!(erfassung.punkte && cfg.punkte); }
    function ortWechseln(art) {
        if (art === ortArt) return;
        if (bearbeitung) bearbeitenBeenden();
        ortArt = art;
        letzterNachweis = null;
        if (art === 'punkt') { punkteLaden(); gpsAktualisieren(); }
        artenLaden();
    }

    function artenLaden() {
        var an = cfg.nachweise;
        var liste = [];
        var ort = ortSchluessel();
        if (an && ort) {
            alleFeatures(an, ortFilter(ort), function (f) {
                liste.push({ fid: f.id, taxon_id: attr(f, 'taxon_id'), flaeche: ortAus(f),
                             name: attr(f, 'deutscher_name') || attr(f, 'wissenschaftlicher_name') || '?',
                             wiss: attr(f, 'wissenschaftlicher_name') || '', am: attr(f, 'erfasst_am') || '',
                             bemerkung: attr(f, 'bemerkung') || '', eingabe: attr(f, 'original_eingabe') || '',
                             ersetzt: attr(f, 'ersetzt') || '', geaendert: attr(f, 'geaendert_am') || '',
                             deckung: attr(f, 'deckung') || '', anzahl: attr(f, 'anzahl') || '',
                             phaenologie: attr(f, 'phaenologie') || '' });
            });
            liste.sort(function (a, b) { return String(b.am).localeCompare(String(a.am)); });
        }
        artenDerFlaeche = liste;
        // Schnellleiste zeigt den aktuellen Stand des Eintrags
        if (letzterNachweis) letzterNachweis = eintragMitFid(letzterNachweis.fid);
        if (bearbeitung) { var b = eintragMitFid(bearbeitung.fid); if (b) bearbeitung = b; }
    }

    function eintragMitFid(fid) {
        for (var i = 0; i < artenDerFlaeche.length; i++) if (artenDerFlaeche[i].fid === fid) return artenDerFlaeche[i];
        return null;
    }

    // ---------------------------------------------------------------- Punktaufnahmen
    function punktName(id) {
        for (var i = 0; i < punkte.length; i++) {
            var p = punkte[i];
            if (p.id === id) return 'Punkt ' + String(p.am).replace('T', ' ').substring(5, 16).replace('-', '.') +
                                    (p.hacc !== null ? ' (±' + Math.round(p.hacc) + ' m)' : '');
        }
        return 'Punkt ' + id;
    }

    // QgsFeature.geometry / QgsGeometry.isNull sind in QField Eigenschaften, in Tests teils Methoden
    function geometrieVon(f) {
        try { return (typeof f.geometry === 'function') ? f.geometry() : f.geometry; } catch (e) { return null; }
    }
    function geometrieLeer(g) {
        if (!g) return true;
        try {
            if ((typeof g.isNull === 'function') ? g.isNull() : g.isNull) return true;
            if (typeof g.isEmpty === 'function') return g.isEmpty();
        } catch (e) { return true; }
        return false;
    }

    function punktXY(f) {
        try {
            var g = geometrieVon(f);
            if (geometrieLeer(g)) return null;
            if (gu) {
                var c = gu.centroid(g);
                if (isFinite(c.x) && isFinite(c.y)) return { x: Number(c.x), y: Number(c.y) };
            }
        } catch (e) {}
        return null;
    }

    function punkteLaden() {
        var pl = cfg.punkte, liste = [];
        if (pl) alleFeatures(pl, null, function (f) {
            var id = attr(f, 'punkt_id');
            if (id === null) return;
            var xy = punktXY(f);
            var h = attr(f, 'gps_genauigkeit');   // NULL kommt in QML bei Zahlenfeldern als 0 an
            liste.push({ id: String(id), am: attr(f, 'erfasst_am') || '', hacc: (h === null || !(Number(h) > 0)) ? null : Number(h),
                         quelle: attr(f, 'pos_quelle') || '', x: xy ? xy.x : null, y: xy ? xy.y : null });
        });
        liste.sort(function (a, b) { return String(b.am).localeCompare(String(a.am)); });
        punkte = liste;
        if (aktiverPunkt && !liste.some(function (p) { return p.id === aktiverPunkt; })) aktiverPunkt = '';
    }

    function punktWaehlen(id) {
        if (bearbeitung) bearbeitenBeenden();
        aktiverPunkt = String(id || '');
        letzterNachweis = null;
        artenLaden();
        gpsAktualisieren();
    }

    function aktiverPunktDaten() {
        for (var i = 0; i < punkte.length; i++) if (punkte[i].id === aktiverPunkt) return punkte[i];
        return null;
    }

    // Koordinate (x, y in kbs – Text wie 'EPSG:4326' oder KBS-Objekt) ins KBS des Punkt-Layers
    function inLayerKbs(x, y, kbs) {
        var pl = cfg.punkte;
        if (!pl || !gu) return null;
        try {
            var quelle = (typeof kbs === 'string') ? (crsu ? crsu.fromDescription(kbs) : null) : kbs;
            if (!quelle) return null;
            var p = gu.reprojectPoint(gu.point(Number(x), Number(y)), quelle, pl.crs);
            if (isFinite(p.x) && isFinite(p.y)) return { x: Number(p.x), y: Number(p.y) };
        } catch (e) { protokoll('Umrechnung fehlgeschlagen: ' + e, true); }
        return null;
    }

    // GPS-Genauigkeit und Abstand zum aktiven Punkt für die Anzeige (alle 3 s im Punkt-Modus)
    function gpsAktualisieren() {
        var pos = gpsPosition();
        var stand = { ok: !!pos, hacc: -1, abstand: -1 };
        if (pos) {
            if (pos.haccValid) stand.hacc = Number(pos.hacc);
            var p = aktiverPunktDaten();
            if (p && p.x !== null) {
                var hier = inLayerKbs(pos.longitude, pos.latitude, 'EPSG:4326');
                if (hier) stand.abstand = Zusatz.abstand(p.x, p.y, hier.x, hier.y);
            }
        }
        gpsStand = stand;
    }

    // quelle: 'gps' (Position, Genauigkeit wird geprüft) oder 'karte' (Kartenmitte, pos_quelle = manuell)
    function punktAnlegen(quelle) {
        var pl = cfg.punkte;
        if (!pl) { meldung('Layer aufnahme_punkte fehlt – am PC abgleich.py oder GoKart Desktop „Einrichten…“.'); return; }
        if (!gu) { meldung('QField-Geometriefunktionen nicht gefunden – Punkt kann nicht angelegt werden.'); return; }
        var xy = null, hacc = null, hoehe = null;
        if (quelle === 'gps') {
            var pos = gpsPosition();
            if (!pos) { meldung('Keine gültige GPS-Position – „Karte“ setzt den Punkt in die Kartenmitte.'); return; }
            hacc = pos.haccValid ? Number(pos.hacc) : null;
            if ((hacc === null || hacc > punktCfg.genauigkeit) && !punktTrotzdem) {
                punktTrotzdem = true;
                trotzdemTimer.restart();
                meldung('GPS-Genauigkeit ' + (hacc === null ? 'unbekannt' : '±' + Math.round(hacc) + ' m') +
                        ' (Schwelle ' + punktCfg.genauigkeit + ' m) – warten, nochmal tippen zum Übernehmen oder „Karte“.');
                return;
            }
            if (pos.elevationValid) hoehe = Number(pos.elevation);
            xy = inLayerKbs(pos.longitude, pos.latitude, 'EPSG:4326');
        } else {
            var fk = fadenkreuzPunkt();
            if (!fk) { meldung('Fadenkreuz/Kartenmitte nicht ermittelbar.'); return; }
            xy = inLayerKbs(fk.x, fk.y, fk.crs);
        }
        punktTrotzdem = false;
        punktSpeichern(xy, quelle === 'gps' ? 'gps' : 'manuell', hacc, hoehe);
    }

    function punktSpeichern(xy, quelle, hacc, hoehe) {
        var pl = cfg.punkte;
        if (!xy) { meldung('Position konnte nicht ins Koordinatensystem des Punkt-Layers umgerechnet werden.'); return; }
        offeneAenderungenSpeichern(pl);
        var am = jetzt();
        var id = Zusatz.neuePunktId(am);
        var ok = inBearbeitung(pl, function () {
            var geom = gu.createGeometryFromWkt('POINT(' + xy.x + ' ' + xy.y + ')');
            var f = fu.createFeature(pl, geom);
            setze(f, pl, 'punkt_id', id);
            setze(f, pl, 'erfasst_am', am);
            setze(f, pl, 'pos_quelle', quelle);
            if (hacc !== null) setze(f, pl, 'gps_genauigkeit', Math.round(hacc * 10) / 10);
            if (hoehe !== null) setze(f, pl, 'hoehe', Math.round(hoehe * 10) / 10);
            return lu.addFeature(pl, f);
        });
        punktStatus = ok ? '✓ Neuer Punkt ' + id + ' (' + quelle + ')' : '✗ Punkt nicht gespeichert: ' + diagnose;
        punktStatusFehler = !ok;
        if (!ok) { meldung('Punkt nicht gespeichert – Details im Dialog.'); return; }
        punkteLaden();
        punktWaehlen(id);
        meldung('📍 Neue Aufnahme ' + punktName(id) + (quelle === 'gps' ? '' : ' – Fadenkreuz'));
        sucheFeld.forceActiveFocus();
    }

    // ---------------------------------------------------------------- Fadenkreuz (Punkt manuell auf der Karte)
    // Koordinate genau unter dem GoKart-Fadenkreuz (Mitte der Karte) im Karten-KBS: { x, y, crs }.
    // Nicht QFields coordinateLocator: der liefert außerhalb des Bearbeitungsmodus eine alte bzw. die
    // GPS-Position. Auch nicht mapSettings.center: das berücksichtigt Ränder (z. B. Positionierungsfeld).
    function fadenkreuzPunkt() {
        try {
            var ms = iface.mapCanvas().mapSettings;
            var c = null;
            try {
                var karte = kartenItem();
                var p = fadenkreuzMarke.mapToItem(karte, fadenkreuzMarke.width / 2, fadenkreuzMarke.height / 2);
                if (ms.screenToCoordinate) c = ms.screenToCoordinate(Qt.point(p.x, p.y));
            } catch (e1) { protokoll('Fadenkreuz (Bildschirm): ' + e1, true); }
            if (!c || !isFinite(c.x) || !isFinite(c.y)) c = ms.center;
            return { x: Number(c.x), y: Number(c.y), crs: ms.destinationCrs };
        } catch (e) { protokoll('Fadenkreuz: ' + e, true); }
        return null;
    }

    function fadenkreuzStarten(modus) {
        if (!cfg.punkte || !gu) { meldung('Punkt-Layer oder QField-Geometriefunktionen fehlen.'); return; }
        if (modus === 'verschieben' && !aktiverPunkt) { meldung('Erst eine Punktaufnahme wählen.'); return; }
        fadenkreuz = modus;
        dialog.close();                      // zuerst: die Karte muss frei sein, egal was danach passiert
        try { fadenkreuzAktualisieren(); } catch (e) { protokoll('Fadenkreuz-Anzeige: ' + e, true); }
        meldung('Karte verschieben, bis das Fadenkreuz auf der Stelle liegt – dann „Hier setzen“.');
    }

    function fadenkreuzAktualisieren() {
        var fk = fadenkreuzPunkt();
        if (!fk) { fadenkreuzInfo = 'Fadenkreuz nicht ermittelbar'; return; }
        var xy = inLayerKbs(fk.x, fk.y, fk.crs);
        var t = xy ? 'R ' + Math.round(xy.x) + ' · H ' + Math.round(xy.y) + ' (' + (cfg.punkte.crs.authid || '') + ')'
                   : 'Umrechnung nicht möglich';
        var fl = '';
        try { if (cfg.flaechen) fl = flaecheAnPunkt(fk.x, fk.y, fk.crs.authid); } catch (e) {}
        if (fl) t += ' · in ' + flaechenName(fl);
        var p = aktiverPunktDaten();
        if (fadenkreuz === 'verschieben' && p && p.x !== null && xy)
            t += ' · ' + Math.round(Zusatz.abstand(p.x, p.y, xy.x, xy.y)) + ' m vom bisherigen Punkt';
        fadenkreuzInfo = t;
    }

    function fadenkreuzUebernehmen() {
        var fk = fadenkreuzPunkt();
        var xy = fk ? inLayerKbs(fk.x, fk.y, fk.crs) : null;
        var modus = fadenkreuz;
        fadenkreuz = '';
        if (modus === 'verschieben') punktVerschieben(xy);
        else punktSpeichern(xy, 'manuell', null, null);
        dialog.open();
    }

    function fadenkreuzAbbrechen() {
        fadenkreuz = '';
        dialog.open();
    }

    // Geometrie lässt sich in QML nicht direkt ändern -> neues Feature mit gleicher punkt_id, altes löschen.
    // Die Artnachweise hängen an der punkt_id und bleiben verknüpft.
    function punktVerschieben(xy) {
        var pl = cfg.punkte;
        if (!xy) { meldung('Position konnte nicht ins Koordinatensystem des Punkt-Layers umgerechnet werden.'); return; }
        var alt = null;
        alleFeatures(pl, '"punkt_id" = ' + textSql(aktiverPunkt), function (f) { if (!alt) alt = f; });
        if (!alt) { meldung('Punkt ' + aktiverPunkt + ' nicht gefunden.'); return; }
        offeneAenderungenSpeichern(pl);
        var namen = pl.fields.names;
        var werte = {};
        // Zahlenfelder (gps_genauigkeit, hoehe) nicht kopieren: NULL käme als 0 an
        for (var i = 0; i < namen.length; i++)
            if (['fid', 'geom', 'geometry', 'gps_genauigkeit', 'hoehe'].indexOf(namen[i]) < 0) werte[namen[i]] = attr(alt, namen[i]);
        var hoeheAlt = attr(alt, 'hoehe');
        if (hoeheAlt !== null && Number(hoeheAlt) !== 0) werte.hoehe = Number(hoeheAlt);
        var altId = alt.id;
        var schritte = 'alter fid ' + altId;
        var ok = inBearbeitung(pl, function () {
            // erst den alten Punkt löschen (punkt_id ist eindeutig), dann den neuen anlegen – beides im selben Puffer
            var weg = lu.deleteFeature(qgisProject, pl, altId, false);
            schritte += ', gelöscht=' + weg;
            if (!weg) return false;
            var f = fu.createFeature(pl, gu.createGeometryFromWkt('POINT(' + xy.x + ' ' + xy.y + ')'));
            for (var n in werte) if (werte[n] !== null) setze(f, pl, n, werte[n]);
            setze(f, pl, 'pos_quelle', 'korrigiert');
            setze(f, pl, 'geaendert_am', jetzt());
            var neu = lu.addFeature(pl, f);
            schritte += ', neu angelegt=' + neu;
            return neu;
        });
        punktStatus = (ok ? '✓ Verschoben: ' : '✗ Verschieben fehlgeschlagen: ') + schritte + ' · ' + diagnose;
        punktStatusFehler = !ok;
        meldung(ok ? '📍 ' + punktName(aktiverPunkt) + ' verschoben.' : 'Verschieben fehlgeschlagen – Details im Dialog.');
        punkteLaden();
        gpsAktualisieren();
    }

    // ---------------------------------------------------------------- Fläche bestimmen
    function flaecheAnPunkt(x, y, crsAuthid) {
        var fl = cfg.flaechen;
        if (!fl) return null;

        var ziel = 'EPSG:25832';
        try {
            if (fl.crs && fl.crs.authid)
                ziel = fl.crs.authid;
        } catch (e) {}

        var punkt = "transform(make_point(" +
                    Number(x) + ", " + Number(y) + "), " +
                    textSql(crsAuthid) + ", " + textSql(ziel) + ")";

        var expr = "intersects($geometry, " + punkt + ")";

        var gefunden = null;
        var kleinsteFlaeche = Infinity;

        alleFeatures(fl, expr, function (f) {
            var wert = attr(f, cfg.key);
            if (wert === null)
                return;
            var id = String(wert);

            var geom = geometrieVon(f);
            if (geometrieLeer(geom))
                return;

            // area() ist in QML nicht aufrufbar -> notfalls Größe der Bounding-Box als Ersatz
            var groesse = 0;
            try {
                if (typeof geom.area === 'function') groesse = geom.area();
                else if (gu && gu.boundingBox) { var bb = gu.boundingBox(geom); groesse = bb.width * bb.height; }
            } catch (e3) {}

            if (groesse < kleinsteFlaeche) {
                kleinsteFlaeche = groesse;
                gefunden = id;
            }
        });

        return gefunden;
    }

    function flaechenName(id) {
        for (var i = 0; i < flaechen.length; i++) if (flaechen[i].id === id) return flaechen[i].name || id;
        return id;
    }

    function flaecheWaehlen(id, quelle) {
        if (!id) { meldung('Keine Fläche ' + quelle + ' gefunden.'); return; }
        aktiveFlaeche = String(id);
        if (bearbeitung) bearbeitenBeenden();
        artenLaden();
        fotosLaden();
        biotopeLaden();
        meldung('Aktive Fläche: ' + flaechenName(aktiveFlaeche) + ' (' + quelle + ')');
    }

    function gpsPosition() {
        var pos = null;
        try { var p = iface.positioning(); if (p) pos = p.positionInformation; } catch (e) {}
        if (!pos) {
            try { var ps = iface.findItemByObjectName('positionSource'); if (ps) pos = ps.positionInformation; } catch (e2) {}
        }
        return (pos && pos.latitudeValid && pos.longitudeValid) ? pos : null;
    }

    function flaecheAusGps() {
        var pos = gpsPosition();
        if (!pos) { meldung('Keine gültige GPS-Position.'); return; }
        flaecheWaehlen(flaecheAnPunkt(pos.longitude, pos.latitude, 'EPSG:4326'), 'per GPS');
    }

    function flaecheAusKartenmitte() {
        try {
            var ms = iface.mapCanvas().mapSettings;
            var c = ms.center;
            flaecheWaehlen(flaecheAnPunkt(c.x, c.y, ms.destinationCrs.authid), 'in Kartenmitte');
        } catch (e) { meldung('Kartenmitte nicht ermittelbar: ' + e); }
    }

    // ---------------------------------------------------------------- Suche & Speichern
    // Eingabe = Artname + optionale Zusatzangaben („Calluna, Deckung drei, blühend“)
    function eingabeZerlegen() { return Zusatz.zerlegen(sucheFeld.text); }
    function suchName() { return eingabeZerlegen().name; }

    function suchen(text) {
        if (!index) return;
        var t = Suche.suchen(index, Zusatz.zerlegen(text).name, 5);
        treffer = t;
        // Genau ein exakter Treffer -> gleich vorauswählen (schneller Ablauf beim Diktieren)
        var exakte = t.filter(function (r) { return r.exakt; });
        auswahlIndex = (exakte.length === 1) ? t.indexOf(exakte[0]) : -1;
    }

    function ausgewaehlt() { return (auswahlIndex >= 0 && auswahlIndex < treffer.length) ? treffer[auswahlIndex] : null; }

    function speichern() {
        var r = ausgewaehlt();
        if (!r) { meldung('Bitte zuerst eine Art auswählen.'); return; }
        var ort = ortSchluessel();
        if (!ort) { meldung(punktModus() ? 'Bitte zuerst eine Punktaufnahme anlegen („Neue Aufnahme hier“).'
                                         : 'Bitte zuerst eine Fläche wählen.'); return; }
        var an = cfg.nachweise;
        if (!an) { meldung('Artnachweis-Layer fehlt – Einrichtung am Desktop prüfen.'); return; }
        var punkt = ort.charAt(0) === '@';
        if (punkt && an.fields.indexFromName('punkt_id') < 0) {
            meldung('Feld punkt_id fehlt in den Artnachweisen – am PC abgleich.py laufen lassen.'); return;
        }
        offeneAenderungenSpeichern(an);

        var schonDa = 0;
        var filter = ortFilter(ort) + ' AND "taxon_id" = ' + Number(r.id);
        alleFeatures(an, filter, function () { schonDa++; });
        var anzeige = r.taxon.deutscher_name || r.taxon.wissenschaftlicher_name;
        if (schonDa > 0) { meldung(anzeige + ' ist auf ' + ortName(ort) + ' bereits erfasst.'); eingabeLeeren(); return; }

        var eingabe = sucheFeld.text;
        var teile = eingabeZerlegen();
        var ok = inBearbeitung(an, function () {
            var f = fu.createFeature(an);
            if (punkt) setze(f, an, 'punkt_id', ort.substring(1));
            else setze(f, an, cfg.fk, ort);
            setze(f, an, 'taxon_id', Number(r.id));
            setze(f, an, 'wissenschaftlicher_name', r.taxon.wissenschaftlicher_name);
            setze(f, an, 'deutscher_name', r.taxon.deutscher_name);
            setze(f, an, 'original_eingabe', eingabe);
            setze(f, an, 'erfasst_am', jetzt());
            for (var k in teile.werte) setze(f, an, k, teile.werte[k]);
            return lu.addFeature(an, f);
        });
        if (!ok) { meldung('Speichern fehlgeschlagen – Details unten im Dialog.'); artenLaden(); return; }

        if (synonymMerken.visible && synonymMerken.checked) synonymSpeichern(r.id, teile.name);
        var zusatzText = Zusatz.kurztext(teile.werte);
        meldung('✔ ' + anzeige + ' → ' + ortName(ort) + (zusatzText ? ' · ' + zusatzText : '') +
                (teile.unklar.length ? ' – nicht erkannt: ' + teile.unklar.join(', ') : ''));
        artenLaden();
        // neuen Eintrag als Ziel der Schnellleiste merken
        var neu = null;
        for (var i = 0; i < artenDerFlaeche.length; i++)
            if (Number(artenDerFlaeche[i].taxon_id) === Number(r.id)) { neu = artenDerFlaeche[i]; break; }
        letzterNachweis = neu;
        eingabeLeeren();
    }

    // ---------------------------------------------------------------- Zusatzangaben (Schnellleiste)
    function zusatzZiel() { return bearbeitung || letzterNachweis; }

    // Antippen setzt den Wert sofort; derselbe Wert nochmal = leeren
    function zusatzSetzen(feld, wert) {
        var z = zusatzZiel(), an = cfg.nachweise;
        if (!z || !an) return;
        var i = an.fields.indexFromName(feld);
        if (i < 0) { meldung('Feld ' + feld + ' fehlt in den Artnachweisen – am PC abgleich.py laufen lassen.'); return; }
        var neu = (String(z[feld] || '') === String(wert)) ? null : wert;
        offeneAenderungenSpeichern(an);
        var ok = inBearbeitung(an, function () {
            var erfolg = an.changeAttributeValue(z.fid, i, neu);
            var g = an.fields.indexFromName('geaendert_am');
            if (g >= 0) erfolg = an.changeAttributeValue(z.fid, g, jetzt()) && erfolg;
            return erfolg;
        });
        if (!ok) { meldung('Nicht gespeichert – Details unten im Dialog.'); return; }
        artenLaden();
        var n = eintragMitFid(z.fid);
        meldung(z.name + ': ' + (Zusatz.kurztext(n || {}) || 'keine Zusatzangaben'));
    }

    function synonymSpeichern(taxonId, text) {
        var es = ebene('eigene_synonyme');
        var t = String(text).trim();
        if (!es || !t) return;
        var ok = inBearbeitung(es, function () {
            var f = fu.createFeature(es);
            setze(f, es, 'taxon_id', Number(taxonId));
            setze(f, es, 'synonym', t);
            setze(f, es, 'schluessel', Suche.normalisieren(t));
            setze(f, es, 'angelegt_am', jetzt());
            return lu.addFeature(es, f);
        });
        if (ok) Suche.nameHinzufuegen(index, taxonId, t, 'eigen');
    }

    function eintragLoeschen(fid) {
        var an = cfg.nachweise;
        if (!an) return;
        if (bearbeitung && bearbeitung.fid === fid) bearbeitenBeenden();
        var ok = inBearbeitung(an, function () { return lu.deleteFeature(qgisProject, an, fid, false); });
        meldung(ok ? 'Eintrag gelöscht.' : 'Löschen fehlgeschlagen.');
        artenLaden();
    }

    // ---------------------------------------------------------------- Artnachweis bearbeiten
    function bearbeitenStarten(eintrag) {
        if (!eintrag) { meldung(punktModus() ? 'An diesem Punkt ist noch keine Art erfasst.'
                                             : 'Auf dieser Fläche ist noch keine Art erfasst.'); return; }
        bearbeitung = eintrag;
        bearbeitFlaeche = eintrag.flaeche || ortSchluessel();
        bemerkungFeld.text = eintrag.bemerkung || '';
        sucheFeld.text = '';
        treffer = [];
        auswahlIndex = -1;
        synonymMerken.checked = false;
        sucheFeld.forceActiveFocus();
    }

    // Häufigster Fall im Gelände: die zuletzt erfasste Art war falsch erkannt
    function letzteKorrigieren() {
        var neueste = null;
        for (var i = 0; i < artenDerFlaeche.length; i++) {
            var a = artenDerFlaeche[i];
            if (!neueste || String(a.am) > String(neueste.am)) neueste = a;
        }
        bearbeitenStarten(neueste);
    }

    function bearbeitenBeenden() {
        bearbeitung = null;
        bearbeitFlaeche = '';
        bemerkungFeld.text = '';
        sucheFeld.text = '';
        treffer = [];
        auswahlIndex = -1;
        synonymMerken.checked = false;
    }

    // Was würde "Änderung speichern" tun? -> { art, flaeche, bemerkung, neueArt, neueFlaeche, neueBemerkung }
    function geplanteAenderung() {
        var b = bearbeitung;
        if (!b) return null;
        var r = ausgewaehlt();
        var neueArt = !!(r && Number(r.id) !== Number(b.taxon_id));
        var ziel = bearbeitFlaeche || b.flaeche;
        var bem = String(bemerkungFeld.text).trim();
        var werte = Zusatz.zerlegen(sucheFeld.text).werte, zusatz = {};
        for (var k in werte) if (String(b[k] || '') !== werte[k]) zusatz[k] = werte[k];
        return { art: r, flaeche: ziel, bemerkung: bem, neueArt: neueArt, zusatz: zusatz,
                 neueZusatz: Object.keys(zusatz).length > 0,
                 neueFlaeche: ziel !== b.flaeche, neueBemerkung: bem !== String(b.bemerkung || '').trim() };
    }

    function aenderungText() {
        var g = geplanteAenderung();
        if (!g) return '';
        var teile = [];
        if (g.neueArt) teile.push('Art → ' + (g.art.taxon.deutscher_name || g.art.taxon.wissenschaftlicher_name));
        if (g.neueFlaeche) teile.push('Fläche → ' + ortName(g.flaeche));
        if (g.neueZusatz) teile.push(Zusatz.kurztext(g.zusatz));
        if (g.neueBemerkung) teile.push(g.bemerkung ? 'Bemerkung' : 'Bemerkung leeren');
        return teile.length ? 'Speichern: ' + teile.join(' · ') : 'Keine Änderung';
    }

    function aenderungSpeichern() {
        var b = bearbeitung, g = geplanteAenderung();
        var an = cfg.nachweise;
        if (!b || !g || !an) return;
        if (!g.neueArt && !g.neueFlaeche && !g.neueBemerkung && !g.neueZusatz) { meldung('Keine Änderung.'); return; }
        offeneAenderungenSpeichern(an);

        var tid = g.neueArt ? Number(g.art.id) : Number(b.taxon_id);
        if (g.neueArt || g.neueFlaeche) {
            var doppelt = 0;
            alleFeatures(an, ortFilter(g.flaeche) + ' AND "taxon_id" = ' + tid, function (f) {
                if (f.id !== b.fid) doppelt++;
            });
            if (doppelt) {
                var nm = g.neueArt ? (g.art.taxon.deutscher_name || g.art.taxon.wissenschaftlicher_name) : b.name;
                meldung(nm + ' ist auf ' + ortName(g.flaeche) + ' bereits erfasst – dort ggf. den doppelten Eintrag löschen.');
                return;
            }
        }

        var eingabe = String(sucheFeld.text).trim();
        var fehlend = [];
        function aendern(feld, wert) {
            var i = an.fields.indexFromName(feld);
            if (i < 0) { fehlend.push(feld); return true; }   // Feld fehlt im Projekt -> überspringen
            return an.changeAttributeValue(b.fid, i, wert);
        }
        var ok = inBearbeitung(an, function () {
            var erfolg = true;
            if (g.neueArt) {
                erfolg = aendern('taxon_id', tid) && erfolg;
                erfolg = aendern('wissenschaftlicher_name', g.art.taxon.wissenschaftlicher_name || null) && erfolg;
                erfolg = aendern('deutscher_name', g.art.taxon.deutscher_name || null) && erfolg;
                if (eingabe) erfolg = aendern('original_eingabe', eingabe) && erfolg;
            }
            if (g.neueFlaeche) erfolg = aendern(cfg.fk, g.flaeche) && erfolg;
            if (g.neueArt || g.neueFlaeche) {
                var alt = String(b.flaeche) + ':' + Number(b.taxon_id);
                var liste = String(b.ersetzt || '').split(',').filter(function (x) { return x.trim() !== ''; });
                if (liste.indexOf(alt) < 0) liste.push(alt);
                erfolg = aendern('ersetzt', liste.join(',')) && erfolg;
            }
            if (g.neueBemerkung) erfolg = aendern('bemerkung', g.bemerkung === '' ? null : g.bemerkung) && erfolg;
            for (var k in g.zusatz) erfolg = aendern(k, g.zusatz[k]) && erfolg;
            erfolg = aendern('geaendert_am', jetzt()) && erfolg;
            return erfolg;
        });
        if (!ok) { meldung('Änderung nicht gespeichert – Details unten im Dialog.'); artenLaden(); return; }

        if (g.neueArt && synonymMerken.visible && synonymMerken.checked) synonymSpeichern(g.art.id, suchName());
        var text = '✔ geändert: ' + aenderungText().replace('Speichern: ', '');
        if (fehlend.indexOf('ersetzt') >= 0 && (g.neueArt || g.neueFlaeche))
            text += ' – Hinweis: Feld "ersetzt" fehlt, am PC abgleich.py laufen lassen, sonst kommt der alte Eintrag zurück.';
        meldung(text);
        bearbeitenBeenden();
        artenLaden();
    }

    // ---------------------------------------------------------------- Standortfotos
    function fotoLayer() { return ebene('fotos'); }

    function fotoUrl(datei) {
        return datei ? 'file://' + qgisProject.homePath + '/' + datei : '';
    }

    function fotosLaden() {
        var fl = fotoLayer();
        var liste = [];
        if (fl && aktiveFlaeche) {
            alleFeatures(fl, '"flaeche_id" = ' + textSql(aktiveFlaeche), function (f) {
                liste.push({ fid: f.id, datei: attr(f, 'datei') || '', kommentar: attr(f, 'kommentar') || '',
                             am: attr(f, 'aufgenommen_am') || '', lon: attr(f, 'lon'), lat: attr(f, 'lat') });
            });
            liste.sort(function (a, b) { return String(b.am).localeCompare(String(a.am)); });   // neueste oben
        }
        fotosDerFlaeche = liste;
    }

    function fotoAufnehmen() {
        if (!fotoLayer()) {
            meldung('Fototabelle fehlt – am PC einmal abgleich.py laufen lassen und das neue Zip importieren.');
            return;
        }
        if (!aktiveFlaeche) { meldung('Bitte zuerst eine Fläche (Standort) wählen.'); return; }
        var pos = gpsPosition();
        var sauber = String(aktiveFlaeche).replace(/[^A-Za-z0-9_-]/g, '_');
        var datei = 'fotos/gokart_' + sauber + '_' + jetzt().replace(/[-:]/g, '').replace('T', '_') + '.jpg';
        try { platformUtilities.createDir(qgisProject.homePath, 'fotos'); } catch (e) {}
        fotoFuer = { flaeche: aktiveFlaeche, lon: pos ? pos.longitude : null, lat: pos ? pos.latitude : null };
        try {
            fotoQuelle = platformUtilities.getCameraPicture(qgisProject.homePath + '/', datei, 'jpg', plugin);
        } catch (e2) {
            fotoQuelle = null;
            protokoll('Kamera-Aufruf fehlgeschlagen: ' + e2, true);
        }
        if (!fotoQuelle) meldung('Kamera nicht verfügbar.');
    }

    function fotoErhalten(datei) {
        var ziel = fotoFuer;
        fotoFuer = null;
        fotoQuelle = null;
        if (!datei || !ziel) return;
        try { if (dateiUtils) dateiUtils.restrictImageSize(qgisProject.homePath + '/' + datei, fotoMaxPixel); } catch (e) {}
        var fl = fotoLayer();
        var ok = inBearbeitung(fl, function () {
            var f = fu.createFeature(fl);
            setze(f, fl, 'flaeche_id', ziel.flaeche);
            setze(f, fl, 'datei', datei);
            setze(f, fl, 'aufgenommen_am', jetzt());
            if (ziel.lon !== null) { setze(f, fl, 'lon', ziel.lon); setze(f, fl, 'lat', ziel.lat); }
            return lu.addFeature(fl, f);
        });
        meldung(ok ? '📷 Foto gespeichert – Kommentar kann darunter ergänzt werden.'
                   : 'Foto aufgenommen, aber nicht eingetragen – Details im Diagnosefeld.');
        fotosLaden();
    }

    function fotoKommentar(foto, text) {
        var fl = fotoLayer();
        var i = fl ? fl.fields.indexFromName('kommentar') : -1;
        if (i < 0) return;
        var t = String(text).trim();
        var ok = inBearbeitung(fl, function () { return fl.changeAttributeValue(foto.fid, i, t === '' ? null : t); });
        meldung(ok ? 'Kommentar gespeichert' : 'Kommentar nicht gespeichert – Details im Diagnosefeld.');
        fotosLaden();
    }

    function fotoEntfernen(foto) {
        var fl = fotoLayer();
        if (!fl) return;
        var ok = inBearbeitung(fl, function () { return lu.deleteFeature(qgisProject, fl, foto.fid, false); });
        meldung(ok ? 'Foto entfernt (Datei bleibt im Ordner fotos/).' : 'Entfernen fehlgeschlagen.');
        fotosLaden();
    }

    function fotoDialogOeffnen() {
        fotoDialog.open();
        konfigLaden();
        offeneAenderungenSpeichern(fotoLayer());
        flaechenLaden();
        fotosLaden();
    }

    // ---------------------------------------------------------------- Biotoptypen
    function biotopLayer() { return ebene('biotoptypen'); }
    function zuordnungLayer() { return ebene('biotopzuordnung'); }

    function biotopSchluesselLaden() {
        var l = ebene('biotop_schluessel'), liste = [];
        if (l) alleFeatures(l, null, function (f) {
            liste.push({ schluessel: String(attr(f, 'schluessel') || ''), name: attr(f, 'name') || '',
                         anzahl: Number(attr(f, 'anzahl') || 0), vollstaendig: Number(attr(f, 'vollstaendig') || 0) === 1 });
        });
        liste.sort(function (a, b) { return a.schluessel.localeCompare(b.schluessel); });
        biotopSchluesselListe = liste;
        // Projektvariable gilt; ohne Variable: einziger vorhandener Schlüssel
        var s = cfg.biotopSchluessel || biotopSchluessel || (liste.length === 1 ? liste[0].schluessel : '');
        if (s !== biotopSchluessel || !biotopIndex) biotopSchluesselWaehlen(s);
    }

    function biotopSchluesselWaehlen(s) {
        biotopSchluessel = String(s || '');
        biotopIndex = null;
        biotopTreffer = [];
        biotopAuswahl = -1;
        var l = biotopLayer();
        if (!l || !biotopSchluessel) return;
        var idx = Biotop.neuerIndex();
        alleFeatures(l, '"schluessel" = ' + textSql(biotopSchluessel), function (f) {
            Biotop.typHinzufuegen(idx, {
                code: String(attr(f, 'code') || ''), name: String(attr(f, 'name') || ''),
                nr: attr(f, 'nr') || '', ebene: Number(attr(f, 'ebene') || 0), obercode: attr(f, 'obercode') || '',
                bund_code: attr(f, 'bund_code') || '', ffh_lrt: attr(f, 'ffh_lrt') || ''
            });
        });
        Biotop.abschliessen(idx);
        biotopIndex = idx;
        if (biotopSucheFeld.text) biotopSuchen(biotopSucheFeld.text);
    }

    function biotopSchluesselInfo() {
        for (var i = 0; i < biotopSchluesselListe.length; i++)
            if (biotopSchluesselListe[i].schluessel === biotopSchluessel) return biotopSchluesselListe[i];
        return null;
    }

    function biotopSuchen(text) {
        var t = Biotop.suchen(biotopIndex, text, 6);
        biotopTreffer = t;
        var exakte = t.filter(function (r) { return r.exakt; });
        biotopAuswahl = (exakte.length === 1) ? t.indexOf(exakte[0]) : -1;
    }

    function biotopGewaehlt() {
        return (biotopAuswahl >= 0 && biotopAuswahl < biotopTreffer.length) ? biotopTreffer[biotopAuswahl].typ : null;
    }

    function biotopeLaden() {
        var zl = zuordnungLayer(), liste = [];
        if (zl && aktiveFlaeche) {
            alleFeatures(zl, '"flaeche_id" = ' + textSql(aktiveFlaeche), function (f) {
                liste.push({ fid: f.id, schluessel: attr(f, 'schluessel') || '', code: attr(f, 'code') || '',
                             name: attr(f, 'name') || '', rolle: attr(f, 'rolle') || 'Neben' });
            });
            liste.sort(function (a, b) {
                if (a.rolle !== b.rolle) return a.rolle === 'Haupt' ? -1 : 1;
                return String(a.code).localeCompare(String(b.code));
            });
        }
        biotopeDerFlaeche = liste;
    }

    function rolleSetzen(zl, fid, rolle) {
        var i = zl.fields.indexFromName('rolle');
        return i >= 0 && zl.changeAttributeValue(fid, i, rolle);
    }

    // rolle: 'Haupt' oder 'Neben'. Ein neues Hauptbiotop stuft ein bisheriges (gleicher Schlüssel) zu Neben herab.
    function biotopSpeichern(rolle) {
        var typ = biotopGewaehlt();
        var zl = zuordnungLayer();
        if (!zl) { meldung('Biotop-Tabellen fehlen – am PC biotope_einspielen.py bzw. abgleich.py laufen lassen.'); return; }
        if (!typ) { meldung('Bitte zuerst einen Biotoptyp auswählen.'); return; }
        if (!aktiveFlaeche) { meldung('Bitte zuerst eine Fläche wählen.'); return; }
        offeneAenderungenSpeichern(zl);
        var vorhanden = null, alteHaupt = [];
        for (var i = 0; i < biotopeDerFlaeche.length; i++) {
            var b = biotopeDerFlaeche[i];
            if (b.schluessel !== biotopSchluessel) continue;
            if (b.code === typ.code) vorhanden = b;
            else if (rolle === 'Haupt' && b.rolle === 'Haupt') alteHaupt.push(b);
        }
        if (vorhanden && vorhanden.rolle === rolle) {
            meldung(typ.code + ' ist auf ' + flaechenName(aktiveFlaeche) + ' bereits als ' + rolle + 'biotop erfasst.');
            return;
        }
        var eingabe = biotopSucheFeld.text;
        var ok = inBearbeitung(zl, function () {
            for (var k = 0; k < alteHaupt.length; k++) if (!rolleSetzen(zl, alteHaupt[k].fid, 'Neben')) return false;
            if (vorhanden) return rolleSetzen(zl, vorhanden.fid, rolle);
            var f = fu.createFeature(zl);
            setze(f, zl, 'flaeche_id', aktiveFlaeche);
            setze(f, zl, 'schluessel', biotopSchluessel);
            setze(f, zl, 'code', typ.code);
            setze(f, zl, 'name', typ.name);
            setze(f, zl, 'rolle', rolle);
            if (typ.bund_code) setze(f, zl, 'bund_code', typ.bund_code);
            setze(f, zl, 'original_eingabe', eingabe);
            setze(f, zl, 'erfasst_am', jetzt());
            return lu.addFeature(zl, f);
        });
        if (!ok) { meldung('Speichern fehlgeschlagen – Details unten im Dialog.'); biotopeLaden(); return; }
        meldung('✔ ' + typ.code + ' (' + rolle + ') → ' + flaechenName(aktiveFlaeche) +
                (alteHaupt.length ? ' · ' + alteHaupt.map(function (b) { return b.code; }).join(', ') + ' jetzt Neben' : ''));
        biotopeLaden();
        biotopSucheFeld.text = '';
        biotopTreffer = [];
        biotopAuswahl = -1;
    }

    function biotopRolleWechseln(b) {
        if (b.rolle === 'Haupt') {
            var zl = zuordnungLayer();
            var ok = inBearbeitung(zl, function () { return rolleSetzen(zl, b.fid, 'Neben'); });
            meldung(ok ? b.code + ' ist jetzt Nebenbiotop.' : 'Ändern fehlgeschlagen.');
            biotopeLaden();
            return;
        }
        // Zum Hauptbiotop machen (bisheriges Hauptbiotop desselben Schlüssels → Neben)
        var zl2 = zuordnungLayer();
        var ok2 = inBearbeitung(zl2, function () {
            for (var i = 0; i < biotopeDerFlaeche.length; i++) {
                var x = biotopeDerFlaeche[i];
                if (x.fid !== b.fid && x.rolle === 'Haupt' && x.schluessel === b.schluessel && !rolleSetzen(zl2, x.fid, 'Neben'))
                    return false;
            }
            return rolleSetzen(zl2, b.fid, 'Haupt');
        });
        meldung(ok2 ? b.code + ' ist jetzt Hauptbiotop.' : 'Ändern fehlgeschlagen.');
        biotopeLaden();
    }

    function biotopEntfernen(b) {
        var zl = zuordnungLayer();
        if (!zl) return;
        var ok = inBearbeitung(zl, function () { return lu.deleteFeature(qgisProject, zl, b.fid, false); });
        meldung(ok ? b.code + ' entfernt.' : 'Entfernen fehlgeschlagen.');
        biotopeLaden();
    }

    function biotopDialogOeffnen() {
        biotopDialog.open();
        konfigLaden();
        offeneAenderungenSpeichern(zuordnungLayer());
        flaechenLaden();
        biotopSchluesselLaden();
        biotopeLaden();
        if (!zuordnungLayer() || !biotopLayer())
            meldung('Biotop-Tabellen fehlen – am PC biotope_einspielen.py bzw. abgleich.py laufen lassen.');
        biotopSucheFeld.forceActiveFocus();
    }

    Timer {
        id: biotopSuchTimer
        interval: 250
        onTriggered: plugin.biotopSuchen(biotopSucheFeld.text)
    }

    Connections {
        target: plugin.fotoQuelle
        ignoreUnknownSignals: true
        function onResourceReceived(path) { plugin.fotoErhalten(path); }
    }

    function eingabeLeeren() {
        sucheFeld.text = '';
        treffer = [];
        auswahlIndex = -1;
        synonymMerken.checked = false;
        sucheFeld.forceActiveFocus();
    }

    function oeffnen() {
        dialog.open();
        konfigLaden();
        offeneAenderungenSpeichern(cfg.nachweise);
        offeneAenderungenSpeichern(ebene('eigene_synonyme'));
        if (!index && !laedt) {
            laedt = true;
            ladeTimer.start();   // UI zuerst zeichnen, dann laden
        } else {
            flaechenLaden();
            punkteLaden();
            artenLaden();
            sucheFeld.forceActiveFocus();
        }
        if (punkteVerfuegbar()) offeneAenderungenSpeichern(cfg.punkte);
    }

    Timer {
        id: ladeTimer
        interval: 50
        onTriggered: {
            var t0 = Date.now();
            var ok = indexLaden();
            flaechenLaden();
            punkteLaden();
            artenLaden();
            laedt = false;
            if (ok) meldung('GoKart: ' + Object.keys(index.taxa).length + ' Taxa geladen (' + (Date.now() - t0) + ' ms)');
            sucheFeld.forceActiveFocus();
        }
    }

    Timer {
        interval: 700
        repeat: true
        running: plugin.fadenkreuz !== ''
        onTriggered: plugin.fadenkreuzAktualisieren()
    }

    // Eigenes Fadenkreuz in der Kartenmitte – QFields Fadenkreuz ist nur im Bearbeitungsmodus sichtbar
    function kartenItem() {
        try { var c = iface.mapCanvas(); if (c && c.width !== undefined && c.height !== undefined) return c; } catch (e) {}
        return iface.mainWindow().contentItem;
    }
    Item {
        id: fadenkreuzMarke
        objectName: 'gokartFadenkreuzMarke'
        parent: plugin.kartenItem()
        visible: plugin.fadenkreuz !== ''
        z: 999
        width: 64; height: 64
        // Mitte der Karte; Koordinate dazu liefert fadenkreuzPunkt() über screenToCoordinate
        x: parent ? (parent.width - width) / 2 : 0
        y: parent ? (parent.height - height) / 2 : 0
        Repeater {
            model: [{ w: 64, h: 6 }, { w: 6, h: 64 }]           // weiße Kontur
            delegate: Rectangle {
                required property var modelData
                anchors.centerIn: parent; width: modelData.w; height: modelData.h; color: 'white'; radius: 2
            }
        }
        Rectangle { anchors.centerIn: parent; width: 60; height: 2; color: '#b3261e' }
        Rectangle { anchors.centerIn: parent; width: 2; height: 60; color: '#b3261e' }
        Rectangle {
            anchors.centerIn: parent; width: 22; height: 22; radius: 11
            color: 'transparent'; border.color: '#b3261e'; border.width: 2
        }
    }

    // Leiste über der Karte, solange ein Punkt per Fadenkreuz gesetzt/verschoben wird
    Rectangle {
        id: fadenkreuzLeiste
        objectName: 'gokartFadenkreuzLeiste'
        parent: iface.mainWindow().contentItem
        visible: plugin.fadenkreuz !== ''
        z: 1000
        anchors.horizontalCenter: parent ? parent.horizontalCenter : undefined
        anchors.bottom: parent ? parent.bottom : undefined
        anchors.bottomMargin: 96
        width: Math.min(parent ? parent.width - 24 : 400, 440)
        height: leisteSpalte.implicitHeight + 20
        radius: 10
        color: '#f7fbf8'
        border.color: plugin.gruen
        ColumnLayout {
            id: leisteSpalte
            anchors.fill: parent
            anchors.margins: 10
            spacing: 6
            Label {
                Layout.fillWidth: true
                text: plugin.fadenkreuz === 'verschieben' ? '📍 Punkt verschieben' : '📍 Neue Punktaufnahme'
                font.bold: true; color: '#1c2934'
            }
            Label {
                Layout.fillWidth: true
                text: 'Karte verschieben, bis das Fadenkreuz auf der Stelle liegt.'
                wrapMode: Text.Wrap; font.pixelSize: 12; color: '#53645a'
            }
            Label {
                objectName: 'gokartFadenkreuzInfo'
                Layout.fillWidth: true
                text: plugin.fadenkreuzInfo
                wrapMode: Text.Wrap; font.pixelSize: 13; color: '#167d50'
            }
            RowLayout {
                Layout.fillWidth: true
                Chip { Layout.fillWidth: true; text: 'Abbrechen'; onClicked: plugin.fadenkreuzAbbrechen() }
                Chip {
                    objectName: 'gokartFadenkreuzSetzen'
                    Layout.fillWidth: true
                    an: true
                    text: '✓ Hier setzen'
                    onClicked: plugin.fadenkreuzUebernehmen()
                }
            }
        }
    }

    Timer {
        id: trotzdemTimer
        interval: 8000
        onTriggered: plugin.punktTrotzdem = false
    }

    Timer {
        id: gpsTimer
        interval: 3000
        repeat: true
        running: dialog.visible && plugin.punktModus()
        onTriggered: plugin.gpsAktualisieren()
    }

    Timer {
        id: suchTimer
        interval: 250
        onTriggered: suchen(sucheFeld.text)
    }

    // ---------------------------------------------------------------- Toolbar-Knopf
    RoundButton {
        id: gokartKnopf
        width: 48
        height: 48
        icon.source: Qt.resolvedUrl('gokart_icon.svg')
        icon.color: 'white'
        icon.width: 24
        icon.height: 24
        background: Rectangle { radius: width / 2; color: plugin.gruen }
        onClicked: plugin.oeffnen()
    }

    RoundButton {
        id: fotoKnopf
        width: 48
        height: 48
        icon.source: Qt.resolvedUrl('gokart_foto.svg')
        icon.color: 'white'
        icon.width: 24
        icon.height: 24
        background: Rectangle { radius: width / 2; color: plugin.gruen }
        onClicked: plugin.fotoDialogOeffnen()
    }

    RoundButton {
        id: biotopKnopf
        width: 48
        height: 48
        icon.source: Qt.resolvedUrl('gokart_biotop.svg')
        icon.color: 'white'
        icon.width: 24
        icon.height: 24
        background: Rectangle { radius: width / 2; color: plugin.gruen }
        onClicked: plugin.biotopDialogOeffnen()
    }

    // ---------------------------------------------------------------- Erfassungsdialog
    Popup {
        id: dialog
        parent: iface.mainWindow().contentItem
        modal: true
        focus: true
        closePolicy: Popup.CloseOnEscape
        width: Math.min(parent.width - 16, 640)
        height: parent.height - 32
        x: (parent.width - width) / 2
        y: 16
        padding: 12
        background: Rectangle { color: 'white'; radius: 12 }
        // QField nutzt ein dunkles Material-Theme -> Dialog explizit hell, sonst weiße Schrift auf Weiß
        Material.theme: Material.Light
        Material.accent: plugin.gruen
        Material.primary: plugin.gruen
        Material.foreground: '#1c2934'
        Material.background: 'white'
        palette.text: '#1c2934'
        palette.windowText: '#1c2934'
        palette.buttonText: '#1c2934'
        palette.base: 'white'

        ColumnLayout {
            anchors.fill: parent
            spacing: 8

            RowLayout {
                Layout.fillWidth: true
                Label { text: 'GoKart · Arterfassung'; font.bold: true; font.pixelSize: 20; color: plugin.gruen; Layout.fillWidth: true }
                Button { text: 'Schließen'; flat: true; onClicked: dialog.close() }
            }

            // --- Wo landet die Art: Fläche oder Punktaufnahme (nur mit Modul "punkte")
            RowLayout {
                Layout.fillWidth: true
                visible: plugin.punkteVerfuegbar()
                Chip {
                    Layout.fillWidth: true
                    text: 'Fläche'
                    enabled: !!plugin.cfg.flaechen
                    an: !plugin.punktModus()
                    onClicked: plugin.ortWechseln('flaeche')
                }
                Chip {
                    objectName: 'gokartPunktModus'
                    Layout.fillWidth: true
                    text: '📍 Punkt (GPS)'
                    an: plugin.punktModus()
                    onClicked: plugin.ortWechseln('punkt')
                }
            }

            // --- Punktaufnahme
            ColumnLayout {
                Layout.fillWidth: true
                visible: plugin.punktModus()
                spacing: 4
                ComboBox {
                    Layout.fillWidth: true
                    model: plugin.punkte.map(function (p) { return plugin.punktName(p.id) + (p.quelle === 'manuell' ? ' · Fadenkreuz' : (p.quelle === 'korrigiert' ? ' · verschoben' : '')); })
                    currentIndex: {
                        for (var i = 0; i < plugin.punkte.length; i++) if (plugin.punkte[i].id === plugin.aktiverPunkt) return i;
                        return -1;
                    }
                    displayText: currentIndex < 0 ? (plugin.punkte.length ? 'Aufnahme wählen …' : 'Noch keine Punktaufnahme') : currentText
                    onActivated: function (i) { plugin.punktWaehlen(plugin.punkte[i].id); }
                }
                RowLayout {
                    Layout.fillWidth: true
                    Button {
                        id: punktKnopf
                        objectName: 'gokartPunktKnopf'
                        Layout.fillWidth: true
                        Layout.preferredHeight: 48
                        text: plugin.punktTrotzdem ? 'Ungenau – trotzdem übernehmen' : '📍  Neue Aufnahme hier'
                        font.pixelSize: 16
                        contentItem: Label {
                            text: punktKnopf.text; font: punktKnopf.font; color: 'white'; elide: Text.ElideRight
                            horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
                        }
                        background: Rectangle { radius: 8; color: plugin.punktTrotzdem ? '#b86e00' : (punktKnopf.down ? '#0f5c3a' : plugin.gruen) }
                        onClicked: plugin.punktAnlegen('gps')
                    }
                    Button {
                        objectName: 'gokartFadenkreuzKnopf'
                        text: '+ Fadenkreuz'
                        onClicked: plugin.fadenkreuzStarten('neu')
                    }
                }
                Chip {
                    objectName: 'gokartPunktVerschieben'
                    Layout.fillWidth: true
                    visible: plugin.aktiverPunkt !== ''
                    text: 'Diesen Punkt verschieben'
                    onClicked: plugin.fadenkreuzStarten('verschieben')
                }
                Label {
                    objectName: 'gokartPunktStatus'
                    Layout.fillWidth: true
                    visible: plugin.punktStatus !== ''
                    text: plugin.punktStatus
                    wrapMode: Text.Wrap; font.pixelSize: 11
                    color: plugin.punktStatusFehler ? '#b3261e' : '#53645a'
                }
                Label {
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    font.pixelSize: 12
                    readonly property bool weit: plugin.gpsStand.abstand > plugin.punktCfg.radius
                    color: weit || (plugin.gpsStand.hacc > plugin.punktCfg.genauigkeit) ? '#a35a00' : '#53645a'
                    text: {
                        var g = plugin.gpsStand, t = [];
                        if (!g.ok) t.push('GPS: keine Position');
                        else t.push('GPS ' + (g.hacc >= 0 ? '±' + Math.round(g.hacc) + ' m' : 'Genauigkeit unbekannt') +
                                    (g.hacc > plugin.punktCfg.genauigkeit ? ' (Schwelle ' + plugin.punktCfg.genauigkeit + ' m)' : ''));
                        if (g.abstand >= 0) t.push(Math.round(g.abstand) + ' m vom Punkt' +
                                                   (weit ? ' – neue Aufnahme?' : ''));
                        var p = plugin.aktiverPunktDaten();
                        if (p && p.x !== null) t.push('Punkt R ' + Math.round(p.x) + ' · H ' + Math.round(p.y));
                        return t.join(' · ');
                    }
                }
            }

            // --- Fläche
            Label { text: 'Fläche'; font.bold: true; visible: !plugin.punktModus() }
            RowLayout {
                Layout.fillWidth: true
                visible: !plugin.punktModus()
                ComboBox {
                    id: flaechenAuswahl
                    Layout.fillWidth: true
                    model: plugin.flaechen.map(function (f) { return f.name ? f.name + ' (' + f.id + ')' : f.id; })
                    currentIndex: {
                        for (var i = 0; i < plugin.flaechen.length; i++) if (plugin.flaechen[i].id === plugin.aktiveFlaeche) return i;
                        return -1;
                    }
                    displayText: currentIndex < 0 ? 'Fläche wählen …' : currentText
                    onActivated: function (i) { plugin.flaecheWaehlen(plugin.flaechen[i].id, 'aus Liste'); }
                }
                Button { text: 'GPS'; flat: false; onClicked: plugin.flaecheAusGps() }
                Button { text: 'Karte'; onClicked: plugin.flaecheAusKartenmitte() }
            }
            CheckBox {
                id: unbenannteZeigen
                visible: !plugin.punktModus()
                text: 'Unbenannte Flächen anzeigen'
                checked: false
                onToggled: plugin.flaechenLaden()
            }

            // --- Bearbeitung eines vorhandenen Nachweises
            Rectangle {
                Layout.fillWidth: true
                visible: plugin.bearbeitung !== null
                implicitHeight: bearbeitSpalte.implicitHeight + 16
                radius: 8
                color: '#fff6e0'
                border.color: '#d9a400'
                ColumnLayout {
                    id: bearbeitSpalte
                    anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
                    anchors.margins: 8
                    spacing: 4
                    RowLayout {
                        Layout.fillWidth: true
                        Label {
                            Layout.fillWidth: true
                            text: plugin.bearbeitung ? '✎ Bearbeiten: ' + plugin.bearbeitung.name : ''
                            font.bold: true; elide: Text.ElideRight; color: '#1c2934'
                        }
                        Button { text: 'Abbrechen'; flat: true; onClicked: plugin.bearbeitenBeenden() }
                    }
                    Label {
                        Layout.fillWidth: true
                        visible: plugin.bearbeitung !== null
                        text: plugin.bearbeitung ? '<i>' + plugin.bearbeitung.wiss + '</i> · erfasst ' +
                              String(plugin.bearbeitung.am).replace('T', ' ').substring(0, 16) +
                              (plugin.bearbeitung.eingabe ? ' · Eingabe „' + plugin.bearbeitung.eingabe + '“' : '') : ''
                        textFormat: Text.StyledText; color: '#53645a'; font.pixelSize: 12; elide: Text.ElideRight
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        visible: plugin.bearbeitung !== null && String(plugin.bearbeitung.flaeche).charAt(0) !== '@'
                        Label { text: 'Fläche'; color: '#1c2934' }
                        ComboBox {
                            id: bearbeitFlaecheAuswahl
                            Layout.fillWidth: true
                            model: plugin.flaechen.map(function (f) { return f.name ? f.name + ' (' + f.id + ')' : f.id; })
                            currentIndex: {
                                for (var i = 0; i < plugin.flaechen.length; i++) if (plugin.flaechen[i].id === plugin.bearbeitFlaeche) return i;
                                return -1;
                            }
                            displayText: currentIndex < 0 ? (plugin.bearbeitFlaeche || 'Fläche wählen …') : currentText
                            onActivated: function (i) { plugin.bearbeitFlaeche = plugin.flaechen[i].id; }
                        }
                    }
                    TextField {
                        id: bemerkungFeld
                        objectName: 'gokartBemerkungFeld'
                        Layout.fillWidth: true
                        placeholderText: 'Bemerkung tippen oder Tastatur-Mikro (z. B. Deckung, blühend) …'
                    }
                }
            }

            // --- Suche
            Label { text: plugin.bearbeitung ? 'Neue Art (optional)' : 'Pflanzenname'; font.bold: true }
            TextField {
                id: sucheFeld
                objectName: 'gokartSucheFeld'
                Layout.fillWidth: true
                font.pixelSize: 20
                placeholderText: plugin.laedt ? 'Pflanzendaten werden geladen …'
                                 : (plugin.bearbeitung ? 'Neue Art sprechen/tippen – leer lassen = Art bleibt'
                                                       : (plugin.zusatzFelder.length ? 'Mikro oder tippen, z. B. „Calluna, Deckung drei“'
                                                                                     : 'Tastatur-Mikro antippen oder tippen'))
                enabled: !plugin.laedt
                inputMethodHints: Qt.ImhNoAutoUppercase
                onTextChanged: suchTimer.restart()
                onAccepted: {
                    suchTimer.stop(); plugin.suchen(text);
                    if (plugin.bearbeitung) { if (plugin.ausgewaehlt()) plugin.aenderungSpeichern(); }
                    else if (plugin.ausgewaehlt()) plugin.speichern();
                }
            }

            BusyIndicator { running: plugin.laedt; visible: running; Layout.alignment: Qt.AlignHCenter }

            Label {
                visible: !plugin.laedt && sucheFeld.text.length > 0 && plugin.treffer.length === 0
                text: 'Keine passende Art gefunden.'
                color: '#a33'
            }

            // --- Treffer (max. 5)
            Repeater {
                model: plugin.treffer
                delegate: Rectangle {
                    required property var modelData
                    required property int index
                    Layout.fillWidth: true
                    implicitHeight: zeile.implicitHeight + 16
                    radius: 8
                    color: index === plugin.auswahlIndex ? plugin.gruenHell : '#f6f8f6'
                    border.width: index === plugin.auswahlIndex ? 2 : 1
                    border.color: index === plugin.auswahlIndex ? plugin.gruen : '#d8e4da'
                    ColumnLayout {
                        id: zeile
                        anchors.left: parent.left; anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                        anchors.margins: 10
                        spacing: 2
                        Label {
                            Layout.fillWidth: true
                            text: modelData.taxon.deutscher_name || modelData.taxon.wissenschaftlicher_name
                            font.bold: true; font.pixelSize: 17; elide: Text.ElideRight; color: '#1c2934'
                        }
                        Label {
                            Layout.fillWidth: true
                            text: '<i>' + (modelData.taxon.voller_name || modelData.taxon.wissenschaftlicher_name || '—') + '</i> · ' + (modelData.taxon.rang || '') +
                                  (modelData.trefferart === 'synonym' ? ' · Synonym: ' + modelData.treffername : '') +
                                  (modelData.trefferart === 'eigen' ? ' · eigenes Synonym' : '')
                            textFormat: Text.StyledText
                            color: '#53645a'; font.pixelSize: 13; elide: Text.ElideRight
                        }
                    }
                    MouseArea { anchors.fill: parent; onClicked: plugin.auswahlIndex = index }
                }
            }

            CheckBox {
                id: synonymMerken
                objectName: 'gokartSynonymMerken'
                visible: plugin.ausgewaehlt() !== null && plugin.suchName().trim().length > 1 &&
                         !Suche.istExakterName(plugin.index, plugin.ausgewaehlt().id, plugin.suchName())
                text: '„' + plugin.suchName().trim() + '“ als eigenes Synonym merken'
            }

            Button {
                Layout.fillWidth: true
                visible: plugin.bearbeitung === null
                text: plugin.ausgewaehlt()
                      ? 'Zu ' + (plugin.ortSchluessel() ? plugin.ortName(plugin.ortSchluessel()) : '?') + ' hinzufügen: ' + (plugin.ausgewaehlt().taxon.deutscher_name || plugin.ausgewaehlt().taxon.wissenschaftlicher_name)
                      : 'Art auswählen'
                enabled: plugin.ausgewaehlt() !== null && plugin.ortSchluessel() !== ''
                highlighted: true
                font.pixelSize: 17
                onClicked: plugin.speichern()
            }
            Button {
                id: aenderKnopf
                objectName: 'gokartAenderKnopf'
                Layout.fillWidth: true
                visible: plugin.bearbeitung !== null
                // bindet an Auswahl, Fläche und Bemerkung, damit der Text live mitläuft
                text: { plugin.auswahlIndex; plugin.treffer; plugin.bearbeitFlaeche; bemerkungFeld.text; return plugin.aenderungText(); }
                enabled: text !== 'Keine Änderung'
                Layout.preferredHeight: 52
                font.pixelSize: 16
                // eigene Farben: unabhängig vom QField-Theme gut lesbar
                contentItem: Label {
                    text: aenderKnopf.text; font: aenderKnopf.font; color: 'white'; elide: Text.ElideRight
                    horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
                }
                background: Rectangle { radius: 8; color: !aenderKnopf.enabled ? '#9fb5a8' : (aenderKnopf.down ? '#0f5c3a' : plugin.gruen) }
                onClicked: plugin.aenderungSpeichern()
            }

            // --- Schnellleiste Zusatzangaben (gokart_zusatz) für die zuletzt erfasste bzw. bearbeitete Art
            Rectangle {
                Layout.fillWidth: true
                visible: plugin.zusatzFelder.length > 0 && plugin.zusatzZiel() !== null
                implicitHeight: zusatzSpalte.implicitHeight + 12
                radius: 8
                color: '#f3f7f4'
                border.color: '#d8e4da'
                ColumnLayout {
                    id: zusatzSpalte
                    anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
                    anchors.margins: 6
                    spacing: 2
                    Label {
                        Layout.fillWidth: true
                        text: plugin.zusatzZiel() ? 'Zusatz: ' + plugin.zusatzZiel().name : ''
                        font.bold: true; font.pixelSize: 13; elide: Text.ElideRight; color: '#1c2934'
                    }
                    Repeater {
                        model: plugin.zusatzFelder
                        delegate: Flow {
                            id: zusatzZeile
                            required property var modelData
                            Layout.fillWidth: true
                            spacing: 4
                            Label {
                                text: Zusatz.FELDER[zusatzZeile.modelData].name
                                width: 78; height: 38; verticalAlignment: Text.AlignVCenter
                                color: '#53645a'; font.pixelSize: 12
                            }
                            Repeater {
                                model: Zusatz.FELDER[zusatzZeile.modelData].werte
                                delegate: Chip {
                                    required property var modelData
                                    objectName: 'gokartZusatz_' + zusatzZeile.modelData + '_' + modelData
                                    text: modelData
                                    an: { var z = plugin.zusatzZiel(); return !!z && String(z[zusatzZeile.modelData] || '') === String(modelData); }
                                    onClicked: plugin.zusatzSetzen(zusatzZeile.modelData, modelData)
                                }
                            }
                        }
                    }
                }
            }

            // --- Diagnose des letzten Speicherns (hilft bei der Fehlersuche im Gelände)
            Label {
                Layout.fillWidth: true
                visible: plugin.diagnoseFehler   // nur bei Fehlern (Ablauf steht weiter in plugin.diagnose)
                text: 'Diagnose: ' + plugin.diagnose
                wrapMode: Text.Wrap
                font.pixelSize: 11
                color: plugin.diagnoseFehler ? '#a33' : '#6a7a70'
            }

            // --- Bereits erfasste Arten der Fläche
            RowLayout {
                Layout.fillWidth: true
                Layout.topMargin: 6
                Label {
                    Layout.fillWidth: true
                    text: plugin.ortSchluessel() ? 'Erfasst ' + (plugin.punktModus() ? 'an ' : 'auf ') + plugin.ortName(plugin.ortSchluessel()) + ': ' + plugin.artenDerFlaeche.length + ' Arten'
                                                 : (plugin.punktModus() ? 'Kein Punkt gewählt' : 'Keine Fläche gewählt')
                    font.bold: true
                    elide: Text.ElideRight
                }
                Button {
                    text: 'Letzte korrigieren'
                    flat: true
                    visible: plugin.artenDerFlaeche.length > 0 && plugin.bearbeitung === null
                    onClicked: plugin.letzteKorrigieren()
                }
            }
            ListView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                model: plugin.artenDerFlaeche
                delegate: Rectangle {
                    id: artZeile
                    required property var modelData
                    readonly property bool aktiv: plugin.bearbeitung !== null && plugin.bearbeitung.fid === modelData.fid
                    width: ListView.view.width
                    implicitHeight: artSpalte.implicitHeight + 4
                    color: aktiv ? '#fff6e0' : 'transparent'
                    radius: 6
                    ColumnLayout {
                        id: artSpalte
                        anchors.left: parent.left; anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                        spacing: 0
                        RowLayout {
                            Layout.fillWidth: true
                            Label { text: artZeile.modelData.name; Layout.fillWidth: true; elide: Text.ElideRight; color: '#1c2934'; font.bold: artZeile.aktiv }
                            Label { text: artZeile.modelData.wiss; color: '#6a7a70'; font.italic: true; font.pixelSize: 12; Layout.maximumWidth: 150; elide: Text.ElideRight }
                            Button {
                                text: 'Bearbeiten'
                                flat: true
                                visible: !artZeile.aktiv
                                onClicked: plugin.bearbeitenStarten(artZeile.modelData)
                            }
                            Button {
                                id: loeschKnopf
                                property bool sicher: false
                                text: sicher ? 'Sicher?' : 'Löschen'
                                flat: true
                                onClicked: { if (sicher) plugin.eintragLoeschen(artZeile.modelData.fid); else { sicher = true; zurueck.start(); } }
                                Timer { id: zurueck; interval: 3000; onTriggered: loeschKnopf.sicher = false }
                            }
                        }
                        Label {
                            Layout.fillWidth: true
                            visible: text !== ''
                            text: Zusatz.kurztext(artZeile.modelData)
                            color: '#167d50'; font.pixelSize: 12; elide: Text.ElideRight
                        }
                        Label {
                            Layout.fillWidth: true
                            visible: artZeile.modelData.bemerkung !== ''
                            text: '💬 ' + artZeile.modelData.bemerkung
                            color: '#53645a'; font.pixelSize: 12; elide: Text.ElideRight
                        }
                    }
                }
            }
        }
    }

    // ---------------------------------------------------------------- Standortfotos
    Popup {
        id: fotoDialog
        parent: iface.mainWindow().contentItem
        modal: true
        focus: true
        closePolicy: Popup.CloseOnEscape
        width: Math.min(parent.width - 16, 640)
        height: parent.height - 32
        x: (parent.width - width) / 2
        y: 16
        padding: 12
        background: Rectangle { color: 'white'; radius: 12 }
        Material.theme: Material.Light
        Material.accent: plugin.gruen
        Material.primary: plugin.gruen
        Material.foreground: '#1c2934'
        Material.background: 'white'
        palette.text: '#1c2934'
        palette.windowText: '#1c2934'
        palette.buttonText: '#1c2934'
        palette.base: 'white'

        ColumnLayout {
            anchors.fill: parent
            spacing: 8

            RowLayout {
                Layout.fillWidth: true
                Label { text: 'GoKart · Standortfotos'; font.bold: true; font.pixelSize: 20; color: plugin.gruen; Layout.fillWidth: true }
                Button { text: 'Schließen'; flat: true; onClicked: fotoDialog.close() }
            }

            Label { text: 'Fläche (Standort)'; font.bold: true }
            RowLayout {
                Layout.fillWidth: true
                ComboBox {
                    Layout.fillWidth: true
                    model: plugin.flaechen.map(function (f) { return f.name ? f.name + ' (' + f.id + ')' : f.id; })
                    currentIndex: {
                        for (var i = 0; i < plugin.flaechen.length; i++) if (plugin.flaechen[i].id === plugin.aktiveFlaeche) return i;
                        return -1;
                    }
                    displayText: currentIndex < 0 ? 'Fläche wählen …' : currentText
                    onActivated: function (i) { plugin.flaecheWaehlen(plugin.flaechen[i].id, 'aus Liste'); }
                }
                Button { text: 'GPS'; onClicked: plugin.flaecheAusGps() }
                Button { text: 'Karte'; onClicked: plugin.flaecheAusKartenmitte() }
            }

            Button {
                id: kameraKnopf
                Layout.fillWidth: true
                Layout.preferredHeight: 52
                enabled: plugin.aktiveFlaeche !== ''
                text: plugin.aktiveFlaeche ? '📷  Foto aufnehmen – ' + plugin.flaechenName(plugin.aktiveFlaeche) : 'Erst Fläche wählen'
                font.pixelSize: 17
                // eigene Farben: unabhängig vom QField-Theme gut lesbar
                contentItem: Label {
                    text: kameraKnopf.text; font: kameraKnopf.font; color: 'white'; elide: Text.ElideRight
                    horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
                }
                background: Rectangle { radius: 8; color: !kameraKnopf.enabled ? '#9fb5a8' : (kameraKnopf.down ? '#0f5c3a' : plugin.gruen) }
                onClicked: plugin.fotoAufnehmen()
            }

            Label {
                Layout.fillWidth: true
                visible: plugin.diagnoseFehler
                text: 'Diagnose: ' + plugin.diagnose
                wrapMode: Text.Wrap; font.pixelSize: 11; color: '#a33'
            }

            Label {
                text: plugin.aktiveFlaeche ? plugin.fotosDerFlaeche.length + ' Foto(s) von ' + plugin.flaechenName(plugin.aktiveFlaeche) : ''
                font.bold: true
                Layout.topMargin: 4
            }

            ListView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                spacing: 14
                model: plugin.fotosDerFlaeche
                delegate: ColumnLayout {
                    id: fotoKarte
                    required property var modelData
                    width: ListView.view.width
                    spacing: 4
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 260
                        color: '#f3f5f3'
                        radius: 8
                        Image {
                            id: bild
                            anchors.fill: parent
                            anchors.margins: 4
                            source: plugin.fotoUrl(fotoKarte.modelData.datei)
                            fillMode: Image.PreserveAspectFit
                            asynchronous: true; cache: false
                            sourceSize.width: 1000; sourceSize.height: 1000
                        }
                        Label {
                            anchors.centerIn: parent
                            visible: bild.status === Image.Error
                            text: 'Bilddatei nicht gefunden:\n' + fotoKarte.modelData.datei
                            horizontalAlignment: Text.AlignHCenter
                            color: '#a33'
                        }
                    }
                    Label {
                        text: String(fotoKarte.modelData.am).replace('T', ' ').substring(0, 16) +
                              (fotoKarte.modelData.lat !== null && fotoKarte.modelData.lat !== undefined
                               ? '  ·  GPS ' + Number(fotoKarte.modelData.lat).toFixed(5) + ', ' + Number(fotoKarte.modelData.lon).toFixed(5) : '')
                        color: '#6a7a70'; font.pixelSize: 12
                    }
                    TextField {
                        id: kommentar
                        Layout.fillWidth: true
                        text: fotoKarte.modelData.kommentar
                        placeholderText: 'Kommentar tippen oder Tastatur-Mikro (z. B. Licht, Feuchte) …'
                        onAccepted: plugin.fotoKommentar(fotoKarte.modelData, text)
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        Button {
                            Layout.fillWidth: true
                            text: 'Kommentar speichern'
                            enabled: kommentar.text.trim() !== fotoKarte.modelData.kommentar
                            onClicked: plugin.fotoKommentar(fotoKarte.modelData, kommentar.text)
                        }
                        Button {
                            id: entfernKnopf
                            property bool sicher: false
                            text: sicher ? 'Sicher?' : 'Foto entfernen'
                            flat: true
                            onClicked: { if (sicher) plugin.fotoEntfernen(fotoKarte.modelData); else { sicher = true; entfernZurueck.start(); } }
                            Timer { id: entfernZurueck; interval: 3000; onTriggered: entfernKnopf.sicher = false }
                        }
                    }
                }
            }
        }
    }

    // ---------------------------------------------------------------- Biotoptypen
    Popup {
        id: biotopDialog
        parent: iface.mainWindow().contentItem
        modal: true
        focus: true
        closePolicy: Popup.CloseOnEscape
        width: Math.min(parent.width - 16, 640)
        height: parent.height - 32
        x: (parent.width - width) / 2
        y: 16
        padding: 12
        background: Rectangle { color: 'white'; radius: 12 }
        Material.theme: Material.Light
        Material.accent: plugin.gruen
        Material.primary: plugin.gruen
        Material.foreground: '#1c2934'
        Material.background: 'white'
        palette.text: '#1c2934'
        palette.windowText: '#1c2934'
        palette.buttonText: '#1c2934'
        palette.base: 'white'

        ColumnLayout {
            anchors.fill: parent
            spacing: 8

            RowLayout {
                Layout.fillWidth: true
                Label { text: 'GoKart · Biotoptyp'; font.bold: true; font.pixelSize: 20; color: plugin.gruen; Layout.fillWidth: true }
                Button { text: 'Schließen'; flat: true; onClicked: biotopDialog.close() }
            }

            Label { text: 'Fläche'; font.bold: true }
            RowLayout {
                Layout.fillWidth: true
                ComboBox {
                    Layout.fillWidth: true
                    model: plugin.flaechen.map(function (f) { return f.name ? f.name + ' (' + f.id + ')' : f.id; })
                    currentIndex: {
                        for (var i = 0; i < plugin.flaechen.length; i++) if (plugin.flaechen[i].id === plugin.aktiveFlaeche) return i;
                        return -1;
                    }
                    displayText: currentIndex < 0 ? 'Fläche wählen …' : currentText
                    onActivated: function (i) { plugin.flaecheWaehlen(plugin.flaechen[i].id, 'aus Liste'); }
                }
                Button { text: 'GPS'; onClicked: plugin.flaecheAusGps() }
                Button { text: 'Karte'; onClicked: plugin.flaecheAusKartenmitte() }
            }

            // --- Schlüssel: kommt aus der Projektvariablen; ohne Variable hier wählbar (gilt nur bis zum Schließen)
            RowLayout {
                Layout.fillWidth: true
                Label { text: 'Schlüssel'; font.bold: true }
                Label {
                    Layout.fillWidth: true
                    visible: plugin.cfg.biotopSchluessel !== '' && plugin.cfg.biotopSchluessel !== undefined
                    text: {
                        var s = plugin.biotopSchluesselInfo();
                        return plugin.biotopSchluessel + (s ? ' – ' + s.name + (s.vollstaendig ? '' : ' (Katalog unvollständig)') : ' (Katalog fehlt im Projekt)');
                    }
                    elide: Text.ElideRight; color: '#53645a'
                }
                ComboBox {
                    Layout.fillWidth: true
                    visible: !(plugin.cfg.biotopSchluessel !== '' && plugin.cfg.biotopSchluessel !== undefined)
                    model: plugin.biotopSchluesselListe.map(function (s) { return s.schluessel + ' – ' + s.name; })
                    currentIndex: {
                        for (var i = 0; i < plugin.biotopSchluesselListe.length; i++)
                            if (plugin.biotopSchluesselListe[i].schluessel === plugin.biotopSchluessel) return i;
                        return -1;
                    }
                    displayText: currentIndex < 0 ? 'Schlüssel wählen …' : currentText
                    onActivated: function (i) { plugin.biotopSchluesselWaehlen(plugin.biotopSchluesselListe[i].schluessel); }
                }
            }

            TextField {
                id: biotopSucheFeld
                objectName: 'gokartBiotopSucheFeld'
                Layout.fillWidth: true
                font.pixelSize: 20
                enabled: plugin.biotopIndex !== null
                placeholderText: plugin.biotopIndex ? 'Code oder Name – tippen oder Tastatur-Mikro' : 'Erst Schlüssel wählen'
                inputMethodHints: Qt.ImhNoAutoUppercase
                onTextChanged: biotopSuchTimer.restart()
                onAccepted: { biotopSuchTimer.stop(); plugin.biotopSuchen(text); if (plugin.biotopGewaehlt()) plugin.biotopSpeichern(plugin.biotopeDerFlaeche.some(function (b) { return b.rolle === 'Haupt' && b.schluessel === plugin.biotopSchluessel; }) ? 'Neben' : 'Haupt'); }
            }

            Label {
                visible: biotopSucheFeld.text.length > 0 && plugin.biotopTreffer.length === 0
                text: 'Kein passender Biotoptyp gefunden.'
                color: '#a33'
            }

            Repeater {
                model: plugin.biotopTreffer
                delegate: Rectangle {
                    required property var modelData
                    required property int index
                    Layout.fillWidth: true
                    implicitHeight: bzeile.implicitHeight + 14
                    radius: 8
                    color: index === plugin.biotopAuswahl ? plugin.gruenHell : '#f6f8f6'
                    border.width: index === plugin.biotopAuswahl ? 2 : 1
                    border.color: index === plugin.biotopAuswahl ? plugin.gruen : '#d8e4da'
                    ColumnLayout {
                        id: bzeile
                        anchors.left: parent.left; anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                        anchors.margins: 10
                        spacing: 2
                        Label {
                            Layout.fillWidth: true
                            text: modelData.typ.code + ' – ' + modelData.typ.name
                            font.bold: true; font.pixelSize: 16; wrapMode: Text.Wrap; color: '#1c2934'
                        }
                        Label {
                            Layout.fillWidth: true
                            visible: text !== ''
                            text: [modelData.typ.nr ? 'Nr. ' + modelData.typ.nr : '',
                                   modelData.typ.unterTypen ? 'Obergruppe (' + modelData.typ.unterTypen + ' Typen)' : '',
                                   modelData.typ.ffh_lrt ? 'FFH ' + modelData.typ.ffh_lrt : '',
                                   modelData.typ.bund_code ? 'Bund ' + modelData.typ.bund_code : ''].filter(function (x) { return x; }).join(' · ')
                            color: '#53645a'; font.pixelSize: 13; elide: Text.ElideRight
                        }
                    }
                    MouseArea { anchors.fill: parent; onClicked: plugin.biotopAuswahl = index }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Button {
                    Layout.fillWidth: true
                    text: 'Hauptbiotop'
                    highlighted: true
                    enabled: plugin.biotopGewaehlt() !== null && plugin.aktiveFlaeche !== ''
                    onClicked: plugin.biotopSpeichern('Haupt')
                }
                Button {
                    Layout.fillWidth: true
                    text: 'Nebenbiotop'
                    enabled: plugin.biotopGewaehlt() !== null && plugin.aktiveFlaeche !== ''
                    onClicked: plugin.biotopSpeichern('Neben')
                }
            }

            Label {
                Layout.fillWidth: true
                visible: plugin.diagnoseFehler
                text: 'Diagnose: ' + plugin.diagnose
                wrapMode: Text.Wrap; font.pixelSize: 11; color: '#a33'
            }

            Label {
                text: plugin.aktiveFlaeche ? 'Biotoptypen von ' + plugin.flaechenName(plugin.aktiveFlaeche) + ': ' + plugin.biotopeDerFlaeche.length : 'Keine Fläche gewählt'
                font.bold: true
                Layout.topMargin: 6
            }
            ListView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                model: plugin.biotopeDerFlaeche
                delegate: RowLayout {
                    required property var modelData
                    width: ListView.view.width
                    Label {
                        text: (modelData.rolle === 'Haupt' ? '● ' : '○ ') + modelData.code + ' – ' + modelData.name +
                              (modelData.schluessel !== plugin.biotopSchluessel ? '  [' + modelData.schluessel + ']' : '')
                        Layout.fillWidth: true; elide: Text.ElideRight; color: '#1c2934'
                        font.bold: modelData.rolle === 'Haupt'
                    }
                    Button {
                        text: modelData.rolle === 'Haupt' ? '→ Neben' : '→ Haupt'
                        flat: true
                        onClicked: plugin.biotopRolleWechseln(modelData)
                    }
                    Button {
                        id: bLoesch
                        property bool sicher: false
                        text: sicher ? 'Sicher?' : 'Löschen'
                        flat: true
                        onClicked: { if (sicher) plugin.biotopEntfernen(modelData); else { sicher = true; bZurueck.start(); } }
                        Timer { id: bZurueck; interval: 3000; onTriggered: bLoesch.sicher = false }
                    }
                }
            }
        }
    }
}
