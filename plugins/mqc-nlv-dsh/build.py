#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""打 DeepSeek Harness 插件包：mqc-nlv-dsh-<版本>.tgz（npm pack 的格式，不需要装 npm）。

    python3 plugins/mqc-nlv-dsh/build.py            # 输出到 plugins/mqc-nlv-dsh/dist/
    python3 plugins/mqc-nlv-dsh/build.py -o 某目录

包里有：插件入口（index.js、skill-provider.js、lib/）、七个技能原样（含各自的自检脚本，去掉缓存与只给 README 看的展示图）、
随包的 openpyxl 与 et_xmlfile（纯 Python，MIT，出 Excel 用）、许可与第三方声明。
同一份源码打出的包逐字节一致（文件按名排序、时间戳固定）。
"""
import argparse
import gzip
import io
import json
import os
import re
import shutil
import sys
import tarfile
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", ".."))
SKILLS_SRC = os.path.join(REPO, "plugins", "mqc-nlv", "skills")
PLUGIN_JSON = os.path.join(REPO, "plugins", "mqc-nlv", ".claude-plugin", "plugin.json")
OWN = ["index.js", "skill-provider.js", "lib", "locale", "docs", "cordis.patch.yml", "icon.svg", "package.json", "README.md", "CHANGELOG.md"]
# 各技能的 tests/ 要带上：大事记表大师、庭审对抗图大师出图后会调用其中的交付核验脚本
SKIP_DIRS = {"__pycache__", "node_modules", "out", "dist", ".git"}
SKIP_FILES = re.compile(r"(\.pyc$|^\.|\.DS_Store$)")
FIXED_MTIME = 499162500          # npm pack 用的固定时间（1985-10-26），保证逐字节可复现
VENDORED_PY = ["openpyxl", "et_xmlfile"]
# 只给 README 看的展示图，运行时不用：不进插件包（包小一大半）。运行时要读的 assets（字体说明、样式令牌、索引表）照带。
DOC_ONLY = re.compile(r"^assets/(longform|modes|screenshots|brand)(/|$)|^assets/gallery[^/]*\.png$")


def frontmatter(path):
    """读 SKILL.md 开头的 name 与 description（支持 `key: 值` 与 `key: >-` 折叠块）。"""
    text = open(path, encoding="utf-8-sig").read()
    if not text.startswith("---"):
        raise SystemExit(f"{path} 没有 YAML 头")
    head = text[3:text.index("\n---", 3)]
    lines = head.split("\n")
    out, i = {}, 0
    while i < len(lines):
        m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", lines[i])
        if not m:
            i += 1
            continue
        key, val = m.group(1), m.group(2).strip()
        if val in (">-", ">", "|", "|-"):
            buf = []
            i += 1
            while i < len(lines) and (lines[i].startswith("  ") or not lines[i].strip()):
                buf.append(lines[i].strip())
                i += 1
            out[key] = (" " if val.startswith(">") else "\n").join(x for x in buf if x)
            continue
        out[key] = val.strip("'\"")
        i += 1
    return out


def copy_skill(src, dst, doc_filter=False):
    for dp, dns, fns in os.walk(src):
        rel = os.path.relpath(dp, src)
        relp = "" if rel == "." else rel.replace(os.sep, "/") + "/"
        dns[:] = sorted(d for d in dns if d not in SKIP_DIRS and not d.startswith(".")
                        and not (doc_filter and DOC_ONLY.search(relp + d)))
        for fn in sorted(fns):
            if SKIP_FILES.search(fn) or (doc_filter and DOC_ONLY.search(relp + fn)):
                continue
            target = os.path.join(dst, rel, fn)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy2(os.path.join(dp, fn), target)


def vendor_python(dst):
    """把本机装着的 openpyxl、et_xmlfile 原样放进包里（连同各自的许可文件）。"""
    notices = []
    os.makedirs(os.path.join(dst, "LICENSES"), exist_ok=True)
    for mod in VENDORED_PY:
        try:
            m = __import__(mod)
        except ImportError:
            raise SystemExit(f"打包要用本机的 {mod}（随插件附带给用户）：先 pip install openpyxl")
        src = os.path.dirname(m.__file__)
        copy_skill(src, os.path.join(dst, mod))
        site = os.path.dirname(src)
        dist = next((d for d in os.listdir(site) if d.lower().startswith(mod.lower().replace("_", "_") + "-")
                     and d.endswith(".dist-info")), None)
        ver = getattr(m, "__version__", None)
        if dist:
            ver = ver or dist.split("-")[1]
            for fn in sorted(os.listdir(os.path.join(site, dist))):
                if re.match(r"(LICEN[CS]E|AUTHORS)", fn, re.I):
                    shutil.copy2(os.path.join(site, dist, fn), os.path.join(dst, "LICENSES", f"{mod}-{fn}"))
        notices.append((mod, ver or "未知"))
    return notices


def find_docx():
    """npm 的 docx 包（时间轴溯源索引、大事记 Word 版要用）。它的 dist/index.cjs 已把依赖打进一个文件，只带这一份。"""
    cand = [os.environ.get("NLV_DOCX_DIR")]
    try:
        import subprocess
        root = subprocess.run(["npm", "root", "-g"], capture_output=True, text=True, timeout=60).stdout.strip()
        cand.append(os.path.join(root, "docx"))
    except Exception:                                   # noqa: BLE001
        pass
    cand += [os.path.join(p, "docx") for p in os.environ.get("NODE_PATH", "").split(os.pathsep) if p]
    for c in cand:
        if c and os.path.isfile(os.path.join(c, "dist", "index.cjs")) and os.path.isfile(os.path.join(c, "package.json")):
            return os.path.realpath(c)
    return None


def vendor_docx(dst):
    src = find_docx()
    if not src:
        raise SystemExit("打包要用 npm 的 docx 包（随插件附带，Word 版要用）：先 npm install -g docx@9，"
                         "或用 NLV_DOCX_DIR 指到它的目录；确实不带时加 --no-docx")
    meta = json.load(open(os.path.join(src, "package.json"), encoding="utf-8"))
    out = os.path.join(dst, "node_modules", "docx")
    os.makedirs(os.path.join(out, "dist"), exist_ok=True)
    shutil.copy2(os.path.join(src, "dist", "index.cjs"), os.path.join(out, "dist", "index.cjs"))
    shutil.copy2(os.path.join(src, "LICENSE"), os.path.join(out, "LICENSE"))
    with open(os.path.join(out, "package.json"), "w", encoding="utf-8") as f:
        json.dump({"name": "docx", "version": meta["version"], "license": meta.get("license", "MIT"),
                   "main": "dist/index.cjs", "note": "随新诉讼可视化插件附带的 docx（只带打包好的 CommonJS 版）"},
                  f, ensure_ascii=False, indent=2)
    return meta["version"]


def build(out_dir, with_docx=True):
    pkg = json.load(open(os.path.join(HERE, "package.json"), encoding="utf-8"))
    suite = json.load(open(PLUGIN_JSON, encoding="utf-8"))["version"]
    if pkg["version"] != suite:
        raise SystemExit(f"版本不一致：插件包 {pkg['version']}，套件 {suite}。两处要一起改")
    stage_root = tempfile.mkdtemp(prefix="nlv-dsh-")
    stage = os.path.join(stage_root, "package")
    os.makedirs(stage)
    for name in OWN:
        src = os.path.join(HERE, name)
        if os.path.isdir(src):
            copy_skill(src, os.path.join(stage, name))
        else:
            shutil.copy2(src, os.path.join(stage, name))
    shutil.copy2(os.path.join(REPO, "LICENSE"), os.path.join(stage, "LICENSE"))

    skills = []
    for name in sorted(os.listdir(SKILLS_SRC)):
        sk = os.path.join(SKILLS_SRC, name, "SKILL.md")
        if not os.path.isfile(sk):
            continue
        fm = frontmatter(sk)
        if fm.get("name") != name:
            raise SystemExit(f"{sk} 的 name（{fm.get('name')}）与目录名不一致")
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name) or not fm.get("description"):
            raise SystemExit(f"{sk}：技能名要是小写连字符、description 不能为空")
        copy_skill(os.path.join(SKILLS_SRC, name), os.path.join(stage, "nlv-skills", name), doc_filter=True)
        skills.append({"name": name, "description": fm["description"]})
    if len(skills) != 7:
        raise SystemExit(f"应有七个技能，找到 {len(skills)} 个")
    # 插件包本身是 ES 模块（package.json 写了 "type": "module"），技能目录里的 Node 脚本（build_docx.js、trace_index.js）
    # 却是 CommonJS（用 require）。不隔开的话 Node 按最近的 package.json 把它们当 ES 模块读，一运行就报 require 未定义。
    with open(os.path.join(stage, "nlv-skills", "package.json"), "w", encoding="utf-8") as f:
        json.dump({"name": "mqc-nlv-skills", "private": True, "type": "commonjs"}, f, ensure_ascii=False, indent=2)
    with open(os.path.join(stage, "nlv-skills", "skills.json"), "w", encoding="utf-8") as f:
        json.dump({"version": pkg["version"], "skills": skills}, f, ensure_ascii=False, indent=2)

    notices = vendor_python(os.path.join(stage, "python"))
    docx_ver = vendor_docx(os.path.join(stage, "nodejs")) if with_docx else None
    with open(os.path.join(stage, "THIRD-PARTY-NOTICES.md"), "w", encoding="utf-8") as f:
        f.write("# 第三方组件 · Third-party notices\n\n本插件以 AGPL-3.0-only 发布；下列随包附带的组件保留各自的许可，许可全文见 `python/LICENSES/`。\n\n")
        f.write("| 组件 | 版本 | 许可 | 用途 |\n| --- | --- | --- | --- |\n")
        for mod, ver in notices:
            f.write(f"| {mod} | {ver} | MIT | 读写 Excel（openpyxl 依赖 et_xmlfile） |\n")
        if docx_ver:
            f.write(f"| docx（npm） | {docx_ver} | MIT | 写 Word：时间轴溯源索引、大事记 Word 版（需本机有 Node.js）。"
                    "它的 dist/index.cjs 已打进 jszip（MIT 或 GPL-3.0，此处按 MIT）、pako（MIT 与 Zlib）、"
                    "sax（BlueOak-1.0.0）、xml-js、nanoid、hash.js 等依赖，许可原文见各项目 |\n")

    os.makedirs(out_dir, exist_ok=True)
    tgz = os.path.join(out_dir, f"{pkg['name']}-{pkg['version']}.tgz")
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.PAX_FORMAT) as tar:
        entries = []
        for dp, dns, fns in os.walk(stage):
            dns.sort()
            for fn in sorted(fns):
                entries.append(os.path.join(dp, fn))
        for p in sorted(entries, key=lambda x: os.path.relpath(x, stage_root).replace(os.sep, "/")):
            arc = os.path.relpath(p, stage_root).replace(os.sep, "/")
            info = tarfile.TarInfo(arc)
            data = open(p, "rb").read()
            info.size = len(data)
            info.mtime = FIXED_MTIME
            info.mode = 0o644
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            tar.addfile(info, io.BytesIO(data))
    with open(tgz, "wb") as f:
        with gzip.GzipFile(filename="", mode="wb", fileobj=f, mtime=0) as gz:
            gz.write(raw.getvalue())
    n = len(entries)
    shutil.rmtree(stage_root)
    print(f"已打包：{tgz}")
    print(f"  {n} 个文件，{os.path.getsize(tgz) / 1048576:.1f} MB；七个技能：{'、'.join(s['name'] for s in skills)}")
    print(f"  随包 Python 组件：{'、'.join(f'{m} {v}' for m, v in notices)}；Word 用的 docx：{docx_ver or '未带'}")
    return tgz


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="打 DeepSeek Harness 插件包")
    ap.add_argument("-o", "--out", default=os.path.join(HERE, "dist"), help="输出目录（默认 plugins/mqc-nlv-dsh/dist）")
    ap.add_argument("--no-docx", action="store_true", help="不带 npm 的 docx 包（本机没有时用；Word 版将不可用）")
    a = ap.parse_args()
    build(a.out, with_docx=not a.no_docx)
