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


RENDERERS = {"bar": render_bar, "hbar": render_hbar, "waffle": render_waffle, "rose": render_rose,
             "dumbbell": render_dumbbell, "strip": render_strip, "sankey": render_sankey,
             "ribbon": render_ribbon, "waterfall": render_waterfall}

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
