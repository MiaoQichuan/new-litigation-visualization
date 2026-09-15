#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Word 后处理：docx 库写不出的三件事，在 OOXML 层补。
这一步不是可选项——不做的话，中英文之间会自动加空、引号与省略号跑成西文、字号回到默认。

  W1 rPrDefault 字体三槽：eastAsia=宋体，ascii/hAnsi/cs=Times New Roman
  W2 autoSpaceDE / autoSpaceDN 置 0：中英文之间不自动加空
     注意 CT_PPrBase 的子元素次序是 schema 强制的，autoSpace 必须排在 spacing 之前
  W3 所有 run 级 rFonts 补 hint="eastAsia"：引号、省略号、书名号等通用标点区的
     歧义字符归中文字体（run 级会盖掉文档默认，所以必须逐个补）
"""
import re, sys, os, shutil, zipfile, tempfile

RPR = ('<w:rPrDefault><w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" '
       'w:cs="Times New Roman" w:eastAsia="宋体" w:hint="eastAsia"/>'
       '<w:sz w:val="{sz}"/><w:szCs w:val="{sz}"/></w:rPr></w:rPrDefault>')
PPR = ('<w:pPrDefault><w:pPr><w:autoSpaceDE w:val="0"/><w:autoSpaceDN w:val="0"/>'
       '<w:spacing w:line="240" w:lineRule="auto"/></w:pPr></w:pPrDefault>')

def postprocess(src, dst, sz=23):
    tmp = tempfile.mkdtemp()
    with zipfile.ZipFile(src) as z: z.extractall(tmp)
    p = os.path.join(tmp, "word", "styles.xml"); s = open(p, encoding="utf-8").read()
    if "<w:rPrDefault/>" not in s or "<w:pPrDefault/>" not in s:
        raise RuntimeError("styles.xml 的 docDefaults 不是预期形态，拒绝盲改")
    s = s.replace("<w:rPrDefault/>", RPR.format(sz=sz), 1).replace("<w:pPrDefault/>", PPR, 1)
    open(p, "w", encoding="utf-8").write(s)
    p = os.path.join(tmp, "word", "document.xml"); d = open(p, encoding="utf-8").read()
    n_before = len(re.findall(r'<w:rFonts[^>]*?/>', d))
    d = re.sub(r'<w:rFonts[^>]*?/>',
               lambda m: m.group(0) if 'w:hint=' in m.group(0) else m.group(0)[:-2] + ' w:hint="eastAsia"/>', d)
    open(p, "w", encoding="utf-8").write(d)
    if os.path.exists(dst): os.remove(dst)
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _, files in os.walk(tmp):
            for f in files:
                a = os.path.join(root, f)
                z.write(a, os.path.relpath(a, tmp))
    shutil.rmtree(tmp)
    return {"rfonts": n_before, "sz": sz}

def verify(path):
    """自证：三件事都落到了文件里，否则报错。"""
    z = zipfile.ZipFile(path)
    st = z.read("word/styles.xml").decode(); dc = z.read("word/document.xml").decode()
    errs = []
    if 'w:eastAsia="宋体"' not in st or 'w:ascii="Times New Roman"' not in st: errs.append("W1 字体三槽")
    if '<w:autoSpaceDE w:val="0"/>' not in st: errs.append("W2 autoSpace")
    if st.index('<w:autoSpaceDE') > st.index('<w:spacing'): errs.append("W2 次序（autoSpace 须在 spacing 前）")
    rf = re.findall(r'<w:rFonts[^>]*?/>', dc)
    if not all('w:hint="eastAsia"' in x for x in rf): errs.append("W3 hint")
    return errs

if __name__ == "__main__":
    src, dst = sys.argv[1], sys.argv[2]
    sz = int(sys.argv[3]) if len(sys.argv) > 3 else 23
    r = postprocess(src, dst, sz)
    e = verify(dst)
    print(f"  后处理完成：{r['rfonts']} 处 rFonts，字号 {sz} 半磅")
    if e: print("  自证失败：" + "、".join(e)); sys.exit(1)
    print("  自证通过：字体三槽 / autoSpace / hint 全部落到文件")
