# -*- coding: utf-8 -*-
"""
美团账单明细提取脚本（按月复用）

用法:
  python extract_meituan_bill.py [输入xls/xlsx] [输出xlsx可选]

逻辑:
  1. 取「订单详情」sheet 作为主表（美团导出的 .xls 多为改了扩展名的真 xlsx，
     也有少量是老 OLE2 格式 .xls，脚本两种都支持）
  2. 订单详情 sheet 表头即首行，无废行，无需跳行
  3. 表头重命名：美团订单号 -> OTA订单号、结算金额 -> 打款金额
  4. 其余原始列全部原样保留，输出为单 sheet 表格

依赖:
  - openpyxl（读取/写出 xlsx，及读取被改扩展名的真 xlsx）
  - xlrd（兜底读取真正的老格式 .xls / OLE2）—— 缺失时仅在该格式下才报错提示
"""
import io
import os
import sys

import openpyxl

SRC = sys.argv[1] if len(sys.argv) > 1 else r"C:/Users/Administrator/Downloads/report-2094136696408457239-1001788364204220.xls"
OUT = sys.argv[2] if len(sys.argv) > 2 else SRC[: SRC.rfind(".")] + "_订单详情.xlsx"

TARGET_KW = "订单详情"
RENAME = {"美团订单号": "OTA订单号", "结算金额": "打款金额"}

# 美团把同一订单拆成「正向销售行 + 退款行」两行（退款可能部分退），
# 故需按订单号聚合：数值列求和（得净结算），文本列取基准行（优先应付>0行）。
KEY_COL = "美团订单号"
NUMERIC_COLS = {
    "应付金额", "退款金额", "商家承担优惠", "调账金额",
    "退款手续费", "公益金额", "结算金额",
    "技术服务费", "技术服务费退款", "张数",
}


def _num(v):
    if v is None or v == "":
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def aggregate_by_order(rows):
    """同美团订单号的多行合并为一行。返回 (合并后行列表, 合并掉的订单号数)。"""
    if not rows:
        return rows, 0
    header = rows[0]
    try:
        key_idx = header.index(KEY_COL)
    except ValueError:
        return rows, 0  # 无订单号列则不聚合，原样返回
    numeric_idxs = [i for i, h in enumerate(header) if h in NUMERIC_COLS]
    pay_idx = header.index("应付金额") if "应付金额" in header else None

    groups = OrderedDict()
    no_key = []
    for r in rows[1:]:
        key = r[key_idx]
        if key is None or key == "":
            no_key.append(list(r))
            continue
        groups.setdefault(key, []).append(list(r))

    merged = []
    merged_count = 0
    for key, recs in groups.items():
        if len(recs) > 1:
            merged_count += 1
        # 基准行：优先选「应付金额≠0」的正向行，否则取首行
        base = None
        if pay_idx is not None:
            for r in recs:
                if _num(r[pay_idx]) != 0:
                    base = r
                    break
        if base is None:
            base = recs[0]
        m = list(base)
        for ci in numeric_idxs:
            total = 0.0
            ok = True
            for r in recs:
                v = r[ci]
                if v is None or v == "":
                    continue
                try:
                    total += float(v)
                except (TypeError, ValueError):
                    ok = False
                    break
            if ok:
                m[ci] = round(total, 2)
        merged.append(m)
    merged.extend(no_key)
    return [header] + merged, merged_count


def pick_sheet(names, kw):
    for n in names:
        if kw in n:
            return n
    return None


def read_rows(path):
    """返回 (sheet名, [每行list])。兼容真 xlsx / 改扩展名的 xlsx / 老 OLE2 .xls。"""
    with open(path, "rb") as f:
        head = f.read(2)
    # PK = ZIP 签名：真 xlsx 或被改扩展名的 xlsx
    if head == b"PK":
        with open(path, "rb") as f:
            wb = openpyxl.load_workbook(io.BytesIO(f.read()), data_only=True)
        name = pick_sheet(wb.sheetnames, TARGET_KW)
        if name is None:
            raise SystemExit("未找到含「%s」的sheet，现有sheet: %s" % (TARGET_KW, wb.sheetnames))
        ws = wb[name]
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
        return name, rows
    # 否则按老 OLE2 .xls 处理（需 xlrd）
    try:
        import xlrd
    except ImportError:
        raise SystemExit("该文件是老格式 .xls，需要 xlrd：请执行 `python -m pip install xlrd`")
    bk = xlrd.open_workbook(path)
    name = pick_sheet(bk.sheet_names(), TARGET_KW)
    if name is None:
        raise SystemExit("未找到含「%s」的sheet，现有sheet: %s" % (TARGET_KW, bk.sheet_names()))
    sh = bk.sheet_by_name(name)
    rows = [sh.row_values(i) for i in range(sh.nrows)]
    return name, rows


def main():
    sheet_name, rows = read_rows(SRC)
    if not rows:
        raise SystemExit("目标 sheet 为空")

    # 同订单号多行合并（金额列求和、文本列取正向行）
    rows, merged_count = aggregate_by_order(rows)

    header = [RENAME.get(str(h).strip(), h) if h is not None else h for h in rows[0]]
    out_rows = [header] + [list(r) for r in rows[1:]]

    out = openpyxl.Workbook()
    o = out.active
    o.title = "订单详情"
    for r in out_rows:
        o.append(r)
    out.save(OUT)

    print("已保存:", OUT)
    print("来源sheet:", sheet_name)
    print("输出行数(含表头):", len(out_rows), " 输出列数:", len(header))
    print("新表头前几列:", header[:3], "...", header[-2:])
    if merged_count:
        print("⚠️ 已合并重复订单号:", merged_count, "个（同一订单的正向行+退款行已聚合成一行，金额列求和为净结算）")


if __name__ == "__main__":
    main()
