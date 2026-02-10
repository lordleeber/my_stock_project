"""
三大法人買賣超彙總 ETL 處理模組

處理 data/raw/institutional_summary/ 下的資料，標準化欄位名稱並合併 SII/OTC。

用途:
    - AI 模型特徵：市場情緒指標（外資/投信/自營商資金流向）
    - 回測條件：如「外資連續賣超 N 天時不進場」

使用方式:
    docker compose run --rm processor python convert_institutional_summary.py

環境變數:
    START_DATE: 起始日期 (YYYYMMDD)
    END_DATE: 結束日期 (YYYYMMDD)
"""

import os
import datetime
import polars as pl

RAW_DIR = os.getenv("RAW_DIR", "/app/data/raw")
PROCESSED_DIR = os.getenv("PROCESSED_DIR", "/app/data/processed")
CATEGORY = "institutional_summary"

# SII 和 OTC 的機構名稱對應到統一名稱
INSTITUTION_MAP = {
    # SII
    "自營商(自行買賣)": "dealer_self",
    "自營商(避險)": "dealer_hedge",
    "投信": "investment_trust",
    "外資及陸資(不含外資自營商)": "foreign_investors",
    "外資自營商": "foreign_dealer",
    "合計": "total",
    # OTC (名稱略有不同)
    "自營商(自行買賣)\u3000": "dealer_self",
    "自營商(避險)\u3000": "dealer_hedge",
    "外資及陸資(不含自營商)": "foreign_investors",
    "外資及陸資合計": "foreign_total",
    "自營商合計": "dealer_total",
    "三大法人合計*": "total",
    "三大法人合計": "total",
}

# 只保留這些機構（排除重複的彙總列）
KEEP_INSTITUTIONS = [
    "dealer_self",
    "dealer_hedge",
    "investment_trust",
    "foreign_investors",
    "foreign_dealer",
    "total",
]


def get_category_date_dir(base_dir, category, date_str):
    """取得類別日期的目錄路徑，優先使用新結構 yyyy/yyyymmdd，若無則回退至 date=yyyymmdd"""
    new_path = os.path.join(base_dir, category, date_str[:4], date_str)
    if os.path.exists(new_path):
        return new_path
    return os.path.join(base_dir, category, f"date={date_str}")


def process_single_file(file_path: str, market: str, date_str: str) -> pl.DataFrame:
    """
    處理單一市場的法人彙總 CSV

    Args:
        file_path: CSV 檔案路徑
        market: 市場別 (sii/otc)
        date_str: 日期字串 (YYYYMMDD)

    Returns:
        處理後的 DataFrame
    """
    try:
        df = pl.read_csv(file_path, encoding="utf-8-sig", infer_schema_length=0)

        if df.is_empty():
            return None

        # 統一欄位名稱（SII 和 OTC 欄位名不同）
        rename_map = {}
        for col in df.columns:
            col_stripped = col.strip()
            if col_stripped == "單位名稱":
                rename_map[col] = "institution"
            elif "買進" in col_stripped:
                rename_map[col] = "buy"
            elif "賣出" in col_stripped:
                rename_map[col] = "sell"
            elif "差額" in col_stripped or "買賣超" in col_stripped:
                rename_map[col] = "net"

        df = df.select(list(rename_map.keys()))
        df = df.rename(rename_map)

        # 清理機構名稱並對應到統一名稱
        df = df.with_columns(
            pl.col("institution").str.strip_chars().alias("institution")
        )
        df = df.with_columns(
            pl.col("institution").replace(INSTITUTION_MAP).alias("institution")
        )

        # 只保留需要的機構
        df = df.filter(pl.col("institution").is_in(KEEP_INSTITUTIONS))

        # 轉換數值（移除千分位逗號）
        for col in ["buy", "sell", "net"]:
            if col in df.columns:
                df = df.with_columns(
                    pl.col(col).str.replace_all(",", "").cast(pl.Int64)
                )

        # 加入日期與市場
        df = df.with_columns([
            pl.lit(date_str).str.strptime(pl.Date, "%Y%m%d").alias("date"),
            pl.lit(market).alias("market"),
        ])

        # 調整欄位順序
        df = df.select(["date", "market", "institution", "buy", "sell", "net"])

        return df

    except Exception as e:
        print(f"Failed to process {file_path}: {e}")
        return None


def process_date(date_str: str) -> bool:
    """處理單一日期的資料"""
    input_dir = get_category_date_dir(RAW_DIR, CATEGORY, date_str)
    output_dir = os.path.join(PROCESSED_DIR, CATEGORY, date_str[:4], date_str)
    output_file = f"{output_dir}/all.csv"

    if os.path.exists(output_file):
        print(f"Skipping {date_str} (already exists)")
        return True

    if not os.path.exists(input_dir):
        print(f"Input directory not found: {input_dir}")
        return False

    all_dfs = []
    for market in ["sii", "otc"]:
        file_path = os.path.join(input_dir, f"{market}.csv")
        if not os.path.exists(file_path):
            continue

        df = process_single_file(file_path, market, date_str)
        if df is not None and not df.is_empty():
            all_dfs.append(df)

    if not all_dfs:
        print(f"No valid data for {date_str}")
        return False

    combined_df = pl.concat(all_dfs).sort(["market", "institution"])

    os.makedirs(output_dir, exist_ok=True)
    combined_df.write_csv(output_file)

    print(f"Processed {date_str} ({combined_df.height} rows)")
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

    print("Starting Institutional Summary ETL...")
    if start_date:
        print(f"Filter Start Date: {start_date.strftime('%Y-%m-%d')}")
    if end_date:
        print(f"Filter End Date: {end_date.strftime('%Y-%m-%d')}")

    category_path = os.path.join(RAW_DIR, CATEGORY)
    if not os.path.exists(category_path):
        print(f"Category path not found: {category_path}")
        return

    # 找出所有需要處理的日期 (支援 date=yyyymmdd 和 yyyy/yyyymmdd 結構)
    all_dates = set()
    for d in os.listdir(category_path):
        if d.startswith("date="):
            all_dates.add(d.split("=")[1])
        elif len(d) == 4 and d.isdigit():
            y_path = os.path.join(category_path, d)
            if os.path.isdir(y_path):
                for sub_d in os.listdir(y_path):
                    if len(sub_d) == 8 and sub_d.isdigit():
                        all_dates.add(sub_d)

    processed_count = 0
    for date_str in sorted(list(all_dates)):
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
