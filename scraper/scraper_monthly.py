import os
import sys
from datetime import datetime
from pathlib import Path

# Ensure project root is importable when executed as a script.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scraper.monthly.fetch_monthly_revenue import process_and_save
from scraper.monthly.fetch_stock_info import main as fetch_stock_info
from scraper.monthly.check_outputs import check_monthly_outputs


def main():
    year = os.getenv("REVENUE_YEAR", "").strip()
    month = os.getenv("REVENUE_MONTH", "").strip()
    output_dir = os.getenv("OUTPUT_DIR", "/app/data")

    if not year or not month:
        print("Error: REVENUE_YEAR and REVENUE_MONTH are required.")
        print(
            "Example: REVENUE_YEAR=2026 REVENUE_MONTH=1 python scraper/scraper_monthly.py"
        )
        return 1

    try:
        year_int = int(year)
        month_int = int(month)
        if month_int < 1 or month_int > 12:
            raise ValueError("month out of range")
    except ValueError:
        print(f"Error: Invalid REVENUE_YEAR/REVENUE_MONTH ({year}/{month}).")
        return 1

    process_and_save(year_int, month_int)

    today = datetime.now().day
    if today == 1:
        print("[stock_info] day=1, refreshing stock_info from TWSE ISIN...")
        try:
            fetch_stock_info()
        except Exception as e:
            print(f"[stock_info] WARN: refresh failed (continuing): {e}")
    else:
        print(f"[stock_info] day={today}, skip (only refreshes on day 1)")

    check_monthly_outputs(output_dir, str(year_int), str(month_int))
    return 0


if __name__ == "__main__":
    sys.exit(main())
