# -*- coding: utf-8 -*-
"""直接把 =ROW()-N 的缓存值写进 sheet XML，绕开 LibreOffice 重算。
理由：recalc 走 LibreOffice 会就地重写工作簿，替换本机未装的字体、
并把宋体那条也合并掉，富文本与字体表都保不住。"""
import zipfile, shutil, re, sys
if __name__ == "__main__":
    # Windows 中文控制台默认 GBK：这个脚本由 pipeline 以子进程方式调用，
    # 不固定成 UTF-8，外部 AI（按 UTF-8 读）看到的仍是乱码。
    import sys as _sys
    for _stream in (_sys.stdout, _sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
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
