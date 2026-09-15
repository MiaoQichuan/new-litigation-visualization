# -*- coding: utf-8 -*-
"""布局回归：17 个 6 到 9 主体的案例，与改动前的原版逐例对比。

    python tests/layout_regression.py

基线是原版 lookup.run 的结果（判据是否通过、交叉、拐弯），
存在 tests/fixtures/layout-baseline.json。任何一例比基线差即判失败：
先比判据（过优于未过），再比交叉，再比拐弯。耗时只报告，不判。
约需一分半到两分钟。
"""
import os, sys, json, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import lookup
from mini_render import render as mr

cases = json.load(open(os.path.join(HERE, "fixtures", "layout-baseline.json"), encoding="utf-8"))
worse, better, t_old, t_new = [], 0, 0.0, 0.0
for c in cases:
    t = time.time()
    r = lookup.run(c["nodes"], [tuple(e) for e in c["edges"]], render=mr)
    dt = time.time() - t
    ok = bool(r[-1].get("guard", {}).get("ok"))
    b = c["baseline"]
    kb, kn = (0 if b["ok"] else 1, b["C"], b["B"]), (0 if ok else 1, r[0][0], r[0][1])
    v = "更好" if kn < kb else ("相同" if kn == kb else "更差")
    better += v == "更好"
    if v == "更差":
        worse.append(c["case"])
    t_old += b["t"]; t_new += dt
    print(f"  {'FAIL' if v == '更差' else 'OK  '} {c['case']:<10} 基线 交{b['C']} 拐{b['B']} "
          f"{'过' if b['ok'] else '未过'}　现在 交{r[0][0]} 拐{r[0][1]} {'过' if ok else '未过'} "
          f"{dt:.1f}s　{v}")
print(f"更好 {better} 例，更差 {len(worse)} 例；耗时 基线 {t_old:.0f}s，现在 {t_new:.0f}s（不同机器不可比）")
sys.exit(1 if worse else 0)
