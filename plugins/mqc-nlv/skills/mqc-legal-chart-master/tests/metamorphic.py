#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""防改差 · 变形测试：从数据自动造几百个标题，一半必须过、一半必须拒。

人写的回归用例总有盲区：修 A 的时候，没人想到去试 B。这里不靠人想，而是按规则批量造：

  对的写法（必须过）            错的写法（必须拒）
  「驳回占 26%」               数字挪一挪：「驳回占 33%」（33 不是任何类目的占比时才算）
  「驳回占26%」「驳回：26%」     主语换一换：「驳回占 41%」（41% 是全额支持的）
  「驳回占２６％」（全角）        方向反一反：「全额支持比驳回少 15 件」
  「驳回 26 件」
  「全额支持比驳回多 15 件」

**拦对的同时不误伤对的**：改规则时最容易只盯着「该拒的拒了没有」，忘了「该过的还过不过」。
这里两边都数，任何一边出一个错就算不过。
"""
import copy
import json
import os
import sys

# 中文 Windows 默认 GBK：不固定成 UTF-8，打印 −、✓ 这类 GBK 没有的字会崩（GBK 模拟环境里实测过）
for _s in (sys.stdout, sys.stderr):
    getattr(_s, "reconfigure", lambda **k: None)(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
EX = os.path.join(ROOT, "examples")

import make                       # noqa: E402
from spec import SpecError, _fmt, derive  # noqa: E402

FW = str.maketrans("0123456789%.", "０１２３４５６７８９％．")
ITEM_CHARTS = ("bar", "hbar", "waffle", "rose")


def verdict(m):
    try:
        _, rep = make.build(m)
        return "accept" if not rep["problems"] else "reject"
    except (SpecError, ValueError):
        return "reject"


def pct_text(v):
    r = round(v, 1)
    return _fmt(int(r)) if float(r).is_integer() else _fmt(r)


def cases_for(name, m):
    """造 (标题, 应当, 说明)。"""
    out = []
    d = derive(copy.deepcopy(m))           # 只算派生数，不走标题校验：校验被改坏时造题不受影响
    if m["chart"] in ITEM_CHARTS:
        items = m["data"]["items"]
        unit = m.get("unit", "")
        tot = sum(i["value"] for i in items)
        shares = {i["id"]: i["value"] / tot * 100 for i in items}
        lab = {i["id"]: str(i["label"]) for i in items}
        pct_data = str(unit).strip() in ("%", "％")
        all_pct = sorted(d["pct"])

        def near_any(x, pool, tol=0.6):
            return any(abs(x - v) <= tol for v in pool)

        for it in items:
            i, L = it["id"], lab[it["id"]]
            if any(ch.isdigit() for ch in L):
                continue                          # 类目名带数字（年份）时造句会和数字核对纠缠，另由人写的用例管
            s = pct_text(shares[i])
            if not pct_data:
                out += [(f"{L}占{s}%", "accept", "占比"), (f"{L}占 {s}%", "accept", "占比·有空格"),
                        (f"{L}：{s}%", "accept", "占比·冒号"), (f"{L}占{s}%".translate(FW), "accept", "占比·全角")]
                v = it["value"]
                out.append((f"{L}{_fmt(v)}{unit}", "accept", "原值"))
                bad = shares[i] + 7.3
                if not near_any(bad, all_pct, 1.0):
                    out.append((f"{L}占{pct_text(bad)}%", "reject", "数字挪了"))
                for o in items:
                    if o["id"] == i or abs(shares[o["id"]] - shares[i]) < 1.0:
                        continue
                    mine = {vv for kk, vv in d["bind"].get(i, set()) if kk == "pct"}
                    if near_any(shares[o["id"]], mine, 0.6):
                        continue
                    if any(ch.isdigit() for ch in lab[o["id"]]):
                        continue
                    out.append((f"{L}占{pct_text(shares[o['id']])}%", "reject", f"主语串到「{lab[o['id']]}」"))
                    break
        # 两两比较：方向
        ok_items = [it for it in items if not any(ch.isdigit() for ch in str(it["label"]))]
        for a in ok_items[:4]:
            for b in ok_items[:4]:
                if a is b or a["value"] == b["value"]:
                    continue
                diff = abs(a["value"] - b["value"])
                more = a["value"] > b["value"]
                right, wrong = ("多", "少") if more else ("少", "多")
                out.append((f"{a['label']}比{b['label']}{right}{_fmt(diff)}{unit}", "accept", "比较·方向对"))
                out.append((f"{a['label']}比{b['label']}{wrong}{_fmt(diff)}{unit}", "reject", "比较·方向反"))
    elif m["chart"] == "dumbbell":
        for it in m["data"]["items"]:
            if not it["from"]:
                continue
            r = it["to"] / it["from"] * 100
            out.append((f"{it['label']}判赔为诉请的{pct_text(r)}%", "accept", "两端之比"))
            bad = r + 9.1
            if not any(abs(bad - v) <= 1.0 for v in d["pct"]):
                out.append((f"{it['label']}判赔为诉请的{pct_text(bad)}%", "reject", "两端之比·数字挪了"))
    # 通用：编一个大数一定拒，紧贴汉字与带空格一样
    for t in ("增长9876%", "增长 9876%", "增长９８７６％"):
        out.append((t, "reject", "编的数"))
    return out


def run(verbose=False):
    total, misses = 0, []
    by_expect = {"accept": 0, "reject": 0}
    for f in sorted(os.listdir(EX)):
        if not f.endswith(".json"):
            continue
        base = json.load(open(os.path.join(EX, f), encoding="utf-8"))
        base.pop("annotations", None)
        if "dataset" in base:                 # 逐件记录的示例：先按 view 算出 data，再照常造题（0.9.8）
            import pivot
            pivot.expand(base)
        for title, want, why in cases_for(f[:-5], base):
            m = copy.deepcopy(base)
            m["title"] = title
            got = verdict(m)
            total += 1
            by_expect[want] += 1
            if got != want:
                misses.append(f"{f[:-5]}：「{title}」应{'过' if want == 'accept' else '拒'}，"
                              f"现在{'过' if got == 'accept' else '拒'}（{why}）")
    return total, by_expect, misses


if __name__ == "__main__":
    t, by, miss = run()
    print(f"变形测试：{t} 条（该过 {by['accept']}、该拒 {by['reject']}），错 {len(miss)} 条")
    for x in miss:
        print("  " + x)
    sys.exit(1 if miss else 0)
