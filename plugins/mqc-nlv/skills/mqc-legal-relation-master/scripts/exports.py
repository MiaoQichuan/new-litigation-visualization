# -*- coding: utf-8 -*-
"""五种输出格式。

三个导出器都用 v1 现成的，不另写一份。它们分两类，输入不同：

  pptx / vsdx　借用 V1 的导出器，交给它之前先规整 SVG（圆角还原为直角）
  drawio　　　 本 skill 自己从最终 SVG 写，走线逐点照搬

三种可编辑格式都从同一份最终 SVG 取几何，导出后由 export_guard
逐个拆开读回、与 SVG 对照，未过的如实写进交付说明。
"""
import sys, os, json, re
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__))
# V1 的渲染与导出模块：单独分发时随包放在 vendor/v1/scripts，
# 在插件里则用同一插件另一个 skill 的那份。随包的优先，版本与自检时一致。
# 都按相对位置找，不写死绝对路径。
_V1 = _os.path.normpath(_os.path.join(_HERE, "..", "vendor", "v1", "scripts"))
if not _os.path.exists(_os.path.join(_V1, "export_pptx.py")):
    _V1 = _os.path.normpath(_os.path.join(
        _HERE, "..", "..", "mqc-litigation-visual-redraw", "scripts"))
for _p in (_HERE, _V1):
    if _p not in sys.path:
        sys.path.insert(0, _p)

FORMATS = ("svg", "png", "pptx", "vsdx", "drawio")


def to_png(svg_path, out_path, width=1700):
    import cairosvg
    cairosvg.svg2png(url=svg_path, write_to=out_path, output_width=width)
    return out_path


def to_pptx(svg_path, out_path, fonts="safe"):
    """出 PPT。字体档默认取 safe。

    v1 有两档：master 用思源宋体 / Noto Sans SC / IBM Plex Mono，
    safe 用宋体 / 微软雅黑 / Consolas。**默认应当是 safe**——
    交付给律师的 PPT 要在他自己的 Windows 上直接能开，
    master 那几款字体多数人机器上没有，一打开就回退成别的字，
    整份版面跟着走样。要用 master，得确认对方装了那几款。

    导出的每个元素都是原生形状（自选图形、文本框、线条），
    不是图片：颜色、大小、位置、文字都能在 PowerPoint 里直接改。
    """
    import export_pptx
    export_pptx.export(_normalized(svg_path), out_path, fonts=fonts)
    return out_path


def to_vsdx(svg_path, out_path):
    import export_vsdx
    export_vsdx.export(_normalized(svg_path), out_path)
    return out_path


def _normalized(svg_path):
    """交给 V1 导出器之前先规整一份临时 SVG。

    V1 的解析器只认 M / L / Q 与双引号属性，而本 skill 的 SVG
    拐角是圆弧（A）、虚线写的是单引号。不规整的话，
    每个拐角歪成一条斜线，虚线全成实线。V1 本身不动。
    """
    import tempfile, svg_geom
    src = open(svg_path, encoding="utf-8").read()
    fd, tmp = tempfile.mkstemp(suffix=".svg")
    os.close(fd)
    open(tmp, "w", encoding="utf-8").write(svg_geom.normalize(src))
    return tmp


STYLE_MODE = {"奇川风": None, "白描": "baimiao", "歸藏风": "guizang"}


def to_drawio(svg_path, out_path, style="奇川风"):
    """从最终 SVG 写 mxfile，几何与 SVG 逐点一致。

    先前的写法只给每条边指定起止主体，让 draw.io 自己排线：
    算好的拐点全部丢掉，主体位置也按网格估算，打开后线穿主体、
    线叠线都是 draw.io 自己画出来的。现在：

      主体　按 SVG 的实际坐标与尺寸写，名称与备注写在块内
      走线　绑定起止主体（拖动主体线会跟着走），出入口用
            exitX / entryX 钉在 SVG 的端点上，中间拐点逐个写成
            waypoint，edgeStyle 不开自动布线
      标签　写成独立文字块，位置取 SVG 标签的实际坐标
    """
    if not isinstance(svg_path, str):
        raise TypeError("to_drawio 现在从最终 SVG 取几何：to_drawio(svg_path, out_path, style)。"
                        "旧版按 nodes / edges / layout 生成的 drawio 会丢掉走线，已停用")
    import svg_geom
    from xml.sax.saxutils import escape, quoteattr
    g = svg_geom.read(open(svg_path, encoding="utf-8").read())
    cells, nid = [], 2

    def fc(c, default):
        c = (c or "").strip()
        return c if re.match(r"^#[0-9A-Fa-f]{6}$", c) else default
    node_ids = []
    for n in g["nodes"]:
        rows = []
        for t in n["lines"]:
            wt = "font-weight:bold;" if t["bold"] else ""
            rows.append(f'<span style="font-size:{t["fs"]:g}px;color:{fc(t["fill"], "#1F2933")};{wt}">'
                        f'{escape(t["t"])}</span>')
        value = "<br>".join(rows)
        fill = fc(n["fill"], "#F3F4F6")
        stroke = fc(n["stroke"], "none") if n["stroke"] else "none"
        arc = min(50, round(n["rx"] / min(n["w"], n["h"]) * 100)) if n["rx"] else 0
        st = (f"rounded={1 if arc else 0};arcSize={arc};whiteSpace=wrap;html=1;"
              f"fillColor={fill};strokeColor={stroke};fontColor=#1F2933;"
              "verticalAlign=middle;align=center;spacing=0;")
        cells.append(f'<mxCell id="n{nid}" value={quoteattr(value)} style="{st}" vertex="1" parent="1">'
                     f'<mxGeometry x="{n["x"]:.2f}" y="{n["y"]:.2f}" width="{n["w"]:.2f}" '
                     f'height="{n["h"]:.2f}" as="geometry"/></mxCell>')
        node_ids.append(f"n{nid}")
        nid += 1

    def owner(pt, reach):
        """端点落在哪个主体的边上；reach 是允许的离边距离（终点要让出箭头长度）。"""
        best = None
        for k, n in enumerate(g["nodes"]):
            dx = max(n["x"] - pt[0], 0, pt[0] - n["x"] - n["w"])
            dy = max(n["y"] - pt[1], 0, pt[1] - n["y"] - n["h"])
            d = (dx * dx + dy * dy) ** 0.5
            if d <= reach and (best is None or d < best[0]):
                best = (d, k)
        return None if best is None else best[1]

    def rel(k, pt):
        n = g["nodes"][k]
        return (min(max((pt[0] - n["x"]) / n["w"], 0), 1),
                min(max((pt[1] - n["y"]) / n["h"], 0), 1))
    for e in g["edges"]:
        pts = e["pts"]
        s0, s1 = pts[0], pts[-1]
        ks = owner(s0, 2.5)
        # 终点在 SVG 里让出了箭头长度，沿末段方向补回去才落在主体边上
        (ax, ay), (bx, by) = pts[-2], pts[-1]
        L = ((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5 or 1
        kt = owner(s1, 16)
        st = ("edgeStyle=none;rounded=0;html=1;orthogonalLoop=0;jettySize=auto;"
              f"strokeColor={fc(e['stroke'], '#4B5563')};strokeWidth={e['sw']:g};"
              "endArrow=block;endFill=1;endSize=8;"
              + ("dashed=1;dashPattern=4 3;" if e["dash"] else ""))
        attrs_ = ""
        if ks is not None:
            rx, ry = rel(ks, s0)
            st += f"exitX={rx:.4f};exitY={ry:.4f};exitDx=0;exitDy=0;exitPerimeter=0;"
            attrs_ += f' source="{node_ids[ks]}"'
        if kt is not None:
            n = g["nodes"][kt]
            # 补到主体边：沿末段方向前进，直到进入主体矩形
            ux, uy = (bx - ax) / L, (by - ay) / L
            ex, ey = bx, by
            for _ in range(40):
                if n["x"] - 0.01 <= ex <= n["x"] + n["w"] + 0.01 and n["y"] - 0.01 <= ey <= n["y"] + n["h"] + 0.01:
                    break
                ex, ey = ex + ux * 0.5, ey + uy * 0.5
            rx, ry = rel(kt, (ex, ey))
            st += f"entryX={rx:.4f};entryY={ry:.4f};entryDx=0;entryDy=0;entryPerimeter=0;"
            attrs_ += f' target="{node_ids[kt]}"'
        way = "".join(f'<mxPoint x="{x:.2f}" y="{y:.2f}"/>' for x, y in pts[1:-1])
        cells.append(f'<mxCell id="e{nid}" value="" style="{st}" edge="1" parent="1"{attrs_}>'
                     f'<mxGeometry relative="1" as="geometry">'
                     f'<mxPoint x="{s0[0]:.2f}" y="{s0[1]:.2f}" as="sourcePoint"/>'
                     f'<mxPoint x="{s1[0]:.2f}" y="{s1[1]:.2f}" as="targetPoint"/>'
                     f'<Array as="points">{way}</Array></mxGeometry></mxCell>')
        nid += 1
    for t in g["texts"]:
        w = max(len(t["t"]) * t["fs"] * 1.05, t["fs"] * 2)
        h = t["fs"] * 1.6
        x = t["x"] - (w / 2 if t["anchor"] == "middle" else (w if t["anchor"] == "end" else 0))
        y = t["y"] - t["fs"] * 1.15
        al = {"middle": "center", "end": "right"}.get(t["anchor"], "left")
        st = (f"text;html=1;strokeColor=none;fillColor=none;align={al};verticalAlign=middle;"
              f"spacing=0;fontSize={t['fs']:g};fontColor={fc(t['fill'], '#1F2933')};"
              + ("fontStyle=1;" if t["bold"] else ""))
        cells.append(f'<mxCell id="t{nid}" value={quoteattr(escape(t["t"]))} style="{st}" vertex="1" parent="1">'
                     f'<mxGeometry x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" as="geometry"/></mxCell>')
        nid += 1
    xml = ('<mxfile host="app.diagrams.net"><diagram name="法律关系图">'
           f'<mxGraphModel dx="{g["W"]:.0f}" dy="{g["H"]:.0f}" grid="0" page="1" '
           f'pageWidth="{g["W"]:.0f}" pageHeight="{g["H"]:.0f}" math="0" shadow="0"><root>'
           '<mxCell id="0"/><mxCell id="1" parent="0"/>'
           + "".join(cells) +
           '</root></mxGraphModel></diagram></mxfile>')
    mode = STYLE_MODE.get(style)
    if mode:
        import export_drawio
        xml = export_drawio.theme_drawio(xml, mode)
    open(out_path, "w", encoding="utf-8").write(xml)
    return out_path


def export_all(svg_path, base, nodes=None, edges=None, layout=None,
               emph=(), style="奇川风", formats=FORMATS, return_guard=False):
    """一次出齐。默认返回 {格式: 路径或原因}，与旧版调用方式完全兼容。

    return_guard=True 时返回 (产物, 导出物判据)，判据为 {格式: (全过, 明细)}。
    nodes / edges / layout / emph 是旧版 drawio 需要的参数，现在 drawio 从
    SVG 取几何，这几个参数收下不用，保留位置是为了旧调用不报错。
    判据未过的格式按交付规则撤下，产物里写明「未交付：原因」。
    """
    if not isinstance(style, str) or style not in STYLE_MODE:
        raise ValueError(f"风格只能是奇川风 / 白描 / 歸藏风其中一种，收到：{style!r}")
    if style != "奇川风":
        src = re.sub(r"<defs>.*?</defs>", "", open(svg_path, encoding="utf-8").read(), flags=re.S)
        if 'data-emph="1"' in src or "#991B1B" in src.upper():
            raise ValueError(f"{style}不提供强调选项，但这张 SVG 带着强调标记或深红。"
                             "强调只在选奇川风时由使用者指定：白描或歸藏风出图时不要传入任何强调")
    out = {"svg": svg_path}
    jobs = {"png": (to_png, (svg_path, base + ".png")),
            "pptx": (to_pptx, (svg_path, base + ".pptx")),
            "vsdx": (to_vsdx, (svg_path, base + ".vsdx")),
            "drawio": (to_drawio, (svg_path, base + ".drawio", style))}
    for name in formats:
        if name == "svg":
            continue
        fn, args = jobs[name]
        try:
            out[name] = fn(*args)
        except Exception as e:
            out[name] = f"失败：{type(e).__name__} {str(e)[:60]}"
    import export_guard
    guard = export_guard.check(svg_path, {k: v for k, v in out.items()
                                          if k in ("pptx", "vsdx", "drawio")})
    # 交付规则（使用者定的）：PPT 与 ProcessOn 用的 vsdx 两者都稳定才交；
    # 任一未过判据，两者一起撤下，只交 SVG、PNG 与 drawio。
    office = [k for k in ("pptx", "vsdx") if k in guard and not guard[k][0]]
    if office:
        why = "、".join(f"{k} " + "/".join(n for n, ok, _ in guard[k][1] if not ok)
                       for k in office)
        for k in ("pptx", "vsdx"):
            if k in out and not str(out[k]).startswith("失败"):
                try:
                    os.remove(out[k])
                except OSError:
                    pass
                out[k] = f"未交付：导出物判据未过（{why}）"
    if "drawio" in guard and not guard["drawio"][0]:
        why = "/".join(n for n, ok, _ in guard["drawio"][1] if not ok)
        try:
            os.remove(out["drawio"])
        except OSError:
            pass
        out["drawio"] = f"未交付：导出物判据未过（{why}）"
    return (out, guard) if return_guard else out
