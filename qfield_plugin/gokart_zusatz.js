.pragma library
// GoKart – Zusatzangaben zu Artnachweisen und Hilfen für Punktaufnahmen (QML-JavaScript, auch in Node testbar)
//
// zerlegen("Calluna, Deckung drei, blühend") -> { name: "Calluna", werte: { deckung: "3", phaenologie: "blühend" },
//                                                unklar: [] }
// Der Artname ist alles vor dem ersten Schlüsselwort (Deckung, Anzahl, Stück …) bzw. Phänologie-Wort.
// Werte und Listen MÜSSEN zu qgis_plugin/gokart_desktop/punkte.py (DECKUNG, ANZAHL, PHAENOLOGIE) passen.

var DECKUNG = ['r', '+', '1', '2m', '2a', '2b', '3', '4', '5'];
var ANZAHL = ['1', '2–5', '6–25', '26–100', '>100'];
var PHAENOLOGIE = ['vegetativ', 'Knospe', 'blühend', 'fruchtend', 'abgestorben'];
var FELDER = {
    deckung: { name: 'Deckung', werte: DECKUNG },
    anzahl: { name: 'Anzahl', werte: ANZAHL },
    phaenologie: { name: 'Phänologie', werte: PHAENOLOGIE }
};
var REIHENFOLGE = ['deckung', 'anzahl', 'phaenologie'];

var ZAHLWORT = {
    'null': 0, 'ein': 1, 'eins': 1, 'eine': 1, 'einen': 1, 'zwei': 2, 'zwo': 2, 'drei': 3, 'vier': 4, 'fuenf': 5,
    'sechs': 6, 'sieben': 7, 'acht': 8, 'neun': 9, 'zehn': 10, 'elf': 11, 'zwoelf': 12, 'fuenfzehn': 15,
    'zwanzig': 20, 'dreissig': 30, 'vierzig': 40, 'fuenfzig': 50, 'hundert': 100, 'einhundert': 100,
    'tausend': 1000
};
var PHAENO_WORT = {
    'vegetativ': 'vegetativ', 'steril': 'vegetativ',
    'knospe': 'Knospe', 'knospen': 'Knospe', 'knospend': 'Knospe',
    'bluehend': 'blühend', 'blueht': 'blühend', 'bluete': 'blühend', 'blute': 'blühend', 'bluhend': 'blühend',
    'fruchtend': 'fruchtend', 'frucht': 'fruchtend', 'fruechte': 'fruchtend', 'fruchtet': 'fruchtend',
    'fruchtstand': 'fruchtend',
    'abgestorben': 'abgestorben', 'vertrocknet': 'abgestorben', 'tot': 'abgestorben'
};
var DECKUNG_WORT = { 'deckung': 1, 'deckungsgrad': 1, 'dg': 1 };
var ANZAHL_WORT = { 'anzahl': 1, 'menge': 1 };
var STUECK_WORT = { 'stueck': 1, 'stuck': 1, 'exemplare': 1, 'exemplar': 1, 'individuen': 1, 'pflanzen': 1 };
var FUELL_WORT = { 'in': 1, 'ist': 1, 'grad': 1, 'mit': 1, 'und': 1, 'etwa': 1, 'ca': 1, 'circa': 1 };

function einfach(t) {
    return String(t).toLowerCase().replace(/ä/g, 'ae').replace(/ö/g, 'oe').replace(/ü/g, 'ue').replace(/ß/g, 'ss');
}

function zahl(t) {
    if (/^\d+$/.test(t)) return Number(t);
    return ZAHLWORT.hasOwnProperty(t) ? ZAHLWORT[t] : null;
}

// Ganzzahl -> Klasse aus ANZAHL (für die Schnellleiste); Text bleibt die genaue Zahl
function anzahlKlasse(n) {
    n = Number(n);
    if (!(n >= 1)) return '';
    if (n === 1) return '1';
    if (n <= 5) return '2–5';
    if (n <= 25) return '6–25';
    if (n <= 100) return '26–100';
    return '>100';
}

function istSchluessel(t) {
    return DECKUNG_WORT[t] || ANZAHL_WORT[t] || PHAENO_WORT.hasOwnProperty(t);
}

// Deckung ab Position i: liefert { wert, n } (n = verbrauchte Wörter) oder null
function deckungLesen(w, i) {
    var t = w[i], nx = w[i + 1] || '';
    if (t === undefined) return null;
    if (t === 'r' || t === 'er' || t === 'err' || t === 'rar') return { wert: 'r', n: 1 };
    if (t === '+' || t === 'plus') return { wert: '+', n: 1 };
    var kompakt = /^([1-5])([mab])?$/.exec(t);
    if (kompakt) {
        if (kompakt[1] === '2' && !kompakt[2]) {
            var b = buchstabe(nx);
            return b ? { wert: '2' + b, n: 2 } : null;
        }
        return { wert: kompakt[1] + (kompakt[1] === '2' ? kompakt[2] : ''), n: 1 };
    }
    var z = zahl(t);
    if (z === null || z < 1 || z > 5) return null;
    if (z === 2) {
        var b2 = buchstabe(nx);
        return b2 ? { wert: '2' + b2, n: 2 } : null;   // "zwei" allein ist in der Skala mehrdeutig
    }
    return { wert: String(z), n: 1 };
}

function buchstabe(t) {
    if (t === 'm' || t === 'em') return 'm';
    if (t === 'a') return 'a';
    if (t === 'b' || t === 'be' || t === 'bee') return 'b';
    return '';
}

// Anzahl ab Position i: "12", "zwölf", "zwei bis fünf", "über hundert", "mehr als hundert"
function anzahlLesen(w, i) {
    var t = w[i];
    if (t === undefined) return null;
    if ((t === 'ueber' || t === 'mehr') && (w[i + 1] === 'hundert' || w[i + 1] === '100' ||
                                          (w[i + 1] === 'als' && (w[i + 2] === 'hundert' || w[i + 2] === '100'))))
        return { wert: '>100', n: w[i + 1] === 'als' ? 3 : 2 };
    if (/^>\s*100$/.test(t)) return { wert: '>100', n: 1 };
    var bereich = /^(\d+)[-–](\d+)$/.exec(t);
    if (bereich) {
        var k = bereich[1] + '–' + bereich[2];
        return ANZAHL.indexOf(k) >= 0 ? { wert: k, n: 1 } : null;
    }
    var a = zahl(t);
    if (a === null) return null;
    if (w[i + 1] === 'bis') {
        var b = zahl(w[i + 2] || '');
        if (b !== null) {
            var kl = a + '–' + b;
            return ANZAHL.indexOf(kl) >= 0 ? { wert: kl, n: 3 } : { wert: String(b), n: 3 };
        }
    }
    return { wert: String(a), n: 1 };
}

function zerlegen(text) {
    var roh = String(text === null || text === undefined ? '' : text);
    var teile = roh.split(/[\s,;]+/).filter(function (x) { return x !== ''; });
    var w = teile.map(function (x) { return einfach(x).replace(/[.:!?]+$/, ''); });
    var start = -1;
    for (var i = 0; i < w.length; i++) {
        if (istSchluessel(w[i])) { start = i; break; }
        if (STUECK_WORT[w[i]] && i > 0 && zahl(w[i - 1]) !== null) {
            start = i - 1;                                       // "12 Stück"
            if (w[i - 2] === 'bis' && i >= 3 && zahl(w[i - 3]) !== null) start = i - 3;   // "2 bis 5 Stück"
            else if (w[i - 2] === 'ueber') start = i - 2;                                 // "über 100 Stück"
            else if (w[i - 2] === 'als' && w[i - 3] === 'mehr') start = i - 3;           // "mehr als 100"
            break;
        }
    }
    var erg = { name: roh.trim(), werte: {}, unklar: [] };
    if (start < 0) return erg;
    if (start === 0) erg.name = '';                  // nur Zusatzangaben (z. B. beim Bearbeiten: „Deckung vier“)
    while (start > 1 && FUELL_WORT[w[start - 1]]) start--;      // "… in Knospe", "… mit Deckung"
    if (start > 0) erg.name = teile.slice(0, start).join(' ').replace(/[,;:\s]+$/, '');
    var j = start;
    while (j < w.length) {
        var t = w[j];
        if (FUELL_WORT[t]) { j++; continue; }
        if (DECKUNG_WORT[t]) {
            var k = j + 1;
            while (FUELL_WORT[w[k]]) k++;
            var d = deckungLesen(w, k);
            if (d) { erg.werte.deckung = d.wert; j = k + d.n; }
            else { erg.unklar.push(teile.slice(j, k + 1).join(' ')); j = k + 1; }
            continue;
        }
        if (ANZAHL_WORT[t]) {
            var m = j + 1;
            while (FUELL_WORT[w[m]]) m++;
            var a = anzahlLesen(w, m);
            if (a) { erg.werte.anzahl = a.wert; j = m + a.n; }
            else { erg.unklar.push(teile.slice(j, m + 1).join(' ')); j = m + 1; }
            continue;
        }
        if (PHAENO_WORT.hasOwnProperty(t)) { erg.werte.phaenologie = PHAENO_WORT[t]; j++; continue; }
        var vor = anzahlLesen(w, j);
        if (vor && STUECK_WORT[w[j + vor.n]]) { erg.werte.anzahl = vor.wert; j += vor.n + 1; continue; }
        if (STUECK_WORT[t]) { j++; continue; }
        erg.unklar.push(teile[j]);
        j++;
    }
    return erg;
}

// "deckung, phaenologie" -> ['deckung', 'phaenologie'] in fester Reihenfolge
function aktiveFelder(text) {
    var teile = String(text === null || text === undefined ? '' : text).toLowerCase().split(/[,;]/)
        .map(function (t) { return t.trim(); });
    return REIHENFOLGE.filter(function (f) { return teile.indexOf(f) >= 0; });
}

// Kurztext für Listen: "D 2a · blühend · 6–25"
function kurztext(e) {
    var t = [];
    if (e.deckung) t.push('D ' + e.deckung);
    if (e.phaenologie) t.push(e.phaenologie);
    if (e.anzahl) t.push('n ' + e.anzahl);
    return t.join(' · ');
}

// ---------------------------------------------------------------- Punktaufnahmen
// Eindeutige Punkt-ID aus Zeitstempel "2026-11-07T14:12:33" + 4 Zufallszeichen: P-20261107-141233-k7x2
function neuePunktId(zeitstempel, zufall) {
    var z = String(zeitstempel).replace(/[-:]/g, '').replace('T', '-');
    var zeichen = 'abcdefghjkmnpqrstuvwxyz23456789';
    var r = '';
    for (var i = 0; i < 4; i++) {
        var x = (zufall && zufall.length > i) ? zufall[i] : Math.random();
        r += zeichen.charAt(Math.floor(x * zeichen.length) % zeichen.length);
    }
    return 'P-' + z + '-' + r;
}

function abstand(x1, y1, x2, y2) {
    var dx = Number(x2) - Number(x1), dy = Number(y2) - Number(y1);
    return Math.sqrt(dx * dx + dy * dy);
}

// Zahl aus einer Projektvariablen, sonst Standard
function zahlOder(v, standard) {
    var n = Number(String(v === null || v === undefined ? '' : v).replace(',', '.'));
    return (String(v === null || v === undefined ? '' : v).trim() !== '' && isFinite(n) && n > 0) ? n : standard;
}
