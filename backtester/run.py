from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

BACKTESTER_DIR = Path(__file__).resolve().parent
if str(BACKTESTER_DIR) not in sys.path:
    sys.path.insert(0, str(BACKTESTER_DIR))

try:
    from backtester.data_loader import load_daily_quotes
    from backtester.engine import CostConfig, simulate_one_trade
except ModuleNotFoundError:
    from data_loader import load_daily_quotes
    from engine import CostConfig, simulate_one_trade


@dataclass
class MonthRunSummary:
    year: int
    month: str
    status: str
    candidates_count: int
    quotes_count: int
    trades_count: int
    closed_trades_count: int
    capital_sum_closed: float
    net_pnl_sum: float
    gross_pnl_sum: float
    return_pct_net_closed: float | None
    return_pct_gross_closed: float | None
    avg_return_pct_net: float | None
    note: str | None = None


def numeric_series(df: pd.DataFrame, col: str) -> pd.Series:
    if col in df.columns:
        return pd.to_numeric(df[col], errors="coerce")
    return pd.Series(np.nan, index=df.index, dtype=float)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one-month walk-forward backtest on real DB quotes.")
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=int, required=True, help="1~12")
    parser.add_argument("--strategies-root", type=Path, default=Path("strategies/output"))
    parser.add_argument("--output-root", type=Path, default=Path("backtester/output"))
    parser.add_argument("--max-calendar-buffer-days", type=int, default=60)

    # Cost model options
    parser.add_argument("--commission-rate", type=float, default=0.001425)
    parser.add_argument("--commission-discount", type=float, default=1.0)
    parser.add_argument("--tax-rate", type=float, default=0.003)
    parser.add_argument("--entry-slippage-bps", type=float, default=0.0)
    parser.add_argument("--exit-slippage-bps", type=float, default=0.0)
    return parser.parse_args()


def validate_month(month: int) -> None:
    if month < 1 or month > 12:
        raise ValueError("month must be in 1..12")


def resolve_month_paths(strategies_root: Path, year: int, month: str) -> tuple[Path, Path]:
    base = strategies_root / f"{year:04d}" / month
    return base / "trade_candidates.csv", base / "results_optimize" / "best_strategy.json"


def load_month_inputs(strategies_root: Path, year: int, month: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    candidates_path, best_strategy_path = resolve_month_paths(strategies_root, year, month)

    missing = []
    if not candidates_path.exists():
        missing.append(f"missing trade_candidates: {candidates_path}")
    if not best_strategy_path.exists():
        missing.append(f"missing best_strategy: {best_strategy_path}")
    if missing:
        raise FileNotFoundError("; ".join(missing))

    candidates = pd.read_csv(candidates_path)
    best = json.loads(best_strategy_path.read_text(encoding="utf-8"))
    return candidates, best


def to_best_config(best: dict[str, Any]) -> dict[str, Any]:
    return {
        "strategy_name": str(best.get("strategy_name", "best")),
        "position": {"shares_per_lot": 1000, "max_position_amount": 200000},
        "entry_rule": json.loads(best["entry_rule"]) if isinstance(best.get("entry_rule"), str) else best.get("entry_rule", {"type": "all"}),
        "take_profit_rule": (
            json.loads(best["take_profit_rule"]) if isinstance(best.get("take_profit_rule"), str) else best.get("take_profit_rule", {"type": "fixed_pct", "pct": 0.08})
        ),
        "exit_rule": json.loads(best["exit_rule"]) if isinstance(best.get("exit_rule"), str) else best.get("exit_rule", {"stop_loss_pct": 0.05, "max_hold_days": 20}),
    }


def build_quote_window(candidates: pd.DataFrame, buffer_days: int) -> tuple[str, str]:
    entry_dt = pd.to_datetime(candidates["entry_date"], errors="coerce")
    valid = entry_dt.dropna()
    if valid.empty:
        raise RuntimeError("all entry_date values are invalid")
    start = valid.min().strftime("%Y-%m-%d")
    end = (valid.max() + pd.Timedelta(days=buffer_days)).strftime("%Y-%m-%d")
    return start, end


def summarize_month_from_trades(year: int, month: str, trades: pd.DataFrame, *, status: str, candidates_count: int, quotes_count: int, note: str | None = None) -> MonthRunSummary:
    if trades.empty:
        return MonthRunSummary(
            year=year,
            month=month,
            status=status,
            candidates_count=candidates_count,
            quotes_count=quotes_count,
            trades_count=0,
            closed_trades_count=0,
            capital_sum_closed=0.0,
            net_pnl_sum=0.0,
            gross_pnl_sum=0.0,
            return_pct_net_closed=None,
            return_pct_gross_closed=None,
            avg_return_pct_net=None,
            note=note,
        )

    net_pnl_sum = float(numeric_series(trades, "pnl_amount_net").fillna(0.0).sum())
    gross_pnl_sum = float(numeric_series(trades, "pnl_amount_gross").fillna(0.0).sum())
    avg_ret = numeric_series(trades, "return_pct_net")
    avg_ret_v = None if avg_ret.dropna().empty else float(avg_ret.dropna().mean())
    closed = trades[trades["status"] == "closed"].copy() if "status" in trades.columns else pd.DataFrame()
    capital_sum_closed = float(numeric_series(closed, "buy_notional").fillna(0.0).sum()) if not closed.empty else 0.0
    return_pct_net_closed = (net_pnl_sum / capital_sum_closed * 100.0) if capital_sum_closed > 0 else None
    return_pct_gross_closed = (gross_pnl_sum / capital_sum_closed * 100.0) if capital_sum_closed > 0 else None
    return MonthRunSummary(
        year=year,
        month=month,
        status=status,
        candidates_count=candidates_count,
        quotes_count=quotes_count,
        trades_count=len(trades),
        closed_trades_count=int(len(closed)),
        capital_sum_closed=capital_sum_closed,
        net_pnl_sum=net_pnl_sum,
        gross_pnl_sum=gross_pnl_sum,
        return_pct_net_closed=return_pct_net_closed,
        return_pct_gross_closed=return_pct_gross_closed,
        avg_return_pct_net=avg_ret_v,
        note=note,
    )


def main() -> None:
    args = parse_args()
    validate_month(args.month)

    year = int(args.year)
    month = f"{int(args.month):02d}"

    strategies_root = (Path.cwd() / args.strategies_root).resolve() if not args.strategies_root.is_absolute() else args.strategies_root.resolve()
    output_root = (Path.cwd() / args.output_root).resolve() if not args.output_root.is_absolute() else args.output_root.resolve()

    output_dir = output_root / f"{year:04d}" / month
    output_dir.mkdir(parents=True, exist_ok=True)

    cost_cfg = CostConfig(
        commission_rate=args.commission_rate,
        commission_discount=args.commission_discount,
        tax_rate=args.tax_rate,
        entry_slippage_bps=args.entry_slippage_bps,
        exit_slippage_bps=args.exit_slippage_bps,
    )

    print(f"\n=== backtest {year}/{month} ===")
    candidates, best = load_month_inputs(strategies_root, year, month)

    monthly_rows: list[MonthRunSummary] = []
    quality_reports: list[dict[str, Any]] = []
    lookahead_violations: list[str] = []

    if candidates.empty:
        trades_df = pd.DataFrame()
        monthly_rows.append(
            MonthRunSummary(
                year=year,
                month=month,
                status="skipped_no_candidates",
                candidates_count=0,
                quotes_count=0,
                trades_count=0,
                closed_trades_count=0,
                capital_sum_closed=0.0,
                net_pnl_sum=0.0,
                gross_pnl_sum=0.0,
                return_pct_net_closed=None,
                return_pct_gross_closed=None,
                avg_return_pct_net=None,
                note="no_candidates",
            )
        )
        print("skip: no candidates")
    else:
        for col in ["symbol", "entry_date", "predict_target_price"]:
            if col not in candidates.columns:
                raise RuntimeError(f"{year}/{month} candidates missing required column: {col}")

        candidates = candidates.copy()
        candidates["symbol"] = candidates["symbol"].astype(str).str.strip()
        entry_series = pd.to_datetime(candidates["entry_date"], errors="coerce")
        if entry_series.isna().any():
            bad_cnt = int(entry_series.isna().sum())
            raise RuntimeError(f"{year}/{month} candidates has {bad_cnt} invalid entry_date values")

        start_date, end_date = build_quote_window(candidates, args.max_calendar_buffer_days)
        quotes, qr = load_daily_quotes(
            symbols=candidates["symbol"].tolist(),
            start_date=start_date,
            end_date=end_date,
            drop_missing_ohlc=True,
        )
        quality_reports.append(
            {
                "year": year,
                "month": month,
                **asdict(qr),
                "start_date": start_date,
                "end_date": end_date,
            }
        )
        print(
            f"quotes loaded: {len(quotes)} rows "
            f"(dropped_missing_ohlc={qr.dropped_due_to_missing_ohlc})"
        )

        cfg = to_best_config(best)
        trade_rows: list[dict[str, Any]] = []
        for _, row in candidates.iterrows():
            trade = simulate_one_trade(row=row, quote_df=quotes, cfg=cfg, cost=cost_cfg)
            trade["signal_year"] = year
            trade["signal_month"] = month
            trade_rows.append(trade)

        trades_df = pd.DataFrame(trade_rows)

        if not trades_df.empty and {"signal_entry_date", "actual_entry_date"}.issubset(trades_df.columns):
            sig = pd.to_datetime(trades_df["signal_entry_date"], errors="coerce")
            act = pd.to_datetime(trades_df["actual_entry_date"], errors="coerce")
            bad_mask = (sig.notna()) & (act.notna()) & (act < sig)
            if bad_mask.any():
                bad_rows = trades_df.loc[bad_mask, ["symbol", "signal_entry_date", "actual_entry_date"]].head(10)
                msg = (
                    f"{year}/{month} look-ahead violation: actual_entry_date earlier than signal_entry_date; "
                    f"examples={bad_rows.to_dict(orient='records')}"
                )
                lookahead_violations.append(msg)
                print(msg)
                monthly_rows.append(
                    MonthRunSummary(
                        year=year,
                        month=month,
                        status="failed_lookahead",
                        candidates_count=len(candidates),
                        quotes_count=len(quotes),
                        trades_count=len(trades_df),
                        closed_trades_count=0,
                        capital_sum_closed=0.0,
                        net_pnl_sum=0.0,
                        gross_pnl_sum=0.0,
                        return_pct_net_closed=None,
                        return_pct_gross_closed=None,
                        avg_return_pct_net=None,
                        note=msg,
                    )
                )
            else:
                monthly_rows.append(
                    summarize_month_from_trades(
                        year,
                        month,
                        trades_df,
                        status="done",
                        candidates_count=len(candidates),
                        quotes_count=len(quotes),
                    )
                )
                print(f"trades simulated: {len(trades_df)}")
        else:
            monthly_rows.append(
                summarize_month_from_trades(
                    year,
                    month,
                    trades_df,
                    status="done",
                    candidates_count=len(candidates),
                    quotes_count=len(quotes),
                )
            )
            print(f"trades simulated: {len(trades_df)}")

    trades_all = trades_df if 'trades_df' in locals() else pd.DataFrame()
    monthly_df = pd.DataFrame([asdict(r) for r in monthly_rows])
    monthly_df = monthly_df.sort_values(["year", "month"]).reset_index(drop=True)
    monthly_df["cum_net_pnl"] = pd.to_numeric(monthly_df["net_pnl_sum"], errors="coerce").fillna(0.0).cumsum()
    equity_curve = monthly_df[["year", "month", "net_pnl_sum", "cum_net_pnl"]].copy()

    trades_path = output_dir / "trades.csv"
    monthly_path = output_dir / "monthly_summary.csv"
    equity_path = output_dir / "equity_curve.csv"
    summary_path = output_dir / "summary.json"

    trades_all.to_csv(trades_path, index=False)
    monthly_df.to_csv(monthly_path, index=False)
    equity_curve.to_csv(equity_path, index=False)

    done_months = int((monthly_df["status"] == "done").sum()) if not monthly_df.empty else 0
    skipped_months = int((monthly_df["status"] != "done").sum()) if not monthly_df.empty else 0
    closed = trades_all[trades_all["status"] == "closed"].copy() if (not trades_all.empty and "status" in trades_all.columns) else pd.DataFrame()
    capital_sum_closed_total = float(numeric_series(closed, "buy_notional").fillna(0.0).sum()) if not closed.empty else 0.0
    total_net_pnl = float(pd.to_numeric(monthly_df["net_pnl_sum"], errors="coerce").fillna(0.0).sum())
    total_gross_pnl = float(pd.to_numeric(monthly_df["gross_pnl_sum"], errors="coerce").fillna(0.0).sum())
    return_pct_net_closed_total = (total_net_pnl / capital_sum_closed_total * 100.0) if capital_sum_closed_total > 0 else None
    return_pct_gross_closed_total = (total_gross_pnl / capital_sum_closed_total * 100.0) if capital_sum_closed_total > 0 else None

    win_rate = None
    if not closed.empty and "pnl_amount_net" in closed.columns:
        pnl_closed = pd.to_numeric(closed["pnl_amount_net"], errors="coerce")
        denom = int(pnl_closed.notna().sum())
        if denom > 0:
            win_rate = float((pnl_closed > 0).sum() / denom)

    if equity_curve.empty:
        max_drawdown = 0.0
    else:
        cum = pd.to_numeric(equity_curve["cum_net_pnl"], errors="coerce").fillna(0.0)
        peak = cum.cummax()
        drawdown = cum - peak
        max_drawdown = float(drawdown.min()) if not drawdown.empty else 0.0

    summary_status = "failed_lookahead" if lookahead_violations else "completed"
    summary = {
        "status": summary_status,
        "start": f"{year:04d}-{month}",
        "end": f"{year:04d}-{month}",
        "strategies_root": str(strategies_root),
        "output_dir": str(output_dir),
        "months_total": int(len(monthly_df)),
        "months_done": done_months,
        "months_skipped": skipped_months,
        "total_trades_rows": int(len(trades_all)),
        "closed_trades_rows": int(len(closed)),
        "capital_sum_closed": capital_sum_closed_total,
        "total_gross_pnl": total_gross_pnl,
        "total_net_pnl": total_net_pnl,
        "return_pct_gross_closed": return_pct_gross_closed_total,
        "return_pct_net_closed": return_pct_net_closed_total,
        "win_rate_closed_net": win_rate,
        "max_drawdown_net_pnl": max_drawdown,
        "cost_config": asdict(cost_cfg),
        "quote_quality_reports": quality_reports,
        "lookahead_violations": lookahead_violations,
        "note": "one-month walk-forward backtest using monthly strategy outputs and real DB quotes",
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\nbacktester run completed")
    print(f"- year/month: {year}/{month}")
    print(f"- output_dir: {output_dir}")
    print(f"- trades: {trades_path}")
    print(f"- monthly_summary: {monthly_path}")
    print(f"- equity_curve: {equity_path}")
    print(f"- summary: {summary_path}")
    print(f"- months_done: {done_months}")
    print(f"- months_skipped: {skipped_months}")
    print(f"- lookahead_violations: {len(lookahead_violations)}")
    if lookahead_violations:
        raise RuntimeError("Look-ahead violation detected. See summary.json for details.")


if __name__ == "__main__":
    main()
