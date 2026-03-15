"""
Batch-run train_eps/evaluate.py for a range of months.

Usage:
  venv/bin/python3 train_eps/batch_evaluate.py
  venv/bin/python3 train_eps/batch_evaluate.py --start-year 2023 --start-month 8
  venv/bin/python3 train_eps/batch_evaluate.py --skip-existing
  venv/bin/python3 train_eps/batch_evaluate.py --dry-run
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent


def available_months() -> list[tuple[int, int]]:
    """Return sorted (year, month) tuples where dataset_evaluate.csv exists."""
    output_dir = ROOT_DIR / "train_eps" / "output"
    months = []
    for csv in output_dir.glob("*/*/dataset_evaluate.csv"):
        try:
            year = int(csv.parent.parent.name)
            month = int(csv.parent.name)
            months.append((year, month))
        except ValueError:
            continue
    return sorted(months)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Batch run evaluate.py for a range of months."
    )
    parser.add_argument("--start-year", type=int, default=None)
    parser.add_argument("--start-month", type=int, default=None)
    parser.add_argument("--end-year", type=int, default=None)
    parser.add_argument("--end-month", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip months where evaluate_by_fold.json already exists",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    all_months = available_months()
    if not all_months:
        print("No dataset_evaluate.csv found under train_eps/output/")
        return

    start = (args.start_year or all_months[0][0], args.start_month or all_months[0][1])
    end = (args.end_year or all_months[-1][0], args.end_month or all_months[-1][1])

    months = [(y, m) for y, m in all_months if start <= (y, m) <= end]
    print(
        f"Batch evaluate: {start[0]}/{start[1]:02d} → {end[0]}/{end[1]:02d}  ({len(months)} months)"
    )

    python = sys.executable
    script = str(ROOT_DIR / "train_eps" / "evaluate.py")

    ok = skipped = failed = 0

    for year, month in months:
        month_s = f"{month:02d}"
        label = f"{year}/{month_s}"

        if args.skip_existing:
            out_path = (
                ROOT_DIR / "models_eps" / str(year) / month_s / "evaluate_by_fold.json"
            )
            if out_path.exists():
                print(f"[skip]  {label}  (evaluate_by_fold.json exists)")
                skipped += 1
                continue

        cmd = [python, script, "--year", str(year), "--month", month_s]

        if args.dry_run:
            print(f"[dry]   {label}  {' '.join(cmd)}")
            continue

        print(f"\n{'=' * 60}")
        print(f"[run]   {label}")
        print(f"{'=' * 60}")
        result = subprocess.run(cmd, cwd=str(ROOT_DIR))
        if result.returncode == 0:
            print(f"[ok]    {label}")
            ok += 1
        else:
            print(f"[FAIL]  {label}  (returncode={result.returncode})")
            failed += 1

    if not args.dry_run:
        print(f"\n{'=' * 60}")
        print(f"Done: ok={ok}  skipped={skipped}  failed={failed}  total={len(months)}")


if __name__ == "__main__":
    main()
