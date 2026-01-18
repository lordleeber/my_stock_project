import os
import sys
import time
import requests
import pathlib
import datetime
import pandas as pd
import csv
from io import StringIO, BytesIO
from bs4 import BeautifulSoup
from common.constants import CATEGORY_MAP

# 櫃買中心 (TPEx) API 網址設定
CATEGORY_DIC = {
    "每日收盤行情": "https://www.tpex.org.tw/web/stock/aftertrading/otc_quotes_no1430/stk_wn1430_result.php?l=zh-tw&o=csv&d={date_tw}&se=EW&s=0,asc,0",
    "三大法人買賣金額統計表": "https://www.tpex.org.tw/web/stock/3insti/3insti_summary/3itrdsum_result.php?l=zh-tw&t=D&p=1&d={date_tw}&o=csv",
    "三大法人買賣超日報": "https://www.tpex.org.tw/web/stock/3insti/daily_trade/3itrade_hedge_result.php?l=zh-tw&o=csv&se=EW&t=D&d={date_tw}&s=0,asc",
    "外資及陸資投資持股統計": "MOPS_SPECIAL_HANDLING", # 特殊標記，使用 MOPS 抓取
    "融資融券": "https://www.tpex.org.tw/web/stock/margin_trading/margin_balance/margin_bal_result.php?l=zh-tw&o=csv&charset=UTF-8&d={date_tw}&c=&s=0,asc",
    "融券借券": "https://www.tpex.org.tw/web/stock/margin_trading/margin_sbl/margin_sbl_result.php?l=zh-tw&d={date_tw}&s=0,asc&o=csv",
    "本益比殖利率淨值": "https://www.tpex.org.tw/web/stock/aftertrading/peratio_analysis/pera_result.php?l=zh-tw&o=csv&charset=UTF-8&d={date_tw}&c=&s=0,asc"
}

# 各頁面的 Referer (櫃買中心會檢查這個)
REFERER_DIC = {
    "每日收盤行情": "https://www.tpex.org.tw/web/stock/aftertrading/otc_quotes_no1430/stk_wn1430.php",
    "三大法人買賣金額統計表": "https://www.tpex.org.tw/web/stock/3insti/3insti_summary/3itrdsum.php",
    "三大法人買賣超日報": "https://www.tpex.org.tw/web/stock/3insti/daily_trade/3itrade_hedge.php",
    "外資及陸資投資持股統計": "https://mops.twse.com.tw/mops/web/t13sa150_otc", # MOPS Referer
    "融資融券": "https://www.tpex.org.tw/web/stock/margin_trading/margin_balance/margin_bal.php",
    "融券借券": "https://www.tpex.org.tw/web/stock/margin_trading/margin_sbl/margin_sbl.php",
    "本益比殖利率淨值": "https://www.tpex.org.tw/web/stock/aftertrading/peratio_analysis/pera.php"
}

EMPTY_SIZE_DIC = {
    "每日收盤行情": 105,
    "三大法人買賣金額統計表": 519,
    "三大法人買賣超日報": 512,
    "外資及陸資投資持股統計": 1040,
    "融資融券": 1300,
    "融券借券": 1483,
    "本益比殖利率淨值": 216
}

COMMON_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
}

def to_tw_date(date_str):
    """將 20230301 轉換為 112/03/01"""
    year = int(date_str[0:4]) - 1911
    month = date_str[4:6]
    day = date_str[6:8]
    return f"{year}/{month}/{day}"

def fetch_mops_foreign_hold(date_string, dst_file_path):
    """抓取 MOPS 外資持股統計並轉存 CSV (使用 BeautifulSoup 解析)"""
    url = "https://mopsov.twse.com.tw/server-java/t13sa150_otc"
    year = int(date_string[0:4])
    month = date_string[4:6]
    day = date_string[6:8]
    
    payload = {
        "step": "2",
        "years": str(year),
        "months": month,
        "days": day,
        "bcode": ""
    }
    
    headers = COMMON_HEADERS.copy()
    headers['Content-Type'] = 'application/x-www-form-urlencoded'
    
    try:
        print(f"Fetching MOPS foreign hold for {date_string}...")
        res = requests.post(url, data=payload, headers=headers)
        
        soup = BeautifulSoup(res.content, 'html.parser', from_encoding='big5')
        rows = soup.find_all('tr')
        data = []
        
        for row in rows:
            cols = row.find_all(['td', 'th'])
            cols_text = [ele.get_text(strip=True) for ele in cols]
            if len(cols_text) > 5:
                data.append(cols_text)
        
        if not data:
            print(f"[{date_string}] MOPS data not found (no rows parsed).")
            return

        df = pd.DataFrame(data)
        found_header = False
        for i in range(len(df)):
            row_values = df.iloc[i].astype(str).values
            if any("證券代號" in x for x in row_values):
                df.columns = df.iloc[i]
                df = df.iloc[i+1:]
                found_header = True
                break
        
        if "證券代號" in df.columns:
            df = df[~df['證券代號'].astype(str).str.contains('證券代號', na=False)]
            df = df[~df['證券代號'].astype(str).str.contains('說明|註|因素', na=False)]
        
        df.to_csv(dst_file_path, index=False, encoding='utf-8-sig', quoting=csv.QUOTE_ALL)
        print(f"[{date_string}] OTC Foreign Hold saved to {dst_file_path} ({len(df)} rows)")

    except Exception as e:
        print(f"[{date_string}] Error fetching MOPS data: {e}")

def fetch_data(date_string, category, output_dir):
    date_tw = to_tw_date(date_string)
    
    # 使用英文目錄名稱
    eng_category = CATEGORY_MAP.get(category, category)
    dst_folder = os.path.join(output_dir, "raw", "otc", eng_category)
    pathlib.Path(dst_folder).mkdir(parents=True, exist_ok=True)
    
    dst_file_path = os.path.join(dst_folder, f"{date_string}.csv")
    
    if os.path.exists(dst_file_path):
        print(f"[{date_string}] OTC {eng_category} already exists, skip.")
        return

    if category == "外資及陸資投資持股統計":
        fetch_mops_foreign_hold(date_string, dst_file_path)
        return

    url = CATEGORY_DIC[category].format(date_tw=date_tw)
    headers = COMMON_HEADERS.copy()
    headers['Referer'] = REFERER_DIC.get(category, "https://www.tpex.org.tw/")

    try:
        print(f"Fetching OTC {eng_category} for {date_string}...")
        response = requests.get(url, headers=headers, timeout=30)
        
        if response.status_code == 200 and "404 - 證券櫃檯買賣中心" not in response.text:
            if len(response.content) <= EMPTY_SIZE_DIC.get(category, 0):
                print(f"[{date_string}] OTC {eng_category} is empty or no data.")
            else:
                content = response.content.decode('big5', errors='ignore')
                f_in = StringIO(content)
                reader = csv.reader(f_in)
                f_out = StringIO()
                writer = csv.writer(f_out, quoting=csv.QUOTE_ALL)
                for row in reader:
                    clean_row = [cell.strip() for cell in row]
                    writer.writerow(clean_row)
                with open(dst_file_path, 'w', encoding='utf-8-sig') as f:
                    f.write(f_out.getvalue())
                print(f"[{date_string}] OTC {eng_category} saved and cleaned to {dst_file_path}")
        else:
            print(f"[{date_string}] OTC {eng_category} data not available (404 or missing).")
            
    except Exception as e:
        print(f"[{date_string}] Error fetching OTC {eng_category}: {e}")

def run_scraper(date_list, output_dir, delay=3.0):
    for date_str in date_list:
        if datetime.datetime.strptime(date_str, "%Y%m%d") > datetime.datetime.today():
            continue
        for category in CATEGORY_DIC:
            fetch_data(date_str, category, output_dir)
            time.sleep(delay)

if __name__ == "__main__":
    output_dir = os.getenv("OUTPUT_DIR", "data")
    start_date_env = os.getenv("START_DATE")
    end_date_env = os.getenv("END_DATE")
    if start_date_env and end_date_env:
         start = datetime.datetime.strptime(start_date_env, "%Y%m%d")
         end = datetime.datetime.strptime(end_date_env, "%Y%m%d")
         delta = end - start
         date_list = [(start + datetime.timedelta(days=i)).strftime("%Y%m%d") for i in range(delta.days + 1)]
    else:
        date_list = [datetime.datetime.today().strftime("%Y%m%d")]
    delay = float(os.getenv("FETCH_DELAY", "3.0"))
    run_scraper(date_list, output_dir, delay)