"""Sweep --top-n for backtester/run_rolling.py and compare risk-adjusted returns.

For each value in --top-n, runs run_rolling.py, copies the outputs into
backtester/output/sweep_top_n/top_<N>/, then prints a comparison table and
writes sweep_summary.csv.

Metrics:
  - total_pnl                 : sum of realized_net_pnl across all settled cohorts
  - mean_monthly_return_pct   : mean of (pnl / (top_n * position_amount)) per cohort
  - sharpe_annual             : mean/std of monthly return * sqrt(12)
  - positive_months_pct       : share of cohorts with realized_net_pnl > 0
  - worst_month_return_pct    : worst single-cohort monthly return
  - max_drawdown_pnl          : max peak-to-trough drawdown on cumulative PnL
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
ROLLING_DIR = ROOT / "backtester" / "output" / "rolling"
SWEEP_DIR = ROOT / "backtester" / "output" / "sweep_top_n"
PY = ROOT / "venv" / "bin" / "python3"


def run_one(
    top_n: int,
    start_date: str,
    end_date: str | None,
    position_amount: float,
) -> Path:
    cmd = [
        str(PY),
        str(ROOT / "backtester" / "run_rolling.py"),
        "--start-date", start_date,
        "--top-n", str(top_n),
        "--position-amount", str(position_amount),
    ]
    if end_date:
        cmd += ["--end-date", end_date]
    print(f"\n[top_n={top_n}] running: {' '.join(cmd)}")
    subprocess.run(cmd, check=True, cwd=ROOT)

    dest = SWEEP_DIR / f"top_{top_n}"
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(ROLLING_DIR, dest)
    return dest


def compute_metrics(dest: Path, position_amount: float) -> dict:
    summary = json.loads((dest / "rolling_summary.json").read_text())
    monthly = pd.read_csv(dest / "rolling_monthly.csv")
    top_n = int(summary["top_n"])
    cohort_capital = top_n * position_amount

    pnl = monthly["realized_net_pnl"].dropna().astype(float)
    ret_pct = pnl / cohort_capital * 100.0

    mean_ret = ret_pct.mean()
    std_ret = ret_pct.std(ddof=1)
    sharpe = (mean_ret / std_ret) * math.sqrt(12) if std_ret and std_ret > 0 else float("nan")

    cum = pnl.cumsum()
    peak = cum.cummax()
    max_dd = float((cum - peak).min()) if len(cum) else float("nan")

    return {
        "top_n": top_n,
        "n_cohorts": int(len(pnl)),
        "trades": int(summary["total_closed_trades"]),
        "win_rate": float(summary["win_rate"]),
        "total_pnl": float(summary["total_net_pnl"]),
        "mean_monthly_return_pct": float(mean_ret),
        "std_monthly_return_pct": float(std_ret),
        "sharpe_annual": float(sharpe),
        "positive_months_pct": float((pnl > 0).mean()),
        "worst_month_return_pct": float(ret_pct.min()) if len(ret_pct) else float("nan"),
        "max_drawdown_pnl": max_dd,
        "still_open": int(summary["still_open_count"]),
    }


def format_table(df: pd.DataFrame) -> str:
    fmt = df.copy()
    for c in ["win_rate", "positive_months_pct"]:
        fmt[c] = fmt[c].map(lambda x: f"{x:.2%}")
    for c in ["mean_monthly_return_pct", "std_monthly_return_pct", "worst_month_return_pct"]:
        fmt[c] = fmt[c].map(lambda x: f"{x:+.3f}%")
    for c in ["total_pnl", "max_drawdown_pnl"]:
        fmt[c] = fmt[c].map(lambda x: f"{x:,.0f}")
    fmt["sharpe_annual"] = fmt["sharpe_annual"].map(lambda x: f"{x:.3f}")
    return fmt.to_string(index=False)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--start-date", default="2022-07-11")
    p.add_argument("--end-date", default=None,
                   help="Optional; if omitted run_rolling.py auto-detects.")
    p.add_argument("--position-amount", type=float, default=100_000.0)
    p.add_argument("--top-n", type=int, nargs="+",
                   default=[5, 10, 15, 20, 25, 30],
                   help="List of top_n values to sweep")
    args = p.parse_args()

    SWEEP_DIR.mkdir(parents=True, exist_ok=True)

    rows = []
    for n in args.top_n:
        dest = run_one(n, args.start_date, args.end_date, args.position_amount)
        rows.append(compute_metrics(dest, args.position_amount))

    df = pd.DataFrame(rows).sort_values("top_n").reset_index(drop=True)

    print("\n=== top_n sweep summary ===")
    print(format_table(df))

    best_sharpe = df.loc[df["sharpe_annual"].idxmax()]
    best_pnl = df.loc[df["total_pnl"].idxmax()]
    print(f"\nbest Sharpe : top_n={int(best_sharpe['top_n'])}  "
          f"sharpe={best_sharpe['sharpe_annual']:.3f}  "
          f"total_pnl={best_sharpe['total_pnl']:,.0f}")
    print(f"best PnL    : top_n={int(best_pnl['top_n'])}  "
          f"sharpe={best_pnl['sharpe_annual']:.3f}  "
          f"total_pnl={best_pnl['total_pnl']:,.0f}")

    out_csv = SWEEP_DIR / "sweep_summary.csv"
    df.to_csv(out_csv, index=False)
    print(f"\nwrote {out_csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
