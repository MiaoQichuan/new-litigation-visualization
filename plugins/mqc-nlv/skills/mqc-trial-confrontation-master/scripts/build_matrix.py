#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""庭审对抗图 · 母表（一张表，纵向读）。
列数收到 16：把同一层级的字段并进一格、分行写，让文字往下走而不是往右铺。
层级：一级对抗部分（深灰白字）→ 二级请求权基础（浅灰，定性风险红字）→ 三级要件行（无底色）。
字体：仅列头用方正小标宋；其余中文宋体、英文数字 Times New Roman；中文标点并入中文侧。
不过 LibreOffice（它会就地重写工作簿并替换未装字体）。
"""
import json, sys
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.cell.rich_text import CellRichText, TextBlock
from openpyxl.cell.text import InlineFont
from openpyxl.utils import get_column_letter
from openpyxl.comments import Comment
from openpyxl.styles.colors import Color

EA, LATIN, TITLE_EA = "宋体", "Times New Roman", "方正小标宋简体"
CJK_PUNCT = set("\u2018\u2019\u201c\u201d\u2026\u2014\u2013\u00b7\u2015\u2010")
CJK = lambda c: ord(c) > 0x2E80 or c in CJK_PUNCT

# 全表不用底色。层级只靠字号、加粗与线：列头加粗压一条粗下线，板块行加粗放大压一条细上线。
# 先是列头整行深红、后来改深灰，两种都是拿一条色带去分层——色块一层都不该有，
# 分层的活交给字和线。红更不做装饰：列头整行深红、每个请求权基础行又是红字，一张表里红占掉十几处，
# 真正该被一眼找到的决定性要件反而淹了。红只留给决定性要件那一行的编号。

# 线一律细，层次只靠灰度分三档：分节界限与列头用深灰，争点板块用中灰，正文用淡灰。
# 先用过 medium 做分节与列头，太重；细线加深色已经够把界限说清楚，再粗就抢了正文。
GRY  = Side(style="thin", color="BFBFBF")   # 正文
MID  = Side(style="thin", color="9CA3AF")   # 争点板块
MED  = Side(style="thin", color="1F2933")   # 分节界限与列头
BORD_G = Border(left=GRY, right=GRY, top=GRY, bottom=GRY)   # 正文行：细灰线框
BORD_H = Border(left=GRY, right=GRY, top=GRY, bottom=MED)   # 列头：粗下线代替底色
BORD_S = Border(left=GRY, right=GRY, top=MED, bottom=GRY)   # 分节标题：粗上线
BORD_P = Border(left=GRY, right=GRY, top=MID, bottom=GRY)   # 争点板块：淡细上线
RED  = "991B1B"     # 全套唯一的红。图与表同一个值，不许再有第二个红
INK  = "1F2933"
MUTED= "6B7280"     # 说明性文字用灰，字号不缩
MAX_RED = 2         # 与图的 L4 同一条纪律：至多标两处，三处及以上不标，改在小结里写明

# 列宽只有三档：短 / 中 / 长。逐列拍一个数字，宽窄就会毫无道理地跳，
# 而且总有几列窄到读不下去（「法律上能否成立」原先 19 字宽，里面却要装四段主张）。
S, M, L = 12, 26, 46
COLS = [("编号",S),("要件名",M),("法院审理标准",L),("要件属性",M),("争议状态",S),
        ("待证事实",L),
        ("请求方主张（是否满足）",L),("抗辩方回应",L),("请求方反制",L),("抗辩方再回应",L),
        ("法律上能否成立（不看证据）",L),("初步研判",L),("关键证据",M),
        ("证明前景与决定性",L),("把握程度与依据",M),("待补材料",M),("对应图中位置",S)]

PROC_LABEL = (("jurisdiction","管辖"), ("parties","主体"), ("res_judicata","重复起诉"))

def _procedural(p):
    """程序站三项分列的是数据结构，交付面要的是中文。
    把对象原样拼进字符串会在表里印出一行 Python 字面量——律师看的东西里不该有代码。"""
    if isinstance(p, dict):
        # 三项各占一行：每项内部本来就有分号，再用分号把三项串起来就读不清了
        body = "\n".join(f"{name}：{str(p.get(key,'')).strip()}"
                         for key, name in PROC_LABEL if str(p.get(key,"")).strip())
        return f"程序事项审查\n{body}" if body else "程序事项审查：未填"
    return f"程序事项审查：{p}" if p else "程序事项审查：未填"

def font_for(t): return EA if any(CJK(c) for c in str(t)) else LATIN

def _col(c):
    """颜色统一成八位 rgb。传六位 openpyxl 会补成 alpha=00，Excel 弹修复。"""
    return None if not c else Color(rgb=("FF"+c if len(c)==6 else c))

def rich(t, sz=10.5, bold=False, color=None):
    t=str(t)
    if not t: return t
    segs,cur,curk=[],"",None
    for ch in t:
        if ch.isspace():                      # 空白跟着前一段走，绝不另起一段
            if curk is None: curk=True
            cur+=ch; continue
        k=CJK(ch)
        if curk is None or k==curk: cur+=ch; curk=k
        else: segs.append((curk,cur)); cur,curk=ch,k
    if cur: segs.append((curk,cur))
    segs=[(k,v) for k,v in segs if v.strip()!="" or len(segs)==1]
    if len(segs)==1: return t
    return CellRichText(*[TextBlock(InlineFont(rFont=(EA if k else LATIN),sz=sz,b=bold,color=_col(color)),s)
                          for k,s in segs])

def put(ws,r,c,v,*,sz=10.5,bold=False,fill=None,halign="left",color=None,note=None,font=None,border=None):
    cell=ws.cell(row=r,column=c)
    cell.value = rich(v,sz,bold,color) if isinstance(v,str) else v
    cell.font = Font(name=font or font_for(v), size=sz, bold=bold, color=color)
    cell.alignment = Alignment(vertical="center", wrap_text=True, horizontal=halign)
    if fill: cell.fill=fill
    cell.border = border or BORD_G
    if note: cell.comment=Comment(note,"庭审对抗图大师")
    return cell

def build(src,dst):
    D=json.load(open(src,encoding="utf-8"))
    # 一张表，全部行可见：不折叠、不冻结。层级只用四档字号加线：
    # 大标题 16、分节标题 12、争点板块行 11、正文一律 10.5。
    # 拆成两张表是偷懒；把说明区折叠起来更糟，那是把内容藏起来回避冻结的丑，
    # 打开表前十几行一片空白。冻结本身不要，滚到哪里由读者自己定。
    wb=Workbook(); ws=wb.active; ws.title="庭审对抗分析"
    N=len(COLS); last=get_column_letter(N)
    SEC, BODY = 12, 10.5

    r=1
    def band(txt, sz=BODY, bold=False, h=30, border=None, muted=False):
        nonlocal r
        put(ws,r,1,txt,sz=sz,bold=bold,
            color=(INK if bold else (MUTED if muted else None)),border=border)
        for j in range(2,N+1): put(ws,r,j,"",border=border)
        ws.merge_cells(start_row=r,start_column=1,end_row=r,end_column=N)
        ws.row_dimensions[r].height=h; r+=1

    put(ws,1,1,D["case"]["title"],sz=16,bold=True,font=TITLE_EA,halign="left",color=INK)
    ws.merge_cells(f"A1:{last}1"); ws.row_dimensions[1].height=42; r=2

    # 节序按办案顺序：先看要什么（诉请），再看怎么打（要件与攻防），
    # 程序与材料是辅助，放最后。这样冻结到列头时，冻住的只有诉请那几行。
    band("一、诉请固定", sz=SEC, bold=True, h=24, border=BORD_S)
    for c in D.get("claims",[]):
        body=f'{c["id"]}　【{c.get("type")}】　'+"　｜　".join(
            f'{k}：{v}' for k,v in (c.get("fields") or {}).items())
        if c.get("breakdown"):
            body+="\n构成明细：" + "；".join(
                f'{b.get("item")} {b.get("amount")} 元（{b.get("basis")}）' for b in c["breakdown"])
        if c.get("boundary"):
            body+="\n适用边界："+c["boundary"]
        band(body, h=76 if c.get("boundary") else 50)

    band("二、要件与攻防", sz=SEC, bold=True, h=24, border=BORD_S)
    HR=r
    for j,(h,w) in enumerate(COLS,1):
        put(ws,HR,j,h,sz=BODY,bold=True,halign="center",color=INK,border=BORD_H)
        ws.column_dimensions[get_column_letter(j)].width=w
    ws.row_dimensions[HR].height=44
    ws.freeze_panes=f"B{HR+1}"      # 冻到列头行；编号列一并冻住，横滚时对得上行

    dec=[e["id"] for p in D["parts"] for cb in p["claim_bases"]
         for e in cb["elements"] if e.get("decisive")=="是"]
    mark = set(dec) if len(dec)<=MAX_RED else set()     # 分散态：一处都不标
    r=HR+1
    for part in D["parts"]:
        put(ws,r,1,f'{part["label"]}　·　{part["track"]}',sz=11,bold=True,color=INK,border=BORD_P)
        for j in range(2,N+1): put(ws,r,j,"",border=BORD_P)
        ws.merge_cells(start_row=r,start_column=1,end_row=r,end_column=N)
        ws.row_dimensions[r].height=24; r+=1
        for cb in part["claim_bases"]:
            head=(f'请求权基础：{cb["basis"]}\n条文性质：{cb["norm_type"]}　｜　{cb["verify"]}　｜　与其他请求权的关系：{cb["concurrence"]}\n'
                  f'法院另作定性的风险：{cb["recharacterization_risk"]}')
            put(ws,r,1,head,sz=BODY,bold=True,color=INK)
            for j in range(2,N+1): put(ws,r,j,"")
            ws.merge_cells(start_row=r,start_column=1,end_row=r,end_column=N)
            ws.row_dimensions[r].height=58; r+=1
            for e in cb["elements"]:
                attr=(f'层次：{e["layer"]}\n类型：{e["kind"]}\n证明责任：{e["burden"]}\n证明标准：{e["standard"]}')
                resp=f'{e["response"]}\n\n抗辩性质：{e["response_class"]}'
                sec =f'{e["second"]}\n\n抗辩性质：{e["second_class"]}' if e["second"] not in ("—","") else e["second"]
                lay1=(f'请求方主张：{e["st_plaintiff"]}\n抗辩方抗辩：{e["st_defendant"]}\n'
                      f'请求方反制：{e["st_replik"]}\n抗辩方再回应：{e["st_duplik"]}')
                lay2=(f'应主张而未主张：{e["gap"]}\n自陈不利事实：{e["self_defeat"]}\n'
                      f'研判：{e["triage"]}\n是否真争点：{e["issue_kind"]}')
                pros=(f'证明前景：{e["prospect"]}\n决定性要件：{e["decisive"]}'
                      f'\n立场方向：{e.get("direction","未标")}'
                      + (f'\n真伪不明的后果：{e["burden_conclusion"]}'
                         if e.get("burden_conclusion") else ""))
                trip=f'法律上把握：{e["conf_law"]}\n证据上把握：{e["conf_evid"]}\n依据来源：{e["source"]}'
                vals=[e["id"],e["name"],e["court_standard"],attr,e["dispute"],e["facts"],
                      e["claim"],resp,e["counter"],sec,lay1,lay2,e["evidence"],pros,trip,
                      e["todo"],e["figure_ref"]]
                hot = e["id"] in mark
                for j,v in enumerate(vals,1):
                    put(ws,r,j,v,halign=("center" if j in (1,5) else "left"),
                        bold=(hot and j==1), color=(RED if hot and j==1 else None),
                        note=(e.get("class_reason") or None) if j==8 else None)
                r+=1
        tail=("" if len(dec)<=MAX_RED else
              f'　｜　本案决定性要件 {len(dec)} 处（{"、".join(dec)}），争点分散，表内不作单点标注')
        put(ws,r,1,f'{part["label"]}　小结：{part["summary"]}{tail}')
        for j in range(2,N+1): put(ws,r,j,"")
        ws.merge_cells(start_row=r,start_column=1,end_row=r,end_column=N)
        ws.row_dimensions[r].height=46; r+=1
    ws.auto_filter.ref=f"A{HR}:{last}{r-1}"

    # 三、案件与程序：程序站与材料范围是辅助，放最后，表头才不会占掉半屏
    band("三、案件与程序", sz=SEC, bold=True, h=24, border=BORD_S)
    band(_procedural(D["case"].get("procedural")), h=86)
    band(f'初步研判：{D["case"]["triage"]}', h=62)
    ca=D["case"].get("counterattacks") or []
    if ca:
        band("攻击性防御（不入抗辩四分法）：" + "；".join(
            f'{c.get("kind")}，{str(c.get("handling","")).strip()}' for c in ca), h=62)
    sc=D.get("scope") or {}
    if sc.get("not_obtained") or sc.get("note"):
        band("本表所据材料范围：已获取 "+("、".join(sc.get("obtained") or []) or "无")
             +"；未获取 "+("、".join(sc.get("not_obtained") or []) or "无")
             +f"；材料成熟度 {sc.get('maturity','未标')}"
             +(f"\n{sc['note']}" if sc.get("note") else ""), h=54)
    band("读法：加粗压淡线的整行为一个争点板块；其下一行为该板块的请求权基础与定性风险；"
         "再下为逐个构成要件。编号标红者为决定性要件。抗辩性质的归类理由见单元格批注。",
         h=32, muted=True)

    wb.save(dst)
    _preserve_space(dst)
    corner = _corner_quotes(dst)
    assert not corner, (f"表里出现直角引号：{corner[:2]}。"
                        f"「」不是大陆法律文书的写法，正文里一处都不许有")
    leak = _leaked_literals(dst)
    assert not leak, (f"交付面漏出了数据结构：{leak[:2]}。"
                      f"律师看的东西里不该有 Python 字面量——把对象渲染成中文再写进单元格")
    hot = _count_red(dst)
    assert hot <= MAX_RED, (f"红用超了：母表里有 {hot} 处深红，上限 {MAX_RED}。"
                            f"红只标决定性要件的编号，不做列头、不做小标题——"
                            f"红一多，真正该被一眼找到的那处就淹了")
    print(f"  母表：{dst}（{N} 列，{r-HR-1} 行内容；深红 {hot} 处，上限 {MAX_RED}）")


def _corner_quotes(path):
    """扫产物找直角引号。数据里带进来的也算——判据读产物，不读源码。"""
    import openpyxl
    out = []
    for ws in openpyxl.load_workbook(path).worksheets:
        for row in ws.iter_rows():
            for c in row:
                if isinstance(c.value, str) and ("「" in c.value or "」" in c.value):
                    out.append((c.coordinate, c.value[:34]))
    return out


def _leaked_literals(path):
    """扫产物找 Python 字面量。程序站改成三项分列的字段后，出表那边没跟着改，
    直接把 dict 拼进了字符串，表里于是印出一行 {'jurisdiction': '...'}。"""
    import openpyxl, re
    pat = re.compile(r"\{'|': '|\[\{|None\b|\bTrue\b|\bFalse\b")
    out = []
    for ws in openpyxl.load_workbook(path).worksheets:
      for row in ws.iter_rows():
        for c in row:
            if isinstance(c.value, str) and pat.search(c.value):
                out.append((c.coordinate, c.value[:40]))
    return out


def _count_red(path):
    """读回产物数深红，不数源码里写了几次。改代码后必须核对产物，这是踩过的坑。"""
    import openpyxl
    n = 0
    for ws in openpyxl.load_workbook(path).worksheets:
      for row in ws.iter_rows():
        for c in row:
            fc = getattr(getattr(c.font, "color", None), "rgb", None)
            bc = getattr(getattr(c.fill, "fgColor", None), "rgb", None)
            n += str(fc or "").endswith(RED) or str(bc or "").endswith(RED)
    return n

def _preserve_space(path):
    """含换行的文本节点必须带 xml:space="preserve"，否则空白被折叠、Excel 判为字符串属性有问题。"""
    import zipfile, shutil, re as _re
    tmp=path+".tmp"; zin=zipfile.ZipFile(path)
    pat=_re.compile(r'<t(?![^>]*xml:space)([^>]*)>([^<]*[\s][^<]*)</t>')
    with zipfile.ZipFile(tmp,"w",zipfile.ZIP_DEFLATED) as zo:
        for it in zin.infolist():
            b=zin.read(it.filename)
            if it.filename.startswith("xl/worksheets/sheet") or it.filename.endswith("sharedStrings.xml"):
                b=pat.sub(lambda m: f'<t xml:space="preserve"{m.group(1)}>{m.group(2)}</t>',
                          b.decode("utf-8")).encode("utf-8")
            zo.writestr(it,b)
    zin.close(); shutil.move(tmp,path)

if __name__=="__main__":
    build(sys.argv[1],sys.argv[2])
