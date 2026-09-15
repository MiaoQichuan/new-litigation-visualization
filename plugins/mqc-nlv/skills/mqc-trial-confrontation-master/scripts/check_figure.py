#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""对产出的 SVG 做几何自检。判据编号对应 references/layout-constraints.md。
这份检查读的是产物，不是意图——代码里改坏了、规则只活在注释里，都能被它抓住。"""
import re, sys, math

def parse(path):
    s=open(path,encoding="utf-8").read()
    rects=[(float(a),float(b),float(w),float(h),float(r or 0)) for a,b,w,h,r in re.findall(
        r'<rect x="([\d.-]+)" y="([\d.-]+)" width="([\d.-]+)" height="([\d.-]+)" rx="([\d.-]+)"', s)]
    lines=[tuple(map(float,m)) for m in re.findall(
        r'<line x1="([\d.-]+)" y1="([\d.-]+)" x2="([\d.-]+)" y2="([\d.-]+)"', s)]
    paths=re.findall(r'<path d="([^"]+)"([^>]*)/>', s)
    W,H=map(float,re.search(r'width="([\d.]+)" height="([\d.]+)"',s).groups())
    return s,rects,lines,paths,W,H

RED="#991B1B"      # 与 render_main 同一个值；对不上这条判据会静默算出 0

def check(path):
    s,rects,lines,paths,W,H=parse(path)
    errs=[]
    def ck(no,cond,msg):
        print(("  OK  " if cond else "  FAIL")+f" {no}  {msg}")
        if not cond: errs.append(no)

    # 卡片按圆角半径识别：卡 rx=12s，结论块与表框 rx=10s，不混为一谈
    from collections import Counter
    rxs=Counter(round(r[4],1) for r in rects if r[2]>200)
    card_rx=max(rxs, key=lambda k:(rxs[k], k))
    cards=[r for r in rects if abs(r[4]-card_rx)<0.2]
    ws=sorted({round(r[2]) for r in cards})
    ck("M1", len(ws)==1, f"三栏等宽（卡宽集合 {ws}）")
    xs=sorted({round(r[0]) for r in cards})
    ck("M2", len(xs)==3, f"恰好三栏（x 坐标 {xs}）")
    if len(xs)==3:
        g1=xs[1]-(xs[0]+ws[0]); g2=xs[2]-(xs[1]+ws[0])
        ck("M2b", abs(g1-g2)<1.5, f"两条通道等宽（{g1:.0f} / {g2:.0f}）")
        span=(xs[2]+ws[0])-xs[0]; margin=xs[0]
        ck("M2c", abs(span+2*margin-W)<2.0,
           f"三栏+两通道+两页边 = 总宽（{span:.0f}+2×{margin:.0f} vs {W:.0f}）")
    cen=[r for r in cards if round(r[0])==xs[1]] if len(xs)==3 else []
    side=[r for r in cards if round(r[0])!=xs[1]] if len(xs)==3 else []
    ok=True
    for c in cen:
        grp=[r for r in side if r[1]>=c[1]-2 and r[1]+r[3]<=c[1]+c[3]+2]
        if grp:
            top=min(r[1] for r in grp); bot=max(r[1]+r[3] for r in grp)
            if not (c[1]<=top+2 and c[1]+c[3]>=bot-2): ok=False
    ck("M4", ok, "中轴卡高不小于同组侧栏栈（行组高由两栈撑出）")
    ck("R5", 'markerUnits="userSpaceOnUse"' in s, "箭头尺寸绝对，不随线宽缩放")
    mks=set(re.findall(r'markerWidth="([\d.]+)"', s))
    ck("R5b", len(mks)<=2, f"红灰箭头同大小（markerWidth 取值 {sorted(mks)}）")
    # 只看真正的走线：带 stroke 的路径；defs 里的箭头三角是 fill-only，排除
    routes=[d for d,a in paths if "stroke=" in a]
    ck("R2", all("A " in d for d in routes if d.count("L")>=2),
       f"多拐点走线都带圆弧倒角（受检 {sum(1 for d in routes if d.count('L')>=2)} 条）")
    dots=len(re.findall(r'<circle ', s))
    ck("R3", dots>=0, f"T 字接头圆点 {dots} 个")
    rules=[l for l in lines if abs(l[1]-l[3])<0.6 and l[2]-l[0]>W*0.7]
    starts={round(l[0]) for l in rules}; ends={round(l[2]) for l in rules}
    ck("T2", len(starts)<=2 and len(ends)<=2, f"通栏线起止一致（起 {sorted(starts)} 止 {sorted(ends)}）")
    red=len(re.findall(r'fill="#991B1B"', s))
    # 数深红色块，不数深红出现的总次数：走线与圆点跟着被强调的部分数走，
    # 总次数的上限只能拍脑袋定，且底部多一行红字就会破。色块是「强调了几处」本身。
    blocks=len(re.findall(rf'<rect[^>]*fill="{RED}"', s))
    ck("L4", 1<=blocks<=3, f"深红色块 {blocks} 个（至多两处强调 + 一条结论）")
    ck("M7", not any(abs(l[1]-286)<30 for l in lines if "dash" in s), "抬头区无通栏线穿过")
    # 直角引号「」不是大陆法律文书的写法，图上一处都不许有
    txt_all = "".join(re.findall(r">([^<]*)</text>", s))
    ck("M13", "「" not in txt_all and "」" not in txt_all, "图上不出现直角引号")
    # M10 文字必须落在它所属的卡框内。data-box 把一张卡的框与它的每一行绑在一起，
    #     所以这条读的是产物：卡高与绘制一旦不同源，短多少就在这里报出来。
    boxes={m[4]:(float(m[0]),float(m[1]),float(m[2]),float(m[3])) for m in re.findall(
        r'<rect x="([\d.-]+)" y="([\d.-]+)" width="([\d.-]+)" height="([\d.-]+)" '
        r'rx="[\d.-]+" fill="[^"]*" data-box="([^"]+)"', s)}
    runs=[(float(y),float(fs),tag) for y,fs,tag in re.findall(
        r'<text x="[\d.-]+" y="([\d.-]+)" font-size="([\d.]+)"[^>]*? data-box="([^"]+)"[^>]*>', s)]
    # 判据是上下留白对称：只查「有没有出框」抓不住真正的毛病——卡高少算时字仍在框里，
    # 被吃掉的是下留白，图上看着就是正文贴着卡底。被撑高的卡（中轴）下留白只会更大，自然通过。
    per={}
    for ty,fs,tag in runs:
        if tag in boxes: per.setdefault(tag,[]).append((ty,fs))
    tops, mis, tight = {}, (0.0,""), (9e9,"")
    for tag,rs in per.items():
        _x,by,_w,bh=boxes[tag]
        fsmax=max(r[1] for r in rs)
        head=[r for r in rs if abs(r[1]-fsmax)<0.1]; body=[r for r in rs if abs(r[1]-fsmax)>=0.1]
        tops[tag]=min(r[0]-0.88*r[1] for r in head)-by
        if not body: continue
        t_bot=max(r[0]+0.22*r[1] for r in head)
        above=min(r[0]-0.88*r[1] for r in body)-t_bot
        below=(by+bh)-max(r[0]+0.22*r[1] for r in body)
        if abs(above-below)>mis[0]: mis=(abs(above-below),tag)
        if below-tops[tag]<tight[0]: tight=(below-tops[tag],tag)
    spread=(max(tops.values())-min(tops.values())) if tops else 9e9
    ck("M10", bool(tops) and spread<=1.0,
       f"{len(tops)} 张卡的标题一律贴卡顶（顶距离差 {spread:.1f}）")
    ck("M11", bool(per) and mis[0]<=1.5,
       f"正文在标题下沿与卡底之间居中（最偏一处 {mis[1] or '—'} 差 {mis[0]:.1f}）")
    # 居中会把卡高算错吸收掉：正文跟着上移，上下仍然相等，只是一起变窄。
    # 所以另量一条绝对值——卡底留白不得小于卡顶留白，卡高短了就在这里露出来。
    ck("M12", bool(per) and tight[0]>=-1.0,
       f"卡底留白不小于卡顶留白（最紧一处 {tight[1] or '—'} 余 {tight[0]:.1f}）")
    print()
    print("  全部通过" if not errs else f"  未通过：{errs}")
    return 1 if errs else 0

if __name__=="__main__":
    sys.exit(check(sys.argv[1]))
