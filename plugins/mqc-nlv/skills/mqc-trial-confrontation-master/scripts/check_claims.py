#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""诉请固定（J）与抗辩归类（K）的机械校验。零第三方依赖。
这两件是九步法前端里少数可机验的部分：类型取自封闭表、必填项缺一即错、
举证责任由归类决定而非另判。判据见 references/intake.md。"""
import json, sys

CLAIM_TYPES = {
    "给付钱款": ["给付主体","标的种类","金额或数量","构成及计算方法"],
    "给付实物": ["给付主体","标的种类","金额或数量","构成及计算方法"],
    "履行行为": ["履行内容","履行方式","是否便于执行"],
    "多被告担责": ["责任性质","份额"],
    "确认":     ["对象"],
    "形成":     ["对象"],
}
DEFENSE_CLASSES = {
    "否认":            "claim",   # 举证责任仍在提出请求的一方
    "权利障碍":        "defend",
    "权利消灭":        "defend",
    "权利受制抗辩权":  "defend",
}
REASON_KEYS = ["一问","二问","三问"]
OUT_OF_SCOPE  = ("确认", "形成")          # 请求权基础分析的适用边界之外
COUNTERATTACK = ("反诉", "抵销", "违约金酌减", "另案主张")   # 反攻，不是抗辩
DIRECTIONS    = ("请求方有利", "抗辩方有利", "中立")
MATURITY      = ("L0", "L1", "L2", "L3")
BLANK = ("—","","（无书面记载）")
import re as _re
NUM = _re.compile(r'(\d[\d,]*\.?\d*)')

def _amount(t):
    """从「金额或数量」里取数。取不出数的（如「按实际发生额」）返回 None，跳过核算。"""
    m=NUM.search(str(t).replace(" ",""))
    if not m: return None
    try: return float(m.group(1).replace(",",""))
    except ValueError: return None

class R:
    def __init__(s): s.errs=[]
    def ck(s,no,cond,msg):
        print(("  OK  " if cond else "  FAIL")+f" {no}  {msg}")
        if not cond: s.errs.append(no)

def check(D):
    r=R()
    # ---- J 诉请固定 ----
    for c in D.get("claims", []):
        t=c.get("type")
        r.ck("J1", t in CLAIM_TYPES, f'{c.get("id","?")} 诉请类型在封闭表内（实为 {t!r}）')
        if t in CLAIM_TYPES:
            miss=[k for k in CLAIM_TYPES[t] if not str(c.get("fields",{}).get(k,"")).strip()]
            r.ck("J2", not miss, f'{c["id"]} {t} 必填项齐全（缺 {miss}）' if miss
                                  else f'{c["id"]} {t} 必填项齐全')
    # ---- J3 诉请金额与构成明细必须算得平 ----
    # 模型填结构化明细，代码做算术。真案子里一抓一个准：主张损失若干，
    # 逐项加起来却是另一个数；或某一段「暂计」而无任何依据。这正是 J2 说的
    # 「构成及计算方法」是对方诉请的固定漏洞所在——只查填没填抓不住它。
    for c in D.get("claims", []):
        if c.get("type") not in ("给付钱款","给付实物"): continue
        tot=_amount(c.get("fields",{}).get("金额或数量",""))
        if tot is None: continue                       # 未主张确定数额的，不核算
        bd=c.get("breakdown")
        r.ck("J3", bool(bd), f'{c["id"]} 主张 {tot:g} 元，附构成明细（breakdown）')
        if bd:
            ssum=sum(float(x.get("amount",0)) for x in bd)
            r.ck("J3b", abs(ssum-tot)<0.01,
                 f'{c["id"]} 明细合计 {ssum:g} 与主张额 {tot:g} 相符')
            nob=[x.get("item") for x in bd if not str(x.get("basis","")).strip()]
            r.ck("J3c", not nob, f'{c["id"]} 每项明细都注明依据（缺 {nob}）' if nob
                                 else f'{c["id"]} 每项明细都注明依据')
    # ---- P 程序站：防「单方材料→全胜」的闸 ----
    # 三项分列成字段来查，不在一段话里数关键词：数关键词逼人凑词，
    # 写「双方均为适格当事人」明明审过主体，却因为没出现「主体」二字而被判不过。
    proc = D.get("case", {}).get("procedural")
    if isinstance(proc, str):        # 旧写法：整段话，只作提示不拦
        r.ck("P1", bool(proc.strip()), "程序事项已填（建议改为 管辖／主体／重复起诉 三项分列）")
    else:
        proc = proc or {}
        miss = [k for k, n in (("jurisdiction", "管辖"), ("parties", "主体"),
                               ("res_judicata", "重复起诉")) if not str(proc.get(k, "")).strip()]
        r.ck("P1", not miss, f'程序站三项均已审查（缺 {miss}）' if miss else '程序站三项均已审查')

    # ---- M 材料成熟度：只改变证明前景能达到多深，不改变结构 ----
    mat = (D.get("scope") or {}).get("maturity")
    r.ck("M1", mat in MATURITY, f'材料成熟度在 L0–L3 内（实为 {mat!r}）')
    if mat in ("L0", "L1"):
        # 降级只降精确度，不降结构：决定性要件照算照标，但证据置信必须降到「低」、
        # 并列明要补什么。绝不用改写 prospect 来表达材料薄——prospect 是决定性判定的
        # 输入，改它等于篡改判定本身：实测把一处「低」改成「待定」，表里仍标决定性，
        # 图上却不再强调，图表就此不一致。
        bad = [e["id"] for p in D.get("parts", []) for cb in p.get("claim_bases", [])
               for e in cb.get("elements", [])
               if e.get("decisive") == "是"
               and (e.get("conf_evid") != "低" or not str(e.get("todo", "")).strip() or
                    str(e.get("todo", "")).strip() == "—")]
        r.ck("M2", not bad,
             f'{mat} 材料下的决定性要件均标了证据置信「低」并列明待补材料（不合 {bad}）')

    # ---- 三标之三：立场方向（前两标为法律置信与证据置信，已分列） ----
    for p in D.get("parts", []):
        for cb in p.get("claim_bases", []):
            for e in cb.get("elements", []):
                r.ck("T1", e.get("direction") in DIRECTIONS,
                     f'{e["id"]} 带立场方向标（实为 {e.get("direction")!r}）')
                # D 组：决定性要件必须落到真伪不明的标准表述上，不得软化
                if e.get("decisive") == "是":
                    # 单立一栏，只进分析表、不进图。塞进 court_standard 会把这句套话
                    # 顶到中轴卡的正文里，每个决定性要件的卡都拖一行，图先被拖垮。
                    txt = str(e.get("burden_conclusion", ""))
                    ok = "真伪不明" in txt and "不利后果" in txt
                    r.ck("D1", ok, f'{e["id"]} 决定性要件在「真伪不明的后果」栏写明由谁承担')

    r.ck("T2", D.get("case", {}).get("stance") in ("原告向", "被告向"),
         f'全案标明了立场（实为 {D.get("case", {}).get("stance")!r}）')

    # ---- E 适用边界：确认之诉／形成之诉不按要件拆 ----
    # 请求权基础分析锚定给付之诉。确认与形成之诉的规范结构不是「要件→法律效果」，
    # 硬拆要件等于把方法用在它失灵的地方，应转法律关系分析法。
    # 封闭表里留着这两个类型，但留着是为了识别边界并转派，不是为了照常推演。
    for c in D.get("claims", []):
        if c.get("type") in OUT_OF_SCOPE:
            r.ck("E1", bool(str(c.get("boundary","")).strip()),
                 f'{c["id"]} 属{c["type"]}之诉，已标出边界与转派去向')
            own=[p for p in D.get("parts",[]) if p.get("claim_ref")==c["id"]]
            bad=[p.get("label") for p in own if p.get("method")!="法律关系分析法"]
            r.ck("E2", not bad,
                 f'{c["id"]} 对应的对抗部分标了按法律关系分析法处理（未标 {bad}）' if bad
                 else f'{c["id"]} 对应的对抗部分标了按法律关系分析法处理')

    # ---- G 攻击性防御：不入四分法 ----
    # 反诉／抵销／违约金酌减／另案主张这四项是反攻，不是抗辩：
    # 它们不否认、不阻却、不消灭原告的请求权，而是另起一条独立的权利主张。
    # 硬塞进四分法必然归错——抵销会被归成「权利消灭」，可它针对的是全案而非某个要件。
    for p in D.get("parts", []):
        for cb in p.get("claim_bases", []):
            for e in cb.get("elements", []):
                for tag,cls in (("回应",e.get("response_class")),("再回应",e.get("second_class"))):
                    raw=str(cls or "").replace("【待核验】","").strip()
                    bad=[k for k in COUNTERATTACK if k in raw]
                    r.ck("G1", not bad,
                         f'{e["id"]} {tag}归类混入攻击性防御（{bad}），应移入 case.counterattacks'
                         if bad else f'{e["id"]} {tag}归类未混入攻击性防御')
    for ca in D.get("case", {}).get("counterattacks", []):
        r.ck("G2", ca.get("kind") in COUNTERATTACK,
             f'攻击性防御「{ca.get("kind")}」在封闭表内（{"／".join(COUNTERATTACK)}）')
        r.ck("G3", bool(str(ca.get("handling","")).strip()),
             f'{ca.get("kind")} 写明了处理路径（反诉／另案／本案抗辩，及费用与期限）')

    # ---- S 材料范围：空段必须归因 ----
    # 律师手上材料不全是庭前常态，允许跑；但每一处空白都要说得出为什么空。
    # 说不出，就只能写成含糊的「无书面记载」，那等于替对方说了他没说过话。
    SRC_DEFAULT={"claim":"起诉状","response":"答辩状","counter":"代理意见","second":"质证意见"}
    sc=D.get("scope") or {}
    got=set(sc.get("obtained") or []); nogot=set(sc.get("not_obtained") or [])
    r.ck("S2", not (got & nogot), f'同一文书不得既称已获取又称未获取（重复 {sorted(got&nogot)}）')
    blanks=[]
    for p in D.get("parts", []):
        for cb in p.get("claim_bases", []):
            for e in cb.get("elements", []):
                for k in ("claim","response","counter","second"):
                    if str(e.get(k,"")).strip() in BLANK:
                        nm=(e.get("src") or {}).get(k) or SRC_DEFAULT[k]
                        if nm not in got and nm not in nogot: blanks.append((e["id"],k,nm))
    r.ck("S1", not blanks,
         f'每处空段的来源都在材料范围里表了态（未表态 {blanks[:3]}）' if blanks
         else '每处空段的来源都在材料范围里表了态')
    # ---- K 抗辩归类 ----
    for p in D.get("parts", []):
        for cb in p.get("claim_bases", []):
            for e in cb.get("elements", []):
                for tag,cls0,burden_field in (("回应", e.get("response_class"), e.get("response_burden")),
                                              ("再回应", e.get("second_class"), e.get("second_burden"))):
                    if cls0 in (None,"","—"): continue
                    # 【待核验】只表示归类待律师复核，不表示可以不受机械判据约束。
                    # 剥掉标记再查：否则给归类加四个字，K2 举证责任与 K3 三问路径一起失效。
                    cls = cls0.replace("【待核验】","").strip()
                    r.ck("K1", cls in DEFENSE_CLASSES, f'{e["id"]} {tag}归类在封闭表内（实为 {cls0!r}）')
                    if cls in DEFENSE_CLASSES:
                        want=DEFENSE_CLASSES[cls]
                        r.ck("K2", burden_field==want,
                             f'{e["id"]} {tag}的举证责任由归类决定：{cls} → {want}（实为 {burden_field!r}）')
                    if cls0.endswith("【待核验】"):
                        print(f"  NOTE K4  {e['id']} {tag}归类标了【待核验】，须律师复核")
                # B2 有再回应必先有反制。卡片留位后每侧恒两张，这条只能在数据层查。
                has=lambda k: str(e.get(k,"")).strip() not in BLANK
                r.ck("B2", not (has("second") and not has("counter")),
                     f'{e["id"]} 抗辩方再回应以请求方反制为前提（反制为空而再回应有内容）')
                if str(e.get("response_class","")).replace("【待核验】","").strip() in DEFENSE_CLASSES:
                    reason=e.get("class_reason","")
                    r.ck("K3", any(k in reason for k in REASON_KEYS),
                         f'{e["id"]} 归类附三问路径（实为 {reason[:18]!r}）')
    return r

if __name__=="__main__":
    D=json.load(open(sys.argv[1],encoding="utf-8"))
    r=check(D)
    print()
    print("  全部通过" if not r.errs else f"  未通过：{sorted(set(r.errs))}")
    sys.exit(1 if r.errs else 0)
