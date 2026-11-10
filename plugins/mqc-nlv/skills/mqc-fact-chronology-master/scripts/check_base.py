# -*- coding: utf-8 -*-
"""底稿检查：只用 Python 标准库。

用法：
    python scripts/check_base.py 案件.base.json

逐条核对底稿与材料原文对得上：引语照录、日期原文照录、编号互相引用、线索覆盖全部事实等。
有「错误」时退出码为 1，必须改到没有错误再生成页面；「提醒」不阻断，但要逐条看过。
每次运行都在底稿同目录的 run-log.md 末尾追加一段记录。
"""
import json, re, sys, os, datetime
if hasattr(sys.stdout, 'reconfigure'):  # 中文 Windows（GBK）下打印不因个别字符崩掉
    sys.stdout.reconfigure(errors='replace'); sys.stderr.reconfigure(errors='replace')

KIND = {'statement': '当事人陈述', 'record': '书证', 'edata': '电子数据', 'testimony': '证人证言'}
CONFIRM = ['未提交', '已提交', '已质证', '法院认定', '生效确认', '未被采纳']
STAGES = ['接受咨询', '谈案', '庭前', '庭审时', '庭后', '结案后']
CORE_TYPES = ['comm', 'meeting', 'agree', 'pay', 'perf', 'notice', 'decision', 'filing', 'other']
PACK_EXTRA = {'lending': ['guar']}
PACKS = ['general', 'construction', 'lending', 'sale', 'lease', 'tort', 'family', 'labor']
PREC = ['day', 'month', 'range', 'approx', 'arange', 'none']
STATE = ['occ', 'agr', 'est']
# 事实标题要中立：这些带评价的字眼不进标题（可以出现在「」照录的引语里）
LOADED = ['违约', '恶意', '拒不', '故意', '显然', '明显', '非法', '欺诈', '虚假', '抵赖', '狡辩', '无理', '理应', '应当', '必须']
DATE_RE = re.compile(r'^\d{4}-\d{2}(-\d{2})?$')
# 判决书、笔录里的这些段落是当事人的说法，不是书证；页面用同一口径
STMT_HINT = ('诉称', '辩称', '答辩', '质证', '拟证明', '陈述', '主张', '代理意见', '申请书')


def valid_date(s):
    if not isinstance(s, str) or not DATE_RE.match(s):
        return False
    try:
        if len(s) == 7:
            datetime.date(int(s[:4]), int(s[5:7]), 1)
        else:
            datetime.date(int(s[:4]), int(s[5:7]), int(s[8:10]))
        return True
    except ValueError:
        return False


def check(c):
    E, W = [], []
    err, warn = E.append, W.append
    if not isinstance(c, dict):
        return ['底稿最外层必须是一个对象'], [], {}
    for k in ('id', 'title'):
        if not c.get(k):
            err(f'缺 {k}')
    pack = c.get('pack', 'general')
    if pack not in PACKS:
        err(f'pack「{pack}」不认识，可用：{"、".join(PACKS)}')
    types = CORE_TYPES + PACK_EXTRA.get(pack, [])

    parties = c.get('parties') or []
    for i, p in enumerate(parties):
        if not p.get('name') or not p.get('role'):
            err(f'parties 第 {i+1} 项缺 name 或 role')

    mats = c.get('materials') or []
    docs = {}
    for m in mats:
        mid = m.get('id')
        if not mid:
            err('有材料缺 id'); continue
        if mid in docs:
            err(f'材料编号重复：{mid}')
        docs[mid] = m
        if not isinstance(m.get('lines'), list) or not m['lines']:
            err(f'{mid} 缺 lines（材料原文，逐行照录）')
        if not m.get('name'):
            err(f'{mid} 缺 name')
        if m.get('kind') not in KIND:
            err(f'{mid} 的 kind「{m.get("kind")}」不认识，可用：{"、".join(KIND)}')
        if m.get('confirm') and m['confirm'] not in CONFIRM:
            err(f'{mid} 的 confirm「{m["confirm"]}」不认识，可用：{"、".join(CONFIRM)}')
        st = m.get('stage', 0)
        if not isinstance(st, int) or not 0 <= st < len(STAGES):
            err(f'{mid} 的 stage 应为 0–5 的整数（{"、".join(f"{i}={s}" for i, s in enumerate(STAGES))}）')
        pg, rd = m.get('pages'), m.get('read')
        if isinstance(pg, int) and isinstance(rd, int) and rd < pg:
            warn(f'{mid} 共 {pg} 页只读了 {rd} 页：漏读的部分要补读，或在 run-log 里写明原因')
        if m.get('medium') == 'image':
            warn(f'{mid} 是图片或扫描件：lines 是识读出来的，交付前要人工对照原件')
    if not mats:
        err('materials 为空')

    def in_doc(d, text):
        return d in docs and any(text in l for l in docs[d].get('lines', []))

    def raw_parts_ok(d, raw):
        # 区间可由两处原文拼成，如「2024.6.3 至 2024.7.14」；括号里的天数等是注记，不要求照录
        core = re.sub(r'（[^）]*）|\([^)]*\)', '', raw)
        parts = [x.strip() for x in re.split(r'至|起，|起|，|、|—|–|~|/|／', core) if re.search(r'\d|[一二三四五六七八九十〇零]', x or '')]
        return bool(parts) and all(in_doc(d, x) for x in parts)

    infer = c.get('inferences') or {}
    for k, v in infer.items():
        if not v.get('n') or not v.get('basis'):
            err(f'inferences.{k} 缺 n（推断类别）或 basis（推断依据）')

    def is_stmt(r):
        if r.get('stmt') is False:
            return False
        if r.get('stmt') is True or docs.get(r.get('d'), {}).get('kind') == 'statement':
            return True
        probe = (r.get('loc') or '') + ' ' + (r.get('q') or '')[:8]  # 位置写明，或引语以「拟证明」「原告诉称」等开头
        return any(k in probe for k in STMT_HINT)

    facts = c.get('facts') or []
    fids = {}
    stmt_only, cited_by, natures = [], {}, {}
    nrec = nq = 0
    for f in facts:
        fid = f.get('id')
        if not fid:
            err('有事实缺 id'); continue
        if fid in fids:
            err(f'事实编号重复：{fid}')
        fids[fid] = f
        title = f.get('title') or ''
        if not title:
            err(f'{fid} 缺 title')
        if f.get('t') not in types:
            err(f'{fid} 的类型 t「{f.get("t")}」不认识，可用：{"、".join(types)}')
        if f.get('state', 'occ') not in STATE:
            err(f'{fid} 的 state 应为 occ（已发生）/agr（约定）/est（推定）')
        bare = re.sub(r'「[^」]*」', '', title)
        if len(bare) > 22:
            warn(f'{fid} 标题偏长（{len(bare)} 字）：一个事实一件事，长的内容放进引语')
        for w in LOADED:
            if w in bare:
                warn(f'{fid} 标题含评价性字眼「{w}」：标题只写发生了什么')
        recs = f.get('recs') or []
        if not recs:
            err(f'{fid} 没有任何记载（recs）：每个事实都要能回到原文')
        for i, r in enumerate(recs, 1):
            nrec += 1
            tag = f'{fid} 第{i}条记载'
            d = r.get('d')
            if d not in docs:
                err(f'{tag} 引用了不存在的材料 {d}'); continue
            q = r.get('q') or ''
            if not q:
                err(f'{tag} 缺引语 q')
            elif not in_doc(d, q):
                err(f'{tag} 的引语在 {d} 原文里找不到（必须逐字照录）：「{q[:30]}」')
            else:
                nq += 1
            for x in r.get('qx') or []:
                if not in_doc(d, x):
                    err(f'{tag} 的补充引语在 {d} 原文里找不到：「{x[:30]}」')
            p = r.get('p', 'day')
            if p not in PREC:
                err(f'{tag} 的 p「{p}」不认识，可用：{"、".join(PREC)}')
            if p != 'none':
                sv = r.get('s')
                if not valid_date(sv):
                    err(f'{tag} 的 s 不是有效日期（YYYY-MM-DD；仅到月可写 YYYY-MM）：{sv}')
                elif len(sv) == 7 and p != 'month':
                    err(f'{tag} 的精度是 {p}，s 必须写到日（YYYY-MM-DD）：{sv}；只有 p=month 可以写 YYYY-MM')
                if p in ('range', 'arange'):
                    if not valid_date(r.get('e')):
                        err(f'{tag} 是区间，缺有效的 e（止日）')
                    elif valid_date(r.get('s')) and r['e'] < r['s']:
                        err(f'{tag} 止日早于起日')
                raw = r.get('raw') or ''
                if not raw:
                    err(f'{tag} 缺 raw（日期在原文里的写法）')
                elif not in_doc(d, raw) and not raw_parts_ok(d, raw) and not r.get('inf'):
                    err(f'{tag} 的日期原文「{raw}」在 {d} 里找不到；推出来的日期要写 inf 并在 inferences 里写依据')
                elif in_doc(d, raw) and not any(raw in (x or '') for x in [q] + (r.get('qx') or [])):
                    err(f'{tag} 的引语没有包含日期原文「{raw}」，读者看不到日期出处（把那一行放进 q 或 qx）')
            if r.get('inf') and r['inf'] not in infer:
                err(f'{tag} 的 inf「{r["inf"]}」在 inferences 里没有定义')
            if r.get('sus') and not r.get('susWhy'):
                err(f'{tag} 标了可疑日期 sus，缺 susWhy（为什么可疑）')
            if r.get('amt') is not None and not isinstance(r['amt'], (int, float)):
                err(f'{tag} 的 amt 必须是数字（单位见底稿 unit，默认「元」）')
        for qt in re.findall(r'「([^」]*)」', title + (f.get('narr') or '')):
            if not any(in_doc(r.get('d'), qt) for r in recs):
                err(f'{fid} 标题或叙述里的引语「{qt}」在其出处原文里找不到')
        if recs and f.get('t') != 'filing' and all(is_stmt(r) for r in recs):
            stmt_only.append(fid)
        cited_by.setdefault(fid, set()).update(r.get('d') for r in recs)
        for r in recs:
            if r.get('amt') is not None and r.get('nature'):
                natures.setdefault(round(float(r['amt']), 2), []).append((fid, r['nature'], r.get('d')))

    for x in c.get('claims') or []:
        if x.get('d') not in docs:
            err(f'主张 {x.get("id")} 引用了不存在的材料 {x.get("d")}')
        elif x.get('q') and not in_doc(x['d'], x['q']):
            err(f'主张 {x.get("id")} 的引语在原文里找不到')
    for r in c.get('relations') or []:
        if not isinstance(r, list) or len(r) < 2:
            err('relations 每项应为 [起点事实, 终点事实, 说明]'); continue
        for k in r[:2]:
            if k not in fids:
                err(f'relations 里的事实 {k} 不存在')
    for a in c.get('attention') or []:
        if a.get('d') not in docs:
            err(f'需留意 {a.get("id")} 引用了不存在的材料')
        elif a.get('q') and not in_doc(a['d'], a['q']):
            err(f'需留意 {a.get("id")} 的引语在原文里找不到')
    seen = {}
    for t in c.get('threads') or []:
        for k in t.get('facts') or []:
            if k not in fids:
                err(f'线索「{t.get("title")}」里的事实 {k} 不存在')
            elif k in seen:
                err(f'事实 {k} 同时放进了线索「{seen[k]}」和「{t.get("title")}」')
            seen[k] = t.get('title')
    if c.get('threads'):
        miss = [k for k in fids if k not in seen]
        if miss:
            warn(f'这些事实没有放进任何线索，事实经过里会单独成段：{"、".join(miss)}')
    else:
        warn('没有 threads（线索）：事实经过会按时间排成一段，建议按事情的线索分段')

    # 没有被任何记载、主张、需留意引用的材料
    used = set(d for v in cited_by.values() for d in v)
    used |= {x.get('d') for x in (c.get('claims') or [])} | {a.get('d') for a in (c.get('attention') or [])}
    for mid, m in docs.items():
        if mid not in used and not m.get('background') and not m.get('sameAs'):
            warn(f'材料 {mid}（{m.get("name","")}）没有被任何记载引用：是不含事实的背景材料（请标 background: true），还是漏读了')
    # 副本、脱敏稿：不得单独支撑一个事实
    copies = {mid: m['sameAs'] for mid, m in docs.items() if m.get('sameAs')}
    for mid, orig in copies.items():
        if orig not in docs:
            err(f'{mid} 的 sameAs 指向不存在的材料 {orig}')
            continue
        both = [k for k, v in cited_by.items() if mid in v and orig in v]
        alone = [k for k, v in cited_by.items() if v == {mid}]
        if both:
            warn(f'{mid} 是 {orig} 的副本，{"、".join(both)} 同时引用了两者（页面不按两份独立证据看待）')
        for k in alone:
            err(f'{k} 只由副本 {mid} 支撑：副本不得单独支撑一个事实，请改挂原件 {orig}')
    # 同一笔金额、不同性质
    for amt, lst in natures.items():
        ns = {n for _, n, _ in lst}
        if len(ns) > 1:
            warn(f'金额 {amt:,} 在不同记载里性质不同（{"；".join(f"{k}·{d}记「{n}」" for k, n, d in lst)}）：确认是同一笔还是两笔')
    if stmt_only:
        warn(f'这些事实全部记载都出自当事人陈述或诉讼中的陈述段落，页面写成「据…陈述」并列入待审：{"、".join(stmt_only)}')

    stats = {'材料': len(mats), '事实': len(facts), '记载': nrec, '引语核对通过': nq,
             '推断日期': sum(1 for f in facts for r in f.get('recs', []) if r.get('inf')),
             '可疑日期': sum(1 for f in facts for r in f.get('recs', []) if r.get('sus')),
             '无日期事实': sum(1 for f in facts if all(r.get('p') == 'none' for r in f.get('recs', [])) and f.get('recs')),
             '仅陈述事实': len(stmt_only),
             '主张': len(c.get('claims') or []), '线索': len(c.get('threads') or []),
             '待读材料': len(c.get('pending') or [])}
    return E, W, stats


HEAD = """# 运行记录

> 「读取记录」「遇到的问题」由 Agent 填写；其后各段由脚本自动追加，同样的结果不重复记。最终以最后一次「生成页面」为准。

## 读取记录

| 编号 | 材料 | 原文件 | 页数 | 读了 | 记载 | 拿不准的地方 |
|---|---|---|---|---|---|---|

## 遇到的问题

（逐条写：哪里规矩不够用、哪里不确定怎么处理、怎么处理的）

---
"""


SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def log(path, step, lines):
    d = os.path.dirname(os.path.abspath(path))
    if os.path.commonpath([d, SKILL_DIR]) == SKILL_DIR:
        d = os.getcwd()  # 用技能自带的范例时，记录写到当前工作目录，不写进技能目录
    p = os.path.join(d, 'run-log.md')
    if not os.path.exists(p):
        open(p, 'w', encoding='utf-8').write(HEAD)
    body = '\n'.join(lines) + '\n'
    old = open(p, encoding='utf-8').read()
    last = old.rsplit('\n## ', 1)[-1] if '\n## ' in old else ''
    if last.split('\n', 1)[-1] == body and (' · ' + step) in last.split('\n', 1)[0]:
        return p  # 与上一段完全相同，不重复追加
    with open(p, 'a', encoding='utf-8') as fh:
        fh.write(f'\n## {datetime.datetime.now():%Y-%m-%d %H:%M:%S} · {step}\n')
        fh.write(body)
    return p


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ('-h', '--help'):
        print(__doc__); sys.exit(0 if len(sys.argv) > 1 else 2)
    path = sys.argv[1]
    try:
        c = json.load(open(path, encoding='utf-8'))
    except Exception as e:
        print(f'读不出底稿：{e}'); log(path, '检查底稿', [f'- 读不出底稿：{e}']); sys.exit(1)
    E, W, st = check(c)
    out = [f'- 底稿：{os.path.basename(path)}（{c.get("title", "")}）',
           '- 统计：' + '，'.join(f'{k} {v}' for k, v in st.items()),
           f'- 错误 {len(E)} 条，提醒 {len(W)} 条']
    out += [f'  - 错误：{x}' for x in E] + [f'  - 提醒：{x}' for x in W]
    print('\n'.join(out))
    lp = log(path, '检查底稿' + ('（未通过）' if E else ''), out)
    print(f'\n已记入 {lp}')
    sys.exit(1 if E else 0)


if __name__ == '__main__':
    main()
