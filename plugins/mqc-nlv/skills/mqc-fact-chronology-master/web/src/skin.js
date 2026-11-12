
/* 版式层：结构照 Fact chronology（单栏：标题、操作行、标签页、时间线卡片、事实表卡片、右侧按需抽屉），
   设计元素取上传工作台（冷灰中性、黑色主按钮、灰槽分段控件、黑体 13px、宋体只给标题、Inter 管数字），
   比官方更密：行高、留白都压紧。按钮上不用小三角，下拉改分段控件。 */
const I=(d,extra='')=>`<svg class="ic" viewBox="0 0 20 20" ${extra}>${d}</svg>`;
const ICO = {
  doc:I('<path d="M5.5 2.75h5.75L14.5 6v11.25h-9z"/><path d="M11 2.75V6.3h3.5"/>'),
  add:I('<path d="M10 4.5v11M4.5 10h11"/>'),
  out:I('<path d="M10 12.5V3.5M6.75 6.5 10 3.25l3.25 3.25"/><path d="M4.5 11v4.25c0 .6.4 1 1 1h9c.6 0 1-.4 1-1V11"/>'),
  play:I('<path d="M7 5.2v9.6c0 .5.5.8.9.5l7-4.8c.4-.3.4-.8 0-1.1l-7-4.8c-.4-.2-.9.1-.9.6z"/>'),
  eye:I('<path d="M2.5 10s2.75-5 7.5-5 7.5 5 7.5 5-2.75 5-7.5 5-7.5-5-7.5-5z"/><circle cx="10" cy="10" r="2.25"/>'),
  fit:I('<path d="M3.5 7.5v-4h4M16.5 7.5v-4h-4M3.5 12.5v4h4M16.5 12.5v4h-4"/>'),
  filter:I('<path d="M3.5 5.5h13M6 10h8M8.5 14.5h3"/>'),
  search:I('<circle cx="9" cy="9" r="5.25"/><path d="m13 13 3.5 3.5"/>'),
  more:I('<circle cx="5" cy="10" r=".9" fill="currentColor"/><circle cx="10" cy="10" r=".9" fill="currentColor"/><circle cx="15" cy="10" r=".9" fill="currentColor"/>'),
  chev:I('<path d="M6.5 8.25 10 11.75l3.5-3.5"/>'),
  prev:I('<path d="M12 4.5 6.5 10l5.5 5.5"/>'),
  next:I('<path d="M8 4.5l5.5 5.5L8 15.5"/>'),
  check:I('<path d="M4.75 10.25 8.25 13.5 15.25 6.5"/>'),
  back:I('<path d="M12 4.5 6.5 10l5.5 5.5"/>'),
  grid:I('<rect x="3" y="3.5" width="14" height="13" rx="2"/><path d="M3 8h14M3 12.25h14M8 3.5v13"/>'),
  pen:I('<path d="M12.75 4.25 15.75 7.25 7.5 15.5H4.5v-3z"/>'),
  lanes:I('<path d="M3.5 6h13M3.5 10h13M3.5 14h13"/>'),
  minus:I('<path d="M5 10h10"/>'),
  plus:I('<path d="M10 5v10M5 10h10"/>'),
  x:I('<path d="M5.5 5.5l9 9M14.5 5.5l-9 9"/>'),
  book:I('<path d="M4 4.5c0-.6.4-1 1-1h9.5v13H5c-.6 0-1-.4-1-1z"/><path d="M7 7h5M7 10h5M7 13h3"/>')
};
function header(){
  const evs=derive(), pc=pendingCount(), building=S.phase!=='ready';
  return `<div class="h10">
    <button class="ibt" title="新建或打开其他案件" onclick="go('new')">${ICO.back}</button>
    <h1 class="title" title="${esc(CASE.title)}">${esc(CASE.title)}</h1>
    <button class="btn" onclick="go('docs')">${ICO.doc}<span class="num">${DOCS.length}</span> 份材料${(S.pend||[]).length?`<span class="pend num">+${S.pend.length} 待读</span>`:''}</button>
    <span class="hsp"></span>
    <label class="btn ghost">${ICO.add}添加材料<input type="file" multiple style="display:none" onchange="addToCase(this.files);this.value=''"></label>
    <button class="btn ghost" onclick="exportPop(event)">${ICO.out}导出</button>
    ${building?`<button class="btn dark rv" disabled>比对后出待审</button>`:`<button class="btn dark rv" onclick="S.drawer&&S.drawer.kind==='review'?closeDrawer():openReview()"><span class="num">${pc}</span> 项待审</button>`}
    <button class="ibt" onclick="morePop(event)" title="更多">${ICO.more}</button>
  </div>
  ${building?progress():''}`;
}
function viewWork(){
  const evs=derive(), nm=evs.filter(e=>new Set(e.recs.map(r=>r.d)).size>1||e.wasConflict||e.amtConflict).length, nd=evs.filter(e=>e.wasConflict||e.amtConflict).length;
  const tabs=[['tl','时间线'],['matrix','对照矩阵'],['narr','事实经过']];
  return `${header()}
  <div class="tabs10">${tabs.map(([k,n,c])=>`<button class="${S.tab===k?'on':''}" onclick="S.tab='${k}';render()">${k==='tl'?ICO.lanes:k==='matrix'?ICO.grid:ICO.book}<span>${n}</span></button>`).join('')}</div>
  ${S.tab==='tl'?viewTL():S.tab==='matrix'?`<div class="card pane" id="pane"></div>`:`<div class="card narr" id="narr"></div>`}
  <div class="foot">由 AI 辅助整理，供办案团队内部核对，不构成法律意见；引用前请回到原文核实。</div>`;
}
function viewTL(){
  const vis=visibleFacts(), undated=derive().filter(e=>e.undated), cl=claimsVisible();
  const totalAll=(()=>{ const k=S.stage; S.stage=5; invalidate(); const n=derive().length; S.stage=k; invalidate(); derive(); return n; })();
  const notes=[]; if(S.stage<5) notes.push(`截至「${STAGES[S.stage]}」`); if(S.play!==null) notes.push('回放中');
  const filtered = vis.length<totalAll;
  const seg=(cls,items,cur,act)=>`<div class="seg ${cls}">${items.map(([v,n])=>`<button class="${cur(v)?'on':''}" aria-pressed="${cur(v)}" onclick="${act(v)}">${n}</button>`).join('')}</div>`;
  return `<div class="card tlcard">
    <div class="tltools${S.timelineMode==='vertical'&&S.play===null?' vertical-tools':''}">
      ${S.play===null?seg('timeline-mode',[['horizontal','横向'],['vertical','纵向']],v=>S.timelineMode===v,v=>`S.timelineMode='${v}';render()`):''}
      ${S.play!==null?playTools():`
      <span class="lab">截至</span>
      ${seg('stage',[[0,'接受咨询'],[1,'谈案'],[2,'庭前'],[5,'全部']],v=>v===5?S.stage>=3:S.stage===v,v=>`S.stage=${v};render()`)}
      <span class="hsp"></span>
      ${S.timelineMode==='vertical'?'<button class="btn sm" onclick="setTimelineMonths(true)">展开全部</button><button class="btn sm" onclick="setTimelineMonths(false)">收起全部</button>':`<span class="rng num" id="rng">${esc(rangeLabel())}</span>
      <span class="zgrp"><button class="ibt" id="zout" onclick="zoom(1/1.6)" title="缩小">${ICO.minus}</button><button class="ibt" onclick="zoom(1.6)" title="放大">${ICO.plus}</button></span>
      <button class="btn sm" id="bfit" onclick="fit()" title="显示全部时间">${ICO.fit}全时段</button>
      <button class="btn sm" onclick="viewPop(event)">${ICO.eye}显示</button>
      <button class="btn sm" onclick="startPlay()">${ICO.play}回放</button>`}`}
    </div>
    ${S.timelineMode==='vertical'&&S.play===null?verticalTimeline(vis):vis.some(e=>!e.undated)||S.play!==null?horizontalTimeline():`<div class="tlempty">本案材料中的事实都没有可定位的日期，暂不能上时间线；它们列在下方「无日期」与事实表里。</div>`}
    ${S.timelineMode!=='vertical'||S.play!==null?legend(vis):''}
    <div class="undated"><div class="lt">无日期 <span class="num">${undated.length}</span>${undated.length?`<button class="lnk udgo" onclick="S.tab='narr';render()" title="无日期的事实在「事实经过」里按线索排在相应位置">在事实经过里看 →</button>`:''}</div><div class="ud-list">
      ${undated.map(e=>`<button class="udchip" onclick="selectEv('${e.id}')"><span class="dot" style="background:${TYPES[e.t].c}"></span><span class="t">${esc(e.title)}</span></button>`).join('')}
      ${S.showClaims?cl.filter(c=>!c.s).map(c=>`<button class="udchip" onclick="openClaim('${c.id}')"><span class="sqo"></span><span class="t">${c.who}主张：${esc(c.title)}</span></button>`).join(''):''}
    </div></div>
    ${S.timelineMode==='horizontal'&&S.play===null?timelineMaterials():''}
  </div>
  <div class="tbar">
    <div class="search">${ICO.search}<input id="q" placeholder="搜索事实、原文、材料名" value="${esc(S.q)}" oninput="S.q=this.value;drawTable()">${S.q?`<button class="qx" onclick="S.q='';render()" title="清空">${ICO.x}</button>`:''}</div>
    <button class="btn sm" onclick="filterPop(event)">${ICO.filter}筛选${activeFilters()?` · ${activeFilters()}`:''}</button>
    <span id="tstate" class="vstate inl"></span>
    <span class="hsp"></span><span id="tcount" class="sub" aria-live="polite"></span><span id="batch"></span>
  </div>
  <div class="card tablecard"><div class="tscroll" id="tablewrap"></div></div>`;
}
function horizontalTimeline(){
  const controls=S.play===null?`<aside class="tl-density" aria-label="时间线纵向疏密">
    <label for="tl-density">纵向疏密</label>
    <input type="range" id="tl-density" min="0" max="2" step="1" value="${S.timelineDensity}" aria-orientation="vertical" aria-valuetext="${TIMELINE_DENSITY[S.timelineDensity]}" oninput="setTimelineDensity(this.valueAsNumber)">
    <div class="density-stops">${TIMELINE_DENSITY.map((name,i)=>`<button type="button" data-density="${i}" aria-pressed="${i===S.timelineDensity}" onclick="setTimelineDensity(${i})">${name}</button>`).join('')}</div>
    <button class="lnk" id="tl-open-materials" onclick="openTimelineMaterials()" hidden>材料目录</button>
    <button class="lnk" id="tl-reset-clusters" onclick="resetTimelineClusters()" hidden>收起局部</button>
  </aside>`:'';
  return `<div class="tl-layout${controls?' has-density':''}">
    <div class="tl-canvas">
      <div class="minirow"><button class="lanebtn" onclick="lanePop(event)" title="泳道按什么分">${ICO.lanes}<span>${LANE_N[S.lanes]}</span>${ICO.chev}</button><div id="mini"></div></div>
      <div class="tlscroll"><div id="tl"></div></div>
    </div>${controls}
  </div>`;
}
function openTimelineMaterials(){
  const materials=$('#timeline-materials');
  if(!materials) return;
  materials.open=true;
  materials.scrollIntoView({block:'start'});
}
function timelineMaterials(){
  const docs=DOCS.filter(d=>docVisible(d.id));
  if(!docs.length) return '';
  return `<details class="timeline-materials" id="timeline-materials" ${S.timelineMaterialsOpen?'open':''} ontoggle="if(this.isConnected) S.timelineMaterialsOpen=this.open" hidden>
    <summary>${S.stage>=5?'全部':'本阶段'} ${docs.length} 份材料</summary>
    <ul>${docs.map(d=>`<li><button class="dref" onclick="openDoc(this.dataset.material)" data-material="${esc(d.id)}"><span class="sub">${esc(d.id)}</span> ${esc(d.name)}</button></li>`).join('')}</ul>
  </details>`;
}

function setTimelineMonths(open){
  document.querySelectorAll('.timeline-month').forEach(el=>{
    S.monthOpen.set(el.dataset.month,open);
    el.open=open;
  });
}
function verticalTimeline(evs){
  const months=new Map();
  for(const e of evs){
    if(!Number.isFinite(e.sortKey)) continue;
    const month=isoOf(e.sortKey).slice(0,7);
    if(!months.has(month)) months.set(month,[]);
    months.get(month).push(e);
  }
  if(!months.size) return '<div class="tlempty">当前没有可按月排列的事实。</div>';
  const pending=pendingFactIds(reviewItems());
  const row=e=>{
    const date=timelineDateLabel(e);
    return `<li><button class="month-fact ${S.selected===e.id?'on':''}" data-fact="${esc(e.id)}" onclick="selectEv(this.dataset.fact)">
      <span class="month-date num">${esc(date)}</span>
      <span class="month-title"><span class="dot" style="background:${TYPES[e.t].c}"></span>${esc(e.title)}</span>
      ${factReviewBadge(e,false,pending)}
    </button></li>`;
  };
  return `<div class="vertical-timeline">${[...months].map(([month,rows])=>`
    <details class="timeline-month" data-month="${month}" ${S.monthOpen.get(month)!==false?'open':''} ontoggle="if(this.isConnected) S.monthOpen.set(this.dataset.month,this.open)">
      <summary><strong>${fmtM(dn(month))}</strong><span class="sub">${rows.length} 条事实</span></summary>
      <ol>${rows.map(row).join('')}</ol>
    </details>`).join('')}</div>`;
}

/* 事实表：保留官方四列（日期｜事实｜来源｜状态），每行压成两行字：标题+标记一行，对外措辞一行 */
function tableFacts(){
  const q=S.q.trim();
  let evs=visibleFacts().filter(e=>{
    if(S.f.types.size && !S.f.types.has(e.t)) return false;
    if(S.f.kinds.size && !e.recs.some(r=>S.f.kinds.has(dKind(r.d)))) return false;
    if(S.f.rev.size && !S.f.rev.has(e.rev)) return false;
    if(S.f.cf && S.f.cf.size && !e.recs.some(r=>S.f.cf.has(dConf(r.d)))) return false;
    if(S.f.conf && !e.wasConflict && !e.amtConflict && !(e.amtVals&&e.amtVals.length>1)) return false;
    if(S.f.key && !e.key) return false;
    if(q && !hay(e).includes(q)) return false;
    return true; });
  if(!S.sortAsc) evs=[...evs].reverse().sort((a,b)=>(a.undated?1:0)-(b.undated?1:0));
  return evs;
}
function drawTable(){
  const host=$('#tablewrap'); if(!host) return;
  const evs=tableFacts();
  const pending=pendingFactIds(reviewItems());
  const cl=S.showClaims?claimsVisible():[];
  TL.tableRows=evs;
  const src=e=>{ const seen=new Map(); e.recs.forEach(r=>{ if(!seen.has(r.d)) seen.set(r.d,r); });
    return [...seen.values()].map(r=>`<span class="sc ${e.adopted&&REC[e.adopted].d===r.d?'ad':''}">${kindTag(r.d)}<button class="dref" title="${esc(DOC[r.d].sub)}${e.conflict||e.wasConflict?'：'+esc(r.raw):''}" onclick="event.stopPropagation();openDoc('${r.d}','${r.rid}')">${r.d}</button></span>`).join(''); };
  const tc=$('#tcount'); if(tc) tc.textContent=`${evs.length} 条事实${cl.length?` · ${cl.length} 条主张`:''}`;
  host.innerHTML=`<table class="ev"><thead><tr><th style="width:150px;cursor:pointer" onclick="S.sortAsc=!S.sortAsc;drawTable()">日期 ${S.sortAsc?'↑':'↓'}</th><th>事实</th><th style="width:190px">来源</th><th style="width:116px">状态</th></tr></thead><tbody>
  ${evs.map(e=>{
    const tags=[];
    if(e.conflict) tags.push('<span class="tag conf">日期冲突</span>');
    if(e.amtConflict) tags.push('<span class="tag conf">金额冲突</span>');
    if(e.adopted) tags.push(`<span class="tag blue">已采信 ${REC[e.adopted].d}</span>`);
    if(e.amt!=null) tags.push(`<span class="tag out num">${fmtAmt(e.amt)}</span>`);
    if(e.state==='agr') tags.push('<span class="tag out">约定</span>');
    if(e.est) tags.push('<span class="tag out">推定</span>');
    if(!e.certain && !e.conflict && e.state!=='agr' && !e.est) tags.push('<span class="tag out">未确定</span>');
    if(e.flag) tags.push(`<span class="tag amber">${e.flag}</span>`);
    if(e.adverse) tags.push('<span class="tag red">不利 · 仅内部</span>');
    return `<tr id="row-${e.id}" class="${S.selected===e.id?'selrow':''}" onclick="selectEv('${e.id}',true)" onmouseenter="linkMark('${e.id}',1)" onmouseleave="linkMark('${e.id}',0)">
     <td class="dt"><div class="dwrap"><input type="checkbox" class="cb" ${S.checked.has(e.id)?'checked':''} onclick="event.stopPropagation();toggleCheck('${e.id}')"><div><div class="d num">${dateLabel(e)}</div>${dateNote(e)?`<div class="n">${dateNote(e)}</div>`:''}</div></div></td>
     <td class="ev"><div class="t"><span class="dot" style="background:${TYPES[e.t].c}"></span>${e.key?'<span class="star-s">★</span>':''}<span class="tt">${esc(e.title)}</span>${tags.join('')}</div><div class="s">${esc(phrase(e))}</div></td>
     <td class="src"><div class="srcs">${src(e)}</div></td>
     <td class="st"><div class="fact-status-cell">${factReviewBadge(e,false,pending)}<button class="stbtn" onclick="event.stopPropagation();toggleRev('${e.f.id}')" title="${e.rev==='done'?'撤销人工确认':'标为已确认'}" aria-label="${e.rev==='done'?'撤销人工确认':'标为已确认'}">${e.rev==='done'?'<span class="review-tick" aria-hidden="true">✓</span>':'<span class="st-needs"></span>'}</button></div></td></tr>`;}).join('')}
  ${cl.map(c=>`<tr class="claimrow" onclick="openClaim('${c.id}')"><td class="dt"><div class="dwrap"><span class="cbsp"></span><div><div class="d num">${c.s?fmtD(c.s):'无日期'}</div><div class="n">主张</div></div></div></td><td class="ev"><div class="t"><span class="sqo"></span><span class="tt">${c.who}主张：${esc(c.title)}</span><span class="tag out">主张不是事实</span></div><div class="s">「${esc(c.q)}」</div></td><td class="src"><span class="sc">${kindTag(c.d)}<button class="dref" onclick="event.stopPropagation();openDoc('${c.d}')">${c.d}</button></span></td><td></td></tr>`).join('')}
  </tbody></table>`;
  batchBar();
  const steps=$('#factSteps');
  if(steps&&S.drawer?.kind==='fact') steps.innerHTML=factSteps(S.drawer.id);
  const ts=$('#tstate'); if(ts) ts.innerHTML=tableState();
}

/* ---------- 工具条：位置固定，不随选择跳动 ---------- */
const LANE_N={type:'按事件类型',doc:'按材料',actor:'按主体',one:'不分泳道'};
function lanePop(ev){
  const it=(v)=>`<button class="mi ${S.lanes===v?'on':''}" onclick="S.lanes='${v}';closePops();render()"><span class="ck">${S.lanes===v?ICO.check:''}</span>${LANE_N[v]}</button>`;
  pop(ev,`<h4>泳道</h4>${['type','doc','actor','one'].map(it).join('')}<div class="msep"></div>
    <label class="mi ${S.lanes!=='type'?'dis':''}"><input type="checkbox" ${S.more?'checked':''} ${S.lanes!=='type'?'disabled':''} onchange="S.more=this.checked;closePops();render()">显示没有事实的泳道</label>`,200);
}
function rangeLabel(){
  const p2=n=>String(n).padStart(2,'0'), f=n=>{ const d=fromDn(n); return `${d.getUTCFullYear()}.${p2(d.getUTCMonth()+1)}`; };
  const full=S.t0<=EXT[0]+0.5 && S.t1>=EXT[1]-0.5;
  return (full?'全部 · ':'')+f(Math.max(S.t0,EXT[0]))+' – '+f(Math.min(S.t1,EXT[1]));
}
function playTools(){
  const order=playOrder(); if(!order.length) return ''; const k=Math.min(S.play,order.length), e=order[k-1];
  return `<span class="playbar"><span class="pk num">回放 ${k} / ${order.length}</span>
    <span class="pdate num">${esc(dateLabel(e))}</span><span class="ptitle">${esc(e.title)}</span>
    <span class="pbtns"><button class="btn sm pstep" onclick="playStep(-1)" title="上一步（←）" ${k<=1?'disabled':''}>${ICO.prev}上一步</button><button class="btn sm dark pstep" onclick="playStep(1)" title="下一步（→）" ${k>=order.length?'disabled':''}>下一步${ICO.next}</button>
    <button class="btn sm" onclick="S.play=null;S.selected=null;render()">退出回放</button></span></span>`;
}

/* =====================================================================
   新建：上传材料之前的界面（照原版 New chronology 的结构）
   ===================================================================== */
const NEW={name:'',src:'firm',q:'',files:[],seq:0};
const EXTN=f=>{ const m=/\.([a-z0-9]+)$/i.exec(f); return m?m[1].toUpperCase():'文本'; };
function viewNew(){
  /* 空白入口：照工作台的样子留白。材料一般在对话里交给 Agent；这里也可以直接放 */
  return `<div class="h10">
    ${CASE&&CASE.id!=='blank'?`<button class="ibt" title="回到当前案件" onclick="go('work')">${ICO.back}</button>`:''}
    <input class="title nwtitle" id="nwname" placeholder="未命名案件" value="${esc(NEW.name)}" oninput="NEW.name=this.value">
    <span class="hsp"></span>
    <label class="btn ghost">${ICO.book}打开底稿<input type="file" accept=".json,application/json" style="display:none" onchange="openFile(this.files[0])"></label>
    ${CASES.length?`<button class="btn ghost" onclick="S.showSamples=!S.showSamples;render()">${ICO.grid}${CASES.length>1?'示例案件':'已打开的案件'}</button>`:''}
  </div>
  <div class="tabs10 dim">${[['时间线',ICO.lanes],['对照矩阵',ICO.grid],['事实经过',ICO.book]].map(([n,i],k)=>`<button class="${k?'':'on'}" disabled>${i}<span>${n}</span></button>`).join('')}</div>
  ${S.showSamples?`<div class="casegrid">${CASES.map((c,i)=>`<button class="card casecard ${CASE&&CASE.id===c.id?'on':''}" onclick="switchCase(${i})"><div class="cct">${esc(c.title)}</div><div class="sub">${esc(c.cause||'')}</div><div class="ccm num">${(c.materials||[]).length} 份材料 · ${(c.facts||[]).length} 个事实</div></button>`).join('')}</div>`:''}
  <div class="card tlcard nwblank" id="nwdrop" ondragover="event.preventDefault();this.classList.add('over')" ondragleave="this.classList.remove('over')" ondrop="event.preventDefault();this.classList.remove('over');addFiles(event.dataTransfer.files)">
    <div class="nwzone">${ICO.doc}<div class="t1">把材料拖到这里</div><div class="t2">起诉状、答辩状、合同、转账记录、聊天记录、证人证言等</div>
      <div class="nwbtns"><label class="btn dark">选择文件<input type="file" multiple style="display:none" onchange="addFiles(this.files);this.value=''"></label><button class="btn" onclick="pasteBox()">粘贴文字</button></div></div>
  </div>
  <div class="card tablecard nwtable"><table class="ev"><thead><tr><th style="width:150px">日期</th><th>事实</th><th style="width:180px">来源</th><th style="width:80px">状态</th></tr></thead><tbody><tr><td colspan="4" class="nwnone">暂无事实</td></tr></tbody></table></div>`;
}
function fmtSize(n){ return n>=1048576?(n/1048576).toFixed(1)+' MB':Math.max(1,Math.round(n/1024))+' KB'; }
function addFiles(list){
  const fs=[...(list||[])]; if(!fs.length) return;
  if(fs.length===1 && /\.json$/i.test(fs[0].name) && !NEW.files.length){ openFile(fs[0]); return; }
  /* 文书日期不取文件保存日期（那常常是扫描或拷贝的日子），读后取落款日 */
  fs.forEach(f=>{ NEW.seq++; const o={id:'L-'+String(NEW.seq).padStart(2,'0'),name:f.name,size:f.size,ext:EXTN(f.name),kind:'',date:'',read:true}; NEW.files.push(o); readInto(f,o); });
  if(!NEW.name){ const n=$('#nwname'); if(n&&n.value) NEW.name=n.value; }
  S.view='stage'; render();
}
function pasteBox(){
  const m=document.createElement('div'); m.className='modal'; m.id='pastem';
  m.innerHTML=`<div class="mbox2"><h3>粘贴文字</h3><div class="sub">一段聊天记录、一份笔录或情况说明。</div>
    <input class="inp" id="pname" placeholder="材料名称，例：微信聊天记录（张三与李四）" style="margin-top:12px">
    <textarea class="inp" id="ptext" rows="10" placeholder="把文字粘贴到这里"></textarea>
    <div class="nwrow"><span class="hsp"></span><button class="btn" onclick="document.getElementById('pastem').remove()">取消</button><button class="btn dark" onclick="addPaste()">添加</button></div></div>`;
  m.onclick=e=>{ if(e.target===m) m.remove(); }; document.body.appendChild(m); setTimeout(()=>$('#pname').focus(),20);
}
function addPaste(){ const n=$('#pname').value.trim()||'粘贴的文字', t=$('#ptext').value; if(!t.trim()){ toast('还没有粘贴文字'); return; }
  NEW.seq++; NEW.files.push({id:'L-'+String(NEW.seq).padStart(2,'0'),name:n,size:new Blob([t]).size,ext:'文本',kind:'',date:'',dsrc:'',read:true,text:t});
  $('#pastem').remove(); S.view='stage'; render(); }
function copyText(t){ try{ navigator.clipboard.writeText(t).then(()=>toast('已复制'),()=>toast('复制未成功，请手动选取')); }catch(e){ toast('复制未成功，请手动选取'); } }
/* 材料清单：上传之后、读取之前（照原版 Documents 表） */
function viewStage(){
  const fs=NEW.files, n=fs.filter(f=>f.read).length;
  return `<div class="nw">
  <div class="nwhead"><button class="ibt" title="返回" onclick="go('new')">${ICO.back}</button><h1 class="title">${esc(NEW.name||'未命名案件')}</h1><span class="meta"><span class="num">${fs.length}</span> 份材料</span>
    <span class="hsp"></span><label class="btn ghost">${ICO.add}继续添加<input type="file" multiple style="display:none" onchange="addFiles(this.files);this.value=''"></label>
    <button class="btn dark" ${n?'':'disabled'} onclick="saveNewBase()">保存底稿：<span class="num">${n}</span> 份待读材料</button></div>
  <div class="card" style="margin-top:14px"><div class="tscroll"><table class="docs stg"><thead><tr><th style="width:36px">读</th><th style="width:64px">编号</th><th>材料</th><th style="width:150px">证据种类</th><th style="width:170px">文书日期</th><th style="width:130px">读取</th><th style="width:40px"></th></tr></thead><tbody>
  ${fs.map((f,i)=>`<tr class="${f.read?'':'off'}"><td><input type="checkbox" ${f.read?'checked':''} onchange="NEW.files[${i}].read=this.checked;render()" title="是否读取这份材料"></td>
    <td><b class="num">${f.id}</b></td>
    <td><div class="fn"><span class="fx">${esc(f.ext)}</span><span>${esc(f.name)}</span></div><div class="sub num">${fmtSize(f.size)}</div></td>
    <td><select class="sel" onchange="NEW.files[${i}].kind=this.value"><option value="" ${f.kind?'':'selected'}>读后自动判定</option>${Object.entries(KIND).map(([k,v])=>`<option value="${k}" ${f.kind===k?'selected':''}>${v.n}</option>`).join('')}</select></td>
    <td><input class="inp dt num" type="date" value="${f.date}" onchange="NEW.files[${i}].date=this.value;render()"><div class="sub">${f.date?'手动填写':'留空则读后取落款日'}</div></td>
    <td><span class="rd">尚未读取</span></td>
    <td><button class="ibt" title="移除" onclick="NEW.files.splice(${i},1);if(!NEW.files.length)S.view='new';render()">${ICO.x}</button></td></tr>`).join('')}
  </tbody></table></div></div></div>`;
}

/* 页面里放进来的材料：先登记为「尚未读取」，内容随底稿一起保存，交回 Agent 时读取 */
function readInto(f,o){ const rd=new FileReader(), txt=/^text\/|\.txt$|\.md$|\.csv$/i.test(f.type+' '+f.name);
  rd.onload=()=>{ if(txt) o.text=rd.result; else o.data=rd.result; }; txt?rd.readAsText(f,'utf-8'):rd.readAsDataURL(f); }
const pendOut=list=>list.filter(f=>f.read!==false).map(f=>({mid:f.id,name:f.name,size:f.size,kind:f.kind?KIND[f.kind].n:'',doc_date:f.date||'',status:'尚未读取',text:f.text||undefined,data:f.data||undefined}));
function saveNewBase(){
  const t=(NEW.name||'').trim()||'未命名案件';
  const base={schema:'v8-base/1',id:'case-'+Date.now().toString(36),title:t,cause:'',pack:'general',parties:[],materials:[],facts:[],claims:[],relations:[],threads:[],pending:pendOut(NEW.files)};
  saveFile(`${t}.base.json`,JSON.stringify(base,null,2),'application/json');
}
function addToCase(list){
  const fs=[...(list||[])]; if(!fs.length) return; if(!S.pend) S.pend=[];
  const nums=[...DOCS.map(d=>d.id),...S.pend.map(d=>d.id)].map(x=>+(/(\d+)$/.exec(x)||[0,0])[1]), pre=(/^([A-Z]+-)/.exec((DOCS[0]||{}).id||'L-')||[0,'L-'])[1];
  let n=Math.max(0,...nums);
  fs.forEach(f=>{ n++; const o={id:pre+String(n).padStart(2,'0'),name:f.name,size:f.size,ext:EXTN(f.name),kind:'',date:'',read:true}; S.pend.push(o); readInto(f,o); });
  render(); toast(`已加入 ${fs.length} 份材料，尚未读取`);
}
if(CASES.length) loadCase(CASES[0]); else { loadCase({id:'blank',title:'',materials:[],facts:[]}); S.view='new'; }
render();
