import os
import sys
import csv
import re
from pathlib import Path
import polars as pl
from datetime import datetime
from .audit_quarterly_reports import run_quality_check

# 環境變數設定
RAW_DIR = os.environ.get("RAW_DIR", "data/raw")
PROCESSED_DIR = os.environ.get("PROCESSED_DIR", "data/processed")
CATEGORY = "quarterly_reports"
DEBUG = os.getenv("DEBUG", "0") == "1"

# Final output column order (schema) - src_col is generated based on this order
SCHEMA_COLS = [
    "date", "symbol", "name", "market",
    "revenue", "revenue_ly", "revenue_yoy",
    "op_income", "op_income_ly", "op_income_yoy",
    "non_op_income", "non_op_income_ly", "non_op_income_yoy",
    "pretax_income", "pretax_income_ly", "pretax_income_yoy",
    "net_income", "net_income_ly", "net_income_yoy",
    "eps", "eps_ly", "eps_yoy",
    "capital", "nav_per_share", "equity_to_assets_ratio",
    "current_ratio", "quick_ratio"
]

FINAL_FIELDS = SCHEMA_COLS + ["src_file", "src_row", "src_col"]

# SII 欄位映射 (1-based column index for src_col generation)
SII_MAPPING = {
    "symbol": 1, "name": 2,
    "revenue": 3, "revenue_ly": 4, "revenue_yoy": 5,
    "op_income": 6, "op_income_ly": 7,
    "non_op_income": 8, "non_op_income_ly": 9,
    "net_income": 10, "net_income_ly": 11, "net_income_yoy": 12,
    "capital": 13,
    "eps": 14, "eps_ly": 15,
    "nav_per_share": 16, "equity_to_assets_ratio": 17,
    "current_ratio": 18, "quick_ratio": 19,
    "pretax_income": 20, "pretax_income_ly": 21, "pretax_income_yoy": 22
}

# OTC 欄位映射 (1-based column index) - 沒有 pretax 欄位
OTC_MAPPING = {
    "symbol": 1, "name": 2,
    "revenue": 3, "revenue_ly": 4, "revenue_yoy": 5,
    "op_income": 6, "op_income_ly": 7,
    "non_op_income": 8, "non_op_income_ly": 9,
    "net_income": 10, "net_income_ly": 11, "net_income_yoy": 12,
    "capital": 13,
    "eps": 14, "eps_ly": 15,
    "nav_per_share": 16, "equity_to_assets_ratio": 17,
    "current_ratio": 18, "quick_ratio": 19
}


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


def process_csv_file(file_path, date_str, market):
    """
    處理單一季報 CSV 檔案，提取本期、去年同期與 YoY
    """
    try:
        # 讀取 CSV (處理 BOM)
        with open(file_path, 'r', encoding='utf-8-sig', errors='replace') as f:
            reader = csv.reader(f)
            rows = list(reader)

        if not rows:
            print(f"  [!] Empty file: {file_path}")
            return None

        # 找到 header 行
        header_idx = find_header_row(rows)
        if header_idx == -1:
            print(f"  [!] Cannot find header row in {file_path}")
            return None

        # 選擇映射 (1-based column indices)
        col_mapping = SII_MAPPING if market == 'sii' else OTC_MAPPING

        # 生成 src_col 字串 based on SCHEMA_COLS order
        src_col_str = generate_src_col(SCHEMA_COLS, col_mapping)

        # 計算相對路徑
        rel_path = file_path.replace("/Users/poyilee/Documents/GitHubLL/my_stock_project/", "/app/")

        records = []
        for row_idx in range(header_idx + 1, len(rows)):
            row = rows[row_idx]
            if len(row) < 2:
                continue

            # 取得 symbol (convert 1-based to 0-based for row access)
            raw_symbol = str(row[col_mapping["symbol"] - 1]).strip()
            if raw_symbol.endswith(".0"):
                raw_symbol = raw_symbol[:-2]

            # 只處理 4 位數字的股票代碼
            if len(raw_symbol) != 4 or not raw_symbol.isdigit():
                continue

            # 初始化資料字典
            data = {f: None for f in FINAL_FIELDS}
            data["date"] = date_str
            data["market"] = market
            data["symbol"] = raw_symbol
            data["name"] = str(row[col_mapping["name"] - 1]).strip() if (col_mapping["name"] - 1) < len(row) else ""

            # 提取數值欄位 (convert 1-based to 0-based for row access)
            for field, idx_1based in col_mapping.items():
                if field in ["symbol", "name"]:
                    continue
                idx = idx_1based - 1  # convert to 0-based
                if idx < len(row):
                    data[field] = clean_numeric(row[idx])

            # 補齊 YoY (如果原始資料沒有)
            if data["op_income_yoy"] is None:
                data["op_income_yoy"] = calculate_yoy(data["op_income"], data["op_income_ly"])
            if data["non_op_income_yoy"] is None:
                data["non_op_income_yoy"] = calculate_yoy(data["non_op_income"], data["non_op_income_ly"])
            if data["eps_yoy"] is None:
                data["eps_yoy"] = calculate_yoy(data["eps"], data["eps_ly"])

            # OTC 手動計算稅前 (OTC CSV 沒有 pretax 欄位)
            if market == 'otc':
                if data["op_income"] is not None and data["non_op_income"] is not None:
                    data["pretax_income"] = data["op_income"] + data["non_op_income"]
                if data["op_income_ly"] is not None and data["non_op_income_ly"] is not None:
                    data["pretax_income_ly"] = data["op_income_ly"] + data["non_op_income_ly"]
                data["pretax_income_yoy"] = calculate_yoy(data["pretax_income"], data["pretax_income_ly"])

            # 加入 lineage 欄位
            data["src_file"] = rel_path
            data["src_row"] = row_idx + 1  # 1-based line number
            data["src_col"] = src_col_str

            records.append(data)

        if DEBUG:
            print(f"  ✓ Parsed {file_path}: {len(records)} records, src_col={src_col_str}")

        return pl.DataFrame(records) if records else None

    except ValueError as e:
        # Fail-fast on validation errors
        print(f"❌ Validation error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        import traceback
        traceback.print_exc()
        return None


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

    if not (re.match(quarter_pattern, start_env) and re.match(quarter_pattern, end_env)):
        print(f"Error: Invalid quarter format (START_DATE={start_env}, END_DATE={end_env}). Expected YYYYQX.")
        sys.exit(1)

    if start_env > end_env:
        print(f"Error: START_DATE must be <= END_DATE (START_DATE={start_env}, END_DATE={end_env}).")
        sys.exit(1)

    for date_dir in date_dirs:
        date_str = date_dir.name  # YYYYQX

        if start_env and date_str < start_env:
            continue
        if end_env and date_str > end_env:
            continue

        print(f"Processing {date_str}...")

        all_dfs = []
        for market in ["sii", "otc"]:
            # 優先使用 CSV，如果不存在則嘗試 XLS
            csv_path = os.path.join(str(date_dir), f"{market}.csv")

            if os.path.exists(csv_path):
                df = process_csv_file(csv_path, date_str, market)
                if df is not None:
                    all_dfs.append(df)
            else:
                print(f"  [!] CSV not found: {csv_path}")

        if all_dfs:
            final_df = pl.concat(all_dfs).unique(subset=["symbol"])
            # 強制統一欄位順序，確保匯入穩定
            final_df = final_df.select(FINAL_FIELDS)

            # 輸出路徑格式: data/processed/quarterly_reports/YYYY/YYYYQX/
            year_str = date_str[:4]
            output_dir = os.path.join(PROCESSED_DIR, CATEGORY, year_str, date_str)
            os.makedirs(output_dir, exist_ok=True)
            output_path = os.path.join(output_dir, "all.csv")
            final_df.write_csv(output_path)
            print(f"  [+] Saved {final_df.height} records to {output_path}")

            # Run QC immediately after processing each quarter
            print(f"  Auditing quarterly_reports data for {date_str}...")
            try:
                issues = run_quality_check(date_str, date_str)
                if issues:
                    print(f"❌ Quarterly reports data quality check failed for {date_str}")
                    for issue in issues[:20]:
                        print(f"   - {issue}")
                    if len(issues) > 20:
                        print(f"   ... and {len(issues) - 20} more issues")
                    print(f"❌ Processing stopped due to data quality error. Fix the issue and re-run.")
                    sys.exit(1)
                print(f"✅ Quarterly reports data quality check passed for {date_str}")
            except ValueError as e:
                print(f"❌ Quarterly reports quality checker configuration error: {e}")
                print("❌ Processing stopped due to quality checker configuration error.")
                sys.exit(1)

            # 簡易資料品質檢查 (Post-processing check)
            if final_df.is_empty():
                print(f"  [!] Warning: {date_str} generated an empty CSV.")
            else:
                # 檢查關鍵欄位是否全為 null (代表映射可能錯誤)
                for col in ["revenue", "eps", "net_income"]:
                    if col in final_df.columns:
                        null_count = final_df.select(pl.col(col).null_count()).item()
                        if null_count == final_df.height:
                            print(f"  [!] CRITICAL: Column '{col}' is entirely NULL in {date_str}. Check mapping logic.")


if __name__ == "__main__":
    main()
