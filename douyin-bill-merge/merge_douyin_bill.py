# -*- coding: utf-8 -*-
"""
抖音分账明细合并脚本（按月复用 / 可作为 WorkBuddy skill 调用）
用法:
  python merge_douyin_bill.py [输入xlsx] [输出xlsx可选]
默认输入: 脚本同目录未指定时请在下方 SRC 直接改路径

合并规则（口径统一于 2026-09-08，用户确认）:
  1. 以「分账明细-正向-团购」为主表（保留全部列）
  2. 用「订单编号」匹配「分账明细-退款-团购」:
       主表.用户实付金额 += 退款.用户实付金额     ← 两边同口径
       主表.提现金额     += 退款.提现金额
     !! 禁止把「订单实收金额」与「用户实付金额」相加:两者相差平台补贴/抖音
        支付优惠，混加会让全额退款时本应为 0 的「客户实付」变成 1.40/12.10。
  3. 把「分账明细-补偿-团购」的 订单编号 / 用户实付金额 / 提现金额
     三列追加到主表最下面
  4. 退款表中未能匹配到主表的订单，作为新行追加（来源=退款(未匹配主表)），避免丢数
  5. 末尾增加「数据来源」列用于标识每行来源
"""
import openpyxl
import sys
import os

SRC = sys.argv[1] if len(sys.argv) > 1 else r"D:/360极速浏览器X下载/分账明细_2026-07-07_2026-08-06.xlsx"
OUT = sys.argv[2] if len(sys.argv) > 2 else SRC[: SRC.rfind(".")] + "_合并.xlsx"


def pick(wb, kw):
    for n in wb.sheetnames:
        if kw in n:
            return wb[n]
    return None


def cidx(header, target):
    for i, h in enumerate(header):
        if h is not None and str(h).strip() == target:
            return i
    return None


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def read_rows(ws):
    """抖音导出的 xlsx 常把 worksheet dimension 固定写成 A1:A1，
    read_only 模式会据此只读出 A1。先强制重算范围再取整表。"""
    if ws is None:
        return []
    if hasattr(ws, "reset_dimensions"):
        ws.reset_dimensions()
    return list(ws.iter_rows(values_only=True))


def main():
    wb = openpyxl.load_workbook(SRC, read_only=True, data_only=True)
    main_ws = pick(wb, "正向") or wb[wb.sheetnames[0]]
    ref_ws = pick(wb, "退款")
    comp_ws = pick(wb, "补偿")

    main_rows = read_rows(main_ws)
    mh = main_rows[0] if main_rows else []
    IDX_ORDER = cidx(mh, "订单编号")
    # 口径统一：输出列「客户实付」一律取「用户实付金额」，找不到才退回「订单实收金额」
    IDX_USERPAY = cidx(mh, "用户实付金额")
    if IDX_USERPAY is None:
        IDX_USERPAY = cidx(mh, "用户商品实付")
    if IDX_USERPAY is None:
        IDX_USERPAY = cidx(mh, "订单实收金额")
    IDX_SHISHOU = IDX_USERPAY
    # 「打款金额」列：主表优先取「商家应得」(2025-12 后的新模板)，老模板回退「提现金额」
    IDX_TIXIAN = cidx(mh, "商家应得")
    if IDX_TIXIAN is None:
        IDX_TIXIAN = cidx(mh, "提现金额(元)")
    if IDX_TIXIAN is None:
        IDX_TIXIAN = cidx(mh, "提现金额")
    assert None not in (IDX_ORDER, IDX_SHISHOU, IDX_TIXIAN), (
        "主表缺少必要列（订单编号/用户实付金额/商家应得）"
    )

    ncols = len(mh)
    SRC_COL = ncols  # 0-based 索引：数据来源列

    # ---- 退款表 -> 映射 ----
    refund_map = {}
    if ref_ws:
        rrows = read_rows(ref_ws)
        rh = rrows[0] if rrows else []
        ro = cidx(rh, "订单编号")
        rs = cidx(rh, "用户实付金额")
        if rs is None:
            rs = cidx(rh, "订单实收金额")
        rt = cidx(rh, "商家应得")
        if rt is None:
            rt = cidx(rh, "提现金额")
        rsh = cidx(rh, "订单实收金额")
        for r in rrows[1:]:
            oid = r[ro] if ro is not None else None
            if oid is None:
                continue
            refund_map[str(oid)] = {
                "user_pay": num(r[rs]) if rs is not None else 0.0,
                "tixian": num(r[rt]) if rt is not None else 0.0,
                "shishou": num(r[rsh]) if rsh is not None else 0.0,
            }

    # ---- 补偿表 -> 列表 ----
    comp_data = []
    if comp_ws:
        crows = read_rows(comp_ws)
        ch = crows[0] if crows else []
        co = cidx(ch, "订单编号")
        cs = cidx(ch, "用户实付金额")
        if cs is None:
            cs = cidx(ch, "订单实收金额")
        ct = cidx(ch, "商家应得")
        if ct is None:
            ct = cidx(ch, "提现金额")
        for r in crows[1:]:
            oid = r[co] if co is not None else None
            if oid is None:
                continue
            comp_data.append(
                {
                    "order": r[co],
                    "shishou": num(r[cs]) if cs is not None else 0.0,
                    "tixian": num(r[ct]) if ct is not None else 0.0,
                }
            )

    # ---- 构建输出 ----
    out = openpyxl.Workbook()
    ws = out.active
    ws.title = "合并明细"
    header_out = list(mh) + ["数据来源"]
    # 输出表头重命名
    rename_map = {
        IDX_ORDER: "OTA订单号",
        IDX_SHISHOU: "客户实付",
        IDX_TIXIAN: "打款金额",
    }
    for _idx, _name in rename_map.items():
        header_out[_idx] = _name
    ws.append(header_out)

    matched_ids = set()
    adjust_log = []
    for r in main_rows[1:]:
        row = list(r)
        if len(row) < ncols:
            row = row + [None] * (ncols - len(row))
        else:
            row = row[:ncols]

        oid = row[IDX_ORDER]
        src = "正向"
        if oid is not None and str(oid) in refund_map:
            m = refund_map[str(oid)]
            before_s = num(row[IDX_SHISHOU])
            before_t = num(row[IDX_TIXIAN])
            row[IDX_SHISHOU] = round(before_s + m["user_pay"], 2)
            row[IDX_TIXIAN] = round(before_t + m["tixian"], 2)
            src = "正向(已并退款)"
            matched_ids.add(str(oid))
            adjust_log.append(
                (oid, before_s, m["user_pay"], before_s + m["user_pay"], before_t, m["tixian"], before_t + m["tixian"])
            )
        row.append(src)
        ws.append(row)

    # 补偿行
    for c in comp_data:
        newrow = [None] * ncols
        newrow[IDX_ORDER] = c["order"]
        newrow[IDX_SHISHOU] = c["shishou"]
        newrow[IDX_TIXIAN] = c["tixian"]
        newrow.append("补偿")
        ws.append(newrow)

    # 退款未匹配主表的，追加避免丢数
    for oid, m in refund_map.items():
        if oid in matched_ids:
            continue
        newrow = [None] * ncols
        newrow[IDX_ORDER] = oid
        newrow[IDX_SHISHOU] = m["user_pay"]
        newrow[IDX_TIXIAN] = m["tixian"]
        newrow.append("退款(未匹配主表)")
        ws.append(newrow)

    out.save(OUT)

    print("已保存:", OUT)
    print("主表数据行:", len(main_rows) - 1)
    print("退款匹配并调整:", len(matched_ids))
    print("补偿追加:", len(comp_data))
    print("退款未匹配主表:", len(refund_map) - len(matched_ids))
    print("---- 调整明细 ----")
    for a in adjust_log:
        print(
            "订单 %s | 客户实付(用户实付) %.2f + %.2f => %.2f | 提现 %.2f + %.2f => %.2f"
            % (a[0], a[1], a[2], a[3], a[4], a[5], a[6])
        )


if __name__ == "__main__":
    main()
