# -*- coding: utf-8 -*-
"""
美团多周账单合并脚本
====================
把多个「美团订单详情」xlsx（可由 meituan-bill-extract 技能生成，或原始美团账单）按列对齐合并成一张总表。

特点：
1. 自动识别每个文件里的「订单详情」sheet（兼容改名后的导出表与原始美团账单）。
2. 表头归一化（幂等）：美团订单号->OTA订单号、结算金额->打款金额。
3. 按列名对齐取并集，缺失列填空，避免列顺序不一致导致错位。
4. 追加「来源」列，标记每行来自哪个原始周文件，便于对账钻取。
5. 输出单 sheet「订单详情」，表头一次 + 所有数据行拼接。

用法：
    python merge_meituan_bills.py 文件1.xlsx 文件2.xlsx ... [-o 输出.xlsx]
不指定 -o 时，输出为 第一个文件同名_多周合集_订单详情.xlsx（同目录）。
"""
import argparse
import glob
import os
import sys

import openpyxl

# 表头归一化（幂等：若已是新名也成立）
HEADER_MAP = {
    "美团订单号": "OTA订单号",
    "结算金额": "打款金额",
}
SRC_SHEET_HINTS = ["订单详情", "账单明细", "明细"]


def find_sheet(wb):
    names = wb.sheetnames
    for hint in SRC_SHEET_HINTS:
        for n in names:
            if hint in n:
                return n
    # 退回：只有一个 sheet 就用它
    if len(names) == 1:
        return names[0]
    raise SystemExit("未在文件中找到订单明细类 sheet: %s (现有: %s)" % (os.path.basename(wb.path or ""), names))


def normalize_header(h):
    return HEADER_MAP.get(h, h)


def read_xlsx_rows(path):
    """返回 (normalized_header_list, [data_row_dicts])。兼容 .xls 实为 xlsx 的情况。"""
    path = path.strip().strip('"').strip("'")
    real_path = path
    # 美团 .xls 有时是改了扩展名的 xlsx：尝试复制成 .xlsx 再读
    if path.lower().endswith(".xls") and not path.lower().endswith(".xlsx"):
        try:
            import shutil
            tmp = path + "x"
            if not os.path.exists(tmp):
                shutil.copy(path, tmp)
            real_path = tmp
        except Exception:
            pass
    wb = openpyxl.load_workbook(real_path, read_only=True, data_only=True)
    sheet = find_sheet(wb)
    ws = wb[sheet]
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    # 找表头行（第一个非空行）
    header_row = None
    for r in rows:
        if any(v is not None for v in r):
            header_row = list(r)
            break
    if header_row is None:
        raise SystemExit("文件无表头: %s" % os.path.basename(path))
    norm_header = [normalize_header(str(c).strip()) if c is not None else "" for c in header_row]
    data = []
    started = False
    for r in rows:
        if not started:
            # 跳过表头行（首行即表头）
            started = True
            continue
        if all(v is None for v in r):
            continue
        d = {norm_header[i]: r[i] for i in range(min(len(norm_header), len(r)))}
        data.append(d)
    return norm_header, data, os.path.basename(path)


def main():
    ap = argparse.ArgumentParser(description="合并多个美团订单详情 xlsx")
    ap.add_argument("inputs", nargs="+", help="一个或多个订单详情 xlsx 路径（支持通配符）")
    ap.add_argument("-o", "--output", help="输出路径，默认 第一个文件同名_多周合集_订单详情.xlsx")
    args = ap.parse_args()

    files = []
    for pat in args.inputs:
        if any(ch in pat for ch in "*?["):
            files.extend(sorted(glob.glob(pat)))
        else:
            files.append(pat)
    files = [f for f in files if f]
    if not files:
        raise SystemExit("未提供任何输入文件")

    all_headers = []          # 列并集（保序）
    seen = set()
    all_data = []             # (row_dict, source_label)
    per_file_summary = []

    for f in files:
        try:
            header, data, src_label = read_xlsx_rows(f)
        except Exception as e:
            print("⚠️ 跳过 %s : %s" % (os.path.basename(f), e))
            continue
        for h in header:
            if h and h not in seen:
                seen.add(h)
                all_headers.append(h)
        # 来源标签：去掉 _订单详情 / 扩展名，保留可辨识部分
        label = src_label
        for suf in ("_订单详情.xlsx", "_订单详情.xls", ".xlsx", ".xls"):
            if label.endswith(suf):
                label = label[: -len(suf)]
                break
        all_data.extend((d, label) for d in data)
        per_file_summary.append((src_label, len(data)))
        print("  ✓ %s : %d 行" % (src_label, len(data)))

    if not all_data:
        raise SystemExit("没有任何有效数据行，退出")

    # 追加「来源」列到最右
    all_headers.append("来源")

    # 写输出
    out = args.output
    if not out:
        base = os.path.splitext(files[0])[0]
        if base.endswith("_订单详情"):
            base = base[: -len("_订单详情")]
        out = base + "_多周合集_订单详情.xlsx"

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "订单详情"
    ws.append(all_headers)
    for d, label in all_data:
        ws.append([d.get(h, None) for h in all_headers[:-1]] + [label])

    wb.save(out)
    print("\n已保存: %s" % out)
    print("总数据行数: %d  列数: %d (含来源列)" % (len(all_data), len(all_headers)))
    print("各文件行数:")
    for s, n in per_file_summary:
        print("   %s : %d" % (s, n))
    # 打款金额合计（如有）
    if "打款金额" in all_headers:
        tot = 0.0
        cnt = 0
        for d, _ in all_data:
            v = d.get("打款金额")
            try:
                if v not in (None, ""):
                    tot += float(v)
                    cnt += 1
            except Exception:
                pass
        print("打款金额合计(非空 %d 行): %.2f" % (cnt, tot))


if __name__ == "__main__":
    main()
