"""
集保股權分散表 ETL 處理模組 (shareholding_div2 格式)

處理 data/raw/shareholding_div2/ 下的單檔 CSV 資料，
轉換為與 shareholding_div 相同的 processed 格式。

raw 格式: TDCC_OD_1-5_YYYYMMDD.csv
  欄位: 資料日期, 證券代號, 持股分級, 人數, 股數, 占集保庫存數比例%

processed 格式: data/processed/shareholding_div/date=YYYYMMDD/all.csv
  欄位: date, symbol, level, level_name, holders, shares, percentage

使用方式:
    docker compose run --rm processor python convert_shareholding2.py

環境變數:
    START_DATE: 起始日期 (YYYYMMDD)
    END_DATE: 結束日期 (YYYYMMDD)
"""

import os
import datetime
import re
import polars as pl

RAW_DIR = os.getenv("RAW_DIR", "/app/data/raw")
PROCESSED_DIR = os.getenv("PROCESSED_DIR", "/app/data/processed")
INPUT_CATEGORY = "shareholding_div2"
OUTPUT_CATEGORY = "shareholding_div"

LEVEL_NAME_MAP = {
    1: "1-999",
    2: "1,000-5,000",
    3: "5,001-10,000",
    4: "10,001-15,000",
    5: "15,001-20,000",
    6: "20,001-30,000",
    7: "30,001-40,000",
    8: "40,001-50,000",
    9: "50,001-100,000",
    10: "100,001-200,000",
    11: "200,001-400,000",
    12: "400,001-600,000",
    13: "600,001-800,000",
    14: "800,001-1,000,000",
    15: "1,000,001以上",
}


def process_file(file_path: str, date_str: str) -> bool:
    """
    處理單一日期的 CSV 檔案

    Args:
        file_path: CSV 檔案路徑
        date_str: 日期字串 (YYYYMMDD)

    Returns:
        是否成功處理
    """
    output_dir = f"{PROCESSED_DIR}/{OUTPUT_CATEGORY}/date={date_str}"
    output_file = f"{output_dir}/all.csv"

    if os.path.exists(output_file):
        print(f"Skipping {date_str} (already exists)")
        return True

    try:
        df = pl.read_csv(file_path, encoding="utf-8-sig", infer_schema_length=0)

        if df.is_empty():
            print(f"No valid data for {date_str}")
            return False

        # 標準化欄位名稱
        # 原始欄位: 資料日期, 證券代號, 持股分級, 人數, 股數, 占集保庫存數比例%
        column_map = {
            "證券代號": "symbol",
            "持股分級": "level",
            "人數": "holders",
            "股數": "shares",
            "占集保庫存數比例%": "percentage",
        }

        df = df.select([col for col in column_map.keys() if col in df.columns])
        df = df.rename({k: v for k, v in column_map.items() if k in df.columns})

        # 轉換數值型別
        df = df.with_columns([
            pl.col("level").cast(pl.Int32),
            pl.col("holders").cast(pl.Int64),
            pl.col("shares").cast(pl.Int64),
            pl.col("percentage").cast(pl.Float64),
        ])

        # 只保留 level 1~15
        df = df.filter(pl.col("level") <= 15)

        # 加入 level_name
        df = df.with_columns(
            pl.col("level").replace_strict(LEVEL_NAME_MAP).alias("level_name")
        )

        # 加入日期
        df = df.with_columns(
            pl.lit(date_str).str.strptime(pl.Date, "%Y%m%d").alias("date")
        )

        # 調整欄位順序 (與 convert_shareholding.py 一致)
        df = df.select(["date", "symbol", "level", "level_name", "holders", "shares", "percentage"])

        # 依 symbol, level 排序
        df = df.sort(["symbol", "level"])

        # 儲存
        os.makedirs(output_dir, exist_ok=True)
        df.write_csv(output_file)

        stock_count = df["symbol"].n_unique()
        print(f"Processed {date_str} ({stock_count} stocks, {df.height} rows)")
        return True

    except Exception as e:
        print(f"Failed to process {file_path}: {e}")
        return False


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

    print("Starting Shareholding Dispersion ETL (div2 format)...")
    if start_date:
        print(f"Filter Start Date: {start_date.strftime('%Y-%m-%d')}")
    if end_date:
        print(f"Filter End Date: {end_date.strftime('%Y-%m-%d')}")

    input_dir = os.path.join(RAW_DIR, INPUT_CATEGORY)
    if not os.path.exists(input_dir):
        print(f"Input directory not found: {input_dir}")
        return

    # 找出所有 CSV 檔案並解析日期
    pattern = re.compile(r"TDCC_OD_1-5_(\d{8})\.csv")
    files = []
    for filename in os.listdir(input_dir):
        match = pattern.match(filename)
        if match:
            files.append((match.group(1), filename))

    files.sort()

    processed_count = 0
    for date_str, filename in files:
        # 日期篩選
        try:
            current_date_obj = datetime.datetime.strptime(date_str, "%Y%m%d")
            if start_date and current_date_obj < start_date:
                continue
            if end_date and current_date_obj > end_date:
                continue
        except ValueError:
            continue

        file_path = os.path.join(input_dir, filename)
        if process_file(file_path, date_str):
            processed_count += 1

    print(f"ETL completed. Processed {processed_count} dates.")


if __name__ == "__main__":
    main()
