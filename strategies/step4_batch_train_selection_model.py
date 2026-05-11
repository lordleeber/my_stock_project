"""
依 walk-forward 方式，為每個 cutoff 月份各訓練一個選股模型。

對每個 cutoff 月份 C，使用 feature_return_analysis.csv 中 (year, month) <= C 的資料訓練，
並儲存至 models_selection/<year>/<month>/。

用法：
  venv/bin/python3 strategies/batch_train_selection_model.py
  venv/bin/python3 strategies/batch_train_selection_model.py --start-year 2023 --start-month 1
  venv/bin/python3 strategies/batch_train_selection_model.py --start-year 2022 --start-month 6 --end-year 2025 --end-month 8
  venv/bin/python3 strategies/batch_train_selection_model.py --dry-run
  venv/bin/python3 strategies/batch_train_selection_model.py --skip-existing

Cutoff 語意：
  cutoff C 的模型由回測器在 C+1 月交易時使用。
  範例：cutoff=2023-07 → 用於排序 2023-08 的進場候選股。

預設範圍：
  START = (2022, 6)  — 最早 cutoff（約有 10 個月訓練資料）
  END   = (2026, 2)  — 最後一個已知遠期報酬的月份（analyze_feature_returns END=2026-02）
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

DEFAULT_START = (2022, 6)
DEFAULT_END = (2026, 2)


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
        description="Batch train one selection model per cutoff month."
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
        help="Skip cutoff months where selection_model.pkl already exists",
    )
    parser.add_argument("--verbose", action="store_true", help="Print per-month output")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    start = (args.start_year, args.start_month)
    end = (args.end_year, args.end_month)

    months = list(month_iter(start, end))
    print(
        f"Batch train selection model: cutoff {start[0]}/{start[1]:02d} → {end[0]}/{end[1]:02d}  ({len(months)} cutoffs)"
    )

    python = sys.executable
    script = str(ROOT_DIR / "strategies" / "step4_train_selection_model.py")

    ok = skipped = failed = 0

    for year, month in months:
        month_s = f"{month:02d}"
        label = f"{year}/{month_s}"

        if args.skip_existing:
            model_path = (
                ROOT_DIR
                / "models_selection"
                / str(year)
                / month_s
                / "selection_model.pkl"
            )
            if model_path.exists():
                if args.verbose:
                    print(f"[skip]  cutoff={label}  (selection_model.pkl exists)")
                skipped += 1
                continue

        cmd = [
            python,
            script,
            "--cutoff-year",
            str(year),
            "--cutoff-month",
            str(month),
            "--n-bins",
            "10",
            "--reg-alpha",
            "0.05",
            "--reg-lambda",
            "0.1",
        ]

        if args.dry_run:
            print(f"[dry]   cutoff={label}  {' '.join(cmd)}")
            continue

        if args.verbose:
            print(f"\n{'=' * 60}")
            print(f"[run]   cutoff={label}")
            print(f"{'=' * 60}")
        result = subprocess.run(
            cmd,
            cwd=str(ROOT_DIR),
            stdout=None if args.verbose else subprocess.DEVNULL,
            stderr=None if args.verbose else subprocess.DEVNULL,
        )
        if result.returncode == 0:
            if args.verbose:
                print(f"[ok]    cutoff={label}")
            ok += 1
        else:
            print(f"[FAIL]  cutoff={label}  (returncode={result.returncode})")
            failed += 1

    if not args.dry_run:
        print(
            f"\nDone: ok={ok}  skipped={skipped}  failed={failed}  total={len(months)}"
        )


if __name__ == "__main__":
    main()
