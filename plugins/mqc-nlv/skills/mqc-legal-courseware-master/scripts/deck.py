# -*- coding: utf-8 -*-
"""课件说明（deck.json）：校验，把一页的磁吸模块拼成一张 1280 × 720 的 SVG。

一份课件 = 若干页；一页 = 12 栏 × 6 行的网格上若干模块（几何见 grid.py）。
每个模块是一张有自己样子的卡片：
  title     标题（无底）     level: page / cover / section；kicker（章节编号）、sub（副题）
  text      正文卡           heading（可选）、text
  bullets   要点卡           heading（可选）、items
  stat      大数字卡         value、label、note；数字是手填的，交付清单会提醒核对
  step      编号卡           heading、text；编号按阅读顺序自动排 01、02、03
  quote     金句卡           text、source（必填）
  chart     V6 图表卡        spec 或 file（assets/x.json）；按卡片内框重画并重过 V6 守卫
  figure    V1–V5 图卡       file（assets/x.svg）、from；等比缩放，字小于 11px 不收
  note      注释（无底）     text
外观 tone：card 卡片 / accent 重音卡 / outline 描边 / bare 无底；不写就用该模块的默认外观。
相邻的同类卡片自动连成一组（join: false 可以拆开）。

**预览与导出走同一个拼页函数**，编辑器里看到的就是 PPTX 里的样子。
规矩（与 V6 同源）：颜色、字体、圆角只从风格里取；整套课件一种风格；字放不下就说放不下，不缩到看不清。
"""
import copy
import html
import json
import math
import os
import re

import paths  # noqa: F401
from kernel import wrap, text_w, TITLE_FONT, BODY_FONT
from styles import palette, WHITELIST
import svgimport
import adapt as A
import grid as G
import brand as B
import prov as P_

W, H = G.W, G.H
SCHEMA = "mqc-nlv/deck@2"
OLD_SCHEMA = "mqc-nlv/deck@1"
STYLES = ("奇川风", "歸藏风")
CUSTOM = "自定义"        # 用户上传模板 / 截图 / 选主色得到的风格，一律叫「自定义」（作者定的：不为哪一家律所单立风格名）
MIN_BODY = 16.0          # 正文最小 16px：投影到教室后排也看得清
BULLET_MAX = 24.0        # 要点字号上限：要点少时放大到这里为止（再大就压过图表标题、和同页别的卡片不一样大）
TYPES = G.TYPES
TEMPLATES = G.TEMPLATES


class DeckError(ValueError):
    pass


# ------------------------------------------------------------- 读与校验
def new_deck(title="未命名图表页", style="奇川风"):
    """新课件：一张空页。编辑器在空页上请律师先选「这一页要讲什么」（法律场景），再排好；封面在「更多」里。"""
    return {"schema": SCHEMA, "title": title, "style": style, "slides": [{"id": "s1", "modules": []}]}


def normalize(d):
    """旧格式（deck@1：版式 + 格子）就地升级成网格模块。返回同一个对象。"""
    if isinstance(d, dict) and d.get("schema") == OLD_SCHEMA:
        d["slides"] = [G.upgrade_slide(s) if "layout" in s else s for s in d.get("slides") or []]
        d["schema"] = SCHEMA
    return d


def _json_error(what, e):
    """把 Python 的 JSON / 编码报错换成律师看得懂的话（第几行第几列），不把英文异常原样甩出去。"""
    if isinstance(e, json.JSONDecodeError):
        return DeckError(f"{what}不是合法的 JSON：第 {e.lineno} 行第 {e.colno} 列附近（常见是少了逗号、引号或括号）")
    if isinstance(e, UnicodeDecodeError):
        return DeckError(f"{what}不是 UTF-8 文本（可能是别的格式改了扩展名，或文件已损坏）")
    return DeckError(f"{what}读不了：{e}")


def load(path):
    if not os.path.exists(path):
        raise DeckError(f"找不到 {path}：这个文件夹里还没有课件（新建用 --new）")
    try:
        with open(path, encoding="utf-8-sig") as f:
            d = json.load(f)
    except (ValueError, UnicodeDecodeError) as e:
        raise _json_error("deck.json ", e)
    normalize(d)
    base = os.path.dirname(os.path.abspath(path))
    adopt_custom(d, base)
    validate(d, base)
    return d


def adopt_custom(d, base_dir):
    """旧课件写的是自定义风格的旧名字（例如当初按律所起的名）：认作「自定义」。
    自定义只有一个位置，换过模板也还是它。返回同一个对象。"""
    if isinstance(d, dict) and d.get("style") not in STYLES and d.get("style") != CUSTOM:
        st, _ = B.firm_style(base_dir)
        if st:
            d["style"] = CUSTOM
    return d


def styles_for(base_dir):
    """这套课件能用的风格：两种内置风格 + 自定义（做过才有）。"""
    st, _ = B.firm_style(base_dir) if base_dir else (None, None)
    return list(STYLES) + ([CUSTOM] if st else [])


def firm_of(deck, base_dir):
    """课件用的是律所风格就返回它，否则 None。"""
    if deck.get("style") in STYLES or not base_dir:
        return None
    st, _ = B.firm_style(base_dir)
    return st if st and deck.get("style") in (CUSTOM, st["name"]) else None


def _newer(got, mine):
    """got 是同一种格式、但代际号比 mine 大（例如 mqc-nlv/deck@3 对 mqc-nlv/deck@2）→ 返回 got，否则 None。"""
    import re as _re
    g = _re.fullmatch(r"(.+)@(\d+)", str(got or ""))
    m = _re.fullmatch(r"(.+)@(\d+)", mine)
    return got if g and m and g.group(1) == m.group(1) and int(g.group(2)) > int(m.group(2)) else None


def validate(d, base_dir=None):
    """结构层的校验：说不清的就拒，不猜。返回 None，有错抛 DeckError。
    base_dir：课件目录（用来认律所风格；不给就只认两种内置风格）。"""
    errs = []
    if not isinstance(d, dict) or d.get("schema") != SCHEMA:
        newer = _newer(d.get("schema") if isinstance(d, dict) else None, SCHEMA)
        if newer:
            raise DeckError(f"这份课件是更新版本的法律课件大师写的（{newer}），本机的版本只认到 {SCHEMA}："
                            "请把插件升级到最新版再打开（课件本身没有坏）")
        raise DeckError(f"课件说明的 schema 要是 {SCHEMA}（旧的 {OLD_SCHEMA} 会自动升级）")
    if d.get("style") not in STYLES:
        st, err = B.firm_style(base_dir) if base_dir else (None, None)
        if err:
            errs.append(err)
        elif not st or d.get("style") not in (CUSTOM, st["name"]):
            if d.get("style") == CUSTOM:
                errs.append("还没有自定义风格：点「自定义」，上传模板或截图，或选一个主色")
            else:
                have = list(STYLES) + ([CUSTOM] if st else [])
                errs.append(f"style 要是 {' / '.join(have)}（整套课件一种风格）")
    errs += G.check_frame(d.get("frame"))
    if not isinstance(d.get("slides"), list) or not d["slides"]:
        errs.append("slides 要是页的列表，至少一页" if not isinstance(d.get("slides"), list) else "slides 至少要有一页")
    seen = set()
    for i, s in enumerate(d["slides"] if isinstance(d.get("slides"), list) else []):
        where = f"第 {i + 1} 页"
        if not isinstance(s, dict):
            errs.append(f"{where}要是一个对象")
            continue
        if s.get("id") in seen or not s.get("id"):
            errs.append(f"{where}的 id 缺失或重复")
        seen.add(s.get("id"))
        mods = s.get("modules")
        if not isinstance(mods, list):
            errs.append(f"{where}要有 modules（模块列表，可以为空）")
            continue
        errs += [f"{where}：{e}" for e in G.check_slide(mods)]
        for m in mods:
            if not isinstance(m, dict):
                continue
            if "pins" in m and (not isinstance(m["pins"], list) or not all(isinstance(k, str) for k in m["pins"])
                                or len(m["pins"]) > MAX_PINS or len(set(m["pins"])) != len(m["pins"])):
                errs.append(f"{where}：「{m.get('id')}」的读图编号（pins）要是不重复的元素键列表，最多 {MAX_PINS} 个")
            if "part" in m and (m.get("type") != "figure" or not isinstance(m["part"], int) or isinstance(m["part"], bool)
                                or m["part"] < 0):
                errs.append(f"{where}：「{m.get('id')}」的要件序号（part）要是从 0 起的整数")
            if "data" in m and (m.get("type") != "figure" or not isinstance(m["data"], str)):
                errs.append(f"{where}：「{m.get('id')}」的数据文件（data）只给图卡")
            if "focus" in m and (m.get("type") not in ("chart", "figure") or not isinstance(m["focus"], list) or not m["focus"]
                                 or not all(isinstance(k, str) for k in m["focus"])):
                errs.append(f"{where}：「{m.get('id')}」的聚焦（focus）要是图上的元素键列表")
            if "crop" in m and (m.get("type") != "figure" or not isinstance(m["crop"], list) or not m["crop"]
                                or not all(isinstance(k, str) for k in m["crop"])):
                errs.append(f"{where}：「{m.get('id')}」的切片（crop）要是图卡上的元素键列表")
            if ("sample" in m or "recipe" in m) and (m.get("type") != "chart" or not isinstance(m.get("recipe", ""), str)):
                errs.append(f"{where}：「{m.get('id')}」的图表库记号（sample / recipe）只给图表卡")
            if "pins" in m and m.get("type") not in ("chart", "figure"):
                errs.append(f"{where}：读图编号只放在图上（图表卡、图卡）")
        if not isinstance(s.get("parked", []), list):
            errs.append(f"{where}的 parked（暂存区）要是列表")
    if errs:
        raise DeckError("；\n".join(errs))


def resolve(mod, base_dir):
    """把 file 引用读进来（chart 的 V6 说明、figure 的 SVG）。"""
    m = dict(mod)
    if m.get("type") == "chart" and "spec" not in m:
        if not m.get("file"):
            raise DeckError("图表卡还是空的：从左边「图表库」挑一张，或在「诉讼图 → 已有的图」点一张 V6 图表")
        p = paths.inside(base_dir, m["file"])
        if p is None:
            raise DeckError(f"图表说明 {m['file']!r} 不在这个课件的文件夹里：素材请放进 assets/（外面的文件不读）")
        if not os.path.exists(p):
            raise DeckError(f"找不到图表说明 {m['file']!r}")
        try:
            with open(p, encoding="utf-8-sig") as f:
                m["spec"] = json.load(f)
        except (ValueError, UnicodeDecodeError) as e:
            raise _json_error(f"图表说明 {m['file']!r} ", e)
    if m.get("type") == "figure" and not m.get("file") and A.kind_of(m):
        return m                                         # 走幻灯片尺寸兼容层：拼页时按图卡尺寸现出图
    if m.get("type") == "figure":
        p = paths.inside(base_dir, m.get("file") or "")
        if m.get("file") and p is None:
            raise DeckError(f"图 {m['file']!r} 不在这个课件的文件夹里：素材请放进 assets/（外面的文件不读）")
        if not m.get("file") or not os.path.exists(p):
            raise DeckError(f"找不到图片文件 {m.get('file')!r}" if m.get("file")
                            else "图卡还是空的：从左边「诉讼图 → 已有的图」点一张 V1–V5 的图")
        try:
            with open(p, encoding="utf-8-sig") as f:
                m["svg"] = f.read()
        except UnicodeDecodeError:
            raise DeckError(f"图 {m['file']!r} 不是 SVG 文本（可能是 PNG / JPG 改了扩展名，或文件已损坏）：请放 V1–V5 导出的 .svg")
    return m


# ------------------------------------------------------------- 风格
def _theme(style, firm=None, dark=False):
    """风格 → 拼页用的主题。firm：律所风格（颜色、粗黑体标题、圆角来自律所风格文件）；dark：深底页（封面、章节页）。"""
    if firm:
        return _firm_theme(firm, dark)
    p, _ = palette(style)
    q = style == "奇川风"
    return {
        "p": p, "q": q, "title_color": p["ink"], "base": style,
        "title_family": TITLE_FONT if q else BODY_FONT,
        "title_weight": 700 if q else 300,
        "head_weight": 700 if q else 400,
        "R": 12.0 if q else 0.0, "r": 4.0 if q else 0.0,           # 卡片外角 / 连组内角
        "tones": {
            "card":    {"fill": "#F3F4F6" if q else "#FFFFFF", "stroke": None, "ink": p["ink"], "ink2": p["ink2"],
                        "mark": p["accent"]},
            "outline": {"fill": "#FFFFFF", "stroke": "#D6DAE0" if q else "#E0E0E0", "ink": p["ink"], "ink2": p["ink2"],
                        "mark": p["accent"]},
            "accent":  {"fill": p["accent"], "stroke": None, "ink": "#FFFFFF", "ink2": "#FFFFFF", "mark": "#FFFFFF"},
            "bare":    {"fill": None, "stroke": None, "ink": p["ink"], "ink2": p["ink2"], "mark": p["accent"]},
        },
        "sizes": {"page": 38 if q else 44, "cover": 60 if q else 68, "section": 52 if q else 58,
                  "kicker": 20, "sub": 28, "head": 22, "body": 20, "quote": 28, "note": 14},
    }


def _firm_theme(firm, dark):
    c = firm["colors"]
    base = firm.get("base") or "奇川风"
    p, _ = palette(base)
    p = dict(p, paper=c["paper"], ink=c["ink"], ink2=c["ink2"], note=c["note"], accent=c["accent"], pattern=None)
    title = c["title"]
    tones = {
        "card":    {"fill": c["card"], "stroke": None, "ink": c["ink"], "ink2": c["ink2"], "mark": c["accent"]},
        "outline": {"fill": c["paper"], "stroke": c["outline"], "ink": c["ink"], "ink2": c["ink2"], "mark": c["accent"]},
        "accent":  {"fill": c["accent"], "stroke": None, "ink": c["cover_ink"], "ink2": c["cover_ink"], "mark": c["cover_ink"]},
        "bare":    {"fill": None, "stroke": None, "ink": c["ink"], "ink2": c["ink2"], "mark": c["accent"]},
    }
    if dark:                                   # 封面、章节页：律所主色满版，白字
        p = dict(p, paper=c["cover_bg"], ink=c["cover_ink"], ink2=c["cover_ink2"], note=c["cover_ink2"],
                 accent=c["cover_ink2"])
        title = c["cover_ink"]
        dt = {"fill": c["cover_card"], "stroke": None, "ink": c["cover_ink"], "ink2": c["cover_ink2"], "mark": c["cover_ink2"]}
        tones = {"card": dt, "accent": dt, "outline": dict(dt, fill=None, stroke=c["cover_ink2"]),
                 "bare": {"fill": None, "stroke": None, "ink": c["cover_ink"], "ink2": c["cover_ink2"], "mark": c["cover_ink2"]}}
    rad = firm.get("radius") or {}
    return {
        "p": p, "q": base == "奇川风", "title_color": title, "base": base, "firm": firm, "dark": dark,
        "title_family": BODY_FONT, "title_weight": firm.get("fonts", {}).get("title_weight", 700),     # 粗黑体（作者定的）
        "head_weight": 700,
        "R": float(rad.get("outer", 10.0)), "r": float(rad.get("inner", 4.0)),
        "tones": tones,
        "sizes": {"page": 38, "cover": 60, "section": 52, "kicker": 20, "sub": 28, "head": 22, "body": 20, "quote": 28,
                  "note": 14},
    }


PAD = {"chart": 16, "figure": 16}
PAD_DEFAULT = 24


def _esc(s):
    return html.escape(str(s), quote=False)


# ------------------------------------------------------------- 字
def _text_lines(s, fs, w):
    out = []
    for para in str(s).split("\n"):
        out += wrap(para, fs, w, keep_alnum=True) if para.strip() else [""]
    return out


def _fit_text(s, fs, w, h, lh=1.35, min_fs=MIN_BODY):
    """找能放下的最大字号（不小于 min_fs）。返回 (字号, 行) 或 (None, 说明)。"""
    f = fs
    while f >= min_fs - 1e-9:
        lines = _text_lines(s, f, w)
        if len(lines) * f * lh <= h + 1e-6:
            return f, lines
        f -= 1
    return None, (f"字太多，放不下（最小 {min_fs:.0f}px 也要 {len(_text_lines(s, min_fs, w))} 行）。"
                  "请删短、把卡片拉大，或拆成两页")


# 宋体标题（0.9.0，缪律师定的）：用方正小标宋本来的字重，不再加粗、不再描边。
# 原来标题是 font-weight 700 + 0.3 同色描边：方正小标宋本身就是重的标题字、没有粗体字面，浏览器和 PowerPoint
# 都会「伪加粗」，再叠一道描边，比小标宋原样粗一大坨。没装小标宋的电脑，按顺序落到本身就偏重的华文中宋、
# 思源宋体 SemiBold，不至于发细。标题打 data-title="1"：导出 PPT 时据此选标题字（见 export.py）。
TITLE_STACK = ("'方正小标宋简体','FZXiaoBiaoSong-B05S','华文中宋','STZhongsong','思源宋体 SemiBold',"
               "'Source Han Serif SC SemiBold','Noto Serif CJK SC SemiBold','思源宋体','Source Han Serif SC',"
               "'Noto Serif CJK SC',serif")
_TEXT_TAG = re.compile(r"<text\b[^>]*>")
_HEAVY = ("600", "700", "800", "900", "bold", "bolder")


def _is_song(family):
    low = family.lower()
    return "sans" not in low and ("serif" in low or "宋" in family)


def unbold_titles(svg):
    """别的模块（V1–V6）的图里，宋体加粗（+ 描边）的字一律改成标题字的本来字重。只动宋体，黑体的粗字不动。"""
    def fix(m):
        tag = m.group(0)
        fam = re.search(r'font-family="([^"]*)"', tag)
        w = re.search(r'font-weight="([^"]*)"', tag)
        if not fam or not w or w.group(1) not in _HEAVY or not _is_song(fam.group(1)):
            return tag
        tag = re.sub(r'\s+font-weight="[^"]*"', "", tag)
        tag = re.sub(r'\s+stroke="[^"]*"', "", tag)
        tag = re.sub(r'\s+stroke-width="[^"]*"', "", tag)
        tag = re.sub(r'font-family="[^"]*"', f'font-family="{TITLE_STACK}"', tag, count=1)
        return tag if "data-title=" in tag else tag[:-1] + ' data-title="1">'
    return _TEXT_TAG.sub(fix, svg)


def _text_svg(x, y, lines, fs, fill, family, weight=400, lh=1.35, mod="", anchor="start"):
    out = []
    yy = y + fs * 0.88
    title = family == TITLE_FONT and weight >= 600       # 只改原来加粗的宋体标题；本来就是常规字重的（金句、要旨正文）原样
    if title:
        family, weight = TITLE_STACK, 400
    for ln in lines:
        if ln:
            out.append(f'<text x="{x:.2f}" y="{yy:.2f}" font-size="{fs:.2f}" fill="{fill}" font-family="{family}"'
                       + (f' font-weight="{weight}"' if weight != 400 else "")
                       + (f' text-anchor="{anchor}"' if anchor != "start" else "")
                       + (' data-title="1"' if title else "")
                       + f' data-mod="{mod}">{_esc(ln)}</text>')
        yy += fs * lh
    return out


def _mark(x, y, side, fill, rounded):
    """要点前的方块记号：与 V6 点阵同一种方块模块（奇川风圆角 = 边长 × 0.22，歸藏风直角）。"""
    r = side * 0.22 if rounded else 0
    return (f'<rect x="{x:.2f}" y="{y:.2f}" width="{side:.2f}" height="{side:.2f}"'
            + (f' rx="{r:.2f}"' if r else "") + f' fill="{fill}" data-mod="mark"/>')


# ------------------------------------------------------------- 卡片
def _card_shape(x, y, w, h, radii, fill, stroke, tag):
    """四角一样就是原生圆角矩形；连组后四角不同，就画成折线（导出后是可编辑的自由形状）。"""
    st = f' stroke="{stroke}" stroke-width="1"' if stroke else ""
    fl = fill or "none"
    if len(set(radii)) == 1:
        r = radii[0]
        return (f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}"' + (f' rx="{r:.2f}"' if r else "")
                + f' fill="{fl}"{st} data-mod="{tag}.card"/>')
    pts = []
    tl, tr, br, bl = radii
    for (cx, cy, r, a0) in ((x + tl, y + tl, tl, 180), (x + w - tr, y + tr, tr, 270),
                            (x + w - br, y + h - br, br, 0), (x + bl, y + h - bl, bl, 90)):
        n = 6 if r > 0 else 0
        for k in range(n + 1):
            a = math.radians(a0 + 90 * k / max(n, 1))
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    d = "M" + " L".join(f"{a:.2f},{b:.2f}" for a, b in pts) + " Z"      # 闭合折线：V1 导出器只认 path，不认 polygon
    return f'<path d="{d}" fill="{fl}"{st} data-mod="{tag}.card"/>'


def _heading(mod, th, tone, x, y, w, tag, fs=None):
    """卡片里的小标题，返回 (元素, 用掉的高度)。"""
    hd = str(mod.get("heading") or "").strip()
    if not hd:
        return [], 0
    fs = fs or th["sizes"]["head"]
    lines = _text_lines(hd, fs, w)[:2]
    return (_text_svg(x, y, lines, fs, tone["ink"], th["title_family"], th["head_weight"], 1.3, tag + ".head"),
            len(lines) * fs * 1.3 + 12)


def _badge(cx, cy, r, n, fill, ink, tag):
    """读图编号：实心小圆 + 白字数字。图上的编号与要点卡前的编号是同一个样子。"""
    return [f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{r:.2f}" fill="{fill}" data-mod="{tag}"/>',
            f'<text x="{cx:.2f}" y="{cy + r * 0.42:.2f}" font-size="{r * 1.18:.2f}" font-weight="700" fill="{ink}" '
            f'font-family="{BODY_FONT}" text-anchor="middle" data-mod="{tag}">{n}</text>']


def _bullets(items, th, tone, x, y, w, h, tag, info, numbered=False):
    fs0 = 24 if h >= 300 and w >= 300 else th["sizes"]["body"]
    f = fs0
    while True:
        side = f * 0.42
        indent = f * (1.7 if numbered else 1.2)
        blocks = [_text_lines(it, f, w - indent) for it in items]
        need = sum(len(b) for b in blocks) * f * 1.4 + (len(items) - 1) * f * 0.5
        if need <= h or f <= MIN_BODY:
            break
        f -= 1
    if need > h + 1e-6:
        info["problems"].append(f"要点放不下：{len(items)} 条在这张卡片里最小 {MIN_BODY:.0f}px 也要 {need:.0f}px 高"
                                f"（卡片内只有 {h:.0f}px）。请删短、把卡片拉大，或拆成两页")
        return []
    if f < fs0:
        info["notes"].append(f"要点多，字号由 {fs0}px 收到 {f:.0f}px")
    else:                                                   # 要点少、卡片大：字适当放大，别全挤在左上角（最多 24px、占到卡片约七成）
        while f < BULLET_MAX:
            g = f + 1
            ind = g * (1.7 if numbered else 1.2)
            bl = [_text_lines(it, g, w - ind) for it in items]
            nd = sum(len(b_) for b_ in bl) * g * 1.4 + (len(items) - 1) * g * 0.5
            if nd > h * 0.72 or sum(len(b_) for b_ in bl) > sum(len(b_) for b_ in blocks):
                break                                       # 再大就要多折一行，或超过七成：停
            f, blocks, need, indent, side = g, bl, nd, ind, g * 0.42
    gap = f * 0.5
    if len(items) > 1 and need < h * 0.6:                   # 还很空：条与条之间放宽（最多一行高），读起来更舒展
        gap = min(f * 1.1, f * 0.5 + (h * 0.6 - need) / (len(items) - 1))
    if len(items) > 6:
        info["warnings"].append(f"一张卡片 {len(items)} 条要点：讲台上超过 6 条就记不住，考虑拆页")
    out = []
    yy = y
    for k, (it, lines) in enumerate(zip(items, blocks), 1):
        if numbered:                                        # 与图上的读图编号同号：讲「先看①」时一一对得上
            out += _badge(x + f * 0.62, yy + f * 0.68, f * 0.62, k, tone["ink"], tone["fill"] or th["p"]["paper"], tag)
            info.setdefault("items", []).append({"n": k, "box": [round(x, 1), round(yy, 1), round(w, 1),
                                                                round(len(lines) * f * 1.4, 1)]})
        else:
            out.append(_mark(x, yy + f * 0.46, side, tone["mark"], th["q"]))
        out += _text_svg(x + indent, yy, lines, f, tone["ink"], BODY_FONT, 400, 1.4, tag)
        yy += len(lines) * f * 1.4 + gap
    return out


def _stat_check(stat, mods, base_dir):
    """大数字能不能由图表推出（V6 的数字核对：类型、数值、主语都要对得上）。
    from 写同页图表卡的 id 或 assets/ 里的图表说明；不写就试同页的图表卡。
    返回 (problems, notes, warnings)。"""
    import spec as V6spec
    text = f"{stat.get('label') or ''} {stat.get('value') or ''}".strip()
    src = stat.get("from")
    cands = []
    if src:
        hit = next((m for m in mods if m["id"] == src and m["type"] == "chart"), None)
        if hit:
            cands.append((f"图表卡「{src}」", hit))
        elif str(src).endswith(".json"):
            cands.append((src, {"type": "chart", "file": src}))
        else:
            return [f"from 写的「{src}」既不是本页的图表卡，也不是 assets/ 里的图表说明"], [], []
    else:
        cands = [(f"图表卡「{m['id']}」", m) for m in mods if m["type"] == "chart"]
    tried = []
    for name, m in cands:
        try:
            spec = resolve(m, base_dir)["spec"]
            mm = copy.deepcopy(spec)
            V6spec.validate(mm)
            errs, warns = V6spec.check_numbers(text, mm, mm.get("_derived") or V6spec.derive(mm), "大数字")
        except Exception as e:                       # noqa: BLE001 —— 图表本身出不来，由图表卡自己报
            tried.append(f"{name}：{str(e).splitlines()[0][:60]}")
            continue
        if not errs:
            return [], [f"数字已由{name}的数据核过（V6 数字核对）"], [w for w in warns]
        tried.append(f"{name}：{errs[0]}")
    if src:
        return [f"大数字「{text}」与{tried[0] if tried else src}"], [], []
    return [], [], [f"大数字「{stat.get('value')}」是手填的，同页没有能推出它的图表：请与原始数据核对，"
                    f"或在 from 里写出处图表"]


CN_NUM = "一二三四五六七八九十"


def _ordinal(mods, mtype):
    order = sorted((m for m in mods if m["type"] == mtype), key=lambda m: (m["y"], m["x"]))
    return {m["id"]: i + 1 for i, m in enumerate(order)}


def _kicker(x, y, label, th, tone, tag, mark=False):
    """卡片顶上的小标签（重音色）。返回 (元素, 用掉的高度)。"""
    fs = 16
    out = []
    dx = 0
    if mark:
        out.append(_mark(x, y + fs * 0.18, fs * 0.62, tone["mark"], th["q"]))
        dx = fs * 0.95
    out += _text_svg(x + dx, y, [label], fs, tone["mark"], BODY_FONT, 700 if th["q"] else 400, 1.2, tag + ".kick")
    return out, fs * 1.2 + 10


def _fit_block(text, fs0, w, h, info, what, lh=1.55, min_fs=MIN_BODY):
    f, lines = _fit_text(text, fs0, w, h, lh=lh, min_fs=min_fs)
    if f is None:
        info["problems"].append(what + lines)
    return f, lines


def _image_el(x, y, w, h, info_logo, tag):
    """位图 Logo：等比放进框里，靠左、上下居中。导出时换成 PPTX 里的图片（唯一允许的位图）。"""
    s = min(w / info_logo["w"], h / info_logo["h"])
    iw, ih = info_logo["w"] * s, info_logo["h"] * s
    return (f'<image x="{x:.2f}" y="{y + (h - ih) / 2:.2f}" width="{iw:.2f}" height="{ih:.2f}" '
            f'href="{B.data_uri(info_logo)}" preserveAspectRatio="xMidYMid meet" data-logo="1" data-mod="{tag}"/>')


def _logo_el(x, y, w, h, logo, tag, notes):
    if logo["kind"] == "raster":
        return _image_el(x, y, w, h, logo, tag)
    el, frep = svgimport.fit(logo["svg"], (x, y, w, h), None, tag)
    notes += frep["problems"]
    return el


PIN_R = 12.0
MAX_PINS = 9


def _pins(mod, info, box, th, tag):
    """读图编号：mod["pins"] 是图内元素（磁吸点）的键，按顺序编 1、2、3……；画在元素右上角，不出这张卡。
    用正文深色，不用重音色——图里已经有一处重音，编号再用红就成了两处。"""
    keys = mod.get("pins") or []
    if not keys:
        return []
    by = {a["key"]: a for a in info.get("anchors") or []}
    ix, iy, iw, ih = box
    out, placed = [], []
    for n, k in enumerate(keys, 1):
        a = by.get(k)
        if not a:
            info["warnings"].append(f"编号 {n} 指向的元素在图里找不到了（图换过？）：请重新放")
            continue
        bx, by_, bw, bh = a["box"]
        if a.get("mid"):                                    # 关系线：贴在线的中点，放在标注的另一侧
            mx, my = a["mid"]
            lab_cx, lab_cy = bx + bw / 2, by_ + bh / 2
            if bw <= bh:                                    # 竖着的关系：标注在左就放右，在右就放左
                cx, cy = (mx + PIN_R + 5, my) if lab_cx < mx else (mx - PIN_R - 5, my)
            else:                                           # 横着的关系：标注在上就放下，在下就放上
                cx, cy = (mx, my + PIN_R + 5) if lab_cy < my else (mx, my - PIN_R - 5)
        elif a.get("card"):                                 # 圆点 + 卡片（V2 编号时间轴）：贴卡片朝外的上角，不压圆点
            cx_, cy_, cw_, _ = a["card"]
            out_left = cx_ <= bx + 1                        # 卡片在圆点左边：贴左上角；在右边：贴右上角
            cx, cy = (cx_ - PIN_R * 0.35 if out_left else cx_ + cw_ + PIN_R * 0.35), cy_ - PIN_R * 0.35
        else:                                               # 主体、事件、柱子：右上角
            cx, cy = bx + bw + PIN_R * 0.35, by_ - PIN_R * 0.35
        cx = min(max(cx, ix + PIN_R), ix + iw - PIN_R)
        cy = min(max(cy, iy + PIN_R), iy + ih - PIN_R)
        for px_, py_ in placed:                              # 两个编号挨太近：往下错开
            if abs(px_ - cx) < PIN_R * 2 and abs(py_ - cy) < PIN_R * 2:
                cy = min(cy + PIN_R * 2.2, iy + ih - PIN_R)
        placed.append((cx, cy))
        out += _badge(cx, cy, PIN_R, n, th["p"]["ink"], th["p"]["paper"], tag)
        info.setdefault("pins", []).append({"n": n, "key": k, "label": a["label"],
                                            "box": [round(cx - PIN_R, 1), round(cy - PIN_R, 1), PIN_R * 2, PIN_R * 2]})
    if len(keys) > 6:
        info["warnings"].append(f"一张图上 {len(keys)} 个编号：讲台上超过 6 个就乱，考虑切片或拆页")
    return out


def _step_numbers(mods):
    order = sorted((m for m in mods if m["type"] == "step"), key=lambda m: (m["y"], m["x"]))
    return {m["id"]: i + 1 for i, m in enumerate(order)}


# ------------------------------------------------------------- 拼一页
def compose(deck, idx, base_dir=".", cache=None, paste=False):
    """第 idx 页 → (svg, 报告)。报告：每个模块的 problems / warnings / notes，供编辑器标红与交付清单。
    paste=True：导出用的「粘贴版」——不画页码、页脚 Logo（律师自己课件的母版里有），整页底色交给导出器改成页面背景。"""
    import make                                    # V6
    from spec import SpecError
    s = deck["slides"][idx]
    mods = s.get("modules") or []
    firm = firm_of(deck, base_dir)
    dark = bool(firm) and any(m["type"] == "title" and m.get("level") in tuple(firm.get("dark_pages") or ("cover", "section"))
                              for m in mods)
    th = _theme(deck["style"], firm, dark)
    p = th["p"]
    g = G.geom(deck.get("frame"))                  # 版面：铺满全屏 / 预留位置
    parts, rep = [], {"modules": {}, "problems": [], "warnings": []}
    defs = ""
    if p.get("pattern"):
        defs = (f'<defs><pattern id="nlv-dots" width="26" height="26" patternUnits="userSpaceOnUse">'
                f'<circle cx="1.5" cy="1.5" r="1.1" fill="{p["pattern"]}"/></pattern></defs>')
    parts.append(f'<rect width="{W}" height="{H}" fill="{p["paper"]}" data-role="paper"/>')
    if defs:
        parts.append(f'<rect width="{W}" height="{H}" fill="url(#nlv-dots)" data-role="texture"/>')
    sides, _groups = G.fusion(mods)
    steps = _step_numbers(mods)
    issues = _ordinal(mods, "issue")
    try:
        brand = B.load(base_dir)
    except B.BrandError as e:
        brand = dict(B.empty(), _dir="")
        rep["warnings"].append(str(e))
    logo = B.logo_info(brand, dark) if (brand.get("logo") or brand.get("logo_on_dark")) else None
    accents = [m["id"] for m in mods if G.tone_of(m) == "accent"]
    if len(accents) > 1:
        rep["warnings"].append(f"第 {idx + 1} 页有 {len(accents)} 张重音卡：一页只该有一处最先被看到的地方")
    reserve = (deck.get("frame") or {}).get("mode") == "reserve"   # 预留位置：页码、页脚 Logo 由律所模板自己出
    show_page_no = not paste and not reserve and not any(m.get("bleed") for m in mods)
    for mod in sorted(mods, key=lambda m: (m["y"], m["x"])):
        info = {"problems": [], "warnings": [], "notes": []}
        rep["modules"][mod["id"]] = info
        t = mod["type"]
        tag = f"{s['id']}.{mod['id']}"
        tone_name = G.tone_of(mod)
        tone = th["tones"][tone_name]
        fsd = sides[mod["id"]]
        cx, cy, cw, ch = G.card_rect(mod, fsd, g)
        if tone_name != "bare":
            parts.append(_card_shape(cx, cy, cw, ch, G.corners(fsd, th["R"], th["r"]), tone["fill"], tone["stroke"], tag))
        x, y, w, h = G.px(mod, g)
        pad = 0 if tone_name == "bare" else PAD.get(t, PAD_DEFAULT)
        ix, iy, iw, ih = x + pad, y + pad, w - 2 * pad, h - 2 * pad
        try:
            mod = resolve(mod, base_dir)
        except (DeckError, OSError, ValueError) as e:
            info["problems"].append(str(e))
            continue

        if t == "title":
            level = mod.get("level") or "page"
            if level in ("cover", "section"):
                show_page_no = False
            fs = th["sizes"].get(level, th["sizes"]["page"])
            kick = str(mod.get("kicker") or "").strip()
            sub = str(mod.get("sub") or "").strip()
            if not str(mod.get("text") or "").strip():
                info["problems"].append("标题还是空的：写上标题，或删掉这个模块")
                continue
            body = []
            kh = 0
            if kick:
                kf = th["sizes"]["kicker"]
                body += _text_svg(ix, 0, [kick], kf, p["accent"], BODY_FONT, 400, 1.2, tag + ".kicker")
                kh = kf * 1.2 + 10
                info["notes"].append("章节编号用重音色")
            sh = th["sizes"]["sub"] * 1.35 + 14 if sub else 0
            f, lines = _fit_text(mod.get("text", ""), fs, iw, ih - kh - sh, lh=1.2, min_fs=24)
            if f is None:
                info["problems"].append("标题" + lines)
                continue
            if f < fs:
                info["notes"].append(f"标题长，字号由 {fs}px 收到 {f:.0f}px")
            body += _text_svg(ix, kh, lines, f, th["title_color"], th["title_family"], th["title_weight"], 1.2, tag)
            tot = kh + len(lines) * f * 1.2
            if sub:
                body += _text_svg(ix, tot + 14, _text_lines(sub, th["sizes"]["sub"], iw)[:2], th["sizes"]["sub"],
                                  p["ink2"], BODY_FONT, 400, 1.35, tag + ".sub")
                tot += sh
            oy = iy + (ih - tot) / 2 if level in ("page", "section") else iy + ih - tot
            parts.append(f'<g transform="translate(0,{oy:.2f})">' + "".join(body) + "</g>")
            if level == "cover":                      # 只有封面加一条重音短线
                parts.append(f'<rect x="{ix:.2f}" y="{oy - 30:.2f}" width="72" height="6" fill="{p["accent"]}" '
                             f'data-mod="{tag}.rule" data-hero="1"/>')
        elif t == "conclusion":                             # 一句话结论：这一页最要紧的那句话，粗体、左侧一道深色竖条
            txt = str(mod.get("text") or "").strip()
            if not txt:
                info["problems"].append("结论还是空的：用一句话说这张图要讲什么")
                continue
            fs0 = 26 if ih >= 70 else 22
            f, lines = _fit_text(txt, fs0, iw - 18, ih, lh=1.3, min_fs=MIN_BODY)
            if f is None:
                info["problems"].append("结论" + lines + "（结论只该一两句）")
                continue
            if len(lines) > 2:
                info["warnings"].append("结论写成了三行以上：一句话结论最好一两行")
            bh = len(lines) * f * 1.3
            by0 = iy + (ih - bh) / 2
            parts.append(f'<rect x="{ix:.2f}" y="{by0 + f * 0.12:.2f}" width="5" height="{bh - f * 0.24:.2f}" '
                         f'fill="{tone["ink"]}" data-mod="{tag}"/>')
            parts += _text_svg(ix + 18, by0, lines, f, tone["ink"], BODY_FONT, 700, 1.3, tag)
        elif t == "note":
            if not str(mod.get("text") or "").strip():
                info["problems"].append("注释还是空的：写上来源或说明，或删掉这个模块")
                continue
            f, lines = _fit_text(mod.get("text", ""), th["sizes"]["note"], iw, ih, lh=1.4, min_fs=12)
            if f is None:
                info["problems"].append("注释" + lines)
                continue
            parts += _text_svg(ix, iy + ih - len(lines) * f * 1.4, lines, f, p["note"], BODY_FONT, 400, 1.4, tag)
        elif t in ("text", "bullets"):
            hp, hh = _heading(mod, th, tone, ix, iy, iw, tag)
            parts += hp
            if t == "text":
                if not str(mod.get("text") or "").strip():
                    info["problems"].append("正文卡还是空的：写一段话，或删掉这个模块")
                    continue
                f, lines = _fit_text(mod.get("text", ""), 24 if ih - hh >= 200 else th["sizes"]["body"], iw, ih - hh, lh=1.5)
                if f is None:
                    info["problems"].append(lines)
                    continue
                parts += _text_svg(ix, iy + hh, lines, f, tone["ink"], BODY_FONT, 400, 1.5, tag)
            else:
                items = [str(i) for i in mod.get("items") or [] if str(i).strip()]
                if not items:
                    info["problems"].append("要点卡还是空的：至少写一条")
                    continue
                parts += _bullets(items, th, tone, ix, iy + hh, iw, ih - hh, tag, info, bool(mod.get("numbered")))
        elif t == "stat":
            val = str(mod.get("value") or "").strip()
            if not val:
                info["problems"].append("大数字卡还没写数字")
                continue
            label = str(mod.get("label") or "").strip()
            note = str(mod.get("note") or "").strip()
            lf = 18
            llines = _text_lines(label, lf, iw)[:2] if label else []
            nlines = _text_lines(note, 14, iw)[:2] if note else []
            rest = len(llines) * lf * 1.35 + (8 if llines else 0) + len(nlines) * 14 * 1.4 + (6 if nlines else 0)
            vf = min(80.0, (ih - rest) / 1.05)
            while vf > 28 and text_w(val, vf) > iw:
                vf -= 2
            if vf < 28 or text_w(val, vf) > iw:
                info["problems"].append(f"数字「{val}」在这张卡片里放不下：把卡片拉宽，或把说明写短")
                continue
            parts += _text_svg(ix, iy, [val], vf, tone["mark"], BODY_FONT, 700 if th["q"] else 300, 1.05,
                               tag + ".value")
            yy = iy + vf * 1.05 + 8
            parts += _text_svg(ix, yy, llines, lf, tone["ink"], BODY_FONT, 400, 1.35, tag + ".label")
            yy += len(llines) * lf * 1.35 + 6
            parts += _text_svg(ix, yy, nlines, 14, tone["ink2"], BODY_FONT, 400, 1.4, tag + ".note")
            sp, sn, sw = _stat_check(mod, mods, base_dir)
            info["problems"] += sp
            info["notes"] += sn
            rep["warnings"] += [f"第 {idx + 1} 页{w}" for w in sw]
        elif t == "step":
            # 编号在上，小标题与正文贴底：卡片高的时候中间留白，像一张卡而不是一段字
            n = steps[mod["id"]]
            nf = 44 if ih >= 200 else 30
            parts += _text_svg(ix, iy, [f"{n:02d}"], nf, tone["mark"], BODY_FONT, 700 if th["q"] else 300, 1.0,
                               tag + ".no")
            room = ih - nf - 20
            hd = str(mod.get("heading") or "").strip()
            body = str(mod.get("text") or "").strip()
            if not hd and not body:
                info["problems"].append("编号卡还是空的：写个小标题或一句话")
                continue
            hf = 26 if room >= 160 else 22
            hl = _text_lines(hd, hf, iw)[:2] if hd else []
            hh = len(hl) * hf * 1.3 + (10 if hl and body else 0)
            blk = []
            bh = 0
            if body:
                f, lines = _fit_text(body, 20 if room >= 160 else 18, iw, room - hh, lh=1.5)
                if f is None:
                    info["problems"].append(lines)
                    continue
                bh = len(lines) * f * 1.5
            top = iy + ih - hh - bh                         # 编号在上、文字贴底：这是卡片的构图（试过把文字提到中间，反而像悬着）
            parts += _text_svg(ix, top, hl, hf, tone["ink"], th["title_family"], th["head_weight"], 1.3, tag + ".head")
            if body:
                parts += _text_svg(ix, top + hh, lines, f, tone["ink2"], BODY_FONT, 400, 1.5, tag)
        elif t == "quote":
            src = str(mod.get("source") or "").strip()
            if not src:
                info["problems"].append("金句要写出处（source）：哪一份判决、哪一条法条。照录原文，出处必填")
                continue
            sl = _text_lines("—— " + src, 16, iw - 20)[:2]
            src_h = len(sl) * 16 * 1.4 + 16
            q0 = 40 if iw >= 600 and ih >= 240 else th["sizes"]["quote"]
            f, lines = _fit_text("「" + str(mod.get("text", "")).strip() + "」", q0, iw - 20,
                                 ih - src_h, lh=1.55, min_fs=18)
            if f is None:
                info["problems"].append(lines)
                continue
            qh = len(lines) * f * 1.55
            qy = iy + (ih - qh - src_h) / 2                 # 金句在卡片里上下居中
            parts.append(f'<rect x="{ix:.2f}" y="{qy + 4:.2f}" width="4" height="{qh - 8:.2f}" fill="{p["accent"]}" '
                         f'data-mod="{tag}.rail"/>')
            parts += _text_svg(ix + 20, qy, lines, f, tone["ink"], th["title_family"], 400, 1.55, tag)
            parts += _text_svg(ix + 20, qy + qh + 16, sl, 16, tone["ink2"], BODY_FONT, 400, 1.4, tag + ".src")
            info["notes"].append("金句照录原文，交付前请与出处逐字核对")
            rep["warnings"].append(f"第 {idx + 1} 页金句：请与「{src}」逐字核对")
        elif t == "statute":
            law = str(mod.get("law") or "").strip().strip("《》")
            body = str(mod.get("text") or "").strip()
            if not law or not body:
                info["problems"].append("法条卡要写法律名称（law）和条文原文（text）：照录官方文本，不凭记忆写")
                continue
            label = f"《{law}》" + str(mod.get("article") or "").strip()
            kp, kh = _kicker(ix, iy, label, th, tone, tag)
            f, lines = _fit_block(body, 24 if ih - kh >= 200 else 20, iw, ih - kh, info, "条文")
            if f is None:
                continue
            parts += kp + _text_svg(ix, iy + kh, lines, f, tone["ink"], th["title_family"], 400, 1.55, tag)
            info["notes"].append("条文照录原文，交付前请与官方文本逐字核对")
            rep["warnings"].append(f"第 {idx + 1} 页法条：请把{label}与官方文本逐字核对")
        elif t == "holding":
            body = str(mod.get("text") or "").strip()
            court = str(mod.get("court") or "").strip()
            no = str(mod.get("case_no") or "").strip()
            if not body or not (court or no):
                info["problems"].append("裁判要旨要写原文（text）和出处（court 法院、case_no 案号）：照录，不编")
                continue
            kp, kh = _kicker(ix, iy, "裁判要旨", th, tone, tag)
            src = "—— " + "　".join(x for x in (court, no) if x)
            sl = _text_lines(src, 16, iw)[:2]
            sh = len(sl) * 16 * 1.4 + 10
            f, lines = _fit_block(body, 24 if ih - kh - sh >= 200 else 20, iw, ih - kh - sh, info, "要旨")
            if f is None:
                continue
            parts += kp + _text_svg(ix, iy + kh, lines, f, tone["ink"], th["title_family"], 400, 1.55, tag)
            parts += _text_svg(ix, iy + ih - len(sl) * 16 * 1.4, sl, 16, tone["ink2"], BODY_FONT, 400, 1.4, tag + ".src")
            rep["warnings"].append(f"第 {idx + 1} 页裁判要旨：请与{court or no}的裁判文书逐字核对")
        elif t == "case":
            no = str(mod.get("case_no") or "").strip()
            if not no:
                info["problems"].append("案例卡要写案号（case_no）：照判决书写，不编")
                continue
            kp, kh = _kicker(ix, iy, "案例", th, tone, tag)
            parts += kp
            yy = iy + kh
            head = str(mod.get("heading") or mod.get("cause") or "").strip()
            if head:
                hl = _text_lines(head, 22, iw)[:2]
                parts += _text_svg(ix, yy, hl, 22, tone["ink"], th["title_family"], th["head_weight"], 1.3, tag + ".head")
                yy += len(hl) * 22 * 1.3 + 8
            meta = [x for x in (no, str(mod.get("court") or "").strip()) if x]
            ml = [ln for x in meta for ln in _text_lines(x, 15, iw)[:2]]
            parts += _text_svg(ix, yy, ml, 15, tone["ink2"], BODY_FONT, 400, 1.45, tag + ".meta")
            yy += len(ml) * 15 * 1.45 + 12
            res = str(mod.get("result") or "").strip()
            if res:
                rl = _text_lines(res, 18, iw)[:3]
                parts += _text_svg(ix, yy, rl, 18, tone["mark"], BODY_FONT, 700 if th["q"] else 400, 1.4, tag + ".result")
                yy += len(rl) * 18 * 1.4 + 10
            pt = str(mod.get("point") or mod.get("text") or "").strip()
            if pt:
                f, lines = _fit_block(pt, 18, iw, iy + ih - yy, info, "案例要点", lh=1.5)
                if f is None:
                    continue
                parts += _text_svg(ix, yy, lines, f, tone["ink2"], BODY_FONT, 400, 1.5, tag)
            elif yy > iy + ih + 1:
                info["problems"].append("案例卡太小，放不下案号与法院：把卡片拉大")
        elif t in ("issue", "risk"):
            label = f"争议焦点{CN_NUM[issues[mod['id']] - 1] if issues[mod['id']] <= 10 else issues[mod['id']]}" \
                if t == "issue" else "风险提示"
            hd = str(mod.get("heading") or "").strip()
            body = str(mod.get("text") or "").strip()
            if not hd and not body:
                info["problems"].append(f"{TYPES[t]['zh']}卡还是空的：写一句话")
                continue
            kp, kh = _kicker(ix, iy, label, th, tone, tag, mark=(t == "risk"))
            parts += kp
            hl = _text_lines(hd, 24 if ih >= 260 else 20, iw)[:3] if hd else []
            hf = 24 if ih >= 260 else 20
            hh = len(hl) * hf * 1.35 + (10 if hl and body else 0)
            parts += _text_svg(ix, iy + kh, hl, hf, tone["ink"], th["title_family"], th["head_weight"], 1.35, tag + ".head")
            if body:
                f, lines = _fit_block(body, 18, iw, ih - kh - hh, info, "")
                if f is None:
                    continue
                parts += _text_svg(ix, iy + kh + hh, lines, f, tone["ink2"], BODY_FONT, 400, 1.55, tag)
        elif t == "evidence":
            items = [str(i).strip() for i in mod.get("items") or [] if str(i).strip()]
            if not items:
                info["problems"].append("证据卡还是空的：一行一份证据，写成「证据名称——证明目的」")
                continue
            hp, hh = _heading(mod, th, tone, ix, iy, iw, tag)
            parts += hp
            rows = [re.split(r"\s*(?:——|—|｜|\|)\s*", it, maxsplit=1) for it in items]
            lab_w = 64
            f = 18
            while True:
                blocks = [(_text_lines(r[0], f, iw - lab_w), _text_lines(r[1], f - 2, iw - lab_w) if len(r) > 1 else [])
                          for r in rows]
                need = sum(len(a) * f * 1.35 + len(b) * (f - 2) * 1.4 + 12 for a, b in blocks)
                if need <= ih - hh or f <= MIN_BODY:
                    break
                f -= 1
            if need > ih - hh + 1e-6:
                info["problems"].append(f"证据放不下：{len(items)} 份在这张卡片里最小字号也要 {need:.0f}px 高。拆页或把卡片拉大")
                continue
            yy = iy + hh
            for k, (a, b2) in enumerate(blocks):
                parts += _text_svg(ix, yy + 1, [f"证据{k + 1}"], 14, tone["mark"], BODY_FONT, 700 if th["q"] else 400, 1.2,
                                   tag + ".no")
                parts += _text_svg(ix + lab_w, yy, a, f, tone["ink"], BODY_FONT, 700 if th["q"] else 400, 1.35, tag)
                yy += len(a) * f * 1.35
                parts += _text_svg(ix + lab_w, yy + 2, b2, f - 2, tone["ink2"], BODY_FONT, 400, 1.4, tag + ".purpose")
                yy += len(b2) * (f - 2) * 1.4 + 12
        elif t == "logo":
            if not logo:
                info["problems"].append("还没有 Logo：在「更多 → 律所名片」里上传（PNG、JPG 或 SVG）")
                continue
            notes = []
            parts.append(_logo_el(x, y, w, h, logo, tag, notes))
            info["notes"].append("Logo 来自律所名片" + ("（PNG/JPG 作为图片放进 PPTX）" if logo["kind"] == "raster" else "（SVG 转成可编辑形状）"))
        elif t == "profile":
            who = mod.get("who") or "firm"
            data = dict(B.who_data(brand, who) or {})
            for k in ("intro", "areas", "title"):
                if mod.get(k):
                    data[k] = mod[k]
            intro = str(data.get("intro") or "").strip()
            areas = [str(a).strip() for a in data.get("areas") or [] if str(a).strip()]
            if not intro and not areas:
                info["problems"].append("名片里还没有这段介绍：在「更多 → 律所名片」里填介绍和业务领域" if not B.who_data(brand, who)
                                        else "介绍是空的：在「更多 → 律所名片」里写介绍或业务领域")
                continue
            yy = iy
            sub = str(data.get("title") or "").strip() if data.get("kind") == "lawyer" else ""
            if sub and not any(m["type"] == "title" and m.get("sub") == sub for m in mods):
                parts += _text_svg(ix, yy, [sub], 18, tone["ink2"], BODY_FONT, 400, 1.3, tag + ".sub")
                yy += 18 * 1.3 + 12
            chip_h = 0
            chip_rows = []
            if areas:
                cf, cx0, rows, cur, cw_ = 15, ix, [], [], 0
                for a in areas:
                    wa = text_w(a, cf) + 24
                    if cur and cw_ + wa > iw:
                        rows.append(cur)
                        cur, cw_ = [], 0
                    cur.append((a, wa))
                    cw_ += wa + 8
                rows.append(cur)
                chip_rows = rows[:3]
                chip_h = 16 * 1.2 + 10 + len(chip_rows) * 40
            if intro:
                tw = min(iw, 820.0)                       # 一行不超过约 36 个字：长段落太宽读不动
                f, lines = _fit_block(intro, 24 if ih >= 300 else 20, tw, iy + ih - yy - chip_h - (16 if areas else 0), info,
                                      "介绍", lh=1.7)
                if f is None:
                    continue
                parts += _text_svg(ix, yy, lines, f, tone["ink"], BODY_FONT, 400, 1.7, tag)
            if chip_rows:
                cy0 = iy + ih - chip_h
                kp, kh = _kicker(ix, cy0, "业务领域", th, tone, tag)
                parts += kp
                ry = cy0 + kh
                for row in chip_rows:
                    rx = ix
                    for a, wa in row:
                        parts.append(f'<rect x="{rx:.2f}" y="{ry:.2f}" width="{wa:.2f}" height="30" '
                                     + (f'rx="{15 if th["q"] else 0}" ' if th["q"] else "")
                                     + f'fill="none" stroke="{th["tones"]["outline"]["stroke"]}" stroke-width="1" data-mod="{tag}.chip"/>')
                        parts += _text_svg(rx + 12, ry + 7.5, [a], 15, tone["ink2"], BODY_FONT, 400, 1.2, tag + ".area")
                        rx += wa + 8
                    ry += 40
            info["notes"].append("内容实时读自律所名片：改名片，这一页跟着变")
        elif t == "contact":
            lines_ = B.contact_lines(brand, mod.get("who"))
            if not lines_:
                info["problems"].append("名片里还没有地址、电话、邮箱或网址：在「更多 → 律所名片」里填")
                continue
            if h <= g["ROW"] + 1e-6:                     # 一行高：横排
                rx = ix if tone_name == "bare" else ix
                cy = iy + (ih - 18) / 2 if tone_name != "bare" else iy + (ih - 18) / 2
                total = sum(text_w(z, 14) + 8 + text_w(v, 17) + 32 for z, v in lines_)
                if total > iw:
                    info["problems"].append("联系方式一行放不下：把卡片拉高到 2 行，或减少几项")
                    continue
                for z, v in lines_:
                    parts += _text_svg(rx, cy + 2, [z], 14, tone["ink2"], BODY_FONT, 400, 1.2, tag + ".lab")
                    rx += text_w(z, 14) + 8
                    parts += _text_svg(rx, cy, [v], 17, tone["ink"], BODY_FONT, 400, 1.2, tag)
                    rx += text_w(v, 17) + 32
            else:
                yy = iy
                for z, v in lines_:
                    vl = _text_lines(v, 17, iw)[:2]
                    need = 14 * 1.3 + 2 + len(vl) * 17 * 1.35 + 12
                    if yy + need > iy + ih + 1e-6:
                        info["warnings"].append("联系方式没放全：把卡片拉高")
                        break
                    parts += _text_svg(ix, yy, [z], 14, tone["ink2"], BODY_FONT, 400, 1.3, tag + ".lab")
                    parts += _text_svg(ix, yy + 14 * 1.3 + 2, vl, 17, tone["ink"], BODY_FONT, 400, 1.35, tag)
                    yy += need
        elif t == "chart":
            cwi, chi = int(iw), int(ih)
            if dark:
                info["problems"].append("律所风格的封面、章节页是深底，图表放不清：请放到内容页")
                continue
            fk = ({"name": firm["name"], "base": th["base"], "accent": firm["colors"]["accent"],
                   "title_font": (firm.get("fonts") or {}).get("title", "sans")} if firm else None)
            key = (json.dumps(mod["spec"], ensure_ascii=False, sort_keys=True), deck["style"], cwi, chi,
                   fk and fk["accent"])
            try:
                if cache is not None and key in cache:
                    svg, crep = cache[key]
                else:
                    svg, crep = make.build(copy.deepcopy(mod["spec"]), th["base"], None, {"w": cwi, "h": chi}, None, fk)
                    if cache is not None:
                        cache[key] = (svg, crep)
            except (SpecError, ValueError) as e:
                info["problems"].append(f"V6 不出这张图：{str(e).splitlines()[0]}")
                continue
            if crep["problems"]:
                info["problems"].append("V6 守卫没过：" + "；".join(crep["problems"][:2]) + "。试试把卡片拉大")
                continue
            if mod.get("sample"):                              # 图表库放进来的示例：照常画出来看样子，但不许当成律师的数据导出
                info["problems"].append("这张图还是图表库里的示例数据：交给 AI 换成您的数据，或在右边改「V6 图表说明」")
            for wn in crep["warnings"]:
                info["warnings"].append(wn)
                rep["warnings"].append(f"第 {idx + 1} 页图表：{wn}")
            info["notes"].append(f"V6 {crep['chart']}，按卡片内框 {cwi}×{chi} 重画并过守卫")
            body = re.sub(r"^<svg[^>]*>|</svg>\s*$", "", svg.strip())
            body = re.sub(r"<title\b.*?</title>|<desc\b.*?</desc>|<defs>.*?</defs>", "", body, flags=re.S)
            body = re.sub(r'<rect [^>]*data-role="(paper|texture)"[^>]*/>', "", body)
            if mod.get("focus"):                               # 聚焦：只点亮这几个数据项，其余调浅
                body = svgimport.fade_ids(body, set(mod["focus"]))
            body = unbold_titles(body)                          # V6 图里的宋体标题：同样不加粗、不描边
            for el in ("path", "text", "circle", "line", "polygon", "polyline"):
                body = body.replace(f"<{el} ", f'<{el} data-mod="{tag}" ')
            parts.append(f'<g transform="translate({ix:.2f},{iy:.2f})">{body}</g>')
            info["anchors"] = svgimport.fit(svg, (ix, iy, cwi, chi))[1]["anchors"]   # V6 每个数据项（柱、扇区、点……）
            _pv = P_.keep(P_.for_chart(crep), info["anchors"])      # 逐件记录算出的图：每一项来自哪几条记录
            if _pv:
                info["prov"] = _pv
            parts += _pins(mod, info, (ix, iy, iw, ih), th, tag)
        elif t == "figure":
            if dark:
                info["problems"].append("律所风格的封面、章节页是深底，图放不清：请放到内容页")
                continue
            if "svg" not in mod:                                   # V5：V7 自己按图卡宽度调 V5 出图（V5 文件不改）
                try:
                    asvg, arep = A.render(mod, base_dir, iw, cache)
                except A.AdaptError as e:
                    info["problems"].append(str(e))
                    continue
                mod["svg"] = asvg
                info["parts"] = arep["parts"]
                info["notes"] += arep["notes"]
                if not mod.get("crop"):                            # 自动只取卡片：去掉标题、索引表、图例
                    _, r0 = svgimport.fit(asvg, svgimport.size_of(asvg))
                    mod["crop"] = [a["key"] for a in r0["anchors"] if a["key"].startswith("card:")] or None
            has_title = any(m["type"] == "title" for m in mods)    # 这一页有自己的标题：略去图里自带的标题
            el, frep = svgimport.fit(mod["svg"], (ix, iy, iw, ih), None if firm else deck["style"], tag,
                                     trim=not mod.get("bleed"), drop_title=has_title,   # 整页出血：原图的边就是页边，不裁
                                     crop=mod.get("crop") or None,                      # 切片：只取这几个元素那一块
                                     light=mod.get("focus") or None)                    # 聚焦：只点亮这几个元素
            info["warnings"] += frep.get("warnings") or []
            if frep.get("view") and frep.get("min_font") and frep.get("scale"):   # 编辑器拉大拉小时实时算字号、吸到最贴合的尺寸
                info["fig"] = {"w": frep["view"][0], "h": frep["view"][1], "pad": pad,
                               "min1": round(frep["min_font"] / frep["scale"], 3)}
            if frep.get("crop"):
                info["crop"] = frep["crop"]
            info["anchors"] = frep["anchors"]                       # 图内元素（磁吸点）：编号、引线以后吸在这些上
            _pv = P_.for_figure(mod, base_dir, info["anchors"])   # V2 / V3 图旁边的出处记录：每件事、每个主体与关系出自哪里
            if _pv:
                info["prov"] = _pv
            if firm and frep["style"] in STYLES:
                w_ = (f"这张图是{frep['style']}的原色（{mod.get('from') or 'V1–V5'}），与律所风格的主色不同；"
                      f"V7 不改别的模块的图，可以回原模块出白描版，放在律所风格里更协调")
                info["warnings"].append(w_)
                rep["warnings"].append(f"第 {idx + 1} 页：{w_}")
            info["problems"] += frep["problems"]
            info["notes"] += frep["notes"] + [f"{mod.get('from') or 'V1–V5'} 的图，等比缩放 {frep['scale']:.2f}"
                                              + (f"，最小字 {frep['min_font']:.1f}px" if frep["min_font"] else "")]
            if frep["problems"] and (not el or not all("最小的字" in p_ for p_ in frep["problems"])):
                continue                                     # 风格不一致等：不画
            parts.append(unbold_titles(el))                  # 字太小也照样画出来：律师要看着图去切片；导出仍被拦下
            parts += _pins(mod, info, (ix, iy, iw, ih), th, tag)   # 字太小也画编号：律师看得到放在哪；导出仍被拦
    footer = deck.get("footer_logo")
    if footer is None:
        footer = bool(brand.get("footer_logo"))
    if footer and logo and show_page_no and mods and not any(m["type"] == "logo" for m in mods):
        notes = []
        parts.append(_logo_el(g["MX"], H - 40, 140, 22, logo, f"{s['id']}.footer-logo", notes))
    if show_page_no and mods:
        parts.append(f'<text x="{W - g["MX"]}" y="{H - 22}" font-size="14" fill="{p["note"]}" font-family="{BODY_FONT}" '
                     f'text-anchor="end" data-mod="page">{idx + 1:02d}</text>')
    if not mods:                                            # 空页：导出前要放东西（编辑器里会请律师先选场景）
        rep["problems"].append(f"第 {idx + 1} 页还是空的：从左边「图表库」挑一张图，或在「诉讼图」里点一个场景")
    n_pins = sum(len(i.get("pins") or []) for i in rep["modules"].values())
    for m in mods:                                          # 要点卡「按编号排」：条数与图上的编号对得上
        if m["type"] == "bullets" and m.get("numbered") and m["id"] in rep["modules"]:
            k = len([i for i in m.get("items") or [] if str(i).strip()])
            if not n_pins:
                rep["modules"][m["id"]]["warnings"].append("要点按编号排，但图上还没放编号：选中图，点「放编号」")
            elif k != n_pins:
                rep["modules"][m["id"]]["warnings"].append(f"图上 {n_pins} 个编号，要点 {k} 条：对不上，讲的时候会乱")
    for mid, info in rep["modules"].items():
        zh = next((TYPES[m["type"]]["zh"] for m in mods if m["id"] == mid), "")
        rep["problems"] += [f"第 {idx + 1} 页{zh}「{mid}」：{x}" for x in info["problems"]]
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
           f'font-family="{BODY_FONT}">{defs}' + "".join(parts) + "</svg>")
    return svg, rep


def chart_alternatives(deck, idx, mod_id, base_dir=".", cache=None):
    """「换一种图」：同一份 V6 数据换成别的图种，交给 V6 自己试——出得来就能换，出不来 V6 会说为什么（数据不适合那种图）。
    返回 [{"chart", "zh", "ok", "current", "why", "spec"}]。只读，不改课件。"""
    import make                                    # V6
    from spec import CHARTS, CHART_ZH, SpecError
    m = next(x for x in deck["slides"][idx]["modules"] if x["id"] == mod_id and x["type"] == "chart")
    mod = resolve(m, base_dir)
    firm = firm_of(deck, base_dir)
    th = _theme(deck["style"], firm)
    g = G.geom(deck.get("frame"))
    _, _, w, h = G.px(m, g)
    pad = 0 if G.tone_of(m) == "bare" else PAD.get("chart", PAD_DEFAULT)
    box = {"w": int(w - 2 * pad), "h": int(h - 2 * pad)}
    fk = ({"name": firm["name"], "base": th["base"], "accent": firm["colors"]["accent"],
           "title_font": (firm.get("fonts") or {}).get("title", "sans")} if firm else None)
    cur = mod["spec"].get("chart")
    out = []
    for c in CHARTS:
        sp = copy.deepcopy(mod["spec"])
        sp["chart"] = c
        key = ("alt", json.dumps(sp, ensure_ascii=False, sort_keys=True), deck["style"], box["w"], box["h"], fk and fk["accent"])
        if cache is not None and key in cache:
            ok, why = cache[key]
        else:
            try:
                make.build(copy.deepcopy(sp), th["base"], None, box, None, fk)
                ok, why = True, ""
            except (SpecError, ValueError) as e:
                ok, why = False, str(e).split("\n")[0][:140]
            if cache is not None:
                cache[key] = (ok, why)
        out.append({"chart": c, "zh": CHART_ZH.get(c, c), "ok": ok, "current": c == cur, "why": why, "spec": sp if ok else None})
    return out


def compose_all(deck, base_dir=".", cache=None, paste=False):
    return [compose(deck, i, base_dir, cache, paste) for i in range(len(deck["slides"]))]


def allowed_colors(deck, base_dir=None):
    """导出审计的颜色白名单。律所风格：律所风格文件里的颜色 + V6 图表（基础风格的灰 + 律所主色）。"""
    firm = firm_of(deck, base_dir)
    if not firm:
        return set(WHITELIST[deck["style"]])
    base = firm.get("base") or "奇川风"
    import firm_style as FS
    v6 = (set(WHITELIST[base]) - {palette(base)[0]["accent"]}) | {firm["colors"]["accent"]}
    return FS.colors(firm) | v6


def texts_of(deck):
    """课件里写的字（回读审计用：导出后都要在 PPTX 里找得到）。"""
    out = []
    for s in deck["slides"]:
        for m in s.get("modules") or []:
            if m["type"] in ("chart", "figure"):
                continue
            if m["type"] in ("profile", "contact", "logo"):
                continue                                     # 这三种的字来自律所名片
            for k in ("text", "heading", "kicker", "sub", "value", "label", "case_no", "court", "result", "point"):
                if m.get(k):
                    out.append(str(m[k]).split("\n")[0])
            for i in m.get("items") or []:
                if m["type"] == "evidence":                  # 「名称——证明目的」分两段画，回读也分两段核
                    out += [x for x in re.split(r"\s*(?:——|—|｜|\|)\s*", str(i), maxsplit=1)]
                else:
                    out.append(str(i))
    return [t for t in out if t.strip()]
