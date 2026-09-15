# -*- coding: utf-8 -*-
"""两轮交互。问题的措辞由这里打印，模型照抄给使用者，不自己改写。

第〇轮　只有超限才问：模块超过 9 个问留哪几个；关系超过 12 条问留哪几条
第一轮　交付给谁（决定风格），一个问题
第二轮　选奇川风时才问：强调标在哪里，至多两处，节点与关系都算（选入制，不答不标）

    python scripts/ask.py trim relations.json
    python scripts/ask.py trim relations.json --keep 编号 --out relations9.json
    python scripts/ask.py trim relations9.json --keep-edges 编号 --out relations9.json
    python scripts/ask.py round1
    python scripts/ask.py round2 relations.json
    python scripts/ask.py resolve relations.json --style 2 --mark 3,7

relations.json 的格式：
    {"nodes": [{"id": "C1", "name": "建设工程施工合同", "note": "2021.3 签订"}, ...],
     "edges": [["OWNER", "C1", "签订"], ...]}

resolve 输出一份 choice.json 的内容，出图脚本只认它：
    {"style": "奇川风", "emphasis": {"nodes": ["PRICE"], "edges": [9]}, "label": "工程价款；本案诉请 折价补偿"}

为什么要把交互写死：不问风格，模型会把三种风格全出一遍，
额度直接翻三倍；不问重点，模型会自己挑一个标红，违反红色选入制。
"""
import sys, json, argparse

STYLES = [
    ("法官", "开庭、提交法院、打印", "白描"),
    ("当事人与客户", "当面讲、微信发", "奇川风"),
    ("同行、讲课、公众号", "线上展示", "歸藏风"),
]
DEFAULT_STYLE = "奇川风"
MAX_MARK = 2


MAX_MODULES = 9
# 关系上限 12：9 个模块下实测，12 条以内布局 2 到 7 秒、交叉至多 1 处；
# 13 条起耗时翻到 12 到 36 秒，交叉升到 3 到 19 处。
MAX_EDGES = 12
LITIGANT = ("原告", "被告", "上诉人", "被上诉人", "第三人", "申请人", "被申请人",
            "再审申请人", "申请执行人", "被执行人", "反诉")


def _edge_ends(e):
    return (e["from"], e["to"]) if isinstance(e, dict) else (e[0], e[1])


def suggest_keep(nodes, edges, limit=MAX_MODULES):
    """建议保留的模块：先保当事人，再按关系多少从相连的里面补。

    只从已保留模块的邻居里补，保证留下来的图是连通的，
    不会出现一个孤零零、跟谁都不连的模块。
    """
    deg = {n["id"]: 0 for n in nodes}
    adj = {n["id"]: set() for n in nodes}
    for e in edges:
        a, b = _edge_ends(e)
        if a in deg and b in deg:
            deg[a] += 1; deg[b] += 1
            adj[a].add(b); adj[b].add(a)
    order = {n["id"]: i for i, n in enumerate(nodes)}
    party = [n["id"] for n in nodes if any(w in (n.get("note") or "") for w in LITIGANT)]
    party.sort(key=lambda k: (-deg[k], order[k]))
    keep = party[:limit]
    if not keep:
        keep = [max(deg, key=lambda k: (deg[k], -order[k]))]
    while len(keep) < limit:
        near = {m for k in keep for m in adj[k]} - set(keep)
        if not near:
            rest = [k for k in deg if k not in keep]
            if not rest:
                break
            near = set(rest)
        keep.append(max(near, key=lambda k: (sum(1 for m in adj[k] if m in keep), deg[k], -order[k])))
    return [k for k in sorted(keep, key=lambda k: order[k])]


def _as_dict(e):
    if isinstance(e, dict):
        return dict(e)
    return dict(zip(("from", "to", "label", "line"), e))


def merge_parallel(edges):
    """同一方向、同一对模块之间的多条关系合成一条，关系名用「；」连起来。

    只合并，不删字：每个关系名原样保留。方向相反的不合并，箭头含义不同。
    合并后标签会变长，但少一条线，布局难度按线数算。
    """
    out, seen = [], {}
    for e in edges:
        d = _as_dict(e)
        k = (d["from"], d["to"])
        if k in seen:
            base = out[seen[k]]
            base["label"] = f'{base["label"]}；{d["label"]}'
            if d.get("source") and d.get("source") != base.get("source"):
                base["source"] = f'{base.get("source", "")}；{d["source"]}'.strip("；")
            base.setdefault("merged", 1)
            base["merged"] += 1
        else:
            seen[k] = len(out)
            out.append(d)
    return out


def suggest_edges(nodes, edges, limit=MAX_EDGES):
    """建议保留的关系：先保连通（每个模块至少挂一条），再按文件里的先后补满。

    relations.json 里关系按重要性从高到低排（写法指南里要求的），
    所以「先后」就是模型对重要性的判断；使用者可以改。
    连通优先时，挂在当事人身上的关系先选。
    """
    party = {n["id"] for n in nodes if any(w in (n.get("note") or "") for w in LITIGANT)}
    parent = {n["id"]: n["id"] for n in nodes}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    order = sorted(range(len(edges)), key=lambda i: (
        0 if (_as_dict(edges[i])["from"] in party or _as_dict(edges[i])["to"] in party) else 1, i))
    keep = []
    for i in order:
        a, b = _edge_ends(_as_dict(edges[i]))
        ra, rb = find(a), find(b)
        if ra != rb and len(keep) < limit:
            parent[ra] = rb
            keep.append(i)
    for i in range(len(edges)):
        if len(keep) >= limit:
            break
        if i not in keep:
            keep.append(i)
    return sorted(keep)


def trim_edges_question(nodes, edges):
    keep = set(suggest_edges(nodes, edges))
    name = {n["id"]: n["name"] for n in nodes}
    lines = [f"模块 {len(nodes)} 个，关系 {len(edges)} 条。超过 {MAX_EDGES} 条，出图会慢很多、线也更乱。",
             f"留哪几条？报编号，至多 {MAX_EDGES} 条，用逗号隔开。", ""]
    for i, e in enumerate(edges, 1):
        d = _as_dict(e)
        mark = "★" if i - 1 in keep else "　"
        lines.append(f"{i}　{mark} {name.get(d['from'], d['from'])} → {name.get(d['to'], d['to'])}：{d['label']}")
    lines += ["", "★ 是建议保留的（每个模块至少留一条，其余按整理时的先后）。不回答就按 ★ 出；",
              "回答「全部」则不删，但会慢很多。",
              "没留下的关系不会丢，会列在出处索引的「未入图」一节。"]
    return "\n".join(lines)


def trim_edges_resolve(rel, keep=None):
    nodes = rel["nodes"]
    edges = rel["edges"]
    if keep is not None and str(keep).strip() == "全部":
        return dict(rel, over12=True)
    if keep is None or str(keep).strip() in ("", "0"):
        idx = suggest_edges(nodes, edges)
    else:
        picks = [p.strip() for p in str(keep).replace("，", ",").split(",") if p.strip()]
        idx = []
        for p in dict.fromkeys(picks):
            if not p.isdigit() or not 1 <= int(p) <= len(edges):
                raise ValueError(f"编号 {p} 不在清单里（1 到 {len(edges)}）")
            idx.append(int(p) - 1)
        if len(idx) > MAX_EDGES:
            raise ValueError(f"至多保留 {MAX_EDGES} 条，收到 {len(idx)} 条")
    kept = [edges[i] for i in sorted(idx)]
    ends = {x for e in kept for x in _edge_ends(_as_dict(e))}
    lonely = [n["name"] for n in nodes if n["id"] not in ends]
    if lonely:
        raise ValueError("这几个模块一条关系都没留下，要么留一条、要么回到上一步删掉模块："
                         + "、".join(lonely))
    out = dict(rel)
    out["edges"] = kept
    dropped = dict(out.get("dropped") or {})
    dropped["edges"] = list(dropped.get("edges") or []) + [edges[i] for i in range(len(edges)) if i not in set(idx)]
    dropped.setdefault("nodes", [])
    out["dropped"] = dropped
    return out


def trim_question(nodes, edges):
    keep = set(suggest_keep(nodes, edges))
    deg = {n["id"]: 0 for n in nodes}
    for e in edges:
        a, b = _edge_ends(e)
        deg[a] = deg.get(a, 0) + 1; deg[b] = deg.get(b, 0) + 1
    lines = [f"材料里整理出 {len(nodes)} 个模块。超过 {MAX_MODULES} 个，出图会慢很多、线也更乱。",
             f"留哪几个？报编号，至多 {MAX_MODULES} 个，用逗号隔开。", ""]
    for i, n in enumerate(nodes, 1):
        mark = "★" if n["id"] in keep else "　"
        note = f"（{n['note']}）" if n.get("note") else ""
        lines.append(f"{i}　{mark} {n['name']}{note}　{deg.get(n['id'], 0)} 条关系")
    lines += ["", "★ 是建议保留的。不回答就按 ★ 出；",
              "回答「全部」则不删，但十几个模块可能要等很久。",
              "没留下的模块和它们的关系不会丢，会列在出处索引的「未入图」一节。"]
    return "\n".join(lines)


def trim_resolve(rel, keep=None):
    nodes = rel["nodes"]
    edges = rel["edges"]
    if keep is None or str(keep).strip() in ("", "0"):
        ids = suggest_keep(nodes, edges)
    elif str(keep).strip() == "全部":
        return dict(rel, over9=True)
    else:
        picks = [p.strip() for p in str(keep).replace("，", ",").split(",") if p.strip()]
        ids = []
        for p in dict.fromkeys(picks):
            if not p.isdigit() or not 1 <= int(p) <= len(nodes):
                raise ValueError(f"编号 {p} 不在清单里（1 到 {len(nodes)}）")
            ids.append(nodes[int(p) - 1]["id"])
        if len(ids) > MAX_MODULES:
            raise ValueError(f"至多保留 {MAX_MODULES} 个，收到 {len(ids)} 个")
        if len(ids) < 2:
            raise ValueError("至少保留 2 个模块")
    keep_set = set(ids)
    kept_edges, dropped_edges = [], []
    for e in edges:
        a, b = _edge_ends(e)
        (kept_edges if a in keep_set and b in keep_set else dropped_edges).append(e)
    if not kept_edges:
        raise ValueError("保留的模块之间一条关系都没有，换几个相连的")
    out = dict(rel)
    out["nodes"] = [n for n in nodes if n["id"] in keep_set]
    out["edges"] = kept_edges
    out["dropped"] = dict(nodes=[n for n in nodes if n["id"] not in keep_set],
                          edges=dropped_edges)
    return out


def round1():
    lines = ["这张法律关系图交付给谁？报个编号就行。", ""]
    for i, (who, use, style) in enumerate(STYLES, 1):
        lines.append(f"{i}　{who}（{use}）→ {style}")
    lines.append(f"{len(STYLES) + 1}　让我定（按{DEFAULT_STYLE}出，接着问重点）")
    lines += ["", f"不回答就按{DEFAULT_STYLE}出。每次只出所选的一种风格。"]
    return "\n".join(lines)


def _load(path):
    """两种写法都认：[from, to, 关系名] 或 {from, to, label}。

    第〇轮写回的文件是后一种。先前这里一律 list(e)，对字典取到的是键名，
    第二轮每条关系都显示成「from → to：label」，使用者无从选起。
    同向重复的关系按与 make.py 相同的规则先合并，两边的编号才对得上。
    """
    d = json.load(open(path, encoding="utf-8"))
    nodes = d["nodes"]
    edges = [[e["from"], e["to"], e.get("label", "")] for e in merge_parallel(d["edges"])]
    return nodes, edges


def _candidates(nodes, edges):
    name = {n["id"]: n["name"] for n in nodes}
    cands = []
    for n in nodes:
        cands.append(("node", n["id"], n["name"] + (f"（{n['note']}）" if n.get("note") else "")))
    for i, e in enumerate(edges):
        label = e[2] if len(e) > 2 and e[2] else "（无标签）"
        cands.append(("edge", i, f"{name.get(e[0], e[0])} → {name.get(e[1], e[1])}：{label}"))
    return cands


def round2(nodes, edges):
    cands = _candidates(nodes, edges)
    k = sum(1 for c in cands if c[0] == "node")
    lines = ["深红标在哪里？至多两处，报编号，用逗号隔开；0 = 不标。", "", "主体与客体"]
    for i, c in enumerate(cands, 1):
        if i == k + 1:
            lines += ["", "关系"]
        lines.append(f"{i}　{c[2]}")
    lines += ["", "不回答就一处红都不标。"]
    return "\n".join(lines)


def resolve(nodes, edges, style=None, mark=None):
    """把使用者的回答变成确定的选择。任何越界都直接报错，不猜。"""
    if style in (None, "", "0"):
        chosen = DEFAULT_STYLE
    elif str(style).isdigit():
        i = int(style)
        if 1 <= i <= len(STYLES):
            chosen = STYLES[i - 1][2]
        elif i == len(STYLES) + 1:
            chosen = DEFAULT_STYLE          # 让我定：没有更多信息时取默认
        else:
            raise ValueError(f"风格编号只能是 1 到 {len(STYLES) + 1}")
    elif style in {s for _, _, s in STYLES}:
        chosen = style
    else:
        raise ValueError(f"风格只能选一种：白描 / 奇川风 / 歸藏风，收到 {style!r}")
    picks = [p.strip() for p in str(mark or "").replace("，", ",").split(",") if p.strip()]
    picks = [p for p in picks if p != "0"]
    if chosen != "奇川风":
        if picks:
            raise ValueError(f"{chosen}不提供强调选项：只有选奇川风才有第二轮，按选入制不标强调")
        return dict(style=chosen, emphasis=dict(nodes=[], edges=[]), label="无（使用者未指定）")
    if len(set(picks)) > MAX_MARK:
        raise ValueError(f"重点至多 {MAX_MARK} 处，收到 {len(set(picks))} 处")
    cands = _candidates(nodes, edges)
    em = dict(nodes=[], edges=[])
    names = []
    for p in dict.fromkeys(picks):
        if not p.isdigit() or not 1 <= int(p) <= len(cands):
            raise ValueError(f"编号 {p} 不在清单里（1 到 {len(cands)}）")
        kind, key, text = cands[int(p) - 1]
        em["nodes" if kind == "node" else "edges"].append(key)
        names.append(text)
    return dict(style=chosen, emphasis=em,
                label="；".join(names) if names else "无（使用者未指定）")


def needs_round2(choice_or_style):
    s = choice_or_style["style"] if isinstance(choice_or_style, dict) else choice_or_style
    return s == "奇川风"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["trim", "round1", "round2", "resolve"])
    ap.add_argument("--keep")
    ap.add_argument("--keep-edges")
    ap.add_argument("--out")
    ap.add_argument("relations", nargs="?")
    ap.add_argument("--style")
    ap.add_argument("--mark")
    a = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if a.cmd == "round1":
        print(round1())
    elif a.cmd == "trim":
        if not a.relations:
            sys.exit("需要 relations.json")
        rel = json.load(open(a.relations, encoding="utf-8"))
        merged = merge_parallel(rel["edges"])
        n_merged = len(rel["edges"]) - len(merged)
        rel["edges"] = merged
        over_n = len(rel["nodes"]) > MAX_MODULES and not rel.get("over9")
        over_e = len(merged) > MAX_EDGES and not rel.get("over12")
        try:
            if a.keep is not None or (a.out is not None and a.keep_edges is None and over_n):
                res = trim_resolve(rel, a.keep)
                what = "模块"
            elif a.keep_edges is not None or (a.out is not None and over_e):
                if over_n:
                    sys.exit("模块还超过 9 个，先定模块（--keep）再定关系")
                res = trim_edges_resolve(rel, a.keep_edges)
                what = "关系"
            elif a.out is not None:
                res, what = rel, None
            else:
                if n_merged:
                    print(f"同方向、同一对模块之间的 {n_merged} 条关系已合并（关系名用「；」连起来，不删字）\n")
                if over_n:
                    print(trim_question(rel["nodes"], merged))
                elif over_e:
                    print(trim_edges_question(rel["nodes"], merged))
                else:
                    print(f"模块 {len(rel['nodes'])} 个、关系 {len(merged)} 条，未超限，跳过第〇轮")
                sys.exit(0)
        except ValueError as e:
            sys.exit("选择无效：" + str(e))
        dst = a.out or a.relations
        json.dump(res, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        d = res.get("dropped") or {}
        msg = f"已写入 {dst}：{len(res['nodes'])} 个模块、{len(res['edges'])} 条关系"
        if n_merged:
            msg += f"（其中合并同向重复关系 {n_merged} 条）"
        if res.get("over9") or res.get("over12"):
            msg += "，使用者要求全部保留"
        elif d:
            msg += f"，未入图累计 {len(d.get('nodes') or [])} 个模块、{len(d.get('edges') or [])} 条关系"
        print(msg)
        if len(res["nodes"]) <= MAX_MODULES and len(res["edges"]) > MAX_EDGES and not res.get("over12"):
            print(f"关系仍有 {len(res['edges'])} 条，超过 {MAX_EDGES} 条，接着问：")
            print(f"python scripts/ask.py trim {dst}")
    else:
        if not a.relations:
            sys.exit("需要 relations.json")
        nodes, edges = _load(a.relations)
        if a.cmd == "round2":
            print(round2(nodes, edges))
        else:
            try:
                print(json.dumps(resolve(nodes, edges, a.style, a.mark), ensure_ascii=False))
            except ValueError as e:
                sys.exit("选择无效：" + str(e))
