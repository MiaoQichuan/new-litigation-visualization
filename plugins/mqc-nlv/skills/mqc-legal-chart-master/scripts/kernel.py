# -*- coding: utf-8 -*-
"""共享内核的入口：V1 的字宽、换行、转义、字体栈与 PPTX 导出，只引用、不复制。

仓库的规矩是「共享内核只有一份，放在 V1」。本模块只做一件事：找到 V1 的 scripts
目录并把它挂上 import 路径。找的顺序与法律关系图大师（V3）一致：

  1. 随包带的 vendor/v1/scripts —— 单独分发本 skill 时用；
  2. 同一插件里的 mqc-litigation-visual-redraw/scripts —— 在插件里用。

两处都按相对位置找，不写死绝对路径。
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_VENDOR = os.path.normpath(os.path.join(_HERE, "..", "vendor", "v1", "scripts"))
_SIBLING = os.path.normpath(os.path.join(_HERE, "..", "..", "mqc-litigation-visual-redraw", "scripts"))

# V6 用到的 V1 能力。只看「文件在不在」不够：外部测试第二轮（R2）里，已注册的技能没有 vendor/，
# 回退到本机一份旧版 V1，文件都在、--check 也说「可用」，一出图就 TypeError（wrap 没有 keep_alnum）。
# 现在按能力逐项核对源码，找第一份够用的；都不够就直说缺什么，不让运行期才崩。
NEEDS = {
    "common.py": [("def wrap(", "keep_alnum", "wrap() 支持 keep_alnum（标题里的数字与拉丁词不拆行）"),
                  ("def text_w(", None, "text_w()"), ("def char_w(", None, "char_w()"), ("def esc(", None, "esc()"),
                  ("TITLE_FONT", None, "TITLE_FONT"), ("FONT", None, "FONT")],
    "export_pptx.py": [("def export(", None, "export()"), ("def audit_deck(", None, "audit_deck()"),
                       ("def _zip_write(", None, "_zip_write()")],
}
NEEDS_EXTRA = [os.path.join("..", "assets", "style-tokens.json")]


def missing(path):
    """这份 V1 缺哪些能力（空列表 = 够用）。只读源码，不 import——import 了就换不回另一份了。"""
    out = []
    for fn, needs in NEEDS.items():
        fp = os.path.join(path, fn)
        if not os.path.exists(fp):
            out.append(f"缺 {fn}")
            continue
        src = open(fp, encoding="utf-8-sig").read()
        for head, word, what in needs:
            i = src.find(head)
            if i < 0:
                out.append(f"{fn} 缺 {what}")
            elif word and word not in src[i:i + 300]:
                out.append(f"{fn} 的 {what} 不满足（版本过旧）")
    for ex in NEEDS_EXTRA:
        if not os.path.exists(os.path.join(path, ex)):
            out.append(f"缺 {os.path.normpath(ex)}")
    return out


CANDIDATES = [("随包 vendor/v1", _VENDOR), ("同一插件里的 V1", _SIBLING)]
REPORT = []
V1 = None
for _name, _path in CANDIDATES:
    if not os.path.isdir(_path):
        REPORT.append((_name, _path, ["不存在"]))
        continue
    _miss = missing(_path)
    REPORT.append((_name, _path, _miss))
    if not _miss and V1 is None:
        V1 = _path
if V1 is None:
    lines = "\n".join(f"  {n}：{p}\n    → {'；'.join(m)}" for n, p, m in REPORT)
    raise SystemExit("找不到够用的 V1 共享内核（mqc-litigation-visual-redraw/scripts）。逐一核对的结果：\n"
                     + lines + "\n请安装 standalone 包（自带 vendor/v1），或把 V1 更新到与本仓库同一版本。")
# 本 skill 的目录排在最前：同名模块（例如 V1 也有 geom.py）一律以本 skill 的为准
for _p in (V1, _HERE):
    if _p in sys.path:
        sys.path.remove(_p)
    sys.path.insert(0, _p)

import common as _c          # noqa: E402  (V1)

esc = _c.esc
wrap = _c.wrap
TITLE_FONT = _c.TITLE_FONT   # 宋体链：方正小标宋 → 思源宋体 → 华文中宋，永不落到仿宋
BODY_FONT = _c.FONT
MONO_FONT = "'IBM Plex Mono','Consolas','Menlo',monospace"


def text_w(s, fs, mono=False, track=0.0):
    """与 V1 同一把尺子（CJK ≈ 1em，拉丁 ≈ 0.56em）；等宽数字按 0.6em 量，
    因为 Plex Mono 与 Consolas 的字宽都是 0.6em，用 0.56 会把数字量窄。"""
    # **逐字从左往右加，不用 sum()。** Python 3.12 起 sum() 对浮点做补偿求和，比逐字累加更精确；
    # 而 V1 的 wrap() 是逐字累加的。两者差在小数点后十几位，却足以让「列宽 = 最宽那个类目名的宽度」
    # 时，最宽的那个名字在 3.12+ 上被自己的列宽挤成两行（实测「机动车交通事故 / 责任」，3.11 不拆）。
    # 同一份说明在不同 Python 上出的图必须逐字节相同，所以这里按 wrap 的次序量。
    w = 0.0
    for ch in s:
        w += (fs if ord(ch) > 0x2E7F else fs * 0.6) if mono else _c.char_w(ch, fs)
    return w + track * max(0, len(s) - 1)
