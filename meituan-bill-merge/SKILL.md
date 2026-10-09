---
name: meituan-bill-merge
description: "美团多周账单合并。把多个「美团订单详情」xlsx（可由 meituan-bill-extract 技能生成，或原始美团账单）按列对齐合并成一张总表：表头归一化（美团订单号->OTA订单号、结算金额->打款金额，幂等），追加「来源」列标记每行原始周文件，输出单 sheet「订单详情」。当用户说「合并美团多周账单」「合并订单详情」「把几周美团账单拼一起」时使用。"
agent_created: true
---

# 美团多周账单合并

把若干份美团账单的「订单详情」sheet 合并成一张干净的总表，用于 OTA 订单核对（按 OTA订单号 + 打款金额 匹配）。

## 何时使用
- 用户每月收到多份单周美团账单（或已用 meituan-bill-extract 导出多份 `_订单详情.xlsx`），需要拼成一张总表。
- 关键词：「合并美团多周账单」「合并订单详情」「把几周美团拼一起」+ 多个 xlsx 路径。

## 合并规则（严格按此执行）
1. 逐个读取每个输入文件的「订单详情」sheet（兼容已改名导出的 `_订单详情.xlsx` 与原始美团账单；自动按关键字 `订单详情/账单明细/明细` 找 sheet）。
2. **表头归一化（幂等）**：`美团订单号 → OTA订单号`、`结算金额 → 打款金额`。若已是新名则保持不变，可重复执行。
3. **按列名对齐取并集**：各文件列顺序/列集不同时，按列名对齐，缺失列填空，避免错位。
4. **追加「来源」列**（置于最右）：值为原始文件名（去掉 `_订单详情`/扩展名），标记每行来自哪个周文件，便于对账钻取。
5. 输出单 sheet「订单详情」：表头 1 行 + 所有数据行拼接。

## 运行方式
脚本 `merge_meituan_bills.py` 与本文件同目录，依赖 openpyxl（纯 Python）。

```bash
# 合并多个文件，输出到指定路径
python "<skill_dir>/merge_meituan_bills.py" 文件1.xlsx 文件2.xlsx 文件3.xlsx -o 输出.xlsx
# 支持通配符
python "<skill_dir>/merge_meituan_bills.py" "Downloads/*_订单详情.xlsx" -o 合并.xlsx
# 不指定 -o 时，默认输出为 第一个文件同名_多周合集_订单详情.xlsx（同目录）
python "<skill_dir>/merge_meituan_bills.py" 文件1.xlsx 文件2.xlsx
```

## 输入约定
- 推荐先用 `meituan-bill-extract` 技能把每份周账单导出为 `_订单详情.xlsx`（已是 OTA订单号/打款金额 命名），再喂给本合并脚本。
- 也可直接喂原始美团 `.xls/.xlsx`：脚本会读「订单详情」sheet 并自动归一化表头；`.xls` 实为改扩展名 xlsx 的情况已兼容（读字节判断，必要时复制为 .xlsx 再读）。

## 输出与核对
- 产物单 sheet「订单详情」，列数 = 各文件列并集 + 1（来源列）。
- 跑完打印：每个文件行数、总数据行数、列数、各文件分布、打款金额合计（若含「打款金额」列）。
- **勾稽校验建议**：把合并的「打款金额合计」与原始各周账单总表（或 meituan-bill-extract 单周产出）的打款额加总比对，应完全相等。

## 环境
- 依赖 `openpyxl`（必装）。任何装有 Python 3 的机器先 `python -m pip install openpyxl` 即可运行。
- WorkBuddy 托管 Python 用法：基础运行时 `versions\3.13.12` 默认不含 openpyxl，请用已安装依赖的 venv 入口：
  `C:\Users\Administrator\.workbuddy\binaries\python\envs\default\Scripts\python.exe "<skill_dir>\merge_meituan_bills.py" 文件1.xlsx 文件2.xlsx -o 输出.xlsx`

## 与 meituan-bill-extract 的配合
完整月度流程：
1. 每份周账单 → `meituan-bill-extract` 导出 `_订单详情.xlsx`（改名）。
2. 所有 `_订单详情.xlsx` → `meituan-bill-merge` 合并成一张总表（含来源列）。
3. 总表直接对接 OTA 订单核对（按 OTA订单号 + 打款金额）。
