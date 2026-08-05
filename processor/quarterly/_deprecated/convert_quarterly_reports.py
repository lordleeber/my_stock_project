import os
import sys
import csv
import re
from pathlib import Path
import polars as pl

# 環境變數設定
RAW_DIR = os.environ.get("RAW_DIR", "data/raw")
PROCESSED_DIR = os.environ.get("PROCESSED_DIR", "data/processed")
CATEGORY = "quarterly_reports"
DEBUG = os.getenv("DEBUG", "0") == "1"

# Final output column order (schema) - src_col is generated based on this order
SCHEMA_COLS = [
    "date",
    "symbol",
    "name",
    "market",
    "revenue_q",
    "revenue_acc",
    "revenue_acc_ly",
    "revenue_acc_yoy",
    "op_income_q",
    "op_income_acc",
    "op_income_acc_ly",
    "op_income_acc_yoy",
    "non_op_income_q",
    "non_op_income_acc",
    "non_op_income_acc_ly",
    "non_op_income_acc_yoy",
    "pretax_income_q",
    "pretax_income_acc",
    "pretax_income_acc_ly",
    "pretax_income_acc_yoy",
    "net_income_q",
    "net_income_acc",
    "net_income_acc_ly",
    "net_income_acc_yoy",
    "eps_q",
    "eps_acc",
    "eps_acc_ly",
    "eps_acc_yoy",
    "capital",
    "nav_per_share",
    "equity_to_assets_ratio",
    "current_ratio",
    "quick_ratio",
]

FINAL_FIELDS = SCHEMA_COLS + ["src_file", "src_row", "src_col"]

# 需要計算單季值的流量欄位 (Accumulated -> Quarterly)
FLOW_FIELDS = [
    "revenue",
    "op_income",
    "non_op_income",
    "pretax_income",
    "net_income",
    "eps",
]

# SII 欄位映射 (1-based column index for src_col generation)
# 這裡對應的是 raw CSV 裡的原始累計值欄位
SII_MAPPING = {
    "symbol": 1,
    "name": 2,
    "revenue_acc": 3,
    "revenue_acc_ly": 4,
    "revenue_acc_yoy": 5,
    "op_income_acc": 6,
    "op_income_acc_ly": 7,
    "non_op_income_acc": 8,
    "non_op_income_acc_ly": 9,
    "net_income_acc": 10,
    "net_income_acc_ly": 11,
    "net_income_acc_yoy": 12,
    "capital": 13,
    "eps_acc": 14,
    "eps_acc_ly": 15,
    "nav_per_share": 16,
    "equity_to_assets_ratio": 17,
    "current_ratio": 18,
    "quick_ratio": 19,
    "pretax_income_acc": 20,
    "pretax_income_acc_ly": 21,
    "pretax_income_acc_yoy": 22,
}

# OTC 欄位映射 (1-based column index)
OTC_MAPPING = {
    "symbol": 1,
    "name": 2,
    "revenue_acc": 3,
    "revenue_acc_ly": 4,
    "revenue_acc_yoy": 5,
    "op_income_acc": 6,
    "op_income_acc_ly": 7,
    "non_op_income_acc": 8,
    "non_op_income_acc_ly": 9,
    "net_income_acc": 10,
    "net_income_acc_ly": 11,
    "net_income_acc_yoy": 12,
    "capital": 13,
    "eps_acc": 14,
    "eps_acc_ly": 15,
    "nav_per_share": 16,
    "equity_to_assets_ratio": 17,
    "current_ratio": 18,
    "quick_ratio": 19,
}


def get_prev_quarter(date_str):
    """取得前一季的標籤 (僅限同年度，Q1 則返回 None)"""
    year = int(date_str[:4])
    q = int(date_str[5])
    if q == 1:
        return None
    return f"{year}Q{q - 1}"


# 加入 common 目錄到搜尋路徑
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from common.schemas import get_polars_schema  # noqa: E402


def load_prev_data(prev_q_str):
    """讀取前一季已處理好的資料"""
    if not prev_q_str:
        return None
    year_str = prev_q_str[:4]
    path = os.path.join(PROCESSED_DIR, CATEGORY, year_str, prev_q_str, "all.csv")
    if DEBUG:
        print(f"  [DEBUG] Checking previous quarter path: {path}")
    if os.path.exists(path):
        try:
            # 強制使用 Schema 確保 symbol 是字串
            schema = get_polars_schema(CATEGORY)
            df = pl.read_csv(path, schema_overrides=schema or {})
            if DEBUG:
                print(
                    f"  [DEBUG] Successfully loaded {len(df)} records from {prev_q_str}"
                )
            return df
        except Exception as e:
            if DEBUG:
                print(f"  [DEBUG] Error loading {path}: {e}")
            return None
    return None


def clean_numeric(val):
    """清理數值，處理 --, null, nan, (123)"""
    if val is None or val == "--" or str(val).strip() == "":
        return None
    try:
        s = str(val).replace(",", "").strip()
        if s.startswith("(") and s.endswith(")"):
            s = "-" + s[1:-1]
        return float(s)
    except (ValueError, TypeError):
        return None


def calculate_yoy(current, ly):
    """手動計算 YoY %"""
    if current is None or ly is None or ly == 0:
        return None
    return round((current - ly) / abs(ly) * 100, 2)


def find_header_row(rows, max_rows=15):
    """找到含有 'Code' 或 '代號' 的 header 行"""
    for idx, row in enumerate(rows[:max_rows]):
        row_str = "".join(str(cell) for cell in row)
        if "Code" in row_str or "代號" in row_str:
            return idx
    return -1


def generate_src_col(schema_cols, col_mapping):
    """Generate src_col string based on schema column order and column mapping.

    Args:
        schema_cols: Final output column order (excluding lineage columns)
        col_mapping: {english_col_name: 1-based_raw_column_index}

    Returns:
        src_col string in format "x#x#1#2#3#4#..."
    """
    src_col_parts = []
    for col in schema_cols:
        if col in col_mapping:
            src_col_parts.append(str(col_mapping[col]))
        else:
            src_col_parts.append("x")
    return "#".join(src_col_parts)


def process_csv_file(file_path, date_str, market, prev_df=None):
    """
    處理單一季報 CSV 檔案，提取本期累計、去年同期累計，並計算單季值
    """
    try:
        # 讀取 CSV (處理 BOM)
        with open(file_path, "r", encoding="utf-8-sig", errors="replace") as f:
            reader = csv.reader(f)
            rows = list(reader)

        if not rows:
            print(f"❌ Empty file: {file_path}")
            sys.exit(1)

        # 找到 header 行
        header_idx = find_header_row(rows)
        if header_idx == -1:
            print(f"❌ Cannot find header row in {file_path}")
            sys.exit(1)

        # 選擇映射
        col_mapping = SII_MAPPING if market == "sii" else OTC_MAPPING
        src_col_str = generate_src_col(SCHEMA_COLS, col_mapping)

        records = []
        for row_idx in range(header_idx + 1, len(rows)):
            row = rows[row_idx]
            if len(row) < 2:
                continue

            raw_symbol = str(row[col_mapping["symbol"] - 1]).strip()
            if raw_symbol.endswith(".0"):
                raw_symbol = raw_symbol[:-2]

            if len(raw_symbol) != 4 or not raw_symbol.isdigit():
                continue

            # 初始化資料字典
            data = {f: None for f in FINAL_FIELDS}
            data["date"] = date_str
            data["market"] = market
            data["symbol"] = raw_symbol
            data["name"] = (
                str(row[col_mapping["name"] - 1]).strip()
                if (col_mapping["name"] - 1) < len(row)
                else ""
            )

            # 1. 提取原始累計值 (acc) 與時點值 (snapshot)
            for field, idx_1based in col_mapping.items():
                if field in ["symbol", "name"]:
                    continue
                idx = idx_1based - 1
                if idx < len(row):
                    data[field] = clean_numeric(row[idx])

            # 2. OTC 手動計算稅前累計 (OTC CSV 沒有 pretax 欄位)
            if market == "otc":
                if (
                    data["op_income_acc"] is not None
                    and data["non_op_income_acc"] is not None
                ):
                    data["pretax_income_acc"] = (
                        data["op_income_acc"] + data["non_op_income_acc"]
                    )
                if (
                    data["op_income_acc_ly"] is not None
                    and data["non_op_income_acc_ly"] is not None
                ):
                    data["pretax_income_acc_ly"] = (
                        data["op_income_acc_ly"] + data["non_op_income_acc_ly"]
                    )

            # 3. 計算 YoY (累計)
            data["revenue_acc_yoy"] = calculate_yoy(
                data["revenue_acc"], data["revenue_acc_ly"]
            )
            data["op_income_acc_yoy"] = calculate_yoy(
                data["op_income_acc"], data["op_income_acc_ly"]
            )
            data["non_op_income_acc_yoy"] = calculate_yoy(
                data["non_op_income_acc"], data["non_op_income_acc_ly"]
            )
            data["pretax_income_acc_yoy"] = calculate_yoy(
                data["pretax_income_acc"], data["pretax_income_acc_ly"]
            )
            data["net_income_acc_yoy"] = calculate_yoy(
                data["net_income_acc"], data["net_income_acc_ly"]
            )
            data["eps_acc_yoy"] = calculate_yoy(data["eps_acc"], data["eps_acc_ly"])

            # 4. 計算單季值 (q)
            # 如果是 Q1，單季值 = 累計值
            # 如果是 Q2-Q4，單季值 = 當前累計 - 前一季累計
            is_q1 = date_str.endswith("Q1")

            # 取得前一季這家公司的資料
            prev_row = None
            if not is_q1 and prev_df is not None:
                try:
                    prev_row = prev_df.filter(pl.col("symbol") == raw_symbol)
                    if prev_row.is_empty():
                        prev_row = None
                except Exception:
                    prev_row = None

            for field in FLOW_FIELDS:
                acc_field = f"{field}_acc"
                q_field = f"{field}_q"

                if is_q1:
                    data[q_field] = data[acc_field]
                else:
                    if data[acc_field] is not None and prev_row is not None:
                        # 從前一季資料中取得當時的累計值 (注意：前一季的累計值欄位名也是 field_acc)
                        prev_acc = prev_row.select(acc_field).item()
                        if prev_acc is not None:
                            data[q_field] = round(data[acc_field] - prev_acc, 2)
                            if DEBUG and raw_symbol == "2330" and field == "eps":
                                print(
                                    f"  [DEBUG] 2330 EPS Subtraction: {data[acc_field]} - {prev_acc} = {data[q_field]}"
                                )

                    # 如果找不到前一季資料，則單季值暫時設為 None (或者可以改為等於累計值，但 None 較為精確)
                    if data[q_field] is None:
                        data[q_field] = data[acc_field]

            # 加入 lineage 欄位
            data["src_file"] = file_path
            data["src_row"] = row_idx + 1
            data["src_col"] = src_col_str

            records.append(data)

        if DEBUG:
            print(f"  ✓ Parsed {file_path}: {len(records)} records")

        return pl.DataFrame(records) if records else None

    except ValueError as e:
        # Fail-fast on validation errors
        print(f"❌ Validation error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


def main():
    raw_path = os.path.join(RAW_DIR, CATEGORY)
    date_dirs = sorted(Path(raw_path).rglob("????Q[1-4]"))

    start_env = os.getenv("START_DATE")
    end_env = os.getenv("END_DATE")
    quarter_pattern = r"^\d{4}Q[1-4]$"

    if not start_env or not end_env:
        print("Error: START_DATE and END_DATE are both required (YYYYQX).")
        print("Example: START_DATE=2024Q1 END_DATE=2024Q1 python convert_quarterly.py")
        sys.exit(1)

    if not (
        re.match(quarter_pattern, start_env) and re.match(quarter_pattern, end_env)
    ):
        print(
            f"Error: Invalid quarter format (START_DATE={start_env}, END_DATE={end_env}). Expected YYYYQX."
        )
        sys.exit(1)

    if start_env > end_env:
        print(
            f"Error: START_DATE must be <= END_DATE (START_DATE={start_env}, END_DATE={end_env})."
        )
        sys.exit(1)

    for date_dir in date_dirs:
        date_str = date_dir.name  # YYYYQX

        if start_env and date_str < start_env:
            continue
        if end_env and date_str > end_env:
            continue

        print(f"Processing {date_str}...")

        # 讀取前一季資料以便計算單季值
        prev_q = get_prev_quarter(date_str)
        prev_df = load_prev_data(prev_q)
        if prev_q and prev_df is None:
            print(
                f"  [!] Note: Previous quarter data ({prev_q}) not found. Single-quarter values will equal accumulated values."
            )

        all_dfs = []
        for market in ["sii", "otc"]:
            csv_path = os.path.join(str(date_dir), f"{market}.csv")

            if os.path.exists(csv_path):
                df = process_csv_file(csv_path, date_str, market, prev_df=prev_df)
                if df is not None:
                    all_dfs.append(df)
            else:
                print(f"  [!] CSV not found: {csv_path}")

        if all_dfs:
            final_df = pl.concat(all_dfs).unique(subset=["symbol"])
            final_df = final_df.select(FINAL_FIELDS)

            year_str = date_str[:4]
            output_dir = os.path.join(PROCESSED_DIR, CATEGORY, year_str, date_str)
            os.makedirs(output_dir, exist_ok=True)
            output_path = os.path.join(output_dir, "all.csv")
            final_df.write_csv(output_path)
            print(f"  [+] Saved {final_df.height} records to {output_path}")

            # TODO: 更新 audit_quarterly_reports 以適應新欄位名後再取消註解
            # print(f"  Auditing quarterly_reports data for {date_str}...")
            # ... 略 ...

            # 簡易資料品質檢查
            if final_df.is_empty():
                print(f"  [!] Warning: {date_str} generated an empty CSV.")
            else:
                for col in ["revenue_acc", "eps_acc", "net_income_acc"]:
                    if col in final_df.columns:
                        null_count = final_df.select(pl.col(col).null_count()).item()
                        if null_count == final_df.height:
                            print(
                                f"  [!] CRITICAL: Column '{col}' is entirely NULL in {date_str}. Check mapping logic."
                            )


if __name__ == "__main__":
    main()
