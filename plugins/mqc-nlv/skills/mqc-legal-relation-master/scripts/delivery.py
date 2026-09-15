# -*- coding: utf-8 -*-
"""交付说明。三件法宝共用一个格式，不各写各的。

V1 的铁则要求每次交付都写明**所用风格**与**所选要害**（或「无强调」）。
先前三个 skill 各写各的，措辞不一，律师拿到手要重新适应。

格式只有四行，按重要性排：交付了什么、用了什么风格、
标了哪个要害、判据过没过。不写寒暄，不写过程。
"""


def summary(files, style="奇川风", emphasis=None, guard=None, scale=None):
    """files 是 {格式: 路径}；emphasis 为 None 表示使用者没有指定要害。"""
    lines = []
    order = ["svg", "png", "pptx", "vsdx", "drawio", "docx", "xlsx", "pdf"]
    keys = [k for k in order if k in files] + [k for k in files if k not in order]
    bad = lambda v: isinstance(v, str) and (v.startswith("失败") or v.startswith("未交付"))
    got = [k for k in keys if not bad(files[k])]
    lines.append("交付：" + "、".join(got))
    for k in keys:
        if bad(files[k]):
            lines.append(f"未交付：{k}，{files[k].split('：', 1)[-1]}")
    lines.append("风格：" + style)
    # 红是选入制：使用者没指定就明说「无强调」，不替他挑一个
    lines.append("强调：" + (emphasis if emphasis else "无（使用者未指定）"))
    if scale:
        lines.append("规模：" + scale)
    if guard is not None:
        ok, msg = (guard if isinstance(guard, tuple) else (guard, ""))
        lines.append("判据：" + ("全部通过" if ok else f"未通过 — {msg}"))
    return "\n".join(lines)


def brief(files, **kw):
    """一行版，用在日志或进度提示里。"""
    s = summary(files, **kw).replace("\n", "　")
    return s
