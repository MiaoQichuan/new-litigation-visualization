# -*- coding: utf-8 -*-
"""法律关系图 · 端口分配。

**优先级已定：保住 k 对齐 > 避免背向出发。**

这不是算出来的，是看图定的。两种优先级各画一张对照过：

  甲　不撑大优先：直连 11/13，交叉 0，拐弯 8，六条判据全过。
      代价是两条边背向出发、沿画布外围绕行。
  乙　正向优先：  直连 7/13，交叉 0，拐弯 13，**G1 失败、2 处穿节点**。
      某一侧被撑大到 4 个端口，通向同一个邻居的几条线全变成拐弯，
      图上出现一片梳子状的折线。

结论是甲，乙不可用。由此可以推出两件事，后面的实现都要守住：

1. 沿外围绕行是可接受的形态，路径生成器必须支持外围通道，
   不能把「绕远」当成失败。
2. 目标函数**不得**加入惩罚单条关系最大跨度的项。加了会重罚甲的
   两条外框线，结果会倒向乙。长度项保持除以 26 的轻权重。
"""
__doc_orig__ = """法律关系图 · 端口分配。

给定布局与关系表，决定每条关系从哪一侧的第几个端口出发与进入。

做法是确定性的：固定候选顺序、固定平局键、固定迭代预算，
相同输入必得相同输出。但它**不是**「无搜索且总是最优」——
某一侧的端口数从 1 变 2，会把端口从中点挪到三分位，
已经放好的线也跟着动，所以只能迭代到稳定，不能一次算准。

八方位的候选边对取自验算报告 5.1，容量与间距取自 relation_core。
"""
import sys
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
from relation_core import CAP, PORT_GAP, D_OUT, D_IN
NW, NH = 140, 48

# 八方位的候选边对，按优先级。同格不分配。
DIR = {"L": (-1, 0), "R": (1, 0), "T": (0, -1), "B": (0, 1)}

CANDIDATES = {
    "E":  [("R", "L")],
    "W":  [("L", "R")],
    "S":  [("B", "T")],
    "N":  [("T", "B")],
    "SE": [("R", "T"), ("B", "L")],
    "SW": [("L", "T"), ("B", "R")],
    "NE": [("R", "B"), ("T", "L")],
    "NW": [("L", "B"), ("T", "R")],
}
# 同行或同列被挡住时的绕行边对
DETOUR = {
    "E":  [("T", "T"), ("B", "B")],
    "W":  [("T", "T"), ("B", "B")],
    "S":  [("L", "L"), ("R", "R")],
    "N":  [("L", "L"), ("R", "R")],
}


def bearing(pa, pb, tol=0.5):
    dx, dy = pb[0] - pa[0], pb[1] - pa[1]
    if abs(dy) < tol:
        return "E" if dx > 0 else "W"
    if abs(dx) < tol:
        return "S" if dy > 0 else "N"
    return ("SE" if dx > 0 else "SW") if dy > 0 else ("NE" if dx > 0 else "NW")


def port_offsets(k, side):
    """一条边上 k 个端口相对中点的偏移。
    k=1 必须落在中点；k≥2 按等分位，且间距不得小于 26。"""
    L = NW if side in "TB" else NH
    if k <= 0:
        return []
    if k == 1:
        return [0.0]
    if L / (k + 1) < PORT_GAP:
        raise ValueError(f"{side} 边放不下 {k} 个端口：间距 {L/(k+1):.1f} < {PORT_GAP}")
    return [L * i / (k + 1) - L / 2 for i in range(1, k + 1)]


def _fits(load, nid, side):
    return load[nid][side] < CAP[side]


def assign(pos, edges, budget=8):
    """返回 {edge_index: (side_a, idx_a, k_a, side_b, idx_b, k_b)}。
    分两趟：先定每条边走哪一对侧（受容量约束），再定同侧的顺序。"""
    n = len(edges)
    sides = [None] * n
    load = {k: {"L": 0, "R": 0, "T": 0, "B": 0} for k in pos}

    # 第一趟：按方位取候选，容量不够就换备选。
    #
    # 排序有两层讲究。第一层：正对（同行或同列）的边优先，因为只有它们
    # 可能直连，被别的边挤掉就只能拐弯。第二层：候选少的优先。
    #
    # 正对优先还有一个更深的原因：端口位置按 L*i/(k+1) 等分，
    # 两个相邻主体之间的关系要全部直连，**两端对应边的端口总数 k 必须相等**。
    # 把一条不相干的边混进这两条边中的一条，k 就不等了，
    # 本可直连的几条会一起变成拐弯。实测三条平行关系因此全部多拐一次。
    def rank(i):
        a, b = edges[i][0], edges[i][1]
        br = bearing(pos[a], pos[b])
        facing = 0 if br in ("E", "W", "S", "N") else 1
        return (facing, len(CANDIDATES[br]), i)
    order = sorted(range(n), key=rank)

    # 正对的边先占住两端的对向侧，后面的边尽量让开，免得撑大 k、破坏对齐
    reserved = set()
    for i in order:
        a, b = edges[i][0], edges[i][1]
        br = bearing(pos[a], pos[b])
        if br in ("E", "W", "S", "N"):
            sa, sb = CANDIDATES[br][0]
            reserved.add((a, sa))
            reserved.add((b, sb))
    for i in order:
        a, b = edges[i][0], edges[i][1]
        br = bearing(pos[a], pos[b])
        picked = None
        facing = br in ("E", "W", "S", "N")

        def take(pairs, avoid_reserved):
            for sa, sb in pairs:
                if not _fits(load, a, sa) or not _fits(load, b, sb):
                    continue
                if avoid_reserved and not facing and (
                        (a, sa) in reserved or (b, sb) in reserved):
                    continue
                return (sa, sb)
            return None

        # 背向出发：出侧方向与位移的点积为负，意味着线要先朝反方向走出去
        # 再绕一大圈回来。它不是绝对禁止（报告的手工方案里就有一条从上边
        # 绕出画布再下来），但必须排在正向之后，否则会为了凑直连数
        # 把两条线推去绕远路。
        dx = pos[b][0] - pos[a][0]
        dy = pos[b][1] - pos[a][1]

        def facing_out(sa, sb):
            va, vb = DIR[sa], DIR[sb]
            return (va[0] * dx + va[1] * dy >= 0) and \
                   (vb[0] * -dx + vb[1] * -dy >= 0)

        prefer = CANDIDATES[br] + DETOUR.get(br, [])
        allpairs = [(x, y) for x in "LRTB" for y in "LRTB"]
        fwd = [p for p in allpairs if facing_out(*p)]
        # 退让顺序：方位对且不动保留侧 → 方位不对但不动保留侧 →
        # 方位对但要动保留侧 → 什么都不挑。
        # 中间那一档很关键：宁可从方位不对的空闲侧绕出去，
        # 也不要去撑大被正对边占住的那一侧——撑大一次，
        # 那一侧上本可直连的几条会一起变成拐弯，总账更亏。
        for pairs, avoid in ((prefer, True), (fwd, True), (allpairs, True),
                             (prefer, False), (fwd, False), (allpairs, False)):
            picked = take(pairs, avoid)
            if picked:
                break

        if picked is None:
            raise ValueError(f"第 {i} 条关系（{a}→{b}）无处可挂："
                             f"{a} 已用 {load[a]}，{b} 已用 {load[b]}")
        sides[i] = picked
        load[a][picked[0]] += 1
        load[b][picked[1]] += 1

    # 第二趟：同侧排序。T/B 一律从左到右，L/R 一律从上到下，
    # 按对端中心在相应轴上的投影排；投影相同时用节点名与边序号兜底，
    # 保证确定性。倒序会凭空制造交叉，所以方向要统一，不能沿周长绕。
    bucket = {}
    for i, (sa, sb) in enumerate(sides):
        a, b = edges[i][0], edges[i][1]
        bucket.setdefault((a, sa), []).append((i, "out", b))
        bucket.setdefault((b, sb), []).append((i, "in", a))
    idx = {}
    for (nid, side), items in bucket.items():
        axis = 0 if side in "TB" else 1
        items.sort(key=lambda t: (pos[t[2]][axis], t[2], t[0]))
        for j, (i, role, _) in enumerate(items, 1):
            idx[(i, role)] = (j, len(items))

    out = {}
    for i, (sa, sb) in enumerate(sides):
        ja, ka = idx[(i, "out")]
        jb, kb = idx[(i, "in")]
        out[i] = (sa, ja, ka, sb, jb, kb)
    return out, load


def verify(pos, edges, result, load):
    """逐项自检。任何一项不过就报出来，不吞。"""
    errs = []
    for nid, sides in load.items():
        for s, k in sides.items():
            if k > CAP[s]:
                errs.append(f"{nid} 的 {s} 边挂了 {k} 条，超过容量 {CAP[s]}")
            if k >= 2:
                L = NW if s in "TB" else NH
                if L / (k + 1) < PORT_GAP:
                    errs.append(f"{nid} 的 {s} 边 {k} 个端口，间距 "
                                f"{L/(k+1):.1f} 小于 {PORT_GAP}")
    if len(result) != len(edges):
        errs.append(f"关系 {len(edges)} 条，只分配了 {len(result)} 条")
    for i, (sa, ja, ka, sb, jb, kb) in result.items():
        if ka == 1 and port_offsets(1, sa)[0] != 0.0:
            errs.append(f"第 {i} 条的出端独占一侧却未居中")
        if kb == 1 and port_offsets(1, sb)[0] != 0.0:
            errs.append(f"第 {i} 条的入端独占一侧却未居中")
        if not (1 <= ja <= ka and 1 <= jb <= kb):
            errs.append(f"第 {i} 条的端口序号越界")
    return errs
