"""
集保股權分散表 ETL 處理模組

處理 data/raw/shareholding_div/ 下的資料，合併成單一 CSV 並標準化格式。

使用方式:
    docker compose run --rm processor python convert_shareholding.py

環境變數:
    START_DATE: 起始日期 (YYYYMMDD)
    END_DATE: 結束日期 (YYYYMMDD)
"""

import os
import datetime
import polars as pl

RAW_DIR = os.getenv("RAW_DIR", "/app/data/raw")
PROCESSED_DIR = os.getenv("PROCESSED_DIR", "/app/data/processed")
CATEGORY = "shareholding_div"
OUTPUT_CATEGORY = "shareholding_dispersion"


def parse_number(value: str) -> int:
    """移除千分位逗號並轉為整數"""
    if value is None:
        return None
    return int(str(value).replace(",", ""))


def parse_percentage(value: str) -> float:
    """轉換百分比為浮點數"""
    if value is None:
        return None
    return float(str(value).replace(",", ""))


def process_single_file(file_path: str, symbol: str, date_str: str) -> pl.DataFrame:
    """
    處理單一股票的集保資料 CSV

    Args:
        file_path: CSV 檔案路徑
        symbol: 股票代號
        date_str: 日期字串 (YYYYMMDD)

    Returns:
        處理後的 DataFrame
    """
    try:
        # 讀取 CSV (有 BOM)
        df = pl.read_csv(file_path, encoding="utf-8-sig", infer_schema_length=0)

        if df.is_empty():
            return None

        # 標準化欄位名稱
        # 原始欄位: 序, 持股分級, 人數, 股數, 占集保庫存數比例(%)
        column_map = {
            "序": "level",
            "持股分級": "level_name",
            "人數": "holders",
            "股數": "shares",
            "占集保庫存數比例(%)": "percentage"
        }

        # 只保留需要的欄位
        available_cols = [col for col in column_map.keys() if col in df.columns]
        df = df.select(available_cols)
        df = df.rename({k: v for k, v in column_map.items() if k in df.columns})

        # 轉換數值型別
        df = df.with_columns([
            pl.col("level").cast(pl.Int32),
            pl.col("holders").str.replace_all(",", "").cast(pl.Int64),
            pl.col("shares").str.replace_all(",", "").cast(pl.Int64),
            pl.col("percentage").str.replace_all(",", "").cast(pl.Float64),
        ])

        # 加入日期與股票代號
        df = df.with_columns([
            pl.lit(date_str).str.strptime(pl.Date, "%Y%m%d").alias("date"),
            pl.lit(symbol).alias("symbol")
        ])

        # 調整欄位順序
        df = df.select(["date", "symbol", "level", "level_name", "holders", "shares", "percentage"])

        return df

    except Exception as e:
        print(f"Failed to process {file_path}: {e}")
        return None


def process_date(date_str: str) -> bool:
    """
    處理單一日期的所有股票資料

    Args:
        date_str: 日期字串 (YYYYMMDD)

    Returns:
        是否成功處理
    """
    input_dir = f"{RAW_DIR}/{CATEGORY}/date={date_str}"
    output_dir = f"{PROCESSED_DIR}/{OUTPUT_CATEGORY}/date={date_str}"
    output_file = f"{output_dir}/all.csv"

    # 檢查是否已處理
    if os.path.exists(output_file):
        print(f"Skipping {OUTPUT_CATEGORY}/{date_str} (already exists)")
        return True

    if not os.path.exists(input_dir):
        print(f"Input directory not found: {input_dir}")
        return False

    # 收集所有股票的資料
    all_dfs = []
    csv_files = [f for f in os.listdir(input_dir) if f.endswith(".csv")]

    for csv_file in csv_files:
        symbol = csv_file.replace(".csv", "")
        file_path = os.path.join(input_dir, csv_file)

        df = process_single_file(file_path, symbol, date_str)
        if df is not None and not df.is_empty():
            all_dfs.append(df)

    if not all_dfs:
        print(f"No valid data for {date_str}")
        return False

    # 合併所有資料
    combined_df = pl.concat(all_dfs)

    # 儲存
    os.makedirs(output_dir, exist_ok=True)
    combined_df.write_csv(output_file)

    print(f"Processed {OUTPUT_CATEGORY}/{date_str} ({len(csv_files)} stocks, {combined_df.height} rows)")
    return True


def get_date_range():
    """取得日期範圍"""
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

    print("Starting Shareholding Dispersion ETL...")
    if start_date:
        print(f"Filter Start Date: {start_date.strftime('%Y-%m-%d')}")
    if end_date:
        print(f"Filter End Date: {end_date.strftime('%Y-%m-%d')}")

    # 取得所有日期目錄
    category_path = os.path.join(RAW_DIR, CATEGORY)
    if not os.path.exists(category_path):
        print(f"Category path not found: {category_path}")
        return

    date_dirs = [d for d in os.listdir(category_path) if d.startswith("date=")]

    processed_count = 0
    for date_entry in sorted(date_dirs):
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

        if process_date(date_str):
            processed_count += 1

    print(f"ETL completed. Processed {processed_count} dates.")


if __name__ == "__main__":
    main()
