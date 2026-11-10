"""案件看板大师 · 页面自测套件（需要 Playwright；先运行 python3 web/build.py --demo）
对每个案例：照录核验 → 按答案表对账 → 四种泳道、两种缩放的版面检查 → 各视图与导出 → 截图。
最后做改坏验证：故意改坏底稿，检查必须报错（每条守卫都必须能失败）。
用法：python3 tests/page_suite.py [html路径] [截图目录]
"""
import asyncio, json, sys, os
import os, tempfile
from playwright.async_api import async_playwright

HTML = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),'web','out','demo.html')
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(tempfile.gettempdir(),'v8-page-suite')

CHECK_JS = r"""
() => {
  const res = {};
  const A = CASE.answer || {};
  const set = a => JSON.stringify([...new Set(a)].sort());
  const ev = derive();
  const got = {
    conflicts: ev.filter(e=>e.conflict).map(e=>e.f.id),
    amountConflicts: ev.filter(e=>e.amtConflict).map(e=>e.f.id),
    undated: ev.filter(e=>e.undated).map(e=>e.f.id),
    suspects: FACTS.flatMap(f=>f.recs.filter(r=>r.sus).map(r=>r.rid)),
    inferTypes: [...new Set(FACTS.flatMap(f=>f.recs.map(r=>r.inf).filter(Boolean)))],
    packRules: reviewItems().filter(it=>it.k==='pack').map(it=>it.id.slice(2)),
    stmtOnly: ev.filter(e=>e.stmtOnly).map(e=>e.f.id),
    dups: dupGroups().map(g=>g.fids.join('+')),
    arith: arithItems().map(a=>a.id)
  };
  res.answer = {};
  for (const k of Object.keys(got)) {
    const exp = A[k] || [];
    res.answer[k] = { ok: set(exp) === set(got[k]), expected: [...new Set(exp)].sort(), got: [...new Set(got[k])].sort() };
  }
  res.validate = validateCase(CASE);
  res.counts = { facts: ev.length, pending: pendingCount(), items: reviewItems().length };
  return res;
}
"""

LAYOUT_JS = r"""
() => {
  const svg = document.querySelector('#tlsvg'); if (!svg) return {missing:true};
  const W = +svg.getAttribute('width');
  const html = svg.innerHTML;
  const nan = (html.match(/NaN|undefined|Infinity/g) || []).length;
  const texts = [...svg.querySelectorAll('text')].map(t => { const b = t.getBBox(); return {x:b.x, y:b.y, w:b.width, h:b.height, s:t.textContent}; })
     .filter(b => b.y > AXH-2 && b.x > LW && b.w > 0);
  let overlaps = [], outside = [];
  for (let i=0;i<texts.length;i++){ const a=texts[i];
    if (a.x < W - 14 && a.x + a.w > W - 13) outside.push(a.s);
    for (let j=i+1;j<texts.length;j++){ const b=texts[j];
      const ox = Math.min(a.x+a.w, b.x+b.w) - Math.max(a.x, b.x), oy = Math.min(a.y+a.h, b.y+b.h) - Math.max(a.y, b.y);
      if (ox > 2 && oy > 3) overlaps.push(a.s + ' ⟂ ' + b.s); } }
  return { nan, overlaps, outside: outside.slice(0,5), labels: texts.length };
}
"""

async def run():
    os.makedirs(OUT, exist_ok=True)
    report = {'cases': [], 'mutation': []}
    async with async_playwright() as p:
        b = await p.chromium.launch(**({'executable_path':os.environ['CHROME']} if os.environ.get('CHROME') else {}), args=['--no-sandbox'])
        pg = await b.new_page(viewport={'width': 1440, 'height': 1000})
        errs = []
        pg.on('pageerror', lambda e: errs.append(str(e)))
        await pg.goto('file://' + HTML); await pg.wait_for_timeout(400)
        n = await pg.evaluate('CASES.length')
        for i in range(n):
            errs.clear()
            cid = await pg.evaluate(f'(switchCase({i}), CASE.id)'); await pg.wait_for_timeout(200)
            r = {'id': cid}
            async def ev(js, default=None):
                try: return await pg.evaluate(js)
                except Exception as e:
                    errs.append('evaluate: '+str(e).split('\n')[0]); await pg.evaluate("() => { S.play=null; S.drawer=null; try{render()}catch(e){} }"); return default
            r.update(await ev(CHECK_JS, {}))
            await pg.screenshot(path=f'{OUT}/{cid}_01_timeline.png', full_page=False)
            lay = {}
            for mode in ['type', 'doc', 'actor', 'one']:
                for zoom in ['fit', 'zoom']:
                    await ev(f"""() => {{ S.lanes='{mode}'; S.more=true; render();
                        if('{zoom}'==='zoom'){{ const ev=derive().filter(e=>!e.undated).map(e=>e.sortKey).sort((a,b)=>a-b); if(ev.length){{ const m=ev[Math.floor(ev.length/2)]; const sp=(EXT[1]-EXT[0])/5; S.t0=m-sp/2; S.t1=m+sp/2; clampView(); drawTimeline(); }} }} }}""")
                    await pg.wait_for_timeout(60)
                    lay[f'{mode}/{zoom}'] = await ev(LAYOUT_JS, {'missing':True})
            r['layout'] = lay
            await pg.evaluate("() => { S.lanes='type'; S.more=false; fit(); render(); }")
            # 视图
            views = {}
            await pg.evaluate("() => { S.tab='matrix'; render(); }"); await pg.wait_for_timeout(80)
            views['matrix'] = await ev("() => !!document.querySelector('table.mx') || !!document.querySelector('#pane')")
            await pg.screenshot(path=f'{OUT}/{cid}_02_matrix.png')
            await pg.evaluate("() => { S.tab='tl'; render(); openReview(); }"); await pg.wait_for_timeout(80)
            views['review_cards'] = await ev("() => document.querySelectorAll('#drawerIn .rcard').length")
            await pg.screenshot(path=f'{OUT}/{cid}_03_review.png')
            views['table_rows'] = await ev("() => document.querySelectorAll('#tablewrap tbody tr').length")
            views['table_expected'] = await ev("() => visibleFacts().length + (S.showClaims?claimsVisible().length:0)")
            await pg.evaluate("() => { closeDrawer(); go('docs'); }"); await pg.wait_for_timeout(60)
            views['docs_rows'] = await ev("() => document.querySelectorAll('table.docs tbody tr').length")
            await pg.evaluate("() => go('work')")
            # 回放
            views['play'] = await ev("() => { try { startPlay(); playStep(1); playStep(1); const ok = S.play!==null || playOrder().length===0; S.play=null; render(); return ok; } catch(e) { return 'ERR '+e.message; } }")
            # 导出向导
            views['export'] = await ev("""() => { try { const t=tlSVG(); const nan=t?(t.svg.match(/NaN|undefined/g)||[]).length:0; return {ok:!!t||!document.querySelector('#tlsvg'), nan}; } catch(e) { return 'ERR '+e.message; } }""")
            # 截至时点
            views['stages'] = await ev("() => [0,1,2,5].map(st => { S.stage=st; render(); return visibleFacts().length; })")
            await pg.evaluate("() => { S.stage=5; render(); }")
            r['views'] = views
            r['page_errors'] = list(errs)
            report['cases'].append(r)
        # 改坏验证
        muts = [
          ('改一个引语的字，照录核验必须报错', "() => { const c=JSON.parse(JSON.stringify(CASES.find(c=>c.id==='lending'))); c.facts[0].recs[0].q=c.facts[0].recs[0].q.replace('李四','李肆'); return validateCase(c).length>0; }"),
          ('引用不存在的材料，必须报错', "() => { const c=JSON.parse(JSON.stringify(CASES.find(c=>c.id==='sale'))); c.facts[1].recs[0].d='S-99'; return validateCase(c).length>0; }"),
          ('抹平一处日期冲突，对账必须不过', "() => { const c=JSON.parse(JSON.stringify(CASES.find(c=>c.id==='lending'))); c.id='mut'; const f=c.facts.find(f=>f.id==='LF06'); f.recs.forEach(r=>{ if(r.s) r.s='2023-10-08'; }); CASES.push(c); loadCase(c); const got=derive().filter(e=>e.conflict).map(e=>e.f.id); CASES.pop(); return !got.includes('LF06'); }"),
          ('抹平一处金额冲突，对账必须不过', "() => { const c=JSON.parse(JSON.stringify(CASES.find(c=>c.id==='lending'))); const f=c.facts.find(f=>f.id==='LF09'); f.recs.forEach(r=>r.amt=2); loadCase(c); return !derive().some(e=>e.amtConflict&&e.f.id==='LF09'); }"),
          ('标题引语改一字，照录核验必须报错', "() => { const c=JSON.parse(JSON.stringify(CASES.find(c=>c.id==='lease'))); c.facts.find(f=>f.id==='RF07').title='吴晓梅称「下周四一起转」'; return validateCase(c).length>0; }"),
          ('改动借条小写金额，数字对不上必须报出', "() => { const c=JSON.parse(JSON.stringify(CASES.find(c=>c.id==='lending'))); c.materials[0].lines[1]=c.materials[0].lines[1].replace('¥500,000','¥510,000'); loadCase(c); return arithItems().length===1; }"),
          ('删掉转账凭证标签，领域规则必须多报一条', "() => { const c=JSON.parse(JSON.stringify(CASES.find(c=>c.id==='lending'))); c.materials.find(m=>m.id==='L-04').tags=[]; loadCase(c); return reviewItems().filter(i=>i.k==='pack').length>1; }"),
        ]
        for name, js in muts:
            try: ok = await pg.evaluate(js)
            except Exception as e: ok = 'ERR ' + str(e)
            report['mutation'].append({'name': name, 'caught': ok})
        await b.close()
    json.dump(report, open(f'{OUT}/report.json', 'w'), ensure_ascii=False, indent=1)
    # 摘要
    bad = 0
    for r in report['cases']:
        probs = []
        for k, v in r['answer'].items():
            if not v['ok']: probs.append(f"答案表 {k}: 期望 {v['expected']} 实得 {v['got']}")
        if r['validate']: probs.append(f"照录核验 {len(r['validate'])} 处: {r['validate'][:2]}")
        for k, v in r['layout'].items():
            if v.get('missing'): continue
            if v['nan']: probs.append(f'{k} 出现 NaN/undefined ×{v["nan"]}')
            if v['overlaps']: probs.append(f'{k} 标签重叠 {len(v["overlaps"])} 处，如 {v["overlaps"][:2]}')
            if v['outside']: probs.append(f'{k} 标签越界 {v["outside"][:2]}')
        vw = r['views']
        if vw['table_rows'] != vw['table_expected']: probs.append(f"表格行数 {vw['table_rows']} ≠ 应有 {vw['table_expected']}")
        if vw['play'] is not True: probs.append(f"回放 {vw['play']}")
        if not (isinstance(vw['export'], dict) and vw['export']['ok'] and not vw['export']['nan']): probs.append(f"导出 {vw['export']}")
        if r['page_errors']: probs.append(f"脚本错误 {r['page_errors'][:2]}")
        bad += bool(probs)
        print(f"■ {r['id']}  事实 {r['counts']['facts']}  待审 {r['counts']['pending']}  截至各阶段 {vw['stages']}")
        for x in probs: print('   ✗', x)
        if not probs: print('   ✓ 全部通过')
    print('改坏验证：')
    for m in report['mutation']: print('  ', '✓' if m['caught'] is True else '✗', m['name'], '' if m['caught'] is True else m['caught'])
    print(f'有问题的案例：{bad} / {len(report["cases"])}')

asyncio.run(run())
