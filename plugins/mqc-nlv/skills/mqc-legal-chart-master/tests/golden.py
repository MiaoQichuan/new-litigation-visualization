#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""防改差 · 金标准账本。

改 V6 最怕的不是新功能没做好，而是**修一处、坏一处**：为了拦一种错写法，把正常写法也拦了；
改了排版，某张图悄悄变了样。这个脚本把「现在的行为」记成账，任何变化都要**明说、记理由**才能过。

两本账（都在 tests/golden/）：

  verdicts.jsonl   判定账：每一行是一个标题 / 批注，以及它该过（accept）还是该拒（reject）。
                   来源：全部示例原标题 + 三轮外部测试 + 每次修复的正反例。**只增不删。**
  outputs.json     成品账：每份示例 × 两种风格 × 每种画布的 SVG 指纹（SHA-256），整页画布另记 PPTX 指纹。

用法：
  python3 tests/golden.py                      核对；有任何变化就列出来、退出码 1
  python3 tests/golden.py --update --reason "为什么变"
                                               确认变化是有意的：重写成品账，并把「哪些变了、为什么」
                                               追加到 tests/golden/CHANGES.md。判定账不能用 --update 改：
                                               判定变了说明规则变了，要手改 verdicts.jsonl 并在 CHANGES.md 写明
"""
import argparse
import base64
import copy
import datetime
import hashlib
import json
import os
import sys

# 中文 Windows 默认 GBK：不固定成 UTF-8，打印 −、✓ 这类 GBK 没有的字会崩（GBK 模拟环境里实测过）
for _s in (sys.stdout, sys.stderr):
    getattr(_s, "reconfigure", lambda **k: None)(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
GOLD = os.path.join(HERE, "golden")
EX = os.path.join(ROOT, "examples")
EXT = os.path.join(HERE, "fixtures", "external")

import make                       # noqa: E402
from spec import SpecError, CANVAS  # noqa: E402

STYLES = ("奇川风", "歸藏风")


def _load_base(name):
    p = os.path.join(EXT, name.split("/", 1)[1] + ".json") if name.startswith("external/") else os.path.join(EX, name + ".json")
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def verdict_of(row):
    m = _load_base(row["base"])
    if row.get("title") is not None:
        m["title"] = row["title"]
    if "annotations" in row:
        m["annotations"] = copy.deepcopy(row["annotations"])
    for k, v in (row.get("mutate") or {}).items():
        obj = m
        keys = k.split(".")
        for kk in keys[:-1]:
            obj = obj[kk]
        obj[keys[-1]] = copy.deepcopy(v)
    try:
        _, rep = make.build(m)
        return ("reject", "守卫：" + rep["problems"][0]) if rep["problems"] else ("accept", "")
    except (SpecError, ValueError) as e:
        return "reject", str(e).split("\n")[0][:120]


def check_verdicts():
    bad = []
    rows = [json.loads(l) for l in open(os.path.join(GOLD, "verdicts.jsonl"), encoding="utf-8") if l.strip()]
    for r in rows:
        got, why = verdict_of(r)
        if got != r["expect"]:
            bad.append(f"{r['id']}（{r['why']}）：「{r.get('title') or r.get('annotations')}」"
                       f"应{('过' if r['expect'] == 'accept' else '拒')}，现在{('过' if got == 'accept' else '拒')}"
                       + (f"——{why}" if why else ""))
    return rows, bad


def _fp(h):
    """指纹用 base32（字母 + 2–7）：十六进制指纹里偶尔会冒出 11 位连续数字，被时间轴大师的脱敏检查当成手机号。"""
    return base64.b32encode(h.digest()).decode("ascii").lower()[:24]


def _pptx_hash(svg):
    import tempfile
    import export_pptx
    with tempfile.TemporaryDirectory() as td:
        ready, alpha = make.pptx_ready(svg)
        sp, pp = os.path.join(td, "d.svg"), os.path.join(td, "d.pptx")
        with open(sp, "w", encoding="utf-8") as f:
            f.write(ready)
        export_pptx.export(sp, pp, fonts="safe")
        make.apply_alpha(pp, alpha)
        # 指纹按 ZIP 里每个部件解压后的内容算，不按压缩后的字节：不同平台的 zlib 压出来的字节可以不同
        import zipfile
        h = hashlib.sha256()
        with zipfile.ZipFile(pp) as z:
            for n in sorted(z.namelist()):
                h.update(n.encode("utf-8"))
                h.update(z.read(n))
        return _fp(h)


def snapshot():
    out = {}
    names = sorted(f[:-5] for f in os.listdir(EX) if f.endswith(".json"))
    for n in names:
        for st in STYLES:
            for cv in CANVAS:
                key = f"{n}|{st}|{cv}"
                try:
                    svg, rep = make.build(os.path.join(EX, n + ".json"), st, None, cv)
                    out[key] = _fp(hashlib.sha256(svg.encode("utf-8"))) if not rep["problems"] \
                        else "守卫：" + rep["problems"][0][:60]
                    if cv == "slide" and not rep["problems"]:
                        out[key + "|pptx"] = _pptx_hash(svg)
                except (SpecError, ValueError) as e:
                    out[key] = "拒：" + str(e)[:60]
    return out


def check_outputs():
    path = os.path.join(GOLD, "outputs.json")
    now = snapshot()
    if not os.path.exists(path):
        return now, [f"{k}：（无账）→ {v}" for k, v in sorted(now.items())]
    old = json.load(open(path, encoding="utf-8"))
    bad = []
    for k in sorted(set(old) | set(now)):
        if old.get(k) != now.get(k):
            bad.append(f"{k}：{old.get(k, '（无）')} → {now.get(k, '（无）')}")
    return now, bad


def main(argv=None):
    ap = argparse.ArgumentParser(description="防改差：金标准账本")
    ap.add_argument("--update", action="store_true")
    ap.add_argument("--reason")
    a = ap.parse_args(argv)
    rows, vbad = check_verdicts()
    now, obad = check_outputs()
    print(f"判定账：{len(rows)} 条，{len(rows) - len(vbad)} 条与账一致")
    for b in vbad:
        print("  判定变了  " + b)
    print(f"成品账：{len(now)} 份，{len(now) - len(obad)} 份与账一致")
    for b in obad[:40]:
        print("  成品变了  " + b)
    if len(obad) > 40:
        print(f"  ……另有 {len(obad) - 40} 份")
    if a.update:
        if vbad:
            print("判定账有变化，不能用 --update 盖过去：先弄清是规则改坏了，还是账要改（手改 verdicts.jsonl 并写 CHANGES.md）",
                  file=sys.stderr)
            return 1
        if not a.reason:
            print("--update 要写 --reason：为什么这些成品变了", file=sys.stderr)
            return 1
        with open(os.path.join(GOLD, "outputs.json"), "w", encoding="utf-8") as f:
            json.dump(now, f, ensure_ascii=False, indent=0, sort_keys=True)
        with open(os.path.join(GOLD, "CHANGES.md"), "a", encoding="utf-8") as f:
            f.write(f"\n## {datetime.date.today().isoformat()} · 成品账更新（{len(obad)} 份变化）\n\n理由：{a.reason}\n\n")
            for b in obad[:200]:
                f.write(f"- {b.split('：', 1)[0]}\n")     # 只记哪一份变了，不记指纹本身（指纹在 outputs.json）
        print(f"成品账已更新，{len(obad)} 份变化与理由记入 tests/golden/CHANGES.md")
        return 0
    return 1 if (vbad or obad) else 0


if __name__ == "__main__":
    sys.exit(main())
