#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""底稿结构校验。不引 jsonschema，自己走必填、枚举、正则与 additionalProperties。"""
import json, re, sys, os
HERE=os.path.dirname(os.path.abspath(__file__))
S=json.load(open(os.path.join(os.path.dirname(HERE),"schemas","casefile.schema.json"),encoding="utf-8"))

def walk(node, sch, path, errs):
    if "const" in sch and node!=sch["const"]: errs.append(f"{path}: 应为 {sch['const']}，实为 {node!r}")
    if "enum" in sch and node not in sch["enum"]: errs.append(f"{path}: 不在枚举 {sch['enum']} 内，实为 {node!r}")
    t=sch.get("type")
    if t=="object" or (isinstance(t,list) and "object" in t) or "properties" in sch:
        if not isinstance(node,dict): errs.append(f"{path}: 应为对象"); return
        for k in sch.get("required",[]):
            if k not in node: errs.append(f"{path}: 缺必填字段 `{k}`")
        if sch.get("additionalProperties") is False:
            for k in node:
                if k not in sch.get("properties",{}): errs.append(f"{path}: 多出字段 `{k}`（schema 未声明）")
        for k,v in node.items():
            if k in sch.get("properties",{}): walk(v, sch["properties"][k], f"{path}.{k}", errs)
    elif t=="array":
        if not isinstance(node,list): errs.append(f"{path}: 应为数组"); return
        for i,x in enumerate(node): walk(x, sch.get("items",{}), f"{path}[{i}]", errs)
    else:
        if "pattern" in sch and isinstance(node,str) and not re.fullmatch(sch["pattern"],node):
            errs.append(f"{path}: 不符合 {sch['pattern']}，实为 {node!r}")
        if "maxLength" in sch and isinstance(node,str) and len(node)>sch["maxLength"]:
            errs.append(f"{path}: 超过 {sch['maxLength']} 字，实为 {len(node)}")
        if t=="null" and node is not None: errs.append(f"{path}: 应为 null，实为 {node!r}")
        if t=="boolean" and not isinstance(node,bool): errs.append(f"{path}: 应为布尔")

def check(cf):
    errs=[]; walk(cf,S,"$",errs); return errs

if __name__=="__main__":
    cf=json.load(open(sys.argv[1],encoding="utf-8"))
    e=check(cf)
    print(f"结构校验 {sys.argv[1]}")
    for x in e: print("  FAIL",x)
    print("  全部通过" if not e else f"\n  {len(e)} 处不符")
    sys.exit(1 if e else 0)
