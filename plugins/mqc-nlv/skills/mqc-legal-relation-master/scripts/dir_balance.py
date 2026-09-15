# -*- coding: utf-8 -*-
"""方向均衡：高度数主体的邻居应当分散在四个方向。

13 主体以上的瓶颈是高度数主体的端口被挤爆：某个主体度数 6，
邻居都堆在左右两侧，而左右各只能挂一个端口，于是好的边被先来的占满，
后到的关系只能用最差的组合（实测出现 T→T，两端都朝上，
必须绕到画布外兜一圈，拐四次，还与别的线交叉）。

布局阶段就该避免这种堆积：同样是把六个邻居放在周围，
让它们分散在上下左右，四条边的需求就均衡了。

计法：对每个主体，按邻居的相对方位统计四个方向的需求数，
再按各方向的容量（上下 4、左右 1）折算成压力，取超出部分求和。
度数低的主体天然不会超，所以这一项只在高度数主体上起作用。
"""
CAP = {"T": 4, "B": 4, "L": 1, "R": 1}


def direction_pressure(assign, edges, cap=None):
    cap = cap or CAP
    need = {k: {"L": 0, "R": 0, "T": 0, "B": 0} for k in assign}
    for a, b, *_ in edges:
        (r1, c1), (r2, c2) = assign[a], assign[b]
        dr, dc = r2 - r1, c2 - c1
        # 按主方向记一次需求。斜对角按位移大的那一维算，
        # 与走线阶段的判方向口径一致。
        if abs(dc) > abs(dr):
            sa, sb = ("R", "L") if dc > 0 else ("L", "R")
        elif abs(dr) > abs(dc):
            sa, sb = ("B", "T") if dr > 0 else ("T", "B")
        else:                       # 正斜角，两个方向都可能，各记半次
            sa = "R" if dc > 0 else "L"
            sb = "T" if dr > 0 else "B"
        need[a][sa] += 1
        need[b][sb] += 1
    return sum(max(0, v - cap[s]) for d in need.values() for s, v in d.items())
