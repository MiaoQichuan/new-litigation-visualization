# -*- coding: utf-8 -*-
"""直接把 =ROW()-N 的缓存值写进 sheet XML，绕开 LibreOffice 重算。
理由：recalc 走 LibreOffice 会就地重写工作簿，替换本机未装的字体、
并把宋体那条也合并掉，富文本与字体表都保不住。"""
import zipfile, shutil, re, sys
src=sys.argv[1]; tmp=src+".tmp"
zin=zipfile.ZipFile(src)
def fix(xml):
    def rep(m):
        ref, f = m.group(1), m.group(2)
        # 偏移量从公式里读，不写死：母表上方加了案件名标题之后，
        # 列头就不在第 1 行，公式随之变成 ROW()-2，写死 ROW()-1 会一条也匹配不上
        mo = re.fullmatch(r"ROW\(\)-(\d+)", f.strip())
        if not mo: return m.group(0)
        off = int(mo.group(1))
        row = int(re.search(r'\d+', ref).group(0))
        return m.group(0).replace("<v></v>", f"<v>{row-off}</v>")
    # openpyxl 写出的形态是 <f>…</f><v></v>，把空的 v 填上
    return re.sub(r'<c r="([A-Z]+\d+)"[^>]*><f>([^<]*)</f><v></v></c>', rep, xml)
with zipfile.ZipFile(tmp,"w",zipfile.ZIP_DEFLATED) as zo:
    for it in zin.infolist():
        b=zin.read(it.filename)
        if it.filename.startswith("xl/worksheets/sheet"):
            b=fix(b.decode("utf-8")).encode("utf-8")
        zo.writestr(it,b)
zin.close(); shutil.move(tmp,src)
print("公式缓存值已写入")
