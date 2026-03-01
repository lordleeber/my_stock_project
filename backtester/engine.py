from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd

try:
    from backtester.data_loader import next_trading_day
except ModuleNotFoundError:
    from data_loader import next_trading_day


@dataclass
class CostConfig:
    commission_rate: float = 0.001425
    commission_discount: float = 1.0
    tax_rate: float = 0.003
    min_commission: float | None = None
    entry_slippage_bps: float = 0.0
    exit_slippage_bps: float = 0.0


def _apply_slippage(price: float, bps: float, side: str) -> float:
    if np.isnan(price):
        return price
    if side == "buy":
        return float(price * (1.0 + bps / 10000.0))
    return float(price * (1.0 - bps / 10000.0))


def _commission(notional: float, cost: CostConfig) -> float:
    fee = float(notional) * float(cost.commission_rate) * float(cost.commission_discount)
    if cost.min_commission is not None:
        fee = max(fee, float(cost.min_commission))
    return float(fee)


def _transaction_cost(entry_price: float, exit_price: float, shares: int, cost: CostConfig) -> dict[str, float]:
    buy_notional = float(entry_price) * int(shares)
    sell_notional = float(exit_price) * int(shares)
    buy_fee = _commission(buy_notional, cost)
    sell_fee = _commission(sell_notional, cost)
    sell_tax = sell_notional * float(cost.tax_rate)
    total_cost = buy_fee + sell_fee + sell_tax
    return {
        "buy_notional": buy_notional,
        "sell_notional": sell_notional,
        "buy_fee": buy_fee,
        "sell_fee": sell_fee,
        "sell_tax": sell_tax,
        "total_cost": total_cost,
    }


def build_position_size(entry_open: float, max_position_amount: float, shares_per_lot: int) -> tuple[int, float]:
    lot_cost = float(entry_open) * int(shares_per_lot)
    if lot_cost <= float(max_position_amount):
        shares = int(shares_per_lot)
    else:
        shares = int(float(max_position_amount) // float(entry_open))
        shares = max(shares, 1)
    return shares, float(shares * float(entry_open))


def check_entry_allowed(row: pd.Series, entry_open: float, entry_rule: dict[str, Any]) -> tuple[bool, str]:
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


def resolve_take_profit_price(row: pd.Series, entry_open: float, tp_rule: dict[str, Any]) -> float | None:
    tp_type = tp_rule.get("type", "target_price")
    if tp_type == "target_price":
        v = float(row.get("predict_target_price", np.nan))
        return None if np.isnan(v) else v

    if tp_type == "fixed_pct":
        pct = float(tp_rule.get("pct", 0.0))
        return float(entry_open * (1.0 + pct))

    if tp_type == "target_price_if_above_entry":
        v = float(row.get("predict_target_price", np.nan))
        if np.isnan(v) or v <= entry_open:
            return None
        return v

    return None


def get_nth_trading_day_after(
    quotes: pd.DataFrame,
    entry_date: pd.Timestamp,
    n: int,
) -> tuple[pd.Timestamp | None, pd.Timestamp | None]:
    if quotes.empty:
        return None, None
    trading_dates = sorted(quotes["date"].dropna().unique())
    future_dates = [d for d in trading_dates if d >= entry_date]
    if not future_dates:
        return None, None
    actual_entry = pd.Timestamp(future_dates[0])
    if len(future_dates) <= n:
        actual_end = pd.Timestamp(future_dates[-1])
    else:
        actual_end = pd.Timestamp(future_dates[n])
    return actual_entry, actual_end


def _result_base(
    row: pd.Series,
    cfg: dict[str, Any],
    cost: CostConfig,
    signal_entry_date: pd.Timestamp,
) -> dict[str, Any]:
    return {
        "symbol": str(row.get("symbol", "")).strip(),
        "strategy_name": str(cfg.get("strategy_name", "unknown")),
        "signal_entry_date": signal_entry_date.strftime("%Y-%m-%d"),
        "target_price": float(row.get("predict_target_price", np.nan)),
        "cost_config": asdict(cost),
    }


def simulate_one_trade(
    row: pd.Series,
    quote_df: pd.DataFrame,
    cfg: dict[str, Any],
    *,
    cost: CostConfig | None = None,
) -> dict[str, Any]:
    cost = cost or CostConfig()
    symbol = str(row.get("symbol", "")).strip()
    signal_entry_raw = row.get("entry_date")
    signal_entry_dt = pd.to_datetime(signal_entry_raw, errors="coerce")
    if pd.isna(signal_entry_dt):
        return {
            **_result_base(row, cfg, cost, pd.Timestamp("1970-01-01")),
            "status": "invalid_signal",
            "exit_reason": "invalid_entry_date",
        }

    base = _result_base(row, cfg, cost, signal_entry_dt)
    sym_quotes = quote_df[quote_df["symbol"].astype(str).str.strip() == symbol].copy()
    if sym_quotes.empty:
        return {**base, "status": "no_quote_for_symbol", "exit_reason": "no_quote_for_symbol"}

    sym_quotes = sym_quotes.sort_values("date").reset_index(drop=True)
    actual_entry_dt = next_trading_day(sym_quotes, on_or_after=signal_entry_dt, symbol=symbol)
    if actual_entry_dt is None:
        return {**base, "status": "no_quote_in_window", "exit_reason": "no_quote_in_window"}

    max_hold_days = int(cfg.get("exit_rule", {}).get("max_hold_days", 20))
    _, end_dt = get_nth_trading_day_after(sym_quotes, actual_entry_dt, n=max_hold_days)
    if end_dt is None:
        return {**base, "status": "no_quote_in_window", "exit_reason": "no_quote_in_window"}

    q = sym_quotes[(sym_quotes["date"] >= actual_entry_dt) & (sym_quotes["date"] <= end_dt)].copy()
    if q.empty:
        return {**base, "status": "no_quote_in_window", "exit_reason": "no_quote_in_window"}

    entry_rows = q[q["date"] == actual_entry_dt]
    if entry_rows.empty or pd.isna(entry_rows.iloc[0]["open"]):
        return {**base, "status": "no_entry_open", "exit_reason": "no_entry_open"}

    entry_open_raw = float(entry_rows.iloc[0]["open"])
    entry_ok, entry_reason = check_entry_allowed(row, entry_open_raw, cfg.get("entry_rule", {}))
    if not entry_ok:
        return {
            **base,
            "status": "skipped",
            "exit_reason": entry_reason,
            "actual_entry_date": actual_entry_dt.strftime("%Y-%m-%d"),
            "entry_open_raw": entry_open_raw,
        }

    entry_open = _apply_slippage(entry_open_raw, cost.entry_slippage_bps, "buy")
    shares_per_lot = int(cfg.get("position", {}).get("shares_per_lot", 1000))
    max_position_amount = float(cfg.get("position", {}).get("max_position_amount", 200000.0))
    shares_bought, capital_used = build_position_size(entry_open, max_position_amount, shares_per_lot)

    stop_loss_pct = float(cfg.get("exit_rule", {}).get("stop_loss_pct", 0.05))
    fixed_stop = entry_open_raw * (1.0 - stop_loss_pct)
    trailing_stop_pct = cfg.get("exit_rule", {}).get("trailing_stop_pct")
    trailing_stop_pct = None if trailing_stop_pct is None else float(trailing_stop_pct)
    prefer_stop_when_both = bool(cfg.get("exit_rule", {}).get("prefer_stop_when_both", True))

    take_profit_price = resolve_take_profit_price(row, entry_open_raw, cfg.get("take_profit_rule", {}))
    highest_high = entry_open_raw

    exit_price_raw = np.nan
    exit_reason = "end_of_window"
    exit_date = pd.Timestamp(q.iloc[-1]["date"])

    q = q.sort_values("date").reset_index(drop=True)
    for i, day in q.iterrows():
        day_high = float(day["high"]) if pd.notna(day["high"]) else np.nan
        day_low = float(day["low"]) if pd.notna(day["low"]) else np.nan
        day_close = float(day["close"]) if pd.notna(day["close"]) else np.nan
        day_date = pd.Timestamp(day["date"])

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
                exit_price_raw = effective_stop
            else:
                exit_reason = "both_hit_same_day_target_first"
                exit_price_raw = float(take_profit_price)
            exit_date = day_date
            break
        if hit_sl:
            exit_reason = "stop_loss"
            exit_price_raw = effective_stop
            exit_date = day_date
            break
        if hit_tp:
            exit_reason = "hit_target_price"
            exit_price_raw = float(take_profit_price)
            exit_date = day_date
            break

        if i + 1 >= max_hold_days:
            exit_reason = f"time_stop_{max_hold_days}d"
            exit_price_raw = day_close
            exit_date = day_date
            break

    if np.isnan(exit_price_raw):
        # Close at the end of available window.
        last = q.iloc[-1]
        exit_price_raw = float(last["close"]) if pd.notna(last["close"]) else np.nan
        exit_date = pd.Timestamp(last["date"])
        exit_reason = "end_of_window"

    exit_price = _apply_slippage(exit_price_raw, cost.exit_slippage_bps, "sell")
    tx_cost = _transaction_cost(entry_open, exit_price, shares_bought, cost)
    gross_pnl = (exit_price - entry_open) * shares_bought
    net_pnl = gross_pnl - tx_cost["total_cost"]
    capital_with_buy_fee = tx_cost["buy_notional"] + tx_cost["buy_fee"]
    ret_pct_gross = (gross_pnl / tx_cost["buy_notional"] * 100.0) if tx_cost["buy_notional"] > 0 else np.nan
    ret_pct_net = (net_pnl / capital_with_buy_fee * 100.0) if capital_with_buy_fee > 0 else np.nan

    return {
        **base,
        "status": "closed",
        "entry_reason": entry_reason,
        "exit_reason": exit_reason,
        "actual_entry_date": actual_entry_dt.strftime("%Y-%m-%d"),
        "exit_date": exit_date.strftime("%Y-%m-%d"),
        "window_end_date": end_dt.strftime("%Y-%m-%d"),
        "entry_open_raw": float(entry_open_raw),
        "entry_open_exec": float(entry_open),
        "exit_price_raw": float(exit_price_raw),
        "exit_price_exec": float(exit_price),
        "take_profit_price_raw": None if take_profit_price is None else float(take_profit_price),
        "shares_bought": int(shares_bought),
        "shares_per_lot": int(shares_per_lot),
        "capital_used": float(capital_used),
        "buy_notional": float(tx_cost["buy_notional"]),
        "sell_notional": float(tx_cost["sell_notional"]),
        "buy_fee": float(tx_cost["buy_fee"]),
        "sell_fee": float(tx_cost["sell_fee"]),
        "sell_tax": float(tx_cost["sell_tax"]),
        "total_cost": float(tx_cost["total_cost"]),
        "pnl_amount_gross": float(gross_pnl),
        "pnl_amount_net": float(net_pnl),
        "return_pct_gross": float(ret_pct_gross),
        "return_pct_net": float(ret_pct_net),
    }
