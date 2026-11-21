import time
from globalVar import log
from stock_info import StockInfo
from wechatPublicCountSendMessage import SendMessage
from stock_config import StockConfig
import requests
from dingtalk_utils import DingTalkNotifier
import asyncio
import date_utils

"""股票监控类,达到设定价格进行提醒"""
class StockMonitor:
    def __init__(self, interactive_prompt):
        """初始化股票监控类"""
        self.interactive_prompt = interactive_prompt
        self.alert_price = interactive_prompt.get_stock_id_and_price()
        self.stockInfo = StockInfo(interactive_prompt.get_stock_exchange(), interactive_prompt.get_se_and_stock_id())
        self.notifier = DingTalkNotifier()
        self.token_time = int(str(time.time()).split(".")[0])  # 保存公众号token获取时间
    def check_current_price(self):
        """检查所有股票的现价是否达到要提醒的价位."""
        print("Checking current price...")
        # print(self.stockInfo.stock_data)
        for data in self.stockInfo.stock_data:
            # print(data)
            stock_code = data[1]
            current_price = data[2]
            #print(f"Stock code: {stock_code}, Current price: {current_price}")
            
            # Initialize the alert count and last alert time if not set
            self.alert_price[stock_code].setdefault('alert_count', 0)
            self.alert_price[stock_code].setdefault('last_alert_time', 0)  # 新增 last_alert_time
            
            # Skip if stock is not in the alert price list
            if stock_code not in self.alert_price:
                continue
            
            # Skip if the alert count is already 1
            if self.alert_price[stock_code]['alert_count'] >= 1:
                continue

            # Get the min and max alert price for the stock
            price_min = self.alert_price[stock_code]['price_min']
            price_max = self.alert_price[stock_code]['price_max']
            
            # Determine if the current price exceeds the alert range
            if current_price <= price_min:
                alert_type = "below"
            elif current_price >= price_max:
                alert_type = "above"
            else:
                continue  # No alert if within the range
            
            # Get the current timestamp
            current_time = time.time()
            last_alert_time = self.alert_price[stock_code]['last_alert_time']

            # Check if 5 minutes have passed since the last alert
            if current_time - last_alert_time < 300:  # 300 seconds = 5 minutes
                continue  # Skip if less than 5 minutes passed since last alert

            # Send alert if conditions are met
            message = f"Stock {stock_code} triggered an alert! Current price: {current_price}, Alert condition: {alert_type}"
            print(message)
            self.alert_price[stock_code]['alert_count'] += 1
            log.logger.info(f"Stock {stock_code} alert triggered, price: {current_price}, alert count: {self.alert_price[stock_code]['alert_count']}")
            
            # Send the alert via DingTalk
            self.notifier.send_alert(message, "Price Alert")

            # Update last alert time
            self.alert_price[stock_code]['last_alert_time'] = current_time

    async def loop_check(self, interval_seconds=300, max_retries=3):
        """异步循环检查股票价格，直到达到指定的告警条件"""
        retry_count = 0
        while True:
            if date_utils.is_trading_time():
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

# Main function to start the monitoring
if __name__ == "__main__":
    interactive_prompt = StockConfig()
    stock_monitor = StockMonitor(interactive_prompt)

    # Start checking the stock prices in a loop
    asyncio.run(stock_monitor.loop_check(interval_seconds=300))  # Check every 5 minutes (300 seconds)
