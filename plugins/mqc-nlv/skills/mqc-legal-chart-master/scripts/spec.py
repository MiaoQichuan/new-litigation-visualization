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

CHARTS = ("bar", "hbar", "waffle", "rose", "dumbbell", "strip", "sankey", "ribbon", "waterfall",
          "funnel", "matrix", "fan", "converge", "cascade", "lineage", "interval", "radpie")
CHART_ZH = {"bar": "竖柱", "hbar": "横条", "waffle": "百点方阵", "rose": "南丁格尔玫瑰",
            "dumbbell": "哑铃", "strip": "逐件分布", "sankey": "桑基", "ribbon": "汇入图", "waterfall": "逐级加减",
            "funnel": "漏斗", "matrix": "气泡矩阵", "fan": "发射扇", "converge": "放射汇聚",
            "cascade": "点阵阶梯", "lineage": "法条沿革", "interval": "区间胶囊", "radpie": "双读饼"}

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
          "ribbon": (16, "个来源与去处"), "waterfall": (12, "级"),
          "funnel": (8, "级"), "matrix": (120, "格"), "fan": (12, "根辐条"), "converge": (60, "个条目"),
          "cascade": (16, "列"), "lineage": (10, "行"), "interval": (12, "条"), "radpie": (8, "个扇区")}
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
             "steps": "{id, label, value}", "stages": "{id, label, value}", "rows": "{id, label}",
             "cols": "{id, label}", "cells": "{row, col, value}"}
_CONVERGE_HINT = {"groups": "{id, label}", "items": "{id, group, label?}"}
_DUMBBELL_HINT = "{id, label, from, to}"
_ITEM_HINT = {"dumbbell": _DUMBBELL_HINT, "lineage": "{id, label, start, revisions?, end?}",
              "interval": "{id, label, from, to, mid?}", "radpie": "{id, label, value, size}"}


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
        if key == "items" and chart in _ITEM_HINT:
            hint = _ITEM_HINT[chart]
        if chart == "converge" and key in _CONVERGE_HINT:
            hint = _CONVERGE_HINT[key]
        for k, row in enumerate(arr):
            if not isinstance(row, dict):
                raise SpecError(f"data.{key}[{k}] 要写成一个对象 {hint}，收到 {row!r:.40}")
            for f in ("id", "from", "to", "row", "col", "group"):
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


# ------------------------------------------------------------ 0.10.0 新增四种画法的校验
def _rows_of(data, key, need, lo, hi, what):
    """一列 {id, label, ...}：个数在 lo..hi 之间，字段齐、id 不重复。"""
    arr = data.get(key)
    if not isinstance(arr, list) or not lo <= len(arr) <= hi:
        raise SpecError(f"{what}要在 data.{key} 里给 {lo} 到 {hi} 个")
    ids = set()
    for k, r in enumerate(arr):
        for f in need:
            if f not in r:
                raise SpecError(f"data.{key}[{k}] 缺 {f}")
        if r["id"] in ids:
            raise SpecError(f"data.{key} 里 id {r['id']!r} 重复")
        ids.add(r["id"])
        if "label" in r and not str(r["label"]).strip():
            raise SpecError(f"data.{key}[{k}].label 是空的")
    return arr


def _validate_funnel(data):
    """漏斗：一级比一级少（或相等）。有增有减不是漏斗，是逐级加减。"""
    stages = _rows_of(data, "stages", ("id", "label", "value"), 2, BUDGET["funnel"][0], "漏斗")
    prev = None
    for k, s in enumerate(stages):
        _num(s["value"], f"data.stages[{k}].value")
        if s["value"] <= 0:
            raise SpecError(f"data.stages[{k}]「{s['label']}」要大于 0；漏斗里件数为 0 的一级请删掉，"
                            f"并在标题或来源里说明到哪一级为止")
        if prev is not None and s["value"] > prev["value"] + 1e-9:
            raise SpecError(f"漏斗的「{s['label']}」（{_fmt(s['value'])}）比上一级「{prev['label']}」"
                            f"（{_fmt(prev['value'])}）多：漏斗只能一级级减少。有增有减请用逐级加减（waterfall）")
        prev = s


def _validate_matrix(data):
    """气泡矩阵：行 × 列，每格一个数，气泡面积即数值。没写的格就是 0。"""
    rows = _rows_of(data, "rows", ("id", "label"), 2, 12, "气泡矩阵的行")
    cols = _rows_of(data, "cols", ("id", "label"), 2, 14, "气泡矩阵的列")
    if len(rows) * len(cols) > BUDGET["matrix"][0]:
        raise SpecError(f"气泡矩阵 {len(rows)} 行 × {len(cols)} 列 = {len(rows) * len(cols)} 格，"
                        f"超过一页的 {BUDGET['matrix'][0]} 格。请拆成两页，或合并长尾为「其他」")
    rid, cid = {r["id"] for r in rows}, {c["id"] for c in cols}
    both = rid & cid
    if both:
        raise SpecError(f"行与列的 id 不能同名：{'、'.join(map(str, sorted(both, key=str)))}")
    cells = data.get("cells")
    if not isinstance(cells, list) or not cells:
        raise SpecError("气泡矩阵要在 data.cells 里给出每一格：[{\"row\": 行 id, \"col\": 列 id, \"value\": 数}]；"
                        "没写的格按 0 画（空格）")
    seen, dashed = set(), False
    for k, c in enumerate(cells):
        for f in ("row", "col", "value"):
            if f not in c:
                raise SpecError(f"data.cells[{k}] 缺 {f}")
        if c["row"] not in rid:
            raise SpecError(_id_miss(f"data.cells[{k}].row", c["row"], [r["id"] for r in rows]))
        if c["col"] not in cid:
            raise SpecError(_id_miss(f"data.cells[{k}].col", c["col"], [x["id"] for x in cols]))
        if (c["row"], c["col"]) in seen:
            raise SpecError(f"data.cells[{k}] 与前面的一格重复（{c['row']} × {c['col']}）")
        seen.add((c["row"], c["col"]))
        _num(c["value"], f"data.cells[{k}].value")
        if c["value"] <= 0:
            raise SpecError(f"data.cells[{k}].value 要大于 0；是 0 的格不要写（没写的格按 0 画）")
        if set(c) - {"row", "col", "value", "status"}:
            raise SpecError(f"data.cells[{k}] 只写 row、col、value、status")
        if "status" in c:
            if c["status"] != "dashed":
                raise SpecError(f"data.cells[{k}].status 只认 \"dashed\"（虚线圈：例如试行期、数据不全的年份）")
            dashed = True
    if dashed and not (isinstance(data.get("dashed_label"), str) and data["dashed_label"].strip()):
        raise SpecError("有虚线圈的格，就要写 data.dashed_label：虚线圈是什么意思（例如「试行期」「当年数据不全」），"
                        "印在图例里")


def _validate_fan(data):
    """发射扇：从一个根发出几根辐条，辐条长即数值；可选 size，辐条端点的圆面积即 size。"""
    items = _items(data, "fan")
    if not 2 <= len(items) <= BUDGET["fan"][0]:
        raise SpecError(f"发射扇要 2 到 {BUDGET['fan'][0]} 根辐条")
    for k, it in enumerate(items):
        if it["value"] <= 0:
            raise SpecError(f"data.items[{k}].value 要大于 0（辐条长度）")
    st = [("start" in it) for it in items]
    if any(st) and not all(st):
        raise SpecError("发射扇的 start（圆在径向上的位置，例如立案后第几周开庭）要么每根辐条都写，要么都不写")
    if all(st):
        for k, it in enumerate(items):
            _num(it["start"], f"data.items[{k}].start")
            if it["start"] < 0:
                raise SpecError(f"data.items[{k}].start 不能是负数")
        if not (isinstance(data.get("start_label"), str) and data["start_label"].strip()):
            raise SpecError("写了 start，就要写 data.start_label：圆的位置代表什么（例如「首次开庭」）")
    has = [("size" in it) for it in items]
    if any(has) and not all(has):
        raise SpecError("发射扇的 size（圆的面积）要么每根辐条都写，要么都不写")
    if all(has):
        for k, it in enumerate(items):
            _num(it["size"], f"data.items[{k}].size")
            if it["size"] <= 0:
                raise SpecError(f"data.items[{k}].size 要大于 0")
        if not (isinstance(data.get("size_label"), str) and data["size_label"].strip()):
            raise SpecError("写了 size，就要写 data.size_label：圆的面积代表什么（例如「标的额（万元）」）")


def _validate_converge(data):
    """放射汇聚：一圈条目（一条请求、一个争点），各自汇入一个主题。"""
    groups = _rows_of(data, "groups", ("id", "label"), 2, 8, "放射汇聚的主题")
    items = data.get("items")
    lim = BUDGET["converge"][0]
    if not isinstance(items, list) or not 4 <= len(items) <= lim:
        raise SpecError(f"放射汇聚要在 data.items 里给 4 到 {lim} 个条目（一个点一条）")
    gid = {g["id"] for g in groups}
    seen = set()
    for k, it in enumerate(items):
        if not isinstance(it, dict):
            raise SpecError(f"data.items[{k}] 要写成一个对象 {{id, group, label?}}")
        for f in ("id", "group"):
            if f not in it:
                raise SpecError(f"data.items[{k}] 缺 {f}")
        if it["id"] in seen or it["id"] in gid:
            raise SpecError(f"data.items[{k}] 的 id {it['id']!r} 重复或与主题同名")
        seen.add(it["id"])
        if it["group"] not in gid:
            raise SpecError(_id_miss(f"data.items[{k}].group", it["group"], [g["id"] for g in groups]))
        if "label" in it and not str(it["label"]).strip():
            raise SpecError(f"data.items[{k}].label 是空的；不写名字就整项不写 label")
        if set(it) - {"id", "group", "label"}:
            raise SpecError(f"data.items[{k}] 只写 id、group、label")
    for g in groups:
        if not any(it["group"] == g["id"] for it in items):
            raise SpecError(f"主题「{g['label']}」没有任何条目；没有条目的主题请删掉")
    has = [("label" in it) for it in items]
    if any(has) and not all(has):
        raise SpecError("条目的 label 要么每一条都写，要么都不写（都不写就只画点，名单附在交付清单里）")


# ------------------------------------------------------------ 0.11.0 新增四种画法的校验
_PER_STEPS = (1, 2, 5, 10, 20, 25, 50)
CASCADE_MAX_CELLS = 30          # 一列最多 30 格：再多，一格就小到看不出是方块


def cascade_per(data):
    """点阵阶梯一格代表多少：写了 data.per 就用它；没写就从 1、2、5、10、20、25、50、100……里
    取最小的一档，使最高的一列不超过 24 格。由数据决定，同一份说明永远同一档。"""
    if data.get("per") is not None:
        return data["per"]
    vmax = max(i["value"] for i in data["items"])
    mag = 1
    while True:
        for s in _PER_STEPS:
            if math.ceil(vmax / (s * mag) - 1e-9) <= 24:
                return s * mag
        mag *= 100 if mag == 1 else 10
        if mag > 10 ** 15:
            return s * mag


def cascade_cells(v, per):
    """一列画几格：四舍五入到格（2.5 格画 3 格）。"""
    return int(math.floor(v / per + 0.5 + 1e-9))


def _validate_cascade(data):
    """点阵阶梯：几个类目各有一个件数，一格 = per 件，一列方块由少到多排成阶梯。"""
    items = _items(data, "cascade")
    lim = BUDGET["cascade"][0]
    if not 3 <= len(items) <= lim:
        raise SpecError(f"点阵阶梯要 3 到 {lim} 列；两三个类目请用竖柱或百点方阵，更多请合并长尾为「其他」")
    for k, it in enumerate(items):
        if it["value"] <= 0:
            raise SpecError(f"data.items[{k}]「{it['label']}」要大于 0；是 0 的一项请删掉")
    per = data.get("per")
    if per is not None:
        _num(per, "data.per")
        if per <= 0:
            raise SpecError("data.per（一格代表多少）要大于 0")
    per = cascade_per(data)
    for k, it in enumerate(items):
        c = cascade_cells(it["value"], per)
        if c < 1:
            raise SpecError(f"「{it['label']}」只有 {_fmt(it['value'])}，不到半格（一格 = {_fmt(per)}），画出来就没了。"
                            f"请把 data.per 调小")
        if c > CASCADE_MAX_CELLS:
            raise SpecError(f"「{it['label']}」要画 {c} 格，一列最多 {CASCADE_MAX_CELLS} 格。请把 data.per 调大"
                            f"（例如 {_fmt(per * 2)}），或不写 per 由脚本选")


_YEAR_KEYS = ("start", "revisions", "end")


def _year(v, where):
    if isinstance(v, bool) or not isinstance(v, int) or not 1000 <= v <= 2999:
        raise SpecError(f"{where} 要是四位数的年份（整数，例如 2023），收到 {v!r:.40}")
    return v


def _validate_lineage(data):
    """法条沿革：一行一部法律、司法解释或一份文件；何年通过、何年修改、何年废止。年份由人写，几何由年份算。"""
    items = _rows_of(data, "items", ("id", "label", "start"), 2, BUDGET["lineage"][0], "法条沿革")
    until = _year(data.get("until"), "data.until（截至哪一年：现行有效的线画到这一年）")
    for k, it in enumerate(items):
        extra = set(it) - {"id", "label", "start", "revisions", "end"}
        if extra:
            raise SpecError(f"data.items[{k}] 只写 id、label、start、revisions、end，多了 {'、'.join(sorted(extra))}")
        a = _year(it["start"], f"data.items[{k}].start")
        revs = it.get("revisions", [])
        if not isinstance(revs, list):
            raise SpecError(f"data.items[{k}].revisions 要是年份列表，例如 [2005, 2013]")
        for j, r in enumerate(revs):
            _year(r, f"data.items[{k}].revisions[{j}]")
        if revs != sorted(set(revs)):
            raise SpecError(f"「{it['label']}」的修改年份要从早到晚写、不重复；同一年改了两次请只写一次，"
                            f"并在 scope 或来源里注明")
        end = it.get("end")
        if end is not None:
            _year(end, f"data.items[{k}].end")
        last = end if end is not None else until
        if a > last:
            raise SpecError(f"「{it['label']}」{a} 年通过，晚于 {'废止年份' if end is not None else '截至年份'} {last}")
        if end is not None and end > until:
            raise SpecError(f"「{it['label']}」{end} 年废止，晚于截至年份 {until}：请把 data.until 改到 {end} 年或以后")
        for r in revs:
            if not a < r <= until or (end is not None and r >= end):
                raise SpecError(f"「{it['label']}」的修改年份 {r} 要在通过（{a}）之后、"
                                f"{'废止（' + str(end) + '）之前' if end is not None else '截至年份（' + str(until) + '）之内'}")
    mk = data.get("marks")
    if mk is not None:
        if not isinstance(mk, dict) or set(mk) - {"start", "revise", "end"}:
            raise SpecError("data.marks 只写 start、revise、end 三项，例如 {\"start\": \"公布\", \"revise\": \"修正\", \"end\": \"废止\"}")
        for key, v in mk.items():
            if not isinstance(v, str) or not 1 <= len(v.strip()) <= 4:
                raise SpecError(f"data.marks.{key} 要是 1 到 4 个字（例如「通过」「修改」「废止」）")


def _validate_interval(data):
    """区间胶囊：每一项一段从低到高的区间（判赔的最低到最高、刑期的下限到上限）；可选 mid 标中位数。"""
    items = _rows_of(data, "items", ("id", "label", "from", "to"), 2, BUDGET["interval"][0], "区间胶囊")
    for k, it in enumerate(items):
        extra = set(it) - {"id", "label", "from", "to", "mid"}
        if extra:
            raise SpecError(f"data.items[{k}] 只写 id、label、from、to、mid，多了 {'、'.join(sorted(extra))}")
        a = _num(it["from"], f"data.items[{k}].from")
        b = _num(it["to"], f"data.items[{k}].to")
        if a > b:
            raise SpecError(f"「{it['label']}」的 from（{_fmt(a)}）比 to（{_fmt(b)}）大：from 写低的一端，to 写高的一端")
        if "mid" in it:
            c = _num(it["mid"], f"data.items[{k}].mid")
            if not a <= c <= b:
                raise SpecError(f"「{it['label']}」的 mid（{_fmt(c)}）不在 {_fmt(a)} 到 {_fmt(b)} 之间")
    has = [("mid" in it) for it in items]
    if any(has) and not all(has):
        raise SpecError("区间胶囊的 mid（胶囊上的白点）要么每一项都写，要么都不写")
    if all(has) and not (isinstance(data.get("mid_label"), str) and data["mid_label"].strip()):
        raise SpecError("写了 mid，就要写 data.mid_label：白点代表什么（例如「中位数」「点估计」）")


COUNT_UNITS = ("", "件", "个", "起", "份", "宗", "人", "家", "次", "项", "条")


def _validate_radpie(data):
    """双读饼：角度 = 占比，从内圈量起的长度 = 第二个量（平均审理天数、平均标的额）。"""
    items = _items(data, "radpie", need=("id", "label", "value", "size"))
    lim = BUDGET["radpie"][0]
    if not 2 <= len(items) <= lim:
        raise SpecError(f"双读饼要 2 到 {lim} 个扇区；更多请合并长尾为「其他」")
    for k, it in enumerate(items):
        if it["value"] <= 0:
            raise SpecError(f"data.items[{k}].value 要大于 0（扇区的角度）；是 0 的一项请删掉")
        _num(it["size"], f"data.items[{k}].size")
        if it["size"] <= 0:
            raise SpecError(f"data.items[{k}].size 要大于 0（扇区从内圈伸出的长度）")
    tot, smax = xsum(i["value"] for i in items), max(i["size"] for i in items)
    for it in items:
        if it["value"] / tot < 0.015:
            raise SpecError(f"「{it['label']}」只占 {_fmt(round(it['value'] / tot * 100, 2))}%，扇区窄到看不见。"
                            f"请把占比不足 1.5% 的几项合并为「其他」")
        if it["size"] < smax / 20:
            raise SpecError(f"「{it['label']}」的 size（{_fmt(it['size'])}）不到最大值的二十分之一，扇区短到看不见。"
                            f"两个量差得这么悬殊，请改用横条或哑铃分开画")
    if not (isinstance(data.get("size_label"), str) and data["size_label"].strip()):
        raise SpecError("双读饼要写 data.size_label：扇区的长短代表什么（例如「平均审理天数」）")
    su = data.get("size_unit")
    if su is not None and not isinstance(su, str):
        raise SpecError("data.size_unit 要是文字（例如「天」「万元」）")


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

    elif chart == "funnel":
        _validate_funnel(data)
    elif chart == "matrix":
        _validate_matrix(data)
    elif chart == "fan":
        _validate_fan(data)
    elif chart == "converge":
        _validate_converge(data)
    elif chart == "cascade":
        _validate_cascade(data)
    elif chart == "lineage":
        _validate_lineage(data)
    elif chart == "interval":
        _validate_interval(data)
    elif chart == "radpie":
        _validate_radpie(data)

    d = derive(m)
    m["_derived"] = d
    if d.get("n_computed") is not None and d["n_computed"] != m["n"]:
        raise SpecError(f"n 写的是 {m['n']}，按数据算是 {d['n_computed']}（{d['n_how']}）。两者必须一致")
    emph = m.get("emphasis")
    if emph is not None and emph not in d["ids"]:
        raise SpecError(_id_miss("emphasis", emph, d["ids"]))
    if emph is not None and chart == "converge" and emph not in d["group_ids"]:
        raise SpecError(f"放射汇聚的重音指向一个主题（groups 里的 id），收到条目 {emph!r}；"
                        f"可选：{'、'.join(map(str, d['group_ids']))}")
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
    elif chart == "funnel":
        n = len(data["stages"])
    elif chart == "matrix":
        n = len(data["rows"]) * len(data["cols"])
    elif chart in ("fan", "converge", "cascade", "lineage", "interval", "radpie"):
        n = len(data["items"])
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
    elif chart == "funnel":
        stages = data["stages"]
        vals = [s["value"] for s in stages]
        ids = [s["id"] for s in stages]
        first = vals[0]
        for s in stages:
            raw(s["value"], ids=[s["id"]])
            N.addp(s["value"] / first * 100, (first - s["value"]) / first * 100, ids=[s["id"], ids[0]])
        for a_, b_ in zip(stages, stages[1:]):
            w = [a_["id"], b_["id"]]
            raw(a_["value"] - b_["value"], ids=w)
            N.addp(b_["value"] / a_["value"] * 100, (a_["value"] - b_["value"]) / a_["value"] * 100, ids=w)
        N.pairs(vals, ids, pct_data=pdata)
        N.add(len(stages))
        out["n_computed"] = int(first) if float(first).is_integer() else None
        out["n_how"] = "第一级的件数"
        labels(*(s["label"] for s in stages))
    elif chart == "matrix":
        rows, cols, cells = data["rows"], data["cols"], data["cells"]
        ids = [r["id"] for r in rows] + [c["id"] for c in cols]
        val = {(c["row"], c["col"]): c["value"] for c in cells}
        tot = xsum(val.values())
        rt = {r["id"]: xsum(v for (a, _), v in val.items() if a == r["id"]) for r in rows}
        ct = {c["id"]: xsum(v for (_, b), v in val.items() if b == c["id"]) for c in cols}
        out["row_total"], out["col_total"], out["cell"] = rt, ct, val
        raw(tot)
        N.add(len(rows), len(cols), len(cells))
        for (a, b), v in val.items():
            raw(v, ids=[a, b])
            if rt[a]:
                N.addp(v / rt[a] * 100, ids=[a, b])
            if ct[b]:
                N.addp(v / ct[b] * 100, ids=[a, b])
        for k_, v in list(rt.items()) + list(ct.items()):
            raw(v, ids=[k_])
            if tot:
                N.addp(v / tot * 100, ids=[k_])
        N.pairs([rt[r["id"]] for r in rows], [r["id"] for r in rows], pct_data=pdata)
        N.pairs([ct[c["id"]] for c in cols], [c["id"] for c in cols], pct_data=pdata)
        # 同一列（或同一行）里的比较只认三种说法：相邻（「比上年减少」）、与第一个比（「较 2019 年增长」）、
        # 与最后一个比（「2026 年为 2019 年的几倍」）。全部两两相比会让可出现的数多到几乎什么都对得上，
        # 编的数就混进来了。
        for line, other, is_row in (([r["id"] for r in rows], [c["id"] for c in cols], True),
                                    ([c["id"] for c in cols], [r["id"] for r in rows], False)):
            for o in other:
                seq = [(x, val.get((x, o) if is_row else (o, x))) for x in line]
                seq = [(x, v) for x, v in seq if v]
                pairs = list(zip(seq, seq[1:]))
                pairs += [(seq[0], e) for e in seq[2:]] + [(e, seq[-1]) for e in seq[1:-2]]
                for (xa, va), (xb, vb) in pairs:
                    w = [xa, xb, o]
                    (N.addpp if pdata else N.add)(vb - va, va - vb, abs(vb - va), ids=w)
                    N.addp((vb - va) / va * 100, vb / va * 100, (va - vb) / va * 100, ids=w)
                    N.add(vb / va, ids=w)
        labels(*(x["label"] for x in rows + cols))
    elif chart == "fan":
        items = data["items"]
        ids = [i["id"] for i in items]
        vals = [i["value"] for i in items]
        for it in items:
            raw(it["value"], ids=[it["id"]])
        N.add(len(items))
        N.pairs(vals, ids, pct_data=pdata)
        if all("size" in i for i in items):
            sizes = [i["size"] for i in items]
            stot = xsum(sizes)
            for it in items:
                N.add(it["size"], ids=[it["id"]])
                N.addp(it["size"] / stot * 100, ids=[it["id"]])
            N.add(stot)
            N.pairs(sizes, ids)
        if all("start" in i for i in items):
            for it in items:
                raw(it["start"], it["start"] + it["value"], ids=[it["id"]])   # 起点与终点（第几周开庭、第几周结案）
        labels(*(i["label"] for i in items))
    elif chart == "converge":
        groups, items = data["groups"], data["items"]
        gids = [g["id"] for g in groups]
        ids = gids + [i["id"] for i in items]
        cnt = {g: sum(1 for i in items if i["group"] == g) for g in gids}
        out["group_count"] = cnt
        out["group_ids"] = gids
        total = len(items)
        for g, c in cnt.items():
            N.add(c, ids=[g])
            N.addp(c / total * 100, ids=[g])
        N.add(total, len(groups))
        N.pairs([cnt[g] for g in gids], gids)
        out["n_computed"], out["n_how"] = total, "条目数（一个点一条）"
        labels(*(g["label"] for g in groups))
        labels(*(i["label"] for i in items if "label" in i))
    elif chart == "cascade":
        items = data["items"]
        ids = [i["id"] for i in items]
        vals = [i["value"] for i in items]
        per = cascade_per(data)
        out["per"] = per
        out["cells"] = {i["id"]: cascade_cells(i["value"], per) for i in items}
        out["rounded"] = any(abs(i["value"] / per - round(i["value"] / per)) > 1e-9 for i in items)
        for it in items:
            raw(it["value"], ids=[it["id"]])
            if not pdata:
                N.addp(it["value"] / m["n"] * 100, ids=[it["id"]])     # 「出现在 16% 的判决里」：占 n 的比例
        N.add(len(items))
        for v in set(vals):
            N.add(sum(1 for x in vals if x == v))
        if not pdata:
            N.add(xsum(vals))
        N.pairs(vals, ids, pct_data=pdata)
        labels(*(i["label"] for i in items))
    elif chart == "lineage":
        items = data["items"]
        ids = [i["id"] for i in items]
        until = data["until"]
        out["n_computed"], out["n_how"] = len(items), "行数（一行一部法律或一份文件）"
        nrev = []
        for it in items:
            w = [it["id"]]
            revs = it.get("revisions", [])
            nrev.append(len(revs))
            N.add(len(revs), ids=w)                                   # 修改几次
            N.add((it.get("end") or until) - it["start"], ids=w)      # 施行多少年（到废止或截至）
            if revs:
                N.add(revs[-1] - it["start"], ids=w)                  # 「30 年间修改 6 次」：通过到最后一次修改
            labels(it["label"], it["start"], *revs, *([it["end"]] if "end" in it else []))
        labels(until)
        N.add(len(items), xsum(nrev))
        N.add(sum(1 for i in items if "end" in i), sum(1 for i in items if "end" not in i))
        # 修改次数不做两两相减：「民法典修改 6 次」会借「公司法比民法典多 6 次」混过去
    elif chart == "interval":
        items = data["items"]
        ids = [i["id"] for i in items]
        for it in items:
            w = [it["id"]]
            a, b = it["from"], it["to"]
            raw(a, b, ids=w)
            if "mid" in it:
                raw(it["mid"], ids=w)
            (N.addpp if pdata else N.add)(b - a, ids=w)               # 区间宽度
            if a > 0:
                N.add(b / a, ids=w)
                N.addp((b - a) / a * 100, ids=w)
        N.add(len(items))
        N.pairs([i["to"] - i["from"] for i in items], ids, pct_data=pdata)
        N.pairs([i["to"] for i in items], ids, pct_data=pdata)
        N.pairs([i["from"] for i in items], ids, pct_data=pdata)
        if all("mid" in i for i in items):
            N.pairs([i["mid"] for i in items], ids, pct_data=pdata)
        labels(*(i["label"] for i in items))
    elif chart == "radpie":
        items = data["items"]
        ids = [i["id"] for i in items]
        vals = [i["value"] for i in items]
        sizes = [i["size"] for i in items]
        tot = xsum(vals)
        spct = str(data.get("size_unit", "")).strip() in ("%", "％")
        shares = {}
        for it in items:
            w = [it["id"]]
            raw(it["value"], ids=w)
            shares[it["id"]] = it["value"] / tot * 100
            N.addp(shares[it["id"]], ids=w)
            (N.addp if spct else N.add)(it["size"], ids=w)
        sl = list(shares.values())
        for a_, ia in zip(sl, ids):
            for b_, ib in zip(sl, ids):
                if ia != ib:
                    N.addpp(a_ - b_, abs(a_ - b_), ids=[ia, ib])
        N.add(len(items))
        if not pdata:
            N.add(tot)
        N.pairs(vals, ids, pct_data=pdata)
        N.pairs(sizes, ids, pct_data=spct)
        out["shares"] = shares
        unit = str(m.get("unit", "")).strip()
        if all(float(v).is_integer() for v in vals) and unit in COUNT_UNITS:
            out["n_computed"], out["n_how"] = int(tot), "各扇区件数之和"
        labels(*(i["label"] for i in items))
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
    for key in ("items", "groups", "nodes", "sources", "targets", "steps", "stages", "rows", "cols"):
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
