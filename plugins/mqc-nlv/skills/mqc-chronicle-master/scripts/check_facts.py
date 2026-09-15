#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""模型产出的事实行校验器。零第三方依赖。
黄金律：模型读懂意思，代码算和验。这里只做验，一条不成立即拒绝出表。
判据编号对应 references/extraction.md 的 A/B/C/D/E 五组。
"""
import json, re, sys
from pathlib import Path
from collections import defaultdict

REF = Path(__file__).resolve().parent.parent / "references"
VERBS = json.loads((REF/"verbs.json").read_text("utf-8"))["verbs"]
BAN   = json.loads((REF/"ban.json").read_text("utf-8"))["words"]
VERBS_BY_LEN = sorted(VERBS, key=len, reverse=True)

PUNCT = set("，。、；：？！（）《》〈〉【】…—·,.;:?!()<>[]-– \t\n\u3000"
            "\u201c\u201d\u2018\u2019\"'")
def strip_p(s): return "".join(c for c in s if c not in PUNCT)

def is_subsequence(needle, hay):
    """B3：主要内容去标点后必须是源文本去标点后的子序列。"""
    it = iter(hay)
    return all(c in it for c in needle)

class Report:
    def __init__(self): self.errs=[]
    def bad(self, code, fid, msg): self.errs.append((code, fid, msg))
    def dump(self):
        if not self.errs:
            print("  全部通过"); return 0
        for c,f,m in self.errs: print(f"  FAIL {c}  {f}  {m}")
        print(f"\n  共 {len(self.errs)} 处不合规，拒绝出表")
        return 1

def check(cf, sources=None):
    R=Report(); F=cf["facts"]
    mids={m["mid"] for m in cf["materials"]}
    pids={p["pid"] for p in cf["parties"]}
    fids=[f["fid"] for f in F]

    for f in F:
        fid=f["fid"]; t=f.get("item","")
        # C 事项标题
        if not next((x for x in VERBS_BY_LEN if t.startswith(x)), None):
            R.bad("C2",fid,f"动词不在封闭表内：{t}（补 verbs.json，不得自行造词）")
        if len(t)>15: R.bad("C3",fid,f"标题 {len(t)} 字，超过 15 字：{t}")
        hit=[w for w in BAN if w in t]
        if hit: R.bad("C4",fid,f"标题含定性词 {hit}：{t}")
        if t.count("《")!=t.count("》"): R.bad("C5",fid,f"书名号不配对：{t}")
        # B 主要内容
        c=f.get("content","")
        if not c: R.bad("B1",fid,"主要内容为空")
        if sources and f.get("mid") in sources:
            if not is_subsequence(strip_p(c), strip_p(sources[f["mid"]])):
                R.bad("B3",fid,"主要内容不是源文本的子序列（疑似改写或概括）")
        # D 日期
        dc=f.get("date_certainty")
        if dc not in ("exact","month","year","range"):
            R.bad("D2",fid,f"日期精度缺失或非四档之一：{dc}")
        else:
            d=f.get("date","")
            pat={"exact":r"^\d{4}-\d{2}-\d{2}$","month":r"^\d{4}-\d{2}$",
                 "year":r"^\d{4}$","range":r"^\d{4}-\d{2}-\d{2}/\d{4}-\d{2}-\d{2}$"}[dc]
            if not re.fullmatch(pat,d):
                R.bad("D1",fid,f"日期写法与精度不符：{dc} 档应形如 {pat}，实为 {d!r}")
        # 图像来源：medium 必须与材料一致，且必须能在产物上标明
        med=f.get("medium")
        mm=next((m for m in cf["materials"] if m["mid"]==f.get("mid")),None)
        if med not in (None,"text","image"):
            R.bad("I1",fid,f"medium 非法：{med}")
        if mm and med and mm.get("medium") in ("image","transcript") and med!="image":
            R.bad("I1",fid,f"材料 {mm['mid']} 是读图来源，事实的 medium 应为 image，实为 {med}")
        if not isinstance(f.get("new_evidence",False),bool):
            R.bad("E5",fid,f"new_evidence 必须是布尔值，实为 {f.get('new_evidence')!r}")
        # E 模型不作判断
        if f.get("iid") not in (None,""):
            R.bad("E2",fid,"争点归属须留空，由律师在母表内填写")
        for k in ("bold","emphasis","favourable","stance"):
            if f.get(k) not in (None,"",False):
                R.bad("E1",fid,f"模型不得填写判断字段：{k}")
        exp = "有书证" if f.get("evidence_no") else "仅当事人陈述"
        if f.get("evidence_status")!=exp:
            R.bad("E4",fid,f"证据状态须由有无证据编号机械决定：应为 {exp}，实为 {f.get('evidence_status')}")
        # 引用完整性
        if f.get("mid") not in mids: R.bad("C5",fid,f"材料编号不存在：{f.get('mid')}")
        if not f.get("locator"): R.bad("A2",fid,"缺少页码或段落定位")
        if not set(f.get("parties",[]))<=pids: R.bad("A1",fid,"引用了主体表外的主体")
        if not set(f.get("relations",[]))<=set(fids): R.bad("E3",fid,"关联指向不存在的事实")

    # A2 同一份证据切成多条时，各条须共用同一材料编号（mid 是册子级，evidence_no 是证据级）
    by=defaultdict(set)
    for f in F:
        if f.get("evidence_no"): by[f["evidence_no"]].add(f.get("mid"))
    for no,ms in by.items():
        if len(ms)>1: R.bad("A2",no,f"同一证据编号跨了多本材料：{sorted(ms)}")
    # E4 无书证者必须进不确定清单
    un={u["fid"] for u in cf.get("uncertainties",[])}
    for f in F:
        if f["evidence_status"]=="仅当事人陈述" and f["fid"] not in un:
            R.bad("E4",f["fid"],"无书证的事实未列入不确定清单")
    # 这里一度加过一条 E6：同一句 why 重复出现即判为套话。
    # 示例数据当场证伪——两次交付设备都缺交付单据，两条事实写同一句说明是正当的。
    # 重复不等于套话，判据不成立，撤回。真正的套话问题由「证据编号那一类不出注」解决。
    return R

if __name__=="__main__":
    cf=json.load(open(sys.argv[1],encoding="utf-8"))
    src=json.load(open(sys.argv[2],encoding="utf-8")) if len(sys.argv)>2 else None
    print(f"校验 {sys.argv[1]}（{len(cf['facts'])} 条事实）")
    sys.exit(check(cf,src).dump())
