#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""场景库构建：library/recipes.txt + library/taxonomy.json → library/index.json

库的思路（ADR 0005）：**场景可以无限扩，画法慢慢长。** 加一个场景只是在 recipes.txt 里加一行，
不写代码；它必须落在已登记的画法上。真正要写渲染器与守卫的只有画法，二三十种就够。

本脚本只做两件事：校验每一行（领域、画法、意图、场景的代码都已登记，字段齐全，名称不重复），
然后生成 index.json。校验失败就不写文件，退出码 1。

  python3 scripts/build_library.py          生成并校验
  python3 scripts/build_library.py --check  只校验 index.json 是否与源文件一致（回归用）
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.normpath(os.path.join(HERE, "..", "library"))


def load():
    tax = json.load(open(os.path.join(LIB, "taxonomy.json"), encoding="utf-8-sig"))
    codes = {k: {x["code"] for x in tax[k]} for k in ("areas", "scenes", "intents", "forms")}
    rows, errs, seen, count = [], [], set(), {}
    for no, line in enumerate(open(os.path.join(LIB, "recipes.txt"), encoding="utf-8-sig"), 1):
        line = line.rstrip("\n")
        if not line.strip() or line.startswith("#"):
            continue
        f = line.split("|")
        if len(f) != 8:
            errs.append(f"第 {no} 行：要 8 列，现在 {len(f)} 列")
            continue
        area, form, intent, scenes, name, q, ex, guard = (x.strip() for x in f)
        sc = [s.strip() for s in scenes.split(",") if s.strip()]
        for label, val, key in (("领域", area, "areas"), ("画法", form, "forms"), ("意图", intent, "intents")):
            if val not in codes[key]:
                errs.append(f"第 {no} 行：{label}代码 {val!r} 没有登记（见 taxonomy.json）")
        for s in sc:
            if s not in codes["scenes"]:
                errs.append(f"第 {no} 行：场景代码 {s!r} 没有登记")
        if not sc or not name or not q or not ex:
            errs.append(f"第 {no} 行：场景、名称、问题、例子都不能空")
        if (area, name) in seen:
            errs.append(f"第 {no} 行：{area} 领域里已有一条叫「{name}」")
        seen.add((area, name))
        count[area] = count.get(area, 0) + 1
        rows.append({"id": f"{area}-{count[area]:02d}", "area": area, "form": form, "intent": intent,
                     "scenes": sc, "name": name, "question": q, "example": ex, "guard": guard})
    return tax, rows, errs


def build(tax, rows):
    st = {x["code"]: x["status"] for x in tax["forms"]}
    for r in rows:
        r["status"] = st[r["form"]]
    use = {}
    for r in rows:
        use[r["form"]] = use.get(r["form"], 0) + 1
    return {"version": 1, "count": len(rows), "form_usage": dict(sorted(use.items(), key=lambda kv: -kv[1])),
            "recipes": rows}


def main(argv):
    tax, rows, errs = load()
    if errs:
        print("场景库有问题，没有生成：", file=sys.stderr)
        for e in errs:
            print("  " + e, file=sys.stderr)
        return 1
    idx = build(tax, rows)
    text = json.dumps(idx, ensure_ascii=False, indent=1) + "\n"
    path = os.path.join(LIB, "index.json")
    if "--check" in argv:
        cur = open(path, encoding="utf-8-sig").read() if os.path.exists(path) else ""
        if cur != text:
            print("index.json 与 recipes.txt 不一致：请运行 python3 scripts/build_library.py", file=sys.stderr)
            return 1
        print(f"场景库一致：{idx['count']} 条")
        return 0
    open(path, "w", encoding="utf-8").write(text)
    ready = sum(1 for r in rows if r["status"] == "ready")
    print(f"场景库：{idx['count']} 条，现在就能画 {ready} 条，待建画法上的 {idx['count'] - ready} 条")
    return 0


if __name__ == "__main__":
    # Windows 中文系统的控制台默认 GBK：不固定成 UTF-8，外部 AI（按 UTF-8 读）看到的是乱码，
    # 遇到 GBK 里没有的字（生僻字人名）还会在图已画好之后崩掉。写法与其余模块一致。
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:                               # noqa: BLE001
            pass
    sys.exit(main(sys.argv[1:]))
