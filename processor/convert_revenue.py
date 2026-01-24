import os
import glob
import datetime
import pandas as pd
import numpy as np

RAW_DIR = "/app/data/raw/revenue"
PROCESSED_DIR = "/app/data/processed/revenue"

# 欄位映射字典 (原始 CSV 欄位名稱可能有多種變體，這裡列出常見的關鍵字)
# MOPS 欄位通常固定，但以防萬一
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
    "備註": "comment"
}

def clean_number(x):
    """清理數值字串：移除逗號，轉換為 float，處理空值"""
    if pd.isna(x) or str(x).strip() == "":
        return None
    try:
        # 移除逗號
        val_str = str(x).replace(",", "").strip()
        # 處理括號 (負數)
        if val_str.startswith("(") and val_str.endswith(")"):
            val_str = "-" + val_str[1:-1]
        return float(val_str)
    except:
        return None

def process_monthly_revenue():
    # 遍歷所有月份目錄: data/raw/revenue/YYYY-MM
    if not os.path.exists(RAW_DIR):
        print(f"Raw revenue directory not found: {RAW_DIR}")
        return

    subdirs = sorted([d for d in os.listdir(RAW_DIR) if os.path.isdir(os.path.join(RAW_DIR, d))])
    
    start_env = os.getenv("START_DATE") # YYYYMMDD
    end_env = os.getenv("END_DATE")     # YYYYMMDD
    
    start_ym = start_env[:6] if start_env and len(start_env) >= 6 else None
    end_ym = end_env[:6] if end_env and len(end_env) >= 6 else None

    for subdir in subdirs:
        # subdir 格式預期為 YYYY-MM
        if len(subdir) != 7 or "-" not in subdir:
            continue
            
        ym_str = subdir.replace("-", "") # YYYYMM
        
        # 簡易日期過濾 (以月份為單位)
        if start_ym and ym_str < start_ym:
            continue
        if end_ym and ym_str > end_ym:
            continue

        print(f"Processing revenue for {subdir}...")
        
        year_str, month_str = subdir.split("-")
        csv_files = glob.glob(os.path.join(RAW_DIR, subdir, "*.csv"))
        
        dfs = []
        
        for file_path in csv_files:
            try:
                # 讀取 CSV，MOPS 格式通常編碼為 utf-8 或 cp950，且前幾行可能是說明
                # 假設 scraper 已經存成 utf-8
                # 透過 skiprows 略過標題說明，自動尋找 header
                # 通常表頭包含 "公司代號"
                
                # 先嘗試讀取前 5 行來判斷 header 位置
                with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                    lines = [f.readline() for _ in range(5)]
                
                header_row = 0
                for i, line in enumerate(lines):
                    if "公司代號" in line:
                        header_row = i
                        break
                
                df = pd.read_csv(file_path, header=header_row, encoding='utf-8', thousands=',')
                
                # 重新命名欄位
                # 因為欄位名稱可能包含換行符號或空白，先正規化
                df.columns = [c.strip().replace("\n", "") for c in df.columns]
                
                # 建立新 DataFrame 只保留需要的欄位
                new_df = pd.DataFrame()
                
                # 自動對應欄位
                for col in df.columns:
                    for key, target in COL_MAPPING.items():
                        if key in col: # 模糊匹配 (例如 "當月營收" in " 營業收入-當月營收 ")
                            # 如果這個 target 已經有對應了，且當前 col 長度更短(更精確)，則替換
                            # 這裡簡化處理，直接 assign
                            if target not in new_df.columns:
                                new_df[target] = df[col]
                            break
                
                # 補齊缺失欄位
                for target in COL_MAPPING.values():
                    if target not in new_df.columns:
                        new_df[target] = None
                        
                # 加入市場別 (從檔名判斷)
                market = "sii" if "sii" in file_path else "otc" if "otc" in file_path else "unknown"
                new_df['market'] = market
                
                dfs.append(new_df)
                
            except Exception as e:
                print(f"Error processing {file_path}: {e}")
                continue
        
        if not dfs:
            print(f"No valid data found for {subdir}")
            continue
            
        # 合併上市與上櫃資料
        final_df = pd.concat(dfs, ignore_index=True)
        
        # 資料清洗
        # 1. 移除 Symbol 為空或非數字的列 (合計列或備註列)
        final_df = final_df[final_df['symbol'].notna()]
        final_df = final_df[final_df['symbol'].astype(str).str.match(r'^\d+$')] # 簡單判斷：只留純數字代號
        
        # 2. 數值標準化
        num_cols = [
            "revenue_current", "revenue_last_month", "revenue_last_year",
            "mom_pct", "yoy_pct", 
            "revenue_cumulative", "revenue_cumulative_last_year", "cumulative_yoy_pct"
        ]
        
        for col in num_cols:
            if col in final_df.columns:
                final_df[col] = final_df[col].apply(clean_number)
        
        # 3. 補充日期欄位 (每個月的 10 號是公布截止日，但營收通常歸屬上個月)
        # 這裡的 subdir 是 "2025-01"，代表的是 "2025年1月的營收"
        # 在資料庫中，我們可以用 2025-01-01 代表這個月份的資料
        final_df['date'] = f"{year_str}-{month_str}-01"
        
        # 輸出
        output_dir = os.path.join(PROCESSED_DIR, subdir)
        os.makedirs(output_dir, exist_ok=True)
        
        # 檔名範例: revenue_202501.csv
        output_file = os.path.join(output_dir, f"revenue_{ym_str}.csv")
        final_df.to_csv(output_file, index=False, encoding='utf-8')
        print(f"Saved {len(final_df)} records to {output_file}")

if __name__ == "__main__":
    process_monthly_revenue()
