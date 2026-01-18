import os
import glob
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
        
        # 強制對齊 Schema
        df = enforce_schema(df, category)
        
        # 儲存
        output_dir = f"{PROCESSED_DIR}/{category}/date={date_str}"
        os.makedirs(output_dir, exist_ok=True)
        
        output_file = f"{output_dir}/{market}.parquet"
        df.write_parquet(output_file)

    except Exception as e:
        print(f"Failed to process {file_path}: {e}")

def main():
    print("Starting ETL Pipeline...")
    
    categories = [d for d in os.listdir(RAW_DIR) if os.path.isdir(os.path.join(RAW_DIR, d))]
    
    for category in categories:
        cat_path = os.path.join(RAW_DIR, category)
        # Raw 結構: raw/{category}/date={date}/{market}.csv
        dates = [d for d in os.listdir(cat_path) if d.startswith("date=")]
        
        for date_entry in dates:
            date_str = date_entry.split("=")[1]
            date_path = os.path.join(cat_path, date_entry)
            
            for market_file in os.listdir(date_path):
                if market_file.endswith(".csv"):
                    market = market_file.split(".")[0]
                    process_file(os.path.join(date_path, market_file), market, category, date_str)

if __name__ == "__main__":
    main()