#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""改坏验证：逐条把数据或参数改坏，断言对应判据必须报错。
只跑通不算数——不会报错的判据等于没有判据。"""
import json, sys, os, copy, io, contextlib
import tempfile as _tempfile
_TMP = _tempfile.gettempdir()   # 不写死 /tmp：Windows 上没有这个目录，自检一跑就找不到文件
HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT,"scripts"))
import render_main as RM
from layout import Geo, columns

sys.path.insert(0, os.path.join(ROOT,"scripts"))
from to_figure import convert as _cv
BASE=_cv(json.load(open(os.path.join(ROOT,"examples","matrix-input.json"),encoding="utf-8")))
CASES=[]
def case(code,desc):
    def deco(fn): CASES.append((code,desc,fn)); return fn
    return deco

@case("L1","一侧放了 3 张卡（四段收口被破坏）")
def _(d): d["parts"][0]["cards"].append({"title":"多余","body":"x","side":"claim"})
@case("L2","左1右2：有再回应却没有反制")
def _(d):
    p=d["parts"][1]
    p["cards"]=[c for c in p["cards"] if c["side"]=="defend"]+[
        next(c for c in p["cards"] if c["side"]=="claim")]
@case("L4","深红算出 3 处，应转入分散态而非硬指一处")
def _(d):
    for p in d["parts"]:
        p["center"].update({"disputed":True,"burden":"claim","prospect":"低"})
    d["_break_code"]="scatter"
@case("M2","三栏加通道之和不等于可用宽")
def _(d): d["_break_cols"]=True
@case("M12","卡高退回旧估法（漏掉呼吸位与字形下沉），卡底留白被吃掉")
def _(d): d["_break_code"]="metrics"
@case("R9","边标签不让线，落回引线高度上，被母线压字")
def _(d): d["_break_code"]="label"
@case("M11","正文退回顶排，被撑高的卡下方空一大块")
def _(d): d["_break_code"]="topalign"
@case("M10","标题跟着正文一起居中，三栏标题不再齐平")
def _(d): d["_break_code"]="titledrop"

def run(d):
    """返回 (是否抛错, 错误码)。"""
    out=os.path.join(_TMP, "_bt.svg")
    try:
        mode=d.pop("_break_code",None)
        if mode=="metrics":
            # 高度估法改坏、基线不动 → 文字必然出框，M10 读产物应当报出
            orig=RM.metrics
            def bad(nt,nb,cut,g):
                tb,bb,note,_=orig(nt,nb,cut,g)
                return tb,bb,note,2*g.PADY+nt*g.FS_T*1.35+nb*g.LH
            RM.metrics=bad
            try:
                with contextlib.redirect_stdout(io.StringIO()): RM.render(d,out)
            finally: RM.metrics=orig
            sys.path.insert(0,os.path.join(ROOT,"scripts"))
            from check_figure import check
            with contextlib.redirect_stdout(io.StringIO()) as buf: rc=check(out)
            return (rc!=0), ("M12" if "FAIL M12 " in buf.getvalue() else "?")
        if mode=="scatter":
            with contextlib.redirect_stdout(io.StringIO()): RM.render(d,out)
            svg=open(out,encoding="utf-8").read()
            ok = d.get("scattered") and "争点分散" in svg and not any(p.get("emph") for p in d["parts"])
            return ok, ("L4" if ok else "?")
        if mode=="titledrop":
            RM.TITLE_TOP=False
            try:
                with contextlib.redirect_stdout(io.StringIO()): RM.render(d,out)
            finally: RM.TITLE_TOP=True
            sys.path.insert(0,os.path.join(ROOT,"scripts"))
            from check_figure import check
            with contextlib.redirect_stdout(io.StringIO()) as buf: rc=check(out)
            return (rc!=0), ("M10" if "FAIL M10 " in buf.getvalue() else "?")
        if mode=="topalign":
            RM.CENTER_V=False
            try:
                with contextlib.redirect_stdout(io.StringIO()): RM.render(d,out)
            finally: RM.CENTER_V=True
            sys.path.insert(0,os.path.join(ROOT,"scripts"))
            from check_figure import check
            with contextlib.redirect_stdout(io.StringIO()) as buf: rc=check(out)
            return (rc!=0), ("M11" if "FAIL M11 " in buf.getvalue() else "?")
        if mode=="label":
            # 让线量归零 → 标签框回到引线高度上，穿越自证应当拦下
            up,dn=RM.LBL_UP,RM.LBL_DN; RM.LBL_UP=RM.LBL_DN=0.0
            try:
                with contextlib.redirect_stdout(io.StringIO()) as buf: ok=RM.render(d,out)
            finally: RM.LBL_UP,RM.LBL_DN=up,dn
            return (ok is False), ("R9" if "穿越自证未通过" in buf.getvalue() else "?")
        if d.pop("_break_cols",False):
            orig=RM.columns
            def bad(W,g,**kw):
                c=orig(W,g,**kw); c["gutter"]+=17.0; c["left"]-=17.0; return c   # 破坏 M2c
            RM.columns=bad
            try:
                with contextlib.redirect_stdout(io.StringIO()): RM.render(d,out)
            finally: RM.columns=orig
            sys.path.insert(0,os.path.join(ROOT,"scripts"))
            from check_figure import check
            with contextlib.redirect_stdout(io.StringIO()) as buf: rc=check(out)
            v=buf.getvalue()
            return (rc!=0), next((x for x in ("M2c","M2b","M2","M1") if f"FAIL {x} " in v), "?")
        with contextlib.redirect_stdout(io.StringIO()): RM.render(d,out)
        return False, None
    except AssertionError as e:
        return True, str(e)

# ---- J/K 两组的改坏验证（独立于图，直接打校验器）----
import json as _j
sys.path.insert(0, os.path.join(ROOT,"scripts"))
from check_claims import check as _ck
import io as _io, contextlib as _cl
_M=_j.load(open(os.path.join(ROOT,"examples","matrix-input.json"),encoding="utf-8"))
def _run_ck(mut):
    d=copy.deepcopy(_M); mut(d)
    with _cl.redirect_stdout(_io.StringIO()) as b: r=_ck(d)
    return sorted(set(r.errs))
JK=[("E1","形成之诉没标出适用边界", lambda d: d["claims"][0].pop("boundary")),
    ("G1","抵销被塞进抗辩四分法",
     lambda d: d["parts"][0]["claim_bases"][0]["elements"][0].__setitem__("response_class","抵销")),
    ("G3","攻击性防御没写处理路径", lambda d: d["case"]["counterattacks"][0].__setitem__("handling","")),
    ("T1","要件缺立场方向标",
     lambda d: d["parts"][0]["claim_bases"][0]["elements"][0].__setitem__("direction","对我方有利")),
    ("T2","全案没标立场", lambda d: d["case"].__setitem__("stance","中立")),
    ("P1","程序站漏掉重复起诉一项",
     lambda d: d["case"]["procedural"].__setitem__("res_judicata","")),
    ("M2","L1 材料下决定性要件没降证据置信、没列待补",
     lambda d: (d["scope"].__setitem__("maturity","L1"),
                d["parts"][0]["claim_bases"][0]["elements"][0].__setitem__("conf_evid","高"))),
    ("D1","决定性要件没写真伪不明由谁承担不利后果",
     lambda d: d["parts"][0]["claim_bases"][0]["elements"][0].__setitem__("burden_conclusion","有风险。")),
    ("E2","形成之诉对应的部分未标按法律关系分析法处理",
     lambda d: d["parts"][0].__setitem__("method","请求权基础方法")),
    ("S1","空段的来源没在材料范围里表态", lambda d: d["scope"].__setitem__("not_obtained",[])),
    ("S2","同一文书既称已获取又称未获取", lambda d: d["scope"]["obtained"].append("质证意见")),
    ("B2","有再回应却没有反制", lambda d: d["parts"][1]["claim_bases"][0]["elements"][0].__setitem__("counter","—")),
    ("J3b","诉请金额与构成明细加不起来", lambda d: d["claims"][1]["breakdown"][0].__setitem__("amount",99999)),
    ("J3c","构成明细某一项没写依据", lambda d: d["claims"][1]["breakdown"][0].__setitem__("basis","")),
    ("J1","诉请类型写成表外的类型", lambda d: d["claims"][1].__setitem__("type","赔偿之诉")),
    ("J2","给付钱款缺「构成及计算方法」", lambda d: d["claims"][1]["fields"].__setitem__("构成及计算方法","")),
    ("K1","抗辩归类写成表外的说法", lambda d: d["parts"][0]["claim_bases"][0]["elements"][0].__setitem__("response_class","权利消灭抗辩")),
    ("K2","归否认却把举证责任记到抗辩方", lambda d: d["parts"][0]["claim_bases"][0]["elements"][0].__setitem__("response_burden","defend")),
    ("K3","归类未附三问路径", lambda d: d["parts"][0]["claim_bases"][0]["elements"][0].__setitem__("class_reason","凭经验")),
]
_f=0
for code,desc,mut in JK:
    got=_run_ck(mut); hit=code in got
    print(("  OK  " if hit else "  MISS")+f" {code:<3} {desc}"+("" if hit else f"   ← 未触发（{got}）"))
    if not hit: _f+=1
print(f"  J/K 组 {len(JK)} 项，{len(JK)-_f} 项触发\n")

ok,_=run(copy.deepcopy(BASE))
print(f"基线（未改坏）：{'干净' if not ok else '已报错'}")
if ok: sys.exit(1)
fails=0
for code,desc,mut in CASES:
    d=copy.deepcopy(BASE); mut(d)
    hit,info=run(d)
    got = (info or "").startswith(code) or code==info or (code=="M2" and (info or "").startswith("M2"))
    print(("  OK  " if (hit and got) else "  MISS")+f" {code:<3} {desc}"+("" if hit and got else f"   ← 未触发（{info}）"))
    if not (hit and got): fails+=1
print()
print(f"{len(CASES)} 项改坏验证，{len(CASES)-fails} 项触发，{fails} 项漏过")
sys.exit(1 if fails else 0)
