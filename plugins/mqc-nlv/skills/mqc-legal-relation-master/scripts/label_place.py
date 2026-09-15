# -*- coding: utf-8 -*-
"""法律关系图 · 标签放置。

规则取自 v1 的冻结标准：

  标签完全落在线的一侧，绝不跨线
  横段的标签在上方，竖段的在远离主体那一侧
  只朝远离线的方向微调，且有界
  躲主体、躲其他标签、躲每一段连接线
  一个标签都不能丢——放不下是要报出来的，不是悄悄省掉

最后一条最要紧。丢标签在图上看不出来，但那条关系的法律性质就没了，
而法律关系图的价值恰恰在每条线标着什么。
"""
import math

FS = 9.5                      # 标签字号
PAD = 4.0                     # 标签盒的外扩
GAP = 7.0                     # 标签与线的最小间隙
STEP = 11.0                   # 微调步长
MAX_TRY = 18                  # 微调上限，超过就换锚段。
                              # 设 9 时有一条要靠兜底才放下，而兜底找到的位置
                              # 本来就没冲突，说明是范围给窄了，不是真放不下
CJK_PUNCT = set("　、。，；：（）《》「」【】·…—％%")


def _w(ch):
    return FS if (ord(ch) > 0x2E80 or ch in CJK_PUNCT) else FS * 0.52


def text_box(s, x, y, anchor="middle"):
    """文本的包围盒。y 是基线，盒子上下各按字号的七成算。"""
    w = sum(_w(c) for c in str(s))
    h = FS * 1.4
    if anchor == "middle":
        x0 = x - w / 2
    elif anchor == "end":
        x0 = x - w
    else:
        x0 = x
    return (x0 - PAD, y - FS * 0.85 - PAD, x0 + w + PAD, y + FS * 0.45 + PAD)


def overlap(a, b):
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def box_hits_seg(box, seg, gap=GAP):
    """标签盒是否压到某一段线（含间隙）。"""
    (x0, y0), (x1, y1) = seg
    bx0, by0, bx1, by1 = box[0] - gap, box[1] - gap, box[2] + gap, box[3] + gap
    if abs(x0 - x1) < .5:
        lo, hi = sorted((y0, y1))
        return bx0 < x0 < bx1 and lo < by1 and hi > by0
    lo, hi = sorted((x0, x1))
    return by0 < y0 < by1 and lo < bx1 and hi > bx0


def anchor_segments(path):
    """可作锚的段，按长度降序。短段放不下标签，长段优先。"""
    segs = list(zip(path, path[1:]))
    return sorted(segs, key=lambda s: -math.dist(*s))


LEADER_MIN = 34.0             # 标签离自己的线超过这么远就要拉引线
CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩"    # 平行关系组的序号


def max_line_width(gap, pad=4.0, clearance=4.0, stroke=1.30):
    """相邻线中心距为 gap 时，标签每行最多能有多宽。

    来自 Astra 第二轮 5.2：(w+2p)/2 + g + t/2 ≤ s，解出
        w ≤ 2(s − g − t/2) − 2p
    取 s=35、p=4、g=4 得 52.7。

    这条很要紧：三条竖线间距 35、标签单行宽 90 到 114 时，
    即使内边距为零，半宽也有 45 到 57，大于 35——
    只要标签还在三条线共存的高度段上，任何 y 都会横跨邻线。
    那不是放置器不够聪明，是可行域为空。换两行也未必够：
    实测「股权代持协议 2016.5.26」分成两行后最宽一行仍有 57.0，超限 4.3。
    """
    return 2 * (gap - clearance - stroke / 2) - 2 * pad


def check_label_fits(lines, gap, **kw):
    """返回 (是否放得下, 最宽一行, 上限)。放不下要报出来，不要闷头换行重试。"""
    limit = max_line_width(gap, **kw)
    w = max((sum(FS if (ord(c) > 0x2E80 or c in CJK_PUNCT) else FS * 0.52
                 for c in ln) for ln in lines), default=0.0)
    return w <= limit, round(w, 1), round(limit, 1)


def parallel_groups(edges):
    """找出同一对主体之间的多条关系。

    这类关系的线挤在一条边上，间距由端口等分位定死（节点宽 140、
    三个端口就是 35），而标签宽近百。标签放哪一侧、引线怎么拉，
    都必然跨过中间那条线，位置优化消除不了归属歧义。
    改用序号：线上只标一个字符，宽度绰绰有余，内容列在旁边的块里。"""
    seen = {}
    for i, (a, b) in enumerate(edges):
        seen.setdefault(frozenset((a, b)), []).append(i)
    return {k: v for k, v in seen.items() if len(v) > 1}


def leader(box, anchor_seg, anchor):
    """从标签盒拉一条引线到它标注的那条线。

    几条平行线挤在一起时，标签比线间距宽得多，放哪边都会横跨别的线，
    位置再怎么优化也消除不了归属的歧义。实务图的通行做法是加引线：
    标签照常放在放得下的地方，用一条细线指回自己那条关系。
    引线离得近就不画，免得平添线条。"""
    (x0, y0), (x1, y1) = anchor_seg
    bx0, by0, bx1, by1 = box
    cy = (by0 + by1) / 2
    if abs(x0 - x1) < .5:                       # 竖段：横着拉过去
        lo, hi = sorted((y0, y1))
        if not (lo <= cy <= hi):
            cy = min(max(cy, lo + 6), hi - 6)
        sx = bx1 if x0 > bx1 else bx0
        if abs(x0 - sx) < LEADER_MIN:
            return None
        return ((sx, cy), (x0, cy))
    cx = (bx0 + bx1) / 2                        # 横段：竖着拉过去
    lo, hi = sorted((x0, x1))
    if not (lo <= cx <= hi):
        cx = min(max(cx, lo + 6), hi - 6)
    sy = by1 if y0 > by1 else by0
    if abs(y0 - sy) < LEADER_MIN:
        return None
    return ((cx, sy), (cx, y0))


def place(paths, labels, rects, hull=None, priority=None):
    """返回每个标签的 (x, y, anchor)，以及放不下的清单。

    放置顺序先看重要性再看段长。按段长排是不够的：
    诉讼标的那条线的锚段不一定长，轮到它时两边已被占满，
    结果最该保住的标签反而是唯一放不下的那个。
    priority 里的先放，它们拿最好的位置。"""
    placed, boxes, failed = [None] * len(labels), [], []
    leaders = [None] * len(labels)
    anchors = [None] * len(labels)
    node_boxes = [(x, y, x + w, y + h) for x, y, w, h in rects]
    all_segs = [s for p in paths for s in zip(p, p[1:])]
    pr = set(priority or ())
    order = sorted(range(len(labels)),
                   key=lambda i: (0 if i in pr else 1,
                                  -max(math.dist(*s) for s in zip(paths[i],
                                                                  paths[i][1:]))))
    for i in order:
        text = labels[i]
        if not text:
            continue
        done = False
        for seg in anchor_segments(paths[i]):
            (x0, y0), (x1, y1) = seg
            vertical = abs(x0 - x1) < .5
            mx, my = (x0 + x1) / 2, (y0 + y1) / 2
            span = math.dist(*seg)
            if span < FS * 2:
                continue
            # 沿线滑动的候选：几条平行线挨得近时，标签光靠垂直方向躲不开——
            # 间距只有三十几，标签却宽得多，会被一路推到别人的线上去，
            # 跟自己那条对不上。让它沿着线错开高度，各自贴住自己的线。
            slides = [0.0]
            for t in (0.22, 0.36, 0.14, 0.44):
                slides += [span * t, -span * t]
            for k in range(MAX_TRY):
                d = GAP + k * STEP
                for sl in slides:
                    if vertical:
                        yy = my + sl
                        if abs(yy - my) > span / 2 - FS:
                            continue
                        side = 1 if (hull is None or mx >= (hull[0] + hull[2]) / 2) else -1
                        for sg_ in (side, -side):
                            x = mx + sg_ * d
                            anchor = "start" if sg_ > 0 else "end"
                            box = text_box(text, x, yy + FS * 0.35, anchor)
                            if (not any(overlap(box, b) for b in boxes + node_boxes)
                                    and not any(box_hits_seg(box, sq) for sq in all_segs)):
                                placed[i] = (x, yy + FS * 0.35, anchor)
                                boxes.append(box)
                                anchors[i] = (seg, box)
                                done = True
                                break
                    else:
                        xx = mx + sl
                        if abs(xx - mx) > span / 2 - FS:
                            continue
                        for sg_ in (-1, 1):
                            y = my + sg_ * d + (0 if sg_ < 0 else FS)
                            box = text_box(text, xx, y, "middle")
                            if (not any(overlap(box, b) for b in boxes + node_boxes)
                                    and not any(box_hits_seg(box, sq) for sq in all_segs)):
                                placed[i] = (xx, y, "middle")
                                boxes.append(box)
                                anchors[i] = (seg, box)
                                done = True
                                break
                    if done:
                        break
                if done:
                    break
            if done:
                break
        if not done:
            # 实在放不下也不能丢：挑一个冲突最少的位置强行放，并报出来。
            # 标签没了，那条关系的法律性质就没了，而这正是图的价值所在。
            best, bx = None, None
            for seg in anchor_segments(paths[i]):
                (x0, y0), (x1, y1) = seg
                vertical = abs(x0 - x1) < .5
                mx, my = (x0 + x1) / 2, (y0 + y1) / 2
                for k in range(MAX_TRY * 2):
                    d = GAP + k * STEP
                    cands = ([(mx + d, my + FS * .35, "start"),
                              (mx - d, my + FS * .35, "end")] if vertical
                             else [(mx, my - d, "middle"), (mx, my + d + FS, "middle")])
                    for x, y, anc in cands:
                        box = text_box(text, x, y, anc)
                        n = (sum(1 for b in boxes + node_boxes if overlap(box, b))
                             + sum(1 for sg in all_segs if box_hits_seg(box, sg)))
                        if best is None or n < best:
                            best, bx = n, (x, y, anc, box)
                if best == 0:
                    break
            placed[i] = bx[:3]
            boxes.append(bx[3])
            anchors[i] = (anchor_segments(paths[i])[0], bx[3])
            failed.append((i, text, f"冲突 {best} 处"))
    for i, a in enumerate(anchors):
        if a and placed[i]:
            leaders[i] = leader(a[1], a[0], placed[i][2])
    return placed, failed, leaders
