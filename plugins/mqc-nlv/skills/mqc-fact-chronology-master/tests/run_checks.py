# -*- coding: utf-8 -*-
"""案件看板大师的回归检查。退出码 0 = 全过。

    python3 tests/run_checks.py            # 脚本与模板（几秒）
    python3 tests/run_checks.py --page     # 另跑页面全量回归（需 Playwright 与 fontTools，约三分钟）

只用 Python 标准库。装了 fontTools 时多核对一项「仓库里的页面模板与源码一致」；
装了 Playwright（及 Chromium）时多跑一遍页面冒烟（打开页面、无脚本错误、待审有内容）。缺了只少这一项，不算失败。

每条守卫都必须能失败：「改坏验证」一节把底稿故意改坏，确认检查真的报错。
"""
import io, json, os, pathlib, re, shutil, subprocess, sys, tempfile, zipfile, copy, contextlib
if hasattr(sys.stdout, 'reconfigure'):  # 中文 Windows（GBK）下打印不因个别字符崩掉
    sys.stdout.reconfigure(errors='replace'); sys.stderr.reconfigure(errors='replace')

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
SCRIPTS = os.path.join(SKILL, 'scripts')
sys.path.insert(0, SCRIPTS)
from check_base import check  # noqa: E402

PY = sys.executable
results = []


def ok(name, cond, detail=''):
    results.append((name, bool(cond), detail))


def run(script, *args, cwd=None):
    r = subprocess.run([PY, os.path.join(SCRIPTS, script), *args], cwd=cwd, capture_output=True,
                       env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
    return r.returncode, r.stdout.decode('utf-8', 'replace') + r.stderr.decode('utf-8', 'replace')


def section(t):
    results.append(('§ ' + t, None, ''))


# ---------------------------------------------------------------- 范例
section('范例底稿')
EX = json.load(open(os.path.join(SKILL, 'examples', 'lending.base.json'), encoding='utf-8'))
E, W, st = check(copy.deepcopy(EX))
ok('lending.base.json 检查无错误', not E, E[:3])
ok('统计：15 个事实、26 条记载、引语全部核对通过', st['事实'] == 15 and st['记载'] == 26 and st['引语核对通过'] == 26, st)

# ---------------------------------------------------------------- 改坏验证
section('改坏验证（每条检查都必须能报错）')


def broken(label, mutate, want):
    c = copy.deepcopy(EX)
    mutate(c)
    E, _, _ = check(c)
    ok(label, any(re.search(want, e) for e in E), E[:2])


def f_(c, fid):
    return next(f for f in c['facts'] if f['id'] == fid)


broken('引语改一个字', lambda c: f_(c, 'LF01')['recs'][0].__setitem__('q', f_(c, 'LF01')['recs'][0]['q'].replace('李四', '李肆')), '找不到')
broken('引用不存在的材料', lambda c: f_(c, 'LF01')['recs'][0].__setitem__('d', 'L-99'), '不存在的材料')
broken('日期原文不在引语里', lambda c: f_(c, 'LF01')['recs'][0].__setitem__('raw', '2023年3月2日'), '找不到|没有包含')
broken('精度为「到日」却只写到月', lambda c: f_(c, 'LF01')['recs'][0].__setitem__('s', '2023-03'), 'YYYY-MM-DD')
broken('止日早于起日', lambda c: f_(c, 'LF01')['recs'][0].update({'p': 'range', 'e': '2020-01-01'}), '止日早于起日')
broken('标题「」引语改一个字', lambda c: f_(c, 'LF05').__setitem__('title', '李四称「这个月先还六万」'), '标题或叙述里的引语')
broken('同一事实放进两条线索', lambda c: c['threads'][1]['facts'].append(c['threads'][0]['facts'][0]), '同时放进了线索')
broken('推断日期没有写依据', lambda c: f_(c, 'LF01')['recs'][0].__setitem__('inf', 'NOPE'), '没有定义')
broken('可疑日期没写原因', lambda c: f_(c, 'LF01')['recs'][0].__setitem__('sus', 1), 'susWhy')


def copy_alone(c):
    m = copy.deepcopy(c['materials'][0]); m['id'] = 'L-99'; m['sameAs'] = c['materials'][0]['id']
    c['materials'].append(m)
    for r in f_(c, 'LF01')['recs']:
        r['d'] = 'L-99'


broken('事实只由副本支撑', copy_alone, '只由副本')

# 仓库里的示例一律用 ASCII 文件名（Windows 自带的解压对中文文件名会失败，见下面「防改差」的路径守卫）；
# 复制进临时工作区时换回用户真实会用的中文名，全流程照旧在中文路径上跑。
DEMO_NAMES = {'materials': '材料', 'facts.json': '事实.json', '1-iou.txt': '借条.txt', '2-complaint.txt': '民事起诉状.txt',
              '3-defence.txt': '答辩状.txt', '4-bank-receipt.txt': '银行转账回单.txt'}

def copy_demo(src, dst):
    """复制示例材料，按 DEMO_NAMES 换成中文名。"""
    for root, dirs, files in os.walk(src):
        rel = os.path.relpath(root, src)
        rel = os.sep.join(DEMO_NAMES.get(p, p) for p in rel.split(os.sep)) if rel != '.' else '.'
        d = os.path.normpath(os.path.join(dst, rel))
        os.makedirs(d, exist_ok=True)
        for f in files:
            shutil.copy(os.path.join(root, f), os.path.join(d, DEMO_NAMES.get(f, f)))


TMP = tempfile.mkdtemp()
if True:
    # ---------------------------------------------------------------- 全流程：入库 → 写事实 → 一键生成
    section('全流程（工作区路径带中文与空格）')
    TMP = tempfile.mkdtemp()
    WS = os.path.join(TMP, '工作区 一')
    copy_demo(os.path.join(SKILL, 'examples', 'demo'), WS)
    MAT = os.path.join(WS, '材料')
    code, out = run('ingest.py', MAT, cwd=WS)
    WORK = os.path.join(MAT, '_案件看板')
    ok('ingest：退出码 0，4 个源文件入库', code == 0 and '入库 4 个文件' in out, out[-300:])
    ok('ingest：原文带行号', any(open(os.path.join(WORK, '原文', f), encoding='utf-8').read().count('｜') > 3 for f in os.listdir(os.path.join(WORK, '原文'))))
    code, out = run('ingest.py', MAT, cwd=WS)
    ok('ingest 再跑一次：已入库的文件跳过，不重读', code == 0 and out.count('已入库，跳过') == 4, out[-300:])
    shutil.copy(os.path.join(WS, '事实.json'), os.path.join(WORK, '事实.json'))
    code, out = run('make.py', WORK, cwd=WS)
    ok('make：退出码 0，生成页面', code == 0 and '页面：' in out, out[-600:])
    ok('make：引语与原文只差空格时自动改正', '引语按原文校正' in out, out[-600:])
    ok('make：引语跨两行时自动接行', '引语跨了 2 行' in out, out[-600:])
    ok('make：算式由脚本算，对不上的列出', '算式核对 2 条，对不上 1 条' in out, out[-600:])
    base_p = next(os.path.join(WORK, f) for f in os.listdir(WORK) if f.endswith('.base.json'))
    base = json.load(open(base_p, encoding='utf-8'))
    ok('底稿：材料原文由脚本按行取，不是 Agent 重抄', all(m.get('lines') for m in base['materials']) and all('src' not in m for m in base['materials']))
    ok('底稿：对不上的算式写成「数字对不上」一条', len(base.get('arith') or []) == 1 and '相差' in base['arith'][0]['why'], base.get('arith'))
    ok('底稿：位置自动写成「第几行」', all(r.get('loc') for f in base['facts'] for r in f['recs']))
    E, W, st = check(base)
    ok('底稿再查一遍无错误；答辩状两件只有陈述的事实被认出', not E and st['仅陈述事实'] == 2, (E[:2], st))
    page = next(os.path.join(WORK, f) for f in os.listdir(WORK) if f.endswith('.html'))
    html = open(page, encoding='utf-8').read()
    ok('页面：单文件、小于 1MB、底稿已填入', os.path.getsize(page) < 1024 * 1024 and '@@CASE_JSON@@' not in html and '张三诉李四' in html)
    log = open(os.path.join(WORK, 'run-log.md'), encoding='utf-8').read()
    n1 = log.count('\n## 20')
    run('make.py', WORK, cwd=WS)
    n2 = open(os.path.join(WORK, 'run-log.md'), encoding='utf-8').read().count('\n## 20')
    ok('run-log：自带读取记录表头；同样的结果不重复记', '## 读取记录' in log and n2 == n1, (n1, n2))
    # 律师在页面上的裁决随底稿保留
    base['decisions'] = {'key': {'F05': 1}}; base['changes'] = [{'t': '标为关键'}]
    json.dump(base, open(base_p, 'w', encoding='utf-8'), ensure_ascii=False)
    run('make.py', WORK, cwd=WS)
    b2 = json.load(open(base_p, encoding='utf-8'))
    ok('重新生成时沿用律师的裁决与改动记录', b2.get('decisions') == {'key': {'F05': 1}} and b2.get('changes'), b2.get('decisions'))

    section('出错时说人话')
    bad = os.path.join(TMP, '坏')
    os.makedirs(bad)
    shutil.copy(os.path.join(WORK, '清单.json'), bad)
    open(os.path.join(bad, '事实.json'), 'w', encoding='utf-8').write('{"title": "x", "facts": [{"id": "F1" "t": "pay"}]}')
    code, out = run('make.py', bad)
    ok('「事实.json」写坏：指出行列与常见原因，不甩堆栈', code == 1 and '第 1 行' in out and 'Traceback' not in out, out[-300:])
    fx = json.load(open(os.path.join(WS, '事实.json'), encoding='utf-8'))
    fx['facts'][0]['recs'][0]['ln'] = 99
    json.dump(fx, open(os.path.join(bad, '事实.json'), 'w', encoding='utf-8'), ensure_ascii=False)
    code, out = run('make.py', bad)
    ok('行号越界：报错并且不生成页面', code == 1 and ('超出' in out or '不在' in out) and '未生成页面' in out, out[-300:])
    for s in ('ingest.py', 'make.py', 'check_base.py', 'build_page.py'):
        code, out = run(s, '--help')
        ok(f'{s} --help 打印用法', code == 0 and '用法' in out, out[:120])

    section('读 Word 与 Excel（标准库）')
    dx = os.path.join(TMP, '格式'); os.makedirs(dx)
    W_NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    with zipfile.ZipFile(os.path.join(dx, '合同.docx'), 'w') as z:
        z.writestr('word/document.xml', f'<w:document xmlns:w="{W_NS}"><w:body><w:p><w:r><w:t>借款合同</w:t></w:r></w:p>'
                   '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>日期</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>金额</w:t></w:r></w:p></w:tc></w:tr>'
                   '<w:tr><w:tc><w:p><w:r><w:t>2023-03-03</w:t></w:r></w:p></w:tc><w:tc><w:p/></w:tc></w:tr></w:tbl></w:body></w:document>')
    S_NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    R_NS = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
    with zipfile.ZipFile(os.path.join(dx, '台账.xlsx'), 'w') as z:
        z.writestr('xl/workbook.xml', f'<workbook xmlns="{S_NS}" xmlns:r="{R_NS}"><sheets><sheet name="付款" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Target="worksheets/sheet1.xml" Type="x"/></Relationships>')
        z.writestr('xl/sharedStrings.xml', f'<sst xmlns="{S_NS}"><si><t>第一批</t></si></sst>')
        z.writestr('xl/worksheets/sheet1.xml', f'<worksheet xmlns="{S_NS}"><sheetData><row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1"><v>5488823</v></c></row></sheetData></worksheet>')
    code, out = run('ingest.py', dx)
    src = json.load(open(os.path.join(dx, '_案件看板', '清单.json'), encoding='utf-8'))['sources']
    lines = {s['file']: s['lines'] for s in src}
    ok('docx：段落与表格都读出，表格一行写成「列 ｜ 列」，空格子写「（空白）」', lines.get('合同.docx') == ['借款合同', '日期 ｜ 金额', '2023-03-03 ｜ （空白）'], lines.get('合同.docx'))
    ok('xlsx：逐表逐行读出', lines.get('台账.xlsx') == ['#工作表：付款', '第一批 ｜ 5488823'], lines.get('台账.xlsx'))

    section('不写进技能目录')
    before = set(os.listdir(os.path.join(SKILL, 'examples')))
    cwd = os.path.join(TMP, '范例')
    os.makedirs(cwd)
    code, out = run('build_page.py', os.path.join(SKILL, 'examples', 'lending.base.json'), cwd=cwd)
    ok('用技能自带的范例生成页面：页面与记录写到当前目录，技能目录不多一个文件',
       code == 0 and set(os.listdir(os.path.join(SKILL, 'examples'))) == before and any(f.endswith('.html') for f in os.listdir(cwd)) and 'run-log.md' in os.listdir(cwd), os.listdir(cwd))

section('页面模板')
tpl = open(os.path.join(SKILL, 'assets', 'template.html'), encoding='utf-8').read()
ok('模板只有一个底稿数据槽', tpl.count('@@CASE_JSON@@') == 1)
ok('脚本里没有真正的 </body>：往页面末尾追加调试脚本不会切错位置', tpl.count('</body>') == 1)
ok('模板小于 1MB', len(tpl.encode('utf-8')) < 1024 * 1024)
try:
    import fontTools  # noqa: F401
    if not os.path.exists(os.path.join(SKILL, 'web', 'build.py')):
        raise ImportError  # 插件包里不带页面源码：这一项只在仓库里核对
    t2 = os.path.join(TMP, 't.html')
    subprocess.run([PY, os.path.join(SKILL, 'web', 'build.py'), '-o', t2], capture_output=True, check=True)
    ok('仓库里的模板与 web/src 源码一致（改了页面源码要重新生成模板）', open(t2, encoding='utf-8').read() == tpl)
except ImportError:
    ok('（跳过：没有 fontTools 或页面源码，不核对模板与源码是否一致）', True)

section('页面冒烟（需要 Playwright）')
try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception:
            b = None
            ok('（跳过：Playwright 找不到 Chromium）', True)
        if b:
            pg = b.new_page(viewport={'width': 1440, 'height': 900}); errs = []
            pg.on('pageerror', lambda e: errs.append(str(e)))
            pg.goto(pathlib.Path(page).as_uri()); pg.wait_for_function('typeof derive==="function" && CASES.length>0', timeout=15000)
            r = pg.evaluate("[derive().length, pendingCount(), !!document.querySelector('#tlsvg')]")
            for t in ('matrix', 'narr'):
                pg.evaluate(f"S.tab='{t}';render()")
            pg.evaluate("S.tab='tl';render();openReview()")
            ok('页面：7 个事实上时间线，待审有内容，三个视图与待审都打得开，没有脚本错误', r[0] == 7 and r[1] > 0 and r[2] and not errs, (r, errs[:2]))
            b.close()
except ImportError:
    ok('（跳过：没有 Playwright）', True)

# ---------------------------------------------------------------- 防改差
section('防改差（每条守卫都配一个故意改坏的反向验证）')
REPO = os.path.abspath(os.path.join(SKILL, '..', '..', '..', '..'))
IN_REPO = os.path.exists(os.path.join(REPO, '.claude-plugin', 'marketplace.json'))

# 1. 页面上不许出现的说法：理论用语、与本技能定位不符的入口（网盘、交给某个 AI）
BANNED = ['三问', '四验', '信息不穿越', '平行宇宙', '新诉讼可视化', '工作台', '网盘', '交给 AI', '交给AI', '交给 Claude', '交给Claude', '事实时间线大师']


def banned_hits(text):
    body = re.sub(r'data:[a-z/+-]+;base64,[A-Za-z0-9+/=]+', '', text)
    return [t for t in BANNED if t in body]


ok('页面模板里没有不许出现的说法', not banned_hits(tpl), banned_hits(tpl))
ok('反向验证：模板里混进「网盘」会被抓住', banned_hits(tpl + '<button>网盘</button>') == ['网盘'])
docs = {f: open(os.path.join(SKILL, f), encoding='utf-8').read() for f in ('SKILL.md', 'README.md', os.path.join('references', 'schema.md'), os.path.join('references', 'reading-guide.md'))}
theory = ['三问', '四验', '信息不穿越', '平行宇宙']
leak = {f: [t for t in theory if t in d] for f, d in docs.items()}
ok('技能文档里没有未发布的理论用语', not any(leak.values()), leak)


# 2. 页面源码里同名的顶层函数只许有一处：后定义的会整段盖掉先定义的，旧的一份留着就是看不见的旧文案
def dup_functions(sources):
    seen, dup = {}, []
    for f, text in sources:
        for m in re.finditer(r'^function\s+(\w+)\s*\(', text, re.M):
            if m.group(1) in seen:
                dup.append(f'{m.group(1)}（{seen[m.group(1)]} 与 {f}）')
            seen.setdefault(m.group(1), f)
    return dup


SRC = os.path.join(SKILL, 'web', 'src')
if os.path.isdir(SRC):
    srcs = [(f, open(os.path.join(SRC, f), encoding='utf-8').read()) for f in ('core.js', 'packs.js', 'app.js', 'features.js', 'skin.js')]
    ok('页面源码里没有被重写后仍留着的旧函数', not dup_functions(srcs), dup_functions(srcs))
    ok('反向验证：复制一个旧函数进来会被抓住', dup_functions(srcs + [('x.js', 'function render(){}\n')]) != [])
else:
    ok('（跳过：插件包里不带页面源码）', True)


# 3. 版本只有一个：SKILL.md、CHANGELOG 第一节、仓库首页的模块表要一致
def versions():
    v = {'SKILL.md': re.search(r'^\s+version:\s*(\S+)', docs['SKILL.md'], re.M).group(1),
         'CHANGELOG.md': re.search(r'^## (\d+\.\d+\.\d+)', open(os.path.join(SKILL, 'CHANGELOG.md'), encoding='utf-8').read(), re.M).group(1)}
    if IN_REPO:
        m = re.search(r'\*\*V8\*\* \[[^\]]+\]\(plugins/mqc-nlv/skills/mqc-fact-chronology-master/\) \| v(\d+\.\d+\.\d+)', open(os.path.join(REPO, 'README.md'), encoding='utf-8').read())
        v['仓库 README'] = m.group(1) if m else '（找不到 V8 那一行）'
        en = os.path.join(REPO, 'README.en.md')
        if os.path.exists(en):
            m = re.search(r'\*\*V8\*\* \[[^\]]+\]\(plugins/mqc-nlv/skills/mqc-fact-chronology-master/\) \| v(\d+\.\d+\.\d+)', open(en, encoding='utf-8').read())
            v['英文 README'] = m.group(1) if m else '（找不到 V8 那一行）'
    return v


vs = versions()
ok(f'版本一致：{vs}', len(set(vs.values())) == 1, vs)
ok('反向验证：版本写岔一处会被抓住', len(set({**vs, 'SKILL.md': '9.9.9'}.values())) > 1)

# 4. 页面里嵌了字体，许可原文必须随模板一起走（插件包与单独技能包都不带 web/）
ok('字体许可原文与模板放在一起（assets/FONTS-OFL.txt）', os.path.exists(os.path.join(SKILL, 'assets', 'FONTS-OFL.txt'))
   and 'SIL OPEN FONT LICENSE Version 1.1' in open(os.path.join(SKILL, 'assets', 'FONTS-OFL.txt'), encoding='utf-8').read())

# 5. 仓库里：图标在、尺寸对，插件版登记了八个技能
if IN_REPO:
    def png_size(path):
        with open(path, 'rb') as f:
            h = f.read(24)
        return (int.from_bytes(h[16:20], 'big'), int.from_bytes(h[20:24], 'big')) if h[:8] == b'\x89PNG\r\n\x1a\n' else None
    icons = {n: png_size(os.path.join(REPO, 'assets', 'icons', n + '.png')) for n in ('v1', 'v2', 'v3', 'v4', 'v5', 'v6', 'v7', 'v8', 'dsh')}
    ok('九枚图标都在，都是 192×192', all(v == (192, 192) for v in icons.values()), icons)
    dsh = open(os.path.join(REPO, 'plugins', 'mqc-nlv-dsh', 'build.py'), encoding='utf-8').read()
    nskills = len([d for d in os.listdir(os.path.join(REPO, 'plugins', 'mqc-nlv', 'skills')) if os.path.exists(os.path.join(REPO, 'plugins', 'mqc-nlv', 'skills', d, 'SKILL.md'))])
    ok(f'插件版打包脚本要求的技能数与仓库里的技能数一致（{nskills}）', f'len(skills) != {nskills}' in dsh)

    # 首页里的链接与图片都要指向真实存在的文件（改首页、挪文件时最容易断）
    def broken_links(md_text, base):
        import urllib.parse
        bad = []
        for m in re.finditer(r'(?:\]\(|src=")([^)"#\s]+)', md_text):
            u = m.group(1)
            if not u.startswith(('http', 'mailto:')) and not os.path.exists(os.path.join(base, urllib.parse.unquote(u))):
                bad.append(u)
        return bad
    readme = open(os.path.join(REPO, 'README.md'), encoding='utf-8').read()
    ok('仓库首页的链接与图片都指向真实文件', not broken_links(readme, REPO), broken_links(readme, REPO))
    readme_en = open(os.path.join(REPO, 'README.en.md'), encoding='utf-8').read() if os.path.exists(os.path.join(REPO, 'README.en.md')) else ''
    ok('英文首页在，链接与图片都指向真实文件', readme_en and not broken_links(readme_en, REPO), broken_links(readme_en, REPO))
    ok('反向验证：首页里一张不存在的图会被抓住', broken_links('<img src="assets/没有这张.png"/>', REPO) == ['assets/没有这张.png'])

    def non_ascii_paths(root):
        bad = []
        for dp, dns, fns in os.walk(root):
            dns[:] = [x for x in dns if x not in ('.git', '__pycache__', 'node_modules', 'dist')]
            bad += [os.path.relpath(os.path.join(dp, n), root) for n in dns + fns if any(ord(c) > 127 for c in n)]
        return bad
    ok('整个仓库的路径都是 ASCII（Windows 自带解压遇到中文文件名会失败）', not non_ascii_paths(REPO), non_ascii_paths(REPO)[:5])
    _t = tempfile.mkdtemp(); open(os.path.join(_t, '材料.txt'), 'w').close()
    ok('反向验证：放进一个中文文件名会被抓住', non_ascii_paths(_t) == ['材料.txt'])

# 6. 检查项只增不减：比上次记下的少，就是有检查被删掉或被跳过了
BASE_P = os.path.join(HERE, 'baseline.json')
n_now = sum(1 for _, g, _ in results if g is not None) + 2  # 加上本节最后这两条


def shrunk(now, base):
    return now < base


KEY = 'checks' if IN_REPO else 'checks_outside_repo'   # 插件包与单独技能包里没有仓库那几项，另记一个数
base_all = json.load(open(BASE_P, encoding='utf-8')) if os.path.exists(BASE_P) else {}
base_n = base_all.get(KEY, 0)
ok(f'检查项只增不减：这次 {n_now} 项，上次记下 {base_n} 项', not shrunk(n_now, base_n), '有检查被删掉或跳过；若是有意为之，改 tests/baseline.json 并在 CHANGELOG 里写明原因')
ok('反向验证：少一项会被抓住', shrunk(base_n - 1, base_n))
if '--update-baseline' in sys.argv and n_now >= base_n:
    base_all[KEY] = n_now
    json.dump(base_all, open(BASE_P, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

if '--page' in sys.argv:
    section('页面全量回归（--page：示例案件对账、改坏验证、交互流程）')
    r0 = subprocess.run([PY, os.path.join(SKILL, 'web', 'build.py'), '--demo'], capture_output=True)
    ok('生成带示例案件的 demo 页面', r0.returncode == 0, r0.stderr.decode('utf-8', 'replace')[-300:])
    for t, want in (('page_suite.py', '有问题的案例：0'), ('page_flows.py', '失败 0')):
        r = subprocess.run([PY, os.path.join(HERE, t)], capture_output=True)
        o = r.stdout.decode('utf-8', 'replace')
        ok(f'{t}', want in o, o[-400:])

shutil.rmtree(TMP, ignore_errors=True)
fails = 0
for name, good, detail in results:
    if good is None:
        print('\n' + name); continue
    print(('  √ ' if good else '  × ') + name + ('' if good else f'    {detail}'))
    fails += not good
n = sum(1 for _, g, _ in results if g is not None)
print(f'\n案件看板大师：{n} 项检查，失败 {fails}')
sys.exit(1 if fails else 0)
