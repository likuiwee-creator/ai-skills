---
name: ctrip-bill-extract
description: "携程(景点玩乐代理)账单明细提取。把携程导出的账单 xlsx 中的订单明细 sheet 单独导出为一张对账表：去除顶部 2 行废行（标题行 + To: 抬头行），表头 携程订单号->OTA订单号、结算价金额->打款金额。兼容两种格式：①单文件（订单明细 sheet）；②多 sheet 汇总账单（含 汇总/流水/订单明细/票种账单，自动取 订单明细）。当用户说「提取携程账单」「携程账单明细」「导出携程订单明细」时使用。"
agent_created: true
---

# 携程账单明细提取

把携程(景点玩乐代理)导出的月度账单 Excel 中的「订单明细」sheet 单独导出为一张干净的对账表。

## 何时使用
- 用户每月初把上月携程账单里的订单明细单独导出为一张表，用于 OTA 订单核对（按 OTA订单号 + 打款金额 匹配）。
- 关键词：「提取携程账单」「携程账单明细」「导出携程订单明细」+ 一个 .xlsx 文件路径。

## 提取规则（严格按此执行）
1. 自动按关键字定位目标 sheet：优先匹配名称含「订单明细」「账单明细」「明细」的 sheet（兼容单文件版与多 sheet 汇总账单版，两者底层都是 订单明细 sheet）。
2. 去除顶部 `SKIP_ROWS=2` 行废行（通常为：标题行 `订单明细` + 抬头行 `To: 公司名`），去完后首行即为真正表头。
3. 表头重命名：
   - `携程订单号` → `OTA订单号`
   - `结算价金额` → `打款金额`
4. 裁掉表头为空的尾部多余列，其余原始列（结算周期 / 结算类型 / 携程付款单号 / 产品信息 / 资源名称 / 客人姓名 / 出发时间 / 返程时间 / 结算价币种 等）全部原样保留，不改动数据。

## 运行方式
脚本 `extract_ctrip_bill.py` 与本文件同目录，依赖 openpyxl（纯 Python，无其他依赖）。

```bash
python "<skill_dir>/extract_ctrip_bill.py" "账单路径.xlsx"
# 可选第二个参数指定输出路径，默认输出为 <原名>_账单明细.xlsx
python "<skill_dir>/extract_ctrip_bill.py" "账单路径.xlsx" "输出路径.xlsx"
```

说明：脚本按 sheet 名关键字自动识别目标 sheet，列名按精确匹配定位（携程订单号 / 结算价金额）并重命名。同一脚本同时兼容单文件版与多 sheet 汇总账单版两种携程格式。

## 输出与核对
- 产物为单 sheet「账单明细」，行数 = 源订单明细数据行（源 max_row − 2 废行）。
- 跑完打印：来源 sheet 名、跳过顶部行数、输出行数、输出列数、新表头前几列，据此向用户汇报。

## 环境
- 脚本依赖 `openpyxl`（纯 Python，无其他依赖）。任何装有 Python 3 的机器，先执行 `python -m pip install openpyxl` 即可运行。
- WorkBuddy 托管 Python 用法：基础运行时 `versions\3.13.12\python.exe` 默认不含 openpyxl，请用已安装依赖的 venv 入口运行：
  `C:\Users\Administrator\.workbuddy\binaries\python\envs\default\Scripts\python.exe "<skill_dir>\extract_ctrip_bill.py" "账单路径.xlsx"`
  或在 venv 内 `python -m pip install openpyxl` 后使用。

## 备注
- 汇总账单版还含 汇总 / 流水 / 票种账单 三个 sheet，本技能默认只导出 订单明细（订单级，对接核对够用）。如需一并导出 流水（资源级更细）/ 汇总（按结算周期汇总金额），在脚本内追加对应 sheet 导出即可。
