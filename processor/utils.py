import polars as pl
from schemas import COLUMN_MAP, NUMERIC_COLS

def find_header_line(file_path, encoding='utf-8-sig'):
    """尋找包含 '證券代號' 或 '代號' 的行數"""
    try:
        with open(file_path, 'r', encoding=encoding) as f:
            for i, line in enumerate(f):
                # 寬鬆檢查
                if ("證券代號" in line or "代號" in line) and "," in line:
                    return i
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
    return -1

def clean_dataframe(df):
    """通用清洗邏輯: 欄位重命名、Symbol 清洗、數值轉型"""
    # 1. 欄位重命名
    valid_cols = [c for c in df.columns if c in COLUMN_MAP]
    df = df.select(valid_cols)
    df = df.rename({c: COLUMN_MAP[c] for c in valid_cols})
    
    # 2. 清洗 Symbol
    if "symbol" in df.columns:
        df = df.with_columns(
            pl.col("symbol")
            .str.replace_all('=|"', '')
            .str.strip_chars()
        )

    # 3. 清洗數值
    for col in df.columns:
        if col in NUMERIC_COLS:
            df = df.with_columns(
                pl.col(col)
                .str.replace_all(",", "")
                .str.replace_all("--", "") # 處理空值
                .str.strip_chars()
                .cast(pl.Float64, strict=False)
            )
            
    return df

def read_raw_csv(file_path):
    """標準化的 Raw CSV 讀取函式，回傳初步清洗後的 DataFrame"""
    skip_rows = find_header_line(file_path)
    if skip_rows == -1:
        return None

    try:
        df = pl.read_csv(file_path, skip_rows=skip_rows, infer_schema_length=0, 
                         ignore_errors=True, truncate_ragged_lines=True)
        
        # 執行基礎清洗，讓回傳的 DF 結構與 Processed Parquet 接近，方便比對
        df = clean_dataframe(df)
        return df
    except Exception as e:
        print(f"Failed to read raw csv {file_path}: {e}")
        return None
