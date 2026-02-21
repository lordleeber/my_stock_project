import argparse
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from strategies.multi_strategy_backtest import normalize_quotes
from strategies.strategyB.grid_search import build_config, run_one_combo


BASE_DIR = Path(__file__).resolve().parent
CANDIDATES_PATH = BASE_DIR.parent / "sii" / "2025" / "10" / "trade_candidates.csv"
QUOTES_CACHE_PATH = BASE_DIR.parent / "sii" / "2025" / "10" / "daily_quotes_20251013_1120_sii.csv"

OUT_ALL = BASE_DIR / "optuna_results_all.csv"
OUT_TOP20 = BASE_DIR / "optuna_results_top20.csv"
OUT_BEST = BASE_DIR / "optuna_best_config.json"
OUT_SUMMARY = BASE_DIR / "optuna_study_summary.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="StrategyB Optuna parameter search")
    parser.add_argument("--n-trials", type=int, default=400)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--timeout-sec", type=int, default=0)
    parser.add_argument("--entry-date", type=str, default="2025-10-13")
    parser.add_argument("--end-date", type=str, default="2025-11-20")
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
        tp_pct = float(trial.suggest_float("tp_pct", 0.03, 0.15, step=0.01))
        sl_pct = float(trial.suggest_float("sl_pct", 0.02, 0.10, step=0.01))
        trailing_stop_pct = float(trial.suggest_float("trailing_stop_pct", 0.01, 0.08, step=0.01))
        max_hold_days = int(trial.suggest_categorical("max_hold_days", [7, 10, 12, 15, 20, 30]))

        cfg = build_config(tp_pct=tp_pct, sl_pct=sl_pct, trailing_pct=trailing_stop_pct, max_hold_days=max_hold_days)
        row = run_one_combo(
            candidates=candidates,
            quotes=quotes,
            cfg=cfg,
            entry_date=args.entry_date,
            end_date=args.end_date,
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

    ranked = result_df.sort_values(by=sort_by, ascending=ascending).reset_index(drop=True)

    result_df.to_csv(OUT_ALL, index=False, encoding="utf-8-sig")
    ranked.head(20).to_csv(OUT_TOP20, index=False, encoding="utf-8-sig")
    OUT_BEST.write_text(json.dumps(ranked.iloc[0].to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        "n_trials": args.n_trials,
        "seed": args.seed,
        "timeout_sec": args.timeout_sec,
        "entry_date": args.entry_date,
        "end_date": args.end_date,
        "best_trial_number": int(study.best_trial.number),
        "best_score": float(study.best_value),
        "best_params": study.best_trial.params,
    }
    OUT_SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("strategyB optuna search ready/done")
    print(f"- all: {OUT_ALL}")
    print(f"- top20: {OUT_TOP20}")
    print(f"- best: {OUT_BEST}")
    print(f"- summary: {OUT_SUMMARY}")


if __name__ == "__main__":
    main()



