# -*- coding: utf-8 -*-
"""打一个能单独安装的法律图表大师包（外部测试 T041：只装 V6、旁边没有 V1 时找不到共享内核）。

    python3 scripts/pack_standalone.py [-o dist/]

做法：把本 skill 原样拷进去，再把它依赖的两个兄弟模块的 scripts/ 整个放进 vendor/：
  vendor/v1/scripts  ← mqc-litigation-visual-redraw（字宽、换行、PPTX 导出、转图）
  vendor/v4/scripts  ← mqc-chronicle-master（读判决书文件）
kernel.py 与 cases.py 本来就先找 vendor/，再找兄弟目录，所以不用改代码。
整个 scripts/ 一起带，不挑单个文件——只带一份 common.py 而漏了它 import 的东西，装上才发现缺。
vendor/VENDOR.json 记下来源、版本与每个文件的 SHA-256；共享内核仍只有一份源头（V1），包里的是拷贝。
打完在临时目录里解开，跑一遍环境自检和一张示例图，过了才算打好。
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
SKILLS = os.path.normpath(os.path.join(ROOT, ".."))
VENDORS = {"v1": "mqc-litigation-visual-redraw", "v4": "mqc-chronicle-master"}
# scripts/ 之外还要读的东西：V1 的 common.py 读 ../assets/style-tokens.json 与 ../schemas/
# （第一次打包就因为漏了它，在空目录里自检失败——所以打完一定要在空目录里验）
VENDOR_EXTRA = {"v1": ["assets/style-tokens.json", "schemas"], "v4": ["schemas"]}
SKIP_DIRS = {"__pycache__", "out", "dist", ".git", "vendor"}


def _version(skill_dir):
    p = os.path.join(skill_dir, "SKILL.md")
    for ln in open(p, encoding="utf-8-sig"):
        if ln.strip().startswith("version:"):
            return ln.split(":", 1)[1].strip()
    return "?"


def _files(top):
    for dp, dns, fns in os.walk(top):
        dns[:] = sorted(d for d in dns if d not in SKIP_DIRS and not d.startswith("."))
        for fn in sorted(fns):
            if fn.endswith(".pyc"):
                continue
            yield os.path.join(dp, fn)


def build(out_dir):
    name = "mqc-legal-chart-master"
    ver = _version(ROOT)
    os.makedirs(out_dir, exist_ok=True)
    zpath = os.path.join(out_dir, f"{name}-{ver}-standalone.zip")
    manifest = {"skill": name, "version": ver, "vendor": {}}
    entries = []
    for f in _files(ROOT):
        entries.append((f, os.path.join(name, os.path.relpath(f, ROOT))))
    for tag, mod in VENDORS.items():
        src = os.path.join(SKILLS, mod, "scripts")
        if not os.path.isdir(src):
            raise SystemExit(f"找不到 {mod}/scripts：请在完整仓库里打包")
        files = {}
        for f in _files(src):
            rel = os.path.relpath(f, src)
            files["scripts/" + rel] = hashlib.sha256(open(f, "rb").read()).hexdigest()
            entries.append((f, os.path.join(name, "vendor", tag, "scripts", rel)))
        for extra in VENDOR_EXTRA.get(tag, []):
            p = os.path.join(SKILLS, mod, extra)
            for f in ([p] if os.path.isfile(p) else list(_files(p)) if os.path.isdir(p) else []):
                rel = os.path.relpath(f, os.path.join(SKILLS, mod))
                files[rel] = hashlib.sha256(open(f, "rb").read()).hexdigest()
                entries.append((f, os.path.join(name, "vendor", tag, rel)))
        lic = os.path.join(SKILLS, "..", "..", "..", "LICENSE")
        manifest["vendor"][tag] = {"module": mod, "version": _version(os.path.join(SKILLS, mod)),
                                   "license": "MIT（与本仓库同一许可）", "files": files}
        if os.path.exists(lic):
            entries.append((lic, os.path.join(name, "vendor", tag, "LICENSE")))
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for src, arc in entries:
            z.write(src, arc)
        z.writestr(os.path.join(name, "vendor", "VENDOR.json"),
                   json.dumps(manifest, ensure_ascii=False, indent=1))
    return zpath


def verify(zpath):
    """在一个旁边什么都没有的临时目录里解开，自检 + 出一张图 + 读一份清单。"""
    td = tempfile.mkdtemp()
    try:
        with zipfile.ZipFile(zpath) as z:
            z.extractall(td)
        sk = os.path.join(td, "mqc-legal-chart-master")
        py = sys.executable
        r1 = subprocess.run([py, os.path.join(sk, "scripts", "make.py"), "--check"], capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
        r2 = subprocess.run([py, os.path.join(sk, "scripts", "make.py"), os.path.join(sk, "examples", "bar-filings.json"),
                             "-o", os.path.join(td, "o", "x")], capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
        csvp = os.path.join(td, "l.csv")
        with open(csvp, "w", encoding="utf-8") as f:
            f.write("案号,法院\n（2023）京01行终1号,北京市第一中级人民法院\n")
        r3 = subprocess.run([py, os.path.join(sk, "scripts", "cases.py"), "ingest", csvp, "-w", os.path.join(td, "w")],
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
        good = (r1.returncode == 0 and "不可用　出图" not in r1.stdout and "不可用　类案编码 · 读判决书" not in r1.stdout
                and r2.returncode == 0 and os.path.exists(os.path.join(td, "o", "x.pptx")) and r3.returncode == 0)
        return good, r1.stdout + r2.stderr + r3.stderr
    finally:
        shutil.rmtree(td, ignore_errors=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description="打单独安装包（带 V1、V4 依赖）")
    ap.add_argument("-o", "--out", default=os.path.join(ROOT, "dist"))
    a = ap.parse_args(argv)
    z = build(a.out)
    good, log = verify(z)
    print(log.strip())
    if not good:
        print(f"包打出来了但自检没过，不要分发：{z}", file=sys.stderr)
        return 1
    print(f"已打包并在空目录里验过：{z}")
    return 0


if __name__ == "__main__":
    # Windows 中文系统的控制台默认 GBK：不固定成 UTF-8，外部 AI（按 UTF-8 读）看到的是乱码，
    # 遇到 GBK 里没有的字（生僻字人名）还会在图已画好之后崩掉。写法与其余模块一致。
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:                               # noqa: BLE001
            pass
    sys.exit(main())
