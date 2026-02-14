import os
import sys
from pathlib import Path

# Backward-compatible wrapper:
CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from daily.check_outputs import check_daily_outputs


if __name__ == "__main__":
    output_dir = os.getenv("OUTPUT_DIR", "/app/data")
    market_type = os.getenv("MARKET_TYPE", "ALL").upper()
    dates = os.getenv("DATE_LIST", "")
    date_list = [d for d in dates.split(",") if d]

    if not date_list:
        print("[INFO] DATE_LIST is empty. Skip daily output check.")
    else:
        check_daily_outputs(date_list, output_dir, market_type)
