from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class BacktestConfig:
    start_date: str
    end_date: str
    force_exit_date: str
    no_pyramiding: bool = True
    max_position_amount: float = 200000.0
    shares_per_lot: int = 1000
    stop_loss_pct: float | None = None
    take_profit_pct: float | None = None
    trailing_stop_pct: float | None = None
    max_hold_days: int | None = None


def _calc_shares(entry_open: float, max_position_amount: float, shares_per_lot: int) -> int:
    lot_cost = entry_open * shares_per_lot
    if lot_cost <= max_position_amount:
        return int(shares_per_lot)
    return max(int(max_position_amount // entry_open), 1)


def _next_trade_date(calendar: list[pd.Timestamp], current: pd.Timestamp) -> pd.Timestamp | None:
    for d in calendar:
        if d > current:
            return d
    return None


def run_backtest(
    signals_df: pd.DataFrame,
    quotes_df: pd.DataFrame,
    cfg: BacktestConfig,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    # signals_df 需要欄位: symbol, signal_date, side(buy/sell), reason(optional)
    # quotes_df 需要欄位: date, symbol, open, high, low, close
    signals = signals_df.copy()
    quotes = quotes_df.copy()

    signals["symbol"] = signals["symbol"].astype(str).str.strip()
    signals["signal_date"] = pd.to_datetime(signals["signal_date"], errors="coerce")
    signals["side"] = signals["side"].astype(str).str.lower().str.strip()
    signals = signals.dropna(subset=["symbol", "signal_date", "side"]).copy()

    quotes["symbol"] = quotes["symbol"].astype(str).str.strip()
    quotes["date"] = pd.to_datetime(quotes["date"], errors="coerce")
    for c in ["open", "high", "low", "close"]:
        quotes[c] = pd.to_numeric(quotes[c], errors="coerce")
    quotes = quotes.dropna(subset=["date", "symbol", "open", "high", "low", "close"]).copy()
    quotes = quotes.sort_values(["date", "symbol"]).reset_index(drop=True)

    start_dt = pd.to_datetime(cfg.start_date)
    end_dt = pd.to_datetime(cfg.end_date)
    force_exit_dt = pd.to_datetime(cfg.force_exit_date)

    quotes = quotes[(quotes["date"] >= start_dt) & (quotes["date"] <= end_dt)].copy()
    calendar = sorted(quotes["date"].dropna().unique().tolist())
    calendar = [pd.Timestamp(x) for x in calendar]
    if not calendar:
        summary = {
            "start_date": cfg.start_date,
            "end_date": cfg.end_date,
            "force_exit_date": cfg.force_exit_date,
            "trading_days": 0,
            "total_buy_capital": 0.0,
            "realized_pnl": 0.0,
            "return_percent": 0.0,
            "trade_count": 0,
            "win_count": 0,
            "loss_count": 0,
            "open_positions_end": 0,
        }
        return pd.DataFrame(), pd.DataFrame(), summary

    quote_map: dict[tuple[str, pd.Timestamp], dict[str, Any]] = {}
    for _, r in quotes.iterrows():
        quote_map[(str(r["symbol"]), pd.Timestamp(r["date"]))] = r.to_dict()

    pending_orders: list[dict[str, Any]] = []
    positions: dict[str, dict[str, Any]] = {}
    trades: list[dict[str, Any]] = []

    realized_pnl = 0.0
    total_buy_capital = 0.0

    for d in calendar:
        # 1) 執行當天開盤單（由前一日訊號觸發）
        today_orders = [o for o in pending_orders if o["exec_date"] == d]
        pending_orders = [o for o in pending_orders if o["exec_date"] != d]
        for od in today_orders:
            symbol = od["symbol"]
            q = quote_map.get((symbol, d))
            if q is None:
                continue
            fill_px = float(q["open"])
            side = od["side"]
            if side == "buy":
                if cfg.no_pyramiding and symbol in positions and positions[symbol]["status"] == "open":
                    continue
                shares = _calc_shares(fill_px, cfg.max_position_amount, cfg.shares_per_lot)
                cap = shares * fill_px
                total_buy_capital += cap
                positions[symbol] = {
                    "symbol": symbol,
                    "entry_date": d,
                    "entry_price": fill_px,
                    "shares": shares,
                    "capital_used": cap,
                    "highest_high": fill_px,
                    "holding_days": 0,
                    "status": "open",
                }
                trades.append(
                    {
                        "symbol": symbol,
                        "side": "buy",
                        "signal_date": od["signal_date"].strftime("%Y-%m-%d"),
                        "exec_date": d.strftime("%Y-%m-%d"),
                        "price": round(fill_px, 4),
                        "shares": shares,
                        "capital_used": round(cap, 2),
                        "reason": od.get("reason", "signal_buy"),
                    }
                )
            elif side == "sell":
                pos = positions.get(symbol)
                if pos is None or pos["status"] != "open":
                    continue
                pnl = (fill_px - float(pos["entry_price"])) * int(pos["shares"])
                realized_pnl += pnl
                pos["status"] = "closed"
                trades.append(
                    {
                        "symbol": symbol,
                        "side": "sell",
                        "signal_date": od["signal_date"].strftime("%Y-%m-%d"),
                        "exec_date": d.strftime("%Y-%m-%d"),
                        "price": round(fill_px, 4),
                        "shares": int(pos["shares"]),
                        "capital_used": round(float(pos["capital_used"]), 2),
                        "pnl_amount": round(pnl, 2),
                        "return_pct": round((fill_px / float(pos["entry_price"]) - 1.0) * 100.0, 4),
                        "reason": od.get("reason", "signal_sell"),
                    }
                )

        # 2) 收盤前判斷部位是否觸發風控，若觸發 -> 下一交易日開盤賣
        next_d = _next_trade_date(calendar, d)
        for symbol, pos in list(positions.items()):
            if pos["status"] != "open":
                continue
            q = quote_map.get((symbol, d))
            if q is None:
                continue
            day_high = float(q["high"])
            day_low = float(q["low"])
            pos["highest_high"] = max(float(pos["highest_high"]), day_high)
            pos["holding_days"] = int(pos["holding_days"]) + 1

            hit = False
            reason = None
            if cfg.take_profit_pct is not None:
                tp_price = float(pos["entry_price"]) * (1.0 + float(cfg.take_profit_pct))
                if day_high >= tp_price:
                    hit = True
                    reason = "take_profit_trigger"

            fixed_stop = None
            if cfg.stop_loss_pct is not None:
                fixed_stop = float(pos["entry_price"]) * (1.0 - float(cfg.stop_loss_pct))
            trail_stop = None
            if cfg.trailing_stop_pct is not None:
                trail_stop = float(pos["highest_high"]) * (1.0 - float(cfg.trailing_stop_pct))
            if fixed_stop is not None or trail_stop is not None:
                stops = [x for x in [fixed_stop, trail_stop] if x is not None]
                if stops:
                    effective_stop = max(stops)
                    if day_low <= effective_stop:
                        hit = True
                        reason = "stop_or_trailing_trigger"

            if cfg.max_hold_days is not None and int(pos["holding_days"]) >= int(cfg.max_hold_days):
                hit = True
                reason = f"time_stop_{int(cfg.max_hold_days)}d_trigger"

            if hit and next_d is not None:
                dup = any(
                    (x["side"] == "sell" and x["symbol"] == symbol and x["exec_date"] == next_d)
                    for x in pending_orders
                )
                if not dup:
                    pending_orders.append(
                        {
                            "symbol": symbol,
                            "side": "sell",
                            "signal_date": d,
                            "exec_date": next_d,
                            "reason": reason,
                        }
                    )

        # 3) 當日訊號 -> 下一交易日開盤生效
        day_sig = signals[signals["signal_date"] == d]
        if next_d is not None and not day_sig.empty:
            for _, s in day_sig.iterrows():
                symbol = str(s["symbol"])
                side = str(s["side"])
                if side == "buy" and cfg.no_pyramiding and symbol in positions and positions[symbol]["status"] == "open":
                    continue
                pending_orders.append(
                    {
                        "symbol": symbol,
                        "side": side,
                        "signal_date": d,
                        "exec_date": next_d,
                        "reason": s.get("reason", f"signal_{side}"),
                    }
                )

        # 4) 強制平倉：force_exit_date 以收盤價直接平倉
        if d == force_exit_dt:
            for symbol, pos in list(positions.items()):
                if pos["status"] != "open":
                    continue
                q = quote_map.get((symbol, d))
                if q is None:
                    continue
                close_px = float(q["close"])
                pnl = (close_px - float(pos["entry_price"])) * int(pos["shares"])
                realized_pnl += pnl
                pos["status"] = "closed_force"
                trades.append(
                    {
                        "symbol": symbol,
                        "side": "sell",
                        "signal_date": d.strftime("%Y-%m-%d"),
                        "exec_date": d.strftime("%Y-%m-%d"),
                        "price": round(close_px, 4),
                        "shares": int(pos["shares"]),
                        "capital_used": round(float(pos["capital_used"]), 2),
                        "pnl_amount": round(pnl, 2),
                        "return_pct": round((close_px / float(pos["entry_price"]) - 1.0) * 100.0, 4),
                        "reason": "force_exit_close",
                    }
                )

    positions_rows = []
    for symbol, p in positions.items():
        positions_rows.append(
            {
                "symbol": symbol,
                "entry_date": pd.Timestamp(p["entry_date"]).strftime("%Y-%m-%d"),
                "entry_price": round(float(p["entry_price"]), 4),
                "shares": int(p["shares"]),
                "capital_used": round(float(p["capital_used"]), 2),
                "highest_high": round(float(p["highest_high"]), 4),
                "holding_days": int(p["holding_days"]),
                "status": p["status"],
            }
        )

    trades_df = pd.DataFrame(trades)
    positions_df = pd.DataFrame(positions_rows)

    sell_df = trades_df[trades_df["side"] == "sell"].copy() if not trades_df.empty else pd.DataFrame()
    win_count = int((sell_df.get("pnl_amount", pd.Series(dtype=float)) > 0).sum()) if not sell_df.empty else 0
    loss_count = int((sell_df.get("pnl_amount", pd.Series(dtype=float)) < 0).sum()) if not sell_df.empty else 0
    return_pct = (realized_pnl / total_buy_capital * 100.0) if total_buy_capital > 0 else 0.0

    summary = {
        "start_date": cfg.start_date,
        "end_date": cfg.end_date,
        "force_exit_date": cfg.force_exit_date,
        "trading_days": len(calendar),
        "no_pyramiding": cfg.no_pyramiding,
        "total_buy_capital": round(float(total_buy_capital), 2),
        "realized_pnl": round(float(realized_pnl), 2),
        "return_percent": round(float(return_pct), 4),
        "trade_count": int(len(trades_df)),
        "sell_count": int(len(sell_df)),
        "win_count": win_count,
        "loss_count": loss_count,
        "open_positions_end": int((positions_df.get("status", pd.Series(dtype=str)) == "open").sum()) if not positions_df.empty else 0,
    }
    return trades_df, positions_df, summary
