"""
通用 ETL 處理進入點 (Integrated with Data Quality Checker)

1. 整合所有類別的處理邏輯 (個股、彙總表、大盤指數)。
2. 採用「日期優先」循環：處理完每一天後，立刻執行品質稽核。
"""

import os
import datetime
import io
import polars as pl
import pandas as pd
import traceback
import re
from pathlib import Path
from schemas import SCHEMA_COLS, COLUMN_MAP, NUMERIC_COLS
from utils import read_raw_csv, read_sii_indices
import data_quality_checker

RAW_DIR = os.getenv("RAW_DIR", "/app/data/raw")
PROCESSED_DIR = os.getenv("PROCESSED_DIR", "/app/data/processed")
FORCE_REPROCESS = os.getenv("FORCE_REPROCESS", "0") == "1"

def log_processing_error(msg, date_str=None, category=None):
    """將處理階段的錯誤訊息記錄到專用的 error_processor.md 檔案"""
    error_file = Path("/app/error_processor.md")
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    with open(error_file, 'a', encoding='utf-8') as f:
        f.write(f"\n## Processor Runtime Error - {timestamp}\n")
        if date_str: f.write(f"**Date:** {date_str}\n")
        if category: f.write(f"**Category:** {category}\n")
        f.write(f"**Message:** {msg}\n")
        f.write(f"**Traceback:**\n```python\n{traceback.format_exc()}\n```\n")
        f.write("---\n")
    print(f"❌ Error logged to error_processor.md: {msg}")

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
    # 更新 src_col：在前面添加 "x#x#" (對應 date 和 market 這兩個處理時添加的欄位)
    if "src_col" in df.columns:
        df = df.with_columns([
            pl.concat_str([pl.lit("x#x#"), pl.col("src_col")]).alias("src_col")
        ])

    # 為 market_indices 重命名欄位（必須在此處進行，因為 enforce_schema 會過濾未定義的列）
    if category == "market_indices":
        if "index_name" in df.columns and ("symbol" not in df.columns or df["symbol"].null_count() == len(df)):
            df = df.with_columns(pl.col("index_name").alias("symbol"))
        if "change" in df.columns and "index_change_points" not in df.columns:
            df = df.with_columns(pl.col("change").alias("index_change_points"))

    if "symbol" in df.columns:
        df = df.filter((pl.col("symbol").is_not_null()) & (pl.col("symbol") != ""))
        df = df.filter(pl.col("symbol").str.len_chars().is_between(2, 10))
    return df

def _handle_institutional_summary(date_str):
    input_dir = get_category_date_dir(RAW_DIR, "institutional_summary", date_str)
    all_dfs = []
    for market in ["sii", "otc"]:
        file_path = os.path.join(input_dir, f"{market}.csv")
        if not os.path.exists(file_path): continue
        try:
            df = pl.read_csv(file_path, encoding="utf-8-sig", infer_schema_length=0)
            if df.is_empty(): continue

            # 記錄原始列索引（1-based）
            original_columns = df.columns
            rename_map = {}
            col_indices = []  # 記錄選擇的列索引

            for idx, col in enumerate(original_columns):
                c = col.strip()
                if c == "單位名稱":
                    rename_map[col] = "institution"
                    col_indices.append(str(idx + 1))  # 1-based
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

            # Review fix: 明確檢查 institution 欄位是否存在
            if "institution" not in df.columns:
                log_processing_error(f"Missing 'institution' column in {market}.csv (cols: {df.columns})", date_str, "institutional_summary")
                continue

            rel_path = str(file_path).split("my_stock_project/")[-1] if "my_stock_project/" in str(file_path) else str(file_path)

            # 生成 src_col 字串
            src_col_str = "#".join(col_indices)

            df = df.with_columns([
                pl.lit(rel_path).alias("src_file"),
                (pl.arange(0, df.height) + 2).alias("src_row"), # CSV 通常 1 行標題，資料從第 2 行開始
                pl.lit(src_col_str).alias("src_col")
            ])

            df = df.with_columns(pl.col("institution").str.strip_chars().replace(INSTITUTION_MAP))
            df = df.filter(pl.col("institution").is_in(KEEP_INSTITUTIONS))
            for col in ["buy", "sell", "net"]:
                if col in df.columns:
                    df = df.with_columns(pl.col(col).str.replace_all(",", "").cast(pl.Int64, strict=False))
            df = df.with_columns([pl.lit(date_str).str.strptime(pl.Date, "%Y%m%d").alias("date"), pl.lit(market).alias("market")])
            # 更新 src_col：在前面添加 "x#x#" (對應 date 和 market)
            if "src_col" in df.columns:
                df = df.with_columns([
                    pl.concat_str([pl.lit("x#x#"), pl.col("src_col")]).alias("src_col")
                ])
            all_dfs.append(df.select(["date", "market", "institution", "buy", "sell", "net", "src_file", "src_row", "src_col"]))
        except Exception as e:
            log_processing_error(f"Error in institutional_summary for {market}: {e}", date_str, "institutional_summary")
    return pl.concat(all_dfs) if all_dfs else None

def _handle_margin_summary(date_str):
    input_dir = get_category_date_dir(RAW_DIR, "margin_trading", date_str); results = []
    sii_path = os.path.join(input_dir, "sii.csv")
    if os.path.exists(sii_path):
        try:
            rel_path = str(sii_path).split("my_stock_project/")[-1] if "my_stock_project/" in str(sii_path) else str(sii_path)
            with open(sii_path, 'r', encoding='utf-8-sig') as f: lines = [f.readline() for _ in range(4)]
            df = pd.read_csv(io.StringIO("".join(lines))); df.columns = [c.strip() for c in df.columns]

            # 記錄需要的列在原始 DataFrame 中的索引（1-based）
            # 輸出順序：date, market, item, buy, sell, cash_repay, prev_balance, today_balance
            needed_cols_ordered = ['項目', '買進', '賣出', '現金(券)償還', '前日餘額', '今日餘額']
            col_indices = ["x", "x"]  # date 和 market 是處理時添加的
            for col_name in needed_cols_ordered:
                if col_name in df.columns:
                    col_idx = list(df.columns).index(col_name) + 1  # 1-based
                    col_indices.append(str(col_idx))

            src_col_str = "#".join(col_indices)

            for idx, row in df.iterrows():
                item = str(row['項目']).strip()
                if "融資" in item or "融券" in item:
                    results.append({
                        "date": datetime.datetime.strptime(date_str, "%Y%m%d").date(),
                        "market": "SII",
                        "item": item,
                        "buy": int(str(row['買進']).replace(",", "")),
                        "sell": int(str(row['賣出']).replace(",", "")),
                        "cash_repay": int(str(row['現金(券)償還']).replace(",", "")),
                        "prev_balance": int(str(row['前日餘額']).replace(",", "")),
                        "today_balance": int(str(row['今日餘額']).replace(",", "")),
                        "src_file": rel_path,
                        "src_row": idx + 2, # 1-based header is at 1, data starts at 2
                        "src_col": src_col_str
                    })
        except Exception as e:
            log_processing_error(f"Error in margin_summary (SII): {e}", date_str, "margin_summary")
    otc_path = os.path.join(input_dir, "otc.csv")
    if os.path.exists(otc_path):
        try:
            rel_path = str(otc_path).split("my_stock_project/")[-1] if "my_stock_project/" in str(otc_path) else str(otc_path)
            with open(otc_path, 'r', encoding='utf-8-sig') as f: lines = f.readlines()
            for i, line in enumerate(lines):
                if i < len(lines) - 5: continue # 只要最後幾行
                if "合計(張)" in line or "融資金(仟元)" in line:
                    parts = [p.strip().replace('"', '') for p in line.split('","')]
                    if len(parts) < 7: continue # 基本長度檢查
                    
                    item = parts[0].replace('"', '')
                    src_row = i + 1
                    if "合計(張)" in item and len(parts) >= 15:
                        # 融資(交易單位)：date(x)#market(x)#item(1)#buy(4)#sell(5)#cash_repay(6)#prev_balance(3)#today_balance(7)
                        results.append({"date": datetime.datetime.strptime(date_str, "%Y%m%d").date(), "market": "OTC", "item": "融資(交易單位)", "buy": int(parts[3].replace(",", "")), "sell": int(parts[4].replace(",", "")), "cash_repay": int(parts[5].replace(",", "")), "prev_balance": int(parts[2].replace(",", "")), "today_balance": int(parts[6].replace(",", "")), "src_file": rel_path, "src_row": src_row, "src_col": "x#x#1#4#5#6#3#7"})
                        # 融券(交易單位)：date(x)#market(x)#item(1)#buy(13)#sell(12)#cash_repay(14)#prev_balance(11)#today_balance(15)
                        results.append({"date": datetime.datetime.strptime(date_str, "%Y%m%d").date(), "market": "OTC", "item": "融券(交易單位)", "buy": int(parts[12].replace(",", "")), "sell": int(parts[11].replace(",", "")), "cash_repay": int(parts[13].replace(",", "")), "prev_balance": int(parts[10].replace(",", "")), "today_balance": int(parts[14].replace(",", "")), "src_file": rel_path, "src_row": src_row, "src_col": "x#x#1#13#12#14#11#15"})
                    elif "融資金(仟元)" in item:
                        # 融資金額(仟元)：date(x)#market(x)#item(1)#buy(4)#sell(5)#cash_repay(6)#prev_balance(3)#today_balance(7)
                        results.append({"date": datetime.datetime.strptime(date_str, "%Y%m%d").date(), "market": "OTC", "item": "融資金額(仟元)", "buy": int(parts[3].replace(",", "")), "sell": int(parts[4].replace(",", "")), "cash_repay": int(parts[5].replace(",", "")), "prev_balance": int(parts[2].replace(",", "")), "today_balance": int(parts[6].replace(",", "")), "src_file": rel_path, "src_row": src_row, "src_col": "x#x#1#4#5#6#3#7"})
        except Exception as e:
            log_processing_error(f"Error in margin_summary (OTC): {e}", date_str, "margin_summary")
    return pl.from_pandas(pd.DataFrame(results)) if results else None

def get_category_date_dir(base_dir, category, date_str):
    """取得類別日期的目錄路徑，優先使用新結構 yyyy/yyyymmdd，若無則回退至 date=yyyymmdd"""
    if category == "monthly_revenue":
        return os.path.join(base_dir, category, f"date={date_str}")

    new_path = os.path.join(base_dir, category, date_str[:4], date_str)
    if os.path.exists(new_path):
        return new_path
    return os.path.join(base_dir, category, f"date={date_str}")

def process_date_category(category, date_str):
    # 輸出目錄統一改為新結構
    if category in ("income_statement", "balance_sheet", "cash_flow"):
        output_dir = f"{PROCESSED_DIR}/{category}/date={date_str}"
    elif category == "monthly_revenue":
        # YYYY/YYYYMXX
        output_dir = f"{PROCESSED_DIR}/{category}/{date_str[:4]}/{date_str}"
    elif category == "quarterly_reports":
        # YYYY/YYYYQX
        output_dir = f"{PROCESSED_DIR}/{category}/{date_str[:4]}/{date_str}"
    else:
        output_dir = f"{PROCESSED_DIR}/{category}/{date_str[:4]}/{date_str}"
    
    if category in ["institutional_summary", "margin_summary"]:
        output_file = f"{output_dir}/all.csv"
        if os.path.exists(output_file) and not FORCE_REPROCESS:
            if os.getenv("DEBUG", "0") == "1":
                print(f"Skipping {category}/{date_str} (already exists)")
            return
        df = _handle_institutional_summary(date_str) if category == "institutional_summary" else _handle_margin_summary(date_str)
        if df is not None:
            os.makedirs(output_dir, exist_ok=True); df.write_csv(output_file)
            print(f"Processed {category}/{date_str}")
        return

    if category == "market_indices":
        # OTC (Raw)
        otc_output = f"{output_dir}/otc.csv"
        otc_raw_dir = get_category_date_dir(RAW_DIR, "market_indices", date_str)
        otc_raw = os.path.join(otc_raw_dir, "otc.csv")
        if os.path.exists(otc_raw) and (not os.path.exists(otc_output) or FORCE_REPROCESS):
            df = _handle_generic_category(otc_raw, "otc", category, date_str)
            if df is not None:
                df = enforce_schema(df, "market_indices")
                os.makedirs(output_dir, exist_ok=True); df.write_csv(otc_output)
                print(f"Processed market_indices/{date_str}/otc")
        
        # SII (Extract)
        sii_output = f"{output_dir}/sii.csv"
        dq_raw_dir = get_category_date_dir(RAW_DIR, "daily_quotes", date_str)
        sii_quote = os.path.join(dq_raw_dir, "sii.csv")
        if os.path.exists(sii_quote) and (not os.path.exists(sii_output) or FORCE_REPROCESS):
            df_indices = read_sii_indices(sii_quote)
            if df_indices is not None:
                df_indices = df_indices.with_columns([pl.lit(date_str).str.strptime(pl.Date, "%Y%m%d").alias("date"), pl.lit("sii").alias("market")])
                # 更新 src_col：在前面添加 "x#x#" (對應 date 和 market)
                if "src_col" in df_indices.columns:
                    df_indices = df_indices.with_columns([
                        pl.concat_str([pl.lit("x#x#"), pl.col("src_col")]).alias("src_col")
                    ])
                df_indices = enforce_schema(df_indices, "market_indices")
                os.makedirs(output_dir, exist_ok=True); df_indices.write_csv(sii_output)
                print(f"Processed market_indices/{date_str}/sii (Extracted)")
        return

    src_cat = category; cat_raw_path = get_category_date_dir(RAW_DIR, src_cat, date_str)
    if not os.path.exists(cat_raw_path): return
    for market_file in os.listdir(cat_raw_path):
        if not market_file.endswith(".csv"): continue
        market = market_file.split(".")[0]; output_file = f"{output_dir}/{market}.csv"
        if os.path.exists(output_file) and not FORCE_REPROCESS:
            continue
        df = _handle_generic_category(os.path.join(cat_raw_path, market_file), market, category, date_str)
        if df is not None:
            df = enforce_schema(df, category); os.makedirs(output_dir, exist_ok=True); df.write_csv(output_file)
            print(f"Processed {category}/{date_str}/{market}")

def main():
    start_env = os.getenv("START_DATE"); end_env = os.getenv("END_DATE")
    start_date = datetime.datetime.strptime(start_env, "%Y%m%d") if start_env else None
    end_date = datetime.datetime.strptime(end_env, "%Y%m%d") if end_env else None
    print("Starting Unified ETL Pipeline...")
    
    all_categories = ["daily_quotes", "institutional_investors", "foreign_holding", "margin_trading", "margin_sbl", "pe_ratio", "market_indices", "institutional_summary", "margin_summary"]

    # 1. 搜集所有需要處理的日期 (掃描所有類別的 Raw 資料並驗證格式)
    date_pattern = re.compile(r'^\d{8}$')
    all_dates = set()
    for cat in all_categories:
        cat_path = os.path.join(RAW_DIR, cat)
        if os.path.exists(cat_path):
            # Scan for date=YYYYMMDD (Old)
            for d in os.listdir(cat_path):
                if d.startswith("date="):
                    date_part = d.split("=")[1]
                    if date_pattern.match(date_part):
                        all_dates.add(date_part)
                
                # Scan for YYYY/YYYYMMDD (New)
                elif len(d) == 4 and d.isdigit():
                    y_path = os.path.join(cat_path, d)
                    if os.path.isdir(y_path):
                        for sub_d in os.listdir(y_path):
                            if date_pattern.match(sub_d):
                                all_dates.add(sub_d)

    
    sorted_dates = sorted(list(all_dates))
    
    # 2. 依照日期順序執行
    for date_str in sorted_dates:
        try:
            curr = datetime.datetime.strptime(date_str, "%Y%m%d")
            # 日期範圍過濾
            if start_date and curr < start_date: continue
            if end_date and curr > end_date: continue
            
            # 2a. 處理當天所有類別
            for category in all_categories:
                process_date_category(category, date_str)
            
            # 2b. 當天處理完後，立刻執行資料品質稽核
            print(f"Auditing data for {date_str}...")

            # 暫存原始環境變數
            original_start = os.environ.get("START_DATE")
            original_end = os.environ.get("END_DATE")

            try:
                # 設定當天日期範圍供 QC 使用
                os.environ["START_DATE"] = date_str
                os.environ["END_DATE"] = date_str

                data_quality_checker.main()
            except SystemExit as e:
                if e.code != 0:
                    error_msg = f"Data quality check failed with exit code {e.code}"
                    print(f"⚠️  {error_msg} for {date_str}")
                    log_processing_error(error_msg, date_str, "quality_check")
                    # 決策: 記錄錯誤但繼續處理下一個日期
            finally:
                # 還原環境變數
                if original_start is not None:
                    os.environ["START_DATE"] = original_start
                else:
                    os.environ.pop("START_DATE", None)

                if original_end is not None:
                    os.environ["END_DATE"] = original_end
                else:
                    os.environ.pop("END_DATE", None)

        except Exception as e:
            log_processing_error(f"Error in main loop for {date_str}: {e}", date_str)
            continue

if __name__ == "__main__":
    main()
