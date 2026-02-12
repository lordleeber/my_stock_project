import os
import glob
import polars as pl
from utils import read_raw_csv

RAW_DIR = "/app/data/raw"
PROCESSED_DIR = "/app/data/processed"

def verify_file(category, date_str, market):
    raw_path = f"{RAW_DIR}/{category}/date={date_str}/{market}.csv"
    proc_path = f"{PROCESSED_DIR}/{category}/date={date_str}/{market}.parquet"
    
    if not os.path.exists(raw_path):
        return # Raw 檔不存在 (可能被刪了?)
    
    if not os.path.exists(proc_path):
        print(f"❌ Missing processed file: {proc_path}")
        return

    try:
        # 1. 讀取 Raw (使用與 convert 相同的邏輯)
        df_raw = read_raw_csv(raw_path)
        if df_raw is None:
            print(f"⚠️  Skipping validation for {raw_path} (Read failed)")
            return

        # 2. 讀取 Processed
        df_proc = pl.read_parquet(proc_path)
        
        # 3. 比對筆數
        # 注意: 我們的 read_raw_csv 已經做過初步清洗，所以理論上筆數應接近
        # 但 enforce_schema 可能會濾掉完全不符合 schema 的行? (目前 convert_daily.py 沒做行過濾)
        # 唯一可能的差異是 df_raw 可能包含一些全 null 的行
        
        # 過濾掉 symbol 為空的行 (這是最基本的有效資料判斷)
        if "symbol" in df_raw.columns:
            df_raw = df_raw.filter(pl.col("symbol").is_not_null())
            df_raw = df_raw.filter(pl.col("symbol").str.len_chars() > 1)
        if "symbol" in df_proc.columns:
            df_proc = df_proc.filter(pl.col("symbol").is_not_null())

        count_raw = len(df_raw)
        count_proc = len(df_proc)
        
        if count_raw != count_proc:
            # 嚴格比對: 筆數必須完全一致
            print(f"❌ {category}/{date_str}/{market}: Count Mismatch (Raw={count_raw}, Proc={count_proc})")
        
        # 4. 比對數值 (Close Price)
        if "close" in df_proc.columns and "close" in df_raw.columns:
            sum_raw = df_raw["close"].fill_null(0).sum()
            sum_proc = df_proc["close"].fill_null(0).sum()
            
            diff = abs(sum_raw - sum_proc)
            if diff > 1e-6:
                print(f"❌ {category}/{date_str}/{market}: Value Mismatch (Diff={diff:.6f})")
            else:
                pass

    except Exception as e:
        print(f"Error validating {proc_path}: {e}")

def main():
    print("Starting Data Validation...")
    
    # 遍歷 Processed 目錄結構
    # processed/{category}/date={date}/{market}.parquet
    categories = [d for d in os.listdir(PROCESSED_DIR) if os.path.isdir(os.path.join(PROCESSED_DIR, d))]
    
    for category in categories:
        cat_path = os.path.join(PROCESSED_DIR, category)
        dates = [d for d in os.listdir(cat_path) if d.startswith("date=")]
        
        for date_entry in dates:
            date_str = date_entry.split("=")[1]
            date_path = os.path.join(cat_path, date_entry)
            
            for f in os.listdir(date_path):
                if f.endswith(".parquet"):
                    market = f.split(".")[0]
                    verify_file(category, date_str, market)
    
    print("Validation Completed.")

if __name__ == "__main__":
    main()
