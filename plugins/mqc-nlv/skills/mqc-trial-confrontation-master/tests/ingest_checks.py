#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""摄入层的改坏验证。这一层最危险的失败是静默：材料丢了却不报错、对账还报平。
每条都造一份真文件去打它，不用桩。"""
import os, sys, zipfile, tempfile
HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT,"scripts"))
from ingest import ingest, reconcile, kind_of, UnknownFormat, read_docx

D=tempfile.mkdtemp(); W=os.path.join(D,"work")
errs=[]
def ck(no,cond,msg):
    print(("  OK  " if cond else "  FAIL")+f" {no}  {msg}")
    if not cond: errs.append(no)

# 造料：一张假图片、一份真 docx、一份纯文本、一个认不出的扩展名
img=os.path.join(D,"a.jpg"); open(img,"wb").write(b"\xff\xd8\xff\xe0stub")
txt=os.path.join(D,"b.txt"); open(txt,"w",encoding="utf-8").write("起诉状正文"*400)
doc=os.path.join(D,"c.docx")
with zipfile.ZipFile(doc,"w") as z:
    z.writestr("word/document.xml",
        '<?xml version="1.0"?><w:document xmlns:w="x"><w:body>'
        '<w:p><w:r><w:t>代理意见</w:t></w:r></w:p>'
        '<w:p><w:r><w:t>合同合法有效</w:t></w:r></w:p></w:body></w:document>')
empty=os.path.join(D,"d.docx")
with zipfile.ZipFile(empty,"w") as z:
    z.writestr("word/document.xml",'<?xml version="1.0"?><w:document xmlns:w="x"></w:document>')
bad=os.path.join(D,"e.rtf"); open(bad,"w").write("x")

ck("I5a", kind_of(img)=="image" and kind_of(doc)=="docx" and kind_of(txt)=="plain",
   "按扩展名分派：图片／docx／纯文本各归各路")

try:
    kind_of(bad); ck("I5b", False, "认不出的扩展名应当报错，实际放行了")
except UnknownFormat:
    ck("I5b", True, "认不出的扩展名拒绝摄入（.rtf）")

ck("I5c", "代理意见" in read_docx(doc) and "合同合法有效" in read_docx(doc),
   "docx 零依赖抽得出正文")

try:
    ingest([empty], W); ck("I5d", False, "抽不出正文的 docx 应当报错，实际当作已读")
except UnknownFormat:
    ck("I5d", True, "抽不出正文的 docx 拒绝摄入，不得当作已读")

mats, srcs, todo = ingest([img, doc, txt], W)
ck("I5e", [m["medium"] for m in mats]==["image","text","text"],
   "图片判为待读图，docx 与纯文本判为文字型")
ck("I5f", len(todo)==1 and todo[0]["images"]==[img],
   "图片本身就是一页待读图，不再送去栅格化")

rec = reconcile(mats, srcs, external_anchor=None)
ck("I4a", rec["unreadable_materials"]==["M01"],
   f"未读图的材料计入未读清单（实为 {rec['unreadable_materials']}）")
rec2 = reconcile(mats, srcs, external_anchor=None, read_images=["M01"])
ck("I4b", not rec2["unreadable_materials"] and rec2["unreadable"]==0,
   "模型读完图并写出转写稿后，两轨对账才平")

# 份数轨的意义：假造一份 0 页材料，页数轨看不出来，份数轨必须看出来
mats3 = mats + [{"mid":"M09","name":"丢掉的材料","kind":"pdf","pages":0,"medium":"text"}]
rec3 = reconcile(mats3, dict(srcs, M09=""), external_anchor=None, read_images=["M01"])
ck("I4c", "M09" in rec3["unreadable_materials"] and rec3["unreadable"]==0,
   "0 页材料在页数轨上报平，必须由份数轨抓出来")

print()
print("  全部通过" if not errs else f"  未通过：{sorted(set(errs))}")
sys.exit(1 if errs else 0)
