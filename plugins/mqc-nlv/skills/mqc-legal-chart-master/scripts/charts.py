# -*- coding: utf-8 -*-
"""七种图的渲染器。

**先定画框，再定绘图区，最后才定每个数据元素。** 画框（标题、副标题、来源行）由画布的
物理尺寸算出；剩下的才是绘图区；绘图区里每根柱、每个点的位置只由一把比例尺决定。

几何约定（与 V1 的「形状即语义」一脉相承）：
  * 奇川风：所有填充形状的尖角都是贝塞尔小圆角（corners.py），线头是圆头；
    歸藏风：一律直角、平头，不磨圆；
  * 纵轴从 0 起，不断轴；
  * 面积编码（玫瑰）半径取平方根；
  * 一张图只有一处重音，就是 emphasis 指向的那一个数据。
"""
import hashlib
import math

from kernel import text_w, wrap
from spec import SpecError, CHART_ZH, _fmt, xsum
from svgfig import Fig
import callout

REF_W, REF_H = 1280.0, 720.0
FLOOR = 11.0          # 任何字都不小于 11px（投影与 A4 打印都在 8pt 以上）


# =============================================================== frame
class Frame:
    """画框：字号、页边、标题块、副标题、来源行、绘图区。"""

    def __init__(self, m, W, H, pal):
        self.m, self.W, self.H, self.p = m, W, H, pal
        k = min(W / REF_W, H / REF_H)
        if H >= W * 0.9:
            # 方图与竖图是给手机看的：1080px 宽的图在手机上缩到三分之一左右，
            # 按幻灯片的比例定字号会小到读不清。字号改按宽度定，比幻灯片大约一半。
            k = W / 860.0
        self.k = k
        guizang = pal["style"] == "歸藏风"
        self.fs = {
            "title": max(22.0, (44.0 if guizang else 38.0) * k),
            "sub": max(13.0, 17.0 * k),
            "tick": max(FLOOR, 13.0 * k),
            "label": max(12.0, 16.0 * k),
            "value": max(12.0, 15.0 * k),
            "big": max(26.0, 46.0 * k),
            "source": max(FLOOR, 12.5 * k),
        }
        self.mx = max(28.0, 64.0 * k)
        self.top = max(24.0, (64.0 if guizang else 50.0) * k)
        self.bottom = max(18.0, 34.0 * k)
        self.track = pal["num_track"] * self.fs["value"]
        # 小圆角半径由风格定：奇川风整页 5px、随画布缩放、不小于 3px；歸藏风为 0（直角）
        base = pal.get("corner", 0.0)
        self.corner = max(3.0, base * k) if base > 0 else 0.0

    def title_text(self):
        return self.m["title"]

    def subtitle_text(self, encoding):
        n = self.m["n"]
        parts = [self.m["scope"]]
        if encoding:
            parts.append(encoding)
        parts.append(f"n = {_fmt(n)}")
        return " · ".join(parts)

    def draw(self, fig, encoding):
        p, fs = self.p, self.fs
        avail = self.W - 2 * self.mx
        title = self.title_text()
        tfs = fs["title"]
        while True:
            lines = wrap(title, tfs, avail, keep_alnum=True)
            if len(lines) <= 2:
                break
            tfs -= 1
            if tfs < 20:
                raise SpecError(f"图名「{title}」太长：在这块画布上两行放不下（每行约 "
                                f"{int(avail // 20)} 字）。请删短")
        y = self.top + tfs * 0.88
        fam = "serif" if p["title_font"] == "serif" else "sans"
        for i, ln in enumerate(lines):
            if i:
                y += tfs * 1.25
            fig.text(self.mx, y, ln, tfs, p["ink"], weight=p["title_weight"], family=fam, role="title")
        y += tfs * 0.17 + fs["sub"] * 0.55          # 标题末行的字底，再空半个副标题字高
        sub = self.subtitle_text(encoding)
        slines = wrap(sub, fs["sub"], avail)
        if len(slines) > 2:
            raise SpecError("副标题（口径 · 编码 · n）两行放不下，请把 scope 写短")
        for ln in slines:
            y += fs["sub"] * 1.1
            fig.text(self.mx, y, ln, fs["sub"], p["ink2"], role="subtitle")
            y += fs["sub"] * 0.35
        self.plot_top = y + max(18.0, 30.0 * self.k)
        # 来源行
        src = "来源：" + self.m["source"]
        srclines = wrap(src, fs["source"], avail)
        if len(srclines) > 2:
            raise SpecError("来源行两行放不下，请把 source 写短")
        yb = self.H - self.bottom
        for i, ln in enumerate(reversed(srclines)):
            fig.text(self.mx, yb - i * fs["source"] * 1.35, ln, fs["source"], p["note"], role="source")
        rule_y = yb - (len(srclines) - 1) * fs["source"] * 1.35 - fs["source"] * 1.55
        fig.line(self.mx, rule_y, self.W - self.mx, rule_y, p["grid"],
                 1, role="rule")
        self.plot_bottom = rule_y - max(14.0, 24.0 * self.k)
        self.plot_left, self.plot_right = self.mx, self.W - self.mx
        # 有批注时，在右侧留一条批注栏：批注不压在数据上
        if self.m.get("annotations"):
            self.note_fs = max(12.0, 15.0 * self.k)
            self.note_w = max(150.0, min(300.0, avail * 0.24))
            gap = max(16.0, 28.0 * self.k)
            self.plot_right -= self.note_w + gap
            self.note_x = self.plot_right + gap
            self.lane = self.note_fs * 1.8      # 竖柱、逐级加减的柱顶上方留一条引线通道
        else:
            self.lane = 0.0
        if self.plot_bottom - self.plot_top < 140:
            raise SpecError("画布太小：扣掉标题、副标题和来源行之后，绘图区不足 140px 高。"
                            "请换大一档画布，或把标题写短")


# =============================================================== helpers
def nice_ticks(vmax, want=5, integer=False):
    """integer=True 用于件数：刻度只取整数（「0.5 件」读起来像数据出了错）。"""
    if vmax <= 0:
        return [0, 1]
    raw = vmax / (want - 1)
    mag = 10 ** math.floor(math.log10(raw))
    for f in (1, 2, 2.5, 5, 10):
        step = f * mag
        if integer and step < 1:
            continue
        if integer and not float(step).is_integer():
            continue
        if vmax / step <= want - 0.5:
            break
    top = math.ceil(vmax / step - 1e-9) * step
    n = int(round(top / step))
    return [round(i * step, 10) for i in range(n + 1)]


def tick_label(v):
    return _fmt(int(v) if float(v).is_integer() else v)


def jitter(*key):
    h = hashlib.sha1("|".join(map(str, key)).encode("utf-8")).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


def _hero_id(m):
    return m.get("emphasis")


def _mark_paint(p, idx=None, hero=False):
    """返回 (fill, stroke, dash)。"""
    if hero:
        return p["accent"], None, None
    if idx is None:
        fill = p["mark"]
        dash = None
    else:
        fill = p["ladder"][min(idx, len(p["ladder"]) - 1)]
        dash = p["dash_ladder"][min(idx, len(p["dash_ladder"]) - 1)]
    return fill, p["outline"], dash


def _num_text(fig, fr, x, y, v, hero=False, anchor="middle", fs=None, unit=None, **meta):
    p = fr.p
    s = _fmt(v) + (unit or "")
    fig.text(x, y, s, fs or fr.fs["value"], p["accent"] if hero else p["ink"], anchor=anchor,
             weight=600 if hero else 500, family="mono", track=fr.track, hero=hero, **meta)


# =============================================================== bar
def render_bar(m, fig, fr):
    items = m["data"]["items"]
    p, fs, k = fr.p, fr.fs, fr.k
    hero = _hero_id(m)
    vmax = max(i["value"] for i in items)
    ticks = nice_ticks(vmax, integer=all(float(i["value"]).is_integer() for i in items))
    tw = max(text_w(tick_label(t), fs["tick"], mono=True) for t in ticks)
    x0 = fr.plot_left + tw + 10 * max(k, 0.6)
    x1 = fr.plot_right
    top = fr.plot_top + fs["value"] * 1.6 + fr.lane
    base = fr.plot_bottom - fs["label"] * 1.7
    slot = (x1 - x0) / len(items)
    # 类目名放不下就换档：竖柱 → 横条（与 V1「排不下自己换一档」同一个思路）
    for i in items:
        if text_w(str(i["label"]), fs["label"]) > slot * 0.94:
            return "hbar"
        if text_w(_fmt(i["value"]), fs["value"], mono=True, track=fr.track) > slot * 0.98:
            return "hbar"
    scale = (base - top) / ticks[-1]
    for t in ticks:
        y = base - t * scale
        fig.line(x0 - 6 * k, y, x1, y, p["axis"] if t == 0 else p["grid"],
                 1.2 if t == 0 else 0.8,
                 role="axis" if t == 0 else "grid", value=t)
        fig.text(x0 - 10 * max(k, 0.6), y + fs["tick"] * 0.35, tick_label(t), fs["tick"], p["note"],
                 anchor="end", family="mono", role="tick")
    bw = min(slot * 0.56, 110 * k + 20)
    for idx, it in enumerate(items):
        h = it["id"] == hero
        cx = x0 + slot * (idx + 0.5)
        hgt = it["value"] * scale
        fill, stroke, dash = _mark_paint(p, hero=h)
        fig.rect(cx - bw / 2, base - hgt, bw, hgt, fill, stroke, 1, dash, role="bar", id=it["id"],
                 value=it["value"], hero=h, extra={"base": base, "scale": scale})
        _num_text(fig, fr, cx, base - hgt - fs["value"] * 0.5, it["value"], hero=h, role="value", id=it["id"])
        fig.text(cx, base + fs["label"] * 1.3, it["label"], fs["label"], p["accent"] if h else p["ink2"],
                 anchor="middle", weight=700 if h else 400, role="category", id=it["id"], hero=h)
    return None


# =============================================================== hbar
def _label_column(items, fs, maxw, key="label"):
    """类目名一列：最多两行。返回 (列宽, {id: lines})。"""
    widest = max(text_w(str(i[key]), fs) for i in items)
    colw = min(widest, maxw)
    out = {}
    for i in items:
        lines = wrap(str(i[key]), fs, colw)
        if len(lines) > 2:
            raise SpecError(f"类目名「{i[key]}」太长，两行放不下（每行约 {int(colw // fs)} 字）。请删短")
        out[i["id"]] = lines
    return colw, out


def render_hbar(m, fig, fr):
    items = list(m["data"]["items"])
    if m.get("order", "desc") != "given":
        items.sort(key=lambda i: -i["value"])
    p, fs, k = fr.p, fr.fs, fr.k
    hero = _hero_id(m)
    colw, lab = _label_column(items, fs["label"], (fr.plot_right - fr.plot_left) * 0.32)
    vmax = max(i["value"] for i in items)
    ticks = nice_ticks(vmax, integer=all(float(i["value"]).is_integer() for i in items))
    vw = max(text_w(_fmt(i["value"]), fs["value"], mono=True, track=fr.track) for i in items)
    x0 = fr.plot_left + colw + 16 * max(k, 0.6)
    x1 = fr.plot_right - vw - 10
    top = fr.plot_top
    bottom = fr.plot_bottom - fs["tick"] * 1.8
    rowh = (bottom - top) / len(items)
    need = fs["label"] * 1.25 * max(len(v) for v in lab.values()) + 4
    if rowh < need:
        raise SpecError(f"横条太多：{len(items)} 条在这块画布上每条只有 {rowh:.0f}px，类目名需要 {need:.0f}px。"
                        f"请合并长尾为「其他」或换大一档画布")
    scale = (x1 - x0) / ticks[-1]
    for t in ticks:
        x = x0 + t * scale
        fig.line(x, top, x, bottom, p["axis"] if t == 0 else p["grid"],
                 1.2 if t == 0 else 0.8,
                 role="axis" if t == 0 else "grid", value=t)
        fig.text(x, bottom + fs["tick"] * 1.4, tick_label(t), fs["tick"], p["note"], anchor="middle",
                 family="mono", role="tick")
    bh = min(rowh * 0.56, max(40 * k + 8, rowh * 0.42))     # 竖版画布行高大，条也跟着厚一些
    for idx, it in enumerate(items):
        h = it["id"] == hero
        cy = top + rowh * (idx + 0.5)
        w = it["value"] * scale
        fill, stroke, dash = _mark_paint(p, hero=h)
        fig.rect(x0, cy - bh / 2, w, bh, fill, stroke, 1, dash, role="hbar", id=it["id"], value=it["value"],
                 hero=h, extra={"base": x0, "scale": scale})
        _num_text(fig, fr, x0 + w + 8, cy + fs["value"] * 0.35, it["value"], hero=h, anchor="start",
                  role="value", id=it["id"])
        lines = lab[it["id"]]
        y = cy - (len(lines) - 1) * fs["label"] * 0.62 + fs["label"] * 0.35
        for ln in lines:
            fig.text(x0 - 12 * max(k, 0.6), y, ln, fs["label"], p["accent"] if h else p["ink2"], anchor="end",
                     weight=700 if h else 400, role="category", id=it["id"], hero=h)
            y += fs["label"] * 1.25
    return None


# =============================================================== waffle
def render_waffle(m, fig, fr):
    items = m["data"]["items"]
    d = m["_derived"]
    p, fs, k = fr.p, fr.fs, fr.k
    hero = _hero_id(m)
    order = sorted(range(len(items)), key=lambda i: (items[i]["id"] != hero, i))
    dots = d["dots"]
    count_mode = d["waffle_mode"] == "count"
    ph = fr.plot_bottom - fr.plot_top
    pw = fr.plot_right - fr.plot_left
    S = min(ph, pw * 0.5)
    # 件数模式只画实有的件数：12 件就是 12 个点，不画满 100 格（88 个空位读起来像缺了数据）。
    # 百分比模式固定 10 × 10。
    total = sum(dots)
    if count_mode and total < 100:
        cols = max(1, math.ceil(math.sqrt(total)))
        rows = math.ceil(total / cols)
        cell = min(S / max(cols, rows), S / 5)
    else:
        cols, rows, cell = 10, 10, S / 10
    side = cell * 0.74            # 方块模块的边长：格与格之间留约四分之一格的缝
    unit0 = m.get("unit", "") if count_mode else "%"
    legw = fs["label"] * 1.2 + max(max(text_w(str(i["label"]), fs["label"]) for i in items),
                                   max(text_w(_fmt(i["value"]), fs["big"], mono=True, track=fr.track)
                                       + 6 + text_w(unit0, fs["label"]) for i in items))
    lgap = max(28.0, 56 * k)
    # 方阵与图例作为一个整体在绘图区里居中：方阵靠左、右边空一大片，读起来像没排完
    gx = fr.plot_left + max(0.0, (pw - cols * cell - lgap - legw) / 2)
    gy = fr.plot_top + (ph - rows * cell) / 2
    seq = []
    for i in order:
        seq += [i] * dots[i]
    ladder_idx = {}
    nxt = 0
    for i in order:
        if items[i]["id"] != hero:
            ladder_idx[i] = nxt
            nxt += 1
    for j in range(cols * rows if count_mode and total < 100 else 100):
        if count_mode and total < 100 and j >= total:
            break
        cx, cy = gx + (j % cols + 0.5) * cell, gy + (j // cols + 0.5) * cell
        if j < len(seq):
            i = seq[j]
            h = items[i]["id"] == hero
            fill, stroke, dash = _mark_paint(p, None if h else ladder_idx[i], hero=h)
            fig.module(cx, cy, side, fill, stroke, 1, dash, role="dot", id=items[i]["id"], hero=h)
        else:                       # 件数不足 100 时的空位：只画一圈发丝，不冒充数据
            fig.module(cx, cy, side * 0.35, p["grid"], role="empty")
    # 图例：大数字
    lx = gx + cols * cell + lgap
    rows = len(items)
    block = min(ph / rows, fs["big"] * 2.6)
    y = fr.plot_top + (ph - block * rows) / 2 + fs["label"]
    unit = m.get("unit", "")
    for i in order:
        it = items[i]
        h = it["id"] == hero
        fill, stroke, dash = _mark_paint(p, None if h else ladder_idx[i], hero=h)
        fig.module(lx + fs["label"] * 0.4, y - fs["label"] * 0.35, fs["label"] * 0.74, fill, stroke, 1, dash,
                   role="key", id=it["id"], hero=h)
        fig.text(lx + fs["label"] * 1.2, y, it["label"], fs["label"], p["accent"] if h else p["ink2"],
                 weight=700 if h else 400, role="category", id=it["id"], hero=h)
        big = it["value"] if count_mode else it["value"]
        yb = y + fs["big"] * 1.05
        s = _fmt(big)
        fig.text(lx + fs["label"] * 1.2, yb, s, fs["big"], p["accent"] if h else p["ink"], weight=600,
                 family="mono", track=fr.track, role="value", id=it["id"], value=it["value"], hero=h)
        suffix = unit if count_mode else "%"
        if suffix:
            fig.text(lx + fs["label"] * 1.2 + text_w(s, fs["big"], mono=True, track=fr.track) + 6, yb, suffix,
                     fs["label"], p["ink2"], role="unit")
        y += block
    if count_mode:
        return None, f"1 格 = 1 {unit}" if unit else "1 格 = 1 件"
    return None, "1 格 = 1%（最大余数法取整）"


# =============================================================== rose
def _ramp(p, i, n, key="ramp"):
    """由大到小第 i 个（共 n 个）用哪一档灰：一档档变浅。"""
    r = p.get(key) or [p["mark"]]
    return r[0] if n <= 1 else r[int(round(i * (len(r) - 1) / (n - 1)))]


def render_rose(m, fig, fr):
    items = m["data"]["items"]
    p, fs, k = fr.p, fr.fs, fr.k
    hero = _hero_id(m)
    vmax = max(i["value"] for i in items)
    ph = fr.plot_bottom - fr.plot_top
    pw = fr.plot_right - fr.plot_left
    labw = max(max(text_w(str(i["label"]), fs["label"]) for i in items),
               max(text_w(_fmt(i["value"]), fs["value"], mono=True) for i in items))
    gap = 10 * max(k, 0.7)
    R = min(ph / 2 - fs["label"] * 2.4 - gap, pw / 2 - labw - gap * 2)
    if R < 70:
        raise SpecError("玫瑰图在这块画布上半径不足 70px：类目名太长或画布太小。请删短类目名或换大一档画布")
    cx = fr.plot_left + pw / 2
    cy = fr.plot_top + ph / 2
    n = len(items)
    step = 2 * math.pi / n
    rings = [t for t in nice_ticks(vmax, 4) if 0 < t <= vmax]
    for t in rings:
        rr = R * math.sqrt(t / vmax)
        fig.circle(cx, cy, rr, None, p["grid"], 0.8, role="ring", value=t)
    sep = p["paper"]
    for idx, it in enumerate(items):
        h = it["id"] == hero
        a0 = -math.pi / 2 + idx * step
        a1 = a0 + step
        r = R * math.sqrt(it["value"] / vmax)
        seg = max(6, int(math.degrees(step) / 3))
        pts = [(cx, cy)] + [(cx + r * math.cos(a0 + (a1 - a0) * s / seg), cy + r * math.sin(a0 + (a1 - a0) * s / seg))
                            for s in range(seg + 1)]
        fill = p["accent"] if h else p["mark"]
        fig.poly(pts, fill, sep, max(1.0, 2.0 * k), role="sector", id=it["id"],
                 value=it["value"], hero=h, extra={"cx": cx, "cy": cy, "r": r, "rmax": R, "vmax": vmax})
    for idx, it in enumerate(items):
        h = it["id"] == hero
        am = -math.pi / 2 + (idx + 0.5) * step
        rr = R + gap
        x, y = cx + rr * math.cos(am), cy + rr * math.sin(am)
        c, s = math.cos(am), math.sin(am)
        anchor = "start" if c > 0.25 else ("end" if c < -0.25 else "middle")
        dy = fs["label"] * (1.6 if s > 0.5 else (-0.5 if s < -0.5 else 0.5))
        fig.text(x, y + dy - fs["label"] * 0.55, it["label"], fs["label"], p["accent"] if h else p["ink2"],
                 anchor=anchor, weight=700 if h else 400, role="category", id=it["id"], hero=h)
        _num_text(fig, fr, x, y + dy + fs["value"] * 0.75, it["value"], hero=h, anchor=anchor, role="value",
                  id=it["id"])
    if rings:
        key = "圈：" + " / ".join(tick_label(t) for t in rings) + (" " + m.get("unit", "") if m.get("unit") else "")
        fig.text(fr.plot_left, fr.plot_bottom, key, fs["tick"], p["note"], role="key")
    unit = m.get("unit") or "数值"
    return None, f"半径 ∝ √{unit}，面积即{unit}"


# =============================================================== dumbbell
def render_dumbbell(m, fig, fr):
    data = m["data"]
    items = data["items"]
    p, fs, k = fr.p, fr.fs, fr.k
    hero = _hero_id(m)
    colw, lab = _label_column(items, fs["label"], (fr.plot_right - fr.plot_left) * 0.24)
    vmax = max(max(i["from"], i["to"]) for i in items)
    ticks = nice_ticks(vmax)
    vw = max(text_w(_fmt(v), fs["value"], mono=True, track=fr.track)
             for i in items for v in (i["from"], i["to"]))
    x0 = fr.plot_left + colw + 18 * max(k, 0.6) + vw + 12
    x1 = fr.plot_right - vw - 14
    top = fr.plot_top
    bottom = fr.plot_bottom - fs["tick"] * 1.8
    rowh = (bottom - top) / len(items)
    if rowh < fs["label"] * 1.25 * max(len(v) for v in lab.values()) + 4:
        raise SpecError("哑铃图行数太多，这块画布放不下；请减少行数或换大一档画布")
    scale = (x1 - x0) / ticks[-1]
    for t in ticks:
        x = x0 + t * scale
        fig.line(x, top, x, bottom, p["grid"], 0.8, role="grid", value=t)
        fig.text(x, bottom + fs["tick"] * 1.4, tick_label(t), fs["tick"], p["note"], anchor="middle",
                 family="mono", role="tick")
    rdot = max(4.5, 7.0 * k)
    for idx, it in enumerate(items):
        h = it["id"] == hero
        cy = top + rowh * (idx + 0.5)
        xa, xb = x0 + it["from"] * scale, x0 + it["to"] * scale
        col = p["accent"] if h else p["ink2"]
        fig.line(min(xa, xb), cy, max(xa, xb), cy, col, (3.0 if h else 1.6) * max(k, 0.7), role="span",
                 id=it["id"], hero=h)
        fig.circle(xa, cy, rdot, p["paper"], col, 1.8 * max(k, 0.7), role="from", id=it["id"],
                   value=it["from"], hero=h, extra={"x0": x0, "scale": scale})
        fig.circle(xb, cy, rdot, col, None, role="to", id=it["id"], value=it["to"], hero=h,
                   extra={"x0": x0, "scale": scale})
        lo, hi = (it["from"], xa), (it["to"], xb)
        if xb < xa:
            lo, hi = hi, lo
        _num_text(fig, fr, lo[1] - rdot - 6, cy + fs["value"] * 0.35, lo[0], hero=h, anchor="end",
                  role="value", id=it["id"])
        _num_text(fig, fr, hi[1] + rdot + 6, cy + fs["value"] * 0.35, hi[0], hero=h, anchor="start",
                  role="value", id=it["id"])
        lines = lab[it["id"]]
        y = cy - (len(lines) - 1) * fs["label"] * 0.62 + fs["label"] * 0.35
        for ln in lines:
            fig.text(fr.plot_left, y, ln, fs["label"], p["accent"] if h else p["ink2"],
                     weight=700 if h else 400, role="category", id=it["id"], hero=h)
            y += fs["label"] * 1.25
    unit = m.get("unit", "")
    return None, f"{data['from_label']} ○ → {data['to_label']} ●" + (f" · {unit}" if unit else "")


# =============================================================== strip
def render_strip(m, fig, fr):
    data = m["data"]
    groups = data["groups"]
    th = data.get("threshold")
    st = m["_derived"]["stats"]
    p, fs, k = fr.p, fr.fs, fr.k
    hero = _hero_id(m)
    colw, lab = _label_column(groups, fs["label"], (fr.plot_right - fr.plot_left) * 0.22)
    vmax = max(max(g["values"]) for g in groups)
    if th:
        vmax = max(vmax, th["value"])
    ticks = nice_ticks(vmax)
    x0 = fr.plot_left + colw + 24 * max(k, 0.6)
    x1 = fr.plot_right - 8
    top = fr.plot_top + (fs["tick"] * 1.8 if th else 0)
    bottom = fr.plot_bottom - fs["tick"] * 1.8
    rowh = (bottom - top) / len(groups)
    scale = (x1 - x0) / ticks[-1]
    for t in ticks:
        x = x0 + t * scale
        fig.line(x, top, x, bottom, p["grid"], 0.8, role="grid", value=t)
        fig.text(x, bottom + fs["tick"] * 1.4, tick_label(t), fs["tick"], p["note"], anchor="middle",
                 family="mono", role="tick")
    if m.get("unit"):
        fig.text(x1, bottom + fs["tick"] * 2.9, m["unit"], fs["tick"], p["note"], anchor="end", role="tick")
    if th:
        xt = x0 + th["value"] * scale
        fig.line(xt, top - fs["tick"] * 0.6, xt, bottom, p["ink2"], 1.2 * max(k, 0.7), dash="6 4",
                 role="threshold", value=th["value"])
        fig.text(xt + 5, top - fs["tick"] * 0.9, f"{th['label']} · {_fmt(th['value'])}", fs["tick"], p["ink2"],
                 role="threshold-label")
    r = max(2.6, 4.0 * k)
    for gi, g in enumerate(groups):
        cy = top + rowh * (gi + 0.5)
        band = rowh * 0.26
        gh = g["id"] == hero
        for j, v in enumerate(g["values"]):
            h = gh and th is not None and v > th["value"]
            yj = cy + (jitter(g["id"], j) - 0.5) * 2 * band
            if h:
                fig.circle(x0 + v * scale, yj, r, p["accent"], role="point", id=g["id"], value=v, hero=True,
                           extra={"x0": x0, "scale": scale})
            else:
                fig.circle(x0 + v * scale, yj, r, p["mark"], role="point", id=g["id"], value=v,
                           extra={"x0": x0, "scale": scale})
        md = st[g["id"]]["median"]
        mh = gh and th is None
        xm = x0 + md * scale
        fig.line(xm, cy - band - r - 4, xm, cy + band + r + 4, p["accent"] if mh else p["rail"],
                 max(2.0, 3.0 * k), square=True, role="median", id=g["id"], value=md, hero=mh)
        _num_text(fig, fr, xm, cy - band - r - 8, md, hero=mh, role="value", id=g["id"])
        lines = lab[g["id"]]
        y = cy - (len(lines) - 1) * fs["label"] * 0.62 + fs["label"] * 0.35
        for ln in lines:
            fig.text(fr.plot_left, y, ln, fs["label"], p["accent"] if gh else p["ink2"],
                     weight=700 if gh else 400, role="category", id=g["id"], hero=gh and (th is not None or mh))
            y += fs["label"] * 1.25
    return None, "1 点 = 1 件 · 竖线为中位数"


# =============================================================== sankey
def _bezier(p0, p1, steps=24):
    (x0, y0), (x1, y1) = p0, p1
    xm = (x0 + x1) / 2
    out = []
    for s in range(steps + 1):
        t = s / steps
        a, b, c, d = (1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t ** 2, t ** 3
        out.append((a * x0 + b * xm + c * xm + d * x1, a * y0 + b * y0 + c * y1 + d * y1))
    return out


def render_sankey(m, fig, fr):
    data = m["data"]
    nodes, links = data["nodes"], data["links"]
    val = m["_derived"]["node_value"]
    p, fs, k = fr.p, fr.fs, fr.k
    hero = _hero_id(m)
    stages = sorted({n["stage"] for n in nodes})
    by_stage = {s: [n for n in nodes if n["stage"] == s] for s in stages}
    lw0 = max(max(text_w(str(n["label"]), fs["label"]), text_w(_fmt(val[n["id"]]), fs["value"], mono=True))
              for n in by_stage[0])
    lwl = max(max(text_w(str(n["label"]), fs["label"]), text_w(_fmt(val[n["id"]]), fs["value"], mono=True))
              for n in by_stage[stages[-1]])
    nw = max(8.0, 12.0 * k)
    xl = fr.plot_left + lw0 + 12
    xr = fr.plot_right - lwl - 12 - nw
    xs = {s: xl + (xr - xl) * i / (len(stages) - 1) for i, s in enumerate(stages)}
    top, bottom = fr.plot_top, fr.plot_bottom
    gap = max(10.0, 18.0 * k)
    scale = min((bottom - top - gap * (len(by_stage[s]) - 1)) / xsum(val[n["id"]] for n in by_stage[s])
                for s in stages)
    # 每一段从「它的第一股来流在上游的位置」开始往下排，而不是一律贴顶：
    # 贴顶时下游节点会高高挂在上方，流带从来源处大幅上扬，读起来像数据在变。
    pos = {}
    order0 = {n["id"]: i for i, n in enumerate(nodes)}
    for s in stages:
        stack = xsum(val[n["id"]] * scale for n in by_stage[s]) + gap * (len(by_stage[s]) - 1)
        start = top
        if s > stages[0]:
            mine = {n["id"] for n in by_stage[s]}
            cands = []
            for src in by_stage[s - 1]:
                off = pos[src["id"]][0]
                for l in sorted((l for l in links if l["from"] == src["id"]), key=lambda l: order0[l["to"]]):
                    if l["to"] in mine:
                        cands.append(off)
                        break
                    off += l["value"] * scale
            start = min(min(cands) if cands else top, bottom - stack)
        y = max(top, start)
        for n in by_stage[s]:
            h = val[n["id"]] * scale
            pos[n["id"]] = [y, h]
            y += h + gap
    order = {n["id"]: i for i, n in enumerate(nodes)}
    out_off = {n["id"]: pos[n["id"]][0] for n in nodes}
    in_off = {n["id"]: pos[n["id"]][0] for n in nodes}
    hero_in = {l["from"] + ">" + l["to"] for l in links if l["to"] == hero}
    for l in sorted(links, key=lambda l: (order[l["from"]], order[l["to"]])):
        h = l["value"] * scale
        a, b = l["from"], l["to"]
        sa = [n for n in nodes if n["id"] == a][0]["stage"]
        xa, xb = xs[sa] + nw, xs[sa + 1]
        ya, yb = out_off[a], in_off[b]
        out_off[a] += h
        in_off[b] += h
        upper = _bezier((xa, ya), (xb, yb))
        lower = _bezier((xb, yb + h), (xa, ya + h))
        lid = a + ">" + b
        hh = lid in hero_in
        if hh:
            fill, stroke = p["accent"], None
        else:
            fill, stroke = p["flow"], None
        ex = {"h": h, "scale": scale}
        if hh:
            ex["hero-of"] = hero          # 流向重音节点的那条带属于同一个数据，不算第二处重音
        fig.poly(upper + lower, fill, stroke, 0.6, role="flow", id=lid, value=l["value"], hero=hh, extra=ex,
                 square=True)
    for n in nodes:
        h = n["id"] == hero
        y, hh = pos[n["id"]]
        s = n["stage"]
        fig.rect(xs[s], y, nw, hh, p["accent"] if h else p["rail"], square=True, role="node", id=n["id"],
                 value=val[n["id"]], hero=h, extra={"scale": scale})
        cyn = y + hh / 2
        if s == stages[0]:
            x, anchor = xs[s] - 8, "end"
        else:
            x, anchor = xs[s] + nw + 8, "start"
        fig.text(x, cyn - 2, n["label"], fs["label"], p["accent"] if h else p["ink2"], anchor=anchor,
                 weight=700 if h else 400, role="category", id=n["id"], hero=h)
        _num_text(fig, fr, x, cyn + fs["value"] * 1.0, val[n["id"]], hero=h, anchor=anchor, role="value",
                  id=n["id"])
    return None, "带宽 = 件数"


# =============================================================== waterfall（逐级加减）
def render_waterfall(m, fig, fr):
    """从一个数出发，一级级加减，落到另一个数。金额拆解、清偿顺位、样本筛选都用它。

    起点与终点是实柱（从 0 起）；中间各级是悬浮柱，上下沿就是加减前后的累计。
    相邻两柱之间一条细虚线接住累计值，读者顺着线就能一路算下去。"""
    data = m["data"]
    st, steps, end = data["start"], data["steps"], data["end"]
    runs = m["_derived"]["runs"]
    p, fs, k = fr.p, fr.fs, fr.k
    hero = _hero_id(m)
    cols = [("start", st["label"], st["value"], 0.0, st["value"], True)]
    for i, s in enumerate(steps):
        cols.append((s["id"], s["label"], s["value"], runs[i], runs[i + 1], False))
    cols.append(("end", end["label"], end["value"], 0.0, end["value"], True))
    vmax = max(max(runs), st["value"], end["value"])
    ticks = nice_ticks(vmax, integer=all(float(r).is_integer() for r in runs))
    tw = max(text_w(tick_label(t), fs["tick"], mono=True) for t in ticks)
    x0 = fr.plot_left + tw + 10 * max(k, 0.6)
    x1 = fr.plot_right
    slot = (x1 - x0) / len(cols)
    lab_lines = {}
    for c in cols:
        lines = wrap(str(c[1]), fs["label"], slot * 0.92)
        if len(lines) > 2:
            raise SpecError(f"「{c[1]}」在柱宽里两行放不下（每行约 {int(slot * 0.92 // fs['label'])} 字）。"
                            + ("批注栏占去了约四分之一的宽度：可去掉批注、或换横版画布；" if m.get("annotations") else "")
                            + "请删短，或减少级数")
        lab_lines[c[0]] = lines
    nlab = max(len(v) for v in lab_lines.values())
    top = fr.plot_top + fs["value"] * 1.6 + fr.lane
    base = fr.plot_bottom - fs["label"] * (0.6 + 1.25 * nlab)
    scale = (base - top) / ticks[-1]
    for t in ticks:
        y = base - t * scale
        fig.line(x0 - 6 * k, y, x1, y, p["axis"] if t == 0 else p["grid"], 1.2 if t == 0 else 0.8,
                 role="axis" if t == 0 else "grid", value=t)
        fig.text(x0 - 10 * max(k, 0.6), y + fs["tick"] * 0.35, tick_label(t), fs["tick"], p["note"],
                 anchor="end", family="mono", role="tick")
    bw = min(slot * 0.58, 120 * k + 20)
    prev = None
    unit = m.get("unit", "")
    for i, (cid, label, v, a, b, total) in enumerate(cols):
        h = cid == hero
        cx = x0 + slot * (i + 0.5)
        lo, hi = min(a, b), max(a, b)
        y_top, y_bot = base - hi * scale, base - lo * scale
        if h:
            fill = p["accent"]
        elif total:
            fill = p["rail"]
        else:
            fill = p["mark"]
        fig.rect(cx - bw / 2, y_top, bw, max(0.01, y_bot - y_top), fill, role="total" if total else "step",
                 id=cid, value=v, hero=h, extra={"from": a, "to": b, "base": base})
        if prev is not None:                                   # 累计值接线
            fig.line(prev, base - a * scale if not total else base - b * scale, cx - bw / 2,
                     base - a * scale if not total else base - b * scale, p["ink2"], 0.8, dash="2 3",
                     role="link")
        prev = cx + bw / 2
        s = (_fmt(v) if total else (("+" if v > 0 else "−") + _fmt(abs(v))))
        fig.text(cx, y_top - fs["value"] * 0.5, s, fs["value"], p["accent"] if h else p["ink"], anchor="middle",
                 weight=600 if h else 500, family="mono", track=fr.track, role="value", id=cid, hero=h)
        y = base + fs["label"] * 1.3
        for ln in lab_lines[cid]:
            fig.text(cx, y, ln, fs["label"], p["accent"] if h else p["ink2"], anchor="middle",
                     weight=700 if h else 400, role="category", id=cid, hero=h)
            y += fs["label"] * 1.25
    return None, f"起点与终点为实柱，中间各级为加减{f' · {unit}' if unit else ''}"


# =============================================================== ribbon（汇入图）
def render_ribbon(m, fig, fr):
    """几个来源汇入几个去处。与桑基的区别：只有两列，流带可以交叉，交叉处半透明叠深。

    学自「四源汇入五宿」一类的二部流带图：流带细描边、半透明；重点那一组描重音色边、
    中间走一条虚线标出流向。法律上最常用的是资金流向：几个付款账户汇入几个收款账户。"""
    data = m["data"]
    srcs, tgts, links = data["sources"], data["targets"], data["links"]
    val = m["_derived"]["node_value"]
    p, fs, k = fr.p, fr.fs, fr.k
    hero = _hero_id(m)

    def side_w(arr):
        return max(max(text_w(str(n["label"]), fs["label"]),
                       text_w(_fmt(val[n["id"]]), fs["value"], mono=True, track=fr.track)) for n in arr)
    nw = max(5.0, 7.0 * k)
    xl = fr.plot_left + side_w(srcs) + 14
    xr = fr.plot_right - side_w(tgts) - 14 - nw
    top, bottom = fr.plot_top, fr.plot_bottom
    gap = max(12.0, 22.0 * k)
    total = xsum(l["value"] for l in links)
    scale = min((bottom - top - gap * (len(srcs) - 1)) / total, (bottom - top - gap * (len(tgts) - 1)) / total)
    pos = {}
    for arr, x in ((srcs, xl), (tgts, xr)):
        stack = total * scale + gap * (len(arr) - 1)
        y = top + (bottom - top - stack) / 2
        for n in arr:
            h = val[n["id"]] * scale
            pos[n["id"]] = (x, y, h)
            y += h + gap
    si = {n["id"]: i for i, n in enumerate(srcs)}
    ti = {n["id"]: i for i, n in enumerate(tgts)}
    out_off = {n["id"]: pos[n["id"]][1] for n in srcs}
    in_off = {n["id"]: pos[n["id"]][1] for n in tgts}
    bands = []
    for l in sorted(links, key=lambda l: (si[l["from"]], ti[l["to"]])):
        h = l["value"] * scale
        ya = out_off[l["from"]]
        out_off[l["from"]] += h
        bands.append([l, ya, h, None])
    for b in sorted(bands, key=lambda b: (ti[b[0]["to"]], si[b[0]["from"]])):
        b[3] = in_off[b[0]["to"]]
        in_off[b[0]["to"]] += b[2]
    xa, xb = xl + nw, xr
    # 普通流带先画，重点流带后画、压在最上面
    bands.sort(key=lambda b: hero in (b[0]["from"], b[0]["to"]))
    for l, ya, h, yb in bands:
        hh = hero is not None and hero in (l["from"], l["to"])
        upper = _bezier((xa, ya), (xb, yb))
        lower = _bezier((xb, yb + h), (xa, ya + h))
        ex = {"h": h, "scale": scale}
        if hh:
            ex["hero-of"] = hero
            fig.poly(upper + lower, p["accent"], p["accent"], max(1.0, 1.6 * k), opacity=0.16, square=True, role="flow",
                     id=f'{l["from"]}>{l["to"]}', value=l["value"], hero=True, extra=ex)
            fig.curve((xa, ya + h / 2), (xb, yb + h / 2), p["accent"], max(1.0, 1.6 * k), dash="1.5 5",
                      role="flowline", id=f'{l["from"]}>{l["to"]}', hero=True, extra={"hero-of": hero})
        else:
            fig.poly(upper + lower, p["mark"], p["mark"], max(0.6, 0.9 * k), opacity=0.24, square=True, role="flow",
                     id=f'{l["from"]}>{l["to"]}', value=l["value"], extra=ex)
    for arr, left in ((srcs, True), (tgts, False)):
        for n in arr:
            x, y, h = pos[n["id"]]
            hn = n["id"] == hero
            fig.rect(x, y, nw, h, p["accent"] if hn else p["rail"], square=True, role="node", id=n["id"],
                     value=val[n["id"]], hero=hn, extra={"scale": scale})
            cy = y + h / 2
            tx, anchor = (x - 8, "end") if left else (x + nw + 8, "start")
            fig.text(tx, cy - 2, n["label"], fs["label"], p["accent"] if hn else p["ink2"], anchor=anchor,
                     weight=700 if hn else 400, role="category", id=n["id"], hero=hn)
            _num_text(fig, fr, tx, cy + fs["value"] * 1.0, val[n["id"]], hero=hn, anchor=anchor, role="value",
                      id=n["id"])
    unit = m.get("unit") or "数量"
    return None, f"带宽 = {unit}"


# =============================================================== 0.10.0 · 四种新画法
# 学自「一页年鉴」一类的编辑型信息图（发射扇、放射汇聚、气泡年鉴、漏斗），只借图形，
# 不借配色：颜色仍是风格原色（灰阶 + 唯一重音），不透明、不渐变（作者定的，守 ADR 0010）。
# 每一种的「那条线」：漏斗条宽 ∝ 件数；气泡、端点圆、枢纽的面积 ∝ 数值（半径取平方根）；
# 辐条长 ∝ 数值。守卫从产物回读这几样，比值不一致就拒。

def _fit_lines(text, fs, width, what, maxl=2):
    lines = wrap(str(text), fs, width)
    if len(lines) > maxl:
        raise SpecError(f"{what}「{text}」在 {width:.0f}px 里 {maxl} 行放不下（每行约 {int(width // fs)} 字）。请删短")
    return lines


def _boxes_clash(boxes, pad=1.0):
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            if _overlap(boxes[i][0], boxes[j][0], pad):
                return boxes[i][1], boxes[j][1]
    return None


def _tbox(x, y, s, fs, anchor="start", mono=False, track=0.0):
    """与守卫 G4 同一把尺子量文字外框（等宽数字、字距都算进去）。"""
    w = text_w(str(s), fs, mono=mono, track=track)
    x0 = x - w / 2 if anchor == "middle" else (x - w if anchor == "end" else x)
    return (x0, y - fs * 0.88, x0 + w, y + fs * 0.17)


# --------------------------------------------------------------- funnel（漏斗）
def render_funnel(m, fig, fr):
    """一级比一级少：线索 → 立案 → 起诉 → 判决 → 执行到位。条宽 ∝ 件数，居中对齐；
    两级之间的浅灰梯形只是把上下两条接起来，读者顺着它看收窄，不承载数值。"""
    stages = m["data"]["stages"]
    p, fs, k = fr.p, fr.fs, fr.k
    hero = _hero_id(m)
    first = stages[0]["value"]
    colw, lab = _label_column(stages, fs["label"], (fr.plot_right - fr.plot_left) * 0.24)
    unit = m.get("unit", "")
    right = {}
    for s in stages:
        pct = s["value"] / first * 100
        right[s["id"]] = (_fmt(s["value"]) + (f" {unit}" if unit else ""),
                          "" if s is stages[0] else f"占第一级 {_fmt(round(pct, 1))}%")
    rw = max(max(text_w(a, fs["value"], mono=True, track=fr.track), text_w(b, fs["tick"]))
             for a, b in right.values())
    gap = 16 * max(k, 0.6)
    x0 = fr.plot_left + colw + gap
    x1 = fr.plot_right - rw - gap
    if x1 - x0 < 160:
        raise SpecError("漏斗在这块画布上条宽不足 160px：类目名太长或画布太小。请删短类目名或换大一档画布")
    cx = (x0 + x1) / 2
    scale = (x1 - x0) / first
    top, bottom = fr.plot_top, fr.plot_bottom
    rowh = (bottom - top) / len(stages)
    need = fs["label"] * 1.25 * max(len(v) for v in lab.values()) + 4
    if rowh < max(need, fs["value"] + fs["tick"] * 1.4):
        raise SpecError(f"漏斗 {len(stages)} 级在这块画布上每级只有 {rowh:.0f}px 高，放不下。请减少级数或换大一档画布")
    bh = min(rowh * 0.58, 64 * k + 10)
    ys = [top + rowh * (i + 0.5) - bh / 2 for i in range(len(stages))]
    for i in range(len(stages) - 1):                       # 两级之间的收窄：先画，压在条下面
        wa, wb = stages[i]["value"] * scale, stages[i + 1]["value"] * scale
        ya, yb = ys[i] + bh, ys[i + 1]
        if yb - ya > 1.0:
            # 收窄带与桑基、汇入图的流带同属「流」：两种风格下都是直角（G9 长条规则）
            fig.poly([(cx - wa / 2, ya), (cx + wa / 2, ya), (cx + wb / 2, yb), (cx - wb / 2, yb)],
                     p["flow"], role="flow", square=True)
    for i, s in enumerate(stages):
        h = s["id"] == hero
        w = s["value"] * scale
        fill, stroke, dash = _mark_paint(p, hero=h)
        fig.rect(cx - w / 2, ys[i], w, bh, fill, stroke, 1, dash, role="stage", id=s["id"], value=s["value"],
                 hero=h, extra={"cx": cx, "scale": scale})
        cy = ys[i] + bh / 2
        lines = lab[s["id"]]
        y = cy - (len(lines) - 1) * fs["label"] * 0.62 + fs["label"] * 0.35
        for ln in lines:
            fig.text(x0 - gap * 0.75, y, ln, fs["label"], p["accent"] if h else p["ink2"], anchor="end",
                     weight=700 if h else 400, role="category", id=s["id"], hero=h)
            y += fs["label"] * 1.25
        a, b = right[s["id"]]
        yv = cy + (fs["value"] * 0.35 if not b else -fs["tick"] * 0.25)
        fig.text(x1 + gap, yv, a, fs["value"], p["accent"] if h else p["ink"], weight=600 if h else 500,
                 family="mono", track=fr.track, role="value", id=s["id"], hero=h)
        if b:
            fig.text(x1 + gap, yv + fs["tick"] * 1.3, b, fs["tick"], p["note"], role="share", id=s["id"])
    return None, f"条宽 = {unit or '件数'} · 百分比为占第一级的比例"


# --------------------------------------------------------------- matrix（气泡矩阵 / 气泡年鉴）
def _pebble(cx, cy, r, key, fig_corner):
    """奇川风的「手作」气泡：十个顶点的卵石形，角全部磨成贝塞尔圆弧，然后**整体缩放到面积恰好 πr²**。
    形状由类目名哈希决定（同一份说明永远同一个形状）；面积由数值决定，读数不受形状影响。"""
    from corners import rounded_d, flatten, area
    n = 10
    pts = []
    for i in range(n):
        a = 2 * math.pi * (i + 0.35 * (jitter(key, "a", i) - 0.5)) / n
        rr = 1.0 + 0.16 * (jitter(key, "r", i) - 0.5)
        pts.append((math.cos(a) * rr, math.sin(a) * rr))
    # 单位尺寸上算面积再缩放：圆角半径随形状一起缩放，面积严格按平方变化
    unit = [(x * 100, y * 100) for x, y in pts]
    a0 = area(flatten(rounded_d(unit, 100.0)))
    s = math.sqrt(math.pi * r * r / a0) * 100
    return rounded_d([(cx + x * s, cy + y * s) for x, y in pts], s)


def render_matrix(m, fig, fr):
    """行 × 列，每格一个气泡，面积 ∝ 数值。法律上最常用：历年 × 案由的收案、各法院 × 结果的件数。
    右边一列是行合计，下边一行是列合计——由脚本算，不由人写。虚线圈表示这一格的口径不完整（试行期等）。"""
    data = m["data"]
    rows, cols, cells = data["rows"], data["cols"], data["cells"]
    d = m["_derived"]
    val, rt, ct = d["cell"], d["row_total"], d["col_total"]
    status = {(c["row"], c["col"]): c.get("status") for c in cells}
    p, fs, k = fr.p, fr.fs, fr.k
    hero = _hero_id(m)
    lfs = fs["label"]
    colw_l, rlab = _label_column(rows, lfs, (fr.plot_right - fr.plot_left) * 0.18)
    tot_w = max([text_w(_fmt(v), fs["value"], mono=True, track=fr.track) for v in rt.values()]
                + [text_w("合计", fs["tick"])])
    gap = 14 * max(k, 0.6)
    x0 = fr.plot_left + colw_l + gap
    x1 = fr.plot_right - tot_w - gap * 1.6
    cw = (x1 - x0) / len(cols)
    clab = {c["id"]: _fit_lines(c["label"], lfs * 0.9 if lfs * 0.9 >= FLOOR else lfs, cw * 0.94, "列名")
            for c in cols}
    cfs = lfs * 0.9 if lfs * 0.9 >= FLOOR else lfs
    nl = max(len(v) for v in clab.values())
    y0 = fr.plot_top + cfs * 1.25 * nl + gap * 0.6
    y1 = fr.plot_bottom - fs["value"] * 1.9
    ch = (y1 - y0) / len(rows)
    if ch < max(lfs * 1.25 * max(len(v) for v in rlab.values()) + 2, 18) or cw < 18:
        raise SpecError(f"气泡矩阵 {len(rows)} 行 × {len(cols)} 列在这块画布上每格只有 {cw:.0f}×{ch:.0f}px，"
                        f"放不下。请减少行列、合并长尾为「其他」，或换大一档画布")
    vmax = max(val.values())
    R = 0.46 * min(cw, ch)
    qichuan = fr.corner > 0
    def heroic(rid, cid):
        return hero is not None and hero in (rid, cid)
    # 列名
    for j, c in enumerate(cols):
        h = c["id"] == hero
        x = x0 + cw * (j + 0.5)
        y = fr.plot_top + cfs * 0.9
        for ln in clab[c["id"]]:
            fig.text(x, y, ln, cfs, p["accent"] if h else p["ink2"], anchor="middle", weight=700 if h else 400,
                     role="category", id=c["id"], hero=h)
            y += cfs * 1.25
    fig.text(x1 + gap * 1.6 + tot_w, fr.plot_top + cfs * 0.9, "合计", fs["tick"], p["note"], anchor="end", role="tick")
    for i, r_ in enumerate(rows):
        h = r_["id"] == hero
        cy = y0 + ch * (i + 0.5)
        fig.line(x0, cy, x1, cy, p["grid"], 0.8, role="grid")
        lines = rlab[r_["id"]]
        y = cy - (len(lines) - 1) * lfs * 0.62 + lfs * 0.35
        for ln in lines:
            fig.text(x0 - gap, y, ln, lfs, p["accent"] if h else p["ink2"], anchor="end", weight=700 if h else 400,
                     role="category", id=r_["id"], hero=h)
            y += lfs * 1.25
        fig.text(x1 + gap * 1.6 + tot_w, cy + fs["value"] * 0.35, _fmt(rt[r_["id"]]), fs["value"],
                 p["accent"] if h else p["ink"], anchor="end", weight=600 if h else 500, family="mono",
                 track=fr.track, role="total", id=r_["id"], hero=h)
        for j, c in enumerate(cols):
            v = val.get((r_["id"], c["id"]))
            if not v:
                continue
            x = x0 + cw * (j + 0.5)
            rr = R * math.sqrt(v / vmax)
            hh = heroic(r_["id"], c["id"])
            cid = f"{r_['id']}|{c['id']}"
            ex = {"row": r_["id"], "col": c["id"], "vmax": vmax, "rmax": R}
            if hh:
                ex["hero-of"] = hero
            if status.get((r_["id"], c["id"])) == "dashed":
                fig.circle(x, cy, rr, None, p["accent"] if hh else p["ink2"], max(1.0, 1.3 * k), dash="3 3",
                           role="bubble", id=cid, value=v, hero=hh, extra=ex)
            elif qichuan and rr >= 7:
                fill = p["accent"] if hh else p["mark"]
                fig.parts.append(f'<path d="{_pebble(x, cy, rr, cid, fr.corner)}" fill="{fill}"'
                                 f'{fig._meta(role="bubble", id=cid, value=v, hero=hh, extra=dict(ex, cx=x, cy=cy))}/>')
            else:
                fig.circle(x, cy, rr, p["accent"] if hh else p["mark"], role="bubble", id=cid, value=v, hero=hh,
                           extra=ex)
            s = _fmt(v)
            vfs = fs["tick"]
            if 2 * rr >= text_w(s, vfs, mono=True) + 6 and 2 * rr >= vfs * 1.3:
                dashed = status.get((r_["id"], c["id"])) == "dashed"
                col = p["ink2"] if dashed else (p["on_accent"] if hh else p["ink"])
                # data-bg：这个数是压在气泡上的，对比度要按气泡的颜色核，不按纸色（回归里的对比度检查读它）
                bg = p["paper"] if dashed else (p["accent"] if hh else p["mark"])
                ex2 = {"bg": bg}
                if hh and not dashed:
                    ex2["hero-of"] = hero
                fig.text(x, cy + vfs * 0.35, s, vfs, col, anchor="middle", family="mono", role="value", id=cid,
                         hero=hh and not dashed, extra=ex2)
    # 列合计：放不下就退一档字号（不小于 11px），还放不下就明说
    tfs_ = fs["value"]
    widest = max(text_w(_fmt(v), tfs_, mono=True, track=fr.track) for v in ct.values())
    if widest > cw * 0.92:
        tfs_ = max(FLOOR, fs["tick"])
        widest = max(text_w(_fmt(v), tfs_, mono=True, track=fr.track) for v in ct.values())
    if widest > cw * 0.92:
        raise SpecError(f"气泡矩阵的列合计（最宽「{_fmt(max(ct.values()))}」）在每列 {cw:.0f}px 里放不下。"
                        f"请减少列数、换大一档画布，或把单位换大一级（元 → 万元）")
    yb = fr.plot_bottom - fs["value"] * 0.45
    fig.line(x0, y1 + gap * 0.2, x1, y1 + gap * 0.2, p["axis"], 0.8, role="rule")
    fig.text(x0 - gap, yb, "合计", fs["tick"], p["note"], anchor="end", role="tick")
    for j, c in enumerate(cols):
        h = c["id"] == hero
        fig.text(x0 + cw * (j + 0.5), yb, _fmt(ct[c["id"]]), tfs_, p["accent"] if h else p["ink"],
                 anchor="middle", weight=600 if h else 500, family="mono", track=fr.track, role="total",
                 id=c["id"], hero=h)
    enc = "气泡面积 = 数值 · 空格 = 0 · 右列与末行为合计"
    if any(st == "dashed" for st in status.values()):
        enc += f" · 虚线圈 = {data['dashed_label']}"
    return None, enc


# --------------------------------------------------------------- fan（发射扇）
def _seg_poly(px, py, a, L, th):
    """从 (px, py) 沿角 a 伸出 L、骑在这条线上、厚 th 的长条：顺着辐条写的标签所占的地方。"""
    c, s_ = math.cos(a), math.sin(a)
    nx, ny = -s_ * th * 0.53, c * th * 0.53
    return [(px - nx, py - ny), (px + c * L - nx, py + s_ * L - ny), (px + c * L + nx, py + s_ * L + ny),
            (px + nx, py + ny)]


def _sat(pa, pb, pad=0.0):
    for poly in (pa, pb):
        for i in range(len(poly)):
            (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % len(poly)]
            ax, ay = y1 - y2, x2 - x1
            L = math.hypot(ax, ay) or 1.0
            A = [(px * ax + py * ay) / L for px, py in pa]
            B = [(px * ax + py * ay) / L for px, py in pb]
            if max(A) + pad <= min(B) or max(B) + pad <= min(A):
                return False
    return True


def _circle_hits_poly(cx, cy, r, poly):
    """圆与凸多边形是否相交（圆心到各边的最近距离 < r，或圆心在多边形内）。"""
    inside = True
    n = len(poly)
    for i in range(n):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % n]
        dx, dy = x2 - x1, y2 - y1
        L2 = dx * dx + dy * dy or 1e-9
        t = max(0.0, min(1.0, ((cx - x1) * dx + (cy - y1) * dy) / L2))
        if math.hypot(cx - x1 - t * dx, cy - y1 - t * dy) < r:
            return True
        if dx * (cy - y1) - dy * (cx - x1) < 0:
            inside = False
    return inside


def _render_fan_spiral(m, fig, fr):
    """照作者给的样图画（10-27 第二次给图后定稿）：
    * 根在左下角，辐条从近乎竖直一根根顺时针倒下来（相邻两根最多隔 12°，辐条多时最后几根略低于水平线）；
    * 每根辐条上先是一个大圆（面积 ∝ size，没有 size 就是同样大小的起点圆），从圆往外一格一个小点，点数 = 数值；
    * 大圆沿着一道螺旋往外排：写了 start 时，圆就在 start 处（径向是同一把尺，虚线弧标出刻度）；
      没写 start 时，圆一个挨一个往外排开、互不相压——这时圆的远近只为排开，虚线弧不标数；
    * 标签顺着辐条写在点的尽头（转过的字），后面跟着数值；
    * 灰度随先后一档档变浅，重音只有一处。"""
    data = m["data"]
    items = list(data["items"])
    has_start = all("start" in i for i in items)
    if m.get("order") != "given":
        if has_start:
            items.sort(key=lambda i: (i["start"], -i["value"]))
        else:
            items.sort(key=lambda i: -i["value"])
    p, fs, k = fr.p, fr.fs, fr.k
    hero = _hero_id(m)
    unit = m.get("unit", "")
    us = f" {unit}" if unit else ""
    has_size = all("size" in i for i in items)
    n = len(items)
    lfs, vfs = fs["label"], fs["tick"]
    pad = 6 * max(k, 0.6)
    stp = min(math.radians(12.0), math.radians(92.0) / max(1, n - 1))
    a0 = math.radians(-84.0)
    angs = [a0 + stp * i for i in range(n)]
    ends = [(i.get("start", 0) + i["value"]) for i in items]
    vmax = max(ends) if has_start else max(i["value"] for i in items)
    ticks = nice_ticks(vmax, 4, integer=all(float(x).is_integer() for x in ends))
    step = ticks[1] - ticks[0]
    sub = step / 5 if max(i["value"] for i in items) / (step / 5) <= 40 else step
    smax = max(i["size"] for i in items) if has_size else None
    rel = [math.sqrt(i["size"] / smax) if has_size else 1.0 for i in items]
    tickw = max(text_w(tick_label(t) + us, vfs, mono=True) for t in ticks) if has_start else 0.0
    ox = fr.plot_left + tickw + pad * 2 + max(8.0, 22.0 * k)
    oy = fr.plot_bottom - max(8.0, 22.0 * k) - pad
    vs = [_fmt(i["value"]) + us for i in items]
    gap = lfs * 0.4
    wl = [text_w(str(i["label"]), lfs) for i in items]
    wv = [text_w(v_, vfs, mono=True, track=fr.track) for v_ in vs]
    rd = max(1.6, 2.4 * k)

    def layout(sc, rb_max):
        """按比例尺 sc 与最大圆半径 rb_max 排一遍；排不下返回 None。"""
        rbs = [rb_max * r_ for r_ in rel] if has_size else [rb_max] * n
        if min(rbs) < 2.5:                            # 最小的圆小到看不见：这种排法不用（面积不能为了看得见而放大）
            return None
        offs = []
        if has_start:
            offs = [i["start"] * sc for i in items]
        else:
            vtop = max(i["value"] for i in items) * sc
            for q in range(n):                        # 沿一道螺旋往外排（像样图）：越往后越远，且与前面每一个圆都不相压
                d = 0.0 if q == 0 else max(offs[-1], vtop * 0.5 * q / max(1, n - 1))
                c, s_ = math.cos(angs[q]), math.sin(angs[q])
                while any(math.hypot(d * c - offs[j] * math.cos(angs[j]), d * s_ - offs[j] * math.sin(angs[j]))
                          < rbs[q] + rbs[j] + 2.0 for j in range(q)):
                    d += 0.5
                offs.append(d)
        circles = [(ox + d * math.cos(a), oy + d * math.sin(a), r_) for d, a, r_ in zip(offs, angs, rbs)]
        for (x, y, r_) in circles:
            if x - r_ < fr.plot_left - 0.5 or x + r_ > fr.plot_right + 0.5 or y - r_ < fr.plot_top - 0.5 \
                    or y + r_ > fr.plot_bottom + 0.5:
                return None
        if has_start:
            for q in range(n):
                for j in range(q):
                    if math.hypot(circles[q][0] - circles[j][0], circles[q][1] - circles[j][1]) \
                            < circles[q][2] + circles[j][2] + 1.0:
                        return None
        labels, tips = [], []
        for q, it in enumerate(items):
            a = angs[q]
            r_tip = offs[q] + (0 if has_start else 0) + it["value"] * sc + (0 if has_start else rbs[q])
            tips.append(r_tip)
            d0 = max(r_tip, offs[q] + rbs[q]) + pad
            L = wl[q] + gap + wv[q]
            poly = _seg_poly(ox + d0 * math.cos(a), oy + d0 * math.sin(a), a, L, lfs)
            if any(x < fr.plot_left - 0.5 or x > fr.plot_right + 0.5 or y < fr.plot_top - 0.5
                   or y > fr.plot_bottom + 0.5 for x, y in poly):
                return None
            labels.append((d0, poly))
        for q in range(n):
            for j in range(q):
                if _sat(labels[q][1], labels[j][1], 1.0):
                    return None
            for j, (x, y, r_) in enumerate(circles):
                if _circle_hits_poly(x, y, r_ + 1.0, labels[q][1]):
                    return None
        return offs, circles, labels, tips
    rb_cap = max(7.0, (22.0 if has_size else 6.0) * k)
    best = None
    for rb_max in (rb_cap, rb_cap * 0.8, rb_cap * 0.64, rb_cap * 0.5):
        # 从大往小试：比例尺太大出界，太小标签在根部挤成一团；取排得下的最大那一档，再细分逼近
        hi = max(fr.plot_right - ox, oy - fr.plot_top) / max(1e-9, vmax)
        lo, sc_ = None, hi
        while sc_ * max(i["value"] for i in items) >= 90:
            if layout(sc_, rb_max) is not None:
                lo = sc_
                break
            hi, sc_ = sc_, sc_ * 0.96
        if lo is None:
            continue
        for _ in range(24):
            mid = (lo + hi) / 2
            if layout(mid, rb_max) is not None:
                lo = mid
            else:
                hi = mid
        best = (lo, rb_max)
        break
    if best is None:
        raise SpecError("发射扇在这块画布上排不开：辐条太多、标签太长或画布太小")
    sc, rb_max = best
    offs, circles, labels, tips = layout(sc, rb_max)
    # 整把扇子（圆、点、标签）在绘图区里居中：根随之挪动，比例尺不变
    xs = [x - r_ for x, _, r_ in circles] + [x + r_ for x, _, r_ in circles] + [pt[0] for _, pl in labels for pt in pl]
    ys = [y - r_ for _, y, r_ in circles] + [y + r_ for _, y, r_ in circles] + [pt[1] for _, pl in labels for pt in pl]
    xs += [ox + t_ * math.cos(a) for t_, a in zip(tips, angs)]
    ys += [oy + t_ * math.sin(a) for t_, a in zip(tips, angs)]
    left_need = (tickw + pad * 2) if has_start else 0.0
    dx = ((fr.plot_left + left_need) + fr.plot_right - min(xs) - max(xs)) / 2
    dx = max(dx, fr.plot_left + left_need - min(xs))
    dy = (fr.plot_top + fr.plot_bottom - min(ys) - max(ys)) / 2
    ox, oy = ox + dx, oy + dy
    offs, circles, labels, tips = layout(sc, rb_max)
    # 刻度弧：写了 start 才标数（径向是同一把尺）；没写 start 时弧只给节奏，不标数
    span_a = (angs[0] - math.radians(6), angs[-1] + math.radians(28))
    rings = [t for t in ticks[1:] if t * sc <= max(tips) + 1] if has_start else []
    if not has_start:
        rr = max(tips) / 4
        rings = [rr * j for j in (1, 2, 3, 4)]
    for j, t in enumerate(rings):
        r = t * sc if has_start else t
        a_hi = span_a[1]
        pts = []                                  # 只画落在绘图区里的那一段
        for s_ in range(61):
            a = span_a[0] + (a_hi - span_a[0]) * s_ / 60
            x, y = ox + r * math.cos(a), oy + r * math.sin(a)
            if fr.plot_left <= x <= fr.plot_right and fr.plot_top <= y <= fr.plot_bottom:
                pts.append((x, y))
            elif pts:
                break
        if len(pts) >= 2:
            fig.path("M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in pts), p["axis"], 0.8,
                     dash=f"1 {max(3.0, 4 * k):.1f}", role="ring", value=t if has_start else None)
        if has_start:
            tx, ty = ox - pad, oy - r + vfs * 0.35
            if ty - vfs >= fr.plot_top and tx - tickw >= fr.plot_left - 0.5:
                fig.text(tx, ty, tick_label(t) + us, vfs, p["note"], anchor="end", family="mono", role="tick")
    for q, it in enumerate(items):
        h = it["id"] == hero
        a = angs[q]
        c, s_ = math.cos(a), math.sin(a)
        cx_, cy_, rb = circles[q]
        col = p["accent"] if h else _ramp(p, q, n)
        dotc = p["accent"] if h else p["mark"]
        r_from = offs[q] + (0 if has_start else rb)
        r_to = r_from + it["value"] * sc
        fig.line(ox + r_from * c, oy + r_from * s_, ox + r_to * c, oy + r_to * s_, p["accent"] if h else p["grid"],
                 0.8 * max(k, 0.7), role="spoke", id=it["id"], value=it["value"], hero=h,
                 extra={"ox": ox, "oy": oy, "scale": sc, "r0": r_from})
        j = 1
        while j * sub <= it["value"] + 1e-9:
            r_ = r_from + j * sub * sc
            if r_ > offs[q] + rb + rd * 1.2:
                fig.circle(ox + r_ * c, oy + r_ * s_, rd, dotc, role="unitdot", id=it["id"], hero=h)
            j += 1
        if has_size:
            fig.circle(cx_, cy_, rb, col, role="bubble", id=it["id"], value=it["size"], hero=h,
                       extra={"vmax": smax, "rmax": rb_max})
        else:
            fig.circle(cx_, cy_, rb, col, role="end", id=it["id"], hero=h)
        d0, _ = labels[q]
        lx, ly = ox + d0 * c, oy + d0 * s_
        deg = math.degrees(a)
        nx, ny = -s_, c                              # 文字基线比辐条低 0.35 字高，字身正好骑在辐条的延长线上
        bx, by = lx + nx * lfs * 0.35, ly + ny * lfs * 0.35
        fig.text(bx, by, it["label"], lfs, p["accent"] if h else p["ink2"], weight=700 if h else 400,
                 rot=deg, role="category", id=it["id"], hero=h)
        vx_, vy_ = bx + (wl[q] + gap) * c, by + (wl[q] + gap) * s_
        _num_text(fig, fr, vx_, vy_, it["value"], hero=h, anchor="start", fs=vfs, unit=us or None,
                  role="value", id=it["id"], rot=deg)
    enc = f"一个小点 = {_fmt(sub)}{us}"
    if has_size:
        enc += f" · 圆面积 = {data['size_label']}"
    if has_start:
        enc += f" · 圆的位置 = {data.get('start_label') or '起点'}，弧上为刻度"
    elif m.get("order") != "given":
        enc += " · 由长到短"
    return None, enc


def _render_fan_arc(m, fig, fr):
    """从一个根发出几根辐条，辐条长 ∝ 数值（审理周数、持续天数）；辐条上一个小点一个刻度单位，
    端点的圆面积 ∝ size（标的额、件数）。辐条按说明里的先后排（通常是时间先后）。

    端点的圆（size）与标签不贴在端点上——短辐条的端点挤在根部，圆与字会压在一起——而是一律排在
    最外圈之外的同一道弧上、沿辐条方向，端点到圆之间用一条发丝虚线接住。圆排在同一道弧上，
    大小才好比。相邻两个标签还会挤时，后一个往外再退一档。"""
    data = m["data"]
    items = list(data["items"])
    if m.get("order") != "given":                 # 0.11.0 起默认由长到短（与尖上的画法一致）
        items.sort(key=lambda i: -i["value"])
    p, fs, k = fr.p, fr.fs, fr.k
    hero = _hero_id(m)
    unit = m.get("unit", "")
    us = f" {unit}" if unit else ""
    has_size = all("size" in i for i in items)
    vmax = max(i["value"] for i in items)
    ticks = nice_ticks(vmax, 4, integer=all(float(i["value"]).is_integer() for i in items))
    lfs, vfs = fs["label"], fs["tick"]
    labw = max(max(text_w(str(i["label"]), lfs), text_w(_fmt(i["value"]) + us, vfs, mono=True, track=fr.track))
               for i in items)
    texth = lfs + vfs * 1.25
    smax = max(i["size"] for i in items) if has_size else None
    tickw = max(text_w(tick_label(t) + us, vfs, mono=True) for t in ticks)
    pad = 10 * max(k, 0.6)
    step_out = texth * 1.15                      # 标签挤时往外退的一档
    a0, a1 = math.radians(-86.0), math.radians(-4.0)
    n = len(items)
    angs = [a0 + (a1 - a0) * i / (n - 1) for i in range(n)]
    da = (a1 - a0) / (n - 1)
    # 端点圆的最大半径：排在同一道弧上，相邻两个不相碰（先按一个保守的弧半径估，再按实际收紧）
    rb_cap = max(8.0, 26.0 * k) if has_size else 0.0
    left0 = fr.plot_left + tickw + pad * 1.5
    oy = fr.plot_bottom - vfs * 0.6
    room = labw + pad * 3 + step_out
    Rx = fr.plot_right - left0 - room - 2 * rb_cap
    Ry = oy - fr.plot_top - texth - pad * 3 - step_out - 2 * rb_cap
    Rmax = min(Rx, Ry)
    if Rmax < 120:
        raise SpecError("发射扇在这块画布上半径不足 120px：标签太长或画布太小。请删短标签或换大一档画布")
    rb_max = min(rb_cap, 0.45 * (Rmax + pad + rb_cap) * 2 * math.sin(da / 2)) if has_size else 0.0
    ox = left0 + max(0.0, (Rx - Rmax) / 2)       # 横向有富余时，整把扇子在绘图区里居中
    scale = Rmax / ticks[-1]
    boxes = []
    for t in ticks[1:]:                          # 刻度：四分之一圆弧，虚线
        r = t * scale
        pts = [(ox + r * math.cos(a0 + (a1 - a0) * s_ / 24), oy + r * math.sin(a0 + (a1 - a0) * s_ / 24))
               for s_ in range(25)]
        fig.path("M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in pts), p["grid"], 0.8, dash="2 4", role="ring",
                 value=t)
        tx, ty = ox - pad * 0.6, oy - r + vfs * 0.35
        fig.text(tx, ty, tick_label(t) + us, vfs, p["note"], anchor="end", family="mono", role="tick")
        boxes.append((_tbox(tx, ty, tick_label(t) + us, vfs, "end", mono=True), "刻度"))
    step = ticks[1] - ticks[0]
    sub = step / 5 if vmax / (step / 5) <= 40 else step       # 辐条上的小点：一个点一个刻度单位
    rd = max(1.6, 2.2 * k)
    RB = Rmax + pad + rb_max                     # 端点圆所在的那道弧
    RL = RB + rb_max + pad
    for i, it in enumerate(items):
        h = it["id"] == hero
        a = angs[i]
        c, s = math.cos(a), math.sin(a)
        L = it["value"] * scale
        ex_, ey_ = ox + L * c, oy + L * s
        col = p["accent"] if h else p["ink2"]
        rb = rb_max * math.sqrt(it["size"] / smax) if has_size else 0.0
        re_ = max(3.0, 4.5 * k)                  # 端点小圆：只标出辐条到哪为止
        anchor = "middle" if c < 0.3 else "start"
        vs = _fmt(it["value"]) + us
        placed = None
        for j in range(2):
            rr = RL + j * step_out
            tx, ty = ox + rr * c, oy + rr * s
            if anchor == "middle":
                ly, vy = ty - vfs * 1.35, ty
            else:
                ly, vy = ty - vfs * 0.15, ty + lfs * 0.95
            bl, bv = _tbox(tx, ly, it["label"], lfs, anchor), _tbox(tx, vy, vs, vfs, anchor, mono=True, track=fr.track)
            inside = all(b[0] >= 0 and b[1] >= 0 and b[2] <= fr.W and b[3] <= fr.H for b in (bl, bv))
            if inside and not any(_overlap(b, o, 2.0) for b in (bl, bv) for o, _ in boxes):
                placed = (rr, tx, ly, vy, bl, bv)
                break
        if placed is None:
            raise SpecError(f"发射扇的标签「{it['label']}」与旁边的挤在一起：辐条太密或标签太长。"
                            f"请减少辐条、删短标签，或换大一档画布")
        rr, tx, ly, vy, bl, bv = placed
        boxes += [(bl, it["label"]), (bv, it["label"])]
        # 端点之外到外圈：发丝虚线接住（不是数据，只是引路）
        far = (RB - rb - 2) if has_size else (rr - pad * 0.5)
        fig.line(ex_ + (re_ + 2) * c, ey_ + (re_ + 2) * s, ox + far * c, oy + far * s,
                 p["grid"], 0.8, dash="1 3", role="guide")
        fig.line(ox, oy, ex_, ey_, p["accent"] if h else p["axis"], (1.8 if h else 1.0) * max(k, 0.7),
                 role="spoke", id=it["id"], value=it["value"], hero=h, extra={"ox": ox, "oy": oy, "scale": scale})
        j = 1
        while j * sub < it["value"] - 1e-9:
            r_ = j * sub * scale
            fig.circle(ox + r_ * c, oy + r_ * s, rd, col, role="unitdot", id=it["id"], hero=h)
            j += 1
        fig.circle(ex_, ey_, re_, col, role="end", id=it["id"], hero=h)
        if has_size:
            fig.circle(ox + RB * c, oy + RB * s, rb, p["accent"] if h else p["mark"], role="bubble", id=it["id"],
                       value=it["size"], hero=h, extra={"vmax": smax, "rmax": rb_max})
        fig.text(tx, ly, it["label"], lfs, p["accent"] if h else p["ink2"], anchor=anchor,
                 weight=700 if h else 400, role="category", id=it["id"], hero=h)
        _num_text(fig, fr, tx, vy, it["value"], hero=h, anchor=anchor, fs=vfs, unit=us or None,
                  role="value", id=it["id"])
    enc = "辐条长 = " + (unit or "数值") + f" · 小点每格 {_fmt(sub)}{us}"
    if has_size:
        enc += f" · 外圈圆面积 = {data['size_label']}"
    if m.get("order") != "given":
        enc += " · 由长到短"
    return None, enc


def render_fan(m, fig, fr):
    """发射扇：先按作者给的样图画（圆沿螺旋排开、小点往外数、标签顺着辐条写）；排不开时，
    退回 0.10.0 的画法（圆与标签排在最外圈之外的同一道弧上，发丝虚线接回辐条尖）——
    原来画得出的说明，现在照样画得出。两种都放不下才拒。"""
    mark = len(fig.parts)
    try:
        return _render_fan_spiral(m, fig, fr)
    except SpecError:
        del fig.parts[mark:]                       # 画了一半的撤掉，换另一种从头画
    try:
        return _render_fan_arc(m, fig, fr)
    except SpecError:
        if m.get("order") == "given":
            raise
        del fig.parts[mark:]
    # 最后一档：按给出的先后排在外弧上（0.10.0 的原样）。由长到短排时标签挤、原来的先后却排得下的少数说明，
    # 不因为换了默认排法就画不出来
    return _render_fan_arc(dict(m, order="given"), fig, fr)


# --------------------------------------------------------------- converge（放射汇聚）
def render_converge(m, fig, fr):
    """一圈条目（一条诉请、一个争点、一份证据），每一条一根线汇入它所属的主题枢纽；
    枢纽面积 ∝ 条目数。条目按主题排在圆周上，主题之间空一段。"""
    data = m["data"]
    groups, items = data["groups"], data["items"]
    cnt = m["_derived"]["group_count"]
    p, fs, k = fr.p, fr.fs, fr.k
    hero = _hero_id(m)
    lfs, tfs = fs["label"], fs["tick"]
    order = {g["id"]: i for i, g in enumerate(groups)}
    seq = sorted(items, key=lambda it: order[it["group"]])            # sorted 是稳定的：组内保持原序
    has_lab = all("label" in it for it in items)
    leafw = max(text_w(str(it["label"]), tfs) for it in items) if has_lab else 0.0
    glab = {g["id"]: f"{g['label']} · {cnt[g['id']]}" for g in groups}
    gw = max(text_w(s, lfs) for s in glab.values())
    pw, ph = fr.plot_right - fr.plot_left, fr.plot_bottom - fr.plot_top
    pad = 8 * max(k, 0.6)
    outer = leafw + pad * 2 + gw + pad
    outer_v = (leafw + pad if has_lab else 0) + pad * 2 + lfs * 1.8
    R = min(pw / 2 - outer, ph / 2 - outer_v)
    if R < 110:
        raise SpecError("放射汇聚在这块画布上半径不足 110px：条目名或主题名太长、或画布太小。"
                        "请删短（或去掉条目名只画点）、或换大一档画布")
    cx, cy = fr.plot_left + pw / 2, fr.plot_top + ph / 2
    gapslots = 1.6
    slots = len(seq) + gapslots * len(groups)
    da = 2 * math.pi / slots
    ang, gmid, pos = {}, {}, -math.pi / 2 + da * gapslots / 2
    for g in groups:
        mine = [it for it in seq if it["group"] == g["id"]]
        start = pos
        for it in mine:
            ang[it["id"]] = pos + da / 2
            pos += da
        gmid[g["id"]] = (start + pos) / 2
        pos += da * gapslots
    cmax = max(cnt.values())
    Hmax = min(0.12 * R, R * 0.38 * math.sin(math.pi / max(len(groups), 2)) * 0.8)
    hub = {}
    for g in groups:
        a = gmid[g["id"]]
        hub[g["id"]] = (cx + 0.36 * R * math.cos(a), cy + 0.36 * R * math.sin(a), Hmax * math.sqrt(cnt[g["id"]] / cmax))
    # 先画线、再画点与枢纽：普通的在下，重点的压在最上面
    for pass_hero in (False, True):
        for it in seq:
            h = it["group"] == hero
            if h != pass_hero:
                continue
            a = ang[it["id"]]
            lx, ly = cx + R * math.cos(a), cy + R * math.sin(a)
            hx, hy, hr = hub[it["group"]]
            c1 = (cx + 0.62 * R * math.cos(a), cy + 0.62 * R * math.sin(a))
            c2 = (hx + (lx - hx) * 0.2, hy + (ly - hy) * 0.2)
            d = (f"M{lx:.2f},{ly:.2f} C{c1[0]:.2f},{c1[1]:.2f} {c2[0]:.2f},{c2[1]:.2f} {hx:.2f},{hy:.2f}")
            fig.path(d, p["accent"] if h else p["axis"], (1.3 if h else 0.8) * max(k, 0.7), role="edge",
                     id=it["id"], hero=h, extra={"hero-of": hero} if h else None)
    boxes = []
    for it in seq:
        h = it["group"] == hero
        a = ang[it["id"]]
        lx, ly = cx + R * math.cos(a), cy + R * math.sin(a)
        fig.circle(lx, ly, max(2.2, 3.0 * k), p["accent"] if h else p["ink2"], role="leaf", id=it["id"], hero=h,
                   extra={"hero-of": hero} if h else None)
        if has_lab:
            c, s = math.cos(a), math.sin(a)
            tx, ty = cx + (R + pad) * c, cy + (R + pad) * s + tfs * 0.35
            anchor = "start" if c > 0.2 else ("end" if c < -0.2 else "middle")
            if anchor == "middle":
                ty += tfs * (0.9 if s > 0 else -0.6)
            fig.text(tx, ty, it["label"], tfs, p["accent"] if h else p["note"], anchor=anchor, role="leaf-label",
                     id=it["id"], hero=h, **({"extra": {"hero-of": hero}} if h else {}))
            boxes.append((_tbox(tx, ty, it["label"], tfs, anchor), it["label"]))
    for g in groups:
        h = g["id"] == hero
        hx, hy, hr = hub[g["id"]]
        fig.circle(hx, hy, hr, p["accent"] if h else p["node"], role="hub", id=g["id"], value=cnt[g["id"]], hero=h,
                   extra={"vmax": cmax, "rmax": Hmax})
        a = gmid[g["id"]]
        c, s = math.cos(a), math.sin(a)
        rr = R + pad * 2 + (leafw + pad if has_lab else 0)
        tx, ty = cx + rr * c, cy + rr * s + lfs * 0.35
        anchor = "start" if c > 0.2 else ("end" if c < -0.2 else "middle")
        if anchor == "middle":
            ty += lfs * (0.9 if s > 0 else -0.6)
        fig.text(tx, ty, glab[g["id"]], lfs, p["accent"] if h else p["ink"], anchor=anchor, weight=700 if h else 600,
                 role="category", id=g["id"], hero=h)
        boxes.append((_tbox(tx, ty, glab[g["id"]], lfs, anchor), glab[g["id"]]))
    for b, what in boxes:
        if b[0] < fr.plot_left - 2 or b[2] > fr.plot_right + 2 or b[1] < fr.plot_top - lfs or b[3] > fr.plot_bottom + 2:
            raise SpecError(f"放射汇聚的「{what}」超出了绘图区：条目名或主题名太长、或画布太扁。"
                            f"请删短、去掉条目名只画点，或换大一档画布")
    clash = _boxes_clash(boxes)
    if clash:
        raise SpecError(f"放射汇聚的「{clash[0]}」与「{clash[1]}」挤在一起：条目太多或名字太长。"
                        f"请删短条目名、去掉条目名只画点，或换大一档画布")
    return None, "一个点 = 一条 · 枢纽面积 = 条目数"


# =============================================================== 0.11.0 · 再添四种画法
# 学自作者给的几张编辑型样图（点阵阶梯、法条沿革、区间胶囊、双读饼），同样只借图形、不借配色。
# V6 与 PPTX 导出都不支持旋转的字：样图里斜放的类目名，这里一律横排（放不下就竖排汉字，仍是正着写）。
# 每一种的「那条线」：点阵阶梯一格 = per；法条沿革横向位置 ∝ 年份；区间胶囊上下沿 = from / to；
# 双读饼角度 ∝ 占比、从内圈量起的长度 ∝ size。守卫从产物回读这几样。

_CJK_ONLY = __import__("re").compile(r"[一-鿿]{1,6}")


def _col_label(text, fs, width):
    """一列底下的类目名：先横排（最多两行）；横排放不下、又全是汉字（不超过六个），就竖排——
    一字一行，字仍是正的（不旋转：V6 与 PPTX 都不出斜字）。返回 (行列表, 是否竖排)。"""
    lines = wrap(str(text), fs, width)
    if len(lines) <= 2:
        return lines, False
    if _CJK_ONLY.fullmatch(str(text)) and fs <= width:
        return list(str(text)), True
    return None, False


# --------------------------------------------------------------- cascade（点阵阶梯）
def render_cascade(m, fig, fr):
    """几个类目各有一个件数（争点出现几次、违约事由几件）：一格 = per，一列方块由少到多排成阶梯，
    每一列的底边比前一列高一级，读者顺着台阶往上看。order: given 时不排序、底边齐平。"""
    data, d = m["data"], m["_derived"]
    items = list(data["items"])
    order = m.get("order") or "asc"
    if order == "desc":
        items.sort(key=lambda i: -i["value"])
    elif order != "given":
        items.sort(key=lambda i: i["value"])
    p, fs, k = fr.p, fr.fs, fr.k
    hero = _hero_id(m)
    per, cells = d["per"], d["cells"]
    unit = m.get("unit", "")
    n = len(items)
    pw = fr.plot_right - fr.plot_left
    slot = pw / n
    lfs, vfs = fs["label"], fs["value"]
    lab = {}
    for it in items:
        lines, vert = _col_label(it["label"], lfs, slot * 0.9)
        if lines is None:
            raise SpecError(f"点阵阶梯的类目名「{it['label']}」在每列 {slot:.0f}px 里放不下。"
                            f"请删短（竖排最多六个汉字）、减少列数，或换横版画布")
        lab[it["id"]] = (lines, vert)
    for it in items:
        if text_w(_fmt(it["value"]), vfs, mono=True, track=fr.track) > slot * 0.96:
            raise SpecError(f"点阵阶梯的数值「{_fmt(it['value'])}」在每列 {slot:.0f}px 里放不下。请减少列数或换大一档画布")
    lh = lfs * 1.18
    labh = max(len(v[0]) for v in lab.values()) * lh
    gap = 8 * max(k, 0.7)
    stair = order in ("asc", "desc")
    q = 0.85 if stair else 0.0                  # 一级台阶 = 0.85 格高
    step = [i if order == "asc" else (n - 1 - i) if order == "desc" else 0 for i in range(n)]
    # 最低一列的底边之下：类目名，加上台阶线斜穿类目名上方的那一点斜度（0.46 级）
    avail = fr.plot_bottom - labh - gap * 1.6 - fr.plot_top - vfs * 1.5
    need = max(cells[it["id"]] + q * step[i] for i, it in enumerate(items)) + 0.46 * q
    cell = min(avail / need, slot * 0.42, 30.0 * k + 6)
    side = cell * 0.8
    if side < 5:
        raise SpecError(f"点阵阶梯的一格在这块画布上不到 5px：格数太多。请把 data.per 调大（现在一格 = {_fmt(per)}），"
                        f"或换大一档画布")
    rise = q * cell
    base0 = fr.plot_bottom - labh - gap * 1.6 - 0.46 * rise
    x0 = fr.plot_left
    ys = [base0 - step[i] * rise for i in range(n)]
    off = gap * 0.6
    # 台阶线：一条斜的点线，从第一列左侧到最后一列右侧，在每一列底下 off 处穿过
    if stair:
        sl = (-rise if order == "asc" else rise) / slot          # 每向右 1px，台阶线升降多少
        xa_, xb_ = x0 + slot * 0.04, x0 + pw - slot * 0.04
        cx0 = x0 + slot * 0.5
        ya = ys[0] + off + (xa_ - cx0) * sl
        yb = ys[0] + off + (xb_ - cx0) * sl
        fig.line(xa_, ya, xb_, yb, p["axis"], max(1.0, 1.4 * k),
                 dash=f"0.1 {max(3.0, 4.2 * k):.1f}" if fr.corner > 0 else f"1.2 {max(3.0, 4.2 * k):.1f}",
                 role="stair")
    else:
        fig.line(x0, ys[0] + off, x0 + pw, ys[0] + off, p["axis"], 1.0, role="axis", value=0)
    ranked = sorted(range(n), key=lambda i: (items[i]["value"], i))
    upper = {ranked[j] for j in range(n) if j >= n / 2}
    for i, it in enumerate(items):
        h = it["id"] == hero
        cx = x0 + slot * (i + 0.5)
        col = p["accent"] if h else (p["ladder"][0] if i in upper else p["mark"])
        c = cells[it["id"]]
        for j in range(c):
            cy = ys[i] - cell * (j + 0.5)
            fig.module(cx, cy, side, col, role="dot", id=it["id"], hero=h, extra={"col": i})
        top = ys[i] - cell * c
        _num_text(fig, fr, cx, top - vfs * 0.55, it["value"], hero=h, role="value", id=it["id"])
        lines, vert = lab[it["id"]]
        y = ys[i] + gap * 1.6 + (0.46 * rise if stair else 0) + lfs * 0.9
        for ln in lines:
            fig.text(cx, y, ln, lfs, p["accent"] if h else p["ink2"], anchor="middle", weight=700 if h else 400,
                     role="category", id=it["id"], hero=h)
            y += lh
    u = unit or "件"
    enc = f"一格 = {_fmt(per)} {u}" + ("（不足一格四舍五入）" if d["rounded"] else "")
    if order == "asc":
        enc += " · 由少到多"
    elif order == "desc":
        enc += " · 由多到少"
    return None, enc


# --------------------------------------------------------------- lineage（法条沿革）
def _year_ticks(lo, hi):
    for st in (1, 2, 5, 10, 20, 25, 50, 100):
        if (hi - lo) / st <= 8:
            break
    t = math.ceil(lo / st) * st
    out = []
    while t <= hi:
        out.append(t)
        t += st
    return out


def render_lineage(m, fig, fr):
    """一行一部法律（司法解释、合同、章程……）：横向是年份。实心点 = 通过，空心圈 = 修改，
    竖线 = 废止；现行有效的线一直画到截至年份。右侧一栏印出状态与修改次数——次数由脚本数。"""
    data = m["data"]
    items = data["items"]
    until = data["until"]
    mk = {"start": "通过", "revise": "修改", "end": "废止", **(data.get("marks") or {})}
    p, fs, k = fr.p, fr.fs, fr.k
    hero = _hero_id(m)
    lfs, tf = fs["label"], fs["tick"]
    colw, lab = _label_column(items, lfs, (fr.plot_right - fr.plot_left) * 0.22)
    right = {}
    for it in items:
        revs = it.get("revisions", [])
        st = f"{it['end']} 年{mk['end']}" if "end" in it else "现行有效"
        right[it["id"]] = (st, f"{mk['revise']} {len(revs)} 次" if revs else "")
    rw = max(max(text_w(a, tf), text_w(b, tf)) for a, b in right.values())
    gap = 14 * max(k, 0.6)
    xa = fr.plot_left + colw + gap * 1.6
    xb = fr.plot_right - rw - gap * 1.6
    lo = min(it["start"] for it in items)
    t0 = (lo // 5) * 5
    if t0 == until:
        t0 -= 5
    ticks = _year_ticks(t0, until)
    sc = (xb - xa) / (until - t0)
    X = lambda yr: xa + (yr - t0) * sc                       # noqa: E731
    top = fr.plot_top + tf * 1.6
    bottom = fr.plot_bottom
    rowh = (bottom - top) / len(items)
    need = lfs * 1.25 * max(len(v) for v in lab.values()) + 4
    if rowh < max(need, tf * 2.6):
        raise SpecError(f"法条沿革 {len(items)} 行在这块画布上每行只有 {rowh:.0f}px，放不下。请减少行数或换大一档画布")
    r = max(3.6, min(7.0 * k, rowh * 0.16))
    # 年份标签：放得下就标在点的上方或下方（同一行相邻的上下交替）；有一处放不下，全图都不标，只看刻度
    show = rowh >= 2 * r + 2 * tf * 1.15 + 6
    plan = {}
    if show:
        for it in items:
            ev = [it["start"]] + list(it.get("revisions", [])) + ([it["end"]] if "end" in it else [])
            boxes, pos = [], []
            for j, yr in enumerate(ev):
                s_ = str(yr)
                w = text_w(s_, tf, mono=True)
                bx = (X(yr) - w / 2, X(yr) + w / 2)
                side = -1
                if any(not (bx[1] + 2 < b[0] or b[1] + 2 < bx[0]) for b, sd in boxes if sd == -1):
                    side = 1
                    if any(not (bx[1] + 2 < b[0] or b[1] + 2 < bx[0]) for b, sd in boxes if sd == 1):
                        show = False
                        break
                boxes.append((bx, side))
                pos.append((yr, side))
            if not show:
                break
            plan[it["id"]] = pos
    # 刻度与竖向网格
    tick_boxes = []
    for t in ticks:
        x = X(t)
        fig.line(x, top - tf * 0.4, x, bottom, p["grid"], 0.8, role="grid", value=t)
        tick_boxes.append(_tbox(x, fr.plot_top + tf, str(t), tf, "middle", mono=True))
    u_anchor = "middle" if _tbox(X(until), 0, f"截至 {until}", tf, "middle")[2] <= fr.W - fr.mx * 0.5 else "end"
    ub = _tbox(X(until), fr.plot_top + tf, f"截至 {until}", tf, u_anchor)
    for t, b in zip(ticks, tick_boxes):
        if t != until and not _overlap(b, ub, 4.0):
            fig.text(X(t), fr.plot_top + tf, str(t), tf, p["note"], anchor="middle", family="mono", role="tick")
    fig.line(X(until), top - tf * 0.4, X(until), bottom, p["axis"], 1.0, role="grid", value=until)
    fig.text(X(until), fr.plot_top + tf, f"截至 {until}", tf, p["ink2"], anchor=u_anchor, role="tick")
    ex = {"x0": xa, "t0": t0, "scale": sc}
    for i, it in enumerate(items):
        h = it["id"] == hero
        cy = top + rowh * (i + 0.5)
        col = p["accent"] if h else p["ink2"]
        sw = (2.4 if h else 1.5) * max(k, 0.7)
        end = it.get("end")
        last = end if end is not None else until
        fig.line(X(it["start"]), cy, X(last), cy, col, sw, role="life", id=it["id"], hero=h,
                 extra=dict(ex, start=it["start"], last=last))
        if end is not None:
            fig.line(X(end), cy - r * 1.5, X(end), cy + r * 1.5, col, sw * 1.2, role="end", id=it["id"],
                     value=end, hero=h, extra=ex)
        fig.circle(X(it["start"]), cy, r, col, role="start", id=it["id"], value=it["start"], hero=h, extra=ex)
        for yr in it.get("revisions", []):
            fig.circle(X(yr), cy, r * 0.86, p["paper"], col, max(1.2, 1.6 * k), role="revise", id=it["id"],
                       value=yr, hero=h, extra=ex)
        if show:
            for yr, side in plan[it["id"]]:
                yy = cy - r - 4 if side < 0 else cy + r + 4 + tf * 0.88
                fig.text(X(yr), yy, str(yr), tf, p["accent"] if h else p["note"], anchor="middle", family="mono",
                         role="year", id=it["id"], hero=h)
        lines = lab[it["id"]]
        y = cy - (len(lines) - 1) * lfs * 0.62 + lfs * 0.35
        for ln in lines:
            fig.text(xa - gap * 1.6, y, ln, lfs, p["accent"] if h else p["ink2"], anchor="end",
                     weight=700 if h else 400, role="category", id=it["id"], hero=h)
            y += lfs * 1.25
        a, b = right[it["id"]]
        xr = xb + gap * 1.6
        if b:
            fig.text(xr, cy - tf * 0.25, a, tf, p["accent"] if h else p["ink2"], role="status", id=it["id"], hero=h)
            fig.text(xr, cy + tf * 1.05, b, tf, p["note"], role="count", id=it["id"])
        else:
            fig.text(xr, cy + tf * 0.35, a, tf, p["accent"] if h else p["ink2"], role="status", id=it["id"], hero=h)
    return None, f"● {mk['start']} · ○ {mk['revise']} · 竖线 = {mk['end']} · 横向为年份"


# --------------------------------------------------------------- interval（区间胶囊）
def _span_ticks(lo, hi, want=5):
    span = (hi - lo) or 1.0
    t = nice_ticks(span, want)
    stp = t[1] - t[0]
    a = math.floor(lo / stp + 1e-9) * stp
    b = math.ceil(hi / stp - 1e-9) * stp
    out, v = [], a
    while v <= b + stp * 1e-6:
        out.append(round(v, 10))
        v += stp
    return out


def render_interval(m, fig, fr):
    """每一项一段区间（判赔的最低到最高、刑期的下限到上限、置信区间），竖着画成一根胶囊；
    上端印 to、下端印 from；可选白点 mid（中位数、点估计）。纵轴含 0（有负数时 0 线在中间）。"""
    data = m["data"]
    items = list(data["items"])
    if m.get("order") == "desc":
        items.sort(key=lambda i: -i["to"])
    p, fs, k = fr.p, fr.fs, fr.k
    hero = _hero_id(m)
    unit = m.get("unit", "")
    lo = min(0, min(i["from"] for i in items))
    hi = max(0, max(i["to"] for i in items))
    ticks = _span_ticks(lo, hi)
    tf, vfs, lfs = fs["tick"], fs["value"], fs["label"]
    tw = max(text_w(tick_label(t), tf, mono=True) for t in ticks)
    gap = 10 * max(k, 0.6)
    x0 = fr.plot_left + tw + gap
    slot = (fr.plot_right - x0) / len(items)
    lab = {}
    for it in items:
        lines, vert = _col_label(it["label"], lfs, slot * 0.9)
        if lines is None or vert:
            raise SpecError(f"区间胶囊的名称「{it['label']}」在每条 {slot:.0f}px 里两行放不下。请删短、减少条目或换横版画布")
        lab[it["id"]] = lines
    widest = max(text_w(_fmt(v), vfs, mono=True, track=fr.track) for it in items for v in (it["from"], it["to"]))
    if widest > slot * 0.96:
        vfs = max(FLOOR, fs["tick"])                 # 放不下先退一档字号（不小于 11px），还放不下就明说
    for it in items:
        for v in (it["from"], it["to"]):
            if text_w(_fmt(v), vfs, mono=True, track=fr.track) > slot * 0.96:
                raise SpecError(f"区间胶囊的数值「{_fmt(v)}」在每条 {slot:.0f}px 里放不下。请减少条目、换大一档画布，"
                                f"或把单位换大一级")
    labh = max(len(v) for v in lab.values()) * lfs * 1.25
    yb = fr.plot_bottom - labh - gap - vfs * 1.5            # 最低刻度所在的 y（下沿数值要放在它下面）
    yt = fr.plot_top + vfs * 1.6
    sc = (yb - yt) / (ticks[-1] - ticks[0])
    Y = lambda v: yb - (v - ticks[0]) * sc                   # noqa: E731
    for t in ticks:
        y = Y(t)
        fig.line(x0, y, fr.plot_right, y, p["axis"] if t == 0 else p["grid"], 1.2 if t == 0 else 0.8,
                 role="axis" if t == 0 else "grid", value=t)
        fig.text(x0 - gap, y + tf * 0.35, tick_label(t), tf, p["note"], anchor="end", family="mono", role="tick")
    w = max(8.0, min(slot * 0.26, 18.0 * k + 4))
    for i, it in enumerate(items):
        h = it["id"] == hero
        cx = x0 + slot * (i + 0.5)
        ya, yb_ = Y(it["to"]), Y(it["from"])
        short = yb_ - ya < w
        if short:                                           # 区间太窄：画成一粒，中心仍在区间中点
            ym = (ya + yb_) / 2
            ya, yb_ = ym - w / 2, ym + w / 2
        fill = p["accent"] if h else p["ladder"][0]
        ex = {"from": it["from"], "to": it["to"], "y0": Y(0), "scale": sc}
        if short:
            ex["short"] = 1
        fig.rect(cx - w / 2, ya, w, yb_ - ya, fill, r=w / 2 if fr.corner > 0 else 0.0, role="range", id=it["id"],
                 value=it["to"] - it["from"], hero=h, extra=ex)
        if "mid" in it:
            fig.circle(cx, Y(it["mid"]), w * 0.26, p["paper"], role="mid", id=it["id"], value=it["mid"],
                       hero=h, extra={"y0": Y(0), "scale": sc})
        _num_text(fig, fr, cx, ya - vfs * 0.45, it["to"], hero=h, fs=vfs, role="value", id=it["id"])
        fig.text(cx, yb_ + vfs * 1.15, _fmt(it["from"]), vfs, p["accent"] if h else p["note"], anchor="middle",
                 family="mono", track=fr.track, role="value", id=it["id"], hero=h)
        y = fr.plot_bottom - labh + lfs * 0.9
        for ln in lab[it["id"]]:
            fig.text(cx, y, ln, lfs, p["accent"] if h else p["ink2"], anchor="middle", weight=700 if h else 400,
                     role="category", id=it["id"], hero=h)
            y += lfs * 1.25
    enc = "胶囊 = 从低到高的区间" + (f"（{unit}）" if unit else "")
    if all("mid" in i for i in items):
        enc += f" · 白点 = {data['mid_label']}"
    return None, enc


# --------------------------------------------------------------- radpie（双读饼）
def _annulus(cx, cy, r0, r1, a0, a1):
    seg = max(4, int(math.degrees(a1 - a0) / 3))
    out = [(cx + r1 * math.cos(a0 + (a1 - a0) * s / seg), cy + r1 * math.sin(a0 + (a1 - a0) * s / seg))
           for s in range(seg + 1)]
    out += [(cx + r0 * math.cos(a1 - (a1 - a0) * s / seg), cy + r0 * math.sin(a1 - (a1 - a0) * s / seg))
            for s in range(seg + 1)]
    return out


def render_radpie(m, fig, fr):
    """一张饼读两个数：角度 = 占比（件数占几成），从内圈量起的长度 = 第二个量（平均审理天数、平均标的额）。
    「占得不多、却最耗时」这类话，一张图就能说清。长度从内圈量起（内圈就是 0），虚线圈是刻度。"""
    data, d = m["data"], m["_derived"]
    items = list(data["items"])
    if m.get("order") == "desc":
        items.sort(key=lambda i: -i["value"])
    p, fs, k = fr.p, fr.fs, fr.k
    hero = _hero_id(m)
    su = data.get("size_unit", "") or ""
    sus = f" {su}" if su and su not in ("%", "％") else su
    shares = d["shares"]
    tot = xsum(i["value"] for i in items)
    smax = max(i["size"] for i in items)
    ticks = nice_ticks(smax, 4, integer=all(float(i["size"]).is_integer() for i in items))
    lfs, vfs = fs["label"], fs["tick"]
    texts = {}
    for it in items:
        texts[it["id"]] = (str(it["label"]), f"{_fmt(round(shares[it['id']], 1))}% · {_fmt(it['size'])}{sus}")
    labw = max(max(text_w(a, lfs), text_w(b, vfs)) for a, b in texts.values())
    blockh = lfs + vfs * 1.35
    pw, ph = fr.plot_right - fr.plot_left, fr.plot_bottom - fr.plot_top
    pad = 12 * max(k, 0.6)
    keyh = vfs * 1.6
    R = min((ph - keyh) / 2 - blockh * 0.7 - pad, pw / 2 - labw - pad * 2.5)
    if R < 80:
        raise SpecError("双读饼在这块画布上半径不足 80px：名称太长或画布太小。请删短名称或换大一档画布")
    r0 = R * 0.26
    cx = fr.plot_left + pw / 2
    cy = fr.plot_top + (ph - keyh) / 2
    L = (R - r0) / ticks[-1]
    for t in ticks[1:]:
        fig.circle(cx, cy, r0 + t * L, None, p["axis"], 0.9, dash=f"1 {max(3.0, 4 * k):.1f}", role="ring", value=t)
    a = -math.pi / 2
    sep = max(1.5, 2.6 * k)
    placed = []
    for it in items:
        h = it["id"] == hero
        span = it["value"] / tot * 2 * math.pi
        rr = r0 + it["size"] * L
        pts = _annulus(cx, cy, r0, rr, a, a + span)
        fig.poly(pts, p["accent"] if h else p["mark"], p["paper"], sep, role="wedge", id=it["id"],
                 value=it["value"], hero=h,
                 extra={"cx": cx, "cy": cy, "r0": r0, "size": it["size"], "scale": L, "total": tot})
        placed.append((it, a + span / 2, rr, h))
        a += span
    # 标签：排在最外一道刻度圈之外，左右两侧各自从上到下排开，挤了就往下让，用发丝线接回扇区
    RL = R + pad
    sides = {1: [], -1: []}
    for it, am, rr, h in placed:
        sd = 1 if math.cos(am) >= 0 else -1
        sides[sd].append([cy + RL * math.sin(am), it, am, rr, h])
    for sd, arr in sides.items():
        arr.sort(key=lambda e: e[0])
        gapy = blockh + 4
        for j in range(1, len(arr)):
            if arr[j][0] - arr[j - 1][0] < gapy:
                arr[j][0] = arr[j - 1][0] + gapy
        over = (arr[-1][0] + blockh * 0.5 - fr.plot_bottom + keyh) if arr else 0
        if over > 0:
            for e in arr:
                e[0] -= over
            for j in range(len(arr) - 2, -1, -1):
                if arr[j + 1][0] - arr[j][0] < gapy:
                    arr[j][0] = arr[j + 1][0] - gapy
        for y, it, am, rr, h in arr:
            if y - blockh * 0.5 < fr.plot_top - 0.5:
                raise SpecError(f"双读饼的标签「{it['label']}」排不下：扇区太多或画布太矮。请合并小类为「其他」或换大一档画布")
            dy = max(-1.0, min(1.0, (y - cy) / RL))
            xx = cx + sd * RL * math.sqrt(max(0.0, 1 - dy * dy))
            tx = xx + sd * pad * 0.6
            ex0, ey0 = cx + (rr + 3) * math.cos(am), cy + (rr + 3) * math.sin(am)
            fig.line(ex0, ey0, xx, y, p["axis"], 0.8, role="guide")
            anchor = "start" if sd > 0 else "end"
            a_, b_ = texts[it["id"]]
            fig.text(tx, y - vfs * 0.15, a_, lfs, p["accent"] if h else p["ink2"], anchor=anchor,
                     weight=700 if h else 400, role="category", id=it["id"], hero=h)
            fig.text(tx, y + lfs * 0.95, b_, vfs, p["accent"] if h else p["ink"], anchor=anchor,
                     role="value", id=it["id"], hero=h)
    key = "虚线圈：" + " / ".join(tick_label(t) for t in ticks[1:]) + sus
    fig.text(fr.plot_left, fr.plot_bottom, key, vfs, p["note"], role="key")
    return None, f"角度 = 占比 · 自内圈量起的长度 = {data['size_label']}"


RENDERERS = {"bar": render_bar, "hbar": render_hbar, "waffle": render_waffle, "rose": render_rose,
             "dumbbell": render_dumbbell, "strip": render_strip, "sankey": render_sankey,
             "ribbon": render_ribbon, "waterfall": render_waterfall,
             "funnel": render_funnel, "matrix": render_matrix, "fan": render_fan, "converge": render_converge,
             "cascade": render_cascade, "lineage": render_lineage, "interval": render_interval,
             "radpie": render_radpie}

ENCODING = {"bar": "纵轴从 0 起", "hbar": "横轴从 0 起"}


def render(m, W, H, pal):
    """返回 (svg, 实际图种, 说明列表)。竖柱放不下会自动换成横条，并记进说明。"""
    notes = []
    chart = m["chart"]
    for _attempt in range(2):
        fr = Frame(m, W, H, pal)
        fig = Fig(W, H, pal, corner=fr.corner)
        if pal.get("pattern"):
            fig.pattern_dots(pal["pattern"])
        # 编码说明要先知道才能画副标题；副标题高度又决定绘图区。先用一份临时画框试画拿到说明。
        enc = ENCODING.get(chart)
        if enc is None:
            probe = Fig(W, H, pal, corner=fr.corner)
            fr_probe = Frame(m, W, H, pal)
            fr_probe.draw(probe, "")
            res = RENDERERS[chart](m, probe, fr_probe)
            enc = res[1] if isinstance(res, tuple) else ""
        fr.draw(fig, enc)
        res = RENDERERS[chart](m, fig, fr)
        switch = res[0] if isinstance(res, tuple) else res
        if switch:
            notes.append(f"{CHART_ZH[chart]}的类目名或数值在柱宽里放不下，已换成{CHART_ZH[switch]}")
            chart = switch
            continue
        if m.get("annotations"):
            annotate(m, fig, fr, chart)
        desc = f"{CHART_ZH[chart]}。{m['scope']}，n = {_fmt(m['n'])}。来源：{m['source']}"
        fig.a11y = (m["title"], desc)
        return fig.svg(), chart, notes
    raise SpecError("换档后仍放不下")


# =============================================================== 批注
def annotate(m, fig, fr, chart):
    """在批注栏里放一句旁白，引一条虚线到目标数据上。路线由 callout 搜出，搜不到就明说。"""
    import guards                                   # 障碍物与守卫用同一套读法
    p = fr.p
    fs = fr.note_fs
    serif = p["title_font"] == "serif"
    placed = []                                     # 已放的批注：(文字外框, 引线采样点)
    for a in m["annotations"]:
        els, _, _ = guards.parse(fig.svg())
        tb = guards.target_box(els, a["target"])
        if tb is None:
            raise SpecError(f"批注指向的「{a['target']}」在图上没有形状")
        obst = guards.obstacles(els, a["target"])
        lines = wrap(a["text"], fs, fr.note_w)
        if len(lines) > 3:
            raise SpecError(f"批注「{a['text']}」在批注栏里超过三行，请删短")
        lh = fs * 1.4
        hb = lh * (len(lines) - 1) + fs * 1.05
        cands = []
        y = fr.plot_top
        while y + hb <= fr.plot_bottom + 0.01:
            cands.append(y)
            y += 2.0
        ty = (tb[1] + tb[3]) / 2
        cands.sort(key=lambda yt: (abs(yt + fs * 0.5 - ty), yt))
        done = None
        for land, arrive in callout.landing_candidates(tb, chart):
            for yt in cands:
                box = (fr.note_x, yt, fr.note_x + max(fig_text_w(l, fs) for l in lines), yt + hb)
                if any(_overlap(box, b, 6) for b, _ in placed):
                    continue
                s = (fr.note_x - 8.0, yt + fs * 0.5)
                c1, c2 = callout.leader_ctrl(s, land, arrive)
                pts = callout.cubic(s, c1, c2, land)
                if callout.leader_hits(pts, obst + [(b, "批注") for b, _ in placed]):
                    continue
                if any(callout.too_close(pts, other) for _, other in placed):
                    continue
                done = (yt, s, c1, c2, land, box, pts)
                break
            if done:
                break
        if not done:
            raise SpecError(f"批注「{a['text']}」的引线找不到一条不压字、不穿过别的数据的路线。"
                            f"请换一个目标，或把这句话写进标题")
        yt, s, c1, c2, land, box, pts = done
        y = yt + fs * 0.88
        for ln in lines:
            fig.text(fr.note_x, y, ln, fs, p["ink2"], family="serif" if serif else "sans",
                     role="annotation", id=a["target"])
            y += lh
        fig.path(callout.leader_d(s, c1, c2, land), p["note"], max(1.0, 1.1 * fr.k), dash="3 3",
                 role="leader", id=a["target"])
        fig.circle(land[0], land[1], max(2.4, 3.2 * fr.k), p["ink2"], role="landing", id=a["target"])
        placed.append((box, pts))


def fig_text_w(s, fs):
    return text_w(s, fs)


def _overlap(a, b, pad=0.0):
    return a[0] < b[2] + pad and b[0] < a[2] + pad and a[1] < b[3] + pad and b[1] < a[3] + pad
