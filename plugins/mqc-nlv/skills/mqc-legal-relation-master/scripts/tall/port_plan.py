# -*- coding: utf-8 -*-
import os
"""端口规划：一次性决定所有端点落在哪一侧、每侧几个、各自序号。

这是一个独立阶段，输出只读的 PortPlan，冻结之后才进入走线。

为什么要拆出来（Astra 第二轮 3.1）：先前是在路由过程里边走边改 k，
换到已有线的边上就把该侧的端口位置全改了，已经走好的线却没重算，
结果拐弯 17 涨到 18、交叉 4 涨到 5。根因不是「下边被占用」，
而是缺少这个规划阶段。

直连的两端要对齐，需要三个条件同时成立，缺一不可：
    equal_k      两侧端口总数相同
    equal_index  同一条关系在两侧取相同的序号
    同原点       上下端口要求两节点 x 中心相同，左右端口要求 y 中心相同
端口位置是 L*i/(k+1)。k 相等只保证刻度间隔一样：k=2 与 k=2 若一端取
第 1 点、另一端取第 2 点，位置是 46.67 与 93.33，照样不直连。
"""
import sys
from itertools import permutations
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from relation_core import CAP, PORT_GAP

NW, NH = 140, 78
SIDES = ("T", "B", "L", "R")
OPP = {"L": "R", "R": "L", "T": "B", "B": "T"}
DIR = {"L": (-1, 0), "R": (1, 0), "T": (0, -1), "B": (0, 1)}


def side_len(side):
    return NW if side in "TB" else NH


def port_offset(k, i, side):
    """一条边上第 i 个端口（从 1 起）相对中点的偏移。k=1 强制落在中点。"""
    if k <= 1:
        return 0.0
    L = side_len(side)
    if L / (k + 1) < PORT_GAP:
        raise ValueError(f"{side} 边放不下 {k} 个端口：间距 {L/(k+1):.1f}")
    return L * i / (k + 1) - L / 2


def count_quads(d):
    """端点总数为 d 时，合法的 (k_T,k_B,k_L,k_R) 数量组合。
    总数最多 5×5×2×2=100 个，按 d 筛完只剩十几个。"""
    out = []
    for kt in range(CAP["T"] + 1):
        for kb in range(CAP["B"] + 1):
            for kl in range(CAP["L"] + 1):
                for kr in range(CAP["R"] + 1):
                    if kt + kb + kl + kr == d:
                        out.append((kt, kb, kl, kr))
    return out


def bearing(pa, pb, tol=0.5):
    dx, dy = pb[0] - pa[0], pb[1] - pa[1]
    if abs(dy) < tol:
        return "E" if dx > 0 else "W"
    if abs(dx) < tol:
        return "S" if dy > 0 else "N"
    return ("SE" if dx > 0 else "SW") if dy > 0 else ("NE" if dx > 0 else "NW")


CANDS = {
    "E": [("R", "L")], "W": [("L", "R")], "S": [("B", "T")], "N": [("T", "B")],
    "SE": [("R", "T"), ("B", "L")], "SW": [("L", "T"), ("B", "R")],
    "NE": [("R", "B"), ("T", "L")], "NW": [("L", "B"), ("T", "R")],
}


def must_straight(pos, edges):
    """哪些关系必须直连：四邻接（同行或同列且中间无其他主体）。
    斜对角不算相邻，沿用上一轮报告的口径。"""
    out = set()
    for idx, (a, b) in enumerate(edges):
        pa, pb = pos[a], pos[b]
        same_col = abs(pa[0] - pb[0]) < .5
        same_row = abs(pa[1] - pb[1]) < .5
        if not (same_col or same_row):
            continue
        blocked = False
        for k, p in pos.items():
            if k in (a, b):
                continue
            if same_col and abs(p[0] - pa[0]) < .5 and \
                    min(pa[1], pb[1]) < p[1] < max(pa[1], pb[1]):
                blocked = True
            if same_row and abs(p[1] - pa[1]) < .5 and \
                    min(pa[0], pb[0]) < p[0] < max(pa[0], pb[0]):
                blocked = True
        if not blocked:
            out.add(idx)
    return out


def plan(pos, edges, verbose=False, max_relax=None):
    """带放宽的规划。四邻接是「优先直连」而不是「必须直连」——
    关系密集的主体，四条边全被直连锁死之后，其余关系就无处可挂了。
    （12 主体案里主债务人有 7 条关系、四条边各锁一条直连，剩 3 条挂不上。）
    冲突时按「对端选择最多」的顺序逐条放宽，并报出放弃了哪些，
    而不是直接失败，也不是静默放弃全部。"""
    want = must_straight(pos, edges)
    deg = {}
    for a, b in edges:
        deg[a] = deg.get(a, 0) + 1
        deg[b] = deg.get(b, 0) + 1
    # 放宽顺序：两端度数之和大的先放——它们的端口本来就紧张，
    # 保住它们的直连代价最高
    order = sorted(want, key=lambda i: -(deg[edges[i][0]] + deg[edges[i][1]]))
    limit = len(want) if max_relax is None else max_relax
    relaxed = []
    for n in range(limit + 1):
        try:
            keep = set(want) - set(order[:n])
            out = _plan_once(pos, edges, keep)
            if verbose and relaxed:
                print(f"  放宽了 {len(relaxed)} 条直连要求："
                      f"{[f'{edges[i][0]}→{edges[i][1]}' for i in relaxed]}")
            return out[0], out[1], keep
        except ValueError as e:
            if n >= limit:
                raise
            relaxed = order[:n + 1]
    raise ValueError("放宽全部直连要求仍不可行")


def _plan_once(pos, edges, straight):
    """返回 PortPlan：{edge_index: (side_a, i_a, k_a, side_b, i_b, k_b)}。

    先给必须直连的关系定侧（它们的选择最受限），再给其余的填空位；
    然后按侧分配序号，直连的两端取相同序号。
    """
    n = len(edges)
    sides = [None] * n
    load = {v: {s: 0 for s in SIDES} for v in pos}
    locked = set()

    # 第一轮：必须直连的，用正对的那一对侧，没有选择余地
    for i in sorted(straight):
        a, b = edges[i]
        br = bearing(pos[a], pos[b])
        sa, sb = CANDS[br][0]
        if load[a][sa] >= CAP[sa] or load[b][sb] >= CAP[sb]:
            raise ValueError(
                f"关系 {a}→{b} 要求直连，但 {a}.{sa} 或 {b}.{sb} 容量已满。"
                f"这是真实冲突：本侧还有容量不代表整个直连约束系统可行。")
        sides[i] = (sa, sb)
        load[a][sa] += 1
        load[b][sb] += 1
        locked.add((a, sa))
        locked.add((b, sb))

    # equal_k 要传播，不能只在最后检查。
    # 直连的两侧共享同一个数量变量：一侧多挂一条，对侧也得多一条才对得齐，
    # 而对侧的端点数由关系决定、加不出来。所以被直连占用的侧就此锁死，
    # 非直连的关系一律不许再进，否则 k 必然不等。
    # 先前没做这个传播，六主体案里 LU.T 被塞到 3 个而 BANK.B 只有 1 个，
    # 那条本该直连的关系就对不齐了。

    # 第二轮：其余关系按方位取候选，容量满了换备选
    for i in range(n):
        if sides[i] is not None:
            continue
        a, b = edges[i]
        br = bearing(pos[a], pos[b])
        pick = None
        # 候选池要按方向合理性排：出侧朝着目标的排前面，背向的排最后。
        # 这条规则旧模块里写过，重写时丢了，于是出现「目标在左上方，
        # 却从下边出、上边进」——向下走去够左上方的目标，必然绕一大圈。
        dx = pos[b][0] - pos[a][0]
        dy = pos[b][1] - pos[a][1]

        def forward(pair):
            va, vb = DIR[pair[0]], DIR[pair[1]]
            fa = va[0] * dx + va[1] * dy
            fb = vb[0] * -dx + vb[1] * -dy
            return (fa >= 0) + (fb >= 0)          # 两端都正向得 2 分

        rest = sorted([(x, y) for x in SIDES for y in SIDES],
                      key=lambda pr: -forward(pr))
        pool = CANDS[br] + rest
        # 锁定侧一律不许进，没有第二档放开。
        # 放开的后果：非直连的关系挤进被直连占用的侧，该侧 k 变大，
        # 对侧的端点数却加不出来，equal_k 当场破掉。
        # 12 主体案里主债务人的下边被塞了 3 条、对侧只有 1 条，就是这么来的。
        # 宁可让这条关系绕远，也不能毁掉一条本可直连的关系。
        for sa, sb in pool:
            if load[a][sa] >= CAP[sa] or load[b][sb] >= CAP[sb]:
                continue
            if (a, sa) in locked or (b, sb) in locked:
                continue
            pick = (sa, sb)
            break
        if pick is None:
            free_a = [x for x in SIDES if load[a][x] < CAP[x] and (a, x) not in locked]
            free_b = [x for x in SIDES if load[b][x] < CAP[x] and (b, x) not in locked]
            raise ValueError(
                f"关系 {a}→{b} 无处可挂。{a} 可用侧 {free_a or '无'}，"
                f"{b} 可用侧 {free_b or '无'}。"
                f"锁定侧是直连关系占用的，让出来就会毁掉那条直连；"
                f"要解决得改布局，或者明确放弃某条直连要求。")
        sides[i] = pick
        load[a][pick[0]] += 1
        load[b][pick[1]] += 1

    # 第三轮：同侧序号。直连的两端必须取相同序号，否则位置对不上。
    idx = {}
    for v in pos:
        for s in SIDES:
            members = [i for i in range(n)
                       if (edges[i][0] == v and sides[i][0] == s)
                       or (edges[i][1] == v and sides[i][1] == s)]
            if not members:
                continue
            k = len(members)
            axis = 0 if s in "TB" else 1
            # 按对端位置排序，同向排列不会凭空制造交叉
            def key(i):
                other = edges[i][1] if edges[i][0] == v else edges[i][0]
                return (pos[other][axis], other, i)
            for j, i in enumerate(sorted(members, key=key), 1):
                idx[(i, v, s)] = (j, k)

    # 第四轮：把直连关系两端的序号强制取齐
    for i in sorted(straight):
        a, b = edges[i]
        sa, sb = sides[i]
        ja, ka = idx[(i, a, sa)]
        jb, kb = idx[(i, b, sb)]
        if ka != kb:
            raise ValueError(
                f"关系 {a}→{b} 要求直连，但 {a}.{sa} 有 {ka} 个端口、"
                f"{b}.{sb} 有 {kb} 个。equal_k 不成立，这是真实冲突。")
        if ja != jb:
            # 同侧内交换序号，把这条关系的两端调到同一位
            for other in range(n):
                if other == i:
                    continue
                if (edges[other][0] == b and sides[other][1 - 1] == sb) or \
                   (edges[other][1] == b and sides[other][1] == sb):
                    pass
            idx[(i, b, sb)] = (ja, kb)
            # 被顶掉的那个端点接手原来的位置
            for other in range(n):
                if other == i:
                    continue
                for role, v2 in ((0, edges[other][0]), (1, edges[other][1])):
                    if v2 == b and sides[other][role] == sb and \
                            idx.get((other, b, sb), (None,))[0] == ja:
                        idx[(other, b, sb)] = (jb, kb)

    out = {}
    for i in range(n):
        a, b = edges[i]
        sa, sb = sides[i]
        ja, ka = idx[(i, a, sa)]
        jb, kb = idx[(i, b, sb)]
        out[i] = (sa, ja, ka, sb, jb, kb)
    return out, load, straight


def verify(pos, edges, plan_out, straight):
    """把 Astra 列的三个条件逐条验。任何一条不过就报出来。"""
    errs = []
    for i, (sa, ja, ka, sb, jb, kb) in plan_out.items():
        a, b = edges[i]
        if ka == 1 and port_offset(1, 1, sa) != 0.0:
            errs.append(f"{a}.{sa} 独占一侧却未居中")
        if i in straight:
            if ka != kb:
                errs.append(f"{a}→{b} 要直连但 k 不等（{ka} vs {kb}）")
            elif ja != jb:
                errs.append(f"{a}→{b} 要直连但序号不等（{ja} vs {jb}）")
            else:
                oa = port_offset(ka, ja, sa)
                ob = port_offset(kb, jb, sb)
                if abs(oa - ob) > .5:
                    errs.append(f"{a}→{b} k 与序号都相等，但偏移不同")
                ca = pos[a][0] if sa in "TB" else pos[a][1]
                cb = pos[b][0] if sb in "TB" else pos[b][1]
                if abs(ca - cb) > .5:
                    errs.append(f"{a}→{b} 两节点原点不同，k 与序号相等也不对齐")
    return errs
