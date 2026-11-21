import pandas as pd
import sqlite3
from datetime import datetime
from datetime import time
import datetime
import json

class NewTaskInfo(object):
    def __init__(self):
        self.ID = 0
        self.szTaskName = ""
        self.szNickName = ""
        self.lStatus = 1
        self.lCur = 0
        self.lGridPrice = 0.0
        self.lGridValue = 0.0
        self.lMaxSell = 0
        self.lFallPrice = 0.0
        self.lGridCount = 10
        self.lSzGridCount = 10
        self.lNewPrice = 0.0
        self.lDealPrice = 0.0
        self.lVol = 0.0
        self.lOweCount = 0

        self.lMaxOweCount = 0
        self.lMinOweCount = 0

        # 0无 1买 2卖 3取消
        self.lDoCount = 0
        self.lBuyCount = 0
        self.lSellCount = 0
        self.lDoType = 0
        now = datetime.datetime.now()
        self.lBonusDate = now + INITIAL_PAST_TIME_OFFSET
        self.lDoTime = now + INITIAL_PAST_TIME_OFFSET
        self.lTradeTime = now + INITIAL_PAST_TIME_OFFSET
        self.lCancelTime = now + INITIAL_PAST_TIME_OFFSET
        self.lLastPriceTime = now + INITIAL_PAST_TIME_OFFSET
        self.lLastSaveTime = now
        self.lLastTime = 0
        self.lDoPrice = 0.0

        self.lMaxTime = now + INITIAL_PAST_TIME_OFFSET

        self.sh = 0
        self.debt = 0
        self.show_count = 0
        self.lNewTask = 0
        self.have_count = 0


def initialize(context):
    # 初始化策略
    # 是否交易
    g.err = 0
    g.is_trade = 0
    g.is_auto = 1
    #是否融
    g.margin = 0
    #是否盘后
    g.do_end = 1
    # 当天最大买或卖数
    g.max_buy_count = 40
    g.max_trade_count = 15

    #最大倍数
    g.max_mul = 2
    # 资金少于则不买入
    g.limit_money = 1000
    # 买卖少于则不操作
    g.min_buy_money = 700
    g.max_buy_money = 3000
    # 留多少钱不回购
    g.out_money = 1000
    # 放大量
    g.more_vol = 3
    # 时间状态 0未开始 1交易中 2交易中快结束 9盘后
    g.time_state = 1
    g.money = 0
    g.buy_money = 0.0
    g.buy_str = ''
    g.last_money = 0
    g.need_money = 0.0
    g.done = 0
    g.sell_count = 0
    g.trade_count = 0
    g.last_name = ""
    g.have_count = 0

    g.TaskList = []
    g.bLastTrade = 0
    g.last_log_time = datetime.datetime.now() + datetime.timedelta(days=-1)
    g.last_trade_log_time = datetime.datetime.now()

    g.last_save_money_time = datetime.datetime.now() + datetime.timedelta(days=-1)
    g.last_read_json_time = datetime.datetime.now()
    g.lCheckOweTime = datetime.datetime.now() + INITIAL_PAST_TIME_OFFSET
    g.money = context.portfolio.cash

    # 文件
    g.file_path = get_research_path() + 'upload_file/UserGridS.db'
    g.file_json_path = get_research_path() + 'upload_file/UserGridJson.txt'

    log.info(g.file_path)

    print("初始资金=", context.portfolio.cash, "留=", g.out_money)
    # 创建数据库引擎对象
    #LoadTradeLog()
    LoadTaskList()
    ClearTradeLog(720, 180)
    do_one_task(context, 1)

    # 定义一个周期处理函数，每3秒执行一次
    if g.is_trade > 0 or get_position_count(context) > 0:
        run_interval(context, interval_handle, seconds=3)
        run_daily(context, after_trading_order_test, time="15:02")
        run_daily(context, after_trading_order_test, time="15:10")
        run_daily(context, after_trading_order_test, time="15:15")
        run_daily(context, after_trading_order_test, time="15:20")
        run_daily(context, after_trading_order_test, time="15:25")
        run_daily(context, after_trading_order_test, time="15:29")
        g.is_trade = 1
    else:
        g.is_trade = 0

    g.security = "600570.SS"
    set_universe(g.security)


def do_one_task(context, first):
    print("执行一次开始 卖出", first)

    #非初始化
    if first <= 0:
        g.done = 1

    CheckUserOrderList()
    CheckBonusList()

    g.have_count = 0
    CheckOweTaskList(context)
    WriteUserMoney()

    for TaskInfo in g.TaskList:
        #SaveTaskInfo(TaskInfo);
        #IsTaskStart(TaskInfo)
        CheckTaskInfo(TaskInfo, first)
        SaveTaskPrice(TaskInfo)
        # if TaskInfo.szTaskName=="113549.SS":
        # SaveTradeLog(TaskInfo,TaskInfo.lGridPrice,10,",test")

    if g.is_trade <= 0:
        StartList = []
        StopList = []
        #000001 启动
        StartList.append("0")
        StopList.append("123099")
        print(StartList)
        for info in StartList:
            print(info)
            StartStopTask(info, 1)
        for info in StopList:
            StartStopTask(info, 0)
        ReadJsonFile()

    PrintTaskList(0)
    log.info("执行一次结束")


def do_end_task(context):
    CheckOweTaskList(context)
    for TaskInfo in g.TaskList:
        SaveTaskPrice(TaskInfo)
    GetTaskItemPrice(context, TaskInfo)


def StartStopTask(szTaskName, dwStart=1):
    if dwStart > 0:
        TaskInfo = FindTaskInfoByID(szTaskName)
        if TaskInfo is not None and TaskInfo.lStatus < 9:
            TaskInfo.lGridValue = 1
            TaskInfo.lStatus = 9
            if abs(TaskInfo.lNewPrice - TaskInfo.lGridPrice) > 0.4:
                TaskInfo.lGridPrice = TaskInfo.lNewPrice
            if TaskInfo.lMaxOweCount <= 0:
                TaskInfo.lMaxOweCount = 250
            if TaskInfo.lOweCount >= 150:
                TaskInfo.lMaxOweCount = TaskInfo.lOweCount + 150
            if TaskInfo.lOweCount >= 10000:
                TaskInfo.lGridValue = 0.01 * int(TaskInfo.lNewPrice * 10) / 10
            if TaskInfo.lGridValue <= 0:
                TaskInfo.lGridValue = 0.01
            TaskInfo.lGridCount = 1000
            TaskInfo.lMaxOweCount = TaskInfo.lOweCount + 10000
            SaveTaskStatus(TaskInfo)
    else:
        TaskInfo = FindTaskInfoByID(szTaskName)
        if TaskInfo is not None and TaskInfo.lStatus != 1:
            TaskInfo.lStatus = 1
            SaveTaskStatus(TaskInfo)


def handle_data(context, data):
    if g.done == 0:
        do_one_task(context, 0)


def interval_handle(context):
    current_time = context.current_dt.time()
    if current_time <= datetime.time(9, 30):
        g.time_state = 0
    elif current_time > datetime.time(15, 0):
        g.time_state = 9
    elif current_time > datetime.time(14, 30):
        g.time_state = 2
    else:
        g.time_state = 1

    if g.done == 0:
        do_one_task(context, 0)

    #执行任务
    DoTaskList(context)


def before_trading_start(context, data):
    if g.is_trade <= 0:
        return
    print("每日开始 检测取消任务")
    for TaskInfo in g.TaskList:
        CheckCancelTask(TaskInfo)
        ResetDayTask(TaskInfo)


def after_trading_order_test(context):
    print("盘后交易 留=", g.out_money)
    do_end_task(context)
    if g.do_end <= 0:
        return
    if g.margin > 0:
        return
    #g.security = "131810.SZ"

    g.security = "204001.SS"
    stock = g.security
    snapshot = get_snapshot(g.security)
    print("盘后交易 =", snapshot)
    g.money = context.portfolio.cash

    WriteUserMoney()
    CheckOweTaskList(context, 1)


def on_order_response(context, order_list):
    print("订单产生 开始")


def on_trade_response(context, trade_list):
    log.info("订单成交 开始")
    WriteUserMoney()
    for trade in trade_list:
        print(trade)
        amount = trade['business_amount']
        stock = trade['stock_code']
        price = trade['business_price']
        status = trade['status']
        if not (status == "7" or status == "8"):
            return

        str_log = ""
        if amount > 0:
            str_log = "订单成交 买入:{},价格{},数量{}".format(stock, price, amount)
        elif amount < 0:
            str_log = "订单成交 卖出:{},价格{},数量{}".format(stock, price, amount)
        log.info(str_log)
        TaskInfo = FindTaskInfoByID(stock)

        if TaskInfo is not None:
            TaskInfo.lDealPrice = price
            if IsTaskStart(TaskInfo):
                TradeTaskInfo(TaskInfo, amount)
            TaskInfo.lDoType = 0
            TaskInfo.lDoCount += 1
            TaskInfo.lTradeTime = datetime.datetime.now()

            g.trade_count += 1
            g.last_name = TaskInfo.szNickName
            if amount > 0:
                TaskInfo.lBuyCount += 1
                g.last_name += "-买"
            else:
                g.sell_count += 1
                TaskInfo.lSellCount += 1
                g.last_name += "-卖"
            SaveTaskInfo(TaskInfo)
            SaveTradeLog(TaskInfo, price, amount, ",trade log")
        else:
            SaveTaskInfo(TaskInfo)


def after_trading_end(context, data):
    do_one_task(context, 1)
    print("盘后交易结束")


def WriteUserMoney():
    with sqlite3.connect(g.file_path) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE UserList SET UseMoney = ?", (g.money + g.buy_money,))
        conn.commit()


def LoadTaskList(TaskName=""):
    with sqlite3.connect(g.file_path) as conn:
        cursor = conn.cursor()
        cursor.execute('pragma table_info(TaskList)')
        col_name = [x[1] for x in cursor.fetchall()]

        if TaskName and len(TaskName) > 0:
            print("加载=", TaskName)
            cursor.execute("SELECT * FROM TaskList WHERE TaskName = ?", (TaskName,))
        else:
            cursor.execute("SELECT * FROM TaskList ORDER BY sort, Status DESC, TaskName")

        allData = cursor.fetchall()
        print("直接获取全部记录：")
        for item in allData:
            szTaskName = item[GetTableIndex(col_name, "TaskName")]
            TaskInfo = FindTaskInfoByID(szTaskName)
            bHave = 1
            if TaskInfo is None:
                TaskInfo = NewTaskInfo()
                bHave = 0
            TaskInfo.ID = item[GetTableIndex(col_name, "ID")]
            TaskInfo.szTaskName = szTaskName
            TaskInfo.szNickName = item[GetTableIndex(col_name, "NickName")]
            TaskInfo.lGridValue = item[GetTableIndex(col_name, "GridValue")]
            TaskInfo.lGridPrice = item[GetTableIndex(col_name, "GridPrice")]
            TaskInfo.lDealPrice = item[GetTableIndex(col_name, "DealPrice")]
            TaskInfo.lGridPrice = round(TaskInfo.lGridPrice, 3)
            TaskInfo.lNewPrice = item[GetTableIndex(col_name, "NewPrice")]
            TaskInfo.lStatus = item[GetTableIndex(col_name, "Status")]
            TaskInfo.lDoType = item[GetTableIndex(col_name, "DoType")]
            TaskInfo.lOweCount = item[GetTableIndex(col_name, "OweCount")]
            TaskInfo.lMaxOweCount = item[GetTableIndex(col_name, "MaxOweCount")]
            bonus_date_str = item[GetTableIndex(col_name, "BonusDate")]
            if bonus_date_str:
                TaskInfo.lBonusDate = datetime.datetime.strptime(bonus_date_str, "%Y-%m-%d %H:%M:%S")
            if TaskInfo.szTaskName.find("SS") >= 0:
                TaskInfo.sh = 1
            elif TaskInfo.lSzGridCount > 0:
                TaskInfo.lGridCount = TaskInfo.lSzGridCount
            if bHave <= 0:
                g.TaskList.append(TaskInfo)

        PrintTaskList(0)


def InsertTaskInfo(TaskInfo):
    with sqlite3.connect(g.file_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO TaskList (TaskName, Status, DoType, OweCount, GridValue, GridPrice, NewPrice) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (TaskInfo.szTaskName, TaskInfo.lStatus, TaskInfo.lDoType, TaskInfo.lOweCount,
             TaskInfo.lGridValue, TaskInfo.lGridPrice, TaskInfo.lNewPrice)
        )
        conn.commit()


def SaveTaskInfo(TaskInfo):
    with sqlite3.connect(g.file_path) as conn:
        cursor = conn.cursor()
        update_fields = ["Status = ?", "DoType = ?", "OweCount = ?", "GridPrice = ?", "DealPrice = ?", "Updatedate = ?"]
        params = [TaskInfo.lStatus, TaskInfo.lDoType, TaskInfo.lOweCount, TaskInfo.lGridPrice, TaskInfo.lDealPrice, datetime.datetime.now()]
        if TaskInfo.lNewPrice > 0:
            update_fields.append("NewPrice = ?")
            params.append(TaskInfo.lNewPrice)
        query = "UPDATE TaskList SET " + ", ".join(update_fields) + " WHERE TaskName = ?"
        params.append(TaskInfo.szTaskName)
        cursor.execute(query, params)
        conn.commit()


def SaveTaskPrice(TaskInfo, bBonus=0, bGridPrice=0):
    with sqlite3.connect(g.file_path) as conn:
        cursor = conn.cursor()
        update_fields = []
        params = []
        if TaskInfo.lNewPrice > 0:
            update_fields.append("NewPrice = ?")
            params.append(TaskInfo.lNewPrice)
        if bBonus:
            update_fields.append("BonusDate = ?")
            params.append(TaskInfo.lBonusDate)
        if bGridPrice:
            update_fields.append("GridPrice = ?")
            params.append(TaskInfo.lGridPrice)
        update_fields.append("Updatedate = ?")
        params.append(datetime.datetime.now())
        if update_fields:
            query = "UPDATE TaskList SET " + ", ".join(update_fields) + " WHERE TaskName = ?"
            params.append(TaskInfo.szTaskName)
            cursor.execute(query, params)
            conn.commit()


def SaveTaskStatus(TaskInfo):
    with sqlite3.connect(g.file_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE TaskList SET Status = ?, GridValue = ?, MaxOweCount = ?, GridPrice = ?, DealPrice = ?, Updatedate = ? "
            "WHERE TaskName = ?",
            (TaskInfo.lStatus, TaskInfo.lGridValue, TaskInfo.lMaxOweCount, TaskInfo.lGridPrice,
             TaskInfo.lGridPrice, datetime.datetime.now(), TaskInfo.szTaskName)
        )
        conn.commit()


def SaveTaskInfoByID(TaskInfo):
    with sqlite3.connect(g.file_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE TaskList SET TaskName = ?, NickName = ?, Updatedate = ? WHERE ID = ?",
            (TaskInfo.szTaskName, TaskInfo.szNickName, datetime.datetime.now(), TaskInfo.ID)
        )
        conn.commit()


def DelTaskInfoByID(TaskInfo):
    with sqlite3.connect(g.file_path) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM TaskList WHERE ID = ?", (TaskInfo.ID,))
        conn.commit()


def DelTaskInfoByTaskName(szTaskName):
    with sqlite3.connect(g.file_path) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM TaskList WHERE TaskName = ?", (szTaskName,))
        conn.commit()


def TradeTaskInfo(TaskInfo, amount):
    TaskInfo.lOweCount += amount
    num = abs(amount)
    if num > TaskInfo.lGridCount * g.max_mul:
        num = TaskInfo.lGridCount * g.max_mul

    lGridValue = TaskInfo.lGridValue * (num / TaskInfo.lGridCount)
    if TaskInfo.lDoType > 0 and abs(amount) <= TaskInfo.lGridCount * g.max_mul:
        if amount > 0:
            TaskInfo.lGridPrice -= lGridValue
        elif amount < 0:
            TaskInfo.lGridPrice += lGridValue
        TaskInfo.lGridPrice = round(TaskInfo.lGridPrice, 3)


def SaveTradeLog(TaskInfo, lPrice, lNum, note):
    with sqlite3.connect(g.file_path) as conn:
        cursor = conn.cursor()
        Status = 1
        szNote = "buy"
        if lNum < 0:
            Status = 2
            szNote = "sell"
        szNote += note
        cursor.execute(
            "INSERT INTO ListTradeLog (TaskName, NickName, Status, OweCount, Price, Count, Note, GridValue, GridPrice, MaxOweCount) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (TaskInfo.szTaskName, TaskInfo.szNickName, Status, TaskInfo.lOweCount,
             lPrice, lNum, szNote, TaskInfo.lGridValue, TaskInfo.lGridPrice, TaskInfo.lMaxOweCount)
        )
        conn.commit()


def LoadTradeLog():
    with sqlite3.connect(g.file_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM ListTradeLog ORDER BY Updatedate DESC LIMIT 5")
        allData = cursor.fetchall()
        for item in allData:
            print(item)


def ClearTradeLog(log_day, ask_day):
    with sqlite3.connect(g.file_path) as conn:
        lTime = datetime.datetime.now() + datetime.timedelta(days=-log_day)
        conn.execute("DELETE FROM ListTradeLog WHERE Updatedate <= ?", (lTime,))
        lTime = datetime.datetime.now() + datetime.timedelta(days=-ask_day)
        conn.execute("DELETE FROM ListTradeAskLog WHERE Updatedate <= ?", (lTime,))
        conn.commit()


#获得表字段名索引
def GetTableIndex(col_name, find_name):
    for index, name in enumerate(col_name):
        if name == find_name:
            return index
    return 1000


def PrintTaskInfo(TaskInfo, index):
    dif = TaskInfo.lNewPrice - TaskInfo.lGridPrice
    dif = round(dif, 2)
    strBuy = ""
    if dif <= -TaskInfo.lGridValue:
        if TaskInfo.lOweCount < TaskInfo.lMaxOweCount:
            strBuy = "-buy"
        if TaskInfo.lOweCount >= TaskInfo.lMaxOweCount:
            if dif <= -TaskInfo.lGridValue:
                strBuy += "-BM"
            else:
                strBuy += "-M"
    str_out = "{}:{}任务:{}-{}{},点{},状态{}-{},持{}/{},格价{},新{}-{}差{}{},量{}".format(
        index, TaskInfo.ID, TaskInfo.szTaskName, TaskInfo.szNickName, TaskInfo.sh,
        TaskInfo.lGridValue, TaskInfo.lStatus, TaskInfo.lDoType,
        TaskInfo.lOweCount, TaskInfo.lMaxOweCount,
        TaskInfo.lGridPrice, TaskInfo.lCur, TaskInfo.lNewPrice, dif, strBuy, TaskInfo.lVol
    )
    str_out += ')'
    if TaskInfo.lSellCount > 0 or TaskInfo.lBuyCount:
        str2 = "卖{}买{}".format(TaskInfo.lSellCount, TaskInfo.lBuyCount)
        str_out += str2

    print(str_out)


def PrintTaskList(dwType, bShow=1):
    if bShow:
        print("任务输出行数=", len(g.TaskList))
    status = 9
    index = 1

    if dwType > 0:
        for TaskInfo in g.TaskList:
            if TaskInfo.lStatus == dwType:
                PrintTaskInfo(TaskInfo, index)
                index += 1
    else:
        for TaskInfo in g.TaskList:
            if TaskInfo.lStatus >= 9:
                PrintTaskInfo(TaskInfo, index)
                index += 1
        print("----")
        for TaskInfo in g.TaskList:
            if TaskInfo.lStatus < 9:
                PrintTaskInfo(TaskInfo, index)
                index += 1

    if bShow:
        print("任务输出结束")


def isDebt(TaskName):
    if TaskName[0:2] == '11':
        return 1
    elif TaskName[0:2] == '12':
        return 2
    return 0


def isFund(TaskName):
    strF = TaskName[0:2]
    strF1 = TaskName[0:1]
    if strF == '51' or strF == '50' or strF == '52' or strF1 == '5':
        return 1
    elif strF == '15' or strF == '16':
        return 2
    return 0


def IsTaskInfo(TaskName):
    for info in g.TaskList:
        if info.szTaskName == TaskName:
            return 1
    return 0


def FindTaskInfoByName(TaskName):
    for info in g.TaskList:
        if info.szTaskName == TaskName:
            return info
    return None


def FindTaskInfoByID(TaskName):
    for info in g.TaskList:
        if info.szTaskName == TaskName:
            return info
    return None


def UpdateTaskInfo(TaskInfo):
    for i, info in enumerate(g.TaskList):
        if info.szTaskName == TaskInfo.szTaskName:
            g.TaskList[i] = TaskInfo
            break


def ClearDataTaskInfo(TaskInfo):
    if TaskInfo is None:
        return


def ResetDayTask(TaskInfo):
    TaskInfo.lDoCount = 0
    TaskInfo.lBuyCount = 0
    TaskInfo.lSellCount = 0
    TaskInfo.lDoType = 0

    g.trade_count = 0
    g.sell_count = 0


def GetLastTime(last_time):
    return (datetime.datetime.now() - last_time).total_seconds()


def AskUserMoney(context):
    pass


def ask_position_list():
    order_list = get_positions()
    return [x for x in order_list if order_list[x].amount != 0]


def CheckUserOrderList():
    #get_open_orders
    order_list = get_all_orders()
    print("检查定单行数=", len(order_list))
    log.info(order_list)
    for order in order_list:
        if order["status"] == "2" or order["status"] == "7":
            #log.info(order)
            symbol = order["symbol"]
            amount = order["amount"]
            print("代码=", symbol, "数量=", "状态=", order["status"])

            TaskInfo = FindTaskInfoByID(symbol)
            if TaskInfo is not None and amount > 0:
                print("定单任务购买=", symbol)
                TaskInfo.lDoType = 1
            elif TaskInfo is not None and amount < 0:
                print("定单任务出售=", symbol)
                TaskInfo.lDoType = 2
    pass


def CheckBonusList():
    #return
    curTime = datetime.datetime.now()
    strDate = curTime.strftime('%Y%m%d')
    print("检测分红,当前时间", curTime.strftime('%Y%m%d'))
    for TaskInfo in g.TaskList:
        print(TaskInfo.lBonusDate.strftime('%Y%m%d'))
        if TaskInfo.lStatus >= 9 and curTime.strftime('%Y%m%d') != TaskInfo.lBonusDate.strftime('%Y%m%d'):

            bonus_item = get_stock_exrights(TaskInfo.szTaskName, curTime.strftime('%Y%m%d'))
            if bonus_item is not None:
                print("分红:", TaskInfo.szTaskName)
                #print(bonus_item.loc[strDate,'bonus_ps'])
                TaskInfo.lBonusDate = datetime.datetime.now()
                SaveTaskPrice(TaskInfo, 1, 1)

    pass


def IsHaveUserOrder(TaskName):
    order_list = get_all_orders()
    for order in order_list:
        if order["status"] == "2" or order["status"] == "7":
            symbol = order["symbol"]
            if len(symbol) >= 6 and symbol[0:6] == TaskName[0:6]:
                return 1
    return 0


def get_position_count(context):
    return len(get_position_list(context))


def get_position_list(context):
    return [x for x in context.portfolio.positions if context.portfolio.positions[x].amount != 0]


def CancelTask(TaskInfo):
    if GetLastTime(TaskInfo.lCancelTime) < 30:
        return
    print("取消定单", TaskInfo.szTaskName)
    TaskInfo.lCancelTime = datetime.datetime.now()
    #SetTaskDoTime(TaskInfo)
    order_list = get_all_orders()
    for order in order_list:
        symbol = order["symbol"]
        amount = order["amount"]
        price = order["price"]
        if (order["status"] == "2" or order["status"] == "7") and symbol[0:6] == TaskInfo.szTaskName[0:6]:
            print("取消定单=", symbol, "价格=", price, "数量=", amount)
            cancel_order_ex(order)

    pass


def IsTimeCancelTask(TaskInfo, lTime):
    if TaskInfo.sh > 0:
        #上 60秒
        if lTime > 180:
            return 1
    else:
        #深 10分钟 防止流量费

        if lTime > 18000:
            return 1

    # else:
    # current_time = datetime.datetime.now()

    # if (current_time > time(14, 0)):
    # return 1

    return 0


def CheckCancelTask(TaskInfo):
    if TaskInfo.lDoType == 3:
        if IsHaveUserOrder(TaskInfo.szTaskName) <= 0:
            print("任务取消状态取消=", TaskInfo.szTaskName)
            TaskInfo.lDoType = 0
            SaveTaskInfo(TaskInfo)
        else:
            CancelTask(TaskInfo)
    elif TaskInfo.lDoType > 0 and GetLastTime(TaskInfo.lDoTime) >= 60:
        SetTaskDoTime(TaskInfo)
        if IsHaveUserOrder(TaskInfo.szTaskName) <= 0:
            print("任务买卖无单取消=", TaskInfo.szTaskName)
            TaskInfo.lDoType = 0
            SaveTaskInfo(TaskInfo)
    elif TaskInfo.lDoType == 1:

        #如果有买单
        print("当前买", TaskInfo.szTaskName)
        g.buy_money += round(TaskInfo.lNewPrice * TaskInfo.lGridCount, 2)
        g.buy_str += ',' + TaskInfo.szTaskName

    pass


def CheckBuyMoneyTask(TaskInfo):
    if TaskInfo.lDoType == 1:
        g.buy_money += TaskInfo.lNewPrice * TaskInfo.lGridCount
        g.buy_str += ',' + TaskInfo.szTaskName
        g.buy_str += ',' + TaskInfo.szNickName
    pass


def SetTaskDoTime(TaskInfo):
    TaskInfo.lDoTime = datetime.datetime.now()
    pass


def CheckOweTaskList(context, bCheck=0):

    g.have_count += 1
    # position_list = get_positions()
    position_list = context.portfolio.positions
    #g.last_log_time = datetime.datetime.now()
    # print("持有=",position_list)

    if GetLastTime(g.lCheckOweTime) >= 30:
        g.lCheckOweTime = datetime.datetime.now()
        print("检查持有 行数=", len(position_list), "时间=", GetLastTime(g.last_log_time))
        for pos in position_list:
            position = position_list[pos]
            # print("持有=",position.sid,"ID=",position.sid[0:6],"数=",position.amount)

            if IsTaskInfo(position.sid) <= 0:
                print("添加持有=", position.sid)
                info = NewTaskInfo()
                info.ID = 0
                info.lNewTask = 1
                info.szTaskName = position.sid
                info.szNickName = ''
                info.lGridPrice = position.last_sale_price
                info.lNewPrice = position.last_sale_price
                info.lOweCount = position.amount
                #if g.is_auto>0 and info.lOweCount==100:

                g.TaskList.append(info)
                InsertTaskInfo(info)
                LoadTaskList(position.sid)

                TaskInfo = FindTaskInfoByID(position.sid)
                CheckTaskInfo(TaskInfo, 0)
                print(TaskInfo)
                print(TaskInfo.szTaskName, "持有=", TaskInfo.lOweCount)
                if g.is_auto > 0 and TaskInfo is not None:
                    amount = position.amount
                    SaveTradeLog(TaskInfo, TaskInfo.lNewPrice, amount, ",no owen check")

                if isDebt(TaskInfo.szTaskName) > 0 and (TaskInfo.lOweCount == 100 or TaskInfo.lOweCount == 150 or TaskInfo.lOweCount == 200):
                    print("auto start new task debt")
                    StartStopTask(TaskInfo.szTaskName, 1)
                elif isFund(TaskInfo.szTaskName) and (TaskInfo.lOweCount == 10000 or TaskInfo.lOweCount == 15000):
                    StartStopTask(TaskInfo.szTaskName, 1)

                print("auto start new task fund", isFund(TaskInfo.szTaskName))

                print("添加持有 代码=", position.sid, "名称=", "持有", position.amount)

            else:
                TaskInfo = FindTaskInfoByID(position.sid)
                TaskInfo.lNewPrice = position.last_sale_price
                TaskInfo.have_count += 1
                # print("修改持有=",position.sid,"ID=",position.sid[0:6],"数=",position.amount)
                if TaskInfo is not None and TaskInfo.lOweCount != position.amount and (bCheck == 1 or GetLastTime(TaskInfo.lTradeTime) >= 30):
                    print("修改持有 代码=", position.sid, "名称=", "格价", TaskInfo.lGridPrice, TaskInfo.szNickName, "持有", position.amount, "原", TaskInfo.lOweCount)
                    if(TaskInfo.lOweCount == 0 and position.amount > 0):
                        TaskInfo.lNewTask = 1
                        amount = position.amount - TaskInfo.lOweCount
                        print("修改持有 数量", amount)
                        if TaskInfo.lDoType > 0:
                            #print("修改持有=2",position.sid)
                            TradeTaskInfo(TaskInfo, amount)
                            TaskInfo.lDoType = 0
                            TaskInfo.lTradeTime = datetime.datetime.now()
                        #print("修改持有=1",position.sid)
                        print("修改持有 参数", amount)
                        TaskInfo.lOweCount = position.amount
                        SaveTaskInfo(TaskInfo)
                        SaveTradeLog(TaskInfo, TaskInfo.lNewPrice, amount, ",owe check")

                    if g.is_auto > 0 and TaskInfo is not None and TaskInfo.lOweCount == 100 and isDebt(TaskInfo.szTaskName) > 0 and TaskInfo.lNewTask > 0:
                        print("auto start have task")
                        StartStopTask(TaskInfo.szTaskName, 1)

    pass


def CheckTaskInfo(TaskInfo, first=0):
    stock = TaskInfo.szTaskName
    if stock.isdecimal() or TaskInfo.ID == 0:
        return
    if g.time_state <= 0:
        return
    # current_time = context.current_dt.time()
    # target_time = time(9, 30)
    # if(current_time <= target_time):
    # return
    if first <= 0:
        if(TaskInfo.szNickName is None or len(TaskInfo.szNickName) <= 0):
            stock_name = get_stock_name(stock)
            TaskInfo.szNickName = stock_name[stock]
            print("查询名称 代码=", stock, "名称=", TaskInfo.szNickName)
            if(len(TaskInfo.szNickName) <= 0):
                return
            TaskInfo.szTaskName = stock
            SaveTaskInfoByID(TaskInfo)

    print("保存名称成功")


def IsTaskStart(TaskInfo):
    if TaskInfo.lStatus < 0 or TaskInfo.lStatus > 9:
        return 0
    if TaskInfo.lStatus <= 1:
        return 0
    if TaskInfo.lGridPrice <= 1 or TaskInfo.lGridPrice > 2000:
        return 0
    if TaskInfo.lGridValue < 0.2 or TaskInfo.lGridValue > 100:
        return 0
    if TaskInfo.lOweCount <= 0:
        TaskInfo.lGridValue = 0
        StartStopTask(TaskInfo.szTaskName, 0)
        # if (isDebt(TaskInfo.szTaskName)):
        # TaskInfo.lGridValue = 0
        # SaveTaskInfoByID(TaskInfo)

        return 0
    if TaskInfo.lGridCount <= 0:
        return 0
    if g.max_buy_count > 0 and (TaskInfo.lBuyCount >= g.max_buy_count or TaskInfo.lSellCount >= g.max_buy_count):
        return 0
    if g.max_trade_count > 0 and (abs(TaskInfo.lSellCount - TaskInfo.lBuyCount) >= g.max_trade_count):
        return 0

    if(TaskInfo.szNickName is None or len(TaskInfo.szNickName) <= 0):
        return 0

    return 1


def IsNoWaitSell(TaskInfo):
    if TaskInfo.lVol >= g.more_vol:
        if TaskInfo.lMaxPrice < 0.001 or TaskInfo.lNewPrice > TaskInfo.lMaxPrice:
            #初始或新高
            if GetLastTime(TaskInfo.lMaxTime) > 20:
                print("新高=", TaskInfo.szNickName, "价=", TaskInfo.lNewPrice, "量=", TaskInfo.lVol)
                TaskInfo.lMaxPrice = TaskInfo.lNewPrice
                TaskInfo.lMaxTime = datetime.datetime.now()
                return 0
            elif GetLastTime(TaskInfo.lMaxTime) < 90:
                #在限制时间内不卖
                return 0
            elif GetLastTime(TaskInfo.lMaxTime) > 1800:
                #超过0.5小时
                TaskInfo.lMaxPrice = TaskInfo.lNewPrice * 1.02
                TaskInfo.lMaxTime = datetime.datetime.now() + datetime.timedelta(seconds=-900)

            return 1


def DoTaskList(context):
    if 1:
        if g.err>0:
            print("服务出错=",g.err)
            return
        print("-------------任务列表开始-------------")
        g.money = context.portfolio.cash
        g.need_money = 0.0
        g.buy_money = 0.0
        g.buy_str = ''
        cur_time = datetime.datetime.now()
        if(GetLastTime(g.last_read_json_time) >15):
            g.last_read_json_time = datetime.datetime.now()
            ReadJsonFile()
        if GetLastTime(g.last_log_time) >=300:
            g.last_log_time = datetime.datetime.now()
            print("定时时间=",cur_time,"现金=",g.money);
            PrintTaskList(0)
        #WriteUserMoney()
        if g.bLastTrade>0 and GetLastTime(g.last_trade_log_time) >=60:
            g.bLastTrade = 0
            g.last_trade_log_time = datetime.datetime.now()
            PrintTaskList(9)
        if GetLastTime(g.last_save_money_time) >60:
            g.last_save_money_time = datetime.datetime.now()
            WriteUserMoney()

        CheckOweTaskList(context,0)
        for TaskInfo in g.TaskList:
            DoTaskItem(context,TaskInfo)
            if g.have_count%10==9 and TaskInfo.have_count==0 and TaskInfo.lOweCount!=0:
                print("持有数量设为0=",TaskInfo.szTaskName);
                TaskInfo.lGridValue = 0
                TaskInfo.lOweCount=0
                TaskInfo.lStatus = 1
                SaveTaskInfo(TaskInfo)
                UpdateTaskInfo(TaskInfo);
                CheckBuyMoneyTask(TaskInfo);
            if(GetLastTime(TaskInfo.lTradeTime)>60):
                GetTaskItemPrice(context,TaskInfo)
        str = "现金{},需{},买{}{},上次{},卖{}买{}".format(g.money,g.need_money,g.buy_money,g.buy_str,g.last_name,g.sell_count,g.trade_count-g.sell_count)
        print(str)
        if g.money!=g.last_money:
            if g.last_money>0:
                WriteUserMoney()
                print("写入现金变动")
            g.last_money =g.money
        print("-------------任务列表结束-------------")
        pass

def isValidStock(snapshot,stock):
    if(snapshot is None):
        return 0
    if not bool(snapshot[stock]):
        return 0
    get_stock = snapshot[stock]
    if(get_stock is None):
        return 0

    return 1

def GetTaskItemPrice(context,TaskInfo):
    TaskInfo.lLastPriceTime = datetime.datetime.now();

    stock = TaskInfo.szTaskName
    snapshot = get_snapshot(stock)
    if(isValidStock(snapshot,stock) == 0):
        return
    #if len(snapshot)<=16：
    #return;
    trade_status = snapshot[stock]['trade_status']
    if trade_status != 'TRADE':
        return
    TaskInfo.lNewPrice = snapshot[stock]['last_px']

    if GetLastTime(TaskInfo.lLastSaveTime)>600:
        TaskInfo.lLastSaveTime = datetime.datetime.now()
        SaveTaskPrice(TaskInfo)

def DoTaskItem(context,TaskInfo):
    TaskInfo.lCur=1
    if IsTaskStart(TaskInfo)<=0:
        return

    TaskInfo.lCur=2
    #print(TaskInfo.szTaskName)
    # 获取实时行情快照
    stock = TaskInfo.szTaskName
    snapshot = get_snapshot(stock)
    #print(snapshot[stock])
    if(isValidStock(snapshot,stock) == 0):
        return
    if not bool(snapshot[stock]):
        return
    TaskInfo.lCur=3
    #print(snapshot)
    trade_status = snapshot[stock]['trade_status']
    #print(trade_status)
    if trade_status != 'TRADE' and trade_status !='ENDTR':
        return

    TaskInfo.lCur=4
    #print("获取快照3",TaskInfo.szTaskName)
    #print(snapshot)
    buy_price = snapshot[stock]['bid_grp'][1][0]
    sell_price = snapshot[stock]['offer_grp'][1][0]
    new_price = snapshot[stock]['last_px']
    TaskInfo.lVol = snapshot[stock]['vol_ratio']
    TaskInfo.lNewPrice = new_price
    TaskInfo.lLastPriceTime = datetime.datetime.now();
    owe_count = TaskInfo.lOweCount
    buy_count = TaskInfo.lGridCount
    cur_time = datetime.datetime.now()
    last_time = (cur_time-TaskInfo.lDoTime).total_seconds();
    last_trade =GetLastTime(TaskInfo.lTradeTime)
    TaskInfo.lLastTime = last_trade
    if buy_price<0.1:
        return
    if (g.min_buy_money >new_price*TaskInfo.lGridCount):
        return
    if (g.max_buy_money <new_price*TaskInfo.lGridCount):
        return

    lDoType = 0
    TaskInfo.lCur=5

    IsNoWaitSell(TaskInfo)
    #print("获取快照4",TaskInfo.szTaskName)
    if last_trade<=30:
        str = "-快照:{}-{},状态{},网{},价{}持{},点{},次{},时{})".format(TaskInfo.szTaskName,TaskInfo.szNickName,TaskInfo.lDoType,TaskInfo.lGridPrice\
        ,new_price,owe_count,TaskInfo.lGridValue,TaskInfo.lDoCount,int(last_trade))
        print(str)
        #print("获取快照1",TaskInfo.szTaskName,"状态",TaskInfo.lDoType,"网时",,"时",last_trade)
    if TaskInfo.lDoType==3:
        print("取消任务开始",TaskInfo.szTaskName)
        CheckCancelTask(TaskInfo)
        SetTaskDoTime(TaskInfo)
        print("取消任务结束=",TaskInfo.szTaskName)
    elif TaskInfo.lDoType==0 and last_trade>=30 and TaskInfo.sh>=0:
        #print("获取快照2",TaskInfo.szTaskName,sell_price)
        TaskInfo.lCur=6
        if TaskInfo.sh<=0:
            c_price=sell_price
            sell_price = new_price
            buy_price = new_price
        if sell_price>=TaskInfo.lGridPrice+TaskInfo.lGridValue and owe_count>=TaskInfo.lGridCount and IsNoWaitSell(TaskInfo)>0:
            TaskInfo.lCur=9
            mul = int((sell_price-TaskInfo.lGridPrice)/TaskInfo.lGridValue)
            if mul>g.max_mul:
                mul = g.max_mul
            buy_count = mul*TaskInfo.lGridCount
            if buy_count>owe_count:
                buy_count = owe_count
            buy_count = -(buy_count)

            print("任务卖出=",TaskInfo.szTaskName,TaskInfo.szNickName,"格价",TaskInfo.lGridPrice,"格点",TaskInfo.lGridValue,"量",buy_count,"价格=",buy_price,"-",sell_price,"持有",owe_count)
            if g.margin>0:
                margin_trade(stock, buy_count, sell_price)
            else:
                order(stock, buy_count, sell_price)
            lDoType = 2
            TaskInfo.lDoType = lDoType
            TaskInfo.lDoTime = datetime.datetime.now();
            TaskInfo.lTradeTime = TaskInfo.lDoTime
            TaskInfo.lCancelTime = TaskInfo.lDoTime
            TaskInfo.lDoPrice = sell_price
        elif owe_count<TaskInfo.lMaxOweCount and buy_price<=TaskInfo.lGridPrice-TaskInfo.lGridValue:
            TaskInfo.lCur=8
            one_price = buy_price*buy_count*1.01
            if g.money>=one_price and one_price>=0.001:
                mul = int((TaskInfo.lGridPrice-buy_price)/TaskInfo.lGridValue)
                can_count = int(g.money/(one_price))
                if mul>g.max_mul:
                    mul = g.max_mul
                if mul>can_count:
                    mul = can_count
                buy_count = mul*TaskInfo.lGridCount
                if buy_count+owe_count>TaskInfo.lMaxOweCount:
                    buy_count = TaskInfo.lMaxOweCount-owe_count

                buy_count = abs(buy_count)

                print("任务买入=",TaskInfo.szTaskName,"格价",TaskInfo.lGridPrice,"格点",TaskInfo.lGridValue,"价格=",buy_price,"-",sell_price,"持有",owe_count)
                if g.margin>0:
                    margin_trade(stock, buy_count, buy_price)
                else:
                    order(stock, buy_count, buy_price)
                g.money -= buy_price*buy_count*1.01
                lDoType = 1
                TaskInfo.lDoType = lDoType
                TaskInfo.lDoTime = datetime.datetime.now();
                TaskInfo.lTradeTime = TaskInfo.lDoTime
                TaskInfo.lCancelTime = TaskInfo.lDoTime
                TaskInfo.lDoPrice = buy_price
            else:
                g.need_money += buy_price*buy_count*1.01
    elif TaskInfo.lDoType==2:
        #print("取消卖",TaskInfo.szTaskName)
        if sell_price<TaskInfo.lGridPrice-TaskInfo.lGridValue:
            print("任务价格取消卖=",TaskInfo.szTaskName,"格价",TaskInfo.lGridPrice,"格点",TaskInfo.lGridValue,"价格=",buy_price,"-",sell_price)
            CancelTask(TaskInfo)
            lDoType = 3
            TaskInfo.lDoType = lDoType
        elif IsTimeCancelTask(TaskInfo,last_time)>0 and sell_price>=TaskInfo.lGridPrice+TaskInfo.lGridValue and sell_price!=TaskInfo.lDoPrice:
            print("任务超时取消卖=",TaskInfo.szTaskName,"格价",TaskInfo.lGridPrice,"格点",TaskInfo.lGridValue,"价格=",buy_price,"-",sell_price)
            CancelTask(TaskInfo)
            lDoType = 3
            TaskInfo.lDoType = lDoType
        else:
            CheckCancelTask(TaskInfo)
    elif TaskInfo.lDoType==1:
        #print("取消买",TaskInfo.szTaskName)
        if buy_price>TaskInfo.lGridPrice + TaskInfo.lGridValue:
            print("任务价格取消买=",TaskInfo.szTaskName,"格价",TaskInfo.lGridPrice,"格点",TaskInfo.lGridValue,"价格=",buy_price,"-",sell_price)
            CancelTask(TaskInfo)
            lDoType = 3
            TaskInfo.lDoType = lDoType
        elif IsTimeCancelTask(TaskInfo,last_time)>0 and buy_price<=TaskInfo.lGridPrice+TaskInfo.lGridValue and buy_price!=TaskInfo.lDoPrice:
            print("任务超时取消买=",TaskInfo.szTaskName,"格价",TaskInfo.lGridPrice,"格点",TaskInfo.lGridValue,"价格=",buy_price,"-",sell_price)
            CancelTask(TaskInfo)
            lDoType = 3
            TaskInfo.lDoType = lDoType
        else:
            print("当前买入",TaskInfo.szTaskName,"价",TaskInfo.lDoPrice)
            CheckCancelTask(TaskInfo)

    if lDoType>0:
        print("更新任务",TaskInfo.szTaskName)
        UpdateTaskInfo(TaskInfo)

    SetTaskDoTime(TaskInfo)
    if GetLastTime(g.last_trade_log_time) >30:
        g.bLastTrade = 1
        g.last_trade_log_time = datetime.datetime.now()
        PrintTaskList(9)
    elif GetLastTime(TaskInfo.lLastSaveTime)>300:
        TaskInfo.lLastSaveTime = datetime.datetime.now()
        SaveTaskPrice(TaskInfo)

    pass

def ClearJsonFile():

    file_path = g.file_json_path

    # print("清除文件数据:",file_path)
    try:
        with open(file_path, 'w') as file:
            # file.truncate(0) # 截断文件到 0 字节
            pass # 不写入任何内容，文件被清空
    except FileNotFoundError:
        print(f"错误：文件未找到 - {file_path}")

def ReadJsonFile():
    file_path = g.file_json_path
    # print("读Json:",file_path)
    try:
        with open(file_path, 'r') as file:
            # result = chardet.detect(f.read())
            # print("文件格式:",result['encoding'])
            lines = file.readlines()
            for line in lines:
                print(line.rstrip())
                ParseJsonText(line.rstrip())
    except FileNotFoundError:
        print(f"错误：文件未找到 - {file_path}")
    except UnicodeDecodeError:
        print(f"错误：文件编码格式不匹配 - {file_path}")

    ClearJsonFile()
    pass

def ParseJsonText(str):
    print("Json:行",str)
    data = json.loads(str)
    # print("Json:解",data)
    dwType = data["dwType"]
    if(dwType is None and dwType == 0):
        return
