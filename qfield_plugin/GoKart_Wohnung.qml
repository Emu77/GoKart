// GoKart – QField-Projekt-Plugin: Pflanzenarten per Sprache/Tastatur suchen und einer Fläche zuordnen
// Datei MUSS so heißen wie das Projekt (GoKart_Wohnung_qfield.qgs -> GoKart_Wohnung_qfield.qml) und daneben liegen.
// Version 0.2: Layer/Felder kommen aus den Projektvariablen, die das Desktop-Plugin ("Einrichten…") setzt:
//   gokart_flaechen_layer (Layer-ID), gokart_flaechen_key, gokart_flaechen_label,
//   gokart_nachweis_layer (Layer-ID), gokart_nachweis_fk
// Getestet gegen die API von QField 4.x; QField 3.x wird über einen Fallback unterstützt.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Controls.Material
import "gokart_suche.js" as Suche

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
    property var artenDerFlaeche: []   // [{ fid, name, wiss, taxon_id }]
    property string letzteMeldung: ''
    property string diagnose: ''         // letzter Speicher-Ablauf, wird im Dialog angezeigt
    property bool diagnoseFehler: false

    readonly property color gruen: '#167d50'
    readonly property color gruenHell: '#e6f6eb'

    Component.onCompleted: {
        if (!apiLaden()) {
            meldung('GoKart: QField-API nicht gefunden – Plugin inaktiv.');
            return;
        }
        iface.addItemToPluginsToolbar(gokartKnopf);
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

    // Liest gokart_*-Variablen; ohne Variablen wird nach bekannten Layernamen gesucht.
    function konfigLaden() {
        var v = projektVariablen();
        var c = {
            flaechen: layerAusRef(v.gokart_flaechen_layer) || ebene('Wohnung – Teilflächen') || ebene('flaechen'),
            key: v.gokart_flaechen_key || 'flaeche_id',
            label: v.gokart_flaechen_label || '',
            nachweise: layerAusRef(v.gokart_nachweis_layer) || ebene('artnachweise'),
            fk: v.gokart_nachweis_fk || 'flaeche_id',
            quelle: v.gokart_flaechen_layer ? 'Projektvariablen' : 'Layernamen (Fallback)'
        };
        if (c.flaechen && !c.label) {
            var kand = ['Raum', 'raum', 'name', 'Name', 'bezeichnung', 'Bezeichnung'];
            for (var i = 0; i < kand.length; i++)
                if (c.flaechen.fields.indexFromName(kand[i]) >= 0) { c.label = kand[i]; break; }
        }
        cfg = c;
        protokoll('Konfiguration aus ' + c.quelle + ': Flächen=' + (c.flaechen ? c.flaechen.name : 'FEHLT') +
                  ' [' + c.key + '], Nachweise=' + (c.nachweise ? c.nachweise.name : 'FEHLT') + ' [' + c.fk + ']',
                  !c.flaechen || !c.nachweise);
        return !!(c.flaechen && c.nachweise);
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

    function artenLaden() {
        var an = cfg.nachweise;
        var liste = [];
        if (an && aktiveFlaeche) {
            alleFeatures(an, '"' + cfg.fk + '" = ' + textSql(aktiveFlaeche), function (f) {
                liste.push({ fid: f.id, taxon_id: attr(f, 'taxon_id'),
                             name: attr(f, 'deutscher_name') || attr(f, 'wissenschaftlicher_name') || '?',
                             wiss: attr(f, 'wissenschaftlicher_name') || '', am: attr(f, 'erfasst_am') || '' });
            });
            liste.sort(function (a, b) { return String(b.am).localeCompare(String(a.am)); });
        }
        artenDerFlaeche = liste;
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

            var geom = f.geometry();
            if (!geom || geom.isNull() || geom.isEmpty())
                return;

            var groesse = geom.area();

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
        artenLaden();
        meldung('Aktive Fläche: ' + flaechenName(aktiveFlaeche) + ' (' + quelle + ')');
    }

    function flaecheAusGps() {
        var pos = null;
        try { var p = iface.positioning(); if (p) pos = p.positionInformation; } catch (e) {}
        if (!pos) {
            try { var ps = iface.findItemByObjectName('positionSource'); if (ps) pos = ps.positionInformation; } catch (e2) {}
        }
        if (!pos || !pos.latitudeValid || !pos.longitudeValid) { meldung('Keine gültige GPS-Position.'); return; }
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
    function suchen(text) {
        if (!index) return;
        var t = Suche.suchen(index, text, 5);
        treffer = t;
        // Genau ein exakter Treffer -> gleich vorauswählen (schneller Ablauf beim Diktieren)
        var exakte = t.filter(function (r) { return r.exakt; });
        auswahlIndex = (exakte.length === 1) ? t.indexOf(exakte[0]) : -1;
    }

    function ausgewaehlt() { return (auswahlIndex >= 0 && auswahlIndex < treffer.length) ? treffer[auswahlIndex] : null; }

    function speichern() {
        var r = ausgewaehlt();
        if (!r) { meldung('Bitte zuerst eine Art auswählen.'); return; }
        if (!aktiveFlaeche) { meldung('Bitte zuerst eine Fläche wählen.'); return; }
        var an = cfg.nachweise;
        if (!an) { meldung('Artnachweis-Layer fehlt – Einrichtung am Desktop prüfen.'); return; }
        offeneAenderungenSpeichern(an);

        var schonDa = 0;
        alleFeatures(an, '"' + cfg.fk + '" = ' + textSql(aktiveFlaeche) + ' AND "taxon_id" = ' + Number(r.id), function () { schonDa++; });
        var anzeige = r.taxon.deutscher_name || r.taxon.wissenschaftlicher_name;
        if (schonDa > 0) { meldung(anzeige + ' ist auf ' + flaechenName(aktiveFlaeche) + ' bereits erfasst.'); eingabeLeeren(); return; }

        var eingabe = sucheFeld.text;
        var ok = inBearbeitung(an, function () {
            var f = fu.createFeature(an);
            setze(f, an, cfg.fk, aktiveFlaeche);
            setze(f, an, 'taxon_id', Number(r.id));
            setze(f, an, 'wissenschaftlicher_name', r.taxon.wissenschaftlicher_name);
            setze(f, an, 'deutscher_name', r.taxon.deutscher_name);
            setze(f, an, 'original_eingabe', eingabe);
            setze(f, an, 'erfasst_am', jetzt());
            return lu.addFeature(an, f);
        });
        if (!ok) { meldung('Speichern fehlgeschlagen – Details unten im Dialog.'); artenLaden(); return; }

        if (synonymMerken.visible && synonymMerken.checked) synonymSpeichern(r.id, eingabe);
        meldung('✔ ' + anzeige + ' → ' + flaechenName(aktiveFlaeche));
        artenLaden();
        eingabeLeeren();
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
        var ok = inBearbeitung(an, function () { return lu.deleteFeature(qgisProject, an, fid, false); });
        meldung(ok ? 'Eintrag gelöscht.' : 'Löschen fehlgeschlagen.');
        artenLaden();
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
            artenLaden();
            sucheFeld.forceActiveFocus();
        }
    }

    Timer {
        id: ladeTimer
        interval: 50
        onTriggered: {
            var t0 = Date.now();
            var ok = indexLaden();
            flaechenLaden();
            artenLaden();
            laedt = false;
            if (ok) meldung('GoKart: ' + Object.keys(index.taxa).length + ' Taxa geladen (' + (Date.now() - t0) + ' ms)');
            sucheFeld.forceActiveFocus();
        }
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

            // --- Fläche
            Label { text: 'Fläche'; font.bold: true }
            RowLayout {
                Layout.fillWidth: true
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
                text: 'Unbenannte Flächen anzeigen'
                checked: false
                onToggled: plugin.flaechenLaden()
            }

            // --- Suche
            Label { text: 'Pflanzenname'; font.bold: true }
            TextField {
                id: sucheFeld
                objectName: 'gokartSucheFeld'
                Layout.fillWidth: true
                font.pixelSize: 20
                placeholderText: plugin.laedt ? 'Pflanzendaten werden geladen …' : 'Tastatur-Mikro antippen oder tippen'
                enabled: !plugin.laedt
                inputMethodHints: Qt.ImhNoAutoUppercase
                onTextChanged: suchTimer.restart()
                onAccepted: { suchTimer.stop(); plugin.suchen(text); if (plugin.ausgewaehlt()) plugin.speichern(); }
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
                visible: plugin.ausgewaehlt() !== null && sucheFeld.text.trim().length > 1 &&
                         !Suche.istExakterName(plugin.index, plugin.ausgewaehlt().id, sucheFeld.text)
                text: '„' + sucheFeld.text.trim() + '“ als eigenes Synonym merken'
            }

            Button {
                Layout.fillWidth: true
                text: plugin.ausgewaehlt()
                      ? 'Zu ' + (plugin.aktiveFlaeche ? plugin.flaechenName(plugin.aktiveFlaeche) : '?') + ' hinzufügen: ' + (plugin.ausgewaehlt().taxon.deutscher_name || plugin.ausgewaehlt().taxon.wissenschaftlicher_name)
                      : 'Art auswählen'
                enabled: plugin.ausgewaehlt() !== null && plugin.aktiveFlaeche !== ''
                highlighted: true
                font.pixelSize: 17
                onClicked: plugin.speichern()
            }

            // --- Diagnose des letzten Speicherns (hilft bei der Fehlersuche im Gelände)
            Label {
                Layout.fillWidth: true
                visible: plugin.diagnose !== ''
                text: 'Diagnose: ' + plugin.diagnose
                wrapMode: Text.Wrap
                font.pixelSize: 11
                color: plugin.diagnoseFehler ? '#a33' : '#6a7a70'
            }

            // --- Bereits erfasste Arten der Fläche
            Label {
                text: plugin.aktiveFlaeche ? 'Erfasst auf ' + plugin.flaechenName(plugin.aktiveFlaeche) + ': ' + plugin.artenDerFlaeche.length + ' Arten' : 'Keine Fläche gewählt'
                font.bold: true
                Layout.topMargin: 6
            }
            ListView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                model: plugin.artenDerFlaeche
                delegate: RowLayout {
                    required property var modelData
                    width: ListView.view.width
                    Label { text: modelData.name; Layout.fillWidth: true; elide: Text.ElideRight; color: '#1c2934' }
                    Label { text: modelData.wiss; color: '#6a7a70'; font.italic: true; font.pixelSize: 12; Layout.maximumWidth: 180; elide: Text.ElideRight }
                    Button {
                        id: loeschKnopf
                        property bool sicher: false
                        text: sicher ? 'Sicher?' : 'Löschen'
                        flat: true
                        onClicked: { if (sicher) plugin.eintragLoeschen(modelData.fid); else { sicher = true; zurueck.start(); } }
                        Timer { id: zurueck; interval: 3000; onTriggered: loeschKnopf.sicher = false }
                    }
                }
            }
        }
    }
}
