"""
市場信用交易彙總 ETL 處理模組

處理 data/raw/margin_trading/ 下的資料，提取 SII/OTC 的市場整體統計數據。

用途:
    - 資金面指標：市場融資融券水位與變化

使用方式:
    docker compose run --rm processor python convert_margin_summary.py

環境變數:
    START_DATE: 起始日期 (YYYYMMDD)
    END_DATE: 結束日期 (YYYYMMDD)
"""

import os
import datetime
import pandas as pd
import io

RAW_DIR = os.getenv("RAW_DIR", "/app/data/raw")
PROCESSED_DIR = os.getenv("PROCESSED_DIR", "/app/data/processed")
CATEGORY = "margin_summary"
INPUT_CATEGORY = "margin_trading"

def get_category_date_dir(base_dir, category, date_str):
    """取得類別日期的目錄路徑，優先使用新結構 yyyy/yyyymmdd，若無則回退至 date=yyyymmdd"""
    new_path = os.path.join(base_dir, category, date_str[:4], date_str)
    if os.path.exists(new_path):
        return new_path
    return os.path.join(base_dir, category, f"date={date_str}")

def process_sii(file_path: str, date_str: str):
    """處理 SII (證交所) 的彙總數據 (位於檔案前 4 行)"""
    try:
        with open(file_path, 'r', encoding='utf-8-sig') as f:
            lines = [f.readline() for _ in range(4)]
        
        # 建立類比檔案物件
        csv_data = "".join(lines)
        df = pd.read_csv(io.StringIO(csv_data))
        
        # 清理欄位名稱並轉換數值
        df.columns = [c.strip() for c in df.columns]
        
        results = []
        for _, row in df.iterrows():
            item = row['項目'].strip()
            if "融資" in item or "融券" in item:
                results.append({
                    "date": datetime.datetime.strptime(date_str, "%Y%m%d").date(),
                    "market": "SII",
                    "item": item,
                    "buy": int(str(row['買進']).replace(",", "")),
                    "sell": int(str(row['賣出']).replace(",", "")),
                    "cash_repay": int(str(row['現金(券)償還']).replace(",", "")),
                    "prev_balance": int(str(row['前日餘額']).replace(",", "")),
                    "today_balance": int(str(row['今日餘額']).replace(",", ""))
                })
        return pd.DataFrame(results)
    except Exception as e:
        print(f"Error processing SII {file_path}: {e}")
        return None

def process_otc(file_path: str, date_str: str):
    """處理 OTC (櫃買中心) 的彙總數據 (位於檔案最後 2 行)"""
    try:
        # 讀取最後幾行
        with open(file_path, 'r', encoding='utf-8-sig') as f:
            lines = f.readlines()
        
        summary_lines = []
        for line in lines[-5:]: # 抓最後 5 行保險
            if "合計(張)" in line or "融資金(仟元)" in line:
                summary_lines.append(line)
        
        results = []
        for line in summary_lines:
            # 簡單切割 CSV (處理逗號與引號)
            parts = [p.strip().replace('"', '') for p in line.split('","')]
            item = parts[0].replace('"', '')
            
            # OTC 的項目名稱與 SII 略有不同，我們將其統一起來以便查詢
            unified_item = item
            if "合計(張)" in item:
                # 這裡需要拆分融資與融券，但 OTC 的 CSV 格式在一列中
                # 欄位順序: 項目, 略, 前資, 資買, 資賣, 現償, 資餘, ..., 前券, 券賣, 券買, 券償, 券餘
                results.append({
                    "date": datetime.datetime.strptime(date_str, "%Y%m%d").date(),
                    "market": "OTC",
                    "item": "融資(交易單位)",
                    "buy": int(parts[3].replace(",", "")),
                    "sell": int(parts[4].replace(",", "")),
                    "cash_repay": int(parts[5].replace(",", "")),
                    "prev_balance": int(parts[2].replace(",", "")),
                    "today_balance": int(parts[6].replace(",", ""))
                })
                results.append({
                    "date": datetime.datetime.strptime(date_str, "%Y%m%d").date(),
                    "market": "OTC",
                    "item": "融券(交易單位)",
                    "buy": int(parts[12].replace(",", "")), # 券買
                    "sell": int(parts[11].replace(",", "")), # 券賣
                    "cash_repay": int(parts[13].replace(",", "")), # 券償
                    "prev_balance": int(parts[10].replace(",", "")), # 前券
                    "today_balance": int(parts[14].replace(",", "")) # 今日券餘
                })
            elif "融資金(仟元)" in item:
                results.append({
                    "date": datetime.datetime.strptime(date_str, "%Y%m%d").date(),
                    "market": "OTC",
                    "item": "融資金額(仟元)",
                    "buy": int(parts[3].replace(",", "")),
                    "sell": int(parts[4].replace(",", "")),
                    "cash_repay": int(parts[5].replace(",", "")),
                    "prev_balance": int(parts[2].replace(",", "")),
                    "today_balance": int(parts[6].replace(",", ""))
                })
        
        return pd.DataFrame(results) if results else None
    except Exception as e:
        print(f"Error processing OTC {file_path}: {e}")
        return None

def process_date(date_str: str):
    input_dir = get_category_date_dir(RAW_DIR, INPUT_CATEGORY, date_str)
    output_dir = os.path.join(PROCESSED_DIR, CATEGORY, date_str[:4], date_str)
    
    if not os.path.exists(input_dir):
        return False

    all_dfs = []
    
    # SII
    sii_path = os.path.join(input_dir, "sii.csv")
    if os.path.exists(sii_path):
        df_sii = process_sii(sii_path, date_str)
        if df_sii is not None:
            all_dfs.append(df_sii)
            
    # OTC
    otc_path = os.path.join(input_dir, "otc.csv")
    if os.path.exists(otc_path):
        df_otc = process_otc(otc_path, date_str)
        if df_otc is not None:
            all_dfs.append(df_otc)

    if not all_dfs:
        return False

    combined_df = pd.concat(all_dfs)
    os.makedirs(output_dir, exist_ok=True)
    combined_df.to_csv(f"{output_dir}/all.csv", index=False)
    print(f"Processed margin_summary for {date_str}")
    return True

def main():
    start_env = os.getenv("START_DATE")
    end_env = os.getenv("END_DATE")
    
    category_path = os.path.join(RAW_DIR, INPUT_CATEGORY)
    if not os.path.exists(category_path):
        return

    # 找出所有需要處理的日期 (支援 date=yyyymmdd 和 yyyy/yyyymmdd 結構)
    all_dates = set()
    for d in os.listdir(category_path):
        if d.startswith("date="):
            all_dates.add(d.split("=")[1])
        elif len(d) == 4 and d.isdigit():
            y_path = os.path.join(category_path, d)
            if os.path.isdir(y_path):
                for sub_d in os.listdir(y_path):
                    if len(sub_d) == 8 and sub_d.isdigit():
                        all_dates.add(sub_d)
    
    for date_str in sorted(list(all_dates)):
        if start_env and date_str < start_env: continue
        if end_env and date_str > end_env: continue
        process_date(date_str)

if __name__ == "__main__":
    main()
