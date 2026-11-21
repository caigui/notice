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

class ConvertibleBondsMonitor:
    def __init__(self):
        self.notifier = DingTalkNotifier()
        self.cbInfo = ConvertibleBonds()  # 初始化 cbInfo
        self.last_notified_time = {}  # 记录每只股票最后一次提醒的时间
        # 溢价率当日波动大于+-5
        self.volatility_threshold = 5
        self.forced_redemption_data = ak.bond_cb_redeem_jsl()

    def check_current_price(self):
        """检查所有股票的现价是否达到要提醒的价位."""
        log.logger.info("Checking current price...")
        title = "债券价格波动±15%"
        
        for data in self.cbInfo.cbInfo:
            stock_code = data['symbol']
            change_percent = data['changepercent']

            if (change_percent > 15 or change_percent < -15) and self.should_notify(stock_code):
                message =f"Stock {stock_code} has a change percent of {change_percent}%"
                try:
                    self.notifier.send_alert(message, title)
                    log.logger.info(f"Successfully sent alert for {stock_code}")
                except Exception as e:
                    log.logger.error(f"Failed to send alert for {stock_code}: {str(e)}")
                self.last_notified_time[stock_code] = time.time()

    def check_conversion_premium_ratio_change(self):
        """检查所有股票的转换溢价率是否达到要提醒的价位."""
        log.logger.info("Checking conversion premium ratio change...")
        title = "可转债溢价率波动预警"

        bond_data = self.cbInfo.cbCprInfo  # Get the data from cbInfo
        if not bond_data:
            log.logger.info("No convertible bonds found to monitor.")
            return

        for data in bond_data:
            stock_code = data['转债代码']
            change_percent = data['changepercent']  # Use the calculated change percent

            if abs(change_percent) > self.volatility_threshold and self.should_notify(stock_code):
                message = f"可转债 {stock_code}  溢价波动 {change_percent:.2f}%"
                try:
                    self.notifier.send_alert(message, title)
                    log.logger.info(f"Successfully sent alert for {stock_code}")
                except Exception as e:
                    log.logger.error(f"Failed to send alert for {stock_code}: {str(e)}")
                self.last_notified_time[stock_code] = time.time()

    def check_negative_premium_rate(self):
        """检查所有可转债的溢价率是否为负并提醒."""
        log.logger.info("Checking for negative premium rates...")
        title = "可转债溢价率为负预警"

        bond_data = self.cbInfo.cbCprInfo  # Get the data from cbInfo
        if not bond_data:
            log.logger.info("No convertible bonds found to monitor.")
            return

        for data in bond_data:
            stock_code = data['转债代码']
            premium_rate = data['转股溢价率']

            # Check if the bond is in the forced redemption data
            forced_redemption_status = None
            if '转债代码' in self.forced_redemption_data.columns:
                matching_row = self.forced_redemption_data[self.forced_redemption_data['转债代码'] == stock_code]
                if not matching_row.empty:
                    forced_redemption_status = matching_row.iloc[0]['强赎状态']
            print(forced_redemption_status)
            # Apply the new condition based on forced redemption status
            if forced_redemption_status == "已公告强赎":
                alert_condition = premium_rate < -0.5
            else:
                alert_condition = premium_rate < 0

            if alert_condition and self.should_notify(stock_code):
                message = f"可转债 {stock_code} 溢价率为负: {premium_rate:.2f}%"
                try:
                    self.notifier.send_alert(message, title)
                    log.logger.info(f"Successfully sent alert for {stock_code}")
                except Exception as e:
                    log.logger.error(f"Failed to send alert for {stock_code}: {str(e)}")
                self.last_notified_time[stock_code] = time.time()

    def should_notify(self, stock_code):
        """检查是否应该发送提醒"""
        last_notified = self.last_notified_time.get(stock_code, 0)
        current_time = time.time()
        return current_time - last_notified >= 150  # 5分钟 = 300秒

    async def loop_check(self, interval_seconds=300, max_retries=3):
        """异步循环检查CB价格，直到达到指定的告警条件"""
        retry_count = 0
        while True:
            try:
                # # 获取最新的CB信息
                # self.cbInfo.get_all_cb_info()
                # self.check_current_price()  # 检查CB价格波动
                # # 获取最新的CPR信息
                # self.cbInfo.get_cb_cpr_info()
                # self.check_conversion_premium_ratio_change()  # 检查溢价率波动
                self.check_negative_premium_rate()  # 检查溢价率为负的情况
                retry_count = 0  # 如果成功，重置重试计数器
                log.logger.info("Stock info fetched and price checked successfully.")
            except requests.RequestException as e:
                retry_count += 1
                log.logger.error(f"Data fetching failed, attempt {retry_count}: {e}")
                if retry_count >= max_retries:
                    log.logger.critical("Network request failed multiple times, exiting the program.")
                    break  # 达到最大重试次数时退出循环
            await asyncio.sleep(interval_seconds)  # 使用 asyncio.sleep 替代 time.sleep

# ConvertibleBonds类已经定义
class ConvertibleBonds:
    def __init__(self):
        self.cbInfo = []
        self.cbCprInfo = []
        #溢价率 20
        self.discount_threshold = 20
        self.cbCprBaseline = None

    def get_all_cb_info(self):
        # 这里应该是获取所有股票信息的逻辑
        # 使用 akshare 获取数据
        bond_zh_hs_cov_spot_df = ak.bond_zh_hs_cov_spot()
        bond_zh_hs_cov_spot_df['changepercent'] = bond_zh_hs_cov_spot_df['changepercent'].astype(float)
        self.cbInfo = bond_zh_hs_cov_spot_df.to_dict(orient='records')

    def get_cb_cpr_info(self):
        # 使用 akshare 获取数据
        try:
            bond_cov_comparison_df = ak.bond_cov_comparison()
            bond_cov_comparison_df['转股溢价率'] = bond_cov_comparison_df['转股溢价率'].astype(float)
            current_data = bond_cov_comparison_df[bond_cov_comparison_df['转股溢价率'] < self.discount_threshold].copy()
            # print(current_data)

            # If baseline doesn't exist, store current data as baseline
            if self.cbCprBaseline is None:
                self.cbCprBaseline = current_data.to_dict(orient='records')
                self.cbCprInfo = current_data.to_dict(orient='records')
                # Initialize change percent for baseline data
                for item in self.cbCprInfo:
                    item['changepercent'] = 0.0
                return

            # Calculate change percent compared to baseline
            # First, convert current_data to a list of dictionaries
            current_data_list = current_data.to_dict(orient='records')

            # Perform the merge manually
            merged_data = []
            for current_item in current_data_list:
                for baseline_item in self.cbCprBaseline:
                    if current_item['转债代码'] == baseline_item['转债代码']:
                        changepercent = (
                            (current_item['转股溢价率'] - baseline_item['转股溢价率'])
                        )
                        merged_item = current_item.copy()
                        merged_item['changepercent'] = changepercent
                        merged_data.append(merged_item)
                        break

            self.cbCprInfo = merged_data
            # print(self.cbCprInfo)

        except Exception as e:
            log.logger.error(f"Error fetching or processing convertible bond data: {e}")
            self.cbCprInfo = []  # Reset to an empty list on error.

# Main function to start the monitoring
if __name__ == "__main__":
    monitor = ConvertibleBondsMonitor()
    asyncio.run(monitor.loop_check())

