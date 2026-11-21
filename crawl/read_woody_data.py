import asyncio
import aiohttp # 这里的 aiohttp 实际上在方案中不会被直接使用，但保留库引用
from concurrent.futures import ThreadPoolExecutor, as_completed
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
# from webdriver_manager.chrome import ChromeDriverManager # 如果你使用 webdriver_manager，可以取消注释
from selenium.webdriver.chrome.service import Service
import time
import re
import os
from datetime import datetime, timedelta

# --- Selenium 相关的同步函数 ---

def get_est_single_url_sync(url):
    """Extract data from a single URL using Selenium in a blocking manner."""
    print(f"Starting Selenium for URL: {url}")
    results = []
    
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    # chrome_options.add_argument('--disable-gpu') # 通常在 headless 模式下有用
    # chrome_options.add_argument('--window-size=1920,1080')
    # chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36')
    # chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    # chrome_options.add_experimental_option('useAutomationExtension', False)
    # chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    # chrome_options.add_argument('--proxy-server=http://127.0.0.1:10808') # 如果需要代理

    # !!! 重要：请确保 chromedriver.exe 的路径是正确的 !!!
    # 如果使用 webdriver_manager，可以这样配置：
    # service = Service(ChromeDriverManager().install()) 
    # 否则，手动指定路径：
    CHROME_DRIVER_EXE_PATH = r"C:\Program Files\Google\Chrome\Application\driver\chromedriver.exe" # <-- 请务必替换为你的 chromedriver.exe 路径
    if not os.path.exists(CHROME_DRIVER_EXE_PATH):
        raise FileNotFoundError(f"ChromeDriver not found at: {CHROME_DRIVER_EXE_PATH}. Please ensure it's installed and the path is correct.")
    service = Service(executable_path=CHROME_DRIVER_EXE_PATH)
    
    driver = None # 初始化 driver 为 None
    try:
        driver = webdriver.Chrome(service=service, options=chrome_options)
        print(f"正在打开网页: {url}")
        driver.get(url)
        print("网页已打开。")
        
        wait = WebDriverWait(driver, 30)
        wait.until(EC.presence_of_element_located((By.ID, 'estimationtable')))
        
        table = driver.find_element(By.ID, 'estimationtable')
        rows = table.find_elements(By.TAG_NAME, 'tr')
        
        header_row = rows[0]
        th_cells = header_row.find_elements(By.TAG_NAME, 'th')
        headers = [cell.text.strip() for cell in th_cells]
        
        # 找到列的索引，确保即使顺序变化也能正确解析
        indices = {
            '代码': -1, '官方EST': -1, 'EST日期': -1, '官方溢价': -1,
            '参考EST': -1, '参考溢价': -1, '实时EST': -1, '实时溢价': -1
        }
        
        for i, header in enumerate(headers):
            if '代码' in header and indices['代码'] == -1:
                indices['代码'] = i
            elif '官方EST' in header and indices['官方EST'] == -1:
                indices['官方EST'] = i
            elif 'EST日期' in header and indices['EST日期'] == -1:
                indices['EST日期'] = i
            # 查找参考EST和实时EST first
            elif '参考EST' in header and indices['参考EST'] == -1:
                indices['参考EST'] = i
            elif '实时EST' in header and indices['实时EST'] == -1:
                indices['实时EST'] = i

        # 现在基于已找到的EST列索引来查找对应的溢价列
        for i, header in enumerate(headers):
            if '溢价' in header:
                # 根据位置关系来判断哪个溢价属于哪个EST
                if indices['官方EST'] != -1 and i == indices['官方EST'] + 2:
                    indices['官方溢价'] = i
                elif indices['参考EST'] != -1 and i == indices['参考EST'] + 1:
                    indices['参考溢价'] = i
                elif indices['实时EST'] != -1 and i == indices['实时EST'] + 1:
                    indices['实时溢价'] = i

        # print(f"Indices found: {indices}") # 调试用

        for row in rows[1:]:
            cells = row.find_elements(By.TAG_NAME, 'td')
            row_data = {
                '代码': "", '官方EST': "", 'EST日期': "", '官方溢价': "",
                '参考EST': "", '参考溢价': "", '实时EST': "", '实时溢价': "",
                'URL': url
            }
            
            # 解析单元格数据 - only if the column index exists in this row
            if indices['代码'] != -1 and indices['代码'] < len(cells):
                try:
                    link_element = cells[indices['代码']].find_element(By.TAG_NAME, 'a')
                    code_raw = link_element.text.strip()
                    # 移除SH, SZ前缀，只保留数字代码
                    if code_raw.startswith(('SH', 'SZ')):
                        code_raw = code_raw[2:]
                    row_data['代码'] = code_raw
                except: pass # 忽略解析错误，可能是没有a标签等

            if indices['官方EST'] != -1 and indices['官方EST'] < len(cells):
                official_est_element = cells[indices['官方EST']].find_elements(By.TAG_NAME, 'font')
                row_data['官方EST'] = official_est_element[0].text.strip() if official_est_element else cells[indices['官方EST']].text.strip()
            
            if indices['EST日期'] != -1 and indices['EST日期'] < len(cells):
                row_data['EST日期'] = cells[indices['EST日期']].text.strip()
            
            if indices['官方溢价'] != -1 and indices['官方溢价'] < len(cells):
                premium_element = cells[indices['官方溢价']].find_elements(By.TAG_NAME, 'font')
                row_data['官方溢价'] = premium_element[0].text.strip() if premium_element else cells[indices['官方溢价']].text.strip()
            
            if indices['参考EST'] != -1 and indices['参考EST'] < len(cells):
                ref_est_element = cells[indices['参考EST']].find_elements(By.TAG_NAME, 'font')
                # Check if the cell is actually empty
                cell_text = cells[indices['参考EST']].text.strip()
                row_data['参考EST'] = ref_est_element[0].text.strip() if ref_est_element and cell_text else ""
            
            if indices['参考溢价'] != -1 and indices['参考溢价'] < len(cells):
                ref_premium_element = cells[indices['参考溢价']].find_elements(By.TAG_NAME, 'font')
                # Check if the cell is actually empty
                cell_text = cells[indices['参考溢价']].text.strip()
                row_data['参考溢价'] = ref_premium_element[0].text.strip() if ref_premium_element and cell_text else ""
            
            if indices['实时EST'] != -1 and indices['实时EST'] < len(cells):
                real_time_est_element = cells[indices['实时EST']].find_elements(By.TAG_NAME, 'font')
                # Check if the cell is actually empty
                cell_text = cells[indices['实时EST']].text.strip()
                row_data['实时EST'] = real_time_est_element[0].text.strip() if real_time_est_element and cell_text else ""
            
            if indices['实时溢价'] != -1 and indices['实时溢价'] < len(cells):
                real_time_premium_element = cells[indices['实时溢价']].find_elements(By.TAG_NAME, 'font')
                # Check if the cell is actually empty
                cell_text = cells[indices['实时溢价']].text.strip()
                row_data['实时溢价'] = real_time_premium_element[0].text.strip() if real_time_premium_element and cell_text else ""
            # 仅添加包含有效数据的行
            if any(row_data.get(key) for key in ['代码', '官方EST', '参考EST', '实时EST']):
                results.append(row_data)
    
    except Exception as e:
        print(f"Error processing {url} in get_est_single_url_sync: {str(e)}")
        # Optionally re-raise or return empty list/error indicator
        # raise e 
    finally:
        if driver:
            driver.quit()
            print(f"Driver quit for {url}")
    
    print(f"Finished Selenium for URL: {url}, found {len(results)} results.")
    return results

# --- 同步的保存函数 ---
def save_results_to_txt(results, filename='woody_data.txt'):
    """Save results to a local text file in the same directory as this script"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    filepath = os.path.join(script_dir, filename)

    # Ensure directory exists
    os.makedirs(script_dir, exist_ok=True)

    # Delete the file if it already exists for a clean save
    if os.path.exists(filepath):
        try:
            os.remove(filepath)
            print(f"Removed existing file: {filepath}")
        except OSError as e:
            print(f"Error removing existing file {filepath}: {e}")

    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            for item in results:
                f.write(str(item) + '\n')
        print(f"Results saved to {filepath}")
    except IOError as e:
        print(f"Error writing to file {filepath}: {e}")

# --- 封装所有同步 I/O 操作 ---
def execute_selenium_tasks_synchronously(urls, filename='woody_data.txt'):
    """
    使用 ThreadPoolExecutor 进行同步并行处理，不依赖 asyncio
    """
    print(f"Starting synchronous execution of Selenium tasks for {len(urls)} URLs.")
    all_results = []
    
    # 限制并发数量，避免开启过多浏览器导致内存溢出
    max_workers = min(len(urls), 3) 
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 提交所有任务
        future_to_url = {executor.submit(get_est_single_url_sync, url): url for url in urls}
        
        # 使用 concurrent.futures.as_completed (同步版本)
        for future in as_completed(future_to_url):
            url = future_to_url[future]
            try:
                # 获取该任务的结果
                result_list = future.result() 
                if isinstance(result_list, list):
                    all_results.extend(result_list)
                    print(f"Successfully collected results from {url}")
            except Exception as exc:
                print(f'{url} generated an exception: {exc}')

    print(f"Finished all Selenium tasks. Collected {len(all_results)} items.")
    # 保存结果
    save_results_to_txt(all_results, filename)
    return all_results
# --- 主的同步函数 ---
def read_and_process_woody_data(filename='woody_data.txt'):
    """
    Reads data from a file or generates it if it doesn't exist or is old.
    This function is now fully synchronous.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    filepath = os.path.join(script_dir, filename)
    
    urls_to_fetch = [
        "https://palmmicro.com/woody/res/qdiimixcn.php",
        "https://palmmicro.com/woody/res/chinafuturecn.php",
        "https://palmmicro.com/woody/res/chinaindexcn.php",
        "https://palmmicro.com/woody/res/qdiihkcn.php",
        "https://palmmicro.com/woody/res/qdiijpcn.php",
        "https://palmmicro.com/woody/res/qdiieucn.php",
        "https://palmmicro.com/woody/res/qdiicn.php"
    ]
    
    should_generate_data = False
    if not os.path.exists(filepath):
        print(f"File '{filename}' does not exist. Generating data...")
        should_generate_data = True
    else:
        mod_time = os.path.getmtime(filepath)
        current_time = time.time()
        if current_time - mod_time > 30 * 60:  # 30 minutes in seconds
            print(f"File '{filename}' is older than 30 minutes. Regenerating data...")
            should_generate_data = True
        else:
            print(f"File '{filename}' exists and is up-to-date.")
    # should_generate_data = False

    if should_generate_data:
        # Call the synchronous function that handles all Selenium tasks and saving
        execute_selenium_tasks_synchronously(urls_to_fetch, filename)
    
    # Wait for the file to be created if it was just generated
    if should_generate_data:
        # Add a short delay to ensure file operations are complete, or a check
        # This loop is more for safety, the ThreadPoolExecutor should have finished
        max_wait_time = 60 # seconds
        start_wait = time.time()
        while not os.path.exists(filepath) and (time.time() - start_wait) < max_wait_time:
            print(f"Waiting for '{filename}' to be ready after generation...")
            time.sleep(2)
        if not os.path.exists(filepath):
            print(f"Error: File '{filename}' was not created after generation attempt.")
            return None # Indicate failure

    # --- Read the file after ensuring it exists ---
    print(f"Reading data from '{filepath}'...")
    merged_data = {}
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        for line in lines:
            line = line.strip()
            if line.startswith("{'代码':"):
                try:
                    # --- 解析单个字典字符串 ---
                    # 使用 eval 是不安全的，强烈建议使用 ast.literal_eval
                    import ast
                    data_dict = ast.literal_eval(line)
                    
                    code = data_dict.get('代码', '')
                    real_time_premium_str = data_dict.get('实时溢价', '')
                    ref_premium_str = data_dict.get('参考溢价', '')
                    official_premium_str = data_dict.get('官方溢价', '')
                    
                    # 提取代码，去除SH/SZ前缀
                    if code.startswith(('SH', 'SZ')):
                        code = code[2:]
                    
                    premium = 0.0
                    # 优先取实时溢价，如果为空则取参考溢价，否则取官方溢价
                    if real_time_premium_str and real_time_premium_str.strip() != '':
                        premium_str = real_time_premium_str
                    elif ref_premium_str and ref_premium_str.strip() != '':
                        premium_str = ref_premium_str
                    elif official_premium_str and official_premium_str.strip() != '':
                        premium_str = official_premium_str
                    else:
                        premium_str = ''
                    
                    if premium_str and premium_str.strip() != '':
                        try:
                            # 移除百分号并转换为浮点数
                            premium = round(float(premium_str.rstrip('%')) / 100, 3)
                        except ValueError:
                            # Handle cases where premium_str is not a valid number
                            print(f"Warning: Could not parse premium '{premium_str}' for code '{code}'. Setting to 0.0.")
                            premium = 0.0
                    
                    merged_data[code] = premium
                except (SyntaxError, ValueError, KeyError, TypeError) as e:
                    print(f"Warning: Could not parse line '{line}': {e}")
                except Exception as e: # Catch any other unexpected errors during parsing
                    print(f"An unexpected error occurred while parsing line '{line}': {e}")

    except FileNotFoundError:
        print(f"Error: File '{filepath}' not found after generation attempt.")
        return None
    except IOError as e:
        print(f"Error reading file '{filepath}': {e}")
        return None
    
    print(f"Successfully read and processed data. Found {len(merged_data)} codes.")
    return merged_data

if __name__ == '__main__':
    print("--- Starting main program ---")
    
    # Call the main synchronous function
    processed_data = read_and_process_woody_data()
    print(processed_data)
    if processed_data is not None:
        print("\n--- Processed Data Snippet ---")
        # Print first 5 items for demonstration
        count = 0
        for code, premium in processed_data.items():
            if count < 5:
                print(f"Code: {code}, Premium: {premium}")
                count += 1
            else:
                break
        print(f"\nTotal codes processed: {len(processed_data)}")
    else:
        print("\nFailed to process data.")
    
    print("--- Program finished ---")