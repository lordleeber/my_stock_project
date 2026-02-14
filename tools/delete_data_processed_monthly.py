import os
import re
import shutil
import argparse
import sys


def normalize_to_month(target: str) -> str:
    """Accept YYYYMXX, YYYYMM, or YYYYMMDD and normalize to YYYYMXX."""
    t = target.strip().upper()

    if re.fullmatch(r"\d{4}M\d{2}", t):
        month = int(t[5:7])
        if 1 <= month <= 12:
            return t
        raise ValueError(f"Invalid month in '{target}'.")

    if re.fullmatch(r"\d{6}", t):
        month = int(t[4:6])
        if 1 <= month <= 12:
            return f"{t[:4]}M{t[4:6]}"
        raise ValueError(f"Invalid month in '{target}'.")

    if re.fullmatch(r"\d{8}", t):
        month = int(t[4:6])
        if 1 <= month <= 12:
            return f"{t[:4]}M{t[4:6]}"
        raise ValueError(f"Invalid month in '{target}'.")

    raise ValueError(
        f"Invalid format '{target}'. Expected YYYYMXX, YYYYMM, or YYYYMMDD "
        f"(e.g., 2024M01, 202401, 20240101)."
    )


def delete_processed_monthly_data(target: str):
    """
    Delete processed monthly revenue data for one month.

    Current processed path:
      - data/processed/monthly_revenue/YYYY/YYYYMXX
    """
    try:
        month_key = normalize_to_month(target)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)

    year = month_key[:4]
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(base_dir, "data", "processed", "monthly_revenue", year, month_key)

    print(f"--- Checking data/processed/monthly_revenue for month {month_key} ---")

    if os.path.exists(path):
        try:
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
            print(f"Deleted: {path}")
            print(f"\nSuccessfully deleted monthly revenue data for {month_key}.")
        except Exception as e:
            print(f"Failed to delete {path}: {e}")
    else:
        print(f"\nNo monthly revenue data found for {month_key} at: {path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Delete processed monthly revenue data for one month."
    )
    parser.add_argument(
        "month_or_date",
        help="YYYYMXX, YYYYMM, or YYYYMMDD (e.g., 2024M01, 202401, 20240101)",
    )
    args = parser.parse_args()
    delete_processed_monthly_data(args.month_or_date)
