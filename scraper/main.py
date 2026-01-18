import os
import datetime
import sys
import pandas_market_calendars as mcal
import fetch_daily_sii
import fetch_daily_otc

def get_date_list():
    start_date_env = os.getenv("START_DATE")
    end_date_env = os.getenv("END_DATE")
    
    # 若未指定日期，預設為今天
    if not start_date_env:
        start_date_env = datetime.datetime.today().strftime("%Y%m%d")
    if not end_date_env:
        end_date_env = datetime.datetime.today().strftime("%Y%m%d")

    try:
        # 轉換格式檢查
        start = datetime.datetime.strptime(start_date_env, "%Y%m%d")
        end = datetime.datetime.strptime(end_date_env, "%Y%m%d")
        
        print(f"Checking trading days between {start_date_env} and {end_date_env}...")
        
        # 使用 pandas_market_calendars 獲取台股交易日 (XTAI)
        twse = mcal.get_calendar('XTAI')
        schedule = twse.schedule(start_date=start, end_date=end)
        
        valid_dates = schedule.index.strftime('%Y%m%d').tolist()
        return valid_dates

    except ValueError:
        print("Error: Invalid date format. Please use YYYYMMDD.")
        sys.exit(1)
    except Exception as e:
        print(f"Error getting calendar: {e}")
        sys.exit(1)

if __name__ == "__main__":
    # 設定參數
    output_dir = os.getenv("OUTPUT_DIR", "data")
    market_type = os.getenv("MARKET_TYPE", "ALL").upper()  # SII, OTC, ALL
    delay = float(os.getenv("FETCH_DELAY", "3.0"))
    
    date_list = get_date_list()
    
    if not date_list:
        print("No valid trading days found in the specified range.")
        sys.exit(0)

    print(f"Target Dates ({len(date_list)} days): {date_list}")
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