import akshare as ak
import pandas as pd
from datetime import datetime, timedelta
from akshare.request import make_request_with_retry_json

class ConvertibleBonds:
    def __init__(self):
        self.cbInfo = []
        self.cbCprInfo = []
        #溢价率 20 （这个变量在这里没用到）
        self.discount_threshold = 20  # This variable is not used in this code

    # 可有筛选出当天的数据
    def get_all_cb_info(self):
        try:
            bond_zh_hs_cov_spot_df = ak.bond_zh_hs_cov_spot()

            # 循环处理每个可转债的历史数据
            for symbol in bond_zh_hs_cov_spot_df['symbol']:  # Assuming '代码' column holds the symbol
                self.process_daily_data(symbol)
            # print(bond_zh_hs_cov_spot_df)
            # 确保 'trade' 和 'low' 列存在且是数值类型
            if 'trade' in bond_zh_hs_cov_spot_df.columns and 'low' in bond_zh_hs_cov_spot_df.columns:
                try:
                    bond_zh_hs_cov_spot_df['trade'] = pd.to_numeric(bond_zh_hs_cov_spot_df['trade'], errors='coerce')
                    bond_zh_hs_cov_spot_df['low'] = pd.to_numeric(bond_zh_hs_cov_spot_df['low'], errors='coerce')

                    # 删除转换后产生的 NaN 值 (即无法转换为数字的值)
                    bond_zh_hs_cov_spot_df = bond_zh_hs_cov_spot_df.dropna(subset=['trade', 'low'])

                    # 剔除 'low' 列为 0 的数据
                    bond_zh_hs_cov_spot_df = bond_zh_hs_cov_spot_df[bond_zh_hs_cov_spot_df['low'] != 0]

                    # 执行筛选：trade列 - low列 > trade列的 15%
                    filtered_df = bond_zh_hs_cov_spot_df[bond_zh_hs_cov_spot_df['trade'] - bond_zh_hs_cov_spot_df['low'] > (0.15 * bond_zh_hs_cov_spot_df['trade'])]
                    if not filtered_df.empty:
                        print(filtered_df)

                except ValueError as e:
                    print(f"Error during numeric conversion or filtering: {e}")
                    print("Please check the data types of 'trade' and 'low' columns.")
                except Exception as e:
                    print(f"An unexpected error occurred: {e}")
            else:
                print("The 'trade' or 'low' column is not found in the DataFrame.")
                print("Available columns:", bond_zh_hs_cov_spot_df.columns)

        except Exception as e:
            print(f"An error occurred: {e}")


    def process_daily_data(self, symbol):
        try:
            bond_zh_hs_cov_daily_df = ak.bond_zh_hs_cov_daily(symbol=symbol)

            # 确保 'close', 'low', 'open', and 'date' 列存在
            if 'close' in bond_zh_hs_cov_daily_df.columns and 'low' in bond_zh_hs_cov_daily_df.columns and 'open' in bond_zh_hs_cov_daily_df.columns and 'date' in bond_zh_hs_cov_daily_df.columns:
                try:
                    # 转换为数值类型
                    bond_zh_hs_cov_daily_df['close'] = pd.to_numeric(bond_zh_hs_cov_daily_df['close'], errors='coerce')
                    bond_zh_hs_cov_daily_df['low'] = pd.to_numeric(bond_zh_hs_cov_daily_df['low'], errors='coerce')
                    bond_zh_hs_cov_daily_df['open'] = pd.to_numeric(bond_zh_hs_cov_daily_df['open'], errors='coerce')

                    # 转换为日期类型
                    bond_zh_hs_cov_daily_df['date'] = pd.to_datetime(bond_zh_hs_cov_daily_df['date'], errors='coerce')

                    # 删除 NaN 值, including 'open'
                    bond_zh_hs_cov_daily_df = bond_zh_hs_cov_daily_df.dropna(subset=['close', 'low', 'open', 'date'])

                    # 过滤近一年的数据
                    one_year_ago = datetime.now() - timedelta(days=365)
                    recent_data_df = bond_zh_hs_cov_daily_df[bond_zh_hs_cov_daily_df['date'] >= one_year_ago]

                    # 剔除 open = low 的数据
                    recent_data_df = recent_data_df[recent_data_df['open'] != recent_data_df['low']]

                    #剔除 recent_data_df['open']  < 90 的时候的数据
                    recent_data_df = recent_data_df[recent_data_df['open'] >= 90]

                    # 过滤掉 close - open > open * 0.15(当日大涨的数据)
                    recent_data_df = recent_data_df[ (recent_data_df['close'] - recent_data_df['open']) <= (0.15 * recent_data_df['open'])]

                    # 执行筛选：close列 - low列 > close列的 15%
                    filtered_daily_df = recent_data_df[recent_data_df['close'] - recent_data_df['low'] > (0.15 * recent_data_df['close'])]

                    # 只在 filtered_daily_df 不为空时才打印
                    if not filtered_daily_df.empty:
                        print(f"Historical data for symbol {symbol} (last year):")
                        print(filtered_daily_df)
                    # else:
                    #     print(f"No historical data found for symbol {symbol} (last year) that meets the criteria.")

                except ValueError as e:
                    print(f"Error processing historical data for {symbol}: {e}")
                except Exception as e:
                    print(f"An unexpected error occurred while processing historical data for {symbol}: {e}")

            else:
                print(f"The 'close', 'low', 'open', or 'date' column is not found in the daily data for symbol {symbol}.")

        except Exception as e:
            print(f"Error fetching daily data for symbol {symbol}: {e}")


def qdii_e_comm_jsl() -> pd.DataFrame:
    """
    集思录-T+0 QDII-欧美市场-商品
    https://www.jisilu.cn/data/qdii/#qdiia
    :return: T+0 QDII-欧美市场-商品
    :rtype: pandas.DataFrame
    """
    url = "https://www.jisilu.cn/data/qdii/qdii_list/C"
    params = {
        "___jsl": "LST___t=1770618317293",
        "rp": "22",
        "page":"1",
    }
    cookie="kbz_newcookie=1; kbzw__user_login=7Obd08_P1ebax9aX2sPfyOzgpK6UkZyh6dbc7OPm1Nq_1KKr2cagmKesp82r0qibqcKtr6mxmNXCpd3ZzN3OrMOnw5iyoO3K1L_RpKabrJ6smKyCsqS0zL_NjKWwrJmvnq-Vp5mYsqDNos6-n8bk4-LY48OllqWnk6C42c_Y6OzcmbrLgqeRpaeumLjZz6qtsInxoquLlqLn59_duNXDv-LpmK6frpCpl5efvsC1va2gmeHS5NGXqdvE4uacmKTY0-Pm2piqoKuQpo-npaOYtNHH1evemK6frpCplw..; kbzw__Session=tgh6j2qgq27k61jf2i8d638it7; Hm_lvt_164fe01b1433a19b507595a43bf58262=1770711009,1770711148; HMACCOUNT=19B655C3D36F5846; Hm_lpvt_164fe01b1433a19b507595a43bf58262=1770711301"
    header = {"Cookie":cookie}
    data_json = make_request_with_retry_json(url, params=params,headers=header)

    print(data_json)
    temp_df = pd.DataFrame([item["cell"] for item in data_json["rows"]])
    print(temp_df)
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
            "discount_rt": "T-1溢价率",
            "index_nm": "相关标的",
            "ref_increase_rt": "T-1指数涨幅",
            "apply_fee": "申购费",
            "redeem_fee": "赎回费",
            "mt_fee": "托管费",
            "issuer_nm": "基金公司",
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



def bond_cb_jsl(cookie: str = None) -> pd.DataFrame:
    """
    集思录可转债
    https://www.jisilu.cn/data/cbnew/#cb
    :param cookie: 输入获取到的游览器 cookie
    :type cookie: str
    :return: 集思录可转债
    :rtype: pandas.DataFrame
    """
    url = "https://www.jisilu.cn/data/cbnew/cb_list_new/"
    headers = {
        "accept": "application/json, text/javascript, */*; q=0.01",
        "accept-encoding": "gzip, deflate, br",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
        "cache-control": "no-cache",
        "content-length": "220",
        "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
        "cookie": cookie,
        "origin": "https://www.jisilu.cn",
        "pragma": "no-cache",
        "referer": "https://www.jisilu.cn/data/cbnew/",
        "sec-ch-ua": '" Not;A Brand";v="99", "Google Chrome";v="91", "Chromium";v="91"',
        "sec-ch-ua-mobile": "?0",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/91.0.4472.164 Safari/537.36",
        "x-requested-with": "XMLHttpRequest",
    }
    params = {
        "___jsl": f"LST___t={int(time.time() * 1000)}",
    }
    payload = {
        "fprice": "",
        "tprice": "",
        "curr_iss_amt": "",
        "volume": "",
        "svolume": "",
        "premium_rt": "",
        "ytm_rt": "",
        "market": "",
        "rating_cd": "",
        "is_search": "N",
        "market_cd[]": "shmb",  # noqa: F601
        "market_cd[]": "shkc",  # noqa: F601
        "market_cd[]": "szmb",  # noqa: F601
        "market_cd[]": "szcy",  # noqa: F601
        "btype": "",
        "listed": "Y",
        "qflag": "N",
        "sw_cd": "",
        "bond_ids": "",
        "rp": "50",
    }
    r = requests.post(url, params=params, json=payload, headers=headers)
    data_json = r.json()
    temp_df = pd.DataFrame([item["cell"] for item in data_json["rows"]])
    temp_df.rename(
        columns={
            "bond_id": "代码",
            "bond_nm": "转债名称",
            "price": "现价",
            "increase_rt": "涨跌幅",
            "stock_id": "正股代码",
            "stock_nm": "正股名称",
            "sprice": "正股价",
            "sincrease_rt": "正股涨跌",
            "pb": "正股PB",
            "convert_price": "转股价",
            "convert_value": "转股价值",
            "premium_rt": "转股溢价率",
            "dblow": "双低",
            "rating_cd": "债券评级",
            "put_convert_price": "回售触发价",
            "force_redeem_price": "强赎触发价",
            "convert_amt_ratio": "转债占比",
            "maturity_dt": "到期时间",
            "year_left": "剩余年限",
            "curr_iss_amt": "剩余规模",
            "volume": "成交额",
            "turnover_rt": "换手率",
            "ytm_rt": "到期税前收益",
        },
        inplace=True,
    )

    temp_df = temp_df[
        [
            "代码",
            "转债名称",
            "现价",
            "涨跌幅",
            "正股代码",
            "正股名称",
            "正股价",
            "正股涨跌",
            "正股PB",
            "转股价",
            "转股价值",
            "转股溢价率",
            "债券评级",
            "回售触发价",
            "强赎触发价",
            "转债占比",
            "到期时间",
            "剩余年限",
            "剩余规模",
            "成交额",
            "换手率",
            "到期税前收益",
            "双低",
        ]
    ]
    temp_df["到期时间"] = pd.to_datetime(temp_df["到期时间"], errors="coerce").dt.date
    temp_df["现价"] = pd.to_numeric(temp_df["现价"], errors="coerce")
    temp_df["涨跌幅"] = pd.to_numeric(temp_df["涨跌幅"], errors="coerce")
    temp_df["正股价"] = pd.to_numeric(temp_df["正股价"], errors="coerce")
    temp_df["正股涨跌"] = pd.to_numeric(temp_df["正股涨跌"], errors="coerce")
    temp_df["正股PB"] = pd.to_numeric(temp_df["正股PB"], errors="coerce")
    temp_df["转股价"] = pd.to_numeric(temp_df["转股价"], errors="coerce")
    temp_df["转股价值"] = pd.to_numeric(temp_df["转股价值"], errors="coerce")
    temp_df["转股溢价率"] = pd.to_numeric(temp_df["转股溢价率"], errors="coerce")
    temp_df["回售触发价"] = pd.to_numeric(temp_df["回售触发价"], errors="coerce")
    temp_df["强赎触发价"] = pd.to_numeric(temp_df["强赎触发价"], errors="coerce")
    temp_df["转债占比"] = pd.to_numeric(temp_df["转债占比"], errors="coerce")
    temp_df["剩余年限"] = pd.to_numeric(temp_df["剩余年限"], errors="coerce")
    temp_df["剩余规模"] = pd.to_numeric(temp_df["剩余规模"], errors="coerce")
    temp_df["成交额"] = pd.to_numeric(temp_df["成交额"], errors="coerce")
    temp_df["换手率"] = pd.to_numeric(temp_df["换手率"], errors="coerce")
    temp_df["到期税前收益"] = pd.to_numeric(temp_df["到期税前收益"], errors="coerce")
    return temp_df




"""
获取当日和历史异常跌-15%的数据
"""    
if __name__ == "__main__":
    qdii_e_comm_jsl_df = ak.qdii_e_comm_jsl()
    print(qdii_e_comm_jsl_df)

    # qdii_e_index_jsl_df = ak.qdii_e_index_jsl()
    # print(qdii_e_index_jsl_df)
    # qdii_e_comm_jsl_df = ak.qdii_e_comm_jsl()
    # print(qdii_e_comm_jsl_df)

    # qdii_a_index_jsl_df = ak.qdii_a_index_jsl()
    # print(qdii_a_index_jsl_df)

    # monitor = ConvertibleBonds()
    # monitor.get_all_cb_info()