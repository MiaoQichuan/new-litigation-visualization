# GitHub 仓库设置清单

开源前照这份过一遍。**这不是代码，是发布前的手工步骤。**

## About（仓库右侧那一栏）

**Description**（一行，会出现在搜索结果里）：

```
把法律画出来 · 给法律人的诉讼可视化工具集，八个模块：诉讼图重画、时间轴、法律关系图、大事记表、庭审对抗图、法律图表、法律课件、案件看板。照录原文、每项可追溯、脚本算图、不联网。Claude Code / DeepSeek Harness 通用。
```

英文版（若要双语）：

```
Make the Law Visible — eight litigation visualization skills for lawyers: visual redraw, timeline, legal relationship map, case chronicle, trial confrontation map, legal charts, courseware and an interactive case board. Verbatim, traceable, computed by scripts, offline. For Claude Code, DeepSeek Harness and any agent that reads SKILL.md.
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

Settings → General → Social preview → 上传 `assets/banner.png`（与首页顶部同一张横幅，3:1）。
需要竖版海报时（公众号、朋友圈），用 `assets/cover.png`。

## 发布前自查

```bash
# 八个模块的回归都要绿
python3 plugins/mqc-nlv/skills/mqc-litigation-visual-redraw/tests/run_checks.py
python3 plugins/mqc-nlv/skills/mqc-timeline-master/tests/run_checks.py
python3 plugins/mqc-nlv/skills/mqc-chronicle-master/tests/run_checks.py
python3 plugins/mqc-nlv/skills/mqc-trial-confrontation-master/tests/run_checks.py
python3 plugins/mqc-nlv/skills/mqc-legal-relation-master/tests/make_checks.py
python3 plugins/mqc-nlv/skills/mqc-legal-chart-master/tests/release_gate.py
python3 plugins/mqc-nlv/skills/mqc-legal-courseware-master/tests/run_checks.py
python3 plugins/mqc-nlv/skills/mqc-fact-chronology-master/tests/run_checks.py
node plugins/mqc-nlv-dsh/tests/dsh_checks.mjs

# 脱敏：仓库里不许有真实案件的当事人、案号、账号
python3 plugins/mqc-nlv/skills/mqc-timeline-master/tests/check_anonymised.py
```

**路径必须全部是 ASCII。** 重画、时间轴大师各有一条守卫盯本模块，案件看板大师那条查整个仓库，理由是 Windows 的
`Expand-Archive` 按系统代码页读 ZIP 条目名，中文文件名会让解压直接失败 ——
而下载 ZIP 是大多数人拿到仓库的方式。内容用中文没问题，文件名不行。

## README 里的图

都在仓库里，不引外链；中英两版首页共用，带 `-en` 的是英文版：

| 图 | 位置 |
| --- | --- |
| 横幅 | `assets/banner.png` |
| 亮点 | `assets/highlights.png` · `assets/highlights-en.png` |
| 八个模块成品墙 | `assets/modules.png` · `assets/modules-en.png`（虚构示例与出图脚本在 `assets/src/showcase/`） |
| 三步上手 | `assets/quickstart.png` |
| 怎么配合 | `assets/flow.png` · `assets/flow-en.png`（由 `assets/src/flow.py` 生成） |
| 案件看板截图 | `assets/v8-board.png` |
| 模块图标 | `assets/icons/v1.png` … `v8.png`、`dsh.png` |
| 作者名片 | `assets/author-card.jpg` |
| 竖版封面（首页不用，对外分享用） | `assets/cover.png` |

## 社区与安全设置（开源当天做一次）

仓库里已备好 GitHub「Community Standards」要的全部文件：`README.md`、`LICENSE`（AGPL-3.0）、
`CONTRIBUTING.md`、`CODE_OF_CONDUCT.md`、`SECURITY.md`、`CITATION.cff`、
`.github/ISSUE_TEMPLATE/`（问题、建议两种表单）、`.github/PULL_REQUEST_TEMPLATE.md`。
推上去之后，在网页上再点几处：

1. **Settings → General → Visibility**：改成 Public。
2. **Settings → Code security**：打开 *Private vulnerability reporting*（SECURITY.md 指向它）、
   *Dependabot alerts*、*Secret scanning*（公开仓库免费）。
3. **Settings → General → Features**：Issues 打开；Discussions 可选。
4. **Insights → Community Standards**：应当全部打勾，有缺项就照提示补。
5. **Settings → Branches**：给 `main` 加保护规则，要求 `checks` 通过才能合并。
6. **Releases**：打一个 tag（`v3.1.0`，与 `plugin.json` 的版本一致；上一版是 v3.0.0）并写发布说明；把 `python3 plugins/mqc-nlv-dsh/build.py` 打出的 `mqc-nlv-dsh-3.1.0.tgz` 作为附件上传，DeepSeek Harness 用户下载它安装。

**仓库里不该出现的东西**（推送前 `git status` 看一眼）：`__pycache__/`、`.DS_Store`、`__MACOSX/`、
真实案件材料、律所模板与 Logo、任何本机路径。`.gitignore` 已覆盖前两项。

