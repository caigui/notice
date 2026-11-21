import datetime
import requests
import time
from selenium import webdriver
from selenium.webdriver import Edge
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.service import Service

def output_excel(df, name):
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"{name}_{timestamp}.xlsx"
    df.to_excel(output_file, index=False)


def get_response(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    return requests.get(url, headers=headers).json()


def post_response(url, data):
    # headers = {
    #     "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    # }
    headers = {
        'authority': 'www.jisilu.cn',
        'accept': 'application/json, text/javascript, */*; q=0.01',
        'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6,zh-TW;q=0.5',
        'cache-control': 'no-cache',
        'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
        # 'cookie': 'kbz_newcookie=1; kbzw__Session=loc35k01i39hdfjf7ec7uv5r60; Hm_lvt_164fe01b1433a19b507595a43bf58262=1682751791,1682751862,1682752839; Hm_lpvt_164fe01b1433a19b507595a43bf58262=1682754715',
        'origin': 'https://www.jisilu.cn',
        'pragma': 'no-cache',
        'referer': 'https://www.jisilu.cn/account/login/',
        'sec-ch-ua': '"Chromium";v="112", "Microsoft Edge";v="112", "Not:A-Brand";v="99"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36 Edg/112.0.1722.64',
        'x-requested-with': 'XMLHttpRequest',
    }  
    cookies = {
        'Hm_lpvt_164fe01b1433a19b507595a43bf58262': '1770858635',
        'Hm_lvt_164fe01b1433a19b507595a43bf58262': '1770618285,1770800381,1770801586,1770858614',
        'HMACCOUNT':'541BCC8A0A6F6C16',
        'kbz_newcookie': '1',
        'kbzw__Session': 'igrimdnd3tu8n2eu2klsko2h77',
    }
    return requests.post(url, data, cookies=cookies, headers=headers)

def get_jsl_cookie():
    # Check if cookie is already cached and not expired (30 minutes = 1800 seconds)
    current_time = time.time()
    if hasattr(get_jsl_cookie, '_cached_cookie') and \
       hasattr(get_jsl_cookie, '_cache_time') and \
       (current_time - get_jsl_cookie._cache_time < 1800):
        return get_jsl_cookie._cached_cookie
    # 不打开浏览器
    options = webdriver.EdgeOptions()
    options.add_argument('headless')
    options.add_argument('disable-gpu')
    service = Service(r'C:\Program Files (x86)\Microsoft\Edge\Application\msedgedriver.exe')
    web = webdriver.Edge(service=service, options=options)
    # 打开浏览器
    # web = webdriver.Edge()
    
    # 登陆
    web.get('https://www.jisilu.cn/account/login/') # 打开登陆页
    web.find_element(By.XPATH,'/html/body/div[3]/div/div/div[1]/div[1]/div[3]/form/div[2]/input').send_keys('17300260592')   # 填入账号
    web.find_element(By.XPATH,'/html/body/div[3]/div/div/div[1]/div[1]/div[3]/form/div[3]/input').send_keys('caigui03902456')  # 填入密码
    web.find_element(By.XPATH,'/html/body/div[3]/div/div/div[1]/div[1]/div[3]/form/div[5]/div[1]/input').click()    # 勾选记住我
    web.find_element(By.XPATH,'/html/body/div[3]/div/div/div[1]/div[1]/div[3]/form/div[5]/div[2]/input').click()    # 勾选条款
    web.find_element(By.XPATH,'/html/body/div[3]/div/div/div[1]/div[1]/div[3]/form/div[6]/a').click()   # 点击登陆
    time.sleep(0.2)
    
    # 登陆后要爬取https://www.jisilu.cn/data/cbnew/cb_list_new/的数据，修改下面代码
    web.get('https://www.jisilu.cn/data/cbnew/cb_list_new/')
    
    # 获取cookie
    cookie = web.get_cookies()
    cookie_str = '; '.join([str(x['name']) + '=' + str(x['value']) for x in cookie])
    print("cookie_str: {}",cookie_str)
    # Cache the cookie value and timestamp
    get_jsl_cookie._cached_cookie = cookie_str
    get_jsl_cookie._cache_time = current_time
    # 关闭浏览器
    web.quit()
    return cookie_str

def get_jsl_cookie2():
    # Get current timestamp and convert to int for cookie
    current_timestamp = int(datetime.datetime.now().timestamp())
    cookie =f'kbzw__Session=pi67k62vhh573cuulpq5mvvu75; Hm_lvt_164fe01b1433a19b507595a43bf58262=1776395907; HMACCOUNT=541BCC8A0A6F6C16; kbz_newcookie=1; kbzw__user_login=7Obd08_P1ebax9aXwZOqmrCorKuRpIKvpuXK7N_u0ejF1dSerMegwtfdrMqqn6qVr5rcqaqwx9PDpt3bz6qdrpqnlqyYrqXW2cXS1qCbq6KtlK2amLKgubXOvp-qrKCvn7CXr5KpmK6ltrG_0aTC2PPV487XkKylo5iJx8ri3eTg7IzFtpaSp6Wjs4HHyuKvqaSZ5K2Wn4G45-PkxsfG1sTe3aihqpmklK2Xm8OpxK7ApZXV4tfcgr3G2uLioYGzyebo4s6onauZpJGlp6GogcPC2trn0qihqpmklK2XuNzIn5KosKOZp5ylkg..; Hm_lpvt_164fe01b1433a19b507595a43bf58262={current_timestamp}'
    return 'kbz_newcookie=1; kbzw__user_login=7Obd08_P1ebax9aXwZOqmrCorKuRpIKvpuXK7N_u0ejF1dSerMegwtfdrMqqn6qVr5rcqaqwx9PDpt3bz6qdrpqnlqyYrqXW2cXS1qCbq6KtlK2amLKgubXOvp-qrKCvn7CXr5KpmK6ltrG_0aTC2PPV487XkKylo5iJx8ri3eTg7IzFtpaSp6Wjs4HHyuKvqaSZ5K2Wn4G45-PkxsfG1sTe3aihqpmklK2Xm8OpxK7ApZXV4tfcgr3G2uLioYGzyebo4s6onauZpJGlp6GogcPC2trn0qihqpmklK2XuNzIn5KosKOZp5ylkg..; kbzw__Session=hmuddbb93puhrr8bl9bueee1h5; Hm_lvt_164fe01b1433a19b507595a43bf58262=1776395907,1776664690; Hm_lpvt_164fe01b1433a19b507595a43bf58262=1776664690; HMACCOUNT=541BCC8A0A6F6C16' # TODO document.cookie
    # Check if cookie is already cached
    if hasattr(get_jsl_cookie, '_cached_cookie'):
        return get_jsl_cookie._cached_cookie
    
    url = "https://www.jisilu.cn/webapi/account/login_process/"
    data = {
        'return_url': 'https://www.jisilu.cn/',
        "user_name": "488dde76a882e64413a6d961128fdc1b",
        "password": "3c608ac416aaf35fcc636d837176fb16",
        "auto_login":"1",
        "aes":"1",
    }
    response = post_response(url, data)
    # print(response.headers)
    cookie_value = response.headers.get("Set-Cookie")
    
    # Cache the cookie value
    get_jsl_cookie._cached_cookie = cookie_value
    return cookie_value


if __name__ == "__main__":
    jsl_cookie = get_jsl_cookie()
    print(jsl_cookie)
    # jsl_cookie="kbzw__user_login=deleted; expires=Thu, 01-Jan-1970 00:00:01 GMT; path=/, kbzw__user_login=7Obd08_P1ebax9aXwZOqmrCorKuRpIKvpuXK7N_u0ejF1dSerMegwtfdrMqqn6qVr5rcqaqwx9PDpt3bz6qdrpqnlqyYrqXW2cXS1qCbq6KtlK2amLKgubXOvp-qrKCvn6qSp5WvmK6ltrG_0aTC2PPV487XkKylo5iJx8ri3eTg7IzFtpaSp6Wjs4HHyuKvqaSZ5K2Wn4G45-PkxsfG1sTe3aihqpmklK2Xm8OpxK7ApZXV4tfcgr3G2uLioYGzyebo4s6onaiUpJGlp6GogcPC2trn0qihqpmklK2XuNzIn5Klq6OZp52ulKiPras.; expires=Thu, 23-Apr-2026 09:02:28 GMT; path=/"
    from qdii_jsl import qdii_e_index_jsl, qdii_e_comm_jsl, qdii_a_index_jsl 

    qdii_e_index_jsl_df = qdii_e_index_jsl(jsl_cookie)
    print(qdii_e_index_jsl_df)

    qdii_e_comm_jsl_df = qdii_e_comm_jsl(jsl_cookie)
    print(qdii_e_comm_jsl_df)


jsl_cookie = ""