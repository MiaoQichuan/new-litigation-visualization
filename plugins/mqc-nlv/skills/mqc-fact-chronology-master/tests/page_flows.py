"""案件看板大师 · 页面交互流程测试（需要 Playwright；先运行 python3 web/build.py --demo）
模拟律师真实操作，每一步检查"数据—时间线—事实表—待审—变更记录"是否同步，撤销能否回到原状。
用法：python3 tests/page_flows.py [html路径]
"""
import asyncio, json, sys
import os, tempfile
from playwright.async_api import async_playwright

HTML = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),'web','out','demo.html')

FLOWS_JS = r"""
() => {
  const out = [];
  const ok = (name, cond, info) => out.push({name, ok: !!cond, info: cond ? '' : (info||'')});
  const ev = () => { invalidate(); return derive(); };
  const E = id => ev().find(e => e.id === id);
  const svgText = () => { const s = document.querySelector('#tlsvg'); return s ? s.textContent : ''; };
  const rows = () => [...document.querySelectorAll('#tablewrap tbody tr:not(.claimrow)')].map(r => r.id.replace('row-',''));
  const snap = () => JSON.stringify({p: pendingCount(), ids: ev().map(e=>e.id+':'+e.conflict+':'+e.amtConflict+':'+e.undated)});
  const base = () => { S.drawer=null; S.selected=null; S.q=''; S.f={types:new Set(),kinds:new Set(),rev:new Set(),conf:false,key:false}; S.stage=5; S.play=null; S.tab='tl'; S.view='work'; resetDecisions(); S.packRes={}; render(); };
  base();
  const P0 = pendingCount(), S0 = snap();

  // 1. 采信：每个日期冲突都采信第一条记载 → 冲突消失、待审减一、表格标注、时间线不再画冲突、有变更记录；撤销后复原
  ev().filter(e=>e.conflict).forEach(e => {
    const fid=e.f.id, r=e.strict[0], before=pendingCount(), logN=S.log.length;
    adopt(fid, r.rid);
    const a=E(e.id);
    ok(`采信 ${fid}：冲突消解`, a && !a.conflict && a.adopted===r.rid, JSON.stringify(a&&{c:a.conflict,ad:a.adopted}));
    ok(`采信 ${fid}：待审减少`, pendingCount() < before, `${before}→${pendingCount()}`);
    ok(`采信 ${fid}：表格显示已采信`, (document.querySelector('#row-'+CSS.escape(e.id))||{}).textContent?.includes('已采信'), '');
    ok(`采信 ${fid}：日期取被采信记载`, a && a.main && a.main.lo===recIv(r)[0], '');
    ok(`采信 ${fid}：写入变更记录`, S.log.length===logN+1, '');
    ok(`采信 ${fid}：出现在已处理列表`, resolvedList().some(x=>x.undo===`unAdopt('${fid}')`), '');
    unAdopt(fid);
    ok(`撤销采信 ${fid}：冲突恢复`, E(e.id) && E(e.id).conflict, '');
  });
  ok('全部撤销后待审数复原', pendingCount()===P0, `${P0}→${pendingCount()}`);

  // 2. 金额冲突采信
  ev().filter(e=>e.amtConflict).forEach(e => {
    const fid=e.f.id, r=e.recs.find(x=>x.amt!=null);
    adopt(fid, r.rid); const a=E(e.id);
    ok(`金额采信 ${fid}：金额取被采信记载`, a && !a.amtConflict && a.amt===+r.amt, JSON.stringify(a&&{m:a.amt,c:a.amtConflict}));
    unAdopt(fid);
    ok(`撤销金额采信 ${fid}`, E(e.id) && E(e.id).amtConflict, '');
  });

  // 3. 拆开 / 只是约定
  ev().filter(e=>e.conflict).forEach(e => {
    const fid=e.f.id, n0=ev().length;
    cres(fid,'split');
    const parts=ev().filter(x=>x.f.id===fid);
    ok(`拆开 ${fid}：拆成多个事实`, parts.length>=2 && parts.every(x=>!x.conflict), `${parts.length} 个`);
    ok(`拆开 ${fid}：每份记载都还在`, parts.reduce((a,x)=>a+x.recs.length,0)===e.recs.length, '');
    ok(`拆开 ${fid}：选中拆分后的事实不崩`, (()=>{ try{ selectEv(parts[0].id); return !!document.querySelector('#drawerIn .ed-title'); }catch(err){ return false; } })(), '');
    delete S.cres[fid]; S.drawer=null; render();
    ok(`撤销拆开 ${fid}`, ev().length===n0 && E(e.id) && E(e.id).conflict, '');
  });

  // 4. 推断：确认 / 改为无日期
  Object.keys(INFER).forEach(k => {
    const users=ev().filter(e=>e.recs.some(r=>r.inf===k)); if(!users.length) return;
    S.inferOk[k]='undated'; render();
    const after=ev();
    const bad=users.filter(u=>{ const a=after.find(x=>x.f.id===u.f.id); return a && a.recs.some(r=>r.inf===k && r.p!=='none'); });
    ok(`推断 ${k} 改为无日期：不再用该推断定位`, after.every(e=>!e.dated.some(r=>r.inf===k)), bad.map(b=>b.id).join());
    ok(`推断 ${k} 改为无日期：待审项消失`, !reviewItems().some(i=>i.id==='I:'+k), '');
    delete S.inferOk[k]; render();
    S.inferOk[k]='ok'; render();
    ok(`推断 ${k} 确认：待审项消失、事实保持有日期`, !reviewItems().some(i=>i.id==='I:'+k) && users.every(u=>{ const a=E(u.id); return a && !a.undated; }), '');
    delete S.inferOk[k]; render();
  });

  // 5. 可疑日期
  FACTS.forEach(f=>f.recs.filter(r=>r.sus).forEach(r => {
    S.susRes[r.rid]='typo'; render();
    ok(`可疑 ${r.rid} 按笔误：时间线上没有该日期`, !ev().some(e=>e.dated.some(x=>x.rid===r.rid)), '');
    S.susRes[r.rid]='event'; render();
    ok(`可疑 ${r.rid} 按原文：生成带标记的事实`, ev().some(e=>e.flag==='日期可疑' && e.recs.some(x=>x.rid===r.rid)), '');
    delete S.susRes[r.rid]; render();
  }));

  // 6. 仅有陈述：暂置
  const np=reviewItems().find(i=>i.k==='np');
  if(np){ np.fs.forEach(e=>S.aside.add(e.id)); render();
    ok('仅有陈述全部暂置：待审项消失', !reviewItems().some(i=>i.k==='np'), '');
    S.aside.clear(); render(); }

  // 7. 领域规则：已知悉
  reviewItems().filter(i=>i.k==='pack').forEach(i => { S.packRes[i.id]=1; render();
    ok(`领域规则 ${i.id} 已知悉`, !reviewItems().some(x=>x.id===i.id), ''); delete S.packRes[i.id]; render(); });

  // 8. 已确认 / 关键 / 批量
  const first=ev()[0];
  if(first){
    toggleRev(first.f.id); ok('标为已确认：表格显示已确认', (document.querySelector('#row-'+CSS.escape(first.id))||{}).textContent?.includes('已确认'), '');
    toggleRev(first.f.id); ok('改回待确认', E(first.id).rev==='todo', '');
    const ids=ev().slice(0,3).map(e=>e.id); ids.forEach(id=>S.checked.add(id)); batch('key');
    ok('批量标为关键', ids.every(id=>E(id).key), ''); ok('批量后清空勾选', S.checked.size===0, '');
  }

  // 9. 搜索
  base();
  const withQ=ev().find(e=>e.recs.some(r=>r.q && r.q.length>6));
  if(withQ){ const frag=withQ.recs.find(r=>r.q&&r.q.length>6).q.slice(1,6); S.q=frag; drawTable();
    ok(`搜索「${frag}」能找到 ${withQ.id}`, rows().includes(withQ.id), rows().join());
    ok('搜索结果都包含关键词', rows().every(id=>{ const e=E(id); return e && hay(e).includes(frag); }), ''); }
  S.q='丌丌丌不存在的词'; drawTable(); ok('搜索无结果时表格为空', rows().length===0, rows().length);
  S.q=''; drawTable();

  // 10. 筛选
  const t0=ev()[0]&&ev()[0].t;
  if(t0){ S.f.types=new Set([t0]); drawTable(); ok(`按类型筛选「${TYPES[t0].n}」`, rows().length>0 && rows().every(id=>E(id).t===t0), ''); S.f.types=new Set(); }
  S.f.conf=true; drawTable(); ok('只看记载不一', rows().every(id=>{ const e=E(id); return e.wasConflict||e.amtConflict||(e.amtVals&&e.amtVals.length>1); }), '');
  ok('只看记载不一：冲突事实都在', ev().filter(e=>e.conflict||e.amtConflict).every(e=>rows().includes(e.id)), '');
  S.f.conf=false; drawTable();

  // 11. 截至时点：时点之后的材料不出现
  [0,1,2,3,4,5].forEach(st => { S.stage=st; render();
    const leak=ev().flatMap(e=>e.recs).filter(r=>dStage(r.d)>st);
    ok(`截至「${STAGES[st]}」：事实不用此后才进入本案的材料`, leak.length===0, leak.map(r=>r.rid).join());
    const rl=reviewItems().filter(i=>(i.e&&i.e.recs.some(r=>dStage(r.d)>st))||(i.r&&dStage(i.r.d)>st)||(i.a&&dStage(i.a.d)>st));
    ok(`截至「${STAGES[st]}」：待审不提前出现`, rl.length===0, rl.map(i=>i.id).join());
    ok(`截至「${STAGES[st]}」：表格行数一致`, rows().length===visibleFacts().length, `${rows().length} vs ${visibleFacts().length}`);
    const cl=claimsVisible().filter(c=>dStage(c.d)>st); ok(`截至「${STAGES[st]}」：主张不提前出现`, cl.length===0, '');
  });
  S.stage=5; render();

  // 12. 每个事实的详情都能打开，且照录每条记载
  const bad=[]; ev().forEach(e=>{ try{ selectEv(e.id); const t=document.querySelector('#drawerIn')?.textContent||''; if(!e.recs.every(r=>!r.q||t.includes(r.q))) bad.push(e.id); }catch(err){ bad.push(e.id+':'+err.message); } });
  ok('每个事实详情可打开并照录全部记载', bad.length===0, bad.slice(0,5).join());
  // 13. 打开原文能高亮到引语
  const badDoc=[]; FACTS.slice(0,40).forEach(f=>f.recs.filter(r=>r.q).forEach(r=>{ openDoc(r.d,r.rid); const hs=[...document.querySelectorAll('#drawerIn .hit')]; if(![r.q,...(r.qx||[])].every(x=>hs.some(h=>h.textContent.includes(x)))) badDoc.push(r.rid); }));
  ok('点出处能在原文里高亮到引语', badDoc.length===0, badDoc.slice(0,5).join());
  S.drawer=null; render();

  // 14. 改材料属性 → 重算
  const st=DOCS.find(d=>d.kind==='statement' && ev().some(e=>e.stmtOnly && e.recs.every(r=>r.d===d.id)));
  if(st){ const before=ev().filter(e=>e.stmtOnly).length;
    S.docOv[st.id]={kind:'record'}; render();
    ok(`把 ${st.id} 改为书证：仅有陈述减少`, ev().filter(e=>e.stmtOnly).length<before || before===0, `${before}→${ev().filter(e=>e.stmtOnly).length}`);
    S.docOv={}; render(); }

  // 15. 清空所有裁决 → 回到初始
  ev().filter(e=>e.conflict).forEach(e=>adopt(e.f.id,e.strict[0].rid));
  reviewItems().filter(i=>i.k==='pack').forEach(i=>S.packRes[i.id]=1);
  Object.keys(INFER).forEach(k=>S.inferOk[k]='ok');
  resetDecisions(); render();
  ok('清空所有裁决后回到初始状态', snap()===S0, `${P0}→${pendingCount()}`);

  // 16. 导出：页面上的东西原样带走
  base();
  { let got=[]; const o=window.saveFile; window.saveFile=(n,d,m)=>{ got.push([n,d,m]); return Promise.resolve(true); };
    exportFacts(); exportNarr('table'); exportNarr('prose'); exportBase(); exportTL('svg');
    window.saveFile=o;
    ok('导出事实表：CSV 带表头、每个事实一行', got[0] && got[0][1].split('\r\n').length===(TL.tableRows||visibleFacts()).length+1, got[0]&&got[0][0]);
    ok('导出大事记表：Word 可打开、有表格', got[1] && /<table/.test(got[1][1]) && /\.doc$/.test(got[1][0]), '');
    ok('导出叙述：Word 可打开、按线索分段', got[2] && /<h2>/.test(got[2][1]), '');
    ok('导出底稿：可再次读入', got[3] && validateCase(JSON.parse(got[3][1])).length===0, '');
    ok('导出时间线图：SVG 无 NaN', !document.querySelector('#tlsvg') || (got[4] && !/NaN|undefined/.test(got[4][1])), ''); }

  // 17. 回放走完全程
  base(); const order=playOrder();
  if(order.length){ startPlay(); let steps=1, okp=true; for(let i=0;i<order.length+2;i++){ playStep(1); if(!document.querySelector('.playbar')) { okp=false; break; } }
    ok('回放可走到最后一步', okp && S.play===order.length, `${S.play}/${order.length}`); S.play=null; render(); }

  // 19. 疑似重复：合并与分开
  base();
  dupGroups().forEach(g=>{
    const n0=ev().length, nrec=g.fids.reduce((a,f)=>a+FACT[f].recs.length,0);
    S.dupRes[g.id]='merge'; render();
    const m=ev().filter(e=>g.fids.includes(e.f.id));
    ok(`合并 ${g.id}：只剩一个事实`, m.length===1 && ev().length===n0-(g.fids.length-1), `${m.length}`);
    ok(`合并 ${g.id}：记载一条不少`, m[0] && m[0].recs.length+FACT[g.fids[0]].recs.filter(r=>r.sus).length>=nrec, '');
    ok(`合并 ${g.id}：待审项消失`, !reviewItems().some(i=>i.id===g.id), '');
    delete S.dupRes[g.id]; render();
    ok(`撤销合并 ${g.id}`, ev().length===n0, '');
    S.dupRes[g.id]='sep'; render(); ok(`分开 ${g.id}：待审项消失、事实数不变`, !reviewItems().some(i=>i.id===g.id) && ev().length===n0, ''); delete S.dupRes[g.id]; render();
  });
  // 20. 数字对不上：已知悉
  arithItems().forEach(a=>{ S.arithRes[a.id]=1; render(); ok(`数字对不上 ${a.id} 已知悉`, !reviewItems().some(i=>i.id===a.id), ''); delete S.arithRes[a.id]; render(); });
  // 21. 事实经过
  base(); S.tab='narr'; S.nView='prose'; render();
  const th=narrThreads(); const inN=th.flatMap(t=>t.items.filter(i=>i.e).map(i=>i.e.id));
  const all=(()=>{ const k=S.stage; S.stage=5; invalidate(); const r=derive().map(e=>e.id); S.stage=k; invalidate(); return r; })();
  ok('事实经过：每个事实恰好出现一次', inN.length===all.length && all.every(id=>inN.includes(id)), `${inN.length}/${all.length}`);
  const allLines=DOCS.flatMap(d=>d.lines).join('\n');
  const qs=th.flatMap(t=>t.items.filter(i=>i.e).flatMap(i=>narrSentence(i.e).match(/「[^」]*」/g)||[])).map(q=>q.slice(1,-1)).filter(q=>!allLines.includes(q));
  ok('事实经过：「」里的文字都能在材料里找到', qs.length===0, qs.slice(0,3).join(' | '));
  S.stage=0; render(); const th0=narrThreads().flatMap(t=>t.items.filter(i=>i.e)).length; S.stage=5; render();
  ok('事实经过：不随「截至」变化', th0===all.length, `${th0}/${all.length}`);
  if((CASE.parties||[]).length){
    S.nName='role'; drawNarr(); const txt=$('#narr').textContent.replace(/「[^」]*」/g,'');
    const leak=(CASE.parties||[]).flatMap(p=>[p.name,p.short,...(p.alias||[])]).filter(Boolean).filter(n=>txt.includes(n));
    ok('称谓切到诉讼地位：引语外不再出现姓名', leak.length===0, leak.join('、'));
    S.nName='name'; drawNarr();
  }
  const fe=th.flatMap(t=>t.items.filter(i=>i.e))[0];
  if(fe){ const k='n:'+fe.e.id; editSent(k,fe.e.id); const gen=narrSentence(fe.e); const qq=(gen.match(/「[^」]*」/g)||[])[0];
    if(qq){ $('#nta').value=gen.replace(qq,'「被改过的引语」'); saveSent(k,fe.e.id); ok('改句子时删改引语会被拒绝', !(S.nEdit||{})[k], ''); drawNarr(); editSent(k,fe.e.id); }
    $('#nta').value=gen.replace(/。$/,'，此句已由律师修改。'); saveSent(k,fe.e.id);
    ok('改句子：保存并显示', !!(S.nEdit||{})[k] && $('#narr').textContent.includes('此句已由律师修改'), '');
    ok('改句子：写入变更记录', S.log.some(l=>l.what==='修改事实经过的一句'), '');
    resetSent(k);
  }
  if(th.length>1){ moveThread(th[1].id,-1); const t2=narrThreads(); ok('线索上移', t2[0].id===th[1].id, ''); mergeThread(t2[1].id,t2[0].id); const t3=narrThreads();
    ok('线索合并后事实一个不少', t3.flatMap(t=>t.items.filter(i=>i.e)).length===all.length && t3.length===th.length-1, ''); S.nOrder=null; S.nMerge={}; drawNarr(); }
  S.nView='table'; drawNarr();
  ok('大事记表：每个事实一行', document.querySelectorAll('#narr table.chron tbody tr:not(.cg):not(.cgap)').length===all.length, '');
  ok('大事记表：主要内容都是原文照录', [...document.querySelectorAll('#narr td.cc')].every(td=>(td.textContent.match(/「[^」]*」/g)||[]).every(q=>allLines.includes(q.slice(1,-1)))), '');
  S.tab='tl'; render();
  // 22. 程序状态筛选
  CONFIRM.forEach(c=>{ S.f.cf=new Set([c]); drawTable(); ok(`按程序状态「${c}」筛选`, rows().every(id=>E(id).recs.some(r=>dConf(r.d)===c)), ''); });
  S.f.cf=new Set(); drawTable();
  // 18. 切换案件后状态清零
  adopt; S.packRes['P:fake']=1; S.checked.add('x');
  return out;
}
"""

SWITCH_JS = r"""
(i) => { switchCase(i); return {pack: Object.keys(S.packRes).length, checked: S.checked.size, log: S.log.length, adopt: Object.keys(S.adopt).length}; }
"""


async def ui_clicks(pg):
    """真实点击（不调函数）：按钮、输入框、下拉框，验证界面响应"""
    res = []
    def ok(n, c, info=''): res.append({'name': n, 'ok': bool(c), 'info': '' if c else str(info)})
    await pg.evaluate("switchCase(CASES.findIndex(c=>c.id==='lending'))"); await pg.wait_for_timeout(150)
    p0 = await pg.evaluate('pendingCount()')
    await pg.get_by_role('button', name=f'{p0} 项待审').click(); await pg.wait_for_timeout(100)
    ok('点「N 项待审」打开待审抽屉', await pg.locator('#drawerIn .rcard').count() > 0)
    await pg.locator('#drawerIn .chip', has_text='日期冲突').click(); await pg.wait_for_timeout(80)
    kinds = await pg.evaluate("[...document.querySelectorAll('#drawerIn .rcard .rk')].map(x=>x.textContent)")
    ok('点「日期冲突」只剩冲突卡片', kinds and all('日期冲突' in k for k in kinds), kinds)
    await pg.locator('#drawerIn .rcard').first.get_by_role('button', name='采信此记载').first.click(); await pg.wait_for_timeout(120)
    p1 = await pg.evaluate('pendingCount()')
    both = await pg.evaluate("(()=>{ const f=Object.keys(S.adopt)[0]; return S.adopt && derive().some(e=>e.f.id===f && e.amtVals.length>1); })()")
    ok('点「采信此记载」后待审相应减少（同时有金额冲突时减二）', p1 == p0 - (2 if both else 1), f'{p0}→{p1}')
    ok('顶部按钮数字同步', await pg.get_by_role('button', name=f'{p1} 项待审').count() == 1)
    await pg.locator('#drawerIn .chip', has_text='全部').click(); await pg.wait_for_timeout(60)
    await pg.locator('#drawerIn .resolved button', has_text='撤销').first.click(); await pg.wait_for_timeout(100)
    ok('点「撤销」后待审复原', await pg.evaluate('pendingCount()') == p0)
    await pg.locator('#drawerIn .x').first.click(); await pg.wait_for_timeout(80)
    ok('点 × 关闭抽屉', await pg.evaluate('S.drawer===null'))
    await pg.fill('#q', '回单'); await pg.wait_for_timeout(80)
    n = await pg.locator('#tablewrap tbody tr:not(.claimrow)').count()
    ok('在搜索框输入「回单」后表格过滤', 0 < n < await pg.evaluate('derive().length'), n)
    await pg.fill('#q', ''); await pg.wait_for_timeout(60)
    await pg.locator('.stage button', has_text='接受咨询').click(); await pg.wait_for_timeout(80)
    ok('点「接受咨询」截断时点', await pg.evaluate('S.stage===0 && visibleFacts().length < derive().length || S.stage===0'))
    await pg.locator('.stage button', has_text='全部').click(); await pg.wait_for_timeout(60)
    tb0 = await pg.evaluate("[...document.querySelectorAll('.tltools > *')].map(e=>{const r=e.getBoundingClientRect();return Math.round(r.x)+','+Math.round(r.width)}).join('|')")
    await pg.locator('.lanebtn').click(); await pg.wait_for_timeout(60)
    await pg.locator('.pop .mi', has_text='按材料').click(); await pg.wait_for_timeout(80)
    ok('泳道菜单切到「按材料」', await pg.evaluate("S.lanes==='doc' && !!document.querySelector('#tlsvg')"))
    tb1 = await pg.evaluate("[...document.querySelectorAll('.tltools > *')].map(e=>{const r=e.getBoundingClientRect();return Math.round(r.x)+','+Math.round(r.width)}).join('|')")
    ok('切泳道后工具条按钮位置不动', tb0==tb1, f'{tb0} → {tb1}')
    await pg.locator('.lanebtn').click(); await pg.wait_for_timeout(60)
    await pg.locator('.pop .mi', has_text='按事件类型').click(); await pg.wait_for_timeout(60)
    for st in ['接受咨询','谈案','庭前','全部']:
        await pg.locator('.stage button', has_text=st).click(); await pg.wait_for_timeout(40)
        tb2 = await pg.evaluate("[...document.querySelectorAll('.tltools > *')].map(e=>{const r=e.getBoundingClientRect();return Math.round(r.x)+','+Math.round(r.width)}).join('|')")
        ok(f'点「{st}」工具条按钮位置不动', tb0==tb2, f'{tb0} → {tb2}')
    await pg.locator('#tablewrap tbody tr:not(.claimrow)').first.click(); await pg.wait_for_timeout(80)
    ok('点表格行打开事实详情', await pg.evaluate("S.drawer && S.drawer.kind==='fact'"))
    await pg.locator('#drawerIn .dref').first.click(); await pg.wait_for_timeout(100)
    ok('点出处编号打开原文并高亮', await pg.locator('#drawerIn .hit mark').count() > 0)
    await pg.keyboard.press('Escape'); await pg.wait_for_timeout(60)
    ok('Esc 从原文退回上一层（事实）', await pg.evaluate("S.drawer && S.drawer.kind==='fact'"))
    await pg.locator('#drawerIn .dhead .x').click(); await pg.wait_for_timeout(60)
    ok('点 × 关闭整个抽屉', await pg.evaluate('S.drawer===null && (S.dStack||[]).length===0'))
    # 回到原状：时间范围标签固定在概览条左侧，不挤动版面
    y0 = await pg.evaluate("document.querySelector('#tl').getBoundingClientRect().top")
    await pg.locator('#minisvg [data-year="2024"]').click(); await pg.wait_for_timeout(80)
    y1 = await pg.evaluate("document.querySelector('#tl').getBoundingClientRect().top")
    ok('选年份后时间线不上下跳动', abs(y1-y0)<0.5, f'{y0}→{y1}')
    ok('选年份后工具条显示当前时段', '2024.01' in await pg.locator('#rng').inner_text())
    await pg.locator('.tltools button', has_text='全时段').click(); await pg.wait_for_timeout(80)
    y2 = await pg.evaluate("document.querySelector('#tl').getBoundingClientRect().top")
    ok('点「全时段」回到全部，版面不动', await pg.evaluate("S.t0===EXT[0] && S.t1===EXT[1]") and abs(y2-y0)<0.5)
    await pg.locator('.stage button', has_text='谈案').click(); await pg.wait_for_timeout(60)
    y3 = await pg.evaluate("document.querySelector('#tl').getBoundingClientRect().top")
    ok('切截至阶段版面不动', abs(y3-y0)<0.5, f'{y0}→{y3}')
    await pg.locator('.stage button', has_text='全部').click(); await pg.wait_for_timeout(60)
    ok('点「全部」回到全部阶段', await pg.evaluate("S.stage===5"))
    await pg.fill('#q', '回单'); await pg.wait_for_timeout(60)
    await pg.evaluate("render()"); await pg.wait_for_timeout(60)
    ok('搜索后出现清空按钮与标签', await pg.locator('.search .qx').count()==1 and await pg.locator('#tstate .vchip').count()==1)
    await pg.locator('.search .qx').click(); await pg.wait_for_timeout(60)
    ok('清空搜索', await pg.evaluate("S.q===''") and await pg.locator('#tablewrap tbody tr:not(.claimrow)').count()==await pg.evaluate('visibleFacts().length'))
    await pg.evaluate("S.f.conf=true; S.f.key=true; render()"); await pg.wait_for_timeout(60)
    ok('筛选显示为标签', await pg.locator('#tstate .vchip').count()==2)
    await pg.locator('#tstate .vall').click(); await pg.wait_for_timeout(60)
    ok('全部清除筛选', await pg.evaluate("!S.f.conf && !S.f.key && activeFilters()===0"))
    await pg.locator('#tablewrap tbody tr:not(.claimrow)').first.click(); await pg.wait_for_timeout(60)
    await pg.locator('#drawerIn .dref').first.click(); await pg.wait_for_timeout(60)
    await pg.locator('#drawerIn .dback').click(); await pg.wait_for_timeout(60)
    ok('抽屉「返回」按钮退回事实', await pg.evaluate("S.drawer && S.drawer.kind==='fact'"))
    await pg.locator('#drawerIn .dhead .x').click(); await pg.wait_for_timeout(60)
    await pg.locator('.tabs10 button', has_text='事实经过').click(); await pg.wait_for_timeout(60)
    ok('点「事实经过」标签页', await pg.locator('#narr table.chron').count()==1)
    await pg.evaluate("moveThread(narrThreads()[1].id,-1)"); await pg.wait_for_timeout(60)
    await pg.locator('#narr .lnk', has_text='恢复线索原样').click(); await pg.wait_for_timeout(60)
    ok('线索恢复原样', await pg.evaluate("!narrModified()"))
    await pg.locator('.tabs10 button', has_text='时间线').click(); await pg.wait_for_timeout(60)
    await pg.locator('#tablewrap tbody tr:not(.claimrow) .stbtn').first.click(); await pg.wait_for_timeout(60)
    ok('点状态圈标为已确认', await pg.locator('#tablewrap tbody tr:not(.claimrow)').first.locator('.st-ok').count() == 1)
    await pg.locator('#tablewrap tbody tr:not(.claimrow) .cb').nth(0).check(); await pg.locator('#tablewrap tbody tr:not(.claimrow) .cb').nth(1).check()
    ok('勾选两行出现批量栏', await pg.locator('#batch .batch').count() == 1)
    await pg.locator('#batch button', has_text='标为关键').click(); await pg.wait_for_timeout(60)
    ok('批量标为关键后勾选清空', await pg.evaluate('S.checked.size===0'))
    await pg.locator('.tltools button', has_text='回放').click(); await pg.wait_for_timeout(60)
    ok('点回放出现回放条', await pg.locator('.playbar').count() == 1)
    ly0 = await pg.evaluate("document.querySelector('.legend').getBoundingClientRect().top")
    for _ in range(4): await pg.locator('.playbar .pstep[title^="下一步"]').click(); await pg.wait_for_timeout(40)
    ly1 = await pg.evaluate("document.querySelector('.legend').getBoundingClientRect().top")
    ok('回放点下一步，图的高度不变、不往下走', abs(ly1-ly0)<0.5, f'{ly0}→{ly1}')
    await pg.locator('.playbar .pstep[title^="上一步"]').click(); await pg.locator('.playbar .pstep[title^="上一步"]').click(); await pg.locator('.playbar .pstep[title^="上一步"]').click(); await pg.locator('.playbar .pstep[title^="上一步"]').click(); await pg.wait_for_timeout(40)
    await pg.keyboard.press('ArrowRight'); await pg.keyboard.press('ArrowRight'); await pg.wait_for_timeout(60)
    ok('方向键前进', await pg.evaluate('S.play===3'))
    await pg.keyboard.press('Escape'); await pg.wait_for_timeout(60)
    ok('Esc 退出回放', await pg.evaluate('S.play===null'))
    await pg.locator('#minisvg [data-year="2024"]').click(); await pg.wait_for_timeout(80)
    ok('概览条点年份选中整年', await pg.evaluate("fmtD(S.t0)==='2024年1月1日' && fmtD(S.t1)==='2025年1月1日'"), await pg.evaluate("[fmtD(S.t0),fmtD(S.t1)]"))
    await pg.locator('.tltools button', has_text='全时段').click(); await pg.wait_for_timeout(80)
    ok('点「全时段」回到全部', await pg.evaluate("S.t0===EXT[0] && S.t1===EXT[1]"))
    bb = await pg.locator('#mwin').bounding_box()
    await pg.mouse.move(bb['x']+100, bb['y']+15); await pg.mouse.down(); await pg.mouse.move(bb['x']+400, bb['y']+15, steps=5); await pg.mouse.up(); await pg.wait_for_timeout(80)
    ok('概览条在全景下拖选一段', await pg.evaluate("S.t0>EXT[0] && S.t1<EXT[1]"))
    gb = await pg.locator('#minisvg [data-h="r"]').bounding_box(); t1 = await pg.evaluate('S.t1')
    await pg.mouse.move(gb['x']+6, gb['y']+17); await pg.mouse.down(); await pg.mouse.move(gb['x']+120, gb['y']+17, steps=5); await pg.mouse.up(); await pg.wait_for_timeout(80)
    ok('拖右把手放大范围', await pg.evaluate('S.t1') > t1)
    await pg.dblclick('#minisvg'); await pg.wait_for_timeout(80)
    ok('双击概览条回到全部', await pg.evaluate("S.t0===EXT[0] && S.t1===EXT[1]"))
    await pg.locator('.h10 .btn', has_text='导出').click(); await pg.wait_for_timeout(80)
    items = await pg.locator('.pop .mi').all_inner_texts()
    ok('点「导出」出菜单：时间线图、事实表、大事记表、叙述、底稿', len(items)>=6 and any('时间线图' in x for x in items) and any('大事记表' in x for x in items), items)
    ok('导出菜单里没有受众向导', await pg.locator('.audb').count()==0)
    await pg.screenshot(path=os.path.join(tempfile.gettempdir(),'v8-ui_export.png'))
    await pg.keyboard.press('Escape')
    return res

async def run():
    async with async_playwright() as p:
        b = await p.chromium.launch(**({'executable_path':os.environ['CHROME']} if os.environ.get('CHROME') else {}), args=['--no-sandbox'])
        pg = await b.new_page(viewport={'width': 1440, 'height': 1000})
        errs = []
        pg.on('pageerror', lambda e: errs.append(str(e)))
        await pg.goto('file://' + HTML); await pg.wait_for_timeout(300)
        n = await pg.evaluate('CASES.length')
        total = fail = 0; allres = {}
        for i in range(n):
            errs.clear()
            cid = await pg.evaluate(f'(switchCase({i}), CASE.id)')
            try: res = await pg.evaluate(FLOWS_JS)
            except Exception as e: res = [{'name': '流程脚本崩溃', 'ok': False, 'info': str(e).split('\n')[0]}]
            st = await pg.evaluate(SWITCH_JS, (i + 1) % n)
            res.append({'name': '切换案件后裁决与勾选清零', 'ok': st['pack'] == 0 and st['checked'] == 0 and st['log'] == 0 and st['adopt'] == 0, 'info': json.dumps(st)})
            await pg.evaluate(f'switchCase({i})')
            if errs: res.append({'name': '页面报错', 'ok': False, 'info': ' | '.join(errs[:3])})
            bad = [r for r in res if not r['ok']]
            total += len(res); fail += len(bad); allres[cid] = res
            print(f'■ {cid}  {len(res)} 项，失败 {len(bad)}')
            for r in bad: print(f'   ✗ {r["name"]}  {r["info"]}')
        errs.clear()
        ui = await ui_clicks(pg)
        if errs: ui.append({'name':'页面报错','ok':False,'info':' | '.join(errs[:3])})
        bad=[r for r in ui if not r['ok']]; total+=len(ui); fail+=len(bad)
        print(f'■ 真实点击  {len(ui)} 项，失败 {len(bad)}')
        for r in bad: print(f'   ✗ {r["name"]}  {r["info"]}')
        print(f'合计 {total} 项检查，失败 {fail}')
        json.dump(allres, open(os.path.join(tempfile.gettempdir(),'v8-flows.json'), 'w'), ensure_ascii=False, indent=1)
        await b.close()

asyncio.run(run())
