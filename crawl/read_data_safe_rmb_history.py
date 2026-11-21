from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
import time
import re

from selenium.webdriver.chrome.options import Options

def get_rmb_history(start_date, end_date):
    # Validate input dates format (YYYY-MM-DD)
    date_pattern = r'^\d{4}-\d{2}-\d{2}$'
    if not re.match(date_pattern, start_date) or not re.match(date_pattern, end_date):
        raise ValueError("Date format should be YYYY-MM-DD")
    
    # Initialize results list
    results = []
    
    # Configure Chrome options (headless mode)
    chrome_options = Options()
    chrome_options.add_argument('--headless')  # 无头模式，后台静默运行，不弹出实体浏览器窗口
    # chrome_options.add_argument('--disable-gpu') # 禁用 GPU 硬件加速，在某些无头环境下可能需要
    # chrome_options.add_argument('--window-size=1920,1080') # 伪装真实桌面显示器分辨率，避免被识别为移动设备或异常尺寸

    # # 核心伪装：设置真实的 User-Agent，防止被识别为无头浏览器默认的 User-Agent
    # # 注意：User-Agent 应定期更新以保持其真实性，以应对网站可能的检测更新
    # chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36')

    # # --- 新增：高级反爬伪装配置 ---
    # # 1. 禁用浏览器正在被自动化程序控制的提示（例如 Chrome 顶部的"Chrome 正在受到自动化测试软件的控制"）
    # chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    # chrome_options.add_experimental_option('useAutomationExtension', False)

    # # 2. 禁用 Blink 引擎中的自动化特征 (window.navigator.webdriver = true)，这是许多 WAF 检测 Selenium 的关键点
    # chrome_options.add_argument('--disable-blink-features=AutomationControlled')

    # 3. 避免加载图片，可以加快页面加载速度，并减少网络流量（可选，根据需求决定是否开启）
    # chrome_options.add_argument('--blink-settings=imagesEnabled=false')

    # 4. (可选) 配置代理，强烈建议用于访问海外网站
    # chrome_options.add_argument('--proxy-server=http://127.0.0.1:10808')
    
    # Start browser
    # 
    CHROME_DRIVER_EXE_PATH = r"C:\Program Files\Google\Chrome\Application\driver\chromedriver.exe" # <-- 在这里指定你的 chromedriver.exe 路径
    service = Service(executable_path=CHROME_DRIVER_EXE_PATH)
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    try:
        # Open target webpage
        url = "https://www.safe.gov.cn/safe/rmbhlzjj/index.html"
        print(f"正在打开网页: {url}")
        driver.get(url)
        print("网页已打开。")
        
        # Switch to iframe
        wait = WebDriverWait(driver, 30)
        wait.until(EC.presence_of_element_located((By.TAG_NAME, 'iframe')))
        iframe = driver.find_element(By.TAG_NAME, 'iframe')
        driver.switch_to.frame(iframe)
        
        # Locate date input boxes
        wait.until(EC.presence_of_element_located((By.ID, 'startDateId')))
        start_date_input = driver.find_element(By.ID, 'startDateId')
        end_date_input = driver.find_element(By.ID, 'endDateId')
        
        # Clear and input dates safely using send_keys instead of execute_script
        start_date_input.clear()
        start_date_input.send_keys(start_date)
        end_date_input.clear()
        end_date_input.send_keys(end_date)
        
        # Locate and click search button
        search_button = driver.find_element(By.XPATH, '//input[@onclick="javascript:validate()"]')
        search_button.click()
        
        # Wait for query results to load using explicit wait instead of fixed sleep
        wait.until(EC.presence_of_element_located((By.ID, 'InfoTable')))
        
        # Locate table and parse data
        table = driver.find_element(By.ID, 'InfoTable')
        rows = table.find_elements(By.TAG_NAME, 'tr')
        
        # Extract header and data
        header_row = rows[0]
        th_cells = header_row.find_elements(By.TAG_NAME, 'th')
        headers = [cell.text.strip() for cell in th_cells]
        
        # Only extract date and dollar data
        dollar_index = -1
        for i, header in enumerate(headers):
            if '美元' in header:
                dollar_index = i
                break
        
        # Parse data rows
        for row in rows[1:]:
            cells = row.find_elements(By.TAG_NAME, 'td')
            if cells and len(cells) > dollar_index:
                date = cells[0].text.strip()
                dollar_rate = cells[dollar_index].text.strip()
                if date and dollar_rate:
                    row_data = {
                        '日期': date,
                        '美元': dollar_rate
                    }
                    results.append(row_data)
                    
    except Exception as e:
        # Log or handle specific exceptions as needed
        raise e
    finally:
        driver.quit()
    
    return results

if __name__ == '__main__':
    start_date = '2026-03-01'
    end_date = '2026-03-31'
    results = get_rmb_history(start_date, end_date)
    print(results)

    # # 获取最近60天的数据
    # start_date, end_date = get_date_range(60)

    # # 或者指定具体日期
    # start_date = "2026-01-01"
    # end_date = "2026-03-31"