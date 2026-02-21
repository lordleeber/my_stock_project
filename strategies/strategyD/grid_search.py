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
    tp1_pct: float,
    tp2_pct: float | None,
    partial_ratio: float,
    sl_pct: float,
    trailing_pct: float,
    max_hold_days: int,
) -> dict:
    tp2_desc = "none" if tp2_pct is None else f"{int(tp2_pct * 100)}"
    return {
        "strategy_name": (
            f"D_tp1_{int(tp1_pct*100)}_tp2_{tp2_desc}"
            f"_part_{int(partial_ratio*100)}_sl_{int(sl_pct*100)}"
            f"_tr_{int(trailing_pct*100)}_h_{max_hold_days}"
        ),
        "position": {"max_position_amount": 200000.0, "shares_per_lot": 1000},
        "entry_rule": {"type": "all"},
        "exit_rule": {
            "tp1_pct": tp1_pct,
            "tp2_pct": tp2_pct,
            "partial_ratio": partial_ratio,
            "stop_loss_pct": sl_pct,
            "trailing_stop_pct": trailing_pct,
            "max_hold_days": max_hold_days,
            "prefer_stop_when_both": True,
        },
    }


def _to_float(v) -> float:
    return float(v) if pd.notna(v) else float("nan")


def simulate_one_partial(
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
        return {
            **base,
            "status": "skipped",
            "exit_reason": entry_reason,
            "entry_open": entry_open,
        }

    # ?捱摰??⊥嚗??Ｗ??寡都?粹?箸??蝑雿?    shares_per_lot = int(cfg["position"]["shares_per_lot"])
    max_position_amount = float(cfg["position"]["max_position_amount"])
    shares_bought, capital_used = build_position_size(entry_open, max_position_amount, shares_per_lot)

    tp1_pct = float(cfg["exit_rule"]["tp1_pct"])
    tp2_pct = cfg["exit_rule"].get("tp2_pct")
    tp2_pct = None if tp2_pct is None else float(tp2_pct)
    partial_ratio = float(cfg["exit_rule"]["partial_ratio"])
    stop_loss_pct = float(cfg["exit_rule"]["stop_loss_pct"])
    trailing_stop_pct = float(cfg["exit_rule"]["trailing_stop_pct"])
    max_hold_days = int(cfg["exit_rule"]["max_hold_days"])
    prefer_stop_when_both = bool(cfg["exit_rule"].get("prefer_stop_when_both", True))

    tp1_price = entry_open * (1.0 + tp1_pct)
    tp2_price = None if tp2_pct is None else entry_open * (1.0 + tp2_pct)
    fixed_stop = entry_open * (1.0 - stop_loss_pct)

    # ?????    partial_hit = False
    partial_shares = int(round(shares_bought * partial_ratio))
    partial_shares = min(max(partial_shares, 1), shares_bought - 1) if shares_bought > 1 else shares_bought
    remaining_shares = shares_bought
    partial_cashout = 0.0
    highest_high_after_partial = entry_open

    q = q.sort_values("date").reset_index(drop=True)
    for i, day in q.iterrows():
        day_high = _to_float(day["high"])
        day_low = _to_float(day["low"])
        day_close = _to_float(day["close"])
        day_date = day["date"].strftime("%Y-%m-%d")

        # 蝚砌??挾: 撠閫貊??
        if not partial_hit:
            hit_sl = pd.notna(day_low) and day_low <= fixed_stop
            hit_tp1 = pd.notna(day_high) and day_high >= tp1_price

            if hit_sl and hit_tp1:
                # ???蝣啣嚗窒?冽?????身????
                if prefer_stop_when_both:
                    exit_price = fixed_stop
                    exit_reason = "both_hit_same_day_stop_first"
                else:
                    # ?孛?潛洵銝畾萄??抬???嗆????蝚砌?畾萎?隞塚??踹??亙???身?撥
                    partial_hit = True
                    partial_cashout += partial_shares * tp1_price
                    remaining_shares = shares_bought - partial_shares
                    highest_high_after_partial = max(entry_open, day_high if pd.notna(day_high) else entry_open)
                    continue

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
                    "partial_hit": False,
                    "partial_cashout": 0.0,
                    "pnl_amount": pnl_amount,
                    "pnl_per_lot": (exit_price - entry_open) * shares_per_lot,
                    "return_pct": (pnl_amount / capital_used * 100.0) if capital_used > 0 else np.nan,
                }

            if hit_sl:
                exit_price = fixed_stop
                pnl_amount = (exit_price - entry_open) * shares_bought
                return {
                    **base,
                    "status": "sold",
                    "entry_reason": entry_reason,
                    "exit_reason": "stop_loss_before_partial",
                    "exit_date": day_date,
                    "entry_open": entry_open,
                    "exit_price": exit_price,
                    "shares_bought": shares_bought,
                    "capital_used": capital_used,
                    "partial_hit": False,
                    "partial_cashout": 0.0,
                    "pnl_amount": pnl_amount,
                    "pnl_per_lot": (exit_price - entry_open) * shares_per_lot,
                    "return_pct": (pnl_amount / capital_used * 100.0) if capital_used > 0 else np.nan,
                }

            if hit_tp1:
                partial_hit = True
                partial_cashout += partial_shares * tp1_price
                remaining_shares = shares_bought - partial_shares
                highest_high_after_partial = max(entry_open, day_high if pd.notna(day_high) else entry_open)

                # ?亙?典歇鞈??嚗?隢??芸??1 ?⊥?瘜?嚗?亦???                if remaining_shares <= 0:
                    pnl_amount = partial_cashout - capital_used
                    return {
                        **base,
                        "status": "sold",
                        "entry_reason": entry_reason,
                        "exit_reason": "take_profit_partial_all_closed",
                        "exit_date": day_date,
                        "entry_open": entry_open,
                        "exit_price": tp1_price,
                        "shares_bought": shares_bought,
                        "capital_used": capital_used,
                        "partial_hit": True,
                        "partial_cashout": partial_cashout,
                        "pnl_amount": pnl_amount,
                        "pnl_per_lot": pnl_amount / shares_bought * shares_per_lot if shares_bought > 0 else np.nan,
                        "return_pct": (pnl_amount / capital_used * 100.0) if capital_used > 0 else np.nan,
                    }
                continue

        # 蝚砌??挾: 撌脣??質?銝?典?嚗銝 trailing stop / tp2 / time stop
        if partial_hit and remaining_shares > 0:
            if pd.notna(day_high):
                highest_high_after_partial = max(highest_high_after_partial, day_high)
            trailing_stop = highest_high_after_partial * (1.0 - trailing_stop_pct)
            effective_stop = max(fixed_stop, trailing_stop)

            hit_sl2 = pd.notna(day_low) and day_low <= effective_stop
            hit_tp2 = (tp2_price is not None) and pd.notna(day_high) and day_high >= tp2_price

            if hit_sl2 and hit_tp2:
                if prefer_stop_when_both:
                    remain_exit_price = effective_stop
                    exit_reason = "partial_then_both_hit_stop_first"
                else:
                    remain_exit_price = tp2_price
                    exit_reason = "partial_then_both_hit_target_first"
                total_cashout = partial_cashout + remaining_shares * remain_exit_price
                pnl_amount = total_cashout - capital_used
                return {
                    **base,
                    "status": "sold",
                    "entry_reason": entry_reason,
                    "exit_reason": exit_reason,
                    "exit_date": day_date,
                    "entry_open": entry_open,
                    "exit_price": remain_exit_price,
                    "shares_bought": shares_bought,
                    "capital_used": capital_used,
                    "partial_hit": True,
                    "partial_cashout": partial_cashout,
                    "pnl_amount": pnl_amount,
                    "pnl_per_lot": pnl_amount / shares_bought * shares_per_lot if shares_bought > 0 else np.nan,
                    "return_pct": (pnl_amount / capital_used * 100.0) if capital_used > 0 else np.nan,
                }

            if hit_sl2:
                remain_exit_price = effective_stop
                total_cashout = partial_cashout + remaining_shares * remain_exit_price
                pnl_amount = total_cashout - capital_used
                return {
                    **base,
                    "status": "sold",
                    "entry_reason": entry_reason,
                    "exit_reason": "partial_then_trailing_stop",
                    "exit_date": day_date,
                    "entry_open": entry_open,
                    "exit_price": remain_exit_price,
                    "shares_bought": shares_bought,
                    "capital_used": capital_used,
                    "partial_hit": True,
                    "partial_cashout": partial_cashout,
                    "pnl_amount": pnl_amount,
                    "pnl_per_lot": pnl_amount / shares_bought * shares_per_lot if shares_bought > 0 else np.nan,
                    "return_pct": (pnl_amount / capital_used * 100.0) if capital_used > 0 else np.nan,
                }

            if hit_tp2:
                remain_exit_price = tp2_price
                total_cashout = partial_cashout + remaining_shares * remain_exit_price
                pnl_amount = total_cashout - capital_used
                return {
                    **base,
                    "status": "sold",
                    "entry_reason": entry_reason,
                    "exit_reason": "partial_then_tp2",
                    "exit_date": day_date,
                    "entry_open": entry_open,
                    "exit_price": remain_exit_price,
                    "shares_bought": shares_bought,
                    "capital_used": capital_used,
                    "partial_hit": True,
                    "partial_cashout": partial_cashout,
                    "pnl_amount": pnl_amount,
                    "pnl_per_lot": pnl_amount / shares_bought * shares_per_lot if shares_bought > 0 else np.nan,
                    "return_pct": (pnl_amount / capital_used * 100.0) if capital_used > 0 else np.nan,
                }

        # ????嚗?隢?血??對??賢??憭拇???像?擗雿?        if i + 1 >= max_hold_days:
            if partial_hit:
                total_cashout = partial_cashout + remaining_shares * day_close
                exit_reason = f"partial_then_time_stop_{max_hold_days}d"
            else:
                total_cashout = shares_bought * day_close
                exit_reason = f"time_stop_{max_hold_days}d"
            pnl_amount = total_cashout - capital_used
            return {
                **base,
                "status": "sold",
                "entry_reason": entry_reason,
                "exit_reason": exit_reason,
                "exit_date": day_date,
                "entry_open": entry_open,
                "exit_price": day_close,
                "shares_bought": shares_bought,
                "capital_used": capital_used,
                "partial_hit": partial_hit,
                "partial_cashout": partial_cashout if partial_hit else 0.0,
                "pnl_amount": pnl_amount,
                "pnl_per_lot": pnl_amount / shares_bought * shares_per_lot if shares_bought > 0 else np.nan,
                "return_pct": (pnl_amount / capital_used * 100.0) if capital_used > 0 else np.nan,
            }

    # ??銝?max_hold_days ??閫貊嚗ㄐ?園??    last = q.tail(1).iloc[0]
    last_close = float(last["close"]) if pd.notna(last["close"]) else np.nan
    last_date = last["date"].strftime("%Y-%m-%d")
    if partial_hit:
        total_cashout = partial_cashout + remaining_shares * last_close
    else:
        total_cashout = shares_bought * last_close
    pnl_amount = total_cashout - capital_used
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
        "partial_hit": partial_hit,
        "partial_cashout": partial_cashout if partial_hit else 0.0,
        "pnl_amount": pnl_amount,
        "pnl_per_lot": pnl_amount / shares_bought * shares_per_lot if shares_bought > 0 else np.nan,
        "return_pct": (pnl_amount / capital_used * 100.0) if capital_used > 0 else np.nan,
    }


def run_one_combo(candidates: pd.DataFrame, quotes: pd.DataFrame, cfg: dict, entry_date: str, end_date: str) -> dict:
    entry_dt = pd.to_datetime(entry_date)
    end_dt = pd.to_datetime(end_date)
    rows = []
    for _, row in candidates.iterrows():
        rows.append(simulate_one_partial(row=row, quote_df=quotes, entry_date=entry_dt, end_date=end_dt, cfg=cfg))

    out = pd.DataFrame(rows)
    sold = out[out["status"] == "sold"].copy()
    open_until_end = out[out["status"] == "open_until_end"].copy()
    skipped = out[out["status"] == "skipped"].copy()

    total_capital = float(sold["capital_used"].sum()) if not sold.empty else 0.0
    total_revenue = float(sold["pnl_amount"].sum()) if not sold.empty else 0.0
    return_percent = (total_revenue / total_capital * 100.0) if total_capital > 0 else 0.0

    return {
        "strategy_name": cfg["strategy_name"],
        "tp1_pct": cfg["exit_rule"]["tp1_pct"],
        "tp2_pct": cfg["exit_rule"]["tp2_pct"],
        "partial_ratio": cfg["exit_rule"]["partial_ratio"],
        "sl_pct": cfg["exit_rule"]["stop_loss_pct"],
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

    tp1_grid = [0.04, 0.06, 0.08, 0.10]
    tp2_grid = [None, 0.12, 0.14, 0.16]
    partial_ratio_grid = [0.30, 0.50, 0.70]
    sl_grid = [0.03, 0.05, 0.07]
    trailing_grid = [0.03, 0.05, 0.07]
    hold_grid = [10, 12, 15, 20]

    total = len(tp1_grid) * len(tp2_grid) * len(partial_ratio_grid) * len(sl_grid) * len(trailing_grid) * len(hold_grid)
    idx = 0
    all_rows = []

    for tp1 in tp1_grid:
        for tp2 in tp2_grid:
            for pr in partial_ratio_grid:
                for sl in sl_grid:
                    for tr in trailing_grid:
                        for h in hold_grid:
                            idx += 1
                            cfg = build_config(
                                tp1_pct=tp1,
                                tp2_pct=tp2,
                                partial_ratio=pr,
                                sl_pct=sl,
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

    print("strategyD grid search ready/done")
    print(f"- all: {OUT_ALL}")
    print(f"- top20: {OUT_TOP20}")
    print(f"- best: {OUT_BEST}")


if __name__ == "__main__":
    main()




