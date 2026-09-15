#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""摄入：按格式分派 → 文字型直读 / 扫描件栅格化待读图 → 产出材料清单与源文本。
判据取自时间轴大师 ADR 0001：PDF 的探测按逐页可读字符数，不看 pdffonts 有没有字体。
扫描件不引 OCR，栅格化后由模型逐页读图写转写稿（ADR 0002），转写稿作为材料进管线，
全套锚定判据（子序列核验、完备性对账）原封不动生效。零第三方依赖。
"""
import os, re, json, subprocess, sys, zipfile

PDF   = (".pdf",)
IMAGE = (".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp", ".heic")
DOCX  = (".docx",)
PLAIN = (".txt", ".md", ".text")


class UnknownFormat(Exception):
    """I5 认不出的格式必须显式报错，不得静默归入扫描件那条路。

    早先只会处理 PDF：非 PDF 文件 pdfinfo 取不到页数 → 页数 0 → 无页可读 →
    判为 scanned → 栅格化产不出图 → 模型什么也读不到。而完备性对账的
    declared 按页数求和，一份被判成 0 页的材料不产生任何未读页，对账在材料
    已经丢掉的情况下报平。律师传了 docx 起诉状与手机拍的照片，两样都被静默
    丢掉且没有任何提示——这是摄入层最危险的一种失败。
    """


def _run(cmd):
    # poppler 的 pdftotext / pdfinfo 输出 UTF-8。不指定编码时按系统区域设置解码，
    # 中文 Windows 上是 GBK：中文要么乱码、要么解码报错，文字层整份读坏。
    return subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


PAGE_MARKER = re.compile(r'-\s*\d{1,4}\s*-')   # 「- 12 -」这类页脚，计数前先剥掉


def kind_of(path):
    e = os.path.splitext(path)[1].lower()
    for exts, k in ((PDF, "pdf"), (IMAGE, "image"), (DOCX, "docx"), (PLAIN, "plain")):
        if e in exts:
            return k
    raise UnknownFormat(
        f"认不出的材料格式：{os.path.basename(path)}（扩展名 {e or '无'}）。"
        f"支持 PDF／图片／docx／纯文本；请先转换，不要让它静默漏掉。")


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
        elif k in ("docx", "plain"):
            txt = (read_docx(p) if k == "docx"
                   else open(p, encoding="utf-8", errors="ignore").read())
            if not txt.strip():
                raise UnknownFormat(f"{item['name']} 抽不出任何正文，不得当作已读")
            item.update(pages=max(1, len(txt) // 1500), medium="text", verdict="text_layer")
            sources[mid] = txt
        else:
            pr = probe(p)
            if pr["pages"] == 0:
                raise UnknownFormat(f"{item['name']} 探测出 0 页，文件可能损坏或不是 PDF")
            item.update(pages=pr["pages"], verdict=pr["verdict"],
                        medium="text" if pr["verdict"] == "text_layer" else "image")
            if pr["verdict"] == "text_layer":
                sources[mid] = read_text(p)
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
    paths = sys.argv[1:-1]
    work = sys.argv[-1]
    try:
        mats, srcs, todo = ingest(paths, work)
    except UnknownFormat as e:
        print(f"  拒绝摄入：{e}")
        sys.exit(1)
    json.dump(mats, open(os.path.join(work, "materials.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    json.dump(srcs, open(os.path.join(work, "sources.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    json.dump(todo, open(os.path.join(work, "todo_read_image.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    for m in mats:
        print(f'  {m["mid"]}  {m["kind"]:<6}{m["verdict"]:<11}{m["pages"]:>4}页  {m["name"]}')
    rec = reconcile(mats, srcs, external_anchor=None)
    print(f'\n  对账：材料 {rec["materials_declared"]} 份、声明 {rec["pages_declared"]} 页；'
          f'已读 {rec["materials_read"]} 份、{rec["pages_read"]} 页')
    if rec["unreadable_materials"]:
        print(f'  尚未读到的材料：{rec["unreadable_materials"]}（读图完成前对账不平，不得出图）')
    if todo:
        tot = sum(t["est_tokens"] for t in todo)
        print(f'  需读图 {len(todo)} 份、{sum(t["pages"] for t in todo)} 页，预估约 {tot:,} token')
        print("  读不读全部由律师定，代码不替他挑页（ADR 0001）")
