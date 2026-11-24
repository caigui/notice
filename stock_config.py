import os
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.shortcuts import checkboxlist_dialog, yes_no_dialog, input_dialog, message_dialog
from prompt_toolkit.styles import Style
from globalVar import log
import csv

EVENT_TYPES = ("配债", "要约收购", "私有化", "吸收合并", "其他")


class StockConfig(object):
    """
    股票预警类，用于读取股票预警配置文件，获取股票预警信息。
    """
    def __init__(self):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.__stock_file_path = os.path.join(script_dir, "stock_notice.csv")
        self.__se_info = [
            ("sse: http://yunhq.sse.com.cn:32041//v1/sh1/snap/"),
            ("sseETF: http://yunhq.sse.com.cn:32041//v1/sh1/list/self/xxxxxx?"
             "callback=jQuery112408966245538614501_1602813033855&select=code%2Cname"
             "%2Copen%2Chigh%2Clow%2Clast%2Cprev_close%2Cchg_rate%2Cvolume%2Camount"
             "%2Ccpxxextendname&_=1602813033858"),
            ("szse: http://www.szse.cn/api/market/ssjjhq/getTimeData?marketId=1&code="),
        ]  # 存放交易所信息

    def get_stock_exchange(self):
        """返回交易所消息"""
        return self.__se_info

    @staticmethod
    def _read_csv_text(file_path):
        """stock_notice.csv 历史为 GBK/GB18030，兼容 UTF-8 与 BOM。"""
        last_err = None
        for enc in ("utf-8-sig", "gb18030", "gbk"):
            try:
                with open(file_path, mode='r', newline='', encoding=enc) as f:
                    return f.read()
            except UnicodeDecodeError as e:
                last_err = e
        raise last_err or IOError("无法解码 %s" % file_path)

    def read_stock_data(self, file_path):
        """
        读取 CSV 文件并返回格式化的股票数据。
        CSV 格式: stock_code, name, price_min, price_max, type, notes
        `type` 缺省为「配债」，兼容旧版 5 列文件；空行/模板行直接跳过。
        """
        stock_data = []
        try:
            text = self._read_csv_text(file_path)
            for row in csv.DictReader(text.splitlines()):
                code = (row.get("stock_code") or "").strip().lstrip("\ufeff")
                if not code:
                    continue                      # 模板行 / 空行
                try:
                    pmin = float(row.get("price_min") or "")
                    pmax = float(row.get("price_max") or "")
                except ValueError:
                    print(f"跳过价格无效的行: {code}")
                    continue
                ev_type = (row.get("type") or "配债").strip() or "配债"
                if ev_type not in EVENT_TYPES:
                    ev_type = "其他"
                stock_data.append({
                    "stock_code": code,
                    "name": (row.get("name") or "").strip(),
                    "price_min": pmin,
                    "price_max": pmax,
                    "type": ev_type,
                    "notes": (row.get("notes") or "").strip(),
                })
        except Exception as e:
            print(f"读取文件出错: {e}")
        return stock_data

    def get_se_and_stock_id(self):
        """
        按交易所分类，返回格式化的股票代码。
        - sse股票代码：以 '6' 开头
        - szse股票代码：以 '0' 或 '3' 开头
        返回示例：
        {
            "sse": ["600000", "600001"],
            "szse": ["000625"]
        }
        """
        formatted_stock_data = {"sse": [], "szse": []}  # 初始化分类字典
        stock_data = self.read_stock_data(self.__stock_file_path)  # 读取CSV数据

        for stock in stock_data:
            stock_code = stock.get("stock_code")  # 获取股票代码
            if not stock_code:  # 检查是否存在 stock_code
                continue
            
            # 根据代码前缀判断交易所并存储股票代码
            if stock_code.startswith('6') or stock_code.startswith('204'):  # sse
                formatted_stock_data["sse"].append(stock_code)
            elif stock_code.startswith('0') or stock_code.startswith('3') or stock_code.startswith('131') or stock_code.startswith('127'):  # szse
                formatted_stock_data["szse"].append(stock_code)

        return formatted_stock_data

    def get_monitored_stock(self):
        """返回从文件读取的监控股票数据"""
        return self.read_stock_data(self.__stock_file_path)

    def get_stock_id_and_price(self):
        """返回格式化的股票代码和监控价格范围"""
        stock_data = self.get_monitored_stock()
        stock_id_price = {}

        for stock in stock_data:
            stock_code = stock["stock_code"]
            price_range = {
                "price_min": stock["price_min"],
                "price_max": stock["price_max"],
                "type": stock.get("type", "配债"),
                "notes": stock.get("notes", ""),
                "name": stock.get("name", ""),
            }
            stock_id_price[stock_code] = price_range

        return stock_id_price


# # 实例化类并调用方法
# interactive_prompt = StockConfig()

# # 交易所信息
# print("交易所信息：")
# print(interactive_prompt.get_stock_exchange())
# # 监控股票数据
# print("\ncsv 监控股票数据：")
# print(interactive_prompt.get_monitored_stock())
# # 按交易所分类的股票数据
# print("\n股票数据按交易所分类：")
# print(interactive_prompt.get_se_and_stock_id())
# # 股票代码和价格范围
# print("\n股票代码及价格范围：")
# print(interactive_prompt.get_stock_id_and_price())

