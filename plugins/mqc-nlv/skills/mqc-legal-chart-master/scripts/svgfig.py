# -*- coding: utf-8 -*-
"""最小的 SVG 写手。

两条约束都是为了让 V1 的 PPTX 导出器原样转写：
  * 颜色、线宽、字号一律写成**显式属性**，不用 class 与 <style>（导出器只读属性）；
  * 填充形状一律带贝塞尔小圆角（corners.rounded_d），连矩形也写成 path，不用 rx。
    导出 PPTX 前由 make.pptx_ready() 处理：矩形还原成原生圆角矩形，其余曲线细分成折线
    （V1 的导出器只认直线段）。
  * 有圆角的风格，线段一律圆头（stroke-linecap="round"）：线头的直角也是尖角。
    歸藏风没有圆角，线头保持平头。

每个数据元素都带 data-role / data-id / data-value，守卫按这些属性回读产物核对比例，
而不是相信渲染器自己的说法。
"""
import hashlib

from kernel import esc, TITLE_FONT, BODY_FONT, MONO_FONT
from corners import rounded_d, rect_pts


def _n(v):
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


class Fig:
    def __init__(self, W, H, pal, corner=2.5):
        self.W, self.H, self.p = W, H, pal
        self.corner = corner        # 小圆角半径（px），由画框按画布尺寸给定
        self.parts = []
        self.defs = []
        self.a11y = None            # (标题, 说明)：读屏软件与搜索引擎读这两句

    # ---- attributes -------------------------------------------------------
    @staticmethod
    def _meta(role=None, id=None, value=None, hero=False, extra=None):
        a = ""
        if role:
            a += f' data-role="{role}"'
        if id is not None:
            a += f' data-id="{esc(str(id))}"'
        if value is not None:
            a += f' data-value="{_n(value) if isinstance(value, (int, float)) else esc(str(value))}"'
        if hero:
            a += ' data-hero="1"'
        for k, v in (extra or {}).items():
            a += f' data-{k}="{_n(v) if isinstance(v, (int, float)) else esc(str(v))}"'
        return a

    @staticmethod
    def _paint(fill, stroke, sw, dash):
        a = f' fill="{fill or "none"}"'
        if stroke:
            a += f' stroke="{stroke}" stroke-width="{_n(sw)}"'
            if dash:
                a += f' stroke-dasharray="{dash}"'
        return a

    # ---- primitives -------------------------------------------------------
    def rect(self, x, y, w, h, fill, stroke=None, sw=1, dash=None, square=False, r=None, **meta):
        """矩形也写成带小圆角的 path；data-shape 记下它原本是矩形，导出 PPTX 时还原成原生圆角矩形。

        square=True 给细长条用（桑基与汇入图两侧的竖条）：作者定的，长条的边不磨圆。"""
        r = 0.0 if square else min(self.corner if r is None else r, w / 2, h / 2)
        ex = dict(meta.pop("extra", None) or {})
        ex.update({"shape": "rect", "x": x, "y": y, "w": w, "h": h, "r": r})
        if square:
            ex["square"] = 1
        self.parts.append(f'<path d="{rounded_d(rect_pts(x, y, w, h), r)}"'
                          f'{self._paint(fill, stroke, sw, dash)}{self._meta(extra=ex, **meta)}/>')

    def module(self, cx, cy, side, fill, stroke=None, sw=1, dash=None, **meta):
        """方块模块：点阵的一格。奇川风是带贝塞尔圆角的正方形（圆角 = 边长 × module），歸藏风是直角正方形。
        作者定的：点阵不用圆点，用方块——像一块块拼起来的模块，也和 V7 课件的磁吸模块同一种语言。"""
        r = side * self.p.get("module", 0.0)
        ex = dict(meta.pop("extra", None) or {})
        ex["module"] = 1
        self.rect(cx - side / 2, cy - side / 2, side, side, fill, stroke, sw, dash, r=r, extra=ex, **meta)

    def circle(self, cx, cy, r, fill, stroke=None, sw=1, dash=None, **meta):
        self.parts.append(f'<circle cx="{_n(cx)}" cy="{_n(cy)}" r="{_n(r)}"'
                          f'{self._paint(fill, stroke, sw, dash)}{self._meta(**meta)}/>')

    def line(self, x1, y1, x2, y2, stroke, sw=1, dash=None, square=False, **meta):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        cap = ' stroke-linecap="round"' if self.corner > 0 and not square else ""
        if square:
            meta["extra"] = dict(meta.get("extra") or {}, square=1)
        self.parts.append(f'<line x1="{_n(x1)}" y1="{_n(y1)}" x2="{_n(x2)}" y2="{_n(y2)}" '
                          f'stroke="{stroke}" stroke-width="{_n(sw)}"{cap}{d}{self._meta(**meta)}/>')

    def poly(self, pts, fill, stroke=None, sw=1, dash=None, opacity=None, square=False, **meta):
        """闭合多边形，尖角磨成贝塞尔小圆角（弧线采样点之间的微小折点不磨）。

        square=True 给流带用（桑基、汇入图）：作者定的，流带是长条，与两侧竖条一样，角不磨圆。

        opacity 只给「叠加本身就是信息」的形状用（汇入图的流带：交叉处颜色变深，读者才看得出
        两股流在那里重叠）。其余一律实心。"""
        op = f' fill-opacity="{_n(opacity)}"' if opacity is not None else ""
        if square:
            meta["extra"] = dict(meta.get("extra") or {}, square=1)
        self.parts.append(f'<path d="{rounded_d(pts, 0.0 if square else self.corner)}"'
                          f'{self._paint(fill, stroke, sw, dash)}{op}{self._meta(**meta)}/>')

    def curve(self, p0, p1, stroke, sw=1, dash=None, **meta):
        """一条水平进出的三次贝塞尔曲线（流向中线）。"""
        (x0, y0), (x1, y1) = p0, p1
        xm = (x0 + x1) / 2
        cap = ' stroke-linecap="round"' if self.corner > 0 else ""
        da = f' stroke-dasharray="{dash}"' if dash else ""
        self.parts.append(f'<path d="M{_n(x0)},{_n(y0)} C{_n(xm)},{_n(y0)} {_n(xm)},{_n(y1)} {_n(x1)},{_n(y1)}"'
                          f' fill="none" stroke="{stroke}" stroke-width="{_n(sw)}"{cap}{da}{self._meta(**meta)}/>')

    def path(self, d, stroke, sw=1, dash=None, **meta):
        """一条开放的描边路径（批注引线）。奇川风圆头，歸藏风平头。"""
        cap = ' stroke-linecap="round"' if self.corner > 0 else ""
        da = f' stroke-dasharray="{dash}"' if dash else ""
        self.parts.append(f'<path d="{d}" fill="none" stroke="{stroke}" stroke-width="{_n(sw)}"{cap}{da}'
                          f'{self._meta(**meta)}/>')

    def text(self, x, y, s, fs, fill, anchor="start", weight=400, family="sans", track=0.0, rot=None, **meta):
        """rot（度，顺时针）：绕 (x, y) 转，给顺着辐条写的标签用（0.11.0，发射扇）。
        V1 的 PPTX 导出器照样转写（文本框带 rot），守卫按转过之后的外框核出界与互压。"""
        fam = {"serif": TITLE_FONT, "mono": MONO_FONT, "sans": BODY_FONT}[family]
        a = f' text-anchor="{anchor}"' if anchor != "start" else ""
        t = f' letter-spacing="{_n(track)}"' if track else ""
        w = f' font-weight="{weight}"' if weight != 400 else ""
        # 宋体标题加同色细描边：没有粗体字面的回退宋体（例如 Linux 上的 LibreOffice）也显得够粗。
        # 做法与 V1 的标题一致。
        st = f' stroke="{fill}" stroke-width="0.3"' if family == "serif" and weight >= 700 else ""
        tr = f' transform="rotate({_n(rot)} {_n(x)} {_n(y)})"' if rot else ""
        self.parts.append(f'<text x="{_n(x)}" y="{_n(y)}" font-size="{_n(fs)}" fill="{fill}"'
                          f' font-family="{fam}"{a}{w}{t}{st}{tr}{self._meta(**meta)}>{esc(str(s))}</text>')

    def pattern_dots(self, color, step=26):
        self.defs.append(f'<pattern id="nlv-dots" width="{step}" height="{step}" patternUnits="userSpaceOnUse">'
                         f'<circle cx="1.5" cy="1.5" r="1.1" fill="{color}"/></pattern>')

    def svg(self):
        W, H, p = self.W, self.H, self.p
        # id 带上这张图自己的指纹（0.9.8）：原来一律叫 nlv-title / nlv-desc / nlv-dots，
        # 两张图放进同一个网页（公众号排版、课件预览）时 id 撞车，读屏软件把第二张图念成第一张的标题。
        # 指纹由图名、说明、尺寸算出：同一份说明出同一个 id，确定性不变。
        uid = hashlib.sha1(f"{self.a11y}|{int(W)}x{int(H)}|{''.join(self.defs)}".encode("utf-8")).hexdigest()[:8]
        head = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{int(W)}" height="{int(H)}" '
                f'viewBox="0 0 {int(W)} {int(H)}" font-family="{BODY_FONT}"'
                + (f' role="img" aria-labelledby="nlv-title-{uid} nlv-desc-{uid}">' if self.a11y else ">"))
        if self.a11y:
            # 学自 diagram-design 的无障碍约定：title 与 desc 是 svg 的头两个子元素
            head += (f'<title id="nlv-title-{uid}">{esc(self.a11y[0])}</title>'
                     f'<desc id="nlv-desc-{uid}">{esc(self.a11y[1])}</desc>')
        bg = f'<rect width="{int(W)}" height="{int(H)}" fill="{p["paper"]}" data-role="paper"/>'
        defs = (f"<defs>{''.join(self.defs)}</defs>".replace('id="nlv-dots"', f'id="nlv-dots-{uid}"')
                if self.defs else "")
        grid = (f'<rect width="{int(W)}" height="{int(H)}" fill="url(#nlv-dots-{uid})" data-role="texture"/>'
                if self.defs else "")
        return head + bg + defs + grid + "".join(self.parts) + "</svg>\n"
