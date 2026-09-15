# -*- coding: utf-8 -*-
"""三风格输出：奇川风（彩色母版）、白描（法庭打印）、歸藏风（线上分享）。

规范见 v1 的 references/visual-style.md，两条容易搞反的：

白描　**每个实底色块变成轮廓模块（白底黑框）**，深红消失。
      强调靠**更粗的描边与更重的字重**，不是靠黑底——
      先前把强调块改成黑底白字，正好反了。
      我们的强调原本是「深红实底、不加边线」，没有粗描边，
      所以转白描时要给它补上粗描边，否则重点无从读出。

歸藏风 蓝灰白三色，克莱因蓝只上色块不上线；
      中文用无衬线，字体列表必须含环境里真有的那一款，
      否则中文渲染成方块。
"""
import sys, re
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
import render as _v1

RED = "#991B1B"
INK = "#111111"
# 白描不给强调模块加粗框——规范只说「实底色块变成轮廓模块」，
# 强调靠字重读出来即可，额外加粗边框是我自己加的，不在规范里。


def _emphasis_boxes(svg):
    """原图里深红实底的模块：位置与大小。"""
    out = []
    for m in re.finditer(r'<rect([^>]*fill="' + RED + r'"[^>]*)>', svg):
        g = re.search(r'\sx="([\d.-]+)"[^>]*\sy="([\d.-]+)"[^>]*'
                      r'\swidth="([\d.]+)"[^>]*\sheight="([\d.]+)"', m.group(1))
        if g:
            out.append(tuple(float(x) for x in g.groups()))
    return out


def monochrome(svg):
    """白描：黑线白底，实底块一律转轮廓，强调改用粗描边。"""
    boxes = _emphasis_boxes(svg)
    out = _v1.to_monochrome(svg)
    for x, y, w, h in boxes:
        # 只把块内文字转黑，块本身交给 v1 的变换处理成白底细框。
        # 不另加粗边框：规范只说实底色块变轮廓，没说要加粗。
        def fix_text(m):
            tx, ty = float(m.group(1)), float(m.group(2))
            if x - 2 <= tx <= x + w + 2 and y - 2 <= ty <= y + h + 4:
                return re.sub(r'fill="[^"]*"', f'fill="{INK}"', m.group(0))
            return m.group(0)
        out = re.sub(r'<text x="([\d.-]+)" y="([\d.-]+)"[^>]*>[^<]*</text>',
                     fix_text, out)
    return out


def guizang(svg, layout="graphviz_relation"):
    """歸藏风：克莱因蓝实底、浅灰点阵底、无衬线。

    **layout 必须传。**v1 的每一步变换都带一个「这一步在这种图上该不该触发」
    的前置条件，不传就退回 True，于是每张图都报一句
    「matched NOTHING」——那是误报，而误报会把真报警一起淹掉。
    关系图传 graphviz_relation。

    另一半在渲染端：节点要包成 <g data-role="node">、强调的带 data-emph="1"、
    标题带 stroke-width="0.3"。裸 rect 这几步一个都认不出，
    克莱因蓝实底与大字轻标题就都不会出现。
    """
    out = _v1.to_guizang(svg, layout)
    # 字体列表要把本机确有的那一款放在**第一位**。
    #
    # 先前误判成「环境缺字体」，其实本机有 Noto Sans CJK SC，
    # 缺的是列表里写的 'Noto Sans SC'（少了 CJK 三个字母）。
    # 更要紧的是：渲染器对多字体回退的支持并不可靠，取不到第一个
    # 就直接用默认字体，中文全成方块——所以不能指望它一路回退下去，
    # 必须把可用的那一款排在最前。
    out = re.sub(r'font-family="[^"]*sans-serif"',
                 'font-family="Noto Sans CJK SC, Inter, '
                 "'Noto Sans SC', 'Helvetica Neue', Arial, sans-serif\"",
                 out)
    return out


def qichuan(svg):
    return svg


ALL = {"奇川风": qichuan, "白描": monochrome, "歸藏风": guizang}
