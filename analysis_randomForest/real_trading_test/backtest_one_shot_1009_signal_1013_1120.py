import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis_randomForest.trading_filter.multi_strategy_backtest import normalize_quotes, simulate_one  # noqa: E402


BASE_DIR = Path(__file__).resolve().parent
BUY_LIST_PATH = BASE_DIR / "fusion_v2_buy_list_2025_1009.csv"
CACHE_ALL_QUOTES_PATH = BASE_DIR / "daily_cache_20251009_1120" / "all_quotes.csv"
BEST_CFG_PATH = (
    ROOT / "analysis_randomForest" / "trading_filter" / "strategy_fusion" / "results_v2" / "optuna_v2_best_config.json"
)
OUT_DIR = BASE_DIR / "one_shot_1009_to_1120"


def build_cfg(best: dict) -> dict:
    return {
        "strategy_name": "one_shot_1009_signal_1013_entry",
        "position": {
            "max_position_amount": float(best.get("max_position_amount", 200000.0)),
            "shares_per_lot": int(best.get("shares_per_lot", 1000)),
        },
        "entry_rule": {"type": "all"},
        "take_profit_rule": {"type": "target_price_if_above_entry"},
        "exit_rule": {
            "stop_loss_pct": float(best.get("stop_loss_pct", 0.11)),
            "max_hold_days": int(best.get("max_hold_days", 15)),
            "trailing_stop_pct": float(best.get("trailing_stop_pct", 0.06)),
            "prefer_stop_when_both": True,
        },
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    buy = pd.read_csv(BUY_LIST_PATH)
    buy["symbol"] = buy["symbol"].astype(str).str.strip()
    quotes = normalize_quotes(pd.read_csv(CACHE_ALL_QUOTES_PATH))
    best = json.loads(BEST_CFG_PATH.read_text(encoding="utf-8"))
    cfg = build_cfg(best)

    entry_dt = pd.to_datetime("2025-10-13")
    end_dt = pd.to_datetime("2025-11-20")

    rows = []
    for _, row in buy.iterrows():
        rows.append(simulate_one(row=row, quote_df=quotes, entry_date=entry_dt, end_date=end_dt, cfg=cfg))

    out = pd.DataFrame(rows)
    sold = out[out["status"] == "sold"].copy()
    open_until_end = out[out["status"] == "open_until_end"].copy()
    skipped = out[out["status"] == "skipped"].copy()

    total_capital = float(sold["capital_used"].sum()) if not sold.empty and "capital_used" in sold.columns else 0.0
    total_revenue = float(sold["pnl_amount"].sum()) if not sold.empty and "pnl_amount" in sold.columns else 0.0
    return_percent = (total_revenue / total_capital * 100.0) if total_capital > 0 else 0.0
    win_money = float(sold.loc[sold["pnl_amount"] > 0, "pnl_amount"].sum()) if not sold.empty else 0.0
    loss_money = float(sold.loc[sold["pnl_amount"] < 0, "pnl_amount"].sum()) if not sold.empty else 0.0

    out_path = OUT_DIR / "trades_one_shot_1009_signal_1013_1120.csv"
    summary_path = OUT_DIR / "summary_one_shot_1009_signal_1013_1120.json"

    out.to_csv(out_path, index=False, encoding="utf-8-sig")

    summary = {
        "signal_date": "2025-10-09",
        "entry_date": "2025-10-13",
        "end_date": "2025-11-20",
        "pick_count_from_signal": int(len(buy)),
        "entered_count": int((out["status"].isin(["sold", "open_until_end"])).sum()) if not out.empty else 0,
        "skipped_count": int(len(skipped)),
        "sold_count": int(len(sold)),
        "open_until_end_count": int(len(open_until_end)),
        "sold_win_count": int((sold["pnl_amount"] > 0).sum()) if not sold.empty else 0,
        "sold_loss_count": int((sold["pnl_amount"] < 0).sum()) if not sold.empty else 0,
        "total_capital": round(total_capital, 2),
        "sold_win_money": round(win_money, 2),
        "sold_losee_money": round(loss_money, 2),
        "total_revenue": round(total_revenue, 2),
        "return_percent": round(return_percent, 4),
        "cfg_stop_loss_pct": float(cfg["exit_rule"]["stop_loss_pct"]),
        "cfg_trailing_stop_pct": float(cfg["exit_rule"]["trailing_stop_pct"]),
        "cfg_max_hold_days": int(cfg["exit_rule"]["max_hold_days"]),
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("one-shot backtest done")
    print(f"- trades: {out_path}")
    print(f"- summary: {summary_path}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
