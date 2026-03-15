import os
import sys
from pathlib import Path

# Backward-compatible wrapper:
CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from monthly.check_outputs import check_monthly_outputs


def main():
    output_dir = os.getenv("OUTPUT_DIR", "/app/data")
    year = os.getenv("REVENUE_YEAR", "").strip()
    month = os.getenv("REVENUE_MONTH", "").strip()

    if not year or not month:
        print(
            "[INFO] REVENUE_YEAR or REVENUE_MONTH not set. Skip monthly output check."
        )
        return

    try:
        check_monthly_outputs(output_dir, year, month)
    except ValueError:
        print(f"[WARN] Invalid REVENUE_MONTH: {month}. Skip monthly output check.")


if __name__ == "__main__":
    main()
