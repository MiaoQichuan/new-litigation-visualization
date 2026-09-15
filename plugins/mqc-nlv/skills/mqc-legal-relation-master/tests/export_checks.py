# -*- coding: utf-8 -*-
"""导出物与交互的回归自检，含改坏验证。

    python tests/export_checks.py

一、四份样图 × 所属风格：pptx / vsdx / drawio 导出物判据全过
二、改坏验证：故意弄坏，判据必须抓住
    · 不规整就交给 V1（圆角成斜线、虚线成实线）→ pptx、vsdx 必须撤下
    · drawio 文字多转义一层 → E6 必须报
    · 非奇川风的 SVG 带深红 → 必须拒绝导出
三、交互边界：多选风格、非奇川风给重点、重点超两处、编号越界 → 必须报错
"""
import os, sys, tempfile, shutil
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import exports, export_guard, ask

FX = os.path.join(HERE, "fixtures")
tmp = tempfile.mkdtemp()
fails = []


def expect(cond, name):
    print(("  OK    " if cond else "  FAIL  ") + name)
    if not cond:
        fails.append(name)


print("一、导出物判据")
for f, style in (("special-chars.svg", "奇川风"), ("dense15-qichuan.svg", "奇川风"),
                 ("dense15-baimiao.svg", "白描"), ("dense15-guizang.svg", "歸藏风")):
    out, g = exports.export_all(os.path.join(FX, f), os.path.join(tmp, f[:-4]),
                                style=style, return_guard=True)
    bad = {k: [n for n, ok, _ in r if not ok] for k, (o, r) in g.items() if not o}
    expect(not bad and all(os.path.exists(out[k]) for k in ("png", "pptx", "vsdx", "drawio")),
           f"{f} {style}" + (f" 未过 {bad}" if bad else ""))

print("二、改坏验证")
svg = os.path.join(FX, "dense15-qichuan.svg")
orig = exports._normalized
exports._normalized = lambda p: p
out = exports.export_all(svg, os.path.join(tmp, "broken"))
exports._normalized = orig
expect(str(out["pptx"]).startswith("未交付") and str(out["vsdx"]).startswith("未交付")
       and not os.path.exists(os.path.join(tmp, "broken.pptx")), "不规整导出 → pptx、vsdx 一起撤下")
spc = os.path.join(FX, "special-chars.svg")
exports.export_all(spc, os.path.join(tmp, "spc"))
d = open(os.path.join(tmp, "spc.drawio"), encoding="utf-8").read().replace("&amp;amp;", "&amp;amp;amp;")
open(os.path.join(tmp, "spc-bad.drawio"), "w", encoding="utf-8").write(d)
r = export_guard.check(spc, {"drawio": os.path.join(tmp, "spc-bad.drawio")})["drawio"][1]
expect(any(n == "E6" and not ok for n, ok, _ in r), "drawio 多转义一层 → E6 报出")
try:
    exports.export_all(svg, os.path.join(tmp, "x"), style="白描")
    expect(False, "非奇川风带深红 → 拒绝导出")
except ValueError:
    expect(True, "非奇川风带深红 → 拒绝导出")

print("三、交互边界")
import json
rel = json.load(open(os.path.join(FX, "relations-demo.json"), encoding="utf-8"))
N, E = rel["nodes"], rel["edges"]
for kw, name in ((dict(style="奇川风,白描"), "多选风格"), (dict(style="1", mark="3"), "白描给重点"),
                 (dict(style="2", mark="1,2,3"), "重点三处"), (dict(style="2", mark="99"), "编号越界")):
    try:
        ask.resolve(N, E, **kw)
        expect(False, name + " → 报错")
    except ValueError:
        expect(True, name + " → 报错")
c = ask.resolve(N, E, style="3")
expect(c["style"] == "歸藏风" and not ask.needs_round2(c), "歸藏风 → 跳过第二轮")
c = ask.resolve(N, E, style="2")
expect(c["emphasis"] == dict(nodes=[], edges=[]) and "未指定" in c["label"], "奇川风不答第二轮 → 一处不标")

shutil.rmtree(tmp, ignore_errors=True)
print("全部通过" if not fails else f"{len(fails)} 项未过")
sys.exit(1 if fails else 0)
