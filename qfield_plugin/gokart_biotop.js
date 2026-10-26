.pragma library
// GoKart – Suche in Biotoptypen-Schlüsseln (gleiche Regeln wie biotope.py im Desktop-Plugin)
// Code exakt > Name exakt > Code-Anfang > Name-Anfang > alle Wörter im Namen > ähnlich (Tipp-/Hörfehler).
// Codes können auch buchstabiert diktiert werden: "we em ypsilon" → WMy.

var ZEICHEN = { 'ä': 'a', 'ö': 'o', 'ü': 'u', 'ß': 'ss', 'é': 'e', 'è': 'e', 'à': 'a' };

var BUCHSTABEN = {
    a: 'a', ah: 'a', be: 'b', b: 'b', ce: 'c', c: 'c', zeh: 'c', de: 'd', d: 'd', e: 'e', eh: 'e',
    ef: 'f', eff: 'f', f: 'f', ge: 'g', g: 'g', ha: 'h', h: 'h', i: 'i', ih: 'i', jot: 'j', j: 'j',
    ka: 'k', k: 'k', el: 'l', l: 'l', em: 'm', m: 'm', en: 'n', n: 'n', o: 'o', oh: 'o', pe: 'p', p: 'p',
    ku: 'q', q: 'q', er: 'r', r: 'r', es: 's', s: 's', te: 't', t: 't', u: 'u', uh: 'u', vau: 'v', v: 'v',
    we: 'w', w: 'w', ix: 'x', x: 'x', ypsilon: 'y', y: 'y', zett: 'z', zet: 'z', z: 'z',
    null: '0', eins: '1', zwei: '2', zwo: '2', drei: '3', vier: '4', funf: '5', sechs: '6', sieben: '7', acht: '8', neun: '9'
};

function norm(text) {
    var s = String(text || '').toLowerCase(), out = '';
    for (var i = 0; i < s.length; i++) { var c = s.charAt(i); out += ZEICHEN[c] !== undefined ? ZEICHEN[c] : c; }
    return out;
}

function kompakt(text) { return norm(text).replace(/[^a-z0-9]/g, ''); }

function codeAusSprache(text) {
    var t = norm(text).split(/[\s,.\-]+/).filter(function (w) { return w.length > 0; });
    if (!t.length || t.length > 8) return null;
    if (t.length === 1 && t[0].length <= 4) return t[0];
    var b = t.map(function (w) { return BUCHSTABEN[w]; });
    if (b.every(function (x) { return !!x; })) return b.join('');
    if (t.every(function (w) { return w.length === 1 || /^\d+$/.test(w); })) return t.join('');
    return null;
}

function aehnlich(a, b) {
    if (!a.length || !b.length) return 0;
    var prev = [], cur, i, j;
    for (j = 0; j <= b.length; j++) prev.push(j);
    for (i = 1; i <= a.length; i++) {
        cur = [i];
        for (j = 1; j <= b.length; j++)
            cur.push(Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a.charAt(i - 1) === b.charAt(j - 1) ? 0 : 1)));
        prev = cur;
    }
    return 1 - prev[b.length] / Math.max(a.length, b.length);
}

function neuerIndex() { return { typen: [] }; }

function typHinzufuegen(index, typ) {
    typ._code = kompakt(typ.code);
    typ._name = norm(typ.name);
    typ._nameK = kompakt(typ.name);
    var alias = /\[([A-Za-z0-9]+)\]\s*$/.exec(typ.name);   // Buchstaben-Code hinter dem Namen (Berlin/Brandenburg)
    typ._alias = alias ? kompakt(alias[1]) : '';
    typ._teile = typ._name.split(/[\s\-,()\/]+/).map(kompakt).filter(function (x) { return x.length > 0; });
    index.typen.push(typ);
}

// Nach dem Laden: Zahl der Untertypen je Code (Obergruppen erkennbar machen)
function abschliessen(index) {
    var n = {};
    index.typen.forEach(function (t) { if (t.obercode) n[t.obercode] = (n[t.obercode] || 0) + 1; });
    index.typen.forEach(function (t) { t.unterTypen = n[t.code] || 0; });
}

function bewerten(q, qk, sprach, woerter, t) {
    if (qk === t._code || (sprach && sprach === t._code)) return 1.0;
    if (t._alias && (qk === t._alias || (sprach && sprach === t._alias))) return 0.99;
    if (qk === t._nameK) return 0.97;
    if (qk.length >= 2 && qk.length <= 4 && t._code.indexOf(qk) === 0) return 0.9 - 0.02 * (t._code.length - qk.length);
    if (t._nameK.indexOf(qk) === 0) return 0.88;
    if (woerter.length && woerter.every(function (w) { return t._nameK.indexOf(w) >= 0; }))
        return 0.8 + 0.05 * Math.min(1, qk.length / Math.max(1, t._nameK.length));
    var best = 0;
    if (woerter.length === 1)
        for (var i = 0; i < t._teile.length; i++) best = Math.max(best, aehnlich(qk, t._teile[i]));
    return 0.7 * Math.max(best, aehnlich(qk, t._nameK));
}

function suchen(index, eingabe, anzahl) {
    var qk = kompakt(eingabe);
    if (!index || !qk) return [];
    var q = norm(eingabe), sprach = codeAusSprache(eingabe);
    var woerter = q.split(/\s+/).map(kompakt).filter(function (w) { return w.length > 0; });
    var liste = [];
    for (var i = 0; i < index.typen.length; i++) {
        var t = index.typen[i], w = bewerten(q, qk, sprach, woerter, t);
        if (w >= 0.5) liste.push({ typ: t, wert: w, exakt: w >= 0.97 });
    }
    liste.sort(function (a, b) {
        var d = Math.round(b.wert * 1000) - Math.round(a.wert * 1000);
        if (d) return d;
        d = (b.typ.ebene || 0) - (a.typ.ebene || 0);
        return d || (a.typ.code < b.typ.code ? -1 : 1);
    });
    return liste.slice(0, anzahl || 6);
}
