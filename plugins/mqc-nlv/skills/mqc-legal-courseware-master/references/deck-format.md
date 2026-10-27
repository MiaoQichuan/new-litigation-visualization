# deck.json 格式（mqc-nlv/deck@2）

```text
{
  "schema": "mqc-nlv/deck@2",          必填，固定（旧的 deck@1 读入时自动升级）
  "title":  "课件标题",                 导出文件名用它
  "style":  "奇川风" | "歸藏风" | "自定义",   整套一种（自定义来自名片目录的 style.json；旧的律所风格名读入时认作「自定义」）
  "frame":  { "mode": "full" } | { "mode": "reserve", "top", "right", "bottom", "left" }   可选：版面（预留位置）
  "slides": [ 页, ... ]                 至少一页
}

页   = { "id": "唯一", "modules": [ 模块, ... ], "parked": [ 模块, ... ]（可选：暂存区，不导出） }
模块 = { "id": "页内唯一", "type": 类型, "x": 栏, "y": 行, "w": 宽, "h": 高, ...内容字段,
         "tone": 外观（可选）, "join": false（可选：不与邻卡连组）, "bleed": true（可选：整页出血） }
```

## 网格

| 常数 | 值 | 说明 |
| --- | --- | --- |
| 画布 | 1280 × 720 | 16:9 |
| 栏 × 行 | 12 × 6 | x 取 0–11，y 取 0–5 |
| 页边距 | 左右 48、上下 56 | |
| 一栏宽 / 一行高 | 84 / 88 | |
| 间距 | 16 | 模块之间的呼吸 |
| 连组间距 | 4 | 连成一组的卡片之间 |
| 卡片圆角 | 奇川风 外角 12、内角 4；歸藏风 直角 | |

格子 (x, y, w, h) 在页面上的位置：`left = 48 + x × 100`，`top = 56 + y × 104`，`width = 84w + 16(w−1)`，`height = 88h + 16(h−1)`。

## 模块

| type | 中文 | 内容字段 | 最小 | 最大高 | 默认外观 | 连组家族 |
| --- | --- | --- | --- | --- | --- | --- |
| title | 标题 | text、level（page / cover / section）、kicker、sub | 3×1 | 3 | bare | — |
| text | 正文 | heading、text | 3×2 | | card | 正文与要点 |
| bullets | 要点 | heading、items | 3×2 | | card | 正文与要点 |
| stat | 大数字 | value、label、note、from | 2×2 | | card | 大数字 |
| step | 编号卡 | heading、text | 3×2 | | card | 编号卡 |
| quote | 金句 | text、source（必填） | 4×2 | | card | — |
| chart | V6 图表 | file 或 spec；可选 pins | 6×4 | | outline | — |
| figure | V1–V5 的图 | file、from；或 V5：data、from（含 V5）、part；可选 crop、pins、focus | 4×3 | | outline | — |
| note | 注释 | text | 2×1 | 1 | bare | — |
| conclusion | 一句话结论 | text（一两句） | 4×1 | 2 | bare | — |
| statute | 法条 | law、article、text（照录原文） | 4×2 | | card | 法条与要旨 |
| holding | 裁判要旨 | text、court、case_no（出处至少一项） | 4×2 | | card | 法条与要旨 |
| case | 案例 | case_no（必填）、court、cause、heading、result、point | 3×2 | | card | 案例 |
| issue | 争议焦点 | heading、text（自动编「争议焦点一、二…」） | 3×2 | | card | 争议焦点 |
| risk | 风险提示 | heading、text | 3×2 | | card | 风险提示 |
| evidence | 证据 | heading、items（「名称——证明目的」） | 5×2 | | card | — |
| logo | Logo | （来自律所名片） | 1×1 | 2 | bare | — |
| profile | 介绍 | who：firm / lawyer:&lt;id&gt;（内容来自名片；可写 intro、areas、title 覆盖） | 4×3 | | card | — |
| contact | 联系方式 | who（可选；来自名片）；1 行高时横排 | 3×1 | | card | — |

外观：`card` 卡片、`accent` 重音卡（只给 text / bullets / step / stat / issue / risk）、`outline` 描边、`bare` 无底。

课件级可选字段：`"footer_logo": true / false`（内容页左下角放小 Logo；不写就按律所名片的设置）。

## 连成一组

两张模块连成一组，当且仅当：同一家族、外观相同且不是 bare、都没写 `join: false`，并且
- 并排：上边对齐、等高、左边那张的右缘正好接上右边那张（`a.x + a.w == b.x`）；或
- 上下叠：左边对齐、等宽、上面那张的下缘正好接上下面那张。

连组后相接的边各向缝里外扩 6px（16 → 4），碰到相接边的角用内角半径。

## 组合（模板）

分三组：**场景**（选图时点的，新建一页按场景排好）、**排法**（以图为中心）、**整套课件**（在编辑器「更多」里）。

| 名字 | 中文 | 组 | 模块 |
| --- | --- | --- | --- |
| scene-timeline | 案情经过 | 场景 | title · figure(V2) 0,1,12,4 · conclusion 0,5,12,1 |
| scene-relation | 法律关系 | 场景 | title · figure(V3) 0,1,8,5 · bullets(numbered) 8,1,4,5 |
| scene-confront | 双方攻防 | 场景 | title · figure(V5) 0,1,12,4 · conclusion 0,5,12,1 |
| scene-chronicle | 事件脉络 | 场景 | title · figure(V4) 0,1,7,5 · issue 7,1,5,3 · risk 7,4,5,2 |
| scene-data | 类案数据 | 场景 | title · chart 0,1,8,4 · conclusion 0,5,8,1 · stat 8,1,4,2 · bullets 8,3,4,3 |
| scene-redraw | 重画的图 | 场景 | title · figure(V1) 0,1,12,4 · conclusion 0,5,12,1 |
| chart-conclusion | 图 + 一句结论 | 排法 | title · chart 0,1,12,4 · conclusion 0,5,12,1 |
| figure-basis | 图 + 依据 | 排法 | title · figure 0,1,7,5 · statute 7,1,5,2 · holding 7,3,5,3 |
| chart-over-bullets | 上图下要点 | 排法 | chart 0,0,12,4 · bullets 0,4,12,2 |

下表是原有的组合（「组」一栏：有图的在「排法」，其余在「整套课件」；timeline 现名「整宽时间轴」）。

| 名字 | 中文 | 模块 |
| --- | --- | --- |
| cover-brand | 封面（带 Logo） | logo 0,0,2,1 · title(cover) 0,2,12,3 · note 0,5,12,1 |
| firm-intro | 律所介绍 | logo 0,0,2,1 · title 2,0,10,1 · profile(firm) 0,1,12,4 · contact 0,5,12,1 |
| lawyer-intro | 律师简介 | title · profile 0,1,7,5 · bullets 7,1,5,5 |
| closing | 结束页 | logo 0,0,2,1 · title(section) 0,2,12,2 · contact 0,4,12,1 |
| statute-read | 法条解读 | title · statute 0,1,6,3 · risk 0,4,6,2 · bullets 6,1,6,5 |
| case-review | 案例复盘 | title · case 0,1,4,5 · holding 4,1,8,2 · bullets 4,3,8,3 |
| issues | 争议焦点 | title · issue ×3（各 4,5） |
| trial-prep | 庭前准备 | title · figure(V3) 0,1,8,5 · issue 8,1,4,3 · risk 8,4,4,2 |
| evidence | 证据梳理 | title · evidence 0,1,7,5 · figure(V2) 7,1,5,5 |
| timeline | 案情经过 | title · figure(V2) 0,1,12,5 |
| similar-cases | 类案研究 | title · chart 0,1,8,5 · stat 8,1,4,2 · bullets 8,3,4,3 |
| cover | 封面 | title(cover) 0,2,12,3 · note 0,5,12,1 |
| section | 章节页 | title(section) 0,2,12,2 |
| chart-notes | 一图一讲 | title 0,0,12,1 · chart 0,1,8,5 · bullets 8,1,4,5 |
| chart-stat | 一图一数一讲 | title · chart 0,1,8,5 · stat 8,1,4,2 · bullets 8,3,4,3 |
| chart-full | 整页图 | title · chart 0,1,12,5 |
| two-charts | 左右两图 | title · chart 0,1,6,5 · chart 6,1,6,5 |
| chart-quote | 图 + 金句 | title · chart 0,1,7,5 · quote 7,1,5,5 |
| kpi | 数字一排 | title · stat ×4（各 3,2）· text 0,3,12,3 |
| three-steps | 三卡并列 | title · step ×3（各 4,5） |
| compare | 左右对照 | title · bullets 0,1,6,5 · bullets 6,1,6,5 |
| bullets | 标题 + 要点 | title · bullets 0,1,12,5 |
| chart-bleed | 整页出血图 | chart 0,0,12,6 bleed |
| figure-full | 整页关系图 | figure 0,0,12,6 bleed |
| quote | 金句页 | quote 1,1,10,4 |

（title 都是 0,0,12,1。坐标次序 x,y,w,h。）

## 图内元素、读图编号、切片（0.5.0）

- 图卡（figure）、图表卡（chart）可写 `pins`：图内元素键的列表（如 `"node:#4"`、`"edge:#10"`、`"id:y2019"`），按顺序编号，最多 9 个、不重复。
- 图卡可写 `crop`：图内元素键的列表，只取这些元素那一块。
- 图卡、图表卡可写 `focus`：图内元素键（图表为 `id:<data-id>`）的列表，这些元素照常，其余调浅。
- 图表卡可带 `recipe`（V6 场景库的场景编号，如 `GEN-10`）与 `sample: true`（0.9.0，编辑器从图表库放进来时写）：
  `sample` 表示 spec 还是 V6 的示例数据，导出前一定被拦下；换成用户的数据（AI apply 带 spec / file，或编辑器里改了说明点「应用」）后去掉。
  只给图表卡。
- 要点卡可写 `numbered: true`：前几条与图上的编号同号。任何模块可写 `locked: true`：整理时不动、编辑器里拖不动。
- 课件可写 `frame`：`{"mode": "full"}` 或 `{"mode": "reserve", "top", "right", "bottom", "left"}`（设计像素，整页 1280×720）。
- 一句话结论卡 `conclusion`：`text`（一两句），最小 4×1、最多 2 行高，不做重音卡。
- V5 图卡可不写 `file`，改写 `data`（V5 数据文件）、`from`（含 V5）与可选的 `part`（要件序号，从 0 起）：拼页时按图卡宽度现出图。
- `style` 可写 `自定义`（课件目录或名片目录里有自定义风格文件时）。

## 校验会拒的

schema 不对；style 不是奇川风 / 歸藏风 / 自定义（写「自定义」却还没做自定义风格也拒）；版面设定不对或预留得太多；没有页；页 id 缺失或重复；模块 id 缺失或重复；类型不认识；坐标不是整数；
出了网格；比最小尺寸小、比最大高度高；外观不认识；重音卡给了不该给的类型；出血不是整页的图；两个模块重叠。

## 拼页会拦的（导出前必须改掉）

空页（还没选场景）；空卡片；字在 16px 下仍放不下；金句没写出处；法条没写法律名称或原文；裁判要旨没写出处；案例没写案号；
名片里没有 Logo / 介绍 / 联系方式却用了对应的卡；大数字的 `from` 推不出它；V6 守卫没过；V1–V5 的图风格不符或缩到字看不清。

## 律所风格文件（style.json，mqc-nlv/firm-style@1）

由 `firm_style.py make` 从模板读取结果生成，放在律所名片目录。字段：`name`、`base`（奇川风 / 歸藏风：图表的灰阶梯与几何按它）、
`colors`（accent 主色、accent_dark、paper、ink 正文、ink2 次要字、note、title 标题色、card 卡片、outline 描边、cover_bg / cover_ink /
cover_ink2 / cover_card 深底页用）、`fonts`（title: sans 粗黑体）、`radius`（outer / inner）、`dark_pages`（["cover", "section"]）、
`logo_box`、`template_margins`、`left_out`（没放进来的辅助色及理由）。

律所名片 brand.json 另可写 `"logo_on_dark": "logo-on-dark.png"`：深底页用的白字版 Logo。
