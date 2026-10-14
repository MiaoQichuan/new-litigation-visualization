# -*- coding: utf-8 -*-
"""幻灯片尺寸兼容层：V7 自己调用 V1–V5 的渲染器，按图卡的尺寸出图（作者定的，2026-10-07）。

V1–V5 的图按 A4 文书设计，放进一页课件常常缩到字小于 11px。作者的规矩：V1–V6 原有定义一个字不改，
由 V7 自己做兼容。所以这里只在**子进程**里调用它们现成的函数、传它们本来就接受的参数，不碰它们的文件：

  V5 庭审对抗图：render_main.render(data, out, s, W) 本来就收字号倍数 s 与画布宽 W。
     V7 用 s=1、W=图卡宽，并可只出一个要件（data["parts"] 只留一项）；出图后在拼页里自动切片，
     只取这些卡片（去掉标题、索引表、图例）——一个要件正好一页。
     输入可以是 V5 的分析输入（matrix-input，先过 V5 自己的 to_figure.py）或图输入（parts 里有 center）。

其余模块实测不适合这样做（V2 的容量计算与 A4 纸张绑在一起，改了画布会转纵向或拒画；V1 只能调最小高度；
V3 的尺寸由布局求解决定、字号已在下限；V4 是竖版表格），它们照旧放 SVG，靠裁边与切片。
每个模块用单独的子进程：V1、V2、V5 都用裸名导入同名小模块（paper、geom……），同一进程里会串。
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile

import paths  # noqa: F401

HERE = os.path.dirname(os.path.abspath(__file__))
SKILLS = os.path.dirname(os.path.dirname(HERE))
V5 = os.path.join(SKILLS, "mqc-trial-confrontation-master", "scripts")
TIMEOUT = 120

_DRIVER_V5 = r"""
import sys, json, copy, io, contextlib
sys.path.insert(0, sys.argv[1])
import render_main as R
d = json.load(open(sys.argv[2], encoding="utf-8"))
part = sys.argv[4]
if part != "all":
    d["parts"] = [d["parts"][int(part)]]
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    ok = R.render(copy.deepcopy(d), sys.argv[3], s=1.0, W=int(float(sys.argv[5])))
sys.exit(0 if ok else 3)
"""


class AdaptError(RuntimeError):
    pass


def kind_of(mod):
    """这张图卡走不走兼容层：有 data（模块的数据文件）且来自 V5。"""
    return "V5" if mod.get("data") and "V5" in str(mod.get("from") or "") else None


def _run(args, what):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
    r = subprocess.run([sys.executable] + args, capture_output=True, text=True, timeout=TIMEOUT, env=env,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        tail = (r.stderr or r.stdout or "").strip().splitlines()[-1:] or ["（没有输出）"]
        raise AdaptError(f"{what}没出成：{tail[0][:160]}")
    return r


def v5_figure_input(src, workdir):
    """V5 的输入 → 图输入。已经是图输入（parts 里有 center）就原样用；否则过 V5 自己的 to_figure.py。"""
    try:
        with open(src, encoding="utf-8-sig") as f:
            d = json.load(f)
    except json.JSONDecodeError as e:
        raise AdaptError(f"V5 数据文件不是合法的 JSON：第 {e.lineno} 行第 {e.colno} 列附近")
    except UnicodeDecodeError:
        raise AdaptError("V5 数据文件不是 UTF-8 文本（可能是别的格式改了扩展名）")
    if not isinstance(d, dict):
        raise AdaptError("V5 数据文件要是一个对象（含 parts）")
    parts = d.get("parts") or []
    if not parts:
        raise AdaptError("这份 V5 数据里没有对抗部分（parts）")
    if all("center" in p for p in parts):
        return src, d
    out = os.path.join(workdir, "figure-input.json")
    _run([os.path.join(V5, "to_figure.py"), src, out], "V5 的图输入")
    with open(out, encoding="utf-8-sig") as f:
        return out, json.load(f)


def render(mod, base_dir, box_w, cache=None):
    """返回 (svg, 报告)。报告：parts（各要件的名字，给编辑器选）、part、notes。"""
    kind = kind_of(mod)
    if kind != "V5":
        raise AdaptError("只有 V5 庭审对抗图走幻灯片尺寸兼容层")
    src = paths.inside(base_dir, mod["data"])
    if src is None:
        raise AdaptError(f"V5 数据文件 {mod['data']!r} 不在这个课件的文件夹里：请放进 assets/（外面的文件不读）")
    if not os.path.exists(src):
        raise AdaptError(f"找不到 V5 数据文件 {mod['data']!r}")
    part = mod.get("part")
    st = os.stat(src)
    key = ("adapt", kind, os.path.abspath(src), st.st_mtime_ns, st.st_size, int(box_w), part)
    if cache is not None and key in cache:
        return cache[key]
    with tempfile.TemporaryDirectory(prefix="nlv7-adapt-") as td:
        fig, d = v5_figure_input(src, td)
        labels = [str(p.get("label") or f"要件 {i + 1}") for i, p in enumerate(d["parts"])]
        if part is not None and not (isinstance(part, int) and 0 <= part < len(labels)):
            raise AdaptError(f"没有第 {part} 个要件（这份数据有 {len(labels)} 个）")
        out = os.path.join(td, "v5.svg")
        _run(["-c", _DRIVER_V5, V5, fig, out, "all" if part is None else str(part), str(box_w)], "V5 对抗图")
        with open(out, encoding="utf-8-sig") as f:
            svg = f.read()
    rep = {"parts": labels, "part": part,
           "notes": [f"V5 按图卡宽 {int(box_w)} 重新出图（字号原样）" + (f"，只出「{labels[part]}」" if part is not None else "")]}
    res = (svg, rep)
    if cache is not None:
        cache[key] = res
    return res


def fingerprint(path):
    with open(path, "rb") as f:
        return hashlib.sha1(f.read()).hexdigest()[:12]
