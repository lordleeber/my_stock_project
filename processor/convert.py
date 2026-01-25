import os
import glob
import datetime
import polars as pl
from schemas import SCHEMA_COLS
from utils import read_raw_csv, read_sii_indices

RAW_DIR = os.getenv("RAW_DIR", "/app/data/raw")
PROCESSED_DIR = os.getenv("PROCESSED_DIR", "/app/data/processed")

def enforce_schema(df, category):
    if category not in SCHEMA_COLS: return df
    required_cols = SCHEMA_COLS[category]
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        df = df.with_columns([pl.lit(None).alias(col) for col in missing_cols])
    return df.select(required_cols)

def save_dataframe(df, output_dir, output_file, category):
    # 強制對齊 Schema
    df = enforce_schema(df, category)
    os.makedirs(output_dir, exist_ok=True)
    df.write_csv(output_file)

def process_file(file_path, market, category, date_str):
    try:
        # 1. 處理主要資料 (如個股行情)
        output_dir = f"{PROCESSED_DIR}/{category}/date={date_str}"
        output_file = f"{output_dir}/{market}.csv"
        
        # 檢查是否已存在 (略過)
        if not os.path.exists(output_file):
             # 使用共用的讀取邏輯
            df = read_raw_csv(file_path)
            
            if df is not None:
                # ... (原本的過濾邏輯)
                if "symbol" in df.columns: # 確保讀到的是個股資料
                    # 加入日期與市場
                    df = df.with_columns([
                        pl.lit(date_str).str.strptime(pl.Date, "%Y%m%d").alias("date"),
                        pl.lit(market).alias("market")
                    ])
                    
                    # 過濾
                    df = df.filter(pl.col("symbol").is_not_null())
                    df = df.filter(pl.col("symbol") != "")
                    df = df.filter(pl.col("symbol").str.len_chars() <= 10)
                    df = df.filter(pl.col("symbol").str.len_chars() > 1)

                    if "name" in df.columns:
                        df = df.filter(pl.col("name").is_not_null())
                        df = df.filter(pl.col("name") != "")
                    
                    save_dataframe(df, output_dir, output_file, category)
                    print(f"Processed {category}/{date_str}/{market}")
        
        # 2. 特殊處理: 如果是 SII Daily Quotes，額外擷取大盤指數
        if category == "daily_quotes" and market == "sii":
            indices_output_dir = f"{PROCESSED_DIR}/market_indices/date={date_str}"
            indices_output_file = f"{indices_output_dir}/{market}.csv"
            
            if not os.path.exists(indices_output_file):
                df_indices = read_sii_indices(file_path)
                if df_indices is not None and not df_indices.is_empty():
                    df_indices = df_indices.with_columns([
                        pl.lit(date_str).str.strptime(pl.Date, "%Y%m%d").alias("date"),
                        pl.lit(market).alias("market")
                    ])
                    # 指數不需要像個股那樣過濾 symbol 長度
                    save_dataframe(df_indices, indices_output_dir, indices_output_file, "market_indices")
                    print(f"Processed market_indices/{date_str}/{market} (Extracted from daily_quotes)")

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
