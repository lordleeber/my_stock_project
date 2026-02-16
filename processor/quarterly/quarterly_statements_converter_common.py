import os
import sys
import glob
import csv
from pathlib import Path
import re
import polars as pl

# 加入 common 目錄到搜尋路徑
sys.path.append(os.path.join(os.path.dirname(__file__), "../.."))
from common.schemas import SCHEMA_COLS, get_polars_schema

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

SYMBOL_COLS = ("公司 代號", "公司代號", "代號", "證券代號")
NAME_COLS = ("公司名稱", "名稱", "證券名稱")


def get_prev_quarter(date_str):
    year = int(date_str[:4])
    q = int(date_str[5])
    if q == 1: return None
    return f"{year}Q{q-1}"


def load_prev_data(category, prev_q_str):
    if not prev_q_str: return None
    year_str = prev_q_str[:4]
    path = os.path.join(PROCESSED_DIR, category, year_str, prev_q_str, "all.csv")
    if os.path.exists(path):
        try:
            schema = get_polars_schema(category)
            return pl.read_csv(path, schema_overrides=schema or {})
        except Exception: return None
    return None


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
        base_col = col.replace("_q", "").replace("_acc", "")
        if base_col in col_mapping:
            src_col_parts.append(str(col_mapping[base_col]))
        else:
            src_col_parts.append("x")
    return "#".join(src_col_parts)


def process_csv_file(csv_file, date_str, market, category, mapping, prev_df=None):
    try:
        with open(csv_file, 'r', encoding='utf-8-sig', errors='replace') as f:
            reader = csv.reader(f)
            rows = list(reader)
        if not rows: return None

        headers = [h.strip() for h in rows[0]]
        col_mapping = build_col_mapping(headers, mapping)
        rel_path = csv_file.replace("/Users/poyilee/Documents/GitHubLL/my_stock_project/", "/app/")
        statement_type = detect_statement_type(market, os.path.basename(csv_file))
        
        schema = SCHEMA_COLS.get(category)
        if not schema: sys.exit(1)
        src_col_str = generate_src_col(schema, col_mapping)

        df = pl.read_csv(csv_file, encoding="utf-8-sig", infer_schema_length=0)
        if df.is_empty(): return None

        # Symbol & Name
        rename = {col: "symbol" for col in df.columns if col.strip() in SYMBOL_COLS}
        rename.update({col: "name" for col in df.columns if col.strip() in NAME_COLS})
        df = df.rename(rename)
        df = df.filter(pl.col("symbol").cast(pl.Utf8).str.contains(r"^\d{4}$"))

        df = df.with_columns([
            pl.lit(date_str).alias("date"),
            pl.lit(market).alias("market"),
            pl.lit(statement_type).alias("statement_type"),
            pl.lit(rel_path).alias("src_file"),
            pl.lit(src_col_str).alias("src_col"),
        ])
        df = df.with_row_index("_row_idx").with_columns((pl.col("_row_idx")+2).cast(pl.Int64).alias("src_row")).drop("_row_idx")

        is_flow = category in ("income_statement", "cash_flow")
        is_q1 = date_str.endswith("Q1")

        # Extract numeric columns
        for raw_name, target_base in mapping.items():
            if raw_name in headers:
                df = df.with_columns(pl.col(raw_name).map_elements(clean_numeric, return_dtype=pl.Float64).alias(target_base))

        # Flow Subtraction Logic
        if is_flow:
            for target_base in set(mapping.values()):
                if target_base in df.columns:
                    acc_col = f"{target_base}_acc"
                    q_col = f"{target_base}_q"
                    df = df.with_columns(pl.col(target_base).alias(acc_col))
                    
                    if is_q1:
                        df = df.with_columns(pl.col(acc_col).alias(q_col))
                    else:
                        if prev_df is not None and acc_col in prev_df.columns:
                            df = df.join(prev_df.select(["symbol", acc_col]).rename({acc_col: "_prev_val"}), on="symbol", how="left")
                            df = df.with_columns(
                                pl.when(pl.col("_prev_val").is_not_null())
                                .then((pl.col(acc_col) - pl.col("_prev_val")).round(2))
                                .otherwise(pl.col(acc_col)).alias(q_col)
                            ).drop("_prev_val")
                        else:
                            df = df.with_columns(pl.col(acc_col).alias(q_col))
        
        for col in schema:
            if col not in df.columns: df = df.with_columns(pl.lit(None).alias(col))
        
        return df.select(schema)

    except Exception as e:
        print(f"Error processing {csv_file}: {e}")
        import traceback; traceback.print_exc(); sys.exit(1)


def process_category(category, qc_runner):
    raw_path = os.path.join(RAW_DIR, category)
    if not os.path.exists(raw_path): return

    if category == "income_statement": mapping = INCOME_MAP
    elif category == "balance_sheet": mapping = BALANCE_MAP
    else: mapping = CASHFLOW_MAP

    date_dirs = sorted(Path(raw_path).rglob("????Q[1-4]"))
    start_env, end_env = os.getenv("START_DATE"), os.getenv("END_DATE")
    
    for date_dir in date_dirs:
        date_str = date_dir.name
        if date_str < start_env or date_str > end_env: continue

        print(f"Processing {category} {date_str}...")
        prev_df = load_prev_data(category, get_prev_quarter(date_str))
        
        output_dir = os.path.join(PROCESSED_DIR, category, date_str[:4], date_str)
        os.makedirs(output_dir, exist_ok=True)
        
        all_dfs = []
        for csv_file in sorted(glob.glob(os.path.join(str(date_dir), "*.csv"))):
            market = os.path.basename(csv_file).split("_")[0]
            df = process_csv_file(csv_file, date_str, market, category, mapping, prev_df=prev_df)
            if df is not None: all_dfs.append(df)

        if all_dfs:
            # 強制轉換所有 DataFrame 的型別以避免 concat 錯誤
            schema = get_polars_schema(category)
            casted_dfs = []
            for df in all_dfs:
                cast_exprs = []
                for col, dtype in schema.items():
                    if col in df.columns:
                        cast_exprs.append(pl.col(col).cast(dtype, strict=False))
                casted_dfs.append(df.with_columns(cast_exprs))
            
            final_df = pl.concat(casted_dfs).unique(subset=["symbol"])
            final_df.write_csv(os.path.join(output_dir, "all.csv"))
            print(f"  [+] Saved {final_df.height} rows")
