# -*- coding: utf-8 -*-
"""按指定的环绕顺序分配端口。

Astra 第四轮给出一个实算结果：K₂,m 的两核，叶的环绕顺序必须互为反向，
否则 rotation 本身就不可平面——枚举 K₂,₇ 的全部 720 种循环顺序，
只有反向那一种 g=0。而且它指出，给定一个错误的 rotation，
再多空间与路径搜索也消不掉交叉，必须回到端口顺序层。

先前想验证这一条却做错了：只改了边在列表里的次序，
而端口分配器按主体的相对位置算，根本不看边序，两种跑出来完全一样。
真正的环绕顺序指的是**端口绕主体一圈的排列次序**，要能指定它才验得了。

约定：顺时针从左上角起，T 从左到右、R 从上到下、B 从右到左、L 从下到上。
"""
NW, NH = 140, 48
CLOCKWISE = ("T", "R", "B", "L")


def ring_slots(cap):
    """按顺时针列出所有端口位（侧, 该侧第几个）。"""
    out = []
    for s in CLOCKWISE:
        for i in range(1, cap[s] + 1):
            out.append((s, i))
    return out


def offset(side, i, k):
    """该侧第 i 个端口（共 k 个）相对边中点的偏移。
    T/B 从左到右、L/R 从上到下计数；顺时针要求 B 与 L 反着来。"""
    L = NW if side in "TB" else NH
    if k <= 1:
        return 0.0
    base = L * i / (k + 1) - L / 2
    return -base if side in ("B", "L") else base


def assign_ring(order, cap, start=0):
    """把一圈邻居按给定顺序摊到端口位上。

    order 是邻居的环绕次序，start 决定从哪个端口位起步（循环移位）。
    返回 {邻居: (侧, 第几个, 该侧共几个)}。
    """
    slots = ring_slots(cap)
    if len(order) > len(slots):
        raise ValueError(f"要放 {len(order)} 个端点，端口位只有 {len(slots)} 个")
    chosen = [slots[(start + i) % len(slots)] for i in range(len(order))]
    per = {}
    for s, _ in chosen:
        per[s] = per.get(s, 0) + 1
    seq = {}
    out = {}
    for nb, (s, _) in zip(order, chosen):
        seq[s] = seq.get(s, 0) + 1
        out[nb] = (s, seq[s], per[s])
    return out


def port_xy(center, side, i, k):
    cx, cy = center
    o = offset(side, i, k)
    return {"L": (cx - NW / 2, cy + o), "R": (cx + NW / 2, cy + o),
            "T": (cx + o, cy - NH / 2), "B": (cx + o, cy + NH / 2)}[side]
