# -*- coding: utf-8 -*-
"""走线判据：读产物 SVG 的坐标，不看源码写了什么。"""
import re, sys, math
STUB = 22
import os as _os, tempfile as _tf
s = open(sys.argv[1] if len(sys.argv) > 1 else _os.path.join(_tf.gettempdir(), "skel.svg"), encoding="utf-8").read()
# 只把主体的矩形当障碍。标签的白底衬也是 rect，但它是用来遮断线的，
# 不该被判成节点——否则每一处底衬都会报成一次穿越。
# 只有主体的矩形算障碍。标签白底也是 rect，把它当主体会凭空报出一堆穿越，
# 这个坑踩过两次：第一次靠宽度过滤绕过去，改正则时又丢了。
# 现在按类型标记排除，标了 label-bg / label-mask 的一律不算。
_rect_tags = re.findall(r'<rect([^>]*)>', s)
rects = []
for _a in _rect_tags:
    if 'label-bg' in _a or 'label-mask' in _a:
        continue
    _m = re.search(r'\sx="([\d.-]+)"[^>]*\sy="([\d.-]+)"[^>]*\swidth="([\d.]+)"'
                   r'[^>]*\sheight="([\d.]+)"', _a)
    if _m and float(_m.group(3)) > 100:
        rects.append(tuple(float(v) for v in _m.groups()))
paths = re.findall(r'<path[^>]*\sd="(M [^"]+)"([^>]*)>', s)

def parse(d):
    pts, segs = [], []
    cur = None
    for m in re.finditer(r'([ML]) ([\d.-]+),([\d.-]+)|A [\d.]+ [\d.]+ 0 0 [01] ([\d.-]+),([\d.-]+)', d):
        if m.group(1):
            p = (float(m.group(2)), float(m.group(3)))
            if cur and m.group(1) == "L": segs.append((cur, p))
            cur = p
        else:
            cur = (float(m.group(4)), float(m.group(5)))
    return segs

errs = []
def ck(no, cond, msg):
    print(("  OK  " if cond else "  FAIL") + f" {no}  {msg}")
    if not cond: errs.append(no)

allsegs = [sg for d, _ in paths for sg in parse(d)]

def hits(seg, r, pad=3):
    (x0, y0), (x1, y1) = seg; rx, ry, rw, rh = r
    if abs(x0 - x1) < .5:
        if not (rx + pad < x0 < rx + rw - pad): return False
        lo, hi = sorted((y0, y1)); return lo < ry + rh - pad and hi > ry + pad
    if abs(y0 - y1) < .5:
        if not (ry + pad < y0 < ry + rh - pad): return False
        lo, hi = sorted((x0, x1)); return lo < rx + rw - pad and hi > rx + pad
    return False

bad = [(sg, r) for sg in allsegs for r in rects if hits(sg, r)]
ck("G1", not bad, f"没有线段穿过节点（{len(bad)} 处）")

ov = []
for i, a in enumerate(allsegs):
    for b in allsegs[i+1:]:
        (ax0, ay0), (ax1, ay1) = a; (bx0, by0), (bx1, by1) = b
        if abs(ax0-ax1) < .5 and abs(bx0-bx1) < .5 and abs(ax0-bx0) < .5:
            l1, h1 = sorted((ay0, ay1)); l2, h2 = sorted((by0, by1))
            if min(h1, h2) - max(l1, l2) > 2: ov.append((a, b))
        if abs(ay0-ay1) < .5 and abs(by0-by1) < .5 and abs(ay0-by0) < .5:
            l1, h1 = sorted((ax0, ax1)); l2, h2 = sorted((bx0, bx1))
            if min(h1, h2) - max(l1, l2) > 2: ov.append((a, b))
ck("G2", not ov, f"没有两条线共线重叠（{len(ov)} 处）")

short = []
for d, attr in paths:
    if "marker-end" not in attr: continue
    sg = parse(d)
    if not sg: continue
    (x0, y0), (x1, y1) = sg[-1]
    if math.hypot(x1-x0, y1-y0) < STUB: short.append((round(math.hypot(x1-x0, y1-y0), 1), d[:44]))
ck("G3", not short, f"箭头之前都留了 {STUB} 的直段（不足 {len(short)} 处）")
for v, d in short[:4]: print(f"       仅 {v}：{d}")

skew = []
for sg in allsegs:
    (x0, y0), (x1, y1) = sg
    if abs(x0 - x1) > .5 and abs(y0 - y1) > .5:
        skew.append(((round(x0), round(y0)), (round(x1), round(y1))))
ck("G7", not skew, f"所有线段都是正交的（斜线 {len(skew)} 段）")
for s_ in skew[:3]: print("       ", s_)

bad5, tot5 = [], 0
for d, _ in paths:
    toks = re.findall(r'([ML]) ([\d.-]+),([\d.-]+)|A ([\d.]+) [\d.]+ 0 0 ([01]) ([\d.-]+),([\d.-]+)', d)
    cur = prev = None
    for t in toks:
        if t[0]:
            p = (float(t[1]), float(t[2]))
            if cur: prev = (cur, p)
            cur = p
        else:
            tot5 += 1
            end = (float(t[5]), float(t[6])); sweep = int(t[4])
            if prev:
                v1 = (prev[1][0]-prev[0][0], prev[1][1]-prev[0][1])
                v2 = (end[0]-cur[0], end[1]-cur[1])
                n1 = math.hypot(*v1) or 1; n2 = math.hypot(*v2) or 1
                v1 = (v1[0]/n1, v1[1]/n1); v2 = (v2[0]/n2, v2[1]/n2)
                cross = v1[0]*v2[1] - v1[1]*v2[0]
                if abs(cross) > 1e-6 and (1 if cross > 0 else 0) != sweep:
                    bad5.append(d[:50])
            cur = end
ck("G5", not bad5, f"圆角的扫掠方向与前后两段一致（{len(bad5)}/{tot5} 处反向）")

# G8　双箭头的距离预算（Astra 第二轮 7.3）
# 有箭头那端要 22+3.12+12=37.12；双箭头零拐弯直连要 d≥46。
# 单箭头的 34 不能原样套用到双箭头上。
D_BOTH_STRAIGHT, D_ARROW_END = 46.0, 37.12
bad8 = []
for d, attr in paths:
    if "marker-start" not in attr:
        continue
    sg = parse(d)
    if not sg:
        continue
    arcs = len(re.findall(r'A [\d.]+ [\d.]+ 0 0 [01]', d))
    L = sum(math.dist(u, v) for u, v in sg)
    if arcs == 0:
        if L + 24 < D_BOTH_STRAIGHT:
            bad8.append(f"双箭头直连 d={L+24:.1f} < {D_BOTH_STRAIGHT}")
    else:
        for seg in (sg[0], sg[-1]):
            if math.dist(*seg) + 12 < D_ARROW_END:
                bad8.append(f"双箭头有拐弯，端段 {math.dist(*seg)+12:.1f} < {D_ARROW_END}")
ck("G8", not bad8, f"双箭头的距离预算（不足 {len(bad8)} 处）")
for b in bad8[:3]: print("       ", b)

# G9　走线不得贴着主体的边走
# 你能一口气指出五处贴边，说明这件事必须自动检测，不能靠人看图。
HUG_NEAR = 34.0   # 略小于通道距离 40：走在通道上的不报，真贴上去的才报
hug = []
for d_, attr_ in paths:
    sg_ = parse(d_)
    if not sg_:
        continue
    # 先认出这条线自己的两个端点主体：线从自己家门口出来，
    # 当然离自己近，那不叫贴边。出端直段 25.12 就是这么被误报的。
    ends = [sg_[0][0], sg_[-1][1]]
    own = []
    for rx, ry, rw, rh in rects:
        for ex, ey in ends:
            if (rx - 14 <= ex <= rx + rw + 14) and (ry - 14 <= ey <= ry + rh + 14):
                own.append((rx, ry, rw, rh))
                break
    for (x0, y0), (x1, y1) in sg_:
        for rr_ in rects:
            if rr_ in own:
                continue
            rx, ry, rw, rh = rr_
            if abs(x0 - x1) < .5:
                lo, hi = sorted((y0, y1))
                if hi < ry + 4 or lo > ry + rh - 4:
                    continue
                dist = min(abs(x0 - rx), abs(x0 - (rx + rw)))
                if dist < 1.0:
                    hug.append(("重合", round(x0), round(lo), round(hi)))
                elif dist < HUG_NEAR:
                    hug.append((round(x0), round(lo), round(hi), round(dist, 1)))
            elif abs(y0 - y1) < .5:
                lo, hi = sorted((x0, x1))
                if hi < rx + 4 or lo > rx + rw - 4:
                    continue
                dist = min(abs(y0 - ry), abs(y0 - (ry + rh)))
                if dist < 1.0:
                    hug.append(("重合", round(lo), round(hi), round(y0)))
                elif dist < HUG_NEAR:
                    hug.append((round(lo), round(hi), round(y0), round(dist, 1)))
_ov = sum(1 for h in hug if h and h[0] == "重合")
ck("G9", not hug, f"走线不贴主体的边（其中与边线重合 {_ov} 段，"
   f"过近 {len(hug)-_ov} 段，净距下限 {HUG_NEAR}）")
for h in hug[:5]: print("       ", h)

# G10　两端对齐却仍然拐弯
# 端口坐标同 x 或同 y、方向相对，中间又没有障碍，就该直连。
# 这种线拐一下特别扎眼，且多半是端口序号没对齐造成的。
bad10 = []
for d, attr in paths:
    if "marker-end" not in attr:
        continue
    sg = parse(d)
    if len(sg) < 2:
        continue
    arcs = len(re.findall(r'A [\d.]+ [\d.]+ 0 0 [01]', d))
    if arcs == 0:
        continue
    p0, pn = sg[0][0], sg[-1][1]
    if abs(p0[0] - pn[0]) < .5 or abs(p0[1] - pn[1]) < .5:
        bad10.append((tuple(round(v) for v in p0), tuple(round(v) for v in pn), arcs))
ck("G10", not bad10, f"两端对齐的线应当直连（拐了弯的 {len(bad10)} 条）")
for b in bad10[:4]: print("       ", b)

# G11　奇川风：色块一律圆角，不许直角边；深红实底块至多两个且不加边线
sharp, hot_blocks, hot_stroked = [], 0, 0
for _a in re.findall(r'<rect([^>]*)>', s):
    # 只查主体的色块。画布背景也是 rect，按宽度筛会把它算成直角色块；
    # 类型标记才是可靠的依据。
    if 'data-kind="node"' not in _a:
        continue
    _rx = re.search(r'\srx="([\d.]+)"', _a)
    if not _rx or float(_rx.group(1)) < 1:
        sharp.append(_a.strip()[:40])
    if '#991B1B' in _a:
        hot_blocks += 1
        if 'stroke="#' in _a:
            hot_stroked += 1
# G11 只管奇川风与白描。歸藏风是 Swiss 路子，方角是它的语言，
# 拿奇川风「不许直角边」的规矩去套它，报出来的不是问题。
# 靠底色认风格：歸藏风用暖白纸底 #FAFAF8。
_guizang = "#FAFAF8" in s
if _guizang:
    ck("G11", True, "歸藏风：方角为该风格所用，不适用奇川风的圆角规矩")
else:
    # 强调的**元素**至多两个，节点与关系都算——
    # 规范说 deep red marks the pivotal element(s), 1–2 per diagram，
    # 而 emphasized node 与 emphasized edge 都是 element。
    # 先前只数实底块，漏了深红的线，示例里 2 节点 + 2 边其实已经超标。
    hot_edges = len(re.findall(r'<path[^>]*stroke="#991B1B"', s))
    hot_total = hot_blocks + hot_edges
    ck("G11", not sharp and hot_total <= 2 and hot_stroked == 0,
       f"色块圆角（直角 {len(sharp)} 个）、强调元素 {hot_total} 个"
       f"（实底块 {hot_blocks} + 深红线 {hot_edges}，上限 2）、"
       f"深红带边线 {hot_stroked} 个（须为 0）")

# G12　文字不得越出画布，也不得越出自己所属的模块
#
# 这一条照搬 V1 的 lint：**量的是文字的实际宽度，不是锚点位置**。
# 居中的标题锚点可以稳稳落在画布内，而它的字形却从两边溢出去。
# 宽度按中文约一个字宽、拉丁约 0.55 个字宽估算，与 V1 同口径。
_W = re.search(r'<svg[^>]*width="([\d.]+)"', s)
_H = re.search(r'<svg[^>]*height="([\d.]+)"', s)
CW = float(_W.group(1)) if _W else 0
CH = float(_H.group(1)) if _H else 0


def _textw(txt, fs):
    # SVG 源码里的 &amp; &lt; 这类转义是一个字符，按源码长度量会把
    # 「A&B 公司」多算四个字宽，名称里带 & < > 的主体被误判撑破模块
    import html as _html
    txt = _html.unescape(txt)
    return sum(fs if ord(c) > 0x2E80 else fs * 0.55 for c in txt)


over = []
for _m in re.finditer(r'<text([^>]*)>([^<]*)</text>', s):
    at, txt = _m.group(1), _m.group(2)
    if not txt.strip():
        continue
    _x = re.search(r'\sx="([\d.-]+)"', at)
    _fs = re.search(r'font-size="([\d.]+)"', at)
    if not (_x and _fs):
        continue
    x, fs = float(_x.group(1)), float(_fs.group(1))
    anc = (re.search(r'text-anchor="(\w+)"', at) or [None, "start"])[1] \
        if re.search(r'text-anchor="(\w+)"', at) else "start"
    tw = _textw(txt, fs)
    left = x - tw / 2 if anc == "middle" else (x - tw if anc == "end" else x)
    if left < -2 or left + tw > CW + 2:
        over.append((txt[:14], round(tw), round(x)))
ck("G12", not over,
   f"文字不越出画布（越出 {len(over)} 处，按中文一个字宽估算）")
for o in over[:3]:
    print(f"        「{o[0]}」宽 {o[1]} 位于 x={o[2]}，画布宽 {CW:.0f}")

# G13　模块内的文字不得超出模块本身
spill = []
for _m in re.finditer(r'<text([^>]*)>([^<]*)</text>', s):
    at, txt = _m.group(1), _m.group(2)
    if not txt.strip() or 'text-anchor="middle"' not in at:
        continue
    _x = re.search(r'\sx="([\d.-]+)"', at)
    _y = re.search(r'\sy="([\d.-]+)"', at)
    _fs = re.search(r'font-size="([\d.]+)"', at)
    if not (_x and _y and _fs):
        continue
    x, y, fs = float(_x.group(1)), float(_y.group(1)), float(_fs.group(1))
    for rx, ry, rw, rh in rects:
        if rx <= x <= rx + rw and ry <= y <= ry + rh + 4:
            tw = _textw(txt, fs)
            if tw > rw - 8:
                spill.append((txt[:12], round(tw), round(rw)))
            break
ck("G13", not spill,
   f"模块内文字不撑破模块（撑破 {len(spill)} 处）")
for sp in spill[:3]:
    print(f"        「{sp[0]}」宽 {sp[1]}，模块宽 {sp[2]}")

red_strokes = len(re.findall(r'stroke="#991B1B"', s))
red_rect = len(re.findall(r'<rect[^>]*stroke="#991B1B"', s))
ck("G4", red_rect == 0, f"节点不用红色描边框（实有 {red_rect} 处）")

# G6 横断交叉：一条竖直段与一条水平段在内部相交。同向段不算。
def _cross(a, b):
    (ax0, ay0), (ax1, ay1) = a; (bx0, by0), (bx1, by1) = b
    av, bv = abs(ax0 - ax1) < .5, abs(bx0 - bx1) < .5
    if av == bv: return False
    if av: vx, vy0, vy1 = ax0, *sorted((ay0, ay1)); hy, hx0, hx1 = by0, *sorted((bx0, bx1))
    else:  vx, vy0, vy1 = bx0, *sorted((by0, by1)); hy, hx0, hx1 = ay0, *sorted((ax0, ax1))
    return hx0 < vx < hx1 and vy0 < hy < vy1

per = [parse(d) for d, _ in paths]
cn = 0
for i, p in enumerate(per):
    for q in per[i+1:]:
        for sa in p:
            for sb in q:
                if _cross(sa, sb): cn += 1
print(f"  {'OK  ' if cn == 0 else 'WARN'} G6  横断交叉 {cn} 处"
      + ("（零交叉）" if cn == 0 else "（可接受，但越少越好）"))

if not allsegs or not rects:
    print("  FAIL 解析　一条线或一个主体都没读到，多半是属性顺序变了、"
          "正则没跟上。这种情况下的「全过」是假的。")
    errs.append("parse")
print(f"\n  共 {len(allsegs)} 段走线、{len(rects)} 个节点")
print("  全部通过" if not errs else f"  未通过：{sorted(set(errs))}")
sys.exit(1 if errs else 0)
