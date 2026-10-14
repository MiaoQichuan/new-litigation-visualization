# -*- coding: utf-8 -*-
"""版面「预留位置」：从律所模板或一张截图里，算出上下左右要让出多少，网格缩进剩下的内容区。

    python3 scripts/frame.py 模板.pptx          # 或 截图.png
    → 上 121 · 右 61 · 下 57 · 左 60（设计像素，整页 1280×720）

作者定的（2026-10-05）：V7 只做法律图表页，律师把它粘进自己的课件。律所模板的 Logo、天头地脚、侧边条
各家不同，不一家一家去配——上传模板或截一张空白页，机器自己算；算得不对，四个数字手动改。
截图只认看得见的东西：背景色以外的像素就是设计元素。所以要截「空白页」（只有 Logo、页眉页脚那一页）。
"""
import os
import struct
import sys
import zlib

import paths  # noqa: F401
import grid as G

W, H = G.W, G.H
GAP = 16                    # 设计元素与内容之间再留一道间距（和模块间距一样）
TOP_ZONE, BOTTOM_ZONE = 0.36, 0.26     # 天头、地脚只在页面上方 36%、下方 26% 里找
SIDE_ZONE = 0.22                        # 左右侧边条只在两边 22% 里找
SHOT_MAX = 25 * 1024 * 1024


class FrameError(ValueError):
    pass


# ------------------------------------------------------------- 读图：先用 Pillow（快、认 JPG），没装就用自带的 PNG 解码
def _sample_pillow(data, cols, rows):
    try:
        from PIL import Image
    except ImportError:
        return None
    import io
    try:
        im = Image.open(io.BytesIO(data)).convert("RGBA")
    except Exception as e:                                   # noqa: BLE001
        raise FrameError(f"这张图读不了：{e}")
    w, h = im.size
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    im = Image.alpha_composite(bg, im).convert("RGB").resize((cols, rows), Image.BOX)
    b = im.tobytes()
    px = [tuple(b[i:i + 3]) for i in range(0, len(b), 3)]
    return w, h, [px[r * cols:(r + 1) * cols] for r in range(rows)]


def _sample_png(data, cols, rows):
    """不装 Pillow 时：自己解 PNG（8 位、不隔行），按格子抽样成 rows × cols 的 RGB。"""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise FrameError("没装 Pillow 时只认 PNG 截图（系统自带的截图默认就是 PNG）")
    pos, idat, plte = 8, b"", None
    w = h = depth = ctype = inter = None
    while pos + 8 <= len(data):
        ln, typ = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + ln]
        if typ == b"IHDR":
            w, h, depth, ctype, _, _, inter = struct.unpack(">IIBBBBB", body)
        elif typ == b"PLTE":
            plte = body
        elif typ == b"IDAT":
            idat += body
        elif typ == b"IEND":
            break
        pos += 12 + ln
    if depth != 8 or inter != 0 or ctype not in (0, 2, 3, 4, 6):
        raise FrameError("这张 PNG 的格式少见（16 位或隔行）：请换一张普通截图")
    ch = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ctype]
    raw = zlib.decompress(idat)
    stride = w * ch
    prev = bytearray(stride)
    want = {}                                    # 图的第 y 行 → 要它的抽样行（图比抽样格小时，一行要给好几格）
    for r in range(rows):
        want.setdefault(min(h - 1, int((r + 0.5) * h / rows)), []).append(r)
    xs = [min(w - 1, int((c + 0.5) * w / cols)) for c in range(cols)]
    out = [None] * rows
    for y in range(h):
        f = raw[y * (stride + 1)]
        line = bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        if f == 2:
            line = bytearray((a + b) & 255 for a, b in zip(line, prev))
        elif f:
            for i in range(stride):
                a = line[i - ch] if i >= ch else 0
                b = prev[i]
                c = prev[i - ch] if i >= ch else 0
                if f == 1:
                    line[i] = (line[i] + a) & 255
                elif f == 3:
                    line[i] = (line[i] + ((a + b) >> 1)) & 255
                elif f == 4:
                    pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                    line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        prev = line
        if y in want:
            row = []
            for x in xs:
                p = line[x * ch:(x + 1) * ch]
                if ctype == 3:
                    k = p[0]
                    rgb = tuple(plte[3 * k:3 * k + 3]) if plte and 3 * k + 2 < len(plte) else (255, 255, 255)
                elif ctype in (0, 4):
                    rgb = (p[0], p[0], p[0])
                else:
                    rgb = (p[0], p[1], p[2])
                al = p[-1] if ctype in (4, 6) else 255         # 透明处按白底算
                row.append(tuple(round(v * al / 255 + 255 * (1 - al / 255)) for v in rgb))
            for r in want[y]:
                out[r] = row
    return w, h, out


def sample(data, cols=320, rows=180):
    s = _sample_pillow(data, cols, rows)
    return s if s is not None else _sample_png(data, cols, rows)


# ------------------------------------------------------------- 截图 → 留白
def from_image(data):
    """截图（PNG / JPG）→ {"mode": "reserve", top, right, bottom, left, "source": "截图", "notes": [...]}。"""
    if not data or len(data) > SHOT_MAX:
        raise FrameError("截图是空的或太大（超过 25MB）")
    cols, rows = 320, 180
    w, h, grid = sample(data, cols, rows)
    notes = []
    if abs(w / h - W / H) > 0.04:
        notes.append(f"截图是 {w}×{h}，不是 16:9：按 16:9 硬套算的，结果请看一眼")
    counts = {}
    for row in grid:
        for p in row:
            q = tuple(v // 8 for v in p)
            counts[q] = counts.get(q, 0) + 1
    bgq = max(counts, key=counts.get)
    bg = tuple(v * 8 + 4 for v in bgq)

    def ink(p):
        return sum(abs(a - b) for a, b in zip(p, bg)) > 48

    mask = [[ink(p) for p in row] for row in grid]
    sx, sy = W / cols, H / rows                  # 抽样格 → 设计像素
    row_ink = [sum(r) for r in mask]
    top_rows = [r for r in range(int(rows * TOP_ZONE)) if row_ink[r] >= 2]
    bot_rows = [r for r in range(int(rows * (1 - BOTTOM_ZONE)), rows) if row_ink[r] >= 2]
    top = (max(top_rows) + 1) * sy + GAP if top_rows else 0
    bottom = (rows - min(bot_rows)) * sy + GAP if bot_rows else 0
    r0, r1 = int(top / sy), rows - int(bottom / sy)
    col_ink = [sum(mask[r][c] for r in range(r0, max(r0, r1))) for c in range(cols)]
    left_cols = [c for c in range(int(cols * SIDE_ZONE)) if col_ink[c] >= 2]
    right_cols = [c for c in range(int(cols * (1 - SIDE_ZONE)), cols) if col_ink[c] >= 2]
    left = (max(left_cols) + 1) * sx + GAP if left_cols else 0
    right = (cols - min(right_cols)) * sx + GAP if right_cols else 0
    mid = [mask[r][c] for r in range(int(r0 + 0.1 * (r1 - r0)), int(r1 - 0.1 * (r1 - r0)))
           for c in range(int(cols * SIDE_ZONE), int(cols * (1 - SIDE_ZONE)))]
    if mid and sum(mid) / len(mid) > 0.02:
        notes.append("截图中间也有内容：请截一张只有 Logo、页眉页脚的空白页，否则中间的字会被当成设计元素")
    fr = _finish(top, right, bottom, left, "截图", notes)
    fr["background"] = "#%02X%02X%02X" % bg
    return fr


# ------------------------------------------------------------- 模板 → 留白（用 template_read 读出的几何）
def from_tokens(tokens):
    """template_read 的结果 → 留白。看 Logo、日期、页脚、页码这些设计元素的位置；
    不看标题占位符（有的模板标题框和 Logo 叠在一起，靠不住）。"""
    geo = tokens.get("geometry") or {}
    boxes = []
    for key in ("logo", "logo_on_dark"):
        b = (tokens.get(key) or {}).get("box")
        if b:
            boxes.append(("Logo", b))
    for key, zh in (("date", "日期"), ("footer", "页脚"), ("page_no", "页码")):
        if geo.get(key):
            boxes.append((zh, geo[key]))
    top = bottom = 0.0
    seen = []
    for zh, (x, y, w, h) in boxes:
        if y + h <= H * TOP_ZONE:
            top = max(top, y + h + GAP)
            seen.append(f"{zh}在上方")
        elif y >= H * (1 - BOTTOM_ZONE):
            bottom = max(bottom, H - y + GAP)
            seen.append(f"{zh}在下方")
    left = float(geo.get("margin_left") or 0)
    right = float(geo.get("margin_right") or 0)
    notes = ["读到：" + "、".join(dict.fromkeys(seen))] if seen else ["模板里没读到 Logo、页脚、页码的位置：只按页边距留白"]
    return _finish(top, right, bottom, left, "模板", notes)


def from_pptx(path):
    import template_read as TR
    try:
        rep, z = TR.read(path)
    except Exception as e:                                   # noqa: BLE001
        raise FrameError(f"读不了这份模板：{e}（老式 .ppt 请先另存为 .pptx）")
    z.close()
    return from_tokens(rep)


def _finish(top, right, bottom, left, source, notes):
    """离页边至少和「铺满全屏」一样宽（上下 56、左右 48）——呼吸感不因预留而变窄；取整；内容区太小就报。"""
    fr = {"mode": "reserve", "source": source,
          "top": round(max(G.MY, top)), "right": round(max(G.MX, right)),
          "bottom": round(max(G.MY, bottom)), "left": round(max(G.MX, left))}
    bad = G.check_frame(fr)
    if bad:
        raise FrameError(bad[0] + "（设计元素占得太多：可以手动改小留白，或改用「铺满全屏」）")
    fr["notes"] = notes
    return fr


def main(argv=None):
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("用法：python3 scripts/frame.py 模板.pptx | 截图.png", file=sys.stderr)
        return 2
    p = argv[0]
    try:
        if p.lower().endswith(".pptx"):
            fr = from_pptx(p)
        else:
            with open(p, "rb") as f:
                fr = from_image(f.read())
    except (FrameError, OSError) as e:
        print(str(e), file=sys.stderr)
        return 1
    g = G.geom(fr)
    print(f"预留位置（{fr['source']}）：上 {fr['top']} · 右 {fr['right']} · 下 {fr['bottom']} · 左 {fr['left']}"
          f"；内容区 {W - fr['left'] - fr['right']}×{H - fr['top'] - fr['bottom']}，每格 {g['COL']:.0f}×{g['ROW']:.0f}")
    for n in fr["notes"]:
        print("  " + n)
    return 0


if __name__ == "__main__":
    if {"-h", "--help"} & set(__import__("sys").argv[1:]):   # 只打印用法、什么都不做（原来会把 --help 当成文件名）
        getattr(__import__("sys").stdout, "reconfigure", lambda **k: None)(encoding="utf-8")
        print((__doc__ or "").strip() or "用法见本模块的 SKILL.md")
        raise SystemExit(0)
    sys.exit(main())
