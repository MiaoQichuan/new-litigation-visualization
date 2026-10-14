# -*- coding: utf-8 -*-
"""小圆角几何：所有填充形状的尖角都用三次贝塞尔曲线磨圆。

作者定的风格：柱、节点、扇区、流带——凡是矩形、三角形、多边形的尖角，一律换成一点点
贝塞尔小圆角。箭头除外（箭头的尖是方向，不是角）。

做法：对多边形的每个顶点，若转角大于 MIN_TURN（真正的角，而不是弧线采样点之间的微小折点），
就在两条边上各退回 d，用一段三次贝塞尔接起来；控制柄长度按圆弧的标准近似取
h = 4/3 · tan(θ/4) · ρ，所以磨出来的角就是半径 ρ 的圆角，不是随手的曲线。
d 不超过相邻两边各自长度的一半，短边上的角自动收小，永远不会把形状磨坏。

PPTX 的导出器只认直线段，所以交付前另有 flatten()：把曲线细分成折线。
"""
import math
import re

MIN_TURN = math.radians(12)   # 小于这个转角的顶点是弧线采样点，不磨
KAPPA_STEPS = 6               # flatten 时每段曲线细分的步数


def _n(v):
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def rounded_d(pts, r):
    """闭合多边形 → 带贝塞尔小圆角的 path d。r <= 0 时退回直线段（守卫会拦下）。"""
    n = len(pts)
    if r <= 0 or n < 3:
        return "M" + " L".join(f"{_n(x)},{_n(y)}" for x, y in pts) + " Z"
    segs = []
    for i in range(n):
        px, py = pts[i - 1]
        vx, vy = pts[i]
        qx, qy = pts[(i + 1) % n]
        ax, ay = vx - px, vy - py
        bx, by = qx - vx, qy - vy
        la, lb = math.hypot(ax, ay), math.hypot(bx, by)
        if la < 1e-9 or lb < 1e-9:
            segs.append(("P", (vx, vy)))
            continue
        ux, uy = ax / la, ay / la          # 进入方向
        wx, wy = bx / lb, by / lb          # 离开方向
        cosang = max(-1.0, min(1.0, ux * wx + uy * wy))
        theta = math.acos(cosang)          # 转角（0 = 直行）
        if theta < MIN_TURN:
            segs.append(("P", (vx, vy)))
            continue
        d = r * math.tan(theta / 2)
        d = min(d, la / 2, lb / 2)
        rho = d / math.tan(theta / 2)      # 实际圆角半径（边太短时会小于 r）
        h = 4 / 3 * math.tan(theta / 4) * rho
        A = (vx - ux * d, vy - uy * d)
        B = (vx + wx * d, vy + wy * d)
        C1 = (A[0] + ux * h, A[1] + uy * h)
        C2 = (B[0] - wx * h, B[1] - wy * h)
        segs.append(("C", A, C1, C2, B))
    first = segs[0]
    start = first[1] if first[0] == "P" else first[4]
    out = [f"M{_n(start[0])},{_n(start[1])}"]
    for s in segs[1:] + [first]:
        if s[0] == "P":
            if s is not first:
                out.append(f"L{_n(s[1][0])},{_n(s[1][1])}")
        else:
            A, C1, C2, B = s[1:]
            out.append(f"L{_n(A[0])},{_n(A[1])}")
            out.append(f"C{_n(C1[0])},{_n(C1[1])} {_n(C2[0])},{_n(C2[1])} {_n(B[0])},{_n(B[1])}")
    return " ".join(out) + " Z"


def rect_pts(x, y, w, h):
    return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]


_TOK = re.compile(r"([MLCZ])([^MLCZ]*)")


def flatten(d, steps=KAPPA_STEPS):
    """path d（M / L / C / Z）→ 折线点列。导出 PPTX 与守卫量几何都用它。"""
    pts, cur = [], None
    for cmd, body in _TOK.findall(d):
        nums = [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", body)]
        if cmd in "ML":
            for i in range(0, len(nums) - 1, 2):
                cur = (nums[i], nums[i + 1])
                pts.append(cur)
        elif cmd == "C":
            for i in range(0, len(nums) - 5, 6):
                p0 = cur
                c1, c2, p3 = (nums[i], nums[i + 1]), (nums[i + 2], nums[i + 3]), (nums[i + 4], nums[i + 5])
                for s in range(1, steps + 1):
                    t = s / steps
                    a, b, c, e = (1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t ** 2, t ** 3
                    pts.append((a * p0[0] + b * c1[0] + c * c2[0] + e * p3[0],
                                a * p0[1] + b * c1[1] + c * c2[1] + e * p3[1]))
                cur = p3
    return pts


def flat_d(d):
    """细分后的折线；只有原路径闭合（带 Z）时才闭合——开口的流向中线若被闭合，PPTX 里会多出一条回程线。"""
    pts = flatten(d)
    return "M" + " L".join(f"{_n(x)},{_n(y)}" for x, y in pts) + (" Z" if d.rstrip().upper().endswith("Z") else "")


def bbox(pts):
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def area(pts):
    s = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i - 1]
        x2, y2 = pts[i]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2
