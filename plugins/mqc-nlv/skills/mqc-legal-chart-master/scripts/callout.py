# -*- coding: utf-8 -*-
"""批注：一句旁白 + 一条虚线贝塞尔引线 + 一个落点。

学自 diagram-design（MIT）的 annotation callout 的做法，代码自写：
  * 批注放在页边的批注栏里，不压在数据上；
  * 引线是一条虚线三次贝塞尔曲线，落点是一个小实心点；
  * 一页最多两条（spec.MAX_ANNOTATIONS）。

引线怎么走由这里**搜**出来：在批注栏里逐个试文字块的高度、在目标上逐个试落点，取第一条
不穿过任何别的文字与数据形状的路线。渲染器与守卫用同一套判定（`leader_hits`），
守卫从最终 SVG 里把障碍物重新读一遍，所以渲染器哪天改坏了、引线穿过了别的柱，守卫照样拦得住。
"""
import math
import re

# 可以横穿的元素：网格、轴线、分隔线、页底纹、批注栏自己
CROSSABLE = {"grid", "axis", "rule", "paper", "texture", "threshold"}
SAMPLES = 64


def cubic(p0, c1, c2, p1, n=SAMPLES):
    out = []
    for i in range(n + 1):
        t = i / n
        u = 1 - t
        out.append((u ** 3 * p0[0] + 3 * u * u * t * c1[0] + 3 * u * t * t * c2[0] + t ** 3 * p1[0],
                    u ** 3 * p0[1] + 3 * u * u * t * c1[1] + 3 * u * t * t * c2[1] + t ** 3 * p1[1]))
    return out


def leader_ctrl(s, p, arrive):
    """起点 s 在批注栏左缘（水平离开），终点 p 在目标上。arrive = 'down'（从上方落下）或 'left'（从右方水平进入）。"""
    (sx, sy), (px, py) = s, p
    if arrive == "down":
        # 先沿通道水平走，到目标正上方再落下：弯只发生在目标上方一小段，不会扫过邻近的柱
        return (px + min(48.0, (sx - px) * 0.3), sy), (px, sy)
    dx = (sx - px) * 0.45
    return (sx - dx, sy), (px + dx, py)


def leader_d(s, c1, c2, p):
    f = lambda v: f"{v:.2f}".rstrip("0").rstrip(".")
    return f"M{f(s[0])},{f(s[1])} C{f(c1[0])},{f(c1[1])} {f(c2[0])},{f(c2[1])} {f(p[0])},{f(p[1])}"


def parse_leader(d):
    nums = [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", d)]
    if not d.lstrip().startswith("M") or "C" not in d or len(nums) != 8:
        return None
    return (nums[0], nums[1]), (nums[2], nums[3]), (nums[4], nums[5]), (nums[6], nums[7])


def _inside(pt, b, pad):
    return b[0] - pad < pt[0] < b[2] + pad and b[1] - pad < pt[1] < b[3] + pad


def leader_hits(pts, obstacles, pad=2.5, tail=6.0):
    """引线采样点落进任何障碍外框（外扩 pad）就算穿过。只有落点周围 tail 像素以内不查：
    那一小段要碰到目标。按距离而不按比例留余量——按比例的话，长引线会在落点前白白放过几十像素，
    正好压过目标旁边的数值。返回撞上的第一个障碍的说明，没有撞上返回 None。"""
    if len(pts) < 2:
        return None
    ex, ey = pts[-1]
    if pts[0][1] > ey + 1e-6 and _arrive_down(pts):
        return "目标下方（引线不能从下往上落）"
    dense = densify(pts)                                 # 采样加密到每 2px 一个点，细字也漏不过去
    for pt in dense[1:]:
        if math.hypot(pt[0] - ex, pt[1] - ey) <= tail:
            continue
        for b, what in obstacles:
            if _inside(pt, b, pad):
                return what
    return None


def densify(pts, step=2.0):
    out = []
    for a, b in zip(pts, pts[1:]):
        k = max(1, int(math.hypot(b[0] - a[0], b[1] - a[1]) / step))
        out += [(a[0] + (b[0] - a[0]) * i / k, a[1] + (b[1] - a[1]) * i / k) for i in range(k)]
    return out + [pts[-1]]


def too_close(pts, other, gap=6.0):
    """两条引线之间最近不到 gap 像素：读者分不清哪条指向哪里。"""
    a, b = densify(pts, 3.0), densify(other, 3.0)
    return any(abs(u[0] - v[0]) < gap and abs(u[1] - v[1]) < gap and math.hypot(u[0] - v[0], u[1] - v[1]) < gap
               for u in a for v in b)


def _arrive_down(pts):
    """末段是不是竖直进入（从上往下或从下往上）。"""
    (x0, y0), (x1, y1) = pts[-4], pts[-1]
    return abs(x1 - x0) < abs(y1 - y0)


def landing_candidates(tb, chart):
    """目标外框上的候选落点：(点, 进入方向)。按图种给出优先次序。"""
    x0, y0, x1, y1 = tb
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    gap = 5.0                                  # 落点离数字留一点空，不压字
    near_end = (x1 - min(14.0, (x1 - x0) / 3), y0)
    if chart in ("hbar", "dumbbell"):
        return [((x1 + gap, cy), "left"), (near_end, "down"), ((cx, y0), "down")]
    return [((cx, y0 - gap), "down"), ((x1, cy), "left"), (near_end, "down"),
            ((x1, y0 + min(10.0, (y1 - y0) / 3)), "left")]
