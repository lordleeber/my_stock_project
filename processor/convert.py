"""
通用 ETL 處理進入點 (Finalized)

整合所有類別的處理邏輯，包含個股、彙總表、大盤指數。
"""

import os
import datetime
import io
import polars as pl
import pandas as pd
from schemas import SCHEMA_COLS, COLUMN_MAP, NUMERIC_COLS
from utils import read_raw_csv, read_sii_indices

RAW_DIR = os.getenv("RAW_DIR", "/app/data/raw")
PROCESSED_DIR = os.getenv("PROCESSED_DIR", "/app/data/processed")

INSTITUTION_MAP = {
    "自營商(自行買賣)": "dealer_self", "自營商(避險)": "dealer_hedge",
    "投信": "investment_trust", "外資及陸資(不含外資自營商)": "foreign_investors",
    "外資自營商": "foreign_dealer", "合計": "total",
    "自營商(自行買賣)\u3000": "dealer_self", "自營商(避險)\u3000": "dealer_hedge",
    "外資及陸資(不含自營商)": "foreign_investors", "外資及陸資合計": "foreign_total",
    "自營商合計": "dealer_total", "三大法人合計*": "total", "三大法人合計": "total",
}
KEEP_INSTITUTIONS = ["dealer_self", "dealer_hedge", "investment_trust", "foreign_investors", "foreign_dealer", "total"]

def enforce_schema(df, category):
    if category not in SCHEMA_COLS: return df
    required_cols = SCHEMA_COLS[category]
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        df = df.with_columns([pl.lit(None).alias(col) for col in missing_cols])
    return df.select(required_cols)

def _handle_generic_category(file_path, market, category, date_str):
    df = read_raw_csv(file_path, category=category)
    if df is None or df.is_empty(): return None
    df = df.with_columns([
        pl.lit(date_str).str.strptime(pl.Date, "%Y%m%d").alias("date"),
        pl.lit(market).alias("market")
    ])
    if "symbol" in df.columns:
        df = df.filter((pl.col("symbol").is_not_null()) & (pl.col("symbol") != ""))
        df = df.filter(pl.col("symbol").str.len_chars().is_between(2, 10))
    return df

def _handle_institutional_summary(date_str):
    input_dir = f"{RAW_DIR}/institutional_summary/date={date_str}"
    all_dfs = []
    for market in ["sii", "otc"]:
        file_path = os.path.join(input_dir, f"{market}.csv")
        if not os.path.exists(file_path): continue
        try:
            df = pl.read_csv(file_path, encoding="utf-8-sig", infer_schema_length=0)
            if df.is_empty(): continue
            rename_map = {}
            for col in df.columns:
                c = col.strip()
                if c == "單位名稱": rename_map[col] = "institution"
                elif "買進" in c: rename_map[col] = "buy"
                elif "賣出" in c: rename_map[col] = "sell"
                elif "差額" in c or "買賣超" in c: rename_map[col] = "net"
            df = df.select(list(rename_map.keys())).rename(rename_map)
            df = df.with_columns(pl.col("institution").str.strip_chars().replace(INSTITUTION_MAP))
            df = df.filter(pl.col("institution").is_in(KEEP_INSTITUTIONS))
            for col in ["buy", "sell", "net"]:
                if col in df.columns:
                    df = df.with_columns(pl.col(col).str.replace_all(",", "").cast(pl.Int64, strict=False))
            df = df.with_columns([pl.lit(date_str).str.strptime(pl.Date, "%Y%m%d").alias("date"), pl.lit(market).alias("market")])
            all_dfs.append(df.select(["date", "market", "institution", "buy", "sell", "net"]))
        except: pass
    return pl.concat(all_dfs) if all_dfs else None

def _handle_margin_summary(date_str):
    input_dir = f"{RAW_DIR}/margin_trading/date={date_str}"; results = []
    sii_path = os.path.join(input_dir, "sii.csv")
    if os.path.exists(sii_path):
        try:
            with open(sii_path, 'r', encoding='utf-8-sig') as f: lines = [f.readline() for _ in range(4)]
            df = pd.read_csv(io.StringIO("".join(lines))); df.columns = [c.strip() for c in df.columns]
            for _, row in df.iterrows():
                item = str(row['項目']).strip()
                if "融資" in item or "融券" in item:
                    results.append({"date": datetime.datetime.strptime(date_str, "%Y%m%d").date(), "market": "SII", "item": item, "buy": int(str(row['買進']).replace(",", "")), "sell": int(str(row['賣出']).replace(",", "")), "cash_repay": int(str(row['現金(券)償還']).replace(",", "")), "prev_balance": int(str(row['前日餘額']).replace(",", "")), "today_balance": int(str(row['今日餘額']).replace(",", ""))})
        except: pass
    otc_path = os.path.join(input_dir, "otc.csv")
    if os.path.exists(otc_path):
        try:
            with open(otc_path, 'r', encoding='utf-8-sig') as f: lines = f.readlines()
            for line in lines[-5:]:
                if "合計(張)" in line or "融資金(仟元)" in line:
                    parts = [p.strip().replace('"', '') for p in line.split('","')]
                    item = parts[0].replace('"', '')
                    if "合計(張)" in item:
                        results.append({"date": datetime.datetime.strptime(date_str, "%Y%m%d").date(), "market": "OTC", "item": "融資(交易單位)", "buy": int(parts[3].replace(",", "")), "sell": int(parts[4].replace(",", "")), "cash_repay": int(parts[5].replace(",", "")), "prev_balance": int(parts[2].replace(",", "")), "today_balance": int(parts[6].replace(",", ""))})
                        results.append({"date": datetime.datetime.strptime(date_str, "%Y%m%d").date(), "market": "OTC", "item": "融券(交易單位)", "buy": int(parts[12].replace(",", "")), "sell": int(parts[11].replace(",", "")), "cash_repay": int(parts[13].replace(",", "")), "prev_balance": int(parts[10].replace(",", "")), "today_balance": int(parts[14].replace(",", ""))})
                    elif "融資金(仟元)" in item:
                        results.append({"date": datetime.datetime.strptime(date_str, "%Y%m%d").date(), "market": "OTC", "item": "融資金額(仟元)", "buy": int(parts[3].replace(",", "")), "sell": int(parts[4].replace(",", "")), "cash_repay": int(parts[5].replace(",", "")), "prev_balance": int(parts[2].replace(",", "")), "today_balance": int(parts[6].replace(",", ""))})
        except: pass
    return pl.from_pandas(pd.DataFrame(results)) if results else None

def process_date_category(category, date_str):
    output_dir = f"{PROCESSED_DIR}/{category}/date={date_str}"
    
    if category in ["institutional_summary", "margin_summary"]:
        df = _handle_institutional_summary(date_str) if category == "institutional_summary" else _handle_margin_summary(date_str)
        if df is not None:
            os.makedirs(output_dir, exist_ok=True); df.write_csv(f"{output_dir}/all.csv")
            print(f"Processed {category}/{date_str}")
        return

    if category == "market_indices":
        # OTC (Raw)
        otc_raw = f"{RAW_DIR}/market_indices/date={date_str}/otc.csv"
        if os.path.exists(otc_raw):
            df = _handle_generic_category(otc_raw, "otc", category, date_str)
            if df is not None:
                if "symbol" not in df.columns or df["symbol"].null_count() == len(df): df = df.with_columns(pl.col("name").alias("symbol"))
                df = enforce_schema(df, "market_indices")
                os.makedirs(output_dir, exist_ok=True); df.write_csv(f"{output_dir}/otc.csv")
                print(f"Processed market_indices/{date_str}/otc")
        # SII (Extract)
        sii_quote = f"{RAW_DIR}/daily_quotes/date={date_str}/sii.csv"
        if os.path.exists(sii_quote):
            df_indices = read_sii_indices(sii_quote)
            if df_indices is not None:
                df_indices = df_indices.with_columns([pl.lit(date_str).str.strptime(pl.Date, "%Y%m%d").alias("date"), pl.lit("sii").alias("market")])
                df_indices = enforce_schema(df_indices, "market_indices")
                os.makedirs(output_dir, exist_ok=True); df_indices.write_csv(f"{output_dir}/sii.csv")
                print(f"Processed market_indices/{date_str}/sii (Extracted)")
        return

    src_cat = category; cat_raw_path = f"{RAW_DIR}/{src_cat}/date={date_str}"
    if not os.path.exists(cat_raw_path): return
    for market_file in os.listdir(cat_raw_path):
        if not market_file.endswith(".csv"): continue
        market = market_file.split(".")[0]; output_file = f"{output_dir}/{market}.csv"
        df = _handle_generic_category(os.path.join(cat_raw_path, market_file), market, category, date_str)
        if df is not None:
            df = enforce_schema(df, category); os.makedirs(output_dir, exist_ok=True); df.write_csv(output_file)
            print(f"Processed {category}/{date_str}/{market}")

def main():
    start_env = os.getenv("START_DATE"); end_env = os.getenv("END_DATE")
    start_date = datetime.datetime.strptime(start_env, "%Y%m%d") if start_env else None
    end_date = datetime.datetime.strptime(end_env, "%Y%m%d") if end_env else None
    print("Starting Unified ETL Pipeline...")
    # 定義所有要處理的類別 (包含虛擬類別)
    all_categories = ["daily_quotes", "institutional_investors", "foreign_holding", "margin_trading", "margin_sbl", "pe_ratio", "market_indices", "institutional_summary", "margin_summary"]
    for category in all_categories:
        # 決定時間參考來源 (margin_summary 參考 margin_trading)
        ref_cat = "margin_trading" if category == "margin_summary" else category
        if category == "institutional_summary" and not os.path.exists(f"{RAW_DIR}/institutional_summary"): ref_cat = "institutional_investors"
        
        ref_path = os.path.join(RAW_DIR, ref_cat)
        if not os.path.exists(ref_path): continue
        for d_entry in os.listdir(ref_path):
            if not d_entry.startswith("date="): continue
            date_str = d_entry.split("=")[1]
            try:
                curr = datetime.datetime.strptime(date_str, "%Y%m%d")
                if (not start_date or curr >= start_date) and (not end_date or curr <= end_date):
                    process_date_category(category, date_str)
            except: continue

if __name__ == "__main__":
    main()
