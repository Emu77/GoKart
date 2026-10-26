// Aufruf: node qfield/test/test_biotop.js   (liest die Kataloge aus qgis_plugin/gokart_desktop/biotope_kataloge)
const fs = require('fs'), vm = require('vm'), path = require('path');
const code = fs.readFileSync(path.join(__dirname, '../../qfield_plugin/gokart_biotop.js'), 'utf8').replace('.pragma library', '');
const S = {}; vm.createContext(S); vm.runInContext(code, S);

function katalog(datei) {
  const zeilen = fs.readFileSync(datei, 'utf8').split('\n').filter(z => z && !z.startsWith('#'));
  const kopf = zeilen.shift().split(';');
  return zeilen.map(z => Object.fromEntries(z.split(';').map((w, i) => [kopf[i], w])))
               .map(r => ({ ...r, ebene: Number(r.ebene) || 0 }));
}
const ordner = path.join(__dirname, '../../qgis_plugin/gokart_desktop/biotope_kataloge');
const faelle = {
  SH: [['WMy', 'WMy'], ['wmy', 'WMy'], ['we em ypsilon', 'WMy'], ['W M Y', 'WMy'], ['Knick', 'HWy'],
       ['typischer Knick', 'HWy'], ['Erlenbruch', 'WBe'], ['Erlen Bruchwald', 'WBe'], ['Flatterbinsen', 'NSf'],
       ['Brombeerflur', 'RHr'], ['Brombeer Flur', 'RHr'], ['Bromberflur', 'RHr'], ['Intensivacker', 'AAy'],
       ['Sandmagerrasen', 'TRy'], ['Graudüne', 'KDg'], ['Neophytenflur', 'RHx'], ['Rasenfläche', 'SGr']],
  NI: [['WCN', 'WCN'], ['Erlen-Bruchwald', 'WA'], ['Fichtenforst', 'WZF'], ['Douglasie', 'WZD'], ['ULN', 'ULN']],
  SH_2003: [['WBe', 'WBe'], ['we be e', 'WBe'], ['Hochmoor', 'MHh'], ['Straßenverkehrsfläche', 'SVs']],
  HH_1999: [['WBE', 'WBE'], ['Kiefernforst', 'WZK'], ['Weidengebüsch Feuchtstandorte', 'HF']],
  BE_2002: [['01101', '01101'], ['FQU', '01101'], ['null eins eins null eins', '01101'], ['Dachbegrünung', '12910']],
  BB_2002: [['Sturzquelle', '0110x1']],
  SN_2003: [['Hohlweg', 'YH'], ['MNB', 'MNB'], ['Streuobstwiese', 'BS']],
};
let ok = 0, n = 0;
for (const [sch, liste] of Object.entries(faelle)) {
  const idx = S.neuerIndex();
  katalog(path.join(ordner, sch + '.csv')).forEach(t => S.typHinzufuegen(idx, t));
  for (const [q, erwartet] of liste) {
    n++;
    const r = S.suchen(idx, q, 6);
    const pos = r.findIndex(x => x.typ.code === erwartet);
    if (pos >= 0) ok++;
    console.log(`${pos === 0 ? 'OK ' : pos > 0 ? 'OK~' : 'XX '} ${sch} ${q.padEnd(18)} → ${r.slice(0, 3).map(x => x.typ.code + ' ' + x.typ.name).join(' | ')}`);
  }
}
console.log(`\n${ok}/${n} gefunden`);
process.exit(ok === n ? 0 : 1);
