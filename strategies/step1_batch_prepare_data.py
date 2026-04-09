"""
批次執行 strategies/prepare_data.py，涵蓋指定月份範圍。

用法：
  venv/bin/python3 strategies/step1_batch_prepare_data.py
  venv/bin/python3 strategies/step1_batch_prepare_data.py --start-year 2023 --start-month 8
  venv/bin/python3 strategies/step1_batch_prepare_data.py --start-year 2021 --start-month 8 --end-year 2025 --end-month 10
  venv/bin/python3 strategies/step1_batch_prepare_data.py --dry-run
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

DEFAULT_START = (2021, 8)
DEFAULT_END = (2025, 10)


def month_iter(start: tuple[int, int], end: tuple[int, int]):
    y, m = start
    while (y, m) <= end:
        yield y, m
        m += 1
        if m > 12:
            m = 1
            y += 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Batch run prepare_data.py for a range of months."
    )
    parser.add_argument("--start-year", type=int, default=DEFAULT_START[0])
    parser.add_argument("--start-month", type=int, default=DEFAULT_START[1])
    parser.add_argument("--end-year", type=int, default=DEFAULT_END[0])
    parser.add_argument("--end-month", type=int, default=DEFAULT_END[1])
    parser.add_argument(
        "--dry-run", action="store_true", help="Print commands without executing"
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip months where dataset_strategy.csv already exists",
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Print per-month output"
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    start = (args.start_year, args.start_month)
    end = (args.end_year, args.end_month)

    months = list(month_iter(start, end))
    print(
        f"Batch prepare_data: {start[0]}/{start[1]:02d} → {end[0]}/{end[1]:02d}  ({len(months)} months)"
    )

    python = sys.executable
    script = str(ROOT_DIR / "strategies" / "step1_prepare_data.py")

    ok = skipped = failed = 0

    for year, month in months:
        month_s = f"{month:02d}"
        label = f"{year}/{month_s}"

        if args.skip_existing:
            out_path = (
                ROOT_DIR
                / "strategies"
                / "output"
                / str(year)
                / month_s
                / "dataset_strategy.csv"
            )
            if out_path.exists():
                if args.verbose:
                    print(f"[skip]  {label}  (dataset_strategy.csv exists)")
                skipped += 1
                continue

        cmd = [python, script, "--year", str(year), "--month", month_s]

        if args.dry_run:
            print(f"[dry]   {label}  {' '.join(cmd)}")
            continue

        if args.verbose:
            print(f"\n{'=' * 60}")
            print(f"[run]   {label}")
            print(f"{'=' * 60}")
        result = subprocess.run(
            cmd, cwd=str(ROOT_DIR),
            stdout=None if args.verbose else subprocess.DEVNULL,
            stderr=None if args.verbose else subprocess.DEVNULL,
        )
        if result.returncode == 0:
            if args.verbose:
                print(f"[ok]    {label}")
            ok += 1
        else:
            print(f"[FAIL]  {label}  (returncode={result.returncode})")
            failed += 1

    if not args.dry_run:
        print(f"\nDone: ok={ok}  skipped={skipped}  failed={failed}  total={len(months)}")


if __name__ == "__main__":
    main()
