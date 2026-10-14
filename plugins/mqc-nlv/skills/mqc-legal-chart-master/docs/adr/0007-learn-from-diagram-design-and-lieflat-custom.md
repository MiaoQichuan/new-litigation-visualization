# 0007 向 diagram-design 与 lieflat-charts-custom 学什么

## 背景

作者又给了两个开源项目：

- **diagram-design**（Cathryn Lavery，MIT，v2.6）：42 种示意图，带风格门禁、客户档案、
  复杂度预算、连线规则与几何自检、批注、无障碍约定、尺寸预设、从 draw.io / Mermaid 导入。
- **lieflat-charts-custom**（PolyForm Noncommercial）：lieflat 的精简分支，7 套整体配色预设，
  按用户说的气质（「莫兰迪」「蓝橙海报感」）选配色。

许可不同，学法也不同（ADR 0001）：diagram-design 是 MIT，可以借代码，但我们这一轮**只学做法、代码自写**，
因为它是 HTML/CSS 示意图，我们是确定性几何 + 守卫，搬过来也用不上；lieflat-custom 是非商用许可，
**只看不抄**。

## 决定：学进来的

| 学自 | 原来的做法 | 我们的版本 |
| --- | --- | --- |
| diagram-design · annotation callout | 斜体衬线旁白 + 虚线贝塞尔引线 + 落点，页边最多两条 | `annotations`：最多两条，右侧批注栏；**引线路线由脚本搜**，不压字、不穿过别的数据；批注里的数字照标题规矩核；守卫 G11 从产物里重读 |
| diagram-design · complexity budget | 每张图最多 9 个节点、12 条连线，超了拆成总览 + 细节 | `spec.BUDGET`：每种图的对象上限集中登记；七成以上在出图计划里提醒拆页 |
| diagram-design · confirm before drawing | 动笔前先说要画什么类型、多大、删掉什么 | `make.py --plan`：只打印出图计划（含守卫结果），不写文件 |
| diagram-design · named profiles | 每个客户一份品牌档案 | `--profile`：律所 / 客户档案，存风格、强调色、画布、字体 |
| diagram-design · size presets | doc-inline、slide、social-og、social-square、A4 | 新增 `square`（公众号配图）、`portrait`（3:4 小红书）、`wide-cover`（头图）；方图与竖图按手机阅读放大字号 |
| diagram-design · accessible SVG | role=img，title 与 desc 是头两个子元素 | 同样做；desc 写图种、口径、n、来源 |
| diagram-design · 类型目录 | fishbone、pyramid、funnel、venn、swimlane、state、layers、paired traces | 场景库登记 8 种新画法（鱼骨、金字塔、漏斗、韦恩、泳道、生命周期环、层层设防、成对推理），配 28 个法律场景 |
| lieflat-custom · 按气质选配色 | 7 套整体配色，按用户的话挑一套 | 9 个**强调色**预设，按题材挑（金融→藏青、ESG→墨绿……）；只换那一处重音，灰阶与几何不动 |

## 决定：不学的

- **整套换色板**（lieflat-custom）：会把奇川风打散，作者要的是「整体统一」。只开放强调色。
- **斜体**（diagram-design 的批注用斜体衬线）：中文没有真斜体，浏览器硬拧的伪斜体难看。批注用宋体常规（奇川风）
  或细黑（歸藏风），靠灰色与位置区分。
- **手绘滤镜、动效**：数据图进 PPTX 与公众号，滤镜在 PowerPoint 里不可编辑；动效留给 V7 工作台。
- **从网站抓品牌色的引导流程**：律所一般就一个品牌色，一份档案文件足够，不必做向导。
- **draw.io / Mermaid 导入**（「抽取，不渲染；重画，不转换」）：这正是 V1 诉讼可视化重画的做法，印证了路线，
  V6 不重复做。

## 否掉的替代方案

- **批注位置让模型写坐标。** 那样位置一错就压字，守卫只能拦不能修，模型要反复试。由脚本搜路，
  模型只说「指向哪个数据、说什么」，与「模型写 JSON、脚本算几何」一致。
- **批注不设条数上限。** 批注一多，图就变成了讲稿。两条是 diagram-design 的经验值，我们照用。
