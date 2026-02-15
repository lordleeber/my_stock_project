import os
import sys
import glob
import csv
from pathlib import Path
import re
import polars as pl

RAW_DIR = os.environ.get("RAW_DIR", "data/raw")
PROCESSED_DIR = os.environ.get("PROCESSED_DIR", "data/processed")
DEBUG = os.getenv("DEBUG", "0") == "1"

INCOME_MAP = {
    "營業收入": "revenue",
    "收益": "revenue",
    "營業成本": "cost_of_revenue",
    "支出及費用": "expenses",
    "營業毛利（毛損）": "gross_profit",
    "營業毛利（毛損）淨額": "gross_profit",
    "營業費用": "operating_expense",
    "其他收益及費損淨額": "other_income_net",
    "營業利益（損失）": "operating_income",
    "營業利益": "operating_income",
    "營業外收入及支出": "non_operating_income",
    "營業外損益": "non_operating_income",
    "稅前淨利（淨損）": "pretax_income",
    "所得稅費用（利益）": "tax_expense",
    "繼續營業單位本期淨利（淨損）": "net_income",
    "繼續營業單位本期稅後淨利（淨損）": "net_income",
    "本期淨利（淨損）": "net_income",
    "本期稅後淨利（淨損）": "net_income",
    "本期稅後純益（純損）": "net_income",
    "基本每股盈餘（元）": "eps",
    "其他綜合損益（淨額）": "other_comprehensive_income",
    "本期其他綜合損益（稅後淨額）": "other_comprehensive_income",
    "本期綜合損益總額": "comprehensive_income",
    "利息淨收益": "net_interest_income",
    "利息以外淨損益": "non_interest_income",
    "利息以外淨收益": "non_interest_income",
    "淨收益": "net_revenue",
}

BALANCE_MAP = {
    "流動資產": "current_assets",
    "非流動資產": "noncurrent_assets",
    "資產總計": "total_assets",
    "資產總額": "total_assets",
    "流動負債": "current_liabilities",
    "非流動負債": "noncurrent_liabilities",
    "負債總計": "total_liabilities",
    "負債總額": "total_liabilities",
    "權益總計": "total_equity",
    "權益總額": "total_equity",
    "股本": "share_capital",
    "資本公積": "capital_surplus",
    "保留盈餘（或累積虧損）": "retained_earnings",
    "保留盈餘": "retained_earnings",
    "其他權益": "other_equity",
    "庫藏股票": "treasury_shares",
    "每股參考淨值": "nav_per_share",
    "歸屬於母公司業主權益合計": "equity_parent",
}

CASHFLOW_MAP = {
    "營業活動之淨現金流入（流出）": "cash_flow_operating",
    "投資活動之淨現金流入（流出）": "cash_flow_investing",
    "籌資活動之淨現金流入（流出）": "cash_flow_financing",
    "匯率變動對現金及約當現金之影響": "fx_effect",
    "本期現金及約當現金增加（減少）數": "net_cash_change",
    "期初現金及約當現金餘額": "cash_begin",
    "期末現金及約當現金餘額": "cash_end",
}

INCOME_SCHEMA_COLS = [
    "date", "market", "symbol", "name", "statement_type",
    "revenue", "cost_of_revenue", "gross_profit", "operating_expense",
    "operating_income", "non_operating_income", "pretax_income", "tax_expense",
    "net_income", "other_comprehensive_income", "comprehensive_income", "eps",
    "net_interest_income", "non_interest_income", "net_revenue", "other_income_net",
]

BALANCE_SCHEMA_COLS = [
    "date", "market", "symbol", "name", "statement_type",
    "current_assets", "noncurrent_assets", "total_assets",
    "current_liabilities", "noncurrent_liabilities", "total_liabilities",
    "total_equity", "equity_parent",
    "share_capital", "capital_surplus", "retained_earnings",
    "other_equity", "treasury_shares", "nav_per_share",
]

CASHFLOW_SCHEMA_COLS = [
    "date", "market", "symbol", "name", "statement_type",
    "cash_flow_operating", "cash_flow_investing", "cash_flow_financing",
    "fx_effect", "net_cash_change", "cash_begin", "cash_end",
]

INCOME_SCHEMA = INCOME_SCHEMA_COLS + ["src_file", "src_row", "src_col"]
BALANCE_SCHEMA = BALANCE_SCHEMA_COLS + ["src_file", "src_row", "src_col"]
CASHFLOW_SCHEMA = CASHFLOW_SCHEMA_COLS + ["src_file", "src_row", "src_col"]

NUMERIC_COLS = set(INCOME_SCHEMA_COLS + BALANCE_SCHEMA_COLS + CASHFLOW_SCHEMA_COLS) - {
    "date", "market", "symbol", "name", "statement_type"
}

SYMBOL_COLS = ("公司 代號", "公司代號", "代號", "證券代號")
NAME_COLS = ("公司名稱", "名稱", "證券名稱")


def clean_numeric(val):
    if val is None or val == "--" or str(val).strip() == "":
        return None
    try:
        s = str(val).replace(",", "").strip()
        if s.startswith("(") and s.endswith(")"):
            s = "-" + s[1:-1]
        return float(s)
    except Exception:
        return None


def detect_statement_type(market, filename):
    base = os.path.splitext(filename)[0]
    if base.startswith(f"{market}_"):
        base = base[len(market) + 1:]
    if base.startswith("cashflow_"):
        base = base[len("cashflow_"):]
    base = re.sub(r"\d+$", "", base)
    return base or "unknown"


def build_col_mapping(headers, mapping):
    col_mapping = {}
    for idx, col in enumerate(headers):
        col_clean = col.strip()
        if col_clean in SYMBOL_COLS:
            col_mapping.setdefault("symbol", idx + 1)
        elif col_clean in NAME_COLS:
            col_mapping.setdefault("name", idx + 1)
        elif col_clean in mapping:
            target = mapping[col_clean]
            col_mapping.setdefault(target, idx + 1)
    return col_mapping


def generate_src_col(schema_cols, col_mapping):
    src_col_parts = []
    for col in schema_cols:
        if col in col_mapping:
            src_col_parts.append(str(col_mapping[col]))
        else:
            src_col_parts.append("x")
    return "#".join(src_col_parts)


def process_csv_file(csv_file, date_str, market, mapping, schema, schema_cols):
    try:
        with open(csv_file, 'r', encoding='utf-8-sig', errors='replace') as f:
            reader = csv.reader(f)
            rows = list(reader)
        if not rows:
            print(f"❌ Empty file: {csv_file}")
            sys.exit(1)

        headers = [h.strip() for h in rows[0]]
        col_mapping = build_col_mapping(headers, mapping)
        rel_path = csv_file.replace("/Users/poyilee/Documents/GitHubLL/my_stock_project/", "/app/")
        statement_type = detect_statement_type(market, os.path.basename(csv_file))
        src_col_str = generate_src_col(schema_cols, col_mapping)

        df = pl.read_csv(csv_file, encoding="utf-8-sig", infer_schema_length=0)
        if df.is_empty():
            return None

        symbol_col = None
        for col in df.columns:
            c = col.strip()
            if c in SYMBOL_COLS:
                symbol_col = col
                break
        if symbol_col is None:
            print(f"❌ Missing symbol column in {csv_file}")
            sys.exit(1)

        rename = {}
        for col in df.columns:
            c = col.strip()
            if c in SYMBOL_COLS:
                rename[col] = "symbol"
            elif c in NAME_COLS:
                rename[col] = "name"
        if rename:
            df = df.rename(rename)

        df = df.with_columns([
            pl.lit(date_str).alias("date"),
            pl.lit(market).alias("market"),
            pl.lit(statement_type).alias("statement_type"),
            pl.lit(rel_path).alias("src_file"),
            pl.lit(src_col_str).alias("src_col"),
        ])
        df = df.with_row_index("_row_idx")
        df = df.with_columns((pl.col("_row_idx") + 2).cast(pl.Int64).alias("src_row"))
        df = df.drop("_row_idx")

        for col in df.columns:
            col_clean = col.strip()
            if col_clean in mapping:
                target = mapping[col_clean]
                if target not in df.columns:
                    df = df.with_columns(pl.col(col).alias(target))
                else:
                    df = df.with_columns(pl.coalesce([pl.col(target), pl.col(col)]).alias(target))

        for col in schema:
            if col not in df.columns:
                df = df.with_columns(pl.lit(None).alias(col))

        for col in schema:
            if col in NUMERIC_COLS and col in df.columns:
                df = df.with_columns(pl.col(col).map_elements(clean_numeric, return_dtype=pl.Float64).alias(col))

        df = df.select(schema)

        if DEBUG:
            print(f"    ✓ {os.path.basename(csv_file)}: {df.height} rows, src_col={src_col_str[:50]}...")

        return df

    except ValueError as e:
        print(f"❌ Validation error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error processing {csv_file}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def process_category(category, qc_runner):
    raw_path = os.path.join(RAW_DIR, category)
    if not os.path.exists(raw_path):
        print(f"Raw dir not found: {raw_path}")
        return

    if category == "income_statement":
        mapping = INCOME_MAP
        schema = INCOME_SCHEMA
        schema_cols = INCOME_SCHEMA_COLS
    elif category == "balance_sheet":
        mapping = BALANCE_MAP
        schema = BALANCE_SCHEMA
        schema_cols = BALANCE_SCHEMA_COLS
    else:
        mapping = CASHFLOW_MAP
        schema = CASHFLOW_SCHEMA
        schema_cols = CASHFLOW_SCHEMA_COLS

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
        date_str = date_dir.name
        if date_str < start_env:
            continue
        if date_str > end_env:
            continue

        print(f"Processing {category} {date_str}...")

        year_str = date_str[:4]
        output_dir = os.path.join(PROCESSED_DIR, category, year_str, date_str)
        os.makedirs(output_dir, exist_ok=True)
        output_file = os.path.join(output_dir, "all.csv")

        all_dfs = []
        for csv_file in sorted(glob.glob(os.path.join(str(date_dir), "*.csv"))):
            market = os.path.basename(csv_file).split("_")[0]
            df = process_csv_file(csv_file, date_str, market, mapping, schema, schema_cols)
            if df is not None and not df.is_empty():
                all_dfs.append(df)

        if all_dfs:
            final_df = pl.concat(all_dfs)
            final_df.write_csv(output_file)
            print(f"  [+] Saved {final_df.height} rows to {output_file}")

            print(f"  Auditing {category} data for {date_str}...")
            try:
                issues = qc_runner(date_str, date_str)
                if issues:
                    print(f"❌ {category} data quality check failed for {date_str}")
                    for issue in issues[:20]:
                        print(f"   - {issue}")
                    if len(issues) > 20:
                        print(f"   ... and {len(issues) - 20} more issues")
                    print("❌ Processing stopped due to data quality error. Fix the issue and re-run.")
                    sys.exit(1)
                print(f"✅ {category} data quality check passed for {date_str}")
            except ValueError as e:
                print(f"❌ {category} quality checker configuration error: {e}")
                print("❌ Processing stopped due to quality checker configuration error.")
                sys.exit(1)

            if final_df.is_empty():
                print(f"  [!] Warning: {date_str} generated an empty CSV.")
        else:
            print(f"❌ No data for {date_str}")
            sys.exit(1)
