# 示例：从最小到完整

四份 `relations.json`，同一个虚构的建设工程施工合同纠纷，**每一份只比前一份多一个要点**。
照着写的时候，先找最接近手上材料的那一份。字段的完整说明见 `../references/relations-guide.md`。

| 文件 | 多了什么 | 跑起来是什么样 |
| --- | --- | --- |
| `relations-1-minimal.json` | 最小：两个主体、一份合同、两条「签订」 | 3 个模块、2 条关系，查完整图 |
| `relations-2-objects.json` | 主体与客体并存：合同指向工程用**虚线**（客体之间），实际施工人指向工程用实线 | 5 个模块、4 条关系 |
| `relations-demo.json` | 完整一案：九个模块、十一条关系；`sources` 写材料，个别关系写 `source`；读不准的放进 `unsure`，出处索引原样列出 | 9 个模块、11 条关系，到上限 |
| `relations-4-over-limit.json` | 超过九个模块（十五个）：`make.py` 不出图，先走第〇轮 `ask.py trim` 由使用者定留哪几个 | 退出码 4，打印第〇轮命令 |

几点：

- 深红标在哪里**不写在 JSON 里**：它由使用者在提问的第二问里选（`ask.py resolve … --mark 编号`），写进 `choice.json`。
- 名称与关系名照录材料，一个字不改；`note` 是一行身份说明，可以是概括。
- 这四份都是虚构的，只为演示写法。同目录的 `case_object.py` 与 `demo.svg`、`demo-*.png` 是另一套演示（主体与客体并存的画法、三种风格的效果），写 JSON 时不必读。
