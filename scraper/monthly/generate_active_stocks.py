import os
import argparse
import logging
from pathlib import Path
import re
import csv

# Setup basic logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

EXCLUDE_NAME_KEYWORDS = [
    "ETF",
    "ETN",
    "槓桿",
    "反向",
    "權證",
    "特別股",
    "特別",
    "債",
    "存託",
    "TDR",
    "受益",
    "期貨",
    "選擇權",
    "指數",
    "REIT",
    "REITs",
]


def _find_latest_date_dir(base_dir: Path) -> str | None:
    if not base_dir.exists():
        return None
    month_keys = []

    # New format: data/raw/monthly_revenue/YYYY/YYYYMXX/
    for year_dir in base_dir.iterdir():
        if not year_dir.is_dir() or not re.match(r"^\d{4}$", year_dir.name):
            continue
        for month_dir in year_dir.iterdir():
            if not month_dir.is_dir():
                continue
            if re.match(r"^\d{4}M\d{2}$", month_dir.name):
                month_keys.append(month_dir.name)

    # Legacy format fallback: data/raw/monthly_revenue/date=YYYYMMDD/
    if not month_keys:
        for child in base_dir.iterdir():
            if not child.is_dir():
                continue
            name = child.name
            if not name.startswith("date="):
                continue
            date_str = name.split("date=", 1)[1]
            if re.match(r"^\d{8}$", date_str):
                month_keys.append(f"{date_str[:4]}M{date_str[4:6]}")

    return max(month_keys) if month_keys else None


def _load_monthly_revenue(path: Path) -> list[dict]:
    if not path.exists():
        logger.warning(f"File not found: {path}")
        return []
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            return list(reader)
    except Exception as e:
        logger.error(f"Failed to read CSV: {path}, error: {e}")
        return []


def _filter_common_stocks(rows: list[dict]) -> list[str]:
    if not rows:
        return []

    sample_keys = rows[0].keys()
    code_col = None
    if "symbol" in sample_keys:
        code_col = "symbol"
    elif "公司代號" in sample_keys:
        code_col = "公司代號"
    elif "證券代號" in sample_keys:
        code_col = "證券代號"

    if not code_col:
        return []

    codes = []
    for row in rows:
        code = str(row.get(code_col, "")).strip()
        if re.match(r"^\d{4}$", code) and not code.startswith("00"):
            codes.append(code)
    return codes


def _normalize_month_key(date_str: str) -> str | None:
    """Accept YYYYMXX / YYYYMM / YYYYMMDD and normalize to YYYYMXX."""
    s = date_str.strip().upper()
    if re.match(r"^\d{4}M\d{2}$", s):
        return s
    if re.match(r"^\d{6}$", s):
        return f"{s[:4]}M{s[4:6]}"
    if re.match(r"^\d{8}$", s):
        return f"{s[:4]}M{s[4:6]}"
    return None


def generate_stock_list(output_file="active_stocks.txt", date_str: str | None = None, data_dir: str | None = None):
    """
    Generates a list of active common stocks from monthly revenue.
    Source (new): data/raw/monthly_revenue/YYYY/YYYYMXX/market.csv
    """

    base_dir = Path(data_dir) if data_dir else Path(os.getenv("OUTPUT_DIR", "data"))
    revenue_dir = base_dir / "raw" / "monthly_revenue"

    month_key = _normalize_month_key(date_str) if date_str else None
    if not month_key:
        month_key = _find_latest_date_dir(revenue_dir)
        if not month_key:
            logger.error(f"No valid date directory found in {revenue_dir}")
            return False

    logger.info(f"Using monthly revenue month: {month_key}")
    year = month_key[:4]
    new_path = revenue_dir / year / month_key / "market.csv"
    legacy_path = revenue_dir / f"date={year}{month_key[5:7]}01" / "market.csv"
    source_path = new_path if new_path.exists() else legacy_path

    rows = _load_monthly_revenue(source_path)
    if not rows:
        logger.error("No monthly revenue data found. Aborting.")
        return False

    codes = _filter_common_stocks(rows)
    all_codes = set(codes)

    if not all_codes:
        logger.error("No valid stock codes found. Aborting.")
        return False

    # Sort and Save
    sorted_codes = sorted(list(all_codes))
    
    with open(output_file, 'w', encoding='utf-8') as f:
        for code in sorted_codes:
            f.write(f"{code}\n")
            
    logger.info(f"Successfully saved {len(sorted_codes)} active stocks to {output_file}")
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate active stock list from monthly revenue")
    parser.add_argument("--output", "-o", default="active_stocks.txt", help="Output file path")
    parser.add_argument("--date", "-d", help="Target month/date (YYYYMXX, YYYYMM, or YYYYMMDD). Default: latest monthly_revenue")
    parser.add_argument("--data-dir", help="Base data dir (default: OUTPUT_DIR or ./data)")
    args = parser.parse_args()

    generate_stock_list(args.output, date_str=args.date, data_dir=args.data_dir)
