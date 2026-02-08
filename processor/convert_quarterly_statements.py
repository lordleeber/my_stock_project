import os
import glob
import re
import polars as pl
import pandas as pd

RAW_DIR = os.environ.get("RAW_DIR", "data/raw")
PROCESSED_DIR = os.environ.get("PROCESSED_DIR", "data/processed")

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

INCOME_SCHEMA = [
    "date", "market", "symbol", "name", "statement_type",
    "revenue", "cost_of_revenue", "gross_profit", "operating_expense",
    "operating_income", "non_operating_income", "pretax_income", "tax_expense",
    "net_income", "other_comprehensive_income", "comprehensive_income", "eps",
    "net_interest_income", "non_interest_income", "net_revenue", "other_income_net",
]

BALANCE_SCHEMA = [
    "date", "market", "symbol", "name", "statement_type",
    "current_assets", "noncurrent_assets", "total_assets",
    "current_liabilities", "noncurrent_liabilities", "total_liabilities",
    "total_equity", "equity_parent",
    "share_capital", "capital_surplus", "retained_earnings",
    "other_equity", "treasury_shares", "nav_per_share",
]

CASHFLOW_SCHEMA = [
    "date", "market", "symbol", "name", "statement_type",
    "cash_flow_operating", "cash_flow_investing", "cash_flow_financing",
    "fx_effect", "net_cash_change", "cash_begin", "cash_end",
]

NUMERIC_COLS = set(INCOME_SCHEMA + BALANCE_SCHEMA + CASHFLOW_SCHEMA) - {
    "date", "market", "symbol", "name", "statement_type"
}

def clean_numeric(val):
    if pd.isna(val) or val == "--" or str(val).strip() == "":
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

def map_and_standardize(df, category):
    if category == "income_statement":
        mapping = INCOME_MAP
        schema = INCOME_SCHEMA
    elif category == "balance_sheet":
        mapping = BALANCE_MAP
        schema = BALANCE_SCHEMA
    else:
        mapping = CASHFLOW_MAP
        schema = CASHFLOW_SCHEMA

    # Build target -> sources to avoid duplicate column names after mapping.
    target_sources = {}
    for col in df.columns:
        if col in mapping:
            target = mapping[col]
            target_sources.setdefault(target, []).append(col)
    for target in list(target_sources.keys()):
        if target in df.columns and target not in target_sources[target]:
            target_sources[target] = [target] + target_sources[target]

    for target, sources in target_sources.items():
        if len(sources) == 1:
            df = df.with_columns(pl.col(sources[0]).alias(target))
        else:
            df = df.with_columns(pl.coalesce([pl.col(s) for s in sources]).alias(target))

    # Ensure required columns
    for col in schema:
        if col not in df.columns:
            df = df.with_columns(pl.lit(None).alias(col))

    # Normalize numeric columns
    for col in schema:
        if col in NUMERIC_COLS:
            df = df.with_columns(
                pl.col(col)
                .map_elements(clean_numeric, return_dtype=pl.Float64)
                .alias(col)
            )
    return df.select(schema)

def process_category(category):
    raw_path = os.path.join(RAW_DIR, category)
    if not os.path.exists(raw_path):
        print(f"Raw dir not found: {raw_path}")
        return

    date_dirs = sorted(glob.glob(os.path.join(raw_path, "date=*")))
    for date_dir in date_dirs:
        date_str = os.path.basename(date_dir).split("=")[1]
        output_dir = os.path.join(PROCESSED_DIR, category, f"date={date_str}")
        os.makedirs(output_dir, exist_ok=True)
        output_file = os.path.join(output_dir, "all.csv")

        all_dfs = []
        for csv_file in sorted(glob.glob(os.path.join(date_dir, "*.csv"))):
            market = os.path.basename(csv_file).split("_")[0]
            statement_type = detect_statement_type(market, os.path.basename(csv_file))
            try:
                df = pl.read_csv(csv_file, encoding="utf-8-sig", infer_schema_length=0)
            except Exception:
                continue
            if df.is_empty() or "公司 代號" not in df.columns and "代號" not in df.columns and "證券代號" not in df.columns:
                continue

            rename = {}
            for col in df.columns:
                c = col.strip()
                if c in ("公司 代號", "公司代號", "代號", "證券代號"):
                    rename[col] = "symbol"
                elif c in ("公司名稱", "名稱", "證券名稱"):
                    rename[col] = "name"
            if rename:
                df = df.rename(rename)

            df = df.with_columns(
                pl.lit(date_str).alias("date"),
                pl.lit(market).alias("market"),
                pl.lit(statement_type).alias("statement_type"),
            )
            df = map_and_standardize(df, category)
            all_dfs.append(df)

        if all_dfs:
            final_df = pl.concat(all_dfs)
            final_df.write_csv(output_file)
            print(f"[+] {category} {date_str}: {final_df.height} rows")

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Convert MOPS quarterly statements to standardized schemas.")
    parser.add_argument("--category", required=True, choices=["income_statement", "balance_sheet", "cash_flow"])
    args = parser.parse_args()
    process_category(args.category)

if __name__ == "__main__":
    main()
