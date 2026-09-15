# -*- coding: utf-8 -*-
import os
"""离线基准：跑遍 5 到 16 个主体的各种排布，把结果固化成查表。

一个案子的关系结构不能代表一档规模，所以每档用四种结构各测一遍：
    星形　一个核连其余（集团案的典型：主债务人连所有人）
    双核　两个核互连且共享叶（原被告双方各领一批）
    链　　依次相连（转包链、债权转让链）
    混合　真实案件的样子：若干簇，簇内密、簇间疏
"""
import random


def make_graph(n, kind, seed=20260915):
    # 不能用 hash(kind)：Python 对字符串的 hash 每个进程都不一样，
    # 基准跑出来的图就不可复现——同一个网格两次跑出交叉 1 和交叉 6，
    # 不是算法变了，是图变了。改用字符和，保证任何时候都生成同一张图。
    rng = random.Random(seed + n * 7 + sum(ord(c) for c in kind) % 100)
    ids = [f"V{i}" for i in range(n)]
    ng = max(2, min(4, n // 3))
    nodes = [dict(id=x, name=x, group=f"G{i % ng}") for i, x in enumerate(ids)]
    if kind == "星形":
        E = [(ids[0], ids[i]) for i in range(1, n)]
    elif kind == "双核":
        E = [(ids[0], ids[1])]
        for i in range(2, n):
            E.append((ids[0], ids[i]))
            if i % 2 == 0:
                E.append((ids[1], ids[i]))
    elif kind == "链":
        E = [(ids[i], ids[i + 1]) for i in range(n - 1)]
        E += [(ids[i], ids[i + 2]) for i in range(0, n - 2, 3)]
    else:                       # 混合：簇内密、簇间疏，最接近真实案件
        E = []
        clusters = [ids[i::ng] for i in range(ng)]
        for cl in clusters:
            for i in range(len(cl) - 1):
                E.append((cl[i], cl[i + 1]))
        for i in range(ng):
            for j in range(i + 1, ng):
                if clusters[i] and clusters[j]:
                    E.append((clusters[i][0], clusters[j][0]))
        hub = ids[0]
        for x in ids[1:]:
            if rng.random() < 0.25 and (hub, x) not in E:
                E.append((hub, x))
    return nodes, E


def all_grids(n, max_ratio=4.0, max_empty=5):
    out = []
    for r in range(1, n + 1):
        for c in range(1, n + 1):
            if r * c < n or r * c - n > max_empty:
                continue
            if max(r, c) / min(r, c) > max_ratio:
                continue
            out.append((r, c))
    return out
