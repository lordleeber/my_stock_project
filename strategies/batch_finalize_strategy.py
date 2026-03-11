"""
Batch-run strategies/finalize_strategy.py for a range of months.

Usage:
  venv/bin/python3 strategies/batch_finalize_strategy.py
  venv/bin/python3 strategies/batch_finalize_strategy.py --start-year 2023 --start-month 8
  venv/bin/python3 strategies/batch_finalize_strategy.py --skip-existing
  venv/bin/python3 strategies/batch_finalize_strategy.py --dry-run
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

DEFAULT_START = (2021, 8)
DEFAULT_END   = (2025, 10)


def month_iter(start: tuple[int, int], end: tuple[int, int]):
    y, m = start
    while (y, m) <= end:
        yield y, m
        m += 1
        if m > 12:
            m = 1
            y += 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch run finalize_strategy.py for a range of months.")
    parser.add_argument("--start-year",  type=int, default=DEFAULT_START[0])
    parser.add_argument("--start-month", type=int, default=DEFAULT_START[1])
    parser.add_argument("--end-year",    type=int, default=DEFAULT_END[0])
    parser.add_argument("--end-month",   type=int, default=DEFAULT_END[1])
    parser.add_argument("--dry-run",      action="store_true")
    parser.add_argument("--skip-existing", action="store_true",
                        help="Skip months where trade_candidates.csv already exists")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    start = (args.start_year, args.start_month)
    end   = (args.end_year,   args.end_month)

    months = list(month_iter(start, end))
    print(f"Batch finalize_strategy: {start[0]}/{start[1]:02d} → {end[0]}/{end[1]:02d}  ({len(months)} months)")

    python = sys.executable
    script = str(ROOT_DIR / "strategies" / "finalize_strategy.py")

    ok = skipped = failed = 0

    for year, month in months:
        month_s = f"{month:02d}"
        label   = f"{year}/{month_s}"

        if args.skip_existing:
            out_path = ROOT_DIR / "strategies" / "output" / str(year) / month_s / "trade_candidates.csv"
            if out_path.exists():
                print(f"[skip]  {label}  (trade_candidates.csv exists)")
                skipped += 1
                continue

        # Skip if prerequisites are missing.
        strategy_path = ROOT_DIR / "strategies" / "output" / str(year) / month_s / "dataset_strategy.csv"
        pred_path     = ROOT_DIR / "strategies" / "output" / str(year) / month_s / "predictions_published.csv"
        if not strategy_path.exists() or not pred_path.exists():
            print(f"[skip]  {label}  (missing dataset_strategy.csv or predictions_published.csv)")
            skipped += 1
            continue

        cmd = [python, script, "--year", str(year), "--month", month_s]

        if args.dry_run:
            print(f"[dry]   {label}  {' '.join(cmd)}")
            continue

        print(f"\n{'='*60}")
        print(f"[run]   {label}")
        print(f"{'='*60}")
        result = subprocess.run(cmd, cwd=str(ROOT_DIR))
        if result.returncode == 0:
            print(f"[ok]    {label}")
            ok += 1
        else:
            print(f"[FAIL]  {label}  (returncode={result.returncode})")
            failed += 1

    if not args.dry_run:
        print(f"\n{'='*60}")
        print(f"Done: ok={ok}  skipped={skipped}  failed={failed}  total={len(months)}")


if __name__ == "__main__":
    main()
