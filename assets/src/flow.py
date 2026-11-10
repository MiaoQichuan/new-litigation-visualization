# 「怎么配合」流程图（中英两版）。在本目录运行 `python3 flow.py`，得到 flow.svg 与 flow-en.svg（引用 ../icons/ 里的模块图标）；
# 再用浏览器按 1820 宽、1.25 倍截图，存为 ../flow.png 与 ../flow-en.png。改模块、改文字只改这个脚本。
# 四段：手上的材料 → 先理清（V8）→ 再出交付件（V1–V7）→ 拿到的成果。
# 实线：读材料或读上游写好的文件；虚线：律师的工作先后，不传文件。
import sys
W, H, TOP = 1820, 1270, 96
C = '#4F5660'; G = '#EEF0F2'; P = '#F3F4F5'; R = '#9C1C1C'; RT = '#F8EEEE'
T1, T2, T3 = '#1F2328', '#6B727C', '#9AA0A8'
L = {
 'zh': dict(font='Noto Sans CJK SC, Noto Sans SC, sans-serif', fs=(18, 14),
   head=[(0, '手上的材料'), (262, '先理清'), (530, '再出交付件'), (1578, '拿到的成果')],
   g=[('三大主力', '日常出图'), ('庭前三大法宝', '开庭之前'), ('课件组合', '讲课与汇报')],
   v8=('第一站', '材料刚到手'),
   inp=[('一张已有的图', '手绘、截图、AI 生成'), ('一个案件的材料', '诉辩状、合同、证据、判决'), ('', 'PDF、扫描件、照片、聊天记录'), ('一组法律数据', '判决结果、案由、金额')],
   outp=[('可编辑的图', 'SVG、PPTX、PNG 等'), ('溯源索引', '每一项对得回原句'), ('大事记三件套', 'Word、Excel、A4 简表'),
         ('对抗图与分析表', '庭前推演、向当事人汇报'), ('一套课件', '导出可编辑 PPT'), ('一页统计图', '标题里的数算得出'),
         ('一张案件看板', '可导出事实表与大事记')],
   e=('事实底稿', '理清、裁决之后，再出交付件'),
   m=['诉讼可视化重画', '时间轴大师', '法律关系图大师', '大事记表大师', '庭审对抗图大师', '法律图表大师', '法律课件大师', '案件看板大师'],
   legend=('读材料或上游文件', '工作先后，不传文件')),
 'en': dict(font='Inter, Noto Sans, Noto Sans CJK SC, sans-serif', fs=(16, 12.5),
   head=[(0, 'What you have'), (262, 'Sort it out'), (530, 'Make the deliverables'), (1578, 'What you get')],
   g=[('Core three', 'everyday figures'), ('Pre-trial three', 'before the hearing'), ('Teaching pair', 'lectures, briefings')],
   v8=('First stop', 'files just arrived'),
   inp=[('An existing chart', 'Hand-drawn, screenshot, AI-made'), ('A case\'s files', 'Pleadings, contracts, evidence'), ('', 'PDF, scans, photos, chats'), ('A set of legal data', 'Outcomes, causes, amounts')],
   outp=[('Editable figures', 'SVG, PPTX, PNG and more'), ('Trace index', 'Each item back to its sentence'), ('Chronicle set', 'Word, Excel, A4 brief'),
         ('Confrontation map', 'Rehearsal, client briefing'), ('A slide deck', 'Editable PPTX'), ('A one-page chart', 'Every number computed'),
         ('An interactive case board', 'Exports facts and chronicle')],
   e=('fact base', 'Sorted and ruled on, then deliver'),
   m=['Visual Redraw', 'Timeline', 'Relationships', 'Chronicle', 'Confrontation', 'Legal Charts', 'Courseware', 'Case Board'],
   legend=('reads files or upstream output', 'order of work, no file passed')),
}
def build(lang):
    t = L[lang]; f1, f2 = t['fs']; out = []
    def box(x, y, w, h, a, b, fill=G):
        out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="{fill}"/>')
        out.append(f'<text x="{x+20}" y="{y+h/2-4}" font-size="{f1}" font-weight="600" fill="{T1}">{a}</text>')
        out.append(f'<text x="{x+20}" y="{y+h/2+20}" font-size="{f2}" fill="{T2}">{b}</text>')
    def panel(x, y, w, h, fill=P): out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="22" fill="{fill}"/>')
    def glabel(x, y, a, b, col=T1):
        out.append(f'<text x="{x}" y="{y}" font-size="17" font-weight="600" fill="{col}">{a}<tspan dx="12" font-size="14" font-weight="400" fill="{T3}">{b}</tspan></text>')
    def mod(x, y, v, name, below=False):
        out.append(f'<image href="../icons/{v}.png" x="{x}" y="{y}" width="138" height="138"/>')
        if below:
            out.append(f'<text x="{x+69}" y="{y+166}" font-size="13" fill="{T3}" text-anchor="middle">{v.upper()}</text>')
            out.append(f'<text x="{x+69}" y="{y+192}" font-size="18" font-weight="600" fill="{T1}" text-anchor="middle">{name}</text>')
        else:
            out.append(f'<text x="{x+152}" y="{y+60}" font-size="13" fill="{T3}">{v.upper()}</text>')
            out.append(f'<text x="{x+152}" y="{y+88}" font-size="18" font-weight="600" fill="{T1}">{name}</text>')
    def path(pts, arrow=True, r=8, dash=False, col=C):
        d = f'M{pts[0][0]},{pts[0][1]}'
        for i in range(1, len(pts) - 1):
            (x0, y0), (x1, y1), (x2, y2) = pts[i-1], pts[i], pts[i+1]
            dx0, dy0 = (x1 > x0) - (x1 < x0), (y1 > y0) - (y1 < y0)
            dx1, dy1 = (x2 > x1) - (x2 < x1), (y2 > y1) - (y2 < y1)
            d += f' L{x1 - dx0*r},{y1 - dy0*r} Q{x1},{y1} {x1 + dx1*r},{y1 + dy1*r}'
        d += f' L{pts[-1][0]},{pts[-1][1]}'
        mk = ('marker-end="url(#arr)"' if col == R else 'marker-end="url(#ar)"') if arrow else ''
        out.append(f'<path d="{d}" fill="none" stroke="{col}" stroke-width="2"{" stroke-dasharray=\"7 6\"" if dash else ""} {mk}/>')
    def elabel(x, y, s, col=T2, anchor='start'): out.append(f'<text x="{x}" y="{y}" font-size="14" fill="{col}" text-anchor="{anchor}">{s}</text>')
    X = 220  # 模块与成果整体右移
    # 分组底
    panel(290+X, 72, 995, 226); panel(940+X, 72, 345, 810, '#EAECEE'); panel(290+X, 577, 645, 305)
    panel(262, 330, 216, 300, RT)
    glabel(312+X, 272, *t['g'][0]); glabel(1000+X if lang == 'en' else 1122+X, 858, *t['g'][1]); glabel(312+X, 603, *t['g'][2])
    out.append(f'<text x="370" y="368" font-size="17" font-weight="700" fill="{R}" text-anchor="middle">{t["v8"][0]}</text>')
    out.append(f'<text x="370" y="390" font-size="14" fill="{T3}" text-anchor="middle">{t["v8"][1]}</text>')
    # 输入
    i = t['inp']
    box(0, 136, 230, 74, *i[0])
    out.append(f'<rect x="0" y="420" width="230" height="96" rx="10" fill="{G}"/>')
    out.append(f'<text x="20" y="454" font-size="{f1}" font-weight="600" fill="{T1}">{i[1][0]}</text>')
    out.append(f'<text x="20" y="478" font-size="{f2}" fill="{T2}">{i[1][1]}</text>')
    out.append(f'<text x="20" y="499" font-size="{f2}" fill="{T2}">{i[2][1]}</text>')
    box(0, 677, 230, 74, *i[3])
    # 成果
    o = t['outp']; ox = 1358+X
    for (y, h), (a, b) in zip([(102, 70), (185, 70), (516, 70), (781, 70), (897, 70), (990, 70), (1100, 70)], o):
        box(ox, y, 242, h, a, b, fill=(RT if a == o[-1][0] else G))
    # 线
    path([(230, 173), (318+X, 173)])                                          # 已有的图 → V1（从第一站上方过去）
    path([(230, 468), (299, 468)])                                            # 材料 → V8
    path([(250, 468), (250, 312), (620+X, 312), (620+X, 173), (643+X, 173)])  # 材料 → V2
    path([(620+X, 312), (1018+X, 312), (1018+X, 244)])                        # 材料 → V3
    path([(900+X, 312), (900+X, 452), (968+X, 452)])                          # 材料 → V4
    path([(230, 714), (318+X, 714)])                                          # 数据 → V6（从第一站下方过去）
    for x in (389+X, 714+X, 1040+X):
        path([(x, 104), (x, 42), (1320+X, 42)], arrow=False)
    path([(1320+X, 42), (1320+X, 137), (1356+X, 137)]); path([(1320+X, 137), (1320+X, 220), (1356+X, 220)])
    path([(1062+X, 383), (1062+X, 244)]); elabel(1076+X, 314+14, t['e'][0])
    path([(1040+X, 523), (1040+X, 643)]); elabel(1054+X, 583, t['e'][0])
    path([(1062+X, 523), (1062+X, 551), (1356+X, 551)])
    path([(1040+X, 785), (1040+X, 816), (1356+X, 816)])
    path([(410+X, 785), (410+X, 815), (620+X, 815), (620+X, 714), (643+X, 714)])
    path([(1018+X, 643), (1018+X, 615), (714+X, 615), (714+X, 643)])
    path([(714+X, 785), (714+X, 932), (1356+X, 932)])
    path([(368+X, 785), (368+X, 1025), (1356+X, 1025)])
    # V8：成果走最下面；虚线指向庭前三件与日常出图
    path([(370, 612), (370, 1135), (1356+X, 1135)], col=R)
    path([(440, 520), (938+X, 520)], dash=True, col=R)
    elabel(560+X, 508, t['e'][1], col=R, anchor='middle')
    # 图例
    lx, ly = 760, 34 - TOP - 5
    path([(lx, ly), (lx+46, ly)]); elabel(lx+58, ly+5, t['legend'][0])
    lx2 = lx + (250 if lang == 'zh' else 300)
    path([(lx2, ly), (lx2+46, ly)], dash=True, col=R); elabel(lx2+58, ly+5, t['legend'][1])
    # 模块
    m = t['m']
    mod(320+X, 104, 'v1', m[0]); mod(645+X, 104, 'v2', m[1]); mod(970+X, 104, 'v3', m[2])
    mod(970+X, 383, 'v4', m[3]); mod(970+X, 645, 'v5', m[4])
    mod(320+X, 645, 'v6', m[5]); mod(645+X, 645, 'v7', m[6])
    mod(301, 410, 'v8', m[7], below=True)
    # 段落标题
    hd = []
    for x, s in t['head']:
        hd.append(f'<text x="{x}" y="34" font-size="15" font-weight="700" letter-spacing="1" fill="{T3}">{s}</text>')
        hd.append(f'<rect x="{x}" y="48" width="28" height="3" rx="1.5" fill="{R if x == 262 else "#C9CDD2"}"/>')
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="{t['font']}">
<defs><marker id="ar" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="{C}"/></marker>
<marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="{R}"/></marker></defs>
<rect width="{W}" height="{H}" fill="#FFFFFF"/>
{chr(10).join(hd)}
<g transform="translate(0,{TOP})">
{chr(10).join(out)}
</g>
</svg>'''
for lang, fn in (('zh', 'flow.svg'), ('en', 'flow-en.svg')):
    open(fn, 'w', encoding='utf-8').write(build(lang))
