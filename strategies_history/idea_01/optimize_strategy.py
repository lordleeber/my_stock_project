"""
optimize_strategy.py — Optimize strategy parameters without look-ahead bias.

Flow:
  1. Load HISTORICAL candidates+quotes (last-year same month + last month)
     → Each stock's entry_date = entry_date
     → end_date = entry_date + 20 trading days (max hold), NOT month-end
  2. Run random-search grid over historical data → find best params
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
    parser = argparse.ArgumentParser(description="Optimize strategy using year/month paths")
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=str, required=True, help="e.g. 09")
    parser.add_argument("--n-trials", type=int, default=300, help="random search trial count")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--min-entered-count", type=int, default=1,
                        help="minimum entered trades to avoid overfitting")
    parser.add_argument(
        "--max-stop-loss-ratio",
        type=float,
        default=0.5,
        help="maximum allowed stop_loss ratio among sold trades (0~1)",
    )
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
        # Never use entry_rule=all; always keep a gating condition.
        "entry_rule": {"type": "target_above_entry_ratio", "ratio": 1.02},
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
        # Momentum entry: target must be above entry by threshold.
        cfg["entry_rule"] = {
            "type": "target_above_entry_ratio",
            "ratio": float(rng.choice(np.arange(1.01, 1.131, 0.01))),
        }
    else:
        # Pullback entry: require pullback vs reference close.
        cfg["entry_rule"] = {
            "type": "pullback_from_ref_close",
            "ratio": float(rng.choice(np.arange(0.90, 0.991, 0.01))),
        }

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
    Each stock's entry_date = its entry_date.
    Each stock's end_date   = entry_date + max_hold_days trading days.
    """
    rows = []
    for _, row in candidates.iterrows():
        pub_date_raw = row.get("entry_date")
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


def _empty_result(cfg: dict[str, Any]) -> dict[str, Any]:
    return {
        "strategy_name": cfg["strategy_name"],
        "entry_rule": json.dumps(cfg.get("entry_rule", {}), ensure_ascii=False),
        "take_profit_rule": json.dumps(cfg.get("take_profit_rule", {}), ensure_ascii=False),
        "exit_rule": json.dumps(cfg.get("exit_rule", {}), ensure_ascii=False),
        "total_picks": 0, "entered_count": 0, "skipped_count": 0,
        "sold_count": 0, "open_until_end_count": 0,
        "sold_win_count": 0, "sold_loss_count": 0,
        "stop_loss_count": 0, "stop_loss_ratio": np.nan,
        "total_capital": 0.0, "total_revenue": 0.0, "return_percent": 0.0,
    }


def _aggregate_result(cfg: dict[str, Any], out: pd.DataFrame) -> dict[str, Any]:
    sold = out[out["status"] == "sold"].copy()
    open_until_end = out[out["status"] == "open_until_end"].copy()
    skipped = out[out["status"] == "skipped"].copy()

    total_capital = float(sold["capital_used"].sum()) if (not sold.empty and "capital_used" in sold.columns) else 0.0
    total_revenue = float(sold["pnl_amount"].sum()) if (not sold.empty and "pnl_amount" in sold.columns) else 0.0
    return_percent = (total_revenue / total_capital * 100.0) if total_capital > 0 else 0.0
    stop_loss_count = int((sold.get("exit_reason", pd.Series(dtype=str)) == "stop_loss").sum()) if not sold.empty else 0
    stop_loss_ratio = (stop_loss_count / len(sold)) if len(sold) > 0 else np.nan

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
        "stop_loss_count": stop_loss_count,
        "stop_loss_ratio": round(float(stop_loss_ratio), 6) if np.isfinite(stop_loss_ratio) else np.nan,
        "total_capital": round(total_capital, 2),
        "total_revenue": round(total_revenue, 2),
        "return_percent": round(return_percent, 4),
    }


def score_trial(row: dict[str, Any], min_entered_count: int, max_stop_loss_ratio: float) -> float:
    entered = int(row.get("entered_count", 0) or 0)
    sold_count = int(row.get("sold_count", 0) or 0)
    stop_loss_ratio = row.get("stop_loss_ratio", np.nan)
    ret = float(row.get("return_percent", 0.0) or 0.0)

    if entered < int(min_entered_count):
        return -999.0
    if sold_count <= 0:
        return -998.0
    if np.isfinite(stop_loss_ratio) and float(stop_loss_ratio) > float(max_stop_loss_ratio):
        return -500.0 + ret
    return ret


def find_quotes_csv(base_dir: Path, year: int, month: int) -> Path | None:
    """Find daily_quotes_*.csv for the given month.

    Search path:
    - strategies/output/<year>/<month>/results_quotes_cache/
    """
    month_s = f"{month:02d}"
    month_dir = base_dir / f"{year:04d}" / month_s

    pattern = str(month_dir / "results_quotes_cache" / "daily_quotes_*.csv")
    matches = glob.glob(pattern)
    if not matches:
        return None
    # Pick the one with the latest end-date (largest filename sort)
    return Path(sorted(matches)[-1])


def candidate_release_date(year: int, month: int) -> str:
    release_day = 15 if month in {5, 8, 11} else 10
    return f"{year:04d}{month:02d}{release_day:02d}"


def release_cutoff_timestamp(year: int, month: int) -> pd.Timestamp:
    ymd = candidate_release_date(year, month)
    return pd.Timestamp(f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:8]}")


def clip_quotes_to_cutoff(quotes: pd.DataFrame, cutoff: pd.Timestamp, label: str) -> pd.DataFrame:
    before = len(quotes)
    out = quotes[quotes["date"] <= cutoff].copy()
    print(f"  [cutoff] {label} <= {cutoff.strftime('%Y-%m-%d')}: {before} -> {len(out)} rows")
    return out


def get_candidates_path(base_dir: Path, year: int, month: int) -> Path:
    month_s = f"{month:02d}"
    ymd = candidate_release_date(year, month)
    return base_dir / f"{year:04d}" / month_s / "results_candidates" / f"trade_candidates_{ymd}.csv"


def load_historical_data(
    base_dir: Path, year: int, month: int, normalize_quotes_fn, asof_cutoff: pd.Timestamp
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Load trade_candidates + daily_quotes for a given period.
    Returns (candidates_df, quotes_df) — empty DataFrames if not found.
    """
    month_s = f"{month:02d}"
    cand_path = get_candidates_path(base_dir, year, month)
    quotes_path = find_quotes_csv(base_dir, year, month)

    if not cand_path.exists():
        raise FileNotFoundError(f"candidates not found: {cand_path}")
    if quotes_path is None:
        raise FileNotFoundError(f"quotes not found in: {base_dir / f'{year:04d}' / month_s / 'results_quotes_cache'}")

    cand = pd.read_csv(cand_path)
    cand["symbol"] = cand["symbol"].astype(str).str.strip()

    quotes = normalize_quotes_fn(pd.read_csv(quotes_path))
    quotes = clip_quotes_to_cutoff(quotes, asof_cutoff, f"{year}/{month_s}")
    print(f"  loaded {len(cand)} candidates, {len(quotes)} quote rows from {year}/{month_s}")
    return cand, quotes


def prev_month(year: int, month: int) -> tuple[int, int]:
    if month == 1:
        return year - 1, 12
    return year, month - 1


def main() -> None:
    args = parse_args()
    if args.max_stop_loss_ratio < 0.0 or args.max_stop_loss_ratio > 1.0:
        raise ValueError("--max-stop-loss-ratio must be in [0, 1]")
    year = int(args.year)
    month = str(args.month).zfill(2)
    month_int = int(month)
    base_dir = (Path.cwd() / "strategies" / "output").resolve()
    asof_cutoff = release_cutoff_timestamp(year, month_int)

    backtest_module = load_backtest_module(Path(__file__).resolve().parent / "multi_strategy_backtest.py")
    normalize_quotes = backtest_module.normalize_quotes
    simulate_one = backtest_module.simulate_one

    # ── Load historical training set ──────────────────────────────────────────
    # Period A: last-year same month
    ly_year, ly_month = year - 1, month_int
    # Period B: last month
    lm_year, lm_month = prev_month(year, month_int)

    training_periods = []
    required_periods = [
        (ly_year, ly_month, "last-year same month"),
        (lm_year, lm_month, "last month"),
    ]
    hist_cands_list: list[pd.DataFrame] = []
    hist_quotes_list: list[pd.DataFrame] = []
    loaded_period_keys: set[tuple[int, int]] = set()

    for (hy, hm, label) in required_periods:
        print(f"\n[training] Loading {label}: {hy}/{hm:02d}")
        cand, quotes = load_historical_data(base_dir, hy, hm, normalize_quotes, asof_cutoff)
        if not cand.empty and not quotes.empty:
            hist_cands_list.append(cand)
            hist_quotes_list.append(quotes)
            training_periods.append(f"{hy}-{hm:02d}")
            loaded_period_keys.add((hy, hm))

    missing = [(hy, hm, label) for (hy, hm, label) in required_periods if (hy, hm) not in loaded_period_keys]
    if missing:
        missing_text = ", ".join([f"{hy}-{hm:02d} ({label})" for (hy, hm, label) in missing])
        raise RuntimeError(
            "Missing required historical training periods: "
            f"{missing_text}. "
            "Please prepare trade_candidates and daily_quotes for both periods."
        )

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
        row["score"] = score_trial(
            row=row,
            min_entered_count=args.min_entered_count,
            max_stop_loss_ratio=args.max_stop_loss_ratio,
        )
        rows.append(row)

    all_df = pd.DataFrame(rows)
    ranked = all_df.sort_values(
        by=["score", "return_percent", "total_revenue", "sold_loss_count"],
        ascending=[False, False, False, True],
    ).reset_index(drop=True)

    best = ranked.iloc[0].to_dict()
    output_dir = base_dir / f"{year:04d}" / month / "results_optimize"
    output_dir.mkdir(parents=True, exist_ok=True)

    # ── Save outputs ──────────────────────────────────────────────────────────
    all_path = output_dir / "optimization_results_all.csv"
    top20_path = output_dir / "optimization_results_top20.csv"
    best_path = output_dir / "best_strategy.json"
    summary_path = output_dir / "optimization_summary.json"

    all_df.to_csv(all_path, index=False, encoding="utf-8-sig")
    ranked.head(20).to_csv(top20_path, index=False, encoding="utf-8-sig")
    best_path.write_text(json.dumps(best, ensure_ascii=False, indent=2), encoding="utf-8")

    summary_path.write_text(
        json.dumps(
            {
                "year": year,
                "month": month,
                "training_periods": training_periods,
                "max_hold_days": args.max_hold_days,
                "n_trials": args.n_trials,
                "seed": args.seed,
                "min_entered_count": args.min_entered_count,
                "max_stop_loss_ratio": args.max_stop_loss_ratio,
                "hist_candidates_count": int(len(hist_candidates)),
                "hist_quotes_rows": int(len(hist_quotes)),
                "best_trial_number": int(best["trial_number"]),
                "best_return_percent": float(best["return_percent"]),
                "best_score": float(best["score"]),
                "note": "entry_date per stock; end_date=entry+max_hold_days trading days",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("\noptimize_strategy done")
    print(f"- year: {year}, month: {month}")
    print(f"- training_periods: {training_periods}")
    print(f"- out_all:          {all_path}")
    print(f"- out_top20:        {top20_path}")
    print(f"- out_best:         {best_path}")
    print(f"- out_summary:      {summary_path}")
    print(f"- best_return_percent (historical): {best['return_percent']}")


if __name__ == "__main__":
    main()
