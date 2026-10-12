'use strict';
(() => {
  const data = window.GOKART_DATEN;
  const $ = id => document.getElementById(id);
  const results = $('treffer'), search = $('suche'), area = $('flaeche');
  if (!data || !Array.isArray(data.taxa)) {
    $('status').textContent = 'Keine Pflanzendaten vorhanden. Bitte zuerst python3 export_daten.py ausführen.';
    return;
  }
  const normalize = s => String(s || '').toLocaleLowerCase('de')
    .replace(/ß/g, 'ss').normalize('NFD').replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9]/g, '');
  const taxa = new Map(data.taxa.map(t => [Number(t.taxon_id), t]));
  const entries = new Map();
  const add = (id, value, kind) => {
    const key = normalize(value);
    if (!key || !taxa.has(Number(id))) return;
    if (!entries.has(Number(id))) entries.set(Number(id), new Map());
    const m = entries.get(Number(id));
    const old = m.get(key);
    if (!old || kind > old.kind) m.set(key, {key, kind, original:String(value)});
  };
  for (const t of data.taxa) {
    add(t.taxon_id, t.deutscher_name, 5);
    add(t.taxon_id, t.wissenschaftlicher_name, 4);
  }
  for (const n of data.namen) add(n.taxon_id, n.wissenschaftlicher_name, 3);
  for (const a of data.aliases) add(a.taxon_id, a.synonym, 5);
  const storageKey = 'gokart_test_flaechen_v1';
  let records = [];
  try { records = JSON.parse(localStorage.getItem(storageKey) || '[]'); if (!Array.isArray(records)) records=[]; } catch { records=[]; }
  let selected = null;
  function similarity(a,b) {
    if (!a || !b) return 0;
    if (a===b) return 1;
    // Damerau-ähnliche Toleranz via Levenshtein, nur für die besten Kandidaten.
    let prev = Array.from({length:b.length+1}, (_,i)=>i);
    for (let i=1;i<=a.length;i++) {
      const row=[i];
      for (let j=1;j<=b.length;j++) row[j]=Math.min(row[j-1]+1,prev[j]+1,prev[j-1]+(a[i-1]===b[j-1]?0:1));
      prev=row;
    }
    return 1-prev[b.length]/Math.max(a.length,b.length);
  }
  function rank(q, e) {
    if (q===e.key) return 1000 + e.kind;
    if (e.key.startsWith(q)) return 810 + Math.min(q.length/e.key.length,1)*100 + e.kind;
    if (e.key.includes(q)) return 680 + Math.min(q.length/e.key.length,1)*100 + e.kind;
    return similarity(q,e.key)*610 + e.kind;
  }
  function find(query) {
    const q=normalize(query); if (!q) return [];
    const ranked=[];
    for (const [id, variants] of entries) {
      let best=-1;
      for (const e of variants.values()) best=Math.max(best,rank(q,e));
      const t=taxa.get(id);
      if (best>150) ranked.push({id,t,score:best});
    }
    ranked.sort((a,b)=>b.score-a.score || String(a.t.deutscher_name||a.t.wissenschaftlicher_name).localeCompare(String(b.t.deutscher_name||b.t.wissenschaftlicher_name),'de'));
    // Bei einem eindeutigen Treffer: taxonomisch ähnliche Arten sinnvoll ergänzen.
    if (ranked.length && ranked[0].score>=1000 && ranked[0].t.wissenschaftlicher_name) {
      const genus=ranked[0].t.wissenschaftlicher_name.split(' ')[0];
      for (const r of ranked.slice(1)) {
        if (r.t.wissenschaftlicher_name?.startsWith(genus+' ')) r.score=Math.max(r.score,740);
      }
      ranked.sort((a,b)=>b.score-a.score || String(a.t.deutscher_name||'').localeCompare(String(b.t.deutscher_name||''),'de'));
    }
    return ranked.slice(0,5);
  }
  function render() {
    selected=null; $('hinzufuegen').disabled=true; results.replaceChildren();
    const q=search.value.trim(); if (!q) { $('status').textContent='Pflanzennamen eingeben.'; return; }
    const found=find(q);
    $('status').textContent=found.length ? `${found.length} Vorschläge – bitte eine Art auswählen.` : 'Keine passenden Pflanzen gefunden.';
    for (const r of found) {
      const btn=document.createElement('button');btn.type='button';btn.className='result';btn.setAttribute('role','option');btn.setAttribute('aria-selected','false');
      const name=document.createElement('strong');name.textContent=r.t.deutscher_name || r.t.wissenschaftlicher_name;
      const details=document.createElement('small');details.textContent=`${r.t.wissenschaftlicher_name || '—'} · Taxon-ID ${r.id} · ${r.t.rang || 'Taxon'}`;
      btn.append(name,details);btn.addEventListener('click',()=>{
        for(const el of results.children) el.setAttribute('aria-selected','false');
        btn.setAttribute('aria-selected','true');selected=r;$('hinzufuegen').disabled=false;
      });results.append(btn);
    }
  }
  function renderRecords(){
    const box=$('erfasst');box.replaceChildren();
    if (!records.length) {const p=document.createElement('p');p.className='hint';p.textContent='Noch keine Testeinträge.';box.append(p);return;}
    for (const r of records.slice().reverse()) {
      const div=document.createElement('div');div.className='entry';
      div.textContent=`Fläche ${r.flaeche_id} · ${r.deutscher_name || r.wissenschaftlicher_name} (${r.wissenschaftlicher_name}) · ID ${r.taxon_id}`;box.append(div);
    }
  }
  $('hinzufuegen').addEventListener('click',()=>{
    if (!selected) return;
    const flaeche=area.value.trim();
    if (!flaeche) {alert('Bitte zuerst eine Flächenkennung eingeben.');area.focus();return;}
    records.push({flaeche_id:flaeche,taxon_id:selected.id,deutscher_name:selected.t.deutscher_name,wissenschaftlicher_name:selected.t.wissenschaftlicher_name,original_spracheingabe:search.value,erfasst_am:new Date().toISOString()});
    localStorage.setItem(storageKey,JSON.stringify(records));renderRecords();
  });
  $('leeren').addEventListener('click',()=>{search.value='';render();search.focus();});
  $('export').addEventListener('click',()=>{
    const blob=new Blob([JSON.stringify(records,null,2)],{type:'application/json'});
    const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download='gokart_test_erfassungen.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1500);
  });
  let timer;search.addEventListener('input',()=>{clearTimeout(timer);timer=setTimeout(render,120);});
  $('status').textContent=`${taxa.size.toLocaleString('de-DE')} Taxa geladen – bereit zur Suche.`;
  renderRecords();
})();
