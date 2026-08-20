---
name: mqc-timeline-master
metadata:
  author: 缪奇川
  version: 2.0.0
  last_updated: 2026-08-19
description: >-
  Turn raw case materials into a faithful, court-ready case timeline (SVG + PNG +
  PPTX + VSDX + drawio, plus a traceability index in Word). Use this whenever the
  user hands over litigation materials — a judgment, complaint, defence, evidence
  list, contract, bank or Alipay statement, WeChat screenshots, scanned exhibits,
  photos, or just a spoken account — and wants the chronology drawn: 时间轴,
  案件经过时间轴, 事实经过, 时间线, 梳理时间, 把经过画出来, 做一张时间轴图,
  诉讼时效时间轴, 履约经过, 付款经过, 供货经过, 催告与送达经过, 两方主张对读.
  Also trigger when the user says 帮我梳理一下这个案子的经过, 把这些材料做成图,
  这些证据整理成时间轴, or supplies scanned/photographed materials with no text
  layer and expects them read. Handles multiple materials at once, mixed formats
  (docx / txt / text-layer PDF / scanned PDF / images), and declares which events
  came from reading images. Default scenario is Chinese litigation; internal
  instructions are in Chinese because the constraints they encode were written
  and argued in Chinese.
---

# 时间轴大师

这个 skill 是 **`mqc-timeline-master`** ——**新诉讼可视化 · New Litigation
Visualization**（把法律画出来）的时间轴模块。它把律师手上的原始材料**忠实还原**成一张
案件经过时间轴。

与 v1（`mqc-litigation-visual-redraw`，重画既有图）的分工：**v1 重画，本模块从材料还原。**
v1 已冻结，本模块复用它的渲染内核与五种格式导出器，不改它一个字。

## 这个 skill 的立场

**它不是一个通用图表工具，是一个还原工具。**

图上的每一个字都要能追回材料原文。所以这里的全部约束都指向一件事：**模型可以答错，
但不许错得无声**。凡是模型的判断，都要能对句子逐一核验。

三条最要紧的红线，违反其一这张图就不能交：

| 绝不 | 改为 |
| --- | --- |
| 手写 SVG 坐标、凭眼睛摆位置 | 写 JSON，几何全部由脚本算 |
| 改写材料的字（换词、调顺序、补字、概括） | 只许删减；卡片每段文字**必须是原句的子序列** |
| 把没发生的事画成发生了（承诺、约定、诉请、我的判断） | 只画客观发生过的事；说不准就不画 |

## 先读什么

**总是先读这一份。** 然后按需要打开，不要全部预载：

| 你要做的 | 读这个 |
| --- | --- |
| 判哪句是事实、抽事项、写正文（模型那一半的活） | `references/model-steps.md` |
| 前后端怎么对接、容量握手、读图、侧标签怎么起名 | `references/front-end.md` |
| 图为什么长这样、每个数从哪来（C / D / M / P 约束表） | `references/layout-constraints.md` |
| 一件事**为什么这么定**、当时否掉了哪些做法 | `docs/adr/`（**动手改之前先读**） |
| 四份 JSON 的形状与判据 | `python scripts/pipeline.py shape verdicts.json` |

`docs/adr/` 那一条要认真：几十轮接力里，同一件事被重新讨论过多次（扫描件能不能读三轮、
侧标签怎么定两轮）。**你想到的做法多半已经被试过并写了失败原因。**

## 黄金律：模型读懂意思，代码算和验

- **模型做**：读材料（含读图）、判哪句是已发生的事实、划分、抽事项、按容量把字写到位。
- **代码做**：算容量、验模型的输出、出图。**代码不做拆解** —— 哪几句属于同一件事，
  是读懂内容之后的判断，正则拿不到（试过一版正则切割器，在真材料上切出三组同名、
  一组吞掉六成句子）。

所以这条路是**两趟**，不是猜一趟：先定骨架 → 代码算出容量 → 再按容量写字。

## 工作流（九步，四轮交互都在前段）

    python scripts/pipeline.py next       # 现在走到第几步、下一步跑什么、缺哪个文件
    python scripts/pipeline.py steps      # 随时打印这张表

**中途接手就先跑 `next`。** 换了会话、跑错顺序、文件写坏之后，不要靠猜 —— 它按产物
而不是自称判断走到了哪一步。

**没有「一键出图」，这是故意的**：下面九步里有四步必须等用户回答，
一口气跑完等于替他答了那四轮，而那四轮是这个 skill 的设计核心。

| 命令 | 谁做 | 做什么 | 要先写的文件 |
| --- | --- | --- | --- |
| `read <材料...>` | 代码 | 读材料、切句、认叙述块 | |
| `pick` | **用户** | 第一轮：勾材料来源（可全选；只有一份时自动跳过） | |
| `span <编号\|全部>` | **用户** | 第二轮：勾时间段（粒度按跨度自适应：多年按年、半年按季度） | |
| `style <1-4>` | **用户** | 第三轮：呈报给谁 → 白描 / 奇川风 / 歸藏风 / 让我定 | |
| `offer` | 模型 | 划分并给勾选清单 | `verdicts.json` + `parts.json` |
| `budget <编号\|all>` | **用户** | 勾哪几个部分 | |
| `capacity` | 代码 | 按真实骨架算形态与容量 | `skeleton.json` |
| `title '…'` | 模型 | 图名（容量内） | |
| `render <出图.svg>` | 代码 | 校验 → 出图 → 顺带写溯源索引 | `items.json` |

第三轮的三档对应三种风格：**法官**（开庭、提交法院）→ 白描；**当事人与客户**（当面讲、
微信发）→ 奇川风；**同行、讲课、公众号** → 歸藏风。

## 扫描件与照片：读图三步

律师给的材料几乎总有扫描件与照片，对方提交的那部分尤其如此。**不读图就永远只看得见
一方，而只看见一方的时间轴恰恰是最危险的产物** —— 它看起来完整，实际是单方陈述。

    python scripts/read_image.py probe 材料.pdf            # ① 逐页量可读字符
    python scripts/read_image.py rasterize 材料.pdf pages/ # ② 150 DPI 栅格化
    #                                                       ③ 你逐页看图，写转写稿
    python scripts/read_image.py check 转写账目.json        # ④ 页数账 + 编号缺号

用的全是 poppler 自带命令，**不装模型、不调 API**。判据是「逐页可读字符数」，
不是「`pdffonts` 有没有字体」（真材料上有反例）。

转写稿要**存档**（Markdown，每页一节、标页码、写明「这是转写不是原件」），并**作为材料**
进管线 —— 这样全套忠实判据原封不动生效。图像来源的事项标 `medium: "image"`、
`locator` 用「第 N 页」、`image_docs.json` 列出读了图的材料，出图时会打印
「这些事项未经逐字核验」。细节见 `references/front-end.md` 与 ADR 0001、0002。

## 交付什么

一次出五种可编辑格式加一份溯源索引：

| 格式 | 给谁用 |
| --- | --- |
| SVG | 主交付物，插进 Word、再编辑 |
| PNG | 预览、归档、微信发 |
| PPTX | 讲课、庭前演示，每个对象可改 |
| VSDX | ProcessOn / Visio / WPS |
| drawio | draw.io 内继续改 |
| 溯源索引 docx | 图上每个元素出自材料何处（五列三线表） |

pptx 与 vsdx 是**读最终那张 SVG** 逐元素转出来的，所以「交付的就是那张图」。

## 集中红线

| 绝不 | 改为 |
| --- | --- |
| 手写 SVG 坐标 | 写 JSON，几何由脚本算 |
| 改写材料的字 | 只许删减，卡片每段必须是原句的**子序列** |
| 编造日期，或把「2020 年」判成 2020/1/1 | `certainty` 四档按材料精度填；`raw` 必须逐字可查 |
| 把**承诺或约定的时点**当事实（付款计划的付款日、合同交货期限） | 不进主轴；要画「到期未付」，材料里得另有记载 |
| 把**诉请、申请事项、法律评价**当事实 | 那是要什么，不是发生了什么 |
| 侧标签写法律定性（自认、违约、抗辩…） | 只写材料上写着的身份；说不准就不出侧标签 |
| 一方材料却分两侧，标「原告主张 / 被告主张」 | **只有一方叙述就是单侧** —— 一方转述对方的话有身份性 |
| 图上出现省略号、截断、缩字号 | 超容量在出图前**拒绝**并要求改短 |
| 为了好看等距画不等距的时间 | 那会宣称一个材料没有的精度；比例轴不成立就走编号型 |
| 自己拍视觉决定（颜色、字号、要不要标记） | 视觉决定归作者，问他 |

## 三种图种，由材料决定

| 图种 | 什么时候用 |
| --- | --- |
| 编号型 | 时点密、跨度不成比例、或无确切日期。轴上距离只表先后。**它永远画得出**，是阶梯的底 |
| 日期型 | 全部时点精确到日、且在轴上分得开。轴按等长单位格铺开，**距离本身在说话** |
| 期间型 | 争点是几段有长度的期间，且互相重叠或包含 —— 条身长度与重叠位置就是论点 |

**图种不由人选，由材料的性质按几何算出**，走不通就自动落到下一档（`render_figure.deliver`
永远给得出一张图）。事项多到横向排不下时自动转纵向并分页。

## 环境

Python 3，零第三方依赖（读 docx 时用 `python-docx`，出 PNG 与栅格化用 poppler /
LibreOffice，溯源索引用 node 的 docx 库）。全部脚本在 `scripts/`，全部守卫在
`tests/run_checks.py`（跑一次约半分钟，两百多条判据；确切条数看它自己，**不要在这里写死数字** —— 写死就会漂）。

改动之前跑一次 `python tests/run_checks.py`，改完再跑一次 —— **它红了就是你改坏了**。
