"""
批次執行 train_eps/predict_and_publish.py，涵蓋指定月份範圍。

用法：
  venv/bin/python3 train_eps/batch_predict_and_publish.py
  venv/bin/python3 train_eps/batch_predict_and_publish.py --start-year 2023 --start-month 8
  venv/bin/python3 train_eps/batch_predict_and_publish.py --skip-existing
  venv/bin/python3 train_eps/batch_predict_and_publish.py --dry-run
"""

from __future__ import annotations

import argparse
import re
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
        description="Batch run predict_and_publish.py for a range of months."
    )
    parser.add_argument("--start-year", type=int, default=DEFAULT_START[0])
    parser.add_argument("--start-month", type=int, default=DEFAULT_START[1])
    parser.add_argument("--end-year", type=int, default=DEFAULT_END[0])
    parser.add_argument("--end-month", type=int, default=DEFAULT_END[1])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip months where predictions_results.csv already exists",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    start = (args.start_year, args.start_month)
    end = (args.end_year, args.end_month)

    months = list(month_iter(start, end))
    print(
        f"Batch predict_and_publish: {start[0]}/{start[1]:02d} → {end[0]}/{end[1]:02d}  ({len(months)} months)"
    )

    python = sys.executable
    script = str(ROOT_DIR / "train_eps" / "step4_predict_and_publish.py")

    ok = skipped = failed = 0

    for year, month in months:
        month_s = f"{month:02d}"
        label = f"{year}/{month_s}"

        if args.skip_existing:
            out_path = (
                ROOT_DIR
                / "models_eps"
                / str(year)
                / month_s
                / "predictions_results.csv"
            )
            if out_path.exists():
                print(f"[skip]  {label}  (predictions_results.csv exists)")
                skipped += 1
                continue

        # 前置檔案缺失則跳過。
        input_path = (
            ROOT_DIR
            / "train_eps"
            / "output"
            / str(year)
            / month_s
            / "dataset_evaluate.csv"
        )
        if not input_path.exists():
            print(
                f"[skip]  {label}  (missing train_eps/output/{year}/{month_s}/dataset_evaluate.csv)"
            )
            skipped += 1
            continue
        models_dir = ROOT_DIR / "models_eps" / str(year) / month_s
        pkl_pattern = re.compile(r"^\d{14}_\d+\.\d+\.pkl$")
        has_model = any(pkl_pattern.match(p.name) for p in models_dir.glob("*.pkl"))
        if not has_model:
            print(f"[skip]  {label}  (no timestamped model pkl in models_eps/{year}/{month_s}/)")
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
