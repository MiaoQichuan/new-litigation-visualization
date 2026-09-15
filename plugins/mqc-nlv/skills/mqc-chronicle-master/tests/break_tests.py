#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""改坏验证：逐条把底稿改坏，断言对应判据必须报错。
只跑通不算数——不会报错的判据等于没有判据。"""
import json, copy, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent/"scripts"))
from check_facts import check

BASE=json.load(open(Path(__file__).parent/"casefile.json",encoding="utf-8"))
# 子序列核验对照的是该条事实所属材料的全文；M01 这本册子里有三条事实，须给全
SRC={"M01":("出卖人广州某地产公司与买受人某某签订，约定建筑面积128.6㎡，总价款1,286万元；"
            "第8条约定逾期交房违约金按日万分之五计。"
            "委托某某全权办理签约、收款事宜，并授权其代为签署相关文件，加盖公章一枚。"
            "催告十日内交付，逾期即解除合同。")}

CASES=[]
def case(code, desc):
    def deco(fn): CASES.append((code,desc,fn)); return fn
    return deco

@case("C2","事项标题用了表外动词")
def _(d): d["facts"][0]["item"]="缔结《商品房买卖合同》"
@case("C3","标题超过 15 字")
def _(d): d["facts"][0]["item"]="签订《商品房买卖合同及其补充协议与附件》"
@case("C4","标题混入定性词")
def _(d): d["facts"][0]["item"]="签订《商品房买卖合同》构成违约"
@case("C5","书名号不配对")
def _(d): d["facts"][0]["item"]="签订《商品房买卖合同"
@case("B1","主要内容为空")
def _(d): d["facts"][0]["content"]=""
@case("B3","主要内容被改写（非源文子序列）")
def _(d): d["facts"][0]["content"]="双方就涉案房屋达成买卖合意并约定了高额违约责任"
@case("D2","日期精度缺失")
def _(d): d["facts"][1]["date_certainty"]=None
@case("D2","日期精度不在四档内")
def _(d): d["facts"][1]["date_certainty"]="approx"
@case("E1","模型填了判断字段")
def _(d): d["facts"][2]["bold"]=True
@case("E2","模型填了争点归属")
def _(d): d["facts"][2]["iid"]="I1"
@case("E3","关联指向不存在的事实")
def _(d): d["facts"][1]["relations"]=["F999"]
@case("E4","有证据编号却标成仅当事人陈述")
def _(d): d["facts"][0]["evidence_status"]="仅当事人陈述"
@case("E4","无证据编号却标成有书证")
def _(d): d["facts"][5]["evidence_status"]="有书证"
@case("E4","无书证的事实未列入不确定清单")
def _(d): d["uncertainties"]=[]
@case("A1","引用了主体表外的主体")
def _(d): d["facts"][0]["parties"]=["P9"]
@case("A2","同一证据编号跨了多本材料")
def _(d):
    # 必须造出真正的冲突：同一编号出现在两本材料下。
    # 只把一条挪走不会触发——编号对应的材料集合仍只有一个元素。
    dup=json.loads(json.dumps(d["facts"][0])); dup["fid"]="F007"; dup["mid"]="M02"
    d["facts"].append(dup)
@case("A2","缺少页码定位")
def _(d): d["facts"][3]["locator"]=""
@case("C5","材料编号不存在")
def _(d): d["facts"][3]["mid"]="M99"
@case("D1","日期写法与精度不符")
def _(d): d["facts"][0]["date"]="2004-04"          # 声明 exact 却只到月
@case("I1","读图材料的事实却标成 text")
def _(d):
    d["materials"][0]["medium"]="image"; d["facts"][0]["medium"]="text"
@case("E5","new_evidence 不是布尔值")
def _(d): d["facts"][0]["new_evidence"]="是"

ok=json.loads(json.dumps(BASE))
base_r=check(ok,SRC)
print(f"基线（未改坏）：{'干净' if not base_r.errs else '已有 '+str(len(base_r.errs))+' 处错误'}")
if base_r.errs:
    for c,f,m in base_r.errs: print("   ",c,f,m)
    sys.exit(1)

fails=0
for code,desc,mut in CASES:
    d=json.loads(json.dumps(BASE)); mut(d)
    r=check(d,SRC)
    caught=[c for c,_,_ in r.errs]
    hit = code in caught
    print(("  OK  " if hit else "  MISS")+f" {code:<4} {desc}"+("" if hit else f"   ← 未触发，实报 {caught or '无'}"))
    if not hit: fails+=1
print()
print(f"{len(CASES)} 项改坏验证，{len(CASES)-fails} 项触发，{fails} 项漏过")
sys.exit(1 if fails else 0)
