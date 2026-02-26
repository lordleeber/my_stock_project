import os
import re
import sys
import datetime
import traceback
from pathlib import Path
from quarterly.convert_quarterly_reports import main as convert_quarterly_reports_main
from quarterly.convert_xbrl import main as convert_xbrl_main
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


def _log_and_fail(msg: str, exc: Exception | None = None):
    error_file = Path("/app/error_processor.log")
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with error_file.open("a", encoding="utf-8") as f:
        f.write(f"\n## Processor Runtime Error - {timestamp}\n")
        f.write("**Entry:** convert_quarterly.py\n")
        f.write(f"**Message:** {msg}\n")
        if exc is not None:
            f.write(f"**Traceback:**\n```python\n{traceback.format_exc()}\n```\n")
        f.write("---\n")
    print(msg)
    raise SystemExit(1)


def main():
    start_env = os.getenv("START_DATE")
    end_env = os.getenv("END_DATE")
    task = os.getenv("QUARTERLY_TASK")

    if not start_env or not end_env or not task:
        _log_and_fail(
            "Error: START_DATE, END_DATE, and QUARTERLY_TASK are all required "
            "(START_DATE/END_DATE format: YYYYQX; QUARTERLY_TASK: reports|detail_xbrl|statements|all)."
        )
    if not (re.match(r"^\d{4}Q[1-4]$", start_env) and re.match(r"^\d{4}Q[1-4]$", end_env)):
        _log_and_fail(
            f"Error: Invalid quarter format (START_DATE={start_env}, END_DATE={end_env}). Expected YYYYQX."
        )
    if start_env > end_env:
        _log_and_fail(
            f"Error: START_DATE must be <= END_DATE (START_DATE={start_env}, END_DATE={end_env})."
        )

    # QUARTERLY_TASK: reports | detail_xbrl | statements | all
    task = task.strip().lower()
    if task not in {"reports", "detail_xbrl", "statements", "all"}:
        _log_and_fail("Error: QUARTERLY_TASK must be one of: reports, detail_xbrl, statements, all")

    if task in {"reports", "all"}:
        convert_quarterly_reports_main()

    if task == "detail_xbrl":
        convert_xbrl_main()

    if task in {"statements", "all"}:
        for category in _parse_statement_categories():
            _run_statement_category(category)


if __name__ == '__main__':
    main()
