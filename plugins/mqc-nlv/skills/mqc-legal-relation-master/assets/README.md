# assets/ 是代码读的查表，模型不要读

这里是 lookup.py 按度序列查预置布局用的索引表。`index_all.json` 104 KB、
`deg_seqs.json` 115 KB，模型读一遍合计约 6.4 万 token，对判断毫无帮助。

运行时你要读的是 SKILL.md 与 `references/relations-guide.md`。
