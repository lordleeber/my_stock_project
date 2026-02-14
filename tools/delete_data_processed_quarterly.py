import os
import re
import shutil
import argparse
import sys


def normalize_to_quarter(target: str) -> str:
    """Accept YYYYQX or YYYYMMDD and normalize to YYYYQX."""
    target = target.strip().upper()

    if re.fullmatch(r"\d{4}Q[1-4]", target):
        return target

    if re.fullmatch(r"\d{8}", target):
        month = int(target[4:6])
        if month < 1 or month > 12:
            raise ValueError(f"Invalid month in date '{target}'.")
        quarter = (month - 1) // 3 + 1
        return f"{target[:4]}Q{quarter}"

    raise ValueError(
        f"Invalid format '{target}'. Expected YYYYQX or YYYYMMDD "
        f"(e.g., 2025Q3 or 20250930)."
    )


def delete_processed_quarterly_data(target: str):
    """
    Delete processed quarterly data for one quarter.

    Current processed paths:
      - data/processed/quarterly_reports/YYYY/YYYYQX
      - data/processed/income_statement/YYYY/YYYYQX
      - data/processed/balance_sheet/YYYY/YYYYQX
      - data/processed/cash_flow/YYYY/YYYYQX
    """
    try:
        quarter = normalize_to_quarter(target)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)

    year = quarter[:4]
    quarterly_categories = [
        "quarterly_reports",
        "income_statement",
        "balance_sheet",
        "cash_flow",
    ]

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    deleted_count = 0

    print(f"--- Checking data/processed for quarter {quarter} ---")
    for cat in quarterly_categories:
        path = os.path.join(base_dir, "data", "processed", cat, year, quarter)
        if os.path.exists(path):
            try:
                if os.path.isdir(path):
                    shutil.rmtree(path)
                else:
                    os.remove(path)
                print(f"Deleted: {path}")
                deleted_count += 1
            except Exception as e:
                print(f"Failed to delete {path}: {e}")

    if deleted_count == 0:
        print(f"\nNo quarterly data found for {quarter}.")
    else:
        print(f"\nTotal quarterly items deleted: {deleted_count}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Delete processed quarterly data for one quarter."
    )
    parser.add_argument(
        "date_or_quarter",
        help="Quarter (YYYYQX) or date (YYYYMMDD), e.g. 2025Q3 or 20250930",
    )
    args = parser.parse_args()
    delete_processed_quarterly_data(args.date_or_quarter)
