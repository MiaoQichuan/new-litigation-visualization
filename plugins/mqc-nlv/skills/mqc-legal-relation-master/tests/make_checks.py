# -*- coding: utf-8 -*-
"""make.py 的端到端自检，含改坏验证。

    python tests/make_checks.py

一、示例案：奇川风带两处重点，一条命令出齐，路线判据与导出物判据全过
二、缓存：换成白描再跑，布局必须复用，不得重新求解
三、拒绝：非奇川风带重点、关系名空着、指向不存在的主体、重点三处
四、长名称：换行加高能装下的必须装下；装不下的如实写进交付说明，不删字
五、第〇轮：超 9 个模块、超 12 条关系都拦下；精简后连通、不丢关系名、未入图的全部进出处索引
六、画不好的输入先拦下并说清原因：自指、反向双关系、孤立模块、不连通的小图
七、第〇轮写回的文件，第二轮能正常列出关系；名称带 & < > 不被误判撑破；长关系名不越出画布
五、第〇轮：超过 9 个模块时停下；建议、拒绝越界、未入图入索引、「全部」放行
"""
import os, sys, json, subprocess, tempfile, shutil
HERE = os.path.dirname(os.path.abspath(__file__))
MAKE = os.path.join(HERE, "..", "scripts", "make.py")
FX = os.path.join(HERE, "fixtures", "relations-demo.json")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
tmp = tempfile.mkdtemp()
fails = []
ENV = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")


def run(*args):
    r = subprocess.run([sys.executable, MAKE, *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=ENV)
    return r.returncode, r.stdout + r.stderr


def expect(cond, name, detail=""):
    print(("  OK    " if cond else "  FAIL  ") + name + ("" if cond else f"\n        {detail[-300:]}"))
    if not cond:
        fails.append(name)


def dump(obj, name):
    p = os.path.join(tmp, name)
    json.dump(obj, open(p, "w", encoding="utf-8"), ensure_ascii=False)
    return p


out = os.path.join(tmp, "o")
print("一、示例案")
ch = dump({"style": "奇川风", "emphasis": {"nodes": ["PRICE"], "edges": [9]}}, "c1.json")
code, log = run(FX, "--out", out, "--choice", ch, "--name", "demo", "--formats", "all")
chk = open(os.path.join(out, "demo-qichuan-checks.txt"), encoding="utf-8").read() if code == 0 else ""
expect(code == 0 and "交付：svg、png、pptx、vsdx、drawio" in log, "要全部时五种格式都交付", log)
# 默认（不选）只出 SVG + PPTX：两者不依赖外部工具，任何 Windows 都能一次出齐。
_od = os.path.join(tmp, "o_default")
_cd, _ld = run(FX, "--out", _od, "--choice", ch, "--name", "dflt")
_made = sorted(os.path.splitext(f)[1] for f in os.listdir(_od)
               if f.startswith("dflt-qichuan.") and not f.endswith((".txt", ".md", ".json")))
expect(_cd == 0 and _made == [".pptx", ".svg"], "不选格式时只出 SVG 与 PPTX", str(_made))
expect("FAIL" not in chk, "路线判据与导出物判据全过", chk)

print("二、缓存")
ch2 = dump({"style": "白描", "emphasis": {"nodes": [], "edges": []}}, "c2.json")
code, log = run(FX, "--out", out, "--choice", ch2, "--name", "demo")
expect(code == 0 and "复用缓存" in log and "开始求解" not in log, "换风格不重跑布局", log)

print("三、拒绝")
bad = dump({"style": "歸藏风", "emphasis": {"nodes": ["PRICE"], "edges": []}}, "c3.json")
expect(run(FX, "--out", out, "--choice", bad)[0] != 0, "歸藏风带重点 → 拒绝")
rel = json.load(open(FX, encoding="utf-8"))
r1 = json.loads(json.dumps(rel)); r1["edges"][0][2] = ""
expect(run(dump(r1, "r1.json"), "--plan-only")[0] != 0, "关系名空着 → 拒绝")
r2 = json.loads(json.dumps(rel)); r2["edges"][0][1] = "NOBODY"
expect(run(dump(r2, "r2.json"), "--plan-only")[0] != 0, "指向不存在的主体 → 拒绝")
bad3 = dump({"style": "奇川风", "emphasis": {"nodes": ["PRICE", "GC"], "edges": [1]}}, "c4.json")
expect(run(FX, "--out", out, "--choice", bad3)[0] != 0, "重点三处 → 拒绝")

print("四、长名称")
r3 = json.loads(json.dumps(rel))
r3["nodes"][0]["name"] = "Example（China）Limited"
r3["nodes"][0]["note"] = "被上诉人 / 投资方 / 受托人"
out3 = os.path.join(tmp, "o3")
code, log = run(dump(r3, "r3.json"), "--out", out3, "--name", "long")
chk = open(os.path.join(out3, "long-qichuan-checks.txt"), encoding="utf-8").read() if code == 0 else ""
expect(code == 0 and "FAIL" not in chk and "须人工处理" not in log, "名称与备注各换一行、加高模块，判据全过", log + chk)
r4 = json.loads(json.dumps(rel))
r4["nodes"][0]["name"] = "Example (China) Investment Holdings Limited"
r4["nodes"][0]["note"] = "被上诉人 / 投资方 / 受托人"
code, log = run(dump(r4, "r4.json"), "--out", os.path.join(tmp, "o4"), "--name", "long4")
expect(code == 0 and "须人工处理" in log and "装不下" in log, "五行装不下 → 交付说明如实写明，不删字", log)

print("五、第〇轮")
ASK = os.path.join(HERE, "..", "scripts", "ask.py")


def ask(*args):
    r = subprocess.run([sys.executable, ASK, *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=ENV)
    return r.returncode, r.stdout + r.stderr


R15 = os.path.join(HERE, "fixtures", "relations-15.json")
full = json.load(open(R15, encoding="utf-8"))
code, log = run(R15, "--plan-only")
expect(code == 4 and "ask.py trim" in log, "15 个模块 → make.py 拦下，提示第〇轮", log)
code, log = ask("trim", R15)
import re as _re
starred = _re.findall(r"^\d+　★ ", log, _re.M)
expect(code == 0 and len(starred) == 9 and "至多 9 个" in log, "第〇轮列出全部模块，★ 恰好标出 9 个", log)
t1 = os.path.join(tmp, "t1.json")
code, log = ask("trim", R15, "--keep", "0", "--out", t1)
r1 = json.load(open(t1, encoding="utf-8")) if code == 0 else {}
expect(code == 0 and len(r1["nodes"]) == 9, "不回答 → 按建议留 9 个", log)
ids = {n["id"] for n in r1.get("nodes", [])}
adj = {k: set() for k in ids}
for e in r1.get("edges", []):
    adj[e["from"]].add(e["to"]); adj[e["to"]].add(e["from"])
seen, stack = set(), [next(iter(ids))] if ids else []
while stack:
    x = stack.pop()
    if x not in seen:
        seen.add(x); stack += list(adj[x])
expect(seen == ids, "建议留下的 9 个模块彼此连通")
labels_all = sorted(e["label"] for e in full["edges"])
labels_now = sorted([e["label"] for e in r1.get("edges", [])] +
                    [e["label"] for e in r1.get("dropped", {}).get("edges", [])])
expect(labels_all == labels_now, "关系一条不丢：留下的 + 未入图的 = 原有的")
code, log = run(t1, "--plan-only")
expect(code == 4 and "超过 12 条" in log, "9 个模块 17 条关系 → 再拦一次", log)
t2 = os.path.join(tmp, "t2.json")
code, log = ask("trim", t1, "--keep-edges", "0", "--out", t2)
r2 = json.load(open(t2, encoding="utf-8")) if code == 0 else {}
ends = {x for e in r2.get("edges", []) for x in (e["from"], e["to"])}
expect(code == 0 and len(r2["edges"]) == 12 and ends == {n["id"] for n in r2["nodes"]},
       "按建议留 12 条，每个模块至少挂一条", log)
labels_now = sorted([e["label"] for e in r2.get("edges", [])] +
                    [e["label"] for e in r2.get("dropped", {}).get("edges", [])])
expect(labels_all == labels_now, "两步精简后关系仍一条不丢")
out5 = os.path.join(tmp, "o5")
code, log = run(t2, "--out", out5, "--name", "c15")
prov = open(os.path.join(out5, "c15-provenance.md"), encoding="utf-8").read() if code == 0 else ""
missing = [n["name"] for n in r2.get("dropped", {}).get("nodes", []) if n["name"] not in prov]
expect(code == 0 and "未入图" in prov and not missing and "判据：全部通过" in log,
       "精简后出图，判据全过，未入图的模块全部写进出处索引", log)
expect(ask("trim", R15, "--keep", "1,2,3,4,5,6,7,8,9,10", "--out", os.path.join(tmp, "x.json"))[0] != 0,
       "留 10 个 → 拒绝")
expect(ask("trim", t1, "--keep-edges", "1,2", "--out", os.path.join(tmp, "y.json"))[0] != 0,
       "有模块一条关系都没留 → 拒绝")
tall = os.path.join(tmp, "all.json")
ask("trim", R15, "--keep", "全部", "--out", tall)
expect(run(tall, "--plan-only")[0] == 0, "回答「全部」→ 放行（不删，但会慢）")
dup = json.loads(json.dumps(rel))
dup["edges"].append([dup["edges"][0][0], dup["edges"][0][1], "另一关系"])
dp = dump(dup, "dup.json"); dout = os.path.join(tmp, "dup-out.json")
code, log = ask("trim", dp, "--out", dout)
m = json.load(open(dout, encoding="utf-8")) if code == 0 else {"edges": []}
expect(code == 0 and len(m["edges"]) == len(rel["edges"]) and
       any(e["label"] == dup["edges"][0][2] + "；另一关系" for e in m["edges"]),
       "同向重复关系合并，关系名原样用「；」连起来", log)

print("六、输入检查")
two = lambda es: {"nodes": [{"id": "A", "name": "甲"}, {"id": "B", "name": "乙"}, {"id": "C", "name": "丙"}], "edges": es}
code, log = run(dump(two([["A", "A", "自己"], ["A", "B", "x"], ["B", "C", "y"]]), "self.json"), "--plan-only")
expect(code == 2 and "同一个模块" in log, "起止同一模块 → 拒绝并说明", log)
code, log = run(dump(two([["A", "B", "买"], ["B", "A", "卖"], ["B", "C", "y"]]), "opp.json"), "--plan-only")
expect(code == 2 and "方向相反" in log and "客体" in log, "反向双关系 → 拒绝并给出经由客体的画法", log)
code, log = run(dump(two([["A", "B", "x"]]), "lonely.json"), "--plan-only")
expect(code == 2 and "丙" in log and "一条关系都没有" in log, "孤立模块 → 拒绝并点名", log)
four = {"nodes": [{"id": k, "name": k} for k in "ABCD"], "edges": [["A", "B", "x"], ["C", "D", "y"]]}
code, log = run(dump(four, "disc.json"), "--plan-only")
expect(code == 3 and "互不相连" in log and "5 到 16" not in log, "不连通的小图 → 说明是不连通，而不是超出范围", log)

print("七、第二轮与文字")
ASKP = os.path.join(HERE, "..", "scripts", "ask.py")
r = subprocess.run([sys.executable, ASKP, "round2", t2], capture_output=True, text=True,
                   encoding="utf-8", errors="replace", env=ENV)
expect(r.returncode == 0 and "from → to" not in r.stdout and "→" in r.stdout,
       "第〇轮写回的文件，第二轮列出的是真实关系", r.stdout[-300:])
sp = {"nodes": [{"id": "A", "name": "A&B <公司>"}, {"id": "B", "name": "乙"}], "edges": [["A", "B", "a<b & c"]]}
code, log = run(dump(sp, "sp.json"), "--out", os.path.join(tmp, "sp"), "--name", "sp")
expect(code == 0 and "判据：全部通过" in log, "名称带 & < > 判据全过", log)
ll = {"nodes": [{"id": "A", "name": "甲"}, {"id": "B", "name": "乙"}],
      "edges": [["A", "B", "这是一条非常非常长的关系名称用来测试标签是否放得下而不越界"]]}
code, log = run(dump(ll, "ll.json"), "--out", os.path.join(tmp, "ll"), "--name", "ll")
expect(code == 0 and "判据：全部通过" in log, "长关系名不越出画布（G12）", log)

# ---- 八、图名不被关系名压住（G14）与本机环境的三条 ---------------------------------
# 真实运行记录：一条从右下绕到左上的回环，关系名落在画布顶端与图名挤在一起，
# 而当时 13 条判据全绿 —— 没有一条管「文字压文字」。G14 定为提示档：报出来，
# 但不把整张图判成不合格（这类拥挤要靠挪关系名或换短图名解决，属版面取舍）。
import re as _re8, glob as _glob8


def _title_of(svg_text):
    """画布上方字号最大的那行文字就是图名；没有图名的图返回 None。"""
    _h = _re8.search(r'<svg[^>]*height="([\d.]+)"', svg_text)
    if not _h:
        return None
    H = float(_h.group(1))
    best = None
    for m in _re8.finditer(r'<text([^>]*)>([^<]+)</text>', svg_text):
        fs = _re8.search(r'font-size="([\d.]+)"', m.group(1))
        y = _re8.search(r'\sy="([\d.]+)"', m.group(1))
        x = _re8.search(r'\sx="([\d.]+)"', m.group(1))
        if fs and y and x and float(y.group(1)) < H * 0.25 and float(fs.group(1)) >= 20:
            cand = (float(fs.group(1)), x.group(1), y.group(1))
            best = cand if best is None or cand[0] > best[0] else best
    return best


_picked8 = None
for _p8 in sorted(_glob8.glob(os.path.join(tmp, "**", "*.svg"), recursive=True)):
    if "-master" in _p8 or _p8.endswith(".drawio.svg"):
        continue
    _s8 = open(_p8, encoding="utf-8").read()
    _t8 = _title_of(_s8)
    if _t8:
        _picked8 = (_p8, _s8, _t8)
        break
if not _picked8:
    print("  （本轮产物里没有带图名的图，G14 验证跳过）")
else:
    _p8, _s8, (_fs8, _x8, _y8) = _picked8
    _bad8 = os.path.join(tmp, "g14-bad.svg")
    open(_bad8, "w", encoding="utf-8").write(_s8.replace(
        "</svg>", f'<text x="{_x8}" y="{_y8}" font-size="13" text-anchor="middle">'
                  f'系其总公司，承担清偿责任</text></svg>'))
    _RG = os.path.join(HERE, "..", "scripts", "route_guard.py")
    _r8 = subprocess.run([sys.executable, _RG, _bad8], capture_output=True, text=True,
                         encoding="utf-8", errors="replace", env=ENV)
    expect("WARN G14" in _r8.stdout, "关系名压住图名会被 G14 报出来（提示档）",
           _r8.stdout[-200:])
    # 不误报这一条要用**已知干净**的图来验：现出一张示例案的图。
    # （随手挑到的图可能本就有拥挤——仓库自带的 15 主体用例精简后就是一例，
    # 图名基线 y=58 字号 30、关系名落在 y=72，字形相叠约 5px，属真实现象。）
    _clean_dir = os.path.join(tmp, "g14clean")
    _cc, _cl = run(FX, "--out", _clean_dir, "--name", "g14c")
    _cf = os.path.join(_clean_dir, "g14c-qichuan.svg")
    if _cc == 0 and os.path.exists(_cf):
        _r8b = subprocess.run([sys.executable, _RG, _cf], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", env=ENV)
        expect("G14" in _r8b.stdout and "WARN G14" not in _r8b.stdout,
               "干净的图不会被 G14 误报", _r8b.stdout[-200:])
    else:
        expect(False, "没出成用于 G14 不误报验证的图", _cl[-200:])

# ---- 模块名断行：收尾标点不落行首、末行不留孤字 ------------------------------------
# 真实运行记录（第三轮）：图上出现「…某某大酒 / 店」孤一个字、
# 《借款（垫款）协议 / 》右书名号单独一行。判据不报，只有人眼看得出来。
# 两条规则只挪断点、不改字，照录原文的纪律不受影响。
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import importlib as _il9
_mk9 = _il9.import_module("make")
_w9 = _mk9.wrap("北京某某科技发展有限公司某某大酒店", _mk9.FS_NODE, 128)
expect(len(_w9) >= 2 and len(_w9[-1]) > 1, "模块名末行不留孤字", str(_w9))
_w9b = _mk9.wrap("《借款（垫款）协议》", _mk9.FS_NODE, 100)
expect(all(not x.startswith(("》", "）", "」", "、", "。", "，")) for x in _w9b[1:]),
       "收尾标点不落到行首", str(_w9b))
_w9c = _mk9.wrap("被上诉人 / 投资方 / 受托人", _mk9.FS_NODE, 120)
expect(all("受托人" not in x or x.strip().endswith("受托人") for x in _w9c),
       "原有的分隔处优先断行没被破坏", str(_w9c))

# G14 必须参与候选布局的挑选：同样合格的候选里，优先选不压图名的。
# 真实运行记录（第二轮）：12 条关系那一版交出了压住图名的布局，使用者只能回读
# checks.txt 才发现 —— 提示档不等于不管，能换就该换。
_lk8 = open(os.path.join(HERE, "..", "scripts", "lookup.py"), encoding="utf-8").read()
expect("(_bad, sc) < (best_g14, best[0])" in _lk8 and '"G15" in (msg or "")' in _lk8,
       "G14、G15 参与候选布局的挑选（同样合格时优先不压图名、不压字的）",
       "挑选的比较式里没有把 G14 排在前面")
# 核对清单要把所有提示项列全（不能只让人回读 checks.txt）
_mk8b = open(os.path.join(HERE, "..", "scripts", "make.py"), encoding="utf-8").read()
expect("_warns = [x for x in gres if x.get(\"warn\")]" in _mk8b and "条提示" in _mk8b,
       "出图后的核对清单把所有提示项列全（含 G14）", "清单仍只列固定几条")

# 折行的避头与孤字合并，不许把文字撑出模块（G13）。全流程验证时抓到过：
# 「《借款（垫款）协议》」被并成一整行 140px，正好等于模块宽，当场撑破。
import importlib as _ilw
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
_mkw = _ilw.import_module("make")
# 用 render 真正调用的那一层（node_lines）来验，并且判据要硬：每行都必须留出
# G13 要求的 8px 余量。第一版守卫写虚了（带了一个恒真的分支），改坏也过得去。
_n13 = {"id": "X", "name": "《借款（垫款）协议》", "note": "2021.05.17 签订"}
_l13 = _mkw.node_lines(_n13, 140)[0]
_wid13 = [round(_mkw.text_w(x, _mkw.FS_NODE)) for x in _l13]
expect(all(w <= 140 - 8 for w in _wid13),
       "避头合并后每行仍留出模块余量（G13 的 8px）", f"{_l13} 行宽 {_wid13}")
for _sty in ("白描", "奇川风", "歸藏风"):
    _dw = tempfile.mkdtemp()
    _chw = os.path.join(_dw, "c.json")
    json.dump({"style": _sty, "emphasis": {"nodes": [], "edges": []}},
              open(_chw, "w", encoding="utf-8"), ensure_ascii=False)
    _cw, _lw = run(FX, "--out", os.path.join(_dw, "o"), "--choice", _chw, "--name", "w13")
    expect(_cw == 0 and "G13" not in _lw, f"{_sty}：折行不撑破模块（G13）", _lw[-200:])

# ---- 提示里的耗时说法要有实测支撑 ----------------------------------------------------
# 「高模块布局慢三到四倍」是早先凭一次观察写下的，实测不成立：同一结构下只慢 0 到 30%，
# 那次的差别来自网格不同。没有实测支撑的倍数不许再写进提示与文档。
import glob as _glc
_bad_claim = []
for _f in _glc.glob(os.path.join(HERE, "..", "**", "*.py"), recursive=True) + \
        _glc.glob(os.path.join(HERE, "..", "**", "*.md"), recursive=True):
    if "__pycache__" in _f or _f.endswith("make_checks.py"):
        continue
    if "慢三到四倍" in open(_f, encoding="utf-8").read():
        _bad_claim.append(os.path.basename(_f))
expect(not _bad_claim, "提示与文档里没有「慢三到四倍」这种未经实测的说法", str(_bad_claim))

# ---- 箭头几何：线不许顶穿箭头，尖端不许插进模块 --------------------------------------
# 老毛病：线画到模块边、箭头贴在线端上，视觉上成了平头；或尖端插进模块里。
# 这里量真出的 SVG（三种风格各一张），判据在 tests/arrow_geom_check.py。
import importlib.util as _ila
_spa = _ila.spec_from_file_location("agc", os.path.join(HERE, "arrow_geom_check.py"))
_agc = _ila.module_from_spec(_spa); _spa.loader.exec_module(_agc)
for _sa in ("奇川风", "白描", "歸藏风"):
    _da = tempfile.mkdtemp()
    _cha = os.path.join(_da, "c.json")
    json.dump({"style": _sa, "emphasis": {"nodes": [], "edges": []}},
              open(_cha, "w", encoding="utf-8"), ensure_ascii=False)
    run(FX, "--out", os.path.join(_da, "o"), "--choice", _cha, "--name", "arw")
    _fa = [p for p in _glob8.glob(os.path.join(_da, "o", "*.svg")) if "-master" not in p]
    if not _fa:
        expect(False, f"{_sa}：没出图，箭头几何无法验", "")
        continue
    _na, _bada = _agc.check(_fa[0])
    _flags = {k: v for k, v in _bada.items() if v}
    expect(_na >= 8 and not _flags, f"{_sa}：箭头不顶穿、不插进模块（量了 {_na} 个）", str(_flags))
# 两份量具必须一致
_stripa = lambda t: "\n".join(l for l in t.splitlines()
                              if not l.startswith("# ⚠") and "各拷一份" not in l)
expect(_stripa(open(os.path.join(HERE, "arrow_geom_check.py"), encoding="utf-8").read())
       == _stripa(open(os.path.join(HERE, "..", "..", "mqc-litigation-visual-redraw",
                                    "tests", "arrow_geom_check.py"), encoding="utf-8").read()),
       "箭头量具与 V1 的那份一致", "两份不一致")

# ---- 2026-09-20 真实运行批次---------------------------------------------
# G15：任意两段文字互相压住要报出来。真实运行里两段关系名重叠 38.6 像素，判据全绿。
_rg9 = os.path.join(HERE, "..", "scripts", "route_guard.py")
_rg9s = open(_rg9, encoding="utf-8").read()
expect("G15" in _rg9s, "有「文字互相压住」判据（G15）", "route_guard 里没有 G15")
# resolve 要直接写出 choice.json（两次真实运行都以为写了、其实没写）
_rt = tempfile.mkdtemp()
shutil.copy(FX, os.path.join(_rt, "r.json"))
subprocess.run([sys.executable, os.path.join(HERE, "..", "scripts", "ask.py"), "resolve",
                os.path.join(_rt, "r.json"), "--style", "2"], capture_output=True, env=ENV)
expect(os.path.exists(os.path.join(_rt, "choice.json")), "ask.py resolve 直接写出 choice.json",
       "只打到屏幕，没写文件")
# 名称过长的提示一次出图只说一遍
_c9, _l9 = run(FX, "--out", os.path.join(_rt, "o"))
expect(_l9.count("高模块布局实测慢") <= 1, "名称过长的提示不重复打印", _l9[:200])

# CI 上撞过：机器装的是 LibreOffice，而后端名单里没有 soffice，于是判「PNG 渲染：无」
# 并停机，连 SVG 都不给出。两条：名单要认 V1 的完整转图链；PNG 不是必需项。
_mk_src = open(os.path.join(HERE, "..", "scripts", "make.py"), encoding="utf-8").read()
expect('found.append("v1:" + _t)' in _mk_src and '"soffice"' in _mk_src,
       "PNG 后端名单认得 V1 的完整转图链（含 LibreOffice）", "名单里没有 soffice 这条")
expect('"无 —— 只影响 PNG 这一种格式' in _mk_src,
       "没有转图工具时不停机（PNG 不是必需项）", "PNG 仍被当成必需项")

# PNG 后端顺序：cairosvg 必须排在最后（它缺中文字体时不报错，直接出豆腐块）
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import importlib as _il8
_mk8 = _il8.import_module("make")
_order8 = [b for b in ("inkscape", "rsvg-convert", "sharp", "cairosvg")]
_src_mk = open(os.path.join(HERE, "..", "scripts", "make.py"), encoding="utf-8").read()
_pos = [_src_mk.index('found.append("%s")' % b) if 'found.append("%s")' % b in _src_mk else -1
        for b in ("inkscape", "cairosvg")]
expect(_src_mk.index('import cairosvg  # noqa: F401') > _src_mk.index('for exe in ("inkscape"'),
       "PNG 后端里 cairosvg 排在 Inkscape 之后", "cairosvg 仍排在前面")
expect("_find_tool" in _src_mk and "ProgramFiles" in _src_mk,
       "转图工具会查 Windows 常见安装位置（不再误报「PNG 渲染：无」）", "没有按路径查找")
expect("中间文件没删成" in _src_mk,
       "中间文件删不掉时不再让整轮失败（沙箱会拦 os.remove）", "仍是硬失败")

shutil.rmtree(tmp, ignore_errors=True)
print("全部通过" if not fails else f"{len(fails)} 项未过")
sys.exit(1 if fails else 0)
