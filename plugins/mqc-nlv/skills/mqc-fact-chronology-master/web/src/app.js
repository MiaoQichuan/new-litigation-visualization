/* =====================================================================
   V8 事实工作台 · 应用层
   ===================================================================== */
/* 当前案件：界面只读这一份底稿，不内置任何案子 */
let CASE, PACK, DOCS=[], FACTS=[], CLAIMS=[], RELATED=[], ATTN=[], INFER={}, TYPES={}, TYPE_ORDER=[], ACTORS={}, ACTOR_ORDER=[], DOC={}, REC={}, FACT={}, EXT=[0,1];
/* 别的 Agent 写的底稿可能缺可选字段：读入时补齐默认值，页面任何一处都不因缺字段而打不开 */
function normCase(c){
  c.materials=(c.materials||[]).map(m=>({kind:'record',lines:[],...m,lines:Array.isArray(m.lines)?m.lines:[],stage:Number.isInteger(m.stage)?m.stage:0}));
  c.facts=(c.facts||[]).map(f=>({t:'other',title:f.id,...f,recs:(f.recs||[]).map(r=>({p:r.s?'day':'none',...r,q:r.q||'',raw:r.raw||''}))}));
  c.attention=(c.attention||[]).map(a=>({title:'',why:'',q:'',loc:'',...a,ctx:Array.isArray(a.ctx)?a.ctx:[]}));
  c.arith=(c.arith||[]).map(a=>({title:'',why:'',q:'',loc:'',...a}));
  c.claims=(c.claims||[]).map(x=>({title:'',q:'',...x}));
  c.relations=(c.relations||[]).filter(r=>Array.isArray(r)&&r.length>=2).map(r=>[r[0],r[1],r[2]||'']);
  c.threads=(c.threads||[]).map(t=>({...t,facts:t.facts||[]}));
  c.parties=c.parties||[]; c.inferences=c.inferences||{};
  return c;
}
function loadCase(c){
  normCase(c); CASE=c; PACK=PACKS[c.pack]||PACKS.general; S.pend=(c.pending||[]).map(p=>({id:p.mid,name:p.name,size:p.size||0,ext:EXTN(p.name||''),kind:'',date:p.doc_date||'',read:true,text:p.text,data:p.data}));
  DOCS=c.materials||[]; FACTS=c.facts||[]; CLAIMS=c.claims||[]; RELATED=c.relations||[]; ATTN=c.attention||[]; INFER=c.inferences||{};
  ACTORS=c.actors||{}; ACTOR_ORDER=c.actorOrder||Object.keys(ACTORS);
  TYPES={}; Object.entries(CORE_TYPES).forEach(([k,v])=>TYPES[k]={...v,...(PACK.types[k]||{})}); Object.assign(TYPES,PACK.extraTypes||{});
  TYPE_ORDER=[...CORE_ORDER.slice(0,-1),...Object.keys(PACK.extraTypes||{}),'other'];
  DOC=Object.fromEntries(DOCS.map(d=>[d.id,d]));
  FACTS.forEach(f=>{ f.recs=f.recs||[]; f.recs.forEach((r,i)=>{ r.rid=f.id+'.'+(i+1); r.fid=f.id; }); if(!TYPES[f.t]) f.t='other'; });
  REC=Object.fromEntries(FACTS.flatMap(f=>f.recs.map(r=>[r.rid,r]))); FACT=Object.fromEntries(FACTS.map(f=>[f.id,f]));
  const ds=FACTS.flatMap(f=>f.recs.flatMap(r=>[r.s,r.e].filter(Boolean))).concat(CLAIMS.map(x=>x.s).filter(Boolean)).map(dn);
  if(ds.length){ const a=Math.min(...ds), b=Math.max(...ds), pad=Math.max(20,(b-a)*.035); EXT=[a-pad,b+pad]; } else { const t=dn(new Date().toISOString().slice(0,10)); EXT=[t-365,t]; }
  Object.assign(S,{view:'work',tab:'tl',phase:'ready',read:DOCS.length,reading:-1,lanes:'type',more:false,typeOff:new Set(),selected:null,checked:new Set(),q:'',drawer:null,rfilter:'all',docOv:{},stage:5,play:null,exp:null,t0:EXT[0],t1:EXT[1],f:{types:new Set(),kinds:new Set(),rev:new Set(),cf:new Set(),conf:false,key:false}});
  resetDecisions();
  if(c.decisions){ DEC_KEYS.forEach(k=>{ if(c.decisions[k]!==undefined) S[k]=JSON.parse(JSON.stringify(c.decisions[k])); }); if(c.decisions.aside) S.aside=new Set(c.decisions.aside); }
  if(Array.isArray(c.changes)) S.log=c.changes.slice();
  invalidate();
}

const S = {
  view:'work', tab:'tl', phase:'ready', read:DOCS.length, reading:-1,
  lanes:'type', more:false, typeOff:new Set(), t0:0, t1:0,
  selected:null, checked:new Set(), q:'', f:{types:new Set(),kinds:new Set(),rev:new Set(),cf:new Set(),conf:false,key:false}, sortAsc:true,
  drawer:null, rfilter:'all',
  adopt:{}, cres:{}, rev:{}, disp:{}, key:{}, adverse:{}, inferOk:{}, susRes:{}, aside:new Set(), attnRes:{}, packRes:{},
  docOv:{}, log:[], stage:5, reviewLayer:true, showRel:false, showClaims:true, play:null, matrixConf:false,
  exp:null
};
/* 只到月（YYYY-MM）或只到年时补 1，免得整幅时间轴算出 NaN */
const dn = iso => { const p=String(iso||'').split('-').map(Number); return Date.UTC(p[0],(p[1]||1)-1,p[2]||1)/864e5; };
const fromDn = n => new Date(n*864e5);
const isoOf = n => fromDn(n).toISOString().slice(0,10);
const esc = s => String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmtD = n => { const d=fromDn(typeof n==='string'?dn(n):n); return `${d.getUTCFullYear()}年${d.getUTCMonth()+1}月${d.getUTCDate()}日`; };
const fmtS = n => { const d=fromDn(typeof n==='string'?dn(n):n); return `${d.getUTCMonth()+1}月${d.getUTCDate()}日`; };
const fmtM = n => { const d=fromDn(typeof n==='string'?dn(n):n); return `${d.getUTCFullYear()}年${d.getUTCMonth()+1}月`; };
const money = v => (Math.round(v*100)/100).toLocaleString('zh-CN',{maximumFractionDigits:2});
const $ = s=>document.querySelector(s);
const fmtAmt = v => `${(+v).toLocaleString('zh-CN',{maximumFractionDigits:6})} ${CASE&&CASE.unit||'元'}`;

/* ---------- 材料属性（可被律师改） ---------- */
const dKind = d => S.docOv[d]?.kind ?? DOC[d].kind;
const dStage = d => S.docOv[d]?.stage ?? DOC[d].stage;
const dConf = d => S.docOv[d]?.confirm ?? DOC[d].confirm;
const docVisible = d => DOCS.findIndex(x=>x.id===d) < S.read && dStage(d) <= S.stage;
const isPrimary = d => ['record','edata'].includes(dKind(d));

/* =====================================================================
   派生：把底稿 + 律师的裁决 算成屏幕上要画的东西
   ===================================================================== */
/* 一条记载是不是当事人的说法：整份材料是陈述；或判决书、笔录里的「诉称」「辩称」「质证」「拟证明」等段落；底稿可用 stmt 明示 */
const STMT_HINT=/诉称|辩称|答辩|质证|拟证明|陈述|主张|代理意见|申请书/;
function recStmt(r){ if(r.stmt===false) return false; if(r.stmt===true) return true; if(S.docOv[r.d]&&S.docOv[r.d].kind) return S.docOv[r.d].kind==='statement'; /* 律师改过材料种类，以律师为准 */ return dKind(r.d)==='statement' || STMT_HINT.test((r.loc||'')+' '+(r.q||'').slice(0,8)); }
function recIv(r){ if(r.p==='day') return [dn(r.s),dn(r.s)]; if(r.p==='none') return null; return [dn(r.s),dn(r.e||r.s)]; }
function deriveOne(f, recs, idOverride, titleOverride){
  const live = recs.map(r=>r.inf && S.inferOk[r.inf]==='undated' ? {...r,p:'none',s:null,e:null,raw:r.raw+'（推断已撤回）'} : r);
  const dated = live.filter(r=>r.p!=='none' && !(r.inf && S.inferOk[r.inf]==='undated'));
  const strict = dated.filter(r=>!r.loose);
  const id = idOverride||f.id;
  const range = f.kind==='range';
  let conflict=false, lo=null, hi=null, main=null, tail=null, spread=0;
  if(strict.length){
    if(!range){
      const ivs=strict.map(recIv); lo=Math.max(...ivs.map(i=>i[0])); hi=Math.min(...ivs.map(i=>i[1]));
      conflict = lo>hi;
      const all=[...ivs.map(i=>i[0]),...ivs.map(i=>i[1])]; spread=Math.max(...all)-Math.min(...all);
    } else {
      const ss=strict.map(r=>dn(r.s)), es=strict.map(r=>dn(r.e));
      conflict = Math.max(...ss)!==Math.min(...ss) || Math.max(...es)!==Math.min(...es);
      spread = Math.max(...es)-Math.min(...es);
    }
  }
  if(S.cres[f.id]==='planned') conflict=false;
  const adopted = S.adopt[f.id] && live.find(r=>r.rid===S.adopt[f.id] && (r.p!=='none'||r.amt!=null)) ? S.adopt[f.id] : null;
  const wasConflict = conflict;
  if(adopted){
    const r=live.find(x=>x.rid===adopted), iv=recIv(r);
    main = !iv ? null : range ? {lo:dn(r.s),hi:dn(r.e),p:'range'} : {lo:iv[0],hi:iv[1],p:r.p};
    conflict=false;
  } else if(!conflict && dated.length){
    if(range){
      if(strict.length) main={lo:dn(strict[0].s),hi:dn(strict[0].e),p:'range'};
      else main={lo:dn(dated[0].s),hi:dn(dated[0].e),p:'arange'};
    } else if(strict.length){
      /* 全部记载都是「大致时段」时保留为时段，不要读成一个日子 */
      const allAr=strict.every(r=>r.p==='arange');
      main = lo===hi ? {lo,hi,p:'day'} : allAr ? {lo,hi,p:'arange'} : {lo,hi,p: strict.some(r=>r.p==='month')?'month':'approx'};
    } else { const iv=recIv(dated[0]); main={lo:iv[0],hi:iv[1],p:'approx'}; }
  } else if(conflict && range){
    const ss=strict.map(r=>dn(r.s)), es=strict.map(r=>dn(r.e));
    main={lo:Math.max(...ss),hi:Math.min(...es),p:'range'}; tail={lo:Math.min(...es),hi:Math.max(...es)};
  }
  const band = (!range && strict.length) ? (()=>{ const ivs=strict.map(recIv); return {lo:Math.min(...ivs.map(i=>i[0])),hi:Math.max(...ivs.map(i=>i[1]))}; })() : null;
  const usedRecs = adopted ? [REC[adopted]] : (conflict? [] : strict.filter(r=>{ if(range||!main) return true; const iv=recIv(r); return iv[0]<=main.hi && iv[1]>=main.lo; }));
  const inferredOnly = dated.length>0 && dated.every(r=>r.inf);
  const hasPrimaryClean = (usedRecs.length?usedRecs:dated).some(r=>isPrimary(r.d) && !r.inf);
  const certain = !conflict && main && ['day','range'].includes(main.p) && hasPrimaryClean;
  const stmtOnly = f.t!=='filing' && live.every(recStmt);
  const sortKey = main? main.lo : band? band.lo : (dated[0]? dn(dated[0].s) : Infinity);
  const withAmt = live.filter(r=>r.amt!=null), amtVals=[...new Set(withAmt.map(r=>+r.amt))];
  const amtConflict = amtVals.length>1 && !adopted && S.cres[f.id]!=='planned';
  const amt = adopted && REC[adopted].amt!=null ? +REC[adopted].amt : (amtVals.length===1? amtVals[0] : null);
  return { id, f, t:f.t, title:titleOverride||f.title, state:f.state, kind:f.kind||'point', act:f.act||[],
    key: S.key[f.id]!==undefined ? S.key[f.id] : !!f.key,
    recs:live, dated, strict, conflict, wasConflict, adopted, main, tail, band, spread,
    undated: dated.length===0, est: inferredOnly, certain, stmtOnly, sortKey,
    rev: S.rev[f.id]||'todo', disp: S.disp[f.id]||'待定', adverse: S.adverse[f.id]||'', role:f.role||'', amt, amtConflict, amtVals, anyConf: conflict||amtConflict };
}
let _cache=null;
function invalidate(){ _cache=null; }
function derive(){
  if(_cache) return _cache;
  const out=[];
  for(const f of effFacts()){
    let recs=f.recs.filter(r=>docVisible(r.d));
    const sus=recs.filter(r=>r.sus); recs=recs.filter(r=>!r.sus);
    if(!recs.length && sus.length && S.susRes[sus[0].rid]!=='event'){ const d=deriveOne(f,sus.map(r=>({...r,p:'none',raw:r.raw+'（日期可疑，待确认）'}))); d.susOnly=1; out.push(d); continue; }
    if(S.cres[f.id]==='split'){
      const groups={}; recs.forEach(r=>{ const iv=recIv(r); const k=iv?iv.join('-'):'none'; (groups[k]=groups[k]||[]).push(r); });
      Object.values(groups).forEach((g,i)=>{ out.push(deriveOne(f,g,f.id+'·'+(i+1),`${f.title}（${[...new Set(g.map(r=>r.d))].join('、')} 所载）`)); });
    } else if(recs.length) out.push(deriveOne(f,recs));
    sus.forEach(r=>{ if(S.susRes[r.rid]==='event'){ const d=deriveOne({...f,id:recs.length?f.id+'x':f.id,title:recs.length?`${f.title}（${docShort(r.d)}所载）`:f.title,key:0},[{...r,sus:0}]); d.flag='日期可疑'; out.push(d);} });
  }
  out.sort((a,b)=>a.sortKey-b.sortKey || a.id.localeCompare(b.id));
  _cache=out; return out;
}
function visibleFacts(){
  let evs=derive();
  if(S.play!==null){ const order=playOrder(); const ids=new Set(order.slice(0,S.play).map(e=>e.id)); evs=evs.filter(e=>ids.has(e.id)); }
  return evs;
}
function playOrder(){ return derive().filter(e=>!e.undated); }
function claimsVisible(){ return CLAIMS.filter(c=>docVisible(c.d)); }

/* ---------- 标签与措辞 ---------- */
function dateLabel(e){
  if(e.undated) return '无日期';
  if(e.conflict && !e.main) return '记载不一';
  if(e.conflict && e.kind==='range') return e.main?`${fmtD(e.main.lo)} 起·止日记载不一`:'起止日记载不一';
  const m=e.main; if(!m) return '记载不一';
  if(m.p==='day') return fmtD(m.lo);
  if(m.p==='month') return fmtM(m.lo);
  if(m.p==='approx') return `约 ${fmtD(m.lo)}—${fmtS(m.hi)}`;
  if(m.p==='range') return `${fmtD(m.lo)} 至 ${fromDn(m.lo).getUTCFullYear()===fromDn(m.hi).getUTCFullYear()?fmtS(m.hi):fmtD(m.hi)}`;
  if(m.p==='arange') return fmtM(m.lo)===fmtM(m.hi)?`约 ${fmtM(m.lo)}`:`约 ${fmtM(m.lo)}—${fmtM(m.hi)}`;
  return '';
}
function dateNote(e){
  const n=[];
  if(e.main && (e.main.p==='approx'||e.main.p==='arange')) n.push('大致时间');
  if(e.main && e.main.p==='month') n.push('仅到月');
  if(e.main && e.main.p==='range') n.push(`${e.main.hi-e.main.lo+1} 天`);
  if(e.est) n.push('推定');
  else if(e.dated.some(r=>r.inf)) n.push('含推断记载');
  if(e.adopted) n.push('已采信');
  return n.join(' · ');
}
const kindTag = d => { const k=dKind(d); return k==='statement'?'<span class="tag amber">陈述</span>':k==='testimony'?'<span class="tag black">证言</span>':`<span class="sq" title="${KIND[k].n}"></span>`; };
const docShort = d => DOC[d].sub.replace(/（.*?）/g,'').replace(/\s.*$/,'');
function bestRec(e){
  if(e.adopted) return REC[e.adopted];
  const pool=(e.conflict?[]:e.dated.length?e.dated:e.recs).filter(r=>!r.sus);
  if(!pool.length) return e.recs[0];
  return [...pool].sort((a,b)=>(KIND[dKind(b.d)].rank-(b.inf?2:0))-(KIND[dKind(a.d)].rank-(a.inf?2:0)))[0];
}
/* 固定措辞：level full=客户·每条写全；doubt=法官·只在存疑处；plain=团队 */
function phrase(e,level='plain'){
  if(e.amtConflict && !e.conflict){
    return '金额记载不一：'+e.recs.filter(r=>r.amt!=null).map(r=>`${docShort(r.d)}（${r.d}）为 ${fmtAmt(r.amt)}`).join('；')+'。';
  }
  if(e.conflict){
    return '日期记载不一：'+e.strict.map(r=>`${docShort(r.d)}（${r.d}）为「${r.raw}」`).join('；')+'。';
  }
  const r=bestRec(e); const k=dKind(r.d);
  const cf=dConf(r.d), pre = cf==='法院认定'||cf==='生效确认' ? '法院已认定的' : cf==='已质证' ? '经质证的' : '';
  let s = k==='statement' ? `据${docShort(r.d)}陈述：「${r.q}」` : k==='testimony' ? `${pre}证人证言称：「${r.q}」` : `${pre}${docShort(r.d)}显示：「${r.q}」`;
  if(cf==='未被采纳' && k!=='statement') s+='（该证据未被法院采纳）';
  if(r.inf) s = `约${dateLabel(e)}（推定：${INFER[r.inf].n}）。`+s;
  if(level==='full'){ const c=dConf(r.d); s += `（${c}${c==='已提交'?'，尚未质证':''}）`; }
  if(level==='doubt' && e.stmtOnly) s += '（目前尚无书证）';
  return s;
}

/* =====================================================================
   待审：全部由代码从底稿与裁决里算出
   ===================================================================== */
function reviewItems(){
  if(S.phase!=='ready') return [];
  const evs=derive(); const items=[];
  evs.filter(e=>e.conflict).forEach(e=>items.push({k:'conflict',id:'C:'+e.f.id,e}));
  evs.filter(e=>e.amtConflict).forEach(e=>items.push({k:'amount',id:'M:'+e.f.id,e}));
  (PACK.rules||[]).forEach(rule=>{
    if(rule.kind==='needDocTag') evs.filter(e=>e.role===rule.role && !e.recs.some(r=>(DOC[r.d].tags||[]).includes(rule.tag))).forEach(e=>{ const id='P:'+rule.id+':'+e.id; if(!S.packRes[id]) items.push({k:'pack',id,rule,fs:[e]}); });
    if(rule.kind==='sum'){ const parts=evs.filter(e=>e.role===rule.parts&&e.amt!=null), tot=evs.filter(e=>e.role===rule.total&&e.amt!=null);
      if(parts.length&&tot.length){ const sum=parts.reduce((a,e)=>a+e.amt,0); tot.forEach(t=>{ const id='P:'+rule.id+':'+t.id; if(Math.abs(sum-t.amt)>0.005 && !S.packRes[id]) items.push({k:'pack',id,rule,fs:[...parts,t],sum,total:t.amt}); }); } }
  });
  Object.keys(INFER).forEach(k=>{ const fs=evs.filter(e=>e.recs.some(r=>r.inf===k)); const gone=derive===null; if(fs.length && !S.inferOk[k]) items.push({k:'infer',id:'I:'+k,key:k,fs}); });
  FACTS.forEach(f=>f.recs.filter(r=>r.sus && docVisible(r.d) && !S.susRes[r.rid]).forEach(r=>items.push({k:'suspect',id:'S:'+r.rid,r,f})));
  const np=evs.filter(e=>e.stmtOnly && !S.aside.has(e.id)); if(np.length) items.push({k:'np',id:'N',fs:np});
  ATTN.filter(a=>docVisible(a.d) && !S.attnRes[a.id]).forEach(a=>items.push({k:'att',id:'A:'+a.id,a}));
  dupGroups().filter(g=>!S.dupRes[g.id]).forEach(g=>items.push({k:'dup',id:g.id,g}));
  arithItems().filter(a=>!S.arithRes[a.id]).forEach(a=>items.push({k:'arith',id:a.id,a}));
  return items;
}
const itemCount = it => it.k==='np'? it.fs.length : it.k==='infer'? 1 : 1;
const pendingCount = () => reviewItems().reduce((a,it)=>a+itemCount(it),0);
const RK = {conflict:'日期冲突',amount:'金额冲突',dup:'疑似重复',arith:'数字对不上',pack:'领域规则',infer:'推断日期',suspect:'可疑日期',np:'仅有当事人陈述',att:'需留意'};

/* =====================================================================
   渲染总入口
   ===================================================================== */
function render(){
  invalidate();
  const v=$('#view');
  if(S.view==='new') v.innerHTML=viewNew();
  else if(S.view==='docs') v.innerHTML=viewDocs();
  else if(S.view==='stage') v.innerHTML=viewStage();
  else v.innerHTML=viewWork();
  renderDrawer();
  if(S.view==='work'){
    if(S.tab==='tl'){ drawTimeline(); drawTable(); }
    if(S.tab==='matrix') drawMatrix();
    if(S.tab==='narr') drawNarr();
  }
}
function logIt(fid,what,detail){ const d=new Date(); S.log.unshift({fid,t:`${d.getHours()}:${String(d.getMinutes()).padStart(2,'0')}`,what,detail}); }

/* ---------- 头部 ---------- */
const ICON={
  doc:'<svg class="ico" viewBox="0 0 16 16"><rect x="3" y="2" width="8" height="11" rx="1.5" fill="none" stroke="currentColor"/><path d="M6 5h7v9H6" fill="none" stroke="currentColor"/></svg>',
  add:'<svg class="ico" viewBox="0 0 16 16"><path d="M4 2h6l3 3v9H4z" fill="none" stroke="currentColor"/><path d="M8.5 7v5M6 9.5h5" stroke="currentColor"/></svg>',
  out:'<svg class="ico" viewBox="0 0 16 16"><path d="M8 2v8M5 7l3 3 3-3M3 13h10" fill="none" stroke="currentColor"/></svg>'
};
function progress(){
  const n=S.read,total=DOCS.length,evs=derive().length;
  const pct=S.phase==='compare'?100:Math.round(n/total*100);
  const txt=S.phase==='compare'?`${evs} 个事实，来自 ${total} 份材料 · 正在把同一件事的记载归并、比对……`
    :`已读 ${n} / ${total} 份，已得 ${evs} 个事实${S.reading>=0?`，正在读 ${DOCS[S.reading].id}`:''}。请保持此页打开。`;
  return `<div class="prog"><div class="bar"><i style="width:${pct}%"></i></div><div class="progtxt"><span>${txt}</span><button class="btn ghost" onclick="stopBuild()">■ 停止</button></div></div>`;
}

/* ---------- 工作台 ---------- */
/* ---------- 时间轴 ---------- */
let LW=158;
function lanesFor(evs){
  const dated=evs.filter(e=>!e.undated), playing=S.play!==null;
  /* 回放时泳道按全部事实排好，不随步数增减，画面不跳 */
  const base=playing?derive().filter(e=>!e.undated):dated;
  const allClaims = S.showClaims ? claimsVisible().filter(c=>c.s) : [], claims=playing?[]:allClaims;
  if(S.lanes==='type'){
    const cnt={}; base.forEach(e=>cnt[e.t]=(cnt[e.t]||0)+1);
    const keys=TYPE_ORDER.filter(t=>S.more || cnt[t]);
    const L=keys.map(t=>({key:t,label:TYPES[t].n,color:TYPES[t].c,items:dated.filter(e=>e.t===t).map(e=>({e}))}));
    if(allClaims.length) L.push({key:'claim',label:'原告主张',color:'#8E8C85',items:claims.map(c=>({c}))});
    return L;
  }
  if(S.lanes==='doc'){
    return DOCS.filter(d=>docVisible(d.id)).map(d=>({key:d.id,label:`${d.id} ${docShort(d.id)}`,doc:d,
      items:dated.flatMap(e=>e.dated.filter(r=>r.d===d.id).map(r=>({e,r})))}));
  }
  if(S.lanes==='actor') return ACTOR_ORDER.filter(a=>base.some(e=>e.act.includes(a))).map(a=>({key:a,label:ACTORS[a],items:dated.filter(e=>e.act.includes(a)).map(e=>({e}))}));
  return [{key:'all',label:'全部事实',items:dated.filter(e=>!S.typeOff.has(e.t)).map(e=>({e}))}];
}
function textW(s,fs=11.5){ let w=0; for(const ch of s) w+=/[\u0000-\u00ff]/.test(ch)?fs*.56:fs; return w; }
function trunc(s,max,fs=11.5){ if(textW(s,fs)<=max) return s; let o=''; for(const ch of s){ if(textW(o+ch+'…',fs)>max) break; o+=ch; } return o?o+'…':''; }
let TL={};
function itemGeom(it,X){
  if(it.c){ const x=X(dn(it.c.s)); return {kind:'claim',x0:x-6,x1:x+6,x}; }
  const e=it.e;
  if(it.r){ const iv=recIv(it.r); if(it.r.p==='range'||it.r.p==='arange') return {kind:'span',a:X(iv[0]),b:X(iv[1]+1)}; if(iv[0]===iv[1]) { const x=X(iv[0]); return {kind:'rec',x0:x-6,x1:x+6,x}; } return {kind:'rband',x0:X(iv[0]),x1:X(iv[1]+1),x:X((iv[0]+iv[1]+1)/2)}; }
  if(e.kind==='range'){ const lo=e.main?e.main.lo:(e.band?e.band.lo:e.sortKey), hi=e.tail?e.tail.hi:(e.main?e.main.hi:(e.band?e.band.hi:lo)); return {kind:'span',a:X(lo), b:X(hi+1)}; }
  if(e.conflict){ const a=X(e.band.lo), b=X(e.band.hi+1); if(b-a<34){ const x=(a+b)/2; return {kind:'pt',x0:x-8,x1:x+8,x}; } return {kind:'span',a,b,sub:'c'}; }
  if(!e.main){ const x=X(e.band?e.band.lo:e.sortKey); return {kind:'pt',x0:x-7,x1:x+7,x}; }
  if(e.main.p==='day'){ const x=X(e.main.lo); return {kind:e.wasConflict?'adopted':'pt',x0:x-7,x1:x+7,x, bx0:e.band?X(e.band.lo):null,bx1:e.band?X(e.band.hi+1):null}; }
  if(e.main.p==='month'||e.main.p==='approx'||e.main.p==='arange') return {kind:'span',a:X(e.main.lo),b:X(e.main.hi+1),sub:'a'};
  return {kind:'pt',x0:X(e.main.lo)-7,x1:X(e.main.lo)+7,x:X(e.main.lo)};
}
function spanLabel(it){ const e=it.e; if(it.r) return it.r.raw; if(e.conflict&&e.kind!=='range') return `${e.title} · ${new Set(e.strict.map(r=>recIv(r).join())).size} 种说法`; return e.conflict? `${e.title} · 止日记载不一` : `${e.title}${e.main&&e.main.p==='range'?`（${e.main.hi-e.main.lo+1} 天）`:''}`; }
function shapeAt(kind,x,y,r,fill,stroke,dash){
  const sh=KIND[kind].shape, da=dash?'stroke-dasharray="2 1.5"':'';
  if(sh==='square') return `<rect x="${x-r}" y="${y-r}" width="${2*r}" height="${2*r}" fill="${fill}" stroke="${stroke}" stroke-width="1.3" ${da}/>`;
  if(sh==='triangle') return `<path d="M${x} ${y-r-1} L${x+r+1} ${y+r} L${x-r-1} ${y+r}Z" fill="${fill}" stroke="${stroke}" stroke-width="1.3" ${da}/>`;
  return `<circle cx="${x}" cy="${y}" r="${r}" fill="${fill}" stroke="${stroke}" stroke-width="1.3" ${da}/>`;
}
function ticks(t0,t1,PW){
  const span=t1-t0, mw=PW/span*30.44, years=[], minor=[]; const a=fromDn(t0), b=fromDn(t1);
  for(let yv=a.getUTCFullYear(); yv<=b.getUTCFullYear()+1; yv++){ const d=Date.UTC(yv,0,1)/864e5; if(d>=t0&&d<=t1) years.push({d,label:String(yv)}); }
  if(!years.length || years[0].d-t0 > 50/(PW/span)) years.unshift({d:t0,label:String(a.getUTCFullYear())});
  const step = mw>=46?1: mw*3>=34?3:12;
  for(let yv=a.getUTCFullYear(); yv<=b.getUTCFullYear(); yv++) for(let m=0;m<12;m+=step){ const d=Date.UTC(yv,m,1)/864e5; if(d<t0||d>t1) continue; minor.push({d,label:step===1?`${m+1}月`:step===3?`Q${m/3+1}`:'',year:m===0}); }
  if(mw>=260){ minor.length=0; for(let d=Math.ceil(t0); d<=t1; d++){ const dt=fromDn(d); if(dt.getUTCDay()===1||dt.getUTCDate()===1) minor.push({d,label:`${dt.getUTCMonth()+1}/${dt.getUTCDate()}`,year:dt.getUTCDate()===1&&dt.getUTCMonth()===0}); } }
  return {years,minor};
}
function gaps(evs){
  const ds=[...new Set(evs.filter(e=>!e.undated).flatMap(e=>e.dated.flatMap(r=>{ const iv=recIv(r); return iv?iv:[]; })))].sort((a,b)=>a-b);
  const out=[]; for(let i=1;i<ds.length;i++) if(ds[i]-ds[i-1]>62) out.push([ds[i-1]+7,ds[i]-7]); return out;
}
function clampView(){ const sp=S.t1-S.t0, full=EXT[1]-EXT[0]; if(sp>full){ S.t0=EXT[0]; S.t1=EXT[1]; return; } if(S.t0<EXT[0]){ S.t0=EXT[0]; S.t1=EXT[0]+sp; } if(S.t1>EXT[1]){ S.t1=EXT[1]; S.t0=EXT[1]-sp; } }
function zoom(f,cx){ const c=cx??(S.t0+S.t1)/2, sp=(S.t1-S.t0)/f; if(sp<10) return; S.t0=c-(c-S.t0)/f; S.t1=S.t0+sp; clampView(); drawTimeline(); }
function fit(){ S.t0=EXT[0]; S.t1=EXT[1]; drawTimeline(); }
function bindTimeline(){
  const svg=$('#tlsvg'), tip=$('#tip');
  svg.onmousemove=ev=>{
    const g=ev.target.closest('.mk'); linkRows(g); if(!g){ tip.style.display='none'; return; }
    let html='';
    if(g.dataset.claim){ const c=CLAIMS.find(x=>x.id===g.dataset.claim); html=`<div class="tt">${c.who}主张：${esc(c.title)}</div><div class="td">主张不是事实</div>`; }
    else if(g.dataset.e){ const e=derive().find(x=>x.id===g.dataset.e); if(!e) return;
      const r=g.dataset.r?REC[g.dataset.r]:null;
      html=`<div class="tt">${esc(e.title)}</div><div class="td">${r?`${r.d} 记为「${esc(r.raw)}」`:dateLabel(e)+(dateNote(e)?' · '+dateNote(e):'')}</div>`+
        (e.conflict&&!r?`<div class="td" style="color:#F6C35B">${e.strict.map(r=>`${r.d}「${esc(r.raw)}」`).join('　')}</div>`:`<div class="td">${[...new Set(e.recs.map(r=>r.d))].map(d=>d+' '+KIND[dKind(d)].short).join('　')}</div>`)+
        `<div class="td">${e.certain?'确定':'未确定'}${S.reviewLayer?' · '+(e.rev==='done'?'已确认':'待确认'):''}</div>`;
    } else { const ids=TL.clusters[g.dataset.c], all=derive(); html=`<div class="tt">${ids.length} 个事实 · 点击放大</div>`+ids.slice(0,6).map(id=>{ const e=all.find(x=>x.id===id); return `<div class="td">${dateLabel(e)}　${esc(e.title)}</div>`; }).join(''); }
    if(g.dataset.e){ const e=derive().find(x=>x.id===g.dataset.e); if(e){ const ds=[...new Set(e.recs.map(r=>r.d))]; html+=`<div class="tsrc">材料 ${ds.map(esc).join('、')} · 下方表中已标亮</div>`; } }
    tip.innerHTML=html; tip.style.display='block'; tip.style.left=(ev.clientX+14)+'px'; tip.style.top=(ev.clientY+14)+'px';
  };
  svg.onmouseleave=()=>{ tip.style.display='none'; linkRows(null); };
  svg.onmousedown=ev=>{
    const g=ev.target.closest('.mk');
    if(g){ if(g.dataset.claim) openClaim(g.dataset.claim); else if(g.dataset.e) selectEv(g.dataset.e); else zoomCluster(+g.dataset.c); return; }
    const x0=ev.clientX, t0=S.t0, t1=S.t1, k=(t1-t0)/TL.PW; document.body.classList.add('panning');
    let raf=0; const move=e2=>{ const dx=(e2.clientX-x0)*k; S.t0=t0-dx; S.t1=t1-dx; clampView(); if(!raf) raf=requestAnimationFrame(()=>{ raf=0; drawTimeline(); }); };
    const up=()=>{ document.body.classList.remove('panning'); removeEventListener('mousemove',move); removeEventListener('mouseup',up); };
    addEventListener('mousemove',move); addEventListener('mouseup',up);
  };
  svg.onwheel=ev=>{ if(!(ev.ctrlKey||ev.metaKey)) return; ev.preventDefault(); const r=svg.getBoundingClientRect(); zoom(ev.deltaY<0?1.25:.8, S.t0+(ev.clientX-r.left-LW)/TL.PW*(S.t1-S.t0)); };
}
/* 图上指到哪个事实，下面事实表里对应的那一行同时亮起；反过来也一样 */
function linkRows(g){
  const ids=!g?[]:g.dataset.e?[g.dataset.e]:g.dataset.c!==undefined?(TL.clusters[g.dataset.c]||[]):[];
  document.querySelectorAll('tr.linkrow').forEach(r=>{ if(!ids.includes(r.id.slice(4))) r.classList.remove('linkrow'); });
  ids.forEach(id=>{ const r=document.getElementById('row-'+id); if(r) r.classList.add('linkrow'); });
}
function linkMark(id,on){ const svg=$('#tlsvg'); if(!svg) return; svg.querySelectorAll('.mk.linkmk').forEach(m=>m.classList.remove('linkmk')); if(on){ const m=svg.querySelector(`.mk[data-e="${id}"]`); if(m) m.classList.add('linkmk'); else { const ci=(TL.clusters||[]).findIndex(c=>c.includes(id)); if(ci>=0){ const c=svg.querySelector(`.mk[data-c="${ci}"]`); if(c) c.classList.add('linkmk'); } } } }
function zoomCluster(ci){ const ids=TL.clusters[ci], ds=derive().filter(e=>ids.includes(e.id)).map(e=>e.sortKey); const a=Math.min(...ds), b=Math.max(...ds), pad=Math.max(10,(b-a)*.8+6); S.t0=a-pad; S.t1=b+pad; clampView(); drawTimeline(); }
function toggleType(t){ S.typeOff.has(t)?S.typeOff.delete(t):S.typeOff.add(t); render(); }

/* ---------- 回放 ---------- */
function startPlay(){ if(!playOrder().length){ toast('没有带日期的事实，无法回放'); return; } S.play=1; S.drawer=null; render(); }
function playBar(){
  const order=playOrder(); if(!order.length){ S.play=null; return ''; } const k=Math.min(S.play,order.length), e=order[k-1];
  return `<div class="playbar"><button class="btn" onclick="playStep(-1)" ${k<=1?'disabled':''}>上一步</button>
    <div class="pcap"><b>第 ${k} / ${order.length} 步　${dateLabel(e)}</b>　${esc(e.title)}<div class="sub">${esc(phrase(e))}</div></div>
    <button class="btn" onclick="playStep(1)" ${k>=order.length?'disabled':''}>下一步</button><button class="btn" onclick="S.play=null;S.selected=null;render()">退出</button></div>`;
}
function playStep(d){ const order=playOrder(); if(!order.length||S.play===null){ S.play=null; return; } S.play=Math.max(1,Math.min(order.length,S.play+d)); const e=order[S.play-1]; S.selected=e.id; const sp=Math.min(EXT[1]-EXT[0],S.t1-S.t0); if(e.sortKey<S.t0||e.sortKey>S.t1){ S.t0=e.sortKey-sp/2; S.t1=e.sortKey+sp/2; clampView(); } render(); }

/* ---------- 事实表 ---------- */
function activeFilters(){ const f=S.f; return f.types.size+f.kinds.size+f.rev.size+(f.cf?f.cf.size:0)+(f.conf?1:0)+(f.key?1:0); }
function toggleRev(fid){ S.rev[fid]=S.rev[fid]==='done'?'todo':'done'; logIt(fid,S.rev[fid]==='done'?'标为已确认':'改回待确认',FACT[fid].title); render(); }
function toggleCheck(id){ S.checked.has(id)?S.checked.delete(id):S.checked.add(id); drawTable(); }
function batchBar(){ const b=$('#batch'); if(!b) return; const n=S.checked.size; b.innerHTML=n?`<span class="batch">已选 ${n} 项 <button onclick="batch('done')">标为已确认</button><button onclick="batch('key')">标为关键</button><button onclick="S.checked.clear();drawTable()">清除</button></span>`:''; }
function batch(k){ derive().filter(e=>S.checked.has(e.id)).forEach(e=>{ if(k==='key') S.key[e.f.id]=1; else S.rev[e.f.id]='done'; logIt(e.f.id,k==='key'?'标为关键':'标为已确认',e.title); }); S.checked.clear(); render(); }

/* ===== 设计层 v2：按 Anthropic Fact chronology 的视觉语言重做 ===== */
function tint(hex,a){ const n=parseInt(hex.slice(1),16), r=n>>16, g=n>>8&255, b=n&255; const m=v=>Math.round(v*a+255*(1-a)); return `rgb(${m(r)},${m(g)},${m(b)})`; }

function viewPop(ev){
  const row=(k,n,d)=>`<label class="opt"><input type="checkbox" ${S[k]?'checked':''} onchange="S.${k}=this.checked;closePops();render()"><span><b>${n}</b><br><span class="sub">${d}</span></span></label>`;
  pop(ev,`<h4>时间线上显示</h4>${row('showRel','关联','材料原文写明的指向，画成细箭头')}${row('showClaims','主张','原告主张画成方框，不与事实混排')}`,270);
}

function legend(evs){
  const li=(svg,t)=>`<span class="li">${svg}${t}</span>`;
  let h=`<div class="legend"><span class="lt">图例</span><span class="lgi">`+
    [li(svgI('unc'),'待审'),li(svgI('occ'),'已确认'),li(svgI('disp'),'有争议'),li(svgI('dia'),'大致日期'),li(svgI('cap'),'仅到月、季或年'),li(svgI('range'),'起止'),
     li(svgI('conf'),'日期冲突'),li(svgI('key'),'关键事实'),li(svgI('band'),'记载不一'),li(svgI('claim'),'主张')].join('')+
    `<span class="li muted">记号较小：把握较低</span></span>`;
  if(S.lanes==='one'){ const cnt={}; evs.forEach(e=>{ if(!e.undated) cnt[e.t]=(cnt[e.t]||0)+1; });
    h+=`<span class="types">${TYPE_ORDER.filter(t=>cnt[t]).map(t=>`<button class="tchip ${S.typeOff.has(t)?'off':''}" onclick="toggleType('${t}')"><span class="dot" style="background:${TYPES[t].c}"></span>${TYPES[t].n} ${cnt[t]}</button>`).join('')}${S.typeOff.size?`<button class="lnk" onclick="S.typeOff.clear();render()">全部显示</button>`:''}</span>`; }
  return h+'</div>';
}
function svgI(k){
  const c='#6D6C68', w=(k==='band'||k==='cap'||k==='range')?26:16;
  const m={
    occ:`<circle cx="8" cy="8" r="5.5" fill="${c}"/>`,
    unc:`<circle cx="8" cy="8" r="5.2" fill="${tint(c,.42)}" stroke="${c}" stroke-width="1.4"/>`,
    disp:`<circle cx="8" cy="8" r="5.2" fill="${tint(c,.42)}" stroke="${c}" stroke-width="1.4"/><path d="M4.8 11.2 11.2 4.8" stroke="${c}" stroke-width="1.4"/>`,
    dia:`<path d="M8 2.2 13.8 8 8 13.8 2.2 8Z" fill="${tint(c,.42)}" stroke="${c}" stroke-width="1.3"/>`,
    cap:`<rect x="1.5" y="3.5" width="23" height="9" rx="4.5" fill="${tint(c,.3)}" stroke="${c}" stroke-width="1.2"/>`,
    range:`<rect x="1.5" y="6" width="23" height="4.5" rx="2.25" fill="${c}"/>`,
    band:`<rect x="1" y="2.5" width="24" height="11" rx="5.5" fill="#FAEED3"/><rect x="5" y="5.5" width="5" height="5" fill="#fff" stroke="${c}" stroke-width="1.1"/><circle cx="18" cy="8" r="2.6" fill="#fff" stroke="${c}" stroke-width="1.1"/>`,
    conf:`<circle cx="8" cy="8" r="3.5" fill="#F2A50C"/>`,
    key:`<circle cx="8" cy="8" r="7" fill="${tint(c,.42)}" stroke="${c}" stroke-width="1.6"/>`,
    claim:`<rect x="3" y="3" width="10" height="10" fill="#fff" stroke="${c}" stroke-width="1.4"/>`
  };
  return `<svg width="${w}" height="16" viewBox="0 0 ${w} 16">${m[k]}</svg>`;
}

/* ---------- 时间轴 ---------- */
let AXH=40, ROWH=34, SPANH=30;
function drawTimeline(){
  const host=$('#tl'); if(!host) return;
  const evs=visibleFacts();
  const W=Math.max(680,host.clientWidth||900), PW=W-LW-14, span=S.t1-S.t0;
  const X=d=>LW+(d-S.t0)/span*PW;
  TL={W,PW,X,pos:{}};
  const lanes=lanesFor(evs), sel=S.selected, clusters=[], parts=[], RT=new Set(S.showRel?RELATED.map(r=>r[1]):[]);
  const L=lanes.map(l=>{
    const rowItems=[], spans=[];
    l.items.forEach(it=>{ const g=itemGeom(it,X); g.it=it; if(g.kind==='span') spans.push(g); else rowItems.push(g); });
    rowItems.sort((a,b)=>a.x0-b.x0);
    const groups=[];
    for(const g of rowItems){ const last=groups[groups.length-1], simple=g.kind==='pt'||g.kind==='rec';
      if(simple && last && last.simple && g.x-last.xl<18){ last.m.push(g); last.xl=g.x; last.x1=g.x1; } else groups.push({m:[g],simple,xl:g.x,x0:g.x0,x1:g.x1}); }
    groups.forEach(gr=>{ if(gr.m.length>1){ gr.x=(gr.m[0].x+gr.xl)/2; gr.x0=gr.x-12; gr.x1=gr.x+12; } });
    spans.sort((a,b)=>a.a-b.a); const rows=[];
    spans.forEach(s=>{ const st=Math.max(s.a,LW)-8, lw=Math.max(s.b-Math.max(s.a,LW)+16, textW(spanLabel(s.it),11.5)*1.12+14); let r=rows.findIndex(end=>end<st); if(r<0){ rows.push(0); r=rows.length-1; } rows[r]=st+lw; s.r=r; });
    return {...l,groups,spans,h:ROWH+rows.length*SPANH};
  });
  if(S.play!==null){ lanesFor(derive()).forEach(fl=>{ const sp=[]; fl.items.forEach(it=>{ const g=itemGeom(it,X); g.it=it; if(g.kind==='span') sp.push(g); }); sp.sort((a,b)=>a.a-b.a); const rows=[];
    sp.forEach(s=>{ const st=Math.max(s.a,LW)-8, lw=Math.max(s.b-Math.max(s.a,LW)+16, textW(spanLabel(s.it),11.5)*1.12+14); let r=rows.findIndex(end=>end<st); if(r<0){ rows.push(0); r=rows.length-1; } rows[r]=st+lw; });
    const l=L.find(x=>x.key===fl.key); if(l) l.h=Math.max(l.h,ROWH+rows.length*SPANH); }); }
  const H=AXH+L.reduce((a,l)=>a+l.h,0)+4;
  const tk=ticks(S.t0,S.t1,PW);
  parts.push(`<defs><clipPath id="clip"><rect x="${LW}" y="0" width="${PW}" height="${H}"/></clipPath>
    <pattern id="hatch" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="7" stroke="#DAD8D1" stroke-width="1"/></pattern>
    <marker id="arr" markerUnits="userSpaceOnUse" markerWidth="8" markerHeight="6" refX="0" refY="3" orient="auto"><path d="M0 0 8 3 0 6z" fill="#8E8C87"/></marker></defs>`);
  parts.push(`<g clip-path="url(#clip)">`);
  gaps(evs).forEach(g=>{ const a=X(g[0]),b=X(g[1]); if(b-a<6) return; parts.push(`<rect x="${a}" y="${AXH}" width="${b-a}" height="${H-AXH}" fill="url(#hatch)" class="gap" data-gap="${Math.round((g[1]-g[0])/30)}"/>`); });
  tk.minor.forEach(t=>parts.push(`<line x1="${X(t.d)}" x2="${X(t.d)}" y1="${AXH-8}" y2="${H}" stroke="${t.year?'#CFCDC6':'#ECEBE6'}"/>`));
  parts.push(`</g>`);
  tk.years.filter(t=>X(t.d)<LW+PW-34).forEach(t=>parts.push(`<text x="${Math.max(LW+4,X(t.d)+4)}" y="14" font-size="12" font-weight="600" fill="#1D1D1F" class="num">${t.label}</text>`));
  tk.minor.forEach((t,i)=>{ if(!t.label) return; const nx=i<tk.minor.length-1?X(tk.minor[i+1].d):X(S.t1); const cx=(X(t.d)+nx)/2; if(cx<LW+8||cx>LW+PW-6) return; parts.push(`<text x="${cx}" y="32" font-size="11.5" fill="#86868B" text-anchor="middle">${t.label}</text>`); });
  parts.push(`<line x1="0" x2="${W}" y1="${AXH}" y2="${AXH}" stroke="#E2E1DB"/>`);
  let y=AXH;
  L.forEach(l=>{
    const top=y, cy=top+ROWH/2;
    parts.push(`<line x1="0" x2="${W}" y1="${top+l.h}" y2="${top+l.h}" stroke="#EDECE7"/>`);
    if(S.lanes==='doc'){ const k=dKind(l.key); parts.push(`<g style="cursor:pointer" onclick="openDoc('${l.key}')">${shapeAt(k,16,cy,4,k==='record'||k==='edata'?'#B9B7B0':k==='statement'?'#E9B44C':'#1A1A1A','none')}<text x="28" y="${cy+4.5}" font-size="13" fill="#1A1A1A">${esc(trunc(l.label,LW-36,13))}</text></g>`); }
    else parts.push(`<circle cx="16" cy="${cy}" r="4.2" fill="${l.color||'#B9B7B0'}"/><text x="28" y="${cy+4.5}" font-size="13" fill="#1A1A1A">${esc(trunc(l.label,LW-36,13))}</text>`);
    parts.push(`<g clip-path="url(#clip)">`);
    l.spans.forEach(s=>{ const yy=top+ROWH+9+s.r*SPANH; parts.push(drawSpan(s,yy,X,sel)); TL.pos[s.it.e.id]=TL.pos[s.it.e.id]||{x:s.a,y:yy,r:3,span:1}; });
    let lastEnd=LW;
    l.groups.forEach((gr,gi)=>{
      const hasRT=gr2=>gr2.m.some(g=>g.it.e&&RT.has(g.it.e.id)), isRT=hasRT(gr);
      const nextX=gi<l.groups.length-1?Math.min(l.groups[gi+1].x0-(hasRT(l.groups[gi+1])?20:0),LW+PW):LW+PW;
      if(gr.m.length>1){
        const ci=clusters.length; clusters.push(gr.m.map(g=>g.it.e.id));
        const c=S.lanes==='type'?l.color:'#6D6C68', es=gr.m.map(g=>g.it.e), hasC=es.some(e=>e.anyConf), hasS=es.some(e=>e.id===sel);
        parts.push(`<g class="mk" data-c="${ci}">${hasS?`<circle cx="${gr.x}" cy="${cy}" r="14" fill="none" stroke="#991B1B" stroke-width="1.5"/>`:''}<circle cx="${gr.x}" cy="${cy}" r="10.5" fill="#fff" stroke="${c}" stroke-width="2"/><text x="${gr.x}" y="${cy+4.2}" text-anchor="middle" font-size="12" font-weight="700" fill="${c}">${gr.m.length}</text>${hasC?`<circle cx="${gr.x+8.6}" cy="${cy-8.6}" r="3.5" fill="#F2A50C"/>`:''}</g>`);
        es.forEach(e=>TL.pos[e.id]={x:gr.x,y:cy,r:11}); const prevEnd=lastEnd; lastEnd=gr.x1;
        { const room=nextX-gr.x1-14, same=new Set(es.map(e=>dateLabel(e))).size===1, lab=`${es.length} 件${same?' · '+dateLabel(es[0]):''}`;
          const lroom=gr.x0-prevEnd-14;
          if(room>40){ const tx=trunc(lab,room,12); parts.push(`<text x="${gr.x1+7}" y="${cy+4.5}" font-size="12" fill="#8A8986" pointer-events="none">${esc(tx)}</text>`); lastEnd=gr.x1+7+textW(tx,12); }
          else if(!isRT && lroom>60 && gr.x0-7<=LW+PW-2){ const tx=trunc(lab,lroom,12); parts.push(`<text x="${gr.x0-7}" y="${cy+4.5}" text-anchor="end" font-size="12" fill="#8A8986" pointer-events="none">${esc(tx)}</text>`); lastEnd=gr.x1; } }
      } else {
        const g=gr.m[0], it=g.it;
        parts.push(drawItem(g,cy,sel,l));
        const label=it.c?`${it.c.who}主张：${it.c.title}`: it.r? it.r.raw : it.e.conflict? `${it.e.title} · ${new Set(it.e.strict.map(r=>recIv(r).join())).size} 种说法` : it.e.title;
        const inside = g.kind==='aband' && (g.x1-g.x0)>textW(label,11.5)+14;
        if(inside) parts.push(`<text x="${g.x0+8}" y="${cy+4}" font-size="11.5" fill="#1A1A1A" pointer-events="none">${esc(label)}</text>`);
        else { const room=nextX-g.x1-14, lroom=g.x0-lastEnd-14; lastEnd=g.x1;
          const lsh=isRT?24:0;
          if(room<=40 && lroom-lsh>60 && g.x0-7<=LW+PW-2 && g.x1>LW){ const strong=it.e&&it.e.key&&!it.r; parts.push(`<text x="${g.x0-7-lsh}" y="${cy+4.5}" text-anchor="end" font-size="12.5" ${strong?'font-weight="600" fill="#991B1B"':'fill="#555452"'} pointer-events="none">${esc(trunc(label,lroom-lsh,strong?13.6:12.5))}</text>`); }
          else if(room>40){ const strong=it.e&&it.e.key&&!it.r, tx=trunc(label,room,strong?13.6:12.5); parts.push(`<text x="${g.x1+7}" y="${cy+4.5}" font-size="12.5" ${strong?'font-weight="600" fill="#991B1B"':'fill="#555452"'} pointer-events="none">${esc(tx)}</text>`); lastEnd=g.x1+7+textW(tx,strong?13.6:12.5); } }
        if(it.e) TL.pos[it.e.id]=TL.pos[it.e.id]||{x:g.x0!=null&&g.kind!=='pt'?g.x0:g.x,y:cy,r:g.kind==='pt'?8:5};
      }
    });
    parts.push(`</g>`);
    Object.values(TL.pos).forEach(p=>{ if(p.top===undefined && p.y>=top && p.y<=top+l.h){ p.top=top; p.bot=top+l.h; } });
    y+=l.h;
  });
  if(S.showRel){ const arrows=[]; RELATED.forEach(([a,b,t])=>{ const pa=TL.pos[a], pb=TL.pos[b]; if(!pa||!pb) return;
      const d=relRoute(pa,pb); if(!d) return;
      arrows.push(`<path d="${d}" fill="none" stroke="#8E8C87" stroke-width="1.2" stroke-linejoin="round" marker-end="url(#arr)"><title>${t}（材料写明的指向）</title></path>`); });
    parts.push(`<g clip-path="url(#clip)" pointer-events="stroke">${arrows.join('')}</g>`); }
  host.innerHTML=`<svg width="${W}" height="${H}" id="tlsvg">${parts.join('')}</svg>`;
  TL.clusters=clusters; bindTimeline(); drawMini(evs); bindGaps(); renderVState(); { const rg=$('#rng'); if(rg) rg.textContent=rangeLabel(); const full=S.t0<=EXT[0]+.5&&S.t1>=EXT[1]-.5; ['#zout','#bfit'].forEach(q=>{ const b=$(q); if(b) b.disabled=full; }); }
}
function bindGaps(){ const svg=$('#tlsvg'); svg.querySelectorAll('.gap').forEach(r=>{ r.addEventListener('mousemove',ev=>{ const tip=$('#gaptip'); tip.textContent=`${r.dataset.gap} 个月无事实`; tip.style.display='block'; tip.style.left=(ev.clientX+10)+'px'; tip.style.top=(ev.clientY-30)+'px'; }); r.addEventListener('mouseleave',()=>$('#gaptip').style.display='none'); }); }
/* 关联连线：正交走线、小圆角；沿泳道分隔线走，最后一段水平进入目标，箭头前留足直段 */
const REL={R:3.5,ARR:8,STUB:16};
function roundedPath(pts,r){
  const P=[pts[0]]; pts.slice(1).forEach(p=>{ const q=P[P.length-1]; if(Math.abs(p[0]-q[0])>.01||Math.abs(p[1]-q[1])>.01) P.push(p); });
  let d=`M${P[0][0].toFixed(1)} ${P[0][1].toFixed(1)}`;
  for(let i=1;i<P.length-1;i++){ const a=P[i-1], b=P[i], c=P[i+1];
    const l1=Math.hypot(b[0]-a[0],b[1]-a[1]), l2=Math.hypot(c[0]-b[0],c[1]-b[1]); if(l1<.01||l2<.01) continue;
    const u=[(b[0]-a[0])/l1,(b[1]-a[1])/l1], v=[(c[0]-b[0])/l2,(c[1]-b[1])/l2], cr=u[0]*v[1]-u[1]*v[0];
    if(Math.abs(cr)<1e-6) continue; const rr=Math.min(r,l1/2,l2/2);
    d+=` L${(b[0]-u[0]*rr).toFixed(1)} ${(b[1]-u[1]*rr).toFixed(1)} A${rr} ${rr} 0 0 ${cr>0?1:0} ${(b[0]+v[0]*rr).toFixed(1)} ${(b[1]+v[1]*rr).toFixed(1)}`; }
  const z=P[P.length-1]; return d+` L${z[0].toFixed(1)} ${z[1].toFixed(1)}`;
}
function relRoute(pa,pb){
  const {R,ARR,STUB}=REL, ra=pa.r||8, rb=pb.r||8;
  const ex=pb.x-rb-ARR, mx=ex-STUB;               /* 箭头底边、最后一个拐点 */
  const down=pb.y>pa.y+2;
  /* 走在目标泳道的上边线（目标在下方或同一泳道），或下边线（目标在上方） */
  const gy = pb.y<pa.y-2 ? (pb.bot!==undefined?pb.bot:pb.y+17)-.5 : (pb.top!==undefined?pb.top:pb.y-17)+.5;
  const sy = pa.y + (gy>pa.y?ra:-ra);
  const pts=[[pa.x,sy],[pa.x,gy],[mx,gy],[mx,pb.y],[ex,pb.y]];
  if(Math.abs(mx-pa.x)<2*R+2){ pts.splice(1,3,[pa.x,pb.y]); }
  return roundedPath(pts,R);
}
function stateMark(e,x,y,r,c){
  /* 照原版图例：待审 = 浅填充加同色描边；已确认 = 实心；有争议 = 带斜线的圈；大致日期 = 菱形；把握较低 = 记号缩小 */
  if(e.est||e.stmtOnly) r=r*.78;
  const done=e.rev==='done', fill=done?c:tint(c,.42), st=done?'':`stroke="${c}" stroke-width="1.6"`;
  if(e.disp==='有争议') return `<circle cx="${x}" cy="${y}" r="${r-.3}" fill="${tint(c,.42)}" stroke="${c}" stroke-width="1.6"/><path d="M${x-r*.62} ${y+r*.62} L${x+r*.62} ${y-r*.62}" stroke="${c}" stroke-width="1.6"/>`;
  if(e.est){ const k=r*1.18; return `<path d="M${x} ${y-k} L${x+k} ${y} L${x} ${y+k} L${x-k} ${y} Z" fill="${fill}" ${st}/>`; }
  return `<circle cx="${x}" cy="${y}" r="${done?r:r-.3}" fill="${fill}" ${st}/>`;
}
function badge(e,x,y){ return ''; }
function drawItem(g,cy,sel,lane){
  const it=g.it;
  if(it.c) return `<g class="mk" data-claim="${it.c.id}"><rect x="${g.x-6}" y="${cy-6}" width="12" height="12" rx="1" fill="#fff" stroke="#6D6C68" stroke-width="1.6"/></g>`;
  const e=it.e, c=TYPES[e.t].c, isSel=sel===e.id;
  if(it.r){
    const r=it.r, k=dKind(r.d);
    const body = g.kind==='rband' ? `<rect x="${g.x0}" y="${cy-7}" width="${Math.max(8,g.x1-g.x0)}" height="14" rx="7" fill="${tint(c,.25)}" stroke="${c}" stroke-width="1.3" stroke-dasharray="2.5 1.8"/>`
      : shapeAt(k,g.x,cy,5.6, e.state==='agr'||r.inf?'#fff':tint(c,.5), c, r.inf||e.state==='agr');
    return `<g class="mk" data-e="${e.id}" data-r="${r.rid}">${isSel?`<circle cx="${g.x}" cy="${cy}" r="12" fill="none" stroke="#991B1B" stroke-width="1.5"/>`:''}<circle cx="${g.x}" cy="${cy}" r="11" fill="transparent"/>${body}${e.conflict?`<circle cx="${g.x+6}" cy="${cy-6}" r="3.3" fill="#F2A50C"/>`:''}</g>`;
  }
  if(g.kind==='cband'){
    const w=Math.max(18,g.x1-g.x0);
    if(w<34){ // 缩放不够时，像官方一样收成一个点 + 冲突橙点；放大后才展开成各记载的刻度
      const x=(g.x0+g.x1)/2, r=e.key?7.5:6.2;
      return `<g class="mk" data-e="${e.id}">${isSel?`<circle cx="${x}" cy="${cy}" r="${r+4.5}" fill="none" stroke="#991B1B" stroke-width="1.5"/>`:''}<circle cx="${x}" cy="${cy}" r="${r+6}" fill="transparent"/><circle cx="${x}" cy="${cy}" r="${r-.3}" fill="${tint(c,.42)}" stroke="${c}" stroke-width="1.6"/><circle cx="${x+r*.78}" cy="${cy-r*.78}" r="3.5" fill="#F2A50C"/>${badge(e,x-r*.8,cy-r*.8)}</g>`;
    }
    let s=`<g class="mk" data-e="${e.id}">${isSel?`<rect x="${g.x0-3}" y="${cy-12}" width="${w+6}" height="24" rx="12" fill="none" stroke="#991B1B" stroke-width="1.5"/>`:''}<rect x="${g.x0}" y="${cy-9}" width="${w}" height="18" rx="9" fill="#FAEED3"/>`;
    e.strict.forEach(r=>{ const iv=recIv(r), X=TL.X; if(iv[0]===iv[1]) s+=shapeAt(dKind(r.d),X(iv[0]+.5),cy,4.2,'#fff','#5F5E5A',!!r.inf); else s+=`<rect x="${X(iv[0])}" y="${cy-4}" width="${Math.max(5,X(iv[1]+1)-X(iv[0]))}" height="8" rx="4" fill="#fff" stroke="#5F5E5A" stroke-width="1.1" stroke-dasharray="2 1.5"/>`; });
    s+=`<circle cx="${g.x0+w-2}" cy="${cy-9}" r="3.5" fill="#F2A50C"/>`+badge(e,g.x0+2,cy-9)+'</g>'; return s;
  }
  if(g.kind==='aband'){
    const w=Math.max(12,g.x1-g.x0);
    return `<g class="mk" data-e="${e.id}">${isSel?`<rect x="${g.x0-3}" y="${cy-11}" width="${w+6}" height="22" rx="11" fill="none" stroke="#991B1B" stroke-width="1.5"/>`:''}<rect x="${g.x0}" y="${cy-8}" width="${w}" height="16" rx="8" fill="${tint(c,.3)}" stroke="${c}" stroke-width="1.3" stroke-dasharray="3 2"/>${badge(e,g.x0+2,cy-8)}</g>`;
  }
  const r=e.key?7.5:6.2;
  if(e.conflict){ const x=g.x; return `<g class="mk" data-e="${e.id}">${isSel?`<circle cx="${x}" cy="${cy}" r="${r+4.5}" fill="none" stroke="#991B1B" stroke-width="1.5"/>`:''}<circle cx="${x}" cy="${cy}" r="${r+6}" fill="transparent"/><circle cx="${x}" cy="${cy}" r="${r-.3}" fill="${tint(c,.42)}" stroke="${c}" stroke-width="1.6"/><circle cx="${x+r*.78}" cy="${cy-r*.78}" r="3.5" fill="#F2A50C"/>${badge(e,x-r*.8,cy-r*.8)}</g>`; }
  return `<g class="mk" data-e="${e.id}">${isSel?`<circle cx="${g.x}" cy="${cy}" r="${r+4.5}" fill="none" stroke="#991B1B" stroke-width="1.5"/>`:''}<circle cx="${g.x}" cy="${cy}" r="${r+6}" fill="transparent"/>${stateMark(e,g.x,cy,r,c)}${e.amtConflict?`<circle cx="${g.x+r*.78}" cy="${cy-r*.78}" r="3.5" fill="#F2A50C"/>`:''}${e.wasConflict&&e.adopted?`<circle cx="${g.x}" cy="${cy}" r="${r+2.6}" fill="none" stroke="#F2A50C" stroke-width="1" stroke-dasharray="1.5 2"/>`:''}${badge(e,g.x-r*.8,cy-r*.8)}</g>`;
}
function drawSpan(s,yy,X,sel){
  const it=s.it, e=it.e, c=TYPES[e.t].c, isSel=sel===e.id, lab=spanLabel(it);
  let body='';
  if(s.sub==='c'){
    const w=s.b-s.a; body=`<rect x="${s.a-6}" y="${yy-9}" width="${w+12}" height="18" rx="9" fill="#FAEED3"/><line x1="${s.a}" x2="${s.b}" y1="${yy}" y2="${yy}" stroke="#D9B66C" stroke-width="1"/>`;
    e.strict.forEach(r=>{ const iv=recIv(r); if(iv[0]===iv[1]) body+=shapeAt(dKind(r.d),X(iv[0]+.5),yy,4.4,'#fff','#4F4E4A',!!r.inf); else { const xa=X(iv[0]), xb=X(iv[1]+1); body+=`<path d="M${xa} ${yy-4} V${yy+4} M${xa} ${yy} H${xb} M${xb} ${yy-4} V${yy+4}" stroke="#4F4E4A" stroke-width="1.3" fill="none" stroke-dasharray="${''}"/>`; } });
    body+=`<circle cx="${s.b+4}" cy="${yy-8}" r="3.5" fill="#F2A50C"/>`;
    const ring=isSel?`<rect x="${s.a-9}" y="${yy-12}" width="${w+18}" height="24" rx="12" fill="none" stroke="#991B1B" stroke-width="1.5"/>`:'';
    const room=LW+TL.PW-Math.max(s.a-6,LW)-4;
    return `<g class="mk" data-e="${e.id}">${ring}${body}${badge(e,s.a-4,yy-8)}</g>${room>30?`<text x="${Math.max(s.a-6,LW+2)}" y="${yy+16}" font-size="11" fill="#1A1A1A" font-weight="${e.key?600:400}" pointer-events="none">${esc(trunc(lab,room,e.key?12.6:11.5))}</text>`:''}`;
  }
  if(s.sub==='a'){
    const w=Math.max(12,s.b-s.a), inside=w>textW(e.title,11.5)+16;
    const ring=isSel?`<rect x="${s.a-4}" y="${yy-11}" width="${w+8}" height="22" rx="11" fill="none" stroke="#991B1B" stroke-width="1.5"/>`:'';
    return `<g class="mk" data-e="${e.id}">${ring}<rect x="${s.a}" y="${yy-8}" width="${w}" height="16" rx="8" fill="${tint(c,.3)}" stroke="${c}" stroke-width="1.3" stroke-dasharray="3 2"/>${badge(e,s.a+2,yy-8)}</g>`+
      (()=>{ const t=`${e.title}${e.main.p==='month'?'（仅到月）':'（大致时间）'}`, room=LW+TL.PW-Math.max(s.a,LW)-6; if(inside) return `<text x="${s.a+8}" y="${yy+4}" font-size="11.5" fill="#1A1A1A" pointer-events="none">${esc(trunc(e.title,Math.min(w-16,room),11.5))}</text>`; return room>30?`<text x="${Math.max(s.a,LW+2)}" y="${yy+16}" font-size="11" fill="#1A1A1A" pointer-events="none">${esc(trunc(t,room,11.5))}</text>`:''; })();
  }
  if(it.r){ const r=it.r; body = r.p==='range' ? `<rect x="${s.a}" y="${yy-2.5}" width="${Math.max(6,s.b-s.a)}" height="5" rx="2.5" fill="${r.inf?'#fff':c}" stroke="${c}" ${r.inf?'stroke-dasharray="2.5 1.8"':'stroke-width="0"'}/>` : `<rect x="${s.a}" y="${yy-7}" width="${Math.max(6,s.b-s.a)}" height="14" rx="7" fill="${tint(c,.3)}" stroke="${c}" stroke-width="1.3" stroke-dasharray="3 2"/>`; }
  else if(e.main && e.main.p==='arange') body=`<rect x="${s.a}" y="${yy-7}" width="${Math.max(6,s.b-s.a)}" height="14" rx="7" fill="${tint(c,.3)}" stroke="${c}" stroke-width="1.3" stroke-dasharray="3 2"/>`;
  else { const a=X(e.main.lo), b=X(e.main.hi+1);
    body = e.state==='agr' ? `<rect x="${a}" y="${yy-3}" width="${Math.max(6,b-a)}" height="6" rx="3" fill="#fff" stroke="${c}" stroke-width="1.4"/>` : `<rect x="${a}" y="${yy-2.5}" width="${Math.max(6,b-a)}" height="5" rx="2.5" fill="${e.certain?c:tint(c,.55)}"/>`;
    if(e.tail){ const ta=X(e.tail.lo), tb=X(e.tail.hi+1); body+=`<rect x="${ta}" y="${yy-7}" width="${Math.max(8,tb-ta)}" height="14" rx="7" fill="#FAEED3"/>`; const tk=[]; e.strict.forEach(r=>{ const x=X(dn(r.e)+.5), k=tk.find(t=>Math.abs(t.x-x)<3); if(k){ k.inf=k.inf&&!!r.inf; } else tk.push({x,inf:!!r.inf}); });
      tk.forEach(t=>{ body+=`<line x1="${t.x}" x2="${t.x}" y1="${yy-4.5}" y2="${yy+4.5}" stroke="#8A5A06" stroke-width="1.5" stroke-linecap="round" ${t.inf?'stroke-dasharray="1.6 1.6"':''}/>`; }); body+=`<circle cx="${tb}" cy="${yy-7}" r="3.3" fill="#F2A50C"/>`; } }
  const ring=isSel?`<rect x="${s.a-4}" y="${yy-9}" width="${s.b-s.a+8}" height="18" rx="9" fill="none" stroke="#991B1B" stroke-width="1.5"/>`:'';
  const room=LW+TL.PW-Math.max(s.a,LW)-4;
  return `<g class="mk" data-e="${e.id}">${ring}${body}${!it.r?badge(e,s.a,yy-4):''}</g>${room>30?`<text x="${Math.max(s.a,LW+2)}" y="${yy+15}" font-size="11" fill="#1A1A1A" pointer-events="none">${esc(trunc(lab,room,11.5))}</text>`:''}`;
}
/* ---------- 事实表 ---------- */
const hay = e => e.title+e.recs.map(r=>r.q+r.raw+r.d+DOC[r.d].sub+DOC[r.d].name+(r.amt!=null?fmtAmt(r.amt):'')).join('');
/* =====================================================================
   对照矩阵：证据 × 比异同
   ===================================================================== */
function drawMatrix(){
  const pane=$('#pane'); let docs=DOCS.filter(d=>docVisible(d.id));
  let rows=derive().filter(e=>new Set(e.recs.map(r=>r.d)).size>1 || e.wasConflict || e.amtConflict);
  if(S.matrixConf) rows=rows.filter(e=>e.wasConflict||e.amtConflict||(e.amtVals&&e.amtVals.length>1));
  const letters='一二三四五六七八九';
  const used=new Set(rows.flatMap(e=>e.recs.map(r=>r.d))); const allDocs=docs.length; docs=docs.filter(d=>used.has(d.id)); const omitted=allDocs-docs.length;
  pane.innerHTML=`<div class="mxbar"><b>同一件事，各份材料怎么说</b><span class="hsp"></span><label class="tg"><input type="checkbox" ${S.matrixConf?'checked':''} onchange="S.matrixConf=this.checked;drawMatrix()">只看记载不一的</label></div>
  <div class="mxwrap"><table class="mx" style="width:${240+docs.length*230}px"><thead><tr><th class="mxh">事实</th>${docs.map(d=>`<th><div class="mxd">${kindTag(d.id)} ${d.id}</div><div class="sub">${esc(docShort(d.id))}</div></th>`).join('')}</tr></thead><tbody>
  ${rows.map(e=>{
    const groups={}; let gi=0; e.strict.forEach(r=>{ const k=recIv(r).join(); if(!(k in groups)) groups[k]=letters[gi++]||'?'; });
    const diff=e.wasConflict||e.amtConflict||(e.amtVals&&e.amtVals.length>1);
    const gap=[e.wasConflict?`相差 ${e.spread} 天`:'', (e.amtVals&&e.amtVals.length>1)?`相差 ${fmtAmt(Math.max(...e.amtVals)-Math.min(...e.amtVals))}`:''].filter(Boolean).join('；');
    return `<tr><td class="mxf" onclick="selectEv('${e.id}')"><div class="t"><span class="dot" style="background:${TYPES[e.t].c}"></span>${esc(e.title)}</div><div class="sub">${diff?`<span class="mxgap">${gap||'记载不一'}</span>`:dateLabel(e)}</div></td>
    ${docs.map(d=>{ const rs=e.recs.filter(r=>r.d===d.id); if(!rs.length) return '<td class="na"></td>';
      return `<td class="${diff?'diff':''}">${rs.map(r=>{ const iv=recIv(r); const g=iv&&e.wasConflict?groups[iv.join()]:''; const ga=(e.amtVals&&e.amtVals.length>1&&r.amt!=null)?letters[e.amtVals.indexOf(+r.amt)]:''; return `<div class="cell ${e.adopted===r.rid?'ad':''}" onclick="openDoc('${r.d}','${r.rid}')">${g?`<span class="grp">说法${g}</span>`:''}${ga?`<span class="grp amt">金额说法${ga}</span>`:''}<b>${esc(r.raw)}</b>${r.amt!=null?` · <b>${fmtAmt(r.amt)}</b>`:''}${r.inf?' <span class="inf">推</span>':''}${e.adopted===r.rid?' <span class="tag blue">已采信</span>':''}<div class="qq">${esc(r.q)}</div></div>`; }).join('')}</td>`; }).join('')}
</tr>`; }).join('')}
  </tbody></table></div>
  `;
}

/* =====================================================================
   抽屉
   ===================================================================== */
function pushD(d){ S.dStack=S.dStack||[]; if(S.drawer && JSON.stringify(S.drawer)!==JSON.stringify(d)){ S.dStack.push(S.drawer); if(S.dStack.length>30) S.dStack.shift(); } S.drawer=d; }
function openDrawer(d){ pushD(d); render(); }
function closeDrawer(){ S.drawer=null; S.dStack=[]; S.selected=null; render(); }
function backDrawer(){ S.drawer=(S.dStack||[]).pop()||null; S.selected=S.drawer&&S.drawer.kind==='fact'?S.drawer.id:null; render(); }
const DLAB={review:'待审',fact:'事实',doc:'原文',claim:'主张',log:'变更记录'};
function openReview(f){ S.rfilter=f||'all'; openDrawer({kind:'review'}); }
function openClaim(id){ openDrawer({kind:'claim',id}); }
function selectEv(id,fromTable){
  S.selected=id; pushD({kind:'fact',id}); if(S.tab!=='tl'){ S.tab='tl'; } render();
  const e=derive().find(x=>x.id===id); if(e && !e.undated && (e.sortKey<S.t0||e.sortKey>S.t1)){ const sp=S.t1-S.t0; S.t0=e.sortKey-sp/2; S.t1=e.sortKey+sp/2; clampView(); drawTimeline(); }
  /* 不自动滚页面：图上点了什么，下面表格对应的行已标亮，页面位置保持不动 */
}
function openDoc(d,rid){ pushD({kind:'doc',d,rid}); render(); setTimeout(()=>{ const m=document.querySelector('#drawerIn .hit'), b=document.querySelector('#drawerIn .dbody'); if(m&&b) b.scrollTop=m.offsetTop-b.offsetTop-b.clientHeight/3; },30); }
function renderDrawer(){
  const sh=$('#shell'), inn=$('#drawerIn');
  if(!S.drawer){ sh.classList.remove('drawer-open'); inn.innerHTML=''; return; }
  sh.classList.add('drawer-open'); const d=S.drawer;
  inn.innerHTML = d.kind==='review'?drawerReview(): d.kind==='fact'?drawerFact(d.id): d.kind==='doc'?drawerDoc(d.d,d.rid): d.kind==='claim'?drawerClaim(d.id): drawerLog();
  const st=S.dStack||[]; if(st.length){ const h=inn.querySelector('.dhead'); if(h) h.insertAdjacentHTML('afterbegin',`<button class="dback" onclick="backDrawer()" title="返回上一层（Esc）"><svg class="ic" viewBox="0 0 16 16"><path d="M10 3.5 5.5 8l4.5 4.5"/></svg>${DLAB[st[st.length-1].kind]||'返回'}</button>`); }
}
function q(s,showDoc=true,loc){
  return `${showDoc?`<div class="srchead">${kindTag(s.d)}<button class="dref" onclick="openDoc('${s.d}','${s.rid||''}')">${s.d}</button><span class="nm">${esc(loc||s.loc)}</span></div>`:''}<div class="q">${esc(s.q)}</div>${(s.qx||[]).map(x=>`<div class="q qx">${esc(x)}</div>`).join('')}`;
}
function drawerReview(){
  const items=reviewItems(), cnt={}; let total=0; items.forEach(it=>{ const n=itemCount(it); cnt[it.k]=(cnt[it.k]||0)+n; total+=n; });
  const chips=[['all','全部',total],['conflict','日期冲突',cnt.conflict||0],['amount','金额冲突',cnt.amount||0],['dup','疑似重复',cnt.dup||0],['arith','数字对不上',cnt.arith||0],['pack',PACK.n+'规则',cnt.pack||0],['infer','推断日期',cnt.infer||0],['suspect','可疑日期',cnt.suspect||0],['np','仅有陈述',cnt.np||0],['att','需留意',cnt.att||0]];
  const list=items.filter(it=>S.rfilter==='all'||it.k===S.rfilter);
  const done=resolvedList().filter(x=>S.rfilter==='all'||x.k===S.rfilter);
  const evs=derive(), E=Object.fromEntries(evs.map(e=>[e.id,e]));
  const rel=`<details class="rel"><summary>${RELATED.length} 组材料写明了指向的事实</summary>${RELATED.map(([a,b,t])=>E[a]&&E[b]?`<div class="relrow"><button class="dref" onclick="selectEv('${a}')">${esc(E[a].title)}</button><span>→</span><button class="dref" onclick="selectEv('${b}')">${esc(E[b].title)}</button><span class="sub">${t}</span></div>`:'').join('')}</details>`;
  return `<div class="dhead"><span>待审</span><button class="x" onclick="closeDrawer()">×</button></div>
  <div class="dbody"><div class="chips">${chips.filter(([k,n,c])=>k==='all'||c>0||S.rfilter===k).map(([k,n,c])=>`<button class="chip ${S.rfilter===k?'on':''}" onclick="S.rfilter='${k}';renderDrawer()">${n}<span class="c">${c}</span></button>`).join('')}</div>
  ${S.phase!=='ready'?'<div class="empty">比对完成后出现待审项</div>':list.map(it=>`<div class="rcard">${card(it)}</div>`).join('')||'<div class="empty">这一类没有待审项</div>'}
  ${done.length?`<div class="sec">已处理 ${done.length}</div>${done.map(x=>`<div class="resolved"><span>${RK[x.k]} · ${esc(x.t)}：<b>${esc(x.label)}</b></span><button class="lnk" onclick="${x.undo}">撤销</button></div>`).join('')}`:''}
  ${S.phase==='ready'?rel:''}</div>`;
}
function resolvedList(){
  const out=[];
  Object.entries(S.dupRes).forEach(([id,v])=>{ const g=dupGroups(true).find(x=>x.id===id); out.push({k:'dup',t:g?g.fids.map(f=>FACT[f].title).join(' / '):id,label:v==='merge'?'已合并为一个事实':'确认是不同的事，分开',undo:`delete S.dupRes['${id}'];logIt(null,'撤销疑似重复处理','');render()`}); });
  Object.keys(S.arithRes).forEach(id=>out.push({k:'arith',t:id.split(':')[1],label:'已知悉',undo:`delete S.arithRes['${id}'];render()`}));
  Object.entries(S.adopt).forEach(([fid,rid])=>out.push({k:'conflict',t:FACT[fid].title,label:`采信 ${REC[rid].d}「${REC[rid].raw}」`,undo:`unAdopt('${fid}')`}));
  Object.entries(S.cres).forEach(([fid,v])=>out.push({k:'conflict',t:FACT[fid].title,label:v==='split'?'不是同一件事，已拆开':'其中一条只是约定，保留全部',undo:`delete S.cres['${fid}'];render()`}));
  Object.entries(S.inferOk).forEach(([k,v])=>out.push({k:'infer',t:INFER[k].n,label:v==='ok'?'确认推断':'改为无日期',undo:`delete S.inferOk['${k}'];render()`}));
  Object.entries(S.susRes).forEach(([rid,v])=>out.push({k:'suspect',t:REC[rid].raw,label:v==='typo'?'按笔误处理，不生成事实':'生成为独立事实',undo:`delete S.susRes['${rid}'];render()`}));
  if(S.aside.size) out.push({k:'np',t:'仅有当事人陈述',label:`暂置 ${S.aside.size} 条`,undo:'S.aside.clear();render()'});
  Object.keys(S.attnRes).forEach(id=>out.push({k:'att',t:ATTN.find(a=>a.id===id).title,label:'已知悉',undo:`delete S.attnRes['${id}'];render()`}));
  Object.keys(S.packRes).forEach(id=>out.push({k:'pack',t:id.split(':')[1],label:'已知悉',undo:`delete S.packRes['${id}'];render()`}));
  return out;
}
function card(it){
  if(it.k==='conflict'){
    const e=it.e, c={ctx:e.f.ctx,note:e.f.cnote};
    const recs=e.strict.concat(e.recs.filter(r=>r.p==='none'||r.loose));
    const days = e.kind==='range' ? e.strict.map(r=>`${r.d} ${dn(r.e)-dn(r.s)+1} 天`).join('；') : null;
    return `<div class="rk">日期冲突</div><div class="rt">${esc(e.title)}${e.key?' <span style="color:#C98A16">★</span>':''}</div>
     ${(()=>{ const G={}; let gi=0; e.strict.forEach(r=>{ const k=recIv(r).join(); if(!(k in G)) G[k]='一二三四五六七八九'[gi++]||'?'; }); e._G=G; return ''; })()}
     ${recs.map(r=>`<div class="cand"><div class="d">${r.p!=='none'&&!r.loose&&e._G[recIv(r).join()]?`<span class="grp">说法${e._G[recIv(r).join()]}</span> `:''}${esc(r.raw)}</div>${q(r)}${r.inf?`<div class="sub">推断：${esc(INFER[r.inf].basis)}</div>`:''}${r.p!=='none'&&!r.loose?`<button class="btn" style="margin-top:6px" onclick="adopt('${e.f.id}','${r.rid}')">采信此记载</button>`:'<div class="sub">无确切日期，不参与比对</div>'}</div>`).join('')}
     ${e.amtConflict?'<div class="warn">该事实金额也记载不一。采信一条记载会同时采用它的日期和金额。</div>':''}
     <div class="calc">各记载最多相差 ${e.spread} 天${days?`；按各记载计停工天数：${days}`:''}。${c.note||''}</div>
     ${(c.ctx||[]).length?`<div class="sub" style="margin-top:6px">材料中的相关记载（仅供对照，不作判断）</div>${c.ctx.map(s=>`<div class="ctx"><b>${s.d}</b> ${esc(s.loc)}：${esc(s.q)}</div>`).join('')}`:''}
     <div class="ra"><button class="lnk" onclick="cres('${e.f.id}','planned')">其中一条只是约定</button><button class="lnk" onclick="cres('${e.f.id}','split')">不是同一件事，拆开</button><button class="lnk" onclick="S.tab='matrix';S.matrixConf=true;render()">去对照矩阵 →</button></div>`;
  }
  if(it.k==='amount'){ const e=it.e;
    return `<div class="rk">金额冲突</div><div class="rt">${esc(e.title)}</div>
     ${e.recs.filter(r=>r.amt!=null).map(r=>`<div class="cand"><div class="d"><span class="grp">说法${'一二三四五六七八九'[e.amtVals.indexOf(+r.amt)]}</span> ${fmtAmt(r.amt)}</div>${q(r)}<button class="btn" style="margin-top:6px" onclick="adopt('${e.f.id}','${r.rid}')">采信此记载</button></div>`).join('')}
     <div class="calc">各记载金额最多相差 ${fmtAmt(Math.max(...e.amtVals)-Math.min(...e.amtVals))}。</div>
     <div class="ra"><button class="lnk" onclick="cres('${e.f.id}','split')">不是同一笔，拆开</button></div>`; }
  if(it.k==='dup'){ const g=it.g, es=g.fids.map(fid=>derive().find(e=>e.f.id===fid)||null).filter(Boolean);
    const ds=new Set(es.map(e=>dateLabel(e)));
    return `<div class="rk">疑似重复</div><div class="rt">${es.length} 个事实可能是同一件事</div>
     ${es.map(e=>`<div class="cand"><div class="d">${dateLabel(e)}</div><div class="sub" style="font-weight:600;color:var(--ink)">${esc(e.title)}</div>${e.recs.map(r=>q(r)).join('')}</div>`).join('')}
     <div class="calc">${esc(g.why)}</div>
     ${ds.size>1?'<div class="warn">日期不同。合并后会出现日期冲突，由您裁决。</div>':''}
     <div class="ra"><button class="lnk" onclick="S.dupRes['${g.id}']='sep';logIt(null,'疑似重复：分开','${esc(es.map(e=>e.title).join(' / '))}');render()">分开</button><button class="btn" onclick="S.dupRes['${g.id}']='merge';logIt(null,'疑似重复：合并为一','${esc(es.map(e=>e.title).join(' / '))}');render()">合并为一</button></div>`; }
  if(it.k==='arith'){ const a=it.a;
    return `<div class="rk">数字对不上</div><div class="rt">${esc(a.title)}</div>${q({d:a.d,q:a.q,loc:a.loc})}
     <div class="calc">${esc(a.why)}</div><div class="sub" style="margin-top:6px">照原样列出，不修正。</div>
     <div class="ra"><button class="btn" onclick="S.arithRes['${a.id}']=1;logIt(null,'数字对不上：已知悉','${esc(a.title)}');render()">已知悉</button></div>`; }
  if(it.k==='pack'){ const r=it.rule;
    return `<div class="rk">${esc(PACK.n)}规则 · ${r.id}</div><div class="rt">${esc(r.title)}</div>
     ${it.fs.map(e=>`<div class="npr"><span><button class="dref" style="font-size:13px;text-decoration:none" onclick="selectEv('${e.id}')">${esc(e.title)}</button><br><span class="d">${dateLabel(e)}</span>${e.amt!=null?' · '+fmtAmt(e.amt):''}</span></div>`).join('')}
     <div class="calc">${esc(r.why)}${it.sum!=null?` 加总 ${fmtAmt(it.sum)}，对照 ${fmtAmt(it.total)}，相差 ${fmtAmt(Math.abs(it.sum-it.total))}。`:''}</div>
     <div class="ra"><button class="btn" onclick="S.packRes['${it.id}']=1;render()">已知悉</button></div>`; }
  if(it.k==='infer'){
    return `<div class="rk infk">推断日期 · ${INFER[it.key].n}</div><div class="rt">${it.fs.length} 个事实用到这一推断</div>
     ${it.fs.map(e=>`<div class="npr"><span><span class="d">${dateLabel(e)}</span>　${esc(e.title)}</span><button class="dref" onclick="selectEv('${e.id}')">查看</button></div>`).join('')}
     <div class="calc">${esc(INFER[it.key].basis)}</div>
     <div class="ra"><button class="lnk" onclick="S.inferOk['${it.key}']='undated';logIt(null,'推断改为无日期','${INFER[it.key].n}');render()">改为无日期</button><button class="btn" onclick="S.inferOk['${it.key}']='ok';logIt(null,'确认推断','${INFER[it.key].n}');render()">确认推断</button></div>`;
  }
  if(it.k==='suspect'){
    return `<div class="rk">可疑日期</div><div class="rt">${esc(it.f.title)}：「${esc(it.r.raw)}」</div>${q(it.r)}
     <div class="warn">${esc(it.r.susWhy||'该日期与同一材料的其他记载明显不合。')} 默认不按这个日期上时间线。</div>
     <div class="ra"><button class="lnk" onclick="S.susRes['${it.r.rid}']='event';logIt('${it.f.id}','可疑日期按原文上时间线','${esc(it.r.raw)}');render()">按原文上时间线</button><button class="btn" onclick="S.susRes['${it.r.rid}']='typo';logIt('${it.f.id}','可疑日期按笔误处理','${esc(it.r.raw)}');render()">按笔误处理</button></div>`;
  }
  if(it.k==='np'){
    return `<div class="rk np">仅有当事人陈述</div><div class="rt">${it.fs.length} 个事实只出自当事人陈述（起诉状、答辩状、情况说明等），未见书证、电子数据或证人证言</div>
     ${it.fs.map(e=>`<div class="npr"><span><button class="dref" style="font-size:13px;text-decoration:none" onclick="selectEv('${e.id}')">${esc(e.title)}</button><br><span class="d">${dateLabel(e)}</span> <span class="tag amber">陈述</span></span><button class="lnk" onclick="S.aside.add('${e.id}');render()">暂置一旁</button></div>`).join('')}
     <div class="ra"><button class="lnk" onclick="${it.fs.map(e=>`S.aside.add('${e.id}')`).join(';')};render()">全部暂置</button></div>`;
  }
  if(it.k==='att'){ const a=it.a;
    return `<div class="rk att">需留意</div><div class="rt">${esc(a.title)}</div>${q({d:a.d,q:a.q,loc:a.loc||''})}<div class="sub">${esc(a.why)}</div>${a.ctx.map(s=>`<div class="ctx"><b>${s.d}</b> ${esc(s.loc)}：${esc(s.q)}</div>`).join('')}
     <div class="ra"><button class="btn" onclick="S.attnRes['${a.id}']=1;render()">已知悉</button></div>`;
  }
}
function adopt(fid,rid){ if(!(fid in S.adopt)) S.revPrev[fid]=S.rev[fid]; S.adopt[fid]=rid; S.rev[fid]='done'; logIt(fid,'采信记载',`${REC[rid].d}「${REC[rid].raw}」`); toast(`已采信 ${REC[rid].d}「${REC[rid].raw}」，其余记载保留在底稿`); render(); }
function unAdopt(fid){ delete S.adopt[fid]; if(fid in S.revPrev){ if(S.revPrev[fid]===undefined) delete S.rev[fid]; else S.rev[fid]=S.revPrev[fid]; delete S.revPrev[fid]; } logIt(fid,'撤销采信',FACT[fid].title); render(); }
function cres(fid,v){ S.cres[fid]=v; logIt(fid,v==='split'?'拆为不同事实':'其中一条只是约定',FACT[fid].title); render(); }

function drawerFact(id){
  const e=derive().find(x=>x.id===id);
  if(!e) return `<div class="dhead"><span></span><button class="x" onclick="closeDrawer()">×</button></div><div class="dbody empty">该事实已拆分或不在当前时点</div>`;
  const fid=e.f.id;
  const rel=RELATED.filter(([a,b])=>a===fid||b===fid).map(([a,b,t])=>{ const o=a===fid?b:a; return `<div class="relrow"><span class="sub">${t}</span><button class="dref" onclick="selectEv('${o}')">${esc(FACT[o].title)}</button></div>`; }).join('');
  const hist=S.log.filter(l=>l.fid===fid);
  return `<div class="dhead"><span class="ed-type"><span class="dot" style="background:${TYPES[e.t].c}"></span>${TYPES[e.t].n} · ${fid}</span><button class="x" onclick="closeDrawer()">×</button></div>
  <div class="dbody">
   <div class="ed-title">${esc(e.title)}</div>
   <div class="ed-date">${dateLabel(e)} ${dateNote(e)?`<span class="sub" style="font-weight:400">· ${dateNote(e)}</span>`:''}</div>
   <div class="tags">${e.state==='agr'?'<span class="tag out">约定·应当发生（空心）</span>':''}${e.est?'<span class="tag out">推定（虚线）</span>':''}<span class="tag ${e.certain?'grey':'out'}">${e.certain?'确定':'未确定'}</span>${e.conflict?'<span class="tag conf">日期冲突</span>':''}${e.amtConflict?'<span class="tag conf">金额冲突</span>':''}${e.role?`<span class="tag grey">角色：${esc(e.role)}</span>`:''}${e.stmtOnly?'<span class="tag amber">仅有当事人陈述</span>':''}</div>
   <div class="ctrls">
    ${S.reviewLayer?`<span class="seg">${[['todo','待确认'],['done','已确认']].map(([v,n])=>`<button class="${e.rev===v?'on':''}" onclick="S.rev['${fid}']='${v}';logIt('${fid}','${n}','');render()">${n}</button>`).join('')}</span>`:''}
    <button class="star ${e.key?'on':''}" onclick="S.key['${fid}']=${e.key?0:1};logIt('${fid}','${e.key?'取消关键':'标为关键'}','');render()">${e.key?'★':'☆'} 关键事实</button>
   </div>
   <div class="kv"><span>争议</span><select class="sel" onchange="S.disp['${fid}']=this.value;logIt('${fid}','争议改为',this.value);render()">${['待定','无争议','有争议'].map(v=>`<option ${e.disp===v?'selected':''}>${v}</option>`).join('')}</select>
    <span>不利事实</span><label class="tg"><input type="checkbox" ${e.adverse?'checked':''} onchange="S.adverse['${fid}']=this.checked?'1':'';logIt('${fid}',this.checked?'标为不利（仅内部）':'取消不利标记','');render()"> 标为不利，仅内部可见</label></div>
   
   <div class="sec">对外措辞（按可靠度自动套固定措辞）</div>
   <div class="phr"><span class="tag grey">给客户</span> ${esc(phrase(e,'full'))}</div>
   <div class="phr"><span class="tag grey">给法官</span> ${esc(phrase(e,'doubt'))}</div>
   <div class="sec">记载 · ${e.recs.length} 条（一事多源）</div>
   ${e.recs.map(r=>`<div class="srcbox ${e.adopted===r.rid?'ad':''}">${q(r)}
     <div class="rmeta"><span>日期原文：<b>${esc(r.raw)}</b>（${{day:'确切日',month:'仅到月',approx:'大致时间',range:'区间',arange:'大致时段',none:'无日期'}[r.p]}）</span>
     ${r.amt!=null?`<span>金额：<b>${fmtAmt(r.amt)}</b></span>`:''}<span>来源：${KIND[dKind(r.d)].n}</span><span>程序确认：${dConf(r.d)}</span><span>出现时点：${STAGES[dStage(r.d)]}</span></div>
     ${r.inf?`<div class="sub">推断：${esc(INFER[r.inf].basis)}</div>`:''}
     <div class="ra" style="justify-content:flex-start">${(e.anyConf||e.adopted)&&(r.p!=='none'||r.amt!=null)&&!r.loose?(e.adopted===r.rid?`<span class="tag blue">已采信</span><button class="lnk" onclick="unAdopt('${fid}')">撤销</button>`:`<button class="btn" onclick="adopt('${fid}','${r.rid}')">采信此记载</button>`):''}<button class="lnk" onclick="openDoc('${r.d}','${r.rid}')">在原文中查看 →</button></div></div>`).join('')}
   ${e.act.length?`<div class="sec">涉及主体</div><div class="tags">${e.act.map(a=>`<span class="tag grey">${ACTORS[a]}</span>`).join('')}</div>`:''}
   ${rel?`<div class="sec">材料写明的指向</div>${rel}`:''}
   <div class="sec">变更记录</div>${hist.length?hist.map(l=>`<div class="relrow"><span class="sub" style="width:40px">${l.t}</span><span>${esc(l.what)} ${esc(l.detail)}</span></div>`).join(''):'<div class="sub">尚无</div>'}
  </div>`;
}
function drawerClaim(id){
  const c=CLAIMS.find(x=>x.id===id);
  return `<div class="dhead"><span class="ed-type"><span class="sqo"></span>主张 · ${c.who}</span><button class="x" onclick="closeDrawer()">×</button></div>
  <div class="dbody"><div class="ed-title">${esc(c.title)}</div><div class="tags"><span class="tag out">主张不是事实</span><span class="tag grey">立场：${c.who}</span></div>
  <div class="sec">原文</div><div class="srcbox">${q(c)}</div>
  <div class="sub" style="margin-top:10px">主张在时间轴上画方框，不与事实混排；进入结果计算模块时只作为对照，不作为计算依据。</div></div>`;
}
function drawerDoc(did,rid){
  const d=DOC[did]; const r=rid?REC[rid]:null; const qs=r?[r.q,...(r.qx||[])]:[];
  const evs=derive().filter(e=>e.recs.some(x=>x.d===did));
  const lines=d.lines.map(l=>{ const h=l.startsWith('#'); let t=esc(h?l.slice(1):l), hit=false; qs.forEach(x=>{ const ex=esc(x); if(t.includes(ex)){ t=t.replace(ex,`<mark>${ex}</mark>`); hit=true; } }); return `<div class="doc-l ${h?'h':''} ${hit?'hit':''}">${t}</div>`; }).join('');
  const back = 'closeDrawer()';
  return `<div class="dhead"><span>${d.id}　${esc(d.sub)}</span><button class="x" onclick="${back}" title="关闭">×</button></div>
  <div class="dbody"><div class="tags" style="margin-top:0">${kindTag(did)}<span class="tag out">${KIND[dKind(did)].n}</span>${d.date?`<span class="tag out wrap">文书日期 ${esc(d.date)}${d.dsrc?`（${esc(d.dsrc)}）`:''}</span>`:''}<span class="tag out">${dConf(did)}</span><span class="tag out">出现时点：${STAGES[dStage(did)]}</span><span class="tag out">${evs.length} 个事实</span></div>
   ${r?`<div class="sub" style="margin:10px 0 4px">高亮为「${esc(FACT[r.fid].title)}」所引原文</div>`:''}
   <div style="margin-top:8px">${lines}</div>
   <div class="sec">本份材料记载的事实</div><div class="tags">${evs.map(e=>`<button class="tchip" onclick="selectEv('${e.id}')"><span class="dot" style="background:${TYPES[e.t].c}"></span>${esc(trunc(e.title,170,12))}</button>`).join('')}</div></div>`;
}
function drawerLog(){
  return `<div class="dhead"><span>变更记录（全案）</span><button class="x" onclick="closeDrawer()">×</button></div><div class="dbody">
  <div class="sub" style="margin-bottom:10px">采信、拆分、确认推断、标注都记在这里，模型抽取的原始记载不被改写。</div>
  ${S.log.length?S.log.map(l=>`<div class="relrow"><span class="sub" style="width:40px">${l.t}</span><span><b>${esc(l.what)}</b>　${esc(l.detail)}${l.fid?` <button class="dref" onclick="selectEv('${l.fid}')">${l.fid}</button>`:''}</span></div>`).join(''):'<div class="empty">还没有记录</div>'}</div>`;
}

/* =====================================================================
   材料表 · 新建 · 生成演示
   ===================================================================== */
function viewDocs(){
  const evs=derive();
  return `<div class="hrow"><button class="back" onclick="go('work')">‹</button><h1 class="title">${esc(CASE.title)}</h1><span class="meta">${DOCS.length} 份材料</span></div>
  <div class="card" style="margin-top:14px">
   <div class="dtab"><span class="on">材料</span><span class="hsp"></span><label class="btn ghost">${ICO.add}添加材料<input type="file" multiple style="display:none" onchange="addToCase(this.files);this.value=''"></label>${(S.pend||[]).length?`<button class="btn dark" onclick="exportBase()">保存底稿：含 <span class="num">${S.pend.length}</span> 份待读材料</button>`:''}</div>
   <div style="padding:6px 16px 14px"><table class="docs"><thead><tr><th style="width:60px">编号</th><th>材料</th><th style="width:130px">证据种类</th><th style="width:150px">程序确认</th><th style="width:120px">出现时点</th><th style="width:170px">文书日期</th><th style="width:200px">读取</th><th style="width:50px"></th></tr></thead><tbody>
   ${DOCS.map((d,i)=>{ const n=evs.filter(e=>e.recs.some(r=>r.d===d.id)).length; const done=i<S.read;
     const pg=d.pages||1, rdp=d.read==null?pg:d.read;
     const cov=`<div class="sub">读了 ${rdp} / ${pg} 页${rdp<pg?` <span class="tag red">漏读 ${pg-rdp} 页</span>`:''}${d.medium==='image'?' <span class="tag amber">扫描件·未逐字核验</span>':''}</div>`;
     const rd=S.reading===i?'<span class="rd reading">正在读…</span>':done?`<span class="rd">${FACTS.reduce((a,f)=>a+f.recs.filter(r=>r.d===d.id).length,0)} 条记载</span><div class="sub">归入 ${n} 个事实</div>${cov}`:S.phase==='build'?'<span class="rd q">排队中</span>':'<span class="rd">尚未读取</span>';
     const ov=(k,v)=>`S.docOv['${d.id}']=Object.assign(S.docOv['${d.id}']||{},{${k}:${v}});logIt(null,'改材料属性','${d.id}');render()`;
     return `<tr><td><b>${d.id}</b></td><td>${esc(d.name)}${d.ext?esc(d.ext):''}<div class="sub">${esc(d.sub)} · ${esc(d.side)}</div></td>
     <td><select class="sel" onchange="${ov('kind','this.value')}">${Object.entries(KIND).map(([k,v])=>`<option value="${k}" ${dKind(d.id)===k?'selected':''}>${v.n}</option>`).join('')}</select></td>
     <td><select class="sel" onchange="${ov('confirm','this.value')}">${CONFIRM.map(c=>`<option ${dConf(d.id)===c?'selected':''}>${c}</option>`).join('')}</select></td>
     <td><select class="sel" onchange="${ov('stage','+this.value')}">${STAGES.map((s,j)=>`<option value="${j}" ${dStage(d.id)===j?'selected':''}>${s}</option>`).join('')}</select></td>
     <td>${esc(d.date)}<div class="sub">取自${d.dsrc}</div></td><td>${rd}</td><td><button class="lnk" onclick="openDoc('${d.id}')">打开</button>${S.docOv[d.id]?`<br><button class="lnk" onclick="delete S.docOv['${d.id}'];logIt(null,'材料属性恢复原状','${d.id}');render()">恢复原状</button>`:''}</td></tr>`; }).join('')}
   ${(S.pend||[]).map((f,i)=>`<tr class="pendrow"><td><b>${f.id}</b></td><td><span class="fx">${esc(f.ext)}</span> ${esc(f.name)}<div class="sub num">${fmtSize(f.size)}</div></td><td colspan="4"></td><td><span class="rd">尚未读取</span></td><td><button class="lnk" onclick="S.pend.splice(${i},1);render()">移除</button></td></tr>`).join('')}
   </tbody></table></div></div>`;
}
function switchCase(i){ loadCase(CASES[i]); render(); toast(`已打开：${CASE.title}`); }
function openFile(f){ if(!f) return; const rd=new FileReader(); rd.onload=()=>{ try{ const c=JSON.parse(rd.result); const v=validateCase(c); if(v.length){ alertBox(v); return; } CASES.push(c); loadCase(c); render(); toast(`已打开：${c.title}`); }catch(e){ alertBox(['不是有效的 JSON：'+e.message]); } }; rd.readAsText(f,'utf-8'); }
function alertBox(list){ toast('底稿有 '+list.length+' 处问题：'+list.slice(0,2).join('；')); }
/* 底稿校验：照录、编号、引用都要对得上（机检；导入时就拦） */
function validateCase(c){
  const errs=[]; const docs=Object.fromEntries((c.materials||[]).map(d=>[d.id,d]));
  if(!c.title) errs.push('缺案件名称');
  (c.facts||[]).forEach(f=>{ if(!f.id||!f.title) errs.push('事实缺编号或标题');
    (f.recs||[]).forEach((r,i)=>{ const d=docs[r.d]; if(!d){ errs.push(`${f.id} 第${i+1}条记载引用了不存在的材料 ${r.d}`); return; }
      if(r.q && !d.lines.some(l=>l.includes(r.q))) errs.push(`${f.id} 第${i+1}条记载的引语在 ${r.d} 原文里找不到（照录核验）`);
      (r.qx||[]).forEach(x=>{ if(!d.lines.some(l=>l.includes(x))) errs.push(`${f.id} 第${i+1}条记载的补充引语在 ${r.d} 原文里找不到（照录核验）`); });
      if(r.p && r.p!=='none' && !r.s) errs.push(`${f.id} 第${i+1}条记载缺日期`);
      if(r.raw && d.lines.some(l=>l.includes(r.raw)) && ![r.q,...(r.qx||[])].some(x=>x&&x.includes(r.raw))) errs.push(`${f.id} 第${i+1}条记载的引语没有包含日期原文「${r.raw}」，读者看不到日期出处`); }); });
  (c.facts||[]).forEach(f=>{ (String(f.title+(f.narr||'')).match(/「[^」]*」/g)||[]).forEach(q=>{ const t=q.slice(1,-1); if(!(f.recs||[]).some(r=>docs[r.d]&&docs[r.d].lines.some(l=>l.includes(t)))) errs.push(`${f.id} 标题里的引语「${t}」在其出处原文里找不到`); }); });
  (c.claims||[]).forEach(x=>{ const d=docs[x.d]; if(d && x.q && !d.lines.some(l=>l.includes(x.q))) errs.push(`主张 ${x.id} 的引语在原文里找不到`); });
  return errs;
}
function resetDecisions(){ Object.assign(S,{dupRes:{},arithRes:{},nEdit:{},nTitle:{},nOrder:null,nMerge:{},adopt:{},revPrev:{},cres:{},rev:{},disp:{},key:{},adverse:{},inferOk:{},susRes:{},attnRes:{},packRes:{},log:[]}); S.aside=new Set(); S.checked=new Set(); }
let timer=null;
function startBuild(){
  clearTimeout(timer); S.read=0; S.phase='build'; resetDecisions(); S.drawer=null; S.selected=null; S.view='work'; S.tab='tl'; S.t0=EXT[0]; S.t1=EXT[1]; S.play=null;
  const step=()=>{ if(S.read<DOCS.length){ S.reading=S.read; render(); timer=setTimeout(()=>{ S.read++; S.reading=-1; render(); timer=setTimeout(step,220); },600); }
    else { S.phase='compare'; render(); timer=setTimeout(()=>{ S.phase='ready'; render(); const ev=derive(); toast(`${ev.length} 个事实，${ev.reduce((a,e)=>a+e.recs.length,0)} 条记载，来自 ${DOCS.length} 份材料 · ${pendingCount()} 项待审`); },1200); } };
  render(); step();
}
function stopBuild(){ clearTimeout(timer); S.phase='ready'; S.reading=-1; render(); }
function go(v){ S.view=v; if(v!=='work'&&S.drawer&&S.drawer.kind!=='doc'){ S.drawer=null; S.dStack=[]; } render(); }


/* =====================================================================
   弹出层与杂项
   ===================================================================== */
function closePops(){ document.querySelectorAll('.pop').forEach(p=>p.remove()); }
function pop(ev,html,w){ closePops(); ev.stopPropagation(); const r=ev.currentTarget.getBoundingClientRect(); const p=document.createElement('div'); p.className='pop'; p.innerHTML=html; p.style.top=(r.bottom+scrollY+6)+'px'; p.style.left=Math.min(r.left+scrollX, innerWidth-(w||280)-16)+'px'; if(w) p.style.width=w+'px'; p.onclick=e=>e.stopPropagation(); document.body.appendChild(p);
  /* 量出实际宽度后再定位：右边放不下就靠右对齐按钮，绝不出界 */
  const pw=p.offsetWidth; let x=r.left+scrollX; if(r.left+pw>innerWidth-12) x=Math.max(12,r.right-pw)+scrollX; p.style.left=x+'px'; }
document.addEventListener('click',closePops);
function filterPop(ev){
  const f=S.f; const box=(g,k,label)=>`<label><input type="checkbox" ${f[g].has(k)?'checked':''} onchange="fToggle('${g}','${k}')"> ${label}</label>`;
  pop(ev,`<div class="fgroup"><h4>事件类型</h4>${TYPE_ORDER.map(t=>box('types',t,`<span class="dot" style="background:${TYPES[t].c}"></span>${TYPES[t].n}`)).join('')}</div>
   <div class="fgroup"><h4>记载来源</h4>${Object.entries(KIND).map(([k,v])=>box('kinds',k,v.n)).join('')}</div>
   <div class="fgroup"><h4>证据的程序状态</h4>${CONFIRM.map(c=>`<label><input type="checkbox" ${(f.cf||new Set()).has(c)?'checked':''} onchange="if(!S.f.cf)S.f.cf=new Set();fToggle('cf','${c}')"> ${c}</label>`).join('')}</div>
   <div class="fgroup"><h4>审阅</h4>${box('rev','todo','待确认')}${box('rev','done','已确认')}</div>
   <label class="opt"><input type="checkbox" ${f.conf?'checked':''} onchange="S.f.conf=this.checked;drawTable()"> 只看记载不一的</label>
   <label class="opt"><input type="checkbox" ${f.key?'checked':''} onchange="S.f.key=this.checked;drawTable()"> 只看关键事实</label>
   <button class="lnk" onclick="S.f={types:new Set(),kinds:new Set(),rev:new Set(),cf:new Set(),conf:false,key:false};closePops();render()">清除筛选</button>`,260);
}
function fToggle(g,k){ const s=S.f[g]; s.has(k)?s.delete(k):s.add(k); drawTable(); }
function morePop(ev){
  pop(ev,`<button class="menuitem" onclick="closePops();openDrawer({kind:'log'})">变更记录（${S.log.length}）</button>
   <button class="menuitem" onclick="closePops();exportBase()">导出底稿 JSON</button>
   <button class="menuitem" onclick="closePops();resetDecisions();render();toast('已清空所有裁决')">清空所有裁决</button>`,200);
}
const DEC_KEYS=['adopt','rev','disp','key','adverse','cres','dupRes','arithRes','susRes','attnRes','packRes','inferOk','nEdit','nTitle','nOrder','nMerge','docOv'];
/* 底稿：与读入的格式完全一样（可再次打开），另附律师在页面上的裁决、改动记录与待读材料 */
function baseJSON(){
  const c=JSON.parse(JSON.stringify(CASE,(k,v)=>(k==='rid'||k==='fid')?undefined:(v instanceof Set?[...v]:v)));
  delete c.answer; delete c.test; delete c.pending;
  c.schema='v8-base/1';
  c.decisions=Object.fromEntries(DEC_KEYS.map(k=>[k,S[k]]).filter(([,v])=>v&&(Array.isArray(v)?v.length:Object.keys(v).length)));
  if(S.aside&&S.aside.size) c.decisions.aside=[...S.aside];
  c.changes=S.log; const pd=pendOut(S.pend||[]); if(pd.length) c.pending=pd;
  return JSON.stringify(c,null,1);
}
function exportBase(){ saveFile(`${CASE.title||CASE.id}.base.json`,baseJSON(),'application/json'); }
function toast(msg){ const t=$('#toast'); t.innerHTML=`<span class="ok">✓</span>${esc(msg)}`; t.style.display='flex'; clearTimeout(toast.t); toast.t=setTimeout(()=>t.style.display='none',3400); }
addEventListener('resize',()=>{ if(S.view==='work'&&S.tab==='tl') drawTimeline(); });
addEventListener('keydown',e=>{
  if(e.target.tagName==='INPUT'||e.target.tagName==='TEXTAREA') return;
  if(e.key==='Escape'){ closePops(); if(S.play!==null){ S.play=null; render(); } else if(S.drawer){ if((S.dStack||[]).length) backDrawer(); else closeDrawer(); } }
  if(S.play!==null && e.key==='ArrowRight') playStep(1);
  if(S.play!==null && e.key==='ArrowLeft') playStep(-1);
});
// 案件库排序：示例 → 自造各案由 → 刁难件
CASES.sort((a,b)=>{ const r=c=>c.id==='test02'?0:(c.test||'').startsWith('刁难')?2:1; return r(a)-r(b); });
/* 启动见版式层末尾 */
