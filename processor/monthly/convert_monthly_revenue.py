import os
import sys
import glob
import datetime
import re
import pandas as pd
import numpy as np
from .audit_monthly_revenue import MonthlyRevenueChecker
from audit_base import DataQualityError

RAW_DIR = "/app/data/raw/monthly_revenue"
PROCESSED_DIR = "/app/data/processed/monthly_revenue"
DEBUG = os.getenv("DEBUG", "0") == "1"

# Final output column order (schema) - src_col is generated based on this order
SCHEMA_COLS = ['date', 'market', 'symbol', 'name', 'revenue_current', 'revenue_last_month',
               'revenue_last_year', 'mom_pct', 'yoy_pct', 'revenue_cumulative',
               'revenue_cumulative_last_year', 'cumulative_yoy_pct', 'comment']


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

# 欄位映射字典（中文列名）
COL_MAPPING = {
    "公司代號": "symbol",
    "公司名稱": "name",
    "當月營收": "revenue_current",
    "上月營收": "revenue_last_month",
    "去年當月營收": "revenue_last_year",
    "上月比較增減(%)": "mom_pct",
    "去年同月增減(%)": "yoy_pct",
    "當月累計營收": "revenue_cumulative",
    "去年累計營收": "revenue_cumulative_last_year",
    "前期比較增減(%)": "cumulative_yoy_pct",
    "備註": "comment",
    # Ignore columns (mapped to None)
    "出表日期": None,
    "資料年月": None,
}

# 英文列名映射（用於已經處理過的原始數據）
COL_MAPPING_EN = {
    "symbol": "symbol",
    "name": "name",
    "revenue": "revenue_current",
    "revenue_last_month": "revenue_last_month",
    "revenue_last_year": "revenue_last_year",
    "mom_pct": "mom_pct",
    "yoy_pct": "yoy_pct",
    "revenue_acc": "revenue_cumulative",
    "revenue_acc_last_year": "revenue_cumulative_last_year",
    "acc_yoy_pct": "cumulative_yoy_pct",
    "comment": "comment",
    # Known columns to ignore (internal use)
    "market": None,  # Handled separately
}

def clean_number(x):
    """清理數值字串：移除逗號，轉換為 float，處理空值"""
    if pd.isna(x) or str(x).strip() == "":
        return None
    try:
        val_str = str(x).replace(",", "").strip()
        if val_str.startswith("(") and val_str.endswith(")"):
            val_str = "-" + val_str[1:-1]
        return float(val_str)
    except:
        return None


def normalize_column_name(col: str) -> str:
    """Normalize column name for matching: lowercase, remove spaces/punctuation."""
    col = col.strip().replace("\n", "").replace(" ", "")
    col = re.sub(r'[（）()]', '', col)  # Remove parentheses
    return col.lower()


def validate_and_map_columns(df_columns: list, use_mapping: dict, is_english: bool, file_path: str) -> tuple:
    """
    Validate all columns have mappings and return column maps.

    Returns:
        tuple: (rename_map, col_mapping)
            - rename_map: {source_column_name: target_column_name} for renaming
            - col_mapping: {target_column_name: 1-based_column_index} for src_col generation

    Raises:
        ValueError: If unknown column found without mapping
    """
    rename_map = {}  # source_col -> target_col (for renaming)
    col_mapping = {}  # target_col -> 1-based index (for src_col)

    for idx, col in enumerate(df_columns):
        col_clean = col.strip().replace("\n", "")
        matched = False

        for key, target in use_mapping.items():
            # English uses exact match, Chinese uses contains match
            if is_english:
                match_found = (col_clean == key)
            else:
                match_found = (key in col_clean)

            if match_found:
                matched = True
                if target is not None and target not in col_mapping:
                    rename_map[col_clean] = target
                    col_mapping[target] = idx + 1  # 1-based index
                break

        if not matched:
            # Check if it's a known ignored column
            norm_col = normalize_column_name(col_clean)
            if norm_col in ['market']:  # market is handled separately
                continue
            raise ValueError(
                f"Unknown column '{col_clean}' at index {idx + 1} in {file_path}. "
                f"Please add mapping to COL_MAPPING or COL_MAPPING_EN in convert_monthly_revenue.py"
            )

    return rename_map, col_mapping

def process_monthly_revenue():
    start_env = os.getenv("START_DATE")
    end_env = os.getenv("END_DATE")
    if not start_env or not end_env:
        print("Error: START_DATE and END_DATE are both required (YYYYMMDD or YYYYMM).")
        print("Example: START_DATE=20240101 END_DATE=20240131 python convert_monthly.py")
        sys.exit(1)

    if len(start_env) < 6 or len(end_env) < 6:
        print(f"Error: Invalid date format (START_DATE={start_env}, END_DATE={end_env}).")
        print("Expected at least YYYYMM (e.g., YYYYMMDD or YYYYMM).")
        sys.exit(1)

    start_cmp = start_env[:6]
    end_cmp = end_env[:6]
    if not (start_cmp.isdigit() and end_cmp.isdigit()):
        print(f"Error: Invalid date format (START_DATE={start_env}, END_DATE={end_env}).")
        print("Expected numeric YYYYMM prefix.")
        sys.exit(1)

    if start_cmp > end_cmp:
        print(f"Error: START_DATE must be <= END_DATE (START_DATE={start_env}, END_DATE={end_env}).")
        sys.exit(1)

    if not os.path.exists(RAW_DIR):
        print(f"Raw revenue directory not found: {RAW_DIR}")
        return

    # 取得所有目錄（僅新格式 YYYY/YYYYMXX）
    all_dirs = []
    for d in os.listdir(RAW_DIR):
        if len(d) == 4 and d.isdigit():
            year_path = os.path.join(RAW_DIR, d)
            if os.path.isdir(year_path):
                for sub_d in os.listdir(year_path):
                    if len(sub_d) == 7 and "M" in sub_d:
                        all_dirs.append(os.path.join(year_path, sub_d))
    
    all_dirs.sort()
    
    for dir_path in all_dirs:
        dir_name = os.path.basename(dir_path)
        
        # YYYYMXX -> YYYYMM
        ym_comparable = dir_name.replace("M", "")
        date_str = dir_name

        # 過濾邏輯 (START_DATE/END_DATE 通常是 YYYYMMDD 或 YYYYMM)
        if ym_comparable < start_cmp:
            continue
        if ym_comparable > end_cmp:
            continue

        print(f"Processing revenue for {dir_name}...")
        
        year_str = dir_name[:4]
        month_str = dir_name[5:7]
            
        csv_files = glob.glob(os.path.join(dir_path, "*.csv"))

        dfs = []
        for file_path in csv_files:
            try:
                # 嘗試判斷 header 位置
                with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                    lines = [f.readline() for _ in range(5)]

                header_row = 0
                for i, line in enumerate(lines):
                    if "公司代號" in line or "symbol" in line.lower():
                        header_row = i
                        break

                df = pd.read_csv(file_path, header=header_row, encoding='utf-8', thousands=',')
                df.columns = [c.strip().replace("\n", "") for c in df.columns]

                # 判斷使用中文或英文映射（英文用精確匹配，中文用包含匹配）
                is_english = "symbol" in df.columns
                use_mapping = COL_MAPPING_EN if is_english else COL_MAPPING

                # Validate columns and get mapping with indices
                rename_map, col_mapping = validate_and_map_columns(
                    df.columns.tolist(), use_mapping, is_english, file_path
                )

                # Calculate relative path for src_file
                # Convert absolute path to relative path from /app/data/raw
                rel_path = file_path.replace("/Users/poyilee/Documents/GitHubLL/my_stock_project/", "/app/")

                # Build new dataframe with lineage tracking
                new_df = pd.DataFrame()

                # 處理 market 欄位：如果原始資料已經有 market 欄位，使用它；否則從檔名判斷
                if 'market' in df.columns:
                    new_df['market'] = df['market'].str.upper()
                    market_idx = df.columns.tolist().index('market') + 1
                    col_mapping['market'] = market_idx
                else:
                    market = "SII" if "sii" in file_path.lower() else "OTC" if "otc" in file_path.lower() else "UNKNOWN"
                    new_df['market'] = market
                    # market derived from filename, not in col_mapping (will be 'x')

                # Add data columns using rename_map
                for src_col_name, target in rename_map.items():
                    if target != 'market':  # market already handled above
                        new_df[target] = df[src_col_name]

                # Add missing columns as None
                for col in SCHEMA_COLS:
                    if col not in new_df.columns and col != 'date':
                        new_df[col] = None

                # Generate src_col based on SCHEMA_COLS order
                src_col_str = generate_src_col(SCHEMA_COLS, col_mapping)

                # Add lineage columns
                # src_row: 1-based line number (header_row + 1 for header, then data rows)
                # The first data row is at line header_row + 2 (1-indexed)
                new_df['src_file'] = rel_path
                new_df['src_row'] = range(header_row + 2, header_row + 2 + len(df))
                new_df['src_col'] = src_col_str

                if DEBUG:
                    print(f"  ✓ Parsed {file_path}: {len(df)} rows, src_col={new_df['src_col'].iloc[0] if len(new_df) > 0 else 'N/A'}")

                dfs.append(new_df)

            except ValueError as e:
                # Fail-fast on validation errors
                print(f"❌ Validation error: {e}")
                sys.exit(1)
            except Exception as e:
                print(f"Error processing {file_path}: {e}")
                continue
        
        if not dfs:
            print(f"No valid data found for {date_str}")
            continue

        final_df = pd.concat(dfs, ignore_index=True)
        final_df = final_df[final_df['symbol'].notna()]
        final_df = final_df[final_df['symbol'].astype(str).str.match(r'^\d+$')]

        num_cols = ["revenue_current", "revenue_last_month", "revenue_last_year", "mom_pct", "yoy_pct",
                    "revenue_cumulative", "revenue_cumulative_last_year", "cumulative_yoy_pct"]

        for col in num_cols:
            if col in final_df.columns:
                final_df[col] = final_df[col].apply(clean_number)

        # 使用 YYYYMXX 格式，例如 2025M01
        final_df['date'] = f"{year_str}M{month_str}"

        # Reorder columns: schema columns + lineage columns
        col_order = SCHEMA_COLS + ['src_file', 'src_row', 'src_col']
        final_df = final_df[[c for c in col_order if c in final_df.columns]]

        # 輸出路徑格式: data/processed/monthly_revenue/YYYY/YYYYMXX/
        output_dir = os.path.join(PROCESSED_DIR, year_str, f"{year_str}M{month_str}")
        os.makedirs(output_dir, exist_ok=True)

        output_file = os.path.join(output_dir, "all.csv")
        final_df.to_csv(output_file, index=False, encoding='utf-8')
        print(f"Saved {len(final_df)} records to {output_file}")

        # Run QC immediately after processing each month
        qc_date_str = f"{year_str}{month_str}01"
        print(f"Auditing monthly_revenue data for {year_str}M{month_str}...")
        try:
            checker = MonthlyRevenueChecker(qc_date_str)
            checker.check()
            print(f"✅ Monthly revenue data quality check passed for {year_str}M{month_str}")
        except DataQualityError as e:
            error_msg = f"Monthly revenue data quality check failed: {str(e)}"
            print(f"❌ {error_msg}")
            print("❌ Processing stopped due to data quality error. Fix the issue and re-run.")
            sys.exit(1)

if __name__ == "__main__":
    process_monthly_revenue()
