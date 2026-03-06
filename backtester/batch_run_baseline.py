from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backtester.run_baseline import CostConfig, run_month_baseline
from backtester.utils import month_iter


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch run baseline backtester by month range.")
    parser.add_argument("--start_year", type=int, required=True)
    parser.add_argument("--start_month", type=int, required=True)
    parser.add_argument("--end_year", type=int, required=True)
    parser.add_argument("--end_month", type=int, required=True)
    parser.add_argument("--commission-rate", type=float, default=0.001425)
    parser.add_argument("--tax-rate", type=float, default=0.003)
    parser.add_argument("--slippage-rate", type=float, default=0.0005)
    parser.add_argument("--position-amount", type=float, default=100000.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if (args.start_year, args.start_month) > (args.end_year, args.end_month):
        raise ValueError("start month must be <= end month")

    cost_cfg = CostConfig(
        commission_rate=args.commission_rate,
        tax_rate=args.tax_rate,
        slippage_rate=args.slippage_rate,
    )

    rows: list[dict] = []
    for y, m in month_iter(args.start_year, args.start_month, args.end_year, args.end_month):
        ym = f"{y:04d}-{m:02d}"
        try:
            out = run_month_baseline(year=y, month=m, cost_cfg=cost_cfg, position_amount=args.position_amount)
            rows.append({"year_month": ym, "status": "ok", "reason": "", "output_dir": out["output_dir"]})
            print(f"[ok] {ym}")
        except FileNotFoundError as e:
            rows.append({"year_month": ym, "status": "skipped_missing_inputs", "reason": str(e), "output_dir": ""})
            print(f"[skip] {ym} missing inputs")
        except Exception as e:  # noqa: BLE001
            rows.append({"year_month": ym, "status": "failed", "reason": str(e), "output_dir": ""})
            print(f"[fail] {ym} {e}")

    out_dir = (Path.cwd() / "backtester" / "output").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = out_dir / "batch_summary_baseline.json"
    summary_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"batch_summary_baseline": str(summary_path), "months": len(rows)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
