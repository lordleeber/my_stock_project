import os
import sys
import time
import requests
import pathlib
import datetime
import pandas as pd
import csv
from io import StringIO, BytesIO

# 證交所 API 網址設定
CATEGORY_DIC = {
    "每日收盤行情": "https://www.twse.com.tw/exchangeReport/MI_INDEX?response=csv&date={date}&type=ALLBUT0999",
    "三大法人買賣金額統計表": "https://www.twse.com.tw/fund/BFI82U?response=csv&dayDate={date}&type=day",
    "三大法人買賣超日報": "https://www.twse.com.tw/fund/T86?response=csv&date={date}&selectType=ALLBUT0999",
    "外資及陸資投資持股統計": "https://www.twse.com.tw/fund/MI_QFIIS?response=csv&date={date}&selectType=ALLBUT0999",
    "融資融券": "https://www.twse.com.tw/exchangeReport/MI_MARGN?response=csv&date={date}&selectType=ALL",
    "融券借券": "https://www.twse.com.tw/exchangeReport/TWT93U?response=csv&date={date}",
    "本益比殖利率淨值": "https://www.twse.com.tw/exchangeReport/BWIBBU_d?response=csv&date={date}&selectType=ALL"
}

# 最小檔案大小檢查 (避免存下錯誤或空的 CSV)
EMPTY_SIZE_DIC = {
    "每日收盤行情": 0,
    "三大法人買賣金額統計表": 2,
    "三大法人買賣超日報": 2,
    "外資及陸資投資持股統計": 1040,
    "融資融券": 818,
    "融券借券": 1483,
    "本益比殖利率淨值": 2
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def fetch_data(date_string, category, output_dir):
    url = CATEGORY_DIC[category].format(date=date_string)
    # 將資料存放在 raw/sii 子目錄下
    dst_folder = os.path.join(output_dir, "raw", "sii", category)
    pathlib.Path(dst_folder).mkdir(parents=True, exist_ok=True)
    
    dst_file_path = os.path.join(dst_folder, f"{date_string}.csv")
    
    if os.path.exists(dst_file_path):
        print(f"[{date_string}] {category} already exists, skip.")
        return

    try:
        print(f"Fetching {category} for {date_string}...")
        response = requests.get(url, headers=HEADERS, timeout=30)
        if response.status_code == 200:
            if len(response.content) <= EMPTY_SIZE_DIC.get(category, 0):
                print(f"[{date_string}] {category} is empty or no data.")
            else:
                # 清理邏輯：去除欄位空白並加上引號
                content = response.content.decode('big5', errors='ignore')
                f_in = StringIO(content)
                reader = csv.reader(f_in)
                
                f_out = StringIO()
                writer = csv.writer(f_out, quoting=csv.QUOTE_ALL)
                
                for row in reader:
                    # 去除每個單元格的首尾空白
                    clean_row = [cell.strip() for cell in row]
                    writer.writerow(clean_row)
                
                with open(dst_file_path, 'w', encoding='utf-8-sig') as f:
                    f.write(f_out.getvalue())
                    
                print(f"[{date_string}] {category} saved and cleaned to {dst_file_path}")
        else:
            print(f"[{date_string}] Failed to fetch {category}. Status code: {response.status_code}")
    except Exception as e:
        print(f"[{date_string}] Error fetching {category}: {e}")

def get_date_list():
    # 優先從環境變數獲取日期範圍
    start_date_env = os.getenv("START_DATE")
    end_date_env = os.getenv("END_DATE")
    
    if start_date_env and end_date_env:
        print(f"Using date range from env: {start_date_env} to {end_date_env}")
        start = datetime.datetime.strptime(start_date_env, "%Y%m%d")
        end = datetime.datetime.strptime(end_date_env, "%Y%m%d")
        delta = end - start
        return [(start + datetime.timedelta(days=i)).strftime("%Y%m%d") for i in range(delta.days + 1)]
    
    # 次之讀取本地檔案
    open_date_file = os.getenv("OPEN_DATE_FILE", "date_info/open_date_2023.txt")
    if os.path.exists(open_date_file):
        print(f"Reading dates from {open_date_file}")
        with open(open_date_file, 'r') as f:
            return [line.strip() for line in f.readlines() if line.strip()]
    
    print("No date source found. Defaulting to today.")
    return [datetime.datetime.today().strftime("%Y%m%d")]

def run_scraper(date_list, output_dir, delay=3.0):
    for date_str in date_list:
        # 簡單過濾：不抓未來的日期
        if datetime.datetime.strptime(date_str, "%Y%m%d") > datetime.datetime.today():
            continue
            
        for category in CATEGORY_DIC:
            fetch_data(date_str, category, output_dir)
            time.sleep(delay) # 避免過快請求被封鎖

if __name__ == "__main__":
    output_dir = os.getenv("OUTPUT_DIR", "data")
    date_list = get_date_list()
    
    # 增加延遲時間以規避 Rate Limit (可透過環境變數調整)
    delay = float(os.getenv("FETCH_DELAY", "3.0"))

    run_scraper(date_list, output_dir, delay)
