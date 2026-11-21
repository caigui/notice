import sys
import os
# 获取当前脚本所在目录的上级目录
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
# 将上级目录添加到 sys.path
sys.path.append(parent_dir)

import time
from globalVar import log
from stock_info import StockInfo
from wechatPublicCountSendMessage import SendMessage
from stock_config import StockConfig
import requests
from dingtalk_utils import DingTalkNotifier
import asyncio
import akshare as ak
import pandas as pd

class StockUpMonitor:
    def __init__(self):
        self.notifier = DingTalkNotifier()
        self.stockInfo = StockInfo()  # 初始化 stockInfo
        self.last_notified_time = {}  # 记录每只股票最后一次提醒的时间

    def check_current_price(self):
        """检查所有股票的现价是否达到要提醒的价位."""
        print("Checking current price...")
        title = "股票价格波动提醒"
        
        for data in self.stockInfo.stockInfo:
            stock_code = data['代码']
            current_price = data['最新价']
            change_percent = data['涨跌幅']
            limit_up = data['limit_up']
            speed = data['speed']
            # 判断是否满足条件，涨停价的90%
            if change_percent >= 0.9 * limit_up and speed > 0.1 and self.should_notify(stock_code):
                message = f"股票 {stock_code} 涨幅 {change_percent}%，涨停限制 {limit_up}%，涨速 {speed}%/秒"
                self.notifier.send_alert(message, title)
                self.last_notified_time[stock_code] = time.time()

    def should_notify(self, stock_code):
        """检查是否应该发送提醒"""
        last_notified = self.last_notified_time.get(stock_code, 0)
        current_time = time.time()
        return current_time - last_notified >= 300  # 5分钟 = 300秒

    async def loop_check(self, interval_seconds=300, max_retries=3):
        """异步循环检查股票价格，直到达到指定的告警条件"""
        retry_count = 0
        while True:
            try:
                # 获取最新的股票信息
                self.stockInfo.get_all_stock_info()
                self.check_current_price()  # 检查股票价格
                retry_count = 0  # 如果成功，重置重试计数器
                log.logger.info("Stock info fetched and price checked successfully.")
            except requests.RequestException as e:
                retry_count += 1
                log.logger.error(f"Data fetching failed, attempt {retry_count}: {e}")
                if retry_count >= max_retries:
                    log.logger.critical("Network request failed multiple times, exiting the program.")
                    break  # 达到最大重试次数时退出循环
            await asyncio.sleep(interval_seconds)  # 使用 asyncio.sleep 替代 time.sleep

# StockInfo类已经定义
class StockInfo:
    def __init__(self):
        self.stockInfo = []

    def get_all_stock_info(self):
        # 获取沪深北股票信息
        stock_zh_a_spot_em_df = ak.stock_zh_a_spot_em()
        print(stock_zh_a_spot_em_df)
        # 合并数据
        combined_df = pd.DataFrame(stock_zh_a_spot_em_df)

        # combined_df = pd.concat([stock_zh_a_spot_df, stock_zh_b_spot_df, stock_zh_index_spot_df], ignore_index=True)

        # 计算涨停限制
        combined_df['limit_up'] = combined_df['涨跌幅'].apply(lambda x: 10 if x < 10 else 20)
        combined_df['speed'] = combined_df['涨速']

        # 选择需要的列
        self.stockInfo = combined_df[['代码', '名称', '最新价', '涨跌幅', 'limit_up', 'speed']].to_dict(orient='records')

# Main function to start the monitoring
if __name__ == "__main__":
    monitor = StockUpMonitor()
    asyncio.run(monitor.loop_check())