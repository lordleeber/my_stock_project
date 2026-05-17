"""
依 walk-forward 方式，為每個 train_through cohort 各訓練一個選股模型。

對每個 train_through cohort T，使用 feature_return_analysis.csv 中 (year, month) <= T 的資料訓練，
並儲存至 models_selection/<train_through_year>/<train_through_month>/。

術語見 strategies/CLAUDE.md § Date Convention：
  train_through = 訓練資料 cohort 上界
  train_through_date = train_through cohort 的 cutoff_date（YYYY-MM-DD）

⚠ 不要叫成 model 的 cutoff_date — cutoff_date 是 target 的屬性，跟 train_through_date
   差一個 cycle。

用法：
  venv/bin/python3 strategies/step4_batch_train_selection_model.py
  venv/bin/python3 strategies/step4_batch_train_selection_model.py --start-year 2023 --start-month 1
  venv/bin/python3 strategies/step4_batch_train_selection_model.py --start-year 2022 --start-month 6 --end-year 2025 --end-month 8
  venv/bin/python3 strategies/step4_batch_train_selection_model.py --dry-run
  venv/bin/python3 strategies/step4_batch_train_selection_model.py --skip-existing

Walk-forward 語意：
  train_through=T 的模型由 step5 在 target cohort T+1 評分時使用。
  範例：train_through=2023/07（train_through_date 2023-07-10）→ 用於排序 2023/08 的候選股。

預設範圍：
  START = (2022, 6)  — 最早 train_through（約有 10 個月訓練資料）
  END   = (2026, 4)  — 最後一個 fwd_return 已可算的 cohort（analyze_feature_returns 涵蓋到 2026/04）
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

DEFAULT_START = (2022, 6)
DEFAULT_END = (2026, 4)


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
        description="Batch train one selection model per train_through cohort."
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
        help="Skip train_through cohorts where selection_model.pkl already exists",
    )
    parser.add_argument("--verbose", action="store_true", help="Print per-month output")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    start = (args.start_year, args.start_month)
    end = (args.end_year, args.end_month)

    months = list(month_iter(start, end))
    print(
        f"Batch train selection model: train_through {start[0]}/{start[1]:02d} → {end[0]}/{end[1]:02d}  ({len(months)} cohorts)"
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
                    print(
                        f"[skip]  train_through={label}  (selection_model.pkl exists)"
                    )
                skipped += 1
                continue

        cmd = [
            python,
            script,
            "--train-through-year",
            str(year),
            "--train-through-month",
            str(month),
            "--n-bins",
            "10",
            "--reg-alpha",
            "0.05",
            "--reg-lambda",
            "0.1",
        ]

        if args.dry_run:
            print(f"[dry]   train_through={label}  {' '.join(cmd)}")
            continue

        if args.verbose:
            print(f"\n{'=' * 60}")
            print(f"[run]   train_through={label}")
            print(f"{'=' * 60}")
        result = subprocess.run(
            cmd,
            cwd=str(ROOT_DIR),
            stdout=None if args.verbose else subprocess.DEVNULL,
            stderr=None if args.verbose else subprocess.DEVNULL,
        )
        if result.returncode == 0:
            if args.verbose:
                print(f"[ok]    train_through={label}")
            ok += 1
        else:
            print(f"[FAIL]  train_through={label}  (returncode={result.returncode})")
            failed += 1

    if not args.dry_run:
        print(
            f"\nDone: ok={ok}  skipped={skipped}  failed={failed}  total={len(months)}"
        )


if __name__ == "__main__":
    main()
