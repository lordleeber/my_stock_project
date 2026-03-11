from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class CostConfig:
    commission_rate: float = 0.001425
    tax_rate: float = 0.003


def build_position_size(entry_open: float, max_position_amount: float, shares_per_lot: int) -> tuple[int, float]:
    # Use budget-based sizing; no fixed one-lot constraint.
    shares = int(max_position_amount // entry_open)
    shares = max(shares, 1)
    return shares, float(shares * entry_open)


def check_entry_allowed(row: pd.Series, entry_open: float, entry_rule: dict[str, Any]) -> tuple[bool, str]:
    rule_type = entry_rule.get("type", "all")
    if rule_type == "all":
        return False, "entry_rule_all_not_allowed"

    if rule_type == "target_above_entry_ratio":
        ratio = float(entry_rule.get("ratio", 1.0))
        target_price = float(row.get("predict_target_price", np.nan))
        if np.isnan(target_price):
            return False, "skip_no_target"
        return target_price >= entry_open * ratio, f"entry_target_ge_{ratio}"

    if rule_type == "pullback_from_ref_close":
        ratio = float(entry_rule.get("ratio", 1.0))
        ref_close = float(row.get("close", np.nan))
        if np.isnan(ref_close):
            return False, "skip_no_ref_close"
        return entry_open <= ref_close * ratio, f"entry_pullback_le_{ratio}"

    return True, "entry_unknown_rule_default_true"


def resolve_take_profit_price(row: pd.Series, entry_open: float, tp_rule: dict[str, Any]) -> float | None:
    tp_type = tp_rule.get("type", "target_price")
    if tp_type == "target_price":
        v = float(row.get("predict_target_price", np.nan))
        return None if np.isnan(v) else v
    if tp_type == "fixed_pct":
        return entry_open * (1.0 + float(tp_rule.get("pct", 0.0)))
    if tp_type == "target_price_if_above_entry":
        v = float(row.get("predict_target_price", np.nan))
        if np.isnan(v) or v <= entry_open:
            return None
        return v
    return None


def _cost_amount(entry_price: float, exit_price: float, shares: int, cost_cfg: CostConfig) -> float:
    buy = entry_price * shares
    sell = exit_price * shares
    commission = (buy + sell) * cost_cfg.commission_rate
    tax = sell * cost_cfg.tax_rate
    return float(commission + tax)


def simulate_one(
    row: pd.Series,
    quote_df: pd.DataFrame,
    strategy_name: str,
    entry_rule: dict[str, Any],
    take_profit_rule: dict[str, Any],
    exit_rule: dict[str, Any],
    cost_cfg: CostConfig,
    position_cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    symbol = str(row["symbol"]).strip()
    signal_entry_dt = pd.to_datetime(row["entry_date"])
    base = {
        "symbol": symbol,
        "strategy_name": strategy_name,
        "signal_entry_date": signal_entry_dt.strftime("%Y-%m-%d"),
        "target_price": float(row.get("predict_target_price", np.nan)),
    }

    sym_quotes = quote_df[quote_df["symbol"] == symbol].copy()
    sym_quotes = sym_quotes[sym_quotes["date"] >= signal_entry_dt].sort_values("date").reset_index(drop=True)
    if sym_quotes.empty:
        return {**base, "status": "no_quote_in_window", "exit_reason": "no_quote_in_window"}

    actual_entry_row = sym_quotes.iloc[0]
    actual_entry_dt = pd.to_datetime(actual_entry_row["date"])
    if actual_entry_dt < signal_entry_dt:
        return {
            **base,
            "status": "lookahead_violation",
            "exit_reason": "actual_entry_before_signal_entry",
            "actual_entry_date": actual_entry_dt.strftime("%Y-%m-%d"),
        }

    entry_open = float(actual_entry_row["open"]) if pd.notna(actual_entry_row["open"]) else np.nan
    if np.isnan(entry_open):
        return {**base, "status": "no_entry_open", "exit_reason": "no_entry_open", "actual_entry_date": actual_entry_dt.strftime("%Y-%m-%d")}

    entry_ok, entry_reason = check_entry_allowed(row=row, entry_open=entry_open, entry_rule=entry_rule)
    if not entry_ok:
        return {
            **base,
            "status": "skipped",
            "actual_entry_date": actual_entry_dt.strftime("%Y-%m-%d"),
            "exit_reason": entry_reason,
            "entry_price": entry_open,
        }

    pos = position_cfg or {"shares_per_lot": 1000, "max_position_amount": 200000}
    shares_per_lot = int(pos.get("shares_per_lot", 1000))
    max_position_amount = float(pos.get("max_position_amount", 200000))
    shares_bought, capital_used = build_position_size(entry_open, max_position_amount, shares_per_lot)

    stop_loss_pct = float(exit_rule.get("stop_loss_pct", 0.05))
    fixed_stop = entry_open * (1.0 - stop_loss_pct)
    trailing_stop_pct = exit_rule.get("trailing_stop_pct")
    trailing_stop_pct = None if trailing_stop_pct is None else float(trailing_stop_pct)
    max_hold_days = int(exit_rule.get("max_hold_days", 20))
    prefer_stop_when_both = bool(exit_rule.get("prefer_stop_when_both", True))
    take_profit_price = resolve_take_profit_price(row=row, entry_open=entry_open, tp_rule=take_profit_rule)
    highest_high = entry_open

    q = sym_quotes.reset_index(drop=True)
    for i, day in q.iterrows():
        day_high = float(day["high"]) if pd.notna(day["high"]) else np.nan
        day_low = float(day["low"]) if pd.notna(day["low"]) else np.nan
        day_close = float(day["close"]) if pd.notna(day["close"]) else np.nan
        day_date = pd.to_datetime(day["date"]).strftime("%Y-%m-%d")

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
                exit_price = float(take_profit_price)
            return _sold_row(
                base=base,
                entry_reason=entry_reason,
                actual_entry_dt=actual_entry_dt,
                entry_open=entry_open,
                exit_date=day_date,
                exit_price=exit_price,
                shares_bought=shares_bought,
                capital_used=capital_used,
                stop_price=effective_stop,
                take_profit_price=take_profit_price,
                exit_reason=exit_reason,
                cost_cfg=cost_cfg,
            )

        if hit_sl:
            return _sold_row(
                base=base,
                entry_reason=entry_reason,
                actual_entry_dt=actual_entry_dt,
                entry_open=entry_open,
                exit_date=day_date,
                exit_price=effective_stop,
                shares_bought=shares_bought,
                capital_used=capital_used,
                stop_price=effective_stop,
                take_profit_price=take_profit_price,
                exit_reason="stop_loss",
                cost_cfg=cost_cfg,
            )

        if hit_tp:
            return _sold_row(
                base=base,
                entry_reason=entry_reason,
                actual_entry_dt=actual_entry_dt,
                entry_open=entry_open,
                exit_date=day_date,
                exit_price=float(take_profit_price),
                shares_bought=shares_bought,
                capital_used=capital_used,
                stop_price=effective_stop,
                take_profit_price=take_profit_price,
                exit_reason="hit_target_price",
                cost_cfg=cost_cfg,
            )

        if i + 1 >= max_hold_days:
            exit_price = day_close
            return _sold_row(
                base=base,
                entry_reason=entry_reason,
                actual_entry_dt=actual_entry_dt,
                entry_open=entry_open,
                exit_date=day_date,
                exit_price=exit_price,
                shares_bought=shares_bought,
                capital_used=capital_used,
                stop_price=effective_stop,
                take_profit_price=take_profit_price,
                exit_reason=f"time_stop_{max_hold_days}d",
                cost_cfg=cost_cfg,
            )

    last = q.tail(1).iloc[0]
    last_close = float(last["close"]) if pd.notna(last["close"]) else np.nan
    last_date = pd.to_datetime(last["date"]).strftime("%Y-%m-%d")
    gross_pnl = (last_close - entry_open) * shares_bought if pd.notna(last_close) else np.nan
    total_cost = _cost_amount(entry_open, last_close, shares_bought, cost_cfg) if pd.notna(last_close) else np.nan
    net_pnl = gross_pnl - total_cost if pd.notna(gross_pnl) else np.nan
    net_return_pct = (net_pnl / capital_used * 100.0) if capital_used > 0 and pd.notna(net_pnl) else np.nan
    return {
        **base,
        "status": "open_until_end",
        "entry_reason": entry_reason,
        "actual_entry_date": actual_entry_dt.strftime("%Y-%m-%d"),
        "exit_reason": "not_hit_until_end",
        "exit_date": last_date,
        "entry_price": entry_open,
        "exit_price": last_close,
        "shares_bought": shares_bought,
        "capital_used": capital_used,
        "stop_price": np.nan,
        "take_profit_price": take_profit_price,
        "gross_pnl": gross_pnl,
        "total_cost": total_cost,
        "net_pnl": net_pnl,
        "return_pct": net_return_pct,
    }


def _sold_row(
    *,
    base: dict[str, Any],
    entry_reason: str,
    actual_entry_dt: pd.Timestamp,
    entry_open: float,
    exit_date: str,
    exit_price: float,
    shares_bought: int,
    capital_used: float,
    stop_price: float,
    take_profit_price: float | None,
    exit_reason: str,
    cost_cfg: CostConfig,
) -> dict[str, Any]:
    gross_pnl = (exit_price - entry_open) * shares_bought
    total_cost = _cost_amount(entry_open, exit_price, shares_bought, cost_cfg)
    net_pnl = gross_pnl - total_cost
    net_return_pct = (net_pnl / capital_used * 100.0) if capital_used > 0 else np.nan
    return {
        **base,
        "status": "sold",
        "entry_reason": entry_reason,
        "actual_entry_date": actual_entry_dt.strftime("%Y-%m-%d"),
        "exit_reason": exit_reason,
        "exit_date": exit_date,
        "entry_price": entry_open,
        "exit_price": exit_price,
        "shares_bought": shares_bought,
        "capital_used": capital_used,
        "stop_price": stop_price,
        "take_profit_price": take_profit_price,
        "gross_pnl": gross_pnl,
        "total_cost": total_cost,
        "net_pnl": net_pnl,
        "return_pct": net_return_pct,
    }


def aggregate_monthly(trades: pd.DataFrame) -> pd.DataFrame:
    sold = trades[trades["status"] == "sold"].copy()
    open_until_end = trades[trades["status"] == "open_until_end"].copy()
    skipped = trades[trades["status"] == "skipped"].copy()
    lookahead = trades[trades["status"] == "lookahead_violation"].copy()

    total_capital = float(sold["capital_used"].sum()) if not sold.empty else 0.0
    gross_pnl = float(sold["gross_pnl"].sum()) if not sold.empty else 0.0
    total_cost = float(sold["total_cost"].sum()) if not sold.empty else 0.0
    net_pnl = float(sold["net_pnl"].sum()) if not sold.empty else 0.0
    return_pct = (net_pnl / total_capital * 100.0) if total_capital > 0 else 0.0

    stop_loss_count = int((sold.get("exit_reason", pd.Series(dtype=str)) == "stop_loss").sum()) if not sold.empty else 0
    stop_loss_ratio = (stop_loss_count / len(sold)) if len(sold) > 0 else np.nan

    row = {
        "total_picks": int(len(trades)),
        "entered_count": int((trades["status"].isin(["sold", "open_until_end"])).sum()),
        "skipped_count": int(len(skipped)),
        "sold_count": int(len(sold)),
        "open_until_end_count": int(len(open_until_end)),
        "lookahead_violation_count": int(len(lookahead)),
        "sold_win_count": int((sold["net_pnl"] > 0).sum()) if not sold.empty else 0,
        "sold_loss_count": int((sold["net_pnl"] < 0).sum()) if not sold.empty else 0,
        "stop_loss_count": stop_loss_count,
        "stop_loss_ratio": round(float(stop_loss_ratio), 6) if np.isfinite(stop_loss_ratio) else np.nan,
        "total_capital": round(total_capital, 2),
        "gross_pnl": round(gross_pnl, 2),
        "total_cost": round(total_cost, 2),
        "net_pnl": round(net_pnl, 2),
        "return_pct": round(return_pct, 4),
    }
    return pd.DataFrame([row])


def build_equity_curve(trades: pd.DataFrame) -> pd.DataFrame:
    x = trades[trades["status"].isin(["sold", "open_until_end"])].copy()
    if x.empty:
        return pd.DataFrame(columns=["date", "daily_net_pnl", "cum_net_pnl"])
    x["date"] = pd.to_datetime(x["exit_date"], errors="coerce")
    x = x.dropna(subset=["date"]).copy()
    daily = x.groupby("date", as_index=False)["net_pnl"].sum().rename(columns={"net_pnl": "daily_net_pnl"})
    daily = daily.sort_values("date").reset_index(drop=True)
    daily["cum_net_pnl"] = daily["daily_net_pnl"].cumsum()
    daily["date"] = daily["date"].dt.strftime("%Y-%m-%d")
    return daily
