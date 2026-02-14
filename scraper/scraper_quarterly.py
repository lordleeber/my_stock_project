import os
import sys
from pathlib import Path

# Ensure project root is importable when executed as a script.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scraper.quarterly.fetch_quarterly_reports import download_quarterly_report, RAW_DIR
from scraper.quarterly.check_outputs import check_quarterly_outputs


def main():
    year = os.getenv("REPORT_YEAR", "").strip()
    quarter = os.getenv("REPORT_QUARTER", "").strip()
    output_dir = os.getenv("OUTPUT_DIR", "/app/data")

    if not year or not quarter:
        print("Error: REPORT_YEAR and REPORT_QUARTER are required.")
        print("Example: REPORT_YEAR=2025 REPORT_QUARTER=3 python scraper/scraper_quarterly.py")
        return 1

    try:
        year_int = int(year)
        quarter_int = int(quarter)
        if quarter_int not in (1, 2, 3, 4):
            raise ValueError("quarter out of range")
    except ValueError:
        print(f"Error: Invalid REPORT_YEAR/REPORT_QUARTER ({year}/{quarter}).")
        return 1

    ok = download_quarterly_report(year_int, quarter_int, RAW_DIR)
    check_quarterly_outputs(output_dir, str(year_int), str(quarter_int))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
