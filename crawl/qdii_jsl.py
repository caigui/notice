#!/usr/bin/env python
# -*- coding:utf-8 -*-
"""
Date: 2024/10/6 17:00
Desc: 集思录-T+0 QDII
集思录：https://www.jisilu.cn/data/qdii/#qdiie
"""

import pandas as pd

from akshare.request import make_request_with_retry_json


def qdii_e_index_jsl(cookie: str = None) -> pd.DataFrame:
    """
    集思录-T+0 QDII-欧美市场-欧美指数
    https://www.jisilu.cn/data/qdii/#qdiia
    :return: T+0 QDII-亚洲市场
    :rtype: pandas.DataFrame
    """
    url = "https://www.jisilu.cn/data/qdii/qdii_list/E"
    params = {
        "___jsl": "LST___t=1728207798534",
        "rp": "22",
    }
    header = {"Cookie":cookie}
    data_json = make_request_with_retry_json(url, params,headers=header)
    temp_df = pd.DataFrame([item["cell"] for item in data_json["rows"]])
    temp_df.rename(
        columns={
            "fund_id": "代码",
            "fund_nm": "名称",
            "price": "现价",
            "increase_rt": "涨幅",
            "volume": "成交",
            "amount": "场内份额",
            "amount_incr": "场内新增",
            "fund_nav": "T-2净值",
            "nav_dt": "净值日期",
            "estimate_value": "T-1估值",
            "last_est_dt": "估值日期",
            "nav_discount_rt": "T-1溢价率",
            "index_nm": "相关标的",
            "ref_increase_rt": "T-1指数涨幅",
            "apply_fee": "申购费",
            "redeem_fee": "赎回费",
            "mt_fee": "托管费",
            "issuer_nm": "基金公司",
            "apply_status":"申购状态",
        },
        inplace=True,
    )
    temp_df = temp_df[
        [
            "代码",
            "名称",
            "现价",
            "涨幅",
            "成交",
            "场内份额",
            "场内新增",
            "T-2净值",
            "净值日期",
            "T-1估值",
            "估值日期",
            "T-1溢价率",
            "相关标的",
            "T-1指数涨幅",
            "申购费",
            "赎回费",
            "托管费",
            "基金公司",
            "申购状态",
        ]
    ]
    temp_df["净值日期"] = pd.to_datetime(temp_df["净值日期"], errors="coerce").dt.date
    temp_df["估值日期"] = pd.to_datetime(temp_df["估值日期"], errors="coerce").dt.date
    temp_df["现价"] = pd.to_numeric(temp_df["现价"], errors="coerce")
    temp_df["成交"] = pd.to_numeric(temp_df["成交"], errors="coerce")
    temp_df["场内份额"] = pd.to_numeric(temp_df["场内份额"], errors="coerce")
    temp_df["场内新增"] = pd.to_numeric(temp_df["场内新增"], errors="coerce")
    temp_df["T-2净值"] = pd.to_numeric(temp_df["T-2净值"], errors="coerce")
    temp_df["T-1估值"] = pd.to_numeric(temp_df["T-1估值"], errors="coerce")
    temp_df["托管费"] = pd.to_numeric(temp_df["托管费"], errors="coerce")
    return temp_df


def qdii_e_comm_jsl(cookie: str = None) -> pd.DataFrame:
    """
    集思录-T+0 QDII-欧美市场-商品
    https://www.jisilu.cn/data/qdii/#qdiia
    :return: T+0 QDII-欧美市场-商品
    :rtype: pandas.DataFrame
    """
    url = "https://www.jisilu.cn/data/qdii/qdii_list/C"
    params = {
        "___jsl": "LST___t=1728207798534",
        "rp": "22",
    }
    header = {"Cookie":cookie}
    data_json = make_request_with_retry_json(url, params=params,headers=header)
    temp_df = pd.DataFrame([item["cell"] for item in data_json["rows"]])
    temp_df.rename(
        columns={
            "fund_id": "代码",
            "fund_nm": "名称",
            "price": "现价",
            "increase_rt": "涨幅",
            "volume": "成交",
            "amount": "场内份额",
            "amount_incr": "场内新增",
            "fund_nav": "T-2净值",
            "nav_dt": "净值日期",
            "estimate_value": "T-1估值",
            "last_est_dt": "估值日期",
            "nav_discount_rt": "T-1溢价率",
            "index_nm": "相关标的",
            "ref_increase_rt": "T-1指数涨幅",
            "apply_fee": "申购费",
            "redeem_fee": "赎回费",
            "mt_fee": "托管费",
            "issuer_nm": "基金公司",
            "apply_status":"申购状态",
        },
        inplace=True,
    )
    temp_df = temp_df[
        [
            "代码",
            "名称",
            "现价",
            "涨幅",
            "成交",
            "场内份额",
            "场内新增",
            "T-2净值",
            "净值日期",
            "T-1估值",
            "估值日期",
            "T-1溢价率",
            "相关标的",
            "T-1指数涨幅",
            "申购费",
            "赎回费",
            "托管费",
            "基金公司",
            "申购状态",
        ]
    ]
    temp_df["净值日期"] = pd.to_datetime(temp_df["净值日期"], errors="coerce").dt.date
    temp_df["估值日期"] = pd.to_datetime(temp_df["估值日期"], errors="coerce").dt.date
    temp_df["现价"] = pd.to_numeric(temp_df["现价"], errors="coerce")
    temp_df["成交"] = pd.to_numeric(temp_df["成交"], errors="coerce")
    temp_df["场内份额"] = pd.to_numeric(temp_df["场内份额"], errors="coerce")
    temp_df["场内新增"] = pd.to_numeric(temp_df["场内新增"], errors="coerce")
    temp_df["T-2净值"] = pd.to_numeric(temp_df["T-2净值"], errors="coerce")
    temp_df["T-1估值"] = pd.to_numeric(temp_df["T-1估值"], errors="coerce")
    temp_df["托管费"] = pd.to_numeric(temp_df["托管费"], errors="coerce")
    return temp_df


def qdii_a_index_jsl() -> pd.DataFrame:
    """
    集思录-T+0 QDII-亚洲市场-亚洲指数
    https://www.jisilu.cn/data/qdii/#qdiia
    :return: T+0 QDII-亚洲市场-亚洲指数
    :rtype: pandas.DataFrame
    """
    url = "https://www.jisilu.cn/data/qdii/qdii_list/A"
    params = {
        "___jsl": "LST___t=1728206439242",
        "rp": "22",
    }
    data_json = make_request_with_retry_json(url, params=params)
    temp_df = pd.DataFrame([item["cell"] for item in data_json["rows"]])
    temp_df.rename(
        columns={
            "fund_id": "代码",
            "fund_nm": "名称",
            "price": "现价",
            "increase_rt": "涨幅",
            "volume": "成交",
            "amount": "场内份额",
            "amount_incr": "场内新增",
            "fund_nav": "净值",
            "nav_dt": "净值日期",
            "estimate_value": "估值",
            "nav_discount_rt": "溢价率",
            "index_nm": "相关标的",
            "ref_increase_rt": "指数涨幅",
            "apply_fee": "申购费",
            "redeem_fee": "赎回费",
            "mt_fee": "托管费",
            "issuer_nm": "基金公司",
            "apply_status":"申购状态",
        },
        inplace=True,
    )

    temp_df = temp_df[
        [
            "代码",
            "名称",
            "现价",
            "涨幅",
            "成交",
            "场内份额",
            "场内新增",
            "净值",
            "净值日期",
            "估值",
            "溢价率",
            "相关标的",
            "指数涨幅",
            "申购费",
            "赎回费",
            "托管费",
            "基金公司",
            "申购状态",
        ]
    ]
    temp_df["净值日期"] = pd.to_datetime(temp_df["净值日期"], errors="coerce").dt.date
    temp_df["现价"] = pd.to_numeric(temp_df["现价"], errors="coerce")
    temp_df["成交"] = pd.to_numeric(temp_df["成交"], errors="coerce")
    temp_df["场内份额"] = pd.to_numeric(temp_df["场内份额"], errors="coerce")
    temp_df["场内新增"] = pd.to_numeric(temp_df["场内新增"], errors="coerce")
    temp_df["净值"] = pd.to_numeric(temp_df["净值"], errors="coerce")
    temp_df["估值"] = pd.to_numeric(temp_df["估值"], errors="coerce")
    temp_df["托管费"] = pd.to_numeric(temp_df["托管费"], errors="coerce")
    return temp_df


if __name__ == "__main__":
    cookie = "kbzw__Session=c1a30gsr12j6ncoe7pt2u89c45; path=/, kbzw__user_login=deleted; expires=Thu, 01-Jan-1970 00:00:01 GMT; path=/, kbzw__user_login=7Obd08_P1ebax9aXwZOqmrCorKuRpIKvpuXK7N_u0ejF1dSerMegwtfdrMqqn6qVr5rcqaqwx9PDpt3bz6qdrpqnlqyYrqXW2cXS1qCbq6KtlK2amLKgubXOvp-qrKCppK2XqpSpmK6ltrG_0aTC2PPV487XkKylo5iJx8ri3eTg7IzFtpaSp6Wjs4HHyuKvqaSZ5K2Wn4G45-PkxsfG1sTe3aihqpmklK2Xm8OpxK7ApZXV4tfcgr3G2uLioYGzyebo4s6opaiQpo-rq6qqj6GTqJnIyt_N6cullqquoauX; expires=Thu, 19-Feb-2026 10:03:52 GMT; path=/"
    # qdii_e_index_jsl_df = qdii_e_index_jsl(cookie)
    # print(qdii_e_index_jsl_df)
    cookie = 'kbzw__Session=pi67k62vhh573cuulpq5mvvu75; Hm_lvt_164fe01b1433a19b507595a43bf58262=1776395907; HMACCOUNT=541BCC8A0A6F6C16; kbz_newcookie=1; kbzw__user_login=7Obd08_P1ebax9aXwZOqmrCorKuRpIKvpuXK7N_u0ejF1dSerMegwtfdrMqqn6qVr5rcqaqwx9PDpt3bz6qdrpqnlqyYrqXW2cXS1qCbq6KtlK2amLKgubXOvp-qrKCvn7CXr5KpmK6ltrG_0aTC2PPV487XkKylo5iJx8ri3eTg7IzFtpaSp6Wjs4HHyuKvqaSZ5K2Wn4G45-PkxsfG1sTe3aihqpmklK2Xm8OpxK7ApZXV4tfcgr3G2uLioYGzyebo4s6onauZpJGlp6GogcPC2trn0qihqpmklK2XuNzIn5KosKOZp5ylkg..; Hm_lpvt_164fe01b1433a19b507595a43bf58262=1776412229'
    qdii_e_comm_jsl_df = qdii_e_comm_jsl(cookie)
    print(qdii_e_comm_jsl_df)

    # qdii_a_index_jsl_df = qdii_a_index_jsl()
    # print(qdii_a_index_jsl_df)