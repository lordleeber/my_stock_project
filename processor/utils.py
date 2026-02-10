import polars as pl
import pandas as pd
import csv
import io
import os
from pathlib import Path
from schemas import COLUMN_MAP, NUMERIC_COLS

def log_parsing_error(file_path, msg, exception=None):
    """
    將 CSV 解析階段的錯誤訊息記錄到專用的 error_processor.md 檔案
    """
    error_file = Path("/app/error_processor.md")
    timestamp = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    date_str = "Unknown"
    
    # 嘗試從路徑提取日期
    if "date=" in str(file_path):
        date_str = str(file_path).split("date=")[1].split("/")[0]

    with open(error_file, 'a', encoding='utf-8') as f:
        f.write(f"\n## Utils Parsing Error - {timestamp}\n")
        f.write(f"**Date:** {date_str}\n")
        f.write(f"**File:** {Path(file_path).name}\n")
        f.write(f"**Message:** {msg}\n")
        if exception:
            f.write(f"**Exception:** {str(exception)}\n")
        f.write("---\n")

def clean_dataframe(df):
    """通用清洗邏輯: 欄位重命名、Symbol 清洗、數值轉型"""
    if df is None or df.is_empty():
        return None
        
    raw_columns = df.columns
    rename_dict = {}
    used_names = {}
    matched_any = False
    
    for i, col in enumerate(raw_columns):
        clean_col = col.strip().replace('"', '').replace('\ufeff', '')
        norm_col = clean_col.replace(" ", "").replace("\u3000", "").replace("\t", "")
        
        eng_name = None
        if clean_col in COLUMN_MAP:
            eng_name = COLUMN_MAP[clean_col]
        elif norm_col in COLUMN_MAP:
            eng_name = COLUMN_MAP[norm_col]
        elif any(k in norm_col for k in ["證券代號", "代號", "股票代號"]):
            eng_name = "symbol"
        elif any(k in norm_col for k in ["證券名稱", "名稱", "股票名稱"]):
            eng_name = "name"
            
        if eng_name:
            if eng_name in used_names:
                used_names[eng_name] += 1
                unique_name = f"{eng_name}_{used_names[eng_name]}"
            else:
                used_names[eng_name] = 1
                unique_name = eng_name
            
            rename_dict[col] = unique_name
            matched_any = True
            
    if not matched_any:
        if os.getenv("DEBUG", "0") == "1":
            print(f"⚠️  clean_dataframe matched 0 columns. First 5 raw: {raw_columns[:5]}")
        return None

    df = df.rename(rename_dict)
    keep_cols = [c for c in df.columns if not c.startswith("raw_")]
    df = df.select(keep_cols)
    
    if "symbol" in df.columns:
        df = df.with_columns(
            pl.col("symbol").cast(pl.Utf8).str.replace_all('=|"', '').str.strip_chars()
        )

    for col in df.columns:
        base_col = col.split('_')[0] if '_' in col else col
        if col in NUMERIC_COLS or base_col in NUMERIC_COLS:
            df = df.with_columns(
                pl.col(col).cast(pl.Utf8)
                .str.replace_all(",", "").str.replace_all("--", "").str.replace_all(" ", "")
                .str.strip_chars().cast(pl.Float64, strict=False)
            )
    return df

def read_raw_csv(file_path, category=None):
    """強化版的 Raw CSV 讀取函式"""
    try:
        if not os.path.exists(file_path):
            return None

        # 自動編碼探測
        try:
            with open(file_path, 'r', encoding='utf-8-sig') as f:
                lines = f.readlines()
        except UnicodeDecodeError:
            # 使用 replace 而非 ignore，保留解碼失敗的標記供後續檢查
            with open(file_path, 'r', encoding='cp950', errors='replace') as f:
                lines = f.readlines()

        if not lines:
            return None
            
        header_idx = -1
        keywords = ["證券代號", "代號"]
        if category == "market_indices": keywords.append("指數")
            
        for i, line in enumerate(lines):
            clean_line = line.replace('"', '').replace('\ufeff', '')
            if any(k in clean_line for k in keywords) and clean_line.count(",") >= 3:
                if category != "market_indices" and "收盤指數" in clean_line: continue
                header_idx = i
                break
        
        if header_idx == -1: return None

        header = []
        is_multi_row = False
        if header_idx > 0:
            prev_line = lines[header_idx-1].replace('"', '').strip()
            # 偵測是否為分類行 (通常有分類字眼且包含大量逗號)
            if any(k in prev_line for k in ["融資", "融券", "借券"]) and prev_line.count(",") >= 3:
                is_multi_row = True
                
        if is_multi_row:
            # 使用簡單的 split 代替 csv.reader 來解析標題，避免引號引發的問題
            cat_row = [c.strip().replace('"', '') for c in next(csv.reader(io.StringIO(lines[header_idx-1])))]
            sub_row = [c.strip().replace('"', '') for c in next(csv.reader(io.StringIO(lines[header_idx])))]
            
            last_cat = ""
            for j, sub in enumerate(sub_row):
                cat = cat_row[j].strip() if j < len(cat_row) else ""
                if cat: last_cat = cat
                header.append(f"{last_cat}-{sub}" if last_cat and sub else (sub or last_cat))
        else:
            header = [c.strip().replace('"', '') for c in next(csv.reader(io.StringIO(lines[header_idx])))]

        if not header:
            return None

        raw_data = []
        mismatched_rows = 0
        csv_reader = csv.reader(io.StringIO("\n".join(lines[header_idx+1:])))

        for row in csv_reader:
            if not row or not row[0]:
                continue

            first = row[0].strip()
            if first.startswith("說明:") or first.startswith("Total") or first == "以上":
                continue

            # 處理行長度不一致的情況
            if len(row) != len(header):
                mismatched_rows += 1
                if len(row) < len(header):
                    row.extend([''] * (len(header) - len(row)))
                elif len(row) > len(header):
                    row = row[:len(header)]

            raw_data.append(row)

        if not raw_data:
            return None

        unique_header = []
        h_counts = {}
        for h in header:
            if h in h_counts:
                h_counts[h] += 1
                unique_header.append(f"{h}_{h_counts[h]}")
            else:
                h_counts[h] = 0
                unique_header.append(h)

        if os.getenv("DEBUG", "0") == "1":
            if mismatched_rows > 0:
                print(f"⚠️  {Path(file_path).name}: {mismatched_rows} rows adjusted for length mismatch")
            print(f"DEBUG: unique_header[:10] = {unique_header[:10]}")
        
        df = pl.DataFrame(raw_data, schema=unique_header, orient="row")
        df_cleaned = clean_dataframe(df)

        # 在 debug 模式下顯示成功訊息
        if df_cleaned is not None and os.getenv("DEBUG", "0") == "1":
            print(f"✓ Loaded {len(df_cleaned)} rows from {Path(file_path).name}")

        return df_cleaned
    except Exception as e:
        log_parsing_error(file_path, f"Failed to parse CSV: {str(e)}", exception=e)
        return None

def read_sii_indices(file_path):
    """特別為 SII 指數區塊設計的讀取邏輯"""
    try:
        with open(file_path, 'r', encoding='utf-8-sig', errors='replace') as f:
            lines = f.readlines()

        # 找到「收盤指數」區塊
        start_idx = -1
        for i, line in enumerate(lines):
            if "收盤指數" in line:
                start_idx = i
                break

        if start_idx == -1:
            return None

        # 提取指數資料行
        index_lines = []
        for line in lines[start_idx:]:
            if line.count(",") < 2:
                break
            index_lines.append(line)

        if not index_lines:
            return None
        
        # 使用 Pandas 處理重複標頭
        pdf = pd.read_csv(io.StringIO("".join(index_lines)))
        
        # 處理舊格式：將 "漲跌(+/-)" 和 "漲跌點數" 合併
        if "漲跌(+/-)" in pdf.columns and "漲跌點數" in pdf.columns:
            def combine_change(row):
                sign = str(row["漲跌(+/-)"]).strip()
                val = str(row["漲跌點數"]).replace(",", "")
                if val == "--" or not val: return None
                try:
                    num = float(val)
                    return -num if sign == "-" else num
                except:
                    return None
            pdf["change_combined"] = pdf.apply(combine_change, axis=1)

        new_rename_map = {}

        for col in pdf.columns:
            c = str(col).strip().replace('"', '')
            if c == "指數" or c == "報酬指數":
                new_rename_map[col] = "symbol"
            elif c == "收盤指數":
                new_rename_map[col] = "close"
            elif c == "change_combined":
                new_rename_map[col] = "change"
            elif "漲跌" in c and "漲跌幅" not in c and "change" not in new_rename_map.values():
                if "漲跌(+/-)" not in pdf.columns: # 只有在單一欄位時才直接對映
                    new_rename_map[col] = "change"

        if "symbol" not in new_rename_map.values():
            return None

        pdf = pdf[list(new_rename_map.keys())].rename(columns=new_rename_map)
        df = pl.from_pandas(pdf)

        # 清洗數值欄位
        for col in ["close", "change"]:
            if col in df.columns:
                df = df.with_columns(
                    pl.col(col).cast(pl.Utf8)
                    .str.replace_all(",", "")
                    .str.replace_all("--", "")
                    .cast(pl.Float64, strict=False)
                )

        # 在 debug 模式下顯示成功訊息
        if os.getenv("DEBUG", "0") == "1":
            print(f"✓ Loaded {len(df)} indices from {Path(file_path).name}")

        return df
    except Exception as e:
        log_parsing_error(file_path, f"Failed to parse SII indices: {str(e)}", exception=e)
        return None