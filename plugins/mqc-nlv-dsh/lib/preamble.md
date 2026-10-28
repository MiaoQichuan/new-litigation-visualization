## 在 DeepSeek Harness 里怎么运行本技能（新诉讼可视化插件版，先读这一节）

本技能随「新诉讼可视化」插件安装，技能目录就是上面给出的 Base directory。下文正文写给所有 AI 助手，
在 DeepSeek Harness 里有三处要按本节的做法改：

1. **运行脚本一律用 `nlv_run` 工具，不要在终端里敲 `python3` / `python`。**
   Windows 上 DeepSeek Harness 用 PowerShell 执行命令，那里没有 `python3` 这个命令，中文路径与引号也容易出错。
   正文里写成 `python3 <本技能目录>/scripts/x.py 参数1 参数2` 的命令，等于调用：
   `nlv_run`，`skill` 填 `{{skill}}`，`script` 填 `scripts/x.py`，`args` 填 `["参数1", "参数2"]`（每项一个，不加引号）。
   要运行另一个技能的脚本（例如正文让你调用法律图表大师），`skill` 填那个技能的名字。
   脚本打印的「下一步」命令若写的是绝对路径，`script` 直接填那个路径也可以。
   脚本在用户的工作区里运行：参数里指向技能目录内文件的（如 `examples/a.json`），要写成 Base directory 拼出的完整路径；
   用户的材料与输出路径照常写相对工作区的路径。
2. **第一次用、或 `nlv_run` 说找不到 Python 时，先调 `nlv_check`**，把它给出的安装说明原样转告用户，不要自己编步骤。
3. **出完成品，用 `present` 工具交付。** `nlv_run` 的结果会列出本次新写出的文件；把成品（SVG、PPTX、XLSX、DOCX、PNG）
   用 `present` 交给用户，用户在对话里点一下就能在右侧预览。中间文件（.json、日志）不必交付。

其余照正文：材料与产物放在用户的工作区（会话的工作目录），不写进技能目录；输入输出路径写相对工作区的路径；
参考文件（references/…、examples/…）用读文件工具按 Base directory 拼出完整路径再读；脚本打印的核对清单照原样转告用户。
