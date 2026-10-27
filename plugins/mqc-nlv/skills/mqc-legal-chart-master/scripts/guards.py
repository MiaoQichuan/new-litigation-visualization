# -*- coding: utf-8 -*-
"""出图前的守卫。全部读**产物**（最终 SVG），不读渲染器的中间变量。

每条守卫都必须能失败：tests/break_tests.py 逐条把渲染器改坏，确认守卫真的报错。

  G1  色板白名单　　　　　　SVG 里每一个颜色都在所选风格的白名单里
  G2  一图一处重音　　　　　带重音色的元素都标了 data-hero，且只属于同一个数据
  G3  最小字号　　　　　　　任何字不小于 11px
  G4  文字不出界、不互压　　按与 V1 同一把尺子量每段文字的外框
  G5  数值与几何成正比　　　柱长、条长、点位、带宽都由同一把比例尺算出；玫瑰按面积
  G6  纵轴从 0 起　　　　　　所有柱共用一条基线，且基线就是 0
  G7  数据一个不少　　　　　说明里的每个 id 都在图上有对应元素
  G8  图名照录　　　　　　　图上的图名与说明里的一字不差
  G9  角的风格　　　　　　　奇川风：所有填充形状都是贝塞尔小圆角，线头圆头；
                           歸藏风：一律直角、平头，不许出现圆角
                           两种风格下，细长条（桑基 / 汇入图的竖条、中位数竖线）与流带（桑基 / 汇入图）都是直角、平头
  G10 平面　　　　　　　　　不许透明、渐变、阴影；唯一例外是汇入图的流带（叠加处变深本身就是信息）
                           点阵（百点方阵的一格与图例）是方块模块：奇川风圆角为边长的 15%–30%，歸藏风直角
  G11 批注　　　　　　　　　条数与说明一致且不超过两条；旁白照录说明；引线落在目标上，
                           不穿过别的文字与数据形状
"""
import html
import math
import re

from kernel import text_w
from corners import flatten, bbox, area, MIN_TURN
import callout

_EL = re.compile(r"<(rect|circle|line|path|text)\b([^>]*?)(/?)>(?:([^<]*)</text>)?")
_AT = re.compile(r'([\w:-]+)="([^"]*)"')
FLOOR = 11.0


def parse(svg):
    els = []
    for m in _EL.finditer(svg):
        a = dict(_AT.findall(m.group(2)))
        a["_k"] = m.group(1)
        if m.group(1) == "text":
            a["_t"] = html.unescape(m.group(4) or "")
        els.append(a)
    W = float(re.search(r'<svg[^>]*width="([\d.]+)"', svg).group(1))
    H = float(re.search(r'<svg[^>]*height="([\d.]+)"', svg).group(1))
    return els, W, H


def _f(a, k, d=0.0):
    try:
        return float(a.get(k, d))
    except ValueError:
        return d


_ROT = re.compile(r"rotate\(\s*(-?[\d.]+)")


def _rot(t):
    m_ = _ROT.search(t.get("transform", ""))
    return float(m_.group(1)) if m_ else 0.0


def _tpoly(t):
    """文字外框的四个角。转过的字（发射扇顺着辐条写的标签）绕 (x, y) 转，与 SVG 一致。"""
    x0, y0, x1, y1 = _bbox0(t)
    pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    a = _rot(t)
    if not a:
        return pts
    px, py = _f(t, "x"), _f(t, "y")
    c, s_ = math.cos(math.radians(a)), math.sin(math.radians(a))
    return [(px + (x - px) * c - (y - py) * s_, py + (x - px) * s_ + (y - py) * c) for x, y in pts]


def _bbox(t):
    pts = _tpoly(t)
    return (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))


def _sat(pa, pb, pad=0.5):
    """两个凸多边形是否真的压在一起（分离轴）。pad：各收进去这么多再判，与轴对齐时的 0.5px 余量一致。"""
    for poly in (pa, pb):
        n = len(poly)
        for i in range(n):
            (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % n]
            ax, ay = y1 - y2, x2 - x1
            L = math.hypot(ax, ay) or 1.0
            ax, ay = ax / L, ay / L
            A = [px * ax + py * ay for px, py in pa]
            B = [px * ax + py * ay for px, py in pb]
            if max(A) - pad <= min(B) + pad or max(B) - pad <= min(A) + pad:
                return False
    return True


def _bbox0(t):
    fs = _f(t, "font-size")
    mono = "Mono" in t.get("font-family", "") or "Consolas" in t.get("font-family", "")
    w = text_w(t["_t"], fs, mono=mono, track=_f(t, "letter-spacing"))
    x = _f(t, "x")
    anchor = t.get("text-anchor", "start")
    if anchor == "middle":
        x -= w / 2
    elif anchor == "end":
        x -= w
    y = _f(t, "y")
    return (x, y - fs * 0.88, x + w, y + fs * 0.17)


MARK_ROLES = ("bar", "hbar", "step", "total", "from", "to", "span", "sector", "dot", "point", "node", "flow",
              "stage", "bubble", "spoke", "hub", "range", "wedge")


def _shape_box(a):
    if a["_k"] == "circle":
        cx, cy, r = _f(a, "cx"), _f(a, "cy"), _f(a, "r")
        return (cx - r, cy - r, cx + r, cy + r)
    if a["_k"] == "line":
        x1, y1, x2, y2 = _f(a, "x1"), _f(a, "y1"), _f(a, "x2"), _f(a, "y2")
        return (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))
    if a["_k"] == "path":
        return bbox(flatten(a.get("d", "")))
    if a["_k"] == "rect":
        x, y = _f(a, "x"), _f(a, "y")
        return (x, y, x + _f(a, "width"), y + _f(a, "height"))
    return _bbox(a)


def target_box(els, tid):
    """目标数据在图上的外框：同一个 id 的数据形状，连同它的数值标签。
    批注指的是「这一个数据」，引线落在柱上或落在它的数上都算指对了。"""
    bs = [_shape_box(a) for a in els if a.get("data-id") == str(tid) and
          (a.get("data-role") in MARK_ROLES or (a["_k"] == "text" and a.get("data-role") == "value"))]
    if not bs:
        return None
    return (min(b[0] for b in bs), min(b[1] for b in bs), max(b[2] for b in bs), max(b[3] for b in bs))


def obstacles(els, tid):
    """引线不许穿过的东西：所有文字（批注栏里别的批注也算），以及目标以外的数据形状与连线。"""
    out = []
    for a in els:
        role = a.get("data-role")
        if role in callout.CROSSABLE:
            continue
        if a["_k"] == "text":
            out.append((_bbox(a), f"文字「{a['_t'][:8]}」"))
        elif a.get("data-id") == str(tid):
            continue
        elif a["_k"] in ("path", "circle", "line", "rect"):
            if role == "leader":
                continue                          # 引线之间另用 too_close 查
            if a["_k"] == "path" and a.get("fill", "none") == "none" and role not in ("link", "span"):
                continue
            out.append((_shape_box(a), f"{role or a['_k']}（{a.get('data-id', '')}）"))
    return out


def _rounded(d):
    """path 的每一个真正的角（直线段之间转角 > MIN_TURN 的顶点）都必须由一段曲线接替。

    rounded_d 把每个角写成「L 到切点 → C 到另一切点」，所以直线顶点处不会出现急转。
    这里只看 M / L 顶点：若相邻两条直线段在某个 L 顶点上直接急转，那就是一个没磨的角。"""
    toks = re.findall(r"([MLCZ])([^MLCZ]*)", d)
    if not any(c == "C" for c, _ in toks):
        return False
    seq = []                                   # (kind, point)
    for c, body in toks:
        nums = [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", body)]
        if c in "ML":
            for i in range(0, len(nums) - 1, 2):
                seq.append(("L", (nums[i], nums[i + 1])))
        elif c == "C":
            seq.append(("C", (nums[-2], nums[-1])))
    n = len(seq)
    for i in range(n):
        kind, v = seq[i]
        if kind != "L":
            continue
        pk, p = seq[i - 1]
        nk, q = seq[(i + 1) % n]
        if nk == "C" or pk == "C":
            continue                            # 这个点是切点，后面接着曲线
        ax, ay, bx, by = v[0] - p[0], v[1] - p[1], q[0] - v[0], q[1] - v[1]
        la, lb = math.hypot(ax, ay), math.hypot(bx, by)
        if la < 1e-6 or lb < 1e-6:
            continue
        c = max(-1.0, min(1.0, (ax * bx + ay * by) / (la * lb)))
        if math.acos(c) > MIN_TURN + 1e-6:
            return False
    return True


def check(svg, m, chart, pal, whitelist):
    """返回问题列表；空列表 = 全过。"""
    els, W, H = parse(svg)
    bad = []

    # G1 色板白名单
    for a in els:
        for key in ("fill", "stroke"):
            c = a.get(key)
            if c and c.startswith("#") and c.upper() not in whitelist:
                bad.append(f"G1 色板：{a['_k']} 用了 {c}，不在{pal['style']}的白名单里")
    for c in re.findall(r'fill="(#[0-9A-Fa-f]{6})"', svg):
        if c.upper() not in whitelist:
            bad.append(f"G1 色板：{c} 不在白名单里")
            break

    # G2 一图一处重音
    acc = pal["accent"].upper()
    hero_ids = {a.get("data-hero-of") or a.get("data-id") for a in els if a.get("data-hero") == "1"}
    if len(hero_ids) > 1:
        bad.append(f"G2 重音：有 {len(hero_ids)} 个数据被标成重音（{'、'.join(sorted(map(str, hero_ids)))}），只许一个")
    for a in els:
        uses = any((a.get(k) or "").upper() == acc for k in ("fill", "stroke"))
        if uses and a.get("data-hero") != "1":
            bad.append(f"G2 重音：一个没有标 data-hero 的 {a['_k']}（{a.get('data-role')}）用了重音色")
            break
    if m.get("emphasis") is None and hero_ids:
        bad.append("G2 重音：说明里没有指定 emphasis，图上却出现了重音")
    if m.get("emphasis") is not None and not hero_ids and chart != "strip":
        bad.append(f"G2 重音：说明指定了 emphasis={m['emphasis']!r}，图上没有画出来")

    # G3 最小字号 / G4 文字外框
    texts = [a for a in els if a["_k"] == "text"]
    boxes = []
    for t in texts:
        fs = _f(t, "font-size")
        if fs < FLOOR - 1e-6:
            bad.append(f"G3 字号：「{t['_t'][:12]}」只有 {fs:.1f}px，低于 {FLOOR:.0f}px")
        b = _bbox(t)
        if b[0] < -0.5 or b[1] < -0.5 or b[2] > W + 0.5 or b[3] > H + 0.5:
            bad.append(f"G4 出界：「{t['_t'][:12]}」越出画布")
        boxes.append((b, t))
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            (a, ta), (b, tb) = boxes[i], boxes[j]
            if a[0] < b[2] - 0.5 and b[0] < a[2] - 0.5 and a[1] < b[3] - 0.5 and b[1] < a[3] - 0.5:
                if (_rot(ta) or _rot(tb)) and not _sat(_tpoly(ta), _tpoly(tb)):
                    continue                     # 转过的字：外接矩形碰了，真正的字框没碰
                bad.append(f"G4 互压：「{ta['_t'][:10]}」与「{tb['_t'][:10]}」重叠")

    # G5 数值与几何成正比 / G6 基线
    marks = [a for a in els if a.get("data-value") is not None and a.get("data-role") in
             ("bar", "hbar", "sector", "from", "to", "point", "flow", "node", "dot")]
    ratios = []
    def box(a):
        return bbox(flatten(a.get("d", "")))

    if chart == "bar":
        bases = []
        for a in marks:
            v = _f(a, "data-value")
            x0, y0, x1, y1 = box(a)
            bases.append(y1)
            if v > 0:
                ratios.append((y1 - y0) / v)
        if bases and max(bases) - min(bases) > 0.25:      # 坐标写到两位小数，留 0.25px 的舍入余量
            bad.append(f"G6 基线：柱底不在同一条线上（{min(bases):.2f} 到 {max(bases):.2f}）")
        zero = [a for a in els if a.get("data-role") == "axis"]
        if not zero or _f(zero[0], "data-value", -1) != 0:
            bad.append("G6 基线：没有画在 0 上的基线")
        elif bases and abs(_f(zero[0], "y1") - min(bases)) > 0.6:
            bad.append("G6 基线：柱底不在 0 线上——纵轴被截断了")
    elif chart == "hbar":
        starts = []
        for a in marks:
            v = _f(a, "data-value")
            x0, y0, x1, y1 = box(a)
            starts.append(x0)
            if v > 0:
                ratios.append((x1 - x0) / v)
        if starts and max(starts) - min(starts) > 0.25:
            bad.append("G6 基线：横条不是从同一条线起画的")
    elif chart == "rose":
        for a in marks:
            v = _f(a, "data-value")
            cx, cy = _f(a, "data-cx"), _f(a, "data-cy")
            r = max(math.hypot(x - cx, y - cy) for x, y in flatten(a.get("d", "")))
            if v > 0:
                ratios.append(r * r / v)          # 面积编码：r² ∝ v
    elif chart in ("dumbbell", "strip"):
        for a in marks:
            v = _f(a, "data-value")
            if v > 0:
                ratios.append((_f(a, "cx") - _f(a, "data-x0")) / v)
    elif chart == "waterfall":
        # 每根柱的上下沿必须正好是加减前后的累计值：起点与终点从 0 起，中间各级悬浮
        bars = [a for a in els if a.get("data-role") in ("total", "step")]
        base = [a for a in els if a.get("data-role") == "axis"]
        if not base or _f(base[0], "data-value", -1) != 0:
            bad.append("G6 基线：逐级加减没有画在 0 上的基线")
        else:
            y0 = _f(base[0], "y1")
            sc = [ (box(a)[3] - box(a)[1]) / abs(_f(a, "data-value")) for a in bars if a.get("data-role") == "total"
                   and _f(a, "data-value") > 0]
            s = sum(sc) / len(sc) if sc else 0
            for a in bars:
                lo, hi = sorted((_f(a, "data-from"), _f(a, "data-to")))
                bx = box(a)
                if abs((y0 - bx[3]) - lo * s) > 0.6 or abs((y0 - bx[1]) - hi * s) > 0.6:
                    bad.append(f"G5 比例：「{a.get('data-id')}」这一级的上下沿不在加减前后的累计值上")
                    break
                if abs(_f(a, "data-value")) > 0:
                    ratios.append((bx[3] - bx[1]) / abs(_f(a, "data-value")))
    elif chart in ("sankey", "ribbon"):
        flow_r = []
        for a in marks:
            v = _f(a, "data-value")
            if a.get("data-role") == "node":
                x0, y0, x1, y1 = box(a)
                ratios.append((y1 - y0) / v)
            else:
                # 流带上下两条曲线竖直相距处处相等，所以 面积 / 水平跨度 = 带宽。
                # 四个小圆角各少一点点面积，量出来略小，单独给 1.5% 的余量。
                pts = flatten(a.get("d", ""))
                x0, _, x1, _ = bbox(pts)
                flow_r.append(area(pts) / (x1 - x0) / v)
        if flow_r and ratios:
            ref = sum(ratios) / len(ratios)
            off = [f for f in flow_r if abs(f - ref) > 0.015 * ref + 0.002]
            if off:
                bad.append(f"G5 比例：桑基流带的宽度与数值不成正比（{off[0]:.4f}，应为 {ref:.4f}）")
    elif chart == "waffle":
        want = dict(zip([i["id"] for i in m["data"]["items"]], m["_derived"]["dots"]))
        got = {}
        for a in els:
            if a.get("data-role") == "dot":
                got[a.get("data-id")] = got.get(a.get("data-id"), 0) + 1
        for k_, v in want.items():
            if got.get(str(k_), 0) != v:
                bad.append(f"G5 比例：「{k_}」应有 {v} 格，图上 {got.get(str(k_), 0)} 个")
    elif chart == "funnel":
        # 条宽 ∝ 件数，且各级共用一条中线（漏斗的「基线」）
        centers = []
        for a in els:
            if a.get("data-role") != "stage" or a.get("data-value") is None:
                continue
            v = _f(a, "data-value")
            x0, y0, x1, y1 = box(a)
            centers.append((x0 + x1) / 2)
            if v > 0:
                ratios.append((x1 - x0) / v)
        if centers and max(centers) - min(centers) > 0.25:
            bad.append("G6 基线：漏斗的各级不在同一条中线上")
    elif chart in ("matrix", "fan", "converge"):
        # 面积编码：气泡、端点圆、枢纽的面积 ∝ 数值（半径取平方根）。圆按 πr² 量，
        # 奇川风的卵石形气泡按回读出来的轮廓面积量——形状可以「手作」，面积不能差。
        areas = []                          # (面积, 数值, 等效半径)
        for a in els:
            if a.get("data-role") not in ("bubble", "hub") or a.get("data-value") is None:
                continue
            v = _f(a, "data-value")
            if v <= 0:
                continue
            if a["_k"] == "circle":
                ar = math.pi * _f(a, "r") ** 2
            else:
                ar = area(flatten(a.get("d", "")))
            areas.append((ar, v, math.sqrt(ar / math.pi)))
        if areas:
            # 比例尺取最大的那一个（坐标写到两位小数，越大越准）；每一个都要落在它的 1.2% 之内，
            # 外加坐标舍入能造成的那一点点（周长 × 0.006px）——很小的气泡不因舍入被误拦
            ar0, v0, _ = max(areas, key=lambda t: t[0])
            ref = ar0 / v0
            for ar, v, rr in areas:
                if abs(ar - ref * v) > 0.012 * ref * v + 2 * math.pi * rr * 0.006 + 0.02:
                    bad.append(f"G5 比例：面积与数值不成正比（数值 {v:g} 的面积 {ar:.1f}，按比例尺应为 {ref * v:.1f}）")
                    break
        if chart == "fan":
            # 辐条长 ∝ 数值；每根辐条都在从同一个根射出的那条射线上，起点离根 data-r0（0.11.0 起点可以在圆外）
            for a in els:
                if a.get("data-role") == "spoke" and a.get("data-value") is not None and _f(a, "data-value") > 0:
                    x1, y1, x2, y2 = _f(a, "x1"), _f(a, "y1"), _f(a, "x2"), _f(a, "y2")
                    L = math.hypot(x2 - x1, y2 - y1)
                    ratios.append(L / _f(a, "data-value"))
                    ox_, oy_ = _f(a, "data-ox"), _f(a, "data-oy")
                    cross = (x1 - ox_) * (y2 - oy_) - (y1 - oy_) * (x2 - ox_)
                    far = math.hypot(x2 - ox_, y2 - oy_) or 1.0
                    if abs(math.hypot(x1 - ox_, y1 - oy_) - _f(a, "data-r0")) > 0.06 or abs(cross) / far > 0.06:
                        bad.append("G6 基线：发射扇的辐条不是从同一个根射出的")
                        break
    elif chart == "cascade":
        # 一格 = per：每一列的格数等于 数值 ÷ per 四舍五入；全图的格一样大、同一列等距叠放
        want = m["_derived"]["cells"]
        cols, sides = {}, []
        for a in els:
            if a.get("data-role") == "dot":
                cols.setdefault(a.get("data-id"), []).append(a)
                sides.append(_f(a, "data-w"))
        for k_, v in want.items():
            got = len(cols.get(str(k_), []))
            if got != v:
                bad.append(f"G5 比例：「{k_}」应有 {v} 格，图上 {got} 格")
        if sides and max(sides) - min(sides) > 0.02:
            bad.append("G5 比例：点阵阶梯的格大小不一")
        for k_, arr in cols.items():
            ys_ = sorted(_f(a, "data-y") for a in arr)
            gaps = [b - a for a, b in zip(ys_, ys_[1:])]
            xs_ = {round(_f(a, "data-x"), 2) for a in arr}
            if (gaps and max(gaps) - min(gaps) > 0.05) or len(xs_) > 1:
                bad.append(f"G5 比例：「{k_}」这一列的格没有等距叠放")
                break
    elif chart == "lineage":
        # 横向位置 ∝ 年份：通过、修改、废止的标记与年份同一把尺；生命线两端也在这把尺上
        for a in els:
            role = a.get("data-role")
            if role in ("start", "revise", "end"):
                x = _f(a, "cx") if a["_k"] == "circle" else _f(a, "x1")
                pairs_ = [(x, _f(a, "data-value"))]
            elif role == "life":
                pairs_ = [(_f(a, "x1"), _f(a, "data-start")), (_f(a, "x2"), _f(a, "data-last"))]
            else:
                continue
            for x, yr in pairs_:
                t0, x0 = _f(a, "data-t0"), _f(a, "data-x0")
                if abs(yr - t0) < 1e-9:
                    if abs(x - x0) > 0.05:
                        bad.append(f"G5 比例：「{a.get('data-id')}」{yr:g} 年的位置不在年份尺上")
                else:
                    ratios.append((x - x0) / (yr - t0))
    elif chart == "interval":
        # 胶囊的上沿 = to、下沿 = from，与 0 线同一把尺；太窄画成一粒的，只核中心。
        # 按像素核（0.6px），不按比值：0.3 这种贴着 0 的数，坐标舍入 0.005px 就能让比值差出 2%
        axis0 = [a for a in els if a.get("data-role") == "axis" and _f(a, "data-value", -1) == 0]
        if not axis0:
            bad.append("G6 基线：区间胶囊没有画 0 线")
        else:
            y0 = _f(axis0[0], "y1")
            pts_ = []                                  # (量到的 y, 数值, id)
            for a in els:
                if a.get("data-role") == "range":
                    _, top, _, bot = box(a)
                    if a.get("data-short") == "1":
                        pts_.append(((top + bot) / 2, (_f(a, "data-from") + _f(a, "data-to")) / 2, a.get("data-id")))
                    else:
                        pts_ += [(top, _f(a, "data-to"), a.get("data-id")), (bot, _f(a, "data-from"), a.get("data-id"))]
                elif a.get("data-role") == "mid":
                    pts_.append((_f(a, "cy"), _f(a, "data-value"), a.get("data-id")))
            far = max(pts_, key=lambda t: abs(t[1]), default=None)
            ref = (y0 - far[0]) / far[1] if far and abs(far[1]) > 1e-12 else 0.0
            for yy, v, id_ in pts_:
                if abs((y0 - yy) - v * ref) > 0.6 + 0.002 * abs(v * ref):
                    bad.append(f"G5 比例：「{id_}」的 {v:g} 不在纵轴的比例尺上（差 {abs((y0 - yy) - v * ref):.1f}px）")
                    break
    elif chart == "radpie":
        # 角度 ∝ 占比（按回读的面积反算角度）；从内圈量起的长度 ∝ size；各扇区同心、同一个内圈
        wedges = [a for a in els if a.get("data-role") == "wedge"]
        cen = {(round(_f(a, "data-cx"), 2), round(_f(a, "data-cy"), 2), round(_f(a, "data-r0"), 2)) for a in wedges}
        if len(cen) > 1:
            bad.append("G6 基线：双读饼的扇区不同心或内圈不一")
        for a in wedges:
            pts = flatten(a.get("d", ""))
            cx, cy, r0 = _f(a, "data-cx"), _f(a, "data-cy"), _f(a, "data-r0")
            ds = [math.hypot(x - cx, y - cy) for x, y in pts]
            R, rin = max(ds), min(ds)
            if abs(rin - r0) > 0.6:
                bad.append(f"G6 基线：「{a.get('data-id')}」不是从内圈量起的")
                break
            ratios.append((R - r0) / _f(a, "data-size"))
            th = 2 * area(pts) / (R * R - r0 * r0)
            want = _f(a, "data-value") / _f(a, "data-total") * 2 * math.pi
            if abs(th - want) > 0.015 * want + 0.01:
                bad.append(f"G5 比例：「{a.get('data-id')}」的角度与占比不符（{math.degrees(th):.1f}°，应为 {math.degrees(want):.1f}°）")
                break
    if ratios:
        lo, hi = min(ratios), max(ratios)
        if hi - lo > max(0.02, 0.003 * hi):
            bad.append(f"G5 比例：几何与数值不成正比（比值 {lo:.4f} 到 {hi:.4f}）")

    # G9 角的风格
    if pal.get("corner", 0) <= 0:
        for a in els:
            if a["_k"] == "path" and a.get("fill", "none") != "none" and "C" in a.get("d", ""):
                bad.append(f"G9 直角：{pal['style']}不用圆角，{a.get('data-role') or '一个形状'}却磨圆了")
                break
            if a["_k"] == "line" and a.get("stroke-linecap") == "round":
                bad.append(f"G9 直角：{pal['style']}的线头应是平头")
                break
    for a in els:
        if a.get("data-role") in ("node", "median", "flow") and a.get("data-square") != "1":
            bad.append(f"G9 长条：{a.get('data-role')}（{a.get('data-id', '')}）是长条，角不该磨圆")
            break
    for a in (els if pal.get("corner", 0) > 0 else []):
        role = a.get("data-role")
        if a.get("data-square") == "1" and role in ("node", "median", "flow"):
            continue
        if a["_k"] == "rect" and role not in ("paper", "texture"):
            bad.append(f"G9 尖角：{role or '一个元素'} 是直角矩形，没有圆角")
        elif a["_k"] == "path" and a.get("fill", "none") != "none":
            if not _rounded(a.get("d", "")):
                bad.append(f"G9 尖角：{role or '一个形状'}（{a.get('data-id', '')}）有没磨圆的尖角")
        elif a["_k"] == "line" and a.get("stroke-linecap") != "round":
            bad.append(f"G9 尖角：{role or '一条线'} 的线头是方的")
    want_r = pal.get("module", 0.0)
    for a in els:
        if a.get("data-role") in ("dot", "key", "empty") and chart in ("waffle", "cascade"):
            if a["_k"] != "path" or a.get("data-module") != "1":
                bad.append(f"G9 方块：{'百点方阵' if chart == 'waffle' else '点阵阶梯'}的{a.get('data-role')}应是方块模块，图上是 {a['_k']}")
                break
            w_, h_, r_ = _f(a, "data-w"), _f(a, "data-h"), _f(a, "data-r")
            if abs(w_ - h_) > 0.01:
                bad.append("G9 方块：点阵的格不是正方形")
                break
            if want_r <= 0 and r_ > 0:
                bad.append(f"G9 方块：{pal['style']}的方块应是直角")
                break
            if want_r > 0 and not 0.15 * w_ - 0.01 <= r_ <= 0.30 * w_ + 0.01:
                bad.append(f"G9 方块：圆角 {r_:.2f} 不在边长 {w_:.2f} 的 15%–30% 之间（太尖不像模块，太圆就成了圆点）")
                break
    if "<polygon" in svg or "<polyline" in svg:
        bad.append("G9 尖角：出现了 polygon / polyline")

    # G10 平面
    for a in els:
        if any(k in a for k in ("opacity", "fill-opacity", "filter")) or "Gradient" in svg:
            if not (chart == "ribbon" and a.get("data-role") == "flow" and "filter" not in a
                    and "opacity" not in a and "Gradient" not in svg):
                bad.append(f"G10 平面：{a.get('data-role') or a['_k']} 用了透明或特效，只有汇入图的流带可以半透明")
                break

    # G11 批注
    ann = m.get("annotations") or []
    leaders = [a for a in els if a.get("data-role") == "leader"]
    if len(leaders) != len(ann) or len(ann) > 2:
        bad.append(f"G11 批注：说明里 {len(ann)} 条批注，图上 {len(leaders)} 条引线（且最多两条）")
    for a in ann:
        tid = str(a["target"])
        drawn = "".join(t["_t"] for t in texts if t.get("data-role") == "annotation" and t.get("data-id") == tid)
        if drawn != a["text"]:
            bad.append(f"G11 批注：图上是「{drawn}」，说明里是「{a['text']}」")
        ld = [x for x in leaders if x.get("data-id") == tid]
        tb = target_box(els, tid)
        if not ld or tb is None:
            bad.append(f"G11 批注：「{tid}」的引线或目标不在图上")
            continue
        seg = callout.parse_leader(ld[0].get("d", ""))
        if seg is None:
            bad.append(f"G11 批注：「{tid}」的引线不是一段三次贝塞尔曲线")
            continue
        end = seg[3]
        if not (tb[0] - 6 <= end[0] <= tb[2] + 6 and tb[1] - 6 <= end[1] <= tb[3] + 6):
            bad.append(f"G11 批注：「{tid}」的引线没有落在目标上")
        pts = callout.cubic(*seg)
        hit = callout.leader_hits(pts, obstacles(els, tid))
        if hit:
            bad.append(f"G11 批注：「{tid}」的引线穿过了{hit}")
        for o in leaders:
            if o.get("data-id") != tid and o.get("data-id", "") > tid:
                os_ = callout.parse_leader(o.get("d", ""))
                if os_ and callout.too_close(pts, callout.cubic(*os_)):
                    bad.append(f"G11 批注：「{tid}」与「{o.get('data-id')}」的引线挨得太近，分不清各指哪里")

    # G7 数据一个不少
    present = {a.get("data-id") for a in els if a.get("data-id") is not None}
    for i in m["_derived"]["ids"]:
        if str(i) not in present:
            bad.append(f"G7 遗漏：数据「{i}」在图上没有对应元素")

    # G8 图名照录
    title = m["title"]
    drawn = "".join(t["_t"] for t in texts if t.get("data-role") == "title")
    if drawn != title:
        bad.append(f"G8 图名：图上是「{drawn}」，说明里是「{title}」")
    return bad
