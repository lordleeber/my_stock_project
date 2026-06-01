"""彙整 backtester/output/rolling/ 的滾動回測結果。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize rolling backtest results.")
    parser.add_argument(
        "--show-monthly", action="store_true", help="Print per-month detail rows."
    )
    parser.add_argument(
        "--rolling-dir",
        type=Path,
        default=None,
        help="Dir holding rolling_*.csv / rolling_summary.json "
        "(default: backtester/output/rolling). Point at a run_rolling --out-dir.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rolling_dir = (
        args.rolling_dir.resolve()
        if args.rolling_dir is not None
        else (Path.cwd() / "backtester" / "output" / "rolling").resolve()
    )
    trades_path = rolling_dir / "rolling_trades.csv"
    monthly_path = rolling_dir / "rolling_monthly.csv"

    if not trades_path.exists():
        print(f"rolling_trades.csv not found: {trades_path}")
        return

    trades = pd.read_csv(trades_path)
    monthly = pd.read_csv(monthly_path) if monthly_path.exists() else pd.DataFrame()

    # exit_reason 分類說明：
    #   "monthly_rotation"  → 正常月度輪倉出場
    #   "still_open"        → 回測結束時仍持有，未計算損益
    #   "no_quote_on_exit"  → 出場日找不到行情，損益為 NaN
    closed = trades[trades["exit_reason"] == "monthly_rotation"].copy()
    still_open = trades[trades["exit_reason"] == "still_open"].copy()
    no_quote = trades[
        trades["exit_reason"].isin(["no_quote_on_exit", "no_quote_on_entry_date"])
    ].copy()

    # 財務統計僅計算有完整損益紀錄的已平倉交易
    total_net_pnl = closed["net_pnl"].sum() if not closed.empty else 0.0
    total_gross_pnl = closed["gross_pnl"].sum() if not closed.empty else 0.0
    total_cost = closed["cost"].sum() if not closed.empty else 0.0
    win_count = int((closed["net_pnl"] > 0).sum()) if not closed.empty else 0
    loss_count = int((closed["net_pnl"] < 0).sum()) if not closed.empty else 0
    total_closed = len(closed)
    win_rate = win_count / total_closed if total_closed > 0 else float("nan")

    avg_return_pct = (
        float(closed["return_pct"].mean()) if not closed.empty else float("nan")
    )
    median_return_pct = (
        float(closed["return_pct"].median()) if not closed.empty else float("nan")
    )

    print("=" * 55)
    print("Rolling Portfolio Backtest Summary")
    print("=" * 55)
    print(f"closed trades    : {total_closed}")
    print(f"  win / loss     : {win_count} / {loss_count}  (win_rate={win_rate:.1%})")
    print(f"  avg return     : {avg_return_pct:.2f}%")
    print(f"  median return  : {median_return_pct:.2f}%")
    print(f"gross pnl        : {total_gross_pnl:+,.0f} TWD")
    print(f"total cost       : {total_cost:,.0f} TWD")
    print(f"net pnl          : {total_net_pnl:+,.0f} TWD")
    print(f"still open       : {len(still_open)}")
    print(f"no-quote skipped : {len(no_quote)}")

    summary_path = rolling_dir / "rolling_summary.json"
    if summary_path.exists():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        mo = summary.get("monthly_stats_38_basis")
        if mo and mo.get("cohort_count"):
            print()
            print(f"Monthly Sharpe (38-basis, n={mo['cohort_count']} real cohorts):")
            print(
                f"  mean / std     : {mo['mean_monthly_return_pct']:+.3f}% / "
                f"{mo['std_monthly_return_pct']:.3f}%"
            )
            print(f"  win months     : {mo['win_months']}/{mo['cohort_count']}")
            print(
                f"  sharpe (mo)    : {mo['monthly_sharpe']:+.3f}  "
                f"(annualized × √{mo['annualization_factor'] ** 2:.1f} = "
                f"{mo['monthly_sharpe_annualized']:+.3f})"
            )
            print(
                f"  worst / best   : {mo['worst_month_return_pct']:+.2f}% / "
                f"{mo['best_month_return_pct']:+.2f}%"
            )

    if args.show_monthly and not monthly.empty:
        print("\n--- Monthly Detail ---")
        cols = [
            c
            for c in [
                "year",
                "month",
                "entry_date",
                "cohort_year",
                "cohort_month",
                "cohort_entry_date",
                "holdings_count",
                "exits",
                "entries",
                "realized_net_pnl",
                "portfolio_capital_deployed",
            ]
            if c in monthly.columns
        ]
        print(monthly[cols].to_string(index=False))


if __name__ == "__main__":
    main()
