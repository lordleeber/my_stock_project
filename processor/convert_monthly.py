import os
import re
import datetime
from pathlib import Path
from convert_stock_info import process_stock_info
from convert_stock_tags import process_stock_tags
from monthly.convert_monthly_revenue import process_monthly_revenue


def _log_and_fail(msg: str):
    error_file = Path("/app/error_processor.log")
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with error_file.open("a", encoding="utf-8") as f:
        f.write(f"\n## Processor Runtime Error - {timestamp}\n")
        f.write("**Entry:** convert_monthly.py\n")
        f.write(f"**Message:** {msg}\n")
        f.write("---\n")
    print(msg)
    raise SystemExit(1)


def _validate_required_params():
    start_env = os.getenv("START_DATE")
    end_env = os.getenv("END_DATE")
    if not start_env or not end_env:
        _log_and_fail("Error: START_DATE and END_DATE are both required (YYYYMMDD or YYYYMM).")

    date_re = re.compile(r"^\d{8}$")
    month_re = re.compile(r"^\d{6}$")
    if not ((date_re.match(start_env) or month_re.match(start_env)) and (date_re.match(end_env) or month_re.match(end_env))):
        _log_and_fail(
            f"Error: Invalid date format (START_DATE={start_env}, END_DATE={end_env}). "
            "Expected YYYYMMDD or YYYYMM."
        )

    start_cmp = start_env if len(start_env) == 8 else f"{start_env}01"
    end_cmp = end_env if len(end_env) == 8 else f"{end_env}31"
    if start_cmp > end_cmp:
        _log_and_fail(f"Error: START_DATE must be <= END_DATE (START_DATE={start_env}, END_DATE={end_env}).")


if __name__ == '__main__':
    _validate_required_params()
    process_stock_info()
    process_stock_tags()
    process_monthly_revenue()
