# -*- coding: utf-8 -*-
import os
"""法律关系图 · 渲染核心。

位置由骨架算出，走线由两端的相对位置查表决定，拐角方向由叉积算出。
这三件都不手写，手写的地方就是反复出错的地方。

几何参数沿用奇川风标定值：线宽 1.30、圆角 3.12（2.4 倍线宽）、
箭头长 12、汇合点 2.60。
"""
import math

SW, R, JR = 1.30, 3.12, 2.60
ARROW = 12                    # 箭头三角形的长度
STUB = 22                     # 出入两端垂直于该边的直段
# 曾试过改成 36 来解决贴边（出端直段 25.12 太短，线一出主体就横向拐走）。
# 12 主体案确实贴边归零了，但两个真实案子当场破了判据：甲案 出现 5 处穿节点。
# 原因是这两个案子里有手工写死的骨架坐标，按旧 STUB 定的，改常量就过期了。
# 全局常量牵一发动全身，贴边改用搜索罚分解决，不动这个数。

# 距离预算。经复算修正：圆角会从直段两端各吃掉 R，箭头再吃掉 ARROW，
# 所以尖角交点到节点边的距离必须比 STUB 大出这些量，否则 G3 过不了。
D_OUT = STUB + R              # 25.12　出端：第一个拐角到源边
D_IN = STUB + R + ARROW       # 37.12　入端：最后一个拐角到目标边
D_STRAIGHT = STUB + ARROW     # 34.00　零拐弯直连：没有圆角裁切，只扣箭头
D_CORNER = 2 * R              # 6.24 　两个连续拐角之间的最小距离

# 端口容量。左右边长 48，按等分位 L*i/(k+1) 排两个端口间距只有 16，
# 不足最小间距 26；且节点圆角 rx=12 使竖直直边只剩 y∈[12,36] 共 24 长，
# 也放不下两个相隔 26 的端口。所以左右每边只能有一个端口，总容量 10 不是 12。
PORT_GAP = 26                 # 同一条边上相邻端口的最小间距
CAP = {"T": 4, "B": 4, "L": 2, "R": 2}   # 有效容量合计 10
INK, LINE, FILL, EDGE, RED, MUTED = (
    "#1F2933", "#4B5563", "#F3F4F6", "#D6DAE0", "#991B1B", "#6B7280")
DIR = {"L": (-1, 0), "R": (1, 0), "T": (0, -1), "B": (0, 1)}

# 关系性质 → 线型。深红只给本案诉讼标的那一条
STYLE = {
    "contract": dict(dash=False, hot=False),   # 合同关系
    "equity":   dict(dash=False, hot=False),   # 股权与持股
    "status":   dict(dash=True,  hot=False),   # 身份、任职、历史状态
    "claim":    dict(dash=False, hot=True),    # 本案诉讼标的
}


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _uni(a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = math.hypot(dx, dy)
    return (0.0, 0.0) if L < 1e-9 else (dx / L, dy / L)


def rounded(pts, r=R):
    """折线转带圆角的 path。拐角的 sweep 由前后两段的叉积算：
    叉积为正是屏幕上的顺时针取 1，为负取 0。手写必然大面积写反。"""
    out = [pts[0]]
    for p in pts[1:]:
        if abs(p[0] - out[-1][0]) > .01 or abs(p[1] - out[-1][1]) > .01:
            out.append(p)
    pts = out
    if len(pts) < 2:
        return ""
    d = f"M {pts[0][0]:.2f},{pts[0][1]:.2f}"
    for i in range(1, len(pts) - 1):
        p0, p1, p2 = pts[i - 1], pts[i], pts[i + 1]
        v1, v2 = _uni(p0, p1), _uni(p1, p2)
        cross = v1[0] * v2[1] - v1[1] * v2[0]
        if abs(cross) < 1e-9:
            continue
        rr = min(r, math.dist(p0, p1) / 2, math.dist(p1, p2) / 2)
        a = (p1[0] - v1[0] * rr, p1[1] - v1[1] * rr)
        b = (p1[0] + v2[0] * rr, p1[1] + v2[1] * rr)
        d += (f" L {a[0]:.2f},{a[1]:.2f} A {rr:.2f} {rr:.2f} 0 0 "
              f"{1 if cross > 0 else 0} {b[0]:.2f},{b[1]:.2f}")
    d += f" L {pts[-1][0]:.2f},{pts[-1][1]:.2f}"
    return d


class Graph:
    def __init__(self, nw=140, nh=48):
        self.NW, self.NH = nw, nh
        self.pos = {}
        self.meta = {}
        self.o = []

    # ---- 布局 ----
    def place(self, pid, x, y, name, note="", hot=False):
        self.pos[pid] = (x, y)
        self.meta[pid] = dict(name=name, note=note, hot=hot)

    def port(self, pid, side, off=0):
        cx, cy = self.pos[pid]
        if side == "L": return (cx - self.NW / 2, cy + off)
        if side == "R": return (cx + self.NW / 2, cy + off)
        if side == "T": return (cx + off, cy - self.NH / 2)
        return (cx + off, cy + self.NH / 2)

    def port_at(self, pid, side, i, k):
        """一条边上第 i 个端口（从 1 起，共 k 个），按等分位 L*i/(k+1)。
        k=1 时落在边的中点——这一条必须强制，只有一条线却不居中，一眼看得出不齐。"""
        if k > CAP[side]:
            raise ValueError(f"{pid} 的 {side} 边要放 {k} 个端口，超过容量 {CAP[side]}")
        L = self.NW if side in "TB" else self.NH
        if k >= 2 and L / (k + 1) < PORT_GAP:
            raise ValueError(f"{pid} 的 {side} 边放 {k} 个端口，间距 "
                             f"{L / (k + 1):.1f} 小于 {PORT_GAP}")
        off = 0 if k == 1 else L * i / (k + 1) - L / 2
        return self.port(pid, side, off)

    def route(self, a, sa, b, sb, oa=0, ob=0, mid=None):
        """出入两端各留一段垂直于该侧的直段，中间按需补一个拐点。
        线只画到箭头三角形的底边，三角形由 marker 从那里往前画，
        尖端落在节点边上；线若画到尖端，出来就是个平头箭头。"""
        p0, p1 = self.port(a, sa, oa), self.port(b, sb, ob)
        da, db = DIR[sa], DIR[sb]
        q0 = (p0[0] + da[0] * D_OUT, p0[1] + da[1] * D_OUT)
        back = D_IN
        q1 = (p1[0] + db[0] * back, p1[1] + db[1] * back)
        def _check(v, axis):
            """主干必须落在 stub 之外。给近了折线会往回走，圆角跟着反向，
            画出来是个别扭的回头弯。与其画错，不如当场报出来。"""
            k = 0 if axis == "x" else 1
            d = da[k]
            if d and (v - q0[k]) * d < 0:
                raise ValueError(
                    f"主干 {axis}={v} 落在 stub 之内（stub 终点 {q0[k]:.0f}，"
                    f"出侧 {sa}），折线会往回走")

        pts = [p0, q0]
        if isinstance(mid, tuple):
            _check(mid[0], "x" if da[0] else "y")
            # 两段主干：跨两列又要走中间通道带时，一条主干不够。
            # 语义按出侧定：横向出就是先到 x=mid[0] 再到 y=mid[1]，
            # 纵向出反过来。给错顺序线会直接跑出画布，这个坑踩过。
            a, b = mid
            pts += ([(a, q0[1]), (a, b), (q1[0], b)] if da[0]
                    else [(q0[0], a), (b, a), (b, q1[1])])
        elif mid is not None:
            pts += ([(mid, q0[1]), (mid, q1[1])] if da[0]
                    else [(q0[0], mid), (q1[0], mid)])
        else:
            same = (abs(q0[0] - q1[0]) < .5) if da[0] == 0 else (abs(q0[1] - q1[1]) < .5)
            if not same:
                pts.append((q1[0], q0[1]) if da[0] else (q0[0], q1[1]))
        tip = (p1[0] + db[0] * ARROW, p1[1] + db[1] * ARROW)
        return pts + [q1, tip]

    # ---- 绘制 ----
    def draw_nodes(self):
        for pid, (cx, cy) in self.pos.items():
            m = self.meta[pid]
            x, y = cx - self.NW / 2, cy - self.NH / 2
            if m["hot"]:
                self.o.append(f'<rect x="{x:.2f}" y="{y:.2f}" width="{self.NW}" '
                              f'height="{self.NH}" rx="12" fill="{RED}"/>')
            else:
                self.o.append(f'<rect x="{x:.2f}" y="{y:.2f}" width="{self.NW}" '
                              f'height="{self.NH}" rx="12" fill="{FILL}" '
                              f'stroke="{EDGE}" stroke-width="1.0"/>')
            col = "#FFFFFF" if m["hot"] else INK
            sub = "#E8D5D5" if m["hot"] else MUTED
            dy = -2 if m["note"] else 5
            self.o.append(f'<text x="{cx:.2f}" y="{cy + dy:.2f}" font-size="12.5" '
                          f'fill="{col}" text-anchor="middle" font-weight="700">'
                          f'{esc(m["name"])}</text>')
            if m["note"]:
                self.o.append(f'<text x="{cx:.2f}" y="{cy + 14:.2f}" font-size="9" '
                              f'fill="{sub}" text-anchor="middle">{esc(m["note"])}</text>')

    def edge(self, a, sa, b, sb, label="", kind="contract",
             oa=0, ob=0, mid=None, lab=None, anchor="middle", arrow=True):
        st = STYLE[kind]
        pts = self.route(a, sa, b, sb, oa, ob, mid)
        hot = st["hot"]
        mk = f' marker-end="url(#{"ar" if hot else "a"})"' if arrow else ""
        ds = ' stroke-dasharray="4 3"' if st["dash"] else ""
        self.o.append(f'<path d="{rounded(pts)}" fill="none" '
                      f'stroke="{RED if hot else LINE}" stroke-width="{SW:.2f}"'
                      f'{ds}{mk}/>')
        if label:
            if lab is None:
                i = max(1, len(pts) // 2)
                lab = ((pts[i - 1][0] + pts[i][0]) / 2,
                       (pts[i - 1][1] + pts[i][1]) / 2 - 8)
            self.o.append(f'<text x="{lab[0]:.2f}" y="{lab[1]:.2f}" font-size="10" '
                          f'fill="{RED if hot else MUTED}" text-anchor="{anchor}">'
                          f'{esc(label)}</text>')

    def tie(self, a, b, label="", gap=0):
        """并列关系：同层横向细线，无箭头。"""
        p0, p1 = self.port(a, "R", gap), self.port(b, "L", gap)
        self.o.append(f'<path d="{rounded([p0, p1])}" fill="none" '
                      f'stroke="{LINE}" stroke-width="{SW:.2f}"/>')
        if label:
            self.o.append(f'<text x="{(p0[0] + p1[0]) / 2:.2f}" y="{p0[1] - 8:.2f}" '
                          f'font-size="10" fill="{MUTED}" text-anchor="middle">'
                          f'{esc(label)}</text>')

    def svg(self, w, h, title, sub, notes=()):
        head = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
                f'viewBox="0 0 {w} {h}" font-family="Noto Sans CJK SC">',
                f'<rect width="{w}" height="{h}" fill="#FFFFFF"/>',
                '<defs>'
                f'<marker id="a" markerWidth="12" markerHeight="8.4" refX="0" refY="4.2" '
                f'markerUnits="userSpaceOnUse" orient="auto">'
                f'<path d="M 0 0 L 12 4.2 L 0 8.4 Z" fill="{LINE}"/></marker>'
                f'<marker id="ar" markerWidth="12" markerHeight="8.4" refX="0" refY="4.2" '
                f'markerUnits="userSpaceOnUse" orient="auto">'
                f'<path d="M 0 0 L 12 4.2 L 0 8.4 Z" fill="{RED}"/></marker>'
                '</defs>',
                f'<text x="40" y="44" font-size="16" font-weight="700" fill="{INK}">'
                f'{esc(title)}</text>',
                f'<text x="40" y="66" font-size="10.5" fill="{MUTED}">{esc(sub)}</text>']
        foot = [f'<text x="40" y="{h - 44 + i * 17:.0f}" font-size="9.5" fill="{MUTED}">'
                f'注{i + 1}：{esc(t)}</text>' for i, t in enumerate(notes)]
        return "\n".join(head + self.o + foot) + "\n</svg>"
