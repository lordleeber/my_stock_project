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
  END   = auto-detect  — feature_return_analysis.csv 裡最新的 playbook_date（= step3 的 END）
"""

from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from strategies.step1_batch_prepare_data import all_playbook_dates  # noqa: E402

DEFAULT_START = "2022-06-11"


def _resolve_default_end() -> str:
    """END 預設 = feature_return_analysis.csv 裡 max(playbook_date)。

    step4 訓練資料來自 feature_return_analysis.csv（step3 產出），所以最新可訓練的
    train_through 就是該檔的 max(playbook_date) — 與 step3 的 END 同步。

    例：今天 2026-05-22，step3 跑完後 feature_return_analysis.csv 涵蓋到 2026-04-11，
        所以 END = 2026-04-11。
        等 2026-06-11 cohort 跑完 step1+2 並重跑 step3，END 會自動推進到 2026-05-16。
    """
    fra = ROOT_DIR / "strategies" / "output" / "feature_return_analysis.csv"
    if not fra.exists():
        raise SystemExit(
            f"feature_return_analysis.csv not found: {fra}\n"
            f"Run: venv/bin/python3 strategies/step3_analyze_feature_returns.py"
        )
    with fra.open(encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        return max(row["playbook_date"] for row in reader)


DEFAULT_END = _resolve_default_end()


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
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="random_state passed to each step4 train (vary to probe model variance)",
    )
    # Lower-capacity defaults (15/15) validated over 30 seeds after the
    # valuation_daily fix — see step4_train_selection_model.py --num-leaves note.
    parser.add_argument(
        "--num-leaves",
        type=int,
        default=15,
        help="LGBMRanker num_leaves passed to each step4 train",
    )
    parser.add_argument(
        "--min-child-samples",
        type=int,
        default=15,
        help="LGBMRanker min_child_samples passed to each step4 train",
    )
    parser.add_argument(
        "--n-seeds",
        type=int,
        default=10,
        help="Train an N-seed ensemble per cohort (passed to step4 --n-seeds). "
        "default 10 (production); 1 = single-seed. See "
        "project_ensemble_validation_2026_06.",
    )
    parser.add_argument(
        "--models-root",
        type=Path,
        default=None,
        help="Root dir for model output (default models_selection/). Use an "
        "isolated dir per validation group so they don't overwrite each other.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dates = all_playbook_dates(args.start_date, args.end_date)
    print(
        f"Batch train selection model: train_through {args.start_date} → {args.end_date}  ({len(dates)} cohorts)"
    )

    python = sys.executable
    script = str(ROOT_DIR / "strategies" / "step4_train_selection_model.py")
    models_root = (
        args.models_root.resolve()
        if args.models_root is not None
        else (ROOT_DIR / "models_selection")
    )

    ok = skipped = failed = 0

    for d in dates:
        if args.skip_existing:
            model_path = models_root / d / "selection_model.pkl"
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
            "--seed",
            str(args.seed),
            "--num-leaves",
            str(args.num_leaves),
            "--min-child-samples",
            str(args.min_child_samples),
            "--n-seeds",
            str(args.n_seeds),
        ]
        if args.models_root is not None:
            cmd += ["--models-root", str(models_root)]

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
