#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""渲染层判据：底稿 → 渲染输入，一个字都不许动。

to_render 是 Word 交付版、Excel 母表、大事记简表三件产物的共同上游，
它一错，三件一起错，而且错得不显眼——日期精度悄悄丢了、主要内容被截了、
证据状态被写死了，产物看上去仍然完整。

实测过：把这一层逐项改坏，全量自检六项全漏。原因是 X 组判据只在 pipeline
跑真案子时才执行，日常自检压根不碰这一层。这组判据就是来补这个洞的。
"""
import json, os, re, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

errs = []
def ck(no, cond, msg):
    print(("  OK  " if cond else "  FAIL") + f" {no}  {msg}")
    if not cond: errs.append(no)


def render(case):
    out = os.path.join(tempfile.mkdtemp(), "ri.json")
    r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "to_render.py"), case, out],
                       capture_output=True, text=True)
    if r.returncode:
        print(r.stdout + r.stderr)
        raise SystemExit(1)
    return json.load(open(out, encoding="utf-8"))


CERT = {"exact": "", "month": "（仅到月）", "year": "（仅到年）", "range": "至"}


def main(case):
    D = json.load(open(case, encoding="utf-8"))
    R = render(case)
    F, rows = D["facts"], R["rows"]

    ck("R1", len(rows) == len(F), f"事实条数不增不减（底稿 {len(F)} 条，渲染 {len(rows)} 条）")
    n = min(len(rows), len(F))

    bad = [F[i]["fid"] for i in range(n) if rows[i]["item"] != F[i]["item"]]
    ck("R2", not bad, f"事项标题逐字照搬，不加不减（不合 {bad[:3]}）")

    bad = [F[i]["fid"] for i in range(n) if rows[i]["content"] != F[i]["content"]]
    ck("R3", not bad, f"主要内容逐字照搬，渲染层不得截断或改写（不合 {bad[:3]}）")

    bad = [F[i]["fid"] for i in range(n)
           if rows[i]["evidence_status"] != F[i]["evidence_status"]]
    ck("R4", not bad, f"证据状态照底稿，渲染层不得另行判断（不合 {bad[:3]}）")

    # 证据状态本就由有无证据编号机械决定，这里再验一次它没被绕过
    bad = [f["fid"] for f in F
           if f["evidence_status"] != ("有书证" if f.get("evidence_no") else "仅当事人陈述")]
    ck("R5", not bad, f"证据状态与有无证据编号一致（不合 {bad[:3]}）")

    bad = []
    for i in range(n):
        mark = CERT[F[i]["date_certainty"]]
        if mark and mark not in rows[i]["date"]:
            bad.append((F[i]["fid"], F[i]["date_certainty"], rows[i]["date"]))
    ck("R6", not bad, f"四档日期精度都在交付面标出（不合 {bad[:2]}）")

    # 来源要有证据编号或材料名，光剩一个「（原告）」不算——
    # 判据写松了就会漏：实测把来源整个清空，末尾的提交方括号仍让它通过
    bad = [F[i]["fid"] for i in range(n)
           if not re.sub(r"（[^）]*）\s*$", "", str(rows[i].get("source", ""))).strip()]
    ck("R7", not bad, f"每行的来源都有证据编号或材料名，不是只剩提交方（不合 {bad[:3]}）")

    want = {f["fid"] for f in F if f.get("parties")}
    bad = [F[i]["fid"] for i in range(n)
           if F[i]["fid"] in want and not str(rows[i].get("parties", "")).strip()]
    ck("R8", not bad, f"底稿有主体的，交付面就要有主体（不合 {bad[:3]}）")

    # 一条事实可以有好几项说不准的东西，全都要带过去，不能只取第一条
    ids = [f["fid"] for f in F]
    multi = {}
    for u in D.get("uncertainties", []):
        if u.get("what") != "证据编号" and u.get("why"):
            multi.setdefault(u["fid"], []).append(u)
    bad = []
    for fid, us in multi.items():
        if fid not in ids: continue
        got = rows[ids.index(fid)].get("explain", "")
        miss = [u["what"] for u in us if u["what"] not in got]
        if miss: bad.append((fid, miss))
    ck("R9", not bad, f"同一事实的多项不确定说明全部带出（缺 {bad[:2]}）")

    print()
    print("  全部通过" if not errs else f"  未通过：{sorted(set(errs))}")
    return 1 if errs else 0


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "tests", "casefile.json")
    sys.exit(main(src))
