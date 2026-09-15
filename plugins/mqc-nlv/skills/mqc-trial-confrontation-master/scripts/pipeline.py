#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""庭审对抗图大师 · 执行管线
  1 摄入     ingest.py         探测 → 文字型直读 / 扫描件栅格化待读图
  2 推演     （模型）按九步法填 case.json，三标随行 —— 唯一一步由模型做
  3 前端校验  check_claims.py   诉请固定（J）与抗辩归类（K）
  4 出表     build_matrix.py   → 庭审对抗分析表.xlsx
  5 出图     to_figure.py → render_main.py  → SVG（图从表派生）
  6 光栅     rasterize.py      → PNG（换单一字族，避开静默的字体回退）
  7 自检     cross_check.py 图表一致 + check_figure.py 图几何
一份输入同时喂表与图；缺顶层 title/subtitle 时渲染器回落到 case 段。
"""
import json, os, subprocess, sys
HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.dirname(HERE)

def step(n,name): print(f"\n[{n}] {name}")

def main(case, outdir="out"):
    os.makedirs(outdir, exist_ok=True)
    D=json.load(open(case,encoding="utf-8"))
    S=lambda *a: subprocess.run(list(a), check=True)

    step(1,"摄入")
    mats=D.get("materials")
    if mats:
        img=[m for m in mats if m.get("medium")=="image"]
        print(f"    材料 {len(mats)} 份，其中读图 {len(img)} 份")
        rec=D.get("reconcile")
        if rec:
            print(f"    对账：声明 {rec['pages_declared']} 页，读 {rec['pages_read']} 页，未读 {rec['unreadable']} 页")
            miss=rec.get("pending_materials") or rec.get("unreadable_materials") or []
            if rec.get("waived"):
                print(f"    律师明示不读：{rec['waived']}（{rec.get('waived_pages',0)} 页，不进推演）")
            if rec["unreadable"] or miss:
                print(f"    拒绝出图：完备性对账不平（未读页 {rec['unreadable']}，"
                      f"待读材料 {miss}）。材料本来就没有的，写进 scope.not_obtained；"
                      f"有但决定不读的，写进 waived——不许把它当成已读。"); return 1
    else:
        print("    本输入未带材料清单（材料由 scripts/ingest.py 先行处理）")

    step(2,"推演（模型已完成，本步只清点）")
    ne=sum(len(cb["elements"]) for p in D["parts"] for cb in p["claim_bases"])
    print(f"    对抗部分 {len(D['parts'])} 个，构成要件 {ne} 条，诉请 {len(D.get('claims',[]))} 项")

    step(3,"前端校验")
    if subprocess.run([sys.executable, os.path.join(HERE,"check_claims.py"), case]).returncode:
        print("    拒绝出表：诉请固定或抗辩归类不合规"); return 1

    step(4,"出表")
    xls=os.path.join(outdir,"庭审对抗分析表.xlsx")
    S(sys.executable, os.path.join(HERE,"build_matrix.py"), case, xls)

    step(5,"出图")
    fig=os.path.join(outdir,"图输入.json")     # 产出目录里不留英文名
    S(sys.executable, os.path.join(HERE,"to_figure.py"), case, fig)   # 表→图，表是唯一的源
    svg=os.path.join(outdir,"庭审对抗图.svg")
    S(sys.executable, os.path.join(HERE,"render_main.py"), fig, svg)

    step(6,"光栅")
    png=os.path.join(outdir,"庭审对抗图.png")
    S(sys.executable, os.path.join(HERE,"rasterize.py"), svg, png)

    step(7,"自检")
    xc = os.path.join(os.path.dirname(HERE), "tests", "cross_check.py")
    if os.path.exists(xc) and subprocess.run([sys.executable, xc, case, svg]).returncode:
        print("    拒绝交付：图表一致性未通过"); return 1
    if subprocess.run([sys.executable, os.path.join(HERE,"check_figure.py"), svg]).returncode:
        print("    拒绝交付：图几何自检未通过"); return 1

    print(f"\n完成：{xls}\n      {svg}\n      {png}")
    return 0

if __name__=="__main__":
    sys.exit(main(sys.argv[1], sys.argv[2] if len(sys.argv)>2 else "out"))
