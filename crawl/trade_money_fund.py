#!/usr/bin/env python
# -*- coding:utf-8 -*-
"""
Date: 2024/10/6 17:00
Desc: 集思录-T+0 QDII
集思录：https://www.jisilu.cn
"""

import pandas as pd

import requests
import simplejson

def trade_money_fund_jsl() -> pd.DataFrame:
    """
    集思录
    :return: 
    :rtype: pandas.DataFrame
    """
    url = "https://www.jisilu.cn/data/repo/trade_money_fund_list/?___jsl=LST___t=1761990217090"
    params = {}
    response = requests.post(url, params=params)  # Removed method="POST"
    try:
        # Check if response contains valid JSON
        data_json = response.json()
        temp_df = pd.DataFrame([item["cell"] for item in data_json["rows"]])
    except simplejson.errors.JSONDecodeError as e:
        print(f"Failed to decode JSON. Response content: {response.text}")
        return pd.DataFrame()  # Return empty DataFrame on error
    except KeyError as e:
        print(f"Error parsing JSON data: {e}")
        return pd.DataFrame()  # Return empty DataFrame on error

        # {
        #     "id": "511620",
        #     "cell": {
        #         "fund_id": "511620",
        #         "fund_nm": "货币基金",
        #         "pinyin": "hbjj",
        #         "issuer_nm": "国泰基金",
        #         "urls": "https:\/\/e.gtfund.com\/Etrade\/Jijin\/view\/id\/511620",
        #         "tradeable_fl": 1,
        #         "active_flg": "N",
        #         "rule_tp": 3,
        #         "descr": "算尾不算头",
        #         "buy_earn": "0.359",
        #         "profit_dt": "2025-10-30",
        #         "profit_style": null,
        #         "profit_rt": "0.356",
        #         "profit_rt_10d": "1.452",
        #         "profit_rt_1m": "1.448",
        #         "profit_rt_3m": "1.480",
        #         "profit_rt_6m": "1.553",
        #         "profit_rt_1y": "1.695",
        #         "profit_per_million": "0.3994",
        #         "unit_total": "3.17",
        #         "unit_change": "0.0100",
        #         "orders": 102,
        #         "price": "100.008",
        #         "pre_close": "100.0090",
        #         "price_dt": "2025-10-31",
        #         "price_time": "14:59:55",
        #         "net_value_dt": "2025-10-30",
        #         "net_value": 100,
        #         "amount": 321,
        #         "profit_rt7": "1.448",
        #         "t2_dt": "11-04(周二)",
        #         "tooltip_price_dt": "10-31(周五)",
        #         "today_net_value": "<span style=\"color:#aaa;font-style:italic\">100.012<\/span>",
        #         "sell_price": 100.01990136986,
        #         "is_eval": true,
        #         "discount_rt": "-0.004",
        #         "discount_rt2": 0.011967123287667,
        #         "profit_rt2": "1.092",
        #         "today_net_value_new": "100.012",
        #         "discount_rt_num": "-0.004",
        #         "tooltip_today_net_value": "估计净值，含3天(2025-10-31到2025-11-02)的净值修正， 每日的实际净值为100.00",
        #         "tooltip_price": "价格时间： 2025-10-31 14:59:55"
        #     }
        # }


    temp_df.rename(
        columns={
            "fund_id": "代码",
            "fund_nm": "名称",
            "price": "现价",
            "today_net_value_new": "净值",
            "discount_rt_num": "溢价",#百分之xxxx
            "profit_rt": "买入赎回年化",#百分之xxxx
            "profit_rt2": "申购卖出年化",#百分之xxxx
            "t2_dt": "到账日",
            "unit_total": "规模",#亿
        },
        inplace=True,
    )
    temp_df = temp_df[
        [
            "代码",
            "名称",
            "现价",
            "净值",
            "溢价",
            "买入赎回年化",
            "申购卖出年化",
            "到账日",
            "规模",
        ]
    ]
    temp_df["现价"] = pd.to_numeric(temp_df["现价"], errors="coerce")
    temp_df["净值"] = pd.to_numeric(temp_df["净值"], errors="coerce")
    temp_df["溢价"] = pd.to_numeric(temp_df["溢价"], errors="coerce")
    temp_df["买入赎回年化"] = pd.to_numeric(temp_df["买入赎回年化"], errors="coerce")
    temp_df["申购卖出年化"] = pd.to_numeric(temp_df["申购卖出年化"], errors="coerce")
    return temp_df


if __name__ == "__main__":
    trade_money_fund_jsl_df = trade_money_fund_jsl()
    print(trade_money_fund_jsl_df)  # Corrected variable name for printing
    df_index = pd.DataFrame(trade_money_fund_jsl_df)  # Corrected variable name for DataFrame creation
    print(df_index)
