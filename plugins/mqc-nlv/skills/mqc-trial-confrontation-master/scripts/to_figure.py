#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""分析表输入 → 主图输入。表是唯一的源，图是它的渲染。
每个对抗部分取其「有争议待证」的要件作中轴（多于一条时取标为决定性的那条，
否则取第一条）；四段攻防从该要件的四个字段派生成左右两栏的卡片。
左右卡数由四段是否有内容决定，故 L1/L2 两条逻辑约束自动成立。"""
import json, sys, re

BLANK  = ("—","","（无书面记载）")   # 与 check_claims 同一套，硬写的占位也走归因
NO_RECORD = "（无书面记载）"      # 该文书已在手，其中确实没写这一段
NOT_HELD  = "（未获取：{}）"       # 该文书本身没拿到，这一段无从得知
SRC_DEFAULT = {"claim":"起诉状","response":"答辩状","counter":"代理意见","second":"质证意见"}

def absence(key, src, scope):
    """S1 空段的归因，供分析表与图底的材料范围用。
    「对方没说」与「我没拿到对方的文书」法律含义完全不同：前者庭上可以据以主张，
    后者只是自己信息不全。图上不为空段留框（见 cards_of），但归因不能丢。"""
    name = (src or {}).get(key) or SRC_DEFAULT[key]
    return NOT_HELD.format(name) if name in (scope.get("not_obtained") or []) else NO_RECORD

def cards_of(e, scope=None):
    """四段 → 卡片。没有的那一段不出卡，版面结构跟着材料走。
    可能的编排只有 左2右2 / 左2右1 / 左1右1 / 左1右0（对方尚无任何回应）四种；
    左1右2 不成立——有再回应必先有反制（B2，在数据层查）。
    空段的归因（无书面记载 / 未获取某文书）不进图上的框，落在分析表与图底的
    材料范围里：图上凭空立一个未获取的框，读图的人会当成对方真有这一手。"""
    out=[]
    def add(side,title,body,edge,_blank):
        if not body or body in BLANK: return       # 没有这一段，就没有这张卡
        out.append({"side":side,"title":title,"body":body,
                    "edge":(edge if edge not in BLANK else "")})
    # 来源取自数据，不写死。庭前阶段对方常常只交证据目录而无答辩状，
    # 把它标成「答辩状」就是在图上写一个不存在的文书，违反 A4 绝不编造。
    src=e.get("src") or {}; scope=scope or {}
    for side,title,key in (("claim","请求方主张","claim"),("defend","抗辩方回应","response"),
                           ("claim","请求方反制","counter"),("defend","抗辩方再回应","second")):
        add(side,title,e.get(key), src.get(key) or SRC_DEFAULT[key], absence(key,src,scope))
    L=[c for c in out if c["side"]=="claim"]; R=[c for c in out if c["side"]=="defend"]
    return L+R

def convert(M):
    """一个「有争议待证」的构成要件占一个行组，不是一个诉请占一个行组。
    早先每个对抗部分只取一条要件进图，单诉请多争点的案子图上只剩一半：
    一件借款返还纠纷有「款项定性」与「返还条件是否成就」两个争议要件，
    图上只画得出定性那条，对方唯一的实质抗辩整个消失，而表里是有的。"""
    parts=[]
    for p in M["parts"]:
        els=[e for cb in p["claim_bases"] for e in cb["elements"]]
        dis=[e for e in els if e.get("dispute")=="有争议待证"] or els[:1]
        for e in dis:
            parts.append({
            "id": e["id"],
            "label": f'{p["label"]}　·　{e["name"]}',
            "ref": e["id"],
            "concl": f'{e["id"]}　{e["name"]}',        # 结论条用短名，长标题留给通栏
            "claim_bases": p["claim_bases"],           # 供 L3b 从属性排除判定
            "center": {"title": f'{e["id"]}　{e["name"]}',
                       "body": e.get("court_standard",""),
                       "disputed": e.get("dispute")=="有争议待证",
                       "burden": "claim" if e.get("burden")=="提出请求的一方" else "defend",
                       "prospect": e.get("prospect","—")},
            "cards": cards_of(e, M.get("scope"))})
    # 母表的标题以「庭审对抗分析表」起头，原样搬到图上会变成图自称分析表，剥掉再用
    sub=re.sub(r'^庭审对抗分析表[\s\u3000]*[·•・\u30fb]?[\s\u3000]*', "", M["case"]["title"])
    sc=M.get("scope") or {}
    cs=M.get("case") or {}
    return {"title":"庭审对抗图","subtitle":sub,"parts":parts,
            "stance":cs.get("stance"), "maturity":(M.get("scope") or {}).get("maturity"),
            "scope_note": ("本图所据材料范围：缺 " + "、".join(sc["not_obtained"])
                           if sc.get("not_obtained") else "")}

if __name__=="__main__":
    M=json.load(open(sys.argv[1],encoding="utf-8"))
    F=convert(M)
    json.dump(F, open(sys.argv[2],"w",encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f'  图输入：{sys.argv[2]}（{len(F["parts"])} 个对抗部分，'
          f'卡片 {sum(len(p["cards"]) for p in F["parts"])} 张）')
