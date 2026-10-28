#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""命令行边界：没给参数、骨架不全、PNG 出不来时，说人话、不甩堆栈、不连累 Excel 与 SVG。
每一项都真跑一次 pipeline.py，看退出码与输出，不只看函数返回值。"""
import json, os, subprocess, sys, tempfile, copy, shutil

if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")
        except Exception:
            pass
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
PIPE = os.path.join(ROOT, "scripts", "pipeline.py")
EX = os.path.join(ROOT, "examples", "matrix-input.json")
TMP = tempfile.mkdtemp(prefix="v5cli_")
ENV = dict(os.environ, PYTHONIOENCODING="utf-8")
ENV.pop("NLV_DEBUG", None)
fails = 0


def ck(code, ok, msg):
    global fails
    print(f"  {'OK  ' if ok else 'FAIL'} {code}  {msg}")
    fails += 0 if ok else 1


def run(*args, env=None):
    r = subprocess.run([sys.executable, PIPE, *args], cwd=TMP, capture_output=True, env=env or ENV)
    return r.returncode, (r.stdout + r.stderr).decode("utf-8", "replace")


def dump(name, obj):
    p = os.path.join(TMP, name)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    return p


BASE = json.load(open(EX, encoding="utf-8"))

rc, out = run()
ck("U1", rc == 2 and "用法" in out and "Traceback" not in out, "不给参数：打印用法、退出码 2，不甩 IndexError")

rc, out = run("--check")
ck("U2", rc == 0 and "分析表 Excel" in out and "对抗图 PNG" in out, "--check 只查环境，逐项说出表、出图、出 PNG")

rc, out = run(dump("empty.json", {}), os.path.join(TMP, "o1"))
ck("U3", rc == 1 and "缺 case 段" in out and "缺 parts" in out and "Traceback" not in out,
   "空对象：一次说全缺什么，指到骨架，不甩 KeyError")
ck("U3b", not os.path.exists(os.path.join(TMP, "o1")), "骨架不全时不建输出目录（不留空文件夹）")

rc, out = run(dump("arr.json", [1, 2]), os.path.join(TMP, "o2"))
ck("U4", rc == 1 and "最外层应是一个对象" in out and "Traceback" not in out, "最外层是数组：说清要对象")

d = copy.deepcopy(BASE)
del d["parts"][0]["claim_bases"][0]["elements"][0]["name"]
del d["parts"][1]["claim_bases"][0]["elements"][0]["evidence"]
rc, out = run(dump("miss.json", d), os.path.join(TMP, "o3"))
ck("U5", rc == 1 and "P1-1 缺字段：name" in out and "缺字段：evidence" in out and "Traceback" not in out,
   "要件缺字段：逐条点名哪条要件缺哪个字段，原来跑到出表才甩 KeyError")

d = copy.deepcopy(BASE)
d["parts"][0]["claim_bases"][0]["elements"] = []
rc, out = run(dump("noel.json", d), os.path.join(TMP, "o4"))
ck("U6", rc == 1 and "缺 elements" in out, "请求权基础下没有要件：拒绝并说明")

rc, out = run("--demo", os.path.join(TMP, "demo"), "2")
ck("U7", rc == 0 and os.path.exists(os.path.join(TMP, "demo", "庭审对抗图.svg"))
   and not os.path.exists(os.path.join(TMP, "demo", "庭审对抗分析表.xlsx")),
   "--demo 用随包示例一条命令跑通；末尾写 2 只出 SVG")

# PNG 出不来（模拟缺 Pillow）：Excel 与 SVG 照常交付，退出码 0，说明 PNG 没出
fake = os.path.join(TMP, "fake", "PIL")
os.makedirs(fake, exist_ok=True)
with open(os.path.join(fake, "__init__.py"), "w", encoding="utf-8") as f:
    f.write('raise ModuleNotFoundError("No module named PIL", name="PIL")\n')
env = dict(ENV, PYTHONPATH=os.path.join(TMP, "fake"))
rc, out = run(EX, os.path.join(TMP, "o5"), "全部", env=env)
ok_files = all(os.path.exists(os.path.join(TMP, "o5", n)) for n in ("庭审对抗分析表.xlsx", "庭审对抗图.svg"))
ck("U8", rc == 0 and ok_files and "PNG 没出成" in out and "CalledProcessError" not in out,
   "PNG 出不来时不连累 Excel 与 SVG，也不甩 CalledProcessError")

shutil.rmtree(TMP, ignore_errors=True)
print("\n" + ("全部通过" if not fails else f"{fails} 项未通过"))
sys.exit(1 if fails else 0)
