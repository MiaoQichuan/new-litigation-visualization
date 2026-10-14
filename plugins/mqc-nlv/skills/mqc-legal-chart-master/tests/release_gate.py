#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""防改差 · 发版闸门。改完 V6、要发版之前跑这一个；任何一项不过，不发。

  1. 回归            tests/run_checks.py 全过
  2. 判定账与成品账  tests/golden.py：已知该过的还过、该拒的还拒；图一个像素都没悄悄变
  3. 变形测试        tests/metamorphic.py：几百个自动造的对错标题，两边都不能错
  4. 设计令牌        module.py tokens --check：给 V7 的令牌与代码一致
  5. 版本一致        SKILL.md、CHANGELOG、令牌里的版本号一致
  6. 单独安装包      打包 → 空目录解开 → 在包里再跑一遍回归
  7. 全插件脱敏      借时间轴大师（V2）的脱敏守卫扫整个插件：V6 的文字（场景库、示例、变更记录）不能让别的模块变红
                    ——0.9.4 之前 V6 一直让 V2 的回归红着，V6 自己的回归不扫整个仓库，所以没看见
  8. 只增不减        回归项数、判定账条数、变形测试条数都不能比上次发版少（tests/golden/gate.json）；
                    上次发版有的每一项检查（按名字，tests/golden/check-names.json）这次都还在
                    ——删测试来「通过」是最隐蔽的改差，这一条专门防它。全过后自动把下限抬到本次的数。

    python3 tests/release_gate.py
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

# 中文 Windows 默认 GBK：不固定成 UTF-8，打印 −、✓ 这类 GBK 没有的字会崩（GBK 模拟环境里实测过）
for _s in (sys.stdout, sys.stderr):
    getattr(_s, "reconfigure", lambda **k: None)(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
GATE = os.path.join(HERE, "golden", "gate.json")
NAMES = os.path.join(HERE, "golden", "check-names.json")


def check_names(out):
    """回归输出里每一项检查的名字（数字归一成 #：「判定账 66 条」与「判定账 67 条」是同一项）。"""
    return sorted({re.sub(r"\d+(?:\.\d+)?", "#", l[8:].split("  →")[0].strip())
                   for l in out.splitlines() if l.startswith(("  OK    ", "  FAIL  "))})


def vanished(names, kept):
    """上次发版有、这次没有的检查。只看条数会放过「删一项、加一项」——0.9.8 自检时真的发生过：
    重写一节检查时误删了另一节，条数不变，闸门照样过。"""
    return sorted(set(kept) - set(names))
PY = sys.executable


def run(args, cwd=None):
    # 子进程一律按 UTF-8 输出、按 UTF-8 读：中文 Windows 默认 GBK，两头不一致就解码报错（GBK 模拟环境里实测过）
    r = subprocess.run([PY] + args, capture_output=True, text=True, cwd=cwd, encoding="utf-8",
                       env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    return r.returncode, r.stdout + r.stderr


def version_of(text, pat):
    m = re.search(pat, text, re.M)
    return m.group(1).strip() if m else None


def main():
    rows, counts = [], {}

    rc, out = run([os.path.join(HERE, "run_checks.py")])
    m = re.search(r"(\d+)/(\d+) 项通过", out)
    counts["checks"] = int(m.group(2)) if m else 0
    names = check_names(out)
    rows.append(("回归", rc == 0, m.group(0) if m else out[-300:]))

    rc, out = run([os.path.join(HERE, "golden.py")])
    mv = re.search(r"判定账：(\d+) 条", out)
    counts["verdicts"] = int(mv.group(1)) if mv else 0
    rows.append(("判定账与成品账", rc == 0, " / ".join(l.strip() for l in out.splitlines()[:2]) if rc == 0 else out[-600:]))

    rc, out = run([os.path.join(HERE, "metamorphic.py")])
    mm = re.search(r"变形测试：(\d+) 条", out)
    counts["metamorphic"] = int(mm.group(1)) if mm else 0
    rows.append(("变形测试", rc == 0, out.strip().splitlines()[0] if rc == 0 else out[-600:]))

    rc, out = run([os.path.join(ROOT, "scripts", "module.py"), "tokens", "--check"])
    rows.append(("设计令牌", rc == 0, out.strip()))

    skill = open(os.path.join(ROOT, "SKILL.md"), encoding="utf-8").read()
    log = open(os.path.join(ROOT, "CHANGELOG.md"), encoding="utf-8").read()
    tok = json.load(open(os.path.join(ROOT, "design", "tokens.json"), encoding="utf-8"))
    vs = {"SKILL.md": version_of(skill, r"^\s*version:\s*(\S+)"), "CHANGELOG": version_of(log, r"^## (\S+)"),
          "tokens.json": tok.get("version")}
    rows.append(("版本一致", len(set(vs.values())) == 1, "、".join(f"{k} {v}" for k, v in vs.items())))

    td = tempfile.mkdtemp()
    rc, out = run([os.path.join(ROOT, "scripts", "pack_standalone.py"), "-o", td])
    if rc == 0:
        z = [f for f in os.listdir(td) if f.endswith(".zip")][0]
        with zipfile.ZipFile(os.path.join(td, z)) as zf:
            zf.extractall(os.path.join(td, "x"))
        rc2, out2 = run([os.path.join(td, "x", "mqc-legal-chart-master", "tests", "run_checks.py")])
        m2 = re.search(r"(\d+)/(\d+) 项通过", out2)
        rows.append(("单独安装包", rc2 == 0, f"{z}；包内回归 {m2.group(0) if m2 else out2[-300:]}"))
    else:
        rows.append(("单独安装包", False, out[-400:]))
    shutil.rmtree(td, ignore_errors=True)

    anon = os.path.normpath(os.path.join(ROOT, "..", "mqc-timeline-master", "tests", "check_anonymised.py"))
    if os.path.exists(anon):
        plugin = os.path.normpath(os.path.join(ROOT, "..", ".."))
        rc, out = run([anon, plugin])
        last = out.strip().splitlines()[-1] if out.strip() else ""
        leaks = [l.strip() for l in out.splitlines() if "mqc-legal-chart-master" in l and "略过" not in l]
        rows.append(("全插件脱敏", rc == 0, last if rc == 0 else "；".join(leaks[:5]) or out[-400:]))
    else:
        rows.append(("全插件脱敏", True, "不在完整仓库里（没有时间轴大师的守卫），跳过"))

    floor = json.load(open(GATE, encoding="utf-8")) if os.path.exists(GATE) else {}
    shrink = [f"{k} {counts.get(k, 0)} < 上次 {v}" for k, v in floor.items() if counts.get(k, 0) < v]
    kept = json.load(open(NAMES, encoding="utf-8")) if os.path.exists(NAMES) else []
    gone = vanished(names, kept)
    if gone:
        shrink.append(f"这些检查不见了（{len(gone)} 项）：{'；'.join(gone[:3])}"
                      f"——确是有意改名或合并，手改 tests/golden/check-names.json 并在 CHANGES.md 写明理由")
    rows.append(("只增不减", not shrink, "；".join(shrink) or "、".join(f"{k} {v}" for k, v in counts.items())))

    print("发版闸门")
    for name, good, why in rows:
        print(f"  {'过' if good else '不过'}　{name}　{why}")
    ok = all(g for _, g, _ in rows)
    if ok:
        union = sorted(set(kept) | set(names))
        if union != kept:
            with open(NAMES, "w", encoding="utf-8") as f:
                json.dump(union, f, ensure_ascii=False, indent=0)
            print(f"  检查名单记到本次：{len(union)} 项")
        new = {k: max(v, floor.get(k, 0)) for k, v in counts.items()}
        if new != floor:
            with open(GATE, "w", encoding="utf-8") as f:
                json.dump(new, f, ensure_ascii=False, indent=1)
            print(f"  下限抬到本次：{new}")
        print("全过，可以发版。")
        return 0
    print("有不过的，不发版。", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
