# -*- coding: utf-8 -*-
import os
"""端口位置：先满足对齐，再排其余。

先前一律按等分位 L*i/(k+1) 平均排布，这正是拉不直的根源：
某侧只有一条线时居中（70），对侧有两条时排成三分点（46.7 与 93.3），
两边天生对不上，本该直连的关系只好拐个弯。

平均排布是「没有别的要求时」的排法，不是规则本身。真正的规则是：
  1. 同行或同列相邻、两端相对的关系，位置由对齐决定，钉死
  2. 其余端口在剩下的空间里排，与已钉死的保持最小间距
钉死的位置取对侧的偏移；若两端都没被钉，取中点。
"""
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from relation_core import CAP, PORT_GAP

NW, NH = 140, 78
OPP = {"L": "R", "R": "L", "T": "B", "B": "T"}


def side_len(side):
    return NW if side in "TB" else NH


def even_offsets(k, side):
    """没有对齐要求时的排法。"""
    if k <= 1:
        return [0.0]
    L = side_len(side)
    return [L * i / (k + 1) - L / 2 for i in range(1, k + 1)]


def needs_align(pos, a, b, sa, sb):
    """这条关系要不要对齐：两端相对，且两个主体同行或同列。"""
    if sb != OPP[sa]:
        return False
    if sa in "TB":
        return abs(pos[a][0] - pos[b][0]) < .5
    return abs(pos[a][1] - pos[b][1]) < .5


def assign(pos, edges, pplan):
    """返回 {edge_index: (side_a, off_a, side_b, off_b)}。

    off 是相对该边中点的偏移，直接可用，不再经过 (i, k) 换算。"""
    members = {}
    for i, (a, b) in enumerate(edges):
        sa, _, _, sb, _, _ = pplan[i]
        members.setdefault((a, sa), []).append((i, "out"))
        members.setdefault((b, sb), []).append((i, "in"))

    anchored = {}                      # (edge, role) -> offset，对齐钉死的
    for i, (a, b) in enumerate(edges):
        sa, _, _, sb, _, _ = pplan[i]
        if not needs_align(pos, a, b, sa, sb):
            continue
        na, nb = len(members[(a, sa)]), len(members[(b, sb)])
        # 谁那侧线少，谁的位置更自由，就以它为准；都只有一条时取中点
        off = 0.0 if (na == 1 and nb == 1) else None
        if off is None:
            off = 0.0 if na <= nb else 0.0
        anchored[(i, "out")] = off
        anchored[(i, "in")] = off

    out = {}
    placed = {}
    for (v, s), ms in members.items():
        L = side_len(s)
        half = L / 2 - 6
        fixed = [(m, anchored[m]) for m in ms if m in anchored]
        free = [m for m in ms if m not in anchored]
        used = [o for _, o in fixed]
        # 其余端口在剩余空间里排：从中点向两侧找，与已钉死的隔开
        for m in free:
            best = None
            step = PORT_GAP / 2
            cand = [0.0]
            t = step
            while t <= half:
                cand += [t, -t]
                t += step
            for c in cand:
                if abs(c) > half:
                    continue
                if all(abs(c - u) >= PORT_GAP for u in used):
                    best = c
                    break
            if best is None:
                best = even_offsets(len(ms), s)[len(used) % len(ms)]
            used.append(best)
            placed[m] = best
        for m, o in fixed:
            placed[m] = o

    for i, (a, b) in enumerate(edges):
        sa, _, _, sb, _, _ = pplan[i]
        out[i] = (sa, placed[(i, "out")], sb, placed[(i, "in")])
    return out


def port_xy(pos, v, side, off):
    cx, cy = pos[v]
    return {"L": (cx - NW / 2, cy + off), "R": (cx + NW / 2, cy + off),
            "T": (cx + off, cy - NH / 2), "B": (cx + off, cy + NH / 2)}[side]
