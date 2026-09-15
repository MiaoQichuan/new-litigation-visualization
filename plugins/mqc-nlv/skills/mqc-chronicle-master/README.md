# 大事记表大师 mqc-chronicle-master

庭前三大法宝之一。把一批案件材料整理成《案件大事记》，产出四样东西：

- Word 交付版（竖版 A4 五列，给法院的制式）
- Excel 母表（可筛选、可分组，律师的工作台）
- 大事记简表（A4 竖版 PDF／SVG／PNG，呈报给法官或当事人的一张表）
- 案件事实底稿 casefile.json（下游的法律关系图大师与攻防图大师读同一份）

照录原文、每行挂出处、不作法律判断。规格见 `references/extraction.md`。

## 跑一次自检

    python tests/run_checks.py

## 管线

    python scripts/ingest.py <材料...> <工作目录>
    python scripts/pipeline.py <casefile.json> [sources.json] [输出目录]

依赖：摄入用 poppler 自带命令（pdfinfo / pdftotext / pdftoppm / pdfimages）；
Word 走 docx（Node）；Excel 走 openpyxl。
简表的 SVG 生成零第三方依赖，**导出 PDF／PNG 需要 cairosvg**；
多页合并成一个 PDF 需要 pypdf，没装就按页分开出，不阻断。
