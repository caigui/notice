import time  # Added for cache timestamp handling
import requests
from bs4 import BeautifulSoup  # Added for HTML parsing

# Cache variables
cached_data = None
last_fetch_time = None

def fetch_and_merge_data(urls, cache_duration=600):
    global cached_data, last_fetch_time
    
    # Check if cache is valid
    current_time = time.time()
    if cached_data and (current_time - last_fetch_time < cache_duration):
        return cached_data  # Return cached data if still valid

    merged_data = {}
    for url in urls:
        try:
            resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding
            
            soup = BeautifulSoup(resp.text, 'html.parser')
            table = soup.find('table', id='estimationtable')
            if table:
                rows = table.find_all('tr')[1:]  # Skip header row
                for row in rows:
                    cells = row.find_all('td')
                    if cells:
                        code = cells[0].get_text(strip=True)[2:]  # Remove first two letters
                        premium_text = cells[-1].get_text(strip=True)
                        if premium_text.strip() == '':  # Check if premium is empty
                            premium = round(float(cells[-3].get_text(strip=True).rstrip('%')) / 100, 3)  # Fallback: use value from two <td> before
                        else:
                            premium = round(float(premium_text.rstrip('%')) / 100, 3)  # Convert percentage to decimal
                        merged_data[code] = premium
        except requests.exceptions.ReadTimeout:
            print(f"Request to {url} timed out. Skipping...")
            continue  # Continue to next URL if timeout occurs

    # Update cache
    cached_data = merged_data
    last_fetch_time = current_time
    # print(merged_data)
    return merged_data

def get_merged_data(cache_duration=600):
    urls = [
        "https://palmmicro.com/woody/res/qdiimixcn.php",
        "https://palmmicro.com/woody/res/chinafuturecn.php",
        "https://palmmicro.com/woody/res/chinaindexcn.php",
        "https://palmmicro.com/woody/res/qdiihkcn.php",
        "https://palmmicro.com/woody/res/qdiijpcn.php",
        "https://palmmicro.com/woody/res/qdiieucn.php",
        "https://palmmicro.com/woody/res/qdiicn.php"
    ]
    return fetch_and_merge_data(urls, cache_duration)


# Entry point
if __name__ == "__main__":
    print(get_merged_data())