#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""读懂一份律所 PPT 模板（律所风格的第一步：只读、只报告，不生成任何东西）。

    python3 scripts/template_read.py 模板.pptx -o out/          读模板，写 tokens.json 与 report.html
    python3 scripts/template_read.py 模板.pptx -o out/ --render 另用 LibreOffice 渲染缩略图放进报告（较慢）

读什么：
  页面尺寸；主题色板与每种颜色实际用了多少次，按角色归类（主色、深色、正文灰、浅色调、辅助色）；
  标题 / 正文的字体、字号、颜色；版面几何（页边距、标题框、内容区、页脚、页码）；Logo 放在哪；
  每一页属于哪种页型（封面 / 章节 / 内容 / 结束页），用什么底色；可读性检查（对比度）。
读出来的东西写进 tokens.json —— 第二步「变成律所风格」用它；report.html 给人核对读得准不准。

模板是律所的财产：这个脚本只在本机读，不上传；读出的 Logo 图片只写进 -o 目录，不进仓库。
"""
import argparse
import base64
import collections
import colorsys
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

EMU = 9525
W, H = 1280, 720


# ------------------------------------------------------------- 颜色
def hex6(c):
    return "#" + c.upper()


def hls(c):
    c = c.lstrip("#")
    r, g, b = (int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return colorsys.rgb_to_hls(r, g, b)


def luminance(c):
    c = c.lstrip("#")
    out = []
    for i in (0, 2, 4):
        v = int(c[i:i + 2], 16) / 255
        out.append(v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4)
    return 0.2126 * out[0] + 0.7152 * out[1] + 0.0722 * out[2]


def contrast(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def hue_dist(a, b):
    d = abs(hls(a)[0] - hls(b)[0])
    return min(d, 1 - d)


# ------------------------------------------------------------- Logo 图片有多亮（只用标准库解 PNG）
def png_ink(data):
    """PNG 里看得见的像素（不透明度 > 50%）的平均亮度 0–1。读不了返回 None。
    白字版 Logo 很亮（给深底用），彩色 / 深色版暗（给浅底用）。支持 8 位、不隔行的灰度 / RGB / 调色板 / 带透明。"""
    import struct
    import zlib
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    pos, idat, plte, trns = 8, b"", None, None
    w = h = depth = ctype = inter = None
    while pos + 8 <= len(data):
        ln, typ = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + ln]
        if typ == b"IHDR":
            w, h, depth, ctype, _, _, inter = struct.unpack(">IIBBBBB", body)
        elif typ == b"PLTE":
            plte = body
        elif typ == b"tRNS":
            trns = body
        elif typ == b"IDAT":
            idat += body
        elif typ == b"IEND":
            break
        pos += 12 + ln
    if depth != 8 or inter != 0 or ctype not in (0, 2, 3, 4, 6):
        return None
    ch = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ctype]
    try:
        raw = zlib.decompress(idat)
    except zlib.error:
        return None
    stride = w * ch
    prev = bytearray(stride)
    tot = n = 0
    step = max(1, h // 120)                       # 抽样：大图不必逐行
    for y in range(h):
        f = raw[y * (stride + 1)]
        line = bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for i in range(stride):
            a = line[i - ch] if i >= ch else 0
            b = prev[i]
            c = prev[i - ch] if i >= ch else 0
            if f == 1:
                line[i] = (line[i] + a) & 255
            elif f == 2:
                line[i] = (line[i] + b) & 255
            elif f == 3:
                line[i] = (line[i] + ((a + b) >> 1)) & 255
            elif f == 4:
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        prev = line
        if y % step:
            continue
        for x in range(0, w, max(1, w // 160)):
            px = line[x * ch:(x + 1) * ch]
            if ctype == 3:
                k = px[0]
                if not plte or 3 * k + 2 >= len(plte):
                    continue
                r, g, b_ = plte[3 * k:3 * k + 3]
                al = trns[k] if trns and k < len(trns) else 255
            elif ctype == 0:
                r = g = b_ = px[0]
                al = 255
            elif ctype == 4:
                r = g = b_ = px[0]
                al = px[1]
            else:
                r, g, b_ = px[:3]
                al = px[3] if ctype == 6 else 255
            if al > 128:
                tot += luminance("%02X%02X%02X" % (r, g, b_))
                n += 1
    return tot / n if n else None


# ------------------------------------------------------------- 读
def _px(v):
    return round(int(v) / EMU)


def _xfrm(x):
    m = re.search(r'<a:off x="(-?\d+)" y="(-?\d+)"/>\s*<a:ext cx="(\d+)" cy="(\d+)"/>', x)
    return [_px(m.group(i)) for i in range(1, 5)] if m else None


def read(path):
    z = zipfile.ZipFile(path)
    names = z.namelist()
    txt = lambda n: z.read(n).decode("utf-8", errors="ignore")
    rep = {"source": os.path.basename(path), "notes": []}

    pres = txt("ppt/presentation.xml")
    sz = re.search(r'<p:sldSz cx="(\d+)" cy="(\d+)"', pres)
    sw, sh = _px(sz.group(1)), _px(sz.group(2))
    rep["slide"] = {"w": sw, "h": sh, "aspect": round(sw / sh, 3), "is_16_9": abs(sw / sh - 16 / 9) < 0.01}
    if not rep["slide"]["is_16_9"]:
        rep["notes"].append(f"页面不是 16:9（{sw}×{sh}）：V7 只出 16:9，几何会按比例换算")
    k = W / sw                       # 换算到 1280×720 设计像素

    # 主题
    theme = txt(sorted(n for n in names if re.match(r"ppt/theme/theme\d+\.xml$", n))[0])
    cs = re.search(r'<a:clrScheme name="([^"]*)">(.*?)</a:clrScheme>', theme, re.S)
    scheme = {}
    for m in re.finditer(r"<a:(dk1|lt1|dk2|lt2|accent\d|hlink|folHlink)>(.*?)</a:\1>", cs.group(2), re.S):
        v = re.search(r'(?:srgbClr val|lastClr)="([0-9A-Fa-f]{6})"', m.group(2))
        if v:
            scheme[m.group(1)] = hex6(v.group(1))
    alias = {"tx1": "dk1", "bg1": "lt1", "tx2": "dk2", "bg2": "lt2"}
    rep["theme"] = {"name": cs.group(1), "scheme": scheme}
    fonts = {}
    for kind in ("majorFont", "minorFont"):
        blk = re.search(rf"<a:{kind}>(.*?)</a:{kind}>", theme, re.S).group(1)
        lat = re.search(r'<a:latin typeface="([^"]*)"', blk)
        ea = re.search(r'<a:ea typeface="([^"]*)"', blk)
        hans = re.search(r'<a:font script="Hans" typeface="([^"]*)"', blk)
        fonts[kind] = {"latin": lat.group(1) if lat else "", "cjk": (hans.group(1) if hans else "") or (ea.group(1) if ea else "")}

    # 母版的文字样式
    master = txt(sorted(n for n in names if re.match(r"ppt/slideMasters/slideMaster\d+\.xml$", n))[0])

    def style(tag):
        blk = re.search(rf"<p:{tag}>(.*?)</p:{tag}>", master, re.S)
        if not blk:
            return {}
        b = blk.group(1)
        lv1 = re.search(r"<a:lvl1pPr(.*?)</a:lvl1pPr>", b, re.S)
        b1 = lv1.group(1) if lv1 else b
        szm = re.search(r'sz="(\d+)"', b1)
        col = re.search(r'<a:(schemeClr|srgbClr) val="(\w+)"', b1)
        colhex = None
        if col:
            colhex = hex6(col.group(2)) if col.group(1) == "srgbClr" else scheme.get(alias.get(col.group(2), col.group(2)))
        return {"size_pt": int(szm.group(1)) / 100 if szm else None, "color": colhex,
                "bold": bool(re.search(r' b="1"', b1)), "bullet": (re.search(r'<a:buChar char="([^"]+)"', b1) or [None, None])[1]}
    ts, bs = style("titleStyle"), style("bodyStyle")
    pt2px = lambda pt: round(pt * 96 / 72 * k, 1) if pt else None
    rep["type"] = {
        "title": {"font": fonts["majorFont"]["latin"], "font_cjk": fonts["majorFont"]["cjk"] or None, "size_pt": ts.get("size_pt"),
                  "size_px": pt2px(ts.get("size_pt")), "color": ts.get("color"), "bold": ts.get("bold")},
        "body": {"font": fonts["minorFont"]["latin"], "font_cjk": fonts["minorFont"]["cjk"] or None, "size_pt": bs.get("size_pt"),
                 "size_px": pt2px(bs.get("size_pt")), "color": bs.get("color"), "bullet": bs.get("bullet")},
    }
    if not fonts["majorFont"]["cjk"] and not fonts["minorFont"]["cjk"]:
        rep["notes"].append("模板没有指定中文字体：PowerPoint 会退回系统默认（常见是宋体或等线）。用于中文课件时要另配一套中文字体")

    # 母版的几何：标题、正文、页脚、页码占位符
    geo = {}
    for ph, key in (("title", "title"), ("body", "body"), ("dt", "date"), ("ftr", "footer"), ("sldNum", "page_no")):
        m = re.search(rf'<p:ph type="{ph}"[^>]*/>.*?(<a:xfrm>.*?</a:xfrm>)', master, re.S)
        if m:
            b = _xfrm(m.group(1))
            geo[key] = [round(v * k) for v in b] if b else None
    if geo.get("title"):
        x, y, w, h = geo["title"]
        geo["margin_left"], geo["margin_top"], geo["margin_right"] = x, y, W - x - w
    if geo.get("page_no"):
        geo["margin_bottom"] = H - (geo["page_no"][1] + geo["page_no"][3])
    rep["geometry"] = geo

    # 每一页：版式名、底色、Logo 候选、标题
    layouts = {}
    for n in names:
        if re.match(r"ppt/slideLayouts/slideLayout\d+\.xml$", n):
            x = txt(n)
            nm = re.search(r'<p:cSld name="([^"]*)"', x)
            layouts[os.path.basename(n)] = (nm.group(1) if nm else "?", x)
    slides = sorted((n for n in names if re.match(r"ppt/slides/slide\d+\.xml$", n)),
                    key=lambda n: int(re.findall(r"\d+", n)[0]))
    order = re.findall(r'<p:sldId [^>]*r:id="(rId\d+)"', pres)
    prels = txt("ppt/_rels/presentation.xml.rels")
    tgt = dict(re.findall(r'Id="(rId\d+)"[^>]*Target="slides/(slide\d+\.xml)"', prels))
    tgt.update({a: b for b, a in re.findall(r'Target="slides/(slide\d+\.xml)"[^>]*Id="(rId\d+)"', prels)})
    if order and all(r in tgt for r in order):
        slides = ["ppt/slides/" + tgt[r] for r in order]

    def full_fill(x):
        """覆盖整页的形状或页面背景的填充色。"""
        bg = re.search(r"<p:bg>(.*?)</p:bg>", x, re.S)
        if bg:
            c = re.search(r'<a:(srgbClr|schemeClr) val="(\w+)"', bg.group(1))
            if c:
                return hex6(c.group(2)) if c.group(1) == "srgbClr" else scheme.get(alias.get(c.group(2), c.group(2)))
        for sp in re.findall(r"<p:sp>(.*?)</p:sp>", x, re.S):
            b = _xfrm(sp)
            if b and b[0] <= 2 and b[1] <= 2 and b[2] >= sw - 4 and b[3] >= sh - 4:
                c = re.search(r'<p:spPr>.*?<a:solidFill>\s*<a:(srgbClr|schemeClr) val="(\w+)"', sp, re.S)
                if c:
                    return hex6(c.group(2)) if c.group(1) == "srgbClr" else scheme.get(alias.get(c.group(2), c.group(2)))
        return None

    pages = []
    # Logo 候选：(位置, 图片) 分别记在浅底页、深底页上出现了几次——律所常有两版 Logo：
    # 深底用白字版，浅底用彩色版（不少大所的模板就是这样）。按出现在哪种底色上分开取，不靠看图。
    seen = {False: collections.Counter(), True: collections.Counter()}
    for i, n in enumerate(slides, 1):
        x = txt(n)
        rels = txt(n.replace("slides/", "slides/_rels/") + ".rels")
        lay = re.search(r'slideLayouts/(slideLayout\d+\.xml)', rels).group(1)
        lname, lx = layouts.get(lay, ("?", ""))
        bgc = full_fill(x) or full_fill(lx) or scheme.get("lt1", "#FFFFFF")
        dark = luminance(bgc) < 0.2
        text = " ".join(re.findall(r"<a:t>([^<]*)</a:t>", x))
        for src, srcrels in ((x, rels), (lx, txt("ppt/slideLayouts/_rels/" + lay + ".rels") if "ppt/slideLayouts/_rels/" + lay + ".rels" in names else "")):
            for pc in re.findall(r"<p:pic>(.*?)</p:pic>", src, re.S):
                b = _xfrm(pc)
                emb = re.search(r'r:embed="([^"]+)"', pc)
                if b and 0 < b[2] < sw * 0.45 and 0 < b[3] < sh * 0.2:       # 小图：Logo 候选
                    key = tuple(round(v * k) for v in b)
                    t = re.search(rf'Id="{re.escape(emb.group(1))}"[^>]*Target="\.\./media/([^"]+)"', srcrels) if emb else None
                    media = t.group(1) if t and re.search(r"\.(png|jpe?g|svg)$", t.group(1), re.I) else None
                    if media:
                        seen[dark][(key, media)] += 1
        low = text.lower()
        if i == 1 or re.search(r"title slide|cover|封面", lname, re.I):
            kind = "cover"
        elif re.search(r"thank|谢谢|q&a|questions\?", low) or re.search(r"thank|end|结束", lname, re.I):
            kind = "closing"
        elif re.search(r"divider|section|章节|过渡", lname, re.I):
            kind = "divider"
        else:
            kind = "content-dark" if dark else "content"
        pages.append({"no": i, "layout": lname, "background": bgc, "dark": dark, "kind": kind,
                      "text": re.sub(r"\s+", " ", text)[:60]})
    rep["pages"] = pages
    kinds = collections.Counter(p["kind"] for p in pages)
    rep["page_kinds"] = dict(kinds)

    both = seen[False] + seen[True]
    if both:
        # 看图本身：可见像素很亮（> 0.6）的是白字版，给深底；其余给浅底。读不出亮度的（JPG、SVG）按出现的底色分。
        light_for, dark_for = collections.Counter(), collections.Counter()
        for (box, media), n_ in both.items():
            ink = png_ink(z.read("ppt/media/" + media)) if media.lower().endswith(".png") else None
            on_dark = ink > 0.6 if ink is not None else seen[True][(box, media)] > seen[False][(box, media)]
            (dark_for if on_dark else light_for)[(box, media)] += n_
        if dark_for:
            (dbox, dmedia), dn = dark_for.most_common(1)[0]
            rep["logo_on_dark"] = {"box": list(dbox), "pages_seen": dn, "media": dmedia, "for": "深底"}
        if light_for:
            # 用得一样多时，取和深底版同一尺寸的那一版：两版 Logo 换着用时大小一致
            dsize = tuple(rep["logo_on_dark"]["box"][2:]) if rep.get("logo_on_dark") else None
            (box, media), n_ = max(light_for.items(), key=lambda kv: (kv[1], kv[0][0][2:] == dsize))
            rep["logo"] = {"box": list(box), "pages_seen": n_, "media": media, "for": "浅底"}
        if not light_for:
            rep["logo"] = dict(rep.pop("logo_on_dark"), **{"for": "深底"})
            rep["notes"].append("只找到白字版 Logo（给深底用）：浅底页上会看不清，请在名片里另传一版浅底用的 Logo")
    else:
        rep["logo"] = None
        rep["notes"].append("没有找到反复出现的小图，可能模板里没有放 Logo；律所风格会用名片里的 Logo")

    # 颜色用量（slide 里直接写的 + 主题色引用），按角色归类
    use = collections.Counter()
    for n in slides:
        x = txt(n)
        use.update(hex6(c) for c in re.findall(r'srgbClr val="([0-9A-Fa-f]{6})"', x))
        for c in re.findall(r'<a:schemeClr val="(\w+)"', x):
            h = scheme.get(alias.get(c, c))
            if h:
                use[h] += 1
    primary = scheme.get("accent1")
    bgw = scheme.get("lt1", "#FFFFFF")
    # 正文色以母版的正文样式为准（模板作者定的）；主题里的「文字 1」常是纯黑，用得多但多半只是默认值
    roles = {"background": bgw, "primary": primary, "primary_dark": None, "text": rep["type"]["body"]["color"], "tints": [],
             "neutrals": [], "secondary": []}
    for c, n_ in use.most_common():
        if c in (bgw, primary) or n_ < 3:
            continue
        l, s = hls(c)[1], hls(c)[2]
        if primary and s >= 0.08 and hue_dist(c, primary) < 0.06:     # 主色同色系（浅色调饱和度低，先认它）
            if l < hls(primary)[1] and roles["primary_dark"] is None:
                roles["primary_dark"] = c
            elif l > 0.75:
                roles["tints"].append(c)
            continue
        if s < 0.2:                                     # 灰（带一点冷暖的灰也算灰）
            if c == roles["text"]:
                continue
            if l < 0.5 and roles["text"] is None:
                roles["text"] = c
            elif l < 0.95:
                roles["neutrals"].append(c)
            continue
        roles["secondary"].append(c)
    roles["text"] = roles["text"] or rep["type"]["body"]["color"]
    rep["colors"] = {"roles": roles, "usage": [[c, n_] for c, n_ in use.most_common(24)]}

    # 可读性
    checks = []
    tc = rep["type"]["title"]["color"] or primary
    for what, a, b, need in (("标题色在白底上", tc, bgw, 4.5), ("正文色在白底上", roles["text"], bgw, 4.5),
                             ("白字在主色底上（封面、章节页）", "#FFFFFF", primary, 4.5)):
        if a and b:
            r = contrast(a, b)
            checks.append({"what": what, "fg": a, "bg": b, "ratio": round(r, 2), "ok": r >= need})
    for t in roles["tints"][:2]:
        r = contrast(roles["text"] or "#333333", t)
        checks.append({"what": f"正文色在浅色调 {t} 上", "fg": roles["text"], "bg": t, "ratio": round(r, 2), "ok": r >= 4.5})
    rep["checks"] = checks
    if rep["type"]["body"]["size_px"] and rep["type"]["body"]["size_px"] < 16:
        rep["notes"].append(f"正文字号 {rep['type']['body']['size_px']}px，小于 V7 的正文下限 16px：投影时偏小，V7 会用 16px 以上")
    return rep, z


# ------------------------------------------------------------- 报告
def render_thumbs(path, outdir, every=1):
    if not shutil.which("soffice") or not shutil.which("pdftoppm"):
        return []
    td = tempfile.mkdtemp()
    try:
        subprocess.run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", td, path], capture_output=True, timeout=600)
        pdf = os.path.join(td, os.path.splitext(os.path.basename(path))[0] + ".pdf")
        if not os.path.exists(pdf):
            return []
        subprocess.run(["pdftoppm", "-r", "24", "-png", pdf, os.path.join(td, "p")], capture_output=True, timeout=600)
        fs = sorted(f for f in os.listdir(td) if f.startswith("p-") and f.endswith(".png"))
        return [base64.b64encode(open(os.path.join(td, f), "rb").read()).decode() for f in fs]
    finally:
        shutil.rmtree(td, ignore_errors=True)


def report_html(rep, thumbs, logo_uri):
    e = lambda s: html.escape(str(s))
    roles = rep["colors"]["roles"]
    usage = dict(rep["colors"]["usage"])

    def sw(c, label):
        if not c:
            return ""
        fg = "#FFFFFF" if luminance(c) < 0.35 else "#1F2933"
        return (f'<div class="sw"><div class="chip" style="background:{c};color:{fg}">{c}</div>'
                f'<div class="lab">{e(label)}<br><span>用了 {usage.get(c, 0)} 次</span></div></div>')
    g = rep["geometry"]
    boxes = ""
    for key, zh, col in (("title", "标题", "#702082"), ("body", "内容区", "#6B7280"), ("footer", "页脚", "#9CA3AF"),
                         ("page_no", "页码", "#9CA3AF")):
        b = g.get(key)
        if b:
            right = key in ("title", "body", "page_no")    # 这几个框的字靠右写：不和 Logo、页脚的字挤在一起
            lx = b[0] + b[2] - 8 if right else b[0] + 8
            ly = b[1] - 10 if key in ("footer", "page_no") else b[1] + b[3] + 30 if key == "title" else b[1] + 34
            # 不在 f-string 里套同一种引号：Python 3.11 不认（用户电脑上是 3.11，V2 的回归会抓）
            anchor = ' text-anchor="end"' if right else ""
            label = zh if key == "page_no" else f"{zh} {b[0]},{b[1]} · {b[2]}×{b[3]}"
            boxes += (f'<rect x="{b[0]}" y="{b[1]}" width="{b[2]}" height="{b[3]}" fill="none" stroke="{col}" stroke-width="3" stroke-dasharray="10 6"/>'
                      f'<text x="{lx}" y="{ly}" font-size="22" fill="{col}"{anchor}>{label}</text>')
    if rep.get("logo"):
        b = rep["logo"]["box"]
        boxes += (f'<rect x="{b[0]}" y="{b[1]}" width="{b[2]}" height="{b[3]}" fill="none" stroke="#B42318" stroke-width="3"/>'
                  f'<text x="{b[0] + b[2] + 14}" y="{b[1] - 12}" font-size="22" fill="#B42318">Logo {b[0]},{b[1]} · {b[2]}×{b[3]}</text>')
    t, bdy = rep["type"]["title"], rep["type"]["body"]
    kinds_zh = {"cover": "封面", "divider": "章节页", "content": "内容页（白底）", "content-dark": "内容页（深底）", "closing": "结束页"}
    groups = collections.defaultdict(list)
    for p in rep["pages"]:
        groups[p["kind"]].append(p)
    pages_html = ""
    for kd in ("cover", "divider", "content", "content-dark", "closing"):
        ps = groups.get(kd) or []
        if not ps:
            continue
        cells = ""
        for p in ps[:12]:
            no, bg = p["no"], p["background"]
            pic = ("<img src=data:image/png;base64," + thumbs[no - 1] + ">") if thumbs and no <= len(thumbs) \
                else '<div class=ph style="background:' + bg + '"></div>'
            cells += "<figure>" + pic + "<figcaption>" + str(no) + " · " + e(p["layout"][:18]) + "</figcaption></figure>"
        more = f'<p class="muted">另有 {len(ps) - 12} 页</p>' if len(ps) > 12 else ""
        pages_html += f'<h3>{kinds_zh[kd]} · {len(ps)} 页</h3><div class="grid">{cells}</div>{more}'
    checks = ""
    for c in rep["checks"]:
        fg, bg, cls, word = c["fg"], c["bg"], ("ok" if c["ok"] else "bad"), ("过" if c["ok"] else "偏低")
        checks += (f'<tr><td>{e(c["what"])}</td><td><span class="dot" style="background:{fg}"></span>{fg} / '
                   f'<span class="dot" style="background:{bg}"></span>{bg}</td><td>{c["ratio"]}</td>'
                   f'<td class="{cls}">{word}</td></tr>')
    logo_seen = (f'Logo 在 {rep["logo"]["pages_seen"]} 页的同一位置出现。' if rep.get("logo") else "")
    prim = rep["colors"]["roles"]["primary"]
    logos_html = "".join(
        '<p>读出的 Logo（' + w + '用）：<img src="' + u + '" alt="Logo" style="height:40px;vertical-align:middle;padding:6px;'
        'border-radius:6px;background:' + (prim if w == "深底" else "#FFFFFF") + ';border:1px solid #E5E7EB"></p>' for w, u in logo_uri)
    secondary_html = "".join(sw(c, "辅助色") for c in roles["secondary"][:8]) or '<span class="muted">没有</span>'
    neutral_html = "".join(sw(c, "灰") for c in roles["neutrals"][:5]) or '<span class="muted">没有</span>'
    tints_html = "".join(sw(c, "浅色调") for c in roles["tints"][:4])
    no_cjk = " · <span class=bad>没有指定中文字体</span>"
    t_cjk = (" · 中文：" + e(t["font_cjk"])) if t["font_cjk"] else no_cjk
    b_cjk = (" · 中文：" + e(bdy["font_cjk"])) if bdy["font_cjk"] else no_cjk
    t_bold = " · 粗体" if t["bold"] else ""
    b_bullet = e(bdy["bullet"] or "无")
    is169 = "（16:9）" if rep["slide"]["is_16_9"] else ""
    notes = "".join(f"<li>{e(n)}</li>" for n in rep["notes"])
    no_notes = "<li>没有</li>"
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>模板读取报告</title><style>
:root{{--ink:#1F2933;--ink2:#6B7280;--line:#E5E7EB;--bg:#F6F7F9;--card:#FFF}}
@media (prefers-color-scheme:dark){{:root:not([data-theme=light]){{--ink:#ECEEF1;--ink2:#A2A8B1;--line:#333840;--bg:#15171A;--card:#1E2125}}}}
body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.65 "PingFang SC","Microsoft YaHei","Noto Sans CJK SC",sans-serif}}
main{{max-width:1080px;margin:0 auto;padding:28px 16px 60px}} h1{{font-size:26px;margin:0 0 4px}} h2{{font-size:19px;margin:34px 0 12px}} h3{{font-size:15px;margin:20px 0 8px;color:var(--ink2)}}
.muted{{color:var(--ink2);font-size:13px}} .card{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px 18px}}
.sws{{display:flex;flex-wrap:wrap;gap:12px}} .sw{{width:150px}} .chip{{height:64px;border-radius:10px;display:flex;align-items:flex-end;padding:8px;font:12px ui-monospace,monospace;border:1px solid var(--line)}}
.lab{{font-size:13px;margin-top:6px}} .lab span{{color:var(--ink2);font-size:12px}}
table{{border-collapse:collapse;width:100%;font-size:14px}} td,th{{border-bottom:1px solid var(--line);padding:8px 6px;text-align:left;vertical-align:top}}
.ok{{color:#1E7B4F;font-weight:600}} .bad{{color:#B42318;font-weight:600}} .dot{{display:inline-block;width:11px;height:11px;border-radius:3px;margin:0 4px -1px 0;border:1px solid var(--line)}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px}} figure{{margin:0}} figure img,.ph{{width:100%;aspect-ratio:16/9;display:block;border-radius:6px;border:1px solid var(--line)}}
figcaption{{font-size:11.5px;color:var(--ink2);margin-top:3px}} svg.geo{{width:100%;height:auto;background:#fff;border-radius:10px;border:1px solid var(--line)}}
.two{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:14px}} code{{font:13px ui-monospace,monospace}}
</style></head><body><main>
<h1>模板读取报告</h1><p class="muted">{e(rep["source"])} · 主题「{e(rep["theme"]["name"])}」 · {len(rep["pages"])} 页 · {rep["slide"]["w"]}×{rep["slide"]["h"]}{is169}。这一步只读、不生成；请核对读得准不准。</p>

<h2>颜色</h2><div class="card"><div class="sws">
{sw(roles["primary"], "主色")}{sw(roles["primary_dark"], "主色·深")}{sw(roles["text"], "正文灰")}{sw(roles["background"], "底色")}
{tints_html}
</div><h3>辅助色（模板里个别页用到）</h3><div class="sws">{secondary_html}</div>
<h3>中性灰</h3><div class="sws">{neutral_html}</div></div>

<h2>字体与字号</h2><div class="two">
<div class="card"><b>标题</b><p>{e(t["font"])}{t_cjk}<br>
{t["size_pt"]}pt（约 {t["size_px"]}px）{t_bold} · <span class="dot" style="background:{t["color"]}"></span>{t["color"]}</p></div>
<div class="card"><b>正文</b><p>{e(bdy["font"])}{b_cjk}<br>
{bdy["size_pt"]}pt（约 {bdy["size_px"]}px）· 项目符号「{b_bullet}」 · <span class="dot" style="background:{bdy["color"]}"></span>{bdy["color"]}</p></div></div>

<h2>版面几何</h2><div class="card"><svg class="geo" viewBox="0 0 1280 720" role="img"><title>版面几何</title>{boxes}</svg>
<p class="muted">页边距：左 {g.get("margin_left")} · 右 {g.get("margin_right")} · 上 {g.get("margin_top")} · 下 {g.get("margin_bottom")}（1280×720 设计像素）。
{logo_seen}</p>
{logos_html}</div>

<h2>页型</h2>{pages_html}

<h2>可读性</h2><div class="card"><table><tr><th>检查</th><th>颜色</th><th>对比度</th><th></th></tr>{checks}</table>
<p class="muted">对比度 4.5 以上，投影和打印都看得清（WCAG AA）。</p></div>

<h2>要注意的</h2><div class="card"><ul>{notes or no_notes}</ul></div>
</main></body></html>"""


def run(pptx, out, render=False):
    """读模板，写 tokens.json、report.html 与取出的 Logo 到 out。返回读出的结果（同 tokens.json）。
    读不了抛 ValueError。编辑器「适配 → 自定义」里上传模板走这里，命令行也走这里。"""
    try:
        rep, z = read(pptx)
    except (zipfile.BadZipFile, KeyError, AttributeError) as ex:
        raise ValueError(f"读不了这份模板：{ex}（是不是 .pptx？老式 .ppt 请先另存为 .pptx）")
    os.makedirs(out, exist_ok=True)
    logo_uri = []
    for key, stem in (("logo", "logo"), ("logo_on_dark", "logo-on-dark")):
        if not (rep.get(key) and rep[key].get("media")):
            continue
        data = z.read("ppt/media/" + rep[key]["media"])
        ext = os.path.splitext(rep[key]["media"])[1].lower()
        fn = stem + ext
        with open(os.path.join(out, fn), "wb") as f:
            f.write(data)
        rep[key]["file"] = fn
        if ext in (".png", ".jpg", ".jpeg"):
            logo_uri.append((rep[key]["for"], f"data:image/{'png' if ext == '.png' else 'jpeg'};base64," + base64.b64encode(data).decode()))
    thumbs = render_thumbs(pptx, out) if render else []
    with open(os.path.join(out, "tokens.json"), "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=1)
    with open(os.path.join(out, "report.html"), "w", encoding="utf-8") as f:
        f.write(report_html(rep, thumbs, logo_uri))
    return rep


def main(argv=None):
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="读懂一份律所 PPT 模板（只读、只报告）")
    ap.add_argument("pptx")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--render", action="store_true")
    a = ap.parse_args(argv)
    try:
        rep = run(a.pptx, a.out, a.render)
    except ValueError as ex:
        print(str(ex), file=sys.stderr)
        return 1
    r = rep["colors"]["roles"]
    print(f"已读：{rep['source']}，{len(rep['pages'])} 页；主色 {r['primary']}，正文 {r['text']}；"
          f"标题 {rep['type']['title']['font'] or '未写'} {str(rep['type']['title']['size_pt']) + 'pt' if rep['type']['title']['size_pt'] else '（字号未写）'}；"
          f"页型 {rep['page_kinds']}")
    for n in rep["notes"]:
        print("  注意　" + n)
    print(f"报告：{os.path.join(a.out, 'report.html')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
