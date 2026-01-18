import os
import glob
import polars as pl
from schemas import COLUMN_MAP, NUMERIC_COLS

RAW_DIR = "/app/data/raw"
PROCESSED_DIR = "/app/data/processed"

def find_header_line(file_path, encoding='utf-8-sig'):
    """尋找包含 '證券代號' 或 '代號' 的行數"""
    try:
        with open(file_path, 'r', encoding=encoding) as f:
            for i, line in enumerate(f):
                # 判斷是否為 header 行 (寬鬆檢查，不強制要求引號)
                if ("證券代號" in line or "代號" in line) and "," in line:
                    return i
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
    return -1

def clean_dataframe(df):
    """通用清洗邏輯"""
    # 1. 欄位重命名
    # 只保留定義在 COLUMN_MAP 中的欄位
    valid_cols = [c for c in df.columns if c in COLUMN_MAP]
    df = df.select(valid_cols)
    df = df.rename({c: COLUMN_MAP[c] for c in valid_cols})
    
    # 2. 清洗 Symbol (針對 SII 三大法人的 Excel 公式 ="0050")
    if "symbol" in df.columns:
        df = df.with_columns(
            pl.col("symbol")
            .str.replace_all('=|"', '') # 去除 ="..."
            .str.strip_chars()
        )

    # 3. 清洗數值
    for col in df.columns:
        if col in NUMERIC_COLS:
            df = df.with_columns(
                pl.col(col)
                .str.replace_all(",", "")
                .str.replace_all("--", "") # 處理空值
                .str.strip_chars()         # 也對數值欄位去除空白 (以防萬一)
                .cast(pl.Float64, strict=False)
            )
            
    return df

def process_file(file_path, market, category):
    # 1. 尋找 Header
    skip_rows = find_header_line(file_path)
    if skip_rows == -1:
        # 有些檔案可能真的沒 header (例如空的)，或者格式完全不同
        print(f"Skipping {file_path}: Header not found.")
        return

    try:
        # 2. 讀取 CSV
        # infer_schema_length=0 強制讀為 String，方便後續清洗
        # truncate_ragged_lines=True 忽略行尾多餘的欄位 (SII 常見問題)
        df = pl.read_csv(file_path, skip_rows=skip_rows, infer_schema_length=0, ignore_errors=True, truncate_ragged_lines=True)
        
        # 3. 清洗
        df = clean_dataframe(df)
        
        # 4. 取得日期
        basename = os.path.basename(file_path)
        date_str = basename.split('.')[0] # YYYYMMDD
        
        # 檢查日期格式是否正確 (避免讀到非日期檔名的檔案)
        if len(date_str) != 8 or not date_str.isdigit():
            print(f"Skipping invalid filename: {basename}")
            return

        df = df.with_columns(
            pl.lit(date_str).str.strptime(pl.Date, "%Y%m%d").alias("date")
        )
        
        # 5. 儲存
        # category 對應到 output folder
        # Mapping: 中文目錄 -> 英文目錄 (簡單映射)
        category_map = {
            "每日收盤行情": "daily_quotes",
            "三大法人買賣金額統計表": "institutional_summary", # 這通常是大盤統計，可能不需要
            "三大法人買賣超日報": "institutional_investors",
            "外資及陸資投資持股統計": "foreign_holding",
            "融資融券": "margin_trading",
            "融券借券": "margin_sbl", # 借券
            "本益比殖利率淨值": "pe_ratio",
        }
        
        english_category = category_map.get(category, category)
        output_path = f"{PROCESSED_DIR}/{english_category}/market={market}/date={date_str}"
        os.makedirs(output_path, exist_ok=True)
        
        df.write_parquet(f"{output_path}/data.parquet")
        # print(f"Processed {market}/{english_category} {date_str}: {len(df)} rows")

    except Exception as e:
        print(f"Failed to process {file_path}: {e}")

def main():
    print("Starting ETL Pipeline...")
    
    markets = ["sii", "otc"]
    categories = [
        "每日收盤行情",
        "三大法人買賣超日報",
        "外資及陸資投資持股統計",
        "融資融券",
        "融券借券",
        "本益比殖利率淨值"
    ]
    
    for market in markets:
        for category in categories:
            # 搜尋該分類下的所有 CSV
            files = glob.glob(f"{RAW_DIR}/{market}/{category}/*.csv")
            if not files:
                continue
                
            print(f"Processing {market}/{category} ({len(files)} files)...")
            for f in files:
                process_file(f, market, category)

if __name__ == "__main__":
    main()