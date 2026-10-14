#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""改坏验证：逐条把渲染器改坏，确认对应的守卫真的报错。

一条从来不会失败的守卫不是守卫。每一项都先确认「没改坏时它不报」，再确认「改坏后它报，
而且报的是该报的那一条」——报错报到别的守卫上，也算这一条没守住。
"""
import json
import os
import sys

# 中文 Windows 默认 GBK：不固定成 UTF-8，打印 −、✓ 这类 GBK 没有的字会崩（GBK 模拟环境里实测过）
for _s in (sys.stdout, sys.stderr):
    getattr(_s, "reconfigure", lambda **k: None)(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import make      # noqa: E402
import charts    # noqa: E402
import styles    # noqa: E402

EX = os.path.join(ROOT, "examples")
rows = []


def spec(name):
    with open(os.path.join(EX, name + ".json"), encoding="utf-8") as f:
        return json.load(f)


def trial(label, tag, example, patch, canvas=None, style=None):
    """patch() 打补丁并返回还原函数。"""
    _, clean = make.build(spec(example), style, None, canvas)
    clean_hit = any(p.startswith(tag) for p in clean["problems"])
    undo = patch()
    try:
        _, rep = make.build(spec(example), style, None, canvas)
        hit = any(p.startswith(tag) for p in rep["problems"])
    finally:
        undo()
    good = (not clean_hit) and hit
    rows.append((label, good))
    print(f"  {'OK  ' if good else 'FAIL'}  {tag}  {label}")


def setattr_undo(obj, name, value):
    old = getattr(obj, name)
    setattr(obj, name, value)
    return lambda: setattr(obj, name, old)


# G1 色板：普通数据换成一个白名单外的蓝
def p_g1():
    orig = styles.palette

    def bad(style, accent=None):
        p, wl = orig(style, accent)
        p = dict(p, mark="#3366FF")
        return p, wl
    return setattr_undo(make, "palette", bad)


trial("普通数据用了白名单外的颜色", "G1", "bar-filings", p_g1)


# G2 重音：把每根柱都涂成重音色，但不标 data-hero
def p_g2():
    orig = charts._mark_paint
    return setattr_undo(charts, "_mark_paint", lambda p, idx=None, hero=False: (p["accent"], None, None))


trial("没标重音的柱也用了重音色", "G2", "bar-filings", p_g2)


# G3 字号：把字号下限拆掉，半页画布上的刻度字会掉到 11px 以下
def p_g3():
    undo1 = setattr_undo(charts, "FLOOR", 4.0)
    orig = charts.Frame.__init__

    def init(self, *a, **k):
        orig(self, *a, **k)
        self.fs["tick"] = 7.0
    undo2 = setattr_undo(charts.Frame, "__init__", init)
    return lambda: (undo2(), undo1())


trial("刻度字小到 7px", "G3", "bar-filings", p_g3, canvas="slide-half")


# G4 文字：把数值标签挪到类目名所在的那一行
def p_g4():
    orig = charts._num_text

    def bad(fig, fr, x, y, v, **k):
        return orig(fig, fr, x, fr.plot_bottom - fr.fs["label"] * 0.4, v, **k)
    return setattr_undo(charts, "_num_text", bad)


trial("数值标签压在类目名上", "G4", "bar-filings", p_g4)


# G5 比例：玫瑰图半径直接用数值（不开方）
class _NoSqrt:
    def __getattr__(self, k):
        import math
        return (lambda x: x) if k == "sqrt" else getattr(math, k)


trial("玫瑰图半径不开方", "G5", "rose-causes", lambda: setattr_undo(charts, "math", _NoSqrt()))


# G5 比例：哑铃图的一端用错比例尺
def p_g5b():
    orig = charts.Fig.circle

    def bad(self, cx, cy, r, fill, stroke=None, sw=1, dash=None, **meta):
        if meta.get("role") == "to" and meta.get("id") == "A":
            cx += 30
        return orig(self, cx, cy, r, fill, stroke, sw, dash, **meta)
    return setattr_undo(charts.Fig, "circle", bad)


trial("哑铃图一个点偏离比例尺", "G5", "dumbbell-claims", p_g5b)


# G6 基线：截断纵轴（刻度不从 0 起）
trial("纵轴从 1,000 起（截断）", "G6", "bar-filings",
      lambda: setattr_undo(charts, "nice_ticks", lambda vmax, want=5, integer=False: [1000, 1500, 2000]))


# G7 遗漏：横条图悄悄丢掉最后一条
def p_g7():
    orig = charts.RENDERERS["hbar"]

    def bad(m, fig, fr):
        m2 = dict(m)
        m2["data"] = dict(m["data"], items=m["data"]["items"][:-1])
        return orig(m2, fig, fr)
    charts.RENDERERS["hbar"] = bad
    return lambda: charts.RENDERERS.__setitem__("hbar", orig)


trial("横条图丢了一条数据", "G7", "hbar-causes", p_g7)


# G8 图名：渲染时给图名添了一个字
def p_g8():
    orig = charts.Frame.title_text
    return setattr_undo(charts.Frame, "title_text", lambda self: orig(self) + "！")


trial("图名被多添了一个字", "G8", "waffle-outcomes", p_g8)

# G9 尖角：圆角半径归零（柱回到直角）
def p_g9():
    orig = charts.Frame.__init__

    def init(self, *a, **k):
        orig(self, *a, **k)
        self.corner = 0.0
    return setattr_undo(charts.Frame, "__init__", init)


trial("柱与扇区的圆角被拿掉", "G9", "bar-filings", p_g9)
trial("玫瑰扇区的圆角被拿掉", "G9", "rose-causes", p_g9)


# G9 尖角：线头改回方头
def p_g9b():
    import svgfig
    orig = svgfig.Fig.line

    def bad(self, *a, **k):
        orig(self, *a, **k)
        self.parts[-1] = self.parts[-1].replace(' stroke-linecap="round"', "")
    return setattr_undo(svgfig.Fig, "line", bad)


trial("线头改回方头", "G9", "dumbbell-claims", p_g9b)

# G9 歸藏风：被磨了圆角
def p_g9c():
    orig = charts.Frame.__init__

    def init(self, *a, **k):
        orig(self, *a, **k)
        self.corner = 5.0
    return setattr_undo(charts.Frame, "__init__", init)


trial("歸藏风被磨了圆角", "G9", "bar-filings", p_g9c, style="歸藏风")

# G5 汇入图：一条流带画宽了
def p_g5c():
    orig = charts._bezier

    def bad(p0, p1, steps=24):
        pts = orig(p0, p1, steps)
        return [(x, y + 6) if p0[0] > p1[0] else (x, y) for x, y in pts]   # 下沿整体下移 6px
    return setattr_undo(charts, "_bezier", bad)


trial("汇入图流带比数值宽", "G5", "ribbon-funds", p_g5c)


# G10 平面：玫瑰扇区被做成半透明
def p_g10():
    import svgfig
    orig = svgfig.Fig.poly

    def bad(self, pts, fill, stroke=None, sw=1, dash=None, opacity=None, **meta):
        return orig(self, pts, fill, stroke, sw, dash, opacity=0.6 if opacity is None else opacity, **meta)
    return setattr_undo(svgfig.Fig, "poly", bad)


trial("玫瑰扇区被做成半透明", "G10", "rose-causes", p_g10)

# G9 长条：汇入图两侧的竖条被磨了圆角
def p_g9d():
    import svgfig
    orig = svgfig.Fig.rect

    def bad(self, *a, square=False, **k):
        return orig(self, *a, square=False, **k)
    return setattr_undo(svgfig.Fig, "rect", bad)


trial("汇入图两侧竖条被磨圆", "G9", "ribbon-funds", p_g9d)

# G5 逐级加减：一级悬浮柱没有落在累计值上
def p_g5d():
    orig = charts.Fig.rect

    def bad(self, x, y, w, h, *a, **k):
        if k.get("role") == "step" and k.get("id") == "penalty":
            y -= 20
        return orig(self, x, y, w, h, *a, **k)
    return setattr_undo(charts.Fig, "rect", bad)


trial("逐级加减有一级没落在累计值上", "G5", "waterfall-award", p_g5d)

# G11 批注
def ann_spec():
    m = spec("bar-filings")
    m["annotations"] = [{"target": "y2019", "text": "起点"}, {"target": "y2025", "text": "终点"}]
    return m


def trial_obj(label, tag, mk, patch):
    _, clean = make.build(mk())
    clean_hit = any(p.startswith(tag) for p in clean["problems"])
    undo = patch()
    try:
        _, rep = make.build(mk())
        hit = any(p.startswith(tag) for p in rep["problems"])
    finally:
        undo()
    good = (not clean_hit) and hit
    rows.append((label, good))
    print(f"  {'OK  ' if good else 'FAIL'}  {tag}  {label}")


class _Blind:
    """只蒙住渲染器的眼睛：渲染器以为哪条路都通，守卫用的还是真的判定。"""
    def __init__(self, real):
        self.real = real

    def __getattr__(self, k):
        if k == "leader_hits":
            return lambda *a, **kw: None
        if k == "too_close":
            return lambda *a, **kw: False
        if k == "landing_candidates":
            return lambda tb, chart: [((tb[2], (tb[1] + tb[3]) / 2), "left")]   # 只许从右侧水平进入
        return getattr(self.real, k)


trial_obj("批注引线穿过别的柱", "G11", ann_spec, lambda: setattr_undo(charts, "callout", _Blind(charts.callout)))


def p_g11b():
    import svgfig
    orig = svgfig.Fig.text

    def bad(self, x, y, s, *a, **k):
        if k.get("role") == "annotation":
            s = s + "了"
        return orig(self, x, y, s, *a, **k)
    return setattr_undo(svgfig.Fig, "text", bad)


trial_obj("批注旁白被改了字", "G11", ann_spec, p_g11b)


def p_g11c():
    import svgfig
    orig = svgfig.Fig.path

    def bad(self, d, *a, **k):
        nums = d.rsplit(" ", 1)
        x, y = nums[1].split(",")
        return orig(self, f"{nums[0]} {x},{float(y) - 60}", *a, **k)
    return setattr_undo(svgfig.Fig, "path", bad)


trial_obj("批注引线没落在目标上", "G11", ann_spec, p_g11c)

# G9 方块模块
def p_g9e():
    import svgfig
    return setattr_undo(svgfig.Fig, "module", lambda self, cx, cy, side, fill, *a, **k:
                        svgfig.Fig.circle(self, cx, cy, side / 2, fill, *a, **k))


trial("百点方阵画回了圆点", "G9", "waffle-outcomes", p_g9e)


def p_g9f():
    import styles
    orig = styles.palette

    def bad(style, accent=None):
        p, wl = orig(style, accent)
        return dict(p, module=0.5), wl
    return setattr_undo(make, "palette", bad)


trial("方块圆角磨成了圆点（边长 × 0.5）", "G9", "waffle-outcomes", p_g9f)


def p_g9g():
    import styles
    orig = styles.palette

    def bad(style, accent=None):
        p, wl = orig(style, accent)
        return dict(p, module=0.22), wl
    return setattr_undo(make, "palette", bad)


trial("歸藏风的方块被磨了圆角", "G9", "waffle-outcomes", p_g9g, style="歸藏风")

# G9 流带：桑基、汇入图的流带被磨了圆角（0.9.3 作者定：流带是长条，角是直角）
def p_g9h():
    import svgfig
    orig = svgfig.Fig.poly

    def bad(self, pts, *a, square=False, **k):
        return orig(self, pts, *a, square=False, **k)
    return setattr_undo(svgfig.Fig, "poly", bad)


trial("汇入图的流带被磨了圆角", "G9", "ribbon-funds", p_g9h)
trial("桑基的流带被磨了圆角", "G9", "sankey-appeals", p_g9h)

fails = [l for l, g in rows if not g]
print(f"\n  {len(rows) - len(fails)}/{len(rows)} 条守卫确认可失败")
sys.exit(1 if fails else 0)
