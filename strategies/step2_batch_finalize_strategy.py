"""
批次執行 strategies/step2_finalize_strategy.py，涵蓋指定 playbook date 範圍。

用法：
  venv/bin/python3 strategies/step2_batch_finalize_strategy.py
  venv/bin/python3 strategies/step2_batch_finalize_strategy.py --start-date 2023-08-16
  venv/bin/python3 strategies/step2_batch_finalize_strategy.py --skip-existing
  venv/bin/python3 strategies/step2_batch_finalize_strategy.py --dry-run
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from strategies.shared_config import latest_playbook_date  # noqa: E402
from strategies.step1_batch_prepare_data import all_playbook_dates  # noqa: E402

DEFAULT_START = "2021-08-16"


def _resolve_default_end() -> str:
    """END 預設 = 今天當下最新的 canonical playbook day（latest_playbook_date()）。

    step2 對每個 date 必須有 dataset_strategy.csv（step1）+ predictions_results.csv（train_eps）；
    缺檔會直接 raise 而非 skip — 寧可早 fail 也不要靜默漏訓。

    例：今天 2026-05-22 → 2026-05-16（5/15 公告日 +1，已過）。
        若 2026-05-16 的 EPS predictions 還沒跑，這支會立刻報錯指出缺哪個檔。
    """
    return latest_playbook_date()


DEFAULT_END = _resolve_default_end()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Batch run step2_finalize_strategy.py for a range of playbook dates."
    )
    parser.add_argument(
        "--start-date", type=str, default=DEFAULT_START, help="YYYY-MM-DD"
    )
    parser.add_argument("--end-date", type=str, default=DEFAULT_END, help="YYYY-MM-DD")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip dates where trade_candidates.csv already exists",
    )
    parser.add_argument("--verbose", action="store_true", help="Print per-date output")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dates = all_playbook_dates(args.start_date, args.end_date)
    print(
        f"Batch step2_finalize_strategy: {args.start_date} → {args.end_date}  ({len(dates)} dates)"
    )

    python = sys.executable
    script = str(ROOT_DIR / "strategies" / "step2_finalize_strategy.py")

    ok = skipped = failed = 0

    for d in dates:
        if args.skip_existing:
            out_path = ROOT_DIR / "strategies" / "output" / d / "trade_candidates.csv"
            if out_path.exists():
                if args.verbose:
                    print(f"[skip]  {d}  (trade_candidates.csv exists)")
                skipped += 1
                continue

        # 前置檔案必須齊全；缺就早 fail。
        strategy_path = ROOT_DIR / "strategies" / "output" / d / "dataset_strategy.csv"
        pred_path = ROOT_DIR / "models_eps" / d / "predictions_results.csv"
        missing: list[str] = []
        if not strategy_path.exists():
            missing.append(str(strategy_path))
        if not pred_path.exists():
            missing.append(str(pred_path))
        if missing:
            raise SystemExit(
                f"[FAIL] {d}: missing required input file(s):\n  "
                + "\n  ".join(missing)
            )

        cmd = [python, script, "--date", d]

        if args.dry_run:
            print(f"[dry]   {d}  {' '.join(cmd)}")
            continue

        if args.verbose:
            print(f"\n{'=' * 60}")
            print(f"[run]   {d}")
            print(f"{'=' * 60}")
        result = subprocess.run(
            cmd,
            cwd=str(ROOT_DIR),
            stdout=None if args.verbose else subprocess.DEVNULL,
            stderr=None if args.verbose else subprocess.DEVNULL,
        )
        if result.returncode == 0:
            if args.verbose:
                print(f"[ok]    {d}")
            ok += 1
        else:
            print(f"[FAIL]  {d}  (returncode={result.returncode})")
            failed += 1

    if not args.dry_run:
        print(
            f"\nDone: ok={ok}  skipped={skipped}  failed={failed}  total={len(dates)}"
        )


if __name__ == "__main__":
    main()
