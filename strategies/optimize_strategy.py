"""
optimize_strategy.py — Optimize strategy parameters without look-ahead bias.

Flow:
  1. Load HISTORICAL candidates+quotes (last-year same month + last month)
     → Each stock's entry_date = its revenue_publish_date (actual publish date)
     → end_date = entry_date + 20 trading days (max hold), NOT month-end
  2. Run random-search grid over 300 trials on historical data → find best params
  3. Apply best params to CURRENT month's candidates → current_month_backtest.csv
     (This represents the forward strategy we would actually execute)
"""
import argparse
import calendar
import glob
import importlib.util
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Optimize strategy using market/year/month paths")
    parser.add_argument("--market", type=str, default="sii", choices=["sii", "otc"])
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=str, required=True, help="e.g. 09")
    parser.add_argument("--n-trials", type=int, default=300, help="random search trial count")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--min-entered-count", type=int, default=1,
                        help="minimum entered trades to avoid overfitting")
    parser.add_argument("--max-hold-days", type=int, default=20,
                        help="maximum trading days to hold a position")
    return parser.parse_args()


def load_backtest_module(module_path: Path):
    spec = importlib.util.spec_from_file_location("multi_strategy_backtest", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module: {module_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def build_base_config(strategy_name: str) -> dict[str, Any]:
    return {
        "strategy_name": strategy_name,
        "position": {"shares_per_lot": 1000, "max_position_amount": 200000},
        "entry_rule": {"type": "all"},
        "take_profit_rule": {"type": "fixed_pct", "pct": 0.08},
        "exit_rule": {
            "stop_loss_pct": 0.05,
            "trailing_stop_pct": None,
            "max_hold_days": 15,
            "prefer_stop_when_both": True,
        },
    }


def sample_config(rng: np.random.Generator) -> dict[str, Any]:
    family = rng.choice(["A", "B", "C"], p=[0.45, 0.35, 0.20])
    cfg = build_base_config(strategy_name=f"auto_{family}")

    if family == "A":
        cfg["take_profit_rule"] = {"type": "fixed_pct", "pct": float(rng.choice(np.arange(0.01, 0.151, 0.01)))}
        cfg["exit_rule"]["stop_loss_pct"] = float(rng.choice(np.arange(0.01, 0.101, 0.01)))
        cfg["exit_rule"]["max_hold_days"] = int(rng.choice([5, 7, 10, 12, 15, 20, 30]))
    elif family == "B":
        cfg["take_profit_rule"] = {"type": "fixed_pct", "pct": float(rng.choice(np.arange(0.03, 0.151, 0.01)))}
        cfg["exit_rule"]["stop_loss_pct"] = float(rng.choice(np.arange(0.02, 0.101, 0.01)))
        cfg["exit_rule"]["trailing_stop_pct"] = float(rng.choice(np.arange(0.01, 0.081, 0.01)))
        cfg["exit_rule"]["max_hold_days"] = int(rng.choice([7, 10, 12, 15, 20, 30]))
    else:
        entry_type = rng.choice(["target_above_entry_ratio", "pullback_from_ref_close"])
        if entry_type == "target_above_entry_ratio":
            ratio = float(rng.choice(np.arange(1.00, 1.121, 0.01)))
        else:
            ratio = float(rng.choice(np.arange(0.90, 1.001, 0.01)))
        cfg["entry_rule"] = {"type": entry_type, "ratio": ratio}

        tp_type = rng.choice(["target_price_if_above_entry", "fixed_pct"])
        if tp_type == "fixed_pct":
            cfg["take_profit_rule"] = {"type": tp_type, "pct": float(rng.choice(np.arange(0.04, 0.121, 0.01)))}
        else:
            cfg["take_profit_rule"] = {"type": tp_type}

        cfg["exit_rule"]["stop_loss_pct"] = float(rng.choice(np.arange(0.02, 0.061, 0.01)))
        cfg["exit_rule"]["max_hold_days"] = int(rng.choice([7, 10, 12, 15, 20]))

    return cfg


def get_nth_trading_day_after(quotes: pd.DataFrame, entry_date: pd.Timestamp, n: int) -> tuple[pd.Timestamp, pd.Timestamp]:
    """
    From the quotes DataFrame, find:
      - actual_entry: the first trading day ON OR AFTER entry_date
        (snaps forward if entry_date is a weekend/holiday)
      - actual_end: the n-th trading day on or after actual_entry

    Returns (actual_entry, actual_end).
    """
    trading_dates = sorted(quotes["date"].unique())
    future_dates = [d for d in trading_dates if d >= entry_date]
    if len(future_dates) == 0:
        return entry_date, entry_date

    actual_entry = future_dates[0]          # snap to next trading day
    remaining = future_dates               # from actual_entry onward
    if len(remaining) <= n:
        actual_end = remaining[-1]
    else:
        actual_end = remaining[n]
    return actual_entry, actual_end



def evaluate_config_historical(
    cfg: dict[str, Any],
    candidates: pd.DataFrame,
    quotes: pd.DataFrame,
    max_hold_days: int,
    simulate_one_fn,
) -> dict[str, Any]:
    """
    Evaluate a config on HISTORICAL candidates.
    Each stock's entry_date = its revenue_publish_date.
    Each stock's end_date   = entry_date + max_hold_days trading days.
    """
    rows = []
    for _, row in candidates.iterrows():
        pub_date_raw = row.get("revenue_publish_date")
        if pd.isna(pub_date_raw) or pub_date_raw == "":
            continue
        entry_dt = pd.to_datetime(pub_date_raw)

        # Get quotes for this symbol only (to count trading days accurately)
        sym = str(row["symbol"]).strip()
        sym_quotes = quotes[quotes["symbol"] == sym].copy()
        if sym_quotes.empty:
            # Fall back to all quotes for trading day counting
            sym_quotes = quotes

        actual_entry, end_dt = get_nth_trading_day_after(sym_quotes, entry_dt, n=max_hold_days)
        rows.append(simulate_one_fn(row=row, quote_df=quotes, entry_date=actual_entry, end_date=end_dt, cfg=cfg))

    if not rows:
        return _empty_result(cfg)

    out = pd.DataFrame(rows)
    return _aggregate_result(cfg, out)


def evaluate_config_current(
    cfg: dict[str, Any],
    candidates: pd.DataFrame,
    quotes: pd.DataFrame,
    max_hold_days: int,
    simulate_one_fn,
) -> pd.DataFrame:
    """
    Apply best config to CURRENT month's candidates.
    Returns a per-stock result DataFrame (not aggregated).
    """
    rows = []
    for _, row in candidates.iterrows():
        pub_date_raw = row.get("revenue_publish_date")
        if pd.isna(pub_date_raw) or pub_date_raw == "":
            continue
        entry_dt = pd.to_datetime(pub_date_raw)

        sym = str(row["symbol"]).strip()
        sym_quotes = quotes[quotes["symbol"] == sym].copy()
        if sym_quotes.empty:
            sym_quotes = quotes

        actual_entry, end_dt = get_nth_trading_day_after(sym_quotes, entry_dt, n=max_hold_days)
        r = simulate_one_fn(row=row, quote_df=quotes, entry_date=actual_entry, end_date=end_dt, cfg=cfg)
        rows.append(r)

    return pd.DataFrame(rows) if rows else pd.DataFrame()


def _empty_result(cfg: dict[str, Any]) -> dict[str, Any]:
    return {
        "strategy_name": cfg["strategy_name"],
        "entry_rule": json.dumps(cfg.get("entry_rule", {}), ensure_ascii=False),
        "take_profit_rule": json.dumps(cfg.get("take_profit_rule", {}), ensure_ascii=False),
        "exit_rule": json.dumps(cfg.get("exit_rule", {}), ensure_ascii=False),
        "total_picks": 0, "entered_count": 0, "skipped_count": 0,
        "sold_count": 0, "open_until_end_count": 0,
        "sold_win_count": 0, "sold_loss_count": 0,
        "total_capital": 0.0, "total_revenue": 0.0, "return_percent": 0.0,
    }


def _aggregate_result(cfg: dict[str, Any], out: pd.DataFrame) -> dict[str, Any]:
    sold = out[out["status"] == "sold"].copy()
    open_until_end = out[out["status"] == "open_until_end"].copy()
    skipped = out[out["status"] == "skipped"].copy()

    total_capital = float(sold["capital_used"].sum()) if (not sold.empty and "capital_used" in sold.columns) else 0.0
    total_revenue = float(sold["pnl_amount"].sum()) if (not sold.empty and "pnl_amount" in sold.columns) else 0.0
    return_percent = (total_revenue / total_capital * 100.0) if total_capital > 0 else 0.0

    return {
        "strategy_name": cfg["strategy_name"],
        "entry_rule": json.dumps(cfg.get("entry_rule", {}), ensure_ascii=False),
        "take_profit_rule": json.dumps(cfg.get("take_profit_rule", {}), ensure_ascii=False),
        "exit_rule": json.dumps(cfg.get("exit_rule", {}), ensure_ascii=False),
        "total_picks": int(len(out)),
        "entered_count": int((out["status"].isin(["sold", "open_until_end"])).sum()),
        "skipped_count": int(len(skipped)),
        "sold_count": int(len(sold)),
        "open_until_end_count": int(len(open_until_end)),
        "sold_win_count": int((sold["pnl_amount"] > 0).sum()) if not sold.empty else 0,
        "sold_loss_count": int((sold["pnl_amount"] < 0).sum()) if not sold.empty else 0,
        "total_capital": round(total_capital, 2),
        "total_revenue": round(total_revenue, 2),
        "return_percent": round(return_percent, 4),
    }


def find_quotes_csv(base_dir: Path, market: str, year: int, month: int) -> Path | None:
    """Find the daily_quotes_*.csv file in the given month directory."""
    month_s = f"{month:02d}"
    pattern = str(base_dir / market / f"{year:04d}" / month_s / f"daily_quotes_*_{market}.csv")
    matches = glob.glob(pattern)
    if not matches:
        return None
    # Pick the one with the latest end-date (largest filename sort)
    return Path(sorted(matches)[-1])


def load_historical_data(
    base_dir: Path, market: str, year: int, month: int, normalize_quotes_fn
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Load trade_candidates + daily_quotes for a given period.
    Returns (candidates_df, quotes_df) — empty DataFrames if not found.
    """
    month_s = f"{month:02d}"
    cand_path = base_dir / market / f"{year:04d}" / month_s / "trade_candidates.csv"
    quotes_path = find_quotes_csv(base_dir, market, year, month)

    if not cand_path.exists():
        print(f"  [warn] candidates not found: {cand_path}")
        return pd.DataFrame(), pd.DataFrame()
    if quotes_path is None:
        print(f"  [warn] quotes not found in: {base_dir / market / f'{year:04d}' / month_s}")
        return pd.DataFrame(), pd.DataFrame()

    cand = pd.read_csv(cand_path)
    cand["symbol"] = cand["symbol"].astype(str).str.strip()

    # Ensure revenue_publish_date column exists
    if "revenue_publish_date" not in cand.columns:
        # Fallback: use day 10 of the month
        cand["revenue_publish_date"] = f"{year:04d}-{month_s}-10"
        print(f"  [warn] revenue_publish_date missing in {cand_path}. Using {year}-{month_s}-10 as fallback.")

    quotes = normalize_quotes_fn(pd.read_csv(quotes_path))
    print(f"  loaded {len(cand)} candidates, {len(quotes)} quote rows from {year}/{month_s}")
    return cand, quotes


def prev_month(year: int, month: int) -> tuple[int, int]:
    if month == 1:
        return year - 1, 12
    return year, month - 1


def main() -> None:
    args = parse_args()
    market = args.market
    year = int(args.year)
    month = str(args.month).zfill(2)
    month_int = int(month)
    base_dir = (Path.cwd() / "strategies").resolve()

    backtest_module = load_backtest_module(Path(__file__).resolve().parent / "multi_strategy_backtest.py")
    normalize_quotes = backtest_module.normalize_quotes
    simulate_one = backtest_module.simulate_one

    # ── Load current month ────────────────────────────────────────────────────
    current_cand_path = base_dir / market / f"{year:04d}" / month / "trade_candidates.csv"
    current_quotes_path = find_quotes_csv(base_dir, market, year, month_int)
    if not current_cand_path.exists():
        raise FileNotFoundError(f"candidates not found: {current_cand_path}")
    if current_quotes_path is None:
        raise FileNotFoundError(f"quotes cache not found for {year}/{month}")

    current_candidates = pd.read_csv(current_cand_path)
    current_candidates["symbol"] = current_candidates["symbol"].astype(str).str.strip()
    current_quotes = normalize_quotes(pd.read_csv(current_quotes_path))

    if "revenue_publish_date" not in current_candidates.columns:
        current_candidates["revenue_publish_date"] = f"{year}-{month}-10"
        print(f"[warn] revenue_publish_date missing in current candidates. Using {year}-{month}-10.")

    # ── Load historical training set ──────────────────────────────────────────
    # Period A: last-year same month
    ly_year, ly_month = year - 1, month_int
    # Period B: last month
    lm_year, lm_month = prev_month(year, month_int)

    training_periods = []
    hist_cands_list: list[pd.DataFrame] = []
    hist_quotes_list: list[pd.DataFrame] = []

    for (hy, hm, label) in [(ly_year, ly_month, "last-year same month"), (lm_year, lm_month, "last month")]:
        print(f"\n[training] Loading {label}: {hy}/{hm:02d}")
        cand, quotes = load_historical_data(base_dir, market, hy, hm, normalize_quotes)
        if not cand.empty and not quotes.empty:
            hist_cands_list.append(cand)
            hist_quotes_list.append(quotes)
            training_periods.append(f"{hy}-{hm:02d}")

    if not hist_cands_list:
        print("\n[warn] No historical training data found. Falling back to current month for optimization.")
        # Last resort: use current month (same old behaviour, with proper per-stock entry dates)
        hist_candidates = current_candidates.copy()
        hist_quotes = current_quotes.copy()
        training_periods = [f"{year}-{month} (current, fallback)"]
    else:
        hist_candidates = pd.concat(hist_cands_list, ignore_index=True)
        hist_quotes = pd.concat(hist_quotes_list, ignore_index=True)
        # Deduplicate quotes by symbol+date (keep last)
        hist_quotes = (
            hist_quotes.sort_values(["symbol", "date"])
            .drop_duplicates(subset=["symbol", "date"], keep="last")
            .reset_index(drop=True)
        )

    print(f"\n[training] Combined: {len(hist_candidates)} candidates, {len(hist_quotes)} quote rows")
    print(f"[training] Periods:  {training_periods}")

    # ── Random search on historical data ─────────────────────────────────────
    rng = np.random.default_rng(args.seed)
    rows: list[dict[str, Any]] = []

    print(f"\n[optimize] Running {args.n_trials} trials on historical data...")
    for i in range(args.n_trials):
        cfg = sample_config(rng=rng)
        row = evaluate_config_historical(
            cfg=cfg,
            candidates=hist_candidates,
            quotes=hist_quotes,
            max_hold_days=args.max_hold_days,
            simulate_one_fn=simulate_one,
        )
        row["trial_number"] = i
        row["score"] = row["return_percent"] if row["entered_count"] >= args.min_entered_count else -999.0
        rows.append(row)

    all_df = pd.DataFrame(rows)
    ranked = all_df.sort_values(
        by=["score", "return_percent", "total_revenue", "sold_loss_count"],
        ascending=[False, False, False, True],
    ).reset_index(drop=True)

    best = ranked.iloc[0].to_dict()
    output_dir = current_cand_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    # ── Apply best params to current month ────────────────────────────────────
    print(f"\n[apply] Applying best strategy to current month {year}/{month}...")
    best_cfg = {
        "strategy_name": best["strategy_name"],
        "position": {"shares_per_lot": 1000, "max_position_amount": 200000},
        "entry_rule": json.loads(best["entry_rule"]),
        "take_profit_rule": json.loads(best["take_profit_rule"]),
        "exit_rule": json.loads(best["exit_rule"]),
    }
    current_result_df = evaluate_config_current(
        cfg=best_cfg,
        candidates=current_candidates,
        quotes=current_quotes,
        max_hold_days=args.max_hold_days,
        simulate_one_fn=simulate_one,
    )

    # ── Save outputs ──────────────────────────────────────────────────────────
    all_path = output_dir / "optimization_results_all.csv"
    top20_path = output_dir / "optimization_results_top20.csv"
    best_path = output_dir / "best_strategy.json"
    current_bt_path = output_dir / "current_month_backtest.csv"
    summary_path = output_dir / "optimization_summary.json"

    all_df.to_csv(all_path, index=False, encoding="utf-8-sig")
    ranked.head(20).to_csv(top20_path, index=False, encoding="utf-8-sig")
    best_path.write_text(json.dumps(best, ensure_ascii=False, indent=2), encoding="utf-8")

    if not current_result_df.empty:
        current_result_df.to_csv(current_bt_path, index=False, encoding="utf-8-sig")

    summary_path.write_text(
        json.dumps(
            {
                "market": market,
                "year": year,
                "month": month,
                "training_periods": training_periods,
                "max_hold_days": args.max_hold_days,
                "n_trials": args.n_trials,
                "seed": args.seed,
                "min_entered_count": args.min_entered_count,
                "hist_candidates_count": int(len(hist_candidates)),
                "hist_quotes_rows": int(len(hist_quotes)),
                "best_trial_number": int(best["trial_number"]),
                "best_return_percent": float(best["return_percent"]),
                "best_score": float(best["score"]),
                "current_month_candidates": int(len(current_candidates)),
                "note": "entry_date=revenue_publish_date per stock; end_date=entry+max_hold_days trading days",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("\noptimize_strategy done")
    print(f"- market: {market}, year: {year}, month: {month}")
    print(f"- training_periods: {training_periods}")
    print(f"- out_all:          {all_path}")
    print(f"- out_top20:        {top20_path}")
    print(f"- out_best:         {best_path}")
    print(f"- out_current_bt:   {current_bt_path}")
    print(f"- out_summary:      {summary_path}")
    print(f"- best_return_percent (historical): {best['return_percent']}")


if __name__ == "__main__":
    main()
