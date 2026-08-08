import os
import sys
from pathlib import Path

# Ensure project root is importable when executed as a script.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scraper.weekly import fetch_tdcc
from scraper.weekly.check_outputs import (
    check_weekly_outputs,
    fail_if_problems,
    normalize_tdcc_date,
)


def main():
    output_dir = "/app/data/raw/shareholding"
    output_root = "/app/data"

    # Reuse existing fetch_tdcc CLI implementation with non-interactive flags.
    sys.argv = [
        "fetch_tdcc.py",
        "--no-prompt",
        "--no-verify",
        "--output-dir",
        output_dir,
    ]
    rc = fetch_tdcc.main()
    if rc != 0:
        return rc

    # 驗證與失敗回報都走 check_outputs 的共用函式，兩個 entrypoint 才不會漂開
    # （之前這裡少了 TDCC_DATE 的格式驗證，同一個輸入在兩邊行為不同）。
    tdcc_date = normalize_tdcc_date(os.getenv("TDCC_DATE"))
    return fail_if_problems(check_weekly_outputs(output_root, tdcc_date))


if __name__ == "__main__":
    sys.exit(main())
