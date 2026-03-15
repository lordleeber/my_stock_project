"""
集保股權分散表 ETL 處理模組 (all-in-one 格式)

處理 data/raw/shareholding/ 下的單檔 CSV 資料（可含年份子目錄）。

raw 格式: TDCC_OD_1-5_YYYYMMDD.csv
  欄位: 資料日期, 證券代號, 持股分級, 人數, 股數, 占集保庫存數比例%

processed 格式: data/processed/shareholding/YYYY/YYYYMMDD.csv
  欄位: date, symbol, level, level_name, holders, shares, percentage

使用方式:
    # 處理當前 shareholding 目錄（預設）
    docker compose run --rm processor python convert_weekly.py

環境變數:
    START_DATE: 起始日期 (YYYYMMDD)
    END_DATE: 結束日期 (YYYYMMDD)
    INPUT_CATEGORY: 輸入目錄名稱 (預設: shareholding)
"""

import os
import sys
import datetime
import re
from pathlib import Path
import polars as pl
from .audit_shareholding import ShareholdingChecker
from audit_base import DataQualityError

RAW_DIR = os.getenv("RAW_DIR", "/app/data/raw")
PROCESSED_DIR = os.getenv("PROCESSED_DIR", "/app/data/processed")
FORCE_REPROCESS = os.getenv("FORCE_REPROCESS", "0") == "1"
INPUT_CATEGORY = os.getenv(
    "INPUT_CATEGORY", "shareholding"
)  # 預設使用新的 shareholding 目錄
OUTPUT_CATEGORY = "shareholding"

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
    16: "400萬以上(含)",  # OpenData API 新增
    17: "總計",  # OpenData API 新增
}

# Final output column order (schema) - src_col is generated based on this order
SCHEMA_COLS = [
    "date",
    "symbol",
    "level",
    "level_name",
    "holders",
    "shares",
    "percentage",
]


def generate_src_col(schema_cols, col_mapping):
    """Generate src_col string based on schema column order and column mapping.

    Args:
        schema_cols: Final output column order (excluding lineage columns)
        col_mapping: {english_col_name: 1-based_raw_column_index}

    Returns:
        src_col string in format "x#2#3#x#4#5#6"
    """
    src_col_parts = []
    for col in schema_cols:
        if col in col_mapping:
            src_col_parts.append(str(col_mapping[col]))
        else:
            src_col_parts.append("x")
    return "#".join(src_col_parts)


def process_file(file_path: str, date_str: str) -> bool:
    """
    處理單一日期的 CSV 檔案

    Args:
        file_path: CSV 檔案路徑
        date_str: 日期字串 (YYYYMMDD)

    Returns:
        是否成功處理
    """
    output_dir = f"{PROCESSED_DIR}/{OUTPUT_CATEGORY}/{date_str[:4]}"
    output_file = f"{output_dir}/{date_str}.csv"

    if os.path.exists(output_file) and not FORCE_REPROCESS:
        print(f"Skipping {date_str} (already exists)")
        return True

    try:
        df = pl.read_csv(file_path, encoding="utf-8-sig", infer_schema_length=0)

        if df.is_empty():
            print(f"No valid data for {date_str}")
            sys.exit(1)

        # 標準化欄位名稱
        # 原始欄位: 資料日期, 證券代號, 持股分級, 人數, 股數, 占集保庫存數比例%
        column_map = {
            "證券代號": "symbol",
            "持股分級": "level",
            "人數": "holders",
            "股數": "shares",
            "占集保庫存數比例%": "percentage",
        }

        # Build col_mapping dict {english_col_name: 1-based_raw_column_index}
        original_columns = df.columns
        col_mapping = {}
        for cn_name, en_name in column_map.items():
            if cn_name in original_columns:
                col_mapping[en_name] = (
                    list(original_columns).index(cn_name) + 1
                )  # 1-based

        # Generate src_col using unified pattern (date=x, level_name=x, rest from raw)
        src_col_str = generate_src_col(SCHEMA_COLS, col_mapping)

        df = df.select([col for col in column_map.keys() if col in df.columns])
        df = df.rename({k: v for k, v in column_map.items() if k in df.columns})
        # TDCC symbol 常見右側補空白，統一先去除
        if "symbol" in df.columns:
            df = df.with_columns(
                pl.col("symbol").cast(pl.Utf8).str.strip_chars().alias("symbol")
            )

        # 轉換數值型別
        df = df.with_columns(
            [
                pl.col("level").cast(pl.Int32),
                pl.col("holders").cast(pl.Int64),
                pl.col("shares").cast(pl.Int64),
                pl.col("percentage").cast(pl.Float64),
            ]
        )

        # 重要：先加入追蹤資訊（在過濾 level 16, 17 之前）
        rel_path = (
            str(file_path).split("my_stock_project/")[-1]
            if "my_stock_project/" in str(file_path)
            else str(file_path)
        )

        # 資料從第 2 行開始 (1-based, index 0 is header)
        df = df.with_columns(
            [
                pl.lit(rel_path).alias("src_file"),
                (pl.arange(0, df.height) + 2).alias("src_row"),
                pl.lit(src_col_str).alias("src_col"),
            ]
        )

        # 之後再進行過濾，這樣留下來的 src_row 才會是正確的原始行號
        df = df.filter(pl.col("level") <= 15)

        # 加入 level_name (derived from LEVEL_NAME_MAP, not from raw — marked as 'x' in src_col)
        df = df.with_columns(
            pl.col("level").replace_strict(LEVEL_NAME_MAP).alias("level_name")
        )

        # 加入日期 (processing-added — marked as 'x' in src_col)
        df = df.with_columns(
            pl.lit(date_str).str.strptime(pl.Date, "%Y%m%d").alias("date")
        )

        # 調整欄位順序（並包含追蹤欄位）
        df = df.select(
            [
                "date",
                "symbol",
                "level",
                "level_name",
                "holders",
                "shares",
                "percentage",
                "src_file",
                "src_row",
                "src_col",
            ]
        )

        # 依 symbol, level 排序
        df = df.sort(["symbol", "level"])

        # 儲存
        os.makedirs(output_dir, exist_ok=True)
        df.write_csv(output_file)

        stock_count = df["symbol"].n_unique()
        print(f"Processed {date_str} ({stock_count} stocks, {df.height} rows)")
        return True

    except ValueError as e:
        print(f"Failed to process {file_path}: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Failed to process {file_path}: {e}")
        sys.exit(1)


def get_date_range():
    """取得日期範圍"""
    start_env = os.getenv("START_DATE")
    end_env = os.getenv("END_DATE")

    if not start_env or not end_env:
        print("Error: START_DATE and END_DATE are both required (YYYYMMDD).")
        print("Example: START_DATE=20240102 END_DATE=20240102 python convert_weekly.py")
        sys.exit(1)

    try:
        start_date = datetime.datetime.strptime(start_env, "%Y%m%d")
        end_date = datetime.datetime.strptime(end_env, "%Y%m%d")
    except ValueError:
        print(
            f"Error: Invalid date format (START_DATE={start_env}, END_DATE={end_env}). Expected YYYYMMDD."
        )
        sys.exit(1)

    if start_date > end_date:
        print(
            f"Error: START_DATE must be <= END_DATE (START_DATE={start_env}, END_DATE={end_env})."
        )
        sys.exit(1)

    return start_date, end_date


def main():
    start_date, end_date = get_date_range()

    print("Starting Shareholding Dispersion ETL (all-in-one format)...")
    print(f"Input directory: {INPUT_CATEGORY}")
    if start_date:
        print(f"Filter Start Date: {start_date.strftime('%Y-%m-%d')}")
    if end_date:
        print(f"Filter End Date: {end_date.strftime('%Y-%m-%d')}")

    input_dir = os.path.join(RAW_DIR, INPUT_CATEGORY)
    if not os.path.exists(input_dir):
        print(f"Input directory not found: {input_dir}")
        sys.exit(1)

    # 找出所有 CSV 檔案並解析日期（含子目錄）
    pattern = re.compile(r"TDCC_OD_1-5_(\d{8})\.csv$")
    files = []
    for path in Path(input_dir).rglob("TDCC_OD_1-5_*.csv"):
        match = pattern.match(path.name)
        if match:
            files.append((match.group(1), str(path)))

    files.sort()

    processed_count = 0
    for date_str, file_path in files:
        # 日期篩選
        try:
            current_date_obj = datetime.datetime.strptime(date_str, "%Y%m%d")
            if start_date and current_date_obj < start_date:
                continue
            if end_date and current_date_obj > end_date:
                continue
        except ValueError:
            continue

        if process_file(file_path, date_str):
            processed_count += 1

            # 處理完後立即執行資料品質稽核（只檢查 shareholding）
            print(f"Auditing shareholding data for {date_str}...")

            try:
                checker = ShareholdingChecker(date_str)
                checker.check()
                print(f"✅ Shareholding data quality check passed for {date_str}")
            except DataQualityError as e:
                error_msg = f"Shareholding data quality check failed: {str(e)}"
                print(f"❌ {error_msg}")
                # 立即停止處理，不再處理後續日期
                print(
                    "❌ Processing stopped due to data quality error. Fix the issue and re-run."
                )
                sys.exit(1)

    print(f"ETL completed. Processed {processed_count} dates.")


if __name__ == "__main__":
    main()
