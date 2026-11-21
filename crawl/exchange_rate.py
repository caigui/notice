import requests
from typing import Optional
import json
import os

# Constants
CHINAMONEY_API_URL = "https://www.chinamoney.com.cn/r/cms/www/chinamoney/data/fx/ccpr.json"
DEFAULT_TIMEOUT = 30
OUTPUT_FILE_PATH = 'chinamoney_rate_api.json'

def get_cny_midprice() -> Optional[str]:
    """从中国货币网获取人民币汇率中间价"""
    # 使用API路径
    url = CHINAMONEY_API_URL
    
    # 模拟浏览器请求头
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest"
    }
    
    try:
        # 发送请求 - 使用 SSL verification
        response = requests.get(url, headers=headers, proxies={}, timeout=DEFAULT_TIMEOUT)
        response.raise_for_status()  # Raise an exception for bad status codes
        
        if response.status_code == 200:
            # Validate and save original JSON to file safely
            safe_file_path = os.path.abspath(OUTPUT_FILE_PATH)
            if os.path.dirname(safe_file_path) == os.getcwd():  # Basic path validation
                with open(safe_file_path, 'w', encoding='utf-8') as f:
                    f.write(response.text)
            
            # Parse JSON data
            data = response.json()
            
            # Get date information
            date_info = ""
            if isinstance(data, dict) and 'data' in data and isinstance(data['data'], dict):
                date_info = data['data'].get('lastDate', "")
            
            # Find USD to CNY exchange rate using helper function
            rate = _find_usd_rate(data)
            
            if rate is not None:
                print(f"✅ 找到美元兑人民币汇率: {rate} (日期: {date_info})")
                return rate
            
    except requests.exceptions.RequestException as e:
        print(f"网络请求过程中出错: {e}")
    except json.JSONDecodeError as e:
        print(f"JSON解析过程中出错: {e}")
    except IOError as e:
        print(f"文件操作过程中出错: {e}")
    except KeyError as e:
        print(f"数据结构错误: 缺少预期的键 {e}")
    except Exception as e:
        print(f"爬取过程中出错: {e}")
    
    return None


def _find_usd_rate(data: dict) -> Optional[str]:
    """Helper function to find USD rate from API response data"""
    # Check both possible data structures
    records_list = []
    
    # First check direct records in root
    if 'records' in data and isinstance(data['records'], list):
        records_list = data['records']
    # Then check nested records in data
    elif ('data' in data and isinstance(data['data'], dict) 
          and 'records' in data['data'] and isinstance(data['data']['records'], list)):
        records_list = data['data']['records']
    
    for record in records_list:
        if (isinstance(record, dict) and 
            'vrtName' in record and 
            'price' in record and 
            isinstance(record['vrtName'], str) and 
            isinstance(record['price'], (str, int, float))):
            
            vrt_name = record['vrtName']
            if '美元' in vrt_name or 'USD' in vrt_name:
                return str(record['price'])
    
    return None

if __name__ == "__main__":
    get_cny_midprice()  