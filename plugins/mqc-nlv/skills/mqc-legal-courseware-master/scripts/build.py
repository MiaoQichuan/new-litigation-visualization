#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""法律课件大师 · 命令行：不开界面，直接出 PPTX（给模型用，也给批量用）。

    python3 scripts/build.py <课件目录>                    读 <目录>/deck.json，导出到 <目录>/exports/<标题>.pptx
    python3 scripts/build.py <课件目录> -o out/课件.pptx
    python3 scripts/build.py <课件目录> --check            只检查每一页（图表守卫、字放不放得下、风格是否一致），不写文件
    python3 scripts/build.py <课件目录> --notes            导出时把图里每个元素的出处写进演讲者备注（V2 时间轴、V3 关系图、用逐件记录的 V6 图表）
    python3 scripts/build.py --new <课件目录> --title 标题  新建一个课件目录（含 deck.json 与 assets/）

退出码：0 成功；1 说明有错；2 有页面没准备好（--check 或导出时）；3 导出后回读没过。
"""
import argparse
import json
import os
import re
import sys

import paths  # noqa: F401
import deck as D
import export as E


def main(argv=None):
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="法律课件大师：课件说明 → 可编辑 PPTX")
    ap.add_argument("folder")
    ap.add_argument("-o", "--out")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--new", action="store_true")
    ap.add_argument("--title")
    ap.add_argument("--style", help="奇川风 / 歸藏风 / 律所名片里的律所风格名")
    ap.add_argument("--fonts", default="safe", choices=("safe", "master"))
    ap.add_argument("--notes", action="store_true", help="把图里每个元素的出处写进演讲者备注（只读原模块的溯源记录）")
    a = ap.parse_args(argv)
    folder = os.path.abspath(a.folder)
    path = os.path.join(folder, "deck.json")
    if a.new:
        if os.path.exists(path):
            print(f"已经有 {path}，不覆盖", file=sys.stderr)
            return 1
        os.makedirs(os.path.join(folder, "assets"), exist_ok=True)
        d = D.new_deck(a.title or os.path.basename(folder), a.style or "奇川风")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
        print(f"已新建：{path}\n把 V6 图表说明（.json）与 V1–V5 的图（.svg）放进 {os.path.join(folder, 'assets')}")
        here = os.path.dirname(os.path.abspath(__file__))
        q = lambda x: f'"{x}"' if (" " in x or not x.isascii()) else x      # noqa: E731
        print("下一步（照抄就能跑）：\n"
              f"  打开编辑器　python3 {q(os.path.join(here, 'studio.py'))} {q(folder)}\n"
              f"  逐页检查　　python3 {q(os.path.abspath(__file__))} {q(folder)} --check")
        return 0
    try:
        d = D.load(path)
    except (D.DeckError, ValueError, OSError) as e:
        print(f"课件说明有错：{e}", file=sys.stderr)
        return 1
    if a.style:
        d["style"] = a.style
        try:
            D.validate(d, folder)
        except D.DeckError as e:
            print(f"风格不能用：{e}", file=sys.stderr)
            return 1
    if a.check:
        bad = 0
        for i, (_, rep) in enumerate(D.compose_all(d, folder, {})):
            mods = sorted(d["slides"][i]["modules"], key=lambda m: (m["y"], m["x"]))
            lay = " + ".join(D.TYPES[m["type"]]["zh"] for m in mods) or "空页"
            flag = "不行" if rep["problems"] else "可以"
            print(f"第 {i + 1:>2} 页 · {lay}　{flag}")
            for p in rep["problems"]:
                print(f"    不行　{p}")
                bad += 1
            for w in rep["warnings"]:
                print(f"    请核　{w}")
        return 2 if bad else 0
    safe = re.sub(r'[\\/:*?"<>|]+', "_", d.get("title") or "课件")[:60]
    out = a.out or os.path.join(folder, "exports", safe + ".pptx")
    try:
        p, rep = E.build(d, folder, out, fonts=a.fonts, cache={}, notes=a.notes)
    except E.ExportError as e:
        msg = str(e)                        # 消息里本来就说了「未导出」的不再加前缀（原来印成「未导出：…，未导出：」）
        print(msg if msg.startswith("未导出") or "未导出" in msg.split("\n")[0] else f"未导出：{msg}", file=sys.stderr)
        return 3 if "回读" in str(e) else 2
    print(f"已导出 {rep['slides']} 页：{p}")
    if a.notes:
        print(f"演讲者备注：{rep['notes']} 页写了出处" if rep["notes"] else "演讲者备注：这套课件的图都没有逐项出处，没有写备注")
    for w in rep["warnings"]:
        print(f"请核　{w}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
