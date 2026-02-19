import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis_randomForest.trading_filter.multi_strategy_backtest import normalize_quotes, simulate_one


BASE_DIR = Path(__file__).resolve().parent
CANDIDATES_PATH = BASE_DIR.parent / "trade_candidates_2025_1013_1120.csv"
QUOTES_CACHE_PATH = BASE_DIR.parent / "daily_quotes_20251013_1120_sii.csv"

OUT_ALL = BASE_DIR / "grid_results_all.csv"
OUT_TOP20 = BASE_DIR / "grid_results_top20.csv"
OUT_BEST = BASE_DIR / "best_config.json"


def build_config(entry_type: str, entry_ratio: float, tp_type: str, tp_pct: float | None, sl_pct: float, max_hold_days: int) -> dict:
    tp_desc = f"tp{int(tp_pct*100)}" if tp_type == "fixed_pct" and tp_pct is not None else "tpTarget"
    return {
        "strategy_name": f"C_{entry_type}_{entry_ratio:.2f}_{tp_desc}_sl{int(sl_pct*100)}_h{max_hold_days}",
        "position": {"max_position_amount": 200000.0, "shares_per_lot": 1000},
        "entry_rule": {"type": entry_type, "ratio": entry_ratio},
        "take_profit_rule": {"type": tp_type} if tp_type != "fixed_pct" else {"type": "fixed_pct", "pct": tp_pct},
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

    total_capital = float(sold["capital_used"].sum()) if not sold.empty else 0.0
    total_revenue = float(sold["pnl_amount"].sum()) if not sold.empty else 0.0
    return_percent = (total_revenue / total_capital * 100.0) if total_capital > 0 else 0.0

    return {
        "strategy_name": cfg["strategy_name"],
        "entry_type": cfg["entry_rule"]["type"],
        "entry_ratio": cfg["entry_rule"]["ratio"],
        "tp_type": cfg["take_profit_rule"]["type"],
        "tp_pct": cfg["take_profit_rule"].get("pct", None),
        "sl_pct": cfg["exit_rule"]["stop_loss_pct"],
        "max_hold_days": cfg["exit_rule"]["max_hold_days"],
        "total_picks": int(len(out)),
        "entered_count": int((out["status"].isin(["sold", "open_until_end"])).sum()),
        "skipped_count": int(len(skipped)),
        "sold_count": int(len(sold)),
        "open_until_end_count": int(len(open_until_end)),
        "sold_win_count": int((sold["pnl_amount"] > 0).sum()) if not sold.empty else 0,
        "sold_loss_count": int((sold["pnl_amount"] < 0).sum()) if not sold.empty else 0,
        "total_capital": round(total_capital, 2),
        "total_revenue(損益)": round(total_revenue, 2),
        "return_percent": round(return_percent, 4),
    }


def main() -> None:
    candidates = pd.read_csv(CANDIDATES_PATH)
    candidates["symbol"] = candidates["symbol"].astype(str).str.strip()
    quotes = normalize_quotes(pd.read_csv(QUOTES_CACHE_PATH))

    entry_specs = []
    entry_specs += [("target_above_entry_ratio", r / 100) for r in range(100, 113)]  # 1.00~1.12
    entry_specs += [("pullback_from_ref_close", r / 100) for r in range(99, 89, -1)]  # 0.99~0.90

    tp_specs = [("target_price_if_above_entry", None)]
    tp_specs += [("fixed_pct", i / 100) for i in range(4, 13)]  # 4%~12%

    sl_grid = [i / 100 for i in range(2, 7)]  # 2%~6%
    hold_grid = [7, 10, 12, 15, 20]

    total = len(entry_specs) * len(tp_specs) * len(sl_grid) * len(hold_grid)
    idx = 0
    all_rows = []

    for entry_type, entry_ratio in entry_specs:
        for tp_type, tp_pct in tp_specs:
            for sl in sl_grid:
                for h in hold_grid:
                    idx += 1
                    cfg = build_config(
                        entry_type=entry_type,
                        entry_ratio=entry_ratio,
                        tp_type=tp_type,
                        tp_pct=tp_pct,
                        sl_pct=sl,
                        max_hold_days=h,
                    )
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

    filtered = result_df[result_df["entered_count"] >= 20].copy()
    if filtered.empty:
        filtered = result_df.copy()

    ranked = filtered.sort_values(
        by=["return_percent", "total_revenue(損益)", "sold_loss_count"],
        ascending=[False, False, True],
    ).reset_index(drop=True)

    result_df.to_csv(OUT_ALL, index=False, encoding="utf-8-sig")
    ranked.head(20).to_csv(OUT_TOP20, index=False, encoding="utf-8-sig")
    OUT_BEST.write_text(json.dumps(ranked.iloc[0].to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    print("strategyC grid search ready/done")
    print(f"- all: {OUT_ALL}")
    print(f"- top20: {OUT_TOP20}")
    print(f"- best: {OUT_BEST}")


if __name__ == "__main__":
    main()
