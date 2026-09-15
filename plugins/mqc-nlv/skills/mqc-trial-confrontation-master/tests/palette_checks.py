#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""配色：全套只许有一个红。
图（SVG）与表（Excel）各自维护过一份，一个 #991B1B、一个 #9E2A2B，肉眼分不出，
但强调色不统一，图表摆在一起就露。这一条扫源码里所有颜色字面量，
凡红系必须是同一个值——新引入的第二个红当场报出来，不靠人记。"""
import os, re, sys
import tempfile as _tempfile
_TMP = _tempfile.gettempdir()   # 不写死 /tmp：Windows 上没有这个目录，自检一跑就找不到文件
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
RED = "991B1B"
HEX = re.compile(r'(?:#|["\'])([0-9A-Fa-f]{6}|[0-9A-Fa-f]{8})(?=["\'\s,)\]]|$)')

def is_red(h):
    """红系：R 显著高于 G 与 B。不按色名、不按变量名——改名就绕过去了。"""
    h = h[-6:]
    r, g, b = (int(h[i:i+2], 16) for i in (0, 2, 4))
    return r > g + 40 and r > b + 40

def scan(text):
    return {m.group(1)[-6:].upper() for m in HEX.finditer(text) if is_red(m.group(1))}

errs = []
def ck(no, cond, msg):
    print(("  OK  " if cond else "  FAIL") + f" {no}  {msg}")
    if not cond: errs.append(no)

found, where = set(), {}
for d in ("scripts", "tests"):
    for fn in sorted(os.listdir(os.path.join(ROOT, d))):
        # 本文件自身带着假红作改坏验证，排除；其余测试照扫
        if not fn.endswith(".py") or fn == os.path.basename(__file__): continue
        p = os.path.join(ROOT, d, fn)
        for h in scan(open(p, encoding="utf-8").read()):
            found.add(h); where.setdefault(h, []).append(f"{d}/{fn}")

ck("C1", found == {RED}, f"源码里的红只有 {RED} 一个（实为 {sorted(found)}）")
if found - {RED}:
    for h in sorted(found - {RED}):
        print(f"       多出的红 {h} 出现在 {where[h]}")

ck("C2", is_red("9E2A2B") and is_red("FF991B1B") and not is_red("4B5563"),
   "红系判定按 RGB 分量算，不按变量名——改名绕不过去")
ck("C3", scan('RED="#8C1C1C"; INK="#1F2933"') == {"8C1C1C"},
   "混进第二个红会被当场抓出（自检自身的改坏验证）")

# C4 母表的红用量：读回产物数，不数源码写了几次
import io, contextlib, json
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import build_matrix as BM
with contextlib.redirect_stdout(io.StringIO()):
    BM.build(os.path.join(ROOT, "examples/matrix-input.json"), os.path.join(_TMP, "_pal.xlsx"))
hot = BM._count_red(os.path.join(_TMP, "_pal.xlsx"))
ck("C4", hot <= BM.MAX_RED, f"母表深红 {hot} 处，上限 {BM.MAX_RED}（只标决定性要件的编号）")

put0 = BM.put
def put_red(ws, r, c, v, **kw):                        # 把红拿去做列头装饰
    if kw.get("bold"): kw["color"] = BM.RED      # 列头行号随诉请条数浮动，不钉死行号
    return put0(ws, r, c, v, **kw)
BM.put = put_red
try:
    with contextlib.redirect_stdout(io.StringIO()):
        BM.build(os.path.join(ROOT, "examples/matrix-input.json"), os.path.join(_TMP, "_pal2.xlsx"))
    caught = False
except AssertionError:
    caught = True
finally:
    BM.put = put0
ck("C5", caught, "拿红做列头装饰会被出表期自证拦下")

# C6 交付面不得漏出数据结构（自证在出表期已拦，这里只做回归）
ck("C6", not BM._leaked_literals(os.path.join(_TMP, "_pal.xlsx")),
   "母表里没有 Python 字面量（对象须渲染成中文再写入）")

print()
print("  全部通过" if not errs else f"  未通过：{sorted(set(errs))}")
sys.exit(1 if errs else 0)
