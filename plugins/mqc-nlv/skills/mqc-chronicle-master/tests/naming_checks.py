#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""下游 skill 的叫法必须与它自己的名字一致。

起因：大事记表大师的文档里有 6 处把「庭审对抗图大师」写成「攻防图大师」。
那个 skill 的目录名是 mqc-trial-confrontation-master，SKILL.md 自称「庭审对抗图大师」，
两套叫法并存时，模型照文档去找一个并不存在的技能。

注意区分：「四段攻防」「攻防路径」「攻防着力点」是这一行本来的说法，不在此列，
只有**指代那个 skill** 的叫法要统一。
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILLS = os.path.dirname(os.path.dirname(HERE))
BAD = ("攻防图大师", "与攻防图的母表", "与攻防图一致")
OFFICIAL = "庭审对抗图大师"

if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    hits = []
    for root, dirs, files in os.walk(SKILLS):
        if "__pycache__" in root:
            continue
        for f in files:
            if not f.endswith((".md", ".py", ".json", ".txt")):
                continue
            p = os.path.join(root, f)
            if os.path.abspath(p) == os.path.abspath(__file__):
                continue          # 判据表里本来就写着那几个旧叫法，别把自己算进去
            try:
                s = open(p, encoding="utf-8").read()
            except Exception:
                continue
            for b in BAD:
                if b in s:
                    hits.append(f"{os.path.relpath(p, SKILLS)}：{b}")
    own = open(os.path.join(SKILLS, "mqc-trial-confrontation-master", "SKILL.md"),
               encoding="utf-8").read()
    if OFFICIAL not in own:
        hits.append("mqc-trial-confrontation-master/SKILL.md 里没有自称「庭审对抗图大师」")
    for h in hits:
        print("  FAIL  " + h)
    print("命名一致性：" + ("全部通过" if not hits else f"{len(hits)} 处未过"))
    sys.exit(1 if hits else 0)
