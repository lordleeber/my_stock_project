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
        output_file = f"{output_dir}/{market}.parquet"
        
        if os.path.exists(output_file):
            print(f"Skipping {category}/{date_str}/{market} (already exists)")
            return

        # 使用共用的讀取邏輯
        df = read_raw_csv(file_path)
        if df is None:
            return

        # 取得日期 (如果 df 裡面沒有日期欄位，雖然我們有 date_str)
        # 這裡我們信任檔名上的 date_str
        if len(date_str) != 8 or not date_str.isdigit():
            return

        # 加入日期與市場欄位
        df = df.with_columns([
            pl.lit(date_str).str.strptime(pl.Date, "%Y%m%d").alias("date"),
            pl.lit(market).alias("market")
        ])
        
        # 過濾無效資料 (Symbol 為空)
        # 注意: 欄位名稱映射已經在 read_raw_csv -> clean_dataframe 中完成
        # 所以這裡的欄位名稱應該已經是 symbol 了
        if "symbol" in df.columns:
            df = df.filter(pl.col("symbol").is_not_null())
            df = df.filter(pl.col("symbol") != "")
            # Filter out noise (single characters like "M", "、")
            df = df.filter(pl.col("symbol").str.len_chars() > 1)
        
        # 強制對齊 Schema
        df = enforce_schema(df, category)
        
        # 儲存
        os.makedirs(output_dir, exist_ok=True)
        df.write_parquet(output_file)
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