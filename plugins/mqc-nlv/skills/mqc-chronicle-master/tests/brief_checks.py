#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""简表自检。图是呈报给法官或当事人的，错在这里没有第二道关。
判据读产物或读版面数学，不读源码里写了什么。输入是 渲染输入.json。"""
import os, re, sys, json, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import build_brief as B

errs = []
def ck(no, cond, msg):
    print(("  OK  " if cond else "  FAIL") + f" {no}  {msg}")
    if not cond: errs.append(no)

def run(ri):
    out = tempfile.mkdtemp()
    svgs = B.build(ri, out)
    D = json.load(open(ri, encoding="utf-8"))
    rows = D.get("rows") or []
    blob = "".join(open(p, encoding="utf-8").read() for p in svgs)
    txt = re.sub(r"<[^>]+>", "", blob)

    ck("M1", sum(w for _, w in B.COLS) == B.AVAIL,
       f"列宽之和等于可用宽（{sum(w for _, w in B.COLS)} / {B.AVAIL}）")
    ck("M4", all('width="210mm"' in open(p, encoding="utf-8").read() and
                 'height="297mm"' in open(p, encoding="utf-8").read() for p in svgs),
       "每页都是 A4 竖版 210×297mm")
    ck("M5", blob.count(f'rx="{B.RX}"') == len(svgs),
       f"每页一个圆角外框（{blob.count(chr(114)+chr(120)+chr(61))} 处 rx）")

    miss = [r["item"][:10] for r in rows if r["item"][:8] not in txt]
    ck("B1", not miss, f"事项一条不漏地进图（缺 {miss[:4]}）")

    # 日期的一致性改由出图前自证盯（build_brief 里的 B2）：
    # 区间日期会折行，扫拼接文本查不准，真材料上当场误报过。

    # 主要内容是按句读取的，所以必须是原文的前缀——取到哪算哪，但不能换成别的字。
    # 末尾那个句号是收句时补的，比对前先去掉。
    norm = lambda t: "".join(str(t).split())
    bad3 = []
    for r in rows:
        full = norm(r.get("content", ""))
        got = norm("".join(B.Row._brief(r.get("content", ""))))
        if not full:
            continue
        if not (full.startswith(got) or full.startswith(got.rstrip("。"))):
            bad3.append(r["item"][:8])
    ck("B3", not bad3, f"主要内容是原文的前缀，只少取不改写（不合 {bad3[:4]}）")

    # 序号是 1 起的连号，不是 F001 这类内部编号
    ck("N1", "F00" not in txt and all(str(i) in txt for i in range(1, min(len(rows), 9) + 1)),
       "序号用 1、2、3，不出现底稿内部编号")

    # 字体分族：中文宋体、英文数字新罗马，各走各的
    zh = re.findall(r'font-family="宋体">([^<]*)<', blob)
    la = re.findall(r'font-family="Times New Roman">([^<]*)<', blob)
    bad_zh = [t for t in zh if re.fullmatch(r"[0-9A-Za-z.\-/%]+", t or "x")]
    bad_la = [t for t in la if re.search(r"[\u4e00-\u9fff]", t or "")]
    ck("F1", not bad_zh and not bad_la and la,
       f"中文走宋体、英文数字走新罗马（错置 {(bad_zh + bad_la)[:3]}）")

    # 全图的红只用在分组标题的色块上，别处一处都不许有
    reds = re.findall(r'fill="#991B1B"', blob)
    groups = len({str(r.get("issue", "")).strip() or "未归入争点" for r in rows}) \
        if any(str(r.get("issue", "")).strip() for r in rows) else 0
    ck("C1", len(reds) == groups,
       f"红只用在分组色块：应 {groups} 处，图上 {len(reds)} 处")


    # 呈报件：主要内容取到完整句读为止，不出现省略号，也不带内部痕迹
    over = [r["item"][:8] for r in rows
            if len(B.Row._brief(r.get("content", ""))) > B.HARD_MAX]
    ck("T1", not over, f"主要内容不超过硬上限 {B.HARD_MAX} 行（超出 {over[:3]}）")

    half = [r["item"][:8] for r in rows
            if "".join(B.Row._brief(r.get("content", ""))).strip()[-1:] not in "。！？"]
    ck("T2", not half, f"主要内容一律以句号收尾，没有半句话、没有分号结尾（不合 {half[:3]}）")

    # 只列确实由我们生成的内部标记。「未见书证」这类词律师可能写在原文里
    # （实测底稿中就有「（未见书证，据当事人陈述）」），拿它去比会误报。
    # 直角引号「」不是大陆法律文书的写法，正文里一处都不许有
    ck("T4", "「" not in txt and "」" not in txt,
       "图上不出现直角引号")

    LEAK = ("……", "Word", "Excel", "母表", "交付版", "节录",
            "本程序新证据", "逐字核验")
    hit = [k for k in LEAK if k in txt]
    ck("T3", not hit, f"呈报件上不出现省略号与内部痕迹（命中 {hit}）")

    ck("P1", all(f"第 {i} 页 / 共 {len(svgs)} 页" in
                 re.sub(r"<[^>]+>", "", open(svgs[i-1], encoding="utf-8").read())
                 for i in range(1, len(svgs) + 1)),
       f"每页都标了页码（共 {len(svgs)} 页）")
    return svgs

def main():
    ri = sys.argv[1] if len(sys.argv) > 1 else None
    if not ri:
        import subprocess
        ri = os.path.join(tempfile.mkdtemp(), "ri.json")
        subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "to_render.py"),
                        os.path.join(ROOT, "tests", "casefile.json"), ri],
                       capture_output=True, check=True)
    run(ri)

    # 改坏验证：标题不折行，撑长它必然越出版心，M3 必须拦下
    d = json.load(open(ri, encoding="utf-8"))
    d["case"]["title"] = d["case"].get("title", "") + "（" + "超长案件名称" * 8 + "）"
    p = os.path.join(tempfile.mkdtemp(), "bad.json")
    json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False)
    try:
        B.build(p, tempfile.mkdtemp()); caught = False
    except AssertionError:
        caught = True
    ck("M3", caught, "文字越出版心会被出图前自证拦下")

    print()
    print("  全部通过" if not errs else f"  未通过：{sorted(set(errs))}")
    return 1 if errs else 0

if __name__ == "__main__":
    sys.exit(main())
