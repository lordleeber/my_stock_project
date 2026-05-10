"""Quarterly XBRL processor entry point.

跑兩段：
1. quarterly.convert_xbrl.main()                — 產出 statement-level XBRL
   (balance_sheet_xbrl / income_statement_xbrl / cash_flow_xbrl + xbrl_codebook)
2. quarterly.convert_quarterly_reports_xbrl.main() — 產出 quarterly_reports_xbrl 寬表

Env vars:
  START_DATE, END_DATE — 必填，YYYYQX，且須相等（單季處理）
"""

import os
import sys

from quarterly.convert_xbrl import main as convert_xbrl_main
from quarterly.convert_quarterly_reports_xbrl import main as convert_qr_xbrl_main


def main():
    start = os.getenv("START_DATE", "").strip()
    end = os.getenv("END_DATE", "").strip()

    if not start or not end:
        print("Error: START_DATE and END_DATE are required (YYYYQX).")
        return 1
    if start != end:
        print(
            f"Error: convert_quarterly_xbrl currently supports single-quarter only "
            f"(START_DATE={start} END_DATE={end})."
        )
        return 1

    print(f"[1/2] convert_xbrl (statement-level) for {start}")
    convert_xbrl_main()

    print(f"[2/2] convert_quarterly_reports_xbrl for {start}")
    sys.argv = ["convert_quarterly_reports_xbrl", "--quarter", start]
    rc = convert_qr_xbrl_main()
    if rc != 0:
        return rc

    print(f"convert_quarterly_xbrl done for {start}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
