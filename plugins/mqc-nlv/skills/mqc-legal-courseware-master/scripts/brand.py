# -*- coding: utf-8 -*-
"""律所名片：Logo、律所介绍、律师介绍。录一次，以后每套课件都能用。

放在哪：
  1. 课件目录下的 brand/（这套课件单独用一套名片，拷走课件时一起带走）；
  2. 否则用本机的公共名片：环境变量 NLV_BRAND_DIR，或 ~/.mqc-nlv/brand/。
目录里：
  brand.json   名片（格式见下）
  logo.png / logo.jpg / logo.svg   Logo（三选一；SVG 会转成可编辑形状，PNG/JPG 作为 PPTX 里唯一允许的图片）

brand.json：
  {"firm": {"name", "short", "intro", "areas": [..], "address", "phone", "email", "website"},
   "lawyers": [{"id", "name", "title", "intro", "areas": [..], "cases": [..], "phone", "email"}],
   "logo": "logo.png", "logo_on_dark": "logo-on-dark.png"（可选：深底页用的白字版）, "footer_logo": true}

名片里的字由介绍卡、联系方式卡**实时读取**：改了名片，所有介绍页一起变。
"""
import base64
import json
import os
import re
import struct

LOGO_EXT = (".png", ".jpg", ".jpeg", ".svg")
LOGO_MAX = 2 * 1024 * 1024
FIRM_KEYS = ("name", "short", "intro", "areas", "address", "phone", "email", "website")
LAWYER_KEYS = ("id", "name", "title", "intro", "areas", "cases", "phone", "email")


class BrandError(ValueError):
    pass


def user_dir():
    return os.environ.get("NLV_BRAND_DIR") or os.path.join(os.path.expanduser("~"), ".mqc-nlv", "brand")


def brand_dir(base_dir):
    local = os.path.join(base_dir or ".", "brand")
    return local if os.path.isdir(local) else user_dir()


def empty():
    return {"firm": {}, "lawyers": [], "logo": None, "footer_logo": False}


def load(base_dir):
    """返回名片（没有就返回空名片，不报错）。"""
    d = brand_dir(base_dir)
    p = os.path.join(d, "brand.json")
    b = empty()
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8-sig") as f:
                b.update(json.load(f))
        except (ValueError, OSError) as e:
            raise BrandError(f"律所名片 {p} 读不了：{e}")
    b["_dir"] = d
    for k in ("logo", "logo_on_dark"):
        if b.get(k) and not os.path.exists(os.path.join(d, b[k])):
            b[k] = None
    return b


def validate(b):
    errs = []
    if not isinstance(b.get("firm", {}), dict):
        errs.append("firm 要是一个对象")
    ids = set()
    for i, l in enumerate(b.get("lawyers") or []):
        if not isinstance(l, dict) or not str(l.get("name") or "").strip():
            errs.append(f"第 {i + 1} 位律师要写姓名")
            continue
        if not l.get("id") or l["id"] in ids:
            errs.append(f"律师「{l.get('name')}」的 id 缺失或重复")
        ids.add(l.get("id"))
    for k in ("areas", "cases"):
        for who in [b.get("firm") or {}] + list(b.get("lawyers") or []):
            if k in who and not isinstance(who[k], list):
                errs.append(f"{k} 要是一个列表（一项一条）")
    if errs:
        raise BrandError("；".join(errs))


def save(base_dir, b):
    clean = {k: v for k, v in b.items() if not k.startswith("_")}
    validate(clean)
    d = brand_dir(base_dir)
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, "brand.json")
    with open(p + ".nlv-new", "w", encoding="utf-8", newline="\n") as f:
        json.dump(clean, f, ensure_ascii=False, indent=1)
    os.replace(p + ".nlv-new", p)            # 改名覆盖，不靠删除
    return p


def save_logo(base_dir, name, data, variant="logo"):
    """variant：logo（浅底用，默认）或 logo_on_dark（深底用的白字版，可选）。"""
    if variant not in ("logo", "logo_on_dark"):
        raise BrandError("Logo 只分浅底用（logo）与深底用（logo_on_dark）两版")
    ext = os.path.splitext(name.lower())[1]
    if ext not in LOGO_EXT:
        raise BrandError("Logo 只收 PNG、JPG 或 SVG")
    if len(data) > LOGO_MAX:
        raise BrandError("Logo 太大（超过 2MB）：请用小一些的图")
    if ext == ".svg":
        if b"<svg" not in data[:4096]:
            raise BrandError("这不是一张 SVG")
    elif image_size(data, ext) is None:
        raise BrandError("这张图读不出尺寸，可能不是 PNG / JPG")
    b = load(base_dir)
    d = b["_dir"]
    os.makedirs(d, exist_ok=True)
    fn = ("logo" if variant == "logo" else "logo-on-dark") + (".jpg" if ext == ".jpeg" else ext)
    p = os.path.join(d, fn)
    with open(p + ".nlv-new", "wb") as f:
        f.write(data)
    os.replace(p + ".nlv-new", p)
    b[variant] = fn
    save(base_dir, b)
    return fn


# ------------------------------------------------------------- Logo
def image_size(data, ext):
    """PNG / JPG 的像素尺寸（不装 Pillow）。读不出返回 None。"""
    try:
        if ext == ".png" and data[:8] == b"\x89PNG\r\n\x1a\n":
            w, h = struct.unpack(">II", data[16:24])
            return w, h
        if ext in (".jpg", ".jpeg") and data[:2] == b"\xff\xd8":
            i = 2
            while i < len(data):
                if data[i] != 0xFF:
                    i += 1
                    continue
                mk = data[i + 1]
                if mk in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                    h, w = struct.unpack(">HH", data[i + 5:i + 9])
                    return w, h
                seg = struct.unpack(">H", data[i + 2:i + 4])[0]
                i += 2 + seg
    except (struct.error, IndexError):
        return None
    return None


def logo_info(b, dark=False):
    """返回 {kind: "raster"|"svg", path, data, w, h, mime} 或 None。
    dark：放在深底页上——有深底用的白字版就用它，没有就用浅底版。"""
    fn = (b.get("logo_on_dark") if dark else None) or b.get("logo") or (b.get("logo_on_dark") if not dark else None)
    if not fn:
        return None
    p = os.path.join(b["_dir"], fn)
    with open(p, "rb") as f:
        data = f.read()
    ext = os.path.splitext(fn.lower())[1]
    if ext == ".svg":
        import svgimport
        svg = data.decode("utf-8", errors="ignore")
        _, _, w, h = svgimport.size_of(svg)
        return {"kind": "svg", "path": p, "svg": svg, "w": w, "h": h}
    wh = image_size(data, ext)
    if not wh:
        return None
    mime = "image/png" if ext == ".png" else "image/jpeg"
    return {"kind": "raster", "path": p, "data": data, "w": wh[0], "h": wh[1], "mime": mime, "ext": ext.lstrip(".")}


def data_uri(info):
    return f"data:{info['mime']};base64," + base64.b64encode(info["data"]).decode("ascii")


# ------------------------------------------------------------- 介绍卡读的人
def who_data(b, who):
    """介绍卡 who = "firm" 或 "lawyer:<id>" → 字段。找不到返回 None。"""
    if who in (None, "", "firm"):
        f = b.get("firm") or {}
        return dict(f, kind="firm") if str(f.get("name") or "").strip() else None
    if str(who).startswith("lawyer:"):
        lid = who.split(":", 1)[1]
        for l in b.get("lawyers") or []:
            if l.get("id") == lid:
                return dict(l, kind="lawyer")
    return None


def contact_lines(b, who=None):
    src = who_data(b, who) if who and who != "firm" else (b.get("firm") or {})
    firm = b.get("firm") or {}
    out = []
    for k, zh in (("address", "地址"), ("phone", "电话"), ("email", "邮箱"), ("website", "网址")):
        v = str((src or {}).get(k) or firm.get(k) or "").strip()
        if v:
            out.append((zh, v))
    return out


# ------------------------------------------------------------- 一键生成介绍页
def intro_slide(b, kind, lawyer_id=None):
    """按名片生成一页模块（不需要 AI）：kind = firm / lawyer / closing。返回 (modules, 说明)。"""
    import grid as G
    firm = b.get("firm") or {}
    if kind == "firm":
        if not str(firm.get("name") or "").strip():
            raise BrandError("先在「更多 → 律所名片」里写上律所名称")
        mods, _ = G.apply_template([], "firm-intro")
        for m in mods:
            if m["type"] == "title":
                m["text"] = firm["name"]
            if m["type"] == "profile":
                m["who"] = "firm"
        return mods, f"律所介绍：{firm['name']}"
    if kind == "lawyer":
        l = who_data(b, f"lawyer:{lawyer_id}")
        if not l:
            raise BrandError("先在「更多 → 律所名片」里加一位律师")
        mods, _ = G.apply_template([], "lawyer-intro")
        for m in mods:
            if m["type"] == "title":
                m["text"] = l["name"]
                if l.get("title"):
                    m["sub"] = l["title"]
            if m["type"] == "profile":
                m["who"] = f"lawyer:{l['id']}"
            if m["type"] == "bullets":
                cases = [str(c) for c in l.get("cases") or [] if str(c).strip()][:5]
                if cases:
                    m["heading"] = "代表业绩"
                    m["items"] = cases
        mods = [m for m in mods if not (m["type"] == "bullets" and not m.get("items"))]
        return mods, f"律师简介：{l['name']}"
    if kind == "closing":
        mods, _ = G.apply_template([], "closing")
        for m in mods:
            if m["type"] == "title":
                m["text"] = "谢谢"
                if firm.get("name"):
                    m["kicker"] = firm["name"]
        return mods, "结束页"
    raise BrandError(f"不认识的介绍页 {kind!r}")


SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,32}$")


# ------------------------------------------------------------- 律所风格（名片目录里的 style.json）
def firm_style(base_dir):
    """返回 (律所风格, 出错说明)。没有律所风格时返回 (None, None)。"""
    import firm_style as FS
    p = os.path.join(brand_dir(base_dir), "style.json")
    if not os.path.exists(p):
        return None, None
    try:
        return FS.load(p), None
    except (FS.FirmStyleError, ValueError, OSError) as e:
        return None, f"律所风格文件 {p} 不合格：{e}"


TEMPLATE_MAX = 60 * 1024 * 1024


def import_template(base_dir, data, name=None, use_logos=None, filename="template.pptx"):
    """律所模板 → 读取报告 + 律所风格（style.json）+ 可选的两版 Logo。返回摘要。
    模板本身不留存（是律所的财产）；只留读出的东西：brand/template/tokens.json、report.html、Logo。"""
    import shutil
    import tempfile
    import firm_style as FS
    import template_read as TR
    if not str(filename).lower().endswith(".pptx"):
        raise BrandError("只收 .pptx 模板（老式 .ppt 请先在 PowerPoint 里另存为 .pptx）")
    if len(data) > TEMPLATE_MAX:
        raise BrandError("模板太大（超过 60MB）：可以先删掉里面的大图片再传")
    if data[:2] != b"PK":
        raise BrandError("这不是一份 .pptx 文件")
    b = load(base_dir)
    d = b["_dir"]
    td = tempfile.mkdtemp(prefix="nlv7-tpl-")
    try:
        src = os.path.join(td, "template.pptx")
        with open(src, "wb") as f:
            f.write(data)
        out = os.path.join(d, "template")
        try:
            tokens = TR.run(src, out)
        except ValueError as e:
            raise BrandError(str(e))
    finally:
        shutil.rmtree(td, ignore_errors=True)
    tokens["source"] = os.path.basename(filename)
    name = str(name or "").strip() or "自定义"        # 作者定的：一律叫「自定义」，不为哪一家律所单立风格名
    try:
        st = FS.make(tokens, name)
    except FS.FirmStyleError as e:
        raise BrandError(f"模板读懂了，但做不成律所风格：{e}")
    p = os.path.join(d, "style.json")
    with open(p + ".nlv-new", "w", encoding="utf-8", newline="\n") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)
    os.replace(p + ".nlv-new", p)
    if use_logos is None:
        use_logos = not b.get("logo")
    logos = []
    if use_logos:
        for key in ("logo", "logo_on_dark"):
            fn = (tokens.get(key) or {}).get("file")
            if fn:
                with open(os.path.join(out, fn), "rb") as f:
                    save_logo(base_dir, fn, f.read(), key)
                logos.append(key)
    return {"name": st["name"], "colors": st["colors"], "left_out": st["left_out"], "notes": tokens.get("notes") or [],
            "logos": logos, "pages": len(tokens.get("pages") or []), "style_file": p}


def _save_style(base_dir, st):
    p = os.path.join(load(base_dir)["_dir"], "style.json")
    with open(p + ".nlv-new", "w", encoding="utf-8", newline="\n") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)
    os.replace(p + ".nlv-new", p)
    return p


def custom_from_color(base_dir, color, source="手选主色"):
    """选一个主色 → 自定义风格。返回摘要（同 import_template）。"""
    import firm_style as FS
    try:
        tok = FS.tokens_from_color(color, source)
        st = FS.make(tok, "自定义")
    except FS.FirmStyleError as e:
        raise BrandError(str(e))
    p = _save_style(base_dir, st)
    note = [f"{tok['picked']} 太浅，投影看不清：已压深到 {st['colors']['accent']}"] if tok["adjusted"] else []
    return {"name": st["name"], "colors": st["colors"], "left_out": st["left_out"], "notes": note,
            "logos": [], "pages": 0, "style_file": p, "picked": tok["picked"]}


def custom_from_image(base_dir, data):
    """一张截图（模板页、律所官网、宣传册……）→ 取主色 → 自定义风格。"""
    import firm_style as FS
    try:
        c = FS.main_color_of(data)
    except FS.FirmStyleError as e:
        raise BrandError(str(e))
    out = custom_from_color(base_dir, c, "截图")
    out["notes"] = [f"从截图里取到主色 {c}"] + out["notes"]
    return out


def disable_firm_style(base_dir):
    """停用律所风格：改名为 style.disabled.json（不删文件，随时可以改回来）。"""
    d = brand_dir(base_dir)
    p = os.path.join(d, "style.json")
    if not os.path.exists(p):
        raise BrandError("没有在用的律所风格")
    os.replace(p, os.path.join(d, "style.disabled.json"))
