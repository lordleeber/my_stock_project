import os
import polars as pl
from schemas import SCHEMA_COLS
from utils import read_raw_csv
import sys

# 加入 common 目錄到搜尋路徑
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from common.schemas import get_polars_schema


def get_category_date_dir(base_dir, category, date_str):
    """Return date directory path in new structure YYYY/YYYYMMDD."""
    return os.path.join(base_dir, category, date_str[:4], date_str)


def enforce_schema(df, category):
    if category not in SCHEMA_COLS:
        return df
    required_cols = SCHEMA_COLS[category]
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        df = df.with_columns([pl.lit(None).alias(col) for col in missing_cols])

    # 按照標準欄位順序排列
    df = df.select(required_cols)

    # 強制執行型別轉換
    schema = get_polars_schema(category)
    if schema:
        # 只針對存在的欄位進行轉換
        cast_exprs = []
        for col, dtype in schema.items():
            if col in df.columns:
                cast_exprs.append(pl.col(col).cast(dtype, strict=False))
        if cast_exprs:
            df = df.with_columns(cast_exprs)

    return df


def generate_src_col(schema_cols, col_mapping):
    """Generate src_col based on schema order and raw column mapping."""
    src_col_parts = []
    for col in schema_cols:
        if col in ["src_file", "src_row", "src_col"]:
            continue
        if col in col_mapping:
            src_col_parts.append(str(col_mapping[col]))
        else:
            src_col_parts.append("x")
    return "#".join(src_col_parts)


def handle_generic_category(file_path, market, category, date_str):
    """Process a generic per-market CSV category and return (df, col_mapping)."""
    df, col_mapping = read_raw_csv(
        file_path, category=category, return_col_mapping=True
    )
    if df is None or df.is_empty():
        return None, {}

    df = df.with_columns(
        [
            pl.lit(date_str).str.strptime(pl.Date, "%Y%m%d").alias("date"),
            pl.lit(market).alias("market"),
        ]
    )

    if "symbol" in df.columns:
        df = df.filter(pl.col("symbol").is_not_null())
        # 只保留 4 碼純數字代號 (過濾 ETF, 權證, 特別股等)
        df = df.filter(pl.col("symbol").cast(pl.Utf8).str.contains(r"^\d{4}$"))

    return df, col_mapping


def process_generic_category_date(
    category, date_str, raw_dir, processed_dir, force_reprocess
):
    """Process one date for generic daily categories."""
    output_dir = os.path.join(processed_dir, category, date_str[:4], date_str)
    cat_raw_path = get_category_date_dir(raw_dir, category, date_str)
    if not os.path.exists(cat_raw_path):
        return

    for market_file in os.listdir(cat_raw_path):
        if not market_file.endswith(".csv"):
            continue
        market = market_file.split(".")[0]
        output_file = os.path.join(output_dir, f"{market}.csv")
        if os.path.exists(output_file) and not force_reprocess:
            continue

        file_path = os.path.join(cat_raw_path, market_file)
        df, col_mapping = handle_generic_category(file_path, market, category, date_str)
        if df is None:
            continue

        df = enforce_schema(df, category)
        if category in SCHEMA_COLS:
            src_col_str = generate_src_col(SCHEMA_COLS[category], col_mapping)
            df = df.with_columns(pl.lit(src_col_str).alias("src_col"))

        os.makedirs(output_dir, exist_ok=True)
        df.write_csv(output_file)
        print(f"Processed {category}/{date_str}/{market}")
