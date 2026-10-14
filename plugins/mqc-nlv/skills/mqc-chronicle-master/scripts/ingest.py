#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""摄入：按格式分派 → 文字型直读 / 扫描件栅格化待读图 → 产出材料清单与源文本。
判据取自时间轴大师 ADR 0001：PDF 的探测按逐页可读字符数，不看 pdffonts 有没有字体。
扫描件不引 OCR，栅格化后由模型逐页读图写转写稿，转写稿作为材料进管线，
全套锚定判据（B3 子序列核验、I1 完备性对账）原封不动生效。零第三方依赖。
"""
import os, re, json, subprocess, sys, zipfile
import shutil

PDF   = (".pdf",)
IMAGE = (".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp", ".heic")
DOCX  = (".docx",)
DOC   = (".doc",)          # 老式 Word：法院与律所往来里仍常见，见 read_doc.py
PLAIN = (".txt", ".md", ".text")
THIN_TEXT = 120               # 文字型材料低于此字数即提示，不阻断


class UnknownFormat(Exception):
    """I5 认不出的格式必须显式报错，不得静默归入扫描件那条路。

    早先只会处理 PDF：非 PDF 文件 pdfinfo 取不到页数 → 页数 0 → 无页可读 →
    判为 scanned → 栅格化产不出图 → 模型什么也读不到。而完备性对账的
    declared 按页数求和，一份被判成 0 页的材料不产生任何未读页，对账在材料
    已经丢掉的情况下报平。律师传了 docx 起诉状与手机拍的照片，两样都被静默
    丢掉且没有任何提示——这是摄入层最危险的一种失败。
    """


_TOOL_CACHE = {}


def _find_tool(name):
    """在 PATH 上找，找不到就查 Windows 的常见安装位置。

    Windows 装 poppler、Node、Inkscape、LibreOffice 默认都不写 PATH，而 shutil.which
    只看 PATH。真实运行记录里，用户机器上装了 Inkscape 却被报「找不到转换工具」，
    Node 也在同一台机器上没被用上。找不到时返回原名，让原来的报错照旧出现。"""
    if name in _TOOL_CACHE:
        return _TOOL_CACHE[name]
    found = shutil.which(name)
    if not found and os.name == "nt":
        rel = {"pdftotext": [("poppler", "bin", "pdftotext.exe"), ("poppler", "Library", "bin", "pdftotext.exe")],
               "pdfinfo": [("poppler", "bin", "pdfinfo.exe"), ("poppler", "Library", "bin", "pdfinfo.exe")],
               "pdftoppm": [("poppler", "bin", "pdftoppm.exe"), ("poppler", "Library", "bin", "pdftoppm.exe")],
               "node": [("nodejs", "node.exe")],
               "inkscape": [("Inkscape", "bin", "inkscape.exe"), ("Inkscape", "inkscape.exe")],
               "rsvg-convert": [r"rsvg-convert.exe"],
               "soffice": [("LibreOffice", "program", "soffice.exe")]}.get(name, [])
        for root in [os.environ.get(v) for v in ("ProgramFiles", "ProgramFiles(x86)",
                                                 "LOCALAPPDATA")]:
            if not root:
                continue
            for tail in rel:
                cand = os.path.join(root, *tail)
                if os.path.exists(cand):
                    found = cand
                    break
            if found:
                break
    _TOOL_CACHE[name] = found or name
    return _TOOL_CACHE[name]


def _run(cmd):
    # poppler 的 pdftotext / pdfinfo 输出 UTF-8。不指定编码时按系统区域设置解码，
    # 中文 Windows 上是 GBK：中文要么乱码、要么解码报错，文字层整份读坏。
    cmd = [_find_tool(cmd[0])] + list(cmd[1:])
    return subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


PAGE_MARKER = re.compile(r'-\s*\d{1,4}\s*-')   # 「- 12 -」这类页脚，计数前先剥掉


def kind_of(path):
    e = os.path.splitext(path)[1].lower()
    for exts, k in ((PDF, "pdf"), (IMAGE, "image"), (DOCX, "docx"), (DOC, "doc"),
                    (PLAIN, "plain")):
        if e in exts:
            return k
    raise UnknownFormat(
        f"认不出的材料格式：{os.path.basename(path)}（扩展名 {e or '无'}）。"
        f"支持 PDF／图片／docx／doc／纯文本；请先转换，不要让它静默漏掉。")


def read_docx(path):
    """零依赖抽正文：按段落取 w:t，丢掉样式与修订标记。表格单元格同样落在 w:t 里。"""
    x = zipfile.ZipFile(path).read("word/document.xml").decode("utf-8", "ignore")
    out = []
    for p in re.split(r"</w:p>", x):
        t = "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", p))
        if t.strip():
            out.append(t)
    return "\n".join(out)


def probe(path):
    """逐页量可读字符。返回 verdict: text_layer | scanned | mixed
    计数前剥掉页码标记：只印着页码的尾页是空白页，不是不可读页（实测判决书第20页仅 4 字符）。"""
    r = _run(["pdfinfo", path])
    m = re.search(r"Pages:\s+(\d+)", r.stdout)
    n = int(m.group(1)) if m else 0
    per = []
    for p in range(1, n + 1):
        t = _run(["pdftotext", "-f", str(p), "-l", str(p), path, "-"]).stdout
        per.append(len("".join(PAGE_MARKER.sub("", t).split())))
    blank = [i for i, c in enumerate(per) if c == 0 and _page_has_no_image(path, i + 1)]
    live = [c for i, c in enumerate(per) if i not in blank]
    readable = sum(1 for c in live if c > 20)
    verdict = ("text_layer" if live and readable == len(live)
               else ("scanned" if readable == 0 else "mixed"))
    return {"pages": n, "chars_per_page": per, "blank_pages": [i + 1 for i in blank],
            "readable_pages": readable, "live_pages": len(live), "verdict": verdict}


def _page_has_no_image(path, p):
    r = _run(["pdfimages", "-list", "-f", str(p), "-l", str(p), path])
    return len([l for l in r.stdout.splitlines()[2:] if l.strip()]) == 0


def rasterize(path, outdir, dpi=150):
    os.makedirs(outdir, exist_ok=True)
    _run(["pdftoppm", "-jpeg", "-r", str(dpi), path, os.path.join(outdir, "p")])
    return sorted(f for f in os.listdir(outdir) if f.endswith(".jpg"))


def read_text(path):
    return _run(["pdftotext", "-layout", path, "-"]).stdout


# ---- 纯文本材料的编码（0.9.8 自检：中文 Windows 的记事本默认存 GBK）--------------------------
# 原来按 UTF-8 读、errors="ignore"：GBK 的判决书被悄悄读成乱码（「ԭ׹˾뱻ҹ˾…」），还当作已读。
# 现在：UTF-8（带不带 BOM）读得通就用；读不通再按 GBK（GB18030）读，且读出来的汉字六成以上是常用字才认
# （真 GBK 的判决书实测九成以上；Big5 繁体、乱码都过不了）；否则拒，请用户另存为 UTF-8。宁可停下，不可把乱码当原文。
_COMMON_HANZI = None


def _common_hanzi():
    global _COMMON_HANZI
    if _COMMON_HANZI is None:                       # GB2312 一级字（3755 个常用字）
        s = set()
        for hi in range(0xB0, 0xD8):
            for lo in range(0xA1, 0xFF):
                try:
                    s.add(bytes((hi, lo)).decode("gb2312"))
                except UnicodeDecodeError:
                    pass
        _COMMON_HANZI = s
    return _COMMON_HANZI


def read_plain(path):
    """读一份纯文本材料，返回 (正文, 编码说明)。编码说明为 None 表示就是 UTF-8。"""
    raw = open(path, "rb").read()
    try:
        return raw.decode("utf-8-sig"), None
    except UnicodeDecodeError:
        pass
    try:
        txt = raw.decode("gb18030")
    except UnicodeDecodeError:
        txt = None
    if txt is not None:
        han = [c for c in txt if "\u4e00" <= c <= "\u9fff"]
        common = _common_hanzi()
        if han and sum(c in common for c in han) / len(han) >= 0.6:   # 真 GBK 的判决书实测九成以上是常用字
            return txt, "GBK"
    raise ValueError(f"{os.path.basename(path)} 不是 UTF-8，也认不准是哪种中文编码：请用记事本「另存为」，"
                     f"编码选 UTF-8，再给我一次")


def ingest(paths, workdir):
    """返回 (materials, sources, todo)。todo 列出还需要模型读图的材料。
    先按格式分派：只有 PDF 走探测那条路；图片本身就是图，不必再栅格化；
    docx 与纯文本直接抽字，抽不出正文即报错，不得当作已读。"""
    os.makedirs(workdir, exist_ok=True)
    materials, sources, todo = [], {}, []
    for i, p in enumerate(paths, 1):
        mid = f"M{i:02d}"
        k = kind_of(p)
        item = {"mid": mid, "name": os.path.basename(p), "kind": k,
                "submitted_by": None, "evidence_prefix": None}
        if k == "image":
            item.update(pages=1, medium="image", verdict="image", rasterized=[p])
            todo.append({"mid": mid, "name": item["name"], "pages": 1,
                         "images": [p], "est_tokens": 1600})
        elif k == "doc":
            import read_doc
            try:
                txt = read_doc.read_doc(p)
            except read_doc.DocReadError as e:
                raise SystemExit(f"{e}：{p}\n  用 Word 另存为 .docx，或 "
                                 f"soffice --headless --convert-to docx \"{p}\"")
        elif k in ("docx", "plain"):
            if k == "docx":
                txt = read_docx(p)
            else:
                try:
                    txt, enc_note = read_plain(p)
                except ValueError as e:
                    raise UnknownFormat(str(e))
                if enc_note:
                    item["encoding"] = enc_note
                    print(f"  提示：{item['name']} 是 {enc_note} 编码（记事本默认），已按 {enc_note} 读入")
            if not txt.strip():
                raise UnknownFormat(f"{item['name']} 抽不出任何正文，不得当作已读")
            item.update(pages=max(1, len(txt) // 1500), medium="text",
                        verdict="text_layer", chars=len(txt))
            sources[mid] = txt
        else:
            pr = probe(p)
            if pr["pages"] == 0:
                raise UnknownFormat(f"{item['name']} 探测出 0 页，文件可能损坏或不是 PDF")
            item.update(pages=pr["pages"], verdict=pr["verdict"],
                        medium="text" if pr["verdict"] == "text_layer" else "image")
            if pr["verdict"] == "text_layer":
                sources[mid] = read_text(p)
                item["chars"] = len(sources[mid])
            else:
                d = os.path.join(workdir, mid)
                imgs = rasterize(p, d)
                item["rasterized"] = [os.path.join(d, f) for f in imgs]
                todo.append({"mid": mid, "name": item["name"], "pages": pr["pages"],
                             "images": item["rasterized"],
                             "est_tokens": pr["pages"] * 1600})   # 只报成本，读不读由律师定
        materials.append(item)
    return materials, sources, todo


def reconcile(materials, sources, external_anchor, read_images=(), waived=()):
    """完备性对账。扫描件那条路上句数对账会变成自证，外部锚是唯一把手。
    份数与页数两轨都要平：只按页数求和时，一份被判成 0 页的材料不产生任何
    未读页，对账会在材料已经丢掉的情况下报平（见 UnknownFormat）。
    read_images 传模型确实读完并写出转写稿的那些 mid。
    waived 传律师明示不读的那些 mid（对照用的判决书、与争点无关的附件）。
    三态分开：已读 / 明示不读 / 该读没读。只有第三态才拒绝出图——
    材料不全是庭前常态，材料丢了才是事故，两者混在一起等于绝大多数案子都跑不了。"""
    done = set(sources) | set(read_images); skip = set(waived)
    declared = sum(m["pages"] for m in materials)
    read = sum(m["pages"] for m in materials if m["mid"] in done)
    missing = [m["mid"] for m in materials
               if m["mid"] not in done and m["mid"] not in skip or
                  (m["pages"] == 0 and m["mid"] not in skip)]
    waived_pages = sum(m["pages"] for m in materials if m["mid"] in skip)
    return {"pages_declared": declared, "pages_read": read,
            "unreadable": declared - read - waived_pages,
            "materials_declared": len(materials), "materials_read": len(done),
            "waived": sorted(skip), "waived_pages": waived_pages,
            "pending_materials": missing,
            "unreadable_materials": missing, "external_anchor": external_anchor}


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
    paths = sys.argv[1:-1]; work = sys.argv[-1]
    try:
        mats, srcs, todo = ingest(paths, work)
    except UnknownFormat as e:
        print(f"  拒绝摄入：{e}"); sys.exit(1)
    json.dump(mats, open(os.path.join(work, "materials.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    json.dump(srcs, open(os.path.join(work, "sources.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    json.dump(todo, open(os.path.join(work, "todo_read_image.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    for m in mats:
        thin = ""
        if m.get("chars") is not None and m["chars"] < THIN_TEXT:
            # 抽得出字就判已读、对账就报平，可正文只有几十个字时材料其实是空的：
            # 实测一份「证据目录及证据」的 docx 只有表头与空表格，正文 85 字。
            thin = f'　← 正文仅 {m["chars"]} 字，请确认是否为空表或含图材料'
        print(f'  {m["mid"]}  {m["kind"]:<6}{m["verdict"]:<11}{m["pages"]:>4}页  {m["name"]}{thin}')
    # 对账在这里就报出来：先前 reconcile 只有定义没有调用方，
    # 摄入阶段看不到平不平，要等到出表时才被 pipeline 拦下
    rec = reconcile(mats, srcs, external_anchor=None)
    print(f'\n  对账：材料 {rec["materials_declared"]} 份、声明 {rec["pages_declared"]} 页；'
          f'已读 {rec["materials_read"]} 份、{rec["pages_read"]} 页')
    if rec["unreadable_materials"]:
        print(f'  尚未读到的材料：{rec["unreadable_materials"]}'
              f'（读图完成前对账不平，不得出表）')
    if todo:
        tot = sum(t["est_tokens"] for t in todo)
        print(f'\n  需读图 {len(todo)} 份、{sum(t["pages"] for t in todo)} 页，预估约 {tot:,} token')
        print("  读不读全部由律师定，代码不替他挑页（ADR 0001）")
