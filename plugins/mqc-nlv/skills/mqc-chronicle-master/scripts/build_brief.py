#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""大事记简表：渲染输入.json → A4 竖版 SVG（一页一张，P1 / P2 …）。

三件套里的第三件，呈报给法官或当事人用。

**读的是 渲染输入.json，与 Word 交付版、Excel 母表同一份输入。**
早先自己从底稿另做一遍映射，结构立刻就与 Word 对不上了：日期写法不同、
序号成了 F001、备注里的标记全丢。同源才不会漂。

结构照 Word 交付版，只去掉「主要内容」那一列——原文照录那一段是 Word 与
Excel 的活，搬上图就成了第二份 Word。剩下序号、日期、事项、备注四列，
备注原样取自 Word 的 note_parts（来源、争点、关联、标记），不是另编的。

版面单位 1 = 0.1mm，画布 2100×2970 即 A4 竖版；字号按磅换算（1pt = 3.528 单位），
打印出来是多大就是多大。
"""
import json, os, re, sys

W, H = 2100, 2970                 # A4 竖版
MARGIN = 240                      # 四周 24mm，与 Word 交付版一致
AVAIL = W - 2 * MARGIN            # 1620
PT = 3.528

FS_TITLE, FS_SUB, FS_HEAD, FS_BODY, FS_TAG, FS_FOOT = (
    22 * PT, 10.5 * PT, 10.5 * PT, 10.5 * PT, 8 * PT, 9 * PT)
LH = 46
ROW_PAD = 20
ROW_MIN = 84

# 偏暖的深灰，不用纯黑也不用中性灰
INK, INK2, LINE, LINE_SOFT, RED = "#33302C", "#6B655D", "#8A8378", "#D8D3C9", "#991B1B"
EA, LATIN, TITLE_EA = "宋体", "Times New Roman", "方正小标宋简体"

# 四列与 Word 交付版同名同序，去掉的是「备注」那一列。
# 备注一格里塞着来源、争点、关联、标记好几段并列信息，排进图里必然乱；
# 主要内容是一段连续原文，折行就是自然的段落折行。来源与标记在 Word 与 Excel 里都有。
# 列宽按实测：事项要装下 14 字的标题（520），日期要装下「2025.01（仅到月）」（320）。
COLS = [("序号", 140), ("日期", 380), ("事项", 460), ("主要内容", 640)]
assert sum(w for _, w in COLS) == AVAIL, "M1 列宽之和须等于可用宽"

# 红只给这几个机械标记，做成小圆角红底白字，全图很少的几处
# 主要内容在图上至多三行，**按句读边界取**：取到完整的句子为止，一句或两句。
# 不按字截、不加省略号——这是呈报件，省略号会让人问「为什么不给我全的」。
# 每个字仍是原文，只是少取几句，所以不违反「照录、不得改写」那条红线。
MAXL_CONTENT = 3
SENT_END = "。；！？"
HARD_MAX = 5                  # 极端长句的硬上限，正常不会走到

CJK_PUNCT = set("　、。，；：（）《》「」【】·…—－’‘“”")
is_cjk = lambda c: ord(c) > 0x2E80 or c in CJK_PUNCT


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def segs(s):
    """按字符集切段：中文与中文标点走宋体，英文数字走新罗马。"""
    out, cur, k = [], "", None
    for ch in str(s):
        c = is_cjk(ch)
        if ch.isspace():
            cur += ch
            continue
        if k is None or c == k:
            cur += ch; k = c
        else:
            out.append((k, cur)); cur, k = ch, c
    if cur:
        out.append((bool(k), cur))
    return out


def justify(line, fs, fill, x, width, y, bold=False):
    """两端对齐：把一行铺满列宽。SVG 没有原生 justify，
    自己把多出来的空隙均摊到字与字之间，逐字定位——
    textLength 与 letter-spacing 在 cairosvg 上都不可靠。"""
    chars = list(str(line))
    if len(chars) < 2:
        return rich(line, fs, fill, x, y, bold=bold)
    nat = text_w(line, fs)
    extra = (width - nat) / (len(chars) - 1)
    b = ' font-weight="700"' if bold else ""
    out, cx = [], x
    for ch in chars:
        out.append(f'<tspan x="{cx:.1f}" y="{y:.0f}" '
                   f'font-family="{EA if is_cjk(ch) else LATIN}">{esc(ch)}</tspan>')
        cx += cw(ch, fs) + extra
    return (f'<text data-x="{x:.0f}" data-w="{width:.0f}" data-a="start" '
            f'font-size="{fs:.0f}" fill="{fill}"{b}>{"".join(out)}</text>')


def cell(o, paras, cx, colw, ytop, h, fs, fill, bold=False, para_mode=False):
    """一格的排法。paras 是段落表，每段已折好行。
    整块文字在格内纵向居中；整格只有一行就横向居中；
    多行时按段排，**只有同一段里因放不下而折出来的行才两端对齐**，段末行靠左。
    备注那一栏是好几个独立段落（来源、关联、标记），各自本来就一行，
    把它们也拉满宽，字距会大得没法看。"""
    inner = colw - 2 * ROW_PAD
    total = sum(len(p) for p in paras)
    y0 = ytop + (h - total * LH) / 2 + LH - 12
    if not para_mode:
        # 序号、日期、事项是标签性的内容，折了行也逐行居中，不拉伸。
        # 真材料撞出来的：区间日期「2020.05.09至2021.08.11」一折行，
        # 两端对齐把它拉成「2 0 2 0 . 0 5 . 0 9 至」，没法看。
        k = 0
        for p in paras:
            for ln in p:
                o.append(rich(ln, fs, fill, cx + colw / 2, y0 + k * LH,
                              anchor="middle", bold=bold))
                k += 1
        return
    k = 0
    for p in paras:
        for i, ln in enumerate(p):
            y = y0 + k * LH; k += 1
            if i == len(p) - 1:                      # 段的最后一行不拉伸
                o.append(rich(ln, fs, fill, cx + ROW_PAD, y, bold=bold))
            else:
                o.append(justify(ln, fs, fill, cx + ROW_PAD, inner, y, bold=bold))


def rich(s, fs, fill, x, y, anchor=None, bold=False):
    """一段文字按字符集拆成 tspan，中文走宋体、英文数字走新罗马。
    整段钉一个 font-family 是错的：英文数字会跟着中文字体走。
    每个 tspan 显式给 x，不靠 text-anchor——cairosvg 遇上「anchor + 多 tspan」
    锚点算不准，页脚的「第 1 页 / 共 2 页」当场错位成「第 页 共 2页」。"""
    b = ' font-weight="700"' if bold else ""
    total = text_w(s, fs)
    cx = x - total if anchor == "end" else (x - total / 2 if anchor == "middle" else x)
    out = []
    for k, v in segs(s):
        out.append(f'<tspan x="{cx:.1f}" y="{y:.0f}" font-family="{EA if k else LATIN}">'
                   f'{esc(v)}</tspan>')
        cx += text_w(v, fs)
    return (f'<text data-x="{x:.0f}" data-w="{total:.0f}" data-a="{anchor or "start"}" '
            f'font-size="{fs:.0f}" fill="{fill}"{b}>{"".join(out)}</text>')


def cw(ch, fs):
    return fs if is_cjk(ch) else fs * 0.52


def text_w(s, fs):
    return sum(cw(c, fs) for c in str(s))


def wrap(s, width, fs):
    s = str(s)
    out, cur, acc = [], "", 0.0
    for t in re.findall(r"[0-9A-Za-z.,:%\-/]+|\s+|.", s):
        w = text_w(t, fs)
        if acc + w > width and cur.strip():
            out.append(cur.rstrip()); cur, acc = "", 0.0
            if t.isspace():
                continue
        cur += t; acc += w
    if cur.strip():
        out.append(cur.rstrip())
    # 避孤字：末行只剩一两个字时从上一行借，否则上一行被拉满、末行吊着一个「》」
    while len(out) >= 2 and len(out[-1]) <= 2 and len(out[-2]) > 3:
        out[-1] = out[-2][-1] + out[-1]; out[-2] = out[-2][:-1]
    return out or [""]


class Row:
    @staticmethod
    def _brief(text):
        """按句读边界取：逐句累加，加不下就停，至少留一句。
        取出来的是若干个完整句子，不是半截话，所以不需要省略号。"""
        w = COLS[3][1] - 2 * ROW_PAD
        text = str(text).strip()

        def finish(t):
            """统一出口：一律以句号收尾。停在分号上的、原文本就没有句末标点的，
            都补成句号——呈报件上一句话必须是说完的。这是规范标点，不动内容。"""
            t = t.rstrip("　 ").rstrip("，、：；;,")
            if t and t[-1] not in "。！？":
                t += "。"
            return wrap(t, w, FS_BODY)[:HARD_MAX]

        if len(wrap(text, w, FS_BODY)) <= MAXL_CONTENT:
            return finish(text)
        sents, cur = [], ""
        for ch in text:
            cur += ch
            if ch in SENT_END:
                sents.append(cur); cur = ""
        if cur.strip():
            sents.append(cur)

        kept = []
        for sn in sents:
            if kept and len(wrap("".join(kept) + sn, w, FS_BODY)) > MAXL_CONTENT:
                break
            kept.append(sn)
        keep = "".join(kept).strip()

        if len(wrap(keep, w, FS_BODY)) > MAXL_CONTENT:
            # 第一句本身就超行：退到次级边界（分句的逗号、顿号、冒号），
            # 断在这些地方仍是一个说得完整的意群，末尾补句号收住。
            for sep in ("，", "、", "："):
                if sep not in keep:
                    continue
                acc, parts = "", keep.split(sep)
                for p in parts[:-1]:
                    if acc and len(wrap(acc + p + sep + "。", w, FS_BODY)) > MAXL_CONTENT:
                        break
                    acc += p + sep
                if acc:
                    keep = acc.rstrip("，、：；") + "。"
                    break

        # 宁可多占一行，也不让半句话出现在呈报件上；实在收不住才让它走满硬上限
        return finish(keep)

    def __init__(self, no, r):
        self.no = no
        # 简表是呈报件，不带内部标记（本程序新证据、读图转写未经逐字核验），
        # 也不带来源与关联——那些在 Word 交付版与 Excel 母表上保留，红线仍然守住。
        # 每格存的是段落表：段落之间是并列关系，段落内部才是折行
        self.cells = [
            [wrap(str(no), COLS[0][1] - 2 * ROW_PAD, FS_BODY)],
            [wrap(r.get("date", ""), COLS[1][1] - 2 * ROW_PAD, FS_BODY)],
            [wrap(r.get("item", ""), COLS[2][1] - 2 * ROW_PAD, FS_BODY)],
            [self._brief(r.get("content", ""))],
        ]
        # 出图前自证：日期要与渲染输入逐字一致。
        # 这条不能靠扫产物文本来查——区间日期会折行，拼起来中间夹着别列的字，
        # 整串就匹配不上；要盯真正画进去的那份数据。
        _d  = "".join(str(r.get("date", "")).split())
        _dg = "".join("".join(self.cells[1][0]).split())
        assert _d == _dg, f"B2 日期与渲染输入不一致：{_dg} ≠ {_d}"
        # 出图前自证：画进主要内容那一栏的字，必须是原文的前缀。
        # 按句读边界取是「少取几句」，不是「换几个字」；末尾那个句号是收句补的。
        _full = "".join(str(r.get("content", "")).split())
        _got  = "".join("".join(self.cells[3][0]).split())
        assert (not _full) or _full.startswith(_got) or _full.startswith(_got.rstrip("。")), \
            f"B3 主要内容不是原文的前缀，渲染层改了字：{_got[:24]}"
        # 而且必须停在句读上。只验前缀不够：截前九个字也是前缀，却是半句话，
        # 而这是呈报件，半句话不能出现在上面。
        assert (not _got) or _got[-1] in "。！？", \
            f"B3 主要内容没停在句读上，是半句话：…{_got[-14:]}"
        n = max(sum(len(p) for p in c) for c in self.cells)
        self.h = max(ROW_MIN, 2 * ROW_PAD + n * LH)


TITLE_H = 230
HEAD_H = 96
FOOT_H = 88
GROUP_H = 106                 # 争点分组：色块加上下呼吸位
GROUP_PAD = 30                # 色块与上方横线之间的呼吸位
RX = 14                       # 外框圆角，小一点
CHIP_RX = 8                   # 色块圆角


def paginate(blocks, first_top, rest_top):
    pages, cur, y = [], [], first_top
    limit = H - MARGIN - FOOT_H
    for i, b in enumerate(blocks):
        h = GROUP_H if b[0] == "group" else b[1].h
        nxt = blocks[i + 1] if i + 1 < len(blocks) else None
        need = h + (nxt[1].h if b[0] == "group" and nxt and nxt[0] == "row" else 0)
        if cur and y + need > limit:
            pages.append(cur); cur, y = [], rest_top
        cur.append((y, b)); y += h
    if cur:
        pages.append(cur)
    return pages


def chip(o, x, y, txt, fs=FS_HEAD):
    """小圆角矩形、红底白字，文字纵横都居中。全图的红只用在这里。"""
    w = text_w(txt, fs) + 48
    h = fs + 30
    o.append(f'<rect x="{x:.0f}" y="{y:.0f}" width="{w:.0f}" height="{h:.0f}" '
             f'rx="{CHIP_RX}" fill="{RED}"/>')
    o.append(rich(txt, fs, "#FFFFFF", x + w / 2, y + h / 2 + fs * 0.36, anchor="middle"))
    return w


def render_page(D, page, idx, total, first, box_top, box_bot):
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W/10:.0f}mm" height="{H/10:.0f}mm" '
         f'viewBox="0 0 {W} {H}">',
         f'<rect width="{W}" height="{H}" fill="#FFFFFF"/>']
    case = D.get("case", {})
    xs, x = [], MARGIN
    for _, w in COLS:
        xs.append(x); x += w

    if first:
        t = case.get("title", "案件大事记")
        o.append(f'<text data-x="{W/2:.0f}" data-w="{text_w(t, FS_TITLE):.0f}" data-a="middle" '
                 f'x="{W/2 - text_w(t, FS_TITLE)/2:.0f}" y="{MARGIN + FS_TITLE*0.86:.0f}" '
                 f'font-size="{FS_TITLE:.0f}" fill="{INK}" font-family="{TITLE_EA}">{esc(t)}</text>')
        o.append(rich(case.get("subtitle", ""), FS_SUB, INK2,
                      W / 2, MARGIN + FS_TITLE + 52, anchor="middle"))

    # 外框：一个圆角矩形把整张表包住（承对抗图索引表的做法），内部只画横线，不画竖线
    o.append(f'<rect x="{MARGIN}" y="{box_top}" width="{AVAIL}" height="{box_bot - box_top}" '
             f'rx="{RX}" fill="none" stroke="{LINE}" stroke-width="3"/>')

    hy = box_top
    for (name, w), cx in zip(COLS, xs):
        o.append(rich(name, FS_HEAD, INK, cx + w / 2, hy + HEAD_H - 34,
                      anchor="middle", bold=True))
    o.append(f'<line x1="{MARGIN + 16}" y1="{hy + HEAD_H}" x2="{W - MARGIN - 16}" y2="{hy + HEAD_H}" '
             f'stroke="{LINE}" stroke-width="3"/>')

    for y, b in page:
        if b[0] == "group":
            # 分组标题做成红底白字的小圆角色块，摆在这一组的左上角，不再压一条横线
            chip(o, MARGIN + ROW_PAD, y + GROUP_PAD, b[1])
            continue
        row = b[1]
        for ci, (paras, cx) in enumerate(zip(row.cells, xs)):
            # 主要内容按正文段落排：一律左起、右侧除末行外都对齐，不居中——
            # 居中会让这一列每行的左边界都不一样，整列看着是散的
            cell(o, paras, cx, COLS[ci][1], y, row.h, FS_BODY,
                 INK if ci == 2 else INK2, bold=(ci == 2), para_mode=(ci == 3))
        if (y, b) != page[-1]:
            o.append(f'<line x1="{MARGIN + 16}" y1="{y + row.h}" x2="{W - MARGIN - 16}" '
                     f'y2="{y + row.h}" stroke="{LINE_SOFT}" stroke-width="2"/>')

    fy = H - MARGIN + 44
    o.append(rich(f'{case.get("subtitle", "")}　大事记简表', FS_FOOT, INK2, MARGIN, fy))
    o.append(rich(f'第 {idx} 页 / 共 {total} 页', FS_FOOT, INK2, W - MARGIN, fy, anchor="end"))
    o.append("</svg>")
    return "\n".join(o)


TEXT_RE = re.compile(r'<text data-x="([\d.-]+)" data-w="([\d.-]+)" data-a="(\w+)"[^>]*>(.*?)</text>')


def verify_svg(svg, page_no):
    """扫产物：任何一段文字都不得越出版心。
    锚点与宽度由渲染时写进 data- 属性，判据读产物，不重算一遍。"""
    for m in TEXT_RE.finditer(svg):
        x, w, a, inner = float(m.group(1)), float(m.group(2)), m.group(3), m.group(4)
        txt = re.sub(r"<[^>]+>", "", inner)
        if not txt.strip():
            continue
        left = x - w if a == "end" else (x - w / 2 if a == "middle" else x)
        assert left + w <= W - MARGIN + 1, (
            f"M3 第 {page_no} 页文字越出右版心（「{txt[:16]}」右端 {left + w:.0f}）")
        assert left >= MARGIN - 1, (
            f"M3 第 {page_no} 页文字越出左版心（「{txt[:16]}」）")


def verify(pages, blocks):
    rows = [b for b in blocks if b[0] == "row"]
    got = sum(1 for pg in pages for _, b in pg if b[0] == "row")
    assert got == len(rows), f"B1 分页丢了事实行：应 {len(rows)} 条，实 {got} 条"
    limit = H - MARGIN - FOOT_H
    for i, pg in enumerate(pages, 1):
        for y, b in pg:
            h = GROUP_H if b[0] == "group" else b[1].h
            assert y + h <= limit + 0.5, f"M2 第 {i} 页有块越出版心"
    nos = [b[1].no for pg in pages for _, b in pg if b[0] == "row"]
    assert nos == list(range(1, len(nos) + 1)), f"N1 序号须是 1 起的连号（实为 {nos[:6]}…）"


def build(src, outdir):
    """src 是 渲染输入.json——与 Word、Excel 同一份输入。"""
    D = json.load(open(src, encoding="utf-8"))
    os.makedirs(outdir, exist_ok=True)
    rs = D.get("rows") or []

    grouped = any(str(r.get("issue", "")).strip() for r in rs)
    blocks = []
    if grouped:
        seen = []
        for r in rs:
            k = str(r.get("issue", "")).strip() or "未归入争点"
            if k not in seen:
                seen.append(k)
        n = 0
        for k in seen:
            blocks.append(("group", k))
            for r in rs:
                if (str(r.get("issue", "")).strip() or "未归入争点") == k:
                    n += 1; blocks.append(("row", Row(n, r)))
    else:
        blocks = [("row", Row(i + 1, r)) for i, r in enumerate(rs)]

    first_top = MARGIN + TITLE_H + HEAD_H
    rest_top = MARGIN + HEAD_H
    pages = paginate(blocks, first_top, rest_top)
    verify(pages, blocks)

    out = []
    for i, pg in enumerate(pages, 1):
        box_top = (MARGIN + TITLE_H) if i == 1 else MARGIN
        box_bot = max(y + (GROUP_H if b[0] == "group" else b[1].h) for y, b in pg) + 12
        svg = render_page(D, pg, i, len(pages), i == 1, box_top, box_bot)
        verify_svg(svg, i)
        p = os.path.join(outdir, f"大事记简表-P{i}.svg")
        open(p, "w", encoding="utf-8").write(svg)
        out.append(p)
    print(f"  简表：{len(pages)} 页，{len(rs)} 条事实"
          f"（{'按争点分组' if grouped else '按时序平铺'}）")
    for p in out:
        print(f"        {p}")
    return out


if __name__ == "__main__":
    build(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "out")
