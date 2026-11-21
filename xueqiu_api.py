import requests,json

# 用来给股票代码添加前缀，已废弃
def add_exchange(shares):
    shares_str = str(shares)
    if (shares_str[:2] == "00") or (shares_str[:3] == "200") or (shares_str[:3] == "300"):
        r_data = "sz"+shares_str
    elif (shares_str[:2] == "60") or (shares_str[:2] == "51") or (shares_str[:3] == "900") or (shares_str[:2] == "68"):
        r_data = "sh"+shares_str
    else:
        r_data = ""
    return r_data

# 处理返回的数据
def xueqiu_analysis_return(dat):
    jdat = json.loads(dat)
    rdat = []
    for n in jdat['data']:
        ndic = {}
        # 股票代码
        ndic['code'] = n['symbol']
        # 现价
        ndic['current'] = n['current']
        # 涨幅百分比
        ndic['percent'] = n['percent']
        # 涨幅
        ndic['chg'] = n['chg']
        # 最高价
        ndic['high'] = n['high']
        # 最低价
        ndic['low'] = n['low']
        # 今日开盘
        ndic['open'] = n['open']
        # 昨日收盘
        ndic['last_close'] = n['last_close']

        rdat.append(ndic)
    return rdat
def xueqiu_api(shares_lis):
    he = {
        "User-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36 Edg/98.0.1108.62"
    }
    url_parameter = ""
    # 把股票代码拼起来，注意需要大写
    for shares in shares_lis:
        exchange_shares = shares["code"].upper()
        if exchange_shares != "":
            url_parameter = url_parameter + exchange_shares + ","
    
    # 发送API请求
    url = "https://stock.xueqiu.com/v5/stock/realtime/quotec.json?symbol="+url_parameter[:-1]
    r = requests.get(url,headers=he)
    r_dat = r.text
    
    return r_dat

# 持仓情况列表
shares_list = [
        {'code': 'SH511360', 'price': '25.477', 'quantity': '1200'},
        #{'code': 'SH513050', 'price': '1.853', 'quantity': '8100'},
        # {'code': 'SH601231', 'price': '14.372', 'quantity': '800'},
        # {'code': 'SZ002273', 'price': '8.434', 'quantity': '600'},
        # {'code': 'SZ002461', 'price': '9.208', 'quantity': '800'}
    ]

# for n in xueqiu_analysis_return(xueqiu_api(shares_list)):
#     print(n)
