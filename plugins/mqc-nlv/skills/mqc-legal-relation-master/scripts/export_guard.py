# -*- coding: utf-8 -*-
"""导出物判据：把 pptx / vsdx / drawio 拆开读回，与 SVG 逐条对照。

路线判据（route_guard）只读 SVG。可编辑格式是另一次转换，
转换本身会出错：圆角被当成斜线、单引号虚线被读成实线、
drawio 把算好的走线扔掉自己重排。这些 SVG 上一处都看不出来，
所以每种导出物都要单独回读。

E1　条数一致：导出物里的走线条数 = SVG 的关系条数
E2　横平竖直：每一段只能水平或竖直（容差 0.5 px）
E3　位置一致：每条线的拐点序列与 SVG 逐点对上（容差 1.5 px）
E4　线型一致：虚线仍是虚线、有箭头的仍有箭头
E5　主体一致：主体块的位置与尺寸对上（容差 1.5 px）
E6　文字齐全：SVG 里的每段文字在导出物里都找得到
"""
import re, sys, os, zipfile, html
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import svg_geom

EMU = 9525.0
TOL_ORTH, TOL_POS = 0.5, 1.5


def _ortho(pts):
    return all(abs(a[0] - b[0]) < TOL_ORTH or abs(a[1] - b[1]) < TOL_ORTH
               for a, b in zip(pts, pts[1:]))


def _match(p, q):
    return len(p) == len(q) and all(abs(a[0] - b[0]) < TOL_POS and abs(a[1] - b[1]) < TOL_POS
                                    for a, b in zip(p, q))


def _compare(ref, got, fmt):
    res = []
    E = ref["edges"]
    res.append(("E1", len(got["edges"]) == len(E),
                f"走线 {len(got['edges'])} 条，SVG {len(E)} 条"))
    bad = [i for i, e in enumerate(got["edges"]) if not _ortho(e["pts"])]
    res.append(("E2", not bad, "全部横平竖直" if not bad else f"{len(bad)} 条有斜段"))
    unmatched = []
    pool = list(got["edges"])
    for i, e in enumerate(E):
        hit = next((g for g in pool if _match(g["pts"], e["pts"]) or
                    _match(list(reversed(g["pts"])), e["pts"])), None)
        if hit is None:
            unmatched.append(i)
        else:
            pool.remove(hit)
            if hit["dash"] != e["dash"] or hit["arrow"] != e["arrow"]:
                unmatched.append(("线型", i))
    pos_bad = [u for u in unmatched if not isinstance(u, tuple)]
    sty_bad = [u for u in unmatched if isinstance(u, tuple)]
    res.append(("E3", not pos_bad, "拐点逐点对上" if not pos_bad else f"{len(pos_bad)} 条对不上"))
    res.append(("E4", not sty_bad, "虚实与箭头一致" if not sty_bad else f"{len(sty_bad)} 条线型不符"))
    nb = 0
    for n in ref["nodes"]:
        if not any(abs(n["x"] - g["x"]) < TOL_POS and abs(n["y"] - g["y"]) < TOL_POS and
                   abs(n["w"] - g["w"]) < TOL_POS and abs(n["h"] - g["h"]) < TOL_POS
                   for g in got["nodes"]):
            nb += 1
    res.append(("E5", nb == 0, "主体块位置尺寸一致" if nb == 0 else f"{nb} 个主体块对不上"))
    want = [t["t"] for n in ref["nodes"] for t in n["lines"]] + [t["t"] for t in ref["texts"]]
    blob = got["text"]
    miss = [w for w in want if w.strip() and w.replace(" ", "") not in blob]
    res.append(("E6", not miss, "文字齐全" if not miss else "缺：" + "、".join(miss[:3])))
    return res


# ---------------------------------------------------------------- pptx
def read_pptx(path):
    z = zipfile.ZipFile(path)
    s = z.read("ppt/slides/slide1.xml").decode("utf-8")
    edges, nodes = [], []
    for m in re.finditer(r"<p:cxnSp>.*?</p:cxnSp>|<p:sp>.*?</p:sp>", s, re.S):
        x = m.group(0)
        off = re.search(r'<a:off x="(-?\d+)" y="(-?\d+)"/><a:ext cx="(\d+)" cy="(\d+)"', x)
        if not off:
            continue
        ox, oy, cx, cy = (int(v) / EMU for v in off.groups())
        dash = "prstDash" in x
        arrow = "tailEnd" in x or "headEnd" in x
        if x.startswith("<p:cxnSp>"):
            fh, fv = 'flipH="1"' in x, 'flipV="1"' in x
            x0, x1 = (ox + cx, ox) if fh else (ox, ox + cx)
            y0, y1 = (oy + cy, oy) if fv else (oy, oy + cy)
            edges.append(dict(pts=[(x0, y0), (x1, y1)], dash=dash, arrow=arrow))
        elif 'fill="none"' in x and "<a:custGeom>" in x:
            pts = [(ox + int(a) / 100000 * cx, oy + int(b) / 100000 * cy)
                   for a, b in re.findall(r'<a:pt x="(-?\d+)" y="(-?\d+)"/>', x)]
            edges.append(dict(pts=pts, dash=dash, arrow=arrow))
        elif "roundRect" in x or "prstGeom prst=\"rect\"" in x:
            nodes.append(dict(x=ox, y=oy, w=cx, h=cy))
    text = html.unescape("".join(re.findall(r"<a:t>([^<]*)</a:t>", s))).replace(" ", "")
    return dict(edges=edges, nodes=nodes, text=text)


# ---------------------------------------------------------------- vsdx
def read_vsdx(path):
    z = zipfile.ZipFile(path)
    name = next(n for n in z.namelist() if re.match(r"visio/pages/page\d+\.xml$", n))
    s = z.read(name).decode("utf-8")
    ph = re.search(r'<Cell N="PageHeight" V="([\d.]+)"', z.read("visio/pages/pages.xml").decode("utf-8"))
    PH = float(ph.group(1)) if ph else None
    edges, nodes = [], []

    def cell(x, n):
        m = re.search(r'<Cell N="%s" V="(-?[\d.e-]+)"' % n, x)
        return float(m.group(1)) if m else None
    for m in re.finditer(r"<Shape\b.*?</Shape>", s, re.S):
        x = m.group(0)
        pinx, piny, w, h = cell(x, "PinX"), cell(x, "PinY"), cell(x, "Width"), cell(x, "Height")
        if None in (pinx, piny, w, h):
            continue
        left, bottom = pinx - w / 2, piny - h / 2
        if 'NameU="Route' in x:
            pts = []
            for r in re.finditer(r'<Row T="(MoveTo|LineTo)"[^>]*><Cell N="X" V="(-?[\d.e-]+)"/><Cell N="Y" V="(-?[\d.e-]+)"/>', x):
                X = (left + float(r.group(2))) * 96
                Y = (PH - (bottom + float(r.group(3)))) * 96
                pts.append((X, Y))
            lp = cell(x, "LinePattern")
            edges.append(dict(pts=pts, dash=lp is not None and lp != 1,
                              arrow=(cell(x, "EndArrow") or 0) > 0))
        elif 'NameU="Module' in x:
            nodes.append(dict(x=left * 96, y=(PH - bottom - h) * 96, w=w * 96, h=h * 96))
    text = html.unescape(re.sub(r"<[^>]+>", "", "".join(re.findall(r"<Text>(.*?)</Text>", s, re.S))))
    return dict(edges=edges, nodes=nodes, text=text.replace(" ", "").replace("\n", ""))


# ---------------------------------------------------------------- drawio
def read_drawio(path):
    s = open(path, encoding="utf-8").read()
    cells = {}
    for m in re.finditer(r'<mxCell\b((?:[^>/]|/(?!>))*)>(.*?)</mxCell>', s, re.S):
        a = svg_geom.attrs(m.group(1))
        g = re.search(r'<mxGeometry\b([^>]*)', m.group(2))
        ga = svg_geom.attrs(g.group(1)) if g else {}
        pts = [(float(p.group(1)), float(p.group(2)))
               for p in re.finditer(r'<mxPoint x="(-?[\d.]+)" y="(-?[\d.]+)"', m.group(2))]
        src = re.search(r'<mxPoint x="(-?[\d.]+)" y="(-?[\d.]+)" as="sourcePoint"', m.group(2))
        tgt = re.search(r'<mxPoint x="(-?[\d.]+)" y="(-?[\d.]+)" as="targetPoint"', m.group(2))
        way = [(float(p.group(1)), float(p.group(2))) for p in
               re.finditer(r'<mxPoint x="(-?[\d.]+)" y="(-?[\d.]+)"\s*/>', m.group(2))]
        cells[a.get("id")] = dict(a=a, g=ga, src=src, tgt=tgt, way=way)
    edges, nodes, text = [], [], []
    for c in cells.values():
        a = c["a"]
        # attrs() 拿到的是属性原文，XML 层的转义还在：先解 XML 一层得到 html，
        # 去标签后再解 html 一层，才是 draw.io 实际显示的文字。多解一层会把
        # 双重转义的错文件也判成对的。
        raw_html = a.get("value", "").replace("&lt;", "<").replace("&gt;", ">") \
            .replace("&quot;", '"').replace("&#39;", "'").replace("&amp;", "&")
        text.append(re.sub(r"<[^>]+>", "", raw_html).replace("&lt;", "<").replace("&gt;", ">")
                    .replace("&quot;", '"').replace("&nbsp;", " ").replace("&amp;", "&"))
        if a.get("edge") == "1":
            st = a.get("style", "")
            if "edgeStyle=orthogonalEdgeStyle" in st or "edgeStyle=elbowEdgeStyle" in st:
                edges.append(dict(pts=[(0, 0), (1, 1)], dash=False, arrow=False))  # 自动布线，判为不一致
                continue
            p0 = (float(c["src"].group(1)), float(c["src"].group(2)))
            p1 = (float(c["tgt"].group(1)), float(c["tgt"].group(2)))
            edges.append(dict(pts=[p0] + c["way"] + [p1], dash="dashed=1" in st,
                              arrow="endArrow=none" not in st))
        elif a.get("vertex") == "1" and "rounded=1" in a.get("style", "") or \
                (a.get("vertex") == "1" and "rounded=0" in a.get("style", "")):
            g = c["g"]
            nodes.append(dict(x=float(g.get("x", 0)), y=float(g.get("y", 0)),
                              w=float(g.get("width", 0)), h=float(g.get("height", 0))))
    return dict(edges=edges, nodes=nodes, text="".join(text).replace(" ", ""))


def check(svg_path, files):
    """files：{'pptx': 路径, 'vsdx': 路径, 'drawio': 路径}。返回 {格式: (全过, 明细)}。"""
    ref = svg_geom.read(open(svg_path, encoding="utf-8").read())
    # 参照 SVG 的走线要补回箭头长度吗？不补：三种导出物都从同一份 SVG 转，
    # 端点应当与 SVG 的 path 端点一致，箭头由格式自身的线端画出。
    out = {}
    for fmt, reader in (("pptx", read_pptx), ("vsdx", read_vsdx), ("drawio", read_drawio)):
        p = files.get(fmt)
        if not p or not os.path.exists(str(p)):
            continue
        try:
            res = _compare(ref, reader(p), fmt)
        except Exception as e:
            res = [("E0", False, f"读不回来：{type(e).__name__} {str(e)[:60]}")]
        out[fmt] = (all(ok for _, ok, _ in res), res)
    return out


if __name__ == "__main__":
    svg = sys.argv[1]
    files = {os.path.splitext(f)[1][1:]: f for f in sys.argv[2:]}
    allok = True
    for fmt, (ok, res) in check(svg, files).items():
        print(fmt, "通过" if ok else "未过")
        for n, o, msg in res:
            print("  ", "OK  " if o else "FAIL", n, msg)
        allok &= ok
    sys.exit(0 if allok else 1)
