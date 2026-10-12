// Aufruf: python3 test/testdaten_export.py qfield_projekt/gokart.gpkg testdaten.json && node test/test_suche.js testdaten.json
const fs = require('fs'), vm = require('vm');
const code = fs.readFileSync(__dirname + '/../plugin/gokart_suche.js', 'utf8').replace('.pragma library', '');
const S = {}; vm.createContext(S); vm.runInContext(code, S);
const d = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
let t0 = Date.now();
const idx = S.neuerIndex();
d.taxa.forEach(t => S.taxonHinzufuegen(idx, t));
d.namen.forEach(n => S.nameHinzufuegen(idx, n[0], n[1], n[2], n[3]));
console.log('Index:', idx.eintraege.length, 'Einträge in', Date.now() - t0, 'ms');
const faelle = [
  ['Stiel-Eiche', 'Quercus robur'], ['stieleiche', 'Quercus robur'], ['Stiel Eiche', 'Quercus robur'],
  ['Stil Eiche', 'Quercus robur'], ['Quercus robur', 'Quercus robur'], ['kwerkus robur', 'Quercus robur'],
  ['Spitzahorn', 'Acer platanoides'], ['Feldahorn', 'Acer campestre'], ['Acer campestre', 'Acer campestre'],
  ['Brennnessel', null], ['Große Brennnessel', 'Urtica dioica'], ['Gänseblümchen', 'Bellis perennis'],
  ['gänse blümchen', 'Bellis perennis'], ['Löwenzahn', null], ['Schafgarbe', null], ['Rot-Klee', 'Trifolium pratense'],
  ['Rotklee', 'Trifolium pratense'], ['Weißklee', 'Trifolium repens'], ['Spitz Wegerich', 'Plantago lanceolata'],
  ['Glatthafer', 'Arrhenatherum elatius'], ['Schwarznessel', null], ['Ruten-Hasenohr', null], ['Hänge Birke', 'Betula pendula'],
  ['Rot Buche', 'Fagus sylvatica'], ['Sumpfdotterblume', 'Caltha palustris'], ['Sumpf Dotter Blume', 'Caltha palustris'],
  ['Spitzwegerisch', 'Plantago lanceolata'], ['Schaf garbe', null], ['Löwen zahn', null], ['Breitwegerich', null], ['Knaul Gras', 'Dactylis glomerata agg.'], ['Wiesen Rispengras', 'Poa pratensis agg.'],
];
let ok = 0, ms = 0;
for (const [q, erwartet] of faelle) {
  const a = Date.now(); const r = S.suchen(idx, q, 5); ms += Date.now() - a;
  const namen = r.map(x => `${x.taxon.deutscher_name || '-'} [${x.taxon.wissenschaftlicher_name}${x.exakt ? ',exakt' : ''}]`);
  const hit = erwartet === null || r.some(x => x.taxon.wissenschaftlicher_name === erwartet);
  const erster = erwartet && r[0] && r[0].taxon.wissenschaftlicher_name === erwartet;
  if (hit) ok++;
  console.log(`${hit ? (erster || !erwartet ? 'OK ' : 'OK~') : 'XX '} ${q.padEnd(20)} → ${namen.join(' | ')}`);
}
console.log(`\n${ok}/${faelle.length} gefunden, Ø ${(ms / faelle.length).toFixed(1)} ms/Suche`);
