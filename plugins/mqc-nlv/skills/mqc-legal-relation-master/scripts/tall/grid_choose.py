# -*- coding: utf-8 -*-
import os
"""网格形状的枚举：形状比布局本身还要紧。

实测同样 12 个主体，2×6 与 4×3 的差距是交叉 9 比 1、拐弯 32 比 20。

想过用「行列比不超过 2」之类的规则先筛一遍，但数据不支持：
    12 主体　4×3（高瘦）最优，2×6（宽扁）最差
    10 主体　2×5（宽扁）最优，5×2（高瘦）最差
方向正好相反，说明形状的好坏取决于关系的具体结构，没有简单的先验规则。
所以不设规则，候选放宽后全部实际走线，让结果说话。

必须实际走线来选：布局目标函数对交叉的相关系数只有 +0.36，选不出来。
"""
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from layout_heuristic import solve_large
from optimize import refine

NW, NH = 140, 78


def candidate_grids(n, max_ratio=4.0, max_empty=5):
    """候选放得宽一些。原设行列比 3、空格 3，13 主体的最优形状 2×7
    （比 3.5）正好被排除，交叉从 7 涨到 10。筛选规则只该挡掉明显荒唐的
    形状，不该替实测做判断。"""
    out = []
    for r in range(1, n + 1):
        for c in range(1, n + 1):
            if r * c < n or r * c - n > max_empty:
                continue
            if max(r, c) / min(r, c) > max_ratio:
                continue
            out.append((r, c))
    return out


def solve(nodes, edges, col=340, row=200, restarts=4, sweeps=30,
          rounds=3, verbose=False):
    n = len(nodes)
    best = None
    for g in candidate_grids(n):
        try:
            c, a = solve_large(nodes, edges, g, restarts=restarts, sweeps=sweeps)
            pos = {k: (v[1] * col + 70, v[0] * row + 24) for k, v in a.items()}
            rects = {k: (v[1] * col, v[0] * row, NW, NH) for k, v in a.items()}
            pp, sk, sc = refine(pos, rects, edges, rounds=rounds)
        except Exception as e:
            if verbose:
                print(f"  {g[0]}x{g[1]} 走不通：{str(e)[:40]}")
            continue
        if verbose:
            print(f"  {g[0]}x{g[1]}　交叉 {sc[0]}　拐弯 {sc[1]}")
        if best is None or sc < best[0]:
            best = (sc, g, a, pos, rects, pp, sk)
    if best is None:
        raise ValueError("所有网格形状都走不通")
    return best
