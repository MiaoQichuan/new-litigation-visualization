# -*- coding: utf-8 -*-
"""端口与路径联合求解。

先定端口再搜路径是错的：搜索只能在给定的出入边之间找路，
端口选错了，再好的搜索也救不回来。实测两条绕行线因此走偏——
候选顺序是死的字母序，R→L 排在 R→B 前面就先被选走，
可从下方绕过来的线本该从下边进。

改成：端口分配只给候选，每个候选各搜一次路径，按实际代价取最优。
代价用拐弯与长度（交叉已在搜索内部计价）。容量按已占用的边校验，
只考虑完全空闲的边或本条已占的边，不去挤别人的位置。
"""
import math, sys
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
from path_search import search, simplify, DIR, W_BEND, inner_penalty, hug_penalty
ARROW_LEN = 12
from port_assign import assign, port_offsets, CAP

NW, NH = 140, 48
OPP = {"L": "R", "R": "L", "T": "B", "B": "T"}
STUB_NEAR = 60.0       # 中间段短于此即视为贴角小拐
W_STUB = 6.0           # 每短一个单位的罚分


def port_xy(pos, nid, side, i, k):
    cx, cy = pos[nid]
    off = port_offsets(k, side)[i - 1]
    return {"L": (cx - NW / 2, cy + off), "R": (cx + NW / 2, cy + off),
            "T": (cx + off, cy - NH / 2), "B": (cx + off, cy + NH / 2)}[side]


def cost(path, hull=None, rects=None):
    """比较候选时用的代价，必须与搜索内部的口径一致。
    内腹罚分只在搜索里生效、这里却不算，等于把它的效果抵消掉——
    选出来的仍是穿内腹那条。两处口径不一致是个隐蔽的坑。"""
    if path is None:
        return float("inf")
    L = sum(math.dist(u, v) for u, v in zip(path, path[1:]))
    pen = sum(inner_penalty(u, v, hull) for u, v in zip(path, path[1:]))
    # 贴角小拐：中间段短得只够擦着目标的一个角拐一下，再从侧面挤进去。
    # 长度上它比绕到正面便宜，看着却很别扭——绕到下方直接从底边中央
    # 进来才干净。短段按差额罚，越短罚得越重。
    for u, v in zip(path[1:-2], path[2:-1]):
        d = math.dist(u, v)
        if d < STUB_NEAR:
            pen += (STUB_NEAR - d) * W_STUB
    return (len(path) - 2) * W_BEND + L + pen


def hug_count(path, rects, near=34.0):
    """路径贴着几个主体走。

    判据用贴边数，不用长度倍数：外围路径未必比内腹长，
    可它会一路擦着好几个主体的边过去，看着比穿过内腹难看得多。
    「连续跟三个模块紧密贴合」就是这个量。"""
    hug = set()
    for (x0, y0), (x1, y1) in zip(path, path[1:]):
        for k, (rx, ry, rw, rh) in rects.items():
            if abs(x0 - x1) < .5:
                lo, hi = sorted((y0, y1))
                if hi < ry - near or lo > ry + rh + near:
                    continue
                if min(abs(x0 - rx), abs(x0 - (rx + rw))) < near:
                    hug.add(k)
            else:
                lo, hi = sorted((x0, x1))
                if hi < rx - near or lo > rx + rw + near:
                    continue
                if min(abs(y0 - ry), abs(y0 - (ry + rh))) < near:
                    hug.add(k)
    return len(hug)


def _hits(seg, rect, pad=3.0):
    (x0, y0), (x1, y1) = seg[0], seg[1]
    rx, ry, rw, rh = rect
    if abs(x0 - x1) < .5:
        if not (rx + pad < x0 < rx + rw - pad):
            return False
        lo, hi = sorted((y0, y1))
        return lo < ry + rh - pad and hi > ry + pad
    if abs(y0 - y1) < .5:
        if not (ry + pad < y0 < ry + rh - pad):
            return False
        lo, hi = sorted((x0, x1))
        return lo < rx + rw - pad and hi > rx + pad
    return False


def hull_of(rects, shrink=30):
    """内腹区：所有主体的总包围盒往里收一点，免得把贴边的正常走线也罚了。"""
    xs = [r[0] for r in rects.values()] + [r[0] + r[2] for r in rects.values()]
    ys = [r[1] for r in rects.values()] + [r[1] + r[3] for r in rects.values()]
    return (min(xs) + shrink, min(ys) + shrink, max(xs) - shrink, max(ys) - shrink)


def solve(pos, rects, edges, xs, ys, verbose=False):
    """返回每条关系的骨架与最终端口。"""
    base, load = assign(pos, edges)
    hull = hull_of(rects)
    # 记录每条边当前占用的侧，用来判断哪些侧是空闲的
    used = {k: dict(v) for k, v in load.items()}
    out, fixed = [], []
    for i, (a, b) in enumerate(edges):
        sa0, ja0, ka0, sb0, jb0, kb0 = base[i]
        cands = []
        # 候选：当前分配，加上两端各自的空闲边（不挤占别人）
        # 候选只收完全空闲的边。
        #
        # 试过放开到「还有余量」的边（上下边容量 4，占一条还能挂三条），
        # 结果更差：换到已有线的边上，该边线数加一，端口位置按等分位重算，
        # 已经走好的那几条跟着错位、全要重新对齐，一轮算下来拐弯从 17 涨到 18、
        # 交叉从 4 涨到 5。要用这条路子，得把受影响的线一起重算并迭代到稳定，
        # 不是加一个候选就能了事的。
        free_a = [s for s in "LRTB" if used[a][s] == 0] + [sa0]
        free_b = [s for s in "LRTB" if used[b][s] == 0] + [sb0]
        for sa in dict.fromkeys(free_a):
            for sb in dict.fromkeys(free_b):
                ka = ka0 if sa == sa0 else 1
                kb = kb0 if sb == sb0 else 1
                ja = ja0 if sa == sa0 else 1
                jb = jb0 if sb == sb0 else 1
                cands.append((sa, ja, ka, sb, jb, kb))
        best = (float("inf"), None, None)
        # 端点节点也要当障碍：把它们排除掉，线就能从自己的边界出发后
        # 掉头穿过自己的节点。出入两端的 stub 点本来就在节点外，
        # 边界上的那一小段用 pad 判定不会误报，所以全部纳入是安全的。
        # 端点自己的主体只挡本体（线要从它边上出来）；
        # 其余主体外扩一圈净空，线不许贴着它们走
        own = [rects[a], rects[b]]
        others = [r for k, r in rects.items() if k not in (a, b)]
        for sa, ja, ka, sb, jb, kb in cands:
            p0 = port_xy(pos, a, sa, ja, ka)
            p1 = port_xy(pos, b, sb, jb, kb)
            # 直连的条件有三条，缺一不可：
            #   两端的侧相对、坐标对齐、**而且出侧朝着目标**。
            # 只看前两条会把「从上边出、进对方下边」也判成正对，
            # 可源在目标上方时从上边出是背离的，线必然要绕过两个节点。
            # 障碍也要含端点自己——漏掉它们，线就直接穿过自己的主体。
            dx, dy = p1[0] - p0[0], p1[1] - p0[1]
            toward = DIR[sa][0] * dx + DIR[sa][1] * dy > 0
            if sb == OPP[sa] and toward and (
                    abs(p0[0] - p1[0]) < .5 if sa in "TB" else abs(p0[1] - p1[1]) < .5):
                # 两条分支都返回端口原点，退箭头长的事统一交给渲染做一次
                straight = [p0, p1]
                if not any(_hits(straight, r) for r in others):
                    c = cost(straight, hull, list(rects.values()))
                    if c < best[0] - 1e-9:
                        best = (c, straight, (sa, ja, ka, sb, jb, kb))
                    continue
            # 先按硬约束搜：绕行不许进内腹。搜不到再放开，
            # 放开是兜底，不是常态——正常的图都应该走得通外围。
            obst = own + others
            path = search(p0, sa, p1, OPP[sb], obst, fixed, xs, ys,
                          hull=hull, ban_inner=True)
            if path is None:
                path = search(p0, sa, p1, OPP[sb], obst, fixed, xs, ys, hull=hull)
            if path is None:
                continue
            path = simplify(path)
            c = cost(path, hull, list(rects.values()))
            if c < best[0] - 1e-9:
                best = (c, path, (sa, ja, ka, sb, jb, kb))
        if best[1] is None:                       # 候选全不通，退回基础分配
            sa, ja, ka, sb, jb, kb = base[i]
            p0 = port_xy(pos, a, sa, ja, ka)
            p1 = port_xy(pos, b, sb, jb, kb)
            path = simplify(search(p0, sa, p1, OPP[sb], own + others, fixed, xs, ys, hull=hull))
            best = (cost(path, hull, list(rects.values())), path, base[i])
        c, path, pick = best
        if verbose and pick != base[i]:
            print(f"    {a}→{b}　{base[i][0]}→{base[i][3]} 改为 {pick[0]}→{pick[3]}"
                  f"　拐弯 {len(path)-2}")
        # 更新占用：原来的侧退掉，新的侧占上
        used[a][base[i][0]] -= 1
        used[b][base[i][3]] -= 1
        used[a][pick[0]] += 1
        used[b][pick[3]] += 1
        out.append((path, pick))
        fixed += list(zip(path, path[1:]))
    return out
