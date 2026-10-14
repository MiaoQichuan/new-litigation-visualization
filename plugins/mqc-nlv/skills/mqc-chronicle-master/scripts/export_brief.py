#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""简表导出：SVG → A4 PDF（呈报用）+ PNG（预览用）。

SVG 是可编辑源，案号、当事人称谓、事项措辞都可能要律师手改，改完重出。
PDF 是主交付：A4 竖版天然对应纸张，法院电子提交系统收的也是它。

光栅化前必须把字族栈换成本机装着的单一字族——cairosvg 解析不了带引号的
多字族栈，会静默回退到一个没有中文的字体，出来满屏豆腐块（时间轴大师踩过）。
pypdf 有就把多页合成一个文件，没有就留分页，不作硬依赖。
"""
import os, re, subprocess, sys

CJK_CANDIDATES = ["Source Han Serif SC", "Noto Serif CJK SC", "Noto Serif CJK TC",
                  "Songti SC", "SimSun", "宋体", "Noto Sans CJK SC"]
# 新罗马的 metric 兼容替代，按优先级；都没有才回落到中文族（它自带拉丁字形）
LATIN_CANDIDATES = ["Times New Roman", "Liberation Serif", "Nimbus Roman",
                    "FreeSerif", "DejaVu Serif"]
# 标题族。方正小标宋是版式规范里定死的，但多数 Linux 机器没有；
# 换掉了就必须报出来，不能让人以为 PDF 上的标题就是方正小标宋。
TITLE_CANDIDATES = ["方正小标宋简体", "FZXiaoBiaoSong-B05S", "FZXiaoBiaoSong-B05",
                    "Source Han Serif SC Heavy", "Noto Serif CJK SC"]


# Windows 字体目录里的文件名 → 字族名（fc-list 在 Windows 上通常没有）
_WIN_FONT_FILES = {
    "simsun.ttc": "SimSun 宋体", "simsunb.ttf": "SimSun 宋体",
    "times.ttf": "Times New Roman", "timesbd.ttf": "Times New Roman",
    "FZXBSJW.TTF": "方正小标宋简体 FZXiaoBiaoSong-B05S", "fzxbsjw.ttf": "方正小标宋简体 FZXiaoBiaoSong-B05S",
    "SourceHanSerifSC-Regular.otf": "Source Han Serif SC",
    "NotoSerifCJKsc-Regular.otf": "Noto Serif CJK SC", "NotoSerifSC-Regular.otf": "Noto Serif CJK SC",
}


def _installed():
    """本机装了哪些字族，返回一段可供 `in` 查找的文本。

    先问 fc-list；没有（Windows 上通常没有）就去扫系统字体目录按文件名认。
    真实运行记录：Windows 上没有 fc-list，这里返回空串，下面直接判「本机没有可用的
    中文字族」并中断导出，还把前面已经做好的 Word 与 Excel 一起拖垮 —— 而那台机器
    明明装着宋体与新罗马。"""
    try:
        out = subprocess.run(["fc-list", ":", "family"],
                             capture_output=True, text=True,
                             encoding="utf-8", errors="replace").stdout   # fc-list 输出 UTF-8
        if out.strip():
            return out
    except (FileNotFoundError, OSError):
        pass
    names = []
    for d in (os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"),
              os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Windows", "Fonts")):
        try:
            files = os.listdir(d)
        except OSError:
            continue
        low = {f.lower(): f for f in files}
        for fn, fam in _WIN_FONT_FILES.items():
            if fn.lower() in low:
                names.append(fam)
    return "\n".join(names)


def pick_font():
    """分别挑中文族与西文族。
    两族要各挑各的：早先把所有 font-family 一律替换成同一个中文族，
    结果写着 Times New Roman 的那些 tspan 跟着被换掉；
    而若只换中文族、西文族本机又没装，cairosvg 会把整段静默丢掉——
    页脚的「第 1 页 / 共 2 页」当场只剩「第 页 共 页」，数字全没了。"""
    have = _installed()
    zh = next((f for f in CJK_CANDIDATES if f in have), None)
    if not zh:
        raise RuntimeError("本机没有可用的中文字族，光栅化会出豆腐块；"
                           "请安装 Noto Serif CJK SC 或思源宋体后重试")
    la = next((f for f in LATIN_CANDIDATES if f in have), zh)
    ti = next((f for f in TITLE_CANDIDATES if f in have), zh)
    return zh, la, ti


def single_family(svg, zh, la, ti):
    """SVG 里写的是逻辑族名（宋体 / 方正小标宋简体 / Times New Roman），
    这里换成本机确实装着的族。单一族名，不留字族栈——cairosvg 解析不了带引号的栈。
    三族各换各的：早先一律替换成同一个中文族，写着新罗马的那些段跟着被换掉。"""
    svg = svg.replace('font-family="方正小标宋简体"', f'font-family="{ti}"')
    svg = svg.replace('font-family="Times New Roman"', f'font-family="{la}"')
    return svg.replace('font-family="宋体"', f'font-family="{zh}"')


def export(svgs, outdir, dpi=200):
    """简表是管线末尾的一件，装不了 cairosvg 也不该把前面做好的 Word 与 Excel 拖垮：
    SVG 已经出来了，这里只是换格式，缺依赖就跳过导出并说清楚怎么补。"""
    try:
        import cairosvg
    except (ImportError, OSError):
        # 缺 cairo 本体（Windows 上常见：pip 装了壳、没有 cairo-2.dll）时抛的是 OSError，
        # 原来只捕 ImportError，于是直接崩掉，连前面做好的 Word 与 Excel 一起拖垮。
        print("  导出跳过：本机没装 cairosvg，PDF 与 PNG 出不了。"
              "SVG 已生成，可直接用或在装有 cairosvg 的机器上重出（pip install cairosvg）。")
        return {"pdf": [], "png": [], "merged": None, "svg": list(svgs)}
    zh, la, ti = pick_font()
    pdfs, pngs = [], []
    for p in svgs:
        s = single_family(open(p, encoding="utf-8-sig").read(), zh, la, ti)
        base = os.path.splitext(os.path.basename(p))[0]
        pdf = os.path.join(outdir, base + ".pdf")
        png = os.path.join(outdir, base + ".png")
        cairosvg.svg2pdf(bytestring=s.encode(), write_to=pdf)
        cairosvg.svg2png(bytestring=s.encode(), write_to=png, dpi=dpi,
                         output_width=int(210 / 25.4 * dpi))
        pdfs.append(pdf); pngs.append(png)

    merged = None
    if len(pdfs) > 1:
        try:
            from pypdf import PdfWriter
            merged = os.path.join(outdir, "大事记简表.pdf")
            w = PdfWriter()
            for f in pdfs:
                w.append(f)
            w.write(merged); w.close()
        except ImportError:
            merged = None

    warn = ""
    if ti != "方正小标宋简体":
        warn = (f"\n        注意：本机没装方正小标宋简体，标题已用 {ti} 代替。"
                f"SVG 里写的仍是方正小标宋，在装有该字体的机器上打开或重出 PDF 即可。")
    if la != "Times New Roman":
        warn += f"\n        注意：本机没装 Times New Roman，英文数字已用 {la}（metric 兼容）代替。"
    print(f"  导出：正文 {zh}｜西文 {la}｜标题 {ti}｜PDF {len(pdfs)} 页"
          + ("，已合并为 大事记简表.pdf" if merged else "（未装 pypdf，按页分开）")
          + f"｜PNG {len(pngs)} 张 {dpi}dpi" + warn)
    return {"pdf": pdfs, "png": pngs, "merged": merged}


if __name__ == "__main__":
    if {"-h", "--help"} & set(__import__("sys").argv[1:]):   # 只打印用法、什么都不做（原来会把 --help 当成文件名）
        getattr(__import__("sys").stdout, "reconfigure", lambda **k: None)(encoding="utf-8")
        print((__doc__ or "").strip() or "用法见本模块的 SKILL.md")
        raise SystemExit(0)
    try:                                   # 常见输入错误（路径、JSON、编码）说人话，不甩堆栈
        __import__("_cli_errors").install()
    except ImportError:
        pass
    # Windows 中文系统的控制台默认 GBK：不固定成 UTF-8，外部 AI（按 UTF-8 读）看到的是
    # 乱码。真实运行记录里，时间轴大师就因此让模型摸索了一轮编码。写法与其余 skill 一致。
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
    outdir = sys.argv[-1]
    export(sys.argv[1:-1], outdir)
