# 更新记录 · mqc-nlv-dsh（DeepSeek Harness 插件）

## 3.0.0 · 2026-10-28 · 随套件 v3.0.0 首发

新诉讼可视化第一次以 DeepSeek Harness 插件的形式发布：在「插件 → 添加插件」里装一次，七个技能全部到位。

- **七个技能随包注册**（技能提供者 `mqc-nlv-dsh/skill-provider`）：正文与仓库里的 SKILL.md 一字不差，
  前面加一段「在 DeepSeek Harness 里怎么运行」的说明；技能目录作为资源根交给模型。
- **`nlv_check`**：找本机的 Python（Windows 上依次试 `py -3`、`python`、`python3` 与 python.org 默认安装目录；
  macOS 另查 Homebrew 与官方安装位置），列出 Excel、PNG、Word 等可选能力；没有 Python 时给出照做就行的安装说明；
  发现以前手动装在 `.dsh/skills`、`.agents/skills` 的同名技能会遮住插件版时，提醒移走。
- **`nlv_run`**：在会话工作区里运行技能脚本。参数按数组直传给 Python、不经 PowerShell 或 bash；
  只运行随包的 `.py`，工作目录限定在工作区之内；超时与中止都会结束整个进程树；
  结果列出本次新写出的文件，提示模型用 DeepSeek Harness 自带的 `present` 交付，对话里点开即可预览。
  参数里写成技能目录相对路径的示例文件（`examples/…`）自动换成完整路径。
- **openpyxl 随包附带**（MIT，含 et_xmlfile），出 Excel 不用 pip 安装；**npm 的 docx 随包附带**（MIT，只带打包好的一个 CommonJS 文件），
  本机有 Node.js 就能出时间轴溯源索引与大事记的 Word 版（`nlv_run` 把它加进 NODE_PATH）。
- 技能目录自带 `package.json`（`type: commonjs`）：插件包是 ES 模块，不隔开的话技能里用 `require` 的 Node 脚本会被当成 ES 模块而出错
  （实测在打包版里大事记的 Word 版因此没写出、退回了 Markdown 版；修好后回归里核对 Word 真的写出来）。
- 图标：随套件 V1–V7 的图标家族（同一倾角、深红 + 暖灰 + 浅灰、出血裁切），画的是「一块模块插进插座」。
- 包里不带只给 README 看的展示图，约 2.6 MB；同一份源码打出的包逐字节一致。
- 回归：`node plugins/mqc-nlv-dsh/tests/dsh_checks.mjs`（64 项：打包、按包名加载、七个技能各跑一次示例、
  越权路径被拒、取消与超时、没有 Python 时的说法、清单字段）；设 `DSH_SRC` 时改用 DeepSeek Harness 源码里的
  `defineTool` 真实现核对参数表。
