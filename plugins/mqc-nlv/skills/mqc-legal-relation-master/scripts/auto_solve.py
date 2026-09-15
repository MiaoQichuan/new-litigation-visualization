# -*- coding: utf-8 -*-
"""统一入口：按规模与结构自动选尺寸、网格与轮数，一次出图。

这些规则都是离线基准跑出来的，运行时只查表，不现算。
使用者点一次就该出图，不该像调试时那样反复试。
"""
import sys, time
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

# 离线基准得出的推荐网格，**按结构分开存**。
#
# 先前只按规模存一份，取的是「所有结构里最好的那个网格」，
# 结果对一种结构好、对另一种就差：9 主体时混合的最优是 2x5、
# 双核是 3x4，混用一份表会让双核的交叉从 2 变成 10。
# 不同结构的最优形状本来就不同，必须分开。
# 这份表来自可复现的基准：图的随机种子改用字符和，
# 不再用 hash()——那玩意每个进程都不一样，跑出来的图对不上。
GRID_BY_KIND = {
    "星形": {5: (3, 3), 6: (4, 2), 7: (3, 4), 8: (2, 4), 9: (3, 3), 10: (4, 3), 11: (5, 3)},
    "双核": {5: (3, 3), 6: (2, 4), 7: (6, 2), 8: (2, 4), 9: (3, 4), 10: (4, 3), 11: (7, 2)},
    "链": {5: (3, 3), 6: (2, 4), 7: (3, 4), 8: (3, 4), 9: (3, 3), 10: (5, 2), 11: (2, 6), 12: (6, 2), 13: (2, 8), 14: (4, 4), 15: (3, 5), 16: (2, 8)},
    "混合": {5: (3, 2), 6: (3, 3), 7: (4, 3), 8: (3, 3), 9: (2, 5), 10: (5, 2), 11: (3, 5), 12: (6, 2), 13: (8, 2), 14: (5, 3), 15: (5, 3), 16: (6, 3)},
}
# 高节点有自己的一套：网格是在高节点几何下跑出来的，
# 直接套矮节点的表会走不通（13 星形就是这么失败的）。
TALL_GRID_TABLE = {
    9: [(3, 4), (3, 3)], 10: [(5, 3), (4, 3)], 11: [(4, 4), (5, 3)],
    12: [(4, 3), (5, 3)], 13: [(5, 3), (3, 6)],
}
CAP_SHORT, CAP_TALL = 10, 12


def classify(nodes, edges):
    """认出结构原型。双核要区分两核之间有没有关系——
    有核间边时核的度数是 n−1，没有是 n−2，可画的规模差两档。
    先前把两者混为一谈，会把本可画的案子误判为不可画。"""
    deg = {}
    pair = set()
    for a, b, *_ in edges:
        deg[a] = deg.get(a, 0) + 1
        deg[b] = deg.get(b, 0) + 1
        pair.add(frozenset((a, b)))
    if len(deg) < 5:
        return "小图"
    ranked = sorted(deg, key=lambda k: -deg[k])
    h1, h2 = ranked[0], ranked[1]
    others = [k for k in deg if k not in (h1, h2)]
    rest_max = max((deg[k] for k in others), default=0)
    if deg[h1] >= len(nodes) - 2 and deg[h2] <= rest_max:
        return "星形"
    if deg[h2] >= rest_max * 1.5:
        shared = sum(1 for k in others
                     if frozenset((k, h1)) in pair and frozenset((k, h2)) in pair)
        if shared >= len(others) * 0.4:
            return "双核带核间边" if frozenset((h1, h2)) in pair else "纯双核"
    # 链的判据要看最大度，不是次大度：混合结构里也常有度数 3 的节点，
    # 只看 rest_max 会把混合误判成链（实测 11 主体的混合被判为链）。
    if deg[h1] <= 3:
        return "链"
    return "混合"


def analyze(nodes, edges):
    """先看这张图画不画得出来，以及该用哪种尺寸。"""
    deg = {}
    for a, b, *_ in edges:
        deg[a] = deg.get(a, 0) + 1
        deg[b] = deg.get(b, 0) + 1
    mx = max(deg.values()) if deg else 0
    n = len(nodes)
    kind = classify(nodes, edges)
    twin = kind in ("纯双核", "双核带核间边")
    if mx > CAP_TALL:
        who = [k for k, v in deg.items() if v == mx]
        return dict(ok=False, maxdeg=mx, n=n,
                    reason=f"「{who[0]}」有 {mx} 条关系，超过单个主体能挂的上限 "
                           f"{CAP_TALL}。需要拆图，或把其中几条关系合并表述。")
    # 高节点的三种情形：度数吃紧、双核且规模够大
    tall = mx > CAP_SHORT or (twin and n >= 10)
    return dict(ok=True, maxdeg=mx, n=n, tall=tall, twin=twin, kind=kind)


def solve(nodes, edges, verbose=False, deep=False):
    """deep=False 是十秒档，True 是使用者不满意时的深度档。"""
    info = analyze(nodes, edges)
    if not info["ok"]:
        raise ValueError(info["reason"])
    n, tall = info["n"], info["tall"]
    root = _os.path.join(_HERE, "tall") if tall else _HERE
    if root not in sys.path:
        sys.path.insert(0, root)
    sys.path.remove(root)
    sys.path.insert(0, root)
    import importlib
    import layout_heuristic, optimize
    importlib.reload(layout_heuristic)
    importlib.reload(optimize)
    NH, ROW = (78, 260) if tall else (48, 200)
    if tall:
        grids = TALL_GRID_TABLE.get(n, [])
    else:
        g0 = GRID_BY_KIND.get(info["kind"], {}).get(n)
        # 本结构的最优排第一，再补上邻近结构的作为备选，
        # 让粗筛有的选——结构识别未必百分之百准确
        grids = ([g0] if g0 else []) + [
            v[n] for k, v in GRID_BY_KIND.items()
            if n in v and v[n] != g0][:2]
    if not grids:
        grids = [(r, c) for r in range(2, n) for c in range(2, n)
                 if n <= r * c <= n + 3][:3]
    # 表里存的是按交叉选出来的，往往是宽扁形状，纵向优先在候选内无从发挥。
    # 所以候选里必须保证有一个纵向的，让它有机会胜出。
    # 候选里至少留两个纵向的：表里存的按交叉选，多是宽扁形状，
    # 只补一个未必是好的那个。实测 16 主体的链，纵向里 8x2 是交叉 3、
    # 6x3 却是 7，差得远；只补一个就可能补错。
    port = [g for g in grids if g[0] >= g[1]]
    if len(port) < 2:
        cand = [(r, c) for r in range(2, n + 1) for c in range(2, n + 1)
                if r >= c and n <= r * c <= n + 3 and r / c <= 4.5
                and (r, c) not in grids]
        cand.sort(key=lambda g: (abs(g[0] / g[1] - 2.2), g[0] * g[1]))
        grids = grids + cand[:2 - len(port)]
    coarse, fine, keep = (1, 2, 2) if not deep else (1, 4, 3)
    t0 = time.time()
    rough = []
    for g in grids:
        if g[0] * g[1] < n:
            continue
        try:
            c, a = layout_heuristic.solve_large(nodes, edges, g, restarts=12, sweeps=30)
            pos = {k: (v[1] * 340 + 70, v[0] * ROW + NH / 2) for k, v in a.items()}
            rects = {k: (v[1] * 340, v[0] * ROW, 140, NH) for k, v in a.items()}
            _, _, sc = optimize.refine(pos, rects, edges, rounds=coarse)
            rough.append((sc, g, a, pos, rects))
        except Exception:
            continue
    if not rough:
        raise ValueError("候选网格都走不通，建议拆图")
    # 同等条件下优先纵向（行多列少）。
    #
    # 法律关系图多数是竖着读的：债权人在上、债务人在中、担保人在下，
    # 或者按时间先后从上往下。纯按交叉与拐弯选，常选出 2x8 这种宽扁形状，
    # 读起来别扭。实测纵向的代价很小——13 主体混合是交叉 +2 但拐弯 −5，
    # 16 主体链是交叉 +1 拐弯 +1——拿这点代价换阅读顺手是划算的。
    # 只有当宽扁的交叉少两个以上时，才让它胜出。
    def rank(item):
        sc, g = item[0], item[1]
        portrait = g[0] >= g[1]
        # 纵向让两个交叉。再多就会把明显差的形状抬上来：
        # 16 主体的链，宽扁 2x8 是交叉 2，纵向 8x2 是 3、6x3 却是 7。
        # 让两个能选中 8x2，让五个就会误选 6x3。
        return (sc[0] - (2 if portrait else 0), sc[1], sc[2])
    rough.sort(key=rank)
    best = None
    for sc0, g, a, pos, rects in rough[:keep]:
        try:
            pp, sk, sc = optimize.refine(pos, rects, edges, rounds=fine)
        except Exception:
            continue
        if best is None or sc < best[0]:
            best = (sc, g, a, pos, rects, pp, sk)
    if best is None:
        raise ValueError("精修阶段全部失败")
    if verbose:
        print(f"  {n} 主体　{'高' if tall else '矮'}节点　"
              f"{best[1][0]}x{best[1][1]}　交叉 {best[0][0]}　拐弯 {best[0][1]}"
              f"　{time.time()-t0:.0f}s")
    return best + (info,)
