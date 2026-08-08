import polars as pl
import pandas as pd
import csv
import io
import os
from pathlib import Path
from common.schemas import COLUMN_MAP, NUMERIC_COLS

# 這支的兩個呼叫點都在 except 區塊裡（「記一筆、回 None、跳過這個檔」的降級路徑），
# 所以寫 log 失敗絕不能升級成中斷——見 _error_report.py 的 docstring。
from _error_report import log_parsing_error


def clean_dataframe(df, return_col_mapping=False):
    """
    通用清洗邏輯: 欄位重命名、Symbol 清洗、數值轉型

    Args:
        df: Polars DataFrame
        return_col_mapping: 如果為 True，返回 (df, col_mapping)，其中 col_mapping 是 {英文欄位名: 原始欄位索引(1-based)}

    Returns:
        df 或 (df, col_mapping)
    """
    if df is None or df.is_empty():
        return (None, {}) if return_col_mapping else None

    raw_columns = df.columns
    rename_dict = {}
    used_names = {}
    matched_any = False
    col_index_mapping = {}  # {英文欄位名: 原始欄位索引(1-based)}

    for i, col in enumerate(raw_columns):
        # 跳過 lineage 追蹤欄位，這些欄位保持原名
        if col in ["src_file", "src_row", "src_col"]:
            continue

        clean_col = col.strip().replace('"', "").replace("\ufeff", "")
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

        # 強制要求所有欄位都有映射
        if eng_name is None:
            raise ValueError(
                f"Unknown column '{clean_col}' (normalized: '{norm_col}') at index {i}. "
                f"Please add mapping to COLUMN_MAP in processor/schemas.py"
            )

        if eng_name:
            if eng_name in used_names:
                used_names[eng_name] += 1
                unique_name = f"{eng_name}_{used_names[eng_name]}"
            else:
                used_names[eng_name] = 1
                unique_name = eng_name

            rename_dict[col] = unique_name
            matched_any = True
            # 記錄英文欄位名對應的原始欄位索引 (1-based)
            col_index_mapping[unique_name] = i + 1

    if not matched_any:
        if os.getenv("DEBUG", "0") == "1":
            print(
                f"⚠️  clean_dataframe matched 0 columns. First 5 raw: {raw_columns[:5]}"
            )
        return (None, {}) if return_col_mapping else None

    df = df.rename(rename_dict)
    keep_cols = [c for c in df.columns if not c.startswith("raw_")]
    df = df.select(keep_cols)

    if "symbol" in df.columns:
        df = df.with_columns(
            pl.col("symbol").cast(pl.Utf8).str.replace_all('=|"', "").str.strip_chars()
        )

    for col in df.columns:
        base_col = col.split("_")[0] if "_" in col else col
        if col in NUMERIC_COLS or base_col in NUMERIC_COLS:
            df = df.with_columns(
                pl.col(col)
                .cast(pl.Utf8)
                .str.replace_all(",", "")
                .str.replace_all("--", "")
                .str.replace_all(" ", "")
                .str.strip_chars()
                .cast(pl.Float64, strict=False)
            )

    if return_col_mapping:
        return df, col_index_mapping
    return df


def read_raw_csv(file_path, category=None, return_col_mapping=False):
    """強化版的 Raw CSV 讀取函式

    Args:
        file_path: CSV 檔案路徑
        category: 資料類別 (如 "market_indices")
        return_col_mapping: 如果為 True，返回 (df, col_mapping)，供後續 enforce_schema 後重新生成 src_col

    Returns:
        df 或 (df, col_mapping) 取決於 return_col_mapping 參數
        col_mapping 是 {英文欄位名: 原始欄位索引(1-based)}
    """
    try:
        if not os.path.exists(file_path):
            return (None, {}) if return_col_mapping else None

        # 自動編碼探測
        try:
            with open(file_path, "r", encoding="utf-8-sig") as f:
                lines = f.readlines()
        except UnicodeDecodeError:
            # 使用 replace 而非 ignore，保留解碼失敗的標記供後續檢查
            with open(file_path, "r", encoding="cp950", errors="replace") as f:
                lines = f.readlines()

        if not lines:
            return (None, {}) if return_col_mapping else None

        header_idx = -1
        keywords = ["證券代號", "代號"]
        if category == "market_indices":
            keywords.append("指數")

        for i, line in enumerate(lines):
            clean_line = line.replace('"', "").replace("\ufeff", "")
            if any(k in clean_line for k in keywords) and clean_line.count(",") >= 3:
                if category != "market_indices" and "收盤指數" in clean_line:
                    continue
                header_idx = i
                break

        if header_idx == -1:
            return (None, {}) if return_col_mapping else None

        header = []
        is_multi_row = False
        if header_idx > 0:
            prev_line = lines[header_idx - 1].replace('"', "").strip()
            # 偵測是否為分類行 (通常有分類字眼且包含大量逗號)
            if (
                any(k in prev_line for k in ["融資", "融券", "借券"])
                and prev_line.count(",") >= 3
            ):
                is_multi_row = True

        if is_multi_row:
            # 使用簡單的 split 代替 csv.reader 來解析標題，避免引號引發的問題
            cat_row = [
                c.strip().replace('"', "")
                for c in next(csv.reader(io.StringIO(lines[header_idx - 1])))
            ]
            sub_row = [
                c.strip().replace('"', "")
                for c in next(csv.reader(io.StringIO(lines[header_idx])))
            ]

            last_cat = ""
            for j, sub in enumerate(sub_row):
                cat = cat_row[j].strip() if j < len(cat_row) else ""
                if cat:
                    last_cat = cat
                header.append(
                    f"{last_cat}-{sub}" if last_cat and sub else (sub or last_cat)
                )
        else:
            header = [
                c.strip().replace('"', "")
                for c in next(csv.reader(io.StringIO(lines[header_idx])))
            ]

        if not header:
            return (None, {}) if return_col_mapping else None

        raw_data_with_lineage = []
        mismatched_rows = 0

        # 直接迭代原始行索引
        for line_idx in range(header_idx + 1, len(lines)):
            line = lines[line_idx]
            # 使用 csv.reader 解析單行
            row_reader = csv.reader(io.StringIO(line))
            try:
                row = next(row_reader)
            except StopIteration:
                continue

            # 原始檔案行號 (1-based)
            actual_src_row = line_idx + 1

            if not row or not row[0]:
                continue

            first = row[0].strip()
            if (
                first.startswith("說明:")
                or first.startswith("Total")
                or first == "以上"
            ):
                continue

            # 處理行長度不一致的情況
            if len(row) != len(header):
                mismatched_rows += 1
                if len(row) < len(header):
                    row.extend([""] * (len(header) - len(row)))
                elif len(row) > len(header):
                    row = row[: len(header)]

            # 儲存資料與精確的原始行號
            raw_data_with_lineage.append(list(row) + [actual_src_row])

        if not raw_data_with_lineage:
            return (None, {}) if return_col_mapping else None

        unique_header = []
        h_counts = {}
        for h in header:
            if h in h_counts:
                h_counts[h] += 1
                unique_header.append(f"{h}_{h_counts[h]}")
            else:
                h_counts[h] = 0
                unique_header.append(h)

        # 加入追蹤欄位標頭 (src_file 和 src_row)
        unique_header.extend(["src_file", "src_row"])

        # 準備資料與追蹤資訊
        final_data = []
        # 取得相對路徑以便儲存
        rel_path = (
            str(file_path).split("my_stock_project/")[-1]
            if "my_stock_project/" in str(file_path)
            else str(file_path)
        )

        for row_with_lineage in raw_data_with_lineage:
            # 最後一欄是我們剛剛暫存的 actual_src_row
            actual_src_row = row_with_lineage[-1]
            # 原始資料列 (除去最後一欄 actual_src_row)
            original_row = row_with_lineage[:-1]

            # 加入追蹤資訊到每一列
            new_row = original_row + [rel_path, actual_src_row]
            final_data.append(new_row)

        if os.getenv("DEBUG", "0") == "1":
            if mismatched_rows > 0:
                print(
                    f"⚠️  {Path(file_path).name}: {mismatched_rows} rows adjusted for length mismatch"
                )
            print(f"DEBUG: unique_header[:10] = {unique_header[:10]}")

        df = pl.DataFrame(final_data, schema=unique_header, orient="row")

        # 呼叫 clean_dataframe 並取得欄位映射
        result = clean_dataframe(df, return_col_mapping=True)
        if result[0] is None:
            return (None, {}) if return_col_mapping else None

        df_cleaned, col_mapping = result

        # 在 debug 模式下顯示成功訊息
        if df_cleaned is not None and os.getenv("DEBUG", "0") == "1":
            print(f"✓ Loaded {len(df_cleaned)} rows from {Path(file_path).name}")

        if return_col_mapping:
            # 返回 DataFrame (不含 src_col) 和欄位映射，由 caller 負責生成 src_col
            return df_cleaned, col_mapping
        else:
            # 舊行為：直接生成 src_col 並返回 DataFrame
            # 根據 clean_dataframe 後的欄位順序生成 src_col
            src_col_parts = []
            for col in df_cleaned.columns:
                if col in ["src_file", "src_row", "src_col"]:
                    continue
                if col in col_mapping:
                    src_col_parts.append(str(col_mapping[col]))
                else:
                    src_col_parts.append("x")

            src_col_str = "#".join(src_col_parts)
            df_cleaned = df_cleaned.with_columns(pl.lit(src_col_str).alias("src_col"))
            return df_cleaned
    except Exception as e:
        log_parsing_error(file_path, f"Failed to parse CSV: {str(e)}", exception=e)
        return (None, {}) if return_col_mapping else None


def read_sii_indices(file_path, return_col_mapping=False):
    """特別為 SII 指數區塊設計的讀取邏輯

    Args:
        file_path: 檔案路徑
        return_col_mapping: 如果為 True，返回 (df, col_mapping)

    Returns:
        df 或 (df, col_mapping) 取決於 return_col_mapping 參數
    """
    try:
        with open(file_path, "r", encoding="utf-8-sig", errors="replace") as f:
            lines = f.readlines()

        # 找到「收盤指數」區塊
        start_idx = -1
        for i, line in enumerate(lines):
            if "收盤指數" in line:
                start_idx = i
                break

        if start_idx == -1:
            return (None, {}) if return_col_mapping else None

        # 提取指數資料行
        index_lines = []
        for line in lines[start_idx:]:
            if line.count(",") < 2:
                break
            index_lines.append(line)

        if not index_lines:
            return (None, {}) if return_col_mapping else None

        # 使用 Pandas 處理重複標頭
        pdf = pd.read_csv(io.StringIO("".join(index_lines)))

        # 記錄原始欄位 (在添加計算欄位之前)
        original_columns = list(pdf.columns)

        # 處理舊格式：將 "漲跌(+/-)" 和 "漲跌點數" 合併
        if "漲跌(+/-)" in pdf.columns and "漲跌點數" in pdf.columns:

            def combine_change(row):
                sign = str(row["漲跌(+/-)"]).strip()
                val = str(row["漲跌點數"]).replace(",", "")
                if val == "--" or not val:
                    return None
                try:
                    num = float(val)
                    return -num if sign == "-" else num
                except Exception:
                    return None

            pdf["change_combined"] = pdf.apply(combine_change, axis=1)

        new_rename_map = {}

        for col in pdf.columns:
            c = str(col).strip().replace('"', "")
            if c == "指數" or c == "報酬指數":
                new_rename_map[col] = "index_name"
            elif c == "收盤指數":
                new_rename_map[col] = "index_close"
            elif c == "change_combined":
                new_rename_map[col] = "index_change_points"
            elif (
                "漲跌" in c
                and "漲跌幅" not in c
                and "index_change_points" not in new_rename_map.values()
            ):
                if "漲跌(+/-)" not in pdf.columns:  # 只有在單一欄位時才直接對映
                    new_rename_map[col] = "index_change_points"

        if "index_name" not in new_rename_map.values():
            return (None, {}) if return_col_mapping else None

        # 取得相對路徑
        rel_path = (
            str(file_path).split("my_stock_project/")[-1]
            if "my_stock_project/" in str(file_path)
            else str(file_path)
        )

        # 建立欄位映射: {英文欄位名: 原始欄位索引(1-based)}
        col_mapping = {}
        for col_name, eng_name in new_rename_map.items():
            if col_name in original_columns:
                col_idx = original_columns.index(col_name) + 1  # 1-based
                col_mapping[eng_name] = col_idx

        pdf = pdf[list(new_rename_map.keys())].rename(columns=new_rename_map)

        # 加入追蹤資訊
        # 這裡 pdf 的 index 是 0-based，實體行號為 start_idx + 1 (Header) + 1 (Data) + index
        pdf["src_file"] = rel_path
        pdf["src_row"] = start_idx + 2 + pdf.index

        df = pl.from_pandas(pdf)

        # 清洗數值欄位
        for col in ["index_close", "index_change_points"]:
            if col in df.columns:
                df = df.with_columns(
                    pl.col(col)
                    .cast(pl.Utf8)
                    .str.replace_all(",", "")
                    .str.replace_all("--", "")
                    .cast(pl.Float64, strict=False)
                )

        # 過濾掉內部重複的標題行 (index_name = "指數" 或 index_close 為 null)
        if "index_name" in df.columns:
            df = df.filter(pl.col("index_name") != "指數")
        if "index_close" in df.columns:
            df = df.filter(pl.col("index_close").is_not_null())

        # 在 debug 模式下顯示成功訊息
        if os.getenv("DEBUG", "0") == "1":
            print(f"✓ Loaded {len(df)} indices from {Path(file_path).name}")

        if return_col_mapping:
            return df, col_mapping
        else:
            # 舊行為：生成 src_col 並返回
            src_col_parts = []
            for col in df.columns:
                if col in ["src_file", "src_row", "src_col"]:
                    continue
                if col in col_mapping:
                    src_col_parts.append(str(col_mapping[col]))
                else:
                    src_col_parts.append("x")
            src_col_str = "#".join(src_col_parts)
            df = df.with_columns(pl.lit(src_col_str).alias("src_col"))
            return df
    except Exception as e:
        log_parsing_error(
            file_path, f"Failed to parse SII indices: {str(e)}", exception=e
        )
        return (None, {}) if return_col_mapping else None
