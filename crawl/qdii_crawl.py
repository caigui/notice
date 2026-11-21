import requests
from bs4 import BeautifulSoup
import re
import time

class FundInfoExtractor:
    def __init__(self):
        pass

    def _crawl_and_get_purchase_info(self, url):
      """
        爬取指定网页，提取所有文本内容并根据交易状态返回可申购状态和限购金额。
      """
      try:
          response = requests.get(url, timeout=10)
          response.raise_for_status()
          response.encoding = 'utf-8'
          soup = BeautifulSoup(response.text, 'html.parser')
          all_text = soup.get_text(separator='\n', strip=True)
          
          purchase_info_list = []
          matches = re.findall(r"交易状态\s*(.+?)\s*购买手续费", all_text, re.DOTALL)
          for status_block in matches:
              status = status_block.replace("\n", " ").strip()  # 将换行符替换为空格并去除首尾空格
              
              if "暂停申购" in status:
                  purchase_info_list.append({
                      "can_purchase": False,
                      "limit_amount": None
                  })
              else:
                  limit_match = re.search(r"单日累计购买上限(\d+)元", status)
                  limit_amount = int(limit_match.group(1)) if limit_match else None

                  purchase_info_list.append({
                    "can_purchase":True,
                    "limit_amount": limit_amount
                  })

          return {
              "all_text": all_text,
              "purchase_info": purchase_info_list
          }

      except requests.exceptions.RequestException as e:
          print(f"Error during request: {e}")
          return None
      except Exception as e:
          print(f"Error during parsing or processing: {e}")
          return None


    def get_fund_purchase_info(self, fund_code):
        """
        根据基金代码获取是否可申购和限购金额。

        Args:
            fund_code: 基金代码，例如 "161128", "501300"。

        Returns:
            一个包含 "can_purchase" (bool) 和 "limit_amount" (int 或 None) 的字典，
            如果爬取失败或未找到信息，则返回 None。
        """
        url = f"https://fund.eastmoney.com/{fund_code}.html"
        result = self._crawl_and_get_purchase_info(url)

        if result and result["purchase_info"]:
           
           #这里假设有多个信息时，默认取第一个,
           # 如果需要遍历请自行修改
           return result["purchase_info"][0]
        else:
          return None


# if __name__ == '__main__':
#     extractor = FundInfoExtractor()

#     fund_codes = ["161128", "501300", "009603"]
#     for code in fund_codes:
#         fund_info = extractor.get_fund_purchase_info(code)
#         time.sleep(1)
#         if fund_info:
#             print(f"基金代码: {code}")
#             print(f"是否可申购: {fund_info['can_purchase']}")
#             if fund_info["limit_amount"] is not None:
#                 print(f"限购金额: {fund_info['limit_amount']}")
#             print("-" * 20)
#         else:
#             print(f"获取基金代码 {code} 信息失败!")
#             print("-" * 20)