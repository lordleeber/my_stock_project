import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


DEFAULT_CANDIDATES = Path(__file__).resolve().parent / "sii" / "2025" / "10" / "trade_candidates.csv"
DEFAULT_QUOTES_CACHE = Path(__file__).resolve().parent / "sii" / "2025" / "10" / "daily_quotes_20251013_1120_sii.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run configurable trading strategy backtest.")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--quotes-cache", type=Path, default=DEFAULT_QUOTES_CACHE)
    parser.add_argument("--entry-date", type=str, required=True)
    parser.add_argument("--end-date", type=str, required=True)
    return parser.parse_args()


def normalize_quotes(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["symbol"] = out["symbol"].astype(str).str.strip()
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    for c in ["open", "high", "low", "close"]:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    return out.sort_values(["symbol", "date"]).reset_index(drop=True)


def build_position_size(entry_open: float, max_position_amount: float, shares_per_lot: int) -> tuple[int, float]:
    lot_cost = entry_open * shares_per_lot
    if lot_cost <= max_position_amount:
        shares = int(shares_per_lot)
    else:
        shares = int(max_position_amount // entry_open)
        shares = max(shares, 1)
    return shares, float(shares * entry_open)


def check_entry_allowed(row: pd.Series, entry_open: float, entry_rule: dict) -> tuple[bool, str]:
    rule_type = entry_rule.get("type", "all")
    if rule_type == "all":
        return True, "entry_all"

    if rule_type == "target_above_entry_ratio":
        ratio = float(entry_rule.get("ratio", 1.0))
        target_price = float(row.get("predict_target_price", np.nan))
        if np.isnan(target_price):
            return False, "skip_no_target"
        ok = target_price >= entry_open * ratio
        return ok, f"entry_target_ge_{ratio}"

    if rule_type == "pullback_from_ref_close":
        ratio = float(entry_rule.get("ratio", 1.0))
        ref_close = float(row.get("close", np.nan))
        if np.isnan(ref_close):
            return False, "skip_no_ref_close"
        ok = entry_open <= ref_close * ratio
        return ok, f"entry_pullback_le_{ratio}"

    return True, "entry_unknown_rule_default_true"


def resolve_take_profit_price(row: pd.Series, entry_open: float, tp_rule: dict) -> float | None:
    tp_type = tp_rule.get("type", "target_price")
    if tp_type == "target_price":
        v = float(row.get("predict_target_price", np.nan))
        return None if np.isnan(v) else v

    if tp_type == "fixed_pct":
        pct = float(tp_rule.get("pct", 0.0))
        return entry_open * (1.0 + pct)

    if tp_type == "target_price_if_above_entry":
        v = float(row.get("predict_target_price", np.nan))
        if np.isnan(v) or v <= entry_open:
            return None
        return v

    return None


def simulate_one(
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
        return {
            **base,
            "status": "skipped",
            "exit_reason": entry_reason,
            "entry_open": entry_open,
        }

    shares_per_lot = int(cfg["position"]["shares_per_lot"])
    max_position_amount = float(cfg["position"]["max_position_amount"])
    shares_bought, capital_used = build_position_size(entry_open, max_position_amount, shares_per_lot)

    stop_loss_pct = float(cfg["exit_rule"].get("stop_loss_pct", 0.05))
    fixed_stop = entry_open * (1.0 - stop_loss_pct)
    trailing_stop_pct = cfg["exit_rule"].get("trailing_stop_pct")
    trailing_stop_pct = None if trailing_stop_pct is None else float(trailing_stop_pct)
    max_hold_days = cfg["exit_rule"].get("max_hold_days")
    max_hold_days = None if max_hold_days is None else int(max_hold_days)
    prefer_stop_when_both = bool(cfg["exit_rule"].get("prefer_stop_when_both", True))

    take_profit_price = resolve_take_profit_price(row=row, entry_open=entry_open, tp_rule=cfg.get("take_profit_rule", {}))
    highest_high = entry_open

    q = q.sort_values("date").reset_index(drop=True)
    for i, day in q.iterrows():
        day_high = float(day["high"]) if pd.notna(day["high"]) else np.nan
        day_low = float(day["low"]) if pd.notna(day["low"]) else np.nan
        day_close = float(day["close"]) if pd.notna(day["close"]) else np.nan
        day_date = day["date"].strftime("%Y-%m-%d")

        if pd.notna(day_high):
            highest_high = max(highest_high, day_high)

        effective_stop = fixed_stop
        if trailing_stop_pct is not None:
            trailing_stop = highest_high * (1.0 - trailing_stop_pct)
            effective_stop = max(effective_stop, trailing_stop)

        hit_sl = pd.notna(day_low) and day_low <= effective_stop
        hit_tp = (take_profit_price is not None) and pd.notna(day_high) and day_high >= take_profit_price

        if hit_sl and hit_tp:
            if prefer_stop_when_both:
                exit_reason = "both_hit_same_day_stop_first"
                exit_price = effective_stop
            else:
                exit_reason = "both_hit_same_day_target_first"
                exit_price = take_profit_price
            pnl_amount = (exit_price - entry_open) * shares_bought
            pnl_per_lot = (exit_price - entry_open) * shares_per_lot
            ret = (exit_price / entry_open - 1.0) * 100.0
            return {
                **base,
                "status": "sold",
                "entry_reason": entry_reason,
                "exit_reason": exit_reason,
                "exit_date": day_date,
                "entry_open": entry_open,
                "exit_price": exit_price,
                "stop_price": effective_stop,
                "take_profit_price": take_profit_price,
                "shares_bought": shares_bought,
                "capital_used": capital_used,
                "pnl_amount": pnl_amount,
                "pnl_per_lot": pnl_per_lot,
                "return_pct": ret,
            }

        if hit_sl:
            exit_price = effective_stop
            pnl_amount = (exit_price - entry_open) * shares_bought
            pnl_per_lot = (exit_price - entry_open) * shares_per_lot
            ret = (exit_price / entry_open - 1.0) * 100.0
            return {
                **base,
                "status": "sold",
                "entry_reason": entry_reason,
                "exit_reason": "stop_loss",
                "exit_date": day_date,
                "entry_open": entry_open,
                "exit_price": exit_price,
                "stop_price": effective_stop,
                "take_profit_price": take_profit_price,
                "shares_bought": shares_bought,
                "capital_used": capital_used,
                "pnl_amount": pnl_amount,
                "pnl_per_lot": pnl_per_lot,
                "return_pct": ret,
            }

        if hit_tp:
            exit_price = take_profit_price
            pnl_amount = (exit_price - entry_open) * shares_bought
            pnl_per_lot = (exit_price - entry_open) * shares_per_lot
            ret = (exit_price / entry_open - 1.0) * 100.0
            return {
                **base,
                "status": "sold",
                "entry_reason": entry_reason,
                "exit_reason": "hit_target_price",
                "exit_date": day_date,
                "entry_open": entry_open,
                "exit_price": exit_price,
                "stop_price": effective_stop,
                "take_profit_price": take_profit_price,
                "shares_bought": shares_bought,
                "capital_used": capital_used,
                "pnl_amount": pnl_amount,
                "pnl_per_lot": pnl_per_lot,
                "return_pct": ret,
            }

        if (max_hold_days is not None) and (i + 1 >= max_hold_days):
            exit_price = day_close
            pnl_amount = (exit_price - entry_open) * shares_bought
            pnl_per_lot = (exit_price - entry_open) * shares_per_lot
            ret = (exit_price / entry_open - 1.0) * 100.0
            return {
                **base,
                "status": "sold",
                "entry_reason": entry_reason,
                "exit_reason": f"time_stop_{max_hold_days}d",
                "exit_date": day_date,
                "entry_open": entry_open,
                "exit_price": exit_price,
                "stop_price": effective_stop,
                "take_profit_price": take_profit_price,
                "shares_bought": shares_bought,
                "capital_used": capital_used,
                "pnl_amount": pnl_amount,
                "pnl_per_lot": pnl_per_lot,
                "return_pct": ret,
            }

    last = q.tail(1).iloc[0]
    last_close = float(last["close"]) if pd.notna(last["close"]) else np.nan
    last_date = last["date"].strftime("%Y-%m-%d")
    pnl_amount = (last_close - entry_open) * shares_bought if pd.notna(last_close) else np.nan
    pnl_per_lot = (last_close - entry_open) * shares_per_lot if pd.notna(last_close) else np.nan
    ret = (last_close / entry_open - 1.0) * 100.0 if pd.notna(last_close) and entry_open != 0 else np.nan
    return {
        **base,
        "status": "open_until_end",
        "entry_reason": entry_reason,
        "exit_reason": "not_hit_until_end",
        "exit_date": last_date,
        "entry_open": entry_open,
        "exit_price": last_close,
        "take_profit_price": take_profit_price,
        "shares_bought": shares_bought,
        "capital_used": capital_used,
        "pnl_amount": pnl_amount,
        "pnl_per_lot": pnl_per_lot,
        "return_pct": ret,
    }


def run_one_strategy(config_path: Path, candidates_path: Path, quotes_cache_path: Path, entry_date: str, end_date: str) -> dict:
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    out_dir = config_path.parent / "results"
    out_dir.mkdir(parents=True, exist_ok=True)

    candidates = pd.read_csv(candidates_path)
    candidates["symbol"] = candidates["symbol"].astype(str).str.strip()
    quotes = normalize_quotes(pd.read_csv(quotes_cache_path))

    entry_dt = pd.to_datetime(entry_date)
    end_dt = pd.to_datetime(end_date)

    rows = []
    for _, row in candidates.iterrows():
        rows.append(simulate_one(row=row, quote_df=quotes, entry_date=entry_dt, end_date=end_dt, cfg=cfg))

    out = pd.DataFrame(rows)
    num_cols = out.select_dtypes(include=["number"]).columns.tolist()
    if num_cols:
        out[num_cols] = out[num_cols].round(2)

    sold = out[out["status"] == "sold"].copy()
    open_until_end = out[out["status"] == "open_until_end"].copy()
    skipped = out[out["status"] == "skipped"].copy()

    total_capital = float(sold["capital_used"].sum()) if not sold.empty and "capital_used" in sold.columns else 0.0
    total_revenue = float(sold["pnl_amount"].sum()) if not sold.empty and "pnl_amount" in sold.columns else 0.0
    return_percent = (total_revenue / total_capital * 100.0) if total_capital > 0 else 0.0

    summary = {
        "strategy_name": cfg["strategy_name"],
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
        "total_revenue(損益)": round(total_revenue, 2),
        "return_percent": round(return_percent, 4),
    }

    all_path = out_dir / "trade_backtest_20251013_1120_all.csv"
    sold_path = out_dir / "trade_backtest_20251013_1120_sold.csv"
    open_path = out_dir / "trade_backtest_20251013_1120_open_until_end.csv"
    summary_path = out_dir / "trade_backtest_20251013_1120_summary.json"

    out.to_csv(all_path, index=False)
    sold.to_csv(sold_path, index=False)
    open_until_end.to_csv(open_path, index=False)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "config": str(config_path),
        "summary": summary,
        "all_path": str(all_path),
        "summary_path": str(summary_path),
    }


def main() -> None:
    args = parse_args()
    result = run_one_strategy(
        config_path=args.config,
        candidates_path=args.candidates,
        quotes_cache_path=args.quotes_cache,
        entry_date=args.entry_date,
        end_date=args.end_date,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
