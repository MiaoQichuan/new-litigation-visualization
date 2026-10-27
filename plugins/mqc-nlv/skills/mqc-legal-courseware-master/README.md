# 法律课件大师（V7）· 法律图表页助手

只做课件里**法律图表那一页**：把 V1–V6 的图放进 12 栏 × 6 行的磁吸网格，配上一句话结论、读图要点、法条、裁判要旨等卡片，
导出可编辑的 PPTX——整页复制或框选复制，粘进您自己的课件。

```bash
python3 scripts/studio.py examples/demo            # 打开磁吸编辑器（浏览器里用）
python3 scripts/studio.py examples/demo --detach   # 由 AI 助手（Agent）代开：独立运行，不随 Agent 的命令结束；--stop 关掉
python3 scripts/build.py examples/demo --check     # 检查示例
python3 scripts/build.py examples/demo -o out/示例.pptx  # 导出（out/ 不入库）
python3 tests/run_checks.py                        # 回归
```

- **图表库**：侧栏第一位，V6 的一百多个法律图表场景（真画出来的缩略图），按场景、画法、关键词找，点一下放进这一页，交给 AI 换成您的数据。
- **磁吸做到图里**：认得出图里的事件、主体、关系、柱子——放读图编号（要点同号联动、导出自带讲课动画）、切片只取几件事放大、
  聚焦只点亮几处、按编号拆成几页；V6 图表一键换一种图。
- **版面**：铺满全屏，或按您的模板 / 截图预留 Logo 与天头地脚。**风格**：奇川风、歸藏风、自定义（模板、截图或一个主色）。
- 只需 Python 3（标准库）；与 V1、V6 放在同一仓库的 `skills/` 下（V7 只读调用它们，不改它们）。
- 写法与规矩见 `SKILL.md`；格式见 `references/deck-format.md`；设计取舍见 `docs/adr/`；版本见 `CHANGELOG.md`。
- 示例 `examples/demo/` 的数据、律所与 Logo 均为虚构。
