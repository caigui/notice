import os
import time
import akshare as ak
import pandas as pd
import numpy as np
import date_utils
import xueqiu_api
import threading
from dingtalk_utils import DingTalkNotifier
import asyncio
import csv
from crawl.qdii_crawl import FundInfoExtractor
import logging
from woody.realtime_netvalue import get_merged_data
from crawl.read_woody_data import read_and_process_woody_data
from crawl.trade_money_fund import trade_money_fund_jsl
from crawl.lof_jsl import lof_stock_jsl,lof_index_jsl
from crawl.qdii_jsl import qdii_e_index_jsl, qdii_e_comm_jsl, qdii_a_index_jsl 
from crawl.crawl_utils import get_jsl_cookie, get_response, post_response, output_excel

class CancellableTask:
    def __init__(self):
        self._is_cancelled = False
        self._last_error = None
        self._last_error_time = 0
    async def loop(self):
        while not self._is_cancelled:
            try:
                await self.run_task()
                await asyncio.sleep(1)  # Important: Await inside the loop
            except asyncio.CancelledError:
                self._is_cancelled = True
                logging.info(f"{self.__class__.__name__}: Task cancelled.")
                break
            except Exception as e:
                # 同一异常 5 分钟内只打一次完整堆栈，避免异常时每轮刷屏
                now = time.time()
                sig = (type(e).__name__, str(e)[:160])
                if sig != getattr(self, '_last_error', None) or \
                        now - getattr(self, '_last_error_time', 0) >= 300:
                    logging.error(f"{self.__class__.__name__}: An error occurred: {e}", exc_info=True)
                    self._last_error, self._last_error_time = sig, now
                await asyncio.sleep(10)
    async def run_task(self):
        """This method has to be implemented by the child class"""
        raise NotImplementedError()
    def cancel(self):
        self._is_cancelled = True

class QDIIQueryStrategy(CancellableTask):
    """定义策略1：QDII套利策略"""

    def __init__(self, target_codes=None, threshold=0.01, sleep_time=3000):
        CancellableTask.__init__(self)
        self.threshold = threshold
        self.sleep_time = sleep_time
        # Dynamically determine the script's directory and construct the file path
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.qdii_file_path = os.path.join(script_dir, "qdii_notice.csv")
        self.target_codes = self.load_target_codes_from_csv(self.qdii_file_path)
        # Fetch only once during initialization
        self.fund_purchase_em_df = ak.fund_purchase_em()
    def load_target_codes_from_csv(self, file_path):
        """从 CSV 文件读取基金代码."""
        target_codes = []
        try:
            with open(file_path, 'r', encoding='utf-8') as csvfile:
                reader = csv.reader(csvfile)
                # 跳过 CSV 文件的表头 (如果存在)
                next(reader, None)
                for row in reader:
                    # 假设基金代码在第一列，并去除空格
                    code = row[0].strip()
                    target_codes.append(code)
        except FileNotFoundError:
            print(f"文件未找到：{file_path}")
            return []
        except Exception as e:
            print(f"读取 CSV 文件时出错: {e}")
            return []
        if not target_codes:
            print("没有加载到基金代码，程序终止")
        else:
            # print(f"加载到的基金代码：{target_codes}")
            print(f"已加载到的基金代码")
        return target_codes
    def process_premium_rate_data(self, df):
        """Process premium rate data based on thresholds and subscription status"""
        condition_codes = df['代码'].isin(self.target_codes)
        
        # Premium rate filtering logic
        condition_premium_high = df['T-1溢价率'] > self.threshold
        condition_premium_low = df['T-1溢价率'] < -self.threshold
        condition_subscription_status = df['申购状态'].str.strip() != '暂停申购'
        
        # Filter data based on premium rate and subscription status
        filtered_df_premium = df[condition_codes & ((condition_premium_high & condition_subscription_status) | condition_premium_low)]
        
        # Update subscription status if needed
        for index, row in filtered_df_premium.iterrows():
            match = self.fund_purchase_em_df[self.fund_purchase_em_df['基金代码'] == row['代码']]
            if not match.empty:
                if row['申购状态'] == "开放申购":
                    filtered_df_premium.loc[index, '申购状态'] = match.iloc[0]['申购状态']
        
        # Filter out rows where 申购状态 is "场内交易"
        filtered_df_premium = filtered_df_premium[filtered_df_premium['申购状态'] != "场内交易"]
        
        return filtered_df_premium
    
    def process_change_percentage_data(self, df):
        """Process change percentage data based on thresholds"""
        condition_codes = df['代码'].isin(self.target_codes)
        
        # Define threshold for change percentage (default X%)
        change_threshold = getattr(self, 'change_threshold', 8) 
        
        # Change percentage filtering logic
        condition_change_high = df['涨幅'] > change_threshold
        condition_change_low = df['涨幅'] < -change_threshold
        
        # Filter data based on change percentage (no subscription status requirement)
        filtered_df_change = df[condition_codes & (condition_change_high | condition_change_low)]
        
        # Filter out rows where 申购状态 is "场内交易"
        filtered_df_change = filtered_df_change[filtered_df_change['申购状态'] != "场内交易"]
        
        return filtered_df_change
    
    async def run_task(self):
        # cookie 只用于提高集思录限流阈值；失败时降级匿名取数，不阻断策略
        try:
            cookie = get_jsl_cookie()
        except Exception as e:
            logging.warning("QDII 策略获取集思录 cookie 失败，降级匿名取数：%s", e)
            cookie = None
        while True:
            if date_utils.is_trading_time():
                print("start qdii_query")
                # 单个数据源异常不应中断整轮：失败则本源返回空表并记一条告警
                def _safe_fetch(name, fn, *args):
                    try:
                        return fn(*args)
                    except Exception as e:
                        logging.warning("QDII 数据源 %s 取数失败，本轮跳过：%s",
                                        name, str(e).splitlines()[0][:140])
                        return []

                qdii_e_index_jsl_df = _safe_fetch("欧美指数", qdii_e_index_jsl, cookie)
                qdii_e_comm_jsl_df = _safe_fetch("欧美商品", qdii_e_comm_jsl, cookie)
                qdii_a_index_jsl_df = _safe_fetch("亚洲指数", qdii_a_index_jsl)
                lof_stock_jsl_df = _safe_fetch("LOF股票", lof_stock_jsl)
                lof_index_jsl_df = _safe_fetch("LOF指数", lof_index_jsl)

                 # 将数据转换为DataFrame并合并
                df_index = pd.DataFrame(qdii_e_index_jsl_df)
                df_comm = pd.DataFrame(qdii_e_comm_jsl_df)
                df_a_index = pd.DataFrame(qdii_a_index_jsl_df)
                lof_stock = pd.DataFrame(lof_stock_jsl_df)
                lof_index = pd.DataFrame(lof_index_jsl_df)

                # Rename '溢价率' column to 'T-1溢价率' in df_a_index
                if '溢价率' in df_a_index.columns:
                    df_a_index.rename(columns={'溢价率': 'T-1溢价率'}, inplace=True)
                    lof_stock.rename(columns={'溢价率': 'T-1溢价率'}, inplace=True)
                    lof_index.rename(columns={'溢价率': 'T-1溢价率'}, inplace=True)

                df = pd.concat([df_index, df_comm, df_a_index,lof_stock,lof_index], ignore_index=True)
                
                # Check if DataFrame is empty or missing required columns
                if df.empty:
                    print("Empty DataFrame received. Skipping processing.")
                    continue
                
                # Check if required columns exist before processing
                required_columns = ['代码', 'T-1溢价率']
                missing_columns = [col for col in required_columns if col not in df.columns]
                if missing_columns:
                    print(f"Missing required columns: {missing_columns}. Skipping processing.")
                    continue
                
                # 将'变化'列中的百分比字符串转换为浮点数（去除百分号并除以100）
                # 部分只更新T-2的数据
                df['T-1溢价率'] = pd.to_numeric(df['T-1溢价率'].str.rstrip('%').replace('-', pd.NA), errors='coerce') / 100
                df['T-1溢价率'] = df['T-1溢价率'].fillna(0).round(3)  # 将NaN替换为0, 保留三位小数
                
                # Handle '涨幅' column if it exists
                if '涨幅' in df.columns:
                    df['涨幅'] = (pd.to_numeric(df['涨幅'].str.rstrip('%'), errors='coerce')).round(4) 
                else:
                    df['涨幅'] = 0.0  # Default value if '涨幅' column doesn't exist

                # 从woody中获取实时溢价，修改成webdirver的方式获取
                print(df[df['代码'] == '501312']['T-1溢价率'])
                real_time_data = read_and_process_woody_data()
                # print('---------TEST----------')
                # print(real_time_data)
                # Add check for empty real_time_data
                if not real_time_data:
                    print("No real-time data available. Skipping updates.")
                else:
                    for code, premium in real_time_data.items():
                        mask = df['代码'] == code  # Match fund code
                        df.loc[mask, 'T-1溢价率'] = premium  # Update T-1溢价率
                # print(df[df['代码'] == '161226']['T-1溢价率'])
                # print(df[df['代码'] == '161226']['申购状态'])
                #TODO 162411的数据提醒失败，需要处理
                # 通过 isin() 方法动态生成条件
                df.to_csv("df.txt", sep='\t', index=False, encoding='utf-8')
                
                # Process both premium rate and change percentage data using the shared df
                filtered_df_premium = self.process_premium_rate_data(df)
                filtered_df_change = self.process_change_percentage_data(df)
                
                # Combine both filtered results
                filtered_df = pd.concat([filtered_df_premium, filtered_df_change]).drop_duplicates().reset_index(drop=True)
                
                if filtered_df.shape[0] > 0:
                    filtered_df = filtered_df.copy()
                    filtered_df.loc[:, 'sort_priority'] = filtered_df['申购状态'].apply(lambda x: 0 if x.startswith('限') else 1)
                    filtered_df = filtered_df.sort_values(by='sort_priority').drop(columns=['sort_priority'])
                    
                    # Updated table header to include 涨幅(%) column
                    table_header =  "| 代码 | T-1溢价率 | 涨幅(%) | 限购金额| 申购状态| 成交（万元）| \n\n "
                    table_header += "|------|----------|---------|---------|--------|------------|\n\n "
                    table_rows = ""
                    for index, row in filtered_df.iterrows():
                        code = row['代码']
                        extractor = FundInfoExtractor()
                        fund_info = extractor.get_fund_purchase_info(code)
                        limit_amount = fund_info.get('limit_amount','无限制') if fund_info else '未知' # handle None
                        status = row['申购状态']
                        volume = row['成交']
                        # Added 涨幅(%) to the table row
                        table_rows += f"| {code} | {row['T-1溢价率']} | {row['涨幅']} | {limit_amount} | {status} | {volume} |\n\n "

                    # Define threshold for change percentage (default 5%)
                    change_threshold = getattr(self, 'change_threshold', 8)  # Default to 5 if not set
                    message = f"QDII T-1溢价率大于{self.threshold * 100}%或涨幅超过{change_threshold}%： \n\n " + table_header + table_rows
                    DingTalkNotifier().send_alert(message, "QDII套利提示")

            await asyncio.sleep(self.sleep_time)


class EFTQueryStrategy(CancellableTask):
    """定义策略2：ETF套利策略 TODO 这个是否可以删除，没有用"""

    def __init__(self, target_code=None, threshold=0.0001, sleep_time=3000):
        CancellableTask.__init__(self)
        # Dynamically determine the script's directory and construct the file path
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.file_path = os.path.join(script_dir, "currency_notice.csv")
        self.target_codes = self.load_target_codes_from_csv(self.file_path)
        self.threshold = threshold
        self.sleep_time = sleep_time

        
    def load_target_codes_from_csv(self,file_path):
        """从 CSV 文件读取基金代码."""
        target_codes = []
        try:
            with open(file_path, 'r', encoding='utf-8') as csvfile:
                reader = csv.reader(csvfile)
                # 跳过 CSV 文件的表头 (如果存在)
                next(reader, None)
                for row in reader:
                    # 假设基金代码在第一列，并去除空格
                    code = row[0].strip()
                    target_codes.append(code)
        except FileNotFoundError:
            print(f"文件未找到：{file_path}")
            return []
        except Exception as e:
            print(f"读取 CSV 文件时出错: {e}")
            return []
        if not target_codes:
         print("没有加载到基金代码，程序终止")
        else:
            # print(f"加载到的基金代码：{target_codes}")
            print(f"已加载到的基金代码")
        return target_codes

    async def run_task(self):
        while True:
            if date_utils.is_trading_time():
                print("start eft_query")
                fund_etf_spot_em_df = ak.fund_etf_spot_ths()

                # 将数据转换为DataFrame
                df = pd.DataFrame(fund_etf_spot_em_df)

                # 查找目标基金代码
                condition1 = df['基金代码'].isin(self.target_codes)

                filtered_df = df[condition1].copy()

                # 雪球获取当前价格
                shares_list = [{'code': 'SH'+code, 'price': '0', 'quantity': '0'} for code in self.target_codes]
                # TODO 单位净值计算不准确，需要调整
                combined_message = ""
                for n in xueqiu_api.xueqiu_analysis_return(xueqiu_api.xueqiu_api(shares_list)):
                    # Match rows in filtered_df based on '基金代码' and update 'current' column
                    for index, row in filtered_df.iterrows():
                        if n['code'] == 'SH' + row['基金代码']:
                            filtered_df.loc[index, 'current'] = n['current']  # Insert 'current' value using .loc
                # 使用布尔索引找到匹配的行
                matched_row = filtered_df[abs(filtered_df['当前-单位净值'] - n['current']) > self.threshold]
                # print(matched_row)
                if matched_row.shape[0] > 0:
                    table_header =  "| 基金代码  | 溢价(/万) | \n\n "
                    table_header += "|-----------|----------| \n\n "
                    table_rows = ""
                    unique_messages = set()  # Set to store unique messages
                    for index, row in matched_row.iterrows():
                        premium = round(n['current'] - row['当前-单位净值'], 4)
                        message_row = f"| {row['基金代码']} | {premium} \n\n "
                        if message_row not in unique_messages:  # Check for uniqueness
                            unique_messages.add(message_row)
                            table_rows += message_row
                    if table_rows:  # Only append if there are rows
                        message = f"溢价率大于0.01%： \n\n " + table_header + table_rows
                        combined_message += message + "\n\n"
                if combined_message:
                    title = "EFT套利提示"
                    DingTalkNotifier().send_alert(combined_message, title)

            await asyncio.sleep(self.sleep_time)


class MoneyFundQueryStrategy(CancellableTask):
    """定义策略3：货币基金套利策略"""

    def __init__(self, threshold_premium=0.003, threshold_annualized=1.5, sleep_time=3000):
        CancellableTask.__init__(self)
        self.threshold_premium = threshold_premium
        self.threshold_annualized = threshold_annualized
        self.sleep_time = sleep_time

    async def run_task(self):
        while True:
            if date_utils.is_trading_time():
                print("start money_fund_query")
                # 获取货币基金数据
                money_fund_df = trade_money_fund_jsl()

                # 筛选满足条件的数据
                condition_premium = money_fund_df['溢价'] >= self.threshold_premium
                condition_annualized_buy_sell = money_fund_df['买入赎回年化'] > self.threshold_annualized
                condition_annualized_sell_buy = money_fund_df['申购卖出年化'] > self.threshold_annualized

                filtered_df = money_fund_df[condition_premium | condition_annualized_buy_sell | condition_annualized_sell_buy]

                if filtered_df.shape[0] > 0:
                    table_header =  "| 代码 | 名称 | 溢价 | 买入赎回年化 | 申购卖出年化 | 到账日 | 规模 |\n\n"
                    table_header += "|------|------|-----|-------------|-------------|--------|-----|\n\n"
                    table_rows = ""
                    for index, row in filtered_df.iterrows():
                        table_rows += f"| {row['代码']} | {row['名称']} | {row['溢价']} | {row['买入赎回年化']} | {row['申购卖出年化']} | {row['到账日']} | {row['规模']} |\n\n"

                    message = f"货币基金溢价/收益率异常：\n\n{table_header}{table_rows}"
                    DingTalkNotifier().send_alert(message, "场内货基套利提示")

            await asyncio.sleep(self.sleep_time)

# 修改 QdiiStrategyExecutor 类以支持新策略
class QdiiStrategyExecutor:
    def __init__(self):
        self.qdii_strategy = QDIIQueryStrategy()
        self.eft_strategy = EFTQueryStrategy()
        self.money_fund_strategy = MoneyFundQueryStrategy()  # 新增货币基金策略

    async def start(self):
        task1 = asyncio.create_task(self.qdii_strategy.loop())
        task2 = asyncio.create_task(self.eft_strategy.loop())
        task3 = asyncio.create_task(self.money_fund_strategy.loop())  # 启动货币基金策略
        return task1, task2, task3

    def cancel(self):
        self.qdii_strategy.cancel()
        self.eft_strategy.cancel()
        self.money_fund_strategy.cancel()  # 取消货币基金策略

# 修改 main 函数以支持新策略
async def main():
    executor = QdiiStrategyExecutor()
    task1, task2, task3 = await executor.start()
    async def shutdown_signal_handler(signum, frame):
        executor.cancel()
        tasks = asyncio.all_tasks()
        for task in tasks:
            task.cancel()
        await asyncio.sleep(1)
    await asyncio.gather(task1, task2, task3)

if __name__ == "__main__":
    asyncio.run(main())
