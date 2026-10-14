# -*- coding: utf-8 -*-
"""把 V1–V5 出的 SVG 收进课件的一个格子：等比缩放、平移、把曲线摊平成折线。

V1–V5 一字不改，所以 V7 只能读它们的成品 SVG。要放进格子里，有三件事：
  1. **等比**缩放进格子（绝不拉伸），居中；
  2. V1 的 PPTX 导出器只认 M / L / Q 的路径与 translate 分组：这里把 A（圆弧）、C、S、T、H、V 与相对坐标
     全部换成绝对坐标的折线，缩放与平移直接算进坐标与字号里——PowerPoint 里的组合缩放不会同步缩字号，
     所以不能靠组合，只能把数改掉；
  3. 缩完字太小就不收：最小的字低于 MIN_FONT 就报「放不下」，不硬塞。

另外：去掉整张图的底色（课件页面自己有底色）；<image> 收不进可编辑的 PPTX，列出来；
按颜色认出这张图是奇川风、歸藏风还是白描，与课件的风格不一致就不收（不重新上色——颜色是那个模块的事）。
"""
import html
import math
import re

MIN_FONT = 11.0          # 与 V6 的字号下限（G3）一致：投影与 A4 打印都在 8pt 以上

_TOK = re.compile(r"<(/?)(g|rect|circle|ellipse|line|path|polygon|polyline|text|image|defs|marker|pattern|title|desc)\b([^>]*?)(/?)>", re.S)
_AT = re.compile(r"""([\w:-]+)\s*=\s*(?:"([^"]*)"|'([^']*)')""")
SKIP_ROLES = {"title", "subtitle", "source", "axis", "tick", "paper", "texture", "canvas-bg"}


def _attrs(raw):
    """属性 → 字典。单引号、双引号都认（V3 的虚线属性写的是单引号：只认双引号时虚线会悄悄变实线）。"""
    return {k: (v1 if v1 or not v2 else v2) for k, v1, v2 in _AT.findall(raw)}


def _f(a, k, d=0.0):
    try:
        return float(str(a.get(k, d)).replace("px", ""))
    except ValueError:
        return d


_TEXT_STYLE = ("fill", "font-family", "font-weight", "font-size", "letter-spacing", "text-anchor", "fill-opacity")


def _first_num(v, fs):
    """坐标属性的第一个数（x="10 20 30" 这种逐字坐标取第一个）；em 按字号换算。没有就 None。"""
    m_ = re.match(r"\s*(-?[\d.]+(?:e-?\d+)?)\s*(em|px)?", str(v or ""))
    if not m_:
        return None
    return float(m_.group(1)) * (fs if m_.group(2) == "em" else 1.0)


def _text_runs(a, inner):
    """一个 <text> → 若干段定好位置的字：[(x, y, 字, 合并后的属性)]。

    V4 的简表把坐标写在 <tspan> 上、<text> 自己没有 x / y；多行文字用 tspan 的 x + dy 分行。
    只读 <text> 的 x / y 会把这些字全堆到左上角（开源前实跑撞到：V4 简表放进来，表头糊成一团、表格是空的）。
    这里逐段算位置：tspan 写了 x / y 就用它的，写了 dx / dy 就在上一段的位置上挪（em 按字号换算），
    什么都没写就接在上一段后面（同一行，样式随前一段）。"""
    fs0 = _f(a, "font-size", 13)
    cx, cy = _first_num(a.get("x"), fs0) or 0.0, _first_num(a.get("y"), fs0) or 0.0
    runs = []
    for m_ in re.finditer(r"<tspan\b([^>]*?)(/?)>(.*?)(?:</tspan>|$)|([^<]+)", inner, re.S):
        if m_.group(4) is not None:                       # tspan 之外的裸字：接在上一段后面
            t_ = m_.group(4)
            if not t_.strip():
                continue
            if runs:
                runs[-1][2] += t_
            else:
                runs.append([cx, cy, t_, dict(a)])
            continue
        if m_.group(2):
            continue
        ta = _attrs(m_.group(1))
        merged = dict(a)
        merged.update({k: v for k, v in ta.items() if k in _TEXT_STYLE})
        fs_ = _f(merged, "font-size", fs0)
        t_ = re.sub(r"<[^>]+>", "", m_.group(3))
        moved = any(k in ta for k in ("x", "y", "dx", "dy"))
        if "x" in ta:
            cx = _first_num(ta["x"], fs_) or 0.0
        if "y" in ta:
            cy = _first_num(ta["y"], fs_) or 0.0
        cx += _first_num(ta.get("dx"), fs_) or 0.0
        cy += _first_num(ta.get("dy"), fs_) or 0.0
        if not moved and runs:
            runs[-1][2] += t_                             # 没写位置：同一行接着写（样式随前一段；另起一段会和前一段叠在一起）
        elif t_.strip():
            runs.append([cx, cy, t_, merged])
    return [r_ for r_ in runs if r_[2].strip()]


def size_of(svg):
    m = re.search(r"<svg\b[^>]*>", svg)
    head = m.group(0) if m else ""
    a = _attrs(head)
    vb = a.get("viewBox")
    if vb:
        x, y, w, h = (float(v) for v in re.split(r"[\s,]+", vb.strip())[:4])
        return x, y, w, h
    return 0.0, 0.0, _f(a, "width", 0), _f(a, "height", 0)


def style_of(svg):
    """按颜色认风格：克莱因蓝 → 歸藏风；奇川深红或其淡色 → 奇川风；近黑 #111111 → 白描；只有灰 → 中性（哪种风格都能收）。"""
    cs = {c.upper() for c in re.findall(r"#[0-9A-Fa-f]{6}\b", svg)}
    if "#002FA7" in cs:
        return "歸藏风"
    if cs & {"#991B1B", "#E8D5D5", "#E5C9C9"}:
        return "奇川风"
    if "#111111" in cs or "#000000" in cs:
        return "白描"
    return "中性"


# ------------------------------------------------------------- path → 折线
_CMD = re.compile(r"([MmLlHhVvCcSsQqTtAaZz])([^MmLlHhVvCcSsQqTtAaZz]*)")
_NUM = re.compile(r"-?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


def _cubic(p0, p1, p2, p3, n=12):
    out = []
    for i in range(1, n + 1):
        t = i / n
        u = 1 - t
        out.append((u ** 3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t ** 3 * p3[0],
                    u ** 3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t ** 3 * p3[1]))
    return out


def _quad(p0, p1, p2, n=8):
    out = []
    for i in range(1, n + 1):
        t = i / n
        u = 1 - t
        out.append((u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0], u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1]))
    return out


def _arc(p0, rx, ry, phi, large, sweep, p1):
    """SVG 圆弧（端点式）→ 折线。按规范 F.6 换成中心式再采样。"""
    if rx == 0 or ry == 0 or p0 == p1:
        return [p1]
    rx, ry = abs(rx), abs(ry)
    ph = math.radians(phi)
    cp, sp = math.cos(ph), math.sin(ph)
    dx, dy = (p0[0] - p1[0]) / 2, (p0[1] - p1[1]) / 2
    x1 = cp * dx + sp * dy
    y1 = -sp * dx + cp * dy
    lam = (x1 * x1) / (rx * rx) + (y1 * y1) / (ry * ry)
    if lam > 1:
        rx, ry = rx * math.sqrt(lam), ry * math.sqrt(lam)
    num = rx * rx * ry * ry - rx * rx * y1 * y1 - ry * ry * x1 * x1
    den = rx * rx * y1 * y1 + ry * ry * x1 * x1
    co = math.sqrt(max(0.0, num / den)) if den else 0.0
    if large == sweep:
        co = -co
    cx1, cy1 = co * rx * y1 / ry, -co * ry * x1 / rx
    cx = cp * cx1 - sp * cy1 + (p0[0] + p1[0]) / 2
    cy = sp * cx1 + cp * cy1 + (p0[1] + p1[1]) / 2

    def ang(ux, uy, vx, vy):
        a = math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)
        return a
    t1 = ang(1, 0, (x1 - cx1) / rx, (y1 - cy1) / ry)
    dt = ang((x1 - cx1) / rx, (y1 - cy1) / ry, (-x1 - cx1) / rx, (-y1 - cy1) / ry)
    if not sweep and dt > 0:
        dt -= 2 * math.pi
    elif sweep and dt < 0:
        dt += 2 * math.pi
    n = max(4, int(abs(dt) / (math.pi / 16)))
    out = []
    for i in range(1, n + 1):
        t = t1 + dt * i / n
        x = cp * rx * math.cos(t) - sp * ry * math.sin(t) + cx
        y = sp * rx * math.cos(t) + cp * ry * math.sin(t) + cy
        out.append((x, y))
    out[-1] = p1
    return out


def path_to_polys(d):
    """返回 [(点列, 是否闭合)]：每个子路径一段。"""
    polys, cur, start, pts = [], (0.0, 0.0), (0.0, 0.0), []
    last_c, last_q, prev = None, None, ""

    def flush(closed=False):
        nonlocal pts
        if len(pts) >= 2:
            polys.append((pts, closed))
        pts = []
    for cmd, body in _CMD.findall(d or ""):
        nums = [float(n) for n in _NUM.findall(body)]
        rel = cmd.islower()
        C = cmd.upper()
        if C == "Z":
            if pts:
                pts.append(start)
            flush(True)
            cur = start
            prev = "Z"
            continue
        step = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Q": 4, "T": 2, "A": 7}[C]
        groups = [nums[i:i + step] for i in range(0, len(nums) - step + 1, step)] or []
        for gi, g in enumerate(groups):
            ox, oy = (cur if rel else (0.0, 0.0))
            if C == "M":
                p = (g[0] + ox, g[1] + oy)
                if gi == 0:
                    flush()
                    start = p
                    pts = [p]
                else:
                    pts.append(p)
                cur = p
            elif C == "L":
                cur = (g[0] + ox, g[1] + oy)
                pts.append(cur)
            elif C == "H":
                cur = (g[0] + (cur[0] if rel else 0.0), cur[1])
                pts.append(cur)
            elif C == "V":
                cur = (cur[0], g[0] + (cur[1] if rel else 0.0))
                pts.append(cur)
            elif C in "CS":
                if C == "C":
                    c1 = (g[0] + ox, g[1] + oy)
                    c2, p = (g[2] + ox, g[3] + oy), (g[4] + ox, g[5] + oy)
                else:
                    c1 = (2 * cur[0] - last_c[0], 2 * cur[1] - last_c[1]) if prev in "CS" and last_c else cur
                    c2, p = (g[0] + ox, g[1] + oy), (g[2] + ox, g[3] + oy)
                pts += _cubic(cur, c1, c2, p)
                last_c, cur = c2, p
            elif C in "QT":
                if C == "Q":
                    c1, p = (g[0] + ox, g[1] + oy), (g[2] + ox, g[3] + oy)
                else:
                    c1 = (2 * cur[0] - last_q[0], 2 * cur[1] - last_q[1]) if prev in "QT" and last_q else cur
                    p = (g[0] + ox, g[1] + oy)
                pts += _quad(cur, c1, p)
                last_q, cur = c1, p
            elif C == "A":
                p = (g[5] + ox, g[6] + oy)
                pts += _arc(cur, g[0], g[1], g[2], int(g[3]), int(g[4]), p)
                cur = p
            if not pts:
                pts = [cur]
            prev = C
    flush()
    return polys


def _clip_seg(p, q, L):
    """线段裁到矩形 L=(x0, y0, x1, y1)（Liang–Barsky）。全在外返回 None。"""
    (x1, y1), (x2, y2) = p, q
    dx, dy = x2 - x1, y2 - y1
    t0, t1 = 0.0, 1.0
    for pp, qq in ((-dx, x1 - L[0]), (dx, L[2] - x1), (-dy, y1 - L[1]), (dy, L[3] - y1)):
        if pp == 0:
            if qq < 0:
                return None
            continue
        r = qq / pp
        if pp < 0:
            t0 = max(t0, r)
        else:
            t1 = min(t1, r)
        if t0 > t1:
            return None
    return (x1 + t0 * dx, y1 + t0 * dy), (x1 + t1 * dx, y1 + t1 * dy)


def _clip_polyline(pts, L):
    """折线裁到矩形：可能断成几段。返回 [段, …]。"""
    out, cur = [], []
    for p, q in zip(pts, pts[1:]):
        c = _clip_seg(p, q, L)
        if c is None:
            if len(cur) > 1:
                out.append(cur)
            cur = []
            continue
        a, b = c
        if cur and math.hypot(cur[-1][0] - a[0], cur[-1][1] - a[1]) < 1e-6:
            cur.append(b)
        else:
            if len(cur) > 1:
                out.append(cur)
            cur = [a, b]
    if len(cur) > 1:
        out.append(cur)
    return out


def _clip_poly(pts, L):
    """闭合多边形裁到矩形（Sutherland–Hodgman）。"""
    def cut(poly, inside, inter):
        res = []
        for i, cur in enumerate(poly):
            prev = poly[i - 1]
            if inside(cur):
                if not inside(prev):
                    res.append(inter(prev, cur))
                res.append(cur)
            elif inside(prev):
                res.append(inter(prev, cur))
        return res

    def ix(x):
        return lambda p, q: (x, p[1] + (q[1] - p[1]) * (x - p[0]) / ((q[0] - p[0]) or 1e-9))

    def iy(y):
        return lambda p, q: (p[0] + (q[0] - p[0]) * (y - p[1]) / ((q[1] - p[1]) or 1e-9), y)
    poly = list(pts[:-1] if len(pts) > 1 and pts[0] == pts[-1] else pts)
    for inside, inter in ((lambda p: p[0] >= L[0], ix(L[0])), (lambda p: p[0] <= L[2], ix(L[2])),
                          (lambda p: p[1] >= L[1], iy(L[1])), (lambda p: p[1] <= L[3], iy(L[3]))):
        if not poly:
            return []
        poly = cut(poly, inside, inter)
    return poly + poly[:1] if poly else []


def _seg_dist(px, py, p, q):
    (x1, y1), (x2, y2) = p, q
    dx, dy = x2 - x1, y2 - y1
    L = dx * dx + dy * dy
    t = 0.0 if L == 0 else max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / L))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


# ------------------------------------------------------------- 放进格子
def _adopt(r0, v0):
    """没标记的卡片归到它旁边的小圆点上。返回 {第几个元素: 元素键}。

    V2 的编号时间轴只给轴上的小圆点标了 data-id，旁边的事件卡片、引线、圆点里的编号都没标。
    结果在 V7 里选「第 3 件事」只拿到一个 10px 的圆点：切片切出空卡片的边、读图编号没有名字、聚焦和讲课动画只亮一个点。

    只管「没有名字的小圆点」（不超过 40×40、里面没认出字），只收没有标记的元素，已标记的一个不动：
      卡片：圆角矩形，和圆点在同一水平带上（圆点中心落在卡片上下沿之内），左右相距不超过 80，取最近的；
            一个圆点只收一张卡片；两个圆点一样近就不收（宁可不认，不认错）。
      卡片里的字、圆点里的编号：字的中心落在卡片或圆点里。
      引线：几乎水平的细线，夹在圆点和卡片之间。"""
    parts = r0.get("parts") or []
    dots = {a["key"]: (a["box"][0], a["box"][1], a["box"][0] + a["box"][2], a["box"][1] + a["box"][3])
            for a in r0.get("anchors") or [] if a["box"][2] <= 40 and a["box"][3] <= 40 and not a["label"].strip()}
    if not dots:
        return {}
    un = [p_ for p_ in parts if p_[7] is None]
    cards = [p_ for p_ in un if p_[4] == "rect" and p_[2] - p_[0] >= 40 and p_[3] - p_[1] >= 16
             and (p_[2] - p_[0]) * (p_[3] - p_[1]) < 0.25 * v0[2] * v0[3]]
    pairs = []
    for c_ in cards:
        cand = []
        for k_, b in dots.items():
            cy = (b[1] + b[3]) / 2
            gap = max(c_[0] - b[2], b[0] - c_[2], 0)
            if c_[1] - 4 <= cy <= c_[3] + 4 and gap <= 80:
                cand.append((gap, k_))
        cand.sort()
        if cand and (len(cand) == 1 or cand[1][0] - cand[0][0] > 1):
            pairs.append((cand[0][0], cand[0][1], c_))
    adopt, taken = {}, set()
    for gap, k_, c_ in sorted(pairs, key=lambda t_: t_[0]):
        if k_ in taken:
            continue
        taken.add(k_)
        adopt[c_[6]] = k_
        b = dots[k_]
        for p_ in un:
            cx, cy = (p_[0] + p_[2]) / 2, (p_[1] + p_[3]) / 2
            if p_[4] == "text" and (c_[0] <= cx <= c_[2] and c_[1] <= cy <= c_[3]):
                adopt[p_[6]] = k_
            elif p_[4] in ("line", "path", "polyline") and p_[3] - p_[1] <= 6 \
                    and abs(cy - (b[1] + b[3]) / 2) <= 6 \
                    and p_[0] >= min(b[0], c_[0]) - 2 and p_[2] <= max(b[2], c_[2]) + 2:
                adopt[p_[6]] = k_
    for k_, b in dots.items():                     # 圆点里的编号（不管有没有配上卡片）
        for p_ in un:
            cx, cy = (p_[0] + p_[2]) / 2, (p_[1] + p_[3]) / 2
            if p_[4] == "text" and b[0] - 2 <= cx <= b[2] + 2 and b[1] - 2 <= cy <= b[3] + 2:
                adopt[p_[6]] = k_
    return adopt


def _a4_footer(r0, v0):
    """A4 文书的页脚（V4 简表的「案名　大事记简表 … 第 1 页 / 共 1 页」）：放进课件页时它把内容高度撑满整页，
    表格只占上面三分之一、字缩到 7px，而且没法切片（简表没有元素标记）。

    只有三样同时成立才认作页脚，返回它的上沿（原图坐标）；否则 None，什么都不动：
      1. 在原图最下面 12% 里，而且那一带只有字；
      2. 和上面的内容隔着一大段空白（超过原图高的 20%）；
      3. 那一带的字连起来有「第 n 页」。"""
    parts = r0.get("parts") or []
    if not parts:
        return None
    band = v0[1] + v0[3] * 0.88
    low = [p_ for p_ in parts if p_[1] >= band]
    if not low or any(p_[4] != "text" for p_ in low):
        return None
    words = "".join(p_[5] for p_ in sorted(low, key=lambda p_: (round(p_[1]), p_[0])))
    if not re.search(r"第\s*\d+\s*页", words):
        return None
    top = min(p_[1] for p_ in low)
    above = [p_ for p_ in parts if p_[1] < band]
    if not above or top - max(p_[3] for p_ in above) < v0[3] * 0.20:
        return None
    return top - 1


def fit(svg, box, deck_style=None, mod="fig", trim=False, drop_title=False, crop=None, light=None):
    """把一张 SVG 等比放进 box=(x, y, w, h)。返回 (元素串, 报告)。报告里 problems 非空就不该收。
    trim：按实际内容裁掉原图四周的页边（V1–V5 的图按 A4 文书留了 56px 左右的边，进课件是白占地方）；
    drop_title：略去原图自带的大标题（data-role="title"）——这一页有自己的标题时，两个标题是重复的。
    两样都只是让同一张图在同样的格子里放得更大、字更大；图里的内容一个不少。"""
    v0 = size_of(svg)
    _, r0 = _fit(svg, v0, None, mod, None, drop_title) if v0[2] > 0 and v0[3] > 0 else (None, {})
    adopt = _adopt(r0, v0) if r0 else {}
    if adopt:                                  # 卡片归到圆点之后再量一遍：切片、编号按带卡片的大小算
        _, r0 = _fit(svg, v0, None, mod, None, drop_title, adopt=adopt)
    if trim or drop_title or crop or light:
        c = r0.get("content")
        foot = _a4_footer(r0, v0) if trim else None
        if foot is not None:                   # A4 页脚不算内容：按页脚之上的内容裁边
            above = [p_ for p_ in r0["parts"] if p_[1] < foot]
            c = [min(p_[0] for p_ in above), min(p_[1] for p_ in above),
                 max(p_[2] for p_ in above), max(p_[3] for p_ in above)]
        view, clip = v0, None
        if trim and c:
            pad = 6.0
            view = (c[0] - pad, c[1] - pad, c[2] - c[0] + 2 * pad, c[3] - c[1] + 2 * pad)
        missing, hide = [], set()
        if crop:                               # 切片：只取这几个图内元素所在的那一块（原图坐标；r0 是 1:1 放的）
            by = {a["key"]: a["box"] for a in r0["anchors"]}
            bs = [by[k] for k in crop if k in by]
            missing = [k for k in crop if k not in by]
            if bs:
                pad = 24.0
                x0 = min(b[0] for b in bs) - pad
                y0 = min(b[1] for b in bs) - pad
                x1 = max(b[0] + b[2] for b in bs) + pad
                y1 = max(b[1] + b[3] for b in bs) + pad
                if c:                          # 不超出原图实际画了东西的范围
                    x0, y0, x1, y1 = max(x0, c[0] - 6), max(y0, c[1] - 6), min(x1, c[2] + 6), min(y1, c[3] + 6)
                clip = (x0, y0, x1, y1)
                view = (x0, y0, x1 - x0, y1 - y0)
                for a_ in r0["anchors"]:           # 没选的元素没整个落在切片里：整个不画，免得切出卡片边、切断字
                    if a_["key"] in crop or a_["key"].startswith("edge:"):
                        continue                   # 关系线照旧：切剩不到 60 的线头不画（见 _fit）
                    bx, by_, bw, bh = a_["box"]
                    ix = max(0.0, min(bx + bw, x1) - max(bx, x0))
                    iy = max(0.0, min(by_ + bh, y1) - max(by_, y0))
                    if bw * bh > 0 and ix * iy < 0.98 * bw * bh:   # 没整个落在切片里：切开的卡片字也被切断，不如不画
                        hide.add(a_["key"])
        out, rep = _fit(svg, box, deck_style, mod, view, drop_title, clip, set(crop or []), set(light) if light else None,
                        foot, adopt, hide)
        if rep.get("foot_dropped"):
            rep["notes"].append("原图是 A4 文书，页脚（「第 n 页」那一行）在课件页上不要，已略去")
        if clip:
            rep["notes"].append(f"切片：只取 {len(crop) - len(missing)} 个元素所在的一块（{view[2]:.0f}×{view[3]:.0f}），"
                                f"同样的格子里放大到 {rep['scale']:.2f} 倍")
            rep["crop"] = [round(v, 1) for v in clip]
        if missing:
            rep["warnings"] = [f"切片里有 {len(missing)} 个元素在图里找不到了（图换过？）：请重新选"]
        if view != v0 and not clip:
            rep["notes"].append(f"按内容裁掉原图四周的空白（{v0[2]:.0f}×{v0[3]:.0f} → {view[2]:.0f}×{view[3]:.0f}）")
        if drop_title and r0.get("title_dropped"):
            rep["notes"].append("原图自带的标题已略去：用这一页自己的标题")
        return out, rep
    return _fit(svg, box, deck_style, mod, adopt=adopt)


FADE = 0.72                       # 聚焦：没点亮的元素往白里调这么多（颜色由图自己的颜色推出来，导出检查认得）


def fade_hex(c, t=FADE):
    c = c.lstrip("#")
    if len(c) != 6:
        return "#" + c
    return "#" + "".join("%02X" % round(int(c[i:i + 2], 16) * (1 - t) + 255 * t) for i in (0, 2, 4))


def _fade_tag(tag):
    return re.sub(r'((?:fill|stroke)=")(#[0-9A-Fa-f]{6})(")', lambda m_: m_.group(1) + fade_hex(m_.group(2)) + m_.group(3), tag)


def fade_ids(svg, keep):
    """V6 图表：带 data-id 的元素里，键（id:xxx）不在 keep 里的调浅。用于聚焦。"""
    def one(m_):
        tag = m_.group(0)
        mid = re.search(r'data-id="([^"]+)"', tag)
        return tag if not mid or f"id:{mid.group(1)}" in keep else _fade_tag(tag)
    return re.sub(r"<(?:rect|path|circle|line|polygon|polyline|text)\b[^>]*>", one, svg)


def guess_from(svg):
    """从 SVG 里的标记认出是哪个模块出的图（拿不准就返回 None）：V3 有 data-kind="edge"/"node"，V5 有 data-box，
    V2 / V1 的时间轴有 data-role="event"/"span"（两家同名，只能说「V1 / V2」）。"""
    if 'data-kind="edge"' in svg or "data-kind='edge'" in svg or 'data-kind="node"' in svg:
        return "V3 法律关系图大师"
    if "data-box=" in svg:
        return "V5 庭审对抗图大师"
    if 'data-role="event"' in svg or 'data-role="span"' in svg:
        return "V1 / V2 时间轴"
    return None


def _fit(svg, box, deck_style=None, mod="fig", view=None, drop_title=False, clip=None, focus=None, light=None, foot=None,
         adopt=None, hide=None):
    vx, vy, W, H = view or size_of(svg)
    rep = {"problems": [], "notes": [], "scale": 0.0, "min_font": None, "style": style_of(svg), "dropped": [],
           "anchors": []}
    if W <= 0 or H <= 0:
        rep["problems"].append("这张 SVG 没有写宽高（width / height / viewBox），不知道该缩多少")
        return "", rep
    bx, by, bw, bh = box
    s = min(bw / W, bh / H)
    rep["scale"] = s
    rep["view"] = [round(W, 1), round(H, 1)]                # 实际放进格子的那一块（裁边、切片之后）的宽高
    tx = bx + (bw - W * s) / 2 - vx * s
    ty = by + (bh - H * s) / 2 - vy * s
    if deck_style and rep["style"] not in ("中性", deck_style):
        rep["problems"].append(f"这张图是{rep['style']}，课件是{deck_style}。请回原模块用{deck_style}重出一张"
                               f"（V7 不给别的模块的图改颜色）")
    out = []
    stack = [(0.0, 0.0, None, False, "")]      # (平移 x, 平移 y, 所属的图内元素, 是否在原图标题里, 所在容器的角色)
    orphans = []                               # 没归属的文字：(out 下标, 中心点)。画完后配给最近的关系线（关系标注）
    content = []                               # 实际画了东西的范围（原图坐标），给 trim 用
    parts = []                                 # 与 content 一一对应：(元素种类, 字, 第几个元素, 归属)，认页脚、认卡片用
    cur = ["", "", 0, None]
    anchors = {}                               # 图内元素（磁吸点）：V1/V2/V6 的 data-id、V3 的节点、V5 的卡片

    def _anchor(a, parent):
        """这个元素（或这一组）是不是一个图内元素：是就返回它的键，否则沿用上一层的。"""
        role = a.get("data-role") or a.get("data-kind") or ""
        if role in SKIP_ROLES:
            return None
        if parent and not a.get("data-id"):    # 已在某个图内元素里、自己又没编号：归它
            return parent
        if a.get("data-id"):                   # 同一编号的柱子、类别名、数值、时间轴上的点与卡片：同一个元素
            key = f"id:{a['data-id']}"
        elif role == "edge":                   # 关系线（V3 的 data-kind="edge"、V1 edges 组里的线）
            key = f"edge:#{sum(1 for k in anchors if k.startswith('edge:')) + 1}"
        elif role == "node":                   # V3 的节点分组没有 id：按节点里的文字认
            key = f"node:#{len(anchors) + 1}"
        elif a.get("data-box"):                # V5：data-box = 要件 id + 一侧 + 行号；去掉行号就是一张卡片
            key = "card:" + re.sub(r"\d+$", "", a["data-box"])
        else:
            return parent
        if key not in anchors or anchors[key].pop("_adopted", False):   # 先收了卡片、圆点后到：按圆点补全
            old = anchors.get(key) or {}
            anchors[key] = {"key": key, "role": role or "item", "id": a.get("data-id"), "label": old.get("label", ""),
                            "box": old.get("box"), "hero": a.get("data-hero") == "1", "value": a.get("data-value")}
            if a.get("data-ref"):                  # V3 的主体、关系：出处记录里的编号（只用来对出处，不改元素键）
                anchors[key]["ref"] = a["data-ref"]
            if old.get("card"):
                anchors[key]["card"] = old["card"]
        return key

    def _grow(key, x0, y0, x1, y1):
        content.append((min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)))
        parts.append((cur[0], cur[1], cur[2], key))
        if not key:
            return
        b = anchors[key]["box"]
        anchors[key]["box"] = [min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)] if b is None else \
            [min(b[0], x0, x1), min(b[1], y0, y1), max(b[2], x0, x1), max(b[3], y0, y1)]
    skip = 0
    fonts = []
    canvas_area = W * H
    # 箭头（<marker>）：原图的定义要带过来，否则编辑器里的预览没有箭头，而导出的 PPTX 有——关系图的方向是有法律意义的。
    # id 加上模块前缀（同一页两张图都叫 #a 会串），按缩放比例改大小；聚焦时调浅的线配一份调浅的箭头。
    markers = {m_.group(2): (_attrs(m_.group(1)), m_.group(3))
               for m_ in re.finditer(r'<marker\b([^>]*?\bid="([^"]+)"[^>]*)>(.*?)</marker>', svg, re.S)}
    mk_pre = re.sub(r"[^A-Za-z0-9_-]", "-", str(mod)) + "-mk-"
    mk_used = set()
    H0 = size_of(svg)                          # 原图的完整画布（裁边、切片前）：认原图标题用
    ttl = [None]
    for m in _TOK.finditer(svg):
        close, kind, raw, selfclose = m.group(1), m.group(2), m.group(3), m.group(4)
        if kind in ("defs", "marker", "pattern", "title", "desc"):
            if close:
                skip = max(0, skip - 1)
            elif not selfclose:
                skip += 1
            continue
        if skip:
            continue
        if kind == "g":
            if close:
                if len(stack) > 1:
                    stack.pop()
            elif not selfclose:
                dx = dy = 0.0
                tm = re.search(r"translate\(\s*(-?[\d.]+)(?:[ ,]+(-?[\d.]+))?\s*\)", raw)
                if tm:
                    dx, dy = float(tm.group(1)), float(tm.group(2) or 0)
                if re.search(r"(scale|rotate|matrix|skew)\(", raw):
                    rep["notes"].append("有一组元素带缩放或旋转变换，按平移处理，请核这一组的位置")
                ga = _attrs(raw)
                crole = ga.get("data-role", "") if not ga.get("data-id") else ""
                stack.append((stack[-1][0] + dx, stack[-1][1] + dy, _anchor(ga, stack[-1][2]),
                              stack[-1][3] or ga.get("data-role") == "title", crole or stack[-1][4]))
            continue
        if close:
            continue
        a = _attrs(raw)
        ox, oy, akey, in_title, crole = stack[-1]
        cur[0], cur[1] = kind, ""
        cur[2] += 1                                # 第几个元素：两遍之间按它对上号
        runs = None
        if kind == "text":
            end = svg.find("</text>", m.end())
            runs = _text_runs(a, svg[m.end():end] if end > 0 else "")
            if not runs:
                continue
            a = dict(runs[0][3], x=str(runs[0][0]), y=str(runs[0][1]))   # 第一段的位置：认标题、切片都按它
        if drop_title and (in_title or a.get("data-role") == "title"):
            rep["title_dropped"] = True
            continue
        if drop_title and kind == "text" and not akey and not crole and a.get("text-anchor") == "middle":
            ay = _f(a, "y") + oy             # 没标 data-role 的原图标题（V3）：顶上居中的大字，和紧跟其下的一行小字
            if _f(a, "font-size", 13) >= 22 and ay < H0[1] + 0.16 * H0[3] and ttl[0] is None:
                ttl[0] = ay
                rep["title_dropped"] = True
                continue
            if ttl[0] is not None and ttl[0] < ay <= ttl[0] + 40 and _f(a, "font-size", 13) < 20:
                continue
        if crole == "edges" and kind in ("path", "line", "polyline") and not akey:
            a = dict(a, **{"data-kind": "edge"})
        akey = _anchor(a, akey)
        if akey is None and adopt and cur[2] in adopt:   # 没标记、但认得出属于某个小圆点（见 _adopt）
            akey = adopt[cur[2]]
            if akey not in anchors:                    # 卡片画在圆点之前：先占个位，圆点到了再补全
                anchors[akey] = {"key": akey, "role": "node", "id": None, "label": "", "box": None, "hero": False,
                                 "value": None, "_adopted": True}
        if hide and akey in hide:                      # 切片：没选、大半在切片外的元素整个不画（不切成一条边）
            continue
        if akey and akey.startswith("edge:") and kind in ("path", "line", "polyline"):
            if kind == "line":
                ept = [(_f(a, "x1"), _f(a, "y1")), (_f(a, "x2"), _f(a, "y2"))]
            elif kind == "path":
                ept = [p for pts, _ in path_to_polys(a.get("d", "")) for p in pts]
            else:
                nums = [float(v) for v in _NUM.findall(a.get("points", ""))]
                ept = [(nums[i], nums[i + 1]) for i in range(0, len(nums) - 1, 2)]
            anchors[akey].setdefault("_pts", []).extend(((px + ox) * s + tx, (py + oy) * s + ty) for px, py in ept)
        X = lambda v: (v + ox) * s + tx
        Y = lambda v: (v + oy) * s + ty
        Lc = (clip[0] - ox, clip[1] - oy, clip[2] - ox, clip[3] - oy) if clip else None   # 切片框（本元素坐标）
        if Lc:
            if kind == "rect":
                x_, y_ = _f(a, "x"), _f(a, "y")
                x2_, y2_ = x_ + _f(a, "width"), y_ + _f(a, "height")
                nx0, ny0, nx1, ny1 = max(x_, Lc[0]), max(y_, Lc[1]), min(x2_, Lc[2]), min(y2_, Lc[3])
                if nx1 - nx0 < 0.5 or ny1 - ny0 < 0.5:
                    continue
                a = dict(a, x=str(nx0), y=str(ny0), width=str(nx1 - nx0), height=str(ny1 - ny0))
            elif kind in ("circle", "ellipse"):
                px_, py_ = _f(a, "cx"), _f(a, "cy")
                if not (Lc[0] - 4 <= px_ <= Lc[2] + 4 and Lc[1] - 4 <= py_ <= Lc[3] + 4):
                    continue
            elif kind == "line":
                p_, q_ = (_f(a, "x1"), _f(a, "y1")), (_f(a, "x2"), _f(a, "y2"))
                cl = _clip_seg(p_, q_, Lc)
                if cl is None:
                    continue
                if math.hypot(cl[1][0] - q_[0], cl[1][1] - q_[1]) > 1e-6:
                    a = {k: v for k, v in a.items() if k != "marker-end"}   # 线被切断：不画指向画面边缘的箭头
                a = dict(a, x1=str(cl[0][0]), y1=str(cl[0][1]), x2=str(cl[1][0]), y2=str(cl[1][1]))
        if light is not None and akey not in light and not (kind == "text" and not akey) \
                and a.get("data-role") not in SKIP_ROLES:     # 聚焦：没点亮的元素调浅（没归属的字等配完关系线再定）
            a = {k: (fade_hex(v) if k in ("fill", "stroke") and re.fullmatch(r"#[0-9A-Fa-f]{6}", v or "") else v)
                 for k, v in a.items()}
            a["_faded"] = "1"
        def _keep(a):
            sw = max(0.5, _f(a, "stroke-width", 1) * s)
            keep = ""
            for k in ("fill", "stroke", "stroke-dasharray", "font-family", "font-weight", "text-anchor", "fill-opacity",
                      "stroke-linecap", "marker-end"):
                if k in a:
                    v = a[k]
                    if k == "marker-end":
                        mid_ = re.match(r"\s*url\(#([^)]+)\)", v)
                        if mid_ and mid_.group(1) in markers:
                            mk_used.add((mid_.group(1), bool(a.get("_faded"))))
                            v = f"url(#{mk_pre}{mid_.group(1)}{'-f' if a.get('_faded') else ''})"
                    if k == "stroke-dasharray":
                        v = " ".join(f"{float(x) * s:.2f}" for x in re.findall(r"[\d.]+", v)) or v
                    keep += f' {k}="{html.escape(v, quote=True)}"'
            if "stroke" in a:
                keep += f' stroke-width="{sw:.2f}"'
            return keep
        keep = _keep(a)
        tag = f' data-mod="{mod}"' + (f' data-anchor="{html.escape(akey, quote=True)}"' if akey else "")
        if kind == "rect":
            w, h = _f(a, "width") * s, _f(a, "height") * s
            if w <= 0 or h <= 0:
                continue
            if _f(a, "width") * _f(a, "height") >= 0.98 * canvas_area:
                rep["dropped"].append("底色")          # 整张图的底：课件页面自己有底色
                continue
            rx = _f(a, "rx") * s
            _grow(akey, X(_f(a, "x")), Y(_f(a, "y")), X(_f(a, "x")) + w, Y(_f(a, "y")) + h)
            if adopt and akey and adopt.get(cur[2]) == akey:   # 归到圆点上的卡片：记下它，读图编号贴卡片的外角
                anchors[akey]["card"] = [round(X(_f(a, "x")), 1), round(Y(_f(a, "y")), 1), round(w, 1), round(h, 1)]
            out.append(f'<rect x="{X(_f(a, "x")):.2f}" y="{Y(_f(a, "y")):.2f}" width="{w:.2f}" height="{h:.2f}"'
                       + (f' rx="{rx:.2f}"' if rx else "") + keep + tag + "/>")
        elif kind in ("circle", "ellipse"):
            rx = _f(a, "r") if kind == "circle" else _f(a, "rx")
            ry = _f(a, "r") if kind == "circle" else _f(a, "ry")
            cx, cy = X(_f(a, "cx")), Y(_f(a, "cy"))
            _grow(akey, cx - rx * s, cy - ry * s, cx + rx * s, cy + ry * s)
            if abs(rx - ry) < 1e-6:
                out.append(f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{rx * s:.2f}"{keep}{tag}/>')
            else:
                pts = [(cx + rx * s * math.cos(t / 24 * 2 * math.pi), cy + ry * s * math.sin(t / 24 * 2 * math.pi))
                       for t in range(24)]
                out.append(f'<path d="M{" L".join(f"{p[0]:.2f},{p[1]:.2f}" for p in pts)} Z"{keep}{tag}/>')
        elif kind == "line":
            _grow(akey, X(_f(a, "x1")), Y(_f(a, "y1")), X(_f(a, "x2")), Y(_f(a, "y2")))
            out.append(f'<line x1="{X(_f(a, "x1")):.2f}" y1="{Y(_f(a, "y1")):.2f}" x2="{X(_f(a, "x2")):.2f}" '
                       f'y2="{Y(_f(a, "y2")):.2f}"{keep}{tag}/>')
        elif kind in ("path", "polygon", "polyline"):
            if kind == "path":
                polys = path_to_polys(a.get("d", ""))
            else:
                nums = [float(v) for v in _NUM.findall(a.get("points", ""))]
                pp = [(nums[i], nums[i + 1]) for i in range(0, len(nums) - 1, 2)]
                polys = [(pp + ([pp[0]] if kind == "polygon" and pp else []), kind == "polygon")]
            if Lc:
                clipped = []
                for pts, closed in polys:
                    if closed:
                        cp = _clip_poly(pts, Lc)
                        if len(cp) >= 4:
                            clipped.append((cp, True))
                    else:
                        pieces = _clip_polyline(pts, Lc)
                        if pieces and pts and math.hypot(pieces[-1][-1][0] - pts[-1][0], pieces[-1][-1][1] - pts[-1][1]) > 1e-6:
                            keep = re.sub(r' marker-end="[^"]*"', "", keep)
                        clipped += [(pc, False) for pc in pieces]
                polys = clipped
                if akey and akey.startswith("edge:") and akey not in (focus or ()):
                    ln = sum(math.hypot(q[0] - p[0], q[1] - p[1]) for pts, _ in polys for p, q in zip(pts, pts[1:]))
                    if ln < 60:                    # 没选中的关系被切得只剩一小截线头：不画，免得像残渣
                        continue
            for pts, closed in polys:
                if pts:
                    _grow(akey, min(X(px) for px, _ in pts), min(Y(py) for _, py in pts),
                          max(X(px) for px, _ in pts), max(Y(py) for _, py in pts))
                d = "M" + " L".join(f"{X(px):.2f},{Y(py):.2f}" for px, py in pts) + (" Z" if closed else "")
                out.append(f'<path d="{d}"{keep}{tag}/>')
        elif kind == "text":
            for rx_, ry_, txt, ra in runs:               # 一段一段放：tspan 各有各的位置（V4 简表、多行文字）
                if foot is not None and ry_ + oy >= foot:   # A4 页脚（见 fit）：课件页上不要
                    rep["foot_dropped"] = True
                    continue
                cur[0], cur[1] = "text", html.unescape(txt.strip())
                if Lc and not (Lc[0] - 4 <= rx_ <= Lc[2] + 4 and Lc[1] - 4 <= ry_ <= Lc[3] + 4):
                    continue
                if light is not None and akey and akey not in light and ra.get("data-role") not in SKIP_ROLES:
                    ra = {k: (fade_hex(v) if k in ("fill", "stroke") and re.fullmatch(r"#[0-9A-Fa-f]{6}", v or "") else v)
                          for k, v in ra.items()}
                rkeep = _keep(ra)
                fs = _f(ra, "font-size", 13) * s
                fonts.append(fs)
                ls = _f(ra, "letter-spacing", 0) * s
                tw = sum(fs if ord(ch) > 0x2E7F else fs * 0.56 for ch in html.unescape(txt.strip()))
                anc = ra.get("text-anchor", "start")
                x0 = X(rx_) - (tw if anc == "end" else tw / 2 if anc == "middle" else 0)
                _grow(akey, x0, Y(ry_) - fs * 0.85, x0 + tw, Y(ry_) + fs * 0.25)
                if not akey and not in_title and ra.get("data-role") not in SKIP_ROLES and crole not in SKIP_ROLES \
                        and _f(ra, "font-size", 13) < 24:          # 坐标轴组里的年份不是关系标注（V2 甘特图）
                    orphans.append((len(out), x0 + tw / 2, Y(ry_) - fs * 0.3, (x0, Y(ry_) - fs * 0.85,
                                    x0 + tw, Y(ry_) + fs * 0.25), html.unescape(txt.strip()), crole == "edge-labels"))
                if akey:                           # 元素的名字：它里面的几段字连起来（柱子 = 数值 + 类别；节点 = 名称 + 说明）
                    w_ = html.unescape(txt.strip())
                    lab = anchors[akey]["label"]
                    if w_ not in lab.split(" ") and len(lab) < 40:
                        anchors[akey]["label"] = (lab + " " + w_).strip()[:40]
                out.append(f'<text x="{X(rx_):.2f}" y="{Y(ry_):.2f}" font-size="{fs:.2f}"'
                           + (f' letter-spacing="{ls:.2f}"' if ls else "") + rkeep + tag + f">{txt}</text>")
        elif kind == "image":
            rep["dropped"].append("图片")
    edges = [v for v in anchors.values() if v.get("_pts")]
    for idx, cx, cy, bb, words, is_label in orphans:     # 关系标注：外框离哪条关系线最近（22 设计像素以内）就归哪条
        best = None
        for e in edges:
            pts_ = [(bb[0], bb[1]), (bb[2], bb[1]), (bb[0], bb[3]), (bb[2], bb[3]), (cx, bb[1]), (cx, bb[3]),
                    (bb[0], cy), (bb[2], cy), (cx, cy)]          # 文字外框上的点：竖线旁的标注按左右边算
            d = min(_seg_dist(x_, y_, p, q) for p, q in zip(e["_pts"], e["_pts"][1:]) for x_, y_ in pts_) \
                if len(e["_pts"]) > 1 else 1e9
            if best is None or d < best[0]:
                best = (d, e)
        if best and (is_label or best[0] <= 22 * max(s, 0.5)):   # V1 的 edge-labels 组里的字明确是关系标注
            e = best[1]
            _grow(e["key"], *bb)
            e["label"] = (e["label"] + " " + words).strip()[:40]
            out[idx] = out[idx].replace(f' data-mod="{mod}"', f' data-mod="{mod}" data-anchor="{html.escape(e["key"], quote=True)}"', 1)
            if light is not None and e["key"] not in light:
                out[idx] = _fade_tag(out[idx])
        elif light is not None:                   # 哪条线也不挨的零散文字：聚焦时同样调浅
            out[idx] = _fade_tag(out[idx])
    for v in anchors.values():                 # 关系线的中点：读图编号贴着线放，而不是飘在外框角上
        pts = v.pop("_pts", None)
        if pts and len(pts) > 1:
            segs = [(p, q, math.hypot(q[0] - p[0], q[1] - p[1])) for p, q in zip(pts, pts[1:])]
            half, run = sum(L for *_, L in segs) / 2, 0.0
            for p, q, L in segs:
                if run + L >= half and L > 0:
                    t = (half - run) / L
                    v["mid"] = [round(p[0] + t * (q[0] - p[0]), 1), round(p[1] + t * (q[1] - p[1]), 1)]
                    break
                run += L
    if content:                                # 换回原图坐标：x_src = (x_page − tx) / s
        xs0, ys0 = min(c[0] for c in content), min(c[1] for c in content)
        xs1, ys1 = max(c[2] for c in content), max(c[3] for c in content)
        rep["content"] = [(xs0 - tx) / s, (ys0 - ty) / s, (xs1 - tx) / s, (ys1 - ty) / s]
        rep["parts"] = [((c[0] - tx) / s, (c[1] - ty) / s, (c[2] - tx) / s, (c[3] - ty) / s, k_, t_, n_, key_)
                        for c, (k_, t_, n_, key_) in zip(content, parts)]
    for v in anchors.values():
        v.pop("_adopted", None)
    rep["anchors"] = [dict(v, box=[round(v["box"][0], 1), round(v["box"][1], 1), round(v["box"][2] - v["box"][0], 1),
                                   round(v["box"][3] - v["box"][1], 1)])
                      for v in anchors.values() if v["box"]]
    if fonts:
        rep["min_font"] = min(fonts)
        if rep["min_font"] < MIN_FONT - 1e-6:
            shown = math.floor(rep["min_font"] * 10) / 10      # 往下取一位：10.97 写成 10.9，不写成「11.0（低于 11）」
            rep["problems"].append(f"缩进这一格后最小的字只有 {shown:.1f}px（低于 {MIN_FONT:.0f}px）。"
                                   f"选中这张图，在右侧「读图」里切片只取要讲的几件事；或把图卡拉大"
                                   + ("。这是竖版的法律关系图：回 V3 加 --shape wide 重出横版，放进课件页字大得多"
                                      if H > W * 1.15 and box[2] > box[3] and 'data-role="node"' in svg and "data-ref=" in svg else ""))
    if not content and not rep["problems"] and not clip:
        rep["problems"].append("这张图里什么都没画（空的 SVG，或只有位图）：请回原模块重新出图")
    if "图片" in rep["dropped"]:
        rep["notes"].append("图里的位图（<image>）收不进可编辑的 PPTX，已略去")
    defs = []
    for mid_, faded in sorted(mk_used):
        ma, inner = markers[mid_]
        attrs = {k: v for k, v in ma.items() if k in ("refX", "refY", "orient", "markerUnits", "viewBox", "markerWidth",
                                                      "markerHeight")}
        if attrs.get("markerUnits") == "userSpaceOnUse":   # 用户坐标里的箭头：随整张图一起缩放
            mw, mh = _f(ma, "markerWidth", 3), _f(ma, "markerHeight", 3)
            attrs.setdefault("viewBox", f"0 0 {mw:g} {mh:g}")
            attrs["markerWidth"], attrs["markerHeight"] = f"{mw * s:.2f}", f"{mh * s:.2f}"
        if faded:
            inner = re.sub(r'((?:fill|stroke)=")(#[0-9A-Fa-f]{6})(")', lambda m_: m_.group(1) + fade_hex(m_.group(2)) + m_.group(3), inner)
        defs.append(f'<marker id="{mk_pre}{mid_}{"-f" if faded else ""}"'
                    + "".join(f' {k}="{html.escape(v, quote=True)}"' for k, v in attrs.items()) + f">{inner}</marker>")
    return "".join(out) + (f"<defs>{''.join(defs)}</defs>" if defs else ""), rep
