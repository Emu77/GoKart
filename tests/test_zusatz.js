// Aufruf: node tests/test_zusatz.js   – Zusatzangaben aus Spracheingabe (gokart_zusatz.js)
const fs = require('fs'), vm = require('vm'), path = require('path');
const code = fs.readFileSync(path.join(__dirname, '../qfield_plugin/gokart_zusatz.js'), 'utf8').replace('.pragma library', '');
const Z = {}; vm.createContext(Z); vm.runInContext(code, Z);

const faelle = [
  ['Calluna', 'Calluna', {}],
  ['Calluna, Deckung drei, blühend', 'Calluna', { deckung: '3', phaenologie: 'blühend' }],
  ['Stiel-Eiche Deckung 2a', 'Stiel-Eiche', { deckung: '2a' }],
  ['Stieleiche deckung zwei a', 'Stieleiche', { deckung: '2a' }],
  ['Spitz Wegerich Deckung zwei m fruchtend', 'Spitz Wegerich', { deckung: '2m', phaenologie: 'fruchtend' }],
  ['Rot-Klee Deckung plus', 'Rot-Klee', { deckung: '+' }],
  ['Rot-Klee Deckung R', 'Rot-Klee', { deckung: 'r' }],
  ['Rot-Klee Deckungsgrad 4', 'Rot-Klee', { deckung: '4' }],
  ['Orchis mascula 12 Stück', 'Orchis mascula', { anzahl: '12' }],
  ['Orchis mascula Anzahl zwei bis fünf', 'Orchis mascula', { anzahl: '2–5' }],
  ['Orchis mascula zwei bis fünf Exemplare', 'Orchis mascula', { anzahl: '2–5' }],
  ['Orchis mascula über hundert Stück', 'Orchis mascula', { anzahl: '>100' }],
  ['Orchis mascula Anzahl mehr als hundert', 'Orchis mascula', { anzahl: '>100' }],
  ['Gänseblümchen blüht', 'Gänseblümchen', { phaenologie: 'blühend' }],
  ['Gänseblümchen in Knospe', 'Gänseblümchen', { phaenologie: 'Knospe' }],
  ['Huflattich vegetativ Deckung 1', 'Huflattich', { phaenologie: 'vegetativ', deckung: '1' }],
  ['Huflattich Deckung zwei', 'Huflattich', {}],          // "zwei" allein mehrdeutig -> unklar
  ['Hasel mit Deckung 3', 'Hasel', { deckung: '3' }],
  ['Deckung vier', '', { deckung: '4' }],                  // nur Zusatz (Bearbeiten)
  ['blühend', '', { phaenologie: 'blühend' }],
];
let fehler = 0;
for (const [ein, name, werte] of faelle) {
  const r = Z.zerlegen(ein);
  const ok = r.name === name && JSON.stringify(sortiert(r.werte)) === JSON.stringify(sortiert(werte));
  if (!ok) fehler++;
  console.log((ok ? '✓' : '✗') + ' ' + JSON.stringify(ein) + ' -> ' + JSON.stringify(r));
}
function sortiert(o) { return Object.fromEntries(Object.entries(o).sort()); }

const unklar = Z.zerlegen('Huflattich Deckung zwei').unklar;
if (!unklar.length) { fehler++; console.log('✗ "Deckung zwei" sollte als unklar gemeldet werden'); }
const id = Z.neuePunktId('2026-11-07T14:12:33', [0, 0.5, 0.99, 0.1]);
if (!/^P-20261107-141233-[a-z2-9]{4}$/.test(id)) { fehler++; console.log('✗ Punkt-ID ' + id); } else console.log('✓ Punkt-ID ' + id);
if (Z.anzahlKlasse(12) !== '6–25' || Z.anzahlKlasse(1) !== '1' || Z.anzahlKlasse(101) !== '>100') { fehler++; console.log('✗ anzahlKlasse'); }
if (Z.aktiveFelder('phaenologie, deckung').join() !== 'deckung,phaenologie') { fehler++; console.log('✗ aktiveFelder'); }
if (Z.zahlOder('', 10) !== 10 || Z.zahlOder('7,5', 10) !== 7.5 || Z.zahlOder('x', 25) !== 25) { fehler++; console.log('✗ zahlOder'); }
if (Math.round(Z.abstand(0, 0, 3, 4)) !== 5) { fehler++; console.log('✗ abstand'); }
console.log(fehler ? `${fehler} Fehler` : 'Alle Fälle bestanden');
process.exit(fehler ? 1 : 0);
