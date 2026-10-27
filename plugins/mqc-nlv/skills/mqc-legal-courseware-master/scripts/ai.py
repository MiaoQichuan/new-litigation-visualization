#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""编辑器 ↔ 对话里的 AI：请求队列。

用户在编辑器里点「让 AI 生成」，写一句想法，编辑器把请求记进 <课件目录>/ai/requests.json；
对话里的 AI（就是读这份 SKILL.md 的模型）用下面的命令取请求、写内容、交回；编辑器发现课件变了就自动刷新（可撤销）。
AI 在对话里跑，所以能调用 V1–V6 出图，也能读用户给的材料；编辑器本身不联网、不需要 API key。

    python3 scripts/ai.py <课件目录> wait [--timeout 90]    等一阵新请求（编辑器里显示「AI 在等」）
                                                       等的时间别超过 Agent 单条命令的时限（常见 2–10 分钟）。没等到（退出码 4）就收尾，
                                                       不要一遍遍再 wait：用户在编辑器里提了请求，会回对话里说「处理课件请求」
    python3 scripts/ai.py <课件目录> list [--all]           列出请求（含要改的那一页的现状、律所名片摘要）
    python3 scripts/ai.py <课件目录> take <id>              开始做（编辑器里显示「AI 正在做」）
    python3 scripts/ai.py <课件目录> apply <id> <结果.json | ->   交回结果（先校验，过了才写进课件）
    python3 scripts/ai.py <课件目录> fail <id> --note "原因"     做不了（告诉用户为什么）
    python3 scripts/ai.py <课件目录> done <id> --note "说明"     收尾（apply 后还有改不了的，例如缺用户的原文）

apply 后打印「还要改」时，请求仍是「正在做」：改好后对同一个请求再 apply（加页类会换掉上次加的那几页）。

结果的写法（apply）：
  kind = module / tool        {"module": {字段…}}           并进目标模块（不写 x/y/w/h 就不动位置）
  kind = page / cover         {"modules": [模块…]}          换掉这一页的模块（按网格写坐标）
  kind = new-page / deck      {"slides": [{"modules": […]}, …]}   插在这一页后面（id 自动编）
  另可加 "note": "给用户的一句话"，"assets": {"文件名": "内容"}（V6 图表说明 .json 写进 assets/）

退出码：0 成功；1 用法或校验错；4 等待超时。

做完就停（0.9.0，缪律师实测）：原来写「做完回到 wait 等下一条」，AI 就一直空等、不收尾，用户看到的是「反反复复搞了半天没有结论」。
现在：处理完待办的请求就在对话里告诉用户做好了什么、还缺什么，然后结束这一轮。
"""
import argparse
import datetime
import json
import os
import sys
import time

import paths  # noqa: F401
import deck as D
import grid as G
import brand as B
import safewrite as W

KINDS = {
    "page": "按想法重做这一页",
    "new-page": "按想法加一页",
    "cover": "生成封面",
    "module": "写 / 重写这张卡",
    "tool": "用 V1–V6 出一张图放进这张卡",
    "deck": "按想法生成几页（大纲）",
}
TOOLS = {
    "V1": "mqc-litigation-visual-redraw（诉讼可视化重画）",
    "V2": "mqc-timeline-master（时间轴大师）",
    "V3": "mqc-legal-relation-master（法律关系图大师）",
    "V4": "mqc-chronicle-master（大事记表大师，出 A4 简表 SVG）",
    "V5": "mqc-trial-confrontation-master（庭审对抗图大师）",
    "V6": "mqc-legal-chart-master（法律图表大师，出图表说明 JSON）",
}
STATUSES = ("pending", "working", "done", "failed", "cancelled")
LISTEN = "listening.json"        # AI 正在 wait 时写下「等到几点」；编辑器据此显示「AI 在等」或「回对话里说一声」


class AIError(ValueError):
    pass


def qpath(folder):
    return os.path.join(folder, "ai", "requests.json")


def load_q(folder):
    p = qpath(folder)
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8-sig") as f:
        return json.load(f)


def save_q(folder, q):
    """调用方持着 W.lock(folder)：读—改—写整段不被别处插进来。"""
    p = qpath(folder)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    W.write_text(p, json.dumps(q[-200:], ensure_ascii=False, indent=1))


def now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def add(folder, kind, slide=None, module=None, tool=None, prompt=""):
    """编辑器调用：记一条请求。返回请求。"""
    if kind not in KINDS:
        raise AIError(f"不认识的请求 {kind!r}")
    if kind == "tool" and tool not in TOOLS:
        raise AIError("要写清用 V1–V6 里的哪一个")
    prompt = str(prompt or "").strip()[:2000]
    deck = D.load(os.path.join(folder, "deck.json"))
    ids = [s["id"] for s in deck["slides"]]
    if kind not in ("deck",) and slide not in ids:
        raise AIError("没有这一页")
    if kind in ("module", "tool"):
        s = deck["slides"][ids.index(slide)]
        if not any(m["id"] == module for m in s["modules"]):
            raise AIError("这一页没有这张卡")
    with W.lock(folder):
        q = load_q(folder)
        n = 1 + max([int(r["id"][1:]) for r in q if r["id"][1:].isdigit()] or [0])
        r = {"id": f"r{n}", "created": now(), "status": "pending", "kind": kind, "slide": slide, "module": module,
             "tool": tool, "prompt": prompt}
        q.append(r)
        save_q(folder, q)
    return r


def set_status(folder, rid, status, note=None, **extra):
    with W.lock(folder):
        q = load_q(folder)
        r = next((x for x in q if x["id"] == rid), None)
        if not r:
            raise AIError(f"没有请求 {rid}")
        r["status"] = status
        r["updated"] = now()
        if note is not None:
            r["note"] = str(note)[:500]
        r.update(extra)
        save_q(folder, q)
    return r


def context(folder, r):
    """给 AI 看的上下文：课件概况、这一页的现状、律所名片摘要、该遵守的规矩。"""
    deck = D.load(os.path.join(folder, "deck.json"))
    b = B.load(folder)
    ids = [s["id"] for s in deck["slides"]]
    out = {"request": r, "deck": {"title": deck["title"], "style": deck["style"], "pages": len(ids),
                                  "outline": [_summary(s) for s in deck["slides"]]}}
    if r.get("slide") in ids:
        i = ids.index(r["slide"])
        out["page_no"] = i + 1
        out["page"] = deck["slides"][i]
        if r.get("module"):
            out["target"] = next((m for m in out["page"]["modules"] if m["id"] == r["module"]), None)
    out["brand"] = {"firm": (b.get("firm") or {}).get("name"), "lawyers": [l.get("name") for l in b.get("lawyers") or []],
                    "has_logo": bool(b.get("logo"))}
    out["assets"] = sorted(os.listdir(os.path.join(folder, "assets"))) if os.path.isdir(os.path.join(folder, "assets")) else []
    out["rules"] = ("按 SKILL.md 第二节写模块（12×6 网格、整数格子、不写颜色字号）；法条与裁判要旨只照录用户材料或官方来源，"
                    "拿不到原文就留空并在 note 里说明，案号不编；数字只许算不许编；整套风格 " + deck["style"])
    if out.get("target"):
        t = out["target"]
        x, y, w, h = G.px(t, G.geom(deck.get("frame")))
        pad = 0 if G.tone_of(t) == "bare" else D.PAD.get(t["type"], D.PAD_DEFAULT)
        out["target_box"] = {"w": round(w - 2 * pad), "h": round(h - 2 * pad),
                             "hint": "图会等比缩进这个框；缩完最小的字要 ≥ 11px（V6 图按这个尺寸重画）"}
    t = out.get("target") or {}
    if t.get("recipe"):                                 # 图表库放进来的：带上这个场景要回答的问题
        rc = next((x for x in _recipes() if x["id"] == t["recipe"]), None)
        if rc:
            out["recipe"] = dict(rc, how=f"按这个场景要回答的问题，用用户的材料写 V6 图表说明（chart 用 {rc['form']}），"
                                         "换掉图卡里的示例数据；标题里的数字要能由数据推出。缺材料就 fail 并说清要什么"
                                         + (f"；特有守卫：{rc['guard']}" if rc.get("guard") else ""))
    if r.get("kind") == "tool":
        sk = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..",
                                           TOOLS[r["tool"]].split("（")[0], "SKILL.md"))
        if r["tool"] == "V6" and not os.path.exists(sk):     # 单独安装时 V6 随包在 vendor/v6
            sk = os.path.normpath(os.path.join(paths.V6, "..", "SKILL.md"))
        out["tool"] = {"name": r["tool"], "skill": TOOLS[r["tool"]], "skill_md": sk if os.path.exists(sk) else None,
                       "how": "按那个模块的 SKILL.md 出图；V1–V5 交 SVG 放进 assets/，V6 交图表说明 JSON 放进 assets/；"
                              "V2、V3 出图旁边的 <名>-trace.json（出处记录）一起放进 assets/，编辑器里悬停看出处、写进演讲者备注都靠它；V3 出图加 --shape wide（横版，放进课件页才看得清）；"
                              "再 apply {\"module\": {\"file\": \"assets/…\"}}。风格要与课件一致"}
    # 怎么交回：写法与照抄就能跑的命令都随请求给出，读上下文的模型不必回头翻 SKILL.md
    out["answer"] = {"format": ANSWER.get(r.get("kind"), ""), "note": '可加 "note": "给用户的一句话"',
                     "take": _cmd(folder, "take", r["id"]), "apply": _cmd(folder, "apply", r["id"], "结果.json"),
                     "fail": _cmd(folder, "fail", r["id"], "--note", '"做不了的原因"'),
                     "then": "apply 打印「还要改」就改好再对同一个请求 apply；做完就停：在对话里告诉用户做好了什么、还缺什么，"
                             "结束这一轮。不要一遍遍 wait 空等——用户再提请求，会回对话里说「处理课件请求」"}
    return out


def _recipes():
    try:
        import studio
        return studio.chart_library()["recipes"]
    except Exception:
        return []


def _cmd(folder, *args):
    """给 AI 照抄的命令：脚本与课件都写真实路径，在哪个目录里跑都对。"""
    q = lambda x: f'"{x}"' if (" " in x or not x.isascii()) else x      # noqa: E731
    return " ".join(["python3", q(os.path.abspath(__file__)), q(os.path.abspath(folder))] + [str(x) for x in args])


ANSWER = {
    "module": '{"module": {字段…}}：并进目标卡片（不写 x/y/w/h 就不动位置）',
    "tool": '先按 tool.skill_md 出图，V1–V5 的 SVG 或 V6 的图表说明写进 assets/（也可放进结果的 "assets": {"x.json": …}），'
            '再交 {"module": {"file": "assets/x…"}}',
    "page": '{"modules": [模块…]}：换掉这一页（按 12×6 网格写坐标）',
    "cover": '{"modules": [模块…]}：换掉这一页（按 12×6 网格写坐标）',
    "new-page": '{"slides": [{"modules": […]}, …]}：插在这一页后面',
    "deck": '{"slides": [{"modules": […]}, …]}：插在这一页后面',
}


def _summary(s):
    mods = s.get("modules") or []
    t = next((m.get("text") for m in mods if m["type"] == "title"), "")
    return {"id": s["id"], "title": t, "modules": [G.TYPES[m["type"]]["zh"] for m in mods]}


def _fresh_ids(mods, taken=()):
    seen = set(taken)
    out = []
    for m in mods:
        m = dict(m)
        if not m.get("id") or m["id"] in seen:
            m["id"] = G.new_id(out + [{"id": x} for x in seen])
        seen.add(m["id"])
        out.append(m)
    return out


def apply(folder, rid, result):
    """校验后写进课件。返回 (请求, 拼页报告里的问题列表)。不过校验就抛 AIError，课件不动。

    拼出来还有要改的（大数字推不出、法条没写原文……）：照样写进去让用户看见，但请求留在「正在做」，
    AI 改好后对**同一个请求**再交一次——加页类的请求会换掉上次加的那几页，不会越加越多；
    改不了（缺用户的材料）就 `done` 并在 note 里说明。原来写进去就算「做好了」，再交被拒，「改到没有为止」做不到。"""
    with W.lock(folder):
        return _apply_locked(folder, rid, result)


def _apply_locked(folder, rid, result):
    q = load_q(folder)
    r = next((x for x in q if x["id"] == rid), None)
    if not r:
        raise AIError(f"没有请求 {rid}")
    if r["status"] in ("done", "cancelled"):
        raise AIError(f"请求 {rid} 已经是 {r['status']}")
    path = os.path.join(folder, "deck.json")
    deck = D.load(path)
    ids = [s["id"] for s in deck["slides"]]
    i = ids.index(r["slide"]) if r.get("slide") in ids else len(ids) - 1
    assets = result.get("assets") or {}
    for name in assets:
        if not D_SAFE(name):
            raise AIError(f"素材文件名 {name!r} 不合规：只许 ASCII 的 .json / .svg")
    # 素材要先写下去，拼页才读得到；但结果没过校验时要原样换回——原来先写后验，验不过说「课件没改」，
    # 同名的素材却已被换掉，别的页在用的图悄悄变了（开源前第三轮实跑撞到）
    backups = {}
    for name, content in assets.items():
        p = os.path.join(folder, "assets", name)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        backups[p] = open(p, "rb").read() if os.path.exists(p) else None
        W.write_text(p, content if isinstance(content, str) else json.dumps(content, ensure_ascii=False, indent=1))
    try:
        return _apply_rest(folder, rid, r, result, deck, ids, i, path)
    except Exception:
        for p, old in backups.items():
            if old is None:
                os.replace(p, p + ".nlv-rejected")        # 新加的素材：挪开（不靠删除；选图里不列 .nlv-rejected）
            else:
                W.write_bytes(p, old)
        raise


def _apply_rest(folder, rid, r, result, deck, ids, i, path):
    k = r["kind"]
    touched = []
    if k in ("module", "tool"):
        patch = dict(result.get("module") or {})
        if not patch:
            raise AIError("结果里要有 module")
        s = deck["slides"][i]
        m = next((m for m in s["modules"] if m["id"] == r["module"]), None)
        if not m:
            raise AIError("目标卡片已经不在了（用户可能删了它）")
        patch.pop("id", None)
        if patch.get("spec"):
            m.pop("file", None)
        if patch.get("file"):
            m.pop("spec", None)
        if patch.get("spec") or patch.get("file"):
            m.pop("sample", None)                       # 图表库放进来的示例数据换成了用户的：不再拦导出
        m.update(patch)
        touched = [i]
    elif k in ("page", "cover"):
        mods = result.get("modules")
        if not isinstance(mods, list) or not mods:
            raise AIError("结果里要有 modules（这一页的模块列表）")
        deck["slides"][i]["modules"] = _fresh_ids(mods)
        touched = [i]
    elif k in ("new-page", "deck"):
        slides = result.get("slides")
        if not isinstance(slides, list) or not slides:
            raise AIError("结果里要有 slides（新页列表）")
        made = [x for x in (r.get("made") or []) if x in ids]
        if made:                                        # 同一个请求再交：换掉上次加的那几页，不越加越多
            i = ids.index(made[0]) - 1
            deck["slides"] = [s for s in deck["slides"] if s["id"] not in made]
            ids = [s["id"] for s in deck["slides"]]
        taken = set(ids) | set(made)
        new = []
        for s in slides:
            n = len(taken) + 1
            while f"s{n}" in taken:
                n += 1
            taken.add(f"s{n}")
            new.append({"id": f"s{n}", "modules": _fresh_ids(s.get("modules") or [])})
        deck["slides"][i + 1:i + 1] = new
        touched = list(range(i + 1, i + 1 + len(new)))
    else:
        raise AIError(f"不认识的请求类型 {k}")
    try:
        D.validate(deck, folder)
    except D.DeckError as e:
        raise AIError("结果没过校验，课件没改：\n" + str(e))
    problems = []
    for t in touched:
        problems += D.compose(deck, t, folder, {})[1]["problems"]
    W.write_text(path, json.dumps(deck, ensure_ascii=False, indent=1))
    made = [deck["slides"][t]["id"] for t in touched] if k in ("new-page", "deck") else []
    if problems:
        left = f"写进去了，还有 {len(problems)} 处要改"
        r = set_status(folder, rid, "working", f"{result['note']}（{left}）" if result.get("note") else left, made=made)
    else:
        r = set_status(folder, rid, "done", result.get("note") or "已完成", made=made)
    return r, problems


def D_SAFE(name):
    import re
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,80}\.(json|svg)", name))


def _listen(folder, until):
    try:
        os.makedirs(os.path.join(folder, "ai"), exist_ok=True)
        W.write_text(os.path.join(folder, "ai", LISTEN), json.dumps({"until": until}))
    except OSError:
        pass                                            # 只影响编辑器里的提示，不影响请求本身


def listening(folder):
    """AI 此刻是否在 wait（编辑器据此提示）。"""
    try:
        with open(os.path.join(folder, "ai", LISTEN), encoding="utf-8") as f:
            return float(json.load(f).get("until") or 0) > time.time()
    except (OSError, ValueError, AttributeError, TypeError):
        return False


def pending(folder):
    return [r for r in load_q(folder) if r["status"] == "pending"]


def main(argv=None):
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="编辑器 ↔ 对话里的 AI：请求队列")
    ap.add_argument("folder")
    ap.add_argument("cmd", choices=("wait", "list", "take", "apply", "fail", "done"))
    ap.add_argument("rid", nargs="?")
    ap.add_argument("result", nargs="?")
    ap.add_argument("--timeout", type=int, default=90)   # 0.9.0：原 900 秒超过多数 Agent 的命令时限，会被中途掐掉
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--note")
    a = ap.parse_args(argv)
    folder = os.path.abspath(a.folder)
    try:
        if a.cmd in ("wait", "list"):
            if a.cmd == "wait":
                t0 = time.time()
                _listen(folder, t0 + a.timeout)
                try:
                    while not pending(folder):
                        if time.time() - t0 > a.timeout:
                            print("等了一阵，没有新请求。请在对话里告诉用户：在编辑器里提了请求后，回到对话说「处理课件请求」。"
                                  "不要再 wait 空等，结束这一轮。")
                            return 4
                        time.sleep(1.0)
                finally:
                    _listen(folder, 0)
            rs = load_q(folder) if a.all else pending(folder)
            print(json.dumps([context(folder, r) for r in rs], ensure_ascii=False, indent=1))
            return 0
        if not a.rid:
            raise AIError("要写请求 id")
        if a.cmd == "take":
            print(json.dumps(set_status(folder, a.rid, "working"), ensure_ascii=False))
            return 0
        if a.cmd in ("fail", "done"):
            print(json.dumps(set_status(folder, a.rid, "failed" if a.cmd == "fail" else "done", a.note), ensure_ascii=False))
            return 0
        if a.cmd == "apply":
            raw = sys.stdin.read() if a.result in (None, "-") else open(a.result, encoding="utf-8-sig").read()
            r, problems = apply(folder, a.rid, json.loads(raw))
            print(f"已写进课件：{r['id']}（{KINDS[r['kind']]}）")
            for p in problems:
                print("  还要改　" + p)
            if problems:
                print(f"请求 {r['id']} 仍是「正在做」：改好后对同一个请求再 apply 一次（会换掉这次写进去的内容）；"
                      f"改不了（例如缺用户的原文）就：{_cmd(folder, 'done', r['id'])} --note \"缺什么、请用户做什么\"")
            return 0
    except (AIError, D.DeckError, B.BrandError, ValueError, OSError) as e:
        print(str(e), file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    sys.exit(main())
