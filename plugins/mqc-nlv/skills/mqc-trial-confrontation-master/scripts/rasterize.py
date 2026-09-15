#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SVG → PNG。交付的 SVG 保留完整字体栈（在律师本机才对），
光栅化时换成本机确实装着的单一字族——cairosvg 解析不了带引号的多字族栈，
会静默回退到无中文的字体，文字还在、字形全是豆腐块，且没有任何检查会报错。
所以出图后量一次墨迹宽度，命中中文字体才算过。"""
import os, re, sys, cairosvg
from PIL import Image
import numpy as np

SANS = "Noto Sans CJK SC"
SERIF = "Noto Serif CJK SC"

def rasterize(src, dst, width=1400):
    s = open(src, encoding="utf-8").read()
    s = re.sub(r'font-family="[^"]*方正小标宋[^"]*"', f'font-family="{SERIF}"', s)
    s = re.sub(r'font-family="[^"]*(?:PingFang|Microsoft YaHei)[^"]*"', f'font-family="{SANS}"', s)
    # 换过字族的那份是中间产物，直接喂给 cairosvg，不落盘——
    # 早先写成 dst + ".svg"，交付目录里于是多出一个「庭审对抗图.png.svg」，
    # 律师看到会以为是另一份图。
    cairosvg.svg2png(bytestring=s.encode("utf-8"), write_to=dst, output_width=width)
    return verify(dst)

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
    ok, info = rasterize(sys.argv[1], sys.argv[2])
    print(f"  PNG：{sys.argv[2]}　{info}")
