# -*- coding: utf-8 -*-
"""一条命令：拼底稿 → 检查 → 生成页面。

用法：
    python scripts/make.py 工作目录

工作目录里要有 ingest.py 产出的「清单.json」和 Agent 写的「事实.json」。
Agent 只写事实，不重抄原文：材料的原文由清单按行号取，引语可以只写行号。
每次运行：
  1. 按「事实.json」拼出底稿（材料原文从清单取；引语按行号取或自动校正空格、全半角差异）；
  2. 沿用工作目录里旧底稿的律师裁决（decisions）、改动记录（changes）、待读材料（pending）；
  3. 检查；没有错误就生成页面。
有错误时只需改「事实.json」里报到的那几条，再运行本命令。
"""
import json, os, re, sys, glob, unicodedata
if hasattr(sys.stdout, 'reconfigure'):  # 中文 Windows（GBK）下打印不因个别字符崩掉
    sys.stdout.reconfigure(errors='replace'); sys.stderr.reconfigure(errors='replace')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check_base import check, log

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, '..', 'assets', 'template.html')
PAGE = re.compile(r'^#第(\d+)页')


def norm(t):
    t = unicodedata.normalize('NFKC', t)
    return re.sub(r'\s+', '', t)


def locate(line, q):
    """在一行里找与 q 只差空格、全半角的那一段，返回原文的写法；找不到返回 None。"""
    nq = norm(q)
    if not nq:
        return None
    idx = []  # 原文每个非空白字符的位置
    s = ''
    for i, ch in enumerate(line):
        n = norm(ch)
        for c in n:
            s += c; idx.append(i)
    k = s.find(nq)
    if k < 0 or s.find(nq, k + 1) >= 0:
        return None
    return line[idx[k]: idx[k + len(nq) - 1] + 1]


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ('-h', '--help'):
        print(__doc__); sys.exit(0 if len(sys.argv) > 1 else 2)
    work = os.path.abspath(sys.argv[1])
    def load(name, hint):
        p = os.path.join(work, name)
        if not os.path.exists(p):
            print(f'工作目录里没有「{name}」：{hint}'); sys.exit(2)
        try:
            return json.load(open(p, encoding='utf-8'))
        except json.JSONDecodeError as e:
            ls = open(p, encoding='utf-8').read().split('\n')
            near = ls[e.lineno - 1][max(0, e.colno - 30): e.colno + 10] if e.lineno <= len(ls) else ''
            print(f'「{name}」不是合法的 JSON：第 {e.lineno} 行第 {e.colno} 列，{e.msg}。附近：{near}\n常见原因：漏了逗号、多了逗号、引号里有未转义的英文双引号（原文里的 " 请写成 \\" 或改用「」）。')
            sys.exit(1)
    src = load('清单.json', '先运行 ingest.py')
    SRC = {s['id']: s for s in src['sources']}
    fx = load('事实.json', '先读原文，按 SKILL.md 第 2 步写好')
    fixes, errs = [], []

    # —— 材料：原文从清单按行取 ——
    mats, MAP = [], {}
    defs = fx.get('materials') or [{'id': f'L-{i+1:02d}', 'src': s['id']} for i, s in enumerate(src['sources'])]
    for m in defs:
        m = dict(m)
        own = 'lines' in m
        sid = m.pop('src', None)
        a, b = m.pop('from', None), m.pop('to', None)
        if sid:
            if sid not in SRC:
                errs.append(f'材料 {m.get("id")} 的 src「{sid}」不在清单里'); continue
            s = SRC[sid]; a = a or 1; b = b or len(s['lines'])
            if 'lines' not in m:
                m['lines'] = s['lines'][a - 1:b]
            m.setdefault('file', s['file'])
            m.setdefault('name', os.path.splitext(os.path.basename(s['file']))[0])
            pages = [int(PAGE.match(l).group(1)) for l in s['lines'][a - 1:b] if PAGE.match(l)]
            if pages:
                m.setdefault('pages', len(pages)); m.setdefault('read', len(pages))
                if set(pages) & set(s.get('blank_pages') or []):
                    m.setdefault('medium', 'image')
            if own and s.get('blank_pages'):
                m.setdefault('medium', 'image')
            MAP[m['id']] = (s, a, b, own)
        m.setdefault('kind', 'record')
        mats.append(m)
    MID = {m['id']: m for m in mats}
    # 拆分检查：一个源文件拆成几份材料时，有没有漏掉、重叠的行
    warns = []
    for sid, s in SRC.items():
        rs = sorted((v[1], v[2], k) for k, v in MAP.items() if v[0] is s)
        if not rs:
            warns.append(f'源文件 {sid}（{s["file"]}）没有对应任何材料：是漏了，还是不需要？不需要也请登记一份并标 background: true')
            continue
        if len(rs) > 1:
            body = [i for i, l in enumerate(s['lines'], 1) if not PAGE.match(l)]
            cov = set()
            for a, b, k in rs:
                cov |= set(range(a, b + 1))
            miss = [i for i in body if i not in cov]
            if miss:
                warns.append(f'{sid} 拆成了 {"、".join(k for _, _, k in rs)}，但第 {miss[0]}–{miss[-1]} 行之间有 {len(miss)} 行没归入任何材料')
            for (a1, b1, k1), (a2, b2, k2) in zip(rs, rs[1:]):
                if a2 <= b1:
                    warns.append(f'{k1} 与 {k2} 的行范围重叠（{sid} 第 {a2}–{b1} 行）')

    def page_of(s, ln):
        for i in range(ln - 1, -1, -1):
            g = PAGE.match(s['lines'][i])
            if g:
                return f'第{g.group(1)}页'
        return ''

    MERGE = {}  # 材料编号 -> [(起行, 止行)]：引语跨了排版折行时，把这几行接成一行

    def span(lines, q, start=None):
        """引语跨了几行（PDF 排版折行、标题与正文分行）时，在相邻 2–4 行接起来的文字里找。返回 (起行号, 止行号, 原文写法)。"""
        rng = [start] if start else range(1, len(lines) + 1)
        for i in rng:
            for n in (2, 3, 4):
                if i - 1 + n > len(lines):
                    break
                joined = ''.join(l.lstrip('#') for l in lines[i - 1:i - 1 + n])
                hit = q if q in joined else locate(joined, q)
                if hit:
                    return i, i + n - 1, hit
        return None

    def resolve(r, tag):
        d = r.get('d')
        if d not in MID:
            return
        lines = MID[d].get('lines') or []
        own = d not in MAP or MAP[d][3]  # 材料原文由 Agent 自己写（扫描件识读）
        base_ln = 1 if own else MAP[d][1]  # 材料第一行在源文件里的行号
        if 'ln' in r:
            ln = r.pop('ln')
            if own:
                if not 1 <= ln <= len(lines):
                    errs.append(f'{tag}：ln {ln} 超出 {d} 的行数'); return
                line = lines[ln - 1]
            else:
                s, a, b, _ = MAP[d]
                if not a <= ln <= b:
                    errs.append(f'{tag}：ln {ln} 不在 {d} 的范围（{s["id"]} 第 {a}–{b} 行）'); return
                line = s['lines'][ln - 1]
                if not r.get('loc'):
                    r['loc'] = (page_of(s, ln) + f' 第{ln}行').strip()
            line = line.lstrip('#')
            if not r.get('q'):
                r['q'] = line
            elif r['q'] not in line:
                hit = locate(line, r['q'])
                if hit:
                    fixes.append(f'{tag}：引语按原文校正「{r["q"][:16]}」→「{hit[:16]}」'); r['q'] = hit
                else:
                    sp = span(lines, r['q'], ln - base_ln + 1) or span(lines, r['q'], max(1, ln - base_ln))
                    if sp:
                        MERGE.setdefault(d, []).append((sp[0], sp[1])); fixes.append(f'{tag}：引语跨了 {sp[1]-sp[0]+1} 行，已把这几行接成一行'); r['q'] = sp[2]
        elif r.get('q') and not any(r['q'] in l for l in lines):
            done = False
            for l in lines:
                hit = locate(l, r['q'])
                if hit:
                    fixes.append(f'{tag}：引语按原文校正「{r["q"][:16]}」→「{hit[:16]}」'); r['q'] = hit; done = True; break
            if not done:
                sp = span(lines, r['q'])
                if sp:
                    MERGE.setdefault(d, []).append((sp[0], sp[1])); fixes.append(f'{tag}：引语跨了 {sp[1]-sp[0]+1} 行，已把这几行接成一行'); r['q'] = sp[2]
        qx = []
        for x in r.pop('qx_ln', []) or []:
            if own:
                if 1 <= x <= len(lines): qx.append(lines[x - 1].lstrip('#'))
            else:
                s, a, b, _ = MAP[d]
                if a <= x <= b: qx.append(s['lines'][x - 1].lstrip('#'))
                else: errs.append(f'{tag}：qx_ln {x} 不在 {d} 的范围')
        if qx:
            r['qx'] = (r.get('qx') or []) + qx
        if r.get('raw') and not any(r['raw'] in (y or '') for y in [r.get('q')] + (r.get('qx') or [])):
            for l in lines:
                hit = locate(l, r['raw'])
                if hit and hit in (r.get('q') or ''):
                    fixes.append(f'{tag}：日期原文按原文校正「{r["raw"]}」→「{hit}」'); r['raw'] = hit; break

    for f in fx.get('facts') or []:
        for i, r in enumerate(f.get('recs') or [], 1):
            resolve(r, f'{f.get("id")} 第{i}条记载')
    for k in ('claims', 'attention', 'arith'):
        for x in fx.get(k) or []:
            resolve(x, f'{k} {x.get("id")}')
            for c in x.get('ctx') or []:
                resolve(c, f'{k} {x.get("id")} 的对照')
    for f in fx.get('facts') or []:
        for c in f.get('ctx') or []:
            resolve(c, f'{f.get("id")} 的对照')

    for d, spans in MERGE.items():
        L = MID[d]['lines']; keep = [True] * len(L); U = []
        for a, b in sorted(set(spans)):  # 相互重叠的几段并成一段
            if U and a <= U[-1][1]:
                U[-1][1] = max(U[-1][1], b)
            else:
                U.append([a, b])
        for a, b in U:
            L[a - 1] = ''.join(x.lstrip('#') for x in L[a - 1:b])
            for k in range(a, b):
                keep[k] = False
        MID[d]['lines'] = [x for x, k in zip(L, keep) if k]

    # 标题、叙述里「」引的原话：与原文只差空格、全半角的，按原文写法改正
    for f in fx.get('facts') or []:
        docs = {r.get('d') for r in f.get('recs') or []}
        for key in ('title', 'narr'):
            t = f.get(key) or ''
            for qt in re.findall(r'「([^」]*)」', t):
                if any(qt in l for d in docs if d in MID for l in MID[d]['lines']):
                    continue
                for d in docs:
                    hit = next((locate(l, qt) for l in (MID[d]['lines'] if d in MID else []) if locate(l, qt)), None)
                    if hit:
                        t = t.replace('「' + qt + '」', '「' + hit + '」'); fixes.append(f'{f.get("id")} 的{"标题" if key == "title" else "叙述"}：引语按原文校正「{qt[:12]}」'); break
            if t:
                f[key] = t

    # 算式核对：Agent 只写算式和材料上写的结果，由脚本来算；对不上的进待审「数字对不上」
    calc_log = []
    for i, c in enumerate(fx.pop('checks', None) or [], 1):
        expr = str(c.get('expr', '')).replace(',', '').replace('，', '').replace('×', '*').replace('÷', '/').replace('－', '-').replace('＋', '+')
        if not re.fullmatch(r'[\d\s.+\-*/()%]+', expr or 'x'):
            errs.append(f'checks 第{i}条的算式只能有数字和 + - * / ( )：{c.get("expr")}'); continue
        try:
            val = eval(expr.replace('%', '/100'), {'__builtins__': {}}, {})
        except Exception:
            errs.append(f'checks 第{i}条的算式算不出来：{c.get("expr")}'); continue
        want = float(str(c.get('equals', '')).replace(',', '') or 'nan')
        tol = float(c.get('tol', 0.005))
        ok = abs(val - want) <= tol
        calc_log.append(f'{"对得上" if ok else "对不上"} {c.get("title", "")}：{c.get("expr")} = {val:,.2f}，材料载 {want:,.2f}')
        if not ok:
            r = {k: c[k] for k in ('d', 'ln', 'q', 'loc') if k in c}
            r.update({'id': c.get('id') or f'K{i}', 'title': c.get('title') or '算式与材料所载不一致',
                      'why': f'{c.get("expr")} = {val:,.2f}，材料载 {want:,.2f}，相差 {abs(val - want):,.2f}。'})
            resolve(r, f'checks {r["id"]}')
            fx.setdefault('arith', []).append(r)

    base = {'schema': 'v8-base/1'}
    base.update({k: v for k, v in fx.items() if k != 'materials'})
    base['materials'] = mats
    # 沿用旧底稿里律师在页面上的裁决、改动记录、待读材料
    title = base.get('title') or '案件看板'
    stem = re.sub(r'[\\/:*?"<>|]', '_', title)
    out_base = os.path.join(work, stem + '.base.json')
    if os.path.exists(out_base):
        try:
            old = json.load(open(out_base, encoding='utf-8'))
            for k in ('decisions', 'changes', 'pending'):
                if old.get(k) and k not in base:
                    base[k] = old[k]
        except Exception:
            pass
    json.dump(base, open(out_base, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

    E, Wn, st = check(base)
    E = errs + E; Wn = warns + Wn
    out = [f'- 底稿：{os.path.basename(out_base)}', '- 统计：' + '，'.join(f'{k} {v}' for k, v in st.items()),
           f'- 自动校正 {len(fixes)} 处，错误 {len(E)} 条，提醒 {len(Wn)} 条']
    if calc_log:
        out.append(f'- 算式核对 {len(calc_log)} 条，对不上 {sum(1 for x in calc_log if x.startswith("对不上"))} 条（已列入待审）')
        out += [f'  - {x}' for x in calc_log]
    out += [f'  - 校正：{x}' for x in fixes[:40]] + [f'  - 错误：{x}' for x in E[:40]] + [f'  - 提醒：{x}' for x in Wn[:40]]
    if E:
        out.append('- 未生成页面：只改「事实.json」里报到的那几条，再运行 make.py')
        print('\n'.join(out)); log(out_base, '拼底稿与检查（未通过）', out); sys.exit(1)
    tpl = open(TEMPLATE, encoding='utf-8').read()
    html = tpl.replace('@@CASE_JSON@@', json.dumps(base, ensure_ascii=False).replace('</', '<\\/'), 1)
    html = html.replace('<title>V8 · 案件看板</title>', f'<title>{title} · 案件看板</title>', 1)
    page = os.path.join(work, stem + '.案件看板.html')
    open(page, 'w', encoding='utf-8').write(html)
    out.append(f'- 页面：{os.path.basename(page)}（{os.path.getsize(page)//1024} KB）。页面已在生成时检查过，不必截图自检。')
    print('\n'.join(out)); log(out_base, '拼底稿、检查、生成页面', out)


if __name__ == '__main__':
    main()
