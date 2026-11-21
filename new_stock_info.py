import requests
import json
from datetime import datetime, timedelta
from dingtalk_utils import DingTalkNotifier
import date_utils
import asyncio

class NewStockNotifier:
    """投资提醒类，用于监控新债和新股的打新提醒"""

    def __init__(self):
        """初始化类实例
        Args:
            dingtalk_webhook (str): 钉钉 Webhook 地址
            dingtalk_secret (str): 钉钉密钥
        """
        self.notifier = DingTalkNotifier()
        self.request_params = {
            "headers": {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/83.0.4103.97 Safari/537.36"
                )
            },
            "timeout": 10,
        }

    def fetch_data(self, url):
        """通用方法：从指定URL获取JSON数据."""
        try:
            response = requests.get(url, **self.request_params)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, json.JSONDecodeError) as e:
            print(f"请求或解析数据失败: {e}")
            return None

    def get_today_bonds(self):
        """获取今日新债申购信息并发送提醒."""
        if not date_utils.is_notification_time():
            return
        url = "http://data.hexin.cn/ipo/bond/cate/info/"
        data = self.fetch_data(url)

        if not data:
            print("未获取到新债数据")
            return

        today = datetime.now()
        future_date = today + timedelta(days=5)

        message = ""
        for bond in data:
            sg_date_str = bond["sgDate"]
            try:
                sg_date = datetime.strptime(sg_date_str, "%Y-%m-%d")
            except ValueError:
                print(f"无法解析日期: {sg_date_str}")
                continue

            # 检查申购日期是否在未来五天内
            if today <= sg_date <= future_date:
                message += f"新债: {bond['zqName']}, 申购日期: {bond['sgDate']}, 发行量: {bond['issue']}亿 \n\n "

        if message:
            self.send_msg(message, "新债提醒")
        else:
            print("今日没有新债申购机会")

    def get_today_stocks(self):
        """获取今日新股申购信息并发送提醒."""
        if not date_utils.is_notification_time():
            return
        url = "https://www.jisilu.cn/data/new_stock/apply/?___jsl=LST___t="
        data = self.fetch_data(url)

        if not data:
            print("未获取到新股数据")
            return

        today = datetime.now() + timedelta(days=-1)
        future_date = today + timedelta(days=5)
        message = ""
        for bond in data.get("rows", []):
            stock_info = bond["cell"]
            
            apply_date_str = self._extract_date(stock_info["apply_dt2"])
            try:
                apply_date = datetime.strptime(apply_date_str, "%Y-%m-%d")
            except ValueError:
                print(f"无法解析日期: {apply_date_str}")
                continue
            # apply_date_str = self._extract_date(stock_info["apply_dt"])
            # apply_date = self._parse_date(apply_date_str)
            # if not apply_date:
            #     print(f"无法解析日期: {apply_date_str}")
            #     continue

            # 检查申购日期是否在未来五天内
            if today <= apply_date <= future_date:
                message += (
                    f"新股: {stock_info['stock_nm']}, "
                    f"申购日期: {apply_date.strftime('%Y-%m-%d')}, "
                    f"代码: {self._extract_code(stock_info['apply_cd'])} \n\n "
                )

        if message:
            self.send_msg(message, "新股提醒")
        else:
            print("今日没有新股申购机会")

    def _parse_date(self, date_str):
        """解析申购日期（支持 01-17(周三) 格式）"""
        try:
            month_day = date_str.split('(')[0]  # 提取 '01-17' 部分
            current_year = datetime.now().year
            return datetime.strptime(f"{current_year}-{month_day}", "%Y-%m-%d")
        except ValueError:
            return None

    def _extract_date(self, date_field):
        """提取申购日期（支持 HTML 格式处理）"""
        if date_field.startswith("<span"):
            return date_field[33:42]
        return date_field

    def _extract_code(self, code_field):
        """提取申购代码（支持 HTML 格式处理）"""
        if code_field.startswith("<span"):
            return code_field[33:39]
        return code_field

    def send_msg(self, message, title):
        """发送消息到钉钉"""
        self.notifier.send_alert(message, title)

        # Define a task to monitor notifications

    def get_pre_list_data(self):
        """获取待发可转债最近一周进展数据"""
        if not date_utils.is_notification_time():
            return
        url = "https://www.jisilu.cn/data/cbnew/pre_list/?___jsl=LST___t="
        data = self.fetch_data(url)

        if not data:
            print("未获取到预列表数据")
            return

        today = datetime.now()
        message = ""
        for item in data.get("rows", []):
            cell = item.get("cell", {})
            progress_nm = cell.get("progress_nm", "")
            progress_dt_str = cell.get("progress_dt", "")

            # Check if progress_nm is valid
            if progress_nm not in ["上市委通过", "同意注册"]:
                continue

            try:
                progress_dt = datetime.strptime(progress_dt_str, "%Y-%m-%d")
            except ValueError:
                print(f"无法解析日期: {progress_dt_str}")
                continue

            # Check if progress_dt is within the last 7 days
            if today - progress_dt > timedelta(days=7):
                continue
            print(cell)
            message += (
                f"股票名称: {cell.get('stock_nm')}, "
                f"方案进展: {cell.get('progress_nm')}, "
                f"进展公告日: {cell.get('progress_dt')}, "
                f"每百元含权: {cell.get('cb_amount')} \n\n " #title="每百元股票含的可转债权利，单位元；=发行规模*100/A股总市值"
            )

        if message:
            self.send_msg(message, "待发转债更新提醒")
        else:
            print("没有符合条件的待发转债更新数据")

    def get_adjustment_reminders(self):
        """Send reminders 10 days before quarterly, semi-annual, and annual adjustments."""
        if not date_utils.is_notification_time():
            return

        # Define adjustment dates for 2025
        adjustment_dates = [
            datetime(2026, 2, 28),  # Quarterly adjustment
            datetime(2026, 5, 31),  # Semi-annual + Quarterly adjustment
            datetime(2026, 8, 31),  # Quarterly adjustment
            datetime(2026, 11, 30)  # Semi-annual + Quarterly + Annual adjustment
        ]

        today = datetime.now()
        message = ""

        for date in adjustment_dates:
            # Compare only month and day, ignoring the year
            if (date.month == today.month and date.day - today.day in range(0, 11)):
                message += f"提醒：距离 {date.strftime('%Y年%m月%d日')} 的调整还有 {date.day - today.day} 天。\n\n"

        if message:
            self.send_msg(message, "指数调整日期提醒")
        else:
            print("没有即将到来的调整日期需要提醒。")

    async def notify_at_specified_times(self):
        while True:
            print("Sending notifications...")
            self.get_today_bonds()
            self.get_today_stocks()
            self.get_pre_list_data()  # Existing method call
            self.get_adjustment_reminders()  # New method call
            await asyncio.sleep(600)  # Wait for a minute before checking again

if __name__ == "__main__":
    notifier = NewStockNotifier()
    notifier.get_pre_list_data()
    # notifier.send_msg("TEST", "TEST")


#     # 获取并通知今日新债信息
#     #notifier.get_today_bonds()

#     # 获取并通知今日新股信息
#     # notifier.get_today_stocks()

#     # notifier.notify_at_specified_times()
