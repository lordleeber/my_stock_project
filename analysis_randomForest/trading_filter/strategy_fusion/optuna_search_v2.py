import argparse
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis_randomForest.trading_filter.multi_strategy_backtest import normalize_quotes
from analysis_randomForest.trading_filter.strategy_fusion.v2_selector_backtest import run_selector_once


BASE_DIR = Path(__file__).resolve().parent
TRADING_DIR = BASE_DIR.parent
CANDIDATES_PATH = TRADING_DIR / "trade_candidates_2025_1013_1120.csv"
QUOTES_PATH = TRADING_DIR / "daily_quotes_20251013_1120_sii.csv"
OUT_DIR = BASE_DIR / "results_v2"

OUT_ALL = OUT_DIR / "optuna_v2_results_all.csv"
OUT_TOP20 = OUT_DIR / "optuna_v2_results_top20.csv"
OUT_BEST = OUT_DIR / "optuna_v2_best_config.json"
OUT_SUMMARY = OUT_DIR / "optuna_v2_study_summary.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Optuna search for fusion v2 selector")
    parser.add_argument("--n-trials", type=int, default=500)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--timeout-sec", type=int, default=0)
    parser.add_argument("--min-entered-count", type=int, default=20)
    parser.add_argument("--entry-date", type=str, default="2025-10-13")
    parser.add_argument("--end-date", type=str, default="2025-11-20")
    return parser.parse_args()


def _load_optuna():
    try:
        import optuna  # type: ignore

        return optuna
    except ModuleNotFoundError:
        raise SystemExit("optuna not installed. Please run: .\\.venv\\Scripts\\python.exe -m pip install optuna")


def main() -> None:
    args = parse_args()
    optuna = _load_optuna()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    candidates = pd.read_csv(CANDIDATES_PATH)
    candidates["symbol"] = candidates["symbol"].astype(str).str.strip()
    quotes = normalize_quotes(pd.read_csv(QUOTES_PATH))

    trial_rows: list[dict] = []

    def objective(trial):
        top_k_strategies = int(trial.suggest_categorical("top_k_strategies", [2, 3, 4, 5]))
        min_votes = int(trial.suggest_categorical("min_votes", [1, 2, 3]))
        max_picks = int(trial.suggest_categorical("max_picks", [20, 30, 40, 50, 60]))
        max_per_industry = int(trial.suggest_categorical("max_per_industry", [4, 6, 8, 10]))
        stop_loss_pct = float(trial.suggest_float("stop_loss_pct", 0.03, 0.12, step=0.01))
        trailing_stop_pct = float(trial.suggest_float("trailing_stop_pct", 0.01, 0.06, step=0.01))
        max_hold_days = int(trial.suggest_categorical("max_hold_days", [7, 10, 12, 15, 20, 30]))
        max_position_amount = float(trial.suggest_categorical("max_position_amount", [100000.0, 150000.0, 200000.0]))

        _, _, summary = run_selector_once(
            candidates=candidates,
            quotes=quotes,
            entry_date=args.entry_date,
            end_date=args.end_date,
            top_k_strategies=top_k_strategies,
            min_strategy_entered=20,
            min_votes=min_votes,
            max_picks=max_picks,
            max_per_industry=max_per_industry,
            max_position_amount=max_position_amount,
            shares_per_lot=1000,
            stop_loss_pct=stop_loss_pct,
            trailing_stop_pct=trailing_stop_pct,
            max_hold_days=max_hold_days,
        )

        row = dict(summary)
        row["trial_number"] = int(trial.number)
        row["score"] = float(summary["return_percent"])
        trial_rows.append(row)

        trial.set_user_attr("entered_count", int(summary["entered_count"]))
        trial.set_user_attr("return_percent", float(summary["return_percent"]))
        return float(summary["return_percent"])

    sampler = optuna.samplers.TPESampler(seed=args.seed)
    study = optuna.create_study(direction="maximize", sampler=sampler)
    study.optimize(
        objective,
        n_trials=args.n_trials,
        timeout=None if args.timeout_sec <= 0 else args.timeout_sec,
        show_progress_bar=True,
    )

    result_df = pd.DataFrame(trial_rows)
    filtered = result_df[result_df["entered_count"] >= args.min_entered_count].copy()
    if filtered.empty:
        filtered = result_df.copy()

    ranked = filtered.sort_values(
        by=["return_percent", "total_revenue", "sold_loss_count"],
        ascending=[False, False, True],
    ).reset_index(drop=True)

    result_df.to_csv(OUT_ALL, index=False, encoding="utf-8-sig")
    ranked.head(20).to_csv(OUT_TOP20, index=False, encoding="utf-8-sig")
    OUT_BEST.write_text(json.dumps(ranked.iloc[0].to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        "n_trials": args.n_trials,
        "seed": args.seed,
        "timeout_sec": args.timeout_sec,
        "min_entered_count": args.min_entered_count,
        "entry_date": args.entry_date,
        "end_date": args.end_date,
        "best_trial_number": int(study.best_trial.number),
        "best_score": float(study.best_value),
        "best_params": study.best_trial.params,
    }
    OUT_SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("fusion v2 optuna done")
    print(f"- all: {OUT_ALL}")
    print(f"- top20: {OUT_TOP20}")
    print(f"- best: {OUT_BEST}")
    print(f"- summary: {OUT_SUMMARY}")


if __name__ == "__main__":
    main()
