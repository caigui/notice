import akshare as ak
import pandas as pd
import numpy as np
from bs4 import BeautifulSoup
import requests
import time

# --- 配置 ---
# 核心股票代码 (以茅台为例，用于计算比价)
MAOTAI_CODE = "600519"
SECOND_CODE = "688256"
# A股指数代码 (例如上证指数)
INDEX_SH = "sh000001"

# --- 函数定义 ---

def get_all_a_stock_basic_info():
    """
    获取全A股的基本信息（用于计算PB, PE, 换手率等）
    """
    all_stocks_data = []
    try:
        # 获取今日行情
        realtime_data = ak.stock_zh_a_spot_em()
        all_stocks_data = realtime_data.to_records(index=False)
    except Exception as e:
        # print(f"获取 {code} 数据时出错: {e}")
        pass # 忽略获取个股数据时的错误

    if all_stocks_data is None :
        print("未能获取到任何股票的交易数据。请检查AKSHARE_TOKEN或网络连接。")
        return pd.DataFrame()

    return pd.DataFrame(all_stocks_data)


def get_second_highest_stock_ratio(stock_data=None):
    """Fetch the ratio of the second-highest stock price to Maotai's price."""
      # 15. 第二高价股与茅台比价 (需要额外获取第二高价股)
    # 此处仅作为演示，实际需要单独计算
    second_highest_price = None
    maotai_price = None
    try:
        # 获取茅台价格
        # stock_zh_a_spot_em_df = ak.stock_zh_a_spot_em()
        maotai_data = stock_data[stock_data['代码'] == MAOTAI_CODE]
        if not maotai_data.empty:
            maotai_price = maotai_data["最新价"].values[0]
        # 获取第二高价股
        second_data = stock_data[stock_data['代码'] == SECOND_CODE]
        if not second_data.empty:
            second_highest_price = second_data["最新价"].values[0]
    except Exception as e:
        print(f"获取第二高价股或茅台价格时发生错误: {e}")
    maotai_ratio = None
    if second_highest_price is not None and maotai_price is not None and maotai_price > 0:
        maotai_ratio = round(second_highest_price / maotai_price, 2)
    # Placeholder: Implement stock price comparison logic
    return maotai_ratio

def calculate_ma20_reversal(stock_data):
    """
    计算MA20是否反转
    通过获取个股历史数据，计算20日均线并判断是否出现反转信号
    """
    try:
        # 以茅台为例计算MA20反转信号
        # 获取历史数据
        stock_hist = ak.stock_zh_a_hist(symbol=MAOTAI_CODE, period="daily", adjust="qfq")
        if len(stock_hist) < 21:  # 需要至少21天数据来计算20日均线及判断趋势
            return "数据不足"
        
        # 计算20日均线
        stock_hist['MA20'] = stock_hist['收盘'].rolling(window=20).mean()
        
        # 简单判断：如果最近一天MA20大于前一日，且前一日小于前两日，则判断为反转向上
        latest_ma20 = stock_hist['MA20'].iloc[-1]
        prev_ma20 = stock_hist['MA20'].iloc[-2]
        prev2_ma20 = stock_hist['MA20'].iloc[-3]
        
        if latest_ma20 > prev_ma20 and prev_ma20 < prev2_ma20:
            return "反转向上"
        elif latest_ma20 < prev_ma20 and prev_ma20 > prev2_ma20:
            return "反转向下"
        else:
            return "无明显反转"
            
    except Exception as e:
        print(f"计算MA20反转时出错: {e}")
        return "计算失败"

def calculate_margin_financing_indicators():
    """
    获取融资融券数据，计算融资余额增长额和交易额占比
    """
    try:
        # 获取融资融券数据
        stock_margin_account_info_df = ak.stock_margin_account_info()
        
        if len(stock_margin_account_info_df) < 2:
            return {
                "融资余额": None,
                "融资余额增长额": None,
                "融资交易额占比": None
            }
        
        # 获取最新两日数据
        latest_row = stock_margin_account_info_df.iloc[-1]
        previous_row = stock_margin_account_info_df.iloc[-2]
        
        # 融资余额 (最新一日的融资余额)
        margin_balance = latest_row['融资余额']
        
        # 融资余额增长额 (最新一日 - 前一日)
        margin_balance_growth = latest_row['融资余额'] - previous_row['融资余额']
        
        # 融资交易额占比 (融资买入额 / 成交金额)
        margin_trading_ratio = None
 
        return {
            "融资余额": margin_balance,
            "融资余额增长额": margin_balance_growth,
            "融资交易额占比": margin_trading_ratio
        }
    except Exception as e:
        print(f"获取融资融券数据时出错: {e}")
        return {
            "融资余额": None,
            "融资余额增长额": None,
            "融资交易额占比": None
        }

def get_panic_index():
    """
    获取恐慌指数 (VIX)
    """
    try:
        # TODO 获取VIX指数数据
        vix_data = ak.index_us_stock_sina(symbol="inx")
        if not vix_data.empty:
            # 获取最新的VIX值
            latest_vix = vix_data.iloc[-1]['close']
            return round(latest_vix, 2)
    except Exception as e:
        print(f"获取恐慌指数时出错: {e}")
    return None

def calculate_market_wide_indicators(all_stocks_df):
    """
    根据全A股数据计算市场广泛指标
    """
    if all_stocks_df.empty:
        return {
            "全A PB (平均)": None,
            "全A PE (平均)": None,
            "总成交额 (加总, 亿)": None,
            "日换手率 (平均)": None,
            "第二高价股与茅台比价": None,
            "MACD/RSI背离 (暂未实现)": None,
            "MA20是否反转": None,
            "ADL指数 (暂未实现)": None,
            "新基金热度 (暂未实现)": None,
            "恐慌指数 (暂未实现)": None,
            "散户开户数 (暂未实现)": None,
            "百度/微信 牛市、股票指数 (暂未实现)": None,
            "政策是否收紧股市 (暂未实现)": None,
        }

    # 1. 全A的PB (平均值)
    # 过滤掉PB为0或NaN的值
    valid_pb = all_stocks_df[all_stocks_df["市净率"].notna() & (all_stocks_df["市净率"] > 0)]
    avg_pb = valid_pb["市净率"].mean() if not valid_pb.empty else None
    if avg_pb is not None:
        avg_pb = round(avg_pb, 2)

    # 2. 全A的PE (平均值)
    # 过滤掉PE为0或NaN或负值的值
    valid_pe = all_stocks_df[all_stocks_df["市盈率-动态"].notna() & (all_stocks_df["市盈率-动态"] > 0)]
    avg_pe = valid_pe["市盈率-动态"].mean() if not valid_pe.empty else None
    if avg_pe is not None:
        avg_pe = round(avg_pe, 2)

    # 5. 总成交额 (加总) - 修改为亿单位，整数
    total_turnover_amount = all_stocks_df["成交额"].sum() if not all_stocks_df.empty else None
    if total_turnover_amount is not None:
        total_turnover_amount = int(total_turnover_amount / 100000000)  # 从万转换为亿，并取整数

    # 4. 日换手率 (平均值)
    valid_turnover = all_stocks_df[all_stocks_df["换手率"].notna()]
    avg_turnover_rate = valid_pe["换手率"].mean() if not valid_pe.empty else None
    if avg_turnover_rate is not None:
        avg_turnover_rate = round(avg_turnover_rate, 2)

    # 巴菲特指标: 总市值/GDP (使用固定GDP值)
    # 2025年预测2024GDP*1.05 (可根据实际情况调整)
    GDP_FIXED_VALUE = 1416500000000 
    total_market_cap = all_stocks_df["总市值"].sum() if not all_stocks_df.empty else None
    buffett_indicator = None
    if total_market_cap is not None and GDP_FIXED_VALUE > 0:
        buffett_indicator = round(total_market_cap / GDP_FIXED_VALUE, 2)
  
    # 获取融资融券相关指标
    # 将total_turnover_amount传递给融资融券计算函数
    margin_indicators = calculate_margin_financing_indicators()
    
    # 手动计算融资交易额占比，使用total_turnover_amount
    if len(ak.stock_margin_account_info()) > 0:
        latest_margin_data = ak.stock_margin_account_info().iloc[-1]
        margin_trading_ratio = None
        if total_turnover_amount is not None and total_turnover_amount > 0:
            # 将亿单位转换回原始单位进行计算
            margin_trading_ratio = round(latest_margin_data['融资买入额'] / total_turnover_amount, 2)
        
        margin_indicators["融资交易额占比"] = margin_trading_ratio
  
    # 对融资余额和融资余额增长额保留两位小数
    if margin_indicators["融资余额"] is not None:
        margin_indicators["融资余额"] = round(margin_indicators["融资余额"], 0)
    if margin_indicators["融资余额增长额"] is not None:
        margin_indicators["融资余额增长额"] = round(margin_indicators["融资余额增长额"], 0)
        
    # 获取大盘拥挤度数据
    market_congestion = None
    try:
        stock_a_congestion_lg_df = ak.stock_a_congestion_lg()
        if not stock_a_congestion_lg_df.empty:
            # 取最后一条的congestion数据
            market_congestion = stock_a_congestion_lg_df.iloc[-1]['congestion']
    except Exception as e:
        print(f"获取大盘拥挤度数据时出错: {e}")
  
    return {
        "全A PB (平均)": avg_pb,
        "全A PE (平均)": avg_pe,
        "总成交额 (加总, 亿)": total_turnover_amount,
        "日换手率 (平均)": avg_turnover_rate,
        "巴菲特指标（%）": buffett_indicator,
        "融资余额（亿）": margin_indicators["融资余额"],
        "融资余额增长额（亿）": margin_indicators["融资余额增长额"],
        "融资/交易额占比": margin_indicators["融资交易额占比"],
        "大盘拥挤度（50%过热）": market_congestion,  # 添加大盘拥挤度指标
        "MA20是否反转": calculate_ma20_reversal(all_stocks_df),  # 实现MA20反转计算
        "第二高价股与茅台比价": get_second_highest_stock_ratio(all_stocks_df),
        "北向和产业资本是否流出": "暂未实现", # 需要专业金融数据API
        "MACD/RSI背离": "暂未实现", # 需要自行计算
        "ADL指数": "暂未实现", # 需要自行计算
        "新基金热度": "暂未实现", # 需要专业数据源
        "恐慌指数": get_panic_index(), # 使用期货VIX实现恐慌指数
        "散户开户数": "暂未实现", # 需要专业数据源
        "百度/微信 牛市、股票指数": "暂未实现", # 需结合搜索和AI判断，非直接指标
        "政策是否收紧股市": "暂未实现" # 需结合政策分析，非直接指标
    }

# --- 主程序 ---
if __name__ == "__main__":
    print("开始收集A股市场指标...")

    # 1. 获取全A股交易数据
    all_stocks_df = get_all_a_stock_basic_info()

    # 2. 计算市场广泛指标
    market_wide_indicators = calculate_market_wide_indicators(all_stocks_df)

    # 3. 打印表格输出
    print("\n--- A股市场关键指标 ---")
    # 将字典转换为DataFrame以便漂亮地打印
    output_df = pd.DataFrame(list(market_wide_indicators.items()), columns=["指标名称", "数值"])
    print(output_df.to_string(index=False))
