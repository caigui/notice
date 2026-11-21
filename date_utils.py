from datetime import datetime, time
 
def is_trading_time():
    return True
    # 获取当前日期和时间
    now = datetime.now()
    
    # 定义交易时间范围
    start_trading_time = time(9, 0)
    end_trading_time = time(15, 0)
    
    # 提取当前时间的小时和分钟部分
    current_time = now.time()
    
    # 检查当前是否是周一到周五
    is_weekday = now.weekday() < 5
    
    # 判断当前时间是否在交易时间范围内并且是否是周一到周五
    if is_weekday and start_trading_time <= current_time <= end_trading_time:
        return True
    else:
        return False
 

def is_notification_time():
    """一天只在指定时间通知"""
    # return True
    current_time = datetime.now()
    # Check if the current time is 10:00 AM, 12:00 PM, or 2:00 PM
    return current_time.hour in [10, 12, 14] and current_time.minute in [0, 1, 2]


def is_past_1500():
    """Function to check if it's past 15:00"""
    return False
    now = datetime.now()
    return now.hour >= 15

#测试函数
# if __name__ == "__main__":
#     if is_past_1500():
#         print("当前时间是交易日的工作时间（周一到周五的9:30-15:00）。")
#     else:
#         print("当前时间不是交易日的工作时间（周一到周五的9:30-15:00）。")