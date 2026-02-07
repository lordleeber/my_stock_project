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

def process_file(file_path, date_str, market):
    """
    處理單一季報 XLS 檔案
    """
    try:
        # 使用 Pandas 讀取 Excel
        df_raw = pd.read_excel(file_path, engine='xlrd', header=None)
        
        # 尋找包含 "Code" 或 "代號" 的行作為 header
        header_idx = -1
        for idx, row in df_raw.head(15).iterrows():
            row_str = "".join(row.astype(str).tolist())
            if "Code" in row_str or "代號" in row_str:
                header_idx = idx
                break
        
        if header_idx == -1:
            return None

        # 取得表頭行名稱 (合併 header_idx 及其前後行，以應對多列標題)
        merged_headers = []
        for col_idx in range(len(df_raw.columns)):
            parts = []
            # 檢查 header_idx 附近幾行，合併成單一標題字串供模糊比對
            for r_offset in range(-2, 2): 
                r_idx = header_idx + r_offset
                if 0 <= r_idx < len(df_raw):
                    val = str(df_raw.iloc[r_idx, col_idx]).strip()
                    if val and val != 'nan':
                        parts.append(val.replace("\r", "").replace("\n", ""))
            merged_headers.append(" ".join(parts))
        header_row = merged_headers
        
        # 建立欄位映射 (索引基準)
        col_map = {}
        if market == 'sii':
            # TWSE SII 格式固定 (C05001 一般業彙總表)
            col_map = {
                "symbol": 0, "name": 1, "revenue": 2, "operating_income": 5,
                "non_operating_income": 7, "net_income": 9, "eps": 13,
                "nav_per_share": 15, "nav_asset_ratio": 16, "current_ratio": 17,
                "quick_ratio": 18
            }
        else:
            # OTC 模糊比對
            for i, c in enumerate(header_row):
                if "Code" in c and "Name" in c: col_map["symbol_name"] = i
                elif "代號" in c: col_map["symbol"] = i
                elif "名稱" in c: col_map["name"] = i
                elif "營業收入" in c and "1-" not in c: col_map["revenue"] = i
                elif "營業利益" in c or "Income(Lose) from Operation" in c: col_map["operating_income"] = i
                elif "營業外" in c: col_map["non_operating_income"] = i
                # 先檢查 EPS，因為它的字串通常包含 "稅後純益"
                elif "每股盈餘" in c or "每股稅後純益" in c or "Net Income Per Share" in c: col_map["eps"] = i
                elif "稅後淨利" in c or "稅後純益" in c or "Net Income after Tax" in c: col_map["net_income"] = i
                elif "每股淨值" in c: col_map["nav_per_share"] = i
                elif "流動比率" in c: col_map["current_ratio"] = i
                elif "速動比率" in c: col_map["quick_ratio"] = i
                elif "淨值佔總資產" in c: col_map["nav_asset_ratio"] = i
                elif "營業活動現金流量" in c or "Cash Flow from Operating" in c: col_map["operating_cash_flow"] = i

        records = []
        # 從 header_idx + 1 開始尋找資料
        for i in range(header_idx + 1, len(df_raw)):
            row = df_raw.iloc[i]
            
            # 取得 symbol
            sym_idx = col_map.get("symbol")
            if sym_idx is None and "symbol_name" in col_map:
                sym_idx = col_map["symbol_name"]
            
            if sym_idx is None: continue
            
            raw_symbol = str(row[sym_idx]).strip()
            if raw_symbol.endswith(".0"): raw_symbol = raw_symbol[:-2]
            
            # 判斷是否為合法個股代號 (4位數字)
            symbol = ""
            name = ""
            if len(raw_symbol) == 4 and raw_symbol.isdigit():
                symbol = raw_symbol
                name_idx = col_map.get("name")
                if name_idx is not None: 
                    name = str(row[name_idx]).strip()
                elif market == 'otc' and sym_idx + 1 < len(row):
                    # 如果 OTC 沒有找到 name 欄位，嘗試取 symbol 的下一欄
                    next_val = str(row[sym_idx + 1]).strip()
                    if next_val and next_val != 'nan' and not next_val.replace('.', '').isdigit():
                        name = next_val
            elif " " in raw_symbol: # 處理 "1101 台泥"
                parts = raw_symbol.split(maxsplit=1)
                if len(parts[0]) == 4 and parts[0].isdigit():
                    symbol, name = parts[0], parts[1]
            elif len(raw_symbol) > 4 and raw_symbol[:4].isdigit(): # 處理 "1101台泥"
                symbol = raw_symbol[:4]
                name = raw_symbol[4:]
            
            if not symbol: continue # 跳過分類行或垃圾行
            
            # 提取數據
            res = {
                "date": date_str, "symbol": symbol, "market": market, "name": name,
                "revenue": clean_numeric(row[col_map["revenue"]]) if "revenue" in col_map else None,
                "operating_income": clean_numeric(row[col_map["operating_income"]]) if "operating_income" in col_map else None,
                "non_operating_income": clean_numeric(row[col_map["non_operating_income"]]) if "non_operating_income" in col_map else None,
                "net_income": clean_numeric(row[col_map["net_income"]]) if "net_income" in col_map else None,
                "eps": clean_numeric(row[col_map["eps"]]) if "eps" in col_map else None,
                "total_assets": None, "total_liabilities": None, "current_assets": None, "current_liabilities": None,
                "nav_per_share": clean_numeric(row[col_map["nav_per_share"]]) if "nav_per_share" in col_map else None,
                "operating_cash_flow": clean_numeric(row[col_map["operating_cash_flow"]]) if "operating_cash_flow" in col_map else None,
                "current_ratio": clean_numeric(row[col_map["current_ratio"]]) if "current_ratio" in col_map else None,
                "quick_ratio": clean_numeric(row[col_map["quick_ratio"]]) if "quick_ratio" in col_map else None,
                "debt_ratio": None
            }
            
            nav_asset = clean_numeric(row[col_map["nav_asset_ratio"]]) if "nav_asset_ratio" in col_map else None
            if nav_asset is not None: res["debt_ratio"] = 100.0 - nav_asset

            records.append(res)
            
        if not records: return None
        
        schema = {
            "date": pl.Utf8, "symbol": pl.Utf8, "market": pl.Utf8, "name": pl.Utf8,
            "revenue": pl.Float64, "operating_income": pl.Float64, "non_operating_income": pl.Float64,
            "net_income": pl.Float64, "eps": pl.Float64,
            "total_assets": pl.Float64, "total_liabilities": pl.Float64, 
            "current_assets": pl.Float64, "current_liabilities": pl.Float64,
            "nav_per_share": pl.Float64, "operating_cash_flow": pl.Float64,
            "current_ratio": pl.Float64, "quick_ratio": pl.Float64, "debt_ratio": pl.Float64
        }
        return pl.DataFrame(records, schema=schema)

    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        import traceback
        traceback.print_exc()
        return None

def main():
    raw_path = os.path.join(RAW_DIR, CATEGORY)
    date_dirs = glob.glob(os.path.join(raw_path, "date=*"))
    
    for date_dir in sorted(date_dirs):
        date_str = os.path.basename(date_dir).split("=")[1]
        print(f"\nProcessing {date_str}...")
        
        output_dir = os.path.join(PROCESSED_DIR, CATEGORY, f"date={date_str}")
        os.makedirs(output_dir, exist_ok=True)
        output_file = os.path.join(output_dir, "all.csv")
        
        all_dfs = []
        for market in ["sii", "otc"]:
            xls_path = os.path.join(date_dir, f"{market}.xls")
            if os.path.exists(xls_path):
                print(f"[*] Processing {market} file...")
                df = process_file(xls_path, date_str, market)
                if df is not None and not df.is_empty():
                    all_dfs.append(df)
        
        if all_dfs:
            final_df = pl.concat(all_dfs)
            final_df = final_df.unique(subset=["symbol"])
            final_df.write_csv(output_file)
            print(f"[+] Saved {final_df.height} combined records to {output_file}")

if __name__ == "__main__":
    main()