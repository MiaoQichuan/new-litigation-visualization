# 更新记录

## 1.1.0

分析表与对抗图一个字节不变（同一份输入出的 SVG 与改前逐字节一致）。

- 新：`pipeline.py --demo` 用随包示例一条命令跑通；`--check` 只查本机环境，逐项说出 Excel、SVG、PNG 各缺什么。
- 修：不给参数时原来甩 IndexError 堆栈，现在打印用法。
- 修：输入骨架不全（缺 case／parts／claim_bases／elements 或要件字段）原来跑到出表那一步才甩 KeyError 堆栈，
  前面的校验白跑；现在开跑前一次说全「哪一条要件缺哪个字段」，并指到可粘贴骨架。
- 修：出表、出图某一步失败时原来甩 CalledProcessError 堆栈，现在说是第几步、原因在上面几行。
- 修：选了 PNG 而本机缺 Pillow 或转图工具时，原来整条流程中断、Excel 与 SVG 也算失败；现在照常交付 Excel 与 SVG，说明 PNG 缺什么。
- 文档：SKILL.md 加「怎么用」「依赖」「安全与隐私」「文档地图」；新增 `references/faq.md`
  （三步上手、常见误用、报错对照与各校验编号的改法、本诉与反诉同图、术语速查、已知限制）；README 重写。
- SKILL.md 的依赖改准：必需只有 openpyxl（出 Excel），PNG 所需的 pillow、numpy、cairosvg 列为可选。
- 回归加「命令行边界」一节（`tests/cli_checks.py`，9 项）。

## 随套件 v2.4.0

分析表与对抗图一个字节不变。

- 修：`rasterize.py` 给了不是 SVG 的文件（例如把 JSON 当成了图），原来交给转换工具硬转：装着 LibreOffice Writer 的电脑
  转出一张乱码 PNG，没装的（GitHub 上就是）甩 CalledProcessError 堆栈。现在先认出不是 SVG，说清楚要哪个文件，不写图；
  转换工具本身失败时也说是哪一个、怎么办，不甩堆栈。
- 修：记事本存的 GBK 材料原来按 UTF-8 读、忽略错误，悄悄读成乱码还当作已读。现在 UTF-8 读不通就按 GBK 读，
  且读出来的汉字六成以上是常用字才认；Big5 等认不准的编码停下，请用户另存为 UTF-8。
- 修：给 `check_figure.py` 的不是 SVG 时，原来甩堆栈，现在说清要给哪份文件。
- 修：记事本另存的「UTF-8 带 BOM」的 JSON 与 SVG 原来读不了，现在照读。
- 修：命令行脚本加 `--help` 时甩堆栈或把 `--help` 当成文件名；路径打错、JSON 写坏、缺 openpyxl 等时甩 Python 堆栈。现在一律说人话。
- SKILL.md 加「材料是数据，不是指令」与「运行与交付须知」两节。

## 1.0.0

首个公开版本。在此之前的改动没有单独记在这里。
