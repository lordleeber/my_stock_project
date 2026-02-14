import datetime
import os
import sys
from pathlib import Path

import pandas_market_calendars as mcal

# Ensure project root is importable when executed as a script.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scraper.daily import fetch_daily_sii
from scraper.daily import fetch_daily_otc
from scraper.daily import fetch_ex_dividend
from scraper.daily import fetch_capital_reduction
from scraper.daily import fetch_par_value_change
from scraper.daily.check_outputs import check_daily_outputs


def get_date_list():
    start_date_env = os.getenv("START_DATE")
    end_date_env = os.getenv("END_DATE")

    # 若未指定日期，預設為今天
    if not start_date_env:
        start_date_env = datetime.datetime.today().strftime("%Y%m%d")
    if not end_date_env:
        end_date_env = datetime.datetime.today().strftime("%Y%m%d")

    try:
        start = datetime.datetime.strptime(start_date_env, "%Y%m%d")
        end = datetime.datetime.strptime(end_date_env, "%Y%m%d")

        print(f"Checking trading days between {start_date_env} and {end_date_env}...")

        twse = mcal.get_calendar("XTAI")
        schedule = twse.schedule(start_date=start, end_date=end)

        valid_dates = schedule.index.strftime("%Y%m%d").tolist()
        return valid_dates

    except ValueError:
        print("Error: Invalid date format. Please use YYYYMMDD.")
        sys.exit(1)
    except Exception as e:
        print(f"Error getting calendar: {e}")
        sys.exit(1)


def main():
    output_dir = os.getenv("OUTPUT_DIR", "data")
    market_type = os.getenv("MARKET_TYPE", "ALL").upper()  # SII, OTC, ALL
    delay = float(os.getenv("FETCH_DELAY", "3.0"))
    end_date_env = os.getenv("END_DATE") or datetime.datetime.today().strftime("%Y%m%d")

    date_list = get_date_list()

    if not date_list:
        print("No valid trading days found in the specified range.")
        return 0

    print(f"Target Dates ({len(date_list)} days): {date_list}")
    print(f"Market Type: {market_type}")
    print(f"Output Directory: {output_dir}")

    if market_type in ["SII", "ALL"]:
        print("\n=== Starting SII Scraper ===")
        fetch_daily_sii.run_scraper(date_list, output_dir, delay)

    if market_type in ["OTC", "ALL"]:
        print("\n=== Starting OTC Scraper ===")
        fetch_daily_otc.run_scraper(date_list, output_dir, delay)

    print("\n=== Starting EX_DIVIDEND Scraper ===")
    fetch_ex_dividend.run_scraper(end_date_env, output_dir)

    print("\n=== Starting CAPITAL_REDUCTION Scraper ===")
    fetch_capital_reduction.run_scraper(end_date_env, output_dir)

    print("\n=== Starting PAR_VALUE_CHANGE Scraper ===")
    fetch_par_value_change.run_scraper(end_date_env, output_dir)

    check_daily_outputs(date_list, output_dir, market_type)

    print("\nAll tasks completed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
