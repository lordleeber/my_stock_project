import argparse
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from strategies.multi_strategy_backtest import normalize_quotes
from strategies.strategyI.grid_search import run_one_combo


BASE_DIR = Path(__file__).resolve().parent
CANDIDATES_PATH = BASE_DIR.parent / "sii" / "2025" / "10" / "trade_candidates.csv"
QUOTES_CACHE_PATH = BASE_DIR.parent / "sii" / "2025" / "10" / "daily_quotes_20251013_1120_sii.csv"

OUT_ALL = BASE_DIR / "optuna_results_all.csv"
OUT_TOP20 = BASE_DIR / "optuna_results_top20.csv"
OUT_BEST = BASE_DIR / "optuna_best_config.json"
OUT_SUMMARY = BASE_DIR / "optuna_study_summary.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="StrategyI Optuna parameter search")
    parser.add_argument("--n-trials", type=int, default=600)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--timeout-sec", type=int, default=0)
    parser.add_argument("--min-selected-count", type=int, default=20)
    return parser.parse_args()


def _load_optuna():
    try:
        import optuna  # type: ignore

        return optuna
    except ModuleNotFoundError:
        raise SystemExit(
            "optuna not installed. Please run: .\\.venv\\Scripts\\python.exe -m pip install optuna"
        )


def main() -> None:
    args = parse_args()
    optuna = _load_optuna()

    candidates = pd.read_csv(CANDIDATES_PATH)
    candidates["symbol"] = candidates["symbol"].astype(str).str.strip()
    quotes = normalize_quotes(pd.read_csv(QUOTES_CACHE_PATH))

    trial_rows: list[dict] = []

    def objective(trial):
        min_volume_lots = float(trial.suggest_categorical("min_volume_lots", [500.0, 1000.0]))
        min_upside_ratio = 1.03
        std_penalty = float(trial.suggest_categorical("std_penalty", [0.2, 0.4, 0.6]))
        gamma = float(trial.suggest_categorical("gamma", [0.7, 1.0, 1.3]))
        min_amount = float(trial.suggest_categorical("min_amount", [50000.0, 100000.0]))
        max_amount = float(trial.suggest_categorical("max_amount", [200000.0, 300000.0]))
        if max_amount <= min_amount:
            return -999.0
        tp_pct = float(trial.suggest_categorical("tp_pct", [0.10, 0.14]))
        sl_pct = float(trial.suggest_categorical("sl_pct", [0.05, 0.07]))
        trailing_pct = trial.suggest_categorical("trailing_stop_pct", [None, 0.05])
        max_hold_days = int(trial.suggest_categorical("max_hold_days", [12, 15]))

        row = run_one_combo(
            candidates=candidates,
            quotes=quotes,
            min_volume_lots=min_volume_lots,
            min_upside_ratio=min_upside_ratio,
            std_penalty=std_penalty,
            gamma=gamma,
            min_amount=min_amount,
            max_amount=max_amount,
            tp_pct=tp_pct,
            sl_pct=sl_pct,
            trailing_pct=trailing_pct,
            max_hold_days=max_hold_days,
        )
        row["trial_number"] = int(trial.number)

        raw_return = float(row["return_percent"])
        score = raw_return

        row["score"] = round(score, 4)
        trial_rows.append(row)

        return score

    sampler = optuna.samplers.TPESampler(seed=args.seed)
    study = optuna.create_study(direction="maximize", sampler=sampler)
    study.optimize(
        objective,
        n_trials=args.n_trials,
        timeout=None if args.timeout_sec <= 0 else args.timeout_sec,
        show_progress_bar=True,
    )

    result_df = pd.DataFrame(trial_rows)
    revenue_col = next((c for c in result_df.columns if "total_revenue" in c), None)
    sort_by = ["score", "return_percent"]
    ascending = [False, False]
    if revenue_col is not None:
        sort_by.append(revenue_col)
        ascending.append(False)
    sort_by.append("sold_loss_count")
    ascending.append(True)

    filtered = result_df[result_df["selected_count"] >= args.min_selected_count].copy()
    if filtered.empty:
        filtered = result_df.copy()
    ranked = filtered.sort_values(by=sort_by, ascending=ascending).reset_index(drop=True)

    result_df.to_csv(OUT_ALL, index=False, encoding="utf-8-sig")
    ranked.head(20).to_csv(OUT_TOP20, index=False, encoding="utf-8-sig")
    OUT_BEST.write_text(json.dumps(ranked.iloc[0].to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        "n_trials": args.n_trials,
        "seed": args.seed,
        "timeout_sec": args.timeout_sec,
        "min_selected_count": args.min_selected_count,
        "best_trial_number": int(study.best_trial.number),
        "best_score": float(study.best_value),
        "best_params": study.best_trial.params,
    }
    OUT_SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("strategyI optuna search ready/done")
    print(f"- all: {OUT_ALL}")
    print(f"- top20: {OUT_TOP20}")
    print(f"- best: {OUT_BEST}")
    print(f"- summary: {OUT_SUMMARY}")


if __name__ == "__main__":
    main()



