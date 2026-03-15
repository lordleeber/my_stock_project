import os
import sys
from .audit_quarterly_common import is_quarter, list_quarters, check_category

CATEGORY = "balance_sheet"


def run_quality_check(start_q, end_q):
    if not is_quarter(start_q) or not is_quarter(end_q):
        raise ValueError(
            f"Invalid quarter format (START_DATE={start_q}, END_DATE={end_q}). Expected YYYYQX."
        )

    issues = []
    for q in list_quarters(start_q, end_q):
        check_category(CATEGORY, q, issues)
    return issues


def main():
    start_q = os.getenv("START_DATE")
    end_q = os.getenv("END_DATE")

    if not start_q or not end_q:
        print("Error: Please set START_DATE and END_DATE in YYYYQX format.")
        print("Example: START_DATE=2020Q1 END_DATE=2025Q3 python convert_quarterly.py")
        sys.exit(1)

    try:
        issues = run_quality_check(start_q, end_q)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)

    if issues:
        print(f"\n❌ Found {len(issues)} issues:")
        for item in issues[:200]:
            print(f"- {item}")
        if len(issues) > 200:
            print(f"... and {len(issues) - 200} more")
        sys.exit(1)

    print("✅ Balance sheet quality checks passed.")
    sys.exit(0)


if __name__ == "__main__":
    main()
