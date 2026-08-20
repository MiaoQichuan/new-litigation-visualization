# GitHub 仓库设置清单

开源前照这份过一遍。**这不是代码，是发布前的手工步骤。**

## About（仓库右侧那一栏）

**Description**（一行，会出现在搜索结果里）：

```
把法律画出来 · 给法律人的诉讼可视化工具集：把凌乱的诉讼图重画成能进材料的图，或直接读案件材料画准一张时间轴。Claude Skill / DeepSeek Harness 通用。
```

英文版（若要双语）：

```
Make the Law Visible — litigation visualisation skills for lawyers: redraw a messy case diagram into a court-ready one, or turn raw case materials into a faithful timeline. Works in Claude Code, Codex, DeepSeek Harness and any agent that reads SKILL.md.
```

**Website**：公众号或个人站（若有）

## Topics（标签）

按三组加，每组都有人在搜：

**这是什么**

```
agent-skills   claude-skills   claude-code   dsh-plugin   deepseek-harness
codex          cursor          agent-skill
```

**它做什么**

```
legal-tech     litigation      timeline       visualization   diagram
svg            data-visualization             legal
```

**怎么做的**

```
deterministic-rendering        python           zero-dependency
```

> `dsh-plugin` 这个 topic 是 DeepSeek Harness 社区插件入口的聚合依据 —— 加上它，
> GitHub 会自动把仓库收进那个 topic 页，不需要向 DeepSeek 主仓库交 PR。

一条命令加完（GitHub CLI）：

```bash
gh repo edit MiaoQichuan/new-litigation-visualization \
  --add-topic agent-skills --add-topic claude-skills --add-topic claude-code \
  --add-topic dsh-plugin --add-topic deepseek-harness --add-topic codex \
  --add-topic legal-tech --add-topic litigation --add-topic timeline \
  --add-topic visualization --add-topic diagram --add-topic svg \
  --add-topic legal --add-topic python --add-topic zero-dependency
```

## Social preview（分享时显示的大图）

Settings → General → Social preview → 上传
`plugins/mqc-nlv/skills/mqc-timeline-master/assets/screenshots/timeline-example.png`

那张是真实输出，比任何宣传图都有说服力。

## 发布前自查

```bash
# 两个模块的回归都要绿
python3 plugins/mqc-nlv/skills/mqc-litigation-visual-redraw/tests/run_checks.py
python3 plugins/mqc-nlv/skills/mqc-timeline-master/tests/run_checks.py

# 脱敏：仓库里不许有真实案件的当事人、案号、账号
python3 plugins/mqc-nlv/skills/mqc-timeline-master/tests/check_anonymised.py
```

**路径必须全部是 ASCII。** 两个模块各有一条守卫盯这件事，理由是 Windows 的
`Expand-Archive` 按系统代码页读 ZIP 条目名，中文文件名会让解压直接失败 ——
而下载 ZIP 是大多数人拿到仓库的方式。内容用中文没问题，文件名不行。

## README 里的图

八张，都在仓库里，不引外链：

| 图 | 位置 |
| --- | --- |
| logo | `mqc-litigation-visual-redraw/assets/brand/nlv-logo-red.png` |
| 时间轴成品示例 | `mqc-timeline-master/assets/screenshots/timeline-example.png` |
| 三类七种图形 | `mqc-litigation-visual-redraw/assets/longform/seven-layouts.png` |
| 三种视觉模式 | `mqc-litigation-visual-redraw/assets/modes/timeline-dated-3modes.png` |
| Skill 运行全过程 | `mqc-litigation-visual-redraw/assets/longform/how-it-works.png` |
| 01 数学 | `mqc-timeline-master/assets/longform/01-mathematics.png` |
| 02 画准 | `mqc-timeline-master/assets/longform/02-exact.png` |
| 03 时间轴 | `mqc-timeline-master/assets/longform/03-the-figure.png` |

三张长图（01 / 02 / 03）同时提供 SVG，需要放大细看或二次编辑时用那一份。
