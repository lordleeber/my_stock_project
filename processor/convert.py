import os
import glob
import polars as pl
from schemas import COLUMN_MAP, NUMERIC_COLS, SCHEMA_COLS

RAW_DIR = "/app/data/raw"
PROCESSED_DIR = "/app/data/processed"

def find_header_line(file_path, encoding='utf-8-sig'):
    try:
        with open(file_path, 'r', encoding=encoding) as f:
            for i, line in enumerate(f):
                if ("證券代號" in line or "代號" in line) and "," in line:
                    return i
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
    return -1

def clean_dataframe(df):
    if "symbol" in df.columns:
        df = df.with_columns(
            pl.col("symbol").str.replace_all('=|"', '').str.strip_chars()
        )
    for col in df.columns:
        if col in NUMERIC_COLS:
            df = df.with_columns(
                pl.col(col).str.replace_all(",", "").str.replace_all("--", "").str.strip_chars().cast(pl.Float64, strict=False)
            )
    return df

def enforce_schema(df, category):
    if category not in SCHEMA_COLS: return df
    required_cols = SCHEMA_COLS[category]
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        df = df.with_columns([pl.lit(None).alias(col) for col in missing_cols])
    return df.select(required_cols)

def process_file(file_path, market, category, date_str):
    skip_rows = find_header_line(file_path)
    if skip_rows == -1: return

    try:
        df = pl.read_csv(file_path, skip_rows=skip_rows, infer_schema_length=0, ignore_errors=True, truncate_ragged_lines=True)
        valid_cols = [c for c in df.columns if c in COLUMN_MAP]
        df = df.select(valid_cols).rename({c: COLUMN_MAP[c] for c in valid_cols})
        df = clean_dataframe(df)
        df = df.with_columns([
            pl.lit(date_str).str.strptime(pl.Date, "%Y%m%d").alias("date"),
            pl.lit(market).alias("market")
        ])
        df = enforce_schema(df, category)
        
        output_dir = f"{PROCESSED_DIR}/{category}/date={date_str}"
        os.makedirs(output_dir, exist_ok=True)
        df.write_parquet(f"{output_dir}/{market}.parquet")
    except Exception as e:
        print(f"Failed to process {file_path}: {e}")

def main():
    print("Starting ETL Pipeline...")
    # 新結構: data/raw/{category}/date={date}/{market}.csv
    categories = [d for d in os.listdir(RAW_DIR) if os.path.isdir(os.path.join(RAW_DIR, d))]
    for category in categories:
        cat_path = os.path.join(RAW_DIR, category)
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
