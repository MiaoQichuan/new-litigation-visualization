# -*- coding: utf-8 -*-
"""查表出图：运行时不再推导任何决定。

跑一次 skill 只做三件事：
  1. 数主体数、算最大度、认结构
  2. 查索引表拿到全部决定（能不能画、用哪档节点、候选网格、各项参数）
  3. 照着跑一遍，不再枚举、不再试

索引表由 build_index.py 离线生成，依据是 5 到 16 主体、四种结构的基准实测。
"""
import sys, json, os, time
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

_IDX = _ALL = None


def index():
    global _IDX
    if _IDX is None:
        p = os.path.join(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets"),
                         "plan_index.json")
        _IDX = json.load(open(p, encoding="utf-8"))
    return _IDX


def index_all():
    """合并索引：7 到 9 走度序列特征组，其余走结构分档。"""
    global _ALL
    if _ALL is None:
        p = os.path.join(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets"),
                         "index_all.json")
        _ALL = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}
    return _ALL


def degseq_key(nodes, edges):
    """度序列特征组的键：主体数、最大度、边数、度数跨度（上限 4）。"""
    deg = {n["id"] if isinstance(n, dict) else n: 0 for n in nodes}
    for a, b, *_ in edges:
        deg[a] = deg.get(a, 0) + 1
        deg[b] = deg.get(b, 0) + 1
    d = sorted(deg.values(), reverse=True)
    return f"{len(d)},{max(d)},{sum(d)//2},{min(max(d)-min(d), 4)}"


def probe(nodes, edges):
    """从案件读出三个特征：主体数、最大度、结构。"""
    from auto_solve import classify
    deg = {}
    for a, b, *_ in edges:
        deg[a] = deg.get(a, 0) + 1
        deg[b] = deg.get(b, 0) + 1
    return dict(n=len(nodes), maxdeg=max(deg.values()) if deg else 0,
                kind=classify(nodes, edges))


def plan(nodes, edges):
    """查表拿决定。表外的规模按最接近的一档兜底。"""
    f = probe(nodes, edges)
    # 1 到 6 个主体：图全部穷举过，索引里存的是结果，直接取布局。
    if f["n"] <= 6:
        from small_lookup import lookup as small
        r = small(nodes, edges)
        if r:
            g, lay, rec = r
            return dict(ok=True, **f, src="完整图", grid=list(g), layout=lay,
                        node=[140, 48], row=200, col=340,
                        grids=[list(g)], restarts=12, coarse=1, fine=1,
                        portrait_bonus=2, tall=False,
                        known=dict(cross=rec["cross"], bends=rec["bends"]))
    # 7 到 9 个主体先查度序列特征组，它比结构分档精确得多：
    # 结构分档只认「星形、双核、链、混合」四类，度序列认的是
    # 最大度、边数、度数跨度，同一档内的案件走线难度才真正接近。
    if 7 <= f["n"] <= 9:
        rec = index_all().get("by_degseq", {}).get(degseq_key(nodes, edges))
        if rec and f["maxdeg"] <= 12:
            out = dict(ok=True, **f)
            out.update(rec)
            out["src"] = "度序列"
            return out
    idx = index()
    key = f"{f['kind']}:{f['n']}"
    rec = idx.get(key)
    if rec is None:
        # 结构没认准或规模超表，按同规模的混合兜底
        rec = idx.get(f"混合:{f['n']}")
    if rec is None:
        return dict(ok=False, **f,
                    reason=f"{f['n']} 个主体超出已验证范围（5 到 16），"
                           f"建议按争点拆成两张图。")
    if not rec["ok"]:
        return dict(ok=False, **f, reason=rec["reason"])
    # 表给的是该结构的典型核度数，实际案件可能更高，以实际为准
    if f["maxdeg"] > 12:
        who = None
        return dict(ok=False, **f,
                    reason=f"关系最多的那个主体有 {f['maxdeg']} 条，"
                           f"超过单个主体能挂的上限 12。需要拆图。")
    out = dict(ok=True, **f)
    out.update({k: v for k, v in rec.items() if k not in ("ok", "core")})
    if f["maxdeg"] > 10 and not out["tall"]:
        out["tall"] = True           # 实际度数比该结构的典型值高，改用高节点
        out["node"], out["row"] = [140, 78], 260
    return out


def run(nodes, edges, verbose=False, svg_path=None, render=None, force_tall=False):
    """按查到的决定跑一遍。

    给了 svg_path 就在出图后自动验一遍判据——索引表只保证交叉与拐弯，
    不保证不穿主体、不贴边、箭头到位，那些必须读产物坐标才知道。
    返回 (指标, 网格, 分配, pos, rects, 端口, 骨架, 决定)，
    验过的话决定里会带上 guard 字段。
    """
    d = plan(nodes, edges)
    if not d["ok"]:
        raise ValueError(d["reason"])
    # 模块里的字排不下两行时改用高节点（与最大度超过 10 时同一套几何），
    # 照录原文靠加高模块解决，不靠删字。
    if force_tall and not d["tall"]:
        d["tall"] = True
        d["node"], d["row"] = [140, 78], 260
    root = _os.path.join(_HERE, "tall") if d["tall"] else _HERE
    sys.path.insert(0, root)
    import importlib, layout_heuristic, optimize
    importlib.reload(layout_heuristic)
    importlib.reload(optimize)
    NH, ROW, COL = d["node"][1], d["row"], d["col"]
    # 1 到 6 直接用存好的布局，不跑搜索
    if d.get("layout"):
        NH, ROW, COL = d["node"][1], d["row"], d["col"]
        a = d["layout"]
        pos = {k: (v[1] * COL + 70, v[0] * ROW + NH / 2) for k, v in a.items()}
        rects = {k: (v[1] * COL, v[0] * ROW, d["node"][0], NH)
                 for k, v in a.items()}
        pp, sk, sc = optimize.refine(pos, rects, edges, rounds=d["fine"])
        if render is not None:
            try:
                from guard_lib import report
                ok, msg = report(render(a, pos, rects, sk, d))
                d["guard"] = dict(ok=ok, msg=msg)
            except Exception:
                pass
        if verbose:
            print(f"  查表：完整图索引　{d['grid'][0]}x{d['grid'][1]}　"
                  f"交叉 {sc[0]} 拐弯 {sc[1]}")
        return (sc, tuple(d["grid"]), a, pos, rects, pp, sk, d)

    t0 = time.time()
    # 候选补上转置形状：表里存的往往只有一个，判据不过时无从可换。
    # 转置极廉价，而且常常正好是过判据的那个——12 主体混合的 6x2 判据未过，
    # 它的转置 2x6 就通过了。
    cand_grids = []
    # 索引给的网格之外，补一个接近正方的网格。实测 9 主体的示例案，
    # 索引只给 5x2，交叉 7 拐弯 24；同一案件放进 3x3 是交叉 1 拐弯 3。
    # 长条网格让远端主体之间只能绕行，正方网格至少要进候选比一比。
    import math as _m
    _c = _m.ceil(_m.sqrt(d["n"]))
    _r = _m.ceil(d["n"] / _c)
    extra = [(_r, _c)] if _r != _c else [(_c, _c)]
    # 只在索引给的网格都是长条（长边至少是短边的两倍）时才补。
    # 索引已经给了接近正方的网格（如 3x4），再补 3x3 实测只多花时间、不出更好的结果。
    if all(max(g) >= 2 * min(g) for g in d["grids"]):
        pass
    else:
        extra = []
    for g in [tuple(x) for x in d["grids"]] + extra:
        for x in (g, (g[1], g[0])):
            if x not in cand_grids and x[0] * x[1] >= d["n"]:
                cand_grids.append(x)
    rough = []
    for g in cand_grids:
        try:
            c, a = layout_heuristic.solve_large(nodes, edges, g,
                                                restarts=d["restarts"], sweeps=30)
            pos = {k: (v[1] * COL + 70, v[0] * ROW + NH / 2) for k, v in a.items()}
            rects = {k: (v[1] * COL, v[0] * ROW, d["node"][0], NH)
                     for k, v in a.items()}
            _, _, sc = optimize.refine(pos, rects, edges, rounds=d["coarse"])
            rough.append((sc, g, a, pos, rects))
        except Exception:
            continue
    if not rough:
        raise ValueError("候选网格都走不通，建议拆图")
    bonus = d["portrait_bonus"]
    rough.sort(key=lambda x: (x[0][0] - (bonus if x[1][0] >= x[1][1] else 0),
                              x[0][1], x[0][2]))
    # 精修并验判据：指标好不等于判据过。
    #
    # 实测 12 主体混合的四个候选网格，三个都有线贴主体太近（G9 未过），
    # 而按交叉与拐弯排，未过的那个反而排在前面。所以选择标准是
    # **先过判据，再比指标**——判据读的是产物坐标，那才是唯一可信的依据。
    #
    # 判据放在运行时而非建索引时，是因为重建索引的代价太大；
    # 代价是每个候选多一次渲染与回读，约一两秒。
    best, fallback = None, None
    # 判据不过时要有得换，所以多带几个候选进精修。
    # 14 主体与 16 主体的情形显示：只看前三个仍可能全都不过。
    for sc0, g, a, pos, rects in rough[:5]:
        try:
            pp, sk, sc = optimize.refine(pos, rects, edges, rounds=d["fine"])
        except Exception:
            continue
        cand = (sc, g, a, pos, rects, pp, sk)
        if fallback is None or sc < fallback[0]:
            fallback = cand
        if render is None:
            if best is None or sc < best[0]:
                best = cand
            continue
        try:
            from guard_lib import report
            tmp = render(a, pos, rects, sk, d)
            ok, msg = report(tmp)
        except Exception as e:
            # 判据跑不起来不能算通过。先前这里记为通过，
            # Windows 上判据因编码读不回结果时，每个候选都被当成合格。
            ok, msg = False, f"判据未能运行：{type(e).__name__}"
        if ok and (best is None or sc < best[0]):
            best = cand
            d["guard"] = dict(ok=True, msg=msg, grid=list(g))
    if best is None and render is not None:
        # 候选全都没过判据时，再试一圈相邻网格（多一行或多一列，含转置）。
        # 7 主体只有 3x3 一个候选的案件，G9 差一段线贴边，
        # 没有第二个候选可换，只能交一张判据未过的图。
        tried = set(cand_grids)
        more = []
        for g0 in list(cand_grids)[:2]:
            for x in ((g0[0], g0[1] + 1), (g0[0] + 1, g0[1])):
                for y in (x, (x[1], x[0])):
                    if y not in tried and y not in more:
                        more.append(y)
        for g in more[:4]:
            try:
                c, a = layout_heuristic.solve_large(nodes, edges, g,
                                                    restarts=d["restarts"], sweeps=30)
                pos = {k: (v[1] * COL + 70, v[0] * ROW + NH / 2) for k, v in a.items()}
                rects = {k: (v[1] * COL, v[0] * ROW, d["node"][0], NH)
                         for k, v in a.items()}
                pp, sk, sc = optimize.refine(pos, rects, edges, rounds=d["fine"])
                from guard_lib import report
                ok, msg = report(render(a, pos, rects, sk, d))
            except Exception:
                continue
            cand = (sc, g, a, pos, rects, pp, sk)
            if fallback is None or sc < fallback[0]:
                fallback = cand
            if ok and (best is None or sc < best[0]):
                best = cand
                d["guard"] = dict(ok=True, msg=msg, grid=list(g))
                break
    if best is None:
        # 候选全都没过判据，取指标最好的那个并如实标注
        best = fallback
        if best is not None and render is not None:
            d["guard"] = dict(ok=False, msg="候选网格都有判据未过，已取指标最好的一个")
    if best is None:
        raise ValueError("精修阶段全部失败")
    if verbose:
        print(f"  查表：{d['kind']} {d['n']} 主体　"
              f"{'高' if d['tall'] else '矮'}节点　候选 {d['grids']}")
        print(f"  结果：{best[1][0]}x{best[1][1]}　交叉 {best[0][0]}　"
              f"拐弯 {best[0][1]}　{time.time()-t0:.0f}s")
        if "guard" in d:
            print(f"  判据：{'通过' if d['guard']['ok'] else '未过'}　{d['guard']['msg']}")
    return best + (d,)
