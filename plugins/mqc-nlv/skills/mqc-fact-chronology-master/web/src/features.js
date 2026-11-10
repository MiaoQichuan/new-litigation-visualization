
/* ===== 疑似重复：拿不准是不是同一件事的，交律师「分开 / 合并为一」 ===== */
function rawIv(f){ const ivs=f.recs.filter(r=>!r.sus&&r.p!=='none'&&docVisible(r.d)).map(recIv).filter(Boolean); if(!ivs.length) return null; return [Math.min(...ivs.map(i=>i[0])),Math.max(...ivs.map(i=>i[1]))]; }
function dupGroups(all){
  const fs=FACTS.filter(f=>all||f.recs.some(r=>docVisible(r.d)));
  const pairs=[];
  for(let i=0;i<fs.length;i++) for(let j=i+1;j<fs.length;j++){
    const a=fs[i], b=fs[j]; if(a.t!==b.t || (a.state||'occ')!==(b.state||'occ') || (a.role||'')!==(b.role||'')) continue;
    const ia=rawIv(a), ib=rawIv(b); if(!ia||!ib) continue;
    if(Math.max(ia[0],ib[0])-Math.min(ia[1],ib[1])>3) continue;
    const va=new Set(a.recs.filter(r=>r.amt!=null).map(r=>+r.amt)), vb=new Set(b.recs.filter(r=>r.amt!=null).map(r=>+r.amt));
    if(!va.size||!vb.size||![...va].some(v=>vb.has(v))) continue;
    pairs.push([a.id,b.id,'类型、金额相同，日期相差不超过 3 天。']);
  }
  (CASE.dupCandidates||[]).forEach(p=>pairs.push(p));
  const par={}; const fnd=x=>par[x]&&par[x]!==x?(par[x]=fnd(par[x])):x;
  const why={};
  pairs.forEach(([a,b,w])=>{ if(!FACT[a]||!FACT[b]) return; par[a]=par[a]||a; par[b]=par[b]||b; par[fnd(a)]=fnd(b); why[a]=w; });
  const groups={}; Object.keys(par).forEach(x=>{ const r=fnd(x); (groups[r]=groups[r]||[]).push(x); });
  return Object.values(groups).map(ids=>{ ids.sort((x,y)=>FACTS.indexOf(FACT[x])-FACTS.indexOf(FACT[y])); return {id:'D:'+ids.join('+'),fids:ids,why:ids.map(x=>why[x]).find(Boolean)||'可能是同一件事。'}; });
}
function effFacts(){
  const merged=Object.entries(S.dupRes||{}).filter(([,v])=>v==='merge').map(([id])=>id.slice(2).split('+'));
  if(!merged.length) return FACTS;
  const drop=new Set(), extra={};
  merged.forEach(ids=>{ const [h,...rest]=ids; if(!FACT[h]) return; rest.forEach(x=>{ if(FACT[x]){ drop.add(x); (extra[h]=extra[h]||[]).push(...FACT[x].recs); } }); });
  return FACTS.filter(f=>!drop.has(f.id)).map(f=>extra[f.id]?{...f,recs:[...f.recs,...extra[f.id]]}:f);
}

/* ===== 数字对不上：大写与小写金额不一致；以及 AI 记下的算术说明 ===== */
function cnMoney(t){
  const dg={零:0,壹:1,贰:2,叁:3,肆:4,伍:5,陆:6,柒:7,捌:8,玖:9}, un={拾:10,佰:100,仟:1000};
  let total=0, sec=0, num=0;
  for(const ch of t){
    if(ch in dg) num=dg[ch];
    else if(ch in un){ sec+=(num||1)*un[ch]; num=0; }
    else if(ch==='万'){ total+=(sec+num)*1e4; sec=0; num=0; }
    else if(ch==='亿'){ total=(total+sec+num)*1e8; sec=0; num=0; }
  }
  return total+sec+num;
}
function arithItems(){
  const out=[];
  DOCS.filter(d=>docVisible(d.id)).forEach(d=>d.lines.forEach((l,i)=>{
    const up=l.match(/([零壹贰叁肆伍陆柒捌玖拾佰仟万亿]{2,})(?:元|圆)/), lo=l.match(/[¥￥]\s?([\d,]+(?:\.\d+)?)|([\d,]{3,}(?:\.\d+)?)\s?元/);
    if(!up||!lo) return;
    const a=cnMoney(up[1]), b=+String(lo[1]||lo[2]).replace(/,/g,'');
    if(a>0 && b>0 && Math.abs(a-b)>0.005) out.push({id:'R:'+d.id+':'+i,d:d.id,loc:`第 ${i} 行`,q:l.replace(/^#/,''),title:`${docShort(d.id)}：大写金额与小写金额不一致`,
      why:`大写「${up[1]}元」合 ${a.toLocaleString('zh-CN')} 元，小写为 ${b.toLocaleString('zh-CN')} 元，相差 ${Math.abs(a-b).toLocaleString('zh-CN')} 元。`});
  }));
  (CASE.arith||[]).filter(a=>docVisible(a.d)).forEach(a=>out.push({...a,id:'R:'+a.id}));
  return out;
}

/* ===== 事实经过：按线索把全部事实讲成一段中立的叙述，每句注出处、可点回原文 ===== */
function cite(d){ return DOC[d].evno||d; }
function nameMode(text){
  const mode=S.nName||'name'; if(mode==='name') return text;
  /* 「被告李四」这类诉讼地位加姓名的写法整体替换，免得变成「被告被告一」 */
  const RP=['被上诉人','上诉人','被申请人','申请人','第三人','原告','被告','证人'];
  const ps=(CASE.parties||[]).map((p,i)=>({i,names:(n=>[...n,...RP.flatMap(r=>n.map(x=>r+x))])([p.name,p.short,...(p.alias||[])].filter(Boolean)).sort((a,b)=>b.length-a.length),
    to: mode==='side' ? (i===(S.nUs||0)?'我方':(p.role||'').replace(/（.*?）/g,'')) : p.role}));
  /* 材料名里带当事人姓名的（如「倪新山VS赵蕾……研究报告」），改称其文书类型（如「再审申请研究报告」），
     既不露真名，也不出现「据我方与被告一……报告陈述」这种别扭的说法；文书类型里也带姓名的，仍按称谓替换 */
  const allN=ps.flatMap(p=>p.names);
  const dirty=t=>t&&allN.some(x=>t.includes(x));
  const ren=DOCS.flatMap(d=>{ const clean=[d.sub,d.name].find(t=>t&&!dirty(t)); return clean?[...new Set([docShort(d.id),d.name,d.sub])].filter(dirty).map(t=>[t,clean]):[]; }).sort((a,b)=>b[0].length-a[0].length);
  return text.split(/(「[^」]*」)/).map(seg=>{ if(seg.startsWith('「')) return seg; ren.forEach(([n,sub])=>{ seg=seg.split(n).join(sub); }); ps.forEach(p=>p.names.forEach(n=>{ seg=seg.split(n).join(p.to); })); return seg; }).join('');
}
function ivText(r){ const iv=recIv(r); if(r.p==='day') return fmtD(iv[0]); if(r.p==='month') return fmtM(iv[0]); if(r.p==='range') return `${fmtD(iv[0])}至${fmtD(iv[1])}`; return `约${fmtD(iv[0])}至${fmtD(iv[1])}`; }
function ivDot(r){ const p=n=>String(n).padStart(2,'0'), f=n=>{ const d=fromDn(n); return `${d.getUTCFullYear()}.${p(d.getUTCMonth()+1)}.${p(d.getUTCDate())}`; }, iv=recIv(r); if(r.p==='day') return f(iv[0]); if(r.p==='month') return f(iv[0]).slice(0,7); if(r.p==='range') return `${f(iv[0])}—${f(iv[1])}`; return `约 ${f(iv[0])}—${f(iv[1])}`; }
function joinDocs(ds){ return [...new Set(ds.map(d=>docShort(d)))].join('、'); }
function narrSentence(e){
  const cites='（'+[...new Set(e.recs.map(r=>cite(r.d)))].join('、')+'）';
  const base=e.f.narr||e.title;
  const groupBy=(recs,key)=>{ const g=new Map(); recs.forEach(r=>{ const k=key(r); if(!g.has(k)) g.set(k,[]); g.get(k).push(r); }); return [...g.entries()]; };
  let s='';
  if(e.conflict){
    const parts=groupBy(e.strict,r=>recIv(r).join()).map(([,rs])=>`${joinDocs(rs.map(r=>r.d))}载为${ivText(rs[0])}`);
    s=`${base}，日期记载不一：${parts.join('；')}`;
  } else {
    let dt = e.undated ? '' : dateLabel(e).replace(' 至 ','至');
    if(e.est && !e.undated){ const r=e.dated.find(x=>x.inf); dt=`约${dt}（${INFER[r.inf].n}，据上下文推定）`; }
    const k=e.recs.every(r=>dKind(r.d)==='statement');
    if(k && e.f.t!=='filing') s=`据${joinDocs(e.recs.map(r=>r.d))}陈述，${dt?dt+'，':''}${base}`;
    else s=`${dt?dt+'，':''}${base}`;
    if(e.susOnly){ const r=e.recs[0]; s=`${base}（材料所载日期「${r.raw.replace(/（日期可疑.*?）/,'')}」不存在，日期待核）`; }
    if(e.adopted){ const others=e.wasConflict?groupBy(e.strict.filter(r=>r.rid!==e.adopted&&recIv(r).join()!==recIv(REC[e.adopted]).join()),r=>recIv(r).join()):[]; if(others.length) s+=`（另，${others.map(([,rs])=>`${joinDocs(rs.map(r=>r.d))}载为${ivText(rs[0])}`).join('；')}）`; }
  }
  if(e.amtConflict || (e.adopted && e.amtVals && e.amtVals.length>1)){
    const parts=groupBy(e.recs.filter(r=>r.amt!=null),r=>+r.amt).map(([v,rs])=>`${joinDocs(rs.map(r=>r.d))}载为${fmtAmt(v)}`);
    s+=`；金额记载不一：${parts.join('，')}`;
  }
  if(e.undated && !e.susOnly) s+='（时间未载明）';
  return s+cites+'。';
}
function narrThreads(){
  const keep=S.stage; S.stage=5; invalidate(); const evs=derive().slice(); S.stage=keep; invalidate(); derive();
  let th=(CASE.threads||[]).map(t=>({id:t.id,title:t.title,fids:new Set(t.facts)}));
  if(!th.length){ const by={}; evs.forEach(e=>{ (by[e.t]=by[e.t]||[]).push(e.f.id); }); th=TYPE_ORDER.filter(t=>by[t]).map(t=>({id:'ty-'+t,title:TYPES[t].n,fids:new Set(by[t])})); }
  const placed=new Set(); th.forEach(t=>t.fids.forEach(f=>placed.add(f)));
  const rest=evs.filter(e=>!placed.has(e.f.id)).map(e=>e.f.id); if(rest.length) th.push({id:'rest',title:'其他',fids:new Set(rest)});
  Object.entries(S.nMerge||{}).forEach(([from,to])=>{ const a=th.find(t=>t.id===from), b=th.find(t=>t.id===to); if(a&&b){ a.fids.forEach(f=>b.fids.add(f)); th=th.filter(t=>t!==a); } });
  if(S.nOrder){ const ord=S.nOrder; th.sort((a,b)=>(ord.indexOf(a.id)+1||99)-(ord.indexOf(b.id)+1||99)); }
  const gs=gaps(evs).filter(g=>g[1]-g[0]>=120); const used=new Set();
  return th.map(t=>{
    const es=evs.filter(e=>t.fids.has(e.f.id)); const dated=es.filter(e=>!e.undated).sort((a,b)=>a.sortKey-b.sortKey), und=es.filter(e=>e.undated);
    const items=[];
    dated.forEach((e,i)=>{ if(i>0){ const p=dated[i-1]; gs.forEach((g,gi)=>{ if(!used.has(gi) && g[0]>=p.sortKey && g[1]<=e.sortKey){ used.add(gi); items.push({gap:1,id:'gap'+gi,text:`${fmtM(g[0])}至${fmtM(g[1])}，现有材料未见记载。`}); } }); } items.push({e}); });
    und.forEach(e=>items.push({e,und:1}));
    return {id:t.id,title:(S.nTitle||{})[t.id]||t.title,items};
  }).filter(t=>t.items.length);
}
function narrHTML(text,e){
  /* 把一句叙述排成带层次的文字：句首日期加粗、记载不一处浅琥珀底、陈述来源用次要色、出处为小标签 */
  let h=esc(text);
  h=h.replace(/（([^（）]*)）。$/,(m,c)=>'<span class="nend"><span class="ncites">'+c.split('、').map(x=>{ const d=DOCS.find(dd=>(dd.evno||dd.id)===x); const rid=d&&e?((e.recs.find(r=>r.d===d.id)||{}).rid||''):''; return d?`<button class="ncite" title="${esc(d.sub)}" onclick="event.stopPropagation();openDoc('${d.id}','${rid}')">${esc(x)}</button>`:`<span class="ncite">${esc(x)}</span>`; }).join('')+'</span>。</span>');
  h=h.replace(/^(据[^，]*?陈述，)/,'<span class="nsrc">$1</span>');
  h=h.replace(/((?:<\/span>)?)(约?\d{4}年\d{1,2}月(?:\d{1,2}日)?(?:至(?:\d{4}年)?\d{1,2}月\d{1,2}日)?)((?:（[^）]*）)?)，/, (m,pre,d,par)=>`${pre}<b class="ndate">${d}</b>${par?`<span class="ninf">${par}</span>`:''}，`);
  h=h.replace(/(日期|金额)记载不一：/g,'<span class="ndiff">$1记载不一</span>：');
  h=h.replace(/（时间未载明）/,'<span class="nund">时间未载明</span>');
  return h;
}
function drawNarr(){
  const host=$('#narr'); if(!host) return;
  const th=narrThreads(); const ed=S.nEdit||{};
  const nFacts=th.reduce((a,t)=>a+t.items.filter(i=>i.e).length,0);
  const nDocs=new Set(th.flatMap(t=>t.items.filter(i=>i.e).flatMap(i=>i.e.recs.map(r=>r.d)))).size;
  const span=t=>{ const d=t.items.filter(i=>i.e&&!i.e.undated).map(i=>i.e.sortKey); if(!d.length) return '时间未载明'; const a=Math.min(...d), b=Math.max(...d); return fmtM(a)===fmtM(b)?fmtM(a):`${fmtM(a)} — ${fmtM(b)}`; };
  const sent=(it)=>{
    if(it.gap) return `<span class="ngap"><span>${esc(it.text.replace(/。$/,''))}</span></span>`;
    const e=it.e, gen=nameMode(narrSentence(e)), k='n:'+e.id, edt=ed[k];
    const text=edt?nameMode(edt.text):gen, stale=edt && nameMode(edt.base)!==gen;
    return `<span class="ns ${S.selected===e.id?'on':''} ${edt?'edited':''}" data-k="${k}" onclick="selectEv('${e.id}',true)">${narrHTML(text,e)}${stale?'<span class="nstale" title="底稿已变动，此句可能过时">已过时</span>':''}<button class="nedit" title="修改这一句" onclick="event.stopPropagation();editSent('${k}','${e.id}')">${ICO.pen}</button></span>`;
  };
  const parties=(CASE.parties||[]);
  host.innerHTML=`<div class="nhead">
    <h2 class="ntitle">事实经过</h2>
    <div class="seg nview">${[['table','大事记表'],['prose','叙述']].map(([v,n])=>`<button class="${(S.nView||'table')===v?'on':''}" onclick="setNView('${v}')">${n}</button>`).join('')}</div>${narrModified()?`<button class="lnk nreset" onclick="resetThreads()">恢复线索原样</button>`:''}
    <span class="hsp"></span>
    <div class="nctl"><span class="lab">称谓</span><div class="seg nname">${[['name','姓名'],['role','诉讼地位'],['side',S.nName==='side'&&parties.length?`我方：${esc((parties[S.nUs||0]||{}).short||(parties[S.nUs||0]||{}).name||'')}`:'我方 / 对方']].map(([v,n])=>`<button class="${(S.nName||'name')===v?'on':''} ${v==='side'?'nside':''}" onclick="${v==='side'&&S.nName==='side'&&parties.length>1?'sidePop(event)':`S.nName='${v}';drawNarr()`}" title="${v==='side'?'再点一次可换「我方」是谁':''}">${n}</button>`).join('')}</div>
    <button class="btn sm" onclick="copyNarr()">复制文字</button><button class="btn sm dark" onclick="exportNarr()">${ICO.out}导出</button></div></div>
  <div class="nbody ${(S.nView||'table')==='table'?'tbl':''}">
   <nav class="ntoc"><div class="ntoc-h">线索</div>${th.map((t,ti)=>`<button onclick="document.getElementById('nt-${t.id}').scrollIntoView({behavior:'smooth',block:'start'})"><span class="num">${ti+1}</span><span class="tt">${esc(t.title)}</span><i class="num">${t.items.filter(x=>x.e).length}</i></button>`).join('')}</nav>
   ${(S.nView||'table')==='table'?narrTable(th):`<div class="nflow">${th.map((t,ti)=>`<section class="nstep" id="nt-${t.id}"><span class="nmk num">${ti+1}</span>
     <div class="nth"><h3 contenteditable="true" spellcheck="false" onblur="renameThread('${t.id}',this.textContent)" onkeydown="if(event.key==='Enter'){event.preventDefault();this.blur()}">${esc(t.title)}</h3><span class="nspan num">${span(t)} · ${t.items.filter(x=>x.e).length} 个事实</span>
     <span class="nops">${ti>0?`<button class="lnk" onclick="moveThread('${t.id}',-1)">上移</button>`:''}${ti<th.length-1?`<button class="lnk" onclick="moveThread('${t.id}',1)">下移</button>`:''}${ti>0?`<button class="lnk" onclick="mergeThread('${t.id}','${th[ti-1].id}')">并入上一条</button>`:''}</span></div>
     <p class="npara">${t.items.map(sent).join('')}</p></section>`).join('')}</div>`}
  </div>`;
}
/* 大事记表：照时间轴大师之外的大事记表大师（V4）的五列——序号、日期、事项、主要内容、备注；按线索分组 */
function chronRow(e){
  const p2=n=>String(n).padStart(2,'0');
  const cites=[...new Map(e.recs.map(r=>[r.d,r])).values()].map(r=>`<button class="ncite" title="${esc(DOC[r.d].sub)}" onclick="event.stopPropagation();openDoc('${r.d}','${r.rid}')">${esc(cite(r.d))}${r.loc?` · ${esc(r.loc)}`:''}</button>`).join('');
  const stmt=e.recs.every(r=>dKind(r.d)==='statement');
  const notes=[];
  if(e.conflict) notes.push('<span class="ndiff">日期记载不一</span>');
  if(e.amtConflict) notes.push('<span class="ndiff">金额记载不一</span>');
  if(e.adopted) notes.push(`<span class="tag blue">已采信 ${esc(cite(REC[e.adopted].d))}</span>`);
  if(stmt && e.f.t!=='filing') notes.push('<span class="tag amber">仅当事人陈述</span>');
  if(e.state==='agr') notes.push('<span class="tag out">约定</span>');
  if(e.est) notes.push('<span class="tag out">推定</span>');
  let content;
  if(e.conflict||e.amtConflict){ const g=new Map(); e.recs.forEach(r=>{ const k=r.d; if(!g.has(k)) g.set(k,r); });
    content=[...g.values()].map(r=>`<div class="cq"><span class="cqd">${esc(docShort(r.d))}</span>「${esc(r.q)}」</div>`).join(''); }
  else { const r=bestRec(e); content=`「${esc(r.q)}」${(r.qx||[]).map(x=>`<span class="cqx">「${esc(x)}」</span>`).join('')}`; }
  return `<tr class="${S.selected===e.id?'on':''}" onclick="selectEv('${e.id}',true)"><td class="cn num"></td><td class="cd num">${e.undated?'<span class="nund">时间未载明</span>':e.conflict?[...new Set(e.strict.map(r=>ivDot(r)))].map(x=>`<div class="cdv">${esc(x)}</div>`).join(''):esc(dot4(e))}</td>
    <td class="ci">${e.key?'<span class="star-s">★</span>':''}${esc(nameMode(e.f.narr?e.title:e.title))}</td><td class="cc">${nameMode(content)}</td><td class="cr">${notes.join('')}<div class="ccites">${cites}</div></td></tr>`;
}
function narrTable(th){
  let n=0;
  const body=th.map((t,ti)=>`<tr class="cg"><td colspan="5"><span class="nmk num">${ti+1}</span><b>${esc(t.title)}</b></td></tr>`+t.items.map(it=>it.gap?`<tr class="cgap"><td></td><td colspan="4">${esc(it.text.replace(/。$/,''))}</td></tr>`:chronRow(it.e).replace('<td class="cn num"></td>',`<td class="cn num">${++n}</td>`)).join('')).join('');
  return `<div class="ctwrap"><table class="chron"><colgroup><col style="width:52px"><col style="width:132px"><col style="width:22%"><col><col style="width:230px"></colgroup>
    <thead><tr><th>序号</th><th>日期</th><th>事项</th><th>主要内容</th><th>备注</th></tr></thead><tbody>${body}</tbody></table></div>`;
}
function renameThread(id,t){ t=t.trim(); if(!t) return drawNarr(); S.nTitle=S.nTitle||{}; if(t!==(S.nTitle[id]||'')){ S.nTitle[id]=t; logIt(null,'线索改名',t); } }
function moveThread(id,d){ const ids=narrThreads().map(t=>t.id); const i=ids.indexOf(id), j=i+d; if(j<0||j>=ids.length) return; [ids[i],ids[j]]=[ids[j],ids[i]]; S.nOrder=ids; logIt(null,'线索调序',''); drawNarr(); }
function mergeThread(from,to){ S.nMerge=S.nMerge||{}; S.nMerge[from]=to; logIt(null,'线索合并',''); drawNarr(); }
function editSent(k,eid){
  const el=document.querySelector(`.ns[data-k="${k}"]`); if(!el) return;
  const e=derive().find(x=>x.id===eid)||(()=>{ const kp=S.stage; S.stage=5; invalidate(); const r=derive().find(x=>x.id===eid); S.stage=kp; invalidate(); return r; })();
  const gen=narrSentence(e), cur=(S.nEdit||{})[k]?.text||gen;
  el.outerHTML=`<span class="ns editing"><textarea class="nta" id="nta">${esc(cur)}</textarea><span class="nbtns"><button class="btn sm dark" onclick="saveSent('${k}','${eid}')">保存</button><button class="btn sm" onclick="drawNarr()">取消</button>${(S.nEdit||{})[k]?`<button class="lnk" onclick="resetSent('${k}')">恢复生成的句子</button>`:''}</span><span class="sub">「」里的原文不能改。</span></span>`;
  const ta=$('#nta'); ta.focus(); ta.style.height=ta.scrollHeight+'px';
}
function saveSent(k,eid){
  const kp=S.stage; S.stage=5; invalidate(); const e=derive().find(x=>x.id===eid); S.stage=kp; invalidate();
  const gen=narrSentence(e), t=$('#nta').value.trim();
  const quotes=(gen.match(/「[^」]*」/g)||[]), lost=quotes.filter(q=>!t.includes(q));
  if(lost.length){ toast('原文引语不能改：'+lost[0]); return; }
  S.nEdit=S.nEdit||{}; S.nEdit[k]={text:t,base:gen}; logIt(e.f.id,'修改事实经过的一句',t.slice(0,30)); drawNarr();
}
function resetSent(k){ delete S.nEdit[k]; logIt(null,'恢复生成的句子',''); drawNarr(); }
function narrPlain(){
  const ed=S.nEdit||{};
  return narrThreads().map((t,i)=>`${'一二三四五六七八九十'[i]||(i+1)}、${t.title}\n`+t.items.map(it=>it.gap?it.text:nameMode((ed['n:'+it.e.id]||{}).text||narrSentence(it.e))).join('')).join('\n\n');
}
function chronPlain(){ let n=0; return ['序号\t日期\t事项\t主要内容\t备注'].concat(narrThreads().flatMap(t=>[`【${t.title}】`].concat(t.items.filter(i=>i.e).map(({e})=>{ const r=bestRec(e); const cont=(e.conflict||e.amtConflict)?[...new Map(e.recs.map(x=>[x.d,x])).values()].map(x=>`${docShort(x.d)}：「${x.q}」`).join('；'):`「${r.q}」`;
  const note=[e.conflict?'日期记载不一':'',e.amtConflict?'金额记载不一':'',e.recs.every(x=>dKind(x.d)==='statement')&&e.f.t!=='filing'?'仅当事人陈述':'',[...new Set(e.recs.map(x=>cite(x.d)))].join('、')].filter(Boolean).join('；');
  return [++n,e.undated?'时间未载明':dot4(e),nameMode(e.title),nameMode(cont),note].join('\t'); })))).join('\n'); }
function copyNarr(){ const t=(S.nView||'table')==='table'?chronPlain():narrPlain(); try{ navigator.clipboard.writeText(t).then(()=>toast('已复制事实经过'),()=>toast('复制失败')); }catch(e){ toast('复制失败'); } }
/* ===== 导出：页面上看得到的东西，原样带走 ===== */
let _dl=null; (async()=>{ try{ if(window.claude&&claude.use) _dl=await claude.use('downloads'); }catch(e){ _dl=null; } })();
async function saveFile(filename,data,mime){
  filename=filename.replace(/[\\/:*?"<>|]/g,'_');
  if(_dl){ try{ await _dl.save({filename,data}); toast('已保存：'+filename); return true; }
    catch(e){ const c=e&&e.code; if(c==='declined'){ toast('已取消保存'); return false; } if(c==='rate_limited'){ toast('已有一个保存确认未处理，请稍后再试'); return false; } } }
  try{ const a=document.createElement('a'); a.href=URL.createObjectURL(data instanceof Blob?data:new Blob([data],{type:mime})); a.download=filename; document.body.appendChild(a); a.click(); a.remove(); toast('已下载：'+filename); return true; }
  catch(e){ toast('下载失败'); return false; }
}
function dot4(e){
  const p=n=>String(n).padStart(2,'0'), f=n=>{ const d=fromDn(n); return `${d.getUTCFullYear()}.${p(d.getUTCMonth()+1)}.${p(d.getUTCDate())}`; }, fm=n=>{ const d=fromDn(n); return `${d.getUTCFullYear()}.${p(d.getUTCMonth()+1)}`; };
  const m=e.main; if(!m) return '日期记载不一';
  if(e.conflict&&e.kind==='range') return f(m.lo)+' 起';
  if(m.p==='day') return (e.est?'约 ':'')+f(m.lo); if(m.p==='month') return fm(m.lo); if(m.p==='approx') return '约 '+f(m.lo);
  if(m.p==='range'){ const a=fromDn(m.lo), b=fromDn(m.hi); return f(m.lo)+'—'+(a.getUTCFullYear()===b.getUTCFullYear()?`${p(b.getUTCMonth()+1)}.${p(b.getUTCDate())}`:f(m.hi)); }
  if(m.p==='arange') return fm(m.lo)===fm(m.hi)?'约 '+fm(m.lo):'约 '+fm(m.lo)+'—'+fm(m.hi);
  return '';
}
const fname=x=>`${CASE.title||'案件看板'}-${x}`;
function exportPop(ev){
  const hasTL=!!$('#tlsvg');
  pop(ev,`<h4>导出</h4>
    <button class="mi" onclick="closePops();exportTL('png')">时间线图（PNG 图片）</button>
    <button class="mi" onclick="closePops();exportTL('svg')">时间线图（SVG 矢量图）</button>
    <button class="mi" onclick="closePops();exportFacts()">事实表（Excel 可打开）</button>
    <button class="mi" onclick="closePops();exportNarr('table')">大事记表（Word 可打开）</button>
    <button class="mi" onclick="closePops();exportNarr('prose')">事实经过叙述（Word 可打开）</button>
    <div class="msep"></div>
    <button class="mi" onclick="closePops();exportBase()">底稿（JSON）</button>
    <button class="mi" onclick="closePops();window.print()">打印当前页面</button>`,236);
}
function tlSVG(){
  const src=$('#tlsvg'); if(!src) return null; const c=src.cloneNode(true);
  const w=+src.getAttribute('width'), h=+src.getAttribute('height');
  c.setAttribute('xmlns','http://www.w3.org/2000/svg'); c.removeAttribute('id');
  c.setAttribute('style',`font-family:-apple-system,"PingFang SC","Microsoft YaHei","Noto Sans CJK SC",sans-serif;font-size:12px`);
  c.insertAdjacentHTML('afterbegin',`<rect width="${w}" height="${h}" fill="#fff"/>`);
  c.querySelectorAll('.mk').forEach(m=>{ m.classList.remove('linkmk'); });
  return {svg:new XMLSerializer().serializeToString(c),w,h};
}
function exportTL(kind){
  if(!$('#tlsvg')){ S.tab='tl'; render(); }
  const t=tlSVG(); if(!t){ toast('先回到时间线'); return; }
  const tag=rangeLabel().replace(/^全部 · /,'').replace(/ /g,'');
  if(kind==='svg'){ saveFile(fname(`时间线（${tag}）.svg`),t.svg,'image/svg+xml'); return; }
  const img=new Image(), k=2; img.onload=()=>{ const cv=document.createElement('canvas'); cv.width=t.w*k; cv.height=t.h*k; const g=cv.getContext('2d'); g.scale(k,k); g.drawImage(img,0,0);
    cv.toBlob(b=>saveFile(fname(`时间线（${tag}）.png`),b,'image/png'),'image/png'); };
  img.onerror=()=>toast('图片生成失败，可改用 SVG'); img.src='data:image/svg+xml;charset=utf-8,'+encodeURIComponent(t.svg);
}
function exportFacts(){
  const rows=(TL.tableRows&&TL.tableRows.length?TL.tableRows:visibleFacts());
  const cell=v=>`"${String(v==null?'':v).replace(/"/g,'""')}"`;
  const lines=[['日期','事实','类型','来源','证据种类','状态','原文'].map(cell).join(',')];
  rows.forEach(e=>{ const ds=[...new Set(e.recs.map(r=>r.d))];
    lines.push([e.undated?'时间未载明':dot4(e), e.title, TYPES[e.t]?TYPES[e.t].n:'', ds.map(d=>DOC[d].evno||d).join('、'), [...new Set(ds.map(d=>KIND[dKind(d)].n))].join('、'),
      e.rev==='done'?'已确认':'待确认', e.recs.map(r=>`${DOC[r.d].evno||r.d}：${r.q}`).join('\n')].map(cell).join(',')); });
  saveFile(fname('事实表.csv'),'﻿'+lines.join('\r\n'),'text/csv');
}
function exportNarr(view){
  view=view||S.nView||'table';
  const body=view==='table' ? `<table><thead><tr><th>序号</th><th>日期</th><th>事项</th><th>主要内容</th><th>备注</th></tr></thead><tbody>${chronPlain().split('\n').slice(1).map(l=>l.startsWith('【')?`<tr class="g"><td colspan="5">${esc(l.replace(/[【】]/g,''))}</td></tr>`:`<tr>${l.split('\t').map(c=>`<td>${esc(c)}</td>`).join('')}</tr>`).join('')}</tbody></table>`
    : narrPlain().split('\n\n').map(p=>{ const [h,...r]=p.split('\n'); return `<h2>${esc(h)}</h2><p>${esc(r.join(''))}</p>`; }).join('');
  const html=`<html xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:w="urn:schemas-microsoft-com:office:word"><head><meta charset="utf-8"><title>${esc(CASE.title)}</title><style>body{font:10.5pt/1.8 "SimSun","Songti SC",serif}h1{font:bold 16pt "SimHei","Heiti SC",sans-serif;text-align:center}h2{font:bold 12pt "SimHei","Heiti SC",sans-serif;margin:14pt 0 4pt}p{text-indent:2em;margin:0 0 8pt}table{border-collapse:collapse;width:100%}td,th{border:.5pt solid #000;padding:3pt 5pt;vertical-align:top;font-size:10pt}th{background:#eee}tr.g td{font-weight:bold;background:#f5f5f5}</style></head><body><h1>${esc(nameMode(CASE.title))}</h1><h1 style="font-size:13pt">${view==='table'?'大事记表':'事实经过'}</h1>${body}</body></html>`;
  saveFile(fname(view==='table'?'大事记表.doc':'事实经过.doc'),html,'application/msword');
}

/* ===== 概览条：拖边缘缩放、拖框平移、在空白处拖出一段、点年份选整年、双击回到全部 ===== */
function drawMini(evs){
  const host=$('#mini'); if(!host) return;
  const W=TL.W, PW=TL.PW, H=34, BH=16, X=d=>LW+(d-EXT[0])/(EXT[1]-EXT[0])*PW, D=x=>EXT[0]+(x-LW)/PW*(EXT[1]-EXT[0]);
  const bins={}, step=7; evs.filter(e=>!e.undated).forEach(e=>{ const b=Math.floor((e.sortKey-EXT[0])/step); bins[b]=(bins[b]||0)+1; });
  const mx=Math.max(1,...Object.values(bins));
  const full=S.t0<=EXT[0]+0.5 && S.t1>=EXT[1]-0.5;
  let s=`<svg width="${W}" height="${H+BH+4}" id="minisvg" style="display:block;user-select:none"><defs><pattern id="hatch2" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="7" stroke="#CFCDC6" stroke-width="1"/></pattern></defs>`;
  const p2=n=>String(n).padStart(2,'0'), ym=n=>{ const d=fromDn(n); return `${d.getUTCFullYear()}.${p2(d.getUTCMonth()+1)}`; };

  /* 左侧留给「泳道」按钮；当前时段写在工具条上 */
  s+=`<rect x="${LW}" y="1" width="${PW}" height="${H}" rx="3" fill="#ECEBE7" data-act="strip"/>`;
  gaps(evs).forEach(g=>{ s+=`<rect x="${X(g[0])}" y="1" width="${X(g[1])-X(g[0])}" height="${H}" fill="url(#hatch2)" pointer-events="none"/>`; });
  const bw=Math.max(2.2,PW/((EXT[1]-EXT[0])/step)-1.4);
  for(const [b,n] of Object.entries(bins)){ const x=X(EXT[0]+b*step)+.7, h=Math.max(4,n/mx*(H-8)); s+=`<rect x="${x}" y="${H+1-h}" width="${bw}" height="${h}" fill="#9A9FA0" pointer-events="none"/>`; }
  derive().filter(e=>e.conflict&&e.band).forEach(e=>{ s+=`<circle cx="${X((e.band.lo+e.band.hi)/2)}" cy="6" r="2.4" fill="#F2A50C" pointer-events="none"/>`; });
  const a=Math.max(LW,X(S.t0)), b=Math.min(LW+PW,X(S.t1));
  s+=`<rect id="mwin" x="${a+.8}" y="1.8" width="${Math.max(8,b-a-1.6)}" height="${H-1.6}" rx="3.5" fill="rgba(29,29,31,.06)" stroke="#6E6E73" stroke-width="1.4" style="cursor:move"/>`;
  const grip=(x,h)=>`<g data-h="${h}" style="cursor:ew-resize"><rect x="${x-6}" y="1" width="12" height="${H}" fill="transparent"/><rect x="${x-3}" y="${H/2-8}" width="6" height="16" rx="3" fill="#FFFFFF" stroke="#6E6E73" stroke-width="1.1" pointer-events="none"/><path d="M${x-1} ${H/2-4} V${H/2+4} M${x+1} ${H/2-4} V${H/2+4}" stroke="#86868B" stroke-width=".9" pointer-events="none"/></g>`;
  s+=grip(a+1.5,'l')+grip(b-1.5,'r');
  /* 年份：点一下选整年；整年都在显示范围内的年份加深 */
  s+=`<rect x="${LW}" y="${H+3}" width="${PW}" height="${BH}" fill="#F1F0EC"/>`;
  const y0=fromDn(EXT[0]).getUTCFullYear(), y1=fromDn(EXT[1]).getUTCFullYear();
  for(let y=y0;y<=y1;y++){
    const ja=dn(`${y}-01-01`), jb=dn(`${y+1}-01-01`), xa=X(Math.max(ja,EXT[0])), xb=X(Math.min(jb,EXT[1]));
    if(y>y0) s+=`<line x1="${X(ja)}" x2="${X(ja)}" y1="${H+3}" y2="${H+3+BH}" stroke="#DDDBD4"/>`;
    if(xb-xa<26) continue;
    const on=!full && S.t0<=ja+1 && S.t1>=jb-1;
    s+=`<g data-year="${y}" style="cursor:pointer"><rect x="${xa}" y="${H+3}" width="${xb-xa}" height="${BH}" fill="${on?'#E4E4E8':'transparent'}"/><text x="${(xa+xb)/2}" y="${H+15}" text-anchor="middle" font-size="11" font-weight="${on?600:400}" fill="${on?'#1D1D1F':'#6E6E73'}" class="num" pointer-events="none">${y}</text></g>`;
  }
  s+='</svg>';
  host.innerHTML=s;
  const svg=$('#minisvg');
  svg.ondblclick=()=>{ fit(); };
  svg.onmousedown=ev=>{
    const r=svg.getBoundingClientRect(), mx0=ev.clientX-r.left, t0=S.t0, t1=S.t1, k=(EXT[1]-EXT[0])/PW;
    const tgt=ev.target.closest('[data-h],[data-year],[data-act],#mwin'); if(!tgt) return;
    ev.preventDefault();
    if(tgt.dataset.act==='all'){ fit(); return; }
    if(tgt.dataset.year){ const y=+tgt.dataset.year; S.t0=Math.max(EXT[0],dn(`${y}-01-01`)); S.t1=Math.min(EXT[1],dn(`${y+1}-01-01`)); clampView(); drawTimeline(); return; }
    const h=tgt.dataset.h;
    if(tgt.dataset.act==='strip' || (tgt.id==='mwin' && full)){
      let moved=false;
      const move=e2=>{ const x=e2.clientX-r.left; if(Math.abs(x-mx0)<4 && !moved) return; moved=true;
        const lo=D(Math.min(x,mx0)), hi=D(Math.max(x,mx0)); S.t0=Math.max(EXT[0],lo); S.t1=Math.min(EXT[1],Math.max(hi,lo+14)); clampView(); drawSoon(); };
      const up=()=>{ removeEventListener('mousemove',move); removeEventListener('mouseup',up);
        if(!moved){ const c=D(mx0), sp=t1-t0; S.t0=c-sp/2; S.t1=c+sp/2; clampView(); drawTimeline(); } };
      addEventListener('mousemove',move); addEventListener('mouseup',up); return;
    }
    const move=e2=>{ const dx=(e2.clientX-r.left-mx0)*k; if(h==='l') S.t0=Math.min(t0+dx,t1-14); else if(h==='r') S.t1=Math.max(t1+dx,t0+14); else { S.t0=t0+dx; S.t1=t1+dx; } clampView(); drawSoon(); };
    const up=()=>{ removeEventListener('mousemove',move); removeEventListener('mouseup',up); };
    addEventListener('mousemove',move); addEventListener('mouseup',up);
  };
}

/* ===== 回到原状：任何偏离默认的视图状态都显示成一枚可点掉的标签，一键还原 ===== */
const XI='<svg class="ic" viewBox="0 0 20 20"><path d="M6 6l8 8M14 6l-8 8"/></svg>';
function chipX(label,clear){ return `<span class="vchip">${label}<button onclick="${clear}" title="取消">${XI}</button></span>`; }
function rangeFull(){ return S.t0<=EXT[0]+0.5 && S.t1>=EXT[1]-0.5; }
function rangeText(){ const p=n=>String(n).padStart(2,'0'), ym=n=>{ const d=fromDn(n); return `${d.getUTCFullYear()}.${p(d.getUTCMonth()+1)}`; };
  const a=Math.max(S.t0,EXT[0]), b=Math.min(S.t1,EXT[1])-1; const ya=fromDn(a), yb=fromDn(b+1);
  if(ya.getUTCMonth()===0&&ya.getUTCDate()===1&&yb.getUTCMonth()===0&&yb.getUTCDate()===1&&yb.getUTCFullYear()-ya.getUTCFullYear()===1) return `${ya.getUTCFullYear()}年`;
  return `${ym(a)} — ${ym(b)}`; }
function renderVState(){
  const host=$('#vstate'); if(!host) return;
  const c=[];
  if(!rangeFull()) c.push(chipX(`时间范围：${rangeText()}`,'fit()'));
  if(S.stage<5){ const k=S.stage; S.stage=5; invalidate(); const all=derive().length; S.stage=k; invalidate(); c.push(chipX(`截至：${STAGES[S.stage]}（显示 ${visibleFacts().length} / ${all} 个事实）`,'S.stage=5;render()')); }
  if(S.typeOff.size) c.push(chipX(`已隐藏 ${S.typeOff.size} 类事件`,'S.typeOff.clear();render()'));
  host.innerHTML=c.length?`${c.join('')}${c.length>1?`<button class="vall" onclick="resetTL()">全部还原</button>`:''}`:'';
  host.style.display=c.length?'flex':'none';
}
function resetTL(){ S.t0=EXT[0]; S.t1=EXT[1]; S.stage=5; S.typeOff.clear(); render(); }
function tableState(){
  const f=S.f, c=[], nm=(set,map)=>[...set].map(map).join('、');
  if(S.q.trim()) c.push(chipX(`搜索：${esc(S.q.trim())}`,"S.q='';render()"));
  if(f.types.size) c.push(chipX(`类型：${nm(f.types,t=>TYPES[t].n)}`,'S.f.types=new Set();render()'));
  if(f.kinds.size) c.push(chipX(`来源：${nm(f.kinds,k=>KIND[k].n)}`,'S.f.kinds=new Set();render()'));
  if(f.cf&&f.cf.size) c.push(chipX(`程序状态：${nm(f.cf,x=>x)}`,'S.f.cf=new Set();render()'));
  if(f.rev.size) c.push(chipX(`审阅：${nm(f.rev,x=>x==='done'?'已确认':'待确认')}`,'S.f.rev=new Set();render()'));
  if(f.conf) c.push(chipX('只看记载不一的','S.f.conf=false;render()'));
  if(f.key) c.push(chipX('只看关键事实','S.f.key=false;render()'));
  if(!S.sortAsc) c.push(chipX('日期倒序','S.sortAsc=true;render()'));
  return c.length?c.join('')+(c.length>1?`<button class="vall" onclick="resetTable()">全部清除</button>`:''):'';
}
function resetTable(){ S.q=''; S.f={types:new Set(),kinds:new Set(),rev:new Set(),cf:new Set(),conf:false,key:false}; S.sortAsc=true; render(); }
function narrModified(){ return !!(S.nOrder || Object.keys(S.nMerge||{}).length || Object.keys(S.nTitle||{}).length); }
function resetThreads(){ S.nOrder=null; S.nMerge={}; S.nTitle={}; logIt(null,'线索恢复原样',''); drawNarr(); }

/* 拖动时每一帧最多重画一次，省资源 */
function drawSoon(){ if(drawSoon.r) return; drawSoon.r=requestAnimationFrame(()=>{ drawSoon.r=0; drawTimeline(); }); }

function sidePop(ev){ const ps=CASE.parties||[]; pop(ev,`<h4>哪一方是「我方」</h4>${ps.map((p,i)=>`<button class="mi" onclick="S.nUs=${i};closePops();drawNarr()"><span class="ck">${(S.nUs||0)===i?ICO.check:''}</span>${esc(p.name)}（${esc(p.role||'')}）</button>`).join('')}`,240); }

/* 切换「大事记表 / 叙述」：表头钉在顶部不动；若已往下翻过，正文从头开始，不让页面突然缩短造成乱跳 */
function setNView(v){ if((S.nView||'table')===v) return; const h=$('#narr'), top=h?h.getBoundingClientRect().top:0; S.nView=v; drawNarr(); if(h && top<0) scrollTo({top:scrollY+h.getBoundingClientRect().top-8,behavior:'instant'}); }
