#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""图与表的一致性自检：编号、板块、决定性要件三处必须对得上。"""
import json,re,sys,os
import tempfile as _tempfile
_TMP = _tempfile.gettempdir()   # 不写死 /tmp：Windows 上没有这个目录，自检一跑就找不到文件
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 可跑任意 casefile：写死只跑示例，真案子上的图表不一致就没人查。
# 实测漏过一次——一处要件表里标了决定性、图上却不再强调，示例上看不出来。
src = sys.argv[1] if len(sys.argv)>1 else os.path.join(ROOT,"examples","matrix-input.json")
svgp= sys.argv[2] if len(sys.argv)>2 else os.path.join(_TMP, "_tcm_out", "庭审对抗图.svg")
m=json.load(open(src,encoding="utf-8"))
sys.path.insert(0, os.path.join(ROOT,"scripts"))
from to_figure import convert
n=convert(m)   # 图由表派生，不另存一份
svg=open(svgp,encoding="utf-8").read()
errs=[]
def ck(no,cond,msg):
    print(("  OK  " if cond else "  FAIL")+f" {no}  {msg}")
    if not cond: errs.append(no)

# 图的行组单位是「有争议待证的构成要件」，所以 X1 比的是要件覆盖：
# 表里每一条有争议待证的要件都必须在图上有行组，反之图上不得出现表里没有的。
mdis={e["id"] for p in m["parts"] for cb in p["claim_bases"] for e in cb["elements"]
      if e.get("dispute")=="有争议待证"}
nk={p["id"] for p in n["parts"]}
ck("X1", mdis==nk, f"有争议待证的要件全部进图（表 {sorted(mdis)} ／ 图 {sorted(nk)}）")
mids={e["id"] for p in m["parts"] for cb in p["claim_bases"] for e in cb["elements"]}
ck("X2", all(re.fullmatch(r'P\d-\d',i) for i in mids), f"要件编号统一为 P 字头（{sorted(mids)}）")
fig=set(re.findall(r'>(P\d-\d)[　\s]', svg))
ck("X3", fig<=mids, f"图上出现的要件编号都在表内（图 {sorted(fig)}）")
# 每个行组的标题必须以它所属对抗部分的名称起头，再接该要件名——图上看得出归属
own={e["id"]:(p["label"],e["name"]) for p in m["parts"] for cb in p["claim_bases"] for e in cb["elements"]}
bad=[p["id"] for p in n["parts"]
     if not (p["label"].startswith(own[p["id"]][0]) and p["label"].endswith(own[p["id"]][1]))]
ck("X4", not bad, f"行组标题＝对抗部分名 + 要件名（不符 {bad}）")
dec={e["id"] for p in m["parts"] for cb in p["claim_bases"] for e in cb["elements"] if e["decisive"]=="是"}
emp={p["ref"] for p in n["parts"] if p["center"].get("disputed") and p["center"].get("burden")=="claim"
     and p["center"].get("prospect") in ("低","存疑")}
ck("X5", dec==emp, f"决定性要件两处判定一致（表 {sorted(dec)} ／ 图 {sorted(emp)}）")
# X7 声明未获取的文书，图上必须写成「未获取」，不得写成「无书面记载」
# X7 未获取的文书：图上不得凭空立框，但图底的材料范围必须写明
sc=(m.get("scope") or {}).get("not_obtained") or []
txt="".join(c["body"] for p in n["parts"] for c in p["cards"])
note=n.get("scope_note","")
ck("X7", ("未获取" not in txt) and (not sc or all(x in note for x in sc)),
   f"未获取只写在图底材料范围，不在卡里立框（缺 {[x for x in sc if x not in note]}）")
ck("X6", all(f'分析表 {p["ref"]} 行' in svg for p in n["parts"]), "索引表的「详见」指向表内具体行")
print()
print("  全部通过" if not errs else f"  未通过：{errs}")
sys.exit(1 if errs else 0)
