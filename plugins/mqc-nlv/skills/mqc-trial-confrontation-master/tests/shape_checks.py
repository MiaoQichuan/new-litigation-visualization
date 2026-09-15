#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""编排结构：版面跟着材料走，有几段攻防出几张卡。
可能的编排只有四种——左2右2 / 左2右1 / 左1右1 / 左1右0（对方尚无任何回应）。
左1右2 不成立：有再回应必先有反制。这一条在数据层（B2）与几何层（L2）各拦一道。"""
import os, sys, json, copy, io, contextlib, subprocess
import tempfile as _tempfile
_TMP = _tempfile.gettempdir()   # 不写死 /tmp：Windows 上没有这个目录，自检一跑就找不到文件
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import render_main as RM
from to_figure import convert

M = json.load(open(os.path.join(ROOT, "examples/matrix-input.json"), encoding="utf-8"))
errs = []
def ck(no, cond, msg):
    print(("  OK  " if cond else "  FAIL") + f" {no}  {msg}")
    if not cond: errs.append(no)

def blank(part_i, *keys):
    d = copy.deepcopy(M)
    for cb in d["parts"][part_i]["claim_bases"]:
        for e in cb["elements"]:
            for k in keys: e[k] = "—"
    return d

def shape(F, i=1):        # 展开后 P1 一组、P2 一组，改的是 P2 那组
    p = F["parts"][i]
    return (sum(1 for c in p["cards"] if c["side"] == "claim"),
            sum(1 for c in p["cards"] if c["side"] == "defend"))

def render(d):
    F = convert(d)
    try:
        with contextlib.redirect_stdout(io.StringIO()): ok = RM.render(F, os.path.join(_TMP, "_shape.svg"))
        return shape(F), (None if ok else "拒绝出图")
    except AssertionError as e:
        return shape(F), str(e)

for no, name, d, want in (
        ("L1a", "四段齐全", blank(1), (2, 2)),
        ("L1b", "没有再回应", blank(1, "second"), (2, 1)),
        ("L1c", "只有主张与回应", blank(1, "second", "counter"), (1, 1)),
        ("L1d", "对方尚无任何回应", blank(1, "second", "response"), (2, 0)),
):
    got, err = render(d)
    ck(no, got == want and err is None, f"{name} → 左{got[0]}右{got[1]}（应为 左{want[0]}右{want[1]}）"
       + (f"，出图被拒：{err[:40]}" if err else ""))

bad = blank(1, "counter")                      # P2-1 的再回应有实质内容，去掉反制即左1右2
got, err = render(bad)
ck("L2", got == (1, 2) and err and err.startswith("L2"), f"左1右2 被几何层拦下（实为 {err[:38] if err else '出图了'}）")

json.dump(bad, open(os.path.join(_TMP, "_shape.json"), "w", encoding="utf-8"), ensure_ascii=False)
r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts/check_claims.py"), os.path.join(_TMP, "_shape.json")],
                   capture_output=True, text=True)
ck("B2", any("FAIL B2" in l for l in r.stdout.splitlines()), "左1右2 在数据层也被拦下（反制为空而再回应有内容）")

print()
print("  全部通过" if not errs else f"  未通过：{sorted(set(errs))}")
sys.exit(1 if errs else 0)
