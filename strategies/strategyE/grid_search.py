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
    atr_lookback: int,
    tp_atr_mult: float,
    sl_atr_mult: float,
    trail_atr_mult: float | None,
    max_hold_days: int,
) -> dict:
    trail_desc = "none" if trail_atr_mult is None else str(int(trail_atr_mult * 10))
    return {
        "strategy_name": (
            f"E_atr{atr_lookback}_tp{int(tp_atr_mult*10)}"
            f"_sl{int(sl_atr_mult*10)}_tr{trail_desc}_h{max_hold_days}"
        ),
        "position": {"max_position_amount": 200000.0, "shares_per_lot": 1000},
        "entry_rule": {"type": "all"},
        "exit_rule": {
            "atr_lookback": atr_lookback,
            "tp_atr_mult": tp_atr_mult,
            "sl_atr_mult": sl_atr_mult,
            "trail_atr_mult": trail_atr_mult,
            "max_hold_days": max_hold_days,
            "prefer_stop_when_both": True,
        },
    }


def add_atr_features(quotes: pd.DataFrame, lookback: int) -> pd.DataFrame:
    out = quotes.copy()
    out = out.sort_values(["symbol", "date"]).reset_index(drop=True)
    prev_close = out.groupby("symbol")["close"].shift(1)
    tr1 = (out["high"] - out["low"]).abs()
    tr2 = (out["high"] - prev_close).abs()
    tr3 = (out["low"] - prev_close).abs()
    out["tr"] = np.nanmax(np.vstack([tr1.values, tr2.values, tr3.values]), axis=0)
    out["atr"] = out.groupby("symbol")["tr"].transform(lambda s: s.rolling(lookback, min_periods=1).mean())
    return out


def _safe_float(v, fallback=np.nan) -> float:
    return float(v) if pd.notna(v) else float(fallback)


def simulate_one_vol(
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
        return {**base, "status": "skipped", "exit_reason": entry_reason, "entry_open": entry_open}

    shares_per_lot = int(cfg["position"]["shares_per_lot"])
    max_position_amount = float(cfg["position"]["max_position_amount"])
    shares_bought, capital_used = build_position_size(entry_open, max_position_amount, shares_per_lot)

    tp_atr_mult = float(cfg["exit_rule"]["tp_atr_mult"])
    sl_atr_mult = float(cfg["exit_rule"]["sl_atr_mult"])
    trail_atr_mult = cfg["exit_rule"].get("trail_atr_mult")
    trail_atr_mult = None if trail_atr_mult is None else float(trail_atr_mult)
    max_hold_days = int(cfg["exit_rule"]["max_hold_days"])
    prefer_stop_when_both = bool(cfg["exit_rule"].get("prefer_stop_when_both", True))

    atr_entry = _safe_float(entry_rows.iloc[0]["atr"])
    if not np.isfinite(atr_entry) or atr_entry <= 0:
        atr_entry = _safe_float(entry_rows.iloc[0]["high"]) - _safe_float(entry_rows.iloc[0]["low"])
    if not np.isfinite(atr_entry) or atr_entry <= 0:
        atr_entry = entry_open * 0.02

    # ??ATR 瘙箏??箏????頝
    tp_price = entry_open + tp_atr_mult * atr_entry
    static_stop = max(0.01, entry_open - sl_atr_mult * atr_entry)
    highest_high = entry_open

    q = q.sort_values("date").reset_index(drop=True)
    for i, day in q.iterrows():
        day_high = _safe_float(day["high"])
        day_low = _safe_float(day["low"])
        day_close = _safe_float(day["close"])
        day_atr = _safe_float(day.get("atr", np.nan), fallback=atr_entry)
        day_date = day["date"].strftime("%Y-%m-%d")

        if np.isfinite(day_high):
            highest_high = max(highest_high, day_high)

        effective_stop = static_stop
        if trail_atr_mult is not None:
            trailing_stop = highest_high - trail_atr_mult * day_atr
            effective_stop = max(effective_stop, trailing_stop)

        hit_sl = np.isfinite(day_low) and day_low <= effective_stop
        hit_tp = np.isfinite(day_high) and day_high >= tp_price

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
                "tp_price": tp_price,
                "stop_price": effective_stop,
                "atr_entry": atr_entry,
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
                "tp_price": tp_price,
                "stop_price": effective_stop,
                "atr_entry": atr_entry,
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
                "tp_price": tp_price,
                "stop_price": effective_stop,
                "atr_entry": atr_entry,
                "shares_bought": shares_bought,
                "capital_used": capital_used,
                "pnl_amount": pnl_amount,
                "pnl_per_lot": (exit_price - entry_open) * shares_per_lot,
                "return_pct": (pnl_amount / capital_used * 100.0) if capital_used > 0 else np.nan,
            }

        if i + 1 >= max_hold_days:
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
                "tp_price": tp_price,
                "stop_price": effective_stop,
                "atr_entry": atr_entry,
                "shares_bought": shares_bought,
                "capital_used": capital_used,
                "pnl_amount": pnl_amount,
                "pnl_per_lot": (exit_price - entry_open) * shares_per_lot,
                "return_pct": (pnl_amount / capital_used * 100.0) if capital_used > 0 else np.nan,
            }

    last = q.tail(1).iloc[0]
    last_close = _safe_float(last["close"])
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
        "tp_price": tp_price,
        "atr_entry": atr_entry,
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
        rows.append(simulate_one_vol(row=row, quote_df=quotes, entry_date=entry_dt, end_date=end_dt, cfg=cfg))

    out = pd.DataFrame(rows)
    sold = out[out["status"] == "sold"].copy()
    open_until_end = out[out["status"] == "open_until_end"].copy()
    skipped = out[out["status"] == "skipped"].copy()

    total_capital = float(sold["capital_used"].sum()) if not sold.empty else 0.0
    total_revenue = float(sold["pnl_amount"].sum()) if not sold.empty else 0.0
    return_percent = (total_revenue / total_capital * 100.0) if total_capital > 0 else 0.0

    return {
        "strategy_name": cfg["strategy_name"],
        "atr_lookback": cfg["exit_rule"]["atr_lookback"],
        "tp_atr_mult": cfg["exit_rule"]["tp_atr_mult"],
        "sl_atr_mult": cfg["exit_rule"]["sl_atr_mult"],
        "trail_atr_mult": cfg["exit_rule"]["trail_atr_mult"],
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

    atr_lookback_grid = [3, 5, 7, 10]
    tp_atr_mult_grid = [1.0, 1.5, 2.0, 2.5, 3.0]
    sl_atr_mult_grid = [1.0, 1.5, 2.0]
    trail_atr_mult_grid = [None, 1.0, 1.5, 2.0]
    hold_grid = [10, 12, 15, 20]

    total = (
        len(atr_lookback_grid)
        * len(tp_atr_mult_grid)
        * len(sl_atr_mult_grid)
        * len(trail_atr_mult_grid)
        * len(hold_grid)
    )
    idx = 0
    all_rows = []

    for atr_lb in atr_lookback_grid:
        quotes_with_atr = add_atr_features(quotes, lookback=atr_lb)
        for tp_mult in tp_atr_mult_grid:
            for sl_mult in sl_atr_mult_grid:
                for tr_mult in trail_atr_mult_grid:
                    for h in hold_grid:
                        idx += 1
                        cfg = build_config(
                            atr_lookback=atr_lb,
                            tp_atr_mult=tp_mult,
                            sl_atr_mult=sl_mult,
                            trail_atr_mult=tr_mult,
                            max_hold_days=h,
                        )
                        print(f"[{idx}/{total}] {cfg['strategy_name']}")
                        all_rows.append(
                            run_one_combo(
                                candidates=candidates,
                                quotes=quotes_with_atr,
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

    print("strategyE grid search ready/done")
    print(f"- all: {OUT_ALL}")
    print(f"- top20: {OUT_TOP20}")
    print(f"- best: {OUT_BEST}")


if __name__ == "__main__":
    main()




