# ADR 0004 — Word 后处理必须落成带自证的脚本

**状态：** 已采纳

## 背景

docx 库写不出三件事，必须在 OOXML 层补：字体三槽（eastAsia 宋体 / ascii 新罗马）、
`autoSpaceDE` 与 `autoSpaceDN` 置 0（中英文之间不自动加空）、所有 run 级 `rFonts`
补 `hint="eastAsia"`（引号、省略号、书名号等通用标点区的歧义字符归中文字体）。

## 决策

落成 `scripts/postprocess_docx.py`，并**自带 verify**：三件事只要有一件没落到文件
就报错退出。管线在渲染步强制调用它。

## 背景里的教训

这三件事曾经只活在一次性 shell 命令里，不在仓库。自检 25 条全过、渲染图看着也对，
但换个人照 SKILL.md 跑，拿到的是中英文之间有空格、引号是西文、字号不对的版本。
**调了七八轮的东西，一行都没进仓库。**

## 注意

`CT_PPrBase` 的子元素次序是 schema 强制的，`autoSpace` 必须排在 `spacing` 之前；
`CT_DocDefaults` 里 `rPrDefault` 必须排在 `pPrDefault` 之前。次序错了 validate 会报
「element is not expected」。
