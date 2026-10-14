# -*- coding: utf-8 -*-
"""找到 V6（法律图表大师）与 V1（共享内核），挂上 import 路径。只引用、不复制、不修改。

V7 不改 V1–V6 的任何代码（作者定的：V1–V5 不能动）。它用到的：
  V6  make.build（按版位重画图表、过守卫）、pptx_ready / apply_alpha（PPTX 前处理）、styles、module.SLOTS
  V1  export_pptx（SVG → 可编辑形状）、common.wrap / text_w（与全套模块同一把字宽尺子）
V6 自己的 kernel.py 会去找 V1，所以这里只要找到 V6。找的顺序：随包 vendor/v6/scripts，再找同一插件里的 V6。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
_VENDOR = os.path.join(ROOT, "vendor", "v6", "scripts")
_SIBLING = os.path.normpath(os.path.join(ROOT, "..", "mqc-legal-chart-master", "scripts"))
V6 = _VENDOR if os.path.exists(os.path.join(_VENDOR, "make.py")) else _SIBLING
if not os.path.exists(os.path.join(V6, "make.py")):
    raise SystemExit("找不到 V6 法律图表大师（mqc-legal-chart-master/scripts）。V7 用它画图表、转 PPTX；请按插件完整安装。")
if V6 not in sys.path:
    sys.path.insert(0, V6)
import kernel  # noqa: E402,F401  V6 的 kernel 会把 V1 挂上路径
# V7 自己的目录排最前：同名模块以 V7 的为准
if HERE in sys.path:
    sys.path.remove(HERE)
sys.path.insert(0, HERE)


def inside(base_dir, rel):
    """课件里引用的素材（file、data）→ 绝对路径；不在课件文件夹里就返回 None。

    规矩是素材都放进这个课件文件夹的 assets/（见 SKILL.md）。别人给的 deck.json 若写成
    "../别的案子/图.svg" 或绝对路径，不读：否则导出时可能把别的案件的图带进您要发出去的 PPT。"""
    base = os.path.abspath(base_dir or ".")
    rel = str(rel or "").replace("\\", "/")          # Windows 上写的 assets\\x.svg：在 Mac 上也认（文件名里不会有反斜杠）
    p = os.path.normpath(os.path.join(base, rel))
    return p if p.startswith(base + os.sep) else None

