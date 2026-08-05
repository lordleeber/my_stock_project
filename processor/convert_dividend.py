import os
import sys
import csv
import datetime
import re
from pathlib import Path
import polars as pl

# 加入 common 目錄到搜尋路徑
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from common.schemas import SCHEMA_COLS, get_polars_schema

RAW_DIR = os.environ.get("RAW_DIR", "data/raw")
PROCESSED_DIR = os.environ.get("PROCESSED_DIR", "data/processed")
CATEGORY = "dividend"
DEBUG = os.getenv("DEBUG", "0") == "1"


def clean_numeric(val):
    if val is None or val == "--" or str(val).strip() == "":
        return None
    try:
        s = str(val).replace(",", "").strip()
        if s.startswith("(") and s.endswith(")"):
            s = "-" + s[1:-1]
        return float(s)
    except Exception:
        return None


def convert_minguo_date(date_str):
    """將民國日期 '111年01月12日' 轉換為 '2022-01-12'"""
    if not date_str:
        return None
    match = re.search(r"(\d+)年(\d+)月(\d+)日", str(date_str))
    if match:
        y, m, d = match.groups()
        # 民國年 + 1911 = 西元年
        year = int(y) + 1911
        return f"{year}-{m.zfill(2)}-{d.zfill(2)}"
    return None


def process_file(csv_file):
    try:
        # 讀取 CSV (跳過第一行標題 "111年01月01日 至 111年12月31日 除權除息計算結果表")
        with open(csv_file, "r", encoding="utf-8-sig", errors="replace") as f:
            reader = csv.reader(f)
            rows = list(reader)

        if len(rows) < 2:
            return None

        # 尋找真正包含 "股票代號" 的標頭行
        header_idx = -1
        for idx, row in enumerate(rows[:5]):
            if "股票代號" in row:
                header_idx = idx
                break

        if header_idx == -1:
            print(f"  [!] Skip {csv_file}: Cannot find header row")
            return None

        headers = [h.strip() for h in rows[header_idx]]

        # 建立映射
        from common.schemas import COLUMN_MAP

        inv_map = {v: k for k, v in COLUMN_MAP.items()}

        col_indices = {}
        for col in [
            "date",
            "symbol",
            "name",
            "close_before",
            "ref_price",
            "rights_dividend_value",
            "type",
        ]:
            raw_name = inv_map.get(col)
            if raw_name in headers:
                col_indices[col] = headers.index(raw_name)

        records = []
        for row_idx in range(header_idx + 1, len(rows)):
            row = rows[row_idx]
            if len(row) <= max(col_indices.values(), default=0):
                continue

            symbol = row[col_indices["symbol"]].strip()
            # 嚴格 4 碼過濾
            if not re.match(r"^\d{4}$", symbol):
                continue

            raw_date = row[col_indices["date"]].strip()
            iso_date = convert_minguo_date(raw_date)
            if not iso_date:
                continue

            data = {
                "date": iso_date,
                "symbol": symbol,
                "name": row[col_indices["name"]].strip(),
                "close_before": clean_numeric(row[col_indices["close_before"]]),
                "ref_price": clean_numeric(row[col_indices["ref_price"]]),
                "rights_dividend_value": clean_numeric(
                    row[col_indices["rights_dividend_value"]]
                ),
                "type": row[col_indices["type"]].strip(),
                "src_file": csv_file,
                "src_row": row_idx + 1,
                "src_col": "x",  # 簡化處理
            }
            records.append(data)

        return pl.DataFrame(records) if records else None
    except Exception as e:
        print(f"Error processing {csv_file}: {e}")
        return None


def _years_to_process(raw_path):
    """要 (重新) 處理哪些年度目錄。

    預設只處理「當年度」——過去年度的 raw 檔在跨年後即 immutable，每次都重算
    純屬白工。設 DIVIDEND_FULL=1 才重算所有年度（首次 bootstrap / 補資料）。
    """
    if os.getenv("DIVIDEND_FULL", "0") == "1":
        return sorted(p.name for p in raw_path.glob("20*") if p.is_dir())
    return [str(datetime.date.today().year)]


def main():
    raw_path = Path(RAW_DIR) / "ex_dividend"
    if not raw_path.exists():
        print(f"Raw path not found: {raw_path}")
        return

    print("Starting Dividend Processor...")

    for year in _years_to_process(raw_path):
        csv_file = raw_path / year / "all.csv"
        if not csv_file.exists():
            print(f"  [!] No raw file for {year}: {csv_file}, skip.")
            continue
        print(f"Processing Year: {year}")

        df = process_file(str(csv_file))
        if df is not None:
            output_dir = Path(PROCESSED_DIR) / CATEGORY / year
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / "all.csv"

            # 將 src_* 重新命名為 pced_* 以符合 common/schemas.py 的定義
            # 雖然 importer 會再重新計算，但在這裡保持一致性
            rename_map = {
                "src_file": "pced_file",
                "src_row": "pced_row",
                "src_col": "pced_col",
            }
            df = df.rename({k: v for k, v in rename_map.items() if k in df.columns})

            # 型別轉換與 Schema 強制
            schema = get_polars_schema(CATEGORY)
            required_cols = SCHEMA_COLS[CATEGORY]

            # 補齊缺失欄位
            missing_cols = [col for col in required_cols if col not in df.columns]
            if missing_cols:
                df = df.with_columns([pl.lit(None).alias(col) for col in missing_cols])

            cast_exprs = []
            for col, dtype in schema.items():
                if col in df.columns:
                    cast_exprs.append(pl.col(col).cast(dtype, strict=False))
            df = df.with_columns(cast_exprs).select(required_cols)

            df.write_csv(output_path)
            print(f"  [+] Saved {df.height} records to {output_path}")


if __name__ == "__main__":
    main()
