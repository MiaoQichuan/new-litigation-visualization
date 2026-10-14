#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""法律图表大师 · 回归检查。退出码 0 = 全过。

本文件为了检验案号抽取，写了几个虚构的案号格式，所以带脱敏守卫的自测标记：ANON_GUARD_SELFTEST

一、示例矩阵：全部示例 × 两种风格 × 六种画布，守卫全过（含 G9 没有尖角、G11 批注）
二、确定性：同一份说明渲染两次，SVG 与 PPTX 逐字节一致
三、PPTX：用 V1 的导出器转写、回读，文字不撑破、不出页
四、说明校验：该拒的都拒（缺 n、n 对不上、标题编数字、要白描……）
五、场景库：源文件与索引一致，检索命中
六、类案编码：机械字段、逐份对账、封闭表、引句照录、金额一致、自动出图
七、学来的：批注、社交画布、无障碍 title/desc、律所档案、出图计划、复杂度预算（强调色预设已在 0.9.3 取消）
八、V7 接口：设计令牌与代码一致、版位适配、模块清单
九、改坏验证：见 break_tests.py，每条守卫都必须能失败
十、外部测试回归：GPT 测试集与修复建议里查出的问题（T012–T028、N01–N18）
十一、第二轮外部测试回归（R2）：环境版本、短行、语义边界、发布事务
十二、防改差：判定账、成品账、变形测试，以及这三样自己能不能失败；禁止删除的环境里发布
十三、第二批学来的：文档与代码同步、对比度、一页多图的 id、坏结构说人话、schema 与代码同步
"""
import copy
import json
import os
import subprocess
import sys
import tempfile

# 中文 Windows 默认 GBK：不固定成 UTF-8，打印 −、✓ 这类 GBK 没有的字会崩（GBK 模拟环境里实测过）
for _s in (sys.stdout, sys.stderr):
    getattr(_s, "reconfigure", lambda **k: None)(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import make                                   # noqa: E402
import cases                                  # noqa: E402
from spec import SpecError                    # noqa: E402

EX = os.path.join(ROOT, "examples")
EXAMPLES = sorted(f for f in os.listdir(EX) if f.endswith(".json"))
results = []


def ok(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    print(f"  {'OK  ' if cond else 'FAIL'}  {name}" + (f"  → {detail}" if detail and not cond else ""))


def ex(name):
    with open(os.path.join(EX, name), encoding="utf-8") as f:
        return json.load(f)


print("一、示例矩阵")
for f in EXAMPLES:
    probs = []
    for st in ("奇川风", "歸藏风"):
        for cv in ("slide", "slide-half", "a4-landscape", "square", "portrait", "wide-cover"):
            try:
                _, rep = make.build(os.path.join(EX, f), st, None, cv)
                probs += [f"{st}/{cv}: {p}" for p in rep["problems"]]
            except SpecError as e:
                probs.append(f"{st}/{cv}: {e}")
    ok(f"{f[:-5]}：两种风格 × 六种画布全过守卫", not probs, "; ".join(probs[:3]))
for st_, acc_ in (("奇川风", "#991B1B"), ("歸藏风", "#002FA7")):
    svg_, rep = make.build(os.path.join(EX, "rose-causes.json"), st_)
    cols_ = {c.upper() for c in __import__("re").findall(r"#[0-9A-Fa-f]{6}", svg_)}
    ok(f"{st_}只用自己的颜色：重音 {acc_}，全图颜色都在本风格白名单里",
       rep["accent"] == acc_ and cols_ <= __import__("styles").WHITELIST[st_], sorted(cols_ - __import__("styles").WHITELIST[st_]))

print("二、确定性")
a, _ = make.build(os.path.join(EX, "strip-duration.json"))
b, _ = make.build(os.path.join(EX, "strip-duration.json"))
ok("同一份说明渲染两次，SVG 逐字节一致（含逐件分布的抖动）", a == b)

print("三、PPTX")
tmp = tempfile.mkdtemp()
for f in EXAMPLES:
    base = os.path.join(tmp, f[:-5])
    r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "make.py"), os.path.join(EX, f),
                        "-o", base, "--formats", "svg,pptx"], capture_output=True, text=True, encoding="utf-8")
    ok(f"{f[:-5]}：PPTX 转写后回读干净", r.returncode == 0 and os.path.exists(base + ".pptx"),
       (r.stderr or r.stdout)[-200:])
r2 = os.path.join(tmp, "again")
subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "make.py"), os.path.join(EX, "bar-filings.json"),
                "-o", r2, "--formats", "svg,pptx"], capture_output=True)
import zipfile
slide = zipfile.ZipFile(os.path.join(tmp, "bar-filings.pptx")).read("ppt/slides/slide1.xml").decode()
ok("PPTX 里的柱是原生圆角矩形（roundRect，可拖控点调圆角）", slide.count('prst="roundRect"') >= 7)
slide = zipfile.ZipFile(os.path.join(tmp, "rose-causes.pptx")).read("ppt/slides/slide1.xml").decode()
ok("PPTX 里的玫瑰扇区是细分后的自由曲线（圆角保留）", slide.count("<a:custGeom>") >= 8)
slide = zipfile.ZipFile(os.path.join(tmp, "ribbon-funds.pptx")).read("ppt/slides/slide1.xml").decode()
ok("PPTX 里汇入图的流带保留半透明（<a:alpha>），代号色没有残留",
   slide.count("<a:alpha ") == 9 and "9CA3B0" not in slide and "991B1C" not in slide)
ok("PPTX 两次导出逐字节一致",
   open(r2 + ".pptx", "rb").read() == open(os.path.join(tmp, "bar-filings.pptx"), "rb").read())

print("四、说明校验（该拒的都拒）")


def rejects(name, mutate, needle, style=None, accent=None):
    m = ex("bar-filings.json") if not isinstance(mutate, tuple) else ex(mutate[0])
    fn = mutate if not isinstance(mutate, tuple) else mutate[1]
    fn(m)
    try:
        make.build(m, style, accent)
        ok(name, False, "没有被拒")
    except (SpecError, ValueError) as e:
        ok(name, needle in str(e), str(e)[:120])


rejects("缺 n → 拒", lambda m: m.pop("n"), "缺 n")
rejects("缺口径 scope → 拒", lambda m: m.pop("scope"), "口径")
rejects("缺来源 source → 拒", lambda m: m.pop("source"), "来源")
rejects("标题编了一个数（60%）→ 拒", lambda m: m.update(title="2025 年收案较 2019 年增长 60%"), "推不出来")
rejects("百点方阵 n 与件数对不上 → 拒", ("waffle-outcomes.json", lambda m: m.update(n=120)), "必须一致")
rejects("玫瑰 n 与合计对不上 → 拒", ("rose-causes.json", lambda m: m.update(n=1000)), "必须一致")
rejects("百点方阵没写件数还是百分比 → 拒", ("waffle-outcomes.json", lambda m: m["data"].pop("measure")), "measure")
rejects("emphasis 指向不存在的 id → 拒", lambda m: m.update(emphasis="y2030"), "没有这个 id")
rejects("负数 → 拒", lambda m: m["data"]["items"][0].update(value=-5), "负数")
rejects("白描 → 拒（V6 不出白描）", lambda m: None, "不出白描", style="白描")
rejects("命令行给强调色（浅色）→ 拒", lambda m: None, "不换强调色", accent="#F4A261")
rejects("命令行给强调色（深色，奇川风）→ 拒：0.9.3 起不换强调色", lambda m: None, "不换强调色", accent="#1E3A5F")
rejects("歸藏风换强调色 → 拒", lambda m: None, "不换强调色", style="歸藏风", accent="#1E3A5F")
rejects("说明 JSON 里写 accent → 拒", lambda m: m.update(accent="#166534"), "不换强调色")
rejects("强调色预设名（墨绿）→ 拒", lambda m: None, "不换强调色", accent="墨绿")
# 律所风格（0.9.5，ADR 0011）：主色只能来自经校验的律所风格文件；随手写的强调色照旧拒（上面五条）
FIRM_OK = {"name": "示例律所风", "base": "奇川风", "accent": "#702082"}
for st_ in ("奇川风", "歸藏风"):
    for f in EXAMPLES:
        svg_, rep = make.build(os.path.join(EX, f), st_, None, None, None, dict(FIRM_OK, base=st_))
        cols_ = {c.upper() for c in __import__("re").findall(r"#[0-9A-Fa-f]{6}", svg_)}
        base_acc = "#991B1B" if st_ == "奇川风" else "#002FA7"
        wl_ = (__import__("styles").WHITELIST[st_] - {base_acc}) | {"#702082"}
        if rep["problems"] or not cols_ <= wl_ or base_acc in cols_:
            ok(f"律所风格（基础 {st_}）{f[:-5]}：守卫全过、只换重音色", False, (rep["problems"][:1], sorted(cols_ - wl_)))
            break
    else:
        ok(f"律所风格（基础 {st_}）：{len(EXAMPLES)} 个示例守卫全过，重音换成律所主色，基础重音色不再出现，其余颜色仍在基础白名单", True)
_, rep = make.build(os.path.join(EX, "bar-filings.json"), None, None, None, None, FIRM_OK)
ok("律所风格：报告里写明律所风格名与主色", rep["firm"] == "示例律所风" and rep["accent"] == "#702082")


def firm_rejects(name, firm, needle, accent=None):
    try:
        make.build(ex("bar-filings.json"), None, accent, None, None, firm)
        ok(name, False, "没有被拒")
    except (SpecError, ValueError) as e:
        ok(name, needle in str(e), str(e)[:120])


firm_rejects("律所主色太浅（白字压不上、纸上看不清）→ 拒", dict(FIRM_OK, accent="#F5EFF7"), "对比度")
firm_rejects("律所主色接近灰（会和灰阶梯混）→ 拒", dict(FIRM_OK, accent="#707372"), "太接近灰色")
firm_rejects("律所主色不是 #RRGGBB → 拒", dict(FIRM_OK, accent="purple"), "#RRGGBB")
firm_rejects("律所风格没有名字 → 拒", dict(FIRM_OK, name=""), "名字")
firm_rejects("律所风格的基础风格是白描 → 拒", dict(FIRM_OK, base="白描"), "基础风格")
firm_rejects("律所风格与强调色同时给 → 拒", FIRM_OK, "不能同时", accent="#1E3A5F")
firm_rejects("律所风格的图标题字体不认识 → 拒", dict(FIRM_OK, title_font="cursive"), "serif / sans")
svg_, rep = make.build(ex("bar-filings.json"), None, None, None, None, dict(FIRM_OK, title_font="sans"))
_t = __import__("re").search(r'<text[^>]*data-role="title"[^>]*>', svg_) or __import__("re").search(r'<text[^>]*font-size="(?:2[4-9]|3\d)[^>]*>', svg_)
ok("律所风格给 sans：图标题用无衬线、字重 700，与课件标题同一种字", not rep["problems"] and _t and "serif" not in _t.group(0).split("font-family=")[1][:40]
   and 'font-weight="700"' in _t.group(0), _t.group(0)[:160] if _t else "没找到标题")
rejects("桑基中间节点进出不等 → 拒",
        ("sankey-appeals.json", lambda m: m["data"]["links"][2].update(value=190)), "对不上")
rejects("汇入图：从去处流出 → 拒",
        ("ribbon-funds.json", lambda m: m["data"]["links"].append({"from": "wang", "to": "bing", "value": 5})), "流向一个去处")
rejects("汇入图：同一对重复 → 拒",
        ("ribbon-funds.json", lambda m: m["data"]["links"].append({"from": "jia", "to": "bing", "value": 5})), "重复")
rejects("汇入图：没有流量的去处 → 拒",
        ("ribbon-funds.json", lambda m: m["data"]["targets"].append({"id": "x", "label": "某账户"})), "没有任何流量")
rejects("不认识的字段（拼错）→ 拒", lambda m: m.update(titel="x"), "不认识的字段")
rejects("图名太长 → 拒", lambda m: m.update(title="2025 年收案较 2019 年增长 56%" * 8), "太长")
m = ex("waffle-outcomes.json")
_, rep = make.build(m)
ok("标题里的「四成」列进人工核对清单", any("四成" in w for w in rep["warnings"]))
m = ex("bar-filings.json")
m["data"]["items"] = [{"id": f"c{i}", "label": "机动车交通事故责任纠纷", "value": 100 + i} for i in range(8)]
m["title"], m["emphasis"] = "八类案由收案件数", None
_, rep = make.build(m)
ok("竖柱类目名放不下 → 自动换成横条并记进说明", rep["chart"] == "hbar" and rep["notes"], rep["notes"])

print("五、场景库")
r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "build_library.py"), "--check"],
                   capture_output=True, text=True, encoding="utf-8")
ok("index.json 与 recipes.txt 一致、每行代码都已登记", r.returncode == 0, (r.stderr or r.stdout)[-200:])
idx = json.load(open(os.path.join(ROOT, "library", "index.json"), encoding="utf-8"))
tax = json.load(open(os.path.join(ROOT, "library", "taxonomy.json"), encoding="utf-8"))
ready_forms = {f["code"] for f in tax["forms"] if f["status"] == "ready" and f["module"] == "V6"}
import charts as _charts                                     # noqa: E402
ok("标「可画」的 V6 画法都真有渲染器", ready_forms <= set(_charts.RENDERERS), sorted(ready_forms - set(_charts.RENDERERS)))
ok("每个领域都至少有 3 条场景",
   all(sum(1 for x in idx["recipes"] if x["area"] == a["code"]) >= 3 for a in tax["areas"]))
r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "find.py"), "破产", "清偿", "-n", "1"],
                   capture_output=True, text=True, encoding="utf-8")
ok("检索「破产 清偿」第一条是清偿顺位分配", "清偿顺位分配" in r.stdout.splitlines()[0] if r.stdout else False, r.stdout[:120])
r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "find.py"), "加班", "-n", "3"],
                   capture_output=True, text=True, encoding="utf-8")
ok("检索「加班」命中劳动领域", "LAB-" in r.stdout, r.stdout[:120])

print("六、类案编码")
import shutil                                                    # noqa: E402
import cases                                                     # noqa: E402
# 示例判决是虚构的，但案号要写成真实的格式才能检验抽取。仓库里存的是「{民}初」这种中性写法
# （时间轴大师的脱敏守卫扫整个插件，真实格式的案号会被它拦下），跑测试时在临时目录里还原。
_FX_SRC = os.path.join(HERE, "fixtures", "cases")
FX = tempfile.mkdtemp()
for _f in os.listdir(_FX_SRC):
    with open(os.path.join(_FX_SRC, _f), encoding="utf-8") as _r, open(os.path.join(FX, _f), "w", encoding="utf-8") as _w:
        _w.write(_r.read().replace("{民}", "民"))
cw = tempfile.mkdtemp()
txts = sorted(os.path.join(FX, f) for f in os.listdir(FX) if f.endswith(".txt"))
docs, _ = cases.ingest(txts, cw)
d1 = docs[0]
ok("机械字段由脚本抽出：案号、法院、层级、省份、程序、年份",
   d1["case_no"] == "（2022）沪0115民初1201号" and d1["court"] == "上海市浦东新区人民法院" and d1["level"] == "基层"
   and d1["province"] == "上海" and d1["procedure"] == "一审" and d1["year"] == 2022, d1)
ok("二审、高院、中文日期都认得出",
   docs[1]["procedure"] == "二审" and docs[1]["level"] == "中级" and docs[8]["level"] == "高级" and docs[8]["date"] == "2023-03-22",
   (docs[1], docs[8]))
ok("相同案号自动标为重复", docs[12].get("duplicate_of") == "D004", docs[12].get("duplicate_of"))
ok("文书标题里的空格（民 事 裁 定 书）不影响认类型", docs[13]["doctype"] == "裁定书", docs[13]["doctype"])
scheme = cases.load_scheme(os.path.join(FX, "coding.json"))
codes = json.load(open(os.path.join(FX, "codes.json"), encoding="utf-8"))
dd, src = cases._load_work(cw)
bad, stats = cases.check(scheme, codes, dd, src)
ok("示例编码全部通过，纳入 12、剔除 2", not bad and stats["included"] == 12, bad[:3])
r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "cases.py"), "charts", os.path.join(FX, "coding.json"),
                    os.path.join(FX, "codes.json"), "-w", cw, "--formats", "svg"], capture_output=True, text=True, encoding="utf-8")
made = [f for f in os.listdir(os.path.join(cw, "charts")) if f.endswith(".svg")]
ok("由编码表自动出图（样本筛选、观点、结果、地域、层级、年份、金额分布）", r.returncode == 0 and len(made) >= 9,
   (r.stdout + r.stderr)[-300:])
ok("Excel 母表与 CSV 都导出了", os.path.exists(os.path.join(cw, "cases.csv")))


def breaks(label, tag, mutate):
    c = json.loads(json.dumps(codes))
    mutate(c)
    b, _ = cases.check(scheme, c, dd, src)
    ok(f"改坏验证 · {label}", any(x.startswith(tag) for x in b), b[:2])


breaks("漏编一份", "C1", lambda c: c.pop(3))
breaks("同一份编了两次", "C1", lambda c: c.append(json.loads(json.dumps(c[0]))))
breaks("剔除理由不在封闭表", "C2", lambda c: c[12].update(reason="看着不像"))
breaks("重复的两份都纳入", "C2", lambda c: c[12].update(include=True, values=c[3]["values"]))
breaks("类别自造（不在选项里）", "C3", lambda c: c[0]["values"]["view"].update(v="认定为融资"))
breaks("引句改了一个字", "C4", lambda c: c[0]["values"]["view"].update(q=c[0]["values"]["view"]["q"].replace("借贷", "借款")))
breaks("金额与引句对不上", "C5", lambda c: c[0]["values"]["claim"].update(v=125))
breaks("在 values 里偷改机械字段", "C6", lambda c: c[0]["values"].update(court="某某法院"))
ok("引句用省略号跳过仍算照录", cases.quote_ok("本院认为……名为买卖实为借贷", src["D001"]))
ok("万元与元换算后能对上", cases.amount_in("支付1,200,000元", 120, "万元"))

print("七、学来的（lieflat-charts-custom 与 diagram-design）")
import styles                                 # noqa: E402
from spec import budget_used                  # noqa: E402
for ch, fn in (("bar", "bar-filings.json"), ("dumbbell", "dumbbell-claims.json"), ("waterfall", "waterfall-award.json")):
    m = ex(fn)
    ids = ([i["id"] for i in m["data"]["items"]] if ch != "waterfall" else [s_["id"] for s_ in m["data"]["steps"]])
    m["annotations"] = [{"target": ids[0], "text": "批注一句"}, {"target": ids[-1], "text": "另一句批注"}]
    probs = []
    for st in ("奇川风", "歸藏风"):
        for cv in (("slide", "wide-cover", "a4-landscape") if ch == "waterfall" else ("slide", "square", "portrait")):
            try:
                _, rep = make.build(copy.deepcopy(m), st, None, cv)
                probs += rep["problems"]
            except SpecError as e:
                probs.append(str(e))
    ok(f"批注 · {ch}：两条批注在两种风格 × 三种画布上找得到路线、守卫全过", not probs, probs[:2])


def ann(m, a):
    m["annotations"] = a


rejects("批注三条 → 拒", lambda m: ann(m, [{"target": f"y20{x}", "text": "一句"} for x in (19, 20, 21)]), "最多 2 条")
rejects("批注编了一个数 → 拒", lambda m: ann(m, [{"target": "y2019", "text": "增长 77.7%"}]), "推不出来")
rejects("批注指向不存在的 id → 拒", lambda m: ann(m, [{"target": "y1999", "text": "一句"}]), "没有这个 id")
rejects("玫瑰图加批注 → 拒（写进标题）",
        ("rose-causes.json", lambda m: ann(m, [{"target": "loan", "text": "一句"}])), "写进标题")
svg, _ = make.build(os.path.join(EX, "bar-filings.json"))
head = svg.split("<rect", 1)[0]
ok("SVG 带 role=img 与 title、desc（无障碍），且是头两个子元素",
   'role="img"' in head and '<title id="nlv-title-' in head and '<desc id="nlv-desc-' in head
   and head.split(">", 1)[1].startswith("<title "))
_, rep = make.build(os.path.join(EX, "rose-causes.json"), None, None, None, "example-firm")
ok("律所档案生效（示例律所：风格、画布）", rep["profile"] == "示例律所" and rep["accent"] == "#991B1B")
_, rep = make.build(os.path.join(EX, "rose-causes.json"), None, None, None,
                    {"name": "旧档案", "style": "奇川风", "accent": "#166534"})
ok("旧档案里留着的强调色：不用、照常出图、交付清单里说明", rep["accent"] == "#991B1B" and not rep["problems"]
   and "已停用" in (rep.get("profile_note") or ""))
pdir = tempfile.mkdtemp()
r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "make.py"), os.path.join(EX, "hbar-annotated.json"),
                    "-o", os.path.join(pdir, "x"), "--plan"], capture_output=True, text=True, encoding="utf-8")
ok("出图计划：只打印、不写文件", r.returncode == 0 and "出图计划" in r.stdout and "批注" in r.stdout
   and not os.listdir(pdir), r.stdout[-200:])
ok("复杂度预算：横条 8 / 16", budget_used(ex("hbar-causes.json")) == (8, 16, "条"))
import re                                     # noqa: E402
sq, _ = make.build(os.path.join(EX, "waffle-outcomes.json"), None, None, "square")
fs = [float(x) for x in re.findall(r'font-size="([\d.]+)"[^>]*data-role="category"', sq)]
ok("方图按手机阅读定字号：类目字 ≥ 18px", fs and min(fs) >= 18, fs[:3])

print("八、V7 接口")
import module                                 # noqa: E402
import charts                                 # noqa: E402
import styles as _st                          # noqa: E402
r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "module.py"), "tokens", "--check"],
                   capture_output=True, text=True, encoding="utf-8")
ok("design/tokens.json 与代码一致（改了风格没重新生成会被拦）", r.returncode == 0, r.stdout)
tk = module.tokens()
for st in ("奇川风", "歸藏风"):
    pal, _ = _st.palette(st)
    fr = charts.Frame(ex("bar-filings.json") | {"_derived": {}}, 1280, 720, pal)
    ts = tk["type_scale_px_at_1280x720"]
    want = {"subtitle": fr.fs["sub"], "label": fr.fs["label"], "value": fr.fs["value"], "tick": fr.fs["tick"],
            "big_number": fr.fs["big"], "source": fr.fs["source"],
            ("title_qichuan" if st == "奇川风" else "title_guizang"): fr.fs["title"]}
    off = {k: (ts[k], v) for k, v in want.items() if abs(ts[k] - v) > 1e-6}
    ok(f"令牌里的字号阶梯与画框一致（{st}）", not off, off)
sq, _ = make.build(os.path.join(EX, "waffle-outcomes.json"))
ok("百点方阵是方块模块（奇川风圆角 = 边长 × 0.22），没有圆点",
   'data-role="dot"' in sq and "<circle" not in sq.split('data-role="source"')[0].split("<desc")[1]
   and 'data-module="1"' in sq)
sg, _ = make.build(os.path.join(EX, "waffle-outcomes.json"), "歸藏风")
mods = re.findall(r'<path d="([^"]*)"[^>]*data-module="1"', sg)
ok("歸藏风的方块是直角", mods and not any("C" in d for d in mods))
for f in EXAMPLES:
    res = module.fit(ex(f))
    bad = [f"{k}/{st}" for k in ("full", "two-thirds", "half") for st, pr in res[k].items() if pr]
    ok(f"{f[:-5]}：V7 的整页、三分之二栏、半栏都放得下", not bad, bad)
mdir = tempfile.mkdtemp()
r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "make.py"), os.path.join(EX, "hbar-annotated.json"),
                    "-o", os.path.join(mdir, "m"), "--formats", "svg,pptx,module"],
                   capture_output=True, text=True, encoding="utf-8")
man = json.load(open(os.path.join(mdir, "m.module.json"), encoding="utf-8")) if r.returncode == 0 else {}
ok("模块清单：带原样说明（无内部字段）、版位、无障碍、出处，可凭它重新渲染",
   man.get("schema") == "mqc-nlv/module@1" and "data" in man.get("spec", {})
   and not any(k.startswith("_") for k in man.get("spec", {})) and man["slots"]["full"]
   and man["render"]["accent"] == "#991B1B" and man["annotations"], (r.stderr or "")[-200:])
if man:
    again, rep2 = make.build(man["spec"], man["render"]["style"], man["render"]["accent_in"], "half")
    ok("V7 凭清单换到半栏重新渲染，守卫全过", not rep2["problems"], rep2["problems"])

print("九、改坏验证")
r = subprocess.run([sys.executable, os.path.join(HERE, "break_tests.py")], capture_output=True, text=True, encoding="utf-8",
                   env=dict(os.environ, PYTHONIOENCODING="utf-8"))
print(r.stdout.rstrip())
ok("每条守卫都确认能失败", r.returncode == 0, r.stderr[-300:])

print("十、外部测试回归（外部测试集与修复建议）")
EXT = os.path.join(HERE, "fixtures", "external")


def ext(name):
    with open(os.path.join(EXT, name + ".json"), encoding="utf-8") as f:
        return json.load(f)


def verdict(m, style=None, accent=None):
    try:
        _, rep = make.build(m, style, accent)
        return "ok", rep
    except (SpecError, ValueError) as e:
        return "reject", str(e)


for tid, why in (("T020", "标题「收案增长9876%」数字紧贴汉字"), ("T028", "批注「金额增长9876%」数字紧贴汉字"),
                 ("T012", "「驳回率41%」：41% 是全额支持的占比"), ("T013", "「提高20%」：其实是 20 个百分点"),
                 ("T014", "「九成」：实际 41%")):
    v, why_ = verdict(ext(tid))
    ok(f"{tid} 拒：{why}", v == "reject", why_ if v == "ok" else "")


def t_title(t, chart="waffle-outcomes.json"):
    m = ex(chart)
    m["title"] = t
    return verdict(m)[0]


n01 = {"增长9876%": "reject", "增长 9876%": "reject"}
ok("N01 数字紧贴汉字与有空格一样被核", all(t_title(t, "bar-filings.json") == want for t, want in n01.items()))
m = ex("bar-filings.json")
m["annotations"] = [{"target": "y2019", "text": "金额增长9876%"}]
ok("N01 批注里紧贴汉字的数字同样被核", verdict(m)[0] == "reject")
legal = {"全额支持41件": "ok", "全额支持占41%": "ok", "驳回26件": "ok", "驳回占26%": "ok",
         "全额支持占４１％": "ok", "驳回比全额支持少15个百分点": "ok", "约三分之一部分支持": "ok",
         "四成诉请获全额支持": "ok"}
bad_ = {"驳回率41%": "reject", "驳回41件": "reject", "全额支持占26%": "reject", "近三分之一驳回": "reject",
        "九成诉请获全额支持": "reject", "全额支持为驳回的两倍": "reject", "驳回12,34件": "reject",
        "全额支持比驳回多15%": "reject"}
got = {t: t_title(t) for t in list(legal) + list(bad_)}
ok("N02/N03 合法写法不误拒（含全角数字、百分点、约数）", all(got[t] == w for t, w in legal.items()),
   {t: got[t] for t in legal if got[t] != legal[t]})
ok("N03 主语与数字串了、类型错了、分组错了都拒", all(got[t] == w for t, w in bad_.items()),
   {t: got[t] for t in bad_ if got[t] != bad_[t]})
m = ex("bar-filings.json")
ok("年份要在材料里：2019、2025 是类目，放行", verdict(m)[0] == "ok")
m["title"] = "2018年以来收案增长56%"
ok("年份不在口径、来源、类目里 → 拒", verdict(m)[0] == "reject")
m["title"] = "依民法典第577条，2025 年收案较 2019 年增长 56%"
v, rep = verdict(m)
ok("条文编号不当数据核，列请核", v == "ok" and any("条文编号" in w for w in rep["warnings"]))
m["title"] = "（2024）沪01民终123号所在法院 2025 年收案较 2019 年增长 56%"
v, rep = verdict(m)
ok("案号不当数据核，列请核", v == "ok" and any("案号" in w for w in rep["warnings"]))
w = ex("waterfall-award.json")
w["title"] = "违约金调减−1,500万元"
ok("带负号的数按符号核（逐级加减 −1,500 对得上）", verdict(w)[0] == "ok")
w["title"] = "违约金调减−1,100万元"
ok("带负号的数主语串了也拒（−1,100 是利息那一级）", verdict(w)[0] == "reject")

print("　类案编码")
ok("N04 金额精确比对：引句 120 万元，编码 120.5 万元 → 不认", not cases.amount_in("支付120万元", 120.5, "万元"))
ok("N04 金额精确比对：引句 120 万元，编码 1200000 元 → 认", cases.amount_in("支付120万元", 1200000, "元"))
ok("N05 约数：「约120万元」不写 approx 不认，写了才认",
   not cases.amount_in("损失约120万元", 120, "万元") and cases.amount_in("损失约120万元", 120, "万元", approx=True))
ok("N05 「120万元及逾期利息」里的「逾」不当约数", cases.amount_in("支付120万元及逾期付款利息", 120, "万元"))
ok("N05 NaN、无穷、真假值不当金额", not any(cases.amount_in("支付120万元", v, "万元")
                                    for v in (float("nan"), float("inf"), True)))
src_ = "本院认为，双方之间并无真实的货物交付，名为买卖实为借贷。"
ok("N06 标点改了 → 不算照录", not cases.quote_ok("本院认为。双方之间并无真实的货物交付", src_))
ok("N06 换行、全角半角 → 仍算照录", cases.quote_ok("本院认为,双方之间\n并无真实的货物交付", src_))
ok("N06 省略号分段顺序颠倒 → 不算照录", not cases.quote_ok("名为买卖实为借贷……本院认为", src_))
ok("N06 扫描件宽松模式：标点差异放过", cases.quote_ok("本院认为。双方之间并无真实的货物交付", src_, "ocr"))
tmpc = tempfile.mkdtemp()
csvp = os.path.join(tmpc, "list.csv")
with open(csvp, "w", encoding="utf-8") as f:
    f.write("案号,法院,裁判结果\n（2023）京01民终1号,北京市第一中级人民法院,驳回\n\n"
            "（2023）京01民终1号,北京市第一中级人民法院,驳回\n（2023）京01民终2号,北京市第一中级人民法院\n")
dd, _ = cases.ingest([csvp], os.path.join(tmpc, "w"))
ok("N09 相同的两行记下各自的真实行号（2、4），空行不错位", [d["row"] for d in dd] == [2, 4, 5], [d["row"] for d in dd])
ok("N09 内容完全相同的两行认作重复；短行标出", dd[1].get("dup_kind") == "内容相同" and dd[2].get("short_row"))
docs_ = [{"did": "D1", "case_no": "X", "doctype": "判决书"}, {"did": "D2", "case_no": "X", "doctype": "裁定书"}]
sc_ = {"fields": []}
b_, st_ = cases.check(sc_, [{"did": "D1", "values": {}}, {"did": "D2", "values": {}}],
                      [dict(docs_[0]), dict(docs_[1], same_case_as="D1")], {"D1": "a", "D2": "b"})
ok("N08 同案号不同文书：不算重复，两份可都纳入，列请核统计单位", not b_ and any("同一案号" in r for r in st_["review"]), b_)
b_, _ = cases.check(sc_, [{"did": "D1", "include": False, "reason": "重复", "note": "保留 D2"},
                          {"did": "D2", "values": {}}],
                    [dict(docs_[0]), dict(docs_[1], doctype="判决书", duplicate_of="D1", dup_kind="案号与文书类型相同")],
                    {"D1": "a", "D2": "a"})
ok("N08 主本剔除、留副本 → 允许（0.8.0 会误拦）", not b_, b_)

print("　交付")
import export_pptx                            # noqa: E402
odir = tempfile.mkdtemp()
old = os.path.join(odir, "chart.svg")
with open(old, "w", encoding="utf-8") as f:
    f.write("旧文件")
orig_audit = export_pptx.audit_deck
export_pptx.audit_deck = lambda p: ["注入的回读故障"]
try:
    rc = make.main([os.path.join(EX, "bar-filings.json"), "-o", os.path.join(odir, "chart")])
finally:
    export_pptx.audit_deck = orig_audit
ok("N12 PPTX 回读失败 → 退出码 3，本次不写任何文件，旧文件原样不动",
   rc == 3 and open(old, encoding="utf-8").read() == "旧文件" and sorted(os.listdir(odir)) == ["chart.svg"], (rc, os.listdir(odir)))
rc = make.main([os.path.join(EX, "bar-filings.json"), "-o", os.path.join(odir, "x"), "--formats", "svg,docx"])
ok("N13 不认识的格式 → 拒，不静默忽略", rc == 1 and not os.path.exists(os.path.join(odir, "x.svg")))
v, why_ = verdict(ex("bar-filings.json"), "歸藏风", "藏青")
ok("N18 歸藏风 + 明写的强调色 → 拒（与档案里的色相同也不静默丢掉）", v == "reject")
_, rep = make.build(os.path.join(EX, "bar-filings.json"), "歸藏风", None, None, "example-firm")
ok("N18 歸藏风 + 档案 → 照常出图，只用克莱因蓝", rep["accent"] == "#002FA7" and not rep["problems"])

print("　单独安装包")
IN_REPO = os.path.isdir(os.path.join(ROOT, "..", "mqc-litigation-visual-redraw", "scripts"))
if IN_REPO:
    pk = tempfile.mkdtemp()
    r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "pack_standalone.py"), "-o", pk],
                       capture_output=True, text=True, encoding="utf-8")
    ok("T041 单独安装包带齐 V1、V4 依赖，在空目录里自检、出图、读清单都过", r.returncode == 0,
       (r.stderr or r.stdout)[-300:])
else:
    # 打包要从完整仓库里取 V1、V4；在已经解开的单独安装包里跑回归时，这一项本来就做不了（R2-063）
    print("  SKIP  T041 打单独安装包：要在完整仓库里运行，这里是单独安装包，跳过（不计入通过与失败）")

print("　契约同步")
sch = json.load(open(os.path.join(ROOT, "schemas", "chart.schema.json"), encoding="utf-8"))
from spec import CHARTS, CANVAS                # noqa: E402
ok("N16 schema 的图种枚举与 spec.py 一致（含逐级加减）", sch["properties"]["chart"]["enum"] == list(CHARTS))
ok("N16 schema 的画布枚举含全部画布与 V7 版位",
   set(sch["properties"]["canvas"]["oneOf"][0]["enum"]) == set(CANVAS) | set(module.SLOTS))
skill = open(os.path.join(ROOT, "SKILL.md"), encoding="utf-8").read()
ok("SKILL.md 不再说「有负数不支持」而漏掉逐级加减", "逐级加减" in skill.split("不用：")[1][:600])
ok("SKILL.md 依赖写明 V4 与 openpyxl", "mqc-chronicle-master" in skill and "openpyxl" in skill)

print("十一、第二轮外部测试回归（R2）")
W = ex("waffle-outcomes.json")
W50 = copy.deepcopy(W)
W50["data"]["items"] = [{"id": "full", "label": "全额支持", "value": 50}, {"id": "part", "label": "部分支持", "value": 24},
                        {"id": "reject", "label": "驳回", "value": 26}]
r2 = [("R2-007 「未获支持占41%」：否定说法指哪几类说不清", W, "未获支持占41%", "reject"),
      ("R2-008 「驳回：41%」：冒号不断句，主语仍是驳回", W, "驳回：41%", "reject"),
      ("R2-008 对照「驳回：26%」放行", W, "驳回：26%", "ok"),
      ("R2-014 全额支持恰好 50%，「过半」不对", W50, "过半诉请获全额支持", "reject"),
      ("R2-014 对照「半数诉请获全额支持」放行", W50, "半数诉请获全额支持", "ok"),
      ("R2-016 「全额支持并未过半」（41%）放行", W, "全额支持并未过半", "ok"),
      ("R2-016 「全额支持不足四成」（41%）拒", W, "全额支持不足四成", "reject"),
      ("R2-025 「第9876件」超出样本", W, "第9876件获得全额支持", "reject"),
      ("R2-028 「全额支持比驳回少15件」方向反了", W, "全额支持比驳回少15件", "reject"),
      ("R2-028 对照「全额支持比驳回多15件」放行", W, "全额支持比驳回多15件", "ok"),
      ("R2-033 「1，234元」中文逗号分组说不清", W, "金额1，234元", "reject"),
      ("R2-034 「1e6元」科学计数法", W, "金额1e6元", "reject"),
      ("合计：「全额支持与部分支持合计占74%」放行", W, "全额支持与部分支持合计占74%", "ok"),
      ("合计：「74% 的诉请获支持」放行（支持 = 全额 + 部分）", W, "74% 的诉请获支持", "ok"),
      ("合计不能安到单个类目上：「全额支持占74%」拒", W, "全额支持占74%", "reject")]
for name, base_, title, want in r2:
    mm = copy.deepcopy(base_)
    mm["title"] = title
    v, why_ = verdict(mm)
    ok(name, v == want, why_ if isinstance(why_, str) else "")
v, rep = verdict(dict(copy.deepcopy(W), title="全额支持并未过半"))
ok("R2-016 否定约数仍列请核", v == "ok" and any("否定" in w for w in rep["warnings"]))
ok("R2-041 金额「12,34元」千分位不对 → 不认", not cases.amount_in("支付12,34元", 1234, "元")
   and cases.amount_in("支付1,234元", 1234, "元"))
tmp2 = tempfile.mkdtemp()
csv2 = os.path.join(tmp2, "short.csv")
with open(csv2, "w", encoding="utf-8") as f:
    f.write("案号,法院,摘要\n（2025）甲0101民初101号,某某人民法院,摘要一\n（2025）甲0101民初102号\n")
try:
    dd2, _ = cases.ingest([csv2], os.path.join(tmp2, "w"))
    ok("R2-058 短行缺中间列不崩，标出短行", len(dd2) == 2 and dd2[1].get("short_row"), dd2)
except Exception as e:
    ok("R2-058 短行缺中间列不崩，标出短行", False, repr(e))
sc3 = {"fields": [], "quote_mode": "ocr"}
_, st3 = cases.check(sc3, [{"did": "D1", "values": {}}], [{"did": "D1"}], {"D1": "x"})
ok("R2-053 方案设了 quote_mode: ocr → 列请核", any("quote_mode" in r_ for r_ in st3["review"]))
dd3 = [{"did": "D1"}, {"did": "D2", "duplicate_of": "D1", "dup_kind": "内容相同"},
       {"did": "D3", "duplicate_of": "D1", "dup_kind": "内容相同"}]
b3, _ = cases.check({"fields": []}, [{"did": "D1", "include": False, "reason": "重复", "note": "x"},
                                     {"did": "D2", "values": {}}, {"did": "D3", "values": {}}],
                    dd3, {"D1": "a", "D2": "a", "D3": "a"})
ok("R2-057 三份相同、剔一留二 → 拒（同组至多一份）", any("同一组重复" in x for x in b3), b3)
b3, _ = cases.check({"fields": []}, [{"did": "D1", "include": False, "reason": "重复", "note": "x"},
                                     {"did": "D2", "values": {}}, {"did": "D3", "include": False, "reason": "重复"}],
                    dd3, {"D1": "a", "D2": "a", "D3": "a"})
ok("R2-057 对照：三份相同、只留一份 → 过", not b3, b3)
d4 = tempfile.mkdtemp()
b4 = os.path.join(d4, "chart")
for ext, txt in ((".svg", "OLD-SVG"), (".pptx", "OLD-PPTX")):
    with open(b4 + ext, "w", encoding="utf-8") as f:
        f.write(txt)
_orig = os.replace


def _bad_replace(a, b):
    if b.endswith("chart.pptx") and ".nlv-" in a and not os.path.basename(a).startswith("old"):
        raise OSError("注入：第二个文件换不上")
    return _orig(a, b)


os.replace = _bad_replace
try:
    rc4 = make.main([os.path.join(EX, "bar-filings.json"), "-o", b4])
finally:
    os.replace = _orig
ok("R2-060 第二个文件发布失败 → 撤回第一个、旧文件原样放回、退出码 3",
   rc4 == 3 and open(b4 + ".svg", encoding="utf-8").read() == "OLD-SVG" and open(b4 + ".pptx", encoding="utf-8").read() == "OLD-PPTX"
   and sorted(os.listdir(d4)) == ["chart.pptx", "chart.svg"], (rc4, os.listdir(d4)))
import kernel as _k                           # noqa: E402
old1 = tempfile.mkdtemp()
import shutil as _sh                          # noqa: E402
_sh.copytree(_k.V1, os.path.join(old1, "scripts"))
_sh.copytree(os.path.join(_k.V1, "..", "assets"), os.path.join(old1, "assets"))
cp = os.path.join(old1, "scripts", "common.py")
src = open(cp, encoding="utf-8").read().replace(", keep_alnum: bool = False", "")
open(cp, "w", encoding="utf-8").write(src)
ok("R2 P0 旧版 V1（wrap 没有 keep_alnum）被认出「版本过旧」，不再等到出图才 TypeError",
   any("版本过旧" in x for x in _k.missing(os.path.join(old1, "scripts"))) and not _k.missing(_k.V1))

print("　证据角色（R2-078，可选的 C7）")
src7 = "原告诉称：双方系借贷关系。本院认为，原告主张证据不足；双方系买卖关系。判决如下：驳回原告的诉讼请求。"
sc7 = {"fields": [{"key": "view", "label": "法院定性", "options": ["借贷", "买卖"], "quote_from": "court"}]}


def c7(v, q, sc=sc7, src=src7):
    return cases.check(sc, [{"did": "D1", "values": {"view": {"v": v, "q": q}}}], [{"did": "D1"}], {"D1": src})[0]


ok("C7 引当事人诉称当作法院认定 → 拒", any(x.startswith("C7") for x in c7("借贷", "原告诉称：双方系借贷关系")))
ok("C7 引「本院认为」之后的原文 → 过", not c7("买卖", "双方系买卖关系"))
ok("C7 原文里根本没有法院部分（只有诉状、摘要）→ 拒",
   any(x.startswith("C7") for x in c7("借贷", "双方系借贷关系", src="原告诉称：双方系借贷关系。")))
sc7b = {"fields": [{"key": "view", "label": "法院定性", "options": ["借贷", "买卖"]}]}
ok("C7 没开（字段不写 quote_from）→ 与 0.9.1 一样不查", not c7("借贷", "原告诉称：双方系借贷关系", sc=sc7b))

print("十二、防改差")
sys.path.insert(0, HERE)
import golden                                  # noqa: E402
import metamorphic                             # noqa: E402
import spec as _spec                           # noqa: E402
import numtokens as _nt                        # noqa: E402
import re as _re                               # noqa: E402
rows_, vbad = golden.check_verdicts()
ok(f"判定账 {len(rows_)} 条：该过的还过、该拒的还拒", not vbad, vbad[:3])
_, obad = golden.check_outputs()
ok("成品账：每份示例 × 两种风格 × 每种画布的 SVG（整页另加 PPTX）指纹与账一致", not obad, obad[:3])
tm, by_, miss = metamorphic.run()
ok(f"变形测试 {tm} 条（该过 {by_['accept']}、该拒 {by_['reject']}）全对", not miss, miss[:3])


def must_fail(label, patch):
    undo = patch()
    try:
        n = len(metamorphic.run()[2]) + len(golden.check_verdicts()[1])
    finally:
        undo()
    ok(f"防改差能失败 · {label}", n > 0, n)


def _swap(obj, name, val):
    old = getattr(obj, name)
    setattr(obj, name, val)
    return lambda: setattr(obj, name, old)


must_fail("不核主语（改松了）", lambda: _swap(_spec, "_subject", lambda *a, **k: None))
must_fail("不核比较方向（改松了）", lambda: _swap(_spec, "_direction", lambda *a, **k: None))
must_fail("退回 0.8.0 的数字正则（改松了）",
          lambda: _swap(_nt, "_TOKEN", _re.compile(_nt._TOKEN.pattern.replace("(?<![0-9A-Za-z_.])", "(?<![\\w.])"))))
_cn = _spec.check_numbers
must_fail("一律拒带 % 的标题（改严了，误伤对的）",
          lambda: _swap(_spec, "check_numbers",
                        lambda t, m_, d_, w="标题": (_cn(t, m_, d_, w)[0] + (["过严"] if "%" in t else []), [])))
import charts as _charts                       # noqa: E402
_fi = _charts.Frame.__init__


def _thin(self, *a, **k):
    _fi(self, *a, **k)
    self.mx += 1                               # 页边挪 1px：肉眼几乎看不出，成品账必须看得出


_u = _swap(_charts.Frame, "__init__", _thin)
try:
    _, obad2 = golden.check_outputs()
finally:
    _u()
ok("防改差能失败 · 页边悄悄挪了 1px，成品账也认得出", len(obad2) > 0, len(obad2))
import release_gate as _rg                     # noqa: E402
_o12 = "  OK    检查甲 66 条\n  OK    检查乙\n  FAIL  检查丙  → 细节\n"
ok("防改差能失败 · 删一项、加一项，条数不变，发版闸门照样认得出少了哪一项（0.9.8 自检时真发生过）",
   _rg.vanished(_rg.check_names(_o12.replace("检查乙", "检查丁")), _rg.check_names(_o12)) == ["检查乙"]
   and _rg.vanished(_rg.check_names(_o12.replace("66", "67")), _rg.check_names(_o12)) == [])

print("　禁止删除的环境（第三轮测试：WorkBuddy 的「安全删除」沙箱）")
import shutil as _sh2                          # noqa: E402
_rm, _rt, _rp = os.remove, _sh2.rmtree, os.replace


def _no_delete(*a, **k):
    raise PermissionError("沙箱禁止删除")


d5 = tempfile.mkdtemp()
b5 = os.path.join(d5, "chart")
os.remove = _no_delete
_sh2.rmtree = lambda p, ignore_errors=False, **k: None if ignore_errors else _no_delete()
try:
    rc5 = make.main([os.path.join(EX, "bar-filings.json"), "-o", b5])
    after_ok = sorted(os.listdir(d5))
    old_svg = open(b5 + ".svg", "rb").read()

    def _bad2(a, b):
        if b.endswith("chart.pptx") and a.endswith(".nlv-new"):
            raise OSError("注入：第二个文件换不上")
        return _rp(a, b)
    os.replace = _bad2
    rc6 = make.main([os.path.join(EX, "waffle-outcomes.json"), "-o", b5])
finally:
    os.remove, _sh2.rmtree, os.replace = _rm, _rt, _rp
ok("删不掉文件也能正常交付，输出目录里不留临时目录", rc5 == 0 and after_ok == ["chart.pptx", "chart.svg"], after_ok)
ok("删不掉文件时回滚：旧 SVG 原样换回，退出码 3，留下的暂存文件在报错里点名",
   rc6 == 3 and open(b5 + ".svg", "rb").read() == old_svg
   and sorted(f for f in os.listdir(d5) if not f.startswith(".")) == ["chart.pptx", "chart.svg"], os.listdir(d5))
with open(b5 + ".svg", "rb") as f_:
    ok("SVG 一律用 \\n 换行（Windows 上也与 Linux 逐字节一致）", b"\r\n" not in f_.read())

print("　坏输入（开源前第二轮实跑）")
_d10 = tempfile.mkdtemp()
_r10 = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "make.py"), os.path.join(_d10, "路径打错.json"), "-o",
                       os.path.join(_d10, "x")], capture_output=True, text=True, encoding="utf-8")
ok("坏输入：图表说明路径打错，说「找不到」并退出，不甩堆栈", _r10.returncode != 0 and "找不到图表说明" in _r10.stderr + _r10.stdout
   and "Traceback" not in _r10.stderr, (_r10.returncode, (_r10.stderr or _r10.stdout)[-160:]))
with open(os.path.join(_d10, "gbk.json"), "wb") as f_:
    f_.write('{"chart": "bar", "title": "收案"}'.encode("gbk"))
try:
    make.spec_load(os.path.join(_d10, "gbk.json")) if hasattr(make, "spec_load") else __import__("spec").load(os.path.join(_d10, "gbk.json"))
    _e10 = ""
except SpecError as e:
    _e10 = str(e)
except Exception as e:                                # noqa: BLE001
    _e10 = "未处理：" + repr(e)
ok("坏输入：图表说明不是 UTF-8（比如另存成了 GBK），说清楚要 UTF-8，不甩编码异常", "UTF-8" in _e10 and "codec" not in _e10, _e10)

print("　跨 Python 版本一致（开源前实跑：3.11 与 3.12+ 出的图不同）")
import kernel as _K                                 # noqa: E402
_names9 = ["机动车交通事故责任", "物业服务合同", "民间借贷纠纷", "A 地块 1 号楼施工"]
_bad9 = []
for _i in range(1000, 4000, 7):                     # 字号扫一遍：哪个字号上「名字被自己的宽度挤断」都算错
    _f9 = _i / 100 + 0.0037
    for _s9 in _names9:
        _acc = 0.0
        for _ch in _s9:
            _acc += _K._c.char_w(_ch, _f9)
        if _K.text_w(_s9, _f9) != _acc or _K.wrap(_s9, _f9, _K.text_w(_s9, _f9)) != [_s9]:
            _bad9.append((_s9, _f9))
ok("量字宽与 wrap 同次序逐字累加：列宽正好等于名字宽度时不拆行（各字号、3.11 与 3.12+ 一致）", not _bad9, _bad9[:3])
_d9 = tempfile.mkdtemp()
make.main([os.path.join(EX, "hbar-annotated.json"), "--canvas", "portrait", "-o", os.path.join(_d9, "h")])
with open(os.path.join(_d9, "h.svg"), encoding="utf-8") as f_:
    ok("横条图竖版：最宽的类目名「机动车交通事故责任」一行放下（3.12+ 曾被拆成两行）",
       ">机动车交通事故责任</text>" in f_.read())

print("十三、0.9.8 · 第二批学来的（diagram-design、Perspective、案图）")
print("　文档与代码同步（学自 diagram-design 的 verify-docs-sync）")
from spec import CHART_ZH as _CZ                     # noqa: E402
_skill = open(os.path.join(ROOT, "SKILL.md"), encoding="utf-8").read()
_readme = open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()
_cat = open(os.path.join(ROOT, "references", "catalog.md"), encoding="utf-8").read()
_ZH = "零一二三四五六七八九十"


def _zh(n):
    return _ZH[n] if n <= 10 else ("十" + _ZH[n - 10] if n < 20 else str(n))


_said = re.findall(r"([一二三四五六七八九十\d]+)份示例", _skill)
ok(f"SKILL.md 说的示例份数等于 examples/ 里的 {len(EXAMPLES)} 份",
   _said and all(x in (_zh(len(EXAMPLES)), str(len(EXAMPLES))) for x in _said), _said)
_kinds = re.findall(r"([一二三四五六七八九十\d]+)种图", _skill + _readme)
ok(f"SKILL.md 与 README 说的图种数等于 spec 里的 {len(CHARTS)} 种",
   _kinds and all(x in (_zh(len(CHARTS)), str(len(CHARTS))) for x in _kinds), _kinds)
_main, _later = _cat.split("## 首批不做", 1) if "## 首批不做" in _cat else (_cat, "")
ok("catalog.md 的选图表覆盖每一种能画的图", all(f"`{c}`" in _main for c in CHARTS),
   [c for c in CHARTS if f"`{c}`" not in _main])
_plan = " ".join(r.split("|")[2] for r in _later.splitlines() if r.startswith("|") and r.count("|") >= 4)   # 「计划图种」一列
_bad_later = [z for c, z in _CZ.items() if z in _plan] + [w for w in ("瀑布",) if w in _plan and "waterfall" in CHARTS]
ok("catalog.md 的「首批不做」里没有已经能画的图", not _bad_later, _bad_later)
_tbl = _skill.split("各图种的 `data`", 1)[1].split("\n\n", 2)[1] if "各图种的 `data`" in _skill else ""
ok("SKILL.md 的 data 写法表列全了每一种图", all(f"`{c}`" in _tbl for c in CHARTS),
   [c for c in CHARTS if f"`{c}`" not in _tbl])
_lib = json.load(open(os.path.join(ROOT, "library", "index.json"), encoding="utf-8"))
_tax = json.load(open(os.path.join(ROOT, "library", "taxonomy.json"), encoding="utf-8"))
_want = f"{len(_tax['areas'])} 个领域、{len(_tax['scenes'])} 种场合、{_lib['count']} 个场景、{len(_tax['forms'])} 种画法"
ok("SKILL.md 里场景库的四个数与库一致", _want in _skill, _want)

print("　对比度（学自 diagram-design 的 verify-contrast）")
_low = set()
for f in EXAMPLES:
    for st in styles.STYLES:
        for cv in ("slide", "square", "portrait"):
            _svg, _ = make.build(os.path.join(EX, f), st, None, cv)
            _paper = styles.palette(st)[0]["paper"]
            for t_ in re.findall(r"<text [^>]*>", _svg):
                fill_ = re.search(r'fill="(#[0-9A-Fa-f]{6})"', t_).group(1)
                if styles.contrast(fill_, _paper) < 4.5:
                    _low.add((st, fill_, re.search(r'data-role="([^"]+)"', t_).group(1)
                              if "data-role" in t_ else "-", round(styles.contrast(fill_, _paper), 2)))
ok("图上每一个字与纸色的对比度 ≥ 4.5 : 1（WCAG AA，含来源行、刻度）", not _low, sorted(_low)[:4])

print("　一页多图（同一网页里放两张图）")
_s1, _ = make.build(os.path.join(EX, "bar-filings.json"))
_s2, _ = make.build(os.path.join(EX, "waffle-outcomes.json"))
_s1b, _ = make.build(os.path.join(EX, "bar-filings.json"))
_ids1 = set(re.findall(r' id="([^"]+)"', _s1))
_ids2 = set(re.findall(r' id="([^"]+)"', _s2))
ok("两张不同的图，SVG 里的 id 一个都不撞（读屏不会把第二张念成第一张）", _ids1 and not (_ids1 & _ids2), sorted(_ids1 & _ids2))
ok("同一份说明出两次，id 完全一样（确定性不变）", _s1 == _s1b)
_g, _ = make.build(os.path.join(EX, "hbar-causes.json"), "歸藏风")
_refs = set(re.findall(r'url\(#([^)]+)\)', _g)) | set(" ".join(re.findall(r'aria-labelledby="([^"]+)"', _g)).split())
ok("每个 url(#…) 与 aria-labelledby 都指得到本图里的 id", _refs and _refs <= set(re.findall(r' id="([^"]+)"', _g)),
   sorted(_refs - set(re.findall(r' id="([^"]+)"', _g))))

print("　坏结构说人话（学自案图：报错指到字段路径）")
_crash, _vague = [], []
for f in EXAMPLES:
    base_ = ex(f)
    if "dataset" in base_:
        continue                                     # 逐件记录的示例另有一节（数据集 + 视图）
    muts_ = [("data", "items"), ("data", 7), ("data", [])]
    for key_ in ("items", "groups", "nodes", "links", "sources", "targets", "steps"):
        if isinstance(base_["data"].get(key_), list):
            muts_ += [(f"data.{key_}[0]", v_) for v_ in ("x", 7, None, [])]
            muts_ += [(f"data.{key_}[0].{fld}", v_) for fld in ("id", "from", "to")
                      if fld in base_["data"][key_][0] for v_ in ([], {})]
            if key_ == "nodes":
                muts_.append(("data.nodes[0].stage", "一审"))
    for nm_ in ("start", "end", "threshold"):
        if nm_ in base_["data"]:
            muts_.append((f"data.{nm_}", 7))
    muts_ += [("unit", None), ("unit", 7)]
    for path_, val_ in muts_:
        m_ = copy.deepcopy(base_)
        parts_ = re.findall(r"[^.\[\]]+", path_)
        o_ = m_
        for k_ in parts_[:-1]:
            o_ = o_[int(k_)] if k_.isdigit() else o_[k_]
        o_[int(parts_[-1]) if parts_[-1].isdigit() else parts_[-1]] = val_
        try:
            make.build(m_)
        except SpecError as e:
            if path_ not in ("unit",) and path_.split("[")[0].split(".")[0] not in str(e):
                _vague.append(f"{f}:{path_}={val_!r} → {str(e)[:40]}")
        except Exception as e:                       # noqa: BLE001
            _crash.append(f"{f}:{path_}={val_!r} → {type(e).__name__}")
ok("写坏结构（data 不是对象、数组里混进裸值、id 写成列表、stage 写成文字……）一律说人话，不甩 Python 堆栈",
   not _crash, _crash[:3])
ok("这类报错都点名出错的字段", not _vague, _vague[:3])
try:
    _m = ex("bar-filings.json")
    _m["data"]["items"][2]["id"] = 7
    _m["emphasis"] = "7"
    make.build(_m)
    _e = ""
except SpecError as e:
    _e = str(e)
ok("emphasis 写文字 \"7\"、id 写数字 7：直说是类型不一致，不说「没有这个 id」", "一个是文字、一个是数字" in _e, _e[:80])

print("　schema 与代码同步（schema 是给模型与外部工具看的，不能拒掉能出图的说明）")
_sch = json.load(open(os.path.join(ROOT, "schemas", "chart.schema.json"), encoding="utf-8"))
_dprops = set(_sch["properties"]["data"]["properties"])
_used = set()
for f in EXAMPLES:
    _used |= set(ex(f).get("data", {}))
ok("schema 的 data 字段覆盖全部示例用到的字段（含逐级加减的 start / steps / end）", _used <= _dprops, sorted(_used - _dprops))
ok("schema 不要求哑铃写 value（哑铃写 from 与 to）",
   "value" not in _sch["properties"]["data"]["properties"]["items"]["items"].get("required", []))
try:
    import jsonschema as _js                         # 有就全量核；没有也不影响上面两条
    _v = _js.Draft202012Validator(_sch)
    _rej = [f"{f}: {e.message[:60]}" for f in EXAMPLES for e in _v.iter_errors(ex(f))]
    ok("全部示例都过 schema（jsonschema 全量核）", not _rej, _rej[:3])
except ImportError:
    print("  SKIP  全部示例都过 schema：本机没装 jsonschema（不计入通过与失败）")

print("　数据集 + 视图（学自 Perspective：模型只抄逐件记录，数数由脚本做）")
import pivot as _pv                                  # noqa: E402


def _ds(chart, rows, view, **kw):
    m_ = {"chart": chart, "title": kw.pop("title", "示例图"), "scope": "示例", "source": "示例数据", "unit": "件",
          "dataset": {"rows": rows, **({"ref": kw.pop("ref")} if "ref" in kw else {})}, "view": view}
    m_.update(kw)
    return m_


def _err(m_):
    try:
        make.build(m_)
        return ""
    except SpecError as e:
        return str(e)
    except Exception as e:                           # noqa: BLE001
        return "崩了：" + repr(e)


_eq = []
for f in EXAMPLES:
    m0 = ex(f)
    if m0["chart"] not in ("bar", "hbar", "rose", "waffle") or "dataset" in m0:
        continue
    if m0["chart"] == "waffle" and m0["data"].get("measure") != "count":
        continue
    rows_ = [{"类": it["label"]} for it in m0["data"]["items"] for _ in range(int(it["value"]))]
    rows_ = rows_[1::2] + rows_[0::2]                 # 打乱先后：结果不该变
    m1 = _ds(m0["chart"], rows_, {"group_by": "类", "sort": [it["label"] for it in m0["data"]["items"]]},
             title=m0["title"], n=len(rows_))
    if "order" in m0:
        m1["order"] = m0["order"]
    _, r1 = make.build(m1)
    got = [(i["label"], i["value"]) for i in r1["spec"]["data"]["items"]]
    want = [(i["label"], i["value"]) for i in m0["data"]["items"]]
    if got != want:
        _eq.append((f, got[:3], want[:3]))
ok("把示例的每一项摊回逐件记录（打乱先后），按 view 数回来，与手写的 data 一项不差", not _eq, _eq[:2])
_svg, _r = make.build(os.path.join(EX, "dataset-causes.json"))
_t = _r["spec"]["_trace"]
_ids = set(re.findall(r'data-id="([^"]+)"', _svg))
ok("图上每一个数据项都追得到 dataset 的行（逐格溯源），件数与行数相等",
   _ids and _ids <= set(_t["cells"]) and all(len(_t["cells"][i["id"]]["rows"]) == i["value"]
                                             for i in _r["spec"]["data"]["items"]), sorted(_ids - set(_t["cells"])))
ok("溯源带上 ref 列（编号），律师按编号翻回原件", all(len(c["refs"]) == len(c["rows"]) for c in _t["cells"].values()))
ok("缺「案由」的那一行：不计入，交付清单点名行号", any("没写「案由」" in w and "行号 7" in w for w in _r["warnings"]), _r["warnings"])
ok("top + other：只留前几类，其余并成「其他」并压在最后", [i["label"] for i in _r["spec"]["data"]["items"]][-1] == "其他"
   and _r["spec"]["n"] == sum(i["value"] for i in _r["spec"]["data"]["items"]))
_d11 = tempfile.mkdtemp()
_rc = make.main([os.path.join(EX, "dataset-causes.json"), "-o", os.path.join(_d11, "c")])
ok("命令行出图：同时写出 c.trace.json（用了 dataset 就一定有溯源文件）",
   _rc == 0 and os.path.exists(os.path.join(_d11, "c.trace.json"))
   and json.load(open(os.path.join(_d11, "c.trace.json"), encoding="utf-8"))["kept"] == 30, os.listdir(_d11))
_rows_s = ([{"一审": "判决", "上诉": "上诉", "二审": "维持"}] * 6 + [{"一审": "判决", "上诉": "上诉", "二审": "改判"}] * 2
           + [{"一审": "判决", "上诉": "服判"}] * 4 + [{"一审": "调解"}] * 3)
_e = _err(_ds("sankey", _rows_s, {"stages": ["一审", "上诉", "二审"]}, title="上诉 8 件，改判 2 件"))
ok("桑基：一审「调解」后面没有下一段 → 起点没有流出，拒（不让模型以为画出来了）", "没有流出" in _e, _e[:60])
_svgS, _rS = make.build(_ds("sankey", _rows_s[:12], {"stages": ["一审", "上诉", "二审"]}, title="上诉 8 件，改判 2 件",
                           emphasis="二审=改判"))
_lk = {(l_["from"], l_["to"]): l_["value"] for l_ in _rS["spec"]["data"]["links"]}
ok("桑基：按逐件记录数出每一段的流量，守恒自动成立", _lk.get(("上诉=上诉", "二审=改判")) == 2
   and _lk.get(("一审=判决", "上诉=服判")) == 4 and _rS["spec"]["n"] == 12 and not _rS["problems"], _lk)
_e = _err(_ds("sankey", _rows_s[:12] + [{"一审": "判决", "上诉": "上诉"}], {"stages": ["一审", "上诉", "二审"]},
              title="上诉 9 件"))
ok("桑基：同一节点有的往下走、有的缺下一段 → 点名行号，不报「进出不等」这种看不懂的话", "没写「二审」" in _e and "行号 12" in _e, _e[:80])
_rows_r = [{"付": "甲公司", "收": "王某", "额": 100}, {"付": "甲公司", "收": "丙公司", "额": 50},
           {"付": "乙公司", "收": "王某", "额": 70}, {"付": "乙公司", "收": "丙公司", "额": 30}]
_, _rR = make.build(_ds("ribbon", _rows_r, {"from": "付", "to": "收", "measure": {"sum": "额"}},
                        title="王某收到 170 万元", unit="万元", emphasis="收=王某"))
ok("汇入图：按「付 → 收」把金额加起来，id 写成「字段=值」两侧不会撞名",
   {(l_["from"], l_["to"]): l_["value"] for l_ in _rR["spec"]["data"]["links"]}[("付=甲公司", "收=王某")] == 100
   and _rR["spec"]["n"] == 4)
_, _rW = make.build(_ds("waffle", [{"r": "支持"}] * 130 + [{"r": "驳回"}] * 70, {"group_by": "r"}, title="驳回占 35%"))
ok("百点方阵：件数超过 100 时由脚本换成百分比（合计正好 100），n 仍是件数",
   _rW["spec"]["data"]["measure"] == "percent" and [i["value"] for i in _rW["spec"]["data"]["items"]] == [65.0, 35.0]
   and _rW["spec"]["n"] == 200)
_, _rT = make.build(_ds("strip", [{"程序": "简易", "天": 30}, {"程序": "简易", "天": 45}, {"程序": "普通", "天": 120},
                                  {"程序": "普通"}], {"group_by": "程序", "values": "天"}, title="普通程序 1 件"))
ok("逐件分布：按组收集每件的值，缺值的那件点名不计", [g["values"] for g in _rT["spec"]["data"]["groups"]] == [[30, 45], [120]]
   and any("没写「天」" in w for w in _rT["warnings"]))
_bad = [
    ("dataset 没有 view", lambda: {k: v for k, v in _ds("bar", [{"a": 1}], {}).items() if k != "view"}, "一起给"),
    ("一行不是对象", lambda: _ds("bar", [{"a": "x"}, "x"], {"group_by": "a"}), "dataset.rows[1]"),
    ("求和的列不是数字", lambda: _ds("hbar", [{"a": "x", "v": 1}, {"a": "y", "v": "三"}], {"group_by": "a", "measure": {"sum": "v"}}),
     "dataset.rows[1].v"),
    ("筛完一行不剩", lambda: _ds("bar", [{"a": "x"}, {"a": "y"}], {"group_by": "a", "filter": {"a": "z"}}), "一行都不剩"),
    ("n 与逐件记录对不上", lambda: _ds("bar", [{"a": "x"}, {"a": "y"}], {"group_by": "a"}, n=5), "按 dataset 算是 2"),
    ("view 拼错字段", lambda: _ds("bar", [{"a": "x"}, {"a": "y"}], {"groupby": "a"}), "groupby"),
    ("哑铃用 dataset", lambda: _ds("dumbbell", [{"a": "x"}], {"group_by": "a"}), "直接写 data"),
    ("玫瑰按金额求和", lambda: _ds("rose", [{"a": "x", "v": 1}] * 3, {"group_by": "a", "measure": {"sum": "v"}}), "按件数画"),
    ("列名写错", lambda: _ds("bar", [{"a": "x"}, {"a": "y"}], {"group_by": "案由"}), "没有一行写了「案由」"),
    ("重音给了被并进「其他」的类目", lambda: _ds("hbar", [{"a": "x"}] * 3 + [{"a": "y"}] * 2 + [{"a": "z"}],
                                               {"group_by": "a", "top": 2}, emphasis="z"), "并进了「其他」"),
]
_miss = [lab for lab, mk, needle in _bad if needle not in _err(mk())]
ok(f"数据集 + 视图写坏的 {len(_bad)} 种情形：都说人话、点名字段", not _miss, [(lab, _err(mk())[:50]) for lab, mk, _n in _bad
                                                               if lab in _miss][:3])
_svgA, _rA = make.build(os.path.join(EX, "dataset-causes.json"))
_man = module.manifest(_rA, [], _rA["spec"])
_svgB, _ = make.build(copy.deepcopy(_man["spec"]))
ok("V7 收进课件后按模块清单重画：与原图逐字节一致；清单里只带用户写的 dataset、view，算出来的不带",
   _svgA == _svgB and _man["spec"] == ex("dataset-causes.json"))
_hand = copy.deepcopy(_man["spec"])
_hand["data"] = copy.deepcopy(_rA["spec"]["data"])
_hand["data"]["items"][0]["value"] += 1
ok("给了 dataset 又手改 data.items：两边对不上就拒，不悄悄用哪一边", "不一致" in _err(_hand))
_sw = copy.deepcopy(_man["spec"])
_sw["chart"] = "bar"
ok("V7 换图种：模块清单里的横条换成竖柱，按 dataset 重算（第二轮实跑：原来被「为横条算的数」挡住）", _err(_sw) == "", _err(_sw)[:60])

print("　每条守卫都有改坏验证（学自 diagram-design 的 break-test 规矩：从约定变成机器检查）")


def _guard_tags(guards_src, break_src):
    made = set(re.findall(r'bad\.append\(f?"(G\d+)\b', guards_src))
    tried = set(re.findall(r'trial(?:_obj)?\([^)]*?"(G\d+)"', break_src, re.S))
    return made, tried


_gsrc = open(os.path.join(ROOT, "scripts", "guards.py"), encoding="utf-8").read()
_bsrc = open(os.path.join(HERE, "break_tests.py"), encoding="utf-8").read()
_made, _tried = _guard_tags(_gsrc, _bsrc)
ok(f"guards.py 报得出的 {len(_made)} 条守卫，break_tests.py 里每一条都有改坏验证",
   _made and _made <= _tried, sorted(_made - _tried, key=lambda x: int(x[1:])))
_m2, _t2 = _guard_tags(_gsrc + '\n        bad.append(f"G99 新守卫：……")', _bsrc)
ok("这条检查自己能失败：加一条没配改坏验证的 G99，会被认出来", "G99" in _m2 - _t2)

print("　全插件：命令行 --help 只打印用法、坏输入说人话（学自 VGraph 与案图）")
_skills = os.path.dirname(ROOT)
_mods = [d for d in ("mqc-litigation-visual-redraw", "mqc-timeline-master", "mqc-legal-relation-master",
                     "mqc-chronicle-master", "mqc-trial-confrontation-master", "mqc-legal-chart-master")
         if os.path.isdir(os.path.join(_skills, d, "scripts"))]
if len(_mods) < 6:
    print("  SKIP  这两项要在完整仓库里运行（不计入通过与失败）")
else:
    from concurrent.futures import ThreadPoolExecutor as _TPE

    def _clis(mods, walk):
        for d_ in mods:
            sd = os.path.join(_skills, d_, "scripts")
            for root_, _dirs, fs_ in (os.walk(sd) if walk else [(sd, [], os.listdir(sd))]):
                for fn in sorted(fs_):
                    p_ = os.path.join(root_, fn)
                    if fn.endswith(".py") and "__main__" in open(p_, encoding="utf-8").read():
                        yield d_, sd, p_

    def _run(job):
        argv, label, need_out = job
        cwd_ = tempfile.mkdtemp()
        try:
            r_ = subprocess.run(argv, cwd=cwd_, capture_output=True, text=True, encoding="utf-8",
                                errors="replace", timeout=120)
        except subprocess.TimeoutExpired:
            return f"{label} 超时"
        bad_ = "Traceback" in r_.stderr or (need_out and (r_.returncode != 0 or os.listdir(cwd_)
                                                         or not r_.stdout.strip()))
        return label if bad_ else None

    _jobs = [([sys.executable, p_, "--help"], f"{d_}/{os.path.relpath(p_, sd)}", True)
             for d_, sd, p_ in _clis(_mods, True)]
    with _TPE(8) as _ex:
        _hb = [x for x in _ex.map(_run, _jobs) if x]
    ok("V1–V6 每个命令行脚本：--help 退出码 0、打印用法、不甩堆栈、不写任何文件", not _hb, _hb[:4])
    _bd = tempfile.mkdtemp()
    with open(os.path.join(_bd, "坏.json"), "w", encoding="utf-8") as f_:
        f_.write('{"a": 1,,}')
    with open(os.path.join(_bd, "gbk.json"), "wb") as f_:
        f_.write(b"\xff\xfe\x00bad")
    _jobs = [([sys.executable, p_, os.path.join(_bd, arg), os.path.join(tempfile.mkdtemp(), "out")],
              f"{d_[4:]}/{os.path.basename(p_)} {arg}", False)
             for d_, sd, p_ in _clis(_mods[:5], False) for arg in ("不存在.json", "坏.json", "gbk.json")]
    with _TPE(8) as _ex:
        _tb = [x for x in _ex.map(_run, _jobs) if x]
    ok("V1–V5 每个命令行脚本：路径打错、JSON 写坏、文件不是 UTF-8，一律说人话，不甩 Python 堆栈（原来 136 处）",
       not _tb, _tb[:4])
    _v6 = os.path.join(ROOT, "scripts")
    _jobs = [([sys.executable, os.path.join(_v6, "cases.py")] + a, "cases.py " + a[0] + " " + os.path.basename(a[1]), False)
             for a in (["ingest", "不存在.pdf", "-w", tempfile.mkdtemp()], ["ingest", os.path.join(_bd, "坏.json"), "-w", tempfile.mkdtemp()],
                       ["check", "不存在.json", "x.json", "-w", tempfile.mkdtemp()],
                       ["check", os.path.join(_bd, "坏.json"), os.path.join(_bd, "坏.json"), "-w", tempfile.mkdtemp()])]
    _jobs += [([sys.executable, os.path.join(_v6, "module.py"), "fit", os.path.join(_bd, a)], "module.py fit " + a, False)
              for a in ("不存在.json", "坏.json", "gbk.json")]
    with _TPE(8) as _ex:
        _tb6 = [x for x in _ex.map(_run, _jobs) if x]
    _r6 = subprocess.run([sys.executable, os.path.join(_v6, "cases.py"), "ingest", "不存在.pdf", "-w", tempfile.mkdtemp()],
                         capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=tempfile.mkdtemp())
    ok("V6 类案编码与模块清单的命令行：坏输入也说人话；路径打错说「找不到」，不再说成「文件可能损坏」",
       not _tb6 and "找不到" in _r6.stderr + _r6.stdout and "损坏" not in _r6.stderr + _r6.stdout, _tb6[:3])

    print("　在用户的工作目录里运行（学自案图：命令在哪儿都能跑、产物不进技能目录）")
    _miss = [d_ for d_ in _mods + ["mqc-legal-courseware-master"]
             if not re.search(r"运行与交付须知|Where to run, where outputs go",
                              open(os.path.join(_skills, d_, "SKILL.md"), encoding="utf-8").read())]
    ok("七个模块的 SKILL.md 都写明：在用户的工作目录里跑、产物不写进技能目录、没看图不说看过", not _miss, _miss)
    _r2 = subprocess.run([sys.executable, os.path.join(_skills, "mqc-timeline-master", "scripts", "pipeline.py"), "next"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=tempfile.mkdtemp(prefix="用户 "))
    _hint = re.findall(r"python3 (\"[^\"]+\"|\S+\.py)", _r2.stdout)
    ok("时间轴大师在用户目录里打印的下一步命令，写的都是脚本的真实路径，照抄就能跑（原来是 python pipeline.py，只在 scripts 目录里能跑）",
       _hint and all(os.path.isfile(h.strip('"')) for h in _hint), _r2.stdout[-200:])

    print("　Windows 真实输入（0.9.8 第四轮自检：记事本存的 UTF-8 带 BOM、记事本与 Excel 默认的 GBK）")
    _wd = tempfile.mkdtemp(prefix="中文 路径 ")

    def _bom(src):
        t = open(src, encoding="utf-8").read().replace("\r\n", "\n").replace("\n", "\r\n")
        p_ = os.path.join(_wd, "BOM " + os.path.basename(src))
        with open(p_, "wb") as f_:
            f_.write(b"\xef\xbb\xbf" + t.encode("utf-8"))
        return p_

    _sk = _skills
    try:                                             # V4、V5 出 Excel 要 openpyxl：没装的电脑（CI 的多版本任务）不测这两项
        import openpyxl                              # noqa: F401
        _xl = True
    except ImportError:
        _xl = False
    _bj = [
        ([sys.executable, os.path.join(_sk, "mqc-litigation-visual-redraw", "scripts", "render.py"),
          _bom(os.path.join(_sk, "mqc-litigation-visual-redraw", "examples", "flowchart.json")),
          os.path.join(_wd, "v1 输出", "f"), "--formats=svg"], "V1 render.py", False),
        ([sys.executable, os.path.join(_sk, "mqc-timeline-master", "scripts", "render_figure.py"),
          _bom(os.path.join(_sk, "mqc-timeline-master", "examples", "two-sides-numbered.json")),
          os.path.join(_wd, "v2 输出.svg")], "V2 render_figure.py", False),
        ([sys.executable, os.path.join(_sk, "mqc-legal-relation-master", "scripts", "make.py"),
          _bom(os.path.join(_sk, "mqc-legal-relation-master", "examples", "relations-demo.json")), "--plan-only"],
         "V3 make.py", False),
        ([sys.executable, os.path.join(_sk, "mqc-chronicle-master", "scripts", "pipeline.py"),
          _bom(os.path.join(_sk, "mqc-chronicle-master", "examples", "case-text-layer.json")), "",
          os.path.join(_wd, "v4 输出")], "V4 pipeline.py", False),
        ([sys.executable, os.path.join(_sk, "mqc-trial-confrontation-master", "scripts", "pipeline.py"),
          _bom(os.path.join(_sk, "mqc-trial-confrontation-master", "examples", "matrix-input.json")),
          os.path.join(_wd, "v5 输出")], "V5 pipeline.py", False),
        ([sys.executable, os.path.join(_v6, "make.py"), _bom(os.path.join(EX, "dataset-causes.json")),
          "-o", os.path.join(_wd, "v6 输出", "c")], "V6 make.py", False),
    ]

    def _ok_rc(job):
        argv, label, _ = job
        r_ = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace",
                            cwd=tempfile.mkdtemp(), timeout=600)
        return None if r_.returncode == 0 else f"{label}：{(r_.stderr or r_.stdout).strip().splitlines()[-1][:60]}"
    if not _xl:
        _bj = [j for j in _bj if not j[1].startswith(("V4", "V5"))]
        print("  （本机没装 openpyxl：BOM 一项只测 V1、V2、V3、V6）")
    with _TPE(6) as _ex:
        _bf = [x for x in _ex.map(_ok_rc, _bj) if x]
    ok("V1–V6：记事本另存的「UTF-8 带 BOM」+ Windows 换行 + 中文带空格路径，照常出图（原来六个模块全报「JSON 写坏了」）",
       not _bf, _bf[:3])
    _law = "原告甲公司与被告乙公司于2025年3月13日签订《货物买卖合同》，约定总价65万元，被告应于交货后七日内验收。"
    _gp, _bp = os.path.join(_wd, "判决书 GBK.txt"), os.path.join(_wd, "判決書 Big5.txt")
    with open(_gp, "wb") as f_:
        f_.write(_law.encode("gbk"))
    with open(_bp, "wb") as f_:
        f_.write("原告甲公司與被告乙公司於民國一一四年三月簽訂《貨物買賣合同》，約定總價新臺幣六十五萬元。".encode("big5"))
    _got, _bad = [], []
    for m_ in ("mqc-chronicle-master", "mqc-trial-confrontation-master"):
        _code = (f"import sys,json;sys.path.insert(0,{os.path.join(_sk, m_, 'scripts')!r});import ingest;"
                 f"r=ingest.ingest([sys.argv[1]],sys.argv[2]);print(json.dumps(r[1],ensure_ascii=False))")
        for src_, want in ((_gp, _law), (_bp, None)):
            r_ = subprocess.run([sys.executable, "-c", _code, src_, tempfile.mkdtemp()], capture_output=True, text=True,
                                encoding="utf-8", errors="replace", env=dict(os.environ, PYTHONIOENCODING="utf-8"))
            if want is not None:
                _got.append(m_[4:] + (" 对" if want in r_.stdout else " 错：" + r_.stdout[-60:]))
            else:
                _bad.append(m_[4:] + (" 拒" if r_.returncode != 0 and "UTF-8" in r_.stderr else " 未拒：" + r_.stdout[-60:]))
    _code2 = (f"import sys,json;sys.path.insert(0,{os.path.join(_sk, 'mqc-timeline-master', 'scripts')!r});"
              f"import read_source;print(json.dumps(read_source.read(sys.argv[1]),ensure_ascii=False))")
    r_ = subprocess.run([sys.executable, "-c", _code2, _gp], capture_output=True, text=True, encoding="utf-8", errors="replace",
                        env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    _got.append("timeline" + (" 对" if "原告甲公司与被告乙公司" in r_.stdout else " 错"))
    ok("记事本存的 GBK 判决书：V2 / V4 / V5 读成原文，不再读成乱码当作已读（原来 V4、V5 悄悄读成「ԭ׹˾…」）",
       all(x.endswith(" 对") for x in _got), _got)
    ok("Big5 等认不准的编码：V4 / V5 停下，请用户另存为 UTF-8，不把乱码当原文", all(x.endswith(" 拒") for x in _bad), _bad)
    _cp = os.path.join(_wd, "案例清单 Excel默认.csv")
    with open(_cp, "wb") as f_:
        f_.write("案号,法院,裁判结果\r\n（2023）京01民终1号,北京市第一中级人民法院,驳回\r\n".encode("gbk"))
    try:
        _dd, _ = cases.ingest([_cp], os.path.join(_wd, "cw"))
        _e = _dd[0].get("court", "")
    except BaseException as e:                       # noqa: BLE001
        _e = repr(e)
    ok("Excel 默认另存的 GBK 案例清单：按 GBK 读入并提示（原来甩 UnicodeDecodeError）", _e == "北京市第一中级人民法院", _e[:60])
    _nl = tempfile.mkdtemp()                         # 模拟「只 pip install openpyxl」的电脑：没有 lxml
    with open(os.path.join(_nl, "sitecustomize.py"), "w", encoding="utf-8") as f_:
        f_.write("import sys\nsys.modules['lxml'] = None\nsys.modules['lxml.etree'] = None\n")
    _out4 = os.path.join(_wd, "v4 无 lxml")
    _pp = os.pathsep.join(x for x in (_nl, os.environ.get("PYTHONPATH")) if x)
    _r4 = None if not _xl else subprocess.run([sys.executable, os.path.join(_sk, "mqc-chronicle-master", "scripts", "pipeline.py"),
                          os.path.join(_sk, "mqc-chronicle-master", "examples", "case-text-layer.json"), "", _out4],
                         capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=tempfile.mkdtemp(),
                         env=dict(os.environ, PYTHONPATH=_pp), timeout=600)
    _x4 = os.path.join(_out4, "案件大事记母表.xlsx")
    _cached = (len(re.findall(r"<f>ROW\(\)-\d+</f><v>\d+</v>",
                              __import__("zipfile").ZipFile(_x4).read("xl/worksheets/sheet1.xml").decode()))
               if os.path.exists(_x4) else 0)
    if _r4 is None:
        print("  SKIP  V4 没有 lxml 时照常交付：本机连 openpyxl 都没装，测不了（不计入通过与失败）")
    else:
        ok("V4 在只装 openpyxl、没有 lxml 的电脑上照常交付，序号列带缓存值（原来拒绝交付，或序号在预览里是空的）",
           _r4.returncode == 0 and _cached > 0, (_r4.returncode, _cached, (_r4.stdout + _r4.stderr).strip().splitlines()[-1:]))

    print("　中文 Windows 的编码（0.9.8 第六轮：学积成在 Windows 上跑 CI；这里用 GBK 区域设置模拟）")
    import ast as _ast

    def _enc_misses(src, where):
        """不写编码就按系统区域设置读写的地方。中文 Windows 上那是 GBK，而本项目的文件与子进程输出一律是 UTF-8。"""
        out_ = []
        for n in _ast.walk(_ast.parse(src)):
            if not isinstance(n, _ast.Call):
                continue
            f = n.func
            name = f.attr if isinstance(f, _ast.Attribute) else (f.id if isinstance(f, _ast.Name) else "")
            kw = {k.arg for k in n.keywords}
            if "encoding" in kw:
                continue
            if name == "open" and isinstance(f, _ast.Name):
                mode = n.args[1].value if len(n.args) > 1 and isinstance(n.args[1], _ast.Constant) else "r"
                mode = next((k.value.value for k in n.keywords if k.arg == "mode" and isinstance(k.value, _ast.Constant)), mode)
                bad = "b" not in str(mode)
            elif name == "read_text":
                bad = not n.args
            elif name == "write_text":
                bad = len(n.args) < 2
            else:
                bad = (name in ("run", "check_output", "Popen") and isinstance(f, _ast.Attribute)
                       and bool({"text", "universal_newlines"} & kw))
            if bad:
                out_.append(f"{where}:{n.lineno} {name}")
        return out_

    _em = []
    for d_ in _mods + ["mqc-legal-courseware-master"]:
        for sub_ in ("scripts", "tests"):
            for root_, _dirs, fs_ in os.walk(os.path.join(_skills, d_, sub_)):
                for fn in sorted(fs_):
                    if fn.endswith(".py"):
                        p_ = os.path.join(root_, fn)
                        _em += _enc_misses(open(p_, encoding="utf-8").read(), f"{d_[4:]}/{os.path.relpath(p_, os.path.join(_skills, d_))}")
    ok("七个模块的脚本与测试：读写文本、读子进程输出，一律写明 UTF-8（原来 60 处按系统编码，中文 Windows 上读坏自己画的 SVG、把写好的 Word 报成没写成）",
       not _em, _em[:5])
    _probe = _enc_misses('open(p)\nopen(p, "rb")\nopen(p, encoding="utf-8")\nsubprocess.run(a, text=True)\nPath(p).read_text()\n', "probe")
    ok("这条检查自己能失败：没写编码的 open、子进程、read_text 都被认出来，二进制与写了编码的不算", len(_probe) == 3, _probe)
    _HELP_LINE = 'getattr(__import__("sys").stdout, "reconfigure"'
    _nu = []
    for d_ in _mods + ["mqc-legal-courseware-master"]:
        for root_, _dirs, fs_ in os.walk(os.path.join(_skills, d_, "scripts")):
            for fn in sorted(fs_):
                p_ = os.path.join(root_, fn)
                if not fn.endswith(".py"):
                    continue
                s_ = open(p_, encoding="utf-8").read()
                if not re.search(r"^if __name__ *== *['\"]__main__['\"]", s_, re.M):
                    continue
                body_ = "\n".join(l_ for l_ in s_.splitlines() if _HELP_LINE not in l_)
                if not re.search(r"reconfigure\(encoding=\"utf-8\"\)", body_):
                    _nu.append(f"{d_[4:]}/{fn}")
    ok("七个模块的每个命令行脚本都把输出固定成 UTF-8（原来 7 个没有——法律图表大师 6 个、关系图大师的 export_guard 1 个：中文 Windows 上外部 AI 读到乱码，生僻字人名还会让它在图画好之后崩掉）",
       not _nu, _nu[:6])
    _loc = tempfile.mkdtemp()
    _lg = shutil.which("localedef") and subprocess.run(["localedef", "-i", "zh_CN", "-f", "GBK", os.path.join(_loc, "zh_CN.GBK")],
                                                         capture_output=True).returncode in (0, 1)
    _genv = dict(os.environ, LOCPATH=_loc, LC_ALL="zh_CN.GBK")
    for _k in ("PYTHONIOENCODING", "PYTHONUTF8", "LANG", "LC_CTYPE"):
        _genv.pop(_k, None)
    _gbk_ok = _lg and subprocess.run([sys.executable, "-c", "import locale;print(locale.getpreferredencoding(False))"],
                                     capture_output=True, env=_genv).stdout.strip().lower() == b"gbk"
    if not _gbk_ok:
        print("  SKIP  模拟中文 Windows（GBK）：本机造不出 GBK 区域设置（没有 localedef，例如 Windows、macOS），不计入通过与失败")
    else:
        _gd = tempfile.mkdtemp()
        _rm = ex("bar-filings.json")
        for _it in _rm["data"]["items"]:
            if _it["id"] == _rm["emphasis"]:
                _it["id"] = "䶮"
        _rm["emphasis"] = "䶮"
        with open(os.path.join(_gd, "rare.json"), "w", encoding="utf-8") as f_:
            json.dump(_rm, f_, ensure_ascii=False)
        _rg = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "make.py"), "rare.json", "-o", "o/rare"],
                             capture_output=True, env=_genv, cwd=_gd, timeout=300)
        _txt = _rg.stdout.decode("utf-8", "replace")
        ok("模拟中文 Windows：编号里有 GBK 没有的生僻字（䶮），照常出图、输出是 UTF-8（原来图画好后崩在打印清单上，退出码 1）",
           _rg.returncode == 0 and "䶮" in _txt and "交付清单" in _txt, (_rg.returncode, _rg.stderr.decode("utf-8", "replace")[-160:]))
        _fb = tempfile.mkdtemp()
        with open(os.path.join(_fb, "node"), "w", encoding="utf-8") as f_:      # 假的 node：只写出文件、印一行 UTF-8
            f_.write(f"#!{sys.executable}\nimport sys\nopen(sys.argv[3], 'wb').write(b'PK')\n"
                     "sys.stdout.buffer.write('写出 王某案-溯源索引.docx 2 字节\\n'.encode('utf-8'))\n")
        os.chmod(os.path.join(_fb, "node"), 0o755)
        _code3 = (f"import sys,os;sys.path.insert(0,{os.path.join(_skills, 'mqc-timeline-master', 'scripts')!r});"
                  "import pipeline as P;P._kill_autospace=lambda p:None;"
                  "P._trace([{'src_sids':[0],'no':'1','head':'签约'}],['甲乙于某日签约。'],{'title':'x'},os.path.join(sys.argv[1],'case.svg'));"
                  "print(sorted(os.listdir(sys.argv[1])))")
        _gd3 = tempfile.mkdtemp()
        with open(os.path.join(_fb, "trace_probe.py"), "w", encoding="utf-8") as f_:   # 写成文件再跑：-c 的中文走命令行编码
            f_.write(_code3.replace(";", "\n"))
        _r3 = subprocess.run([sys.executable, os.path.join(_fb, "trace_probe.py"), _gd3], capture_output=True,
                             env=dict(_genv, PATH=_fb + os.pathsep + os.environ.get("PATH", "")), timeout=120)
        _fs3 = os.listdir(_gd3)
        ok("模拟中文 Windows：时间轴大师的 Word 溯源索引写好了就算写好，不再因 node 的 UTF-8 输出解码失败报成「没写成」、另出一份 Markdown",
           _r3.returncode == 0 and any(x.endswith(".docx") for x in _fs3) and not any(x.endswith(".md") for x in _fs3),
           (_r3.returncode, _fs3, _r3.stderr.decode("utf-8", "replace")[-160:]))

    print("　装得上（开源前检查：技能的前置字段与插件清单，写坏了用户装不上或认不出）")

    def _frontmatter(text):
        """SKILL.md 开头 --- 之间的 name 与 description（只用标准库；description 支持单行、引号与 >- / | 折行写法）。"""
        m_ = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n", text, re.S)
        if not m_:
            return None, None
        lines_, out_ = m_.group(1).split("\n"), {}
        i_ = 0
        while i_ < len(lines_):
            km = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", lines_[i_])
            i_ += 1
            if not km:
                continue
            key, val = km.group(1), km.group(2).strip()
            if val[:1] in (">", "|"):
                body = []
                while i_ < len(lines_) and (lines_[i_].startswith((" ", "\t")) or not lines_[i_].strip()):
                    body.append(lines_[i_].strip())
                    i_ += 1
                val = " ".join(x for x in body if x) if val[0] == ">" else "\n".join(body).strip()
            elif val[:1] in "\"'" and val[-1:] == val[:1] and len(val) > 1:
                val = val[1:-1]
            out_[key] = val
        return out_.get("name"), out_.get("description")

    _fm = []
    for d_ in _mods + ["mqc-legal-courseware-master"]:
        nm_, de_ = _frontmatter(open(os.path.join(_skills, d_, "SKILL.md"), encoding="utf-8").read())
        if nm_ != d_:
            _fm.append(f"{d_}：name 是 {nm_!r}，应与目录名相同")
        elif not re.fullmatch(r"[a-z0-9-]{1,64}", nm_) or re.search(r"anthropic|claude", nm_):
            _fm.append(f"{d_}：name 只能是小写字母、数字、连字符，64 字以内，不含保留词")
        if not de_ or len(de_) > 1024:
            _fm.append(f"{d_}：description {'是空的' if not de_ else f'有 {len(de_)} 字，超过 1024'}")
        elif re.search(r"<[A-Za-z/]", de_):
            _fm.append(f"{d_}：description 里有尖括号标签")
    ok("七个模块的 SKILL.md 前置字段都装得上：name 与目录同名、写法合规，description 不空且不超过 1024 字（超了技能装不上）",
       not _fm, _fm[:4])
    _probe_fm = _frontmatter("---\nname: x-y\nmetadata:\n  v: 1\ndescription: >-\n  " + "长" * 1030 + "\n  尾\n---\n正文")
    ok("这条检查自己能失败：折行写的 1032 字 description 被量出来", _probe_fm == ("x-y", "长" * 1030 + " 尾"), _probe_fm[1][:20] if _probe_fm[1] else None)
    _repo = os.path.dirname(_skills)                                   # plugins/mqc-nlv
    _plug = os.path.join(_repo, ".claude-plugin", "plugin.json")
    _mk = os.path.join(os.path.dirname(os.path.dirname(_repo)), ".claude-plugin", "marketplace.json")   # 仓库根
    try:
        _pj = json.load(open(_plug, encoding="utf-8"))
        _mj = json.load(open(_mk, encoding="utf-8"))
        _src = [p_ for p_ in _mj.get("plugins", []) if p_.get("name") == _pj.get("name")]
        _pm = [] if _src else [f"marketplace.json 里没有名为 {_pj.get('name')} 的插件"]
        for p_ in _src:
            if os.path.normpath(os.path.join(os.path.dirname(os.path.dirname(_mk)), p_.get("source", ""))) != os.path.normpath(_repo):
                _pm.append(f"marketplace.json 的 source {p_.get('source')!r} 指不到插件目录")
    except (OSError, ValueError) as e:
        _pm = [f"插件清单读不了：{e}"]
    ok("插件清单（plugin.json、marketplace.json）是合法 JSON，名字对得上，source 指向插件目录", not _pm, _pm)
    _nocl = [d_ for d_ in _mods + ["mqc-legal-courseware-master"] if not os.path.isfile(os.path.join(_skills, d_, "CHANGELOG.md"))]
    ok("七个模块都有 CHANGELOG.md（PR 模板与 CONTRIBUTING 要求在对应模块记一笔；原来 V3、V4、V5 没有）", not _nocl, _nocl)

    print("　更新版本写的文件（学自案图：文件比程序新，就明说「请升级」，不说成文件坏了）")
    _up = []
    sys.path.insert(0, os.path.join(_skills, "mqc-litigation-visual-redraw", "scripts"))
    import common as _v1common
    _m1 = json.load(open(os.path.join(_skills, "mqc-litigation-visual-redraw", "examples", "flowchart.json"), encoding="utf-8"))
    for _sv, _want in ((2, "newer version"), ("x", "unsupported")):
        try:
            _v1common.validate_map(dict(_m1, schema_version=_sv))
            _up.append(f"V1 {_sv!r} 没拦")
        except RuntimeError as e:
            if _want not in str(e) or (_sv == 2 and "update the plugin" not in str(e)):
                _up.append(f"V1 {_sv!r}：{str(e)[:60]}")
    _vm = os.path.join(_skills, "mqc-timeline-master", "scripts", "validate_map.py")
    _ex2 = os.path.join(_skills, "mqc-timeline-master", "examples", "dated-limitation.json")
    _m2 = json.load(open(_ex2, encoding="utf-8"))
    _wd2 = tempfile.mkdtemp()
    for _sv, _want in ((3, "升级"), (0, "应为 1 或 2")):
        _p2 = os.path.join(_wd2, f"m{_sv}.json")
        with open(_p2, "w", encoding="utf-8") as f_:
            json.dump(dict(_m2, schema_version=_sv), f_, ensure_ascii=False)
        _r2v = subprocess.run([sys.executable, _vm, _p2], capture_output=True, text=True, encoding="utf-8", errors="replace")
        if _r2v.returncode == 0 or _want not in _r2v.stdout + _r2v.stderr:
            _up.append(f"V2 {_sv}：{(_r2v.stdout + _r2v.stderr).strip()[-80:]}")
    ok("V1、V2：说明是更新版本写的（版本号比本机大），明说「请把插件升级」；写错的版本号照旧说写错了", not _up, _up)



print("　更新版本写的说明（学自案图）")
try:
    make.build(dict(ex("bar-filings.json"), schema_version=2))
    _nv = "没拦"
except SpecError as e:
    _nv = str(e)
try:
    make.build(dict(ex("bar-filings.json"), schema_version="1"))
    _nv2 = "没拦"
except SpecError as e:
    _nv2 = str(e)
ok("说明是更新版本的法律图表大师写的（schema_version 2）：明说「请把插件升级」；写成文字 \"1\" 照旧说只支持 1",
   "升级" in _nv and "只支持 1" in _nv2 and "升级" not in _nv2, (_nv[:60], _nv2[:60]))


print("　浮点数据跨 Python 版本一致（0.9.8 第二轮实跑：浮点金额的汇入图在 3.11 与 3.13 上差 0.01 px）")
import builtins as _bi                              # noqa: E402


def _naive_sum(it, start=0):                        # 3.11 的内置 sum：逐个相加
    t = start
    for v in it:
        t = t + v
    return t


def _neumaier_sum(it, start=0):                     # 3.12+ 的内置 sum：浮点补偿求和
    vals = list(it)
    if all(isinstance(v, int) for v in vals) and isinstance(start, int):
        return _naive_sum(vals, start)
    t, c = float(start), 0.0
    for v in vals:
        y = t + v
        c += (t - y) + v if abs(t) >= abs(v) else (v - y) + t
        t = y
    return t + c


_rb = ex("ribbon-funds.json")
for _l in _rb["data"]["links"]:
    _l["value"] = round(_l["value"] * 1.13, 3)
_rb["title"] = "示例图"
_rb.pop("annotations", None)
_outs = []
_real = _bi.sum
try:
    for _fn in (_naive_sum, _neumaier_sum):
        _bi.sum = _fn
        _outs.append(make.build(copy.deepcopy(_rb))[0])
finally:
    _bi.sum = _real
ok("浮点金额的汇入图：按 3.11 与 3.12+ 两种内置求和各画一次，逐字节相同", _outs[0] == _outs[1])

fails = [n for n, c, _ in results if not c]
print()
print(f"{len(results) - len(fails)}/{len(results)} 项通过。" if not fails else f"{len(fails)} 项未过：{'；'.join(fails)}")
sys.exit(1 if fails else 0)
