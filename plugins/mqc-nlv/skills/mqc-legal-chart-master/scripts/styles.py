# -*- coding: utf-8 -*-
"""两种风格。颜色只有这两套，不另立颜色。

色值全部取自 V1 已冻结的三套规范（references/visual-style.md），不另立颜色：
  奇川风　中性灰 + 唯一深红 #991B1B
  歸藏风　克莱因蓝 #002FA7 + 灰 + 白，纸色 #FAFAF8，浅灰点阵底

V6 不出白描：数据图的去处是课件与屏幕，不进卷宗、不打印（作者定的）。

数据图比示意图多一样东西：多个类目要用不同的灰区分（「灰阶梯」）。梯子上的灰也全部取自
各自风格的白名单，所以守卫可以照旧逐色核对，不会因为 V6 多出一种颜色。

**不接受自选强调色**（0.9.3，作者定的）：0.7.0 曾开放九个强调色预设与任意色值，外部测试一跑就出现了
绿、青、紫的图，与奇川风、歸藏风都不是一回事。现在奇川风的重音只有 #991B1B，歸藏风只有 #002FA7。
理由见 ADR 0010。

**律所风格**（0.9.5，作者定的）：律所把自己的模板交给法律课件大师（V7），V7 生成一份律所风格文件；
这份文件里的主色可以替代基础风格的重音色——只此一处，经对比度校验，见 firm_palette() 与 ADR 0011。
图的其余部分（灰阶梯、几何、圆角）仍按基础风格；随手写的强调色照旧拒。
"""
import re as _re
import colorsys as _colorsys

STYLES = ("奇川风", "歸藏风")
ALIASES = {"qichuan": "奇川风", "guizang": "歸藏风", "swiss": "歸藏风", "ikb": "歸藏风"}

_Q = {
    # note（来源行、刻度、图例键）原是 #9CA3AF：白纸上对比度只有 2.5 : 1，投影与打印最先看不清的
    # 恰恰是「数据出处」那一行。0.9.8 起与 ink2 同色（4.8 : 1，过 WCAG AA），层级靠字号区分——
    # 歸藏风一直就是这样做的（note 与 ink2 都是 #737373）。
    "paper": "#FFFFFF", "ink": "#1F2933", "ink2": "#6B7280", "note": "#6B7280",
    "grid": "#ECEEF1", "axis": "#C3C9D2",
    "mark": "#9CA3AF",                       # 单系列的普通数据
    "ladder": ["#4B5563", "#9CA3AF", "#D1D5DB"],   # 多类目：由深到浅，按重要性分配
    "flow": "#E9ECEF", "node": "#374151",
    "rail": "#4B5563",      # 细长条（桑基 / 汇入图两侧的竖条、中位数竖线）：深灰，不用近黑
    "accent": "#991B1B", "on_accent": "#FFFFFF",
    "outline": None, "dash_ladder": [None, None, None],
    "title_weight": 700, "title_font": "serif", "num_track": 0.0,
    "pattern": None,
    "corner": 5.0,      # 贝塞尔小圆角：整页幻灯片上 5px，随画布缩放（见 ADR 0004）
    "module": 0.22,     # 方块模块（点阵的一格）的圆角 = 边长 × 0.22：比大形状的角圆一些，看上去仍是正方形
}
_G = {
    "paper": "#FAFAF8", "ink": "#333333", "ink2": "#737373", "note": "#737373",
    "grid": "#E0E0E0", "axis": "#BDBDBD",
    "mark": "#BDBDBD",
    "ladder": ["#737373", "#BDBDBD", "#E0E0E0"],
    "flow": "#E0E0E0", "node": "#333333",
    "rail": "#737373",
    "accent": "#002FA7", "on_accent": "#FFFFFF",
    "outline": None, "dash_ladder": [None, None, None],
    "title_weight": 300, "title_font": "sans", "num_track": 0.06,   # 歸藏风：越大越轻；拉丁与数字加字距
    "pattern": "#D4D4D2",
    "corner": 0.0,      # 歸藏风是瑞士风格：利落的直角，不磨圆（作者定的）
    "module": 0.0,      # 方块模块也是直角
}
_BASE = {"奇川风": _Q, "歸藏风": _G}

WHITELIST = {
    "奇川风": {"#FFFFFF", "#F3F4F6", "#E9ECEF", "#D6DAE0", "#D1D5DB", "#ECEEF1", "#C3C9D2",
            "#9CA3AF", "#6B7280", "#4B5563", "#374151", "#1F2933", "#991B1B"},
    "歸藏风": {"#FAFAF8", "#333333", "#737373", "#BDBDBD", "#D4D4D2", "#E0E0E0", "#002FA7", "#FFFFFF"},
}


def norm_style(name):
    if not name:
        return "奇川风"
    return ALIASES.get(str(name).lower(), name)


def _lum(hexcol):
    c = hexcol.lstrip("#")
    vals = []
    for i in (0, 2, 4):
        v = int(c[i:i + 2], 16) / 255
        vals.append(v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4)
    return 0.2126 * vals[0] + 0.7152 * vals[1] + 0.0722 * vals[2]


def contrast(a, b):
    la, lb = _lum(a), _lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


MIN_CONTRAST = 4.5   # 强调色上要压白字，也要在白纸上当文字用：两头都按正文标准


class FirmStyleError(ValueError):
    pass


def firm_palette(firm):
    """律所风格 → (palette, whitelist)。firm = {"name", "base": 奇川风 / 歸藏风, "accent": "#RRGGBB", "title_font"?}。
    换重音色；主色要在纸色上当字看得清、上面压白字也看得清，且不能是灰（会和灰阶梯混）。
    title_font（可选）：serif / sans，图标题与课件标题同一种字（律所风格用粗黑体时给 sans，字重随之用 700）。"""
    if not isinstance(firm, dict):
        raise FirmStyleError("律所风格要是一个对象")
    name = str(firm.get("name") or "").strip()
    base = norm_style(firm.get("base") or "奇川风")
    acc = str(firm.get("accent") or "").strip().upper()
    if not name:
        raise FirmStyleError("律所风格要有名字")
    if base not in _BASE:
        raise FirmStyleError(f"律所风格的基础风格要是 {' / '.join(STYLES)}，收到 {base!r}")
    if not _re.fullmatch(r"#[0-9A-F]{6}", acc):
        raise FirmStyleError(f"律所主色要写成 #RRGGBB，收到 {firm.get('accent')!r}")
    b = _BASE[base]
    r, g, bl = (int(acc[i:i + 2], 16) / 255 for i in (1, 3, 5))
    _, light, sat = _colorsys.rgb_to_hls(r, g, bl)
    if sat < 0.2:
        raise FirmStyleError(f"律所主色 {acc} 太接近灰色：图里的灰阶梯会和重音分不开。请用律所的品牌色")
    for what, fg, bg in (("当文字放在纸上", acc, b["paper"]), ("上面压白字", b["on_accent"], acc)):
        c = contrast(fg, bg)
        if c < MIN_CONTRAST:
            raise FirmStyleError(f"律所主色 {acc} {what}，对比度只有 {c:.1f}（至少 {MIN_CONTRAST}）：投影时看不清。"
                                 f"请用更深一档的品牌色")
    tf = firm.get("title_font")
    if tf not in (None, "serif", "sans"):
        raise FirmStyleError(f"律所风格的图标题字体只有 serif / sans 两种，收到 {tf!r}")
    p = dict(b)
    p["style"] = base
    p["accent"] = acc
    p["firm"] = name
    if tf:
        p["title_font"] = tf
        p["title_weight"] = 700
    wl = (set(WHITELIST[base]) - {b["accent"]}) | {acc}
    return p, wl


def palette(style, accent=None):
    """返回 (palette, whitelist)。只有两种风格的原色；给了强调色就拒（作者定的，见 ADR 0010）。"""
    style = norm_style(style)
    if style not in _BASE:
        extra = "。V6 不出白描：数据图用于课件与屏幕，不打印" if style == "白描" else ""
        raise ValueError(f"未知风格 {style!r}；可选：{'、'.join(STYLES)}{extra}")
    if accent:
        raise ValueError(f"V6 不换强调色（收到 {accent!r}）：奇川风的重音只用深红 #991B1B，歸藏风只用克莱因蓝 "
                         f"#002FA7，图上不出现第三种颜色。要换气质，请换风格（--style 奇川风 / 歸藏风）")
    p = dict(_BASE[style])
    p["style"] = style
    return p, set(WHITELIST[style])
