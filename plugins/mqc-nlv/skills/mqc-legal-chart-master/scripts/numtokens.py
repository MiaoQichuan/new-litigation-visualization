# -*- coding: utf-8 -*-
"""从标题、批注里抽出每一个数字，记下它是什么类型。全模块只此一处抽数字。

0.8.0 的教训（外部测试 T020 / T028）：旧正则用 (?<![\\w.]) 防止把「T001」里的 001 当成数，
可 Python 的 \\w 包括汉字——「增长9876%」里的 9876 紧贴着「长」，于是整个数字没被抽出来，
「只许算、不许编」这条硬规则在中文最常见的写法下形同虚设。这里的边界只看 ASCII 字母、数字、
下划线与小数点，汉字后面的数字一律抽出。

每个 token：
  text    原文片段（含符号、百分号）
  start, end  在原文里的位置
  value   float（千分位已去掉；全角数字已换成半角）
  sign    "+" / "-" / ""
  kind    "pct"（带 %）、"pp"（带「个百分点」）、"num"（其余）
  role    "data"（要由数据推出）、"year"（年份，须出现在口径 / 来源 / 类目里）、
          "cite"（条文编号「第 577 条」，不是数据，列请核）
另返回 masked：案号等整段标识符（不是数据，列请核）。
"""
import re

_FW = str.maketrans("０１２３４５６７８９％．－＋", "0123456789%.-+")
_CASE_NO = re.compile(r"[（(]\s*\d{4}\s*[）)][^\s，。；、,;]{0,24}?\d+\s*号")
_TOKEN = re.compile(
    r"(?<![0-9A-Za-z_.])"                       # 左边不能紧贴 ASCII 字母、数字、下划线、小数点；汉字可以
    r"(?P<sign>[+\-−])?"
    r"(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"(?![0-9.]|,\d)"                           # 右边不能是还没读完的数字（「12,34」不拼成 1234）
    r"(?P<tail>\s*(?:%|个百分点|百分点))?")
_BADGROUP = re.compile(r"(?<![0-9])\d+(?:,\d{1,2}(?!\d)|,\d{4,})")
_FWGROUP = re.compile(r"(?<![0-9])\d{1,3}(?:，\d{3})+(?!\d)")      # 「1，234」：千分位还是两个数，说不清
_SCI = re.compile(r"(?<![0-9A-Za-z_.])\d+(?:\.\d+)?[eE][+\-]?\d+")
CITE_AFTER = ("条", "款", "项", "章", "节", "编", "目")


def normalize(text):
    return str(text).translate(_FW)


def extract(text):
    """返回 (tokens, masked, problems)。problems 是写法本身有毛病的数字（例如分组错误的 12,34）。"""
    s = normalize(text)
    masked, problems = [], []
    for mt in _CASE_NO.finditer(s):
        masked.append(mt.group(0))
    s_m = _CASE_NO.sub(lambda mt: " " * len(mt.group(0)), s)
    for mt in _BADGROUP.finditer(s_m):
        problems.append(f"「{mt.group(0)}」的千分位分组不对（应每三位一组）")
    for mt in _FWGROUP.finditer(s_m):
        problems.append(f"「{mt.group(0)}」用了中文逗号：是千分位还是两个数说不清，请写成 "
                        f"{mt.group(0).replace('，', ',')} 或 {mt.group(0).replace('，', '')}")
    for mt in _SCI.finditer(s_m):
        problems.append(f"「{mt.group(0)}」是科学计数法，图上不用；请写成普通数字")
    toks = []
    for mt in _TOKEN.finditer(s_m):
        raw = mt.group("num")
        tail = (mt.group("tail") or "").strip()
        sign = mt.group("sign") or ""
        sign = "-" if sign in "-−" and sign else sign
        kind = "pct" if tail == "%" else "pp" if tail else "num"
        before = s_m[max(0, mt.start() - 1):mt.start()]
        after = s_m[mt.end():mt.end() + 2].lstrip()
        role = "data"
        if kind == "num" and not sign:
            if after[:1] in CITE_AFTER:
                role = "cite"                      # 第 577 条、第 3 款：条文编号
            elif before == "第":
                role = "ordinal"                   # 第 9876 件、第 3 名：顺序编号，要落在样本里
            elif re.fullmatch(r"(1[89]|20)\d\d", raw) and after[:1] in ("年", "-", "–", "—", "~", "至", "到"):
                role = "year"
        toks.append({"text": mt.group(0).strip(), "start": mt.start(), "end": mt.end(),
                     "value": float(raw.replace(",", "")), "sign": sign, "kind": kind, "role": role,
                     "raw": raw})
    return toks, masked, problems
