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
if __name__ == "__main__":
    # Windows 中文控制台默认 GBK：这个脚本由 pipeline 以子进程方式调用，
    # 不固定成 UTF-8，外部 AI（按 UTF-8 读）看到的仍是乱码。
    import sys as _sys
    for _stream in (_sys.stdout, _sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

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
# ---- 折行：收尾标点不落行首、末行不留孤字 ------------------------------------------
# 同类毛病在法律关系图大师的真实运行里出现过（图上「…某某大酒 / 店」与「协议 / 》」），
# 这里的 wrap_w 原来是纯贪心，两条都没有。只挪断点、不改字。
# 下面的宽度是在「去掉规则」的副本上实测会出问题的。
import sys as _sys8, os as _os8
_sys8.path.insert(0, _os8.path.join(_os8.path.dirname(_os8.path.abspath(__file__)), "..", "scripts"))
import geom as _geom8
_NO_START8 = "》）」』、。，；：？！%"
_h8, _o8 = [], []
for _t8 in ("本院认为，双方签署的《借款（垫款）协议》合法有效；",
            "被告某某公司返还垫款474600元，驳回其他诉讼请求。"):
    for _w8 in (90, 105, 110, 115, 130, 160):
        _L8 = _geom8.wrap_w(_t8, _w8, 13)
        _h8 += [x for x in _L8[1:] if x and x[0] in _NO_START8]
        if len(_L8) >= 2 and len(_L8[-1]) == 1:
            _o8.append(_L8[-1])
ck("W1", not _h8, f"折行后收尾标点不落行首（命中 {_h8[:3]}）")
ck("W2", not _o8, f"折行后末行不留孤字（命中 {_o8[:3]}）")

sys.exit(1 if errs else 0)
