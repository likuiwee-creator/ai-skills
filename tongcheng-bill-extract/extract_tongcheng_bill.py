"""
同程对账单提取脚本

功能：
  把同程导出的对账单(单个 xlsx)中的「对账单详情」sheet 提取为一张干净的表：
    1. 去除顶部 1 行废行(仅含标题 "对账单详情" 的那行)
    2. 表头改名: 订单短号 -> OTA订单号, 实际结算金额 -> 打款金额
    3. 其余列原样保留

用法：
  python extract_tongcheng_bill.py "<账单路径.xlsx>"
  python extract_tongcheng_bill.py "<账单路径.xlsx>" -o "<输出路径.xlsx>"

依赖：openpyxl  (若缺失: python -m pip install openpyxl)
"""

import copy
import os
import re
import sys

import openpyxl


SRC = None
OUT = None

TARGET_KW = "对账单详情"
RENAME = {"订单短号": "OTA订单号", "实际结算金额": "打款金额"}


def main():
    wb = openpyxl.load_workbook(SRC, data_only=True)

    # 找目标 sheet（按关键字匹配，兼容「对账单详情」/「账单详情」等叫法）
    target = None
    for n in wb.sheetnames:
        if TARGET_KW in n:
            target = n
            break
    if target is None:
        # 回退：只有一个 sheet 就直接用
        target = wb.sheetnames[0]
        print("未找到含 '%s' 的 sheet，已回退使用第一个 sheet: %s" % (TARGET_KW, target))

    ws = wb[target]
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        raise SystemExit("目标 sheet 为空")

    # 去除顶部 1 行废行（仅含标题的那行）。判定：该行只有一个非空单元格且内容为标题字眼，
    # 或首格等于 sheet 名。这里统一「去掉第 1 行（索引0）」，与用户描述一致。
    # 安全校验：若第 0 行已经是真表头(含 订单短号/实际结算金额)，则跳过去除，避免误删。
    header_candidate = rows[0]
    looks_like_junk = (
        sum(1 for c in header_candidate if c is not None and str(c).strip() != "") <= 1
    )
    if looks_like_junk:
        rows = rows[1:]
        print("已去除顶部 1 行废行")
    else:
        print("提示: 顶部行疑似已是真表头，未做去除（如确需去行请告知）")

    if not rows:
        raise SystemExit("去除废行后无数据")

    # 改名表头
    header = []
    for h in rows[0]:
        if h is None:
            header.append(h)
            continue
        hs = str(h).strip()
        header.append(RENAME.get(hs, h))
    out_rows = [header] + [list(r) for r in rows[1:]]

    out = openpyxl.Workbook()
    o = out.active
    o.title = "对账单详情"
    for r in out_rows:
        o.append(r)
    out.save(OUT)

    # 重复订单号检查（透明提示，不自动聚合——同程一个主单可能拆多行明细）
    if "OTA订单号" in header:
        io = header.index("OTA订单号")
        ids = [r[io] for r in out_rows[1:] if r[io] is not None]
        from collections import Counter
        c = Counter(ids)
        dups = {k: v for k, v in c.items() if v > 1}
        print("OTA订单号(原订单短号) 唯一数: %d, 重复数: %d" % (len(set(ids)), len(dups)))
        if dups:
            print("  说明: 同程一个主单可能拆多行(不同套餐/SKU)，OTA订单号 重复属正常，已逐行保留不做合并。")

    print("已保存:", OUT)
    print("来源sheet:", target)
    print("输出行数(含表头):", len(out_rows), " 输出列数:", len(header))
    print("新表头前几列:", header[:3], "...")
    print("改名检查 -> 含 OTA订单号/打款金额:",
          "OTA订单号" in header, "打款金额" in header)
    print("旧名是否已移除 -> 含 订单短号/实际结算金额:",
          "订单短号" in header, "实际结算金额" in header)


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        raise SystemExit("用法: python extract_tongcheng_bill.py <账单.xlsx> [-o 输出.xlsx]")
    SRC = args[0]
    # 输出路径
    if "-o" in args:
        i = args.index("-o")
        OUT = args[i + 1]
    else:
        base, ext = os.path.splitext(SRC)
        OUT = base + "_订单详情.xlsx"
    if not os.path.exists(SRC):
        raise SystemExit("源文件不存在: %s" % SRC)
    main()
