#!/usr/bin/env python3
"""把 fetch_tdcc_history.py 的 per-stock 檔合併成 TDCC OpenData 的 bulk 格式。

TDCC OpenData（`getOD.ashx?id=1-5`，即 fetch_tdcc.py 打的那支）只給最新一週，
沒有歷史。要回補漏掉的某一週，只能走 fetch_tdcc_history.py 逐檔爬歷史查詢頁，
但它的輸出是 per-stock 格式，餵不進 processor/weekly/convert_shareholding.py
（那支只認 bulk 的 `TDCC_OD_1-5_YYYYMMDD.csv`）。這支就是中間那一段。

回補一週的完整路徑：

    # 1. 逐檔爬（約 1.4 秒/檔；--file 用 repo 根目錄的 active_stocks.txt）
    docker compose run --rm \\
      -v "$PWD/active_stocks.txt:/app/active_stocks.txt:ro" \\
      --entrypoint "" scraper-weekly \\
      python scraper/weekly/fetch_tdcc_history.py \\
        --date YYYYMMDD --file /app/active_stocks.txt --no-verify

    # 2. 合併成 bulk（純 stdlib，直接在 host 跑）
    venv/bin/python3 scraper/weekly/merge_shareholding.py --date YYYYMMDD

    # 3. 之後接回常規 pipeline
    docker compose run --rm -e START_DATE=YYYYMMDD -e END_DATE=YYYYMMDD \\
      processor python convert_weekly.py
    docker compose run --rm -e START_DATE=YYYYMMDD -e END_DATE=YYYYMMDD \\
      importer python import_weekly.py
    docker compose run --rm calculator \\
      python calculate_shareholding_concentration.py --force-full

輸入: data/raw/shareholding_div/date=YYYYMMDD/<symbol>.csv
      欄位: 序,持股分級,人數,股數,占集保庫存數比例(%)
輸出: data/raw/shareholding/YYYY/TDCC_OD_1-5_YYYYMMDD.csv
      欄位: 資料日期,證券代號,持股分級,人數,股數,占集保庫存數比例%

用法:
    venv/bin/python3 scraper/weekly/merge_shareholding.py --date 20260709
    venv/bin/python3 scraper/weekly/merge_shareholding.py --all

環境變數:
    RAW_DIR: raw 資料根目錄（預設 <repo>/data/raw）
"""

import os
import sys
import argparse
import csv
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[1]
RAW_DIR = os.getenv("RAW_DIR", str(PROJECT_ROOT / "data" / "raw"))
INPUT_DIR = f"{RAW_DIR}/shareholding_div"
OUTPUT_DIR = f"{RAW_DIR}/shareholding"

# 歷史查詢頁的分級是文字，OpenData bulk 是數字 level。這 15 個字串即
# processor/weekly/convert_shareholding.py 的 LEVEL_NAME_MAP 的 1~15。
# 頁面第 16 列是「合　計」（全形空格），不在這裡 → 自動被丟掉，正好符合
# audit_shareholding.py「每個 symbol 剛好 15 列」的約束。OpenData 才有的
# level 16（400萬以上）/17（總計）在歷史查詢頁不存在，convert 端本來也會
# 用 `level <= 15` 濾掉，兩邊一致。
LEVEL_MAPPING = {
    "1-999": 1,
    "1,000-5,000": 2,
    "5,001-10,000": 3,
    "10,001-15,000": 4,
    "15,001-20,000": 5,
    "20,001-30,000": 6,
    "30,001-40,000": 7,
    "40,001-50,000": 8,
    "50,001-100,000": 9,
    "100,001-200,000": 10,
    "200,001-400,000": 11,
    "400,001-600,000": 12,
    "600,001-800,000": 13,
    "800,001-1,000,000": 14,
    "1,000,001以上": 15,
}

EXPECTED_LEVELS = 15

OUTPUT_FIELDS = [
    "資料日期",
    "證券代號",
    "持股分級",
    "人數",
    "股數",
    "占集保庫存數比例%",
]


def get_level_code(level_text):
    """把持股分級文字映成 1~15 的 level code；認不得的（含「合　計」）回 None。"""
    if not level_text:
        return None
    # 全形空格也要拿掉：頁面的合計列寫成「合　計」，而分級文字本身偶有半形空格。
    normalized = level_text.strip().replace(" ", "").replace("　", "")
    return LEVEL_MAPPING.get(normalized)


def _read_stock(file_path, symbol, date_str):
    """讀單一檔的 per-stock CSV，回傳 bulk 格式的 row list（不足 15 級則回 []）。"""
    rows = []
    with open(file_path, "r", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            level_code = get_level_code(row.get("持股分級", ""))
            if level_code is None:
                continue
            holders = (row.get("人數") or "").strip().replace(",", "")
            shares = (row.get("股數") or "").strip().replace(",", "")
            percentage = (row.get("占集保庫存數比例(%)") or "").strip()
            if not holders or not shares:
                continue
            rows.append(
                {
                    "資料日期": date_str,
                    "證券代號": symbol,
                    "持股分級": level_code,
                    "人數": holders,
                    "股數": shares,
                    "占集保庫存數比例%": percentage,
                }
            )
    # convert 端的 audit 要求每個 symbol 剛好 15 列，缺一列就會讓**整個日期**
    # 硬失敗。與其在 convert 才炸，不如在這裡就把不完整的 symbol 拿掉並列出來：
    # 回補本來就是部分快照，少幾檔可以接受，整批卡住不行。
    return rows if len(rows) == EXPECTED_LEVELS else []


def merge_date(date_str):
    """把某一天的 per-stock 檔合併成一份 bulk CSV。"""
    input_date_dir = Path(INPUT_DIR) / f"date={date_str}"

    if not input_date_dir.is_dir():
        print(f"❌ Input directory not found: {input_date_dir}")
        return False

    csv_files = sorted(p for p in input_date_dir.iterdir() if p.suffix == ".csv")
    if not csv_files:
        print(f"⚠️  No CSV files found in {input_date_dir}")
        return False

    print(f"Processing {date_str}: {len(csv_files)} stocks...")

    all_rows = []
    processed_stocks = 0
    dropped = []

    for file_path in csv_files:
        symbol = file_path.stem
        try:
            rows = _read_stock(file_path, symbol, date_str)
        except Exception as e:
            print(f"⚠️  Error processing {symbol}: {e}")
            dropped.append(symbol)
            continue

        if not rows:
            dropped.append(symbol)
            continue

        all_rows.extend(rows)
        processed_stocks += 1

    if not all_rows:
        print(f"❌ No valid data to write for {date_str}")
        return False

    year_dir = Path(OUTPUT_DIR) / date_str[:4]
    year_dir.mkdir(parents=True, exist_ok=True)
    output_file = year_dir / f"TDCC_OD_1-5_{date_str}.csv"

    with open(output_file, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"✓ Created {output_file}")
    print(f"  Processed: {processed_stocks} stocks, {len(all_rows)} rows")
    if dropped:
        print(
            f"  ⚠️  Dropped {len(dropped)} stocks without exactly {EXPECTED_LEVELS} "
            f"levels: {', '.join(dropped[:10])}" + (" ..." if len(dropped) > 10 else "")
        )
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Merge per-stock TDCC history files into the OpenData bulk format"
    )
    parser.add_argument("--date", help="Specific date to merge (YYYYMMDD)")
    parser.add_argument(
        "--all", action="store_true", help="Merge all dates found in shareholding_div"
    )

    args = parser.parse_args()

    if args.all:
        if not os.path.isdir(INPUT_DIR):
            print(f"❌ Input directory not found: {INPUT_DIR}")
            return 1

        date_dirs = sorted(
            d.name for d in Path(INPUT_DIR).iterdir() if d.name.startswith("date=")
        )
        if not date_dirs:
            print(f"⚠️  No date directories found in {INPUT_DIR}")
            return 1

        print(f"Found {len(date_dirs)} dates to process")
        success_count = sum(
            1 for d in date_dirs if merge_date(d.replace("date=", "", 1))
        )
        print(f"\n✅ Completed: {success_count}/{len(date_dirs)} dates processed")
        return 0 if success_count == len(date_dirs) else 1

    if args.date:
        return 0 if merge_date(args.date) else 1

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
