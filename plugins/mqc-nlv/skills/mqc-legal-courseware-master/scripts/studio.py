#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""法律课件大师 · 编辑器（本机）。

    python3 scripts/studio.py <课件目录>            打开编辑器（浏览器自动打开）
    python3 scripts/studio.py <课件目录> --port 8765 --no-open
    python3 scripts/studio.py <课件目录> --detach     由 AI 助手（Agent）代开时用这个：编辑器独立运行，命令马上返回
    python3 scripts/studio.py <课件目录> --stop       关掉独立运行的编辑器

为什么要 --detach（0.9.0）：Agent 的命令有时限（常见 2–10 分钟），到点或一轮结束会把它启动的进程一并清掉。
前台跑、普通后台跑（&），编辑器都会在几分钟后断掉——浏览器里页面还在，点什么都没反应。
--detach 让编辑器脱离 Agent 独立运行，先确认浏览器真能连上，再打印网址；连不上（多半是 Agent 的沙箱关了网络）
就明说，退出码 3，并给出两条路。

只用 Python 标准库：不装 Node、不装数据库、不联网。只监听本机 127.0.0.1，材料不出这台电脑。
课件目录的样子：

    我的课件/
      deck.json        课件说明（编辑器自动保存；模型也可以直接写它）
      assets/            V6 图表说明（*.json）与 V1–V5 的图（*.svg），出现在编辑器「诉讼图 → 已有的图」里
      exports/            导出的 PPTX

预览与导出走同一个拼页函数（deck.compose），编辑器里看到的就是 PPTX 里的样子。
"""
import argparse
import json
import tempfile
import os
import re
import socket
import subprocess
import sys
import time
import threading
import urllib.parse
import urllib.request
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


V6_LIBRARY = os.path.join(paths.V6, "..", "library")


def form_examples():
    """每种画法一份 V6 自带的示例说明（图表库的缩略图与「放进这一页」用它）。文件名以画法开头的优先。"""
    out = {}
    if not os.path.isdir(V6_EXAMPLES):
        return out
    for fn in sorted(os.listdir(V6_EXAMPLES)):
        if not fn.endswith(".json"):
            continue
        try:
            spec = json.load(open(os.path.join(V6_EXAMPLES, fn), encoding="utf-8-sig"))
        except (ValueError, OSError):
            continue
        c = spec.get("chart") if isinstance(spec, dict) else None
        if not isinstance(c, str):
            continue
        if c not in out or (fn.startswith(c + "-") and not out[c][0].startswith(c + "-")):
            spec.pop("annotations", None)
            out[c] = (fn[:-5], spec)
    return out


def chart_library():
    """图表库：V6 场景库里现在就能画的场景（画法已就绪、有示例），按画法交错排，漏斗排最后（作者定的：备用画法，不主推）。"""
    from spec import CHARTS, CHART_ZH
    ex = form_examples()
    try:
        ix = json.load(open(os.path.join(V6_LIBRARY, "index.json"), encoding="utf-8-sig"))
        tx = json.load(open(os.path.join(V6_LIBRARY, "taxonomy.json"), encoding="utf-8-sig"))
    except (ValueError, OSError):
        return {"forms": [], "recipes": [], "scenes": [], "intents": []}
    scenes = {x["code"]: x["name"] for x in tx.get("scenes", [])}
    areas = {x["code"]: x["name"] for x in tx.get("areas", [])}
    intents = {x["code"]: x["name"] for x in tx.get("intents", [])}
    ok = [r for r in ix.get("recipes", []) if r.get("status") == "ready" and r.get("form") in ex and r["form"] in CHARTS]
    order = [c for c in CHARTS if c != "funnel"]
    buckets = {c: [r for r in ok if r["form"] == c] for c in order}
    ranked = []
    while any(buckets.values()):
        for c in order:
            if buckets[c]:
                ranked.append(buckets[c].pop(0))
    ranked += [r for r in ok if r["form"] == "funnel"]
    recipes = [{"id": r["id"], "name": r.get("name", ""), "question": r.get("question", ""), "example": r.get("example", ""),
                "guard": r.get("guard", ""), "form": r["form"], "form_zh": CHART_ZH.get(r["form"], r["form"]),
                "scenes": [scenes.get(c, c) for c in r.get("scenes", [])], "area": areas.get(r.get("area"), ""),
                "intent": intents.get(r.get("intent"), "")}
               for r in ranked]
    cnt = {}
    for r in recipes:
        for z in r["scenes"]:
            cnt[z] = cnt.get(z, 0) + 1
    forms = [{"code": c, "zh": CHART_ZH.get(c, c), "example": ex[c][0], "n": sum(1 for r in recipes if r["form"] == c)}
             for c in order + ["funnel"] if c in ex]
    icnt = {}
    for r in recipes:
        if r["intent"]:
            icnt[r["intent"]] = icnt.get(r["intent"], 0) + 1
    return {"forms": forms, "recipes": recipes, "scenes": sorted(cnt, key=lambda z: (-cnt[z], z)),
            "intents": [{"name": z, "n": icnt[z]} for z in sorted(icnt, key=lambda z: (-icnt[z], z))]}


def chart_thumb(deck, base_dir, form, cache=None):
    """图表库缩略图：这种画法的 V6 示例，按课件的风格（含律所风格）画。"""
    import make
    ex = form_examples().get(form)
    if not ex:
        return None
    firm = D.firm_of(deck, base_dir)
    th = D._theme(deck["style"], firm)
    fk = ({"name": firm["name"], "base": th["base"], "accent": firm["colors"]["accent"],
           "title_font": (firm.get("fonts") or {}).get("title", "sans")} if firm else None)
    key = ("thumb", form, deck["style"], fk and fk["accent"])
    if cache is not None and key in cache:
        return cache[key]
    from spec import SpecError
    svg = None
    for w, h in ((1280, 720), (1600, 900)):   # 按整页幻灯片的比例画（缩略图框也是 16:9）：字与图的比例和放进课件时一样
        try:
            svg, _ = make.build(json.loads(json.dumps(ex[1])), th["base"], None, {"w": w, "h": h}, None, fk)
            break
        except (SpecError, ValueError):
            continue
    if svg is None:
        return None
    if cache is not None:
        cache[key] = svg
    return svg


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
                m = re.fullmatch(r"/brand/(qichuan-(?:avatar|favicon)\.png)", u.path)
                if m:                                   # 作者的头像：侧栏左上角与浏览器标签页的小图标
                    with open(os.path.join(ROOT, "web", "brand", m.group(1)), "rb") as f:
                        return self._send(200, f.read(), "image/png")
                if u.path == "/grid.js":
                    return self._send(200, open(GRID_JS, encoding="utf-8-sig").read(), "text/javascript; charset=utf-8")
                if u.path == "/api/state":
                    mt = str(mtime(proj.path))                  # 先取版本再读：读到的只会比版本新，合并时只会多核一次
                    return self._send(200, {"mtime": mt, "deck": proj.load(), "rules": grid_json(proj.dir), "styles": D.styles_for(proj.dir),
                                            "project": os.path.basename(proj.dir), "dir": proj.dir})
                if u.path == "/api/library":
                    return self._send(200, proj.library())
                if u.path == "/api/ping":            # --detach / --stop 认人：这个端口上开的是不是这套课件
                    return self._send(200, {"dir": proj.dir, "pid": os.getpid()})
                if u.path == "/api/version":
                    bd = B.brand_dir(proj.dir)
                    # 课件的版本用字符串：纳秒数超过 JS 能精确表示的整数，回传时会被四舍五入，保存时就对不上号
                    return self._send(200, {"deck": str(mtime(proj.path)), "ai": mtime(A.qpath(proj.dir)),
                                            "listen": A.listening(proj.dir),
                                            "brand": max(mtime(os.path.join(bd, "brand.json")), mtime(bd))})
                if u.path == "/api/ai":
                    return self._send(200, {"requests": A.load_q(proj.dir)[-50:], "kinds": A.KINDS, "tools": A.TOOLS,
                                            "listening": A.listening(proj.dir)})
                if u.path == "/api/chartlib":
                    return self._send(200, chart_library())
                m = re.fullmatch(r"/api/chartthumb/([a-z]+)\.svg", u.path)
                if m:
                    with proj.lock:
                        svg = chart_thumb(proj.load(), proj.dir, m.group(1), proj.cache)
                    if not svg:
                        return self._send(404, {"error": "没有这种画法的示例"})
                    return self._send(200, svg, "image/svg+xml; charset=utf-8")
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
                                             notes=(q.get("notes") or ["0"])[0] == "1",
                                             title_face="方正小标宋简体" if (q.get("tf") or ["0"])[0] == "1" else None)
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


STATE = ".nlv-studio.json"     # 独立运行的编辑器：网址与进程号（--stop 用它）
LOG = ".nlv-studio.log"


def serve(folder, port=8765, open_browser=True, state=None):
    proj = Project(folder)
    port = free_port(port)
    srv = ThreadingHTTPServer(("127.0.0.1", port), make_handler(proj))
    url = f"http://127.0.0.1:{port}/"
    if state:                  # 独立运行：端口真的绑上之后才写网址，等它的那一头据此确认
        W.write_text(os.path.join(proj.dir, STATE), json.dumps({"url": url, "pid": os.getpid(), "token": state}))
    print(f"法律课件大师 · 编辑器已打开：{url}\n课件：{proj.path}\n"
          + ("用 --stop 关掉。" if state else "关掉这个窗口（或 Ctrl+C）就退出。"), flush=True)
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


def _ping(url, folder, timeout=2.0):
    """像浏览器那样连一下编辑器，并认清开的是不是这套课件（端口可能已被别的课件的编辑器占了）。
    连上且是这套课件 → 返回编辑器进程号；否则 None。
    不走代理：有的电脑设了 HTTP_PROXY，127.0.0.1 也会被送去代理。"""
    try:
        op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with op.open(url + "api/ping", timeout=timeout) as r:
            got = json.loads(r.read().decode("utf-8"))
        same = os.path.normcase(os.path.abspath(got.get("dir") or "")) == os.path.normcase(os.path.abspath(folder))
        return got.get("pid") if same and isinstance(got.get("pid"), int) else None
    except Exception:
        return None


def _reachable(url, folder, timeout=2.0):
    return _ping(url, folder, timeout) is not None


def _read_state(folder):
    try:
        with open(os.path.join(folder, STATE), encoding="utf-8") as f:
            st = json.load(f)
        return st if isinstance(st, dict) and isinstance(st.get("url"), str) else None
    except (OSError, ValueError):
        return None


def _spawn_detached(cmd, log):
    """起一个脱离 Agent 的进程：不在 Agent 的进程组 / 作业对象里，Agent 清理时不会被连带掐掉。"""
    kw = {"stdin": subprocess.DEVNULL, "stdout": log, "stderr": subprocess.STDOUT, "close_fds": True}
    if os.name == "nt":
        base = 0x00000008 | 0x00000200          # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        try:                                    # 再跳出 Agent 的作业对象；作业不许跳出时退一步
            return subprocess.Popen(cmd, creationflags=base | 0x01000000, **kw)   # CREATE_BREAKAWAY_FROM_JOB
        except OSError:
            return subprocess.Popen(cmd, creationflags=base, **kw)
    return subprocess.Popen(cmd, start_new_session=True, **kw)


def _net_isolated(dev="/proc/net/dev"):
    """Linux 上 Agent 关网的常见做法是把命令放进独立的网络命名空间：里面只剩回环口 lo。
    这时编辑器在沙箱里连得上，沙箱外的浏览器却连不上——光靠「连一下」看不出来，要单独认。"""
    if not sys.platform.startswith("linux"):
        return False
    try:                                   # 读 /proc/net/dev（随网络命名空间变）；/sys/class/net 不随它变，认不出来
        with open(dev, encoding="ascii", errors="replace") as f:
            names = [ln.split(":", 1)[0].strip() for ln in f.readlines()[2:] if ":" in ln]
        return names == ["lo"]
    except OSError:
        return False


def _open_browser(url):
    """替用户打开浏览器，但绝不拖住 Agent 的命令：
    - 浏览器由一个脱离的小进程去开，输入输出都不接 Agent 的管道（Linux 上 xdg-open 拉起的浏览器会继承管道，
      Agent 要等管道关上才算命令结束，就一直等下去）；
    - 没有图形界面的 Linux（多是远程或沙箱）上不开：webbrowser 会退到 lynx 这类终端浏览器，开了也没人看，只给网址。"""
    if sys.platform.startswith("linux") and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return
    try:
        _spawn_detached([sys.executable, "-c", "import sys, webbrowser; webbrowser.open(sys.argv[1])", url],
                        subprocess.DEVNULL)
    except OSError:
        pass


def detach(folder, port=8765, open_browser=True, wait=15.0):
    folder = os.path.abspath(folder)
    Project(folder)                                   # 先在这里验课件目录：错了当场报，不留一个死进程
    old = _read_state(folder)
    if old and _reachable(old["url"], folder):
        # 不再替用户开浏览器：AI 常会重复执行「打开编辑器」，每次都弹一个新标签页，用户那边就乱了（缪律师实测）
        print(f"这套课件的编辑器已经开着：{old['url']}\n用户已经打开的那个页面照常用；关掉了的话，请在浏览器里打开这个网址。")
        return 0
    try:
        os.remove(os.path.join(folder, STATE))
    except OSError:
        pass
    # 用一次性记号认「是不是刚起的那个」，不比进程号：Windows 的虚拟环境里 python.exe 是个转发器，
    # 真正跑服务的是它再起的子进程，进程号对不上
    token = "%d-%d" % (os.getpid(), time.time_ns())
    with open(os.path.join(folder, LOG), "ab") as log:
        proc = _spawn_detached([sys.executable, os.path.abspath(__file__), folder, "--port", str(port),
                                "--no-open", "--_serve", token], log)
    t0, url = time.time(), None
    while time.time() - t0 < wait:
        st = _read_state(folder)
        if st and st.get("token") == token:
            url = st["url"]
            if _reachable(url, folder):
                break
        if proc.poll() is not None:
            break
        time.sleep(0.3)
    if url and _reachable(url, folder) and _net_isolated():
        print(f"编辑器在 {url} 起来了，但这条命令跑在关了网络的沙箱里：您的浏览器多半连不上。\n"
              "若浏览器能打开这个网址，照常用即可；打不开有两条路：\n"
              "  1. 在 Agent 里允许这条命令在沙箱外运行（或打开网络权限），再开一次；\n"
              "  2. 不开编辑器：直接说要做什么，AI 写 deck.json，用 build.py 检查并导出 PPTX。", file=sys.stderr)
        return 3
    if url and _reachable(url, folder):
        print(f"法律课件大师 · 编辑器已打开：{url}\n课件：{folder}\n"
              f"编辑器独立运行，关掉对话也还在；不用时：python3 {os.path.abspath(__file__)} \"{folder}\" --stop")
        if open_browser:
            _open_browser(url)
        return 0
    if proc.poll() is None:
        proc.terminate()
    tail = ""
    try:
        with open(os.path.join(folder, LOG), encoding="utf-8", errors="replace") as f:
            tail = "".join(f.readlines()[-5:]).strip()
    except OSError:
        pass
    print("编辑器没能打开：" + (f"服务在 {url} 起来了，但连不上。" if url else "服务没有起来。") + "\n"
          "多半是 AI 助手（Agent）的沙箱关了网络或不许开本机网页。两条路：\n"
          "  1. 在 Agent 里允许这条命令在沙箱外运行（或打开网络权限），再开一次；\n"
          "  2. 不开编辑器：直接说要做什么，AI 写 deck.json，用 build.py 检查并导出 PPTX。"
          + (f"\n日志：\n{tail}" if tail else ""), file=sys.stderr)
    return 3


def stop(folder):
    folder = os.path.abspath(folder)
    st = _read_state(folder)
    if not st:
        print("这套课件没有独立运行的编辑器。")
        return 0
    pid = _ping(st["url"], folder)            # 只结束「这个网址上、开着这套课件」的那个进程，不信文件里的旧进程号
    if pid and pid > 0 and pid != os.getpid():
        try:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
            else:
                import signal
                os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
        for _ in range(20):
            if not _reachable(st["url"], folder, 0.5):
                break
            time.sleep(0.2)
    try:
        os.remove(os.path.join(folder, STATE))
    except OSError:
        pass
    print("编辑器已关掉。" if not _reachable(st["url"], folder, 0.5) else f"没关掉：{st['url']} 还开着，请结束进程 {pid}。")
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
    ap.add_argument("--detach", action="store_true", help="独立运行（AI 助手代开时用）：命令马上返回，编辑器不随 Agent 结束")
    ap.add_argument("--stop", action="store_true", help="关掉独立运行的编辑器")
    ap.add_argument("--_serve", metavar="TOKEN", help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    if a.stop:
        return stop(a.folder)
    if a.detach:
        return detach(a.folder, a.port, not a.no_open)
    return serve(a.folder, a.port, not a.no_open, state=a._serve)


if __name__ == "__main__":
    sys.exit(main())
