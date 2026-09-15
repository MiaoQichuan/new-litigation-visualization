# -*- coding: utf-8 -*-
"""建设工程施工合同纠纷 · 主体与客体并存的法律关系图。

先前只画主体之间的关系，那是不完整的。真正的法律关系要靠客体串起来：
谁和谁**就哪个工程**签了**哪份合同**。合同、工程、标的物本身就是模块，
缺了它们，「总包」「分包」这些线只能标在两个主体之间，
说不清依据的是哪一份合同、指向的是哪一段工程。

模块分两类。奇川风的色块一律圆角，**不允许直角边**，所以不能靠方角区分——
曾用 rx=0 画客体，那是违规的。改用底色深浅区分：
    主体（当事人）  圆角矩形，浅灰底
    客体（合同、工程、标的物）  同样圆角，更淡的底色

强调模块另有一套规矩，全图至多两个：
    深红实底、白字、**不加边线**

关系也随之分两类：
    主体与客体之间   签订、承建、监理、施工，实线
    客体与客体之间   标的指向、从属，虚线
"""
import sys, math
import os as _o; sys.path.insert(0, _o.path.join(_o.path.dirname(_o.path.abspath(__file__)), "..", "scripts"))
from port_plan import plan, port_offset
from optimize import refine
from label_place import place, FS

NW, NH = 140, 48
OX, OY = 150, 170
SW, R, ARROW = 1.30, 3.12, 12
SW_EMPH = 3.0        # 强调关系的线宽，规范定的是 3
# 字号按 style-tokens 的 type_scale，先前整套都偏小：
FS_TITLE, FS_SUB = 30, 13      # 文档标题 / 副标题
# 节点内的字号规范是 16 / 13，但那要配更大的模块；
# 而模块尺寸是端口容量与间距的基准，改它要同时动五个模块的常量
# （Astra 早说过几何应当随配置传递，这一步还没做）。
# 所以节点内暂取能在 140×48 里装下的最大值，并如实记下这个差距。
FS_NODE, FS_NOTE = 14, 11      # 规范 16 / 13，受模块尺寸所限
FS_LABEL = 12                  # 关系标签
# 字体栈的**第一位必须是渲染这张图的机器上真有的那一款**。
# 规范给的顺序是 PingFang SC 打头（Mac 优先），可渲染器取不到第一个
# 就直接放弃、不往后找，中文全成方块——歸藏风刚栽过一次，这里又栽一次。
# 把 Noto Sans CJK SC 提到最前，后面仍按规范排：
# Mac 用户回退到 PingFang，Windows 回退到微软雅黑，都能正常显示。
FONT_STACK = ("'Noto Sans CJK SC','PingFang SC','Microsoft YaHei',"
              "'Noto Sans SC','Helvetica Neue',Arial,sans-serif")
# 标题用宋体，正文用无衬线——法律图的标题要有公文的分量。
# 规范的首选是方正小标宋（商业字体，只按名引用、不随包分发），
# 整条链只在好看的宋体之间降级，**绝不落到仿宋**（太细太随意）。
# 交付的 PNG 规范指定用 Noto Serif CJK SC 栅格化，本机正有这一款，
# 按「第一位必须是本机真有的」把它提前，其余顺序不动。
TITLE_FONT = ("'Noto Serif CJK SC','方正小标宋简体','FZXiaoBiaoSong-B05S',"
              "'思源宋体','Source Han Serif SC','华文中宋','STZhongsong',serif")
INK, LINE, EDGE, RED, MUTED = "#1F2933", "#4B5563", "#D6DAE0", "#991B1B", "#6B7280"
FILL_SUBJ, FILL_OBJ = "#F3F4F6", "#FAFAFA"

# kind: S 主体　O 客体
NODES = [
    dict(id="OWNER", name="发包人", note="建设单位", kind="S"),
    dict(id="GC", name="总承包人", note="施工总承包", kind="S"),
    dict(id="SUB", name="分包人", note="专业分包", kind="S"),
    dict(id="ACTUAL", name="实际施工人", note="原告", kind="S"),
    dict(id="SUPER", name="监理单位", note="受托监理", kind="S"),
    dict(id="C1", name="建设工程施工合同", note="2021.3 签订", kind="O"),
    dict(id="C2", name="专业分包合同", note="2021.9 签订", kind="O"),
    dict(id="PROJ", name="涉案工程", note="A 地块 1 号楼", kind="O"),
    dict(id="PRICE", name="工程价款", note="诉讼标的 3200 万元", kind="O", hot=True),
]
EDGES = [
    ("OWNER", "C1", "签订", "c"),
    ("GC", "C1", "签订", "c"),
    ("C1", "PROJ", "承建标的", "s"),
    ("GC", "C2", "签订", "c"),
    ("SUB", "C2", "签订", "c"),
    ("C2", "PROJ", "分包范围", "s"),
    ("ACTUAL", "PROJ", "实际施工", "c"),
    ("SUPER", "PROJ", "受托监理", "c"),
    ("PROJ", "PRICE", "已完工程量对应", "s"),
    ("ACTUAL", "PRICE", "本案诉请 折价补偿", "h"),
    ("OWNER", "PRICE", "欠付范围内担责", "c"),
]


def render(path_svg=None, path_png=None):
    import tempfile as _tf
    path_svg = path_svg or _o.path.join(_tf.gettempdir(), "cobj.svg")
    path_png = path_png or _o.path.join(_tf.gettempdir(), "cobj.png")
    ids = [n["id"] for n in NODES]
    kind = {n["id"]: n["kind"] for n in NODES}
    # 布局交给求解器。手排看着像那么回事，实测却让两条本可直连的线拐了弯、
    # 还有一条绕了整个底部。主体与客体分成两组，同组的自然会靠在一起。
    from layout_heuristic import solve_large
    solver_nodes = [dict(id=n["id"], name=n["name"],
                         group=("主体" if n["kind"] == "S" else "客体"))
                    for n in NODES]
    cost, grid = solve_large(solver_nodes, [(a, b) for a, b, _, _ in EDGES],
                             (3, 3), restarts=6, sweeps=40)
    COL, ROW = 330, 190
    pos = {k: (v[1] * COL + 70, v[0] * ROW + 24) for k, v in grid.items()}
    rects = {k: (v[1] * COL, v[0] * ROW, NW, NH) for k, v in grid.items()}
    E = [(a, b) for a, b, _, _ in EDGES]
    pp, sk, sc = refine(pos, rects, E, rounds=5)
    print(f"  交叉 {sc[0]}　拐弯 {sc[1]}　长 {sc[2]:.0f}")
    skel = [[(x + OX, y + OY) for x, y in p] for p in sk]

    def uni(p, q):
        dx, dy = q[0] - p[0], q[1] - p[1]
        L = math.hypot(dx, dy)
        return (0., 0.) if L < 1e-9 else (dx / L, dy / L)

    def rounded(pts):
        out = [pts[0]]
        for p in pts[1:]:
            if abs(p[0] - out[-1][0]) > .01 or abs(p[1] - out[-1][1]) > .01:
                out.append(p)
        pts = out
        d = f"M {pts[0][0]:.2f},{pts[0][1]:.2f}"
        for i in range(1, len(pts) - 1):
            p0, p1, p2 = pts[i - 1], pts[i], pts[i + 1]
            v1, v2 = uni(p0, p1), uni(p1, p2)
            cr = v1[0] * v2[1] - v1[1] * v2[0]
            if abs(cr) < 1e-9:
                continue
            r = min(R, math.dist(p0, p1) / 2, math.dist(p1, p2) / 2)
            A = (p1[0] - v1[0] * r, p1[1] - v1[1] * r)
            B = (p1[0] + v2[0] * r, p1[1] + v2[1] * r)
            d += (f" L {A[0]:.2f},{A[1]:.2f} A {r:.2f} {r:.2f} 0 0 "
                  f"{1 if cr > 0 else 0} {B[0]:.2f},{B[1]:.2f}")
        d += f" L {pts[-1][0]:.2f},{pts[-1][1]:.2f}"
        return d

    O = []
    for n in NODES:
        x, y = rects[n["id"]][0] + OX, rects[n["id"]][1] + OY
        obj = n["kind"] == "O"
        hot = n.get("hot", False)
        # 节点包成 <g data-role="node">，强调的带 data-emph="1"。
        # 这是 v1 三风格变换认的结构：白描要认出实底块转轮廓，
        # 歸藏风要认出强调块转克莱因蓝实底。裸 rect 它一个都认不出，
        # 于是那两步「matched NOTHING」，风格就没真正生效。
        O.append(f'<g data-role="node"{" data-emph=\"1\"" if hot else ""}>')
        if hot:
            O.append(f'<rect data-kind="node" x="{x}" y="{y}" width="{NW}" '
                     f'height="{NH}" rx="12" fill="{RED}"/>')
        else:
            O.append(f'<rect data-kind="node" x="{x}" y="{y}" width="{NW}" '
                     f'height="{NH}" rx="12" '
                     f'fill="{FILL_OBJ if obj else FILL_SUBJ}" '
                     f'stroke="{EDGE}" stroke-width="1"/>')
        O.append(f'<text x="{x+NW/2:.0f}" y="{y+23:.0f}" font-size="{FS_NODE}" '
                 f'fill="{"#FFFFFF" if hot else INK}" text-anchor="middle" '
                 f'font-weight="700">{n["name"]}</text>')
        O.append(f'<text x="{x+NW/2:.0f}" y="{y+39:.0f}" font-size="{FS_NOTE}" '
                 f'fill="{"#E8D5D5" if hot else MUTED}" text-anchor="middle">'
                 f'{n["note"]}</text>')
        O.append('</g>')
    for i, p in enumerate(skel):
        q = list(p)
        v = uni(q[-2], q[-1])
        q[-1] = (q[-1][0] - v[0] * ARROW, q[-1][1] - v[1] * ARROW)
        k = EDGES[i][3]
        hot = k == "h"
        ds = " stroke-dasharray='4 3'" if k == "s" else ""
        O.append(f'<path data-kind="edge" d="{rounded(q)}" fill="none" '
                 f'stroke="{RED if hot else LINE}" stroke-width="{SW_EMPH if hot else SW}"{ds} '
                 f'marker-end="url(#{"ar" if hot else "a"})"/>')
    LAB = [e[2] for e in EDGES]
    rr = [(rects[n["id"]][0] + OX, rects[n["id"]][1] + OY, NW, NH) for n in NODES]
    lab, failed, leads = place(skel, LAB, rr,
                               priority=[i for i, e in enumerate(EDGES) if e[3] == "h"])
    print(f"  标签 {sum(1 for l in lab if l)}/{len(LAB)}")
    for i, l in enumerate(lab):
        if not l:
            continue
        x, y, anc = l
        hot = EDGES[i][3] == "h"
        O.append(f'<text x="{x:.0f}" y="{y:.0f}" font-size="{FS_LABEL}" '
                 f'fill="{RED if hot else MUTED}" text-anchor="{anc}">{LAB[i]}</text>')
    # 画布按内容算，不写死——标题要居中于**内容中心**，
    # 而规范说的居中是相对内容，不是相对一张偏心的画布。
    xs_all = [v[0] + OX for v in rects.values()] + \
             [v[0] + OX + NW for v in rects.values()] + \
             [x for p in skel for x, _ in p]
    ys_all = [v[1] + OY for v in rects.values()] + \
             [v[1] + OY + NH for v in rects.values()] + \
             [y for p in skel for _, y in p]
    W = int(max(xs_all)) + OX
    H = int(max(ys_all)) + 80
    CX = W // 2
    head = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
            f'viewBox="0 0 {W} {H}" font-family={FONT_STACK!r}>',
            f'<rect width="{W}" height="{H}" fill="#FFFFFF"/>', '<defs>'
            f'<marker id="a" markerWidth="12" markerHeight="8.4" refX="0" refY="4.2" '
            f'markerUnits="userSpaceOnUse" orient="auto">'
            f'<path d="M 0 0 L 12 4.2 L 0 8.4 Z" fill="{LINE}"/></marker>'
            f'<marker id="ar" markerWidth="12" markerHeight="8.4" refX="0" refY="4.2" '
            f'markerUnits="userSpaceOnUse" orient="auto">'
            f'<path d="M 0 0 L 12 4.2 L 0 8.4 Z" fill="{RED}"/></marker></defs>',
            # 标题居中于内容中心，顶部留天头，与内容之间留出呼吸的间隙。
            # stroke-width="0.3" 是给歸藏风认标题用的标记。
            # 加粗是 font-weight 700 加一道 0.3 的同色描边，两者缺一不可；
            # 先前只写了描边宽度没给颜色，等于没生效。
            f'<text x="{CX}" y="58" font-family={TITLE_FONT!r} '
            f'font-size="{FS_TITLE}" font-weight="700" '
            f'stroke="{INK}" stroke-width="0.3" fill="{INK}" '
            f'text-anchor="middle">'
            f'建设工程施工合同纠纷 · 主体与客体并存</text>',
            f'<text x="{CX}" y="86" font-size="{FS_SUB}" fill="{MUTED}" '
            f'text-anchor="middle">'
            f'浅灰为当事人，更淡的为合同与工程　深红实底为全图重点，至多两个</text>']
    open(path_svg, "w", encoding="utf-8").write("\n".join(head + O) + "\n</svg>")
    import cairosvg
    cairosvg.svg2png(url=path_svg, write_to=path_png, output_width=1700)


if __name__ == "__main__":
    render()
