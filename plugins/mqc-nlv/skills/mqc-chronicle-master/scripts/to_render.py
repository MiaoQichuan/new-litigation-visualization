#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""底稿 → 两个生成器的渲染输入。底稿是唯一事实来源，这里只做映射，不新增内容。"""
import json, sys, re
CF=json.load(open(sys.argv[1],encoding="utf-8"))
M={m["mid"]:m for m in CF["materials"]}
def DATE(d,c):
    """四档精度各自的写法。区间档此前掉进 else 被错标为「仅到年」。"""
    dot=lambda x: x.replace("-",".")
    if c=="exact": return dot(d)
    if c=="month": return dot(d)+"（仅到月）"
    if c=="year":  return dot(d)+"（仅到年）"
    if c=="range":
        a,_,b=d.partition("/")
        return f"{dot(a)}至{dot(b)}"
    raise ValueError(f"未知日期精度：{c}")

# 不确定清单里「没有证据编号」这一类不出注：证据状态已由有无证据编号机械算出，
# 备注里也已经写了「未见书证」，再出一条尾注说同一件事，六条事实就是六条同样的话。
SKIP_UNCERTAIN = ("证据编号",)

def mat_name(m):
    """展示用的材料名：去掉扩展名，也去掉上传环境加的时间戳前缀。
    律师看到的该是「民事起诉状」，不是一串文件名。
    要用更规范的名称，直接改 casefile 的 materials[].name，这里原样呈现。"""
    n = re.sub(r"^\d{10,}[_-]", "", m["name"])
    return re.sub(r"\.(pdf|docx|doc|jpe?g|png|txt|md)$", "", n, flags=re.I)

ends=[]; rows=[]
for f in CF["facts"]:
    m=M[f["mid"]]
    src = f["evidence_no"] or mat_name(m)
    party = m.get("submitted_by") or ""
    parts=[f"{src}（{party}）" if party else src]
    if f.get("iid"): parts.append(f["iid"])
    rel=f.get("relations") or []
    if rel:
        tgt=[x for x in CF["facts"] if x["fid"] in rel]
        short="、".join(DATE(t["date"],t["date_certainty"]).split("（")[0] for t in tgt)
        parts.append("关联："+short)
    flags=[]
    if f.get("new_evidence"): flags.append("本程序新证据")
    if f["evidence_status"]=="仅当事人陈述": flags.append("未见书证")
    # 一条事实可以有好几项说不准的东西，全要，不能只取第一条——
    # 早先用 next() 取首个匹配，凡是前面排着「证据编号」那条的，
    # 后面真正有内容的说明就被挡住了，一个字也出不来。
    uns=[u for u in CF.get("uncertainties",[]) if u["fid"]==f["fid"]
         and u.get("why") and u.get("what") not in SKIP_UNCERTAIN]
    for un in uns:
        why=un["why"]
        if why in ends:                      # 同一句话只出一条注，多条事实共用注号
            flags.append(f"见注{ends.index(why)+1}")
        else:
            ends.append(why); flags.append(f"见注{len(ends)}")
    if f.get("medium")=="image": flags.append("读图转写·未经逐字核验")
    if flags: parts.append("　".join(flags))
    # Word 把这些信息合成一格备注，Excel 要分列来筛，所以另出一份结构化的。
    # 早先只产 note_parts，母表的主体、关联、说明三列于是一直是空的——
    # 而母表本该是四件产物里最完整的那一份。
    PM = {p["pid"]: p.get("name") or p["pid"] for p in CF.get("parties", [])}
    rows.append({"date":DATE(f["date"],f["date_certainty"]),"item":f["item"],
                 "content":f["content"],"note_parts":parts,
                 "issue":"",                         # 争点由律师在母表内填（E2）
                 "parties":"、".join(PM.get(p,p) for p in (f.get("parties") or [])),
                 "relation":("、".join(DATE(t["date"],t["date_certainty"]).split("（")[0]
                                      for t in CF["facts"] if t["fid"] in rel) if rel else ""),
                 # 「证据编号」那一类不进说明列：证据状态列已经写着「仅当事人陈述」，
                 # 同一件事说两遍，跟 Word 尾注那边守同一条规矩
                 "explain":"；".join(f'{u["what"]}：{u["why"]}' for u in uns),
                 "new_evidence":bool(f.get("new_evidence")),
                 "evidence_status":f["evidence_status"],
                 "source":f"{src}（{party}）" if party else src})
out={"case":{"title":"案件大事记","subtitle":CF["case"]["title"]},"rows":rows,"endnotes":ends,
     "arithmetic_notes":CF.get("arithmetic_notes") or []}
json.dump(out,open(sys.argv[2],"w",encoding="utf-8"),ensure_ascii=False,indent=1)
print(f"{len(rows)} 行，{len(ends)} 条注")
