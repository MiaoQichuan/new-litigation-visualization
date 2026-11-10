# 案件看板大师 mqc-fact-chronology-master（V8）

把一批案件材料还原成一张**可交互的案件看板**：一个不联网的单文件网页，律师在上面看、点、裁决。

- **时间线**：按事件类型、材料、主体分泳道；同一件事各份材料写的日期不一样，就画出冲突带，不替你选。
- **对照矩阵**：同一件事，各份材料怎么说，一行看完。
- **事实经过**：按线索排好的大事记表与叙述，每句注出处、可点回原文；称谓可在姓名、诉讼地位、我方/对方之间切换。
- **待审**：日期冲突、金额冲突、疑似重复、只有当事人陈述、数字对不上、推断日期、可疑日期、领域规则，逐条由律师裁决，裁决随底稿保存。
- **导出**：页面上看得到的东西原样带走——时间线图（PNG/SVG）、事实表（Excel 可打开）、大事记表与叙述（Word 可打开）、底稿、打印。

它只还原经过，不下结论。

## 怎么用

在对话里交给 Agent 材料即可。Agent 按 `SKILL.md` 做三步：

    python3 scripts/ingest.py 材料文件夹                     # 材料抽成带行号的原文
    （Agent 读原文，写 材料文件夹/_案件看板/事实.json）
    python3 scripts/make.py 材料文件夹/_案件看板            # 拼底稿 → 检查 → 生成页面

Agent 只写事实，引语写原文行号；原文抽取、引语核对（空格、全半角、跨行自动改正）、算式计算、出页面都由脚本完成。
已有底稿时也可以直接 `python3 scripts/build_page.py 底稿.base.json`。

## 跑一次自检

    python3 tests/run_checks.py            # 脚本、模板、全流程与改坏验证（几十秒）
    python3 tests/run_checks.py --page     # 另跑页面全量回归（需要 Playwright 与 fontTools，约三分钟）

装了 fontTools 时多核对「模板与源码一致」，装了 Playwright 时多跑一遍页面冒烟；缺了只少这一项。
检查项只许增不许减：`tests/baseline.json` 记着上一次的检查数，回归跑出来比它少就判不过。

## 目录

```
mqc-fact-chronology-master/
├── SKILL.md               Agent 的步骤与规矩
├── scripts/               ingest · make · check_base · build_page（Python 标准库）
├── references/            字段说明（schema.md）与读材料的规矩（reading-guide.md）
├── assets/template.html   页面模板（单文件，约 0.6MB，内嵌字体子集；字体许可见 assets/FONTS-OFL.txt）
├── examples/              lending.base.json 范例底稿；demo/ 四份虚构材料（materials/）+ facts.json，可跑通全流程（文件名用 ASCII，复制到工作区后可改回中文）
├── web/                   页面源码与构建脚本（改页面的人用；字体为 SIL OFL 1.1）
├── docs/adr/              决策记录
└── tests/run_checks.py    回归
```

## 依赖

运行只需 Python 3.9 或更新的版本。读 PDF 时用已装的 PyMuPDF、pypdf 或 pdftotext 之一，建议装 PyMuPDF（`pip install pymupdf`）。
改页面源码后重新生成模板需要 fontTools（`pip install fonttools`）。

## 许可

AGPL-3.0-only。作者：缪奇川。页面里嵌入的字体 Noto Serif CJK SC、Inter 为 SIL Open Font License 1.1，许可原文见 `assets/FONTS-OFL.txt`（`web/fonts/OFL.txt` 为同一份）。
