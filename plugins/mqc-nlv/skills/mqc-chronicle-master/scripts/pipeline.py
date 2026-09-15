#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""大事记表大师 · 执行管线
黄金律：模型读懂意思，代码算和验。模型只在第二步出 JSON，其余全部确定性。

  1 摄入   ingest.py          探测 → 文字型直读 / 扫描件栅格化
  2 抽取   （模型）           照 references/extraction.md 的 A-E 出事实行
  3 校验   check_facts.py     任何一条判据不成立即拒绝出表
  4 渲染   to_render.py       底稿 → Word 交付版 + Excel 母表
  5 自检   交付物自检          列宽、字体、对齐、备注上限
"""
import json, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

def step(n, name): print(f"\n[{n}] {name}")

def main(casefile, sources=None, outdir="out"):
    os.makedirs(outdir, exist_ok=True)
    cf = json.load(open(casefile, encoding="utf-8"))

    step(1, "摄入")
    mats = cf["materials"]; rec = cf["reconcile"]
    img = [m for m in mats if m.get("medium") == "image"]
    print(f"    材料 {len(mats)} 份，其中读图 {len(img)} 份")
    print(f"    对账：声明 {rec['pages_declared']} 页，读 {rec['pages_read']} 页，"
          f"未读 {rec['unreadable']} 页；外部锚：{rec['external_anchor']}")
    if rec["unreadable"]:
        print("    拒绝出表：有未读页，完备性对账不平"); return 1

    step(2, "抽取（模型已完成，本步只清点）")
    print(f"    事实 {len(cf['facts'])} 条，主体 {len(cf['parties'])} 个，"
          f"不确定 {len(cf.get('uncertainties', []))} 条")

    step(3, "校验")
    sys.path.insert(0, HERE)
    from check_facts import check
    src = json.load(open(sources, encoding="utf-8")) if sources else None
    if not src: print("    未提供源文本，B3 子序列核验跳过（扫描件须先出转写稿）")
    r = check(cf, src)
    if r.dump(): return 1

    step(4, "渲染（Word 交付版与 Excel 母表）")
    # 产出目录是律师直接打开的，文件名一律中文：他看到的是「案件大事记」，
    # 不是 chronicle.docx 这种。中间件也一样，混一个英文名在里面就显得是半成品。
    ri  = os.path.join(outdir, "渲染输入.json")
    raw = os.path.join(outdir, "案件大事记-未后处理.docx")
    doc = os.path.join(outdir, "案件大事记.docx")
    xls = os.path.join(outdir, "案件大事记母表.xlsx")
    S = lambda *a: subprocess.run(list(a), check=True)
    S(sys.executable, os.path.join(HERE, "to_render.py"), casefile, ri)
    S("node", os.path.join(HERE, "build_docx.js"), ri, raw)
    S(sys.executable, os.path.join(HERE, "postprocess_docx.py"), raw, doc)
    os.remove(raw)
    S(sys.executable, os.path.join(HERE, "build_xlsx.py"), ri, xls)
    S(sys.executable, os.path.join(HERE, "cache_formulas.py"), xls)

    step(5, "简表（呈报用）")
    sys.path.insert(0, HERE)
    from build_brief import build as build_brief
    from export_brief import export as export_brief
    svgs = build_brief(ri, outdir)      # 与 Word、Excel 同一份输入，结构才不会漂
    ex = export_brief(svgs, outdir) if svgs else {"merged": None, "pdf": []}

    step(6, "交付物自检")
    r = subprocess.run([sys.executable,
                        os.path.join(ROOT, "tests", "check_deliverables.py"), doc, xls, ri])
    if r.returncode: print("    拒绝交付：交付物自检未通过"); return 1
    r = subprocess.run([sys.executable,
                        os.path.join(ROOT, "tests", "brief_checks.py"), ri])
    if r.returncode: print("    拒绝交付：简表自检未通过"); return 1

    brief = (ex.get("merged") or (ex["pdf"][0] if ex.get("pdf") else None)
             or (svgs[0] if svgs else "（无事实，未出简表）"))
    print(f"\n完成：{doc}\n      {xls}\n      {ri}\n      {brief}")
    return 0

if __name__ == "__main__":
    a = sys.argv[1:]
    sys.exit(main(a[0], a[1] if len(a) > 1 else None, a[2] if len(a) > 2 else "out"))
