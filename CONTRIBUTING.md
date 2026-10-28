# 参与贡献 · Contributing

谢谢愿意帮这个项目变好。下面几条不是客套，是这个仓库能一直「画得准」的原因，提交前请读完。

*English speakers are welcome too — open an issue or PR in English; the rules below apply all the same.*

## 先说最重要的一条：不要上传真实案件材料

Issue、PR、示例、测试样本里，**一律不放真实当事人、案号、账号、身份证号、手机号、真实判决原文**。
复现问题请用虚构或脱敏后的材料。仓库有脱敏守卫
（`mqc-timeline-master/tests/check_anonymised.py`），提交前会被查。

律所的模板、Logo、品牌规范同理：**是律所的财产，不进仓库**。测试用的「模板」都是用虚构律所自己做出来的。

## 这个仓库的几条规矩

1. **模型只读意思，几何交给脚本。** 坐标、尺寸、字数预算都由确定性脚本算出来。不要把「让模型估一个位置」写进流程。
2. **出图那条路零第三方依赖。** 渲染与导出只用 Python 标准库。Pillow、openpyxl、python-docx 等只允许用在测试或明确的可选能力上，而且缺席时要退化、不能崩。
3. **每条守卫都必须能失败。** 新加一条检查后，故意把代码改坏，确认它真的报错，再改回来。会误报的检查宁可不加。
4. **共享内核只有一份。** 几何、字体、换行、导出的公共代码在 V1（`mqc-litigation-visual-redraw`）。别的模块引用它，不许各自分叉；单独分发时随包带的副本由守卫逐字节比对。
5. **路径必须全是 ASCII。** Windows 解压 ZIP 时中文文件名会失败。内容可以是中文，文件名不行。
6. **只增不减。** 已有的回归项不删；修好的问题要固化成守卫。
7. **读写文本一律写明 UTF-8。** `open`、`read_text`、`write_text`、带 `text=True` 的子进程都写 `encoding="utf-8"`，
   命令行脚本的入口把输出固定成 UTF-8。不写时 Python 按系统区域设置走，中文 Windows 上是 GBK——自己画的 SVG 都会读坏。
   回归里有一项全插件检查专管这条；CI 另在 GBK 区域设置下把全部回归再跑一遍。

## 提交前跑一遍回归

```bash
python3 plugins/mqc-nlv/skills/mqc-litigation-visual-redraw/tests/run_checks.py
python3 plugins/mqc-nlv/skills/mqc-timeline-master/tests/run_checks.py
python3 plugins/mqc-nlv/skills/mqc-legal-relation-master/tests/make_checks.py
python3 plugins/mqc-nlv/skills/mqc-chronicle-master/tests/run_checks.py
python3 plugins/mqc-nlv/skills/mqc-trial-confrontation-master/tests/shape_checks.py
python3 plugins/mqc-nlv/skills/mqc-legal-chart-master/tests/release_gate.py
python3 plugins/mqc-nlv/skills/mqc-legal-courseware-master/tests/run_checks.py
```

退出码 0 才算过。GitHub Actions 会在每次 push 与 PR 时跑同一套（见 `.github/workflows/checks.yml`）。
如果改动有意改变了输出，请更新对应的金样（各模块的 `tests/` 里有说明），并在 PR 里写明为什么变。

## 版本与兼容

用户手上的那份说明（JSON）就是我们对他们的承诺。升级时按下面几条判断「这是不是一次不兼容的改动」：

- **改严算不兼容，改松不算。** 一份原来能出图的说明，升级后被拒了，就是不兼容——哪怕新规则更对。
  确要这样改，在该模块的 `CHANGELOG.md` 里单列「不兼容」一节，写清哪类说明会被拒、用户该怎么改。
  新增一条「请核」提示不算不兼容：提示不拦出图。
- **承诺的是**：字段名与含义、哪些字段必填、命令行的子命令与参数、产物的文件名与格式。
- **不承诺的是**：版面细节（位置、尺寸、走线）、提示与报错的措辞、代码内部结构。
  版面有意变了，按上一节更新金样或成品账并写明理由。
- **怎么守住**：法律图表大师（V6）由机器把关——判定账（`tests/golden/verdicts.jsonl`）记着哪些说明该过、哪些该拒，
  发版闸门不许任何一条悄悄翻转，也不许任何一项检查消失。其余模块目前靠这条规矩与各自的回归把关，补上判定账是后续工作。

## 提 PR 的流程

1. Fork，从 `main` 开一个分支。
2. 一个 PR 只做一件事；改动大的先开 Issue 讨论方向。
3. 在对应模块的 `CHANGELOG.md` 记一笔；涉及取舍的，在 `docs/adr/` 写一条决策记录，**包括否掉的替代方案**。
4. 按 PR 模板勾完清单。

## 许可

提交到本仓库的贡献，视为同意以本仓库的 [AGPL-3.0 许可](LICENSE) 发布。
