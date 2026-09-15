# -*- coding: utf-8 -*-
import os
"""法律关系图 · 正交路径搜索。

在由节点边界、端口坐标与通道线张成的稀疏网格上搜一条正交路径。
状态带方向，转向要付拐弯代价；已固定的线段参与交叉计价。

三条必须守住的约束（来自几何审计）：
  出端第一段 ≥ D_OUT  = 25.12（圆角会从直段两端各裁掉 R）
  入端最后一段 ≥ D_IN = 37.12（还要再扣掉箭头长度）
  相邻两个拐点之间 ≥ D_CORNER = 6.24（否则两个圆角互相裁切）

外围通道是可行区域的一部分，不是失败兜底。绕外围走是已经定下来的
可接受形态，搜索不得对它额外罚分——这条来自两个方案的视觉比对结论。
"""
import heapq, math, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from relation_core import D_OUT, D_IN, D_CORNER, CAP

NW, NH = 140, 78
DIR = {"L": (-1, 0), "R": (1, 0), "T": (0, -1), "B": (0, 1)}
W_BEND = 60.0          # 一个拐弯折合的长度代价
W_CROSS = 4000.0       # 一次交叉折合的长度代价，远大于任何绕行
# 绕行一律走外围。外围那一圈就是给绕行线用的跑道，像航线一样分层。
# 例外只有一种：外围路径绕得实在离谱时（见 joint_route 的倍数判据），
# 才允许那一条走内腹。例外要窄，放宽了内外混走，图中间反而更乱。
W_INNER = 2.2
W_HUG = 1.6            # 贴着主体边走的罚分倍率
HUG_NEAR = 60.0        # 多近算贴。原取 30，可实测净距 54 的线看着仍然贴边——
                       # 这个数是拍的不是算的。提到 60，罚分才会把线推向空隙中央。
MARGIN = 80            # 画布外围通道距最外侧节点的距离
MIN_CLEAR = 20         # 通道候选与主体边的最小间隔，小于此的一律不生成


def build_grid(rects, ports, margin=MARGIN, lane=40):
    """lane 是通道离主体边的距离。取 26 时线贴着主体走，判据实测净距正好 26。
    行间空隙 152、列间 200，让到 40 仍排得下中间通道。
    只动这一个参数——上次连 STUB 一起改，手工骨架全部过期、甲案 当场破了 G1。"""
    """lane 是通道离主体边的距离。

    原来取 26（与端口最小间距同值），线就贴着主体走过去，
    看图的人一眼就说「贴边」。判据实测净距 25 到 26，
    正是这个参数直接造成的——不是走线算错，是通道本来就设得太近。
    行间空隙 152、列间 200，两边各让 40 仍放得下中间通道。"""
    """候选坐标：节点边界外扩一个车道、各端口坐标、以及外围两圈。
    Hanan 网格的变体——最优正交路径的拐点必落在这些坐标上。"""
    xs, ys = set(), set()
    for x, y, w, h in rects:
        # 只取主体外侧的通道，**不取边界本身**。
        # 把 x 和 x+w 也放进候选，线就会正好走在主体的边线上，
        # 与那条边完全重合——那不是靠得近，是压在上面。
        for v in (x - lane, x + w + lane):
            xs.add(v)
        for v in (y - lane, y + h + lane):
            ys.add(v)
    for px, py in ports:
        xs.add(px)
        ys.add(py)
    # 相邻边界之间若留有足够空隙，再插入几条等分通道线。
    # 只给一条可走，几条线就全挤在同一条上，重叠与交叉反而更多；
    # 空隙本来就宽（行间 152、列间 180），该分成几条跑道用。
    def densify(vals):
        vals = sorted(vals)
        add = []
        for a, b in zip(vals, vals[1:]):
            gap = b - a
            if gap > 70:
                n = min(3, int(gap // 40))
                add += [a + gap * (i + 1) / (n + 1) for i in range(n)]
        return set(add)

    xs |= densify(xs)
    ys |= densify(ys)

    # 加密插入的等分线不管离主体多近，实测出现过离边只有 3.3 的通道，
    # 线走上去就是贴着主体边平行走。这里统一过滤：
    # 离任何主体的边太近的候选一律不要。
    # 端口坐标正落在边上（距离为 0），不在过滤区间内，不受影响。
    def too_close(v, lows, highs):
        for lo, hi in zip(lows, highs):
            if 0.5 < abs(v - lo) < MIN_CLEAR or 0.5 < abs(v - hi) < MIN_CLEAR:
                return True
        return False

    xlo = [r[0] for r in rects]
    xhi = [r[0] + r[2] for r in rects]
    ylo = [r[1] for r in rects]
    yhi = [r[1] + r[3] for r in rects]
    xs = {v for v in xs if not too_close(v, xlo, xhi)} | {p[0] for p in ports}
    ys = {v for v in ys if not too_close(v, ylo, yhi)} | {p[1] for p in ports}
    x0 = min(r[0] for r in rects) - margin
    x1 = max(r[0] + r[2] for r in rects) + margin
    y0 = min(r[1] for r in rects) - margin
    y1 = max(r[1] + r[3] for r in rects) + margin
    xs |= {x0, x0 + lane, x1 - lane, x1}
    ys |= {y0, y0 + lane, y1 - lane, y1}
    return sorted(xs), sorted(ys)


def inner_penalty(p, q, hull):
    """内腹穿行量，绕行禁入。"""
    """绕行线要走外围，不要从主体之间的内腹穿过去。

    内腹是所有主体的总包围盒。一条绕行线若从内腹横切，会把图中间搅乱，
    沿外围绕远反而清爽。这一条是视觉判断定下来的，不是从长度推出来的。

    罚分不设最小段长：搜索是在网格上逐小段走的，每段才二三十，
    设了门槛就一段也罚不到。必要的穿越由调用方保证——
    能直连的先直连、根本不进搜索，所以不会误伤相邻主体之间的直线。"""
    if hull is None:
        return 0.0
    x0, y0, x1, y1 = hull
    ax, ay = p
    bx, by = q
    if abs(ax - bx) < .5:
        if not (x0 <= ax <= x1):
            return 0.0
        lo, hi = sorted((ay, by))
        seg = max(0.0, min(hi, y1) - max(lo, y0))
        return W_INNER * seg
    else:
        if not (y0 <= ay <= y1):
            return 0.0
        lo, hi = sorted((ax, bx))
        seg = max(0.0, min(hi, x1) - max(lo, x0))
    return W_INNER * seg


def hug_penalty(p, q, rects, near=HUG_NEAR):
    """贴着主体的边平行走要罚。

    这是「连续跟三个模块紧密贴合」的那条线的病根，而它与走内走外无关：
    那条线沿着几个主体的顶边横穿，位置在内腹禁区之外所以完全合法，
    又比绕到更外面短，搜索没有理由不选它。
    真正该禁的是贴，不是内。罚了贴边，线自己就会往外让或者改走通道。"""
    (x0, y0), (x1, y1) = p, q
    pen = 0.0
    for rx, ry, rw, rh in rects:
        if abs(x0 - x1) < .5:
            lo, hi = sorted((y0, y1))
            if hi < ry - near or lo > ry + rh + near:
                continue
            if min(abs(x0 - rx), abs(x0 - (rx + rw))) < near:
                pen += min(hi, ry + rh) - max(lo, ry)
        else:
            lo, hi = sorted((x0, x1))
            if hi < rx - near or lo > rx + rw + near:
                continue
            if min(abs(y0 - ry), abs(y0 - (ry + rh))) < near:
                pen += min(hi, rx + rw) - max(lo, rx)
    return W_HUG * max(0.0, pen)


def blocked(p, q, rects, pad=3.0, clear_rects=(), clear=0):
    """线段是否撞上障碍。两种情况都算：穿过主体的内部，
    以及压在主体的某条边线上与之重合。

    后一种先前完全没管：端口坐标会进网格，于是通道正好落在主体边界上，
    线沿着那条边走过去，看上去就是主体被一条线划开了。
    这不是「靠得近」，是重合，必须当障碍挡掉。"""
    (x0, y0), (x1, y1) = p, q
    for rx, ry, rw, rh in list(rects) + list(clear_rects):
        if abs(x0 - x1) < .5:
            lo, hi = sorted((y0, y1))
            if (abs(x0 - rx) < 1 or abs(x0 - (rx + rw)) < 1) and \
                    min(hi, ry + rh) - max(lo, ry) > 2:
                return True
        elif abs(y0 - y1) < .5:
            lo, hi = sorted((x0, x1))
            if (abs(y0 - ry) < 1 or abs(y0 - (ry + rh)) < 1) and \
                    min(hi, rx + rw) - max(lo, rx) > 2:
                return True
    for rx, ry, rw, rh in list(rects) + list(clear_rects):
        if abs(x0 - x1) < .5:
            if rx + pad < x0 < rx + rw - pad:
                lo, hi = sorted((y0, y1))
                if lo < ry + rh - pad and hi > ry + pad:
                    return True
        elif abs(y0 - y1) < .5:
            if ry + pad < y0 < ry + rh - pad:
                lo, hi = sorted((x0, x1))
                if lo < rx + rw - pad and hi > rx + pad:
                    return True
    return False


def seg_overlap(a, b, tol=2.0):
    """两段是否共线重叠。G2 禁止这个，但 seg_cross 对同方向的两段
    直接返回 False，等于漏检——搜索一路按「无交叉」走，
    画出来两条线叠在一起。判据早就定了的约束，搜索必须一起守。"""
    (ax0, ay0), (ax1, ay1) = a
    (bx0, by0), (bx1, by1) = b
    if abs(ax0 - ax1) < .5 and abs(bx0 - bx1) < .5 and abs(ax0 - bx0) < .5:
        l1, h1 = sorted((ay0, ay1)); l2, h2 = sorted((by0, by1))
        return min(h1, h2) - max(l1, l2) > tol
    if abs(ay0 - ay1) < .5 and abs(by0 - by1) < .5 and abs(ay0 - by0) < .5:
        l1, h1 = sorted((ax0, ax1)); l2, h2 = sorted((bx0, bx1))
        return min(h1, h2) - max(l1, l2) > tol
    return False


def seg_cross(a, b):
    (ax0, ay0), (ax1, ay1) = a
    (bx0, by0), (bx1, by1) = b
    av, bv = abs(ax0 - ax1) < .5, abs(bx0 - bx1) < .5
    if av == bv:
        return False
    if av:
        vx, vy0, vy1 = ax0, *sorted((ay0, ay1))
        hy, hx0, hx1 = by0, *sorted((bx0, bx1))
    else:
        vx, vy0, vy1 = bx0, *sorted((by0, by1))
        hy, hx0, hx1 = ay0, *sorted((ax0, ax1))
    return hx0 + .5 < vx < hx1 - .5 and vy0 + .5 < hy < vy1 - .5


def search(start, sdir, goal, gdir, rects, fixed, xs, ys,
           budget=200000, hull=None, ban_inner=False, clear_rects=()):
    """从 start 沿 sdir 出发，到 goal 沿 gdir 进入（gdir 是进入方向）。
    返回骨架折线，或 None。"""
    sx, sy = start
    gx, gy = goal
    # 出端强制走满 D_OUT，入端预留 D_IN，两端各先定一个锚点
    dv = DIR[sdir]
    a0 = (sx + dv[0] * D_OUT, sy + dv[1] * D_OUT)
    gv = DIR[gdir]
    a1 = (gx - gv[0] * D_IN, gy - gv[1] * D_IN)
    # 出入两端的这一小段贴着自己的节点边界，用 pad 判定不算穿越；
    # 若真被判穿，说明端口或方向给错了，直接失败而不是放行
    if blocked(start, a0, rects) or blocked(a1, goal, rects):
        return None

    xi = {v: i for i, v in enumerate(xs)}
    yi = {v: i for i, v in enumerate(ys)}
    for v in (a0[0], a1[0]):
        if v not in xi:
            xs = sorted(xs + [v]); xi = {u: i for i, u in enumerate(xs)}
    for v in (a0[1], a1[1]):
        if v not in yi:
            ys = sorted(ys + [v]); yi = {u: i for i, u in enumerate(ys)}

    def neighbours(ix, iy, d):
        """沿四个方向走到相邻网格点。与当前方向不同即为一次拐弯。"""
        for nd, (dx, dy) in DIR.items():
            jx, jy = ix + (1 if dx > 0 else -1 if dx < 0 else 0), \
                     iy + (1 if dy > 0 else -1 if dy < 0 else 0)
            if not (0 <= jx < len(xs) and 0 <= jy < len(ys)):
                continue
            p = (xs[ix], ys[iy])
            q = (xs[jx], ys[jy])
            step = math.dist(p, q)
            if step < 1e-9:
                continue
            if nd != d and step < D_CORNER:
                continue
            yield jx, jy, nd, p, q, step

    start_state = (xi[a0[0]], yi[a0[1]], sdir)
    goal_cell = (xi[a1[0]], yi[a1[1]])
    dist = {start_state: 0.0}
    prev = {}
    pq = [(0.0, start_state)]
    seen = 0
    seg_cache = {}
    while pq:
        c, st = heapq.heappop(pq)
        if c > dist.get(st, 1e18):
            continue
        ix, iy, d = st
        if (ix, iy) == goal_cell and d == gdir:
            pts = [goal, a1]
            cur = st
            while cur in prev:
                cur, p = prev[cur]
                pts.append(p)
            # 出端锚点 a0 不在 prev 链上（它是起点，没有前驱）。
            # 漏掉它就会从第一个网格点直接连回 start，两点不同轴就是一条斜线。
            # 整套走线全是正交的，出现斜线一定是重建的错，不是搜索的错。
            pts.append(a0)
            pts.append(start)
            pts.reverse()
            return pts
        seen += 1
        if seen > budget:
            return None
        for jx, jy, nd, p, q, step in neighbours(ix, iy, d):
            # 一小段 (p, q) 的罚分只取决于这一段本身，与从哪个方向走到 p 无关，
            # 而同一个网格点会以四个方向各进一次队列，同一段因此被重复算上几遍。
            # 这里按段缓存，算法、罚分与加法顺序一律不变，结果逐位相同。
            key = (ix, iy, jx, jy)
            parts = seg_cache.get(key)
            if parts is None:
                if blocked(p, q, rects, clear_rects=clear_rects):
                    parts = False
                else:
                    inner = inner_penalty(p, q, hull)
                    if ban_inner and hull and inner > 0:
                        parts = False
                    else:
                        parts = (W_CROSS * sum(1 for f in fixed if seg_cross((p, q), f)),
                                 # 共线重叠比交叉更不能接受：交叉至少看得出是两条线，
                                 # 重叠就直接看成一条了，那条关系在图上等于没有
                                 W_CROSS * 2 * sum(1 for f in fixed if seg_overlap((p, q), f)),
                                 inner,
                                 hug_penalty(p, q, rects))  # 贴边罚分：改常量会让手工骨架过期，改罚分不会
                seg_cache[key] = parts
            if parts is False:
                continue
            add = step + (W_BEND if nd != d else 0.0)
            add += parts[0]
            add += parts[1]
            add += parts[2]
            add += parts[3]
            ns = (jx, jy, nd)
            nc = c + add
            if nc < dist.get(ns, 1e18) - 1e-9:
                dist[ns] = nc
                prev[ns] = (st, (xs[jx], ys[jy]))
                heapq.heappush(pq, (nc, ns))
    return None


def simplify(pts):
    """去掉共线的中间点。"""
    out = [pts[0]]
    for p in pts[1:]:
        if len(out) >= 2:
            a, b = out[-2], out[-1]
            if abs((b[0]-a[0])*(p[1]-b[1]) - (b[1]-a[1])*(p[0]-b[0])) < 1e-9:
                out[-1] = p
                continue
        if math.dist(out[-1], p) > 1e-9:
            out.append(p)
    return out
