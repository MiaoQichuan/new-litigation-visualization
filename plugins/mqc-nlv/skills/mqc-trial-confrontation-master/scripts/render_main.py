#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""庭审对抗图 · 主图渲染器。零第三方依赖。
汇聚式：左栈诸卡并入一条左母线 → 单干进法院审查卡左边框中点；右侧镜像。
法院审查卡高度 = 行组高 = max(左栈总高, 右栈总高)，两端天然对齐，母线两腿天然等长。
自由度为零：母线 x 由通道中线定，母线上下端由首末卡中线定，单干 y 由三者共同的中线定。
视觉照 references/visual-style.md：实心块不描边、卡圆角12、边标签纯文字无底框、
标题下无横线、深红 #991B1B 实心白字且全图 1–2 处、箭头固定 10px 且 refX 按 cover 算。
"""
import json, math, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from layout import Geo, columns
from geom import text_w, wrap_w, Rect, verify

BG="#FFFFFF"; INK="#1F2933"; INK2="#6B7280"; NOTE="#9CA3AF"
LINE="#4B5563"; SOFT="#C3C9D2"; CARD="#F3F4F6"; STEP="#E9ECEF"; RED="#991B1B"
TITLE_FONT="'方正小标宋简体','FZXiaoBiaoSong-B05S','思源宋体','Source Han Serif SC','Noto Serif CJK SC','华文中宋',serif"
BODY_FONT="'PingFang SC','Microsoft YaHei','Noto Sans CJK SC','Noto Sans SC','Helvetica Neue',Arial,sans-serif"

def fillet(pts, r):
    pts=[p for i,p in enumerate(pts) if i==0 or abs(p[0]-pts[i-1][0])>0.4 or abs(p[1]-pts[i-1][1])>0.4]
    if len(pts)<2: return ""
    d=[f"M {pts[0][0]:.2f},{pts[0][1]:.2f}"]
    for i in range(1,len(pts)-1):
        p0,p1,p2=pts[i-1],pts[i],pts[i+1]
        v1=(p1[0]-p0[0],p1[1]-p0[1]); l1=math.hypot(*v1) or 1
        v2=(p2[0]-p1[0],p2[1]-p1[1]); l2=math.hypot(*v2) or 1
        rr=min(r,l1/2,l2/2)
        u1=(v1[0]/l1,v1[1]/l1); u2=(v2[0]/l2,v2[1]/l2)
        a=(p1[0]-u1[0]*rr,p1[1]-u1[1]*rr); b=(p1[0]+u2[0]*rr,p1[1]+u2[1]*rr)
        sw=1 if u1[0]*u2[1]-u1[1]*u2[0]>0 else 0
        d.append(f"L {a[0]:.2f},{a[1]:.2f} A {rr:.2f} {rr:.2f} 0 0 {sw} {b[0]:.2f},{b[1]:.2f}")
    d.append(f"L {pts[-1][0]:.2f},{pts[-1][1]:.2f}")
    return " ".join(d)

def arrow(mid, color, sw, size, s):
    """固定尺寸箭头；refX 按 cover=2.0 倍线宽算出，不钉死（visual-style）。"""
    L=size*s; HW=L/2; cover=2.0*sw
    return (f'<marker id="{mid}" viewBox="0 0 12 12" refX="{12*cover/L:.3f}" refY="6" '
            f'markerWidth="{L:.2f}" markerHeight="{L:.2f}" markerUnits="userSpaceOnUse" orient="auto">'
            f'<path d="M 0 0 L 12 6 L 0 12 Z" fill="{color}"/></marker>'), cover

TITLE_TOP = True   # M10 标题一律贴卡顶左上排，三栏抬头因此齐平
CENTER_V  = True   # M11 正文在标题下沿与卡底之间纵向居中（标题不跟着走）
LEGEND_W_RATIO = 0.52      # T6 图底左侧图例占幅宽的比例，结论条据此让位
LBL_UP, LBL_DN = 12.0, 22.0   # R9 边标签相对引线的让线量（首卡向上 / 末卡向下），按比例因子计
ASC, DESC = 0.88, 0.22   # 字形基线以上的上沿 / 以下的下沉，按字号计。
                         # 卡内文字块的上下留白都以它们量出，各等于 PADY——留白只由 PADY 一处定。

def metrics(nt, nb, cut, g):
    """M10 卡内所有基线与卡高在这一处算出，绘制与高度同源——改这里两边一起动。
    早先高度按 2*PADY + 标题行 + 正文行 估，漏了标题与正文之间的呼吸位与字形下沉，
    凡「高度恰等于自身 need」的卡（侧栏最高的那张、行组由中轴撑出时的中轴卡）
    底部留白都短一截；截断标注还会压在最后一行正文上。
    返回 (标题基线, 正文基线, 截断标注基线或 None, 卡高)，基线均相对卡顶。"""
    tb=[g.PADY+ASC*g.FS_T+i*g.FS_T*1.35 for i in range(max(1,nt))]
    bb=[tb[-1]+g.FS_T*0.5+(i+1)*g.LH for i in range(nb)]
    last, fs = (bb[-1], g.FS) if bb else (tb[-1], g.FS_T)
    note=None
    if cut:                                   # 截断标注另占一行，不挤最后一行正文
        note=last+g.LH*0.9; last, fs = note, g.FS*0.85
    return tb, bb, note, last+DESC*fs+g.PADY

def body_off(c, h, g):
    """M11 正文块在「标题下沿 → 卡底」之间居中，返回相对自然位置的下移量。
    卡高恰等于所需时算出的偏移为零，所以不改变紧排的卡。"""
    if not c.bb: return 0.0
    t_bot = c.tb[-1] + DESC*g.FS_T
    b_top = c.bb[0]  - ASC*g.FS
    last, fs = (c.note_y, g.FS*0.85) if c.cut else (c.bb[-1], g.FS)
    off = (h + t_bot - b_top - (last + DESC*fs))/2
    # 偏移可以是小的负数：标题与正文之间的呼吸位本就比字形下沉多出一点，
    # 紧排的卡因此天然偏下约两个像素。钳成非负会让这批卡差着 4px 过不了 M11。
    return max(t_bot - b_top, off)          # 下限：正文上沿不得高过标题下沿

class Card:
    MAX=4
    def __init__(s_,d,w,g,maxline=None):
        s_.MAXL = maxline or Card.MAX
        s_.d=d; s_.w=w; s_.g=g
        s_.tl=wrap_w(d["title"], w-2*g.PAD, g.FS_T)
        ls=wrap_w(d["body"], w-2*g.PAD, g.FS)
        s_.cut=len(ls)>s_.MAXL; s_.ls=ls[:s_.MAXL]
        s_.tb, s_.bb, s_.note_y, s_.need = metrics(len(s_.tl), len(s_.ls), s_.cut, g)

def draw(o,c,x,y,h,g,fill,txt=INK,sub=INK2,rx=None,tag=""):
    """data-box 把一张卡的框与它的每一行文字绑在一起，供 check_figure 逐行核对是否落在框内。"""
    rx = 12*g.s if rx is None else rx
    b = f' data-box="{tag}"' if tag else ''
    # M10 标题不动：卡高再怎么被撑大，标题都贴卡顶，三栏的标题因此在同一水平线上。
    # M11 只有正文在「标题下沿到卡底」这段剩余空间里居中。中轴卡的高度是行组高、
    #     由两侧撑出，正文照顶排会在下方留出一大块空；整卡一起居中则标题会掉下来。
    whole = 0.0 if TITLE_TOP else max(0.0,(h-c.need)/2)
    t_dy = y + whole
    b_dy = y + (whole if not TITLE_TOP else (body_off(c,h,g) if CENTER_V else 0.0))
    o.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{c.w:.1f}" height="{h:.1f}" rx="{rx:.1f}" fill="{fill}"{b}/>')
    for ln,by in zip(c.tl,c.tb):
        o.append(f'<text x="{x+g.PAD:.1f}" y="{t_dy+by:.1f}" font-size="{g.FS_T:.1f}" '
                 f'fill="{txt}" font-weight="700"{b}>{ln}</text>')
    for ln,by in zip(c.ls,c.bb):
        o.append(f'<text x="{x+g.PAD:.1f}" y="{b_dy+by:.1f}" font-size="{g.FS:.1f}" fill="{sub}"{b}>{ln}</text>')
    if c.cut:
        o.append(f'<text x="{x+c.w-g.PAD:.1f}" y="{b_dy+c.note_y:.1f}" font-size="{g.FS*0.85:.1f}" '
                 f'fill="{NOTE}" text-anchor="end"{b}>全文见表</text>')

def render(data,out,s=2.2,W=3000):
    data.setdefault("title", "庭审对抗图")
    data.setdefault("subtitle", data.get("case",{}).get("title",""))
    g=Geo(s); col=columns(W,g,center_ratio=1.0)   # 三栏等宽：法院审查不比两侧大
    xL=col["margin"]; xC=xL+col["left"]+col["gutter"]; xR=xC+col["center"]+col["gutter"]
    laneL=xL+col["left"]+col["gutter"]/2           # 左通道正中
    laneR=xC+col["center"]+col["gutter"]/2         # 右通道正中
    SWc=1.4*s; SWe=2.1*s
    mk,coverC = arrow("a",LINE,SWc,10,s)
    mkr,coverR= arrow("r",RED, SWe,10,s)   # 红灰箭头同大小
    SWp=SWc*0.8
    mkp,coverP = arrow("p",SOFT,SWp,10,s)                      # 对位线箭头：与线同色
    mkb=(f'<marker id="b" viewBox="0 0 12 12" refX="{12*2.0*SWp/(10*s):.3f}" refY="6" '
         f'markerWidth="{10*s:.2f}" markerHeight="{10*s:.2f}" markerUnits="userSpaceOnUse" orient="auto-start-reverse">'
         f'<path d="M 0 0 L 12 6 L 0 12 Z" fill="{SOFT}"/></marker>')
    trimP=3.5*s+coverP
    trimC=3.5*s+coverC; trimR=3.5*s+coverR
    S =f'stroke="{LINE}" stroke-width="{SWc:.2f}" fill="none" stroke-linejoin="round"'
    SR=f'stroke="{RED}"  stroke-width="{SWe:.2f}" fill="none" stroke-linejoin="round"'
    R=2.4*SWc      # G-圆角：切掉拐点顶点约一个线宽
    o=[]; rects=[]; paths=[]; labels=[]

    top=28*s
    o.append(f'<text x="{W/2:.0f}" y="{top+34*s:.0f}" font-size="{30*s:.0f}" font-weight="700" fill="{INK}" '
             f'font-family="{TITLE_FONT}" text-anchor="middle">{data["title"]}</text>')
    st=data.get("stance"); mt=data.get("maturity")
    sub=data["subtitle"] + (f'　·　{st}推演　·　材料成熟度 {mt or "未标"}' if st else "")
    o.append(f'<text x="{W/2:.0f}" y="{top+62*s:.0f}" font-size="{13*s:.0f}" fill="{INK2}" text-anchor="middle">{sub}</text>')
    head=top+62*s+40*s
    # 立场与材料成熟度写在抬头之上：同一张图，原告向与被告向的读法相反——
    # D1 算的是「提出请求的一方证不出」，那对抗辩方是好消息、对请求方是警报。
    # 图上只呈现客观研判，怎么打（攻防着力点、诉请设计）不进这张图。
    rm=data.get("role_map",{})
    for x,w,t,k in [(xL,col["left"],"提出请求的一方","claim"),(xC,col["center"],"法院审查",None),
                    (xR,col["right"],"抗辩的一方","defend")]:
        o.append(f'<text x="{x+w/2:.0f}" y="{head:.0f}" font-size="{16*s:.0f}" font-weight="700" fill="{INK}" text-anchor="middle">{t}</text>')
        if k and rm.get(k):
            o.append(f'<text x="{x+w/2:.0f}" y="{head+20*s:.0f}" font-size="{13*s:.0f}" fill="{INK2}" text-anchor="middle">{rm[k]}</text>')

    for p in data["parts"]:                                   # 规则判定，不靠人标
        c=p["center"]
        cbs=p.get("claim_bases",[])
        dependent = any(cb.get("norm_type")=="辅助规范" or "不独立存在" in cb.get("concurrence","")
                        for cb in cbs)          # D1 从属性排除：孳息等从属请求不独立计入决定性要件
        p["emph"]= (bool(c.get("disputed")) and c.get("burden")=="claim"
                    and c.get("prospect") in ("低","存疑") and not dependent)
        p["_hit"]= p["emph"]          # 规则的原始判定，分散态下 emph 会被清掉，这个留着
    # L4 分散态：判定照算不封顶，算出三处及以上时全图不用深红。
    # 不能由代码挑出「最要紧的两个」——决定性要件排序按 A2 属于只给方向、
    # 结论留空等律师填，替他挑就是替他下结论。而 L4 要封的是视觉强调的密度，
    # 不是断言一个案子只能有两个决定性要件。争点零散的案子硬指一处反而误导。
    n_emph=sum(1 for p in data["parts"] if p.get("emph"))
    data["scattered"] = n_emph>2
    if data["scattered"]:
        for p in data["parts"]: p["emph"]=False
    for p in data["parts"]:
        nl=sum(1 for c in p["cards"] if c["side"]=="claim")
        nr=sum(1 for c in p["cards"] if c["side"]=="defend")
        assert 1<=nl<=2 and 0<=nr<=2, (f'L1 {p["id"]}：请求方至少一张、至多两张，'
                                       f'抗辩方 0–2 张（0 即对方尚无任何回应）')
        assert nr<=nl, (f'L2 {p["id"]}：抗辩方再回应以主张方反制为前提，'
                        f'左 {nl} 张时右侧不得有 {nr} 张。有效组合只有 左1右1 / 左2右1 / 左2右2')
    DASH_UP   = 116*s          # 虚线在行组顶之上多少
    HEAD_BOT  = head + 28*s     # 抬头文字块底缘（含角色映射行的下沉）
    HEAD_CLR  = 24*s            # 抬头与第一条虚线之间的呼吸位（固定值，改这一处即可）
    y = HEAD_BOT + HEAD_CLR + DASH_UP
    assert y - DASH_UP >= HEAD_BOT + HEAD_CLR - 0.5, "M7 抬头与第一条虚线交错"
    G=[]
    for part in data["parts"]:
        cL=[Card(c,col["left"],g)  for c in part["cards"] if c["side"]=="claim"]
        cR=[Card(c,col["right"],g) for c in part["cards"] if c["side"]=="defend"]
        cC=Card(part["center"],col["center"],g,maxline=8)   # 中轴高度即行组高，容量更大
        hS=max([c.need for c in cL+cR],default=cC.need); gap=hS*0.38
        st=lambda n: n*hS+(n-1)*gap if n else 0
        Hg=max(st(len(cL)),st(len(cR)),cC.need)      # 行组高由左右两栈撑出
        G.append(dict(part=part,cL=cL,cR=cR,cC=cC,hS=hS,gap=gap,Hg=Hg,y=y))
        gb_last=y+Hg
        y+=Hg+198*s            # 组间距：组底→下对位线44 →虚线82 →上对位线154 →下组顶198
    Htot=gb_last+104*s     # 末组底→索引表：下对位线44 + 呼吸60，不含组间距

    for gr in G:
        part,cL,cR,cC,hS,gap,Hg,gy=(gr[k] for k in ("part","cL","cR","cC","hS","gap","Hg","y"))
        st=lambda n: n*hS+(n-1)*gap if n else 0
        rects.append(Rect(xC,gy,col["center"],Hg,part["id"]))
        cmid=gy+Hg/2
        for cards,xs,side in ((cL,xL,"L"),(cR,xR,"R")):
            if not cards: continue
            n0=len(gr.get("lines",[]))          # 本侧走线在 lines 里的起点，切片按它取，不按卡数倒数
            y0=gy+(Hg-st(len(cards)))/2
            mids=[]
            for i,c in enumerate(cards):
                yy=y0+i*(hS+gap); tag=f'{part["id"]}{side}{i}'
                rects.append(Rect(xs,yy,col["left"],hS,tag)); mids.append(yy+hS/2)
                gr.setdefault("draw",[]).append((c,xs,yy,hS,tag))
                if c.d.get("edge"):
                    # R9 边标签贴卡外缘排，纵向让开母线：首卡的在其引线之上、末卡的在其引线之下，
                    #    两处都在母线竖段的上下端之外。居中在卡缘与母线之间会被竖段从字上穿过。
                    FSe=12*s; mid=yy+hS/2
                    assert text_w(c.d["edge"],FSe) <= col["gutter"]-12*s, (
                        f'R9 边标签{c.d["edge"]}宽过栏间通道，会压进卡片或中轴：'
                        f'请改用不超过 {int((col["gutter"]-12*s)//FSe)} 个中文字的短名，全称写进表')
                    ly = mid-LBL_UP*s if i==0 else mid+LBL_DN*s
                    lx0 = (xs+col["left"]+6*s) if side=="L" else (xs-6*s)
                    lw  = text_w(c.d["edge"], FSe)
                    gr.setdefault("labels",[]).append(
                        (c.d["edge"], lx0, ly, "start" if side=="L" else "end", FSe))
                    labels.append(Rect(lx0 if side=="L" else lx0-lw,
                                       ly-FSe*0.85, lw, FSe*1.07, f'lbl{part["id"]}{side}{i}'))
            lane = laneL if side=="L" else laneR
            x_out = xs+col["left"] if side=="L" else xs
            x_in  = (xC-trimC) if side=="L" else (xC+col["center"]+trimC)
            if len(cards)==1:                                    # 退化：直连，不并母线
                pts=[(x_out,mids[0]),(lane,mids[0]),(lane,cmid),(x_in,cmid)] \
                    if abs(mids[0]-cmid)>2 else [(x_out,mids[0]),(x_in,cmid)]
                gr.setdefault("lines",[]).append((pts,"head"))
            else:
                # G4：首尾两条腿与母线必须是同一条连续折线，两个拐角由 fillet 处理。
                #     两条独立路径端点对接一定缺一块半线宽见方的角（法律关系图已验）。
                mtop, mbot = min(mids), max(mids)
                gr.setdefault("lines",[]).append(
                    ([(x_out,mtop),(lane,mtop),(lane,mbot),(x_out,mbot)],None))
                for m in mids:                                   # 中间腿：T 字，直线 + 圆点
                    if abs(m-mtop)>1 and abs(m-mbot)>1:
                        gr.setdefault("lines",[]).append(([(x_out,m),(lane,m)],None))
                        gr.setdefault("dots",[]).append((lane,m))
                gr.setdefault("lines",[]).append(([(lane,cmid),(x_in,cmid)],"head"))
                if abs(cmid-mtop)>1 and abs(cmid-mbot)>1:
                    gr.setdefault("dots",[]).append((lane,cmid))
            # 全部走线都进自证，不只末一条：漏检的那几条正是容易被后来改动碰坏的
            ends={part["id"]}|{f'{part["id"]}{side}{i}' for i in range(len(cards))}
            for k,(pts,_) in enumerate(gr.get("lines",[])[n0:]):
                paths.append((f'{part["id"]}{side}#{k}',pts,ends))

    bad=verify(rects+labels,paths,pad=2.0)        # 标签框一并作障碍：走线压字与走线穿卡同样不许
    if bad:
        print("  G5 穿越自证未通过："); [print("   ",*b) for b in bad[:8]]; return False

    for gr in G:
        # 战场分隔：极浅灰虚线通栏；分组名用红色小标宋，贴线上沿、左对齐
        ry=gr["y"]-116*s
        o.append(f'<line x1="{xL:.0f}" y1="{ry:.1f}" x2="{xR+col["right"]:.0f}" y2="{ry:.1f}" '
                 f'stroke="#DCDFE3" stroke-width="{1.2*s:.1f}" stroke-dasharray="{6*s:.0f} {4*s:.0f}"/>')
        o.append(f'<text x="{xL:.0f}" y="{ry+26*s:.0f}" font-size="{15*s:.0f}" font-weight="700" '
                 f'fill="{RED}" font-family="{TITLE_FONT}">{gr["part"]["label"]}</text>')
        cid=gr["part"]["id"]+"C"
        if gr["part"].get("emph"):
            draw(o,gr["cC"],xC,gr["y"],gr["Hg"],g,RED,"#FFFFFF","#FFFFFF",tag=cid)   # 全图唯一深红
        else:
            draw(o,gr["cC"],xC,gr["y"],gr["Hg"],g,STEP,tag=cid)
        for c,xs,yy,hh,tg in gr.get("draw",[]): draw(o,c,xs,yy,hh,g,CARD,tag=tg)
        for pts,kind in gr.get("lines",[]):
            red = bool(gr["part"].get("emph"))          # 深红整束：进入决定性要件的走线
            mk_=(' marker-end="url(#r)"' if red else ' marker-end="url(#a)"') if kind=="head" else ''
            ST = SR if red else S
            o.append(f'<path d="{fillet(pts,R)}" {ST}{mk_}/>')
        dotc = RED if gr["part"].get("emph") else LINE
        dotr = (SWe if gr["part"].get("emph") else SWc)*2
        for dx,dy in gr.get("dots",[]):
            o.append(f'<circle cx="{dx:.1f}" cy="{dy:.1f}" r="{dotr:.1f}" fill="{dotc}"/>')
        # 对位线：第 i 对的左右两张卡互相对应（主张↔回应、反制↔再回应）
        Ls=[d for d in gr.get("draw",[]) if d[1]<xC]; Rs=[d for d in gr.get("draw",[]) if d[1]>xC]
        for i,(_,lx,ly,lh,_t) in enumerate(Ls if Rs else []):     # 右侧空则无对位可言
            j=min(i,len(Rs)-1)                      # 反制无对应再回应时，退回与回应相连
            (_,rx_,ry_,rh,_t2)=Rs[j]
            above=(i==0)
            py = (gr["y"]-44*s) if above else (gr["y"]+gr["Hg"]+44*s)
            y_l = (ly-trimP) if above else (ly+lh+trimP)
            y_r = (ry_-trimP) if above else (ry_+rh+trimP)
            pts=[(lx+col["left"]/2,y_l),(lx+col["left"]/2,py),(rx_+col["right"]/2,py),(rx_+col["right"]/2,y_r)]
            lab = "主张 ↔ 回应" if above else ("反制 ↔ 再回应" if len(Rs)>1 else "反制 ↔ 回应")
            o.append(f'<path d="{fillet(pts,R)}" stroke="{SOFT}" stroke-width="{SWp:.2f}" fill="none" '
                     f'stroke-linejoin="round" marker-start="url(#b)" marker-end="url(#p)"/>')
            o.append(f'<text x="{(lx+rx_+col["left"])/2:.0f}" y="{py+(-9*s if above else 17*s):.0f}" '
                     f'font-size="{12*s:.0f}" fill="{NOTE}" text-anchor="middle">{lab}</text>')
        for lab,lx0,ly,an,FSe in gr.get("labels",[]):      # 位置在布局阶段算好并已过穿越自证
            o.append(f'<text x="{lx0:.0f}" y="{ly:.0f}" font-size="{FSe:.0f}" '
                     f'font-weight="600" fill="{INK2}" text-anchor="{an}">{lab}</text>')

    # ---------- 索引表：照参考图的做法 ----------
    # 圆角细框；标题居中在框内顶部，其下一条横线；列头加粗无底色，其下一条横线；
    # 行间不划线；结论用深红实心块放在框外右下。
    PADT=14*s          # 表框顶到标题的留白
    INSET=26*s        # 横线与文字共用同一内缩，列全部落在线内
    Wc=(xR+col["right"])-xL
    COLS=[("编号",0.17,"start"),("请求权基础 / 核心要件",0.41,"start"),
          ("证明责任",0.15,"start"),("证明前景",0.11,"middle"),("详见",0.16,"end")]
    Wi=Wc-2*INSET; x_in0=xL+INSET
    xs_=[x_in0]; [xs_.append(xs_[-1]+w*Wi) for _,w,_ in COLS[:-1]]
    rowh=36*s
    tbl_y = Htot
    tbl_h = PADT + 30*s + 16*s + rowh + rowh*len(data["parts"]) + PADT
    o.append(f'<rect x="{xL:.0f}" y="{tbl_y:.0f}" width="{Wc:.0f}" height="{tbl_h:.0f}" rx="{10*s:.0f}" '
             f'fill="none" stroke="{SOFT}" stroke-width="{1.4*s:.1f}"/>')
    cy_=tbl_y+PADT+24*s
    o.append(f'<text x="{xL+Wc/2:.0f}" y="{cy_:.0f}" font-size="{17*s:.0f}" font-weight="700" fill="{INK}" '
             f'font-family="{TITLE_FONT}" text-anchor="middle">对抗部分索引</text>')
    cy_+=20*s
    o.append(f'<line x1="{x_in0:.0f}" y1="{cy_:.1f}" x2="{x_in0+Wi:.1f}" y2="{cy_:.1f}" '
             f'stroke="{SOFT}" stroke-width="{1.2*s:.1f}"/>')
    cy_+=rowh*0.72
    for (t,w,al),x0 in zip(COLS,xs_):
        ax = x0 if al=="start" else (x0+w*Wi/2 if al=="middle" else x0+w*Wi)
        o.append(f'<text x="{ax:.0f}" y="{cy_:.0f}" font-size="{13*s:.0f}" font-weight="700" fill="{INK}" '
                 f'text-anchor="{al}">{t}</text>')
    cy_+=14*s
    o.append(f'<line x1="{x_in0:.0f}" y1="{cy_:.1f}" x2="{x_in0+Wi:.1f}" y2="{cy_:.1f}" '
             f'stroke="{SOFT}" stroke-width="{1.2*s:.1f}"/>')
    BURDEN={"claim":"提出请求的一方","defend":"抗辩的一方"}
    for p in data["parts"]:
        c=p["center"]; cy_+=rowh
        cells=[p["id"], c["title"], BURDEN.get(c.get("burden"),"—"), c.get("prospect","—"), f'分析表 {p.get("ref","—")} 行']
        for (t,(h,w,al)),x0 in zip(zip(cells,COLS),xs_):
            ax = x0 if al=="start" else (x0+w*Wi/2 if al=="middle" else x0+w*Wi)
            # 分散态不作单点强调：图上不标，母表也不标，两边同一条纪律
            fill = RED if (h=="编号" and p.get("_hit") and not data.get("scattered")) else INK2
            fam  = f' font-family="{TITLE_FONT}" font-weight="700"' if h=="编号" else ""
            txt  = wrap_w(str(t), w*Wi-14*s, 13*s)[0]
            o.append(f'<text x="{ax:.0f}" y="{cy_:.0f}" font-size="{13*s:.0f}" fill="{fill}" '
                     f'text-anchor="{al}"{fam}>{txt}</text>')
    ey=tbl_y+tbl_h+26*s
    emph=[p for p in data["parts"] if p.get("emph")]
    concl = (f'决定性要件 · {emph[0].get("concl") or emph[0]["label"]}' if emph else
             (f'决定性要件 {n_emph} 处，争点分散：' + " / ".join(p["id"] for p in data["parts"] if p.get("_hit"))
              if data.get("scattered") else ""))
    # T6 图例三行整宽排在上，结论条另起一行排在其下，两者纵向分开——
    # 挤在同一行放不下：图例本身就占满幅宽，分散态下结论条又要列出全部编号，
    # 一路向左压到图例上去（实测四处决定性要件时压住两行）。
    LEG_H = (80 if data.get("scope_note") else 60)*s
    if concl:
        # 宽度由文字反解，不写死比例：标题变长时钉死的 0.46 会让字溢出红块
        fs = 16*s
        while fs > 12*s and text_w(concl,fs)+56*s > Wc: fs -= 0.5*s
        cy = ey + LEG_H
        cw=min(Wc, max(Wc*0.46, text_w(concl,fs)+56*s)); cx=xL+Wc-cw
        o.append(f'<rect x="{cx:.0f}" y="{cy:.0f}" width="{cw:.0f}" height="{50*s:.0f}" rx="{10*s:.0f}" fill="{RED}"/>')
        o.append(f'<text x="{cx+cw/2:.0f}" y="{cy+32*s:.0f}" font-size="{fs:.0f}" font-weight="700" '
                 f'fill="#FFFFFF" text-anchor="middle">{concl}</text>')
    o.append(f'<text x="{xL:.0f}" y="{ey+20*s:.0f}" font-size="{12*s:.0f}" fill="{NOTE}">'
             + ("本图只呈现客观研判，攻防着力点与诉请设计不进此图 ｜ " if data.get("stance") else "")
             + f'判据：有争议 × 客观证明责任在提出请求的一方 × 现有证据未达证明标准，三条同时命中即决定性要件</text>')
    o.append(f'<text x="{xL:.0f}" y="{ey+40*s:.0f}" font-size="{12*s:.0f}" fill="{NOTE}">'
             + ("本案命中三处以上，按分散态出图：不作单点强调，决定性要件逐项见表 ｜ "
                if data.get("scattered") else "深红＝决定性要件与其走线 ｜ ")
             + f'浅灰双向线＝四段对位 ｜ 通栏虚线＝对抗部分分界 ｜ 详细内容见 Excel 母表</text>')
    if data.get("scope_note"):
        # S2 材料不全是庭前常态，但必须写在图上。不写，读图的人会默认它看过全部卷宗。
        o.append(f'<text x="{xL:.0f}" y="{ey+60*s:.0f}" font-size="{12*s:.0f}" font-weight="700" fill="{INK}">'
                 f'{data["scope_note"]}　该部分攻防以未获取留位，不作对方未主张处理</text>')
    Htot=ey+LEG_H+(50*s if concl else 0)+30*s

    body=(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{Htot:.0f}" viewBox="0 0 {W} {Htot:.0f}" '
          f'font-family="{BODY_FONT}"><rect width="{W}" height="{Htot:.0f}" fill="{BG}"/><defs>{mk}{mkr}{mkp}{mkb}</defs>')
    open(out,"w",encoding="utf-8").write(body+"\n".join(o)+"</svg>")
    print(f"  {out}  {W}×{Htot:.0f}  比 {W/Htot:.3f}  行组 {len(G)}  卡片 {len(rects)}")
    print(f"  G5 穿越自证通过：{len(paths)} 段走线，0 处穿过非端点卡片或边标签（障碍 {len(rects)+len(labels)} 块）")
    return True

if __name__=="__main__":
    sys.exit(0 if render(json.load(open(sys.argv[1],encoding="utf-8")), sys.argv[2]) else 1)
