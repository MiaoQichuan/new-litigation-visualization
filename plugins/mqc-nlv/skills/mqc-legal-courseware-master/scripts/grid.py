# -*- coding: utf-8 -*-
"""磁吸网格：一页 12 栏 × 6 行，模块只落在格子上。

借鉴 M3E Canvas（lnkiai，MIT）的做法，按课件重写：
  * 零件化：每种模块有自己的样子、最小尺寸和默认尺寸；
  * 磁吸：模块落点吸到最近的格子，尺寸按格子跳，放不下就找最近的空位，再放不下就不让落；
  * 连成一组：相邻的同类卡片（等高并排，或等宽上下叠）连成一组，相接处间距收窄、内角收小，外角不变；
  * 整理：按规则上推补缝、并排等高、把底边和右边的空白补齐。只动位置和大小，不动内容。

这里只算几何，不画图；拼页在 deck.py，编辑器（web/studio.html）里有同一套规则的 JS 版，
两边由回归里的「规则对照」核对。
"""

COLS, ROWS = 12, 6
MX, MY = 48, 56            # 页边距：左右 48、上下 56
COL, ROW = 84, 88          # 一栏宽、一行高
GUT = 16                   # 模块之间的间距（呼吸）
FUSE_GAP = 4               # 连成一组的卡片之间收窄到 4px
W, H = 1280, 720
assert MX * 2 + COLS * COL + (COLS - 1) * GUT == W
assert MY * 2 + ROWS * ROW + (ROWS - 1) * GUT == H

# 模块：中文名、最小 / 默认尺寸（栏 × 行）、默认外观、可连成一组的家族、最大行数
TYPES = {
    "title":   {"zh": "标题",     "min": (3, 1), "default": (12, 1), "tone": "bare",    "family": None,   "maxh": 3},
    "text":    {"zh": "正文",     "min": (3, 2), "default": (4, 3),  "tone": "card",    "family": "text"},
    "bullets": {"zh": "要点", "group": "整套课件",     "min": (3, 2), "default": (4, 3),  "tone": "card",    "family": "text"},
    "stat":    {"zh": "大数字",   "min": (2, 2), "default": (3, 2),  "tone": "card",    "family": "stat"},
    "step":    {"zh": "编号卡",   "min": (3, 2), "default": (4, 3),  "tone": "card",    "family": "step"},
    "quote":   {"zh": "金句", "group": "整套课件",     "min": (4, 2), "default": (6, 3),  "tone": "card",    "family": None},
    "chart":   {"zh": "V6 图表",  "min": (6, 4), "default": (8, 5),  "tone": "outline", "family": None},
    "figure":  {"zh": "V1–V5 图", "min": (4, 3), "default": (8, 5),  "tone": "outline", "family": None},
    "note":    {"zh": "注释",     "min": (2, 1), "default": (6, 1),  "tone": "bare",    "family": None,   "maxh": 1},
    "conclusion": {"zh": "一句话结论", "min": (4, 1), "default": (8, 1), "tone": "bare", "family": None,   "maxh": 2},
    # —— 法律内容卡 ——
    "statute": {"zh": "法条",     "min": (4, 2), "default": (6, 2),  "tone": "card",    "family": "law"},
    "holding": {"zh": "裁判要旨", "min": (4, 2), "default": (6, 3),  "tone": "card",    "family": "law"},
    "case":    {"zh": "案例",     "min": (3, 2), "default": (4, 3),  "tone": "card",    "family": "case"},
    "issue":   {"zh": "争议焦点", "min": (3, 2), "default": (4, 3),  "tone": "card",    "family": "issue"},
    "risk":    {"zh": "风险提示", "min": (3, 2), "default": (4, 2),  "tone": "card",    "family": "risk"},
    "evidence": {"zh": "证据",    "min": (5, 2), "default": (7, 4),  "tone": "card",    "family": None},
    # —— 律所名片 ——
    "logo":    {"zh": "Logo",     "min": (1, 1), "default": (2, 1),  "tone": "bare",    "family": None,   "maxh": 2},
    "profile": {"zh": "介绍",     "min": (4, 3), "default": (7, 5),  "tone": "card",    "family": None},
    "contact": {"zh": "联系方式", "min": (3, 1), "default": (4, 2),  "tone": "card",    "family": None},
}
TONES = {"card": "卡片", "accent": "重音卡", "outline": "描边", "bare": "无底"}
NO_ACCENT = {"chart", "figure", "title", "note", "conclusion", "quote", "statute", "holding", "case", "evidence", "logo", "profile",
             "contact"}     # 图压在重音色上看不清；标题与注释不做卡片


# ------------------------------------------------------------- 版面：铺满全屏 / 预留位置
# 作者定的（2026-10-05）：图表页要能粘进律所自己的课件。两种版面——
#   full     铺满全屏：页边距 48 / 56，网格就是上面这些常数；
#   reserve  预留位置：上、下、左、右各留多少（设计像素），让出律所模板的 Logo、天头地脚、侧边条；
#            网格仍是 12 栏 × 6 行、间距不变，只是每格按剩下的内容区算，整页出血的图也只铺满内容区。
MIN_COL, MIN_ROW = 40, 56          # 内容区再小，卡片里的字就排不下了
MIN_INSET = 24                      # 预留位置时离页边至少留这么多


def frame_insets(frame):
    """版面 → (上, 右, 下, 左) 留白。frame 为 None 或 mode=full 时就是默认页边距。"""
    if not frame or frame.get("mode", "full") == "full":
        return (MY, MX, MY, MX)
    return tuple(float(frame[k]) for k in ("top", "right", "bottom", "left"))


def check_frame(frame):
    """校验版面设定。返回问题列表。"""
    if frame is None:
        return []
    if not isinstance(frame, dict) or frame.get("mode", "full") not in ("full", "reserve"):
        return ["版面（frame）的 mode 只能是 full（铺满全屏）或 reserve（预留位置）"]
    if frame.get("mode", "full") == "full":
        return []
    bad = []
    for k, zh in (("top", "上"), ("right", "右"), ("bottom", "下"), ("left", "左")):
        v = frame.get(k)
        if not isinstance(v, (int, float)) or isinstance(v, bool) or v < 0:
            bad.append(f"预留位置的「{zh}」要是不小于 0 的数（设计像素，整页 {W}×{H}）")
    if bad:
        return bad
    t, r, b, l_ = frame_insets(frame)
    col = (W - l_ - r - (COLS - 1) * GUT) / COLS
    row = (H - t - b - (ROWS - 1) * GUT) / ROWS
    if col < MIN_COL or row < MIN_ROW:
        need_w = COLS * MIN_COL + (COLS - 1) * GUT
        need_h = ROWS * MIN_ROW + (ROWS - 1) * GUT
        bad.append(f"预留得太多，内容区只剩 {W - l_ - r:.0f}×{H - t - b:.0f}：至少要 {need_w}×{need_h}，"
                   f"卡片里的字才排得下")
    return bad


def geom(frame=None):
    """版面 → 网格几何（与编辑器 grid.js 的 geom 同一套算法）。"""
    t, r, b, l_ = frame_insets(frame)
    full = not frame or frame.get("mode", "full") == "full"
    return {"COLS": COLS, "ROWS": ROWS, "GUT": GUT, "FUSE_GAP": FUSE_GAP, "W": W, "H": H,
            "MX": l_, "MY": t, "COL": (W - l_ - r - (COLS - 1) * GUT) / COLS,
            "ROW": (H - t - b - (ROWS - 1) * GUT) / ROWS,
            "BLEED": [0, 0, W, H] if full else [l_, t, W - l_ - r, H - t - b]}


DEFAULT = geom(None)


def px(m, g=None):
    """模块 → 页面上的 (x, y, w, h)（未计连组的外扩）。g：网格几何（geom 的结果），不给就是铺满全屏。
    整页出血（bleed）的图占满整页；预留位置时只占满内容区。"""
    g = g or DEFAULT
    if m.get("bleed"):
        return tuple(g["BLEED"])
    return (g["MX"] + m["x"] * (g["COL"] + GUT), g["MY"] + m["y"] * (g["ROW"] + GUT),
            m["w"] * g["COL"] + (m["w"] - 1) * GUT, m["h"] * g["ROW"] + (m["h"] - 1) * GUT)


def tone_of(m):
    if m.get("bleed"):
        return "bare"
    return m.get("tone") or TYPES[m["type"]]["tone"]


def overlaps(a, b):
    return a["x"] < b["x"] + b["w"] and b["x"] < a["x"] + a["w"] and a["y"] < b["y"] + b["h"] and b["y"] < a["y"] + a["h"]


def check_module(m):
    """单个模块的几何。返回问题列表。"""
    t = TYPES.get(m.get("type"))
    if not t:
        return [f"模块 {m.get('id')!r} 的类型 {m.get('type')!r} 不认识；可选：{'、'.join(TYPES)}"]
    bad = []
    for k in ("x", "y", "w", "h"):
        if not isinstance(m.get(k), int) or isinstance(m.get(k), bool):
            bad.append(f"模块 {m.get('id')!r} 的 {k} 要是整数（格子数）")
    if bad:
        return bad
    if m["x"] < 0 or m["y"] < 0 or m["x"] + m["w"] > COLS or m["y"] + m["h"] > ROWS:
        bad.append(f"{t['zh']}「{m.get('id')}」出了页面：网格是 {COLS} 栏 × {ROWS} 行")
    mw, mh = t["min"]
    if m["w"] < mw or m["h"] < mh:
        bad.append(f"{t['zh']}「{m.get('id')}」太小（{m['w']}×{m['h']}）：最小 {mw} 栏 × {mh} 行")
    if "maxh" in t and m["h"] > t["maxh"]:
        bad.append(f"{t['zh']}「{m.get('id')}」最多 {t['maxh']} 行高")
    tone = m.get("tone")
    if tone is not None and tone not in TONES:
        bad.append(f"模块「{m.get('id')}」的外观 {tone!r} 不认识；可选：{'、'.join(TONES)}")
    if m.get("bleed") and (m["type"] not in ("chart", "figure") or (m["w"], m["h"]) != (COLS, ROWS)):
        bad.append(f"整页出血（bleed）只给占满整页（{COLS}×{ROWS}）的图表卡或图卡")
    if "locked" in m and not isinstance(m["locked"], bool):
        bad.append(f"模块「{m.get('id')}」的 locked 要是 true / false")
    if tone == "accent" and m["type"] in NO_ACCENT:
        bad.append(f"{t['zh']}不做重音卡：重音卡只给大数字、编号卡、正文、要点")
    return bad


def check_slide(mods):
    bad = []
    ids = set()
    for m in mods:
        if not isinstance(m, dict):
            bad.append("模块要是一个对象")
            continue
        if not m.get("id") or m["id"] in ids:
            bad.append(f"模块 id {m.get('id')!r} 缺失或重复")
        ids.add(m.get("id"))
        bad += check_module(m)
    if bad:
        return bad
    for i, a in enumerate(mods):
        for b in mods[i + 1:]:
            if overlaps(a, b):
                bad.append(f"「{a['id']}」与「{b['id']}」重叠：一个格子只放一个模块")
    return bad


# ------------------------------------------------------------- 连成一组
def _joinable(a, b):
    fa, fb = TYPES[a["type"]]["family"], TYPES[b["type"]]["family"]
    return (fa and fa == fb and tone_of(a) == tone_of(b) and tone_of(a) != "bare"
            and a.get("join", True) is not False and b.get("join", True) is not False)


def fusion(mods):
    """每个模块哪几条边与邻居连成一组：{id: {"l","r","t","b"} 的子集}；以及组（id 列表）。"""
    sides = {m["id"]: set() for m in mods}
    parent = {m["id"]: m["id"] for m in mods}

    def find(k):
        while parent[k] != k:
            parent[k] = parent[parent[k]]
            k = parent[k]
        return k

    for a in mods:
        for b in mods:
            if a is b or not _joinable(a, b):
                continue
            if a["y"] == b["y"] and a["h"] == b["h"] and a["x"] + a["w"] == b["x"]:
                sides[a["id"]].add("r")
                sides[b["id"]].add("l")
                parent[find(a["id"])] = find(b["id"])
            if a["x"] == b["x"] and a["w"] == b["w"] and a["y"] + a["h"] == b["y"]:
                sides[a["id"]].add("b")
                sides[b["id"]].add("t")
                parent[find(a["id"])] = find(b["id"])
    groups = {}
    for m in mods:
        groups.setdefault(find(m["id"]), []).append(m["id"])
    return sides, [g for g in groups.values() if len(g) > 1]


def card_rect(m, fused_sides, g=None):
    """连组的边向缝里外扩，使组内间距收到 FUSE_GAP，外缘仍与网格对齐。"""
    x, y, w, h = px(m, g)
    e = (GUT - FUSE_GAP) / 2
    if "l" in fused_sides:
        x -= e
        w += e
    if "r" in fused_sides:
        w += e
    if "t" in fused_sides:
        y -= e
        h += e
    if "b" in fused_sides:
        h += e
    return x, y, w, h


def corners(fused_sides, outer, inner):
    """四角半径（左上、右上、右下、左下）：碰到连组边的角收小。"""
    s = fused_sides
    return (inner if s & {"t", "l"} else outer, inner if s & {"t", "r"} else outer,
            inner if s & {"b", "r"} else outer, inner if s & {"b", "l"} else outer)


# ------------------------------------------------------------- 落点
def free_spot(mods, w, h, x0=0, y0=0, skip=None):
    """离 (x0, y0) 最近、放得下 w×h 的空位；没有返回 None。"""
    others = [m for m in mods if m.get("id") != skip]
    best = None
    for y in range(ROWS - h + 1):
        for x in range(COLS - w + 1):
            c = {"x": x, "y": y, "w": w, "h": h}
            if any(overlaps(c, o) for o in others):
                continue
            d = (x - x0) ** 2 + (y - y0) ** 2 * 1.5
            if best is None or d < best[0]:
                best = (d, x, y)
    return None if best is None else (best[1], best[2])


def place(mods, mtype, x0=0, y0=0, w=None, h=None, skip=None):
    """放一个模块：先按要的尺寸找空位，放不下就逐步缩到最小尺寸。返回 (x, y, w, h) 或 None。"""
    mw, mh = TYPES[mtype]["min"]
    dw, dh = TYPES[mtype]["default"]
    w, h = w or dw, h or dh
    tries = []
    for ww in range(w, mw - 1, -1):
        for hh in range(h, mh - 1, -1):
            tries.append((ww * hh, ww, hh))
    for _, ww, hh in sorted(tries, key=lambda t: -t[0]):
        s = free_spot(mods, ww, hh, x0, y0, skip)
        if s:
            return s[0], s[1], ww, hh
    return None


# ------------------------------------------------------------- 整理
def fig_best_w(m, fig, g=None):
    """图卡的「最贴合」宽度：再宽字也不会变大、只多出左右空白的那一档（与编辑器 figBest 同算法）。fig：拼页报告里的 fig。"""
    g = g or DEFAULT
    mw = TYPES[m["type"]]["min"][0]
    ph = px(dict(m, x=0, y=0), g)[3]
    for w in range(mw, COLS - m["x"] + 1):
        pw = px({"x": 0, "y": 0, "w": w, "h": 1}, g)[2]
        if (pw - 2 * fig["pad"]) / fig["w"] >= (ph - 2 * fig["pad"]) / fig["h"]:
            return w
    return COLS - m["x"]


def fit_figures(mods, figs, g=None):
    """整理的第 0 步（作者要的「协调」）：图卡比图宽很多时收到最贴合的宽度，右边紧挨着、同几行的卡片向左长过来补上。
    figs：{模块 id: 拼页报告里的 fig}。返回 (新模块列表, 说明, 收过的图卡 id)。"""
    out = [dict(m) for m in mods]
    notes, fixed = [], set()
    for m in out:
        f = figs.get(m["id"])
        if not f or m.get("locked") or m.get("bleed"):
            continue
        b = fig_best_w(m, f, g)
        if b >= m["w"]:
            continue
        d = m["w"] - b
        right = m["x"] + m["w"]
        nbrs = [o for o in out if o is not m and o["x"] == right and not o.get("locked")
                and o["y"] < m["y"] + m["h"] and m["y"] < o["y"] + o["h"]]
        m["w"] = b
        fixed.add(m["id"])
        for o in nbrs:
            o["x"] -= d
            o["w"] += d
        notes.append(f"「{m['id']}」图卡收到最贴合的 {b} 栏" + (f"，右边 {len(nbrs)} 张卡片补上空位" if nbrs else ""))
    return out, notes, fixed


def tidy(mods, fixed_w=()):
    """按规则整理。返回 (新模块列表, 说明)。规则：
    1 上推：自上而下，每个模块往上推到碰到别的模块或页顶（左右位置不动）；
    1b 左靠：左边整段都空着的模块往左靠，中间不留空栏（标题不动）；
    2 等高：并排相邻、同一顶边的同类卡片拉到同高（取能放下的最大高度），于是连成一组；
    3 补齐：下方直到页底都空着的模块向下长满；右侧直到页边都空着的向右长满（标题、注释不长高）。"""
    out = [dict(m) for m in mods]
    notes = []
    order = sorted(out, key=lambda m: (m["y"], m["x"]))
    for m in order:
        if m.get("locked"):                    # 锁定的卡片不动；别的卡片绕开它
            continue
        y0 = m["y"]
        while m["y"] > 0:
            m["y"] -= 1
            if any(o is not m and overlaps(m, o) for o in out):
                m["y"] += 1
                break
        if m["y"] != y0:
            notes.append(f"「{m['id']}」上推 {y0 - m['y']} 行")
    for m in sorted(out, key=lambda m: (m["x"], m["y"])):  # 1b 左靠：左边整段都空着就往左靠，中间不留空栏（作者要的「协调」）
        if m.get("locked") or m["type"] == "title":
            continue
        x0 = m["x"]
        while m["x"] > 0:
            m["x"] -= 1
            if any(o is not m and overlaps(m, o) for o in out):
                m["x"] += 1
                break
        if m["x"] != x0:
            notes.append(f"「{m['id']}」左靠 {x0 - m['x']} 栏")

    def can(m, **kw):
        if m.get("locked"):
            return False
        c = dict(m, **kw)
        if c["x"] + c["w"] > COLS or c["y"] + c["h"] > ROWS or c["h"] > TYPES[c["type"]].get("maxh", ROWS):
            return False
        return not any(o is not m and overlaps(c, o) for o in out)

    rows = {}
    for m in out:
        if TYPES[m["type"]]["family"]:
            rows.setdefault((m["y"], TYPES[m["type"]]["family"]), []).append(m)
    for (_, _), ms in rows.items():
        ms.sort(key=lambda m: m["x"])
        run = [ms[0]]
        for m in ms[1:] + [None]:
            if m is not None and m["x"] == run[-1]["x"] + run[-1]["w"]:
                run.append(m)
                continue
            if len(run) > 1:
                target = max(r["h"] for r in run)
                while target > 0 and not all(r["h"] >= target or can(r, h=target) for r in run):
                    target -= 1
                for r in run:
                    if r["h"] < target:
                        notes.append(f"「{r['id']}」与邻卡等高：{r['h']} → {target} 行")
                        r["h"] = target
            run = [m] if m is not None else []
    for m in sorted(out, key=lambda m: (m["y"], m["x"])):
        if m["type"] in ("title", "note"):
            continue
        h0, w0 = m["h"], m["w"]
        while can(m, h=m["h"] + 1):
            m["h"] += 1
        while m["id"] not in fixed_w and can(m, w=m["w"] + 1):
            m["w"] += 1
        if (m["h"], m["w"]) != (h0, w0):
            notes.append(f"「{m['id']}」补齐空白：{w0}×{h0} → {m['w']}×{m['h']}")
    return out, notes


# ------------------------------------------------------------- 组合（模板）
def _m(t, x, y, w, h, **kw):
    return dict(type=t, x=x, y=y, w=w, h=h, **kw)


TEMPLATES = {
    # —— 场景（新建一页先选法律场景：图从哪个模块来、旁边配什么，一次排好）——
    "scene-timeline": {"zh": "案情经过", "group": "场景", "mods": [_m("title", 0, 0, 12, 1),
                       _m("figure", 0, 1, 12, 4, **{"from": "V2 时间轴大师"}), _m("conclusion", 0, 5, 12, 1)]},
    "scene-relation": {"zh": "法律关系", "group": "场景", "mods": [_m("title", 0, 0, 12, 1),
                       _m("figure", 0, 1, 8, 5, **{"from": "V3 法律关系图大师"}), _m("bullets", 8, 1, 4, 5, numbered=True)]},
    "scene-confront": {"zh": "双方攻防", "group": "场景", "mods": [_m("title", 0, 0, 12, 1),
                       _m("figure", 0, 1, 12, 4, **{"from": "V5 庭审对抗图大师"}), _m("conclusion", 0, 5, 12, 1)]},
    "scene-chronicle": {"zh": "事件脉络", "group": "场景", "mods": [_m("title", 0, 0, 12, 1),
                        _m("figure", 0, 1, 7, 5, **{"from": "V4 大事记表大师"}), _m("issue", 7, 1, 5, 3), _m("risk", 7, 4, 5, 2)]},
    "scene-data":     {"zh": "类案数据", "group": "场景", "mods": [_m("title", 0, 0, 12, 1), _m("chart", 0, 1, 8, 4),
                       _m("conclusion", 0, 5, 8, 1), _m("stat", 8, 1, 4, 2), _m("bullets", 8, 3, 4, 3)]},
    "scene-redraw":   {"zh": "重画的图", "group": "场景", "mods": [_m("title", 0, 0, 12, 1),
                       _m("figure", 0, 1, 12, 4, **{"from": "V1 诉讼可视化重画"}), _m("conclusion", 0, 5, 12, 1)]},
    # —— 排法（以图为中心）——
    "chart-conclusion": {"zh": "图 + 一句结论", "group": "排法", "mods": [_m("title", 0, 0, 12, 1), _m("chart", 0, 1, 12, 4),
                         _m("conclusion", 0, 5, 12, 1)]},
    "figure-basis":   {"zh": "图 + 依据", "group": "排法", "mods": [_m("title", 0, 0, 12, 1), _m("figure", 0, 1, 7, 5),
                       _m("statute", 7, 1, 5, 2), _m("holding", 7, 3, 5, 3)]},
    "chart-over-bullets": {"zh": "上图下要点", "group": "排法", "mods": [_m("chart", 0, 0, 12, 4), _m("bullets", 0, 4, 12, 2)]},
    # —— 律所 ——
    "cover-brand":  {"zh": "封面（带 Logo）", "group": "整套课件", "mods": [_m("logo", 0, 0, 2, 1), _m("title", 0, 2, 12, 3, level="cover"),
                                                                 _m("note", 0, 5, 12, 1)]},
    "firm-intro":   {"zh": "律所介绍",       "group": "整套课件", "mods": [_m("logo", 0, 0, 2, 1), _m("title", 2, 0, 10, 1),
                                                                 _m("profile", 0, 1, 12, 4, who="firm"), _m("contact", 0, 5, 12, 1)]},
    "lawyer-intro": {"zh": "律师简介",       "group": "整套课件", "mods": [_m("title", 0, 0, 12, 1), _m("profile", 0, 1, 7, 5),
                                                                 _m("bullets", 7, 1, 5, 5)]},
    "closing":      {"zh": "结束页",         "group": "整套课件", "mods": [_m("logo", 0, 0, 2, 1), _m("title", 0, 2, 12, 2, level="section"),
                                                                 _m("contact", 0, 4, 12, 1)]},
    # —— 法律场景 ——
    "statute-read": {"zh": "法条解读",       "group": "整套课件", "mods": [_m("title", 0, 0, 12, 1), _m("statute", 0, 1, 6, 3),
                                                                 _m("risk", 0, 4, 6, 2), _m("bullets", 6, 1, 6, 5)]},
    "case-review":  {"zh": "案例复盘",       "group": "整套课件", "mods": [_m("title", 0, 0, 12, 1), _m("case", 0, 1, 4, 5),
                                                                 _m("holding", 4, 1, 8, 2), _m("bullets", 4, 3, 8, 3)]},
    "issues":       {"zh": "争议焦点",       "group": "整套课件", "mods": [_m("title", 0, 0, 12, 1), _m("issue", 0, 1, 4, 5),
                                                                 _m("issue", 4, 1, 4, 5), _m("issue", 8, 1, 4, 5)]},
    "trial-prep":   {"zh": "庭前准备",       "group": "排法", "mods": [_m("title", 0, 0, 12, 1),
                                                                 _m("figure", 0, 1, 8, 5, **{"from": "V3 法律关系图大师"}),
                                                                 _m("issue", 8, 1, 4, 3), _m("risk", 8, 4, 4, 2)]},
    "evidence":     {"zh": "证据梳理",       "group": "排法", "mods": [_m("title", 0, 0, 12, 1), _m("evidence", 0, 1, 7, 5),
                                                                 _m("figure", 7, 1, 5, 5, **{"from": "V2 时间轴大师"})]},
    "timeline":     {"zh": "整宽时间轴",       "group": "排法", "mods": [_m("title", 0, 0, 12, 1),
                                                                 _m("figure", 0, 1, 12, 5, **{"from": "V2 时间轴大师"})]},
    "similar-cases": {"zh": "类案研究",      "group": "排法", "mods": [_m("title", 0, 0, 12, 1), _m("chart", 0, 1, 8, 5),
                                                                  _m("stat", 8, 1, 4, 2), _m("bullets", 8, 3, 4, 3)]},
    # —— 通用 ——
    "cover":        {"zh": "封面", "group": "整套课件",           "mods": [_m("title", 0, 2, 12, 3, level="cover"), _m("note", 0, 5, 12, 1)]},
    "section":      {"zh": "章节页", "group": "整套课件",         "mods": [_m("title", 0, 2, 12, 2, level="section")]},
    "chart-notes":  {"zh": "一图一讲", "group": "排法",       "mods": [_m("title", 0, 0, 12, 1), _m("chart", 0, 1, 8, 5), _m("bullets", 8, 1, 4, 5)]},
    "chart-stat":   {"zh": "一图一数一讲", "group": "排法",   "mods": [_m("title", 0, 0, 12, 1), _m("chart", 0, 1, 8, 5), _m("stat", 8, 1, 4, 2),
                                                    _m("bullets", 8, 3, 4, 3)]},
    "chart-full":   {"zh": "整页图", "group": "排法",         "mods": [_m("title", 0, 0, 12, 1), _m("chart", 0, 1, 12, 5)]},
    "two-charts":   {"zh": "左右两图", "group": "排法",       "mods": [_m("title", 0, 0, 12, 1), _m("chart", 0, 1, 6, 5), _m("chart", 6, 1, 6, 5)]},
    "chart-quote":  {"zh": "图 + 金句", "group": "排法",      "mods": [_m("title", 0, 0, 12, 1), _m("chart", 0, 1, 7, 5), _m("quote", 7, 1, 5, 5)]},
    "kpi":          {"zh": "数字一排", "group": "整套课件",       "mods": [_m("title", 0, 0, 12, 1), _m("stat", 0, 1, 3, 2), _m("stat", 3, 1, 3, 2),
                                                    _m("stat", 6, 1, 3, 2), _m("stat", 9, 1, 3, 2), _m("text", 0, 3, 12, 3)]},
    "three-steps":  {"zh": "三卡并列", "group": "整套课件",       "mods": [_m("title", 0, 0, 12, 1), _m("step", 0, 1, 4, 5), _m("step", 4, 1, 4, 5),
                                                    _m("step", 8, 1, 4, 5)]},
    "compare":      {"zh": "左右对照", "group": "整套课件",       "mods": [_m("title", 0, 0, 12, 1), _m("bullets", 0, 1, 6, 5), _m("bullets", 6, 1, 6, 5)]},
    "bullets":      {"zh": "标题 + 要点", "group": "整套课件",    "mods": [_m("title", 0, 0, 12, 1), _m("bullets", 0, 1, 12, 5)]},
    "chart-bleed":  {"zh": "整页出血图", "group": "排法",     "mods": [_m("chart", 0, 0, 12, 6, bleed=True)]},
    "figure-full":  {"zh": "整页关系图", "group": "排法",     "mods": [_m("figure", 0, 0, 12, 6, bleed=True)]},
    "quote":        {"zh": "金句页", "group": "整套课件",         "mods": [_m("quote", 1, 1, 10, 4)]},
}
COMPAT = {"text": ("text", "bullets"), "bullets": ("bullets", "text")}
CONTENT_KEYS = ("text", "sub", "kicker", "items", "heading", "value", "label", "note", "source", "spec", "file", "from",
                "level", "tone", "join", "bleed", "law", "article", "case_no", "court", "cause", "result", "point", "who",
                "pins", "numbered", "crop", "locked", "data", "part", "focus", "sample", "recipe")


def new_id(mods, prefix="m"):
    n = 1
    ids = {m.get("id") for m in mods}
    while f"{prefix}{n}" in ids:
        n += 1
    return f"{prefix}{n}"


def apply_template(mods, name):
    """把一页换成某个组合：原有内容按类型、阅读顺序搬进新格子；搬不下的原样返回（编辑器里放在「暂存」）。"""
    t = TEMPLATES[name]
    left = sorted([dict(m) for m in mods], key=lambda m: (m["y"], m["x"]))
    out = []
    for slot in t["mods"]:
        nm = {k: v for k, v in slot.items()}
        hit = next((m for m in left if m["type"] == slot["type"]), None) or \
            next((m for m in left if m["type"] in COMPAT.get(slot["type"], ())), None)
        if hit:
            left.remove(hit)
            for k in CONTENT_KEYS:
                if k in hit and k not in ("level",):
                    nm[k] = hit[k]
            if hit["type"] in COMPAT.get(slot["type"], ()):
                nm["type"] = hit["type"]
            nm["id"] = hit["id"]
        else:
            nm["id"] = new_id(out + left + [dict(id=x["id"]) for x in mods])
        out.append(nm)
    return out, left


# ------------------------------------------------------------- 旧格式（deck@1 版式）升级
_V1_MAP = {
    "cover": ("cover", {"title": ("title", "text"), "subtitle": ("title", "sub"), "meta": ("note", "text")}),
    "section": ("section", {"kicker": ("title", "kicker"), "title": ("title", "text")}),
    "bullets": ("bullets", {"title": ("title", "text"), "body": ("bullets", None)}),
    "full": ("chart-bleed", {"main": ("chart", None)}),
    "chart-notes": ("chart-notes", {"main": ("chart", None), "side_title": ("bullets", "heading"), "side": ("bullets", None)}),
    "two": ("two-charts", {"left": ("chart", None), "right": ("chart", None)}),
    "wide": ("chart-full", {"title": ("title", "text"), "main": ("chart", None)}),
    "quote": ("quote", {"quote": ("quote", None)}),
}


def upgrade_slide(s):
    """deck@1 的一页（版式 + 格子）→ 网格模块。"""
    tname, slotmap = _V1_MAP[s["layout"]]
    mods = [dict(m, id=f"m{i + 1}") for i, m in enumerate(TEMPLATES[tname]["mods"])]
    used = set()
    no_title = True
    for name, mod in (s.get("slots") or {}).items():
        if not mod or name not in slotmap:
            continue
        ttype, key = slotmap[name]
        kind = mod.get("type")
        target_type = ttype
        if kind in ("figure",) and ttype == "chart":
            target_type = "chart"            # 落到图表格里再改类型
        cand = [m for m in mods if m["type"] == target_type and m["id"] not in used] if key is None else \
            [m for m in mods if m["type"] == target_type]
        if not cand:
            continue
        m = cand[0]
        if key is None:
            used.add(m["id"])
            for k, v in mod.items():
                if k != "type":
                    m[k] = v
            if kind == "text" and m["type"] == "bullets":
                m["type"] = "text"
            elif kind in ("figure", "quote", "bullets", "text", "chart"):
                m["type"] = kind
        else:
            m[key] = mod.get("text", "")
        if m["type"] == "title":
            no_title = False
    return {"id": s["id"], "modules": mods}
