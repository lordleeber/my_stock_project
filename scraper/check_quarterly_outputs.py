import os
import sys
from pathlib import Path

# Backward-compatible wrapper:
CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from quarterly.check_outputs import check_quarterly_outputs


def main():
    output_dir = os.getenv("OUTPUT_DIR", "/app/data")
    year = os.getenv("REPORT_YEAR", "").strip()
    quarter = os.getenv("REPORT_QUARTER", "").strip()

    if not year or not quarter:
        print(
            "[INFO] REPORT_YEAR or REPORT_QUARTER not set. Skip quarterly output check."
        )
        return

    check_quarterly_outputs(output_dir, year, quarter)


if __name__ == "__main__":
    main()
