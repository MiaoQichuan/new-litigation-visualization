#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""法律课件大师 · 编辑器（本机）。

    python3 scripts/studio.py <课件目录>            打开编辑器（浏览器自动打开）
    python3 scripts/studio.py <课件目录> --port 8765 --no-open

只用 Python 标准库：不装 Node、不装数据库、不联网。只监听本机 127.0.0.1，材料不出这台电脑。
课件目录的样子：

    我的课件/
      deck.json        课件说明（编辑器自动保存；模型也可以直接写它）
      assets/            V6 图表说明（*.json）与 V1–V5 的图（*.svg），出现在编辑器「选图 → 已有的图」里
      exports/            导出的 PPTX

预览与导出走同一个拼页函数（deck.compose），编辑器里看到的就是 PPTX 里的样子。
"""
import argparse
import json
import tempfile
import os
import re
import socket
import sys
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import paths  # noqa: F401
import deck as D
import export as E
import ai as A
import brand as B
import safewrite as W

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
WEB = os.path.join(ROOT, "web", "studio.html")
GRID_JS = os.path.join(ROOT, "web", "grid.js")
V6_EXAMPLES = os.path.join(paths.V6, "..", "examples")
SAFE_NAME = re.compile(r"^[^/\\:*?\"<>|]{1,80}\.(json|svg)$")


class Project:
    def __init__(self, folder):
        self.dir = os.path.abspath(folder)
        self.assets = os.path.join(self.dir, "assets")
        self.out = os.path.join(self.dir, "exports")
        self.path = os.path.join(self.dir, "deck.json")
        os.makedirs(self.assets, exist_ok=True)
        if not os.path.exists(self.path):
            self.save(D.new_deck(os.path.basename(self.dir.rstrip(os.sep)) or "未命名课件"))
        self.cache = {}
        self.lock = threading.Lock()

    def load(self):
        with open(self.path, encoding="utf-8-sig") as f:
            return D.adopt_custom(D.normalize(json.load(f)), self.dir)

    def save(self, deck):
        D.validate(deck, self.dir)
        with W.lock(self.dir):              # 与对话里的 AI（ai.py apply）、别的窗口错开写；暂存文件各用各的
            W.write_text(self.path, json.dumps(deck, ensure_ascii=False, indent=1))

    def library(self):
        charts, figures = [], []
        import prov
        for fn in sorted(os.listdir(self.assets)):
            p = os.path.join(self.assets, fn)
            if fn.endswith(".json") and prov.is_sidecar(fn):
                continue                                # 图旁边的出处记录（V2 的 -trace.json）不是图表，不列
            if fn.endswith(".json"):
                try:
                    spec = json.load(open(p, encoding="utf-8-sig"))
                    if isinstance(spec, dict) and "chart" not in spec and isinstance(spec.get("parts"), list):
                        figures.append({"name": fn[:-5], "file": "assets/" + fn, "kind": "v5", "style": "奇川风",
                                        "parts": len(spec["parts"]), "w": 0, "h": 0,
                                        "title": (spec.get("case") or {}).get("title") or fn[:-5]})
                        continue
                    charts.append({"name": fn[:-5], "file": "assets/" + fn, "title": spec.get("title", ""),
                                   "chart": spec.get("chart", ""), "origin": "素材"})
                except (ValueError, OSError):
                    pass
            elif fn.endswith(".svg"):
                import svgimport
                svg = open(p, encoding="utf-8-sig", errors="ignore").read()
                _, _, w, h = svgimport.size_of(svg)
                figures.append({"name": fn[:-4], "file": "assets/" + fn, "style": svgimport.style_of(svg),
                                "w": w, "h": h, "from": svgimport.guess_from(svg)})
        builtin = []
        if os.path.isdir(V6_EXAMPLES):
            for fn in sorted(os.listdir(V6_EXAMPLES)):
                if fn.endswith(".json"):
                    try:                                # 一个坏的示例不连累整个图库
                        spec = json.load(open(os.path.join(V6_EXAMPLES, fn), encoding="utf-8-sig"))
                    except (ValueError, OSError):
                        continue
                    spec.pop("annotations", None)
                    builtin.append({"name": fn[:-5], "title": spec.get("title", ""), "chart": spec.get("chart", ""),
                                    "spec": spec, "origin": "V6 示例"})
        return {"charts": charts, "builtin": builtin, "figures": figures}


def mtime(p):
    try:
        return os.stat(p).st_mtime_ns
    except OSError:
        return 0


def grid_json(proj_dir=None):
    """编辑器要的规则：网格常数、模块、组合、外观。编辑器的 JS 只照这份做，不自己另立规矩。"""
    import grid as G
    import styles
    return {
        "grid": {k: getattr(G, k) for k in ("COLS", "ROWS", "MX", "MY", "COL", "ROW", "GUT", "FUSE_GAP", "W", "H",
                                            "MIN_COL", "MIN_ROW")},
        "types": {k: {**v, "min": list(v["min"]), "default": list(v["default"])} for k, v in G.TYPES.items()},
        "templates": G.TEMPLATES, "tones": G.TONES, "no_accent": sorted(G.NO_ACCENT),
        "styles": _styles_json(proj_dir),
    }


def _styles_json(proj_dir):
    import styles
    out = {st: {"accent": styles._BASE[st]["accent"], "R": D._theme(st)["R"], "r": D._theme(st)["r"],
                "paper": styles._BASE[st]["paper"], "builtin": True} for st in D.STYLES}
    firm, _ = B.firm_style(proj_dir) if proj_dir else (None, None)
    if firm:
        th = D._theme(firm["name"], firm)
        c = firm["colors"]
        out[D.CUSTOM] = {"accent": c["accent"], "R": th["R"], "r": th["r"], "paper": c["paper"], "builtin": False,
                             "tint": c["card"], "dark": c["accent_dark"], "ink": c["ink"], "outline": c["outline"]}
    return out


def save_backdrop(proj_dir, data):
    """预留位置用的截图：存在课件目录 frame/ 里，只垫在编辑器里看，不导出。只留一张，旧的改名作废（不删）。"""
    ext = "png" if data[:8] == b"\x89PNG\r\n\x1a\n" else "jpg"
    d_ = os.path.join(proj_dir, "frame")
    os.makedirs(d_, exist_ok=True)
    for old in ("png", "jpg"):
        op = os.path.join(d_, "backdrop." + old)
        if old != ext and os.path.exists(op):
            os.replace(op, op + ".old")
    fp = os.path.join(d_, "backdrop." + ext)
    with open(fp + ".nlv-new", "wb") as f:
        f.write(data)
    os.replace(fp + ".nlv-new", fp)
    return fp


def make_handler(proj):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
            if isinstance(body, (dict, list)):
                body = json.dumps(body, ensure_ascii=False)
            if isinstance(body, str):
                body = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _body(self):
            n = int(self.headers.get("Content-Length") or 0)
            return self.rfile.read(n) if n else b""

        def do_GET(self):
            u = urllib.parse.urlparse(self.path)
            q = urllib.parse.parse_qs(u.query)
            if self.headers.get("Host", "").split(":")[0] not in ("127.0.0.1", "localhost"):
                # 读也要核 Host：不核的话，恶意网页可借「DNS 重绑定」把自己的域名指到 127.0.0.1，读走课件内容与导出的 PPTX
                return self._send(403, {"error": "只接受本机请求"})
            try:
                if u.path in ("/", "/index.html"):
                    return self._send(200, open(WEB, encoding="utf-8-sig").read(), "text/html; charset=utf-8")
                if u.path == "/grid.js":
                    return self._send(200, open(GRID_JS, encoding="utf-8-sig").read(), "text/javascript; charset=utf-8")
                if u.path == "/api/state":
                    mt = str(mtime(proj.path))                  # 先取版本再读：读到的只会比版本新，合并时只会多核一次
                    return self._send(200, {"mtime": mt, "deck": proj.load(), "rules": grid_json(proj.dir), "styles": D.styles_for(proj.dir),
                                            "project": os.path.basename(proj.dir), "dir": proj.dir})
                if u.path == "/api/library":
                    return self._send(200, proj.library())
                if u.path == "/api/version":
                    bd = B.brand_dir(proj.dir)
                    # 课件的版本用字符串：纳秒数超过 JS 能精确表示的整数，回传时会被四舍五入，保存时就对不上号
                    return self._send(200, {"deck": str(mtime(proj.path)), "ai": mtime(A.qpath(proj.dir)),
                                            "brand": max(mtime(os.path.join(bd, "brand.json")), mtime(bd))})
                if u.path == "/api/ai":
                    return self._send(200, {"requests": A.load_q(proj.dir)[-50:], "kinds": A.KINDS, "tools": A.TOOLS})
                if u.path == "/api/brand":
                    b = B.load(proj.dir)
                    firm, ferr = B.firm_style(proj.dir)
                    return self._send(200, {"brand": {k: v for k, v in b.items() if not k.startswith("_")},
                                            "dir": b["_dir"], "local": b["_dir"] == os.path.join(proj.dir, "brand"),
                                            "style": firm, "style_error": ferr,
                                            "has_report": os.path.exists(os.path.join(b["_dir"], "template", "report.html"))})
                if u.path == "/api/brand/template-report":
                    p = os.path.join(B.brand_dir(proj.dir), "template", "report.html")
                    if not os.path.exists(p):
                        return self._send(404, {"error": "还没有读过模板"})
                    return self._send(200, open(p, encoding="utf-8-sig").read(), "text/html; charset=utf-8")
                if u.path == "/api/frame/backdrop":            # 预留位置的截图：只垫在编辑器里看，不导出
                    for ext, mime in (("png", "image/png"), ("jpg", "image/jpeg")):
                        fp = os.path.join(proj.dir, "frame", "backdrop." + ext)
                        if os.path.exists(fp):
                            with open(fp, "rb") as f:
                                return self._send(200, f.read(), mime)
                    return self._send(404, {"error": "还没有截图"})
                if u.path == "/api/brand/logo":
                    dark = (q.get("variant") or [""])[0] == "dark"
                    b_ = B.load(proj.dir)
                    if dark and not b_.get("logo_on_dark"):
                        return self._send(404, {"error": "还没有深底用的 Logo"})
                    info = B.logo_info(b_, dark)
                    if not info:
                        return self._send(404, {"error": "还没有 Logo"})
                    if info["kind"] == "svg":
                        return self._send(200, info["svg"], "image/svg+xml; charset=utf-8")
                    return self._send(200, info["data"], info["mime"])
                m = re.fullmatch(r"/api/slide/(\d+)\.svg", u.path)
                if m:
                    deck = proj.load()
                    i = int(m.group(1))
                    sid = (q.get("s") or [None])[0]       # 编辑器按「页 id」要：要的路上页被挪了位置，也拿到这一页，不拿成别的页
                    ids = [x["id"] for x in deck["slides"]]
                    if sid is not None:
                        if sid not in ids:
                            return self._send(404, {"error": "没有这一页"})
                        i = ids.index(sid)
                    if not 0 <= i < len(deck["slides"]):
                        return self._send(404, {"error": "没有这一页"})
                    with proj.lock:
                        svg, _ = D.compose(deck, i, proj.dir, proj.cache)
                    return self._send(200, svg, "image/svg+xml; charset=utf-8")
                if u.path == "/api/report" and q.get("ids"):    # 只查这几页（编辑器只重查变了的页）
                    deck = proj.load()
                    want = set((q.get("ids") or [""])[0].split(","))
                    by_id = {}
                    with proj.lock:
                        for i, s_ in enumerate(deck["slides"]):
                            if s_["id"] in want:
                                by_id[s_["id"]] = D.compose(deck, i, proj.dir, proj.cache)[1]
                    return self._send(200, {"by_id": by_id})
                if u.path == "/api/report":
                    deck = proj.load()
                    only = q.get("i")
                    idxs = [int(only[0])] if only else range(len(deck["slides"]))
                    reps = []
                    with proj.lock:
                        for i in idxs:
                            if 0 <= i < len(deck["slides"]):
                                reps.append(D.compose(deck, i, proj.dir, proj.cache)[1])
                    return self._send(200, reps)
                if u.path == "/api/asset":
                    rel = (q.get("f") or [""])[0]
                    p = os.path.abspath(os.path.join(proj.dir, rel))
                    if not p.startswith(proj.assets + os.sep) or not p.endswith(".json") or not os.path.exists(p):
                        return self._send(404, {"error": "只读 assets/ 里的 .json"})
                    return self._send(200, open(p, encoding="utf-8-sig").read())
                if u.path == "/api/download":
                    f = os.path.basename((q.get("f") or [""])[0])
                    p = os.path.join(proj.out, f)
                    if not f.endswith(".pptx") or not os.path.exists(p):
                        return self._send(404, {"error": "没有这个文件"})
                    data = open(p, "rb").read()
                    return self._send(200, data, "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                                      {"Content-Disposition": "attachment; filename*=UTF-8''" + urllib.parse.quote(f)})
                return self._send(404, {"error": "not found"})
            except (D.DeckError, ValueError, OSError) as e:
                return self._send(400, {"error": str(e)})

        def do_POST(self):
            u = urllib.parse.urlparse(self.path)
            q = urllib.parse.parse_qs(u.query)
            if self.headers.get("Host", "").split(":")[0] not in ("127.0.0.1", "localhost"):
                return self._send(403, {"error": "只接受本机请求"})
            origin = self.headers.get("Origin") or self.headers.get("Referer")
            if origin and urllib.parse.urlparse(origin).netloc != self.headers.get("Host", ""):
                return self._send(403, {"error": "只接受编辑器自己的请求"})   # 别的网页里的脚本不能改您的课件
            try:
                if u.path == "/api/deck":
                    deck = json.loads(self._body().decode("utf-8"))
                    base = (q.get("base") or [""])[0]
                    with proj.lock, W.lock(proj.dir):   # 核版本与写入之间不许别的进程插进来
                        # 编辑器带上它最后看到的版本：磁盘上的已经被别的窗口或 AI 改过，就不覆盖，把现在的课件交回去让它合并
                        # （原来是整份覆盖：两个窗口前后脚保存，先存的那一处改动会被悄悄冲掉）
                        if base and base != str(mtime(proj.path)):
                            return self._send(200, {"ok": False, "conflict": True, "deck": proj.load(),
                                                    "mtime": str(mtime(proj.path))})
                        try:
                            proj.save(deck)
                        except D.DeckError as e:
                            return self._send(200, {"ok": False, "error": str(e)})
                        return self._send(200, {"ok": True, "mtime": str(mtime(proj.path))})
                if u.path == "/api/ai":
                    body = json.loads(self._body().decode("utf-8"))
                    try:
                        r = A.add(proj.dir, body.get("kind"), body.get("slide"), body.get("module"), body.get("tool"),
                                  body.get("prompt"))
                    except (A.AIError, D.DeckError) as e:
                        return self._send(200, {"ok": False, "error": str(e)})
                    return self._send(200, {"ok": True, "request": r})
                if u.path == "/api/ai/cancel":
                    rid = (q.get("id") or [""])[0]
                    try:
                        r = A.set_status(proj.dir, rid, "cancelled")
                    except A.AIError as e:
                        return self._send(200, {"ok": False, "error": str(e)})
                    return self._send(200, {"ok": True, "request": r})
                if u.path == "/api/brand":
                    b = json.loads(self._body().decode("utf-8"))
                    try:
                        B.save(proj.dir, b)
                    except B.BrandError as e:
                        return self._send(200, {"ok": False, "error": str(e)})
                    return self._send(200, {"ok": True})
                if u.path == "/api/brand/logo":
                    name = os.path.basename((q.get("name") or [""])[0])
                    variant = "logo_on_dark" if (q.get("variant") or [""])[0] == "dark" else "logo"
                    try:
                        fn = B.save_logo(proj.dir, name, self._body(), variant)
                    except B.BrandError as e:
                        return self._send(200, {"ok": False, "error": str(e)})
                    return self._send(200, {"ok": True, "logo": fn})
                if u.path == "/api/custom":                   # 自定义风格：上传模板（.pptx）或截图（.png / .jpg）
                    import frame as F
                    name = os.path.basename((q.get("name") or [""])[0])
                    low = name.lower()
                    n = int(self.headers.get("Content-Length") or 0)
                    if n > max(B.TEMPLATE_MAX, F.SHOT_MAX):
                        return self._send(200, {"ok": False, "error": "文件太大"})
                    data = self._body()
                    fr = None
                    try:
                        if low.endswith(".pptx"):
                            summ = B.import_template(proj.dir, data, "自定义", False, name)
                            with tempfile.TemporaryDirectory(prefix="nlv7-frame-") as td:
                                tp = os.path.join(td, "t.pptx")
                                with open(tp, "wb") as f:
                                    f.write(data)
                                try:
                                    fr = F.from_pptx(tp)
                                except F.FrameError:
                                    fr = None
                        elif low.endswith((".png", ".jpg", ".jpeg")):
                            summ = B.custom_from_image(proj.dir, data)
                            try:
                                fr = F.from_image(data)
                                save_backdrop(proj.dir, data)
                                fr["backdrop"] = True
                            except F.FrameError:
                                fr = None
                        else:
                            return self._send(200, {"ok": False, "error": "只收模板（.pptx）或图片（.png / .jpg）"})
                    except B.BrandError as e:
                        return self._send(200, {"ok": False, "error": str(e)})
                    return self._send(200, {"ok": True, **summ, "frame": fr})
                if u.path == "/api/chart/alts":               # 换一种图：V6 自己试，能换的才亮
                    body = json.loads(self._body().decode("utf-8") or "{}")
                    deck = proj.load()
                    try:
                        with proj.lock:
                            alts = D.chart_alternatives(deck, int(body.get("slide", 0)), body.get("module"), proj.dir, proj.cache)
                    except (StopIteration, IndexError, ValueError, D.DeckError) as e:
                        return self._send(200, {"ok": False, "error": f"这张卡不是图表卡，或还是空的：{e}"})
                    return self._send(200, {"ok": True, "alts": alts})
                if u.path == "/api/custom/color":
                    try:
                        body = json.loads(self._body().decode("utf-8") or "{}")
                        summ = B.custom_from_color(proj.dir, body.get("color"))
                    except (B.BrandError, ValueError) as e:
                        return self._send(200, {"ok": False, "error": str(e)})
                    return self._send(200, {"ok": True, **summ})
                if u.path == "/api/frame/read":               # 预留位置：上传律所模板或一张截图，算出四边留白
                    import frame as F
                    name = os.path.basename((q.get("name") or [""])[0]).lower()
                    n = int(self.headers.get("Content-Length") or 0)
                    if n > max(B.TEMPLATE_MAX, F.SHOT_MAX):
                        return self._send(200, {"ok": False, "error": "文件太大"})
                    data = self._body()
                    try:
                        if name.endswith(".pptx"):
                            if data[:2] != b"PK":
                                raise F.FrameError("这不是 .pptx 文件（老式 .ppt 请先另存为 .pptx）")
                            with tempfile.TemporaryDirectory(prefix="nlv7-frame-") as td:
                                tp = os.path.join(td, "t.pptx")
                                with open(tp, "wb") as f:
                                    f.write(data)
                                fr = F.from_pptx(tp)
                        elif name.endswith((".png", ".jpg", ".jpeg")):
                            fr = F.from_image(data)
                            save_backdrop(proj.dir, data)
                            fr["backdrop"] = True
                        else:
                            raise F.FrameError("只收律所模板（.pptx）或截图（.png / .jpg）")
                    except F.FrameError as e:
                        return self._send(200, {"ok": False, "error": str(e)})
                    return self._send(200, {"ok": True, "frame": fr})
                if u.path == "/api/brand/template":
                    name = os.path.basename((q.get("name") or [""])[0])
                    n = int(self.headers.get("Content-Length") or 0)
                    if n > B.TEMPLATE_MAX:
                        return self._send(200, {"ok": False, "error": "模板太大（超过 60MB）"})
                    logos = (q.get("logos") or [""])[0]
                    try:
                        summ = B.import_template(proj.dir, self._body(), (q.get("style") or [""])[0],
                                                 None if logos == "" else logos == "1", name)
                    except B.BrandError as e:
                        return self._send(200, {"ok": False, "error": str(e)})
                    return self._send(200, {"ok": True, **summ})
                if u.path == "/api/brand/style/disable":
                    firm, _ = B.firm_style(proj.dir)
                    try:
                        B.disable_firm_style(proj.dir)
                    except B.BrandError as e:
                        return self._send(200, {"ok": False, "error": str(e)})
                    with W.lock(proj.dir):
                        with open(proj.path, encoding="utf-8-sig") as f:            # 这套课件正用着它：换回奇川风
                            raw = json.load(f)
                        if raw.get("style") not in D.STYLES:                # 自定义（含旧名字）：换回奇川风
                            raw["style"] = "奇川风"
                            proj.save(raw)
                    return self._send(200, {"ok": True})
                if u.path == "/api/brand/intro":
                    body = json.loads(self._body().decode("utf-8"))
                    try:
                        mods, note = B.intro_slide(B.load(proj.dir), body.get("kind"), body.get("lawyer"))
                    except B.BrandError as e:
                        return self._send(200, {"ok": False, "error": str(e)})
                    for k, m in enumerate(mods):
                        m["id"] = f"m{k + 1}"
                    return self._send(200, {"ok": True, "modules": mods, "note": note})
                if u.path in ("/api/tidy", "/api/template"):
                    import grid as G
                    body = json.loads(self._body().decode("utf-8"))
                    mods = body.get("modules") or []
                    bad = G.check_slide(mods)
                    if bad:
                        return self._send(200, {"ok": False, "error": "；".join(bad)})
                    if u.path == "/api/tidy":
                        figs = {}                      # 图卡的比例：拿这一页拼一遍，从报告里取
                        try:
                            deck = proj.load()
                            tmp = dict(deck, slides=[{"id": "__tidy", "modules": mods}])
                            with proj.lock:
                                rep = D.compose(tmp, 0, proj.dir, proj.cache)[1]
                            figs = {k: v["fig"] for k, v in rep["modules"].items() if v.get("fig")}
                            geo = G.geom(deck.get("frame"))
                        except Exception:                # noqa: BLE001 —— 拼不出来就只做原来的整理
                            geo = None
                        mods, n0, fixed = G.fit_figures(mods, figs, geo) if figs else (mods, [], set())
                        out, notes = G.tidy(mods, fixed)
                        notes = n0 + notes
                        return self._send(200, {"ok": True, "modules": out, "notes": notes})
                    if body.get("name") not in G.TEMPLATES:
                        return self._send(200, {"ok": False, "error": "没有这个组合"})
                    out, left = G.apply_template(mods, body["name"])
                    return self._send(200, {"ok": True, "modules": out, "left": left})
                if u.path == "/api/export":
                    deck = proj.load()
                    safe = re.sub(r'[\\/:*?"<>|]+', "_", deck.get("title") or "课件")[:60]
                    page = (q.get("page") or [None])[0]
                    pages = None
                    if page is not None:                    # 只导出这一页
                        if not page.isdigit():
                            return self._send(200, {"ok": False, "error": "页号不对"})
                        pages = [int(page)]
                        safe += f"-第{int(page) + 1}页"
                    out = os.path.join(proj.out, safe + ".pptx")
                    try:
                        with proj.lock:
                            p, rep = E.build(deck, proj.dir, out, cache=proj.cache, pages=pages,
                                             animate=(q.get("animate") or ["1"])[0] != "0",
                                             notes=(q.get("notes") or ["0"])[0] == "1")
                    except (E.ExportError, D.DeckError) as e:
                        return self._send(200, {"ok": False, "error": str(e)})
                    return self._send(200, {"ok": True, "file": os.path.basename(p), "path": p, **rep})
                if u.path == "/api/upload":
                    name = os.path.basename((q.get("name") or [""])[0])
                    if not SAFE_NAME.match(name):
                        return self._send(200, {"ok": False, "error": "只收 .json（V6 图表说明、图旁边的出处记录）与 .svg（V1–V5 的图）"})
                    data = self._body()
                    if len(data) > 20 * 1024 * 1024:
                        return self._send(200, {"ok": False, "error": "文件太大（超过 20MB）"})
                    import prov
                    if name.endswith(".json") and prov.is_sidecar(name):   # V2、V3 图旁边的出处记录：和图一起拖进来就能看出处
                        try:
                            tr = json.loads(data.decode("utf-8-sig"))
                            assert isinstance(tr, dict) and isinstance(tr.get("rows"), list)
                        except Exception:
                            return self._send(200, {"ok": False, "error": "这不是 V2 / V3 出图时写的出处记录（要有 rows）"})
                    elif name.endswith(".json"):
                        try:
                            spec = json.loads(data.decode("utf-8-sig"))
                            assert isinstance(spec, dict) and ("chart" in spec or isinstance(spec.get("parts"), list))
                        except Exception:
                            return self._send(200, {"ok": False, "error": "这不是 V6 图表说明（要有 chart 字段）或 V5 对抗图数据（要有 parts）"})
                    p = os.path.join(proj.assets, name)
                    W.write_bytes(p, data)
                    return self._send(200, {"ok": True, "file": "assets/" + name, "sidecar": name.endswith(".json") and prov.is_sidecar(name)})
                return self._send(404, {"error": "not found"})
            except (ValueError, OSError) as e:
                return self._send(400, {"error": str(e)})
    return H


def free_port(start):
    for p in range(start, start + 50):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    raise SystemExit("找不到空闲端口")


def serve(folder, port=8765, open_browser=True):
    proj = Project(folder)
    port = free_port(port)
    srv = ThreadingHTTPServer(("127.0.0.1", port), make_handler(proj))
    url = f"http://127.0.0.1:{port}/"
    print(f"法律课件大师 · 编辑器已打开：{url}\n课件：{proj.path}\n关掉这个窗口（或 Ctrl+C）就退出。")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


def main(argv=None):
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="法律课件大师 · 编辑器")
    ap.add_argument("folder")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-open", action="store_true")
    a = ap.parse_args(argv)
    return serve(a.folder, a.port, not a.no_open)


if __name__ == "__main__":
    sys.exit(main())
