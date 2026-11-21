# import pandas as pd
# print(pd.__version__)      # 注意是双下划线

import akshare as ak

fund_purchase_em_df = ak.fund_purchase_em()
print(fund_purchase_em_df)

# Extract and print unique values of '申购状态'
unique_subscription_statuses = fund_purchase_em_df['申购状态'].unique()
print("Unique values in '申购状态':", unique_subscription_statuses)

# # Filter data for fund code '159941' and display its subscription status
# filtered_fund = fund_purchase_em_df[fund_purchase_em_df['基金代码'] == '159941']
# if not filtered_fund.empty:
#     print(filtered_fund[['基金代码', '申购状态']])
# else:
#     print("基金代码 159941 未找到")
