"""
依 walk-forward 方式，為每個 train_through cohort 各訓練一個選股模型。

對每個 train_through cohort T，使用 feature_return_analysis.csv 中 (year, month) <= T 的資料訓練，
並儲存至 models_selection/<YYYY-MM-DD>/。<YYYY-MM-DD> = T 的 playbook run date。

術語見 strategies/CLAUDE.md § Date Convention：
  train_through_playbook_date = 訓練資料 cohort 上界的 playbook run date（YYYY-MM-DD）
  train_through_cutoff_date   = 該 cohort 的 cutoff_date（公告日，PIT 用）

⚠ 不要叫成 model 的 cutoff_date — cutoff 是 target 的屬性，跟 train_through 差一個 cycle。

用法：
  venv/bin/python3 strategies/step4_batch_train_selection_model.py
  venv/bin/python3 strategies/step4_batch_train_selection_model.py --start-date 2023-01-11
  venv/bin/python3 strategies/step4_batch_train_selection_model.py --start-date 2022-06-11 --end-date 2025-08-16
  venv/bin/python3 strategies/step4_batch_train_selection_model.py --dry-run
  venv/bin/python3 strategies/step4_batch_train_selection_model.py --skip-existing

Walk-forward 語意：
  train_through_playbook_date=T 的模型由 step5 在 target playbook_date 嚴格大於 T 的最近一輪評分時使用。
  範例：train_through=2023-07-11（cutoff 2023-07-10）→ 用於排序 2023-08-16 (cohort 2023/08) 的候選股。

預設範圍：
  START = 2022-06-11  — 最早 train_through（約有 10 個月訓練資料）
  END   = 2026-04-11  — 最後一個 fwd_return 已可算的 cohort（analyze_feature_returns 涵蓋到 2026/04）
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from strategies.step1_batch_prepare_data import all_playbook_dates  # noqa: E402

DEFAULT_START = "2022-06-11"
DEFAULT_END = "2026-04-11"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Batch train one selection model per train_through cohort."
    )
    parser.add_argument(
        "--start-date", type=str, default=DEFAULT_START, help="YYYY-MM-DD"
    )
    parser.add_argument("--end-date", type=str, default=DEFAULT_END, help="YYYY-MM-DD")
    parser.add_argument(
        "--dry-run", action="store_true", help="Print commands without executing"
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip train_through dates where selection_model.pkl already exists",
    )
    parser.add_argument("--verbose", action="store_true", help="Print per-date output")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dates = all_playbook_dates(args.start_date, args.end_date)
    print(
        f"Batch train selection model: train_through {args.start_date} → {args.end_date}  ({len(dates)} cohorts)"
    )

    python = sys.executable
    script = str(ROOT_DIR / "strategies" / "step4_train_selection_model.py")

    ok = skipped = failed = 0

    for d in dates:
        if args.skip_existing:
            model_path = ROOT_DIR / "models_selection" / d / "selection_model.pkl"
            if model_path.exists():
                if args.verbose:
                    print(f"[skip]  train_through={d}  (selection_model.pkl exists)")
                skipped += 1
                continue

        cmd = [
            python,
            script,
            "--date",
            d,
            "--n-bins",
            "10",
            "--reg-alpha",
            "0.05",
            "--reg-lambda",
            "0.1",
        ]

        if args.dry_run:
            print(f"[dry]   train_through={d}  {' '.join(cmd)}")
            continue

        if args.verbose:
            print(f"\n{'=' * 60}")
            print(f"[run]   train_through={d}")
            print(f"{'=' * 60}")
        result = subprocess.run(
            cmd,
            cwd=str(ROOT_DIR),
            stdout=None if args.verbose else subprocess.DEVNULL,
            stderr=None if args.verbose else subprocess.DEVNULL,
        )
        if result.returncode == 0:
            if args.verbose:
                print(f"[ok]    train_through={d}")
            ok += 1
        else:
            print(f"[FAIL]  train_through={d}  (returncode={result.returncode})")
            failed += 1

    if not args.dry_run:
        print(
            f"\nDone: ok={ok}  skipped={skipped}  failed={failed}  total={len(dates)}"
        )


if __name__ == "__main__":
    main()
