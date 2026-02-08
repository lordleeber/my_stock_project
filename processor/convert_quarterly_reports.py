import os
import glob
import polars as pl
import pandas as pd
from datetime import datetime
import numpy as np

# 環境變數設定
RAW_DIR = os.environ.get("RAW_DIR", "data/raw")
PROCESSED_DIR = os.environ.get("PROCESSED_DIR", "data/processed")
CATEGORY = "quarterly_reports"

# 定義最終統一的欄位順序
FINAL_FIELDS = [
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

def clean_numeric(val):
    """清理數值，處理 --, null, nan, (123)"""
    if pd.isna(val) or val == "--" or str(val).strip() == "":
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

def process_file(file_path, date_str, market):
    """
    處理單一季報 XLS 檔案，提取本期、去年同期與 YoY
    """
    try:
        df_raw = pd.read_excel(file_path, engine='xlrd', header=None)
        header_idx = -1
        for idx, row in df_raw.head(15).iterrows():
            row_str = "".join(row.astype(str).tolist())
            if "Code" in row_str or "代號" in row_str:
                header_idx = idx
                break
        
        if header_idx == -1: return None

        if market == 'sii':
            mapping = {
                "symbol": 0, "name": 1,
                "revenue": 2, "revenue_ly": 3, "revenue_yoy": 4,
                "op_income": 5, "op_income_ly": 6,
                "non_op_income": 7, "non_op_income_ly": 8,
                "net_income": 9, "net_income_ly": 10, "net_income_yoy": 11,
                "pretax_income": 19, "pretax_income_ly": 20, "pretax_income_yoy": 21,
                "eps": 13, "eps_ly": 14,
                "capital": 12, "nav_per_share": 15, "equity_to_assets_ratio": 16,
                "current_ratio": 17, "quick_ratio": 18
            }
        else:
            mapping = {
                "symbol": 0, "name": 1,
                "revenue": 2, "revenue_ly": 3, "revenue_yoy": 4,
                "op_income": 5, "op_income_ly": 6,
                "non_op_income": 7, "non_op_income_ly": 8,
                "net_income": 9, "net_income_ly": 10, "net_income_yoy": 11,
                "eps": 13, "eps_ly": 14,
                "capital": 12, "nav_per_share": 15, "equity_to_assets_ratio": 16,
                "current_ratio": 17, "quick_ratio": 18
            }

        records = []
        for i in range(header_idx + 1, len(df_raw)):
            row = df_raw.iloc[i]
            raw_symbol = str(row[mapping["symbol"]]).strip()
            if raw_symbol.endswith(".0"): raw_symbol = raw_symbol[:-2]
            
            if len(raw_symbol) != 4 or not raw_symbol.isdigit(): continue
            
            data = {f: None for f in FINAL_FIELDS}
            data.update({"date": date_str, "symbol": raw_symbol, "market": market, "name": str(row[mapping["name"]]).strip()})
            
            for field, idx in mapping.items():
                if field in ["date", "symbol", "market", "name"]: continue
                data[field] = clean_numeric(row[idx]) if idx < len(row) else None
            
            # 補齊 YoY
            if data["op_income_yoy"] is None:
                data["op_income_yoy"] = calculate_yoy(data["op_income"], data["op_income_ly"])
            if data["non_op_income_yoy"] is None:
                data["non_op_income_yoy"] = calculate_yoy(data["non_op_income"], data["non_op_income_ly"])
            if data["eps_yoy"] is None:
                data["eps_yoy"] = calculate_yoy(data["eps"], data["eps_ly"])
            
            # OTC 手動計算稅前
            if market == 'otc':
                if data["op_income"] is not None and data["non_op_income"] is not None:
                    data["pretax_income"] = data["op_income"] + data["non_op_income"]
                if data["op_income_ly"] is not None and data["non_op_income_ly"] is not None:
                    data["pretax_income_ly"] = data["op_income_ly"] + data["non_op_income_ly"]
                data["pretax_income_yoy"] = calculate_yoy(data["pretax_income"], data["pretax_income_ly"])

            records.append(data)
            
        return pl.DataFrame(records) if records else None

    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return None

def main():
    raw_path = os.path.join(RAW_DIR, CATEGORY)
    date_dirs = sorted(glob.glob(os.path.join(raw_path, "date=*")))
    
    for date_dir in date_dirs:
        date_str = os.path.basename(date_dir).split("=")[1]
        print(f"Processing {date_str}...")
        
        all_dfs = []
        for market in ["sii", "otc"]:
            xls_path = os.path.join(date_dir, f"{market}.xls")
            if os.path.exists(xls_path):
                df = process_file(xls_path, date_str, market)
                if df is not None: all_dfs.append(df)
        
        if all_dfs:
            final_df = pl.concat(all_dfs).unique(subset=["symbol"])
            # 強制統一欄位順序，確保匯入穩定
            final_df = final_df.select(FINAL_FIELDS)
            output_dir = os.path.join(PROCESSED_DIR, CATEGORY, f"date={date_str}")
            os.makedirs(output_dir, exist_ok=True)
            output_path = os.path.join(output_dir, "all.csv")
            final_df.write_csv(output_path)
            print(f"  [+] Saved {final_df.height} records")
            
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