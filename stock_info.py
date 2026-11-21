import requests
from globalVar import log
from stock_config import StockConfig

class StockInfo(object):
    """股票信息对象"""
    
    def __init__(self, se, monitored_stock):
        """
        初始化要监控的股票及其链接
        Args:
            se: 交易所消息（交易所:链接），列表类型
            monitored_stock: 要监控的股票代码，字典类型 {交易所名: [股票代码, ...]}
        """
        self.monitored_stock = monitored_stock
        self.session = requests.session()
        self.session.keep_alive = False
        self.stock_urls = {}  # 存放股票代码和链接
        self.stock_data = []  # 存放获取到的股票信息
        
        # 初始化股票代码与对应的链接
        self._init_stock_urls(se)
    
    def _init_stock_urls(self, se):
        """解析交易所信息，初始化股票链接."""
        dict_se = {el.split(": ")[0]: el.split(": ")[1] for el in se}
        for exchange, stock_list in self.monitored_stock.items():
            if exchange not in dict_se:  # 检查是否有对应的交易所链接
                log.logger.warning(f"交易所 '{exchange}' 未找到对应的链接信息.")
                continue
            for stock_code in stock_list:
                self.stock_urls[stock_code] = dict_se[exchange] + stock_code

    def _get_data(self, url):
        """
        通过接口获取单个股票数据.
        Args:
            url: 股票的API接口链接
        Returns:
            返回解析后的数据或 None
        """
        try:
            with self.session.get(url) as response:  # 使用上下文管理器自动关闭
                response.raise_for_status()
                return response.json()
        except requests.RequestException as err:
            log.logger.error(f"网络请求失败: {err}")
            return None


    def get_all_stock_info(self):
        """获取所有的股票信息."""
        self.stock_data.clear()  # 清除之前数据
        for stock_code, url in self.stock_urls.items():
            json_data = self._get_data(url)
            # print(url)
            # print(json_data)
            if json_data:
                if "sse" in url:
                    data = self._parse_stock_data(json_data)
                if "szse" in url:
                    data = self._parse_stock_data_szse(json_data)
                if data:
                    self.stock_data.append(data)
        log.logger.info("获取股票信息完成.")
        self.stock_data.sort(key=lambda stock: stock[3], reverse=True)  # 以涨幅排序

    def _parse_stock_data(self, json_data):
        """
        解析单个股票 JSON 数据.
        Args:
            json_data: JSON 格式的股票数据
        Returns:
            返回元组 (股票名称, 股票代码, 现价, 涨幅, 涨跌, 昨收, 开盘, 最高, 最低, 交易时间)
        """
        try:
            snap = json_data.get("snap", [])
            if not snap or len(snap) < 8:  # 数据校验，确保 snap 数据存在且索引有效
                log.logger.warning(f"股票数据异常: {json_data}")
                return None
            return (
                snap[0],                # 股票名称
                json_data.get("code"),  # 股票代码
                float(snap[5]),         # 现价
                float(snap[7]),         # 涨幅
                float(snap[6]),         # 涨跌
                float(snap[1]),         # 昨收
                float(snap[2]),         # 开盘
                float(snap[3]),         # 最高
                float(snap[4]),         # 最低
                json_data.get("time")   # 交易时间
            )
        except (IndexError, KeyError, TypeError, ValueError) as e:
            log.logger.error(f"数据解析错误: {e}, JSON数据: {json_data}")
            return None

    def _parse_stock_data_szse(self, json_data):
        stock_data = json_data['data']

        # print(stock_data)
        # 从返回数据中提取各项信息
        stock_name = stock_data['name']  # 股票名称
        stock_code = stock_data['code']  # 股票代码
    
        try:
            current_price = float(stock_data.get('now', 0))  # 现价
        except ValueError:
            current_price = 0
        try:
            price_change = float(stock_data.get('delta', 0))  # 涨跌
        except ValueError:
            price_change = 0
        try:
            price_change_percent = float(stock_data.get('deltaPercent', 0))  # 涨幅
        except ValueError:
            price_change_percent = 0
        try:
            close_price = float(stock_data.get('close', 0))  # 昨收
        except ValueError:
            close_price = 0
        try:
            open_price = float(stock_data.get('open', 0))  # 开盘
        except ValueError:
            open_price = 0
        try:
            highest_price = float(stock_data.get('high', 0))  # 最高
        except ValueError:
            highest_price = 0
        try:
            lowest_price = float(stock_data.get('low', 0))  # 最低
        except ValueError:
            lowest_price = 0

        trade_time = stock_data.get('marketTime', 'N/A')  # 交易时间

        # 返回包含上述信息的元组
        return (stock_name, stock_code, current_price, price_change_percent, price_change, close_price, open_price, highest_price, lowest_price, trade_time)

    def display_stock_info(self, batch_size=10):
        """分批次显示所有的股票信息"""
        if not self.stock_data:
            print("未获取到任何股票信息，请检查接口或监控的股票代码。")
            return
        
        print("股票信息如下：\n")
        for i in range(0, len(self.stock_data), batch_size):
            batch = self.stock_data[i:i + batch_size]
            for data in batch:
                print("{:<10}({}) 现价：{:>7.2f} 涨幅：{:>6.2f}% 涨跌：{:>6.2f} 昨收：{:>7.2f} 开盘：{:>7.2f} 最高：{:>7.2f} 最低：{:>7.2f} 交易时间：{}".format(
                    data[0], data[1], data[2], data[3], data[4], data[5], data[6], data[7], data[8], data[9]
                ))

# if __name__ == "__main__":
#     # 交易所链接和股票列表
#     interactive_prompt = StockConfig()  
#     se = interactive_prompt.get_stock_exchange()
#     # monitored_stock =interactive_prompt.get_se_and_stock_id()
#     # 静态监控股票代码数据
#     monitored_stock =   {
#             "sse": ["600000", "600001"],
#             "szse": ["000625"]
#         }
#     # 初始化
#     print(se)
#     print(monitored_stock)
#     stock_info = StockInfo(se, monitored_stock)
    
#     # 获取数据
#     print("正在获取股票数据，请稍候...")
#     stock_info.get_all_stock_info()
    
#     # 显示数据
#     stock_info.display_stock_info(batch_size=5)