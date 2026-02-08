import polars as pl
from io import BytesIO
from schemas import COLUMN_MAP, NUMERIC_COLS

def clean_dataframe(df):
    """通用清洗邏輯: 欄位重命名、Symbol 清洗、數值轉型"""
    
    # 1. 取得目前的欄位名稱，並建立一個「乾淨名稱」到「原始名稱」的映射
    # 目的：處理 CSV 中帶有空格、引號或 BOM 的欄位名
    raw_to_clean = {c: c.strip().replace('"', '').replace('\ufeff', '') for c in df.columns}
    
    # 2. 建立「英文欄位名」到「原始欄位名」的映射
    # 我們遍歷 COLUMN_MAP，看看有沒有哪個乾淨名稱匹配得上
    rename_map = {}
    for raw_col, clean_col in raw_to_clean.items():
        if clean_col in COLUMN_MAP:
            eng_name = COLUMN_MAP[clean_col]
            rename_map[raw_col] = eng_name
            
    # 3. 特別處理 Symbol 和 Name (如果沒對上的話)
    if "symbol" not in rename_map.values():
        for raw_col, clean_col in raw_to_clean.items():
            if "證券代號" in clean_col or clean_col == "代號":
                rename_map[raw_col] = "symbol"
                break
    
    if "name" not in rename_map.values():
        for raw_col, clean_col in raw_to_clean.items():
            if "證券名稱" in clean_col or clean_col == "名稱":
                rename_map[raw_col] = "name"
                break

    if not rename_map:
        return None

    # 4. 執行 Select 與 Rename
    df = df.select(list(rename_map.keys()))
    df = df.rename(rename_map)
    
    # 5. 清洗 Symbol (移除 = " 等雜質)
    if "symbol" in df.columns:
        df = df.with_columns(
            pl.col("symbol").cast(pl.Utf8) # 強制轉字串
            .str.replace_all('=|"', '')
            .str.strip_chars()
        )

    # 6. 數值清洗
    for col in df.columns:
        if col in NUMERIC_COLS:
            df = df.with_columns(
                pl.col(col).cast(pl.Utf8) # 先轉字串再處理
                .str.replace_all(",", "")
                .str.replace_all("--", "")
                .str.strip_chars()
                .cast(pl.Float64, strict=False)
            )
            
    return df

def read_raw_csv(file_path, category=None):
    """標準化的 Raw CSV 讀取函式，支援跨列標題合併"""
    try:
        # 1. 讀取檔案內容
        with open(file_path, 'r', encoding='utf-8-sig', errors='ignore') as f:
            lines = f.readlines()
        
        # 2. 尋找主標頭行 (包含 證券代號/代號/指數)
        # 注意: 如果是 daily_quotes，應排除 "指數"，否則會抓到大盤區塊
        header_idx = -1
        keywords = ["證券代號", "代號"]
        if category == "market_indices":
            keywords.append("指數")
            
        for i, line in enumerate(lines):
            clean_line = line.replace('"', '').replace('\ufeff', '')
            if any(k in clean_line for k in keywords) and clean_line.count(",") >= 3:
                # 特別檢查: 排除大盤指數區塊，如果目標是個股
                if category != "market_indices" and "收盤指數" in clean_line:
                    continue
                header_idx = i
                break
        
        if header_idx == -1:
            return None

        # 3. 處理跨列標題 (例如 SII 融資融券)
        # 如果上一行 (header_idx - 1) 包含「融資」或「融券」等分類字眼，且其逗號數較少
        # 則我們嘗試手動合併它們
        current_header = [c.strip().replace('"', '') for c in lines[header_idx].split(",")]
        
        if header_idx > 0:
            prev_line = lines[header_idx-1].replace('"', '').strip()
            # 偵測是否為分類行 (通常有大量空欄位)
            if "融資" in prev_line or "融券" in prev_line or "借券" in prev_line:
                categories = [c.strip().replace('"', '') for c in lines[header_idx-1].split(",")]
                
                # 合併邏輯: 遍歷子標題，向上尋找最近的一個非空分類名
                merged_header = []
                last_cat = ""
                for j, sub in enumerate(current_header):
                    # 如果當前分類行有值，更新 last_cat
                    if j < len(categories) and categories[j]:
                        last_cat = categories[j]
                    
                    # 只有在有分類且 sub 不是關鍵欄位時才合併
                    if last_cat and sub and sub not in ["代號", "名稱", "證券代號", "證券名稱", "註記", "備註"]:
                        merged_header.append(f"{last_cat}-{sub}")
                    else:
                        merged_header.append(sub)
                
        # 使用合併後的標題重建資料
        # 關鍵修正: 處理每行逗號數量不一的問題 (Ragged lines) 並正確處理引號內的逗號
        import csv
        header_line = ",".join(merged_header if 'merged_header' in locals() else current_header)
        expected_cols = len(header_line.split(","))
        
        cleaned_lines = [header_line]
        for line in lines[header_idx+1:]:
            if not line.strip() or line.strip().replace(",", "") == "":
                continue
            
            # 使用 csv.reader 解析單行，正確處理 "公司,名稱" 這種格式
            try:
                reader = csv.reader([line.strip()])
                parts = next(reader)
            except:
                parts = line.strip().split(",")
                
            if len(parts) > expected_cols:
                parts = parts[:expected_cols]
            elif len(parts) < expected_cols:
                parts.extend([""] * (expected_cols - len(parts)))
            
            # 重新組合成標準 CSV 行 (不含引號以簡化後續處理)
            cleaned_lines.append(",".join(['"' + p.replace('"', '""') + '"' for p in parts]))

        content = "\n".join(cleaned_lines)

        df = pl.read_csv(BytesIO(content.encode('utf-8')), infer_schema_length=0, 
                         ignore_errors=True)
        
        # 4. 執行清洗
        df = clean_dataframe(df)
        return df
    except Exception as e:
        print(f"Failed to read raw csv {file_path}: {e}")
        import traceback
        traceback.print_exc()
        return None

def read_sii_indices(file_path):
    """專門從 SII 每日收盤行情 CSV 中提取大盤指數區塊"""
    try:
        with open(file_path, 'r', encoding='utf-8-sig', errors='ignore') as f:
            lines = f.readlines()
        
        # 1. 尋找指數區塊的開始與結束
        start_idx = -1
        end_idx = -1
        
        for i, line in enumerate(lines):
            clean_line = line.replace('"', '').replace('\ufeff', '')
            # 指數區塊標題通常包含 "指數" 與 "收盤指數"
            if "指數" in clean_line and "收盤指數" in clean_line:
                if start_idx == -1:
                     start_idx = i
                continue
            
            # 找到下一個區塊的標題 (通常是個股區塊) 作為結束點
            if start_idx != -1 and ("證券代號" in clean_line or "代號" in clean_line):
                end_idx = i
                break
        
        if start_idx == -1:
            return None # 沒找到指數區塊

        if end_idx == -1:
            end_idx = len(lines) # 如果沒找到下一個區塊，就讀到最後

        # 2. 擷取指數內容
        # 排除掉中間可能的空行或分隔線
        raw_content = "".join(lines[start_idx:end_idx])
        
        # 3. 讀取 CSV
        # 這裡需要小心，因為第一行是 header
        df = pl.read_csv(BytesIO(raw_content.encode('utf-8')), infer_schema_length=0, 
                         ignore_errors=True, truncate_ragged_lines=True)
        
        # 4. 清洗
        # 先執行標準清洗，這會把 "指數" -> "name"
        df = clean_dataframe(df)
        
        if df is not None:
             # 確保 name 存在
             if "name" in df.columns:
                 # 過濾：只保留名稱以「指數」結尾的資料
                 df = df.filter(pl.col("name").str.ends_with("指數"))

                 # 根據 direction 調整 change 的正負號
                 if "direction" in df.columns and "change" in df.columns:
                     df = df.with_columns(
                         pl.when(pl.col("direction") == "-")
                         .then(-pl.col("change"))
                         .otherwise(pl.col("change"))
                         .alias("change")
                     )

                 # 填補 symbol: 大盤指數沒有代號，直接用名稱當代號
                 if "symbol" not in df.columns:
                     df = df.with_columns(pl.col("name").alias("symbol"))
                 else:
                     # 如果有 symbol 但全空，用 name 填補
                     df = df.with_columns(
                         pl.when(pl.col("symbol").is_null())
                         .then(pl.col("name"))
                         .otherwise(pl.col("symbol"))
                         .alias("symbol")
                     )

        return df

    except Exception as e:
        print(f"Failed to read indices from {file_path}: {e}")
        return None
