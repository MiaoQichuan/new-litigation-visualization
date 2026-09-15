# -*- coding: utf-8 -*-
"""端口方案的局部改进。

规划阶段只保证可行：直连的关系靠 equal_k 与 equal_index 锁死，
其余按方位取第一个可行候选。这对 甲案够了（拐弯 11→6），
对 乙案却退步（14→20）——那五条非直连关系的端口被挤到了
不好的位置，而规划阶段并不知道走线代价。

所以补一轮局部改进：逐条尝试换侧，重走全图，只在字典序 (交叉, 拐弯, 长度)
变好时接受。直连关系与被锁定的侧一律不动。
"""
import sys, math, itertools
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
from port_plan import plan, port_offset, CANDS, bearing, SIDES, CAP, OPP
from port_offsets import assign as assign_offsets, port_xy as _pxy
from path_search import build_grid, search, simplify
from joint_route import hull_of

NW, NH = 140, 48


def port_xy(pos, v, s, i, k, off=None):
    """off 给定时直接用它，不再按 (i,k) 等分算。
    等分是「没有别的要求时」的排法，有对齐要求时必须让位。"""
    cx, cy = pos[v]
    o = port_offset(k, i, s) if off is None else off
    return {"L": (cx - NW / 2, cy + o), "R": (cx + NW / 2, cy + o),
            "T": (cx + o, cy - NH / 2), "B": (cx + o, cy + NH / 2)}[s]


def _cross(x, y):
    (ax0, ay0), (ax1, ay1) = x
    (bx0, by0), (bx1, by1) = y
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


def route_all(pos, rects, edges, pplan, xs, ys, hull):
    obst = list(rects.values())
    offs = assign_offsets(pos, edges, pplan)
    fixed, skel = [], []
    for i, (a, b) in enumerate(edges):
        sa, ja, ka, sb, jb, kb = pplan[i]
        _, oa, _, ob = offs[i]
        p0 = port_xy(pos, a, sa, ja, ka, oa)
        p1 = port_xy(pos, b, sb, jb, kb, ob)
        q = search(p0, sa, p1, OPP[sb], obst, fixed, xs, ys, hull=hull,
                   ban_inner=True)
        if q is None:
            q = search(p0, sa, p1, OPP[sb], obst, fixed, xs, ys, hull=hull)
        if q is None:
            return None
        q = simplify(q)
        skel.append(q)
        fixed += list(zip(q, q[1:]))
    return skel


def score(skel):
    """字典序 (交叉, 拐弯, 长度)，越小越好。"""
    sg = [list(zip(s, s[1:])) for s in skel]
    C = sum(1 for i, j in itertools.combinations(range(len(sg)), 2)
            for u in sg[i] for v in sg[j] if _cross(u, v))
    B = sum(len(s) - 2 for s in skel)
    L = sum(math.dist(u, v) for s in skel for u, v in zip(s, s[1:]))
    return (C, B, round(L, 1))


def refine(pos, rects, edges, rounds=2, verbose=False):
    """返回改进后的 (pplan, skel, score)。"""
    pplan, load, straight = plan(pos, edges)
    locked = set()
    for i in sorted(straight):
        a, b = edges[i]
        locked.add((a, pplan[i][0]))
        locked.add((b, pplan[i][3]))

    ports = []
    _o = assign_offsets(pos, edges, pplan)
    for i, (a, b) in enumerate(edges):
        sa, ja, ka, sb, jb, kb = pplan[i]
        ports += [port_xy(pos, a, sa, ja, ka, _o[i][1]),
                  port_xy(pos, b, sb, jb, kb, _o[i][3])]
    xs, ys = build_grid(list(rects.values()), ports)
    hull = hull_of(rects)

    best_skel = route_all(pos, rects, edges, pplan, xs, ys, hull)
    if best_skel is None:
        raise ValueError("初始方案走不通")
    best = score(best_skel)
    if verbose:
        print(f"  初始　交叉 {best[0]}　拐弯 {best[1]}　长 {best[2]:.0f}")

    for rnd in range(rounds):
        improved = False
        # 拐弯最多的先试：它最可能是被挤到坏位置的那条
        order = sorted((i for i in range(len(edges)) if i not in straight),
                       key=lambda i: -(len(best_skel[i]) - 2))
        for i in order:
            a, b = edges[i]
            cur = pplan[i]
            for sa in SIDES:
                for sb in SIDES:
                    if (sa, sb) == (cur[0], cur[3]):
                        continue
                    if (a, sa) in locked or (b, sb) in locked:
                        continue
                    cand = dict(pplan)
                    # 换侧后该侧的端口数变了，两侧都要重排序号
                    cand[i] = (sa, 1, 1, sb, 1, 1)
                    trial = _renumber(pos, edges, cand, straight)
                    if trial is None:
                        continue
                    sk = route_all(pos, rects, edges, trial, xs, ys, hull)
                    if sk is None:
                        continue
                    s = score(sk)
                    if s < best:
                        best, best_skel, pplan = s, sk, trial
                        improved = True
                        if verbose:
                            print(f"  第 {rnd+1} 轮　{a}→{b} 换到 {sa}→{sb}："
                                  f"交叉 {s[0]}　拐弯 {s[1]}　长 {s[2]:.0f}")
                        break
                if improved:
                    break
            if improved:
                break
        if not improved:
            break
    return pplan, best_skel, best


def _renumber(pos, edges, pplan, straight):
    """换侧之后重排每一侧的序号，并把直连关系两端取齐。容量超了返回 None。"""
    load = {}
    for i, (a, b) in enumerate(edges):
        sa, _, _, sb, _, _ = pplan[i]
        load.setdefault((a, sa), []).append(i)
        load.setdefault((b, sb), []).append(i)
    for (v, s), members in load.items():
        if len(members) > CAP[s]:
            return None
        L = NW if s in "TB" else NH
        if len(members) >= 2 and L / (len(members) + 1) < 26:
            return None
    out = {}
    idx = {}
    for (v, s), members in load.items():
        axis = 0 if s in "TB" else 1
        def key(i):
            other = edges[i][1] if edges[i][0] == v else edges[i][0]
            return (pos[other][axis], other, i)
        for j, i in enumerate(sorted(members, key=key), 1):
            idx[(i, v, s)] = (j, len(members))
    for i, (a, b) in enumerate(edges):
        sa, _, _, sb, _, _ = pplan[i]
        ja, ka = idx[(i, a, sa)]
        jb, kb = idx[(i, b, sb)]
        if i in straight:
            if ka != kb:
                return None
            if ja != jb:
                jb = ja                      # 直连两端取齐
        out[i] = (sa, ja, ka, sb, jb, kb)
    return out
