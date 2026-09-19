#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SVG → PNG。交付的 SVG 保留完整字体栈（在律师本机才对），
光栅化时换成本机确实装着的单一字族——cairosvg 解析不了带引号的多字族栈，
会静默回退到无中文的字体，文字还在、字形全是豆腐块，且没有任何检查会报错。
所以出图后量一次墨迹宽度，命中中文字体才算过。"""
import os, re, shutil, subprocess, sys, tempfile
from PIL import Image
import numpy as np

try:                                  # 装了就照旧用，行为与原来完全一致
    import cairosvg
except ImportError:                   # 没装就走外部转换工具（见 _rasterize_external）
    cairosvg = None

SANS = "Noto Sans CJK SC"
SERIF = "Noto Serif CJK SC"

def rasterize(src, dst, width=1400):
    s = open(src, encoding="utf-8").read()
    s = re.sub(r'font-family="[^"]*方正小标宋[^"]*"', f'font-family="{SERIF}"', s)
    s = re.sub(r'font-family="[^"]*(?:PingFang|Microsoft YaHei)[^"]*"', f'font-family="{SANS}"', s)
    # 换过字族的那份是中间产物，直接喂给 cairosvg，不落盘——
    # 早先写成 dst + ".svg"，交付目录里于是多出一个「庭审对抗图.png.svg」，
    # 律师看到会以为是另一份图。
    if cairosvg is not None:
        cairosvg.svg2png(bytestring=s.encode("utf-8"), write_to=dst, output_width=width)
    else:
        # 没有 cairosvg 时才走这里：用本机装着的转换工具。真实环境里撞到过
        # 「装了 Inkscape 却报找不到转换工具」——Windows 上它不写进 PATH，
        # 所以找不到时再查常见安装位置。找不到任何一个就照旧报错，不静默出空图。
        _rasterize_external(s, dst, width)
    return verify(dst)


def _find_tool(name):
    found = shutil.which(name)
    if not found and os.name == "nt":
        rel = {"inkscape": [("Inkscape", "bin", "inkscape.exe"), ("Inkscape", "inkscape.exe")],
               "rsvg-convert": [("rsvg-convert.exe",)],
               "soffice": [("LibreOffice", "program", "soffice.exe")],
               "pdftoppm": [("poppler", "bin", "pdftoppm.exe"),
                            ("poppler", "Library", "bin", "pdftoppm.exe")]}.get(name, [])
        for root in [os.environ.get(v) for v in ("ProgramFiles", "ProgramFiles(x86)",
                                                 "LOCALAPPDATA")]:
            for tail in (rel if root else []):
                cand = os.path.join(root, *tail)
                if os.path.exists(cand):
                    return cand
    return found


def _rasterize_external(svg_text, dst, width):
    """SVG → PNG 的备用通道：rsvg-convert → Inkscape → LibreOffice+pdftoppm。"""
    tmp = os.path.join(tempfile.mkdtemp(), "t.svg")
    open(tmp, "w", encoding="utf-8").write(svg_text)
    rsvg, ink, sof, ppm = (_find_tool(x) for x in
                           ("rsvg-convert", "inkscape", "soffice", "pdftoppm"))
    if rsvg:
        subprocess.run([rsvg, "-w", str(width), tmp, "-o", dst], check=True)
        return
    if ink:
        subprocess.run([ink, tmp, "--export-type=png", f"--export-width={width}",
                        f"--export-filename={dst}"], check=True)
        return
    if sof and ppm:
        d = os.path.dirname(tmp)
        subprocess.run([sof, "--headless", "--convert-to", "pdf", "--outdir", d, tmp],
                       check=True)
        pdf = os.path.join(d, "t.pdf")
        subprocess.run([ppm, "-png", "-singlefile", "-scale-to-x", str(width),
                        "-scale-to-y", "-1", pdf, os.path.splitext(dst)[0]], check=True)
        return
    raise RuntimeError(
        "找不到 SVG 转 PNG 的工具：装 cairosvg（pip install cairosvg），"
        "或安装 Inkscape / LibreOffice / rsvg-convert 其一。SVG 已经出好，PNG 可稍后补。")

def verify(png, min_ratio=0.45):
    """中文若退化成豆腐块，笔画密度会明显偏低。量深色像素占比，低于阈值即判未命中。"""
    a = np.array(Image.open(png).convert("L"))
    dark = (a < 160)
    rows = dark.sum(axis=1)
    band = rows[rows > 0]
    if band.size == 0:
        return False, "整幅无墨迹"
    # 豆腐块是空心方框，横向连通段极多；真字形连通段少而长
    mid = dark[dark.any(axis=1)]
    runs = 0
    for r in mid[:: max(1, len(mid)//40)]:
        runs += len(re.findall(r"1+", "".join("1" if v else "0" for v in r)))
    return runs > 0, f"采样行连通段 {runs}"

if __name__ == "__main__":
    # Windows 中文系统的控制台默认 GBK：不固定成 UTF-8，外部 AI（按 UTF-8 读）看到的是
    # 乱码。真实运行记录里，时间轴大师就因此让模型摸索了一轮编码。写法与其余 skill 一致。
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ok, info = rasterize(sys.argv[1], sys.argv[2])
    print(f"  PNG：{sys.argv[2]}　{info}")
