#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""大事记表大师 · 执行管线
黄金律：模型读懂意思，代码算和验。模型只在第二步出 JSON，其余全部确定性。

  1 摄入   ingest.py          探测 → 文字型直读 / 扫描件栅格化
  2 抽取   （模型）           照 references/extraction.md 的 A-E 出事实行
  3 校验   check_facts.py     任何一条判据不成立即拒绝出表
  4 渲染   to_render.py       底稿 → Word 交付版 + Excel 母表
  5 自检   交付物自检          列宽、字体、对齐、备注上限
"""
import json, os, shutil, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

def step(n, name): print(f"\n[{n}] {name}")

def _preflight(need):
    """开跑前先查第三方库，缺了就一句话说清，不要跑到一半才抛异常。

    真实环境里撞到过：3.11 环境没装 openpyxl，整条流程走到第 4 步「渲染」才崩，
    前面的抽取与校验白跑，报错还是一串 traceback，看不出该装什么。"""
    import importlib.util
    missing = [(m, why) for m, why in need if importlib.util.find_spec(m) is None]
    if missing:
        print("缺少必需的第三方库，先装上再跑：")
        for m, why in missing:
            print(f"  {m}（{why}）    pip install {m}")
        return False
    return True


def _find_node():
    """Windows 装 Node 默认不写 PATH，which 找不到时查常见位置。"""
    if os.name != "nt":
        return None
    for root in [os.environ.get(v) for v in ("ProgramFiles", "ProgramFiles(x86)",
                                             "LOCALAPPDATA")]:
        cand = os.path.join(root, "nodejs", "node.exe") if root else ""
        if cand and os.path.exists(cand):
            return cand
    return None


def _rows_markdown(render_input, out_md):
    """Word 交付版的同内容 Markdown 表：列与 Word 同名同序，逐行照抄，不另行加工。"""
    d = json.load(open(render_input, encoding="utf-8"))
    esc = lambda x: str("" if x is None else x).replace("|", "｜").replace("\n", " ")
    note = lambda r: "；".join(str(x) for x in (r.get("note_parts") or []) if x)
    out = [f"# {d['case']['title']}　{d['case'].get('subtitle', '')}".rstrip(), "",
           "| 序号 | 日期 | 事项 | 主要内容 | 备注 |", "| --- | --- | --- | --- | --- |"]
    for i, r in enumerate(d.get("rows") or [], 1):
        out.append("| " + " | ".join([str(i), esc(r.get("date")), esc(r.get("item")),
                                      esc(r.get("content")), esc(note(r))]) + " |")
    ends = d.get("endnotes") or []
    if ends:
        out += ["", "## 尾注"] + [f"{i}. {esc(x)}" for i, x in enumerate(ends, 1)]
    open(out_md, "w", encoding="utf-8").write("\n".join(out) + "\n")
    return out_md


# 交付物菜单。默认三样：Word、Excel、简表 SVG —— 都不依赖转图工具，任何机器都出得来。
# 简表的 PDF 与 PNG 要 cairosvg（还要 cairo 本体），选了才出。
FORMAT_MENU = (("word", "Word 交付版", "案件大事记.docx（没有 Node 时改出同内容的 Markdown）"),
               ("excel", "Excel 母表", "案件大事记母表.xlsx，律师在里面填争点"),
               ("brief", "简表 SVG", "A4 呈报件，矢量，可直接插进材料"),
               ("pdf", "简表 PDF", "多页合并，要 cairosvg"),
               ("png", "简表 PNG", "位图预览，要 cairosvg"))
DEFAULT_FORMATS = ("word", "excel", "brief")


def parse_formats(ans):
    """把「1,2,4」「全部」「word,excel」或空，变成交付物元组。"""
    a = str(ans or "").strip().lower().replace("，", ",").replace("、", ",")
    keys = [k for k, _, _ in FORMAT_MENU]
    if not a:
        return DEFAULT_FORMATS
    if a in ("全部", "all", "所有"):
        return tuple(keys)
    sel = []
    for tok in [x.strip() for x in a.split(",") if x.strip()]:
        if tok.isdigit() and 1 <= int(tok) <= len(keys):
            sel.append(keys[int(tok) - 1])
        elif tok in keys:
            sel.append(tok)
    out = tuple(k for k in keys if k in sel)
    # PDF / PNG 是从简表 SVG 转的，选了它们就得有简表
    if ("pdf" in out or "png" in out) and "brief" not in out:
        out = tuple(k for k in keys if k in set(out) | {"brief"})
    return out or DEFAULT_FORMATS


def main(casefile, sources=None, outdir="out", formats=None):
    os.makedirs(outdir, exist_ok=True)
    cf = json.load(open(casefile, encoding="utf-8"))
    want = set(parse_formats(formats) if isinstance(formats, str) or formats is None
               else formats)
    print("交付物：" + "、".join(n for k, n, _ in FORMAT_MENU if k in want)
          + ("" if formats else "（默认；要别的就在命令行末尾加 1,2,4 或 全部）"))

    if "excel" in want and not _preflight([("openpyxl", "Excel 母表")]):
        return 2
    step(1, "摄入")
    mats = cf["materials"]; rec = cf["reconcile"]
    img = [m for m in mats if m.get("medium") == "image"]
    print(f"    材料 {len(mats)} 份，其中读图 {len(img)} 份")
    print(f"    对账：声明 {rec['pages_declared']} 页，读 {rec['pages_read']} 页，"
          f"未读 {rec['unreadable']} 页；外部锚：{rec['external_anchor']}")
    if rec["unreadable"]:
        print("    拒绝出表：有未读页，完备性对账不平"); return 1

    step(2, "抽取（模型已完成，本步只清点）")
    print(f"    事实 {len(cf['facts'])} 条，主体 {len(cf['parties'])} 个，"
          f"不确定 {len(cf.get('uncertainties', []))} 条")

    step(3, "校验")
    sys.path.insert(0, HERE)
    from check_facts import check
    src = json.load(open(sources, encoding="utf-8")) if sources else None
    if not src: print("    未提供源文本，B3 子序列核验跳过（扫描件须先出转写稿）")
    r = check(cf, src)
    if r.dump(): return 1

    step(4, "渲染（Word 交付版与 Excel 母表）")
    # 产出目录是律师直接打开的，文件名一律中文：他看到的是「案件大事记」，
    # 不是 chronicle.docx 这种。中间件也一样，混一个英文名在里面就显得是半成品。
    ri  = os.path.join(outdir, "渲染输入.json")
    raw = os.path.join(outdir, "案件大事记-未后处理.docx")
    doc = os.path.join(outdir, "案件大事记.docx")
    xls = os.path.join(outdir, "案件大事记母表.xlsx")
    S = lambda *a: subprocess.run(list(a), check=True)
    S(sys.executable, os.path.join(HERE, "to_render.py"), casefile, ri)
    # Word 交付版要 node 与它的 docx 模块。真实环境里这一步崩过（本机 Node 报错），
    # 原来 check=True 会让整条流程连 Excel 与简表一起失败，律师什么也拿不到。
    # 现在：node 不可用就跳过 Word，改出同内容的 Markdown 版并明说原因，其余照出。
    node = (shutil.which("node") or _find_node()) if "word" in want else None
    docx_ok = "word" not in want          # 没选 Word 就不必去找 node，也不报缺
    if "word" in want and node and subprocess.run([node, os.path.join(HERE, "build_docx.js"),
                                                   ri, raw]).returncode == 0 \
            and os.path.exists(raw):
        S(sys.executable, os.path.join(HERE, "postprocess_docx.py"), raw, doc)
        os.remove(raw)
        docx_ok = True
    if not docx_ok and "word" in want:
        md = _rows_markdown(ri, os.path.join(outdir, "案件大事记.md"))
        why = "node 不可用" if not node else "node 导出失败"
        print(f"  Word 交付版没写成（{why}）——已改出 Markdown 版 {os.path.basename(md)}，"
              f"内容相同；Excel 母表与简表照常生成。装好 Node.js 后重跑即可拿到 Word 版。")
    if "excel" in want:
        S(sys.executable, os.path.join(HERE, "build_xlsx.py"), ri, xls)
        S(sys.executable, os.path.join(HERE, "cache_formulas.py"), xls)

    step(5, "简表（呈报用）")
    sys.path.insert(0, HERE)
    from build_brief import build as build_brief
    from export_brief import export as export_brief
    svgs = build_brief(ri, outdir) if "brief" in want else []
    ex = (export_brief(svgs, outdir) if svgs and ("pdf" in want or "png" in want)
          else {"merged": None, "pdf": []})

    step(6, "交付物自检")
    r = subprocess.run([sys.executable,
                        os.path.join(ROOT, "tests", "check_deliverables.py"), doc, xls, ri])
    if r.returncode: print("    拒绝交付：交付物自检未通过"); return 1
    r = subprocess.run([sys.executable,
                        os.path.join(ROOT, "tests", "brief_checks.py"), ri])
    if r.returncode: print("    拒绝交付：简表自检未通过"); return 1

    brief = (ex.get("merged") or (ex["pdf"][0] if ex.get("pdf") else None)
             or (svgs[0] if svgs else "（无事实，未出简表）"))
    print(f"\n完成：{doc}\n      {xls}\n      {ri}\n      {brief}")
    print("核对清单（核对以此为准，不必查看图片）：交付物自检与简表自检见上，"
          "事项条数、字体三槽、页码与红色用法都已逐项判过。")
    return 0

if __name__ == "__main__":
    # Windows 中文系统的控制台默认 GBK：不固定成 UTF-8，外部 AI（按 UTF-8 读）看到的是
    # 乱码。真实运行记录里，时间轴大师就因此让模型摸索了一轮编码。写法与其余 skill 一致。
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
    a = sys.argv[1:]
    sys.exit(main(a[0], a[1] if len(a) > 1 else None, a[2] if len(a) > 2 else "out",
                  a[3] if len(a) > 3 else None))
