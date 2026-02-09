import polars as pl
import csv
import io
import os
from pathlib import Path
from datetime import datetime
from schemas import COLUMN_MAP, NUMERIC_COLS

def log_error(file_path, error_msg, exception=None):
    """統一的錯誤記錄函式，寫入 error_processor.md"""
    try:
        import traceback
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with open("error_processor.md", "a", encoding="utf-8") as f:
            f.write(f"\n## {Path(file_path).name if file_path else 'Unknown'} - {timestamp}\n")
            f.write(f"**Error**: {error_msg}\n")
            if exception:
                f.write(f"```\n{traceback.format_exc()}\n```\n")
            f.write("\n---\n")
    except Exception as log_err:
        print(f"Failed to write error log: {log_err}")

def clean_dataframe(df):
    """通用清洗邏輯: 欄位重命名、Symbol 清洗、數值轉型"""
    if df is None or df.is_empty():
        return None
        
    # 1. 取得目前的欄位名稱
    raw_columns = df.columns
    
    # 2. 建立重新命名映射 (處理重複欄位名)
    # TWSE 有時會在同一個 CSV 裡給出兩個名字一模一樣的欄位，這會搞死 DataFrame
    new_columns = []
    rename_dict = {}
    used_names = {}
    
    matched_any = False
    
    for i, col in enumerate(raw_columns):
        clean_col = col.strip().replace('"', '').replace('\ufeff', '')
        # 正規化：移除所有空白
        norm_col = clean_col.replace(" ", "").replace("\u3000", "").replace("\t", "")
        
        eng_name = None
        # 優先完全匹配
        if clean_col in COLUMN_MAP:
            eng_name = COLUMN_MAP[clean_col]
        # 其次正規化匹配
        elif norm_col in COLUMN_MAP:
            eng_name = COLUMN_MAP[norm_col]
        # 針對 Symbol 和 Name 的精確模糊匹配（避免誤判如「證券代號備註」）
        elif norm_col in ["證券代號", "代號", "股票代號", "商品代號"]:
            eng_name = "symbol"
        elif norm_col in ["證券名稱", "名稱", "股票名稱", "商品名稱"]:
            eng_name = "name"
            
        if eng_name:
            # 處理重複的英文名稱 (例如兩列都叫 dealer_net)
            if eng_name in used_names:
                used_names[eng_name] += 1
                unique_name = f"{eng_name}_{used_names[eng_name]}"
            else:
                used_names[eng_name] = 1
                unique_name = eng_name
            
            rename_dict[col] = unique_name
            new_columns.append(unique_name)
            matched_any = True
        else:
            # 未匹配的欄位保留原始名稱或丟棄 (這裡選擇保留，稍後 select)
            new_columns.append(f"raw_{i}")
            
    if not matched_any:
        return None

    # 執行 Rename
    df = df.rename(rename_dict)
    
    # 僅保留有意義的欄位
    keep_cols = [c for c in df.columns if not c.startswith("raw_")]
    df = df.select(keep_cols)
    
    # 3. 清洗 Symbol (移除 = " 等雜質)
    if "symbol" in df.columns:
        df = df.with_columns(
            pl.col("symbol").cast(pl.Utf8)
            .str.replace_all('=|"', '')
            .str.strip_chars()
        )

    # 4. 數值清洗
    for col in df.columns:
        # 檢查是否為數值欄位 (包含帶編號的變體)
        base_col = col.split('_')[0] if '_' in col else col
        is_numeric = col in NUMERIC_COLS or base_col in NUMERIC_COLS
        
        if is_numeric:
            df = df.with_columns(
                pl.col(col).cast(pl.Utf8)
                .str.replace_all(",", "")
                .str.replace_all("--", "")
                .str.replace_all(" ", "")
                .str.strip_chars()
                .cast(pl.Float64, strict=False)
            )
            
    return df

def read_raw_csv(file_path, category=None):
    """
    強化版的 Raw CSV 讀取函式，支援 csv 模組精確解析與欄位對齊

    Args:
        file_path (str): CSV 檔案的絕對路徑
        category (str, optional): 資料類別 ("market_indices" 或 None)

    Returns:
        pl.DataFrame | None: 清洗後的 DataFrame，若解析失敗則返回 None

    Features:
        - 自動編碼探測 (UTF-8-BOM / CP950)
        - 使用 csv.reader 處理引號內逗號
        - 動態列長度校正 (Ragged Rows)
        - 跨列標題合併 (融資融券)
    """
    try:
        if not os.path.exists(file_path):
            return None

        # 先探測編碼，通常是 utf-8-sig 或 cp950
        try:
            with open(file_path, 'r', encoding='utf-8-sig') as f:
                lines = f.readlines()
        except UnicodeDecodeError as e:
            log_error(file_path, f"UTF-8 encoding failed, falling back to CP950: {e}")
            with open(file_path, 'r', encoding='cp950', errors='replace') as f:
                lines = f.readlines()

        if not lines:
            return None
            
        # 1. 尋找主標頭行
        header_idx = -1
        keywords = ["證券代號", "代號"]
        if category == "market_indices":
            keywords.append("指數")
            
        for i, line in enumerate(lines):
            clean_line = line.replace('"', '').replace('\ufeff', '')
            if any(k in clean_line for k in keywords) and clean_line.count(",") >= 3:
                if category != "market_indices" and "收盤指數" in clean_line:
                    continue
                header_idx = i
                break
        
        if header_idx == -1:
            return None

        # 2. 處理標頭 (Header Parsing)
        header = []
        is_multi_row = False
        if header_idx > 0:
            prev_line = lines[header_idx-1].replace('"', '').strip()
            if any(k in prev_line for k in ["融資", "融券", "借券"]):
                is_multi_row = True
                
        if is_multi_row:
            header_csv = csv.reader(io.StringIO("\n".join([lines[header_idx-1], lines[header_idx]])))
            cat_row = next(header_csv)
            sub_row = next(header_csv)
            
            last_cat = ""
            for j, sub in enumerate(sub_row):
                cat = cat_row[j].strip() if j < len(cat_row) else ""
                if cat: last_cat = cat
                if last_cat and sub:
                    header.append(f"{last_cat}-{sub}")
                else:
                    header.append(sub or last_cat)
        else:
            # 使用 csv.reader 解析單行標題，確保處理引號內逗號
            h_row = next(csv.reader(io.StringIO(lines[header_idx])))
            header = [c.strip() for c in h_row]

        # 3. 解析資料行 (Data Parsing)
        raw_data = []
        csv_content = "\n".join(lines[header_idx+1:])
        csv_reader = csv.reader(io.StringIO(csv_content))

        mismatched_rows = 0
        for line_num, row in enumerate(csv_reader, start=header_idx+2):
            if not row or not row[0] or row[0].startswith("說明:") or row[0].startswith("Total") or "以上" in row[0]:
                continue

            # 欄位長度校正
            if len(row) != len(header):
                mismatched_rows += 1
                if len(row) < len(header):
                    row.extend([''] * (len(header) - len(row)))
                else:
                    row = row[:len(header)]

            raw_data.append(row)

        # 記錄長度不一致警告
        if mismatched_rows > 0:
            log_error(file_path, f"Row length mismatch: {mismatched_rows} rows adjusted (expected {len(header)} columns)")
            
        if not raw_data:
            return None
            
        # 4. 轉為 DataFrame 並清洗
        # 為了解決重複 Header 問題，我們先給予臨時唯一名稱，或者使用 Polars 的對應功能
        # 這裡我們手動處理重複 Header
        unique_header = []
        h_counts = {}
        for h in header:
            if h in h_counts:
                h_counts[h] += 1
                unique_header.append(f"{h}_{h_counts[h]}")
            else:
                h_counts[h] = 0
                unique_header.append(h)

        df = pl.DataFrame(raw_data, schema=unique_header, orient="row")
        df_cleaned = clean_dataframe(df)

        # 成功讀取日誌
        if df_cleaned is not None:
            print(f"✓ Loaded {len(df_cleaned)} rows from {Path(file_path).name}")

        return df_cleaned

    except Exception as e:
        error_msg = f"Failed to parse CSV: {str(e)}"
        print(f"✗ {error_msg} - {Path(file_path).name}")
        log_error(file_path, error_msg, exception=e)
        return None

def read_sii_indices(file_path):
    """
    特別為 SII 指數區塊設計的讀取邏輯

    Args:
        file_path (str): SII 每日收盤行情 CSV 檔案路徑

    Returns:
        pl.DataFrame | None: 包含 symbol, close, change 欄位的指數資料

    Note:
        - 從 CSV 中提取「收盤指數」區塊
        - 自動處理千分位逗號與缺失值 (---)
    """
    try:
        with open(file_path, 'r', encoding='utf-8-sig', errors='replace') as f:
            lines = f.readlines()

        start_idx = -1
        for i, line in enumerate(lines):
            if "收盤指數" in line:
                start_idx = i
                break

        if start_idx == -1:
            log_error(file_path, "Cannot find '收盤指數' header in SII indices")
            return None

        index_lines = []
        for line in lines[start_idx:]:
            if line.count(",") < 2: break
            index_lines.append(line)

        if not index_lines:
            log_error(file_path, "No data rows found in SII indices block")
            return None

        df = pl.read_csv(io.StringIO("".join(index_lines)), infer_schema_length=0)

        rename_map = {}
        for col in df.columns:
            c = col.strip().replace('"', '')
            if c == "指數": rename_map[col] = "symbol"
            elif c == "收盤指數": rename_map[col] = "close"
            elif "漲跌" in c: rename_map[col] = "change"

        if "symbol" not in rename_map.values():
            log_error(file_path, f"Cannot find required columns in SII indices. Found: {df.columns}")
            return None

        df = df.select(list(rename_map.keys())).rename(rename_map)

        for col in ["close", "change"]:
            if col in df.columns:
                df = df.with_columns(
                    pl.col(col).str.replace_all(",", "").str.replace_all("--", "").cast(pl.Float64, strict=False)
                )

        print(f"✓ Loaded {len(df)} indices from {Path(file_path).name}")
        return df

    except Exception as e:
        error_msg = f"Failed to parse SII indices: {str(e)}"
        print(f"✗ {error_msg} - {Path(file_path).name}")
        log_error(file_path, error_msg, exception=e)
        return None
