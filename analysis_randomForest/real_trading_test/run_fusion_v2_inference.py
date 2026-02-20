import argparse
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis_randomForest.trading_filter.strategy_fusion.v2_selector_backtest import (  # noqa: E402
    pick_top_strategies,
    load_strategy_strength,
    select_by_votes,
)


DEFAULT_INPUT = Path(__file__).resolve().parent / "trade_candidates_2025_1009.csv"
DEFAULT_BEST = ROOT / "analysis_randomForest" / "trading_filter" / "strategy_fusion" / "results_v2" / "optuna_v2_best_config.json"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run fusion v2 inference on one-day real candidates.")
    parser.add_argument("--input-csv", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--best-config", type=Path, default=DEFAULT_BEST)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(args.input_csv)
    df["symbol"] = df["symbol"].astype(str).str.strip()

    best = json.loads(args.best_config.read_text(encoding="utf-8"))
    top_k = int(best.get("top_k_strategies", 3))
    min_strategy_entered = int(best.get("min_strategy_entered", 20))
    min_votes = int(best.get("min_votes", 2))
    max_picks = int(best.get("max_picks", 20))
    max_per_industry = int(best.get("max_per_industry", 8))

    strength = load_strategy_strength()
    top_strategies = pick_top_strategies(strength, top_k=top_k, min_entered=min_strategy_entered)
    selected = select_by_votes(
        candidates=df,
        selected_strategies=top_strategies,
        min_votes=min_votes,
        max_picks=max_picks,
        max_per_industry=max_per_industry,
    )
    selected_symbols = set(selected["symbol"].astype(str).tolist())

    out = df.copy()
    out["is_selected"] = out["symbol"].isin(selected_symbols)
    out["action_now"] = out["is_selected"].map({True: "buy_next_open", False: "watchlist"})

    action_cols = [
        "symbol",
        "name",
        "industry",
        "date",
        "close",
        "volume",
        "volume_lots",
        "pe_current",
        "predict_q3_eps",
        "ttm_eps_official_live",
        "ttm_eps_forward_live",
        "predict_target_price",
        "is_selected",
        "action_now",
    ]
    action_cols = [c for c in action_cols if c in out.columns]
    out = out[action_cols].sort_values(["is_selected", "symbol"], ascending=[False, True]).reset_index(drop=True)

    selected_out = out[out["is_selected"]].copy().reset_index(drop=True)
    watch_out = out[~out["is_selected"]].copy().reset_index(drop=True)

    date_tag = "unknown_date"
    if "date" in out.columns and out["date"].notna().any():
        date_tag = str(pd.to_datetime(out["date"].iloc[0]).date()).replace("-", "")

    out_all_path = args.output_dir / f"fusion_v2_actions_{date_tag}.csv"
    out_buy_path = args.output_dir / f"fusion_v2_buy_list_{date_tag}.csv"
    out_watch_path = args.output_dir / f"fusion_v2_watch_list_{date_tag}.csv"
    out_summary_path = args.output_dir / f"fusion_v2_inference_summary_{date_tag}.json"

    out.to_csv(out_all_path, index=False, encoding="utf-8-sig")
    selected_out.to_csv(out_buy_path, index=False, encoding="utf-8-sig")
    watch_out.to_csv(out_watch_path, index=False, encoding="utf-8-sig")

    summary = {
        "input_csv": str(args.input_csv),
        "best_config": str(args.best_config),
        "top_strategies": top_strategies,
        "top_k_strategies": top_k,
        "min_strategy_entered": min_strategy_entered,
        "min_votes": min_votes,
        "max_picks": max_picks,
        "max_per_industry": max_per_industry,
        "input_rows": int(len(df)),
        "buy_count": int(len(selected_out)),
        "watch_count": int(len(watch_out)),
    }
    out_summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("fusion v2 inference done")
    print(f"- actions: {out_all_path}")
    print(f"- buy_list: {out_buy_path}")
    print(f"- watch_list: {out_watch_path}")
    print(f"- summary: {out_summary_path}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
