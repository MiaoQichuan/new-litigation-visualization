#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全量自检入口。任何一节失败即整体失败。"""
import subprocess, sys, os
import tempfile as _tempfile
_TMP = _tempfile.gettempdir()   # 不写死 /tmp：Windows 上没有这个目录，自检一跑就找不到文件
HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.dirname(HERE)
def run(title, cmd):
    print(f"\n===== {title} =====")
    return subprocess.run(cmd, cwd=ROOT).returncode
fails=0
fails+= run("管线（含摄入清点、前端校验、出表出图光栅、图自检）", [sys.executable,"scripts/pipeline.py","examples/matrix-input.json",os.path.join(_TMP, "_tcm_out")])
fails+= run("出表", [sys.executable,"scripts/build_matrix.py","examples/matrix-input.json",os.path.join(_TMP, "_m.xlsx")])
fails+= run("图几何自检", [sys.executable,"scripts/check_figure.py",os.path.join(_TMP, "_tcm_out", "庭审对抗图.svg")])
fails+= run("字段出口", [sys.executable,"tests/coverage_checks.py"])
fails+= run("配色", [sys.executable,"tests/palette_checks.py"])
fails+= run("编排结构", [sys.executable,"tests/shape_checks.py"])
fails+= run("摄入分派与完备性对账", [sys.executable,"tests/ingest_checks.py"])
fails+= run("诉请固定与抗辩归类", [sys.executable,"scripts/check_claims.py","examples/matrix-input.json"])
fails+= run("图表一致性", [sys.executable,"tests/cross_check.py"])
fails+= run("改坏验证", [sys.executable,"tests/break_tests.py"])
print("\n"+("全部通过" if not fails else f"{fails} 节未通过"))
sys.exit(1 if fails else 0)
