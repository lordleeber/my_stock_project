import os
import polars as pl
from schemas import SCHEMA_COLS
from utils import read_sii_indices
from .convert_category_base import (
    get_category_date_dir,
    enforce_schema,
    generate_src_col,
    handle_generic_category,
)

RAW_DIR = os.getenv("RAW_DIR", "/app/data/raw")
PROCESSED_DIR = os.getenv("PROCESSED_DIR", "/app/data/processed")
FORCE_REPROCESS = os.getenv("FORCE_REPROCESS", "0") == "1"
CATEGORY = "market_indices"


def _clean_market_indices_numeric(df):
    numeric_cols = ["index_close", "index_change_points"]
    for col in numeric_cols:
        if col in df.columns and df[col].dtype == pl.Utf8:
            df = df.with_columns(pl.col(col).str.replace_all(",", "").alias(col))
    return df


def process_date(
    date_str,
    raw_dir=RAW_DIR,
    processed_dir=PROCESSED_DIR,
    force_reprocess=FORCE_REPROCESS,
):
    output_dir = os.path.join(processed_dir, CATEGORY, date_str[:4], date_str)

    # OTC (raw market_indices)
    otc_output = os.path.join(output_dir, "otc.csv")
    otc_raw_dir = get_category_date_dir(raw_dir, CATEGORY, date_str)
    otc_raw = os.path.join(otc_raw_dir, "otc.csv")
    if os.path.exists(otc_raw) and (not os.path.exists(otc_output) or force_reprocess):
        df, col_mapping = handle_generic_category(otc_raw, "otc", CATEGORY, date_str)
        if df is not None:
            if "index_name" in df.columns and (
                "symbol" not in df.columns or df["symbol"].null_count() == len(df)
            ):
                df = df.with_columns(pl.col("index_name").alias("symbol"))
                if "index_name" in col_mapping:
                    col_mapping["symbol"] = col_mapping["index_name"]
            if "change" in df.columns and "index_change_points" not in df.columns:
                df = df.with_columns(pl.col("change").alias("index_change_points"))
                if "change" in col_mapping:
                    col_mapping["index_change_points"] = col_mapping["change"]

            df = _clean_market_indices_numeric(df)
            df = enforce_schema(df, CATEGORY)
            src_col_str = generate_src_col(SCHEMA_COLS[CATEGORY], col_mapping)
            df = df.with_columns(pl.lit(src_col_str).alias("src_col"))
            os.makedirs(output_dir, exist_ok=True)
            df.write_csv(otc_output)
            print(f"Processed market_indices/{date_str}/otc")

    # SII (extract from daily_quotes/sii.csv)
    sii_output = os.path.join(output_dir, "sii.csv")
    dq_raw_dir = get_category_date_dir(raw_dir, "daily_quotes", date_str)
    sii_quote = os.path.join(dq_raw_dir, "sii.csv")
    if os.path.exists(sii_quote) and (
        not os.path.exists(sii_output) or force_reprocess
    ):
        df_indices, sii_col_mapping = read_sii_indices(
            sii_quote, return_col_mapping=True
        )
        if df_indices is not None:
            df_indices = df_indices.with_columns(
                [
                    pl.lit(date_str).str.strptime(pl.Date, "%Y%m%d").alias("date"),
                    pl.lit("sii").alias("market"),
                ]
            )
            if "index_name" in df_indices.columns:
                df_indices = df_indices.with_columns(
                    pl.col("index_name").alias("symbol")
                )
            if "index_name" in sii_col_mapping:
                sii_col_mapping["symbol"] = sii_col_mapping["index_name"]
            df_indices = enforce_schema(df_indices, CATEGORY)
            src_col_str = generate_src_col(SCHEMA_COLS[CATEGORY], sii_col_mapping)
            df_indices = df_indices.with_columns(pl.lit(src_col_str).alias("src_col"))
            os.makedirs(output_dir, exist_ok=True)
            df_indices.write_csv(sii_output)
            print(f"Processed market_indices/{date_str}/sii (Extracted)")
