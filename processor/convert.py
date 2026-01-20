import os
import glob
import datetime
import polars as pl
from schemas import SCHEMA_COLS
from utils import read_raw_csv

RAW_DIR = "/app/data/raw"
PROCESSED_DIR = "/app/data/processed"

def enforce_schema(df, category):
    if category not in SCHEMA_COLS: return df
    required_cols = SCHEMA_COLS[category]
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        df = df.with_columns([pl.lit(None).alias(col) for col in missing_cols])
    return df.select(required_cols)

def process_file(file_path, market, category, date_str):
    try:
        # 儲存路徑檢查
        output_dir = f"{PROCESSED_DIR}/{category}/date={date_str}"
        output_file = f"{output_dir}/{market}.csv"
        
        if os.path.exists(output_file):
            print(f"Skipping {category}/{date_str}/{market} (already exists)")
            return

        # 使用共用的讀取邏輯
        df = read_raw_csv(file_path)
        if df is None:
            return

        # 檢查是否成功匹配到 Symbol (代表正確抓取到個股行情而非大盤統計)
        if "symbol" not in df.columns:
            print(f"Warning: No 'symbol' column found in {file_path}. Skipping.")
            return

        # 取得日期
        if len(date_str) != 8 or not date_str.isdigit():
            return

        # 加入日期與市場欄位
        df = df.with_columns([
            pl.lit(date_str).str.strptime(pl.Date, "%Y%m%d").alias("date"),
            pl.lit(market).alias("market")
        ])
        
        # 過濾無效資料 (Symbol 為空或名稱為空)
        df = df.filter(pl.col("symbol").is_not_null())
        df = df.filter(pl.col("symbol") != "")
        
        # 股票代號通常不會超過 10 碼 (排除檔尾長篇說明)
        df = df.filter(pl.col("symbol").str.len_chars() <= 10)
        df = df.filter(pl.col("symbol").str.len_chars() > 1)

        # 有效資料必須有名稱
        if "name" in df.columns:
            df = df.filter(pl.col("name").is_not_null())
            df = df.filter(pl.col("name") != "")
        
        # 強制對齊 Schema
        df = enforce_schema(df, category)
        
        # 儲存
        os.makedirs(output_dir, exist_ok=True)
        df.write_csv(output_file)
        print(f"Processed {category}/{date_str}/{market}")

    except Exception as e:
        print(f"Failed to process {file_path}: {e}")

def get_date_range():
    start_env = os.getenv("START_DATE")
    end_env = os.getenv("END_DATE")
    
    start_date = None
    end_date = None

    if start_env:
        try:
            start_date = datetime.datetime.strptime(start_env, "%Y%m%d")
        except ValueError:
            print(f"Warning: Invalid START_DATE format ({start_env}). Ignoring.")

    if end_env:
        try:
            end_date = datetime.datetime.strptime(end_env, "%Y%m%d")
        except ValueError:
            print(f"Warning: Invalid END_DATE format ({end_env}). Ignoring.")
            
    return start_date, end_date

def main():
    start_date, end_date = get_date_range()
    
    print("Starting ETL Pipeline...")
    if start_date:
        print(f"Filter Start Date: {start_date.strftime('%Y-%m-%d')}")
    if end_date:
        print(f"Filter End Date: {end_date.strftime('%Y-%m-%d')}")
    
    categories = [d for d in os.listdir(RAW_DIR) if os.path.isdir(os.path.join(RAW_DIR, d))]
    
    for category in categories:
        cat_path = os.path.join(RAW_DIR, category)
        # Raw 結構: raw/{category}/date={date}/{market}.csv
        if not os.path.exists(cat_path): continue
        
        dates = [d for d in os.listdir(cat_path) if d.startswith("date=")]
        
        for date_entry in dates:
            date_str = date_entry.split("=")[1]
            
            # 日期篩選
            try:
                current_date_obj = datetime.datetime.strptime(date_str, "%Y%m%d")
                if start_date and current_date_obj < start_date:
                    continue
                if end_date and current_date_obj > end_date:
                    continue
            except ValueError:
                continue

            date_path = os.path.join(cat_path, date_entry)
            
            for market_file in os.listdir(date_path):
                if market_file.endswith(".csv"):
                    market = market_file.split(".")[0]
                    process_file(os.path.join(date_path, market_file), market, category, date_str)

if __name__ == "__main__":
    main()
