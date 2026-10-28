#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""庭审对抗图大师 · 执行管线
  1 摄入     ingest.py         探测 → 文字型直读 / 扫描件栅格化待读图
  2 推演     （模型）按九步法填 case.json，三标随行 —— 唯一一步由模型做
  3 前端校验  check_claims.py   诉请固定（J）与抗辩归类（K）
  4 出表     build_matrix.py   → 庭审对抗分析表.xlsx
  5 出图     to_figure.py → render_main.py  → SVG（图从表派生）
  6 光栅     rasterize.py      → PNG（换单一字族，避开静默的字体回退）
  7 自检     cross_check.py 图表一致 + check_figure.py 图几何
一份输入同时喂表与图；缺顶层 title/subtitle 时渲染器回落到 case 段。

用法：
  python3 pipeline.py <case.json> [输出目录] [交付物]   交付物：1=Excel 2=SVG 3=PNG，可写 1,2,3 或 全部；默认 Excel+SVG
  python3 pipeline.py --demo [输出目录]                 用随包示例跑一遍（默认写到 ./庭审对抗图-示例）
  python3 pipeline.py --check                           只查本机环境：出表、出图、出 PNG 各缺什么
"""
import json, os, subprocess, sys
HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.dirname(HERE)

def step(n,name): print(f"\n[{n}] {name}")

def _preflight(need):
    """开跑前先查第三方库，缺了就一句话说清，不要跑到一半才抛异常。

    真实环境里撞到过：环境缺库时，整条流程走到出表那一步才崩，前面的校验白跑，
    报错还是一串 traceback，看不出该装什么。"""
    import importlib.util
    missing = [(m, why) for m, why in need if importlib.util.find_spec(m) is None]
    if missing:
        print("缺少必需的第三方库，先装上再跑：")
        for m, why in missing:
            print(f"  {m}（{why}）    pip install {m}")
        return False
    return True


# 交付物菜单。默认 Excel + SVG：两者不依赖转图工具，任何机器都出得来；
# PNG 要本机能把 SVG 转成位图（真实运行里这一步最常卡住），选了才出。
FORMAT_MENU = (("excel", "分析表 Excel", "庭审对抗分析表.xlsx，逐项可改"),
               ("svg", "对抗图 SVG", "主交付物，矢量可编辑"),
               ("png", "对抗图 PNG", "位图预览，要本机有转图工具"))
DEFAULT_FORMATS = ("excel", "svg")


def parse_formats(ans):
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
    if "png" in out and "svg" not in out:      # PNG 从 SVG 转，必须先有 SVG
        out = tuple(k for k in keys if k in set(out) | {"svg"})
    return out or DEFAULT_FORMATS


# 出表、出图要读的字段。缺了原来跑到出表那一步才甩 KeyError 堆栈，前面的校验白跑；
# 现在开跑前一次查完，逐条说「哪一条、少了什么、照哪份骨架补」。
_ELEMENT_KEYS = ("id", "name", "layer", "kind", "burden", "standard", "dispute", "facts",
                 "claim", "response", "response_class", "counter", "second", "second_class",
                 "st_plaintiff", "st_defendant", "st_replik", "st_duplik", "gap", "self_defeat",
                 "triage", "issue_kind", "evidence", "prospect", "decisive", "conf_law", "conf_evid",
                 "source", "todo", "figure_ref", "court_standard")
_GUIDE = "references/casefile-guide.md 第 4 节「可粘贴骨架」"


def check_shape(D):
    """输入的骨架对不对：返回问题清单（空表示可以往下跑）。只查有没有、是不是那种类型，不查内容。"""
    if not isinstance(D, dict):
        return [f"输入最外层应是一个对象（{{…}}），实为{type(D).__name__}。照 {_GUIDE} 起头"]
    errs = []
    case = D.get("case")
    if not isinstance(case, dict):
        errs.append("缺 case 段（案件名、初步研判、立场都写在这里）")
    else:
        for k, what in (("title", "案件名（图与表的大标题）"), ("triage", "初步研判（两三句收束）")):
            if not str(case.get(k) or "").strip():
                errs.append(f"case.{k} 没写：{what}")
    parts = D.get("parts")
    if not isinstance(parts, list) or not parts:
        errs.append("缺 parts（对抗部分）或它是空的：至少要有一个争点板块")
        return errs
    for i, part in enumerate(parts, 1):
        where = f"第 {i} 个对抗部分"
        if not isinstance(part, dict):
            errs.append(f"{where}应是一个对象"); continue
        where = f"{where}（{part.get('label') or '未写 label'}）"
        for k in ("label", "track", "summary"):
            if k not in part:
                errs.append(f"{where}缺 {k}")
        cbs = part.get("claim_bases")
        if not isinstance(cbs, list) or not cbs:
            errs.append(f"{where}缺 claim_bases（请求权基础）或它是空的"); continue
        for j, cb in enumerate(cbs, 1):
            els = cb.get("elements") if isinstance(cb, dict) else None
            if not isinstance(els, list) or not els:
                errs.append(f"{where}第 {j} 条请求权基础缺 elements（构成要件）或它是空的"); continue
            for k, e in enumerate(els, 1):
                if not isinstance(e, dict):
                    errs.append(f"{where}第 {k} 条要件应是一个对象"); continue
                miss = [x for x in _ELEMENT_KEYS if x not in e]
                if miss:
                    errs.append(f"要件 {e.get('id') or where + '第%d条' % k} 缺字段：{'、'.join(miss)}"
                                "（没有内容的段填「—」，不要删字段）")
    return errs


def _run(no, name, *cmd):
    """跑一步子脚本；失败时一句话说清是哪一步，原因就在上面几行（不甩 CalledProcessError 堆栈）。"""
    r = subprocess.run(list(cmd))
    if r.returncode:
        print(f"    第 {no} 步「{name}」没跑通：原因见上面几行。改好输入后重跑同一条命令即可。")
    return r.returncode


def env_check():
    """只查环境，不出图：出表、出图、出 PNG 各自缺什么，缺了会怎样。"""
    import importlib.util as u
    has = lambda m: u.find_spec(m) is not None
    print(f"Python {sys.version.split()[0]}")
    print(f"  出图 SVG    可用（只用标准库）")
    print(f"  分析表 Excel {'可用' if has('openpyxl') else '缺 openpyxl：pip install openpyxl（只要图可在命令末尾写 2）'}")
    png_libs = [m for m in ("PIL", "numpy") if not has(m)]
    sys.path.insert(0, HERE)
    try:
        import rasterize as _r
        tools = ["cairosvg"] if getattr(_r, "cairosvg", None) else []
        tools += [t for t in ("rsvg-convert", "inkscape") if _r._find_tool(t)]
        if _r._find_tool("soffice") and _r._find_tool("pdftoppm"):
            tools.append("LibreOffice")
    except ImportError:
        tools = []
    if png_libs:
        print(f"  对抗图 PNG  可选；缺 {'、'.join('Pillow' if m == 'PIL' else m for m in png_libs)}："
              f"pip install pillow numpy。不影响 Excel 与 SVG")
    elif tools:
        print(f"  对抗图 PNG  可用（{'、'.join(tools)}）")
    else:
        print("  对抗图 PNG  可选；本机暂未找到转图工具（cairosvg / Inkscape / LibreOffice / resvg-js / Playwright 任一即可），"
              "不影响 Excel 与 SVG")
    return 0


def main(case, outdir="out", formats=None):
    if "excel" in set(parse_formats(formats)) and not _preflight([("openpyxl", "分析表 Excel")]):
        return 2
    D=json.load(open(case,encoding="utf-8-sig"))
    bad = check_shape(D)
    if bad:
        print(f"输入的骨架不全，先补上再跑（共 {len(bad)} 处）：")
        for b in bad[:20]:
            print(f"  · {b}")
        if len(bad) > 20:
            print(f"  ……另有 {len(bad) - 20} 处，补完前面的再跑一次就能看到")
        print(f"照着补：{_GUIDE}；完整示例见 examples/matrix-input.json")
        return 1
    os.makedirs(outdir, exist_ok=True)

    step(1,"摄入")
    mats=D.get("materials")
    if mats:
        img=[m for m in mats if m.get("medium")=="image"]
        print(f"    材料 {len(mats)} 份，其中读图 {len(img)} 份")
        rec=D.get("reconcile")
        if rec:
            print(f"    对账：声明 {rec['pages_declared']} 页，读 {rec['pages_read']} 页，未读 {rec['unreadable']} 页")
            miss=rec.get("pending_materials") or rec.get("unreadable_materials") or []
            if rec.get("waived"):
                print(f"    律师明示不读：{rec['waived']}（{rec.get('waived_pages',0)} 页，不进推演）")
            if rec["unreadable"] or miss:
                print(f"    拒绝出图：完备性对账不平（未读页 {rec['unreadable']}，"
                      f"待读材料 {miss}）。材料本来就没有的，写进 scope.not_obtained；"
                      f"有但决定不读的，写进 waived——不许把它当成已读。"); return 1
    else:
        print("    本输入未带材料清单（材料由 scripts/ingest.py 先行处理）")

    step(2,"推演（模型已完成，本步只清点）")
    ne=sum(len(cb["elements"]) for p in D["parts"] for cb in p["claim_bases"])
    print(f"    对抗部分 {len(D['parts'])} 个，构成要件 {ne} 条，诉请 {len(D.get('claims',[]))} 项")

    step(3,"前端校验")
    if subprocess.run([sys.executable, os.path.join(HERE,"check_claims.py"), case]).returncode:
        print("    拒绝出表：诉请固定或抗辩归类不合规"); return 1

    want = set(parse_formats(formats))
    print("交付物：" + "、".join(n for k, n, _ in FORMAT_MENU if k in want)
          + ("" if formats else "（默认；要别的就在命令行末尾加 1,2,3 或 全部）"))
    step(4,"出表")
    xls=os.path.join(outdir,"庭审对抗分析表.xlsx")
    if "excel" in want and _run(4, "出表", sys.executable, os.path.join(HERE,"build_matrix.py"), case, xls):
        return 1

    step(5,"出图")
    fig=os.path.join(outdir,"图输入.json")     # 产出目录里不留英文名
    if _run(5, "表→图", sys.executable, os.path.join(HERE,"to_figure.py"), case, fig):   # 表→图，表是唯一的源
        return 1
    svg=os.path.join(outdir,"庭审对抗图.svg")
    if _run(5, "出图", sys.executable, os.path.join(HERE,"render_main.py"), fig, svg):
        return 1

    step(6,"光栅")
    png=os.path.join(outdir,"庭审对抗图.png")
    png_skipped = False
    if "png" in want:
        # PNG 只是预览：转不出来时不连累 Excel 与 SVG，照常交付并说明 PNG 缺了什么
        if subprocess.run([sys.executable, os.path.join(HERE,"rasterize.py"), svg, png]).returncode:
            png_skipped = True
            print("    PNG 没出成（原因见上一行）。Excel 与 SVG 照常交付；"
                  "要 PNG 就按提示补上工具后重跑，或用 --check 看本机缺什么")
    else:
        print("    未选 PNG，跳过（要就在命令行末尾加 3 或 全部）")

    step(7,"自检")
    xc = os.path.join(os.path.dirname(HERE), "tests", "cross_check.py")
    if os.path.exists(xc) and subprocess.run([sys.executable, xc, case, svg]).returncode:
        print("    拒绝交付：图表一致性未通过"); return 1
    if subprocess.run([sys.executable, os.path.join(HERE,"check_figure.py"), svg]).returncode:
        print("    拒绝交付：图几何自检未通过"); return 1

    _made = [p for k, p in (("excel", xls), ("svg", svg), ("png", png))
             if k in want and os.path.exists(p)]
    print("\n完成：" + "\n      ".join(_made))
    if png_skipped:
        print("      （PNG 未出，见上文）")
    # 与其余 skill 一致：把结论用文字给出，模型不必再去转图、看图核对
    # （时间轴大师的真实运行里，读图工具显示不了 PNG 时模型反复转格式，白花五分钟）。
    print("核对清单（核对以此为准，不必查看图片）：图几何与图表一致两项自检见上；"
          "文字、三栏、深红处数都已逐项判过。")
    return 0

if __name__=="__main__":
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
    _a = sys.argv[1:]
    if not _a:
        print("用法：" + __doc__.split("用法：", 1)[1].rstrip())
        sys.exit(2)
    if _a[0] == "--check":
        sys.exit(env_check())
    if _a[0] == "--demo":
        _out = _a[1] if len(_a) > 1 else "庭审对抗图-示例"
        print(f"用随包示例跑一遍，产物写到 {os.path.abspath(_out)}")
        sys.exit(main(os.path.join(ROOT, "examples", "matrix-input.json"), _out, _a[2] if len(_a) > 2 else None))
    sys.exit(main(_a[0], _a[1] if len(_a)>1 else "out", _a[2] if len(_a)>2 else None))
