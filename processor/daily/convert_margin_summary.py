import os
import io
import datetime
import traceback
import re
from pathlib import Path
import pandas as pd
import polars as pl
from .convert_category_base import get_category_date_dir

RAW_DIR = os.getenv("RAW_DIR", "/app/data/raw")
PROCESSED_DIR = os.getenv("PROCESSED_DIR", "/app/data/processed")
FORCE_REPROCESS = os.getenv("FORCE_REPROCESS", "0") == "1"
CATEGORY = "margin_summary"
INPUT_CATEGORY = "margin_trading"


def log_processing_error(msg, date_str=None, category=None):
    error_file = Path("/app/error_processor.log")
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(error_file, "a", encoding="utf-8") as f:
        f.write(f"\n## Processor Runtime Error - {timestamp}\n")
        if date_str:
            f.write(f"**Date:** {date_str}\n")
        if category:
            f.write(f"**Category:** {category}\n")
        f.write(f"**Message:** {msg}\n")
        f.write(f"**Traceback:**\n```python\n{traceback.format_exc()}\n```\n")
        f.write("---\n")
    print(f"❌ Error logged to error_processor.log: {msg}")


def fail_invalid_params(msg):
    error_file = Path("/app/error_processor.log")
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(error_file, "a", encoding="utf-8") as f:
        f.write(f"\n## Processor Runtime Error - {timestamp}\n")
        f.write("**Entry:** daily/convert_margin_summary.py\n")
        f.write(f"**Category:** {CATEGORY}\n")
        f.write(f"**Message:** {msg}\n")
        f.write("---\n")
    print(msg)
    raise SystemExit(1)


def _handle_margin_summary(date_str, raw_dir=RAW_DIR):
    input_dir = get_category_date_dir(raw_dir, INPUT_CATEGORY, date_str)
    results = []

    sii_path = os.path.join(input_dir, "sii.csv")
    if os.path.exists(sii_path):
        try:
            rel_path = str(sii_path).split("my_stock_project/")[-1] if "my_stock_project/" in str(sii_path) else str(sii_path)
            with open(sii_path, "r", encoding="utf-8-sig") as f:
                lines = [f.readline() for _ in range(4)]
            df = pd.read_csv(io.StringIO("".join(lines)))
            df.columns = [c.strip() for c in df.columns]

            needed_cols_ordered = ["項目", "買進", "賣出", "現金(券)償還", "前日餘額", "今日餘額"]
            col_indices = ["x", "x"]
            for col_name in needed_cols_ordered:
                if col_name in df.columns:
                    col_idx = list(df.columns).index(col_name) + 1
                    col_indices.append(str(col_idx))
            src_col_str = "#".join(col_indices)

            for idx, row in df.iterrows():
                item = str(row["項目"]).strip()
                if "融資" in item or "融券" in item:
                    results.append({
                        "date": datetime.datetime.strptime(date_str, "%Y%m%d").date(),
                        "market": "SII",
                        "item": item,
                        "buy": int(str(row["買進"]).replace(",", "")),
                        "sell": int(str(row["賣出"]).replace(",", "")),
                        "cash_repay": int(str(row["現金(券)償還"]).replace(",", "")),
                        "prev_balance": int(str(row["前日餘額"]).replace(",", "")),
                        "today_balance": int(str(row["今日餘額"]).replace(",", "")),
                        "src_file": rel_path,
                        "src_row": idx + 2,
                        "src_col": src_col_str,
                    })
        except Exception as e:
            log_processing_error(f"Error in margin_summary (SII): {e}", date_str, CATEGORY)

    otc_path = os.path.join(input_dir, "otc.csv")
    if os.path.exists(otc_path):
        try:
            rel_path = str(otc_path).split("my_stock_project/")[-1] if "my_stock_project/" in str(otc_path) else str(otc_path)
            with open(otc_path, "r", encoding="utf-8-sig") as f:
                lines = f.readlines()
            for i, line in enumerate(lines):
                if i < len(lines) - 5:
                    continue
                if "合計(張)" in line or "融資金(仟元)" in line:
                    parts = [p.strip().replace('"', "") for p in line.split('","')]
                    if len(parts) < 7:
                        continue

                    item = parts[0].replace('"', "")
                    src_row = i + 1
                    if "合計(張)" in item and len(parts) >= 15:
                        results.append({"date": datetime.datetime.strptime(date_str, "%Y%m%d").date(), "market": "OTC", "item": "融資(交易單位)", "buy": int(parts[3].replace(",", "")), "sell": int(parts[4].replace(",", "")), "cash_repay": int(parts[5].replace(",", "")), "prev_balance": int(parts[2].replace(",", "")), "today_balance": int(parts[6].replace(",", "")), "src_file": rel_path, "src_row": src_row, "src_col": "x#x#1#4#5#6#3#7"})
                        results.append({"date": datetime.datetime.strptime(date_str, "%Y%m%d").date(), "market": "OTC", "item": "融券(交易單位)", "buy": int(parts[12].replace(",", "")), "sell": int(parts[11].replace(",", "")), "cash_repay": int(parts[13].replace(",", "")), "prev_balance": int(parts[10].replace(",", "")), "today_balance": int(parts[14].replace(",", "")), "src_file": rel_path, "src_row": src_row, "src_col": "x#x#1#13#12#14#11#15"})
                    elif "融資金(仟元)" in item:
                        results.append({"date": datetime.datetime.strptime(date_str, "%Y%m%d").date(), "market": "OTC", "item": "融資金額(仟元)", "buy": int(parts[3].replace(",", "")), "sell": int(parts[4].replace(",", "")), "cash_repay": int(parts[5].replace(",", "")), "prev_balance": int(parts[2].replace(",", "")), "today_balance": int(parts[6].replace(",", "")), "src_file": rel_path, "src_row": src_row, "src_col": "x#x#1#4#5#6#3#7"})
        except Exception as e:
            log_processing_error(f"Error in margin_summary (OTC): {e}", date_str, CATEGORY)

    return pl.from_pandas(pd.DataFrame(results)) if results else None


def process_date(date_str, raw_dir=RAW_DIR, processed_dir=PROCESSED_DIR, force_reprocess=FORCE_REPROCESS):
    output_dir = os.path.join(processed_dir, CATEGORY, date_str[:4], date_str)
    output_file = os.path.join(output_dir, "all.csv")

    if os.path.exists(output_file) and not force_reprocess:
        if os.getenv("DEBUG", "0") == "1":
            print(f"Skipping {CATEGORY}/{date_str} (already exists)")
        return

    df = _handle_margin_summary(date_str, raw_dir=raw_dir)
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

    category_path = os.path.join(RAW_DIR, INPUT_CATEGORY)
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
