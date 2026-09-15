# -*- coding: utf-8 -*-
"""1 到 6 个主体：直接取用存好的布局，不跑搜索。

这一档的图全部穷举过（143 张），索引里存的是**结果**而非候选。
运行时算一次规范形式，查到布局直接用，省掉布局搜索与粗筛精修。

规范形式要同时记下达到它的那个顶点排列，否则索引里的布局
对不回实际的主体——这一步先前漏过，是这类查表最容易错的地方。
"""
import sys, json, itertools, os
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

_SMALL = None


def table():
    global _SMALL
    if _SMALL is None:
        p = os.path.join(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets"),
                         "idx_small.json")
        _SMALL = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}
    return _SMALL


def canon_with_map(n, edges):
    """返回 (规范位串, 顶点排列)。排列把实际顶点编号映射到索引里的编号。"""
    best, bestp = None, None
    for p in itertools.permutations(range(n)):
        s = "".join("1" if (min(p[i], p[j]), max(p[i], p[j])) in edges else "0"
                    for i in range(n) for j in range(i + 1, n))
        if best is None or s < best:
            best, bestp = s, p
    return best, bestp


def lookup(nodes, edges):
    """查到就返回 (网格, 每个主体的格位, 索引记录)，查不到返回 None。

    映射不靠规范形式的排列，而是直接拿索引里存的边集找同构。
    原因是建索引时存的 layout 用的是**原始边集的顶点编号**，
    没有重标号成规范编号；靠 perm 反推会对不上，实测索引记零交叉、
    实走却是 1 交叉 13 拐弯。n≤6 最多枚举 720 种排列，找同构很快。
    """
    ids = [n["id"] if isinstance(n, dict) else n for n in nodes]
    n = len(ids)
    if not (1 <= n <= 6):
        return None
    idx = {x: i for i, x in enumerate(ids)}
    E = {(min(idx[a], idx[b]), max(idx[a], idx[b])) for a, b, *_ in edges}
    c, _ = canon_with_map(n, E)
    rec = table().get(f"{n}:{c}")
    if not rec or not rec.get("ok"):
        return None
    stored = {tuple(e) for e in rec.get("edges", [])}
    lay = rec.get("layout") or {}
    if not lay:
        return None
    # 找一个把实际顶点映到存储顶点的排列，使两边的边集重合
    for p in itertools.permutations(range(n)):
        if {(min(p[a], p[b]), max(p[a], p[b])) for a, b in E} == stored:
            out = {}
            for i, x in enumerate(ids):
                k = f"V{p[i]}"
                if k not in lay:
                    return None
                out[x] = tuple(lay[k])
            return tuple(rec["grid"]), out, rec
    return None
