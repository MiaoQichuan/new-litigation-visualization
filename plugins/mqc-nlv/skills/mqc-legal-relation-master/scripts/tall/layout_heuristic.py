# -*- coding: utf-8 -*-
import os
"""大规模布局：穷举换成局部搜索。

穷举到 9 个主体是极限（9! 约 36 万还能跑，10! 已经 363 万，
12! 是 4.8 亿，不可能）。12 个主体必须用启发式。

做法是成对交换加多起点重启，确定性：起点由度数排序给出，
随机数用固定种子，同样的输入必得同样的输出。
"""
import random, itertools
from layout_solver import score as score_basic


def solve_large(nodes, edges, grid, restarts=6, sweeps=40, seed=20260915,
                score=None, topk=1):
    score = score or score_basic
    rows, cols = grid
    slots = [(r, c) for r in range(rows) for c in range(cols)]
    ids = [n["id"] for n in nodes]
    deg = {i: 0 for i in ids}
    for a, b, *_ in edges:
        deg[a] += 1
        deg[b] += 1
    # 起点：度数高的放靠中心的槽位，这比随机起点收敛快得多
    cy, cx = (rows - 1) / 2, (cols - 1) / 2
    ranked_slots = sorted(slots, key=lambda s: abs(s[0] - cy) + abs(s[1] - cx))
    ranked_ids = sorted(ids, key=lambda i: -deg[i])
    best, pool = None, []
    rng = random.Random(seed)
    for r in range(restarts):
        if r == 0:
            assign = dict(zip(ranked_ids, ranked_slots))
        else:
            shuffled = list(ranked_slots)
            rng.shuffle(shuffled)
            assign = dict(zip(ranked_ids, shuffled))
        cur = score(assign, nodes, edges)
        for _ in range(sweeps):
            improved = False
            for a, b in itertools.combinations(ids, 2):
                assign[a], assign[b] = assign[b], assign[a]
                s = score(assign, nodes, edges)
                if s < cur - 1e-9:
                    cur, improved = s, True
                else:
                    assign[a], assign[b] = assign[b], assign[a]
            if not improved:
                break
        pool.append((cur, dict(assign)))
        if best is None or cur < best[0]:
            best = (cur, dict(assign))
    if topk <= 1:
        return best
    # 去掉重复的分配，按分数取前 K 个交给下一阶段实际走线
    seen, out = set(), []
    for c, a in sorted(pool, key=lambda x: x[0]):
        key = tuple(sorted(a.items()))
        if key in seen:
            continue
        seen.add(key)
        out.append((c, a))
        if len(out) >= topk:
            break
    return out
