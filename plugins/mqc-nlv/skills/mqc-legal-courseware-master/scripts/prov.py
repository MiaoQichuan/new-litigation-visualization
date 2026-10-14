# -*- coding: utf-8 -*-
"""图里每个元素出自哪里：编辑器里鼠标停在元素上就看得到（学自案图：悬停看摘要、出处跟着元素走）。

只读别的模块已经写好的出处，不改别的模块，也不猜：
  V2 时间轴大师   出图时在图旁边写了 <名>-trace.json（溯源索引：事项编号、事项、材料、第几句、原文摘录）。
                  把它和图一起放进 assets/，编号与图里的 data-id 一一对上。
  V3 法律关系图大师 出图时同样写 <名>-trace.json（每个主体、每条关系的出处，照录 relations.json 的 source），
                  编号与图里的 data-ref 对上（主体 id；关系「起点→终点」）。
  V6 法律图表大师  图表说明用了 dataset + view（逐件记录）时，V6 自己算出每一项来自哪几条记录、编号是什么。
其余的图（V1、V3、V4、V5、没用逐件记录的 V6）没有逐项出处：不显示，不编。

返回 {元素键: {"head": 事项或类目, "src": 出自哪里, "quote": 原文摘录（V2）, "refs": 记录编号（V6）}}，元素键与磁吸点的键相同（id:<data-id>）。
"""
import json
import os

import paths

MAX_LIST = 12            # 一项来自很多条记录时，只列前几条编号


def is_sidecar(name):
    """这个素材文件是不是出处记录（不是图表说明）：选图里不列它。"""
    return name.endswith("-trace.json") or name.endswith(".trace.json")


def for_figure(mod, base_dir, anchors=None):
    """图旁边的 <名>-trace.json → {元素键: 出处}。元素按 data-id（V2 的事项编号）或 data-ref（V3 的主体、关系）对上号。"""
    f = str(mod.get("file") or "")
    if not f.lower().endswith(".svg"):
        return {}
    p = paths.inside(base_dir, f[:-4] + "-trace.json")
    if not p or not os.path.isfile(p):
        return {}
    try:
        with open(p, encoding="utf-8-sig") as fh:
            payload = json.load(fh)
    except (ValueError, OSError):
        return {}
    rows = payload.get("rows") if isinstance(payload, dict) else None
    out = {}
    for r in rows if isinstance(rows, list) else []:
        if not isinstance(r, dict):
            continue
        no = str(r.get("no") or "").strip()
        if not no:
            continue
        src = " ".join(str(x) for x in (r.get("file"), r.get("locator")) if x)
        quote = str(r.get("quote") or "")
        # 没写出处的也列出来，明说「没写」：讲之前最该补的就是这几条（备注里不写它们）
        out[no] = {"head": str(r.get("head") or ""), "src": src or "（原图的说明里没写出处）", "quote": quote,
                   **({} if src or quote else {"missing": True})}
    by = {}
    for a in anchors or []:                     # 元素键 ← 出处编号：先认 data-id，再认 data-ref
        no = a.get("id") if a.get("id") is not None else a.get("ref")
        if no is not None and str(no) in out:
            by[a["key"]] = out[str(no)]
    return by


def for_chart(crep):
    import make                                           # V6
    t = make.m_trace(crep) if crep else None
    if not t or not isinstance(t.get("cells"), dict):
        return {}
    out = {}
    for cid, c in t["cells"].items():
        rows = list(c.get("rows") or [])
        refs = [str(x) for x in (c.get("refs") or [])]
        more = "…" if len(rows) > MAX_LIST else ""
        # 行号与 V6 自己的说法一致：从 0 数（V6 的提示与 .trace.json 都这样写），免得同一行在两处叫两个号
        src = f"逐件记录 {len(rows)} 条（行号 {'、'.join(str(r) for r in rows[:MAX_LIST])}{more}，从 0 数）"
        ids = ("编号：" + "、".join(refs[:MAX_LIST]) + ("…" if len(refs) > MAX_LIST else "")) if refs else ""
        out["id:" + str(cid)] = {"head": str(cid), "src": src, "refs": ids, "quote": ""}   # 编号不是原文，不放进引文框
    return out


def keep(prov, anchors):
    """只留图里真有的元素（切片、换图后可能少了几个）。"""
    keys = {a["key"] for a in anchors or []}
    return {k: v for k, v in prov.items() if k in keys}
