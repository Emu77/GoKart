// GoKart – QField-Projekt-Plugin: Pflanzenarten per Sprache/Tastatur suchen und einer Fläche zuordnen
// Datei MUSS so heißen wie das Projekt (gokart.qgs -> gokart.qml) und daneben liegen.
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
    property var index: null
    property bool laedt: false
    property var treffer: []
    property int auswahlIndex: -1
    property var flaechen: []          // [{ id, name }]
    property string aktiveFlaeche: ''
    property var artenDerFlaeche: []   // [{ fid, name, wiss, taxon_id }]
    property string letzteMeldung: ''

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
        for (var i = 0; i < varianten.length; i++) {
            try {
                var o = Qt.createQmlObject(varianten[i], plugin, 'gokartApi' + i);
                if (o && o.lu && o.fu) { lu = o.lu; fu = o.fu; return true; }
            } catch (e) { /* nächste Variante */ }
        }
        return false;
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

    function inBearbeitung(lyr, aktion) {
        lyr.startEditing();
        var ok = false;
        try { ok = aktion(); } catch (e) { console.log('GoKart: ' + e); ok = false; }
        if (ok) ok = lyr.commitChanges();
        if (!ok) { try { lyr.rollBack(); } catch (e2) {} }
        return ok;
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
                deutscher_name: attr(f, 'anzeige_name') || attr(f, 'deutscher_name'),
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
        var fl = ebene('flaechen');
        var liste = [];
        if (fl) alleFeatures(fl, null, function (f) {
            var id = attr(f, 'flaeche_id');
            if (id) liste.push({ id: String(id), name: attr(f, 'name') || '' });
        });
        liste.sort(function (a, b) { return a.id.localeCompare(b.id); });
        flaechen = liste;
        if (!aktiveFlaeche && liste.length === 1) aktiveFlaeche = liste[0].id;
    }

    function artenLaden() {
        var an = ebene('artnachweise');
        var liste = [];
        if (an && aktiveFlaeche) {
            alleFeatures(an, '"flaeche_id" = ' + textSql(aktiveFlaeche), function (f) {
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
        var fl = ebene('flaechen');
        if (!fl) return null;
        var ziel = 'EPSG:25833';
        try { if (fl.crs && fl.crs.authid) ziel = fl.crs.authid; } catch (e) {}
        var expr = "intersects($geometry, transform(make_point(" + Number(x) + ", " + Number(y) + "), " +
                   textSql(crsAuthid) + ", " + textSql(ziel) + "))";
        var gefunden = null;
        alleFeatures(fl, expr, function (f) { if (!gefunden) gefunden = attr(f, 'flaeche_id'); });
        return gefunden;
    }

    function flaecheWaehlen(id, quelle) {
        if (!id) { meldung('Keine Fläche ' + quelle + ' gefunden.'); return; }
        aktiveFlaeche = String(id);
        artenLaden();
        meldung('Aktive Fläche: ' + aktiveFlaeche + ' (' + quelle + ')');
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
        var an = ebene('artnachweise');
        if (!an) { meldung('Layer "artnachweise" fehlt.'); return; }

        var schonDa = 0;
        alleFeatures(an, '"flaeche_id" = ' + textSql(aktiveFlaeche) + ' AND "taxon_id" = ' + Number(r.id), function () { schonDa++; });
        var anzeige = r.taxon.deutscher_name || r.taxon.wissenschaftlicher_name;
        if (schonDa > 0) { meldung(anzeige + ' ist auf ' + aktiveFlaeche + ' bereits erfasst.'); eingabeLeeren(); return; }

        var eingabe = sucheFeld.text;
        var ok = inBearbeitung(an, function () {
            var f = fu.createFeature(an);
            setze(f, an, 'flaeche_id', aktiveFlaeche);
            setze(f, an, 'taxon_id', Number(r.id));
            setze(f, an, 'wissenschaftlicher_name', r.taxon.wissenschaftlicher_name);
            setze(f, an, 'deutscher_name', r.taxon.deutscher_name);
            setze(f, an, 'original_eingabe', eingabe);
            setze(f, an, 'erfasst_am', jetzt());
            return lu.addFeature(an, f);
        });
        if (!ok) { meldung('Speichern fehlgeschlagen.'); return; }

        if (synonymMerken.visible && synonymMerken.checked) synonymSpeichern(r.id, eingabe);
        meldung('✔ ' + anzeige + ' → ' + aktiveFlaeche);
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
        var an = ebene('artnachweise');
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
                Button { text: '✕'; flat: true; onClicked: dialog.close() }
            }

            // --- Fläche
            Label { text: 'Fläche'; font.bold: true }
            RowLayout {
                Layout.fillWidth: true
                ComboBox {
                    id: flaechenAuswahl
                    Layout.fillWidth: true
                    model: plugin.flaechen.map(function (f) { return f.name ? f.id + ' – ' + f.name : f.id; })
                    currentIndex: {
                        for (var i = 0; i < plugin.flaechen.length; i++) if (plugin.flaechen[i].id === plugin.aktiveFlaeche) return i;
                        return -1;
                    }
                    displayText: currentIndex < 0 ? 'Fläche wählen …' : currentText
                    onActivated: function (i) { plugin.flaecheWaehlen(plugin.flaechen[i].id, 'aus Liste'); }
                }
                Button { text: '📍 GPS'; flat: false; onClicked: plugin.flaecheAusGps() }
                Button { text: '✛ Karte'; onClicked: plugin.flaecheAusKartenmitte() }
            }

            // --- Suche
            Label { text: 'Pflanzenname'; font.bold: true }
            TextField {
                id: sucheFeld
                objectName: 'gokartSucheFeld'
                Layout.fillWidth: true
                font.pixelSize: 20
                placeholderText: plugin.laedt ? 'Pflanzendaten werden geladen …' : '🎤 sprechen oder tippen'
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
                      ? 'Zu ' + (plugin.aktiveFlaeche || '?') + ' hinzufügen: ' + (plugin.ausgewaehlt().taxon.deutscher_name || plugin.ausgewaehlt().taxon.wissenschaftlicher_name)
                      : 'Art auswählen'
                enabled: plugin.ausgewaehlt() !== null && plugin.aktiveFlaeche !== ''
                highlighted: true
                font.pixelSize: 17
                onClicked: plugin.speichern()
            }

            // --- Bereits erfasste Arten der Fläche
            Label {
                text: plugin.aktiveFlaeche ? 'Erfasst auf ' + plugin.aktiveFlaeche + ': ' + plugin.artenDerFlaeche.length + ' Arten' : 'Keine Fläche gewählt'
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
                        text: sicher ? 'Löschen?' : '✕'
                        flat: true
                        onClicked: { if (sicher) plugin.eintragLoeschen(modelData.fid); else { sicher = true; zurueck.start(); } }
                        Timer { id: zurueck; interval: 3000; onTriggered: loeschKnopf.sicher = false }
                    }
                }
            }
        }
    }
}
