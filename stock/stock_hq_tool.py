import requests
import traceback
from typing import List, Dict, Any

class StockHQFromSina:
    """
    从新浪获取股票实时行情数据的工具类
    """

    def __init__(self):
        self.headers = {
            'Referer': 'https://finance.sina.com.cn',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36'
        }

    def generate_stock_code(self, data_dict: Dict[str, Any]) -> str:
        """
        生成股票代码字符串
        """
        stock_codes = []
        for code in data_dict.keys():
            # 根据股票代码前缀判断市场
            if code.startswith(('50', '60', '68')):
                # 上海市场
                stock_codes.append(f'sh{code}')
            elif code.startswith(('00', '30', '15', '16')):
                # 深圳市场
                stock_codes.append(f'sz{code}')
            elif code.startswith('92'):
                # 北京市场
                stock_codes.append(f'bj{code}')
            else:
                # 默认按上海市场处理
                stock_codes.append(f'sh{code}')
        return ','.join(stock_codes)

    def get_stock_hq(self, stock_codes: List[str]) -> Dict[str, Any]:
        """
        获取股票实时行情数据
        
        Args:
            stock_codes: 股票代码列表
            
        Returns:
            包含股票数据和错误信息的字典
        """
        result = {'data': [], 'error': []}
        
        try:
            # Remove duplicates while preserving order
            unique_stock_codes = list(dict.fromkeys(stock_codes))
            
            # 构造数据字典
            data_dict = {code: '' for code in unique_stock_codes}
            
            # 生成股票代码 - only for the unique codes
            stock_code = self.generate_stock_code(data_dict)
            
            # Send request with unique codes only
            url = f"http://hq.sinajs.cn/list={stock_code}"
            response = requests.get(url, headers=self.headers)
            
            if response.status_code == 200:
                res_list = response.text.split(';')
                data_dict_result = {}
                
                for line in res_list:
                    try:
                        if len(line.strip()) < 30:
                            continue
                            
                        stock_info = line.strip().split(',')
                        # Extract stock code from the response line
                        code_part = stock_info[0].split('=')[0]
                        # Extract the actual stock code from the variable name
                        if 'str' in code_part:
                            # Format: var hq_str_sh600000 or var hq_str_sz000001
                            raw_code = code_part.replace('var hq_str_', '')
                            if raw_code.startswith('sh'):
                                code = raw_code[2:]  # Remove 'sh' prefix
                            elif raw_code.startswith('sz'):
                                code = raw_code[2:]  # Remove 'sz' prefix
                            elif raw_code.startswith('bj'):
                                code = raw_code[2:]  # Remove 'bj' prefix
                            else:
                                code = raw_code
                        else:
                            continue
                        
                        # Skip if code not in our request list
                        if code not in data_dict:
                            continue
                        
                        # Check if we already have data for this code
                        if code in data_dict_result:
                            stock_data = data_dict_result[code]
                        else:
                            # Create new stock data object
                            stock_data = StockData()
                            stock_data.code = code
                        
                        # Update basic stock information
                        if len(stock_info) > 1:
                            stock_data.name = stock_info[0].split('"')[-1]
                            
                        if len(stock_info) > 3:
                            try:
                                stock_data.current_price = float(stock_info[3])
                            except (ValueError, IndexError):
                                pass
                        if len(stock_info) > 1:
                            try:
                                stock_data.open_price = float(stock_info[1])
                            except (ValueError, IndexError):
                                pass
                        
                        # Handle volume information (position 8 in the response)
                        if len(stock_info) > 8:
                            try:
                                volume_raw = int(float(stock_info[8]))  # Convert to int after float to handle decimals
                                stock_data.volume = volume_raw // 100 if volume_raw >= 100 else volume_raw  # Normalize volume
                            except (ValueError, IndexError):
                                stock_data.volume = 0
                        
                        # Get transaction amount directly from API (index 9 in the response)
                        if len(stock_info) > 9:
                            try:
                                transaction_amount = float(stock_info[9])
                                stock_data.transaction_amount = transaction_amount
                            except (ValueError, IndexError):
                                stock_data.transaction_amount = 0
                        else:
                            stock_data.transaction_amount = 0
                        
                        if len(stock_info) > 2:
                            try:
                                stock_data.last_price = float(stock_info[2])
                            except (ValueError, IndexError):
                                pass
                        if len(stock_info) > 4:
                            try:
                                stock_data.max_price = float(stock_info[4])
                            except (ValueError, IndexError):
                                pass
                        if len(stock_info) > 5:
                            try:
                                stock_data.min_price = float(stock_info[5])
                            except (ValueError, IndexError):
                                pass
                        if len(stock_info) > 30:
                            try:
                                stock_data.day = stock_info[30].replace('-', '')
                            except IndexError:
                                pass
                        
                        # Only add to result if we have meaningful data
                        if stock_data.name and stock_data.name.strip():  # Only add if name exists and is not empty
                            data_dict_result[code] = stock_data
                    
                    except Exception as e:
                        print(f"数据解析保存失败: {line}")
                        print(traceback.format_exc())
                
                # Add valid results to final result
                for code, stock_data in data_dict_result.items():
                    result['data'].append(stock_data.to_dict())
                    # print(f"获取到股票数据: {stock_data}")
                
                # Identify which codes didn't return valid data
                received_codes = set(data_dict_result.keys())
                requested_codes = set(unique_stock_codes)
                missing_codes = requested_codes - received_codes
                result['error'] = list(missing_codes)
                
            else:
                print(f"请求未正常返回，状态码: {response.status_code}")
                result['error'] = unique_stock_codes
                
        except Exception as e:
            print(f"获取股票行情时出现异常: {e}")
            print(traceback.format_exc())
            result['error'] = unique_stock_codes
            
        return result


class StockData:
    """
    股票数据模型
    """
    
    def __init__(self):
        self.code = ""
        self.name = ""
        self.current_price = 0.0
        self.open_price = 0.0
        self.last_price = 0.0
        self.max_price = 0.0
        self.min_price = 0.0
        self.volume = 0  # Trading volume
        self.transaction_amount = 0  # Transaction amount (price * volume * 100)
        self.turnover_rate = 0.0
        self.day = ""
    
    def to_dict(self):
        """转换为字典格式"""
        return {
            'code': self.code,
            'name': self.name,
            'current_price': self.current_price,
            'open_price': self.open_price,
            'last_price': self.last_price,
            'max_price': self.max_price,
            'min_price': self.min_price,
            'volume': self.volume,
            'transaction_amount': self.transaction_amount,
            'turnover_rate': self.turnover_rate,
            'day': self.day
        }
    
    def __str__(self):
        return f"StockData(code={self.code}, name={self.name}, current_price={self.current_price}, volume={self.volume}, transaction_amount={self.transaction_amount})"


# 使用示例
if __name__ == "__main__":
    # 创建工具实例
    stock_hq_tool = StockHQFromSina()
    
    # 获取股票数据
    codes = ["000001", "600000", "000002"]  # 示例股票代码
    result = stock_hq_tool.get_stock_hq(codes)
    
    # 输出结果
    print("获取到的数据:")
    for item in result['data']:
        print(item)
    
    if result['error']:
        print("错误信息:")
        print(result['error'])