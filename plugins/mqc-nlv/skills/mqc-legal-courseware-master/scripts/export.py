# -*- coding: utf-8 -*-
"""课件 → 一份 PPTX，每页每个元素都可编辑。

做法：每一页先拼成一张 1280 × 720 的 SVG（与编辑器预览同一个函数），交给 V6 的 pptx_ready（矩形还原成原生
圆角矩形、曲线细分、半透明代号色）→ V1 的导出器（SVG → 文字框与形状）→ V6 的 apply_alpha（写回透明度），
得到一页的 PPTX；最后把各页合成一份。V1、V6 的代码只调用、不改。

导出前先过一遍：任何一页有问题（图表守卫没过、字放不下、风格不一致）就不出——与 V6 的「守卫不过不交付」一致。
导出后再回读：页数对、没有一张位图（全可编辑）、颜色只用风格原色、课件里写的字都在。
"""
import os
import re
import tempfile
import zipfile
import xml.etree.ElementTree as ET

import paths  # noqa: F401
import deck as D

NS_P = "http://schemas.openxmlformats.org/presentationml/2006/main"
NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
REL_SLIDE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide"
REL_IMAGE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"
EMU = 9525                       # 1 设计像素 = 9525 EMU（1280 px ↔ 12192000 EMU，与 V1 导出器一致）
LOGO_MEDIA = "nlv_logo_"         # PPTX 里唯一允许的图片：律所 Logo（作者定的例外，见 ADR 0003）
CT_SLIDE = "application/vnd.openxmlformats-officedocument.presentationml.slide+xml"


class ExportError(RuntimeError):
    pass

# 标题字（0.9.0）：只认这几种名字。编辑器确认本机装了方正小标宋，才让 PPT 里的标题用它（不加粗）；
# 没装就照旧用安全字体里的宋体加粗——在别人电脑上也不变样。
TITLE_FACES = ("方正小标宋简体",)


def _one_slide(svg, workdir, k, fonts, title_face=None):
    import make                                          # V6
    import export_pptx                                   # V1
    ready, alpha = make.pptx_ready(svg)
    sp = os.path.join(workdir, f"s{k}.svg")
    pp = os.path.join(workdir, f"s{k}.pptx")
    with open(sp, "w", encoding="utf-8", newline="\n") as f:
        f.write(ready)
    export_pptx.export(sp, pp, fonts=fonts, title_face=title_face if title_face in TITLE_FACES else None)
    make.apply_alpha(pp, alpha)
    with zipfile.ZipFile(pp) as z:
        return {n: z.read(n) for n in z.namelist()}


_IMG = re.compile(r'<image x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" height="([\d.]+)" '
                  r'href="data:image/(png|jpeg);base64,([A-Za-z0-9+/=]+)"[^>]*data-logo="1"[^>]*/>')


def lift_logos(svg):
    """把页里的位图 Logo 摘出来（V1 导出器只画形状与文字）。返回 (去掉 Logo 的 svg, [(x, y, w, h, 扩展名, 字节)])。"""
    import base64
    found = []

    def take(m):
        x, y, w, h = (float(m.group(i)) for i in range(1, 5))
        found.append((x, y, w, h, "png" if m.group(5) == "png" else "jpeg", base64.b64decode(m.group(6))))
        return ""
    return _IMG.sub(take, svg), found


def put_logos(part, logos, k):
    """把 Logo 作为图片放回第 k 页（单页 PPTX 的部件字典里改 slide1）。"""
    if not logos:
        return part
    x = part["ppt/slides/slide1.xml"].decode("utf-8")
    rels = part["ppt/slides/_rels/slide1.xml.rels"].decode("utf-8")
    pics, addrels = [], []
    for j, (lx, ly, lw, lh, ext, data) in enumerate(logos, 1):
        fn = f"{LOGO_MEDIA}s{k}_{j}.{'png' if ext == 'png' else 'jpg'}"
        part["ppt/media/" + fn] = data
        rid = f"rIdLogo{j}"
        addrels.append(f'<Relationship Id="{rid}" Type="{REL_IMAGE}" Target="../media/{fn}"/>')
        pics.append(
            f'<p:pic><p:nvPicPr><p:cNvPr id="{9000 + j}" name="Logo {j}" descr="Logo"/><p:cNvPicPr><a:picLocks noChangeAspect="1"/>'
            f'</p:cNvPicPr><p:nvPr/></p:nvPicPr><p:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch>'
            f'</p:blipFill><p:spPr><a:xfrm><a:off x="{round(lx * EMU)}" y="{round(ly * EMU)}"/>'
            f'<a:ext cx="{round(lw * EMU)}" cy="{round(lh * EMU)}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
            f'</p:spPr></p:pic>')
    x = x.replace("</p:spTree>", "".join(pics) + "</p:spTree>", 1)
    rels = rels.replace("</Relationships>", "".join(addrels) + "</Relationships>", 1)
    part["ppt/slides/slide1.xml"] = x.encode("utf-8")
    part["ppt/slides/_rels/slide1.xml.rels"] = rels.encode("utf-8")
    return part


# ------------------------------------------------------------- 粘贴友好：律师把这一页复制进自己的课件
# 作者定的（2026-10-05）：V7 只做法律图表页，导出的 PPTX 是给律师复制进自己课件用的。所以：
#   * 整页底色不画成形状，写成页面背景——整页粘贴（用目标主题）时露出他自己的母版（Logo、页脚），
#     框选粘贴时也不会带走一块白板；
#   * 每个构件（标题、图、说明、依据……）打成一组，点一下就选中整张图，复制、挪动都不散；
#   * 颜色、字体都写在形状上（V1 导出器本来就这样），不用主题色、不用占位符——粘过去不变色、不跑位。
SLIDE_W, SLIDE_H = 1280 * EMU, 720 * EMU
_PAPER = re.compile(r'<rect width="1280" height="720" fill="(#[0-9A-Fa-f]{6})" data-role="paper"/>')
for _pfx, _uri in (("a", NS_A), ("p", NS_P), ("r", "http://schemas.openxmlformats.org/officeDocument/2006/relationships")):
    ET.register_namespace(_pfx, _uri)


def _q(ns, tag):
    return f"{{{ns}}}{tag}"


def _box(el):
    """顶层形状的外框（EMU）：(x, y, w, h)；读不到返回 None。"""
    xf = el.find(f".//{_q(NS_A, 'xfrm')}")
    if xf is None:
        return None
    off, ext = xf.find(_q(NS_A, "off")), xf.find(_q(NS_A, "ext"))
    if off is None or ext is None:
        return None
    return (int(off.get("x")), int(off.get("y")), int(ext.get("cx")), int(ext.get("cy")))


def _has_text(el):
    return any((t.text or "").strip() for t in el.iter(_q(NS_A, "t")))


def paste_ready(part, mods, paper, g=None, anchors=None):
    """单页 PPTX 的部件字典 → 粘贴友好的版本（就地改 slide1.xml）。mods：这一页的模块（带 x/y/w/h）。"""
    import grid as G
    root = ET.fromstring(part["ppt/slides/slide1.xml"])
    csld = root.find(_q(NS_P, "cSld"))
    tree = csld.find(_q(NS_P, "spTree"))
    kids = [k for k in list(tree) if k.tag not in (_q(NS_P, "nvGrpSpPr"), _q(NS_P, "grpSpPr"))]
    # 1) 开头那几块整页大小、没有字的形状（页面底色、底纹）去掉，底色写成页面背景
    for k in kids:
        b = _box(k)
        if b and b[0] <= 0 and b[1] <= 0 and b[2] >= SLIDE_W and b[3] >= SLIDE_H and not _has_text(k):
            tree.remove(k)
        else:
            break
    if paper:
        bg = ET.Element(_q(NS_P, "bg"))
        bgpr = ET.SubElement(bg, _q(NS_P, "bgPr"))
        ET.SubElement(ET.SubElement(bgpr, _q(NS_A, "solidFill")), _q(NS_A, "srgbClr"), val=paper.lstrip("#").upper())
        ET.SubElement(bgpr, _q(NS_A, "effectLst"))
        csld.insert(0, bg)
    # 2) 每个构件打成一组：形状的中心落在哪个模块的格子里，就归哪个模块（模块之间不重叠）
    kids = [k for k in list(tree) if k.tag not in (_q(NS_P, "nvGrpSpPr"), _q(NS_P, "grpSpPr"))]
    ids = [int(c.get("id")) for c in tree.iter(_q(NS_P, "cNvPr")) if (c.get("id") or "").isdigit()]
    next_id = max(ids + [1]) + 1
    slots = []
    for m in mods:
        x, y, w, h = G.px(m, g)
        pad = G.GUT / 2                          # 连成一组的卡片会外扩到间距里
        slots.append((m, ((x - pad) * EMU, (y - pad) * EMU, (x + w + pad) * EMU, (y + h + pad) * EMU)))
    members = {m["id"]: [] for m in mods}
    for k in kids:
        b = _box(k)
        if not b:
            continue
        cx, cy = b[0] + b[2] / 2, b[1] + b[3] / 2
        hit = next((m for m, (x0, y0, x1, y1) in slots if x0 <= cx <= x1 and y0 <= cy <= y1), None)
        if hit:
            members[hit["id"]].append(k)
    groups = 0
    def make_group(ks, name, descr):
        nonlocal next_id
        bs = [_box(k) for k in ks]
        x0, y0 = min(b[0] for b in bs), min(b[1] for b in bs)
        x1, y1 = max(b[0] + b[2] for b in bs), max(b[1] + b[3] for b in bs)
        g = ET.Element(_q(NS_P, "grpSp"))
        nv = ET.SubElement(g, _q(NS_P, "nvGrpSpPr"))
        ET.SubElement(nv, _q(NS_P, "cNvPr"), id=str(next_id), name=name, descr=descr)
        next_id += 1
        ET.SubElement(nv, _q(NS_P, "cNvGrpSpPr"))
        ET.SubElement(nv, _q(NS_P, "nvPr"))
        gp = ET.SubElement(ET.SubElement(g, _q(NS_P, "grpSpPr")), _q(NS_A, "xfrm"))
        for tag, a_, b_ in (("off", x0, y0), ("ext", x1 - x0, y1 - y0), ("chOff", x0, y0), ("chExt", x1 - x0, y1 - y0)):
            ET.SubElement(gp, _q(NS_A, tag), **({"x": str(a_), "y": str(b_)} if "ff" in tag.lower()
                                                 else {"cx": str(a_), "cy": str(b_)}))
        return g

    def anchor_of(k, ans):
        """形状落在哪个图内元素里：中心点在元素外框内（外扩 3px），取面积最小的那个（节点比包住它的长关系线优先）。"""
        b = _box(k)
        if not b:
            return None
        cx, cy = b[0] + b[2] / 2, b[1] + b[3] / 2
        area = b[2] * b[3]                         # 比元素范围大一倍以上的形状（卡片底色、整张图的框）不归它
        hit = [a for a in ans if (a["box"][0] - 3) * EMU <= cx <= (a["box"][0] + a["box"][2] + 3) * EMU
               and (a["box"][1] - 3) * EMU <= cy <= (a["box"][1] + a["box"][3] + 3) * EMU
               and area <= 2 * max(1.0, a["box"][2] * a["box"][3]) * EMU * EMU + 1]
        return min(hit, key=lambda a: a["box"][2] * a["box"][3]) if hit else None

    for m in mods:
        ks = members[m["id"]]
        if len(ks) < 2:
            continue
        zh = G.TYPES.get(m["type"], {}).get("zh", m["type"])
        g = make_group(ks, f"{zh} {m['id']}", f"nlv-group:{m['id']}")
        pos = list(tree).index(ks[0])
        for k in ks:
            tree.remove(k)
        # 图里的每个元素（事件、主体、关系、柱子）再各成一组、按名字命名：在 PowerPoint 里能逐个加动画、逐个讲
        ans = (anchors or {}).get(m["id"]) or []
        buckets, order = {}, []
        for k in ks:
            a = anchor_of(k, ans) if ans else None
            if a is None:
                order.append(k)
                continue
            if a["key"] not in buckets:
                buckets[a["key"]] = (a, [])
                order.append(a["key"])
            buckets[a["key"]][1].append(k)
        for item in order:
            if not isinstance(item, str):
                g.append(item)
                continue
            a, kids = buckets[item]
            nm = a["label"] or a["key"]
            if len(kids) == 1:
                c = kids[0].find(f".//{_q(NS_P, 'cNvPr')}")
                c.set("name", nm)
                c.set("descr", f"nlv-anchor:{a['key']}")
                g.append(kids[0])
            else:
                sub = make_group(kids, nm, f"nlv-anchor:{a['key']}")
                for k in kids:
                    sub.append(k)
                g.append(sub)
                groups += 1
        tree.insert(pos, g)
        groups += 1
    xml = ET.tostring(root, encoding="unicode")
    if "xmlns:r=" not in xml:                    # ET 只写用到的命名空间；r 留着，以后往这页加图片、链接不出错
        xml = xml.replace("<p:sld ", '<p:sld xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" ', 1)
    part["ppt/slides/slide1.xml"] = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' + xml).encode("utf-8")
    return part, groups


# ------------------------------------------------------------- 讲课动画（作者定的方向，2026-10-07）
# 放了读图编号的页：点一下，编号 1 和它指向的元素一起淡入；再点一下，编号 2……没编号的部分一开始就在。
# 写的是 PowerPoint 自己的动画（p:timing，淡入），律师在动画窗格里能改、能删。
def timing_xml(steps):
    """steps：[[形状 id, …], …]，每一项是一次点击要出现的形状。返回 <p:timing>…</p:timing>。"""
    ids = iter(range(3, 10000))
    clicks = []
    for shapes in steps:
        effects = []
        for k, spid in enumerate(shapes):
            a, b, c = next(ids), next(ids), next(ids)
            effects.append(
                f'<p:par><p:cTn id="{a}" presetID="10" presetClass="entr" presetSubtype="0" fill="hold" grpId="0" '
                f'nodeType="{"clickEffect" if k == 0 else "withEffect"}"><p:stCondLst><p:cond delay="0"/></p:stCondLst><p:childTnLst>'
                f'<p:set><p:cBhvr><p:cTn id="{b}" dur="1" fill="hold"><p:stCondLst><p:cond delay="0"/></p:stCondLst></p:cTn>'
                f'<p:tgtEl><p:spTgt spid="{spid}"/></p:tgtEl><p:attrNameLst><p:attrName>style.visibility</p:attrName></p:attrNameLst>'
                f'</p:cBhvr><p:to><p:strVal val="visible"/></p:to></p:set>'
                f'<p:animEffect transition="in" filter="fade"><p:cBhvr><p:cTn id="{c}" dur="400"/>'
                f'<p:tgtEl><p:spTgt spid="{spid}"/></p:tgtEl></p:cBhvr></p:animEffect></p:childTnLst></p:cTn></p:par>')
        o, i_ = next(ids), next(ids)
        clicks.append(f'<p:par><p:cTn id="{o}" fill="hold"><p:stCondLst><p:cond delay="indefinite"/></p:stCondLst><p:childTnLst>'
                      f'<p:par><p:cTn id="{i_}" fill="hold"><p:stCondLst><p:cond delay="0"/></p:stCondLst><p:childTnLst>'
                      + "".join(effects) + '</p:childTnLst></p:cTn></p:par></p:childTnLst></p:cTn></p:par>')
    return ('<p:timing><p:tnLst><p:par><p:cTn id="1" dur="indefinite" restart="never" nodeType="tmRoot"><p:childTnLst>'
            '<p:seq concurrent="1" nextAc="seek"><p:cTn id="2" dur="indefinite" nodeType="mainSeq"><p:childTnLst>'
            + "".join(clicks) +
            '</p:childTnLst></p:cTn><p:prevCondLst><p:cond evt="onPrev" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl></p:cond>'
            '</p:prevCondLst><p:nextCondLst><p:cond evt="onNext" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl></p:cond>'
            '</p:nextCondLst></p:seq></p:childTnLst></p:cTn></p:par></p:tnLst></p:timing>')


def add_pin_animation(part, pins):
    """pins：这一页各图卡的编号 [{"n", "key"}, …]（已按编号排好）。在 slide1.xml 末尾写入讲课动画。返回步数。"""
    x = part["ppt/slides/slide1.xml"].decode("utf-8")
    ids = {d: i for i, d in re.findall(r'<p:cNvPr id="(\d+)" name="[^"]*" descr="nlv-anchor:([^"]+)"', x)}
    steps = []
    for p_ in pins:
        shapes = [ids[k] for k in (f"pin:{p_['n']}", p_["key"], f"item:{p_['n']}") if k in ids]   # 编号、它指的元素、同号要点
        if shapes:
            steps.append(shapes)
    if not steps:
        return 0
    x = x.replace("</p:sld>", timing_xml(steps) + "</p:sld>", 1)
    part["ppt/slides/slide1.xml"] = x.encode("utf-8")
    return len(steps)


def merge(slides_parts, out_path, notes=None):
    """把若干份一页的 PPTX 合成一份：第一份做底，其余只取 slide1.xml 依次编号。
    V1 导出器出的每一份共用同一套母版、版式、主题，所以只需加页、登记关系与内容类型。"""
    import export_pptx
    base = dict(slides_parts[0])
    n = len(slides_parts)
    for k in range(2, n + 1):
        base[f"ppt/slides/slide{k}.xml"] = slides_parts[k - 1]["ppt/slides/slide1.xml"]
        base[f"ppt/slides/_rels/slide{k}.xml.rels"] = slides_parts[k - 1]["ppt/slides/_rels/slide1.xml.rels"]
    for part in slides_parts[1:]:
        for name, data in part.items():
            if name.startswith("ppt/media/" + LOGO_MEDIA):
                base[name] = data
    pres = base["ppt/presentation.xml"].decode("utf-8")
    ids = "".join(f'<p:sldId id="{255 + k}" r:id="rIdS{k}"/>' for k in range(1, n + 1))
    pres = re.sub(r"<p:sldIdLst>.*?</p:sldIdLst>", f"<p:sldIdLst>{ids}</p:sldIdLst>", pres, flags=re.S)
    base["ppt/presentation.xml"] = pres.encode("utf-8")
    rels = base["ppt/_rels/presentation.xml.rels"].decode("utf-8")
    rels = re.sub(r'<Relationship Id="[^"]+" Type="[^"]+/slide" Target="slides/slide1.xml"/>', "", rels)
    add = "".join(f'<Relationship Id="rIdS{k}" Type="{REL_SLIDE}" Target="slides/slide{k}.xml"/>' for k in range(1, n + 1))
    rels = rels.replace("</Relationships>", add + "</Relationships>")
    base["ppt/_rels/presentation.xml.rels"] = rels.encode("utf-8")
    ct = base["[Content_Types].xml"].decode("utf-8")
    ct = re.sub(r'<Override PartName="/ppt/slides/slide1.xml"[^>]*/>', "", ct)
    add = "".join(f'<Override PartName="/ppt/slides/slide{k}.xml" ContentType="{CT_SLIDE}"/>' for k in range(1, n + 1))
    for ext, mime in (("png", "image/png"), ("jpg", "image/jpeg")):
        if any(n.startswith("ppt/media/") and n.endswith("." + ext) for n in base) and f'Extension="{ext}"' not in ct:
            add += f'<Default Extension="{ext}" ContentType="{mime}"/>'
    ct = ct.replace("</Types>", add + "</Types>")
    base["[Content_Types].xml"] = ct.encode("utf-8")
    if notes:                                         # 要了才写演讲者备注；不要就一个字节都不加
        import notes as N_
        N_.add(base, notes)
    order = ["[Content_Types].xml", "_rels/.rels"] + sorted(k for k in base if k not in ("[Content_Types].xml", "_rels/.rels"))
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        for name in order:
            export_pptx._zip_write(z, name, base[name])
    return out_path


def texts_of(deck, base_dir=None):
    """课件里用户写下的字（标题、要点、数字、金句）：导出后逐条回读核对。"""
    return D.texts_of(deck)


def audit(pptx_path, deck, base_dir=".", paste=True, notes=None):
    """回读：返回问题列表（空 = 过）。notes：要写进演讲者备注的 {第几页: [几行]}，要了就一并核。"""
    bad = []
    with zipfile.ZipFile(pptx_path) as z:
        if notes is not None:
            import notes as N_
            bad += N_.audit(z, notes)
        names = z.namelist()
        slides = sorted((n for n in names if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)),
                        key=lambda n: int(re.findall(r"\d+", n)[0]))
        if len(slides) != len(deck["slides"]):
            bad.append(f"页数不对：课件 {len(deck['slides'])} 页，PPTX 里 {len(slides)} 页")
        pres = z.read("ppt/presentation.xml").decode("utf-8")
        if pres.count("<p:sldId ") != len(deck["slides"]):
            bad.append("presentation.xml 里登记的页数与课件不符")
        alltext = []
        allowed = {c.lstrip("#").upper() for c in D.allowed_colors(deck, base_dir)}
        if any(m.get("focus") for s_ in deck["slides"] for m in s_.get("modules") or []):   # 聚焦调浅的颜色：由原色推出
            import svgimport
            base_ = allowed | _figure_colors(deck, base_dir)
            allowed |= {svgimport.fade_hex(c).lstrip("#").upper() for c in base_}
        for n in slides:
            x = z.read(n).decode("utf-8")
            try:
                ET.fromstring(x)
            except ET.ParseError as e:
                bad.append(f"{n} 不是合法的 XML：{e}")
                continue
            pics = re.findall(r"<p:pic>.*?</p:pic>", x, flags=re.S)
            if any('descr="Logo"' not in pc or not re.search(r'r:embed="rIdLogo\d+"', pc) for pc in pics) \
                    or x.count("<a:blip") != len(pics):
                bad.append(f"{n} 里有位图：V7 的每个元素都应是可编辑的形状或文字（只有律所 Logo 例外）")
            if pics:
                rels = z.read(n.replace("slides/", "slides/_rels/") + ".rels").decode("utf-8")
                if any(f"media/{LOGO_MEDIA}" not in t for t in re.findall(r'Target="([^"]+)"[^>]*/>', rels)
                       if "media/" in t):
                    bad.append(f"{n} 引用了 Logo 以外的图片")
            # 粘贴友好：不用主题色、不用占位符（粘进别人的课件会变色、跑位）；没有整页大小的底色块；图是一组
            if paste and ("schemeClr" in x or "<p:ph" in x):
                bad.append(f"{n} 用了主题色或占位符：粘进别的课件会变色、跑位")
            if paste and re.search(r'<a:off x="0" y="0"\s*/><a:ext cx="{0}" cy="{1}"\s*/>'.format(SLIDE_W, SLIDE_H), x):
                bad.append(f"{n} 有整页大小的底色块：整页粘贴会盖住目标课件的母版，底色应写成页面背景")
            if paste and "<p:bg>" not in x:
                bad.append(f"{n} 没有页面背景")
            k_ = slides.index(n)
            if paste and k_ < len(deck["slides"]):
                for m in deck["slides"][k_].get("modules") or []:
                    if m["type"] in ("chart", "figure") and f'descr="nlv-group:{m["id"]}"' not in x:
                        bad.append(f"{n} 的图「{m['id']}」没打成一组：在 PowerPoint 里没法一下选中整张图")
            if "<p:timing>" in x:                # 讲课动画指向的形状都在这一页上
                have = set(re.findall(r'<p:cNvPr id="(\d+)"', x))
                miss = set(re.findall(r'<p:spTgt spid="(\d+)"', x)) - have
                if miss:
                    bad.append(f"{n} 的讲课动画指向不存在的形状：{'、'.join(sorted(miss))}")
            alltext.append("".join(re.findall(r"<a:t>([^<]*)</a:t>", x)))
            cols = {c.upper() for c in re.findall(r'srgbClr val="([0-9A-Fa-f]{6})"', x)}
            # 页面自己的颜色必须在风格白名单里；V1–V5 的图里的淡色属于那个模块的风格家族，单独登记
            extra = cols - allowed - _figure_colors(deck, base_dir) - _logo_colors(base_dir)
            if extra:
                bad.append(f"{n} 出现了风格之外的颜色：{'、'.join('#' + c for c in sorted(extra))}")
        joined = "".join(alltext).replace(" ", "")
        for t in texts_of(deck, base_dir):
            frag = re.sub(r"\s+", "", t)[:12]
            if frag and frag not in joined:
                bad.append(f"课件里写的字「{t[:16]}」在 PPTX 里找不到")
    return bad


def _logo_colors(base_dir):
    """SVG Logo 转成形状后带着自己的颜色：那是律所的品牌色，不算风格之外。"""
    out = set()
    for dark in (False, True):                          # 浅底版、深底版两版 Logo 都算
        try:
            import brand as B
            info = B.logo_info(B.load(base_dir), dark)
        except Exception:                               # noqa: BLE001 —— 名片读不了时，Logo 本身已被拼页拦下
            continue
        if info and info["kind"] == "svg":
            out |= {c.upper() for c in re.findall(r"#([0-9A-Fa-f]{6})\b", info["svg"])}
    return out


_ACACHE = {}


def _figure_colors(deck, base_dir):
    cs = set()
    for s in deck["slides"]:
        for mod in s.get("modules") or []:
            if mod.get("type") == "figure" and not mod.get("file") and mod.get("data"):   # V5 兼容层现出的图
                import adapt as A
                try:
                    cs |= {c.upper() for c in re.findall(r"#([0-9A-Fa-f]{6})\b", A.render(mod, base_dir, 1152, _ACACHE)[0])}
                except A.AdaptError:
                    pass
                continue
            if mod.get("type") == "figure":
                p = paths.inside(base_dir, mod.get("file") or "")
                if p and os.path.isfile(p):
                    cs |= {c.upper() for c in re.findall(r"#([0-9A-Fa-f]{6})\b", open(p, encoding="utf-8-sig").read())}
    return cs


# V1 导出器（export_pptx.parse_svg）读得懂的元素。拼出来的页里出现别的元素，导出时会被悄悄丢掉
# （0.2.0 开发中撞过：连组卡片画成 <polygon>，PPTX 里那几张卡没了底色）——所以导出前先查，查到就拒。
V1_KINDS = {"svg", "defs", "pattern", "g", "rect", "circle", "line", "path", "text", "tspan", "title", "desc"}


def unsupported(svg):
    """拼好的页里 V1 导出器不认的元素名（去重）。"""
    return sorted({t for t in re.findall(r"<([a-zA-Z][\w:-]*)", svg)} - V1_KINDS)


def pick_pages(deck, pages):
    """只导出其中几页（编辑器的「只导出这一页」）：pages 是从 0 数的页号；返回一份只含这几页的课件。"""
    if pages is None:
        return deck
    n = len(deck["slides"])
    bad = [i for i in pages if not isinstance(i, int) or not 0 <= i < n]
    if bad or not pages:
        raise ExportError(f"要导出的页号不对：{pages}（这份课件共 {n} 页）")
    return dict(deck, slides=[deck["slides"][i] for i in pages])


def build(deck, base_dir, out_path, fonts="safe", cache=None, pages=None, paste=True, animate=True, notes=False,
          title_face=None):
    """返回 (输出路径, 报告)。有问题抛 ExportError，不写半成品。pages：只导出这几页（从 0 数）。
    paste=False 只给测试用：照旧画页码、页脚 Logo、整页底色块（测试拿它冒充一份律所模板）。"""
    D.validate(deck, base_dir)
    full = deck
    deck = pick_pages(deck, pages)
    idxs = pages if pages is not None else range(len(full["slides"]))
    composed = [D.compose(full, i, base_dir, cache, paste) for i in idxs]   # 按原页号拼：报错里的「第几页」对得上
    problems = [p for _, rep in composed for p in rep["problems"]]
    if problems:
        raise ExportError("未导出：有几页还没准备好：\n  " + "\n  ".join(problems))
    warnings = [w for _, rep in composed for w in rep["warnings"]]
    # 箭头定义（<marker>）只给编辑器预览用：导出器直接把 marker-end 变成 PowerPoint 的线端箭头，不读定义
    lifted = [lift_logos(re.sub(r"<defs>(?:<marker\b.*?</marker>)+</defs>", "", svg, flags=re.S)) for svg, _ in composed]
    for k, (svg, _) in enumerate(lifted):
        bad = unsupported(svg)
        if bad:
            raise ExportError(f"第 {k + 1} 页有导出器不认的元素 {'、'.join(bad)}：导出会丢形状，未导出")
    groups = clicks = 0
    import grid as G
    geo = G.geom(deck.get("frame"))
    with tempfile.TemporaryDirectory(prefix="nlv7-") as td:
        parts = []
        for k, (svg, logos) in enumerate(lifted):
            part = put_logos(_one_slide(svg, td, k + 1, fonts, title_face), logos, k + 1)
            m = _PAPER.search(composed[k][0])
            if not paste:
                parts.append(part)
                continue
            ans = {mid: (inf.get("anchors") or []) + [{"key": f"pin:{p_['n']}", "label": f"编号 {p_['n']}", "box": p_["box"]}
                                                      for p_ in inf.get("pins") or []]
                   + [{"key": f"item:{i_['n']}", "label": f"要点 {i_['n']}", "box": i_["box"]} for i_ in inf.get("items") or []]
                   for mid, inf in composed[k][1]["modules"].items() if inf.get("anchors") or inf.get("items")}
            part, g = paste_ready(part, deck["slides"][k].get("modules") or [], m.group(1) if m else None, geo, ans)
            groups += g
            if animate:                      # 讲课动画：点一下出一个编号和它指的元素
                pins = [p_ for inf in composed[k][1]["modules"].values() for p_ in (inf.get("pins") or [])]
                clicks += add_pin_animation(part, sorted(pins, key=lambda p_: p_["n"]))
            parts.append(part)
        tmp_out = os.path.join(td, "deck.pptx")
        note_lines = None
        if notes:                            # 出处写进演讲者备注（只读原模块写好的出处，见 prov.py）
            import notes as N_
            note_lines = {k + 1: N_.lines_for(rep) for k, (_, rep) in enumerate(composed)}
        merge(parts, tmp_out, note_lines)
        bad = audit(tmp_out, deck, base_dir, paste, note_lines)
        if bad:
            raise ExportError("导出后回读没过，未交付：\n  " + "\n  ".join(bad))
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        with open(tmp_out, "rb") as r:
            data = r.read()
        stage = out_path + ".nlv-new"
        with open(stage, "wb") as w:
            w.write(data)
        os.replace(stage, out_path)          # 同目录改名覆盖：不靠删除（WorkBuddy 的沙箱禁删）
    return out_path, {"slides": len(composed), "warnings": warnings, "groups": groups, "clicks": clicks,
                      "notes": sum(1 for v in (note_lines or {}).values() if v)}
