import functools
import os
import re
import polars as pl
from .convert_category_base import get_category_date_dir

RAW_DIR = os.getenv("RAW_DIR", "/app/data/raw")
PROCESSED_DIR = os.getenv("PROCESSED_DIR", "/app/data/processed")
FORCE_REPROCESS = os.getenv("FORCE_REPROCESS", "0") == "1"
CATEGORY = "institutional_summary"

INSTITUTION_MAP = {
    "自營商(自行買賣)": "dealer_self",
    "自營商(避險)": "dealer_hedge",
    "投信": "investment_trust",
    "外資及陸資(不含外資自營商)": "foreign_investors",
    "外資自營商": "foreign_dealer",
    "合計": "total",
    "自營商(自行買賣)\u3000": "dealer_self",
    "自營商(避險)\u3000": "dealer_hedge",
    "外資及陸資(不含自營商)": "foreign_investors",
    "外資及陸資合計": "foreign_total",
    "自營商合計": "dealer_total",
    "三大法人合計*": "total",
    "三大法人合計": "total",
}

KEEP_INSTITUTIONS = [
    "dealer_self",
    "dealer_hedge",
    "investment_trust",
    "foreign_investors",
    "foreign_dealer",
    "total",
]


from _error_report import (  # noqa: E402
    fail_invalid_params as _fail_invalid_params,
)
from _error_report import log_processing_error  # noqa: E402

# 呼叫端一律 `fail_invalid_params(msg)`，entry/category 在這裡綁定一次。
fail_invalid_params = functools.partial(
    _fail_invalid_params,
    entry="daily/convert_institutional_summary.py",
    category=CATEGORY,
)


def _handle_institutional_summary(date_str, raw_dir=RAW_DIR):
    input_dir = get_category_date_dir(raw_dir, CATEGORY, date_str)
    all_dfs = []

    for market in ["sii", "otc"]:
        file_path = os.path.join(input_dir, f"{market}.csv")
        if not os.path.exists(file_path):
            continue

        try:
            df = pl.read_csv(file_path, encoding="utf-8-sig", infer_schema_length=0)
            if df.is_empty():
                continue

            original_columns = df.columns
            rename_map = {}
            col_indices = []

            for idx, col in enumerate(original_columns):
                c = col.strip()
                if c == "單位名稱":
                    rename_map[col] = "institution"
                    col_indices.append(str(idx + 1))
                elif "買進" in c:
                    rename_map[col] = "buy"
                    col_indices.append(str(idx + 1))
                elif "賣出" in c:
                    rename_map[col] = "sell"
                    col_indices.append(str(idx + 1))
                elif "差額" in c or "買賣超" in c:
                    rename_map[col] = "net"
                    col_indices.append(str(idx + 1))

            df = df.select(list(rename_map.keys())).rename(rename_map)

            if "institution" not in df.columns:
                log_processing_error(
                    f"Missing 'institution' column in {market}.csv (cols: {df.columns})",
                    date_str,
                    CATEGORY,
                )
                continue

            rel_path = (
                str(file_path).split("my_stock_project/")[-1]
                if "my_stock_project/" in str(file_path)
                else str(file_path)
            )
            src_col_str = "#".join(col_indices)

            df = df.with_columns(
                [
                    pl.lit(rel_path).alias("src_file"),
                    (pl.arange(0, df.height) + 2).alias("src_row"),
                    pl.lit(src_col_str).alias("src_col"),
                ]
            )

            df = df.with_columns(
                pl.col("institution").str.strip_chars().replace(INSTITUTION_MAP)
            )
            df = df.filter(pl.col("institution").is_in(KEEP_INSTITUTIONS))

            for col in ["buy", "sell", "net"]:
                if col in df.columns:
                    df = df.with_columns(
                        pl.col(col)
                        .str.replace_all(",", "")
                        .cast(pl.Int64, strict=False)
                    )

            df = df.with_columns(
                [
                    pl.lit(date_str).str.strptime(pl.Date, "%Y%m%d").alias("date"),
                    pl.lit(market).alias("market"),
                ]
            )

            df = df.with_columns(
                pl.concat_str([pl.lit("x#x#"), pl.col("src_col")]).alias("src_col")
            )
            all_dfs.append(
                df.select(
                    [
                        "date",
                        "market",
                        "institution",
                        "buy",
                        "sell",
                        "net",
                        "src_file",
                        "src_row",
                        "src_col",
                    ]
                )
            )

        except Exception as e:
            log_processing_error(
                f"Error in institutional_summary for {market}: {e}", date_str, CATEGORY
            )

    return pl.concat(all_dfs) if all_dfs else None


def process_date(
    date_str,
    raw_dir=RAW_DIR,
    processed_dir=PROCESSED_DIR,
    force_reprocess=FORCE_REPROCESS,
):
    output_dir = os.path.join(processed_dir, CATEGORY, date_str[:4], date_str)
    output_file = os.path.join(output_dir, "all.csv")

    if os.path.exists(output_file) and not force_reprocess:
        if os.getenv("DEBUG", "0") == "1":
            print(f"Skipping {CATEGORY}/{date_str} (already exists)")
        return

    df = _handle_institutional_summary(date_str, raw_dir=raw_dir)
    if df is not None:
        os.makedirs(output_dir, exist_ok=True)
        df.write_csv(output_file)
        print(f"Processed {CATEGORY}/{date_str}")


if __name__ == "__main__":
    start_env = os.getenv("START_DATE")
    end_env = os.getenv("END_DATE")

    if not start_env or not end_env:
        fail_invalid_params(
            "Error: START_DATE and END_DATE are both required (YYYYMMDD)."
        )
    if not (re.match(r"^\d{8}$", start_env) and re.match(r"^\d{8}$", end_env)):
        fail_invalid_params(
            f"Error: Invalid date format (START_DATE={start_env}, END_DATE={end_env}). Expected YYYYMMDD."
        )
    if start_env > end_env:
        fail_invalid_params(
            f"Error: START_DATE must be <= END_DATE (START_DATE={start_env}, END_DATE={end_env})."
        )

    category_path = os.path.join(RAW_DIR, CATEGORY)
    if not os.path.exists(category_path):
        raise SystemExit(0)

    all_dates = set()
    for d in os.listdir(category_path):
        if len(d) == 4 and d.isdigit():
            y_path = os.path.join(category_path, d)
            if os.path.isdir(y_path):
                for sub_d in os.listdir(y_path):
                    if len(sub_d) == 8 and sub_d.isdigit():
                        all_dates.add(sub_d)

    for date_str in sorted(list(all_dates)):
        if date_str < start_env:
            continue
        if date_str > end_env:
            continue
        process_date(date_str)
