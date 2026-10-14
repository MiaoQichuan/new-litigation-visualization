#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在场景库里找图。**模型不读全库，只读这里返回的几条。**

库会越扩越大（几百条），整份读进来既费 token 又容易挑花眼。做法与法律关系图大师的布局查表
一样：代码去查，模型只看结果。

  python3 scripts/find.py 破产 清偿                 关键词（可多个）
  python3 scripts/find.py 资金 --area CRM          限定领域
  python3 scripts/find.py --scene client --ready   某场景下现在就能画的
  python3 scripts/find.py --show BKR-01            看一条的全部字段
  python3 scripts/find.py --forms                  各画法被多少场景用到（开发顺序）
  python3 scripts/find.py 加班 --tone lively       只要灵动的画法（steady = 严谨）

打分：名称命中权重最高，其次问题与例子；中文按单字与双字切分，不依赖分词库。
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.normpath(os.path.join(HERE, "..", "library"))


def grams(s):
    s = "".join(ch for ch in s.lower() if not ch.isspace())
    return set(s) | {s[i:i + 2] for i in range(len(s) - 1)}


def load():
    idx = json.load(open(os.path.join(LIB, "index.json"), encoding="utf-8-sig"))
    tax = json.load(open(os.path.join(LIB, "taxonomy.json"), encoding="utf-8-sig"))
    names = {k: {x["code"]: x["name"] for x in tax[k]} for k in ("areas", "scenes", "intents", "forms")}
    names["module"] = {x["code"]: x["module"] for x in tax["forms"]}
    return idx, tax, names


def score(r, words, names):
    if not words:
        return 1.0
    fields = [(r["name"], 5.0), (names["areas"][r["area"]] + names["intents"][r["intent"]], 2.0),
              (r["question"], 2.0), (r["example"], 1.0), (names["forms"][r["form"]], 1.5),
              ("".join(names["scenes"][s] for s in r["scenes"]), 1.0)]
    total = 0.0
    for w in words:
        g = grams(w)
        best = 0.0
        for text, wt in fields:
            if w in text:
                best = max(best, wt * 2)
            else:
                tg = grams(text)
                hit = len(g & tg) / max(1, len(g))
                best = max(best, wt * hit if hit >= 0.5 else 0)
        total += best
    return total


MODULE_SKILL = {"V1": "诉讼可视化重画", "V2": "时间轴大师", "V3": "法律关系图大师",
                "V4": "大事记表大师", "V5": "庭审对抗图大师"}


def mark_of(r, names):
    """一眼看清这一条现在能不能由 V6 画（外部评审 F11：库里有不等于 V6 已实现）。"""
    mod = names["module"].get(r["form"], "V6")
    if r["status"] == "ready" and mod != "V6":
        return f"V6 不画·转 {mod} {MODULE_SKILL.get(mod, '')}"
    return {"ready": "V6 可画", "todo": "待建·V6 现在画不了", "caution": "慎用"}[r["status"]]


def line(r, names):
    mark = mark_of(r, names)
    return (f"{r['id']:<8} {r['name']}　〔{names['forms'][r['form']]}·{mark}〕"
            f"　{names['areas'][r['area']]} / {names['intents'][r['intent']]}\n         {r['question']}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="在法律图表场景库里找图")
    ap.add_argument("words", nargs="*")
    ap.add_argument("--area")
    ap.add_argument("--scene")
    ap.add_argument("--intent")
    ap.add_argument("--form")
    ap.add_argument("--ready", action="store_true", help="只看现在就能画的")
    ap.add_argument("--tone", choices=("steady", "lively"), help="画法气质：严谨 / 灵动")
    ap.add_argument("-n", type=int, default=8)
    ap.add_argument("--show")
    ap.add_argument("--forms", action="store_true")
    a = ap.parse_args(argv)
    idx, tax, names = load()
    rs = idx["recipes"]
    if a.show:
        r = next((r for r in rs if r["id"] == a.show), None)
        if not r:
            print(f"没有 {a.show}")
            return 1
        print(f"{r['id']}　{r['name']}")
        print(f"领域　{names['areas'][r['area']]}　意图　{names['intents'][r['intent']]}")
        print(f"场景　{'、'.join(names['scenes'][s] for s in r['scenes'])}")
        print(f"画法　{names['forms'][r['form']]}（{r['form']}，{ {'ready': '现在就能画', 'todo': '画法待建', 'caution': '慎用'}[r['status']] }）")
        print(f"问题　{r['question']}")
        print(f"例子　{r['example']}")
        if r["guard"]:
            print(f"守卫　{r['guard']}")
        return 0
    if a.forms:
        fm = {x["code"]: x for x in tax["forms"]}
        print("画法　　　　　　　　　被几条场景用到　状态　气质")
        for code, n in idx["form_usage"].items():
            x = fm[code]
            print(f"  {x['name']:<10}{code:<12}{n:>4}　　{ {'ready': '可画', 'todo': '待建', 'caution': '慎用'}[x['status']] }（{x['module']}）"
                  f"　{'灵动' if x.get('tone') == 'lively' else '严谨'}")
        return 0
    tone = {x["code"]: x.get("tone", "steady") for x in tax["forms"]}
    pool = [r for r in rs
            if (not a.area or r["area"] == a.area) and (not a.scene or a.scene in r["scenes"])
            and (not a.intent or r["intent"] == a.intent) and (not a.form or r["form"] == a.form)
            and (not a.ready or r["status"] == "ready")
            and (not a.tone or tone[r["form"]] == a.tone)]
    scored = sorted(((score(r, a.words, names), r) for r in pool), key=lambda t: (-t[0], t[1]["id"]))
    scored = [t for t in scored if t[0] > 0][: a.n]
    if not scored:
        print("没有找到。换个说法，或去掉筛选条件；库里没有的场景请在 library/recipes.txt 里补一行。")
        return 1
    for _, r in scored:
        print(line(r, names))
    return 0


if __name__ == "__main__":
    # Windows 中文系统的控制台默认 GBK：不固定成 UTF-8，外部 AI（按 UTF-8 读）看到的是乱码，
    # 遇到 GBK 里没有的字（生僻字人名）还会在图已画好之后崩掉。写法与其余模块一致。
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:                               # noqa: BLE001
            pass
    sys.exit(main())
