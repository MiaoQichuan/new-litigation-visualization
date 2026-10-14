# -*- coding: utf-8 -*-
"""演讲者备注：把这一页图里每个元素的出处写进 PowerPoint 的「备注」（讲课时演示者视图里看得到，观众看不到）。

只在导出时要了才写（build.py --notes、编辑器导出时勾「出处写进演讲者备注」）；不要就一个字节都不加，
导出的 PPTX 与原来逐字节相同。出处只读原模块写好的（见 prov.py），不编。

结构照 PowerPoint 自己存出来的样子：一份备注母版（带主题）、每页一份备注页（图片占位 + 正文占位），
相互登记关系与内容类型。各部分的写法与 python-pptx 默认模板一致。
"""
import re
from xml.sax.saxutils import escape

NS = ('xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
      'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"')
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/"
CT_MASTER = "application/vnd.openxmlformats-officedocument.presentationml.notesMaster+xml"
CT_NOTES = "application/vnd.openxmlformats-officedocument.presentationml.notesSlide+xml"
CT_THEME = "application/vnd.openxmlformats-officedocument.theme+xml"
XML_HEAD = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'

_GRP = ('<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
        '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>')

MASTER = (XML_HEAD + f'<p:notesMaster {NS}><p:cSld><p:bg><p:bgRef idx="1001"><a:schemeClr val="bg1"/></p:bgRef></p:bg>'
          f'<p:spTree>{_GRP}'
          '<p:sp><p:nvSpPr><p:cNvPr id="2" name="Slide Image Placeholder 1"/><p:cNvSpPr><a:spLocks noGrp="1" noRot="1" noChangeAspect="1"/></p:cNvSpPr>'
          '<p:nvPr><p:ph type="sldImg" idx="2"/></p:nvPr></p:nvSpPr>'
          '<p:spPr><a:xfrm><a:off x="381000" y="685800"/><a:ext cx="6096000" cy="3429000"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
          '<a:noFill/><a:ln w="12700"><a:solidFill><a:prstClr val="black"/></a:solidFill></a:ln></p:spPr></p:sp>'
          '<p:sp><p:nvSpPr><p:cNvPr id="3" name="Notes Placeholder 2"/><p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr>'
          '<p:nvPr><p:ph type="body" sz="quarter" idx="3"/></p:nvPr></p:nvSpPr>'
          '<p:spPr><a:xfrm><a:off x="685800" y="4343400"/><a:ext cx="5486400" cy="4114800"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>'
          '<p:txBody><a:bodyPr vert="horz" lIns="91440" tIns="45720" rIns="91440" bIns="45720" rtlCol="0"/><a:lstStyle/>'
          '<a:p><a:pPr lvl="0"/><a:r><a:rPr lang="zh-CN"/><a:t>备注</a:t></a:r></a:p></p:txBody></p:sp>'
          '</p:spTree></p:cSld>'
          '<p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" accent3="accent3" '
          'accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/>'
          '<p:notesStyle><a:lvl1pPr marL="0" algn="l" defTabSz="914400" rtl="0" eaLnBrk="1" latinLnBrk="0" hangingPunct="1">'
          '<a:defRPr sz="1200" kern="1200"><a:solidFill><a:schemeClr val="tx1"/></a:solidFill>'
          '<a:latin typeface="+mn-lt"/><a:ea typeface="+mn-ea"/><a:cs typeface="+mn-cs"/></a:defRPr></a:lvl1pPr></p:notesStyle>'
          '</p:notesMaster>')


def _para(text):
    return f'<a:p><a:r><a:rPr lang="zh-CN" dirty="0"/><a:t>{escape(text)}</a:t></a:r></a:p>'


def notes_xml(lines):
    body = "".join(_para(t) for t in lines) or '<a:p><a:endParaRPr lang="zh-CN"/></a:p>'
    return (XML_HEAD + f'<p:notes {NS}><p:cSld><p:spTree>{_GRP}'
            '<p:sp><p:nvSpPr><p:cNvPr id="2" name="Slide Image Placeholder 1"/><p:cNvSpPr><a:spLocks noGrp="1" noRot="1" noChangeAspect="1"/></p:cNvSpPr>'
            '<p:nvPr><p:ph type="sldImg"/></p:nvPr></p:nvSpPr><p:spPr/></p:sp>'
            '<p:sp><p:nvSpPr><p:cNvPr id="3" name="Notes Placeholder 2"/><p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr>'
            '<p:nvPr><p:ph type="body" idx="1"/></p:nvPr></p:nvSpPr><p:spPr/>'
            f'<p:txBody><a:bodyPr/><a:lstStyle/>{body}</p:txBody></p:sp>'
            '</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:notes>')


def lines_for(report):
    """一页的拼页报告 → 备注里的几行（这一页图里每个元素的出处）。没有出处就返回空列表。"""
    out = []
    for info in (report.get("modules") or {}).values():
        for key, p in (info.get("prov") or {}).items():
            if p.get("missing"):                       # 没写出处的不往备注里写「没写」：备注是讲课用的
                continue
            head = p.get("head") or key
            src = "；".join(x for x in (p.get("src"), p.get("refs")) if x)
            out.append(f"· {head}：{src}" + (f"「{p['quote']}」" if p.get("quote") else ""))
    return (["出处（从原模块的溯源记录读来，没有改动；讲课前请与材料核对）"] + out) if out else []


def add(base, notes):
    """base：合并好的 PPTX 各部分 {名字: bytes}；notes：{第几页（从 1 数）: [几行字]}。就地加上备注母版与备注页。"""
    notes = {k: v for k, v in notes.items() if v}
    if not notes:
        return base
    base["ppt/notesMasters/notesMaster1.xml"] = MASTER.encode("utf-8")
    base["ppt/theme/theme2.xml"] = base["ppt/theme/theme1.xml"]          # 备注母版要有自己的主题：照抄幻灯片的那一份
    base["ppt/notesMasters/_rels/notesMaster1.xml.rels"] = (
        XML_HEAD + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f'<Relationship Id="rId1" Type="{REL}theme" Target="../theme/theme2.xml"/></Relationships>').encode("utf-8")
    ct_add = (f'<Override PartName="/ppt/notesMasters/notesMaster1.xml" ContentType="{CT_MASTER}"/>'
              f'<Override PartName="/ppt/theme/theme2.xml" ContentType="{CT_THEME}"/>')
    for k, lines in sorted(notes.items()):
        base[f"ppt/notesSlides/notesSlide{k}.xml"] = notes_xml(lines).encode("utf-8")
        base[f"ppt/notesSlides/_rels/notesSlide{k}.xml.rels"] = (
            XML_HEAD + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'<Relationship Id="rId1" Type="{REL}notesMaster" Target="../notesMasters/notesMaster1.xml"/>'
            f'<Relationship Id="rId2" Type="{REL}slide" Target="../slides/slide{k}.xml"/></Relationships>').encode("utf-8")
        sr = f"ppt/slides/_rels/slide{k}.xml.rels"
        base[sr] = base[sr].decode("utf-8").replace(
            "</Relationships>", f'<Relationship Id="rIdNotes" Type="{REL}notesSlide" Target="../notesSlides/notesSlide{k}.xml"/></Relationships>'
        ).encode("utf-8")
        ct_add += f'<Override PartName="/ppt/notesSlides/notesSlide{k}.xml" ContentType="{CT_NOTES}"/>'
    ct = base["[Content_Types].xml"].decode("utf-8")
    base["[Content_Types].xml"] = ct.replace("</Types>", ct_add + "</Types>").encode("utf-8")
    pres = base["ppt/presentation.xml"].decode("utf-8")
    pres = pres.replace("</p:sldMasterIdLst>", '</p:sldMasterIdLst><p:notesMasterIdLst><p:notesMasterId r:id="rIdNM1"/></p:notesMasterIdLst>', 1)
    base["ppt/presentation.xml"] = pres.encode("utf-8")
    rels = base["ppt/_rels/presentation.xml.rels"].decode("utf-8")
    base["ppt/_rels/presentation.xml.rels"] = rels.replace(
        "</Relationships>", f'<Relationship Id="rIdNM1" Type="{REL}notesMaster" Target="notesMasters/notesMaster1.xml"/></Relationships>'
    ).encode("utf-8")
    return base


def audit(z, notes):
    """导出后回读：要写的备注都在、XML 合法、关系与内容类型登记齐。z 是打开的 ZipFile。返回问题列表。"""
    import xml.etree.ElementTree as ET
    bad = []
    names = set(z.namelist())
    want = {k for k, v in notes.items() if v}
    have = {int(n) for n in re.findall(r"ppt/notesSlides/notesSlide(\d+)\.xml", " ".join(names))}
    if have != want:
        bad.append(f"演讲者备注的页对不上：要写第 {sorted(want)} 页，PPTX 里是 {sorted(have)}")
    if want:
        ct = z.read("[Content_Types].xml").decode("utf-8")
        for part in ["ppt/notesMasters/notesMaster1.xml"] + [f"ppt/notesSlides/notesSlide{k}.xml" for k in want]:
            if part not in names:
                bad.append(f"缺 {part}")
                continue
            try:
                ET.fromstring(z.read(part))
            except ET.ParseError as e:
                bad.append(f"{part} 不是合法的 XML：{e}")
            if f'PartName="/{part}"' not in ct:
                bad.append(f"{part} 没登记内容类型")
        if "notesMasterIdLst" not in z.read("ppt/presentation.xml").decode("utf-8"):
            bad.append("presentation.xml 没登记备注母版")
        for k in want:
            if f"notesSlide{k}.xml" not in z.read(f"ppt/slides/_rels/slide{k}.xml.rels").decode("utf-8"):
                bad.append(f"第 {k} 页没挂上备注")
    return bad
