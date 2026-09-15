# -*- coding: utf-8 -*-
"""从最终 SVG 读出几何：主体块、走线、文字。

三种可编辑格式（pptx / vsdx / drawio）与导出物判据都从这里取几何，
保证交出去的每一种文件与 SVG 是同一张图，不存在第二套布局。

SVG 里的走线拐角是圆弧（A 命令），这是奇川风的圆角。
可编辑格式不画圆弧：拐角一律还原成真正的直角拐点。
V1 的解析器只认 M / L / Q，遇到 A 会把圆弧两端直接连起来，
一个拐角就歪成一条斜线，这里在交给 V1 之前先还原。
"""
import re
import html as _html

_NUM = r"-?\d+(?:\.\d+)?"


def attrs(tag):
    """同时认双引号与单引号属性。V1 只认双引号，
    单引号写的 stroke-dasharray 会被整个漏掉，虚线就成了实线。"""
    return {m.group(1): (m.group(3) if m.group(3) is not None else m.group(4))
            for m in re.finditer(r'([\w:-]+)\s*=\s*("([^"]*)"|\'([^\']*)\')', tag)}


def square_path(d):
    """带圆弧拐角的正交路径 → 直角拐点序列。"""
    toks = re.findall(r"[MLAmla]|" + _NUM, d)
    cmds, i = [], 0
    while i < len(toks):
        c = toks[i]
        if c in "ML":
            cmds.append((c, float(toks[i + 1]), float(toks[i + 2]))); i += 3
        elif c == "A":
            cmds.append(("A", float(toks[i + 6]), float(toks[i + 7]))); i += 8
        elif c in "mla":
            raise ValueError("相对坐标命令未支持：" + c)
        else:
            i += 1
    out = []
    for c, x, y in cmds:
        if c != "A":
            out.append((x, y))
            continue
        # 圆弧起点 a = out[-1]，终点 b = (x, y)。
        # 前一段水平，拐点就在 (b.x, a.y)；前一段竖直，拐点在 (a.x, b.y)。
        ax, ay = out[-1]
        prev = out[-2] if len(out) > 1 else None
        horiz = prev is not None and abs(prev[1] - ay) < 1e-6
        out[-1] = (x, ay) if horiz else (ax, y)
    # 去掉重合点与共线中间点
    clean = [out[0]]
    for p in out[1:]:
        if abs(p[0] - clean[-1][0]) > 1e-6 or abs(p[1] - clean[-1][1]) > 1e-6:
            clean.append(p)
    res = [clean[0]]
    for k in range(1, len(clean) - 1):
        a, b, c = res[-1], clean[k], clean[k + 1]
        if (abs(a[0] - b[0]) < 1e-6 and abs(b[0] - c[0]) < 1e-6) or \
           (abs(a[1] - b[1]) < 1e-6 and abs(b[1] - c[1]) < 1e-6):
            continue
        res.append(b)
    res.append(clean[-1])
    return res


def normalize(svg):
    """交给 V1 导出器之前的规整：圆弧拐角还原为直角，单引号属性改双引号。"""
    def fix_path(m):
        tag = m.group(0)
        a = attrs(tag)
        if a.get("data-kind") == "edge" and "A" in a.get("d", ""):
            pts = square_path(a["d"])
            nd = "M " + " L ".join(f"{x:.2f},{y:.2f}" for x, y in pts)
            tag = re.sub(r'\sd=("[^"]*"|\'[^\']*\')', f' d="{nd}"', tag, count=1)
        return tag
    svg = re.sub(r"<path\b[^>]*>", fix_path, svg)
    svg = re.sub(r"(\s[\w:-]+)='([^']*)'", r'\1="\2"', svg)
    return svg


def read(svg):
    """返回 dict(W, H, nodes, edges, texts)，坐标已计入各层 translate。

    nodes：[dict(x, y, w, h, rx, fill, stroke, emph, lines=[文字…])]
    edges：[dict(pts, dash, arrow, stroke, sw)]，pts 为直角拐点序列
    texts：主体块之外的文字（标题、副标题、关系标签）
    歸藏风会把整张图包进 translate(0,60)，不计入偏移就全部对不上。
    """
    m = re.search(r"<svg\b[^>]*>", svg)
    sa = attrs(m.group(0))
    vb = [float(v) for v in re.findall(_NUM, sa.get("viewBox", ""))]
    W = vb[2] if len(vb) == 4 else float(sa.get("width", 0))
    H = vb[3] if len(vb) == 4 else float(sa.get("height", 0))
    body = re.sub(r"<defs>.*?</defs>", "", svg[m.end():], flags=re.S)
    nodes, edges, texts = [], [], []
    stack = []            # 每层 g：(dx, dy, 是否主体组)
    cur = None            # 正在收集的主体
    tok = re.compile(r"<(/?)(g|rect|path|text)\b([^>]*?)(/?)>(?:([^<]*)</text>)?", re.S)

    def off():
        return (sum(a for a, _, _ in stack), sum(b for _, b, _ in stack))
    for t in tok.finditer(body):
        close, tag, raw, selfclose, inner = t.groups()
        if tag == "g":
            if close:
                if stack:
                    _, _, isnode = stack.pop()
                    if isnode and cur is not None:
                        nodes.append(cur)
                        cur = None
                continue
            a = attrs(raw)
            tr = re.search(r"translate\(\s*(" + _NUM + r")[\s,]*(" + _NUM + r")?", a.get("transform", ""))
            dx, dy = (float(tr.group(1)), float(tr.group(2) or 0)) if tr else (0.0, 0.0)
            isnode = a.get("data-role") == "node"
            stack.append((dx, dy, isnode))
            if isnode:
                cur = dict(emph=a.get("data-emph") == "1", lines=[])
            if selfclose:
                stack.pop()
            continue
        if close:
            continue
        a = attrs(raw)
        ox, oy = off()
        if tag == "rect" and cur is not None and "x" not in cur:
            cur.update(x=float(a.get("x", 0)) + ox, y=float(a.get("y", 0)) + oy,
                       w=float(a["width"]), h=float(a["height"]), rx=float(a.get("rx", 0)),
                       fill=a.get("fill"), stroke=a.get("stroke"))
        elif tag == "path" and a.get("data-kind") == "edge":
            pts = [(x + ox, y + oy) for x, y in square_path(a["d"])]
            edges.append(dict(pts=pts, dash=bool(a.get("stroke-dasharray")),
                              arrow="marker-end" in a, stroke=a.get("stroke", "#4B5563"),
                              sw=float(a.get("stroke-width", 1.3))))
        elif tag == "text":
            item = dict(t=_html.unescape(re.sub(r"<[^>]+>", "", inner or "")), fs=float(a.get("font-size", 12)),
                        fill=a.get("fill", "#1F2933"),
                        bold=a.get("font-weight") in ("700", "bold"))
            if cur is not None:
                cur["lines"].append(item)
            else:
                item.update(x=float(a.get("x", 0)) + ox, y=float(a.get("y", 0)) + oy,
                            anchor=a.get("text-anchor", "start"))
                texts.append(item)
    return dict(W=W, H=H, nodes=nodes, edges=edges, texts=texts)
