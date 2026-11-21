import akshare as ak
import pandas as pd
import numpy as np
import time

# --- 配置 ---
# 推荐去akshare官网注册获取token，填写在这里以提高数据获取成功率和频率
# ak.stock_zh_get_realtime_base['akshare_token'] = "YOUR_AKSHARE_TOKEN"
# 如果没有token，也可以尝试不设置，但可能会有限制

# 宏观指数代码 (例如上证指数，用于获取A股总市值作为参考，虽然不是直接计算PE)
# 我们直接用akshare获取A股的整体PE。
# akshare.stock_zh_index_cons(symbol="000001") # 这个是指数成分股
# akshare.index_zh_a_hist(symbol="000001") # 这个是指数历史数据
# akshare.stock_zh_a_all() # 这个可以获取所有A股代码和名称
# akshare.stock_zh_a_spot_em() # 这个可以获取实时行情，包含PE

# 国债代码，例如：
# 10年期国债收益率，查询akshare文档，通常在宏观经济数据或债券数据部分
# ak.bond_us_yield() # 美债
# ak.bond_cn_yield() # 境内债券收益率
# ak.bond_cn_us_rate() # 境内外债券收益率比较

# 搜索akshare文档，找到十年期国债收益率的接口
# 发现 akshare.bond_cn_yield() 可以获取中国国债收益率曲线
# '国债收益率_10年' 是我们要找的

def get_a_share_avg_pe():
    """
    计算A股全市场的平均市盈率（PE）
    注意：会剔除PE为负数和异常值。
    """
    print("正在获取 A 股全市场市盈率（PE）...")
    try:
        # 获取所有A股的实时行情，包含 PE, PB, 市值等
        # stock_zh_a_spot_em() 返回一个DataFrame，每行为一只股票的实时行情
        all_stocks_realtime = ak.stock_zh_a_spot_em()

        if all_stocks_realtime.empty:
            print("未能获取到任何A股实时行情数据。")
            return None

        # 筛选市盈率 (PE) 数据
        # 1. 确保 PE 不是 NaN (空值)
        # 2. 筛选 PE > 0 的值 (剔除负PE，即亏损的公司)
        valid_pe_df = all_stocks_realtime[
            (all_stocks_realtime["pe"].notna()) &
            (all_stocks_realtime["pe"] > 0)
        ]

        if valid_pe_df.empty:
            print("未找到有效的正市盈率数据。")
            return None

        avg_pe = valid_pe_df["pe"].mean()
        print(f"A股全市场平均市盈率 (PE, 剔除负值): {avg_pe:.4f}")
        return avg_pe

    except Exception as e:
        print(f"获取 A 股全市场市盈率时发生错误: {e}")
        return None

def get_ten_year_treasury_yield():
    """
    获取中国十年期国债收益率
    """
    print("正在获取十年期国债收益率...")
    try:
        # bond_cn_yield() 返回的是一个DataFrame，其中包含不同期限国债的收益率
        # 我们需要找到 '国债收益率_10年' 这一列的最新值
        # 假设是按日期排序的，取最后一行
        treasury_yield_df = ak.bond_cn_yield()

        if treasury_yield_df.empty:
            print("未能获取到中国国债收益率数据。")
            return None

        # 查找 '国债收益率_10年' 列，如果不存在，尝试其他可能的名称
        target_column = None
        if '国债收益率_10年' in treasury_yield_df.columns:
            target_column = '国债收益率_10年'
        elif '10年期国债收益率' in treasury_yield_df.columns: # 备用名称
            target_column = '10年期国债收益率'
        # ... 可以根据实际情况添加更多可能的列名

        if target_column is None:
            print("未找到 '国债收益率_10年' 或类似名称的列。")
            print("可用的列名:", treasury_yield_df.columns.tolist())
            return None

        # 取最新一天的十年期国债收益率
        latest_yield = treasury_yield_df[target_column].iloc[-1]
        print(f"十年期国债收益率: {latest_yield:.4f}")
        return latest_yield

    except Exception as e:
        print(f"获取十年期国债收益率时发生错误: {e}")
        return None

def calculate_graham_market_valuation_indicator(avg_pe, treasury_yield_10y):
    """
    计算格雷厄姆市场估值指标
    """
    if avg_pe is None or treasury_yield_10y is None or treasury_yield_10y == 0:
        print("无法计算格雷厄姆市场估值指标，缺少必要数据或国债收益率为零。")
        return None

    # 盈利收益率 = 1 / PE
    earning_yield = 1 / avg_pe
    print(f"A股全市场盈利收益率: {earning_yield:.4f}")

    # 格雷厄姆指数 = 盈利收益率 / 十年期国债收益率
    graham_indicator = earning_yield / treasury_yield_10y
    return graham_indicator

# --- 主程序 ---
if __name__ == "__main__":
    print("开始计算 A 股格雷厄姆市场估值指标...")

    # 1. 获取 A 股平均市盈率
    avg_pe = get_a_share_avg_pe()
    time.sleep(1) # 暂停一下，避免请求过快

    # 2. 获取十年期国债收益率
    treasury_yield_10y = get_ten_year_treasury_yield()
    time.sleep(1) # 暂停一下

    # 3. 计算格雷厄姆指数
    graham_index_value = calculate_graham_market_valuation_indicator(avg_pe, treasury_yield_10y)

    print("\n--- 计算结果 ---")
    if graham_index_value is not None:
        print(f"A股格雷厄姆市场估值指标: {graham_index_value:.4f}")
        print("\n指标解读（一般情况）：")
        print(" - 指标 > 1: 股市盈利收益率高于国债收益率，可能意味着股市相对吸引人（估值可能偏低或具有安全边际）。")
        print(" - 指标 ≈ 1: 股市盈利收益率与国债收益率相当。")
        print(" - 指标 < 1: 股市盈利收益率低于国债收益率，可能意味着股市估值偏高，风险相对较大。")
        print("注意：此指标仅为参考，实际投资需结合多种因素分析。")
    else:
        print("未能计算出格雷厄姆市场估值指标。")
