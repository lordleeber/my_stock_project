import os
import re
import sys
from quarterly.convert_quarterly_reports import main as convert_quarterly_reports_main
from quarterly.convert_income_statements import main as convert_income_statements_main
from quarterly.convert_balance_sheet import main as convert_balance_sheet_main
from quarterly.convert_cash_flow import main as convert_cash_flow_main


def _parse_statement_categories():
    raw = os.getenv("QUARTERLY_STATEMENT_CATEGORIES", "income_statement,balance_sheet,cash_flow")
    categories = [c.strip() for c in raw.split(",") if c.strip()]
    valid = {"income_statement", "balance_sheet", "cash_flow"}
    invalid = [c for c in categories if c not in valid]
    if invalid:
        raise ValueError(f"Invalid QUARTERLY_STATEMENT_CATEGORIES: {invalid}")
    return categories


def _run_statement_category(category):
    if category == "income_statement":
        convert_income_statements_main()
    elif category == "balance_sheet":
        convert_balance_sheet_main()
    elif category == "cash_flow":
        convert_cash_flow_main()
    else:
        raise ValueError(f"Invalid statement category: {category}")


def main():
    start_env = os.getenv("START_DATE")
    end_env = os.getenv("END_DATE")
    if not start_env or not end_env:
        print("Error: START_DATE and END_DATE are both required (YYYYQX).")
        print("Example: START_DATE=2024Q1 END_DATE=2024Q1 python convert_quarterly.py")
        sys.exit(1)
    if not (re.match(r"^\d{4}Q[1-4]$", start_env) and re.match(r"^\d{4}Q[1-4]$", end_env)):
        print(f"Error: Invalid quarter format (START_DATE={start_env}, END_DATE={end_env}). Expected YYYYQX.")
        sys.exit(1)
    if start_env > end_env:
        print(f"Error: START_DATE must be <= END_DATE (START_DATE={start_env}, END_DATE={end_env}).")
        sys.exit(1)

    # QUARTERLY_TASK: reports | statements | all
    task = os.getenv("QUARTERLY_TASK", "all").strip().lower()
    if task not in {"reports", "statements", "all"}:
        raise ValueError("QUARTERLY_TASK must be one of: reports, statements, all")

    if task in {"reports", "all"}:
        convert_quarterly_reports_main()

    if task in {"statements", "all"}:
        for category in _parse_statement_categories():
            _run_statement_category(category)


if __name__ == '__main__':
    main()
