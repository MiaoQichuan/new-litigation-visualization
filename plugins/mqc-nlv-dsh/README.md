# 新诉讼可视化 · DeepSeek Harness 插件（mqc-nlv-dsh）

把「新诉讼可视化」的七个技能（V1–V7）作为一个插件装进 DeepSeek Harness：时间轴、法律关系图、大事记、
庭审对抗图、法律图表、法律课件，以及诉讼图重画。装好后在对话里用中文说需求即可，成品出现在对话的文件卡片里，
点一下在右侧预览。

## 安装

1. 电脑上先装 **Python 3.9 或更新的版本**（python.org 下载；Windows 安装时第一页勾选「Add python.exe to PATH」）。
2. 在 DeepSeek Harness 左侧点 **插件 → 添加插件**，在输入框里填下面任意一种，点「安装」，再「立即启用」：
   - 下载好的安装包的完整路径，例如 `C:\Users\您\Downloads\mqc-nlv-dsh-3.0.0.tgz`（**不要带引号**：Windows「复制文件地址」会自动加上引号，要删掉；安装源保持「中国大陆镜像源」，不要改成自定义地址）
   - 发布到 npm 之后：`mqc-nlv-dsh`
3. 完全退出 DeepSeek Harness 再打开，新建会话，说「检查新诉讼可视化的环境」。

以前手动把技能放进过 `.dsh/skills` 或 `.agents/skills` 的，请先移走那些同名文件夹：它们会优先于插件里的版本。

## 插件里有什么

| 部分 | 作用 |
| --- | --- |
| 七个技能 | 原样随包，正文前加一段「在 DeepSeek Harness 里怎么运行」的说明 |
| `nlv_check` 工具 | 找本机的 Python（Windows 上 `py`、`python` 与默认安装目录都认），查可选能力，缺了说怎么装 |
| `nlv_run` 工具 | 在会话工作区里运行技能脚本：参数直传、不经 PowerShell，中文路径与引号不出错；只运行随包脚本 |
| openpyxl | 出 Excel 用，随包附带，不用 pip 安装 |
| docx（npm） | 写 Word 用（时间轴溯源索引、大事记 Word 版），随包附带；本机需有 Node.js |

成品由模型用 DeepSeek Harness 自带的 `present` 工具交付，对话里出现文件卡片；SVG、PPTX、Excel、PDF 都能在右侧预览。

## 安全与隐私

全部在本机运行，不联网、不调用外部接口。`nlv_run` 只运行随插件附带的技能脚本，工作目录限定在当前会话的工作区之内。

## 从源码打包

```bash
python3 plugins/mqc-nlv-dsh/build.py          # 输出 plugins/mqc-nlv-dsh/dist/mqc-nlv-dsh-<版本>.tgz
node plugins/mqc-nlv-dsh/tests/dsh_checks.mjs  # 用模拟宿主跑一遍注册、调用与七个技能的出图
```

## 许可

AGPL-3.0-only。作者：缪奇川。随包的 openpyxl、et_xmlfile、docx 为 MIT，见 `THIRD-PARTY-NOTICES.md`。
