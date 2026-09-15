#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全量自检入口。任何一节失败即整体失败。"""
import subprocess, sys, os, json
HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.dirname(HERE)
def run(title, cmd, cwd=ROOT):
    print(f"\n===== {title} =====")
    r=subprocess.run(cmd, cwd=cwd)
    return r.returncode
fails=0
fails+= run("摄入分派与完备性对账", [sys.executable, "tests/ingest_checks.py"])
fails+= run("改坏验证", [sys.executable, "tests/break_tests.py"])   # 项数由脚本自己报，别写死
fails+= run("样例底稿校验", [sys.executable, "scripts/check_facts.py", "tests/casefile.json"])
fails+= run("样例 · 文字型", [sys.executable, "scripts/check_facts.py", "examples/case-text-layer.json"])
fails+= run("样例 · 扫描件（含 B3 子序列核验）", [sys.executable, "scripts/check_facts.py",
            "examples/case-scanned.json", "examples/case-scanned-transcript.json"])
for _f in ["tests/casefile.json","examples/case-text-layer.json","examples/case-scanned.json"]:
    fails+= run(f"结构校验 {_f}", [sys.executable, "scripts/check_schema.py", _f])
import tempfile as _tf
for _f in ["tests/casefile.json","examples/case-text-layer.json"]:
    fails+= run(f"渲染层 {_f}", [sys.executable, "tests/render_checks.py", _f])
for _f in ["tests/casefile.json","examples/case-text-layer.json"]:
    _ri=os.path.join(_tf.mkdtemp(),"ri.json")
    subprocess.run([sys.executable,"scripts/to_render.py",_f,_ri],cwd=ROOT,capture_output=True)
    fails+= run(f"简表 {_f}", [sys.executable, "tests/brief_checks.py", _ri])
# 端到端跑一次示例：出表那一层（build_xlsx / build_docx）原先没有日常覆盖，
# X 组判据只在 pipeline 里执行，把母表的主体列、证据状态、序号公式改坏全都漏过。
_out = _tf.mkdtemp()
fails+= run("端到端（示例 · 含交付物自检）",
            [sys.executable, "scripts/pipeline.py", "tests/casefile.json", "", _out])

print("\n===== 规格一致性 =====")
V=json.load(open(os.path.join(ROOT,"references/verbs.json"),encoding="utf-8"))["verbs"]
B=json.load(open(os.path.join(ROOT,"references/ban.json"),encoding="utf-8"))["words"]
ok = len(V)==len(set(V)) and len(B)==len(set(B)) and not (set(V)&set(B))
print(("  OK  " if ok else "  FAIL")+f" 动词表 {len(V)} 个、定性词表 {len(B)} 个，无重复、无交集")
fails += 0 if ok else 1
print("\n" + ("全部通过" if not fails else f"{fails} 节未通过"))
sys.exit(1 if fails else 0)
