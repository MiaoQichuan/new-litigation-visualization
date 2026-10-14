# -*- coding: utf-8 -*-
"""数据集 + 视图：模型只抄逐件记录，分组、计数、求和、排序由脚本做（0.9.8，学自 Perspective）。

为什么要有这一层
----------------
原来的写法是模型先把 286 份判决数成「民间借贷 97、买卖合同 64……」，再把这几个数写进 data。
守卫能核「标题里的数是不是由这些数推出来的」，却核不了「这些数本身是不是数对了」——
数错一份，图照样过守卫。Perspective 的做法是把**原始数据**与**怎么看**分开：数据只存一份，
「按什么分组、怎么汇总、筛哪些、怎么排」写成一份视图配置，由引擎来算。

于是模型的活从「数数」变成「抄表」：一件一行，照录材料。数数交给脚本，脚本数错了测得出来。
每一个柱、每一格、每一股流带都记下来自哪几行（逐格溯源），交付时写进 <名>.trace.json，
律师可以从图上任何一个数追回到具体是哪几份判决。

写法（顶层两个字段，与 data 二选一地给数据；data 里仍可写 from_label、threshold 这类说明）::

    "dataset": {"rows": [{"案号": "(2025)…1号", "案由": "民间借贷", "年份": 2025}, ...],
                "ref": "案号"},                       # ref 可选：溯源时用哪一列指认一行
    "view": {"group_by": "案由",                      # 竖柱 / 横条 / 百点方阵 / 玫瑰 / 逐件分布
             "measure": "count",                      # 或 {"sum": "判赔金额"}（竖柱、横条）
             "filter": {"年份": 2025, "层级": ["基层", "中级"], "标的": {"min": 0, "max": 100}},
             "sort": "desc",                          # desc / asc / label / ["民间借贷", "买卖合同", …]
             "top": 7, "other": "其他",               # 只留前 7，其余并成「其他」
             "missing": "drop"}                       # 缺这一列的行：drop（不计入，交付清单点名）/ bucket（并成「未写明」）

    逐件分布：  "view": {"group_by": "程序", "values": "审理天数"}
    桑基：      "view": {"stages": ["一审结果", "是否上诉", "二审结果"]}
    汇入图：    "view": {"from": "付款账户", "to": "收款账户", "measure": {"sum": "金额"}}

id 由脚本起：单一维度的图，id 就是类目名本身（emphasis 直接写「民间借贷」）；
桑基与汇入图两侧可能同名，id 写成「字段=值」（emphasis 写「二审结果=改判」）。

不做的：哑铃与逐级加减本来就是一行一项，直接写 data；百点方阵与玫瑰只按件数画（金额构成请用横条）。
"""
import math
import re

from spec import SpecError        # spec 在校验时才 import 本模块，这里不会循环

GROUPED = ("bar", "hbar", "waffle", "rose")
VIEW_KEYS = {"group_by", "measure", "filter", "sort", "top", "other", "missing", "values", "stages", "from", "to"}
COMPUTED = {"items", "groups", "nodes", "links", "sources", "targets", "measure"}
MISSING_LABEL = "未写明"


def _blank(v):
    return v is None or (isinstance(v, str) and not v.strip())


def _num(v):
    return (isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v))


def _key(v):
    """类目名：数字年份 2025 与文字「2025」当作同一类，统一成文字。"""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def _natural(s):
    return [(0, int(t), "") if t.isdigit() else (1, 0, t) for t in re.findall(r"\d+|\D+", s)]


def _field(view, name, where="view"):
    v = view.get(name)
    if not isinstance(v, str) or not v.strip():
        raise SpecError(f"{where}.{name} 要写一个列名（dataset.rows 里的字段名），收到 {v!r:.40}")
    return v


def _rows(m):
    ds = m.get("dataset")
    if isinstance(ds, list):
        ds = {"rows": ds}
    if not isinstance(ds, dict) or not isinstance(ds.get("rows"), list) or not ds["rows"]:
        raise SpecError("dataset 要写成 {\"rows\": [一件一行的对象, …]}，且至少一行")
    extra = set(ds) - {"rows", "ref"}
    if extra:
        raise SpecError(f"dataset 里不认识的字段：{'、'.join(sorted(extra))}（只有 rows 与 ref）")
    for k, r in enumerate(ds["rows"]):
        if not isinstance(r, dict):
            raise SpecError(f"dataset.rows[{k}] 要写成一个对象（一件一行，列名: 值），收到 {r!r:.40}")
    ref = ds.get("ref")
    if ref is not None and (not isinstance(ref, str) or not any(ref in r for r in ds["rows"])):
        raise SpecError(f"dataset.ref 写的是 {ref!r}，没有一行有这一列")
    return ds["rows"], ref


def _filter(rows, flt):
    """返回 (留下的行号, 被过滤掉的行数)。"""
    if flt is None:
        return list(range(len(rows))), 0
    if not isinstance(flt, dict) or not flt:
        raise SpecError("view.filter 要写成 {列名: 值 | [值, …] | {\"min\": 下限, \"max\": 上限}}")
    for col, cond in flt.items():
        if isinstance(cond, dict):
            if set(cond) - {"min", "max"} or not cond or not all(_num(x) for x in cond.values()):
                raise SpecError(f"view.filter.{col} 的区间要写成 {{\"min\": 数字, \"max\": 数字}}（可只写一头）")
    keep = []
    for i, r in enumerate(rows):
        ok = True
        for col, cond in flt.items():
            v = r.get(col)
            if isinstance(cond, dict):
                ok = _num(v) and cond.get("min", -math.inf) <= v <= cond.get("max", math.inf)
            elif isinstance(cond, list):
                ok = not _blank(v) and _key(v) in {_key(c) for c in cond}
            else:
                ok = not _blank(v) and _key(v) == _key(cond)
            if not ok:
                break
        if ok:
            keep.append(i)
    if not keep:
        raise SpecError("view.filter 筛完一行都不剩：请核对列名与取值（文字要与材料一字不差）")
    return keep, len(rows) - len(keep)


def _measure(view, chart):
    ms = view.get("measure", "count")
    if ms == "count":
        return None
    if isinstance(ms, dict) and set(ms) == {"sum"} and isinstance(ms["sum"], str):
        if chart in ("waffle", "rose", "strip", "sankey"):
            raise SpecError(f"view.measure 求和只用于竖柱、横条、汇入图；{chart} 按件数画"
                            f"（金额的构成请改用横条）")
        return ms["sum"]
    raise SpecError("view.measure 写 \"count\"（数件数），或 {\"sum\": \"列名\"}（把这一列加起来）")


def _sum(rows, ix, col, what):
    """把这几行的 col 加起来。

    不用内置 sum()：Python 3.12 起它对浮点做补偿求和，3.11 与 3.12+ 会差在末位，
    同一份说明在两个版本上出的图就不再逐字节相同（0.9.6 修过同一类问题）。
    math.fsum 是精确求和、各版本一致；再四舍五入到 9 位小数，去掉 0.30000000000000004 这种尾巴。"""
    vals = [_value(rows, i, col) for i in ix]
    if all(isinstance(v, int) for v in vals):
        tot = sum(vals)
    else:
        tot = round(math.fsum(vals), 9)
        if tot.is_integer():
            tot = int(tot)
    if tot < 0:
        raise SpecError(f"「{what}」这一类把「{col}」加起来是 {tot}，是负数：本模块只画非负量。"
                        f"有正有负的数据请等后续的正负条图（逐级加减可以画加减，但它不用 dataset）")
    return tot


def _value(rows, i, col):
    v = rows[i].get(col)
    if not _num(v):
        raise SpecError(f"dataset.rows[{i}].{col} 要是数字（求和、分布都按这一列算），收到 {v!r:.40}")
    return v


def _group(rows, idx, col, missing, report):
    """→ {类目名: [行号…]}，按出现先后。缺这一列的行按 missing 处理。"""
    out, gone = {}, []
    for i in idx:
        v = rows[i].get(col)
        if _blank(v):
            if missing == "bucket":
                out.setdefault(MISSING_LABEL, []).append(i)
            else:
                gone.append(i)
            continue
        if isinstance(v, (list, dict)):
            raise SpecError(f"dataset.rows[{i}].{col} 要是一个值（文字或数字），收到 {v!r:.40}")
        out.setdefault(_key(v), []).append(i)
    if gone:
        report.append((col, gone))
    if not out:
        raise SpecError(f"没有一行写了「{col}」：请核对 view 里的列名与 dataset 是否一致")
    return out


def _order(groups, val, sort, chart):
    names = list(groups)
    if sort is None:
        sort = "label" if chart == "bar" else "desc"
    if isinstance(sort, list):
        miss = [s for s in names if s not in [_key(x) for x in sort]]
        if miss:
            raise SpecError(f"view.sort 列了顺序，但漏了这些类目：{'、'.join(miss[:5])}")
        pos = {_key(x): k for k, x in enumerate(sort)}
        return sorted(names, key=lambda s: pos[s])
    # 并列时按类目名排（不按在 dataset 里出现的先后）：同一批记录换个顺序抄，图一样
    if sort == "desc":
        return sorted(names, key=lambda s: (-val[s], _natural(s)))
    if sort == "asc":
        return sorted(names, key=lambda s: (val[s], _natural(s)))
    if sort == "label":
        return sorted(names, key=_natural)
    if sort == "given":
        return names                                     # 按在 dataset 里第一次出现的先后
    raise SpecError("view.sort 写 desc / asc / label / given，或列出全部类目的顺序")


def _shares(counts, total):
    """件数 → 百分比，保留一位，合计正好 100（最大余数法）。"""
    raw = [c * 1000 / total for c in counts]
    base = [int(math.floor(x)) for x in raw]
    for i in sorted(range(len(raw)), key=lambda i: (-(raw[i] - base[i]), i))[:1000 - sum(base)]:
        base[i] += 1
    return [b / 10 for b in base]


def expand(m):
    """有 dataset / view 就把它们算成 data（原地改 m），返回溯源；没有就什么都不做、返回 None。"""
    has_ds, has_v = "dataset" in m, "view" in m
    if not has_ds and not has_v:
        return None
    if not (has_ds and has_v):
        raise SpecError("dataset 与 view 要一起给：dataset 是逐件记录，view 写怎么分组、怎么汇总")
    chart = m.get("chart")
    if chart in ("dumbbell", "waterfall"):
        raise SpecError("哑铃与逐级加减本来就是一行一项：直接写 data，不用 dataset / view")
    view = m["view"]
    if not isinstance(view, dict):
        raise SpecError("view 要是一个对象，例如 {\"group_by\": \"案由\"}")
    extra = set(view) - VIEW_KEYS
    if extra:
        raise SpecError(f"view 里不认识的字段：{'、'.join(sorted(extra))}（拼错了？）")
    rows, ref = _rows(m)
    data = m.get("data")
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise SpecError("data 要是一个对象")
    given = {k: data[k] for k in COMPUTED if k in data}
    missing = view.get("missing", "drop")
    if missing not in ("drop", "bucket"):
        raise SpecError("view.missing 写 drop（缺这一列的行不计入）或 bucket（并成「未写明」一类）")
    idx, filtered = _filter(rows, view.get("filter"))
    dropped = []
    cells = {}
    out = {}
    added_order = False
    if chart in GROUPED:
        col = _field(view, "group_by")
        sumcol = _measure(view, chart)
        g = _group(rows, idx, col, missing, dropped)
        val = {s: (_sum(rows, ix, sumcol, s) if sumcol else len(ix)) for s, ix in g.items()}
        names = _order(g, val, view.get("sort"), chart)
        top = view.get("top")
        if top is not None:
            if not isinstance(top, int) or isinstance(top, bool) or top < 2:
                raise SpecError("view.top 要是 ≥ 2 的整数（留前几类）")
            if len(names) > top:
                other = view.get("other", "其他")
                if not isinstance(other, str) or not other.strip() or other in g:
                    raise SpecError("view.other 要是一个与现有类目不重名的名字，例如「其他」")
                byv = sorted(names, key=lambda s: (-val[s], _natural(s)))
                keep = set(byv[:top - 1])
                rest = [s for s in names if s not in keep]
                for who, x in [("emphasis", m.get("emphasis"))] + [(f"annotations[{k}]", a.get("target"))
                                                                     for k, a in enumerate(m.get("annotations") or [])
                                                                     if isinstance(a, dict)]:
                    if isinstance(x, (str, int)) and not isinstance(x, bool) and _key(x) in rest:
                        raise SpecError(f"{who} 指向「{_key(x)}」，它按 view.top = {top} 并进了「{other}」，图上没有单独这一项："
                                        f"把 top 调大，或换一个要标的类目")
                g[other] = sorted(i for s in rest for i in g[s])
                val[other] = _sum([{"v": val[s]} for s in rest], range(len(rest)), "v", other) if sumcol \
                    else sum(val[s] for s in rest)
                names = [s for s in names if s in keep] + [other]
                if chart == "hbar" and "order" not in m:
                    m["order"] = "given"                 # 横条默认按数值重排；并出来的「其他」要压在最后
                    added_order = True
        counts = [val[s] for s in names]
        items = [{"id": s, "label": s, "value": v} for s, v in zip(names, counts)]
        if chart == "waffle":
            tot = sum(counts)
            if tot <= 100:
                out["measure"] = "count"
            else:
                out["measure"] = "percent"
                for it, p in zip(items, _shares(counts, tot)):
                    it["value"] = p
        out["items"] = items
        cells = {s: g[s] for s in names}
    elif chart == "strip":
        vcol = _field(view, "values")
        _measure(view, chart)
        col = view.get("group_by")
        if col is None:
            g, names = {"全部": list(idx)}, ["全部"]
        else:
            g = _group(rows, idx, _field(view, "group_by"), missing, dropped)
            names = _order(g, {k: len(v) for k, v in g.items()}, view.get("sort", "given"), chart)
        groups, gone = [], []
        for s_ in names:
            ix = []
            for i in g[s_]:
                if _blank(rows[i].get(vcol)):
                    gone.append(i)
                    continue
                _value(rows, i, vcol)
                ix.append(i)
            if ix:
                ix.sort(key=lambda i: (rows[i][vcol], i))      # 按值排：同一批记录换个顺序抄，点位一样
                groups.append({"id": s_, "label": s_, "values": [rows[i][vcol] for i in ix]})
                cells[s_] = ix
        if gone:
            dropped.append((vcol, sorted(gone)))
        if not groups:
            raise SpecError(f"没有一行写了「{vcol}」")
        out["groups"] = groups
    elif chart == "sankey":
        st = view.get("stages")
        if not isinstance(st, list) or not 2 <= len(st) <= 4 or not all(isinstance(x, str) and x for x in st):
            raise SpecError("view.stages 要列 2 到 4 个列名，按先后：例如 [\"一审结果\", \"是否上诉\", \"二审结果\"]")
        _measure(view, chart)
        nodes, links = {}, {}
        for i in idx:
            path = []
            for k, col in enumerate(st):
                v = rows[i].get(col)
                if _blank(v):
                    break                                  # 走到这一段就停了（例如服判息诉，没有二审结果）
                if isinstance(v, (list, dict)):
                    raise SpecError(f"dataset.rows[{i}].{col} 要是一个值，收到 {v!r:.40}")
                path.append((k, col, _key(v)))
            if not path:
                dropped.append((st[0], [i]))
                continue
            for k, col, v in path:
                nid = f"{col}={v}"
                nodes.setdefault(nid, {"id": nid, "label": v, "stage": k})
                cells.setdefault(nid, []).append(i)
            for a, b in zip(path, path[1:]):
                key = (f"{a[1]}={a[2]}", f"{b[1]}={b[2]}")
                links.setdefault(key, []).append(i)
        dropped = _merge_drops(dropped)
        for nid, n in nodes.items():                       # 同一个节点：要么都往下走，要么都停在这里
            if n["stage"] == len(st) - 1:
                continue
            go = {i for (a, _), ix in links.items() if a == nid for i in ix}
            stop = [i for i in cells[nid] if i not in go]
            if go and stop:
                nxt = st[n["stage"] + 1]
                raise SpecError(f"「{nid}」有 {len(go)} 行往下走、{len(stop)} 行没写「{nxt}」"
                                f"（行号 {'、'.join(map(str, stop[:8]))}，从 0 数）：补上，或用 view.filter 排除这几行")
        order = sorted(nodes.values(), key=lambda n: (n["stage"], -len(cells[n["id"]]), n["label"]))
        out["nodes"] = order
        out["links"] = [{"from": a, "to": b, "value": len(ix)} for (a, b), ix in
                        sorted(links.items(), key=lambda t: (nodes[t[0][0]]["stage"], -len(t[1]), t[0]))]
        for (a, b), ix in links.items():
            cells[f"{a} → {b}"] = ix
    elif chart == "ribbon":
        fc, tc = _field(view, "from"), _field(view, "to")
        sumcol = _measure(view, chart)
        src, tgt, links = {}, {}, {}
        for i in idx:
            a, b = rows[i].get(fc), rows[i].get(tc)
            if _blank(a) or _blank(b):
                dropped.append((fc if _blank(a) else tc, [i]))
                continue
            a, b = f"{fc}={_key(a)}", f"{tc}={_key(b)}"
            src.setdefault(a, []).append(i)
            tgt.setdefault(b, []).append(i)
            links.setdefault((a, b), []).append(i)
        dropped = _merge_drops(dropped)
        if not links:
            raise SpecError(f"没有一行同时写了「{fc}」与「{tc}」")
        w = {k: (_sum(rows, ix, sumcol, f"{k[0]} → {k[1]}") if sumcol else len(ix)) for k, ix in links.items()}
        tot_s = {s: math.fsum(v for (a, _), v in w.items() if a == s) for s in src}      # 只用来排序
        tot_t = {t: math.fsum(v for (_, b), v in w.items() if b == t) for t in tgt}
        out["sources"] = [{"id": s, "label": s.split("=", 1)[1]} for s in sorted(src, key=lambda s: (-tot_s[s], s))]
        out["targets"] = [{"id": t, "label": t.split("=", 1)[1]} for t in sorted(tgt, key=lambda t: (-tot_t[t], t))]
        out["links"] = [{"from": a, "to": b, "value": v} for (a, b), v in sorted(w.items(), key=lambda t: (-t[1], t[0]))]
        cells.update(src)
        cells.update(tgt)
        for (a, b), ix in links.items():
            cells[f"{a} → {b}"] = ix
    else:
        raise SpecError(f"dataset / view 不支持 chart={chart!r}")
    if given:
        for k, v in given.items():
            if out.get(k) != v:
                raise SpecError(f"data.{k} 与 dataset 按 view 算出来的不一致：给了 dataset 就不要手写 data.{k}，"
                                f"删掉它交给脚本算（或者去掉 dataset / view，自己写 data）")
    data = dict(data)
    data.update(out)
    m["data"] = data
    used = sorted({i for ix in cells.values() for i in ix})
    if chart in GROUPED or chart == "strip":
        kept = sum(len(ix) for ix in cells.values())
    else:
        kept = len({i for k, ix in cells.items() if " → " not in k for i in ix})
    added_n = "n" not in m
    if added_n:
        m["n"] = kept
    elif m["n"] != kept and isinstance(m["n"], int) and not isinstance(m["n"], bool):
        raise SpecError(f"n 写的是 {m['n']}，按 dataset 算是 {kept}（{len(rows)} 行，过滤掉 {filtered} 行，"
                        f"缺字段不计 {sum(len(ix) for _, ix in dropped)} 行）。两者必须一致——可以不写 n，交给脚本算")
    trace = {"rows": len(rows), "filtered": filtered, "kept": kept, "used_rows": len(used),
             "dropped": [{"column": c, "rows": ix} for c, ix in dropped],
             "ref": ref, "cells": {}}
    for k, ix in cells.items():
        trace["cells"][k] = {"rows": ix, **({"refs": [rows[i].get(ref) for i in ix]} if ref else {})}
    # 脚本替用户补上的字段：交给 V7 的模块清单不带这些，换图种、换版位时一律按 dataset 重算，
    # 不让「为横条算的数」挡住「换成竖柱」（第二轮实跑发现）
    trace["_added"] = {"data": sorted(k for k in out if k not in given), "order": added_order, "n": added_n}
    return trace


def _merge_drops(dropped):
    by = {}
    for c, ix in dropped:
        by.setdefault(c, []).extend(ix)
    return [(c, sorted(set(ix))) for c, ix in by.items()]


def warnings(trace):
    """交付清单里要人看一眼的：缺字段没计入的行。"""
    out = []
    for d in trace["dropped"]:
        ix = d["rows"]
        show = "、".join(str(i) for i in ix[:8]) + ("……" if len(ix) > 8 else "")
        out.append(f"dataset 有 {len(ix)} 行没写「{d['column']}」，没有计入（行号 {show}，从 0 数）。"
                   f"要算进去就补上，或在 view 里写 \"missing\": \"bucket\" 并成「{MISSING_LABEL}」")
    return out
