# -*- coding: utf-8 -*-
"""读入并校验一份图表说明（chart spec），算出所有派生数。

分工与其他模块一致：模型只写 JSON，**派生数一律由这里算**——合计、占比、中位数、
增长率、超过阈值的件数。JSON 里没有放派生数的字段，模型想写也没处写。

标题里出现的阿拉伯数字必须能由数据推出（原值、n、或这里算出的派生数之一），
否则拒绝出图。这是「照录原文」在数字上的对应物：图上的字只许删、不许改，
图上的数只许算、不许编。

中文的倍数与分数（「四成」「三分之一」「翻倍」）不在机器核对范围内，会列进交付清单
请律师人工过一眼。宁可少核一条，也不留一条会误判的检查。
"""
import json
import os
import math
import re
from statistics import median

CHARTS = ("bar", "hbar", "waffle", "rose", "dumbbell", "strip", "sankey", "ribbon", "waterfall")
CHART_ZH = {"bar": "竖柱", "hbar": "横条", "waffle": "百点方阵", "rose": "南丁格尔玫瑰",
            "dumbbell": "哑铃", "strip": "逐件分布", "sankey": "桑基", "ribbon": "汇入图", "waterfall": "逐级加减"}

CANVAS = {                      # 物理尺寸 → 像素（96 dpi，与 PPTX 的 EMU 换算一致）
    "slide": (1280, 720),       # 16:9 整页，13.33 × 7.5 英寸
    "slide-half": (608, 600),   # 16:9 页面里左右各半的内容区
    "a4-landscape": (1123, 794),
    "square": (1080, 1080),     # 1:1，公众号正文配图、朋友圈、视频号封面
    "portrait": (1080, 1440),   # 3:4 竖版，小红书与手机竖屏
    "wide-cover": (1200, 630),  # 约 1.9:1，文章头图与链接预览
}
CANVAS_ZH = {"slide": "16:9 整页", "slide-half": "16:9 半页", "a4-landscape": "A4 横向",
             "square": "1:1 方图", "portrait": "3:4 竖图", "wide-cover": "头图"}

# 复杂度预算（学自 diagram-design 的 complexity budget）：每种图一页最多画多少个对象。
# 超了不是「挤一挤」，而是拆成「总览一页 + 细节一页」，或合并长尾为「其他」。
# 用到七成以上，出图计划里会提醒「接近上限」。
BUDGET = {"bar": (14, "根柱"), "hbar": (16, "条"), "waffle": (4, "个类目"), "rose": (12, "个扇区"),
          "dumbbell": (12, "行"), "strip": (6, "组"), "sankey": (14, "个节点"),
          "ribbon": (16, "个来源与去处"), "waterfall": (12, "级")}
MAX_ANNOTATIONS = 2           # 批注一页最多两条：第三条开始，读者就分不清哪条要紧
ANNOTATABLE = ("bar", "hbar", "dumbbell", "waterfall")
MIN_CANVAS = (480, 360)

TOP_KEYS = {"schema_version", "chart", "title", "scope", "source", "unit",
            "n", "emphasis", "style", "accent", "canvas", "data", "order", "note", "annotations",
            "dataset", "view"}         # dataset + view：逐件记录与怎么看，由 pivot.py 算成 data（0.9.8）

_FRACTION_WORDS = re.compile(r"(一半|半数|过半|[一二两三四五六七八九]成|[二三四五六七八九十]分之[一二三四五六七八九]|翻番|翻倍|[一二两三四五六七八九十]倍)")


def xsum(vals):
    """与 Python 版本无关的求和。内置 sum() 在 3.12 起对浮点做补偿求和，与 3.11 差在末位，
    桑基、汇入图按这个和排位置，图就差 0.01 px、不再逐字节相同（0.9.8 实测：浮点金额的汇入图）。
    全是整数时照旧精确相加；有浮点就用 math.fsum（精确舍入，各版本一致）。"""
    vals = list(vals)
    if all(isinstance(v, int) for v in vals):
        return sum(vals)
    return math.fsum(vals)


class SpecError(ValueError):
    pass


def _num(v, where):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise SpecError(f"{where} 要是数字，收到 {v!r}")
    return v


def _items(data, chart, need=("id", "label", "value")):
    items = data.get("items")
    if not isinstance(items, list) or not items:
        raise SpecError(f"{CHART_ZH[chart]}要在 data.items 里给出数据")
    ids = set()
    for k, it in enumerate(items):
        for f in need:
            if f not in it:
                raise SpecError(f"data.items[{k}] 缺 {f}")
        if it["id"] in ids:
            raise SpecError(f"data.items 里 id {it['id']!r} 重复")
        ids.add(it["id"])
        for f in need:
            if f in ("value", "from", "to"):
                _num(it[f], f"data.items[{k}].{f}")
                if it[f] < 0:
                    raise SpecError(f"data.items[{k}].{f} 是负数。本模块首批图种都只画非负量；"
                                    f"有正有负的数据请等后续的正负条图")
    return items


# 每一类数组里，一条要写成什么样子：报错时原样告诉模型
_ROW_HINT = {"items": "{id, label, value}", "groups": "{id, label, values}", "nodes": "{id, label, stage}",
             "links": "{from, to, value}", "sources": "{id, label}", "targets": "{id, label}",
             "steps": "{id, label, value}"}
_DUMBBELL_HINT = "{id, label, from, to}"


def _is_key(v):
    """id、from、to 不能是列表或对象（原来会崩）。其余写法原来能出图的，照旧放行。"""
    return not isinstance(v, (list, dict))


def _shape(m, chart, data):
    """结构预检：先把「形状不对」说成人话，再做语义校验。

    外部实测（0.9.8 之前）：data 写成字符串、items 里混进一个裸字符串、id 写成列表、stage 写成文字……
    约四百种写坏法会直接甩出 Python 堆栈（TypeError / AttributeError），模型读不懂、只能乱试。
    这里只拦「原来就会崩」的写法，原来能出图的说明一份也不多拒。报错都带字段路径。"""
    if "unit" in m and not isinstance(m["unit"], str) and not m["unit"]:
        m.pop("unit")                                # null、0、[]：当作没写（百点方阵原来会崩）
    elif "unit" in m and not isinstance(m["unit"], str):
        m["unit"] = str(m["unit"])                   # 写成了数字：多数图种原来就按文字印出，玫瑰与百点方阵却会崩
    if not isinstance(data, dict):
        raise SpecError(f"data 要是一个对象（{{...}}），收到 {type(data).__name__} {data!r:.40}")
    for key, hint in _ROW_HINT.items():
        arr = data.get(key)
        if arr is None or not isinstance(arr, list):
            continue
        if chart == "dumbbell" and key == "items":
            hint = _DUMBBELL_HINT
        for k, row in enumerate(arr):
            if not isinstance(row, dict):
                raise SpecError(f"data.{key}[{k}] 要写成一个对象 {hint}，收到 {row!r:.40}")
            for f in ("id", "from", "to"):
                if f in row and not _is_key(row[f]):
                    raise SpecError(f"data.{key}[{k}].{f} 要是文字（建议加引号），收到 {row[f]!r:.40}")
            if key == "nodes" and "stage" in row and not isinstance(row["stage"], int):
                raise SpecError(f"data.nodes[{k}].stage 要是整数（第几段，从 0 起），收到 {row['stage']!r:.40}")
    for nm in ("start", "end", "threshold"):
        x = data.get(nm)
        if x is not None and not isinstance(x, dict):
            raise SpecError(f"data.{nm} 要写成一个对象 {{label, value}}，收到 {x!r:.40}")


def _id_miss(where, v, ids):
    """指向的 id 不存在时的报错。若只是「文字 '7'」对「数字 7」这种类型不一致，直说。"""
    same = [i for i in ids if str(i) == str(v)]
    if same:
        return (f"{where} 写的是 {v!r}，数据里的 id 是 {same[0]!r}：一个是文字、一个是数字，"
                f"两边写成同一种（建议 id 一律加引号写成文字）")
    return f"{where} 指向 {v!r}，数据里没有这个 id。可选：{'、'.join(map(str, ids))}"


def load(path_or_obj):
    if isinstance(path_or_obj, dict):
        m = json.loads(json.dumps(path_or_obj))
    else:
        if not os.path.isfile(path_or_obj):           # 路径打错是最常见的：说清楚，不甩 FileNotFoundError 的堆栈
            raise SpecError(f"找不到图表说明 {path_or_obj}：请核对路径（中文路径与空格都可以，记得加引号）")
        try:
            with open(path_or_obj, encoding="utf-8-sig") as f:
                m = json.load(f)
        except json.JSONDecodeError as e:
            raise SpecError(f"JSON 写坏了：第 {e.lineno} 行第 {e.colno} 列，{e.msg}")
        except UnicodeDecodeError:
            raise SpecError("图表说明不是 UTF-8 文本：请用 UTF-8 保存（可能是别的格式改了扩展名）")
    return validate(m)


def validate(m):
    errs = []
    if not isinstance(m, dict):
        raise SpecError("图表说明的顶层要是一个对象")
    trace = None
    if ("dataset" in m or "view" in m) and m.get("chart") in CHARTS:
        import pivot                                  # 逐件记录 → data：分组、计数、求和由脚本做
        trace = pivot.expand(m)
    extra = set(m) - TOP_KEYS
    if extra:
        errs.append(f"不认识的字段：{'、'.join(sorted(extra))}（拼错了？）")
    _sv = m.get("schema_version", 1)
    if isinstance(_sv, int) and not isinstance(_sv, bool) and _sv > 1:
        # 更新版本的法律图表大师写的：明说「请升级」，别让人以为说明写坏了（学自案图：文件比程序新，就这么说）
        errs.append(f"这份说明是更新版本的法律图表大师写的（schema_version {_sv}），本机的版本只认到 1：请把插件升级到最新版再试")
    elif _sv != 1:
        errs.append("schema_version 只支持 1")
    chart = m.get("chart")
    if chart not in CHARTS:
        errs.append(f"chart 要是 {' / '.join(CHARTS)} 之一，收到 {chart!r}")
    for f in ("title", "scope", "source"):
        if not isinstance(m.get(f), str) or not m[f].strip():
            why = {"title": "图名", "scope": "口径（样本是什么、从哪来、什么时间段）",
                   "source": "来源行"}[f]
            errs.append(f"缺 {f}：{why}。没有{why}的图不出")
    if "n" not in m:
        errs.append("缺 n：样本量。公开裁判文书不是全量，图上必须写明 n")
    elif not isinstance(m["n"], int) or isinstance(m["n"], bool) or m["n"] <= 0:
        errs.append(f"n 要是正整数，收到 {m['n']!r}")
    if errs:
        raise SpecError("；\n".join(errs))

    data = m.get("data") or {}
    _shape(m, chart, data)
    if chart in ("bar", "hbar", "waffle", "rose"):
        items = _items(data, chart)
        if chart in ("rose",) and len(items) < 3:
            raise SpecError("玫瑰图至少要 3 个类目；两三个类目请用横条或百点方阵")
        if chart == "rose" and len(items) > 12:
            raise SpecError("玫瑰图最多 12 个类目；更多请合并长尾为「其他」，或改用横条")
        if chart == "bar" and len(items) > 14:
            raise SpecError("竖柱最多 14 根；类目更多请改用横条，或拆成「总览 + 细节」两页")
        if chart == "hbar" and len(items) > 16:
            raise SpecError("横条最多 16 条；更多请合并长尾为「其他」")
        if chart == "waffle" and not 2 <= len(items) <= 4:
            raise SpecError("百点方阵要 2 到 4 个类目（含强调的那一类）；更多请用横条")
        if chart in ("waffle", "rose") and xsum(i["value"] for i in items) <= 0:
            raise SpecError("合计为 0，画不出构成")
    elif chart == "dumbbell":
        items = _items(data, chart, need=("id", "label", "from", "to"))
        if len(items) > 12:
            raise SpecError("哑铃图最多 12 行")
        for f in ("from_label", "to_label"):
            if not isinstance(data.get(f), str) or not data[f]:
                raise SpecError(f"哑铃图要写 data.{f}（两端各叫什么，例如「诉请」「判赔」）")
    elif chart == "strip":
        groups = data.get("groups")
        if not isinstance(groups, list) or not 1 <= len(groups) <= 6:
            raise SpecError("逐件分布要在 data.groups 里给 1 到 6 组")
        seen = set()
        for k, g in enumerate(groups):
            for f in ("id", "label", "values"):
                if f not in g:
                    raise SpecError(f"data.groups[{k}] 缺 {f}")
            if g["id"] in seen:
                raise SpecError(f"data.groups 里 id {g['id']!r} 重复")
            seen.add(g["id"])
            if not isinstance(g["values"], list) or not g["values"]:
                raise SpecError(f"data.groups[{k}].values 要是非空的数字列表（一件一个值）")
            for j, v in enumerate(g["values"]):
                _num(v, f"data.groups[{k}].values[{j}]")
                if v < 0:
                    raise SpecError(f"data.groups[{k}].values[{j}] 是负数")
            if len(g["values"]) > 400:
                raise SpecError("每组最多 400 件；更多请改画分箱（后续图种）")
        th = data.get("threshold")
        if th is not None:
            if not isinstance(th, dict) or "value" not in th or "label" not in th:
                raise SpecError("data.threshold 要写成 {\"value\": 180, \"label\": \"六个月\"}")
            _num(th["value"], "data.threshold.value")
    elif chart == "waterfall":
        st, steps, end = data.get("start"), data.get("steps"), data.get("end")
        if not isinstance(st, dict) or not isinstance(end, dict) or not isinstance(steps, list) or not steps:
            raise SpecError("逐级加减要写 data.start、data.steps、data.end：从哪个数出发、每一级加减多少、落到哪个数")
        if len(steps) > 12:
            raise SpecError("逐级加减最多 12 级；更多请合并成「其他」")
        for nm, x in (("start", st), ("end", end)):
            if "label" not in x or "value" not in x:
                raise SpecError(f"data.{nm} 要有 label 与 value")
            _num(x["value"], f"data.{nm}.value")
        ids = set()
        for k, s in enumerate(steps):
            for f in ("id", "label", "value"):
                if f not in s:
                    raise SpecError(f"data.steps[{k}] 缺 {f}")
            if s["id"] in ("start", "end") or s["id"] in ids:
                raise SpecError(f"data.steps[{k}] 的 id {s['id']!r} 重复或与 start / end 同名")
            ids.add(s["id"])
            _num(s["value"], f"data.steps[{k}].value")
            if s["value"] == 0:
                raise SpecError(f"data.steps[{k}]「{s['label']}」是 0；没有加减的一级请删掉")
        run = st["value"]
        for s in steps:
            run += s["value"]
            if run < -1e-9:
                raise SpecError(f"加减到「{s['label']}」时小于 0；逐级加减的累计不能为负")
        if abs(run - end["value"]) > 1e-6 * max(1.0, abs(end["value"])):
            raise SpecError(f"逐级加减不平：{_fmt(st['value'])} 加减各级之后是 {_fmt(round(run, 6))}，"
                            f"终点写的是 {_fmt(end['value'])}。每一级都要列出来，最后一级必须等于终点")
    elif chart == "ribbon":
        srcs, tgts, links = data.get("sources"), data.get("targets"), data.get("links")
        if not all(isinstance(x, list) and x for x in (srcs, tgts, links)):
            raise SpecError("汇入图要在 data.sources、data.targets、data.links 里给出来源、去处与流量")
        if not 2 <= len(srcs) <= 8 or not 2 <= len(tgts) <= 8:
            raise SpecError("汇入图两侧各 2 到 8 个；更多请合并为「其他」")
        ids = {}
        for side, arr in (("sources", srcs), ("targets", tgts)):
            for k, n in enumerate(arr):
                for f in ("id", "label"):
                    if f not in n:
                        raise SpecError(f"data.{side}[{k}] 缺 {f}")
                if n["id"] in ids:
                    raise SpecError(f"汇入图里 id {n['id']!r} 重复（来源与去处也不能同名）")
                ids[n["id"]] = side
        seen = set()
        for k, l in enumerate(links):
            for f in ("from", "to", "value"):
                if f not in l:
                    raise SpecError(f"data.links[{k}] 缺 {f}")
            if ids.get(l["from"]) != "sources" or ids.get(l["to"]) != "targets":
                raise SpecError(f"data.links[{k}] 要从一个来源（sources）流向一个去处（targets）")
            if (l["from"], l["to"]) in seen:
                raise SpecError(f"data.links[{k}] 与前面的一条重复（{l['from']} → {l['to']}）；同一对请合并成一条")
            seen.add((l["from"], l["to"]))
            _num(l["value"], f"data.links[{k}].value")
            if l["value"] <= 0:
                raise SpecError(f"data.links[{k}].value 要大于 0")
        for nid, side in ids.items():
            key = "from" if side == "sources" else "to"
            if not any(l[key] == nid for l in links):
                raise SpecError(f"「{nid}」没有任何流量；没有流量的来源或去处请删掉")
    elif chart == "sankey":
        nodes, links = data.get("nodes"), data.get("links")
        if not isinstance(nodes, list) or not isinstance(links, list) or not nodes or not links:
            raise SpecError("桑基图要在 data.nodes 与 data.links 里给出节点和流量")
        ids = {}
        for k, n in enumerate(nodes):
            for f in ("id", "label", "stage"):
                if f not in n:
                    raise SpecError(f"data.nodes[{k}] 缺 {f}")
            if n["id"] in ids:
                raise SpecError(f"节点 id {n['id']!r} 重复")
            ids[n["id"]] = n
        stages = sorted({n["stage"] for n in nodes})
        if stages != list(range(len(stages))) or not 2 <= len(stages) <= 4:
            raise SpecError("桑基图的 stage 要从 0 连续编号，2 到 4 段")
        for k, l in enumerate(links):
            for f in ("from", "to", "value"):
                if f not in l:
                    raise SpecError(f"data.links[{k}] 缺 {f}")
            for f in ("from", "to"):
                if l[f] not in ids:
                    raise SpecError(_id_miss(f"data.links[{k}].{f}", l[f], list(ids)).replace("数据里没有这个 id", "没有这个节点"))
            if ids[l["to"]]["stage"] != ids[l["from"]]["stage"] + 1:
                raise SpecError(f"data.links[{k}] 只能连到下一段")
            _num(l["value"], f"data.links[{k}].value")
            if l["value"] <= 0:
                raise SpecError(f"data.links[{k}].value 要大于 0")
        for nid, n in ids.items():
            fin = xsum(l["value"] for l in links if l["to"] == nid)
            fout = xsum(l["value"] for l in links if l["from"] == nid)
            # 中间段的节点可以是终点（例如「服判息诉」）；一旦有流出，就必须进出相等
            if n["stage"] not in (0, stages[-1]) and fout > 0 and abs(fin - fout) > 1e-9:
                raise SpecError(f"节点「{n['label']}」流入 {_fmt(fin)}、流出 {_fmt(fout)}，对不上。"
                                f"中间节点必须进出相等，差额请画成一条去向（例如「其他」）")
            if n["stage"] == 0 and fout <= 0:
                raise SpecError(f"起点「{n['label']}」没有流出")
            if n["stage"] > 0 and fin <= 0:
                raise SpecError(f"节点「{n['label']}」没有流入")
        if len(nodes) > BUDGET["sankey"][0]:
            raise SpecError(f"桑基图最多 {BUDGET['sankey'][0]} 个节点，收到 {len(nodes)} 个。"
                            f"请拆成「总览一页 + 细节一页」，或把小去向合并为「其他」")

    d = derive(m)
    m["_derived"] = d
    if d.get("n_computed") is not None and d["n_computed"] != m["n"]:
        raise SpecError(f"n 写的是 {m['n']}，按数据算是 {d['n_computed']}（{d['n_how']}）。两者必须一致")
    emph = m.get("emphasis")
    if emph is not None and emph not in d["ids"]:
        raise SpecError(_id_miss("emphasis", emph, d["ids"]))
    errs, warns = check_numbers(m["title"], m, d, "标题")
    if errs:
        raise SpecError("；\n".join(errs))
    m["_warnings"] = warns + [f"标题含中文约数「{w}」：已按区间核到有数据对得上，但约数的分寸请人工过一眼"
                              for w in _FRACTION_WORDS.findall(m["title"])]
    _check_annotations(m, d)
    if trace is not None:
        import pivot
        m["_pivot_added"] = trace.pop("_added")
        m["_trace"] = trace
        m["_warnings"] += pivot.warnings(trace)
    return m


def budget_used(m):
    """返回 (用了多少, 上限, 量词)。"""
    data, chart = m["data"], m["chart"]
    if chart in ("bar", "hbar", "waffle", "rose", "dumbbell"):
        n = len(data["items"])
    elif chart == "strip":
        n = len(data["groups"])
    elif chart == "sankey":
        n = len(data["nodes"])
    elif chart == "ribbon":
        n = len(data["sources"]) + len(data["targets"])
    else:
        n = len(data["steps"])
    lim, unit = BUDGET[chart]
    return n, lim, unit


def _check_annotations(m, d):
    """批注（学自 diagram-design 的 annotation callout）：一句旁白 + 一条虚线引线指到一个数据上。

    批注是作者的话，不是数据，所以不要求照录；但它里面的阿拉伯数字与标题同一条规矩：
    只许算、不许编。"""
    ann = m.get("annotations")
    if ann is None:
        return
    if not isinstance(ann, list) or not ann:
        raise SpecError("annotations 要是一个列表：[{\"target\": 数据 id, \"text\": \"一句话\"}]")
    if m["chart"] not in ANNOTATABLE:
        raise SpecError(f"批注目前只支持{'、'.join(CHART_ZH[c] for c in ANNOTATABLE)}；"
                        f"{CHART_ZH[m['chart']]}请把要说的话写进标题")
    if len(ann) > MAX_ANNOTATIONS:
        raise SpecError(f"批注一页最多 {MAX_ANNOTATIONS} 条，收到 {len(ann)} 条。"
                        f"挑最要紧的两条；其余放讲稿或下一页")
    seen = set()
    for k, a in enumerate(ann):
        if not isinstance(a, dict) or set(a) - {"target", "text"} or "target" not in a or "text" not in a:
            raise SpecError(f"annotations[{k}] 只写 target 与 text 两项")
        if a["target"] not in d["ids"]:
            raise SpecError(_id_miss(f"annotations[{k}]", a["target"], d["ids"]))
        if a["target"] in seen:
            raise SpecError(f"annotations[{k}] 与前一条指向同一个数据；一个数据只配一条批注")
        seen.add(a["target"])
        t = a["text"]
        if not isinstance(t, str) or not 2 <= len(t.strip()) <= 40:
            raise SpecError(f"annotations[{k}].text 要是 2 到 40 字的一句话（旁白，不是段落）")
        errs, warns = check_numbers(t, m, d, f"批注「{t}」")
        if errs:
            raise SpecError("；\n".join(errs) + "。批注与标题同一条规矩")
        m["_warnings"] += warns
        m["_warnings"] += [f"批注含中文约数「{w}」：已按区间核对，分寸请人工过一眼"
                           for w in _FRACTION_WORDS.findall(t)]


def _fmt(v):
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    if isinstance(v, int):
        return f"{v:,}"
    s = f"{v:,.6f}".rstrip("0").rstrip(".")
    return s


class _Nums:
    """派生数分三类登记：num（件数、金额、差额、倍数）、pct（占比、增长率，标题里带 %）、
    pp（百分点差，标题里写「个百分点」）。另按数据 id 记下「这个数说的是谁」，供标题核对主语。"""

    def __init__(self):
        self.num, self.pct, self.pp = set(), set(), set()
        self.bind = {}                      # id -> {(kind, value)}

    @staticmethod
    def _ok(v):
        return v is not None and not isinstance(v, bool) and math.isfinite(v)

    def _put(self, kind, vals, ids):
        bag = getattr(self, kind)
        for v in vals:
            if not self._ok(v):
                continue
            v = round(v, 6)
            bag.add(v)
            for i in ids:
                self.bind.setdefault(i, set()).add((kind, v))

    def add(self, *vals, ids=()):
        self._put("num", vals, ids)

    def addp(self, *vals, ids=()):
        self._put("pct", vals, ids)

    def addpp(self, *vals, ids=()):
        self._put("pp", vals, ids)

    def pairs(self, vals, ids=None, pct_data=False):
        """两两比较：差额（数据本身是百分比时，差额就是百分点）、相对增减、占比、倍数。"""
        ids = ids or [None] * len(vals)
        for a, ia in zip(vals, ids):
            for b, ib in zip(vals, ids):
                if ia == ib and a == b:
                    continue
                who = [x for x in (ia, ib) if x is not None]
                if pct_data:
                    self.addpp(a - b, abs(a - b), ids=who)
                else:
                    self.add(a - b, abs(a - b), ids=who)
                if a:
                    self.addp((b - a) / a * 100, b / a * 100, ids=who)
                    self.add(b / a, ids=who)


def _pct_data(m):
    return str(m.get("unit", "")).strip() in ("%", "％", "百分比") or \
        (m["chart"] == "waffle" and (m["data"] or {}).get("measure") == "percent")


def derive(m):
    """算出所有派生数。返回 dict：num / pct / pp 三类可出现在标题里的数，bind 是每个数据 id 的指标。"""
    chart, data = m["chart"], m["data"]
    N = _Nums()
    ids = []
    out = {"n_computed": None, "n_how": ""}
    pdata = _pct_data(m)
    label_nums = []

    def labels(*ls):
        for lb in ls:
            for x in re.findall(r"\d+(?:\.\d+)?", str(lb)):
                label_nums.append(float(x))

    def raw(*vals, ids=()):
        (N.addp if pdata else N.add)(*vals, ids=ids)

    N.add(m["n"])
    if chart in ("bar", "hbar", "waffle", "rose"):
        items = data["items"]
        vals = [i["value"] for i in items]
        ids = [i["id"] for i in items]
        tot = xsum(vals)
        for it in items:
            raw(it["value"], ids=[it["id"]])
        N.add(len(items))
        if not pdata:
            N.add(tot)
        for v in set(vals):                     # 「几个类目并列」：取某个值的类目有几个
            N.add(sum(1 for x in vals if x == v))
        shares = {}
        if tot:
            for it in items:
                shares[it["id"]] = it["value"] / tot * 100
                N.addp(shares[it["id"]], ids=[it["id"]])
            sl = list(shares.values())
            for a, ia in zip(sl, ids):
                for b, ib in zip(sl, ids):
                    if ia != ib:
                        N.addpp(a - b, abs(a - b), ids=[ia, ib])
        N.pairs(vals, ids, pct_data=pdata)
        # 几个类目合起来：「获支持（全额 + 部分）占 74%」。不绑主语——合计不属于其中任何一个类目
        # 几个类目合起来的件数与占比：「获支持（全额 + 部分）占 74%」。**不进通用的数集**——
        # 类目一多，组合几乎能凑出任何数（7 个类目有 120 种组合），会把编的数放进来。
        # 只有分句里点到了恰好这几个类目，才认这个合计（见 check_numbers）。
        combos = []
        if 3 <= len(items) <= 8 and tot:
            from itertools import combinations
            for r_ in range(2, len(items)):
                for c_ in combinations(range(len(items)), r_):
                    sv = xsum(vals[i] for i in c_)
                    combos.append((frozenset(ids[i] for i in c_), sv, sv / tot * 100))
        out["combos"] = combos
        labels(*(i["label"] for i in items))
        if chart == "rose":
            out["n_computed"], out["n_how"] = int(tot) if float(tot).is_integer() else None, "各类目件数之和"
        if chart == "waffle":
            # 件数还是百分比，必须在说明里写明（data.measure），不靠猜：合计恰好 100 的件数
            # 与百分比长得一模一样，猜错了 n 就会被悄悄放过。
            measure = data.get("measure")
            if measure not in ("count", "percent"):
                raise SpecError("百点方阵要写明 data.measure：\"count\"（数值是件数，1 格 = 1 件）"
                                "或 \"percent\"（数值是百分比，1 格 = 1%）")
            count_mode = measure == "count"
            out["waffle_mode"] = measure
            if count_mode:
                if not all(float(v).is_integer() for v in vals):
                    raise SpecError("measure 是 count，数值就要是整数件数")
                if tot > 100:
                    raise SpecError(f"件数合计 {_fmt(tot)} 超过 100，一张方阵放不下。请改用 measure: percent")
                out["n_computed"], out["n_how"] = int(tot), "各类目件数之和（1 格 = 1 件）"
            elif abs(tot - 100) > 0.5:
                raise SpecError(f"measure 是 percent，各项合计要是 100；现在是 {_fmt(tot)}")
            out["dots"] = _largest_remainder(vals, 100) if not count_mode else [int(v) for v in vals]
        out["shares"] = shares
    elif chart == "dumbbell":
        items = data["items"]
        ids = [i["id"] for i in items]
        out["n_computed"], out["n_how"] = len(items), "行数"
        for i in items:
            a, b, w = i["from"], i["to"], [i["id"]]
            raw(a, b, ids=w)
            (N.addpp if pdata else N.add)(a - b, b - a, abs(a - b), ids=w)
            if a:
                N.addp(b / a * 100, (b - a) / a * 100, (a - b) / a * 100, ids=w)
                N.add(b / a, a / b if b else None, ids=w)
            labels(i["label"])
        N.add(len(items))
    elif chart == "strip":
        groups = data["groups"]
        ids = [g["id"] for g in groups]
        th = (data.get("threshold") or {}).get("value")
        total = 0
        stats = {}
        for g in groups:
            v, w = g["values"], [g["id"]]
            total += len(v)
            md = median(v)
            st = {"n": len(v), "median": md, "min": min(v), "max": max(v), "mean": xsum(v) / len(v)}
            N.add(len(v), ids=w)
            raw(md, min(v), max(v), st["mean"], ids=w)
            if th is not None:
                over = sum(1 for x in v if x > th)
                st["over"] = over
                N.add(over, len(v) - over, ids=w)
                N.addp(over / len(v) * 100, ids=w)
            stats[g["id"]] = st
            labels(g["label"])
        if th is not None:
            raw(th)
            ov = sum(s["over"] for s in stats.values())
            N.add(ov)
            N.addp(ov / total * 100)
        N.pairs([s["median"] for s in stats.values()], ids, pct_data=pdata)
        out["stats"] = stats
        out["n_computed"], out["n_how"] = total, "各组件数之和"
    elif chart == "waterfall":
        st, steps, end = data["start"], data["steps"], data["end"]
        ids = ["start"] + [s["id"] for s in steps] + ["end"]
        a, b = st["value"], end["value"]
        raw(a, ids=["start"])
        raw(b, ids=["end"])
        N.add(a - b, b - a, ids=["start", "end"])
        N.add(len(steps))
        if a:
            N.addp(b / a * 100, (a - b) / a * 100, (b - a) / a * 100, ids=["start", "end"])
            N.add(b / a, ids=["start", "end"])
        run, runs = a, [a]
        for s in steps:
            v = s["value"]
            run += v
            runs.append(run)
            raw(v, abs(v), run, ids=[s["id"]])
            if a:
                N.addp(abs(v) / a * 100, ids=[s["id"]])
            labels(s["label"])
        labels(st["label"], end["label"])
        neg = xsum(-s["value"] for s in steps if s["value"] < 0)
        pos = xsum(s["value"] for s in steps if s["value"] > 0)
        raw(neg, pos)
        if a:
            N.addp(neg / a * 100, pos / a * 100)
        out["runs"] = runs
    elif chart == "ribbon":
        srcs, tgts, links = data["sources"], data["targets"], data["links"]
        ids = [n["id"] for n in srcs] + [n["id"] for n in tgts]
        val = {n["id"]: xsum(l["value"] for l in links if l["from"] == n["id"]) for n in srcs}
        val.update({n["id"]: xsum(l["value"] for l in links if l["to"] == n["id"]) for n in tgts})
        total = xsum(l["value"] for l in links)
        out["node_value"] = val
        for k_, v in val.items():
            raw(v, ids=[k_])
            N.addp(v / total * 100, ids=[k_])
        raw(total)
        N.add(len(links), len(srcs), len(tgts))
        for l in links:
            w = [l["from"], l["to"]]
            raw(l["value"], ids=w)
            N.addp(l["value"] / total * 100, l["value"] / val[l["from"]] * 100,
                   l["value"] / val[l["to"]] * 100, ids=w)
        N.pairs([val[n["id"]] for n in srcs], [n["id"] for n in srcs], pct_data=pdata)
        N.pairs([val[n["id"]] for n in tgts], [n["id"] for n in tgts], pct_data=pdata)
        labels(*(n["label"] for n in srcs + tgts))
    elif chart == "sankey":
        nodes, links = data["nodes"], data["links"]
        ids = [n["id"] for n in nodes]
        val = {}
        for n in nodes:
            fin = xsum(l["value"] for l in links if l["to"] == n["id"])
            fout = xsum(l["value"] for l in links if l["from"] == n["id"])
            val[n["id"]] = max(fin, fout)
        out["node_value"] = val
        root = xsum(val[n["id"]] for n in nodes if n["stage"] == 0)
        out["n_computed"], out["n_how"] = int(root) if float(root).is_integer() else None, "第一段节点之和"
        for k_, v in val.items():
            raw(v, ids=[k_])
            N.addp(v / root * 100, ids=[k_])
        raw(root)
        for l in links:
            w = [l["from"], l["to"]]
            raw(l["value"], ids=w)
            N.addp(l["value"] / val[l["from"]] * 100, l["value"] / root * 100, ids=w)
        for n in nodes:
            sib = [l for l in links if l["from"] == n["id"]]
            N.pairs([l["value"] for l in sib], [l["to"] for l in sib], pct_data=pdata)
        labels(*(n["label"] for n in nodes))
    out["num"], out["pct"], out["pp"], out["bind"] = N.num, N.pct, N.pp, N.bind
    out["label_nums"] = set(label_nums)
    out["nums"] = N.num | N.pct | N.pp          # 旧接口：所有可出现的数（只用于展示，不用于核对）
    out["ids"] = ids
    return out


def _largest_remainder(vals, total):
    s = xsum(vals)
    raw = [v / s * total for v in vals]
    base = [int(math.floor(r)) for r in raw]
    rest = total - sum(base)
    order = sorted(range(len(vals)), key=lambda i: (-(raw[i] - base[i]), i))
    for i in order[:rest]:
        base[i] += 1
    return base


_KIND_ZH = {"num": "数", "pct": "百分比", "pp": "百分点差"}
_CLAUSE = re.compile(r"[，。；;,！!？?\n]")          # 冒号不断句：「驳回：41%」的主语就是驳回
_NEG = re.compile(r"(未|不|没有|没|非|无|并未|尚未|不足|不到|未能)$")
_BOUND = ("超过", "逾", "不止", "超", "多于", "以上", "近", "约")


def _match(x, pool, bound=False):
    for v in pool:
        if x == v or x == round(v) or x == round(v, 1) or (bound and abs(v) >= 1 and x == math.floor(v)):
            return True
    return False


def _labels(m):
    """数据 id → 类目名（图上读者看到的那几个字）。"""
    d, out = m["data"] or {}, {}
    for key in ("items", "groups", "nodes", "sources", "targets", "steps"):
        for x in d.get(key) or []:
            if isinstance(x, dict) and "id" in x and "label" in x:
                out[x["id"]] = str(x["label"])
    for key in ("start", "end"):
        if isinstance(d.get(key), dict) and "label" in d[key]:
            out[key] = str(d[key]["label"])
    return out


def _subject(text, tok, labels):
    """数字所在分句里，离它最近的类目名（优先在它前面的）。返回 id 或 None。"""
    seg_start = max([mt.end() for mt in _CLAUSE.finditer(text, 0, tok["start"])] or [0])
    nxt = _CLAUSE.search(text, tok["end"])
    seg_end = nxt.start() if nxt else len(text)
    hits = []
    for i, lb in labels.items():
        if not lb:
            continue
        for mt in re.finditer(re.escape(lb), text[seg_start:seg_end]):
            a, b = seg_start + mt.start(), seg_start + mt.end()
            hits.append((a, b, i))
    hits = [h for h in hits if not any(o[0] <= h[0] and h[1] <= o[1] and (o[1] - o[0]) > (h[1] - h[0])
                                       for o in hits)]          # 「支持」被「全额支持」盖住时不算
    before = [h for h in hits if h[1] <= tok["start"]]
    after = [h for h in hits if h[0] >= tok["end"]]
    if before:
        return max(before, key=lambda h: h[1])[2]
    if after:
        return min(after, key=lambda h: h[0])[2]
    return None


_CN = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def _fraction_claims(text):
    """中文分数与倍数 → [(原文, 下限, 上限, 类型)]。类型 pct 对占比与增长率核，ratio 对倍数核。
    容差放宽到「一成」的一半：四成 = 35%–45%（「近四成」「约四成」都在里面）。
    宁可放过边缘的说法，也不误拦正常写法；拦下的只是明显对不上的（41% 写成「九成」）。"""
    out = []
    for mt in re.finditer(r"([一二两三四五六七八九])成", text):
        v = _CN[mt.group(1)] * 10
        out.append((mt.group(0), v - 5, v + 5, "pct", mt.start(), mt.end()))
    for mt in re.finditer(r"([二三四五六七八九十])分之([一二三四五六七八九])", text):
        v = _CN[mt.group(2)] / _CN[mt.group(1)] * 100
        out.append((mt.group(0), v - 3, v + 3, "pct", mt.start(), mt.end()))
    for mt in re.finditer(r"一半|半数", text):
        out.append((mt.group(0), 45, 55, "pct", mt.start(), mt.end()))
    for mt in re.finditer(r"过半|超过半数|逾半|超过一半", text):
        out.append((mt.group(0), 50 + 1e-9, 100, "pct", mt.start(), mt.end()))   # 过半是 > 50，恰好 50 不是
    for mt in re.finditer(r"翻[一]?[倍番]", text):
        out.append((mt.group(0), 1.9, 2.1, "ratio", mt.start(), mt.end()))
    for mt in re.finditer(r"(?<![0-9])([两二三四五六七八九十])倍", text):
        v = _CN[mt.group(1)]
        out.append((mt.group(0), v * 0.95, v * 1.05, "ratio", mt.start(), mt.end()))
    return out


def _clause(text, tok):
    a = max([mt.end() for mt in _CLAUSE.finditer(text, 0, tok["start"])] or [0])
    nxt = _CLAUSE.search(text, tok["end"])
    return a, (nxt.start() if nxt else len(text))


def _mentioned(text, tok, labels):
    """分句里点到了哪些类目：类目名原样出现的，加上「获支持」这种只写了类目名一部分的
    （「支持」同时是「全额支持」「部分支持」的一部分，就算点到这两个）。"""
    a, b = _clause(text, tok)
    seg = text[a:b]
    out, covered = set(), [False] * len(seg)
    for i, lb in sorted(labels.items(), key=lambda kv: -len(kv[1])):
        for mt in re.finditer(re.escape(lb), seg) if lb else ():
            if not any(covered[mt.start():mt.end()]):
                out.add(i)
                for j in range(mt.start(), mt.end()):
                    covered[j] = True
    rest = "".join(ch if not covered[j] else "|" for j, ch in enumerate(seg))
    for L in (4, 3, 2):
        for j in range(len(rest) - L + 1):
            frag = rest[j:j + L]
            if "|" in frag or not re.fullmatch(r"[\u4e00-\u9fff]+", frag):
                continue
            owners = {i for i, lb in labels.items() if frag in lb}
            if len(owners) >= 2:
                out |= owners
    return frozenset(out)


def _combo(x, kind, text, tok, labels, d):
    """x 是不是分句里点到的那几个类目合起来的件数或占比。"""
    ment = _mentioned(text, tok, labels)
    if len(ment) < 2:
        return False
    for ids_, sv, sp in d.get("combos") or ():
        if ids_ == ment and _match(x, {round(sp if kind == "pct" else sv, 6)}):
            return True
    return False


def _negated_label(text, tok, labels):
    """「未获支持占41%」：分句里没有类目名，却有一个否定词加类目名的一部分。
    否定说法指哪几类说不清（未获支持 = 驳回？还是驳回 + 部分支持？），要求直接写类目名（外部测试 R2-007）。"""
    a, b = _clause(text, tok)
    seg = text[a:b]
    frags = {lb[i:i + 2] for lb in labels.values() for i in range(len(lb) - 1) if len(lb) >= 2}
    for mt in re.finditer(r"(未|不|没有|没|非|无)(获|被|予|得|到)?", seg):
        tail = seg[mt.end():mt.end() + 4]
        for f_ in frags:
            if tail.startswith(f_) or tail[1:].startswith(f_):
                return seg[mt.start():mt.end() + tail.find(f_) + len(f_)]
    return None


def _direction(text, tok, labels, d, m):
    """「A 比 B 多 / 少 X」：X 的大小对、方向反了也要拦（外部测试 R2-028）。只核类目可比的图。"""
    a, b = _clause(text, tok)
    seg = text[a:tok["start"]]
    mt = re.search(r"比(.{1,12}?)(多|少|高|低|增加|减少|上升|下降)了?\s*$", seg)
    if not mt:
        return None
    up = mt.group(2) in ("多", "高", "增加", "上升")
    pre, post = seg[:mt.start()], mt.group(1)
    hit = lambda s_: max(((s_.rfind(lb) + len(lb), i) for i, lb in labels.items() if lb and lb in s_),
                         default=(None, None))[1]
    ia, ib = hit(pre), hit(post)
    vals = {}
    data = m["data"] or {}
    for it in data.get("items") or []:
        vals[it["id"]] = it["value"]
    if ia is None or ib is None or ia not in vals or ib not in vals:
        return None
    va, vb = vals[ia], vals[ib]
    if tok["kind"] == "pp":
        sh = d.get("shares") or {}
        va, vb = sh.get(ia, va), sh.get(ib, vb)
    elif tok["kind"] == "pct":
        if not vb:
            return None
        va, vb = va / vb * 100, 100.0
    diff = va - vb
    if diff == 0 or (diff > 0) == up:
        return None
    return (f"说「{labels[ia]}比{labels[ib]}{mt.group(2)} {tok['text']}」，方向反了："
            f"「{labels[ia]}」比「{labels[ib]}」{'多' if diff > 0 else '少'}")


def check_numbers(text, m, d, what="标题"):
    """核对一段文字里的每一个数。返回 (错误列表, 请核列表)。

    * 带 % 的只能是占比、增长率；写「个百分点」的只能是百分点差；其余是件数、金额、差额、倍数。
      类型不对就算推不出——「提高 20%」与「提高 20 个百分点」不是一回事；
    * 一个数前后有类目名时，核它是不是**这个类目**的数：驳回 26 件、全额支持 41 件，
      「驳回率 41%」会被拦下（外部测试 T012）；
    * 年份须出现在口径、来源或类目里；条文编号、案号不是数据，列请核。"""
    from numtokens import extract
    errs, warns = [], []
    toks, masked, problems = extract(text)
    for c in masked:
        warns.append(f"{what}含案号「{c}」：不是数据，请核对与材料一致")
    for pb in problems:
        errs.append(f"{what}里{pb}")
    ctx = " ".join([str(m.get("scope", "")), str(m.get("source", ""))] + list(_labels(m).values()))
    labels = _labels(m)
    for t in toks:
        x = -t["value"] if t["sign"] == "-" else t["value"]
        if t["role"] == "cite":
            warns.append(f"{what}含条文编号「{t['text']}」：不是数据，请核对条文")
            continue
        if t["role"] == "ordinal":
            if not (float(t["value"]).is_integer() and 1 <= t["value"] <= m["n"]):
                errs.append(f"{what}里的「第{t['raw']}…」是顺序编号，可样本只有 {_fmt(m['n'])} 个，排不到第 {t['raw']}")
            else:
                warns.append(f"{what}含顺序编号「第{t['raw']}」：不是统计数，请核对它指的是哪一件")
            continue
        if t["role"] == "year":
            if t["raw"] not in ctx and not _match(t["value"], d["label_nums"]):
                errs.append(f"{what}里的年份 {t['raw']} 不在口径、来源或类目里。时间范围请写进 scope，"
                            f"图上的年份要能在材料里找到")
            continue
        pool = d[t["kind"]] | (d["label_nums"] if t["kind"] == "num" else set())
        bound = any(w in text[max(0, t["start"] - 3):t["start"]] for w in _BOUND)
        combo = t["kind"] in ("num", "pct") and _combo(x, t["kind"], text, t, labels, d)
        if combo:
            continue
        ok = _match(x, pool, bound) if t["sign"] else (_match(x, pool, bound) or _match(-x, pool, bound))
        if not ok:
            hint = ""
            if t["kind"] == "pct" and _match(t["value"], d["pp"]):
                hint = f"；{_fmt(t['value'])} 是两个百分比之差，应写「{_fmt(t['value'])} 个百分点」，不是「%」"
            elif t["kind"] == "num" and _match(t["value"], d["pct"]):
                hint = "；这个数是百分比，要带 %"
            elif t["kind"] == "pp" and _match(t["value"], d["pct"]):
                hint = "；这个数是相对增减或占比，应带 %，不是「个百分点」"
            errs.append(f"{what}里的{_KIND_ZH[t['kind']]} {t['text']} 由数据推不出来{hint}。"
                        f"数只许算、不许编：写原值、n，或由数据直接算得的占比、增长、差额、件数")
            continue
        sid = _subject(text, t, labels)
        if sid is None and labels:
            ng = _negated_label(text, t, labels)
            if ng:
                errs.append(f"{what}里的「{ng}」不是图上的类目名，{t['text']} 说的是哪几类说不清。"
                            f"请直接写类目名（{'、'.join(list(labels.values())[:4])}）")
                continue
        dirr = _direction(text, t, labels, d, m)
        if dirr:
            errs.append(f"{what}{dirr}")
            continue
        if sid is not None and d["bind"]:
            mine = {v for k, v in d["bind"].get(sid, set()) if k == t["kind"]}
            if not _match(x, mine, bound) and not _match(-x, mine, bound):
                owners = [i for i, bag in d["bind"].items() if i != sid and
                          _match(x, {v for k, v in bag if k == t["kind"]}, bound)]
                own = "、".join(f"「{labels.get(o, o)}」" for o in owners[:3])
                errs.append(f"{what}把 {t['text']} 安在「{labels[sid]}」上，" +
                            (f"可这个数属于{own}。" if owners else f"可「{labels[sid]}」没有这个数。") +
                            "主语与数字要对得上（分母、类目不能串）；说几个类目合起来，就把这几个类目名都写上")
    for word, lo, hi, kind, a, b in _fraction_claims(text):
        k = "pct" if kind == "pct" else "num"
        # 中文比例说的是「占多少」：只对 0–100 之间的占比核，不让一个 150% 的增长率替「过半」作证
        shares = d.get("shares") or {}
        if kind == "pct" and shares:
            # 有构成的图：中文比例说的是「占多少」，只拿占比核：单个类目，或分句里点到的那几个类目合起来
            ment = _mentioned(text, {"start": a, "end": b}, labels)
            pool = {round(v, 6) for v in shares.values()} | {round(p_, 6) for ids_, _, p_ in d.get("combos") or ()
                                                              if ids_ == ment}
        else:
            pool = {v for v in d[k] if 0 <= v <= 100} if kind == "pct" else {v for v in d["num"] if v > 0}
        sid = _subject(text, {"start": a, "end": b}, labels)

        def own(i):
            # 有主语时只用它的「占比」核：「部分支持是全额支持的 48%」这类类目间比值不能替「过半」作证
            if kind == "pct" and i in shares:
                return {round(shares[i], 6)}
            return {v for kk, v in d["bind"].get(i, set()) if kk == k and (kind != "pct" or 0 <= v <= 100)}
        neg = _NEG.search(text[max(0, a - 3):a])
        if neg:
            # 「并未过半」「不足四成」：说的是「比这个少」。有主语就核主语，没有主语只列请核
            bound = 50 if word in ("过半", "超过半数", "逾半", "超过一半", "一半", "半数") else (lo + hi) / 2
            if sid is not None and d["bind"].get(sid):
                mine = own(sid)
                if mine and not any(v <= bound + 1e-9 for v in mine):
                    errs.append(f"{what}说「{labels[sid]}」{neg.group(0)}{word}，可它的占比是 "
                                f"{'、'.join(_fmt(round(v, 1)) for v in sorted(mine))}")
            warns.append(f"{what}含否定的约数「{neg.group(0)}{word}」：方向已核，分寸请人工过一眼")
            continue
        if sid is not None and d["bind"].get(sid):
            mine = own(sid)
            if not any(lo <= v <= hi for v in mine):
                errs.append(f"{what}把「{word}」安在「{labels[sid]}」上，可「{labels[sid]}」的数对不上"
                            f"（与它相关的百分比是 {'、'.join(_fmt(round(v, 1)) for v in sorted(mine) if 0 < v <= 100)[:40] or '无'}）")
                continue
        if not any(lo <= v <= hi for v in pool):
            near = sorted(pool, key=lambda v: min(abs(v - lo), abs(v - hi)))[:3]
            errs.append(f"{what}里的「{word}」与数据对不上：图上没有一个{'占比或增长率' if kind == 'pct' else '倍数'}"
                        f"落在这个范围（最接近的是 {'、'.join(_fmt(round(v, 1)) for v in near) or '无'}）")
    return errs, warns


def title_numbers(title, d):
    """旧接口（0.8.0 及以前），保留给外部脚本：返回推不出来的数字原文列表。
    只做数字层核对（类型 + 数值），不做主语绑定；新代码请用 check_numbers。"""
    from numtokens import extract
    bad = []
    toks, _, problems = extract(title)
    for t in toks:
        if t["role"] != "data":
            continue
        pool = d.get(t["kind"], d.get("nums", set())) | (d.get("label_nums", set()) if t["kind"] == "num" else set())
        x = -t["value"] if t["sign"] == "-" else t["value"]
        if not (_match(x, pool) or (not t["sign"] and _match(-x, pool))):
            bad.append(t["text"])
    return bad + problems
