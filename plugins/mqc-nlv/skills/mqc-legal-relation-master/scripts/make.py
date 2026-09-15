# -*- coding: utf-8 -*-
"""法律关系图大师的一条命令入口。

模型只做一件事：读材料，写 casefile.json（格式见 references/casefile-guide.md）。
其余全部由本脚本完成：规模判断、布局、渲染、三风格、五种格式、
路线判据、导出物判据、出处索引、交付说明。

    python make.py relations.json --plan-only                     规模判断，一秒内返回
    python make.py relations.json --out 目录 --choice choice.json  出图
    python make.py --check                                        只查运行环境
    python make.py relations.json --out 目录 --choice choice.json --relayout

choice.json 就是 ask.py resolve 打印的那一行，风格与重点只认它：
没有 choice 就按奇川风、一处红都不标。每次只出所选的一种风格。

布局是唯一耗时的环节（十几个主体要一两分钟）。结果存进 out/layout.json，
案件的主体与关系没变时直接复用：改标题、改备注、换风格、
导出失败后重来，都不再重跑布局。
"""
import sys, os, json, math, hashlib, argparse, shutil, subprocess, time

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

STYLES = ("奇川风", "白描", "歸藏风")  # 每次只出所选的一种
STYLE_SLUG = {"奇川风": "qichuan", "白描": "baimiao", "歸藏风": "guizang"}
INK, LINE, EDGE, RED, MUTED = "#1F2933", "#4B5563", "#D6DAE0", "#991B1B", "#6B7280"
FILL_SUBJ, FILL_OBJ = "#F3F4F6", "#FAFAFA"
FS_TITLE, FS_SUB, FS_NODE, FS_NOTE, FS_LABEL = 30, 13, 14, 11, 12
SW, SW_EMPH, ARROW = 1.30, 3.0, 12
OX, OY = 150, 170
FONT_STACK = ("'Noto Sans CJK SC','PingFang SC','Microsoft YaHei',"
              "'Noto Sans SC','Helvetica Neue',Arial,sans-serif")
TITLE_FONT = ("'Noto Serif CJK SC','方正小标宋简体','FZXiaoBiaoSong-B05S',"
              "'思源宋体','Source Han Serif SC','华文中宋','STZhongsong',serif")


def die(msg, code=2):
    print("停止：" + msg)
    sys.exit(code)


# ------------------------------------------------------------------ 环境
def png_backends():
    found = []
    try:
        import cairosvg  # noqa: F401
        found.append("cairosvg")
    except Exception:
        pass
    for exe in ("rsvg-convert", "inkscape"):
        if shutil.which(exe):
            found.append(exe)
    if shutil.which("node"):
        r = subprocess.run(["node", "-e", "require('sharp')"], capture_output=True)
        if r.returncode == 0:
            found.append("sharp")
    return found


def check_env(verbose=True):
    rows = [("Python", sys.version.split()[0], True)]
    import exports
    v1 = exports._V1
    rows.append(("V1 导出器", "在" if os.path.exists(os.path.join(v1, "export_pptx.py")) else "缺",
                 os.path.exists(os.path.join(v1, "export_pptx.py"))))
    b = png_backends()
    rows.append(("PNG 渲染", "、".join(b) if b else "无（pip install cairosvg，或装 rsvg-convert）", bool(b)))
    if verbose:
        for k, v, ok in rows:
            print(f"  {'OK  ' if ok else 'FAIL'} {k}：{v}")
    return all(ok for _, _, ok in rows), b


def to_png(svg, png, backends, width=1700):
    for b in backends:
        try:
            if b == "cairosvg":
                import cairosvg
                cairosvg.svg2png(url=svg, write_to=png, output_width=width)
            elif b == "rsvg-convert":
                subprocess.run(["rsvg-convert", "-w", str(width), "-o", png, svg], check=True)
            elif b == "inkscape":
                subprocess.run(["inkscape", svg, "--export-type=png", f"--export-filename={png}",
                                f"--export-width={width}"], check=True, capture_output=True)
            elif b == "sharp":
                js = ("const s=require('sharp');s(process.argv[1],{density:144})"
                      ".resize({width:+process.argv[3]}).png().toFile(process.argv[2])"
                      ".catch(e=>{console.error(e);process.exit(1)})")
                subprocess.run(["node", "-e", js, svg, png, str(width)], check=True)
            if os.path.exists(png) and os.path.getsize(png) > 0:
                return png
        except Exception:
            continue
    return "失败：没有可用的 PNG 渲染器（先跑 make.py --check）"


# ------------------------------------------------------------------ 读案件
def load(path):
    """读 relations.json。两种写法都认：

    nodes：[{id, name, note?, kind?: 主体/客体（或 S/O）, source?}]
    edges：[[from, to, 关系名]] 或 [{from, to, label, line?: 实线/虚线, source?}]
    """
    try:
        cf = json.load(open(path, encoding="utf-8"))
    except Exception as e:
        die(f"relations.json 读不了：{e}")
    errs = []
    kind_map = {"S": "主体", "O": "客体", "主体": "主体", "客体": "客体", None: "主体"}
    nodes = []
    for n in cf.get("nodes") or []:
        if not n.get("id") or not n.get("name"):
            errs.append(f"主体缺 id 或 name：{n}")
            continue
        if n.get("kind") not in kind_map:
            errs.append(f"{n['id']} 的 kind 只能是 主体 / 客体")
        nodes.append(dict(n, kind=kind_map.get(n.get("kind"), "主体")))
    ids = [n["id"] for n in nodes]
    if len(set(ids)) != len(ids):
        errs.append("主体 id 有重复")
    edges = []
    for i, e in enumerate(cf.get("edges") or []):
        if isinstance(e, (list, tuple)):
            e = dict(zip(("from", "to", "label", "line"), e))
        e = dict(e)
        e.setdefault("line", "实线")
        for k in ("from", "to", "label"):
            if not e.get(k):
                errs.append(f"第 {i+1} 条关系缺 {k}（关系名照录原文，不能空着）")
        for k in ("from", "to"):
            if e.get(k) and e[k] not in ids:
                errs.append(f"第 {i+1} 条关系的 {k}「{e[k]}」不是已列主体")
        if e["line"] not in ("实线", "虚线"):
            errs.append(f"第 {i+1} 条关系的 line 只能是 实线 / 虚线")
        edges.append(e)
    # 同向重复的关系合成一条（关系名用「；」连起来，不删字）。
    # 两条线走同一对端口必然叠在一起（G2），先前只在第〇轮合并，
    # 没超限、不走第〇轮的案件照样叠线。与 ask.py 同一规则，重点编号才对得上。
    if not errs:
        from ask import merge_parallel
        before = len(edges)
        edges = merge_parallel(edges)
        if len(edges) < before:
            print(f"  注意：同向重复的关系 {before - len(edges)} 条已合并，关系名用「；」连起来")
        for e in edges:
            e.setdefault("line", "实线")
        seen = {(e["from"], e["to"]) for e in edges}
        for e in edges:
            if e["from"] == e["to"]:
                errs.append(f"「{e['label']}」起止是同一个模块，关系图画不出指向自己的线；"
                            "改成指向对应的客体（合同、款项、股权）")
            elif (e["to"], e["from"]) in seen and e["from"] < e["to"]:
                a_ = next(n["name"] for n in nodes if n["id"] == e["from"])
                b_ = next(n["name"] for n in nodes if n["id"] == e["to"])
                errs.append(f"「{a_}」与「{b_}」之间有方向相反的两条关系，两条线会叠在一起；"
                            "按本 skill 的画法经由客体连接（如 甲 → 《买卖合同》 ← 乙），"
                            "或合成一条关系")
        linked = {x for e in edges for x in (e["from"], e["to"])}
        lonely = [n["name"] for n in nodes if n["id"] not in linked]
        if lonely:
            errs.append("这些模块一条关系都没有，图上会是孤零零的块：" + "、".join(lonely)
                        + "；要么补上关系，要么移入 unsure")
    if cf.get("emphasis") or any(n.get("hot") for n in cf.get("nodes") or []):
        print("  注意：relations.json 里的重点标记一律不用，重点只认 ask.py resolve 给出的 choice")
    if errs:
        die("relations.json 有问题：\n  " + "\n  ".join(errs))
    return cf, nodes, edges


def load_choice(path, nodes, edges):
    if not path:
        return dict(style="奇川风", emphasis=dict(nodes=[], edges=[]), label="无（使用者未指定）")
    try:
        c = json.load(open(path, encoding="utf-8"))
    except Exception as e:
        die(f"choice.json 读不了：{e}")
    st = c.get("style")
    if st not in STYLES:
        die(f"choice 的风格只能是一种：奇川风 / 白描 / 歸藏风，收到 {st!r}")
    em = c.get("emphasis") or {}
    hn, he = list(em.get("nodes") or []), list(em.get("edges") or [])
    if st != "奇川风" and (hn or he):
        die(f"{st}不提供强调选项，choice 里却带了强调；重新跑 ask.py resolve")
    if len(hn) + len(he) > 2:
        die("重点至多两处（主体与关系合计）")
    ids = {n["id"] for n in nodes}
    for h in hn:
        if h not in ids:
            die(f"重点主体「{h}」不在 relations.json 里")
    for h in he:
        if not isinstance(h, int) or not 0 <= h < len(edges):
            die(f"重点关系编号 {h} 越界")
    return dict(style=st, emphasis=dict(nodes=hn, edges=he), label=c.get("label"))


# ------------------------------------------------------------------ 字排
def text_w(s, fs):
    return sum(fs if ord(c) > 0x2E80 else fs * 0.55 for c in s)


def wrap(s, fs, width):
    """只插断行，不改字。

    优先在空格、斜线、顿号、逗号这类分隔处断；一段本身超宽才逐字断。
    「被上诉人 / 投资方 / 受托人」要断成「被上诉人 / 投资方 /」「受托人」，
    不能断成「…受」「托人」。拉丁词整词不拆。
    """
    import re
    toks = re.findall(r"[^\s/、，,；;]+[\s/、，,；;]*|[\s/、，,；;]+", s)
    lines, cur = [], ""

    def push_long(tok):
        nonlocal cur
        for ch in re.findall(r"[A-Za-z0-9.&'\-]+\s*|.", tok):
            if text_w(cur + ch, fs) <= width or not cur.strip():
                cur += ch
            else:
                lines.append(cur.rstrip())
                cur = ch.lstrip()
    for t in toks:
        if text_w(cur + t.rstrip(), fs) <= width:
            cur += t
        elif text_w(t.rstrip(), fs) <= width:
            if cur.strip():
                lines.append(cur.rstrip())
            cur = t.lstrip()
        else:
            push_long(t)
    if cur.strip():
        lines.append(cur.rstrip())
    return lines or [s]


def node_lines(n, NW):
    inner = NW - 12
    name = wrap(n["name"], FS_NODE, inner)
    note = wrap(n["note"], FS_NOTE, inner) if n.get("note") else []
    return name, note


# ------------------------------------------------------------------ 布局
def layout_key(nodes, edges, tall):
    raw = json.dumps([[n["id"] for n in nodes], [[e["from"], e["to"]] for e in edges], tall],
                     ensure_ascii=False)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def get_layout(nodes, edges, out, relayout):
    from lookup import run
    from mini_render import render as mini
    need_tall = any(len(a) + len(b) > 2 for a, b in (node_lines(n, 140) for n in nodes))
    if need_tall:
        # 只是提示，不改做法：照录原文靠加高模块，不删字
        who = [n["name"] for n in nodes if sum(map(len, node_lines(n, 140))) > 2]
        print("  提示：" + "、".join(who) + " 的名称加备注超过两行，全图改用高模块；"
              "高模块布局实测慢三到四倍，备注能写短就写短")
    key = layout_key(nodes, edges, need_tall)
    cache = os.path.join(out, "layout.json")
    if not relayout and os.path.exists(cache):
        c = json.load(open(cache, encoding="utf-8"))
        if c.get("key") == key:
            print("  布局：复用缓存（主体与关系未变）")
            return c
    E = [(e["from"], e["to"]) for e in edges]
    t = time.time()
    print(f"  布局：{len(nodes)} 个主体 {len(E)} 条关系，开始求解……", flush=True)
    # 求解器要的是带 group 的主体：主体与客体分成两组，同组的自然靠在一起
    solver_nodes = [dict(id=n["id"], name=n["name"], group=n["kind"]) for n in nodes]
    try:
        sc, grid, a, pos, rects, pp, sk, d = run(solver_nodes, E, render=mini,
                                                  force_tall=need_tall)
    except ValueError as e:
        die(str(e), 3)
    c = dict(key=key, grid=list(grid), score=list(sc), rects={k: list(v) for k, v in rects.items()},
             skel=[[list(p) for p in path] for path in sk], node=list(d["node"]),
             tall=bool(d["tall"]), src=d.get("src"), guard=d.get("guard"),
             seconds=round(time.time() - t, 1))
    json.dump(c, open(cache, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"  布局：完成，{c['seconds']}s，网格 {grid[0]}x{grid[1]}，交叉 {sc[0]} 拐弯 {sc[1]}")
    return c


# ------------------------------------------------------------------ 渲染
def render_svg(cf, nodes, edges, hot_n, hot_e, L, path):
    """hot_n 是主体 id 集合，hot_e 是关系序号集合。"""
    from relation_core import rounded
    from label_place import place
    NW, NH = L["node"]
    rects = {k: tuple(v) for k, v in L["rects"].items()}
    skel = [[(x + OX, y + OY) for x, y in p] for p in L["skel"]]
    O, problems = [], []
    for n in nodes:
        x, y = rects[n["id"]][0] + OX, rects[n["id"]][1] + OY
        obj = n.get("kind") == "客体"
        hot = n["id"] in hot_n
        name, note = node_lines(n, NW)
        rows = [(t, FS_NODE, True) for t in name] + [(t, FS_NOTE, False) for t in note]
        lh = {FS_NODE: 17, FS_NOTE: 14}
        total = sum(lh[fs] for _, fs, _ in rows)
        if total > NH - 6:
            problems.append(f"「{n['name']}」的名称与备注共 {len(rows)} 行，模块装不下；"
                            "名称照录不能删，请把备注改短或移入出处索引")
        O.append(f'<g data-role="node"{" data-emph=\"1\"" if hot else ""}>')
        if hot:
            O.append(f'<rect data-kind="node" x="{x}" y="{y}" width="{NW}" height="{NH}" rx="12" fill="{RED}"/>')
        else:
            O.append(f'<rect data-kind="node" x="{x}" y="{y}" width="{NW}" height="{NH}" rx="12" '
                     f'fill="{FILL_OBJ if obj else FILL_SUBJ}" stroke="{EDGE}" stroke-width="1"/>')
        cy = y + (NH - total) / 2
        for t, fs, bold in rows:
            cy += lh[fs]
            col = ("#FFFFFF" if bold else "#E8D5D5") if hot else (INK if bold else MUTED)
            O.append(f'<text x="{x + NW / 2:.0f}" y="{cy - (lh[fs] - fs) / 2 - 1:.0f}" font-size="{fs}" '
                     f'fill="{col}" text-anchor="middle"{" font-weight=\"700\"" if bold else ""}>'
                     f'{esc(t)}</text>')
        O.append("</g>")
    for i, p in enumerate(skel):
        e = edges[i]
        q = list(p)
        dx, dy = q[-1][0] - q[-2][0], q[-1][1] - q[-2][1]
        Ln = math.hypot(dx, dy) or 1
        q[-1] = (q[-1][0] - dx / Ln * ARROW, q[-1][1] - dy / Ln * ARROW)
        hot = i in hot_e
        ds = ' stroke-dasharray="4 3"' if e.get("line") == "虚线" else ""
        O.append(f'<path data-kind="edge" d="{rounded(q)}" fill="none" '
                 f'stroke="{RED if hot else LINE}" stroke-width="{SW_EMPH if hot else SW}"{ds} '
                 f'marker-end="url(#{"ar" if hot else "a"})"/>')
    labels = [e["label"] for e in edges]
    rr = [(rects[n["id"]][0] + OX, rects[n["id"]][1] + OY, NW, NH) for n in nodes]
    lab, failed, _ = place(skel, labels, rr,
                           priority=sorted(hot_e))
    for i, l in enumerate(lab):
        if not l:
            continue
        hot = i in hot_e
        O.append(f'<text x="{l[0]:.0f}" y="{l[1]:.0f}" font-size="{FS_LABEL}" '
                 f'fill="{RED if hot else MUTED}" text-anchor="{l[2]}">{esc(labels[i])}</text>')
    miss = [labels[i] for i, l in enumerate(lab) if not l]
    if miss:
        problems.append("关系名放不下，图上缺失：" + "、".join(miss))
    xs = [v[0] + OX + NW for v in rects.values()] + [x for p in skel for x, _ in p]
    ys = [v[1] + OY + NH for v in rects.values()] + [y for p in skel for _, y in p]
    W, H = int(max(xs)) + OX, int(max(ys)) + 80
    # 关系名也要算进画布。先前只按主体与走线定宽，长关系名的标签
    # 放在右侧外沿时字形越出画布（G12）。只加宽，不挪任何位置。
    for i, l in enumerate(lab):
        if not l:
            continue
        tw = text_w(labels[i], FS_LABEL)
        right = l[0] + (tw / 2 if l[2] == "middle" else (0 if l[2] == "end" else tw))
        W = max(W, int(math.ceil(right)) + 40)
        H = max(H, int(math.ceil(l[1])) + 40)
    title = cf.get("title", "")
    tw = text_w(title, FS_TITLE)
    if tw > W - 60:
        W = int(tw + 120)
    CX = W // 2
    head = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
            f'viewBox="0 0 {W} {H}" font-family="{FONT_STACK}">',
            f'<rect width="{W}" height="{H}" fill="#FFFFFF"/>',
            '<defs><marker id="a" markerWidth="12" markerHeight="8.4" refX="0" refY="4.2" '
            'markerUnits="userSpaceOnUse" orient="auto">'
            f'<path d="M 0 0 L 12 4.2 L 0 8.4 Z" fill="{LINE}"/></marker>'
            '<marker id="ar" markerWidth="12" markerHeight="8.4" refX="0" refY="4.2" '
            'markerUnits="userSpaceOnUse" orient="auto">'
            f'<path d="M 0 0 L 12 4.2 L 0 8.4 Z" fill="{RED}"/></marker></defs>']
    if title:
        head.append(f'<text x="{CX}" y="58" font-family="{TITLE_FONT}" font-size="{FS_TITLE}" '
                    f'font-weight="700" stroke="{INK}" stroke-width="0.3" fill="{INK}" '
                    f'text-anchor="middle">{esc(title)}</text>')
    if cf.get("subtitle"):
        head.append(f'<text x="{CX}" y="86" font-size="{FS_SUB}" fill="{MUTED}" '
                    f'text-anchor="middle">{esc(cf["subtitle"])}</text>')
    open(path, "w", encoding="utf-8").write("\n".join(head + O) + "\n</svg>")
    return problems


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ------------------------------------------------------------------ 出处索引
def provenance(cf, nodes, edges, path):
    out = [f"# 出处索引", "", f"材料：{'、'.join(cf.get('sources', [])) or '未列明'}", ""]
    out += ["## 主体与客体", ""]
    for n in nodes:
        out.append(f"{n['name']}　{n.get('note', '')}　出处：{n.get('source', '未注明')}")
    out += ["", "## 关系", ""]
    for e in edges:
        a = next(n["name"] for n in nodes if n["id"] == e["from"])
        b = next(n["name"] for n in nodes if n["id"] == e["to"])
        out.append(f"{a} → {b}　{e['label']}　出处：{e.get('source', '未注明')}")
    dropped = cf.get("dropped") or {}
    if dropped.get("nodes") or dropped.get("edges"):
        names = {n["id"]: n["name"] for n in nodes + list(dropped.get("nodes") or [])}
        out += ["", "## 未入图（第〇轮精简时未保留）", ""]
        for n in dropped.get("nodes") or []:
            out.append(f"{n['name']}　{n.get('note', '')}　出处：{n.get('source', '未注明')}")
        for e in dropped.get("edges") or []:
            if isinstance(e, (list, tuple)):
                e = dict(zip(("from", "to", "label"), e))
            out.append(f"{names.get(e['from'], e['from'])} → {names.get(e['to'], e['to'])}　"
                       f"{e.get('label', '')}　出处：{e.get('source', '未注明')}")
    unsure = cf.get("unsure") or []
    if unsure:
        out += ["", "## 读不准、待人工确认", ""] + [str(u) for u in unsure]
    open(path, "w", encoding="utf-8").write("\n".join(out) + "\n")


# ------------------------------------------------------------------ 主流程
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("relations", nargs="?")
    ap.add_argument("--out")
    ap.add_argument("--choice", help="ask.py resolve 的输出")
    ap.add_argument("--plan-only", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--relayout", action="store_true")
    ap.add_argument("--name", default=None, help="产物文件名前缀（英文数字），默认取 slug 或 relation")
    a = ap.parse_args()

    if a.check:
        ok, _ = check_env()
        sys.exit(0 if ok else 1)
    if not a.relations:
        die("要给出 relations.json 的路径")
    cf, nodes, edges = load(a.relations)
    from lookup import plan
    d = plan([dict(id=n["id"], name=n["name"], group=n["kind"]) for n in nodes],
             [(e["from"], e["to"]) for e in edges])
    if not d["ok"]:
        # 索引查不到时，lookup 一律报「超出已验证范围（5 到 16）」。
        # 几个模块的小图查不到，多半是图不连通，照原话报会让人去拆图，越拆越不对。
        comp = {n["id"]: n["id"] for n in nodes}

        def _f(x):
            while comp[x] != x:
                x = comp[x]
            return x
        for e in edges:
            comp[_f(e["from"])] = _f(e["to"])
        parts = len({_f(n["id"]) for n in nodes})
        if parts > 1 and len(nodes) <= 6:
            die(f"这 {len(nodes)} 个模块分成了 {parts} 组互不相连，6 个以内的小图须连通；"
                "补上把它们连起来的关系，或分成几张图", 3)
        die(d["reason"], 3)
    print(f"  规模：{len(nodes)} 个主体 {len(edges)} 条关系，结构 {d.get('kind')}，"
          f"查{d.get('src', '结构分档')}")
    if len(edges) > 12 and not cf.get("over12") and len(nodes) <= 9:
        print(f"\n  关系 {len(edges)} 条，超过 12 条。先跑第〇轮：")
        print(f"  python scripts/ask.py trim {a.relations}")
        sys.exit(4)
    if len(nodes) > 9 and not cf.get("over9"):
        # 超过 9 个模块，布局难度与耗时成倍上升（15 个模块在 Windows 上
        # 实测半小时以上）。先走第〇轮让使用者定留哪几个，再出图。
        print(f"\n  模块 {len(nodes)} 个，超过 9 个。先跑第〇轮：")
        print(f"  python scripts/ask.py trim {a.relations}")
        sys.exit(4)
    if a.plan_only:
        return
    if not a.out:
        die("要给出 --out 输出目录")
    choice = load_choice(a.choice, nodes, edges)
    ok, backends = check_env(verbose=False)
    if not ok:
        check_env()
        die("运行环境不全，见上")
    os.makedirs(a.out, exist_ok=True)
    L = get_layout(nodes, edges, a.out, a.relayout)

    import styles, exports, guard_lib, delivery
    st = choice["style"]
    slug = a.name or cf.get("slug") or "relation"
    base = os.path.join(a.out, f"{slug}-{STYLE_SLUG[st]}")
    hot_n, hot_e = set(choice["emphasis"]["nodes"]), set(choice["emphasis"]["edges"])
    master = base + "-master.svg"
    problems = render_svg(cf, nodes, edges, hot_n, hot_e, L, master)
    svg = open(master, encoding="utf-8").read()
    svg = styles.guizang(svg, "graphviz_relation") if st == "歸藏风" else styles.ALL[st](svg)
    open(base + ".svg", "w", encoding="utf-8").write(svg)
    os.remove(master)
    gok, gres = guard_lib.check(base + ".svg")
    files, eguard = exports.export_all(base + ".svg", base, style=st, return_guard=True,
                                       formats=("pptx", "vsdx", "drawio"))
    files["png"] = to_png(base + ".svg", base + ".png", backends)
    emph = "、".join([next(n["name"] for n in nodes if n["id"] == h) for h in choice["emphasis"]["nodes"]] +
                    [edges[h]["label"] for h in choice["emphasis"]["edges"]])
    if not emph:
        emph = None   # 白描、歸藏风不提供强调选项，按选入制写「无（使用者未指定）」
    failed = [x["name"] for x in gres if not x["ok"]]
    warns = [f"{x['name']} {x['msg']}" for x in gres if x.get("warn")]
    text = delivery.summary(files, style=st, emphasis=emph, guard=(gok, "、".join(failed)),
                            scale=f"{len(nodes)} 个主体 {len(edges)} 条关系")
    if warns:
        text += "\n提示：" + "；".join(warns)
    if problems:
        text += "\n须人工处理：" + "；".join(problems)
    lines = [f"[路线判据] {'全部通过' if gok else '未过'}"]
    lines += [f"  {'FAIL' if not x['ok'] else ('WARN' if x.get('warn') else 'OK  ')} {x['name']} {x['msg']}"
              for x in gres]
    for fmt, (ok_, res) in eguard.items():
        lines.append(f"[导出物判据 {fmt}] {'通过' if ok_ else '未过'}")
        lines += [f"  {'OK  ' if o else 'FAIL'} {n_} {m_}" for n_, o, m_ in res]
    open(base + "-checks.txt", "w", encoding="utf-8").write("\n".join(lines) + "\n")
    open(base + "-delivery.txt", "w", encoding="utf-8").write(text + "\n")
    provenance(cf, nodes, edges, os.path.join(a.out, f"{slug}-provenance.md"))
    print()
    print(text)
    print(f"\n产物目录：{os.path.abspath(a.out)}")


if __name__ == "__main__":
    main()
