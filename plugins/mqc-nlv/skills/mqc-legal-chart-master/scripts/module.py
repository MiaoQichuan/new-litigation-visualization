# -*- coding: utf-8 -*-
"""V6 → V7 的接口：设计令牌（tokens）、版位（slots）、模块清单（module manifest）。

V7 法律课件大师要把 V1–V6 的产物当作「磁吸模块」拼进课件。为此 V6 对外承诺三样东西：

1. **设计令牌** `design/tokens.json`：颜色、圆角规则、方块模块、字体、字号阶梯、画布、强调色预设。
   由本脚本从 styles.py / spec.py / charts.py 生成，**不手改**；测试核对两边一致。
   V7 的页面装饰（页眉、页码、卡片底、目录）用同一份令牌，课件与图才是一个样子。
2. **版位** SLOTS：V7 页面上一个模块可占的几种格子。V6 对每个版位都能回答「放得下吗」（fit）。
3. **模块清单** `<名>.module.json`：V7 存的是**说明 JSON**，不是图片。换版位、换风格、换强调色，
   V7 拿说明重新调 V6 渲染，守卫重新验一遍。图永远是从数据算出来的，不会在课件里被拉伸变形。

    python3 scripts/module.py tokens            重新生成 design/tokens.json
    python3 scripts/module.py tokens --check    只核对，不一致则退出码 1
    python3 scripts/module.py fit 说明.json      列出这份说明在各版位、两种风格下放不放得下
"""
import json
import os
import sys

import kernel
from spec import CANVAS, CANVAS_ZH, MIN_CANVAS, BUDGET, MAX_ANNOTATIONS, ANNOTATABLE, CHARTS, CHART_ZH
from styles import _BASE, WHITELIST, STYLES

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
TOKENS = os.path.join(ROOT, "design", "tokens.json")
SCHEMA = "mqc-nlv/module@1"

# V7 页面（16:9，1280 × 720）上的版位。宽高都是模块自己的外框，含模块内的标题与来源行。
SLOTS = {
    "full": {"w": 1280, "h": 720, "zh": "整页"},
    "two-thirds": {"w": 816, "h": 600, "zh": "三分之二栏"},
    "half": {"w": 608, "h": 600, "zh": "半栏"},
    "wide": {"w": 1152, "h": 480, "zh": "通栏矮条（页面标题之下）"},
}


def version():
    with open(os.path.join(ROOT, "SKILL.md"), encoding="utf-8-sig") as f:
        for ln in f:
            if ln.strip().startswith("version:"):
                return ln.split(":", 1)[1].strip()
    return "?"


def tokens():
    styles = {}
    for name in STYLES:
        b = _BASE[name]
        styles[name] = {
            "color": {k: b[k] for k in ("paper", "ink", "ink2", "note", "grid", "axis", "mark", "flow",
                                        "node", "rail", "accent", "on_accent")},
            "ladder": list(b["ladder"]),
            "whitelist": sorted(WHITELIST[name]),
            "pattern": b["pattern"],
            "title": {"font": b["title_font"], "weight": b["title_weight"]},
            "num_track_em": b["num_track"],
            "corner": {
                "shape_px_at_1280x720": b["corner"],
                "scale": "随画布缩放：px × min(W/1280, H/720)，不小于 3px" if b["corner"] else "无",
                "min_px": 3.0 if b["corner"] else 0.0,
                "module_ratio": b["module"],
                "module_rule": ("方块模块（点阵的一格、图例色块、V7 的小卡片角标）的圆角 = 边长 × module_ratio"
                                if b["module"] else "方块模块为直角正方形"),
                "rails": "细长条（竖条、中位数线）一律直角、平头，用 rail 色",
                "arrows": "箭头不磨圆",
                "linecap": "round" if b["corner"] else "butt",
                "curve": "三次贝塞尔（cubic）；PPTX 中矩形还原为 roundRect，其余细分为折线",
            },
            "custom_accent": False,
        }
    return {
        "schema": "mqc-nlv/tokens@1",
        "generated_by": "scripts/module.py tokens —— 不要手改，改 styles.py 后重新生成",
        "skill": "V6 mqc-legal-chart-master", "version": version(),
        "styles": styles,
        "fonts": {"title_serif": kernel.TITLE_FONT, "body": kernel.BODY_FONT, "mono": kernel.MONO_FONT,
                  "pptx_safe": {"serif": "宋体", "sans": "微软雅黑", "mono": "Consolas"}},
        "type_scale_px_at_1280x720": {"title_qichuan": 38, "title_guizang": 44, "subtitle": 17, "label": 16,
                                      "value": 15, "big_number": 46, "tick": 13, "source": 12.5,
                                      "annotation": 15, "floor": 11},
        "type_scale_rule": "横版按 min(W/1280, H/720) 缩放；方图与竖图（H ≥ 0.9W）按 W/860 缩放；任何字不小于 floor",
        "accent_policy": "只用风格原色：奇川风 #991B1B，歸藏风 #002FA7；不接受自选强调色（ADR 0010）",
        "canvases": {k: {"w": w, "h": h, "zh": CANVAS_ZH.get(k, k)} for k, (w, h) in CANVAS.items()},
        "min_canvas": {"w": MIN_CANVAS[0], "h": MIN_CANVAS[1]},
        "slots": SLOTS,
        "charts": {c: {"zh": CHART_ZH[c], "budget": BUDGET[c][0], "unit": BUDGET[c][1],
                       "annotatable": c in ANNOTATABLE} for c in CHARTS},
        "max_annotations": MAX_ANNOTATIONS,
        "rules": ["一页一处重音", "纵轴从 0 起", "图上的数只许算不许编", "不出白描", "平面：只有汇入图流带可半透明"],
    }


def dump_tokens():
    return json.dumps(tokens(), ensure_ascii=False, indent=2) + "\n"


def fit(spec, styles=STYLES, accent=None):
    """返回 {版位: {风格: 问题列表}}；空列表 = 放得下。"""
    import copy
    import make
    from spec import SpecError
    out = {}
    for k, s in SLOTS.items():
        out[k] = {}
        for st in styles:
            try:
                _, rep = make.build(copy.deepcopy(spec), st, accent if st == "奇川风" else None,
                                    {"w": s["w"], "h": s["h"]})
                out[k][st] = rep["problems"]
            except (SpecError, ValueError) as e:
                out[k][st] = [str(e)]
    return out


def manifest(rep, files, spec_obj):
    """模块清单：V7 收进课件的就是这一份。spec 原样带上（去掉脚本内部算出的字段）。"""
    m = rep["spec"]
    clean = {k: v for k, v in spec_obj.items() if not k.startswith("_")}
    added = spec_obj.get("_pivot_added")
    if added:                                   # 用了 dataset：脚本算出来的不带走，V7 重画时按 dataset 重算
        clean["data"] = {k: v for k, v in clean.get("data", {}).items() if k not in added["data"]}
        if not clean["data"]:
            clean.pop("data")
        for k in ("order", "n"):
            if added[k]:
                clean.pop(k, None)
    fits = fit(clean, styles=(rep["style"],))
    return {
        "schema": SCHEMA,
        "kind": "chart",
        "producer": {"skill": "V6 mqc-legal-chart-master", "version": version()},
        "chart": rep["chart"], "chart_zh": CHART_ZH[rep["chart"]],
        "spec": clean,
        "render": {"style": rep["style"], "accent": rep["accent"], "accent_in": rep.get("accent_in"),
                   "w": rep["W"], "h": rep["H"], "profile": rep.get("profile")},
        "slots": {k: not v[rep["style"]] for k, v in fits.items()},
        "a11y": {"title": m["title"], "desc": f"{CHART_ZH[rep['chart']]}。{m['scope']}，n = {m['n']}。来源：{m['source']}"},
        "provenance": {"scope": m["scope"], "n": m["n"], "source": m["source"]},
        "emphasis": m.get("emphasis"),
        "annotations": m.get("annotations") or [],
        "review": rep["warnings"],
        "files": [os.path.basename(f) for f in files],
        "rerender": "python3 scripts/make.py <spec.json> --style <风格> --canvas <宽x高>",
    }


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if not argv:
        print(__doc__)
        return 1
    if argv[0] == "tokens":
        text = dump_tokens()
        old = open(TOKENS, encoding="utf-8-sig").read() if os.path.exists(TOKENS) else ""
        if "--check" in argv:
            ok = old == text
            print("design/tokens.json 与代码一致" if ok else "design/tokens.json 过期：运行 module.py tokens 重新生成")
            return 0 if ok else 1
        os.makedirs(os.path.dirname(TOKENS), exist_ok=True)
        with open(TOKENS, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"已写 {os.path.relpath(TOKENS, ROOT)}")
        return 0
    if argv[0] == "fit" and len(argv) > 1:
        with open(argv[1], encoding="utf-8-sig") as f:
            spec = json.load(f)
        res = fit(spec)
        for k, by in res.items():
            s = SLOTS[k]
            cells = []
            for st, probs in by.items():
                cells.append(f"{st} {'放得下' if not probs else '放不下：' + probs[0][:40]}")
            print(f"  {s['zh']:<14}{s['w']}×{s['h']}　" + "　".join(cells))
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    # Windows 中文系统的控制台默认 GBK：不固定成 UTF-8，外部 AI（按 UTF-8 读）看到的是乱码，
    # 遇到 GBK 里没有的字（生僻字人名）还会在图已画好之后崩掉。写法与其余模块一致。
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:                               # noqa: BLE001
            pass
    try:                                   # 常见输入错误（路径、JSON、编码）说人话，不甩堆栈
        __import__("_cli_errors").install()
    except ImportError:
        pass
    sys.exit(main())
