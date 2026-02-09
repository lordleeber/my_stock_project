import os
import argparse
import pandas as pd
import logging
from pathlib import Path
import re

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
    dates = []
    for child in base_dir.iterdir():
        if not child.is_dir():
            continue
        name = child.name
        if not name.startswith("date="):
            continue
        date_str = name.split("date=", 1)[1]
        if re.match(r"^\d{8}$", date_str):
            dates.append(date_str)
    return max(dates) if dates else None


def _load_monthly_revenue(path: Path) -> pd.DataFrame:
    if not path.exists():
        logger.warning(f"File not found: {path}")
        return pd.DataFrame()
    return pd.read_csv(path, dtype=str)


def _filter_common_stocks(df: pd.DataFrame) -> pd.Series:
    code_col = None
    if "symbol" in df.columns:
        code_col = "symbol"
    elif "公司代號" in df.columns:
        code_col = "公司代號"
    elif "證券代號" in df.columns:
        code_col = "證券代號"

    if not code_col:
        return pd.Series([], dtype=str)

    codes = df[code_col].astype(str).str.strip()
    mask = codes.str.match(r"^\d{4}$", na=False)
    mask &= ~codes.str.startswith("00")
    return codes[mask]


def generate_stock_list(output_file="active_stocks.txt", date_str: str | None = None, data_dir: str | None = None):
    """
    Generates a list of active common stocks from monthly revenue.
    Source: data/raw/monthly_revenue/date=YYYYMMDD/market.csv
    """

    base_dir = Path(data_dir) if data_dir else Path(os.getenv("OUTPUT_DIR", "data"))
    revenue_dir = base_dir / "raw" / "monthly_revenue"

    if not date_str:
        date_str = _find_latest_date_dir(revenue_dir)
        if not date_str:
            logger.error(f"No valid date directory found in {revenue_dir}")
            return False

    logger.info(f"Using monthly revenue date: {date_str}")

    df = _load_monthly_revenue(revenue_dir / f"date={date_str}" / "market.csv")
    if df is None or df.empty:
        logger.error("No monthly revenue data found. Aborting.")
        return False

    codes = _filter_common_stocks(df)
    all_codes = set(codes.tolist())

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
    parser.add_argument("--date", "-d", help="Target date (YYYYMMDD). Default: latest in data/raw/daily_quotes")
    parser.add_argument("--data-dir", help="Base data dir (default: OUTPUT_DIR or ./data)")
    args = parser.parse_args()

    generate_stock_list(args.output, date_str=args.date, data_dir=args.data_dir)
