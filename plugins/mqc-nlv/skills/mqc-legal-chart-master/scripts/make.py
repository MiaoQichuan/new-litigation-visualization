#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""法律图表大师 · 出图入口。

用法：
  python3 scripts/make.py <说明.json> [-o out/图名] [--style 奇川风|歸藏风]
                          [--canvas slide|square|portrait|…|宽x高]
                          [--profile 律所档案] [--formats svg,pptx,png,module] [--fonts safe|master]
  （module：另写一份 <名>.module.json 模块清单，给 V7 法律课件大师收进课件）
  python3 scripts/make.py <说明.json> --plan   只出「出图计划」，不写文件：先给用户确认
  python3 scripts/make.py --check              环境自检

一条管线：读说明 → 校验并算派生数 → 渲染 → 守卫 → 导出。守卫不过就不交付（退出码 2）。
优先次序：命令行 > 说明 JSON > 律所档案（--profile）> 默认。
"""
import argparse
import os
import re
import sys
import tempfile

import kernel  # noqa: F401  挂上 V1 的路径
from spec import load, SpecError, CANVAS, CANVAS_ZH, MIN_CANVAS, CHART_ZH, _fmt, budget_used
from styles import palette, norm_style, firm_palette  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PROFILE_KEYS = {"name", "style", "accent", "canvas", "fonts", "note"}


def _slots():
    import module
    return module.SLOTS


def load_profile(name):
    """律所 / 客户档案（学自 diagram-design 的 named profiles）：把风格、强调色、画布、字体存成一份，
    一个律所做的所有图都用同一份。找的顺序：给的是路径就读路径；否则依次找
    ./.mqc-nlv/profiles/<名>.json、~/.mqc-nlv/profiles/<名>.json、本技能的 profiles/<名>.json。"""
    if not name:
        return {}
    cands = [name] if name.endswith(".json") else []
    cands += [os.path.join(".mqc-nlv", "profiles", name + ".json"),
              os.path.join(os.path.expanduser("~"), ".mqc-nlv", "profiles", name + ".json"),
              os.path.join(HERE, "..", "profiles", name + ".json")]
    for c in cands:
        if os.path.isfile(c):
            import json
            with open(c, encoding="utf-8-sig") as f:
                prof = json.load(f)
            extra = set(prof) - PROFILE_KEYS
            if extra:
                raise SpecError(f"档案 {c} 里有不认识的字段：{'、'.join(sorted(extra))}"
                                f"（只认 {'、'.join(sorted(PROFILE_KEYS))}）")
            return prof
    raise SpecError(f"找不到档案 {name!r}；放在 ~/.mqc-nlv/profiles/{name}.json，或直接给路径")
from charts import render
from guards import check


def resolve_canvas(c):
    c = c or "slide"
    if isinstance(c, dict):
        W, H = c.get("w"), c.get("h")
    elif isinstance(c, str) and c in CANVAS:
        W, H = CANVAS[c]
    elif isinstance(c, str) and c in _slots():
        W, H = _slots()[c]["w"], _slots()[c]["h"]          # V7 的版位名也认
    elif isinstance(c, str) and "x" in c:
        try:
            W, H = (float(v) for v in c.lower().split("x"))
        except ValueError:
            raise SpecError(f"画布写成「宽x高」（像素，96 dpi），收到 {c!r}")
    else:
        raise SpecError(f"未知画布 {c!r}；可选：{'、'.join(CANVAS)}，V7 版位 {'、'.join(_slots())}，或「宽x高」")
    if not isinstance(W, (int, float)) or not isinstance(H, (int, float)):
        raise SpecError("画布的 w、h 要是数字")
    if W < MIN_CANVAS[0] or H < MIN_CANVAS[1]:
        raise SpecError(f"画布 {W:.0f}×{H:.0f} 太小；最小 {MIN_CANVAS[0]}×{MIN_CANVAS[1]}")
    return float(W), float(H)


def build(spec_path_or_obj, style=None, accent=None, canvas=None, profile=None, firm=None):
    """说明 → (svg, 报告)。不写文件；测试与导出都走这里。守卫不过抛 SpecError。
    firm：律所风格（V7 的律所风格文件里的 name / base / accent），重音换成律所主色，其余按基础风格。"""
    m = load(spec_path_or_obj)
    prof = profile if isinstance(profile, dict) else load_profile(profile)
    style = norm_style(style or m.get("style") or prof.get("style"))
    if accent is None and "accent" in m:
        accent = m["accent"]
    # 说明里、命令行里明写的强调色：palette() 直接拒（不静默丢掉，外部评审 N18）。
    # 档案里留着的强调色（0.9.2 以前的档案）：档案是默认值，不是指令——不用，交付清单里说一声。
    prof_note = "档案里的强调色已停用（V6 只用风格原色）" if prof.get("accent") else None
    if firm:
        if accent:
            raise SpecError("律所风格与强调色不能同时给：律所风格里已有主色")
        try:
            pal, wl = firm_palette(dict(firm, base=firm.get("base") or style))
        except ValueError as e:
            raise SpecError(str(e))
        style = pal["style"]
    else:
        pal, wl = palette(style, accent)
    canvas_key = canvas or m.get("canvas") or prof.get("canvas")
    W, H = resolve_canvas(canvas_key)
    svg, chart, notes = render(m, W, H, pal)
    bad = check(svg, m, chart, pal, wl)
    rep = {"chart": chart, "style": style, "accent": pal["accent"], "accent_in": None, "firm": pal.get("firm"), "W": W, "H": H,
           "canvas": (canvas_key if isinstance(canvas_key, str) and canvas_key in CANVAS
                      else "slide" if canvas_key is None else None),
           "notes": notes, "warnings": m["_warnings"], "problems": bad, "spec": m,
           "profile": prof.get("name"), "profile_note": prof_note}
    return svg, rep


def checklist(rep, files):
    m = rep["spec"]
    lines = ["", "交付清单", "--------"]
    lines.append(f"图种　{CHART_ZH[rep['chart']]}" + (f"（{'；'.join(rep['notes'])}）" if rep["notes"] else ""))
    lines.append(f"风格　{rep['style']}（重音 {rep['accent']}）"
                 + (f" · 档案「{rep['profile']}」" if rep.get("profile") else "")
                 + (f"；{rep['profile_note']}" if rep.get("profile_note") else ""))
    lines.append(f"画布　{CANVAS_ZH.get(rep.get('canvas'), '自定')} {rep['W']:.0f} × {rep['H']:.0f} px"
                 f"（{rep['W'] / 96:.2f} × {rep['H'] / 96:.2f} 英寸）")
    lines.append(f"样本　n = {_fmt(m['n'])}" + ("，由 dataset 逐行数出" if m.get("_trace") is not None
                                                 else "，已与数据对账" if m["_derived"].get("n_computed") is not None
                                                 else "，按说明照录（这一种图无法由数据反算）"))
    t = m.get("_trace")
    if t is not None:
        dn = sum(len(d["rows"]) for d in t["dropped"])
        lines.append(f"数据　由 dataset 的 {t['rows']} 行按 view 算出：过滤掉 {t['filtered']} 行"
                     + (f"、缺字段不计 {dn} 行" if dn else "") + f"，计入 {t['kept']} 行；"
                     f"每一项来自哪几行写进 .trace.json（出图时）")
    emph = m.get("emphasis")
    lines.append(f"重音　{emph if emph is not None else '不标'}")
    for a in m.get("annotations") or []:
        lines.append(f"批注　{a['target']}：{a['text']}")
    used, lim, unit = budget_used(m)
    lines.append(f"预算　{used} / {lim} {unit}" + ("　接近上限：考虑拆成「总览 + 细节」两页，或合并长尾"
                                                   if used >= 0.7 * lim and lim >= 6 else ""))
    for w in rep["warnings"]:
        lines.append(f"请核　{w}")
    for f in files:
        lines.append(f"文件　{f}")
    return "\n".join(lines)


def plan(rep):
    """出图计划（学自 diagram-design 的「动笔前先确认」）：把要画什么、画多大、标哪里、
    哪些要人核，先给用户看一眼。改起来只是改一份 JSON，比交付后再返工便宜得多。"""
    out = checklist(rep, [])
    out = out.replace("交付清单", "出图计划（未写文件；确认后去掉 --plan 再跑）", 1)
    if rep["problems"]:
        out += "\n守卫　没过：" + "；".join(rep["problems"])
    else:
        out += "\n守卫　全过"
    return out


FORMATS = ("svg", "pptx", "png", "module")
REQUIRED = ("svg", "pptx", "module")         # 要了就必须做成；png 是可选的，缺转图工具时跳过并说明


def m_trace(rep):
    """用了 dataset / view 时的溯源（类目 → 行号与 ref），否则 None。"""
    t = rep["spec"].get("_trace")
    if t is None:
        return None
    return {"说明": "图上每一项来自 dataset.rows 的哪几行（行号从 0 数；refs 是 dataset.ref 指定那一列的值）",
            "chart": rep["chart"], "title": rep["spec"]["title"], **t}


def publish(svg, rep, base, fmts, a):
    """先在系统临时目录里把要的格式全做出来、回读检查，全部过了才一次性换到 base.*。
    必需的格式有一样失败，就什么都不写——不让「PPTX 审计失败被撤下、SVG 却留着、退出码还是 0」
    这种半成品被当成交付（外部评审 F12）。返回 (交付的文件, 失败说明, 提示)。

    临时目录放在系统临时目录、不放在用户的输出目录：有的环境禁止删除文件（第三轮测试里 WorkBuddy 的
    「安全删除」沙箱让 os.remove / rmtree 直接失败），清不掉的临时目录不能留在用户眼前。"""
    import shutil
    out_dir = os.path.dirname(os.path.abspath(base))
    os.makedirs(out_dir, exist_ok=True)
    name = os.path.basename(base)
    work = tempfile.mkdtemp(prefix="nlv-")
    made, failed, notes = [], [], []
    try:
        tmp = os.path.join(work, name)
        # newline="\n"：Windows 上文本模式会把换行写成 \r\n，同一张图在两个平台上字节就不一样了
        with open(tmp + ".svg", "w", encoding="utf-8", newline="\n") as f:
            f.write(svg)
        made.append(".svg")
        if "pptx" in fmts:
            try:
                import export_pptx
                prep = os.path.join(work, "deck.svg")
                ready, alpha = pptx_ready(svg)
                with open(prep, "w", encoding="utf-8", newline="\n") as f:
                    f.write(ready)
                export_pptx.export(prep, tmp + ".pptx", fonts=a.fonts or load_profile(a.profile).get("fonts") or "safe")
                apply_alpha(tmp + ".pptx", alpha)
                issues = export_pptx.audit_deck(tmp + ".pptx")
                if issues:
                    failed.append("PPTX 回读没过：" + "；".join(issues[:3]))
                else:
                    made.append(".pptx")
            except Exception as e:
                failed.append(f"PPTX 导出出错：{e}")
        if "png" in fmts:
            try:
                import render as v1render
                v1render.svg_to_png(tmp + ".svg", tmp + ".png")
                made.append(".png")
            except Exception as e:
                notes.append(f"PNG 未出（可选格式，其余照常交付）：{e}")
        if m_trace(rep) is not None:
            # 逐格溯源（0.9.8）：图上每一个柱、每一格、每一股流带来自 dataset 的哪几行。
            # 用了 dataset 就一定写——这是「数是脚本数的」可以被律师复核的凭据，与 SVG 同进退。
            try:
                import json
                with open(tmp + ".trace.json", "w", encoding="utf-8", newline="\n") as f:
                    json.dump(m_trace(rep), f, ensure_ascii=False, indent=1)
                made.append(".trace.json")
            except Exception as e:
                failed.append(f"溯源文件出错：{e}")
        if "module" in fmts and not failed:
            try:
                import json
                import module
                listed = [base + ext for ext in made]
                man = module.manifest(rep, listed, rep["spec"])
                with open(tmp + ".module.json", "w", encoding="utf-8", newline="\n") as f:
                    json.dump(man, f, ensure_ascii=False, indent=2)
                made.append(".module.json")
            except Exception as e:
                failed.append(f"模块清单出错：{e}")
        if failed:
            return [], failed, notes
        return _commit(work, tmp, base, made), [], notes
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _try_remove(path):
    try:
        os.remove(path)
        return True
    except OSError:
        return False


def _commit(work, tmp, base, made):
    """把做好的文件一次性换上去，**成功与回滚都不靠删除**。

    1. 先把每个新文件拷成输出目录里的隐藏暂存文件（.<名>.nlv-new），同目录才能原子替换；
    2. 旧文件的内容先读进内存；
    3. 逐个 os.replace（改名覆盖，不是删除）换上去；
    4. 中途哪一步失败（文件被 PowerPoint 占着、磁盘满）：已换上的，若原来有旧文件就把旧内容换回去，
       原来没有的才需要删——删不掉（环境禁止删除）就如实报出来，不假装回滚干净。
    第二轮测试 R2-060：0.9.0 第二个文件换失败时第一个新文件留下了；第三轮测试：0.9.1 的回滚靠 os.remove，
    在禁止删除的沙箱里同样会留下文件。"""
    import shutil
    out_dir = os.path.dirname(os.path.abspath(base))
    stem = os.path.basename(base)
    stage = {ext: os.path.join(out_dir, f".{stem}{ext}.nlv-new") for ext in made}
    old = {}
    for ext in made:
        if os.path.exists(base + ext):
            with open(base + ext, "rb") as f:
                old[ext] = f.read()
    placed = []
    try:
        for ext in made:                       # 拷一个换一个：失败时至多留下正在换的那一个暂存文件
            shutil.copyfile(tmp + ext, stage[ext])
            os.replace(stage[ext], base + ext)
            placed.append(ext)
        return [base + ext for ext in made]
    except Exception as e:
        stuck = []
        for ext in placed:
            if ext in old:
                back = stage[ext] + ".old"
                try:
                    with open(back, "wb") as f:
                        f.write(old[ext])
                    os.replace(back, base + ext)
                except OSError:
                    stuck.append(base + ext)
            elif not _try_remove(base + ext):
                stuck.append(base + ext)
        for ext in made:
            if os.path.exists(stage[ext]) and not _try_remove(stage[ext]):
                stuck.append(stage[ext])
        if stuck:
            raise OSError(f"{e}；回滚时这些文件删不掉（环境禁止删除？），请手动删除：{'、'.join(stuck)}") from e
        raise


def pptx_ready(svg):
    """交给 V1 导出器之前的规整。返回 (规整后的 SVG, 透明度表)。

    * 原本是矩形的 path（data-shape="rect"）还原成 <rect rx>，PowerPoint 里成为原生圆角矩形，
      拖动黄色控点还能调圆角；
    * 其余带贝塞尔曲线的 path 细分成折线——V1 的导出器只认直线段，交给它 C 命令会被读成弦；
    * 半透明的形状（汇入图的流带）：V1 的导出器不认 fill-opacity。这里先把它的填充色换成一个
      图上没有用过的「代号色」，导出后 apply_alpha() 再把代号色换回原色并写上透明度。
      这样不必改共享内核，PPTX 里流带照样叠得出深浅。
    SVG 交付物本身不动。"""
    from corners import flat_d
    used = {c.upper() for c in re.findall(r"#[0-9A-Fa-f]{6}", svg)}
    alpha = {}                        # 代号色 → (原色, 透明度)

    def sentinel(color, op):
        for k, (c0, o0) in alpha.items():
            if c0 == color and o0 == op:
                return k
        r, g, b = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
        for step in range(1, 256):
            cand = "#%02X%02X%02X" % (r, g, (b + step) % 256)
            if cand not in used and cand not in alpha:
                alpha[cand] = (color, op)
                return cand
        raise RuntimeError("找不到可用的代号色")

    def one(mt):
        tag = mt.group(0)
        attrs = dict(re.findall(r'([\w:-]+)="([^"]*)"', tag))
        if attrs.get("data-shape") == "rect":
            keep = " ".join(f'{k}="{v}"' for k, v in attrs.items() if k != "d")
            return (f'<rect x="{attrs["data-x"]}" y="{attrs["data-y"]}" width="{attrs["data-w"]}" '
                    f'height="{attrs["data-h"]}" rx="{attrs["data-r"]}" {keep}/>')
        if "fill-opacity" in attrs and attrs.get("fill", "none") != "none":
            sc = sentinel(attrs["fill"].upper(), float(attrs["fill-opacity"]))
            tag = tag.replace(f'fill="{attrs["fill"]}"', f'fill="{sc}"', 1)
        if "C" in attrs.get("d", ""):
            tag = tag.replace(f'd="{attrs["d"]}"', f'd="{flat_d(attrs["d"])}"', 1)
        return tag
    return re.sub(r"<path\b[^>]*/>", one, svg), alpha


def apply_alpha(pptx_path, alpha):
    """把代号色换回原色并写上透明度（OOXML 的 alpha 以十万分之一计）。ZIP 时间戳固定，保持逐字节可比。"""
    if not alpha:
        return
    import zipfile
    import export_pptx
    with zipfile.ZipFile(pptx_path) as z:
        items = [(i, z.read(i.filename)) for i in z.infolist()]
    with zipfile.ZipFile(pptx_path, "w") as z:
        for info, data in items:
            if info.filename == "ppt/slides/slide1.xml":
                s = data.decode("utf-8")
                for sc, (c, op) in alpha.items():
                    s = s.replace(f'<a:srgbClr val="{sc[1:]}"/>',
                                  f'<a:srgbClr val="{c[1:]}"><a:alpha val="{int(round(op * 100000))}"/></a:srgbClr>')
                data = s.encode("utf-8")
            export_pptx._zip_write(z, info.filename, data)


def env_check():
    """按能力分项自检（外部评审 H04）：出图、读文书、读 xlsx 清单、PNG 各自依赖不同，
    缺一样只关掉那一样，不把「标准库就能出图」说成「什么格式都能读」。"""
    ok = True
    print("法律图表大师 · 环境自检")
    print(f"  Python {sys.version.split()[0]}")
    rows = []
    try:
        import export_pptx  # noqa: F401
        used = next(n for n, p, m in kernel.REPORT if p == kernel.V1)
        skipped = [f"{n}（{'；'.join(m)}）" for n, p, m in kernel.REPORT if p != kernel.V1 and m != ["不存在"]]
        rows.append(("出图（SVG / PPTX）", True, f"V1 共享内核：{used} {kernel.V1}，所需能力逐项核过"
                     + (f"；跳过了 {'、'.join(skipped)}" if skipped else "")))
    except Exception as e:
        ok = False
        rows.append(("出图（SVG / PPTX）", False, f"缺 V1 共享内核：{e}。请按插件完整安装"))
    try:
        import cases
        has_v4 = cases._v4_ok(cases.V4)
        rows.append(("类案编码 · 读判决书文件", has_v4,
                     f"V4 大事记表大师的读取层：{cases.V4}" if has_v4 else
                     "缺 V4 大事记表大师（mqc-chronicle-master）的读取层：只能读案例清单，不能读判决书文件"))
    except SystemExit as e:
        rows.append(("类案编码 · 读判决书文件", False, str(e)))
    try:
        import openpyxl  # noqa: F401
        rows.append(("类案编码 · 读 .xlsx 清单 / 导出 Excel 母表", True, "openpyxl 可用"))
    except ImportError:
        rows.append(("类案编码 · 读 .xlsx 清单 / 导出 Excel 母表", False,
                     "缺 openpyxl（pip install openpyxl）：清单请另存 .csv；母表只出 .csv"))
    rows.append(("类案编码 · 读 .csv 清单", True, "标准库"))
    try:
        import render as v1render  # noqa: F401
        rows.append(("PNG（可选）", True, "由 V1 的转图链负责；缺转图工具时跳过 PNG，其余照出"))
    except Exception as e:
        rows.append(("PNG（可选）", False, f"不可用（{e}）；SVG 与 PPTX 不受影响"))
    for name, good, why in rows:
        print(f"  {'可用' if good else '不可用'}　{name}　{why}")
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="法律图表大师：说明 JSON → SVG / PPTX / PNG")
    ap.add_argument("spec", nargs="?")
    ap.add_argument("-o", "--out", default=None)
    ap.add_argument("--style")
    ap.add_argument("--accent", help="已停用：V6 只用两种风格的原色；给了会报错并说明")
    ap.add_argument("--canvas")
    ap.add_argument("--formats", default="svg,pptx")
    ap.add_argument("--fonts", default=None, choices=("safe", "master"))
    ap.add_argument("--profile")
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    if a.check:
        return env_check()
    if not a.spec:
        ap.error("要给一份说明 JSON")
    try:
        svg, rep = build(a.spec, a.style, a.accent, a.canvas, a.profile)
    except (SpecError, ValueError) as e:
        print(f"未出图：{e}", file=sys.stderr)
        return 1
    if a.plan:
        print(plan(rep))
        return 2 if rep["problems"] else 0
    if rep["problems"]:
        print("未出图：守卫没过", file=sys.stderr)
        for b in rep["problems"]:
            print("  " + b, file=sys.stderr)
        return 2
    base = a.out or os.path.join("out", os.path.splitext(os.path.basename(a.spec))[0])
    fmts = [x.strip() for x in a.formats.split(",") if x.strip()]
    unknown = [x for x in fmts if x not in FORMATS]
    if unknown:
        print(f"未出图：不认识的格式 {'、'.join(unknown)}；可选 {'、'.join(FORMATS)}", file=sys.stderr)
        return 1
    try:
        files, failed, notes = publish(svg, rep, base, set(fmts) | {"svg"}, a)
    except OSError as e:
        files, failed, notes = [], [f"发布时出错，已撤回本次写出的文件、放回原来的文件：{e}"], []
    for n in notes:
        print(n, file=sys.stderr)
    if failed:
        print("未交付：必需的产物没做成，本次一个文件都没有写出（目录里同名的旧文件不是本次产物）：",
              file=sys.stderr)
        for f_ in failed:
            print("  " + f_, file=sys.stderr)
        return 3
    print(checklist(rep, files))
    return 0


if __name__ == "__main__":
    # Windows 中文系统的控制台默认 GBK：不固定成 UTF-8，外部 AI（按 UTF-8 读）看到的是乱码，
    # 遇到 GBK 里没有的字（生僻字人名）还会在图已画好之后崩掉。写法与其余模块一致。
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:                               # noqa: BLE001
            pass
    sys.exit(main())
