import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from strategies.multi_strategy_backtest import (  # noqa: E402
    build_position_size,
    check_entry_allowed,
    normalize_quotes,
)


BASE_DIR = Path(__file__).resolve().parent
CANDIDATES_PATH = BASE_DIR.parent / "sii" / "2025" / "10" / "trade_candidates.csv"
QUOTES_CACHE_PATH = BASE_DIR.parent / "sii" / "2025" / "10" / "daily_quotes_20251013_1120_sii.csv"

OUT_ALL = BASE_DIR / "grid_results_all.csv"
OUT_TOP20 = BASE_DIR / "grid_results_top20.csv"
OUT_BEST = BASE_DIR / "best_config.json"


def build_config(
    switch_day: int,
    early_tp: float,
    early_sl: float,
    late_tp: float,
    late_sl: float,
    trailing_pct: float | None,
    max_hold_days: int,
) -> dict:
    tr_desc = "none" if trailing_pct is None else str(int(trailing_pct * 100))
    return {
        "strategy_name": (
            f"G_sw{switch_day}_etp{int(early_tp*100)}_esl{int(early_sl*100)}"
            f"_ltp{int(late_tp*100)}_lsl{int(late_sl*100)}_tr{tr_desc}_h{max_hold_days}"
        ),
        "position": {"max_position_amount": 200000.0, "shares_per_lot": 1000},
        "entry_rule": {"type": "all"},
        "exit_rule": {
            "switch_day": switch_day,
            "early_tp_pct": early_tp,
            "early_sl_pct": early_sl,
            "late_tp_pct": late_tp,
            "late_sl_pct": late_sl,
            "trailing_stop_pct": trailing_pct,
            "max_hold_days": max_hold_days,
            "prefer_stop_when_both": True,
        },
    }


def simulate_one_time_regime(
    row: pd.Series,
    quote_df: pd.DataFrame,
    entry_date: pd.Timestamp,
    end_date: pd.Timestamp,
    cfg: dict,
) -> dict:
    symbol = str(row["symbol"]).strip()
    base = {
        "symbol": symbol,
        "strategy_name": cfg["strategy_name"],
        "entry_date": entry_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d"),
        "target_price": float(row.get("predict_target_price", np.nan)),
    }

    q = quote_df[(quote_df["symbol"] == symbol) & (quote_df["date"] >= entry_date) & (quote_df["date"] <= end_date)].copy()
    if q.empty:
        return {**base, "status": "no_quote_in_window", "exit_reason": "no_quote_in_window"}

    entry_rows = q[q["date"] == entry_date]
    if entry_rows.empty or pd.isna(entry_rows.iloc[0]["open"]):
        return {**base, "status": "no_entry_open", "exit_reason": "no_entry_open"}

    entry_open = float(entry_rows.iloc[0]["open"])
    entry_ok, entry_reason = check_entry_allowed(row=row, entry_open=entry_open, entry_rule=cfg.get("entry_rule", {}))
    if not entry_ok:
        return {**base, "status": "skipped", "exit_reason": entry_reason, "entry_open": entry_open}

    shares_per_lot = int(cfg["position"]["shares_per_lot"])
    max_position_amount = float(cfg["position"]["max_position_amount"])
    shares_bought, capital_used = build_position_size(entry_open, max_position_amount, shares_per_lot)

    switch_day = int(cfg["exit_rule"]["switch_day"])
    early_tp = float(cfg["exit_rule"]["early_tp_pct"])
    early_sl = float(cfg["exit_rule"]["early_sl_pct"])
    late_tp = float(cfg["exit_rule"]["late_tp_pct"])
    late_sl = float(cfg["exit_rule"]["late_sl_pct"])
    trailing_pct = cfg["exit_rule"].get("trailing_stop_pct")
    trailing_pct = None if trailing_pct is None else float(trailing_pct)
    max_hold_days = int(cfg["exit_rule"]["max_hold_days"])
    prefer_stop_when_both = bool(cfg["exit_rule"].get("prefer_stop_when_both", True))

    q = q.sort_values("date").reset_index(drop=True)
    highest_high = entry_open

    for i, day in q.iterrows():
        holding_day = i + 1
        day_high = float(day["high"]) if pd.notna(day["high"]) else np.nan
        day_low = float(day["low"]) if pd.notna(day["low"]) else np.nan
        day_close = float(day["close"]) if pd.notna(day["close"]) else np.nan
        day_date = day["date"].strftime("%Y-%m-%d")

        if pd.notna(day_high):
            highest_high = max(highest_high, day_high)

        # ?挾??early ?嚗?畾萇 late ?
        if holding_day <= switch_day:
            tp_pct = early_tp
            sl_pct = early_sl
        else:
            tp_pct = late_tp
            sl_pct = late_sl

        tp_price = entry_open * (1.0 + tp_pct)
        static_stop = entry_open * (1.0 - sl_pct)
        effective_stop = static_stop
        if trailing_pct is not None:
            trailing_stop = highest_high * (1.0 - trailing_pct)
            effective_stop = max(effective_stop, trailing_stop)

        hit_sl = pd.notna(day_low) and day_low <= effective_stop
        hit_tp = pd.notna(day_high) and day_high >= tp_price

        if hit_sl and hit_tp:
            if prefer_stop_when_both:
                exit_price = effective_stop
                exit_reason = "both_hit_same_day_stop_first"
            else:
                exit_price = tp_price
                exit_reason = "both_hit_same_day_target_first"
            pnl_amount = (exit_price - entry_open) * shares_bought
            return {
                **base,
                "status": "sold",
                "entry_reason": entry_reason,
                "exit_reason": exit_reason,
                "exit_date": day_date,
                "entry_open": entry_open,
                "exit_price": exit_price,
                "shares_bought": shares_bought,
                "capital_used": capital_used,
                "pnl_amount": pnl_amount,
                "pnl_per_lot": (exit_price - entry_open) * shares_per_lot,
                "return_pct": (pnl_amount / capital_used * 100.0) if capital_used > 0 else np.nan,
            }

        if hit_sl:
            exit_price = effective_stop
            pnl_amount = (exit_price - entry_open) * shares_bought
            return {
                **base,
                "status": "sold",
                "entry_reason": entry_reason,
                "exit_reason": "stop_loss",
                "exit_date": day_date,
                "entry_open": entry_open,
                "exit_price": exit_price,
                "shares_bought": shares_bought,
                "capital_used": capital_used,
                "pnl_amount": pnl_amount,
                "pnl_per_lot": (exit_price - entry_open) * shares_per_lot,
                "return_pct": (pnl_amount / capital_used * 100.0) if capital_used > 0 else np.nan,
            }

        if hit_tp:
            exit_price = tp_price
            pnl_amount = (exit_price - entry_open) * shares_bought
            return {
                **base,
                "status": "sold",
                "entry_reason": entry_reason,
                "exit_reason": "hit_target_price",
                "exit_date": day_date,
                "entry_open": entry_open,
                "exit_price": exit_price,
                "shares_bought": shares_bought,
                "capital_used": capital_used,
                "pnl_amount": pnl_amount,
                "pnl_per_lot": (exit_price - entry_open) * shares_per_lot,
                "return_pct": (pnl_amount / capital_used * 100.0) if capital_used > 0 else np.nan,
            }

        if holding_day >= max_hold_days:
            exit_price = day_close
            pnl_amount = (exit_price - entry_open) * shares_bought
            return {
                **base,
                "status": "sold",
                "entry_reason": entry_reason,
                "exit_reason": f"time_stop_{max_hold_days}d",
                "exit_date": day_date,
                "entry_open": entry_open,
                "exit_price": exit_price,
                "shares_bought": shares_bought,
                "capital_used": capital_used,
                "pnl_amount": pnl_amount,
                "pnl_per_lot": (exit_price - entry_open) * shares_per_lot,
                "return_pct": (pnl_amount / capital_used * 100.0) if capital_used > 0 else np.nan,
            }

    last = q.tail(1).iloc[0]
    last_close = float(last["close"]) if pd.notna(last["close"]) else np.nan
    last_date = last["date"].strftime("%Y-%m-%d")
    pnl_amount = (last_close - entry_open) * shares_bought
    return {
        **base,
        "status": "open_until_end",
        "entry_reason": entry_reason,
        "exit_reason": "not_hit_until_end",
        "exit_date": last_date,
        "entry_open": entry_open,
        "exit_price": last_close,
        "shares_bought": shares_bought,
        "capital_used": capital_used,
        "pnl_amount": pnl_amount,
        "pnl_per_lot": (last_close - entry_open) * shares_per_lot,
        "return_pct": (pnl_amount / capital_used * 100.0) if capital_used > 0 else np.nan,
    }


def run_one_combo(candidates: pd.DataFrame, quotes: pd.DataFrame, cfg: dict, entry_date: str, end_date: str) -> dict:
    entry_dt = pd.to_datetime(entry_date)
    end_dt = pd.to_datetime(end_date)
    rows = []
    for _, row in candidates.iterrows():
        rows.append(simulate_one_time_regime(row=row, quote_df=quotes, entry_date=entry_dt, end_date=end_dt, cfg=cfg))

    out = pd.DataFrame(rows)
    sold = out[out["status"] == "sold"].copy()
    open_until_end = out[out["status"] == "open_until_end"].copy()
    skipped = out[out["status"] == "skipped"].copy()

    total_capital = float(sold["capital_used"].sum()) if not sold.empty else 0.0
    total_revenue = float(sold["pnl_amount"].sum()) if not sold.empty else 0.0
    return_percent = (total_revenue / total_capital * 100.0) if total_capital > 0 else 0.0

    return {
        "strategy_name": cfg["strategy_name"],
        "switch_day": cfg["exit_rule"]["switch_day"],
        "early_tp_pct": cfg["exit_rule"]["early_tp_pct"],
        "early_sl_pct": cfg["exit_rule"]["early_sl_pct"],
        "late_tp_pct": cfg["exit_rule"]["late_tp_pct"],
        "late_sl_pct": cfg["exit_rule"]["late_sl_pct"],
        "trailing_stop_pct": cfg["exit_rule"]["trailing_stop_pct"],
        "max_hold_days": cfg["exit_rule"]["max_hold_days"],
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
    candidates = pd.read_csv(CANDIDATES_PATH)
    candidates["symbol"] = candidates["symbol"].astype(str).str.strip()
    quotes = normalize_quotes(pd.read_csv(QUOTES_CACHE_PATH))

    switch_day_grid = [5, 7, 10]
    early_tp_grid = [0.06, 0.08, 0.10]
    early_sl_grid = [0.03, 0.05]
    late_tp_grid = [0.10, 0.12, 0.14]
    late_sl_grid = [0.05, 0.07]
    trailing_grid = [None, 0.05]
    hold_grid = [12, 15, 20]

    total = (
        len(switch_day_grid)
        * len(early_tp_grid)
        * len(early_sl_grid)
        * len(late_tp_grid)
        * len(late_sl_grid)
        * len(trailing_grid)
        * len(hold_grid)
    )
    idx = 0
    all_rows = []

    for sw in switch_day_grid:
        for etp in early_tp_grid:
            for esl in early_sl_grid:
                for ltp in late_tp_grid:
                    for lsl in late_sl_grid:
                        for tr in trailing_grid:
                            for h in hold_grid:
                                idx += 1
                                cfg = build_config(
                                    switch_day=sw,
                                    early_tp=etp,
                                    early_sl=esl,
                                    late_tp=ltp,
                                    late_sl=lsl,
                                    trailing_pct=tr,
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
    filtered = result_df[result_df["entered_count"] >= 100].copy()
    if filtered.empty:
        filtered = result_df.copy()

    ranked = filtered.sort_values(
        by=["return_percent", "total_revenue", "sold_loss_count"],
        ascending=[False, False, True],
    ).reset_index(drop=True)

    result_df.to_csv(OUT_ALL, index=False, encoding="utf-8-sig")
    ranked.head(20).to_csv(OUT_TOP20, index=False, encoding="utf-8-sig")
    OUT_BEST.write_text(json.dumps(ranked.iloc[0].to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    print("strategyG grid search ready/done")
    print(f"- all: {OUT_ALL}")
    print(f"- top20: {OUT_TOP20}")
    print(f"- best: {OUT_BEST}")


if __name__ == "__main__":
    main()




