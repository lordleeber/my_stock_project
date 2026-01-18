import os
import datetime
import sys
import fetch_daily_sii
import fetch_daily_otc

def get_date_list():
    start_date_env = os.getenv("START_DATE")
    end_date_env = os.getenv("END_DATE")
    
    if start_date_env and end_date_env:
        try:
            start = datetime.datetime.strptime(start_date_env, "%Y%m%d")
            end = datetime.datetime.strptime(end_date_env, "%Y%m%d")
            delta = end - start
            return [(start + datetime.timedelta(days=i)).strftime("%Y%m%d") for i in range(delta.days + 1)]
        except ValueError:
            print("Error: Invalid date format. Please use YYYYMMDD.")
            sys.exit(1)
    
    # 如果沒有環境變數，嘗試讀取檔案或預設今天
    open_date_file = os.getenv("OPEN_DATE_FILE", "date_info/open_date_2023.txt")
    if os.path.exists(open_date_file):
        print(f"Reading dates from {open_date_file}")
        with open(open_date_file, 'r') as f:
            return [line.strip() for line in f.readlines() if line.strip()]

    print("No date range specified. Defaulting to today.")
    return [datetime.datetime.today().strftime("%Y%m%d")]

if __name__ == "__main__":
    # 設定參數
    output_dir = os.getenv("OUTPUT_DIR", "data")
    market_type = os.getenv("MARKET_TYPE", "ALL").upper()  # SII, OTC, ALL
    delay = float(os.getenv("FETCH_DELAY", "3.0"))
    
    date_list = get_date_list()
    print(f"Target Dates: {len(date_list)} days from {date_list[0]} to {date_list[-1]}")
    print(f"Market Type: {market_type}")
    print(f"Output Directory: {output_dir}")

    # 執行抓取
    if market_type in ["SII", "ALL"]:
        print("\n=== Starting SII Scraper ===")
        fetch_daily_sii.run_scraper(date_list, output_dir, delay)
    
    if market_type in ["OTC", "ALL"]:
        print("\n=== Starting OTC Scraper ===")
        fetch_daily_otc.run_scraper(date_list, output_dir, delay)
    
    print("\nAll tasks completed.")
