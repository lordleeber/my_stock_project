import argparse
import calendar
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
    parser.add_argument("--min-entered-count", type=int, default=20, help="minimum entered trades to avoid overfitting")
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


def evaluate_config(
    cfg: dict[str, Any],
    candidates: pd.DataFrame,
    quotes: pd.DataFrame,
    entry_date: str,
    end_date: str,
    simulate_one_fn,
) -> dict[str, Any]:
    entry_dt = pd.to_datetime(entry_date)
    end_dt = pd.to_datetime(end_date)

    rows = []
    for _, row in candidates.iterrows():
        rows.append(simulate_one_fn(row=row, quote_df=quotes, entry_date=entry_dt, end_date=end_dt, cfg=cfg))
    out = pd.DataFrame(rows)

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


def main() -> None:
    args = parse_args()
    market = args.market
    year = int(args.year)
    month = str(args.month).zfill(2)
    last_day = calendar.monthrange(year, int(month))[1]
    entry_date = f"{year:04d}-{month}-01"
    end_date = f"{year:04d}-{month}-{last_day:02d}"

    default_candidates = (Path.cwd() / "strategies" / market / f"{year:04d}" / month / "trade_candidates.csv").resolve()
    default_quotes = (
        Path.cwd()
        / "strategies"
        / market
        / f"{year:04d}"
        / month
        / f"daily_quotes_{year:04d}{month}01_{year:04d}{month}{last_day:02d}_{market}.csv"
    ).resolve()

    candidates_path = default_candidates
    quotes_path = default_quotes

    if not candidates_path.exists():
        raise FileNotFoundError(f"candidates not found: {candidates_path}")
    if not quotes_path.exists():
        raise FileNotFoundError(f"quotes cache not found: {quotes_path}")

    output_dir = candidates_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    backtest_module = load_backtest_module(Path(__file__).resolve().parent / "multi_strategy_backtest.py")
    normalize_quotes = backtest_module.normalize_quotes
    simulate_one = backtest_module.simulate_one

    candidates = pd.read_csv(candidates_path)
    candidates["symbol"] = candidates["symbol"].astype(str).str.strip()
    quotes = normalize_quotes(pd.read_csv(quotes_path))

    rng = np.random.default_rng(args.seed)
    rows: list[dict[str, Any]] = []

    for i in range(args.n_trials):
        cfg = sample_config(rng=rng)
        row = evaluate_config(
            cfg=cfg,
            candidates=candidates,
            quotes=quotes,
            entry_date=entry_date,
            end_date=end_date,
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
                "market": market,
                "year": year,
                "month": month,
                "candidates": str(candidates_path),
                "quotes_cache": str(quotes_path),
                "entry_date": entry_date,
                "end_date": end_date,
                "n_trials": args.n_trials,
                "seed": args.seed,
                "min_entered_count": args.min_entered_count,
                "best_trial_number": int(best["trial_number"]),
                "best_return_percent": float(best["return_percent"]),
                "best_score": float(best["score"]),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("optimize_strategy done")
    print(f"- market: {market}")
    print(f"- year: {year}")
    print(f"- month: {month}")
    print(f"- candidates: {candidates_path}")
    print(f"- quotes: {quotes_path}")
    print(f"- out_all: {all_path}")
    print(f"- out_top20: {top20_path}")
    print(f"- out_best: {best_path}")
    print(f"- out_summary: {summary_path}")
    print(f"- best_return_percent: {best['return_percent']}")


if __name__ == "__main__":
    main()
