#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""庭审对抗图 · 版面数学。零第三方依赖。
一个比例因子 s 推出全部尺寸；走线只允许四种形态；容量由不等式反解。
判据编号 M（主图）/ S（分图）/ R（走线）与 references/layout-constraints.md 一一对应。
"""
import math

class Geo:
    """沿用关系图已定的几何：圆角 = 2.4 × 线宽（切掉顶点约一个线宽），
    箭头长 12s、半角 19.3°、markerUnits 绝对、路径终点落在三角尾边内。"""
    def __init__(s_, s=1.0):
        s_.s       = s
        s_.FS      = 13.0 * s
        s_.FS_T    = 15.0 * s
        s_.LH      = 19.0 * s
        s_.PAD     = 12.0 * s
        s_.PADY    = 10.0 * s
        s_.SW      = 1.3 * s
        s_.R       = 2.4 * s_.SW
        s_.AL      = 12.0 * s
        s_.A_HALF  = 19.3
        s_.AHW     = s_.AL * math.tan(math.radians(s_.A_HALF))
        s_.TIP_GAP = 3.0 * s
        s_.OVER    = max(1.2*s, s_.AL*s_.SW/(2*s_.AHW))
        s_.LANE    = 4.0 * s_.SW
        s_.PORT    = 18.0 * s
        s_.CORNER_KEEP = 12.0 * s

CJK_W = 0.52

def chars_per_line(card_w, g):
    """M9 反解：卡宽定了每行字数就定了。"""
    return int((card_w - 2*g.PAD) // (g.FS * CJK_W))

def card_height(title_lines, body_lines, g):
    return 2*g.PADY + title_lines*(g.FS_T*1.35) + body_lines*g.LH

def columns(total_w, g, margin_ratio=0.045, gutter_ratio=0.055, center_ratio=1.0):
    """M3/M4：三栏等宽（法院审查不比两侧大），三栏加两通道精确等于可用宽。
    早先曾规定中轴须不窄于两侧 1.6 倍，实际出图后否掉：中轴过宽会让法院审查看着比双方还重。"""
    M = total_w * margin_ratio
    U = total_w - 2*M
    G = total_w * gutter_ratio
    side = (U - 2*G) / (2 + center_ratio)
    center = side * center_ratio
    assert abs(side*2 + center + 2*G - U) < 1e-6, "M4 不成立"
    assert center > 0 and side > 0, "M3 不成立：栏宽须为正"
    return {"margin":M, "usable":U, "gutter":G, "left":side, "center":center, "right":side}

def lane_capacity(gutter, g):
    """M6：栏间通道里能并排走几条线。"""
    return int((gutter - 2*g.R) // g.LANE)

def port_capacity(edge_len, g):
    """M7：一张卡的一条边上能落几条线。"""
    return max(1, int((edge_len - 2*g.CORNER_KEEP) // g.PORT) + 1)

ROUTES = {
    "R1": "同高直连：起终点同行，一条横线，零拐角",
    "R2": "跨行折线：横—竖—横，两个拐角，竖段落在栏间通道内",
    "R3": "长距绕行：中轴向下出到底部带再折回，四个拐角，专用于攻击线",
    "R4": "多线汇入：同一边框上按 PORT 间距分点落位，不新增拐角",
}

def lines_for(text_len, card_w, g, cap=None):
    """M9：卡宽定了每行字数，字数与文本长度定了行数。cap 为行数上限，超出截断并标注。"""
    cpl = chars_per_line(card_w, g)
    n = max(1, math.ceil(text_len / cpl))
    return (min(n, cap) if cap else n), (bool(cap) and n > cap)

def row_group(n_left, n_right, len_side, len_center, total_w, g, cap_side=4, cap_center=3):
    """M11：一个对抗部分占一个横向行组。
    行组高 = max(中轴卡高, 左侧诸卡总高, 右侧诸卡总高) —— 左中右由此天然对齐。
    侧栏卡高由文字反解，这是真正的自变量；中轴卡高跟随行组，不再写死。"""
    col = columns(total_w, g)
    lS, cutS = lines_for(len_side,   col["left"],   g, cap_side)
    lC, cutC = lines_for(len_center, col["center"], g, cap_center)
    hS = card_height(1, lS, g)
    hC = card_height(1, lC, g)
    gap = hS * 0.28
    stack = lambda n: n*hS + (n-1)*gap if n else 0
    h = max(hC, stack(n_left), stack(n_right))
    return {"行组高": h, "侧卡高": hS, "中轴卡高": hC, "卡间距": gap,
            "侧栏行数": lS, "中轴行数": lC, "截断": cutS or cutC,
            "侧栏每行字数": chars_per_line(col["left"], g),
            "中轴每行字数": chars_per_line(col["center"], g)}

def feasible(parts, total_w, g, max_h):
    """M10：parts 为各对抗部分的 (左卡数, 右卡数, 侧文长, 中轴文长)。"""
    col = columns(total_w, g)
    gs = [row_group(*p, total_w, g) for p in parts]
    inter = gs[0]["行组高"] * 0.22
    body = sum(x["行组高"] for x in gs) + inter*(len(gs)-1)
    total_h = 96*g.s + body + 72*g.s
    return {
        "行组数": len(gs),
        "侧栏每行字数": gs[0]["侧栏每行字数"], "中轴每行字数": gs[0]["中轴每行字数"],
        "各行组高": [round(x["行组高"]) for x in gs],
        "有截断": any(x["截断"] for x in gs),
        "通道可并排线数": lane_capacity(col["gutter"], g),
        "卡侧边可落点数": port_capacity(max(x["侧卡高"] for x in gs), g),
        "总高": round(total_h,1), "长宽比": round(total_w/total_h,3),
        "装得下": total_h <= max_h,
    }

if __name__ == "__main__":
    g = Geo(2.2)
    W, MAXH = 3000, 4800
    print("走线四形态（M5：只允许这四种，其余拒绝出图）")
    for k,v in ROUTES.items(): print(f"  {k}  {v}")
    print(f"\n主图可行域（幅宽 {W}，总高上限 {MAXH}；侧栏每行 {chars_per_line(columns(W,g)['left'],g)} 字）")
    print(f"{'部分数':>5} {'每部分左/右卡':>12} {'侧文长':>6} {'各行组高':>22} {'总高':>7} {'长宽比':>7} {'截断':>5} {'装得下':>6}")
    for np_ in (2,3,4,5,6):
        for lr in ((1,1),(2,2),(3,3)):
            for L in (30, 60, 110):
                parts=[(lr[0],lr[1],L,50)]*np_
                r=feasible(parts, W, g, MAXH)
                hs=str(r['各行组高'][:4])
                print(f"{np_:>5} {str(lr):>12} {L:>6} {hs:>22} {r['总高']:>7} {r['长宽比']:>7} "
                      f"{'是' if r['有截断'] else '否':>5} {'是' if r['装得下'] else '否':>6}")
    c = columns(W, g)
    tot = c['left']+c['center']+c['right']+2*c['gutter']+2*c['margin']
    print(f"\n三栏：左 {c['left']:.0f} · 中 {c['center']:.0f} · 右 {c['right']:.0f}；"
          f"通道 {c['gutter']:.0f}×2；页边 {c['margin']:.0f}×2 → 合计 {tot:.0f}（应为 {W}）")
