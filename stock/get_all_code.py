import akshare as ak
import pandas as pd


def get_all_stock_code():
    # 获取所有A股的代码和名称
    stock_list_df = ak.stock_info_a_code_name()
    # 打印前几行看看效果
    print(stock_list_df.head())
    # 如果需要，可以轻松保存为CSV文件
    stock_list_df.to_csv("all_a_code.csv", index=False, encoding="utf-8-sig")


get_all_stock_code()