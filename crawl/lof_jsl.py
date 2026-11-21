#!/usr/bin/env python
# -*- coding:utf-8 -*-
"""
Date: 2025/11/11 17:00
Desc: 集思录-T+0 QDII
集思录：https://www.jisilu.cn/data/lof/#index
"""

import pandas as pd

from akshare.request import make_request_with_retry_json


def lof_stock_jsl() -> pd.DataFrame:
    """
    集思录-LOF-股票LLOF
    https://www.jisilu.cn/data/lof/#stock
    :return: LOF-股票LOF
    :rtype: pandas.DataFrame
    """
    url = "https://www.jisilu.cn/data/lof/stock_lof_list/"
    params = {
        "___jsl": "LST___t=1762857595504",
        "rp": "25",
    }
    data_json = make_request_with_retry_json(url, params)
    temp_df = pd.DataFrame([item["cell"] for item in data_json["rows"]])
    # {
    #             "fund_id": "160105",
    #             "fund_nm": "南方积配LOF",
    #             "price": "1.345",
    #             "pre_close": "1.3500",
    #             "increase_rt": "-0.37",
    #             "volume": "5.25",
    #             "stock_volume": "3.9500",
    #             "price_dt": "2025-11-11",
    #             "last_time": "15:14:18",
    #             "amount": 1122,
    #             "amount_incr": "0",
    #             "amount_increase_rt": "0.00",
    #             "fund_nav": "1.3466",
    #             "nav_incr_rt": "-0.44",
    #             "nav_dt": "2025-11-10",
    #             "estimate_value": "1.3333",
    #             "est_val_dt": "-",
    #             "last_est_time": "15:14:18",
    #             "nav_discount_rt": "0.88",
    #             "report_dt": "2025-09-30",
    #             "stock_ratio": "91.86",
    #             "stock_amount": "6.63",
    #             "bond_ratio": "0.10",
    #             "bond_amount": "0.01",
    #             "all_amount": "7.22",
    #             "stock_increase_rt": "-0.99",
    #             "apply_fee": "1.50%",
    #             "apply_status": "开放申购",
    #             "apply_fee_tips": "M＜100万\t1.50%\r\n100万≤M＜1000万\t1.20%\r\n1000万≤M\t每笔1000元",
    #             "redeem_fee": "1.50%",
    #             "redeem_status": "开放赎回",
    #             "redeem_fee_tips": "T＜7日\t1.50%\r\nT≥7天\t0.50%",
    #             "min_amt": "申购起点：1000元\r\n定投起点：100元\r\n日累计申购限额：无限额\r\n首次购买：1000元\r\n追加购买：1000元",
    #             "issuer_nm": "南方基金",
    #             "urls": "https:\/\/www.nffund.com\/main\/nffund\/personal-financing\/detail.shtml?fundCode=160105",
    #             "notes": "",
    #             "owned": 0,
    #             "holded": 0,
    #             "index_id": "",
    #             "ratio_tips": "报告日期：2025-09-30\n总 市 值：7.22亿元\n股票占比：91.86%\n股票市值：6.63亿元\n债券占比：0.10%\n债券市值：0.01亿元",
    #             "apply_redeem_status": "-",
    #             "amount_incr_tips": "最新份额：1122万份；增长：0.00%",
    #             "turnover_rt": "0.35",
    #             "index_increase_rt": "-"
    #         }
    temp_df.rename(
        columns={
            "fund_id": "代码",
            "fund_nm": "名称",
            "price": "现价",
            "pre_close": "前收盘价",
            "increase_rt": "涨幅",
            "volume": "成交",
            "stock_volume": "成交量",
            "price_dt": "价格日期",
            "last_time": "最新时间",
            "amount": "场内份额",
            "amount_incr": "场内新增",
            "amount_increase_rt": "场内份额增长率",
            "fund_nav": "基金净值",
            "nav_incr_rt": "净值增长率",
            "nav_dt": "净值日期",
            "estimate_value": "实时估值",
            "est_val_dt": "估值日期",
            "last_est_time": "最新估值时间",
            "nav_discount_rt": "溢价率",
            "report_dt": "报告日期",
            "stock_ratio": "股票占比",
            "stock_amount": "股票市值",
            "bond_ratio": "债券占比",
            "bond_amount": "债券市值",
            "all_amount": "总资产",
            "stock_increase_rt": "股票涨幅",
            "apply_fee": "申购费",
            "apply_status": "申购状态",
            "redeem_fee": "赎回费",
            "redeem_status": "赎回状态",
            "min_amt": "最小金额",
            "issuer_nm": "基金公司",
            "index_increase_rt": "指数涨幅",
        },
        inplace=True,
    )
    temp_df = temp_df[
        [
            "代码",
            "名称",
            "现价",
            "前收盘价",
            "涨幅",
            "成交",
            "成交量",
            "价格日期",
            "最新时间",
            "场内份额",
            "场内新增",
            "场内份额增长率",
            "基金净值",
            "净值增长率",
            "净值日期",
            "实时估值",
            "估值日期",
            "最新估值时间",
            "溢价率",
            "报告日期",
            "股票占比",
            "股票市值",
            "债券占比",
            "债券市值",
            "总资产",
            "股票涨幅",
            "申购费",
            "申购状态",
            "赎回费",
            "赎回状态",
            "最小金额",
            "基金公司",
            "指数涨幅",
        ]
    ]
    temp_df["价格日期"] = pd.to_datetime(temp_df["价格日期"], errors="coerce").dt.date
    temp_df["最新时间"] = pd.to_datetime(temp_df["最新时间"], format="%H:%M:%S", errors="coerce").dt.time
    # temp_df["估值日期"] = pd.to_datetime(temp_df["估值日期"], errors="coerce").dt.date
    temp_df["最新估值时间"] = pd.to_datetime(temp_df["最新估值时间"], format="%H:%M:%S", errors="coerce").dt.time
    temp_df["现价"] = pd.to_numeric(temp_df["现价"], errors="coerce")
    temp_df["成交"] = pd.to_numeric(temp_df["成交"], errors="coerce")
    temp_df["场内份额"] = pd.to_numeric(temp_df["场内份额"], errors="coerce")
    temp_df["场内新增"] = pd.to_numeric(temp_df["场内新增"], errors="coerce")
    temp_df["基金净值"] = pd.to_numeric(temp_df["基金净值"], errors="coerce")
    temp_df["实时估值"] = pd.to_numeric(temp_df["实时估值"], errors="coerce")
    return temp_df


def lof_index_jsl() -> pd.DataFrame:
    """
    集思录-LOF-指数LOF
    https://www.jisilu.cn/data/lof/#index
    :return: LOF-指数LOF
    :rtype: pandas.DataFrame
    """
    url = "https://www.jisilu.cn/data/lof/index_lof_list/"
    params = {
        "___jsl": "LST___t=1762857501404",
        "rp": "25",
    }
    data_json = make_request_with_retry_json(url, params=params)
    temp_df = pd.DataFrame([item["cell"] for item in data_json["rows"]])
    # {
    #             "fund_id": "160119",
    #             "fund_nm": "500ETF联接LOF",
    #             "asset_ratio": "95.000",
    #             "price": "2.033",
    #             "pre_close": "2.0470",
    #             "price_dt": "2025-11-11",
    #             "increase_rt": "-0.68",
    #             "volume": "57.61",
    #             "stock_volume": "28.2800",
    #             "last_time": "15:14:21",
    #             "amount": 4243,
    #             "amount_incr": "-1",
    #             "amount_increase_rt": "-0.02",
    #             "fund_nav": "2.0589",
    #             "nav_dt": "2025-11-10",
    #             "estimate_value": "2.0450",
    #             "est_val_dt": "2025-11-11",
    #             "last_est_time": "15:14:21",
    #             "nav_discount_rt": "-0.59",
    #             "index_id": "399905",
    #             "index_nm": "中证 500",
    #             "index_increase_rt": "-0.71",
    #             "idx_price_dt": "2025-11-11",
    #             "apply_fee": "1.20%",
    #             "apply_status": "开放申购",
    #             "apply_fee_tips": "M＜100万\t1.20%\r\n100万≤M＜500万\t0.70%\r\n500万≤M＜1000万\t0.20%\r\n1000万≤M\t每笔1000元",
    #             "redeem_fee": "1.50%",
    #             "redeem_status": "开放赎回",
    #             "redeem_fee_tips": "N＜7天\t1.50%\r\n7天≤N＜30天\t0.50%\r\n30天≤N＜180天\t0.25%\r\nN≥180日\t0.00%",
    #             "min_amt": "申购起点：1000元\r\n定投起点：100元\r\n日累计申购限额：无限额\r\n首次购买：1000元\r\n追加购买：1000元",
    #             "notes": "",
    #             "issuer_nm": "南方基金",
    #             "urls": "https:\/\/www.nffund.com\/main\/nffund\/personal-financing\/detail.shtml?fundCode=160119",
    #             "owned": 0,
    #             "holded": 0,
    #             "apply_redeem_status": "-",
    #             "amount_incr_tips": "最新份额：4243万份；增长：-0.02%",
    #             "turnover_rt": "0.67"
    #         }
    temp_df.rename(
        columns={
            "fund_id": "代码",
            "fund_nm": "名称",
            "price": "现价",
            "pre_close": "前收盘价",
            "increase_rt": "涨幅",
            "volume": "成交",
            "stock_volume": "成交量",
            "price_dt": "价格日期",
            "last_time": "最新时间",
            "amount": "场内份额",
            "amount_incr": "场内新增",
            "amount_increase_rt": "场内份额增长率",
            "fund_nav": "基金净值",
            "nav_dt": "净值日期",
            "estimate_value": "实时估值",
            "est_val_dt": "估值日期",
            "last_est_time": "最新估值时间",
            "nav_discount_rt": "溢价率",
            "index_nm": "相关标的",
            "index_increase_rt": "指数涨幅",
            "apply_fee": "申购费",
            "apply_status": "申购状态",
            "redeem_fee": "赎回费",
            "apply_fee_tips": "申购费率说明",
            "redeem_fee_tips": "赎回费率说明",
            "min_amt": "最小金额",
            "issuer_nm": "基金公司",
        },
        inplace=True,
    )
    temp_df = temp_df[
        [
            "代码",
            "名称",
            "现价",
            "前收盘价",
            "涨幅",
            "成交",
            "成交量",
            "价格日期",
            "最新时间",
            "场内份额",
            "场内新增",
            "场内份额增长率",
            "基金净值",
            "净值日期",
            "实时估值",
            "估值日期",
            "最新估值时间",
            "溢价率",
            "相关标的",
            "指数涨幅",
            "申购费",
            "申购状态",
            "赎回费",
            "申购费率说明",
            "赎回费率说明",
            "最小金额",
            "基金公司",
        ]
    ]
    temp_df["价格日期"] = pd.to_datetime(temp_df["价格日期"], errors="coerce").dt.date
    temp_df["最新时间"] = pd.to_datetime(temp_df["最新时间"], format="%H:%M:%S", errors="coerce").dt.time
    # temp_df["估值日期"] = pd.to_datetime(temp_df["估值日期"], errors="coerce").dt.date
    temp_df["最新估值时间"] = pd.to_datetime(temp_df["最新估值时间"], format="%H:%M:%S", errors="coerce").dt.time
    temp_df["现价"] = pd.to_numeric(temp_df["现价"], errors="coerce")
    temp_df["成交"] = pd.to_numeric(temp_df["成交"], errors="coerce")
    temp_df["场内份额"] = pd.to_numeric(temp_df["场内份额"], errors="coerce")
    temp_df["场内新增"] = pd.to_numeric(temp_df["场内新增"], errors="coerce")
    temp_df["基金净值"] = pd.to_numeric(temp_df["基金净值"], errors="coerce")
    temp_df["实时估值"] = pd.to_numeric(temp_df["实时估值"], errors="coerce")
    return temp_df


if __name__ == "__main__":
    lof_stock_jsl_df = lof_stock_jsl()
    print(lof_stock_jsl_df)

    lof_index_jsl_df = lof_index_jsl()
    print(lof_index_jsl)
