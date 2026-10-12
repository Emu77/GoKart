.pragma library
// GoKart – fehlertolerante Pflanzennamensuche (QML-JavaScript, auch in Node testbar)
// normalisieren() MUSS identisch zu werkzeuge/gokart_namen.py bleiben.

var ZEICHEN = {
    'ä': 'a', 'ö': 'o', 'ü': 'u', 'ß': 'ss', 'é': 'e', 'è': 'e', 'ê': 'e', 'ë': 'e',
    'á': 'a', 'à': 'a', 'â': 'a', 'å': 'a', 'í': 'i', 'ì': 'i', 'î': 'i', 'ï': 'i',
    'ó': 'o', 'ò': 'o', 'ô': 'o', 'ú': 'u', 'ù': 'u', 'û': 'u', 'ç': 'c', 'ñ': 'n',
    'ø': 'o', 'æ': 'ae', 'œ': 'oe', '×': 'x'
};

// Gewichtung der Namensart (höher = bevorzugt bei gleicher Trefferqualität)
var ART = { eigen: 6, deutsch: 5, zusatz: 5, wissenschaftlich: 4, synonym: 3 };
// Bevorzugung des Rangs bei Gleichstand (Art vor Unterart vor Aggregat vor Gattung)
var RANG = { SPE: 4, SSP: 3, VAR: 2, AGG: 2, GRU: 1, SEC: 1, SGE: 1, GAT: 0 };

function normalisieren(text) {
    var s = String(text === null || text === undefined ? '' : text).toLowerCase();
    var out = '';
    for (var i = 0; i < s.length; i++) {
        var ch = s.charAt(i);
        out += ZEICHEN.hasOwnProperty(ch) ? ZEICHEN[ch] : ch;
    }
    return out.replace(/[^a-z0-9]/g, '');
}

// Kölner Phonetik auf normalisiertem Text (a-z0-9): gleicht Hör-/Erkennungsfehler aus,
// z. B. "kwerkus" = "quercus", "stil" = "stiel", "knaulgras" = "knäuelgras"
function phonetik(s) {
    var roh = '';
    for (var i = 0; i < s.length; i++) {
        var c = s.charAt(i), vor = i > 0 ? s.charAt(i - 1) : '', nach = s.charAt(i + 1);
        var code = '';
        if ('aeijouy'.indexOf(c) >= 0) code = '0';
        else if (c === 'h') code = '';
        else if (c === 'b') code = '1';
        else if (c === 'p') code = (nach === 'h') ? '3' : '1';
        else if (c === 'd' || c === 't') code = ('csz'.indexOf(nach) >= 0 && nach !== '') ? '8' : '2';
        else if (c === 'f' || c === 'v' || c === 'w') code = '3';
        else if (c === 'g' || c === 'k' || c === 'q') code = '4';
        else if (c === 'c') {
            if (i === 0) code = ('ahkloqrux'.indexOf(nach) >= 0 && nach !== '') ? '4' : '8';
            else code = ('ahkoqux'.indexOf(nach) >= 0 && nach !== '' && vor !== 's' && vor !== 'z') ? '4' : '8';
        }
        else if (c === 'x') code = (vor === 'c' || vor === 'k' || vor === 'q') ? '8' : '48';
        else if (c === 'l') code = '5';
        else if (c === 'm' || c === 'n') code = '6';
        else if (c === 'r') code = '7';
        else if (c === 's' || c === 'z') code = '8';
        roh += code;
    }
    var out = '';
    for (var k = 0; k < roh.length; k++) {
        var d = roh.charAt(k);
        if (k > 0 && d === roh.charAt(k - 1)) continue;   // Doppelte zusammenfassen
        out += d;
    }
    return out.charAt(0) + out.substring(1).replace(/0/g, '');
}

// Levenshtein mit frühem Abbruch, wenn maxDist überschritten wird
function distanz(a, b, maxDist) {
    if (Math.abs(a.length - b.length) > maxDist) return maxDist + 1;
    var prev = new Array(b.length + 1);
    for (var j = 0; j <= b.length; j++) prev[j] = j;
    for (var i = 1; i <= a.length; i++) {
        var row = [i];
        var rowMin = i;
        var ca = a.charCodeAt(i - 1);
        for (var k = 1; k <= b.length; k++) {
            var v = Math.min(row[k - 1] + 1, prev[k] + 1, prev[k - 1] + (ca === b.charCodeAt(k - 1) ? 0 : 1));
            row[k] = v;
            if (v < rowMin) rowMin = v;
        }
        if (rowMin > maxDist) return maxDist + 1;
        prev = row;
    }
    return prev[b.length];
}

// Erzeugt einen leeren Suchindex
function neuerIndex() {
    return { taxa: {}, eintraege: [], schluessel: {} };
}

// taxon: { taxon_id, wissenschaftlicher_name, deutscher_name, rang }
function taxonHinzufuegen(index, taxon) {
    index.taxa[taxon.taxon_id] = taxon;
}

// art: 'eigen' | 'deutsch' | 'wissenschaftlich' | 'synonym'
function nameHinzufuegen(index, taxonId, name, art, schluessel) {
    var key = schluessel || normalisieren(name);
    if (!key || !index.taxa[taxonId]) return;
    var doppelt = taxonId + '|' + key;
    var vorhanden = index.schluessel[doppelt];
    var gewicht = ART[art] || 1;
    if (vorhanden !== undefined) {
        var e = index.eintraege[vorhanden];
        if (gewicht > e.gewicht) { e.gewicht = gewicht; e.art = art; e.name = String(name); }
        return;
    }
    index.schluessel[doppelt] = index.eintraege.length;
    index.eintraege.push({ id: taxonId, key: key, phon: phonetik(key), name: String(name), art: art, gewicht: gewicht });
}

function bewerten(q, qp, e) {
    if (q === e.key) return 1000 + e.gewicht;
    if (e.key.indexOf(q) === 0) return 820 + Math.min(q.length / e.key.length, 1) * 100 + e.gewicht;
    if (q.length >= 3 && e.key.indexOf(q) > 0) return 700 + Math.min(q.length / e.key.length, 1) * 100 + e.gewicht;
    var best = 0;
    // Ähnlich klingend: Phonetik-Code gleich / Präfix / wenige Abweichungen.
    // Kölner Phonetik ist grob, daher zusätzlich mit Buchstabenähnlichkeit gewichten.
    if (qp.length >= 3 && qp.charAt(0) === e.phon.charAt(0)) {
        var pScore = 0;
        if (qp === e.phon) pScore = 1;
        else if (e.phon.indexOf(qp) === 0) pScore = 0.85 * Math.min(qp.length / e.phon.length + 0.3, 1);
        else {
            var mp = Math.max(1, Math.floor(qp.length * 0.25));
            var dp = distanz(qp, e.phon, mp);
            if (dp <= mp) pScore = 0.8 * (1 - dp / Math.max(qp.length, e.phon.length));
        }
        if (pScore > 0) {
            var vgl = e.key.length > q.length + 4 ? e.key.substring(0, q.length + 2) : e.key;
            var lang = Math.max(q.length, vgl.length);
            var buchst = 1 - distanz(q, vgl, lang) / lang;
            best = 380 + pScore * 200 + buchst * 300 + e.gewicht;
        }
    }
    // Tippfehler (gleicher Anfangsbuchstabe, max. ~30 % abweichende Zeichen)
    if (q.charAt(0) === e.key.charAt(0)) {
        var maxDist = Math.max(1, Math.floor(Math.max(q.length, e.key.length) * 0.3));
        var d = distanz(q, e.key, maxDist);
        if (d <= maxDist) best = Math.max(best, (1 - d / Math.max(q.length, e.key.length)) * 650 + e.gewicht);
    }
    return best;
}

// Liefert bis zu `anzahl` Treffer: [{ id, taxon, score, treffername, trefferart, exakt }]
function suchen(index, eingabe, anzahl) {
    anzahl = anzahl || 5;
    var q = normalisieren(eingabe);
    if (!q) return [];
    var qp = phonetik(q);
    var beste = {};
    for (var i = 0; i < index.eintraege.length; i++) {
        var e = index.eintraege[i];
        var s = bewerten(q, qp, e);
        if (s <= 0) continue;
        var b = beste[e.id];
        if (!b || s > b.score) beste[e.id] = { id: e.id, score: s, treffername: e.name, trefferart: e.art, exakt: s >= 1000 };
    }
    var liste = [];
    for (var id in beste) {
        var t = index.taxa[id];
        var r = beste[id];
        r.taxon = t;
        r.id = t.taxon_id;
        liste.push(r);
    }
    function sortieren(a, b) {
        if (b.score !== a.score) return b.score - a.score;
        var ra = RANG[a.taxon.rang] || 0, rb = RANG[b.taxon.rang] || 0;
        if (rb !== ra) return rb - ra;
        return String(a.taxon.wissenschaftlicher_name).localeCompare(String(b.taxon.wissenschaftlicher_name));
    }
    liste.sort(sortieren);
    // Schwache Treffer weglassen, wenn es deutlich bessere gibt
    if (liste.length) {
        var grenze = Math.max(450, liste[0].score - 330);
        liste = liste.filter(function (r) { return r.score >= grenze; });
    }
    // Eindeutiger Treffer: Arten derselben Gattung als Alternativen nach vorn holen
    if (liste.length && liste[0].exakt && liste[0].taxon.wissenschaftlicher_name) {
        var gattung = String(liste[0].taxon.wissenschaftlicher_name).split(' ')[0] + ' ';
        for (var n = 1; n < liste.length; n++) {
            if (String(liste[n].taxon.wissenschaftlicher_name).indexOf(gattung) === 0)
                liste[n].score = Math.max(liste[n].score, 740);
        }
        liste.sort(sortieren);
    }
    return liste.slice(0, anzahl);
}

// Hat die Eingabe exakt einen Namen dieses Taxons getroffen?
function istExakterName(index, taxonId, eingabe) {
    if (!index) return true;
    var q = normalisieren(eingabe);
    return index.schluessel[taxonId + '|' + q] !== undefined;
}
