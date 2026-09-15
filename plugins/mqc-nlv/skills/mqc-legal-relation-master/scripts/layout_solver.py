# -*- coding: utf-8 -*-
"""法律关系图 · 布局求解器。

排布不是画出来的，是算出来的。

给定主体与关系，每个主体的出发点数与回归点数就定了；
一个节点只有四条边、每条边能挂的线有限，所以哪些主体必须靠近、
哪些必须占据四面开阔的位置，都是可以穷举的。

做法：把主体放进 rows×cols 的网格，穷举全部分配，用代价函数打分，取最低。
代价只算四件事，都是走线好不好画的直接原因：
  1. 每条关系的走线代价（相邻直连最省，隔着节点最贵）
  2. 每个节点每条边的端口负载（一条边挤太多线就要罚）
  3. 同属性的主体是否挨着
  4. 跨列跨行的线要占通道，通道越挤越罚
"""
from itertools import permutations


def degrees(nodes, edges):
    """每个主体的出发点数与回归点数。排布的全部依据都从这里来。"""
    out = {n["id"]: 0 for n in nodes}
    inn = {n["id"]: 0 for n in nodes}
    for a, b, *_ in edges:
        out[a] += 1
        inn[b] += 1
    return {k: dict(out=out[k], inn=inn[k], deg=out[k] + inn[k]) for k in out}


# 两个槽位之间走一条线的代价
def _edge_cost(p, q):
    (r1, c1), (r2, c2) = p, q
    dr, dc = abs(r1 - r2), abs(c1 - c2)
    if dr == 0 and dc == 1: return 0.0      # 同行相邻，直连
    if dc == 0 and dr == 1: return 0.0      # 同列相邻，直连
    if dr == 1 and dc == 1: return 1.0      # 斜对角，拐一次
    if dr == 0: return 2.5 + (dc - 2)       # 同行不相邻，要绕过中间的节点
    if dc == 0: return 2.5 + (dr - 2)       # 同列不相邻，同上
    return 1.6 + 0.4 * (dr + dc - 2)        # 跨行跨列，走通道带


def _side(p, q):
    """这条线从 p 的哪一侧出去。端口负载按侧统计。"""
    (r1, c1), (r2, c2) = p, q
    if abs(c2 - c1) >= abs(r2 - r1):
        return "R" if c2 > c1 else "L"
    return "B" if r2 > r1 else "T"


def score(assign, nodes, edges, port_cap=2, w_group=2.0, w_port=2.5):
    """assign: {id: (row, col)}。分数越低越好。"""
    total = 0.0
    load = {n["id"]: {"L": 0, "R": 0, "T": 0, "B": 0} for n in nodes}
    for a, b, *_ in edges:
        pa, pb = assign[a], assign[b]
        total += _edge_cost(pa, pb)
        load[a][_side(pa, pb)] += 1
        load[b][_side(pb, pa)] += 1
    for nid, sides in load.items():
        for s, k in sides.items():
            if k > port_cap:
                total += w_port * (k - port_cap)
    grp = {}
    for n in nodes:
        grp.setdefault(n.get("group", n["id"]), []).append(n["id"])
    for g, ids in grp.items():
        if len(ids) < 2:
            continue
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                (r1, c1), (r2, c2) = assign[ids[i]], assign[ids[j]]
                if abs(r1 - r2) + abs(c1 - c2) > 1:
                    total += w_group
    return total


def solve(nodes, edges, grids=None, port_cap=2, top=3):
    """穷举网格与分配，返回打分最低的几个方案。
    主体数在十个以内时穷举是可行的（10! 约三百六十万，仍能跑完）。"""
    n = len(nodes)
    if grids is None:
        grids = [(r, c) for r in range(1, n + 1) for c in range(1, n + 1)
                 if r * c >= n and r * c <= n + 2 and r <= c]
    best = []
    for rows, cols in grids:
        slots = [(r, c) for r in range(rows) for c in range(cols)]
        ids = [x["id"] for x in nodes]
        for perm in permutations(slots, n):
            assign = dict(zip(ids, perm))
            s = score(assign, nodes, edges, port_cap)
            best.append((s, (rows, cols), assign))
            if len(best) > 4000:
                best.sort(key=lambda x: x[0])
                best = best[:top]
    best.sort(key=lambda x: x[0])
    return best[:top]


def report(nodes, edges):
    d = degrees(nodes, edges)
    print("主体　　　　　出发　回归　合计　属性")
    for n in sorted(nodes, key=lambda x: -d[x["id"]]["deg"]):
        k = d[n["id"]]
        print(f"  {n['name']:<14}{k['out']:>3}{k['inn']:>6}{k['deg']:>6}   "
              f"{n.get('group', '')}")
    print(f"\n关系 {len(edges)} 条，主体 {len(nodes)} 个")
    return d
