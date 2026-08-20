# mqc-timeline-master · 时间轴大师

> **新诉讼可视化 · New Litigation Visualization** 的时间轴模块。
> 把律师手上的原始材料，忠实还原成一张能直接打印、能溯源、排布上不会出错的
> 诉讼时间轴。

**时间轴大师，用数学，画准一张时间轴。**

与第一个模块 [`mqc-litigation-visual-redraw`（诉讼可视化重画）](../mqc-litigation-visual-redraw/)
的分工：**重画是「你先画一张，我升级审美」；时间轴大师直接吃材料。**
重画那一套的全部优势，这里整套继承过来 —— 同一套几何、同一套视觉、同一套导出、
同一套纪律。

## 它做什么

| 阶段 | 做什么 |
| --- | --- |
| 读材料 | 判决书 · 起诉状 · 答辩状 · 合同 · 证据目录 · 银行与支付宝流水 · 微信聊天记录 · 扫描件 · 手机照片 · 一段口述 |
| 算排布 | 图种 · 层数 · 位置 · 尺寸 · 字数容量，全部由几何算出，不查表 |
| 出成品 | SVG · PNG · PPTX · VSDX · drawio，另附一份溯源索引 Word |

没有文字层的扫描件与照片也读得出来：先探测（逐页量可读字符数），再按 150 DPI
栅格化，然后逐页看图。**不引 OCR 依赖**，用的是 poppler 自带命令。交付时会声明
哪几份材料出自读图。

## 它最多问你五个问题

1. **材料用哪几份** —— 只有一份就不问
2. **时间取哪一段** —— 日期不足八个就不问
3. **风格用哪一种** —— 奇川风推荐；打印用白描；讲课用歸藏风。不回默认奇川风
4. **整份还是取几段** —— 它读完会给一份清单，每段标好首末句原文
5. **深红标在哪一处** —— 全图只标一处，本案的胜负手。只有奇川风才问

该问的才问，问完就出图，之后不再打断你。

## 为什么画得准

- **排布是算出来的，不是摆出来的。** 卡宽由座次算、层数由拥挤度算、字数容量二分
  实测。同一份材料，换谁跑都是同一张图。
- **图上的字，是材料里的字。** 每一段正文必须是原句的子序列 —— 只许删，不许改写、
  不许调顺序、不许补字。换一个词都会在出图之前被拦住。
- **算不出就拒绝，不降级硬画。** 任何一条约束不成立，当场停下并指名是哪一条。
  图上不出现省略号，也不缩字号。

排布的每一个数都从 A4 纸的物理尺寸算起（绘图宽 958 = 1070 − 留白 56 × 2），
所以插进 Word 直接能印。

## 怎么装

```
/plugin marketplace add MiaoQichuan/new-litigation-visualization
/plugin install mqc-nlv@mqc-nlv
```

装完在有 shell 权限的环境里跑一次环境自检：

```bash
python3 ../mqc-litigation-visual-redraw/scripts/doctor.py
```

### 在 DeepSeek Harness 里用

这是一个标准的 `SKILL.md` 目录，**没有任何产品特定的胶水代码**，所以凡是能读
skill 指令的 agent 都能用：Claude Code、Codex、DeepSeek Harness、Cursor、
Gemini CLI、Copilot、Cline、Aider 等等。**同一份仓库，不需要维护两套。**

DeepSeek Harness 直接挂目录（dsh 的技能发现是扁平的，指到装着本目录的那一层，
它会扫到下面每一个 `<模块名>/SKILL.md`）：

```yaml
skills:
  local:
    customSkillDirs:
      - "./new-litigation-visualization/plugins/mqc-nlv/skills"
```

dsh 的技能发现优先级（先命中先生效）：项目 `.dsh` → 项目 `.agents` →
`customSkillDirs` → 用户 `.dsh` → 用户 `.agents`。

限制说在前面：

- 脚本用 Python 3（零第三方依赖）。出 PNG 需要 LibreOffice 或 poppler，
  读扫描件需要 poppler 的 `pdftoppm`，溯源索引需要 node。
- 只读你给的材料、只往你指定的目录写文件，**不联网、不调外部 API、不需要凭据**。
- dsh 目前把 `allowed-tools` / `disallowed-tools` 当未知字段处理，
  技能内的工具约束需要你在 harness 层自行保证。

## 它不做什么

- **不做脱敏。** 你拿什么材料来，它就照原样画出来。要脱敏，在给它材料之前自己做。
- **不做法律判断。** 它不评价证据、不认定事实、不给意见。它只把材料里已经写着的
  事实经过摆到纸上。
- **不把没发生的事画成发生了。** 合同条款是约定，诉请是主张，付款计划是承诺 ——
  三者都不进主轴。

## 工程

Python 3，零第三方依赖。全部脚本在 `scripts/`，全部守卫在 `tests/run_checks.py`
（跑一次约半分钟，两百多条判据）。改动之前跑一次，改完再跑一次 —— 它红了就是改坏了。

约束表在 `references/layout-constraints.md`（C / D / M / P 四系列，每条带实测数字
与当初撞坏的记录）。一件事**为什么这么定、当时否掉了哪些做法**，看 `docs/adr/`。

## 许可

MIT。作者：缪奇川 律师。
