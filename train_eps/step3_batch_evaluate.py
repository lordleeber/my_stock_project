"""
批次執行 train_eps/step3_evaluate.py，涵蓋 train_eps/output/<YYYY-MM-DD>/ 下
所有已存在的 playbook 日期。

用法：
  venv/bin/python3 train_eps/step3_batch_evaluate.py
  venv/bin/python3 train_eps/step3_batch_evaluate.py --start-date 2024-05-15
  venv/bin/python3 train_eps/step3_batch_evaluate.py --skip-existing
  venv/bin/python3 train_eps/step3_batch_evaluate.py --dry-run
"""

from __future__ import annotations

import argparse
import sys
import subprocess
from pathlib import Path

_HERE = Path(__file__).resolve().parent
ROOT_DIR = _HERE.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from shared_config import parse_playbook_date  # noqa: E402


def available_dates() -> list[str]:
    """回傳所有存在 dataset_evaluate.csv 的 playbook 日期（YYYY-MM-DD）排序列表。"""
    output_dir = ROOT_DIR / "train_eps" / "output"
    dates: list[str] = []
    for csv in output_dir.glob("*/dataset_evaluate.csv"):
        d = csv.parent.name
        try:
            parse_playbook_date(d)
        except ValueError:
            # 不是合法的 canonical playbook date，略過
            continue
        dates.append(d)
    return sorted(dates)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Batch run step3_evaluate.py for a range of playbook dates."
    )
    parser.add_argument("--start-date", type=str, default=None, help="YYYY-MM-DD")
    parser.add_argument("--end-date", type=str, default=None, help="YYYY-MM-DD")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip dates where evaluate_by_fold.json already exists",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    all_dates = available_dates()
    if not all_dates:
        print("No dataset_evaluate.csv found under train_eps/output/")
        return

    start = args.start_date or all_dates[0]
    end = args.end_date or all_dates[-1]
    if args.start_date:
        parse_playbook_date(args.start_date)
    if args.end_date:
        parse_playbook_date(args.end_date)

    dates = [d for d in all_dates if start <= d <= end]
    print(f"Batch evaluate: {start} → {end}  ({len(dates)} dates)")

    python = sys.executable
    script = str(ROOT_DIR / "train_eps" / "step3_evaluate.py")

    ok = skipped = failed = 0

    for d in dates:
        if args.skip_existing:
            out_path = ROOT_DIR / "models_eps" / d / "evaluate_by_fold.json"
            if out_path.exists():
                print(f"[skip]  {d}  (evaluate_by_fold.json exists)")
                skipped += 1
                continue

        cmd = [python, script, "--date", d]

        if args.dry_run:
            print(f"[dry]   {d}  {' '.join(cmd)}")
            continue

        print(f"\n{'=' * 60}")
        print(f"[run]   {d}")
        print(f"{'=' * 60}")
        result = subprocess.run(cmd, cwd=str(ROOT_DIR))
        if result.returncode == 0:
            print(f"[ok]    {d}")
            ok += 1
        else:
            print(f"[FAIL]  {d}  (returncode={result.returncode})")
            failed += 1

    if not args.dry_run:
        print(f"\n{'=' * 60}")
        print(f"Done: ok={ok}  skipped={skipped}  failed={failed}  total={len(dates)}")


if __name__ == "__main__":
    main()
