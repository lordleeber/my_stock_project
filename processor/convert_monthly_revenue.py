import os
import glob
import datetime
import pandas as pd
import numpy as np

RAW_DIR = "/app/data/raw/monthly_revenue"
PROCESSED_DIR = "/app/data/processed/monthly_revenue"

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
    "備註": "comment"
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
    "comment": "comment"
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

def process_monthly_revenue():
    if not os.path.exists(RAW_DIR):
        print(f"Raw revenue directory not found: {RAW_DIR}")
        return

    # 取得目錄列表，格式為 date=YYYYMMDD
    date_dirs = sorted([d for d in os.listdir(RAW_DIR) if d.startswith("date=")])
    
    start_env = os.getenv("START_DATE")
    end_env = os.getenv("END_DATE")

    for date_dir in date_dirs:
        date_str = date_dir.split("=")[1]
        ym_str = date_str[:6] # 202501
        
        if start_env and date_str < start_env: continue
        if end_env and date_str > end_env: continue

        print(f"Processing revenue for {date_str}...")
        
        year_str = date_str[:4]
        month_str = date_str[4:6]
        csv_files = glob.glob(os.path.join(RAW_DIR, date_dir, "*.csv"))
        
        dfs = []
        for file_path in csv_files:
            try:
                # 嘗試判斷 header 位置
                with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                    lines = [f.readline() for _ in range(5)]
                
                header_row = 0
                for i, line in enumerate(lines):
                    if "公司代號" in line:
                        header_row = i
                        break
                
                df = pd.read_csv(file_path, header=header_row, encoding='utf-8', thousands=',')
                df.columns = [c.strip().replace("\n", "") for c in df.columns]

                # 判斷使用中文或英文映射（英文用精確匹配，中文用包含匹配）
                is_english = "symbol" in df.columns
                use_mapping = COL_MAPPING_EN if is_english else COL_MAPPING

                new_df = pd.DataFrame()
                for col in df.columns:
                    for key, target in use_mapping.items():
                        # 英文列名使用精確匹配，中文列名使用包含匹配
                        matched = (col == key) if is_english else (key in col)
                        if matched:
                            if target not in new_df.columns:
                                new_df[target] = df[col]
                            break

                for target in use_mapping.values():
                    if target not in new_df.columns:
                        new_df[target] = None

                # 處理 market 欄位：如果原始資料已經有 market 欄位，使用它；否則從檔名判斷
                if 'market' in df.columns:
                    new_df['market'] = df['market'].str.upper()
                else:
                    market = "SII" if "sii" in file_path.lower() else "OTC" if "otc" in file_path.lower() else "UNKNOWN"
                    new_df['market'] = market
                dfs.append(new_df)
                
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
        
        # 輸出路徑格式: data/processed/monthly_revenue/date=YYYYMXX/
        subdir_name = f"date={year_str}M{month_str}"
        output_dir = os.path.join(PROCESSED_DIR, subdir_name)
        os.makedirs(output_dir, exist_ok=True)
        
        output_file = os.path.join(output_dir, "all.csv")
        final_df.to_csv(output_file, index=False, encoding='utf-8')
        print(f"Saved {len(final_df)} records to {output_file}")

if __name__ == "__main__":
    process_monthly_revenue()