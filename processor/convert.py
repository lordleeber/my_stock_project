import os
import glob
import polars as pl
from schemas import COLUMN_MAP, NUMERIC_COLS, SCHEMA_COLS

RAW_DIR = "/app/data/raw"
PROCESSED_DIR = "/app/data/processed"

def find_header_line(file_path, encoding='utf-8-sig'):
    """尋找包含 '證券代號' 或 '代號' 的行數"""
    try:
        with open(file_path, 'r', encoding=encoding) as f:
            for i, line in enumerate(f):
                if ("證券代號" in line or "代號" in line) and "," in line:
                    return i
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
    return -1

def clean_dataframe(df):
    """通用清洗邏輯"""
    # 1. 欄位重命名
    valid_cols = [c for c in df.columns if c in COLUMN_MAP]
    df = df.select(valid_cols)
    df = df.rename({c: COLUMN_MAP[c] for c in valid_cols})
    
    # 2. 清洗 Symbol
    if "symbol" in df.columns:
        df = df.with_columns(
            pl.col("symbol")
            .str.replace_all('=|"', '')
            .str.strip_chars()
        )

    # 3. 清洗數值
    for col in df.columns:
        if col in NUMERIC_COLS:
            df = df.with_columns(
                pl.col(col)
                .str.replace_all(",", "")
                .str.replace_all("--", "")
                .str.strip_chars()
                .cast(pl.Float64, strict=False)
            )
            
    return df

def enforce_schema(df, category):
    """強制對齊 Schema (補齊缺失欄位，排序，移除多餘欄位)"""
    if category not in SCHEMA_COLS:
        return df
        
    required_cols = SCHEMA_COLS[category]
    
    # 補齊缺失欄位
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        # 使用 with_columns 一次補齊，效能較佳
        df = df.with_columns([
            pl.lit(None).alias(col) for col in missing_cols
        ])
            
    # 選取並排序欄位 (這會自動丟棄多餘欄位)
    df = df.select(required_cols)
    return df

def process_file(file_path, market, category):
    skip_rows = find_header_line(file_path)
    if skip_rows == -1:
        return

    try:
        # 讀取 CSV
        df = pl.read_csv(file_path, skip_rows=skip_rows, infer_schema_length=0, ignore_errors=True, truncate_ragged_lines=True)
        
        # 清洗
        df = clean_dataframe(df)
        
        # 取得日期
        basename = os.path.basename(file_path)
        date_str = basename.split('.')[0]
        
        if len(date_str) != 8 or not date_str.isdigit():
            return

        # 加入日期與市場欄位
        df = df.with_columns([
            pl.lit(date_str).str.strptime(pl.Date, "%Y%m%d").alias("date"),
            pl.lit(market).alias("market")
        ])
        
        # 強制對齊 Schema (這一步至關重要)
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
    
    # 動態掃描 raw 目錄
    categories = [d for d in os.listdir(RAW_DIR) if os.path.isdir(os.path.join(RAW_DIR, d))]
    
    for category in categories:
        cat_path = os.path.join(RAW_DIR, category)
        markets = [d for d in os.listdir(cat_path) if os.path.isdir(os.path.join(cat_path, d))]
        
        for market in markets:
            files = glob.glob(f"{RAW_DIR}/{category}/{market}/*.csv")
            if not files:
                continue
                
            print(f"Processing {category}/{market} ({len(files)} files)...")
            for f in files:
                process_file(f, market, category)

if __name__ == "__main__":
    main()