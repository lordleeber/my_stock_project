import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from strategies.multi_strategy_backtest import normalize_quotes, simulate_one


BASE_DIR = Path(__file__).resolve().parent
CANDIDATES_PATH = BASE_DIR.parent / "sii" / "2025" / "10" / "trade_candidates.csv"
QUOTES_CACHE_PATH = BASE_DIR.parent / "sii" / "2025" / "10" / "daily_quotes_20251013_1120_sii.csv"

OUT_ALL = BASE_DIR / "grid_results_all.csv"
OUT_TOP20 = BASE_DIR / "grid_results_top20.csv"
OUT_BEST = BASE_DIR / "best_config.json"


def build_config(tp_pct: float, sl_pct: float, max_hold_days: int) -> dict:
    return {
        "strategy_name": f"A_tp{int(tp_pct*100)}_sl{int(sl_pct*100)}_h{max_hold_days}",
        "position": {"max_position_amount": 200000.0, "shares_per_lot": 1000},
        "entry_rule": {"type": "all"},
        "take_profit_rule": {"type": "fixed_pct", "pct": tp_pct},
        "exit_rule": {
            "stop_loss_pct": sl_pct,
            "max_hold_days": max_hold_days,
            "trailing_stop_pct": None,
            "prefer_stop_when_both": True,
        },
    }


def run_one_combo(candidates: pd.DataFrame, quotes: pd.DataFrame, cfg: dict, entry_date: str, end_date: str) -> dict:
    entry_dt = pd.to_datetime(entry_date)
    end_dt = pd.to_datetime(end_date)
    rows = []
    for _, row in candidates.iterrows():
        rows.append(simulate_one(row=row, quote_df=quotes, entry_date=entry_dt, end_date=end_dt, cfg=cfg))
    out = pd.DataFrame(rows)
    sold = out[out["status"] == "sold"].copy()
    open_until_end = out[out["status"] == "open_until_end"].copy()
    skipped = out[out["status"] == "skipped"].copy()

    total_capital = float(sold["capital_used"].sum()) if not sold.empty and "capital_used" in sold.columns else 0.0
    total_revenue = float(sold["pnl_amount"].sum()) if not sold.empty and "pnl_amount" in sold.columns else 0.0
    return_percent = (total_revenue / total_capital * 100.0) if total_capital > 0 else 0.0

    return {
        "strategy_name": cfg["strategy_name"],
        "tp_pct": cfg["take_profit_rule"]["pct"],
        "sl_pct": cfg["exit_rule"]["stop_loss_pct"],
        "max_hold_days": cfg["exit_rule"]["max_hold_days"],
        "total_picks": int(len(out)),
        "entered_count": int((out["status"].isin(["sold", "open_until_end"])).sum()),
        "skipped_count": int(len(skipped)),
        "sold_count": int(len(sold)),
        "open_until_end_count": int(len(open_until_end)),
        "sold_win_count": int((sold["pnl_amount"] > 0).sum()) if not sold.empty else 0,
        "sold_loss_count": int((sold["pnl_amount"] < 0).sum()) if not sold.empty else 0,
        "sold_win_money": round(float(sold.loc[sold["pnl_amount"] > 0, "pnl_amount"].sum()) if not sold.empty else 0.0, 2),
        "sold_losee_money": round(float(sold.loc[sold["pnl_amount"] < 0, "pnl_amount"].sum()) if not sold.empty else 0.0, 2),
        "total_capital": round(total_capital, 2),
        "total_revenue(??)": round(total_revenue, 2),
        "return_percent": round(return_percent, 4),
    }


def main() -> None:
    candidates = pd.read_csv(CANDIDATES_PATH)
    candidates["symbol"] = candidates["symbol"].astype(str).str.strip()
    quotes = normalize_quotes(pd.read_csv(QUOTES_CACHE_PATH))

    tp_grid = [i / 100 for i in range(1, 16)]  # 1%~15%
    sl_grid = [i / 100 for i in range(1, 11)]  # 1%~10%
    hold_grid = [5, 7, 10, 12, 15, 20, 30]

    all_rows = []
    total = len(tp_grid) * len(sl_grid) * len(hold_grid)
    idx = 0

    for tp in tp_grid:
        for sl in sl_grid:
            for h in hold_grid:
                idx += 1
                cfg = build_config(tp_pct=tp, sl_pct=sl, max_hold_days=h)
                print(f"[{idx}/{total}] {cfg['strategy_name']}")
                all_rows.append(
                    run_one_combo(
                        candidates=candidates,
                        quotes=quotes,
                        cfg=cfg,
                        entry_date="2025-10-13",
                        end_date="2025-11-20",
                    )
                )

    result_df = pd.DataFrame(all_rows)

    # ???日脣??嚗??????梢??摨?    filtered = result_df[result_df["entered_count"] >= 100].copy()
    if filtered.empty:
        filtered = result_df.copy()

    ranked = filtered.sort_values(
        by=["total_revenue(??)", "return_percent", "sold_loss_count"],
        ascending=[False, False, True],
    ).reset_index(drop=True)

    result_df.to_csv(OUT_ALL, index=False, encoding="utf-8-sig")
    ranked.head(20).to_csv(OUT_TOP20, index=False, encoding="utf-8-sig")

    best = ranked.iloc[0].to_dict()
    OUT_BEST.write_text(json.dumps(best, ensure_ascii=False, indent=2), encoding="utf-8")

    print("grid search done")
    print(f"- all: {OUT_ALL}")
    print(f"- top20: {OUT_TOP20}")
    print(f"- best: {OUT_BEST}")
    print(json.dumps(best, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()



