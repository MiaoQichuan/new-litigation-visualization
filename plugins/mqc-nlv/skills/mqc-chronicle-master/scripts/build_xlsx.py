# -*- coding: utf-8 -*-
"""Excel 母表：AI 只填前六列，加黑/删减/摘录留给律师。
xlsx 的 <font> 没有 Word 那样的 eastAsia 槽，一个 font 只能一个字体名，
所以用单元格富文本按字符集拆 run：中文走宋体，英文数字走 Times New Roman。"""
import json, re
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.cell.rich_text import CellRichText, TextBlock
from openpyxl.cell.text import InlineFont
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.utils import get_column_letter

EA="宋体"; LATIN="Times New Roman"; TITLE_EA="方正小标宋简体"
# 中文弯引号、省略号、破折号等位于通用标点区，码位低于 0x2E80，
# 必须显式并入中文一侧，否则会被当成西文挂到新罗马上。
CJK_PUNCT=set("\u2018\u2019\u201c\u201d\u2026\u2014\u2013\u00b7\u2015\u2010")
CJK=lambda c: ord(c)>0x2E80 or c in CJK_PUNCT

def font_for(t):
    """单段内容的字体：含中文走宋体，纯英文数字走新罗马。"""
    t=str(t)
    return EA if any(CJK(c) for c in t) else LATIN

def rich(t, sz=10.5, bold=False):
    """按中文/非中文切段，各挂各的字体。全中文或全西文时退回普通字符串（更省）。"""
    t=str(t)
    if not t: return t
    segs=[]; cur=""; curk=None
    for ch in t:
        k=CJK(ch)
        if curk is None or k==curk: cur+=ch; curk=k
        else: segs.append((curk,cur)); cur=ch; curk=k
    if cur: segs.append((curk,cur))
    if len(segs)==1: return t   # 单段：字体由调用方按 font_for() 决定
    return CellRichText(*[TextBlock(InlineFont(rFont=(EA if k else LATIN), sz=sz, b=bold), s)
                          for k,s in segs])

import sys
IN=sys.argv[1] if len(sys.argv)>1 else "渲染输入.json"
OUT=sys.argv[2] if len(sys.argv)>2 else "案件大事记母表.xlsx"
D=json.load(open(IN,encoding="utf-8"))
wb=Workbook(); ws=wb.active; ws.title="大事记母表"

COLS=[("序号",6),("日期",12),("主体",14),("事项",26),("主要内容",52),
      ("来源",26),("争点",10),("关联",26),("说明",24),("新证据",9),("证据状态",14),("加黑",8)]
# 样式与攻防图的母表一套：不用底色，层次靠字号、加粗与三档灰度的细线。
# 列头原先压一条浅色底，跟另一张表摆在一起就不是一家的。
INK="1F2933"
MUTED="6B7280"     # 说明性文字用灰，字号跟正文一样——靠缩小字号来区分，整张表就花了
GRY=Side(style="thin", color="BFBFBF")      # 正文
MED=Side(style="thin", color="1F2933")      # 表头
BORD=Border(left=GRY, right=GRY, top=GRY, bottom=GRY)
BORD_H=Border(left=GRY, right=GRY, top=GRY, bottom=MED)

LAST=get_column_letter(len(COLS))
# 表头：案件名单占一行，左对齐，方正小标宋，与攻防图的母表同一种起手式
t=ws.cell(row=1,column=1,value=f'{D["case"]["subtitle"]}　·　大事记母表')
t.font=Font(name=TITLE_EA,size=16,bold=True,color=INK)
t.alignment=Alignment(horizontal="left",vertical="center")
ws.merge_cells(f"A1:{LAST}1"); ws.row_dimensions[1].height=42

HR=2
for j,(h,wd) in enumerate(COLS,1):
    c=ws.cell(row=HR,column=j,value=h)
    c.font=Font(name=EA,size=10.5,bold=True,color=INK)
    c.alignment=Alignment(horizontal="center",vertical="center",wrap_text=True)
    c.border=BORD_H
    ws.column_dimensions[get_column_letter(j)].width=wd
ws.freeze_panes=f"B{HR+1}"        # 冻列头一行加编号一列，与攻防图一致
ws.row_dimensions[HR].height=30

for i,r in enumerate(D["rows"],start=HR+1):
    vals=[f"=ROW()-{HR}",                   # 序号用公式，插行删行自动调整；HR 是列头行
          r["date"], r.get("parties",""), r["item"], r["content"], r["source"],
          r.get("issue",""), r.get("relation",""), r.get("explain",""),
          "是" if r.get("new_evidence") else "", r["evidence_status"], ""]
    for j,v in enumerate(vals,1):
        c=ws.cell(row=i,column=j)
        c.value = v if (j==1 or not isinstance(v,str)) else rich(v)
        c.font=Font(name=font_for(v) if isinstance(v,str) else LATIN, size=10.5)
        c.alignment=Alignment(vertical="top",wrap_text=True,
                              horizontal="center" if j in (1,2,7,10,11,12) else "left")
        c.border=BORD
    ws.row_dimensions[i].height=None

n=len(D["rows"])+HR
ws.auto_filter.ref=f"A{HR}:{LAST}{n}"

an=D.get("arithmetic_notes") or []
for k,t in enumerate(an):
    c=ws.cell(row=n+1+k, column=1, value=rich(f"算术备注{k+1}：{t}"))
    c.font=Font(name=EA,size=10.5,color=MUTED)
    c.alignment=Alignment(vertical="top",wrap_text=True)
    ws.merge_cells(start_row=n+1+k,start_column=1,end_row=n+1+k,end_column=len(COLS))
n += len(an)

lg=ws.cell(row=n+2,column=1,value=rich("填写说明：序号至来源各列由大事记表大师编满（照录原文、每行挂来源、一条不漏）；"
      "争点加黑两列与主要内容的删减由律师完成。说明列自动带出不确定清单里的条目，可再补。"
      "证据状态为仅当事人陈述的行，表示未见书证；证据编号缺失这一类不再重复写进说明列。"))
lg.font=Font(name=EA,size=10.5,color=MUTED); lg.alignment=Alignment(vertical="top")
ws.merge_cells(start_row=n+2,start_column=1,end_row=n+2,end_column=len(COLS))

wb.save(OUT); print(f"  Excel 母表：{OUT}（{n-1} 行）")
