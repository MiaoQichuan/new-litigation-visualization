#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""律所风格（第二步：把读懂的模板变成一种风格，和奇川风、歸藏风并列）。

    python3 scripts/firm_style.py make tokens.json --name 某某律所风 -o 律所名片目录/style.json
    python3 scripts/firm_style.py check 律所名片目录/style.json

tokens.json 是 template_read.py 读出来的东西。作者定的规矩（2026-10-05）：
  * 中文标题用粗黑体（PowerPoint 里是微软雅黑加粗），与英文 Arial Black 一类的粗体气质一致；
  * 只用主色家族 + 灰，模板里的辅助色（青、黄、品红……）先不放进来——一页仍只有一处重音；
  * V6 图表的重音跟着换成律所主色（经 V6 的 firm_palette 校验，见 V6 ADR 0011）。
律所风格文件放在律所名片目录（brand/style.json 或本机公共名片），不进开源仓库——模板是律所的财产。
"""
import argparse
import json
import os
import re
import sys

import paths  # noqa: F401
from template_read import contrast, hls, luminance

SCHEMA = "mqc-nlv/firm-style@1"
HEX = re.compile(r"#[0-9A-F]{6}")
MIN_TEXT = 4.5


class FirmStyleError(ValueError):
    pass


def _pick_tint(tints, ink):
    """卡片底色：主色家族的浅色调里，模板用得最多、上面正文仍看得清的那一档（tints 按用量排）。"""
    ok = [t for t in tints if contrast(ink, t) >= MIN_TEXT and hls(t)[1] >= 0.85]
    return ok[0] if ok else None


def make(tokens, name, base="奇川风"):
    """tokens（template_read 的结果）→ 律所风格。只取主色家族与灰。"""
    roles = tokens["colors"]["roles"]
    acc = (roles.get("primary") or "").upper()
    dark = (roles.get("primary_dark") or acc).upper()
    paper = (roles.get("background") or "#FFFFFF").upper()
    ink = (roles.get("text") or "#333333").upper()
    tints = [t.upper() for t in roles.get("tints") or []]
    grays = [g.upper() for g in roles.get("neutrals") or []]
    # 模板没有合用的浅色调：退到浅灰，一档比一档浅，直到上面的正文看得清
    card = _pick_tint(tints, ink) or next((g for g in ("#F3F4F6", "#F6F7F8", "#F9FAFA", "#FCFCFC")
                                           if contrast(ink, g) >= MIN_TEXT), paper)
    outline = next((t for t in sorted(tints, key=lambda t: hls(t)[1]) if t != card), None) or "#D6DAE0"
    # 次要字：要比正文明显浅一档（亮度高出 25% 以上），又在纸上、卡片上都看得清；没有就用正文色
    ink2 = next((g for g in grays if contrast(g, paper) >= MIN_TEXT and contrast(g, card) >= MIN_TEXT
                 and luminance(g) > luminance(ink) * 1.25), ink)
    note = next((g for g in grays if 2.0 <= contrast(g, paper) < MIN_TEXT), "#9CA3AF")
    cover_ink2 = next((t for t in sorted(tints, key=lambda t: -hls(t)[1]) if contrast(t, acc) >= MIN_TEXT), "#FFFFFF")
    tc = (tokens.get("type", {}).get("title", {}).get("color") or acc).upper()
    st = {
        "schema": SCHEMA, "name": name, "base": base, "source": tokens.get("source"),
        "colors": {
            "accent": acc, "accent_dark": dark, "paper": paper, "ink": ink, "ink2": ink2, "note": note,
            "title": tc, "card": card, "outline": outline,
            "cover_bg": acc, "cover_ink": "#FFFFFF", "cover_ink2": cover_ink2, "cover_card": dark,
        },
        "fonts": {"title": "sans", "title_weight": 700, "body": "sans",
                  "note": "中文标题用粗黑体（PowerPoint 里是微软雅黑加粗）；模板英文标题字体："
                          + str(tokens.get("type", {}).get("title", {}).get("font") or "未写")},
        "radius": {"outer": 10.0 if base == "奇川风" else 0.0, "inner": 4.0 if base == "奇川风" else 0.0},
        "dark_pages": ["cover", "section"],
        "logo_box": (tokens.get("logo") or {}).get("box"),
        "template_margins": {k: tokens.get("geometry", {}).get(k) for k in ("margin_left", "margin_top", "margin_right")},
        "left_out": {"secondary": roles.get("secondary") or [],
                     "why": "作者定的：先只用主色家族与灰，一页一处重音；辅助色以后要用再开"},
    }
    check(st)
    return st


# ------------------------------------------------------------- 没有模板时：从一张截图或一个主色做自定义风格
INK = "#333333"
NEUTRAL = "#585E6A"          # 次要字：比正文浅一档，在主色浅底卡片上也看得清


def _hex(r, g, b):
    return "#%02X%02X%02X" % tuple(max(0, min(255, round(v * 255))) for v in (r, g, b))


def _mix(c, w, t):
    """c 与 w 按 t 混合（t=1 全是 w）。"""
    a, b = c.lstrip("#"), w.lstrip("#")
    return "#" + "".join("%02X" % round(int(a[i:i + 2], 16) * (1 - t) + int(b[i:i + 2], 16) * t) for i in (0, 2, 4))


def readable_accent(c, paper="#FFFFFF"):
    """主色太浅时往深里压（色相不变），直到投影时在白纸上看得清（对比度 ≥ 4.5）。"""
    import colorsys
    h, l_, s_ = hls(c)
    while contrast(c, paper) < MIN_TEXT and l_ > 0.05:
        l_ -= 0.02
        c = _hex(*colorsys.hls_to_rgb(h, l_, s_))
    return c


def tokens_from_color(color, source="手选主色"):
    """一个主色 → 与 template_read 同形的 tokens：深色、浅色调都按主色推出来，正文用中性深灰。"""
    import colorsys
    c = str(color or "").strip().upper()
    if not HEX.fullmatch(c):
        raise FirmStyleError("主色要写成 #RRGGBB，例如 #702082")
    if hls(c)[2] < 0.2:
        raise FirmStyleError(f"{c} 接近灰色：自定义风格要有一个看得出颜色的主色")
    acc = readable_accent(c)
    h, l_, s_ = hls(acc)
    dark = _hex(*colorsys.hls_to_rgb(h, max(0.08, l_ * 0.78), s_))
    return {"source": source, "colors": {"roles": {
        "primary": acc, "primary_dark": dark, "background": "#FFFFFF", "text": INK,
        "tints": [_mix(acc, "#FFFFFF", 0.9), _mix(acc, "#FFFFFF", 0.72)], "neutrals": [NEUTRAL], "secondary": []}},
        "type": {"title": {"color": acc}}, "adjusted": acc != c, "picked": c}


def main_color_of(data):
    """截图 → 主色：最常见的「有颜色」的那一族（饱和度够、不太亮不太暗），取这一族的平均色。"""
    import frame as F
    try:
        _, _, grid_ = F.sample(data, 160, 90)
    except F.FrameError as e:
        raise FirmStyleError(str(e))
    bins = {}
    for row in grid_:
        for p in row:
            c = "#%02X%02X%02X" % p
            h, l_, s_ = hls(c)
            if s_ < 0.25 or not 0.12 <= l_ <= 0.85:
                continue
            k = int(h * 24) % 24
            bins.setdefault(k, []).append(p)
    if not bins:
        raise FirmStyleError("截图里找不到主色（几乎全是黑白灰）：请直接选一个主色")
    best = max(bins.values(), key=len)
    buckets = {}                                 # 这一族里出现最多的那个颜色（抗锯齿的边缘像素偏浅，不能平均）
    for p in best:
        buckets.setdefault(tuple(v // 12 for v in p), []).append(p)
    top = max(buckets.values(), key=len)
    n = len(top)
    return "#%02X%02X%02X" % tuple(round(sum(p[i] for p in top) / n) for i in range(3))


def check(st):
    """校验律所风格文件。返回 None，有错抛 FirmStyleError（说清是哪一处、差多少）。"""
    if not isinstance(st, dict) or st.get("schema") != SCHEMA:
        from deck import _newer
        newer = _newer(st.get("schema") if isinstance(st, dict) else None, SCHEMA)
        if newer:
            raise FirmStyleError(f"这份律所风格是更新版本的法律课件大师写的（{newer}），本机的版本只认到 {SCHEMA}："
                                 "请把插件升级到最新版")
        raise FirmStyleError(f"律所风格文件的 schema 要是 {SCHEMA}")
    if not str(st.get("name") or "").strip():
        raise FirmStyleError("律所风格要有名字（例如「某某律所风」）")
    if st["name"] in ("奇川风", "歸藏风"):
        raise FirmStyleError("律所风格不能和内置风格同名")
    c = st.get("colors") or {}
    need = ("accent", "accent_dark", "paper", "ink", "ink2", "note", "title", "card", "outline",
            "cover_bg", "cover_ink", "cover_ink2", "cover_card")
    bad = [k for k in need if not HEX.fullmatch(str(c.get(k) or "").upper())]
    if bad:
        raise FirmStyleError("这些颜色缺了或不是 #RRGGBB：" + "、".join(bad))
    import styles as V6styles                               # V6：主色那一关由 V6 自己把
    try:
        V6styles.firm_palette({"name": st["name"], "base": st.get("base"), "accent": c["accent"]})
    except ValueError as e:
        raise FirmStyleError(str(e))
    pairs = [("正文在纸上", "ink", "paper"), ("正文在卡片上", "ink", "card"), ("次要字在纸上", "ink2", "paper"),
             ("次要字在卡片上", "ink2", "card"), ("标题在纸上", "title", "paper"), ("白字在重音卡上", "cover_ink", "accent"),
             ("封面字在封面底上", "cover_ink", "cover_bg"), ("封面次要字在封面底上", "cover_ink2", "cover_bg"),
             ("深底卡片上的字", "cover_ink", "cover_card")]
    low = []
    for what, fg, bg in pairs:
        r = contrast(c[fg], c[bg])
        if r < MIN_TEXT:
            low.append(f"{what}（{c[fg]} / {c[bg]}）对比度 {r:.1f}，至少 {MIN_TEXT}")
    if low:
        raise FirmStyleError("这些地方投影时看不清：" + "；".join(low))
    if luminance(c["cover_bg"]) > 0.3:
        raise FirmStyleError("封面、章节页的底色要是深色（律所主色或更深）：白字才压得住")


def colors(st):
    """这份律所风格用到的所有颜色（导出审计的白名单）。"""
    return {v.upper() for v in st["colors"].values() if isinstance(v, str) and HEX.fullmatch(v.upper())}


def load(path):
    with open(path, encoding="utf-8-sig") as f:
        st = json.load(f)
    check(st)
    return st


def main(argv=None):
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="律所风格：由模板读取结果生成，或检查一份律所风格文件")
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("make")
    m.add_argument("tokens")
    m.add_argument("--name", required=True)
    m.add_argument("--base", default="奇川风", choices=("奇川风", "歸藏风"))
    m.add_argument("-o", "--out", required=True)
    c = sub.add_parser("check")
    c.add_argument("style")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "make":
            with open(a.tokens, encoding="utf-8-sig") as f:
                st = make(json.load(f), a.name, a.base)
            os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
            with open(a.out + ".nlv-new", "w", encoding="utf-8", newline="\n") as f:
                json.dump(st, f, ensure_ascii=False, indent=1)
            os.replace(a.out + ".nlv-new", a.out)
            col = st["colors"]
            print(f"已生成律所风格「{st['name']}」：主色 {col['accent']}，标题 {col['title']}，正文 {col['ink']}，卡片 {col['card']}")
            if st["left_out"]["secondary"]:
                print(f"  没放进来的辅助色：{'、'.join(st['left_out']['secondary'])}（{st['left_out']['why']}）")
            print(f"文件：{a.out}")
        else:
            st = load(a.style)
            print(f"律所风格「{st['name']}」校验通过")
    except (FirmStyleError, KeyError, ValueError, OSError) as e:
        print(str(e), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
