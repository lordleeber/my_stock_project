import json
from dataclasses import dataclass
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis_randomForest.trading_filter.strategy_fusion.v2_selector_backtest import (  # noqa: E402
    load_strategy_strength,
    pick_top_strategies,
    select_by_votes,
)


BASE_DIR = Path(__file__).resolve().parent
CACHE_DIR = BASE_DIR / "daily_cache_20251009_1120"
UNIVERSE_PATH = ROOT / "analysis_randomForest" / "trading_filter" / "trade_candidates_2025_1013_1120.csv"
BEST_CFG_PATH = (
    ROOT / "analysis_randomForest" / "trading_filter" / "strategy_fusion" / "results_v2" / "optuna_v2_best_config.json"
)
OUT_DIR = BASE_DIR / "sim_20251009_1120"


@dataclass
class Position:
    symbol: str
    name: str
    industry: str
    entry_date: str
    entry_price: float
    shares: int
    capital_used: float
    highest_high: float
    holding_days: int
    target_price: float
    status: str = "open"


def list_trading_dates(cache_dir: Path) -> list[str]:
    files = sorted(cache_dir.glob("quotes_*.csv"))
    dates = []
    for f in files:
        tag = f.stem.replace("quotes_", "")
        if len(tag) == 8:
            dates.append(f"{tag[:4]}-{tag[4:6]}-{tag[6:8]}")
    return dates


def load_day_quotes(cache_dir: Path, date_str: str) -> pd.DataFrame:
    tag = date_str.replace("-", "")
    p = cache_dir / f"quotes_{tag}.csv"
    if not p.exists():
        return pd.DataFrame(columns=["date", "symbol", "open", "high", "low", "close", "volume"])
    q = pd.read_csv(p)
    q["symbol"] = q["symbol"].astype(str).str.strip()
    for c in ["open", "high", "low", "close", "volume"]:
        if c in q.columns:
            q[c] = pd.to_numeric(q[c], errors="coerce")
    return q


def calc_shares(entry_open: float, max_position_amount: float, shares_per_lot: int) -> int:
    lot_cost = entry_open * shares_per_lot
    if lot_cost <= max_position_amount:
        return shares_per_lot
    return max(int(max_position_amount // entry_open), 1)


def build_day_candidates(universe: pd.DataFrame, day_quotes: pd.DataFrame) -> pd.DataFrame:
    if day_quotes.empty:
        return universe.head(0).copy()
    q = day_quotes[["symbol", "date", "close", "volume"]].copy()
    q = q.rename(columns={"date": "trade_date"})
    out = universe.merge(q, on="symbol", how="inner", suffixes=("", "_day"))
    if "volume_day" in out.columns:
        out["volume"] = pd.to_numeric(out["volume_day"], errors="coerce")
    else:
        out["volume"] = pd.to_numeric(out.get("volume", np.nan), errors="coerce")
    if "close_day" in out.columns:
        out["close"] = pd.to_numeric(out["close_day"], errors="coerce")
    else:
        out["close"] = pd.to_numeric(out.get("close", np.nan), errors="coerce")
    out["volume_lots"] = out["volume"] / 1000.0
    return out


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    universe = pd.read_csv(UNIVERSE_PATH)
    universe["symbol"] = universe["symbol"].astype(str).str.strip()
    universe["predict_target_price"] = pd.to_numeric(universe["predict_target_price"], errors="coerce")
    universe["pred_rf_delta"] = pd.to_numeric(universe["pred_rf_delta"], errors="coerce")
    universe["pred_delta_std"] = pd.to_numeric(universe["pred_delta_std"], errors="coerce")
    universe = universe.dropna(subset=["predict_target_price", "pred_rf_delta", "pred_delta_std"]).copy()

    best = json.loads(BEST_CFG_PATH.read_text(encoding="utf-8"))
    top_k = int(best.get("top_k_strategies", 3))
    min_strategy_entered = int(best.get("min_strategy_entered", 20))
    min_votes = int(best.get("min_votes", 2))
    max_picks = int(best.get("max_picks", 20))
    max_per_industry = int(best.get("max_per_industry", 8))
    max_position_amount = float(best.get("max_position_amount", 200000.0))
    shares_per_lot = int(best.get("shares_per_lot", 1000))
    stop_loss_pct = float(best.get("stop_loss_pct", 0.11))
    trailing_stop_pct = float(best.get("trailing_stop_pct", 0.06))
    max_hold_days = int(best.get("max_hold_days", 15))

    strength = load_strategy_strength()
    top_strategies = pick_top_strategies(strength, top_k=top_k, min_entered=min_strategy_entered)

    dates = list_trading_dates(CACHE_DIR)
    if not dates:
        raise SystemExit("No cached daily files found.")

    positions: dict[str, Position] = {}
    pending_orders: list[dict] = []
    order_rows: list[dict] = []
    exec_rows: list[dict] = []

    realized_pnl = 0.0
    total_buy_capital = 0.0

    for i, d in enumerate(dates):
        day_quotes = load_day_quotes(CACHE_DIR, d)
        quote_map = {r["symbol"]: r for _, r in day_quotes.iterrows()}

        # 1) 先執行今天開盤單（由前一日訊號產生）
        today_orders = [o for o in pending_orders if o["exec_date"] == d]
        pending_orders = [o for o in pending_orders if o["exec_date"] != d]
        for od in today_orders:
            symbol = od["symbol"]
            q = quote_map.get(symbol)
            if q is None or pd.isna(q.get("open")):
                od2 = dict(od)
                od2["status"] = "cancel_no_open"
                exec_rows.append(od2)
                continue
            open_px = float(q["open"])
            if od["side"] == "buy":
                if symbol in positions and positions[symbol].status == "open":
                    od2 = dict(od)
                    od2["status"] = "skip_already_held"
                    exec_rows.append(od2)
                    continue
                shares = calc_shares(open_px, max_position_amount, shares_per_lot)
                cap = shares * open_px
                total_buy_capital += cap
                positions[symbol] = Position(
                    symbol=symbol,
                    name=str(od.get("name", "")),
                    industry=str(od.get("industry", "")),
                    entry_date=d,
                    entry_price=open_px,
                    shares=shares,
                    capital_used=cap,
                    highest_high=open_px,
                    holding_days=0,
                    target_price=float(od.get("target_price", np.nan)),
                )
                ex = dict(od)
                ex.update(
                    {
                        "status": "filled",
                        "fill_price": round(open_px, 4),
                        "shares": shares,
                        "capital_used": round(cap, 2),
                    }
                )
                exec_rows.append(ex)
            else:
                pos = positions.get(symbol)
                if pos is None or pos.status != "open":
                    od2 = dict(od)
                    od2["status"] = "skip_not_held"
                    exec_rows.append(od2)
                    continue
                pnl = (open_px - pos.entry_price) * pos.shares
                realized_pnl += pnl
                pos.status = "closed"
                ex = dict(od)
                ex.update(
                    {
                        "status": "filled",
                        "fill_price": round(open_px, 4),
                        "shares": pos.shares,
                        "capital_used": round(pos.capital_used, 2),
                        "pnl_amount": round(pnl, 2),
                        "return_pct": round((open_px / pos.entry_price - 1.0) * 100.0, 4),
                    }
                )
                exec_rows.append(ex)

        # 2) 當日訊號 -> 下到下一個交易日開盤
        next_date = dates[i + 1] if i + 1 < len(dates) else None
        if next_date is None or day_quotes.empty:
            continue

        day_candidates = build_day_candidates(universe, day_quotes)
        if not day_candidates.empty:
            selected = select_by_votes(
                candidates=day_candidates,
                selected_strategies=top_strategies,
                min_votes=min_votes,
                max_picks=max_picks,
                max_per_industry=max_per_industry,
            )
        else:
            selected = day_candidates

        selected_symbols = set(selected["symbol"].astype(str).tolist()) if not selected.empty else set()

        # 2a) buy signal: 在選股名單、且目前未持有
        for _, r in selected.iterrows():
            symbol = str(r["symbol"]).strip()
            pos = positions.get(symbol)
            if pos is not None and pos.status == "open":
                continue
            od = {
                "signal_date": d,
                "exec_date": next_date,
                "side": "buy",
                "symbol": symbol,
                "name": str(r.get("name", "")),
                "industry": str(r.get("industry", "")),
                "target_price": float(r.get("predict_target_price", np.nan)),
                "reason": "model_buy_signal",
            }
            pending_orders.append(od)
            order_rows.append(od)

        # 2b) sell signal: 持倉且達出場條件
        for symbol, pos in list(positions.items()):
            if pos.status != "open":
                continue
            q = quote_map.get(symbol)
            if q is None:
                continue
            day_high = float(q["high"]) if pd.notna(q.get("high")) else pos.highest_high
            day_low = float(q["low"]) if pd.notna(q.get("low")) else pos.entry_price
            pos.highest_high = max(pos.highest_high, day_high)
            pos.holding_days += 1

            fixed_stop = pos.entry_price * (1.0 - stop_loss_pct)
            trailing_stop = pos.highest_high * (1.0 - trailing_stop_pct)
            effective_stop = max(fixed_stop, trailing_stop)

            hit_target = pd.notna(pos.target_price) and day_high >= pos.target_price
            hit_stop = day_low <= effective_stop
            hit_time = pos.holding_days >= max_hold_days
            if not (hit_target or hit_stop or hit_time):
                continue

            reason = "hit_target_price" if hit_target else ("stop_loss_or_trailing" if hit_stop else f"time_stop_{max_hold_days}d")
            od = {
                "signal_date": d,
                "exec_date": next_date,
                "side": "sell",
                "symbol": symbol,
                "reason": reason,
            }
            # 避免同檔同日重複掛賣單
            dup = any((x["exec_date"] == next_date and x["side"] == "sell" and x["symbol"] == symbol) for x in pending_orders)
            if not dup:
                pending_orders.append(od)
                order_rows.append(od)

    # 到期未平倉：用最後一天 close 做 MTM
    last_date = dates[-1]
    last_quotes = load_day_quotes(CACHE_DIR, last_date)
    last_map = {r["symbol"]: r for _, r in last_quotes.iterrows()}
    unrealized = 0.0
    open_count = 0
    for symbol, pos in positions.items():
        if pos.status != "open":
            continue
        q = last_map.get(symbol)
        if q is None or pd.isna(q.get("close")):
            continue
        close_px = float(q["close"])
        unrealized += (close_px - pos.entry_price) * pos.shares
        open_count += 1

    total_pnl_mtm = realized_pnl + unrealized
    return_pct_on_buy_capital = (total_pnl_mtm / total_buy_capital * 100.0) if total_buy_capital > 0 else 0.0

    orders_df = pd.DataFrame(order_rows)
    exec_df = pd.DataFrame(exec_rows)
    pos_rows = []
    for p in positions.values():
        pos_rows.append(
            {
                "symbol": p.symbol,
                "name": p.name,
                "industry": p.industry,
                "entry_date": p.entry_date,
                "entry_price": round(p.entry_price, 4),
                "shares": p.shares,
                "capital_used": round(p.capital_used, 2),
                "highest_high": round(p.highest_high, 4),
                "holding_days": p.holding_days,
                "target_price": round(p.target_price, 4) if pd.notna(p.target_price) else np.nan,
                "status": p.status,
            }
        )
    pos_df = pd.DataFrame(pos_rows).sort_values(["status", "symbol"]).reset_index(drop=True)

    orders_path = OUT_DIR / "orders_signal_20251009_1120.csv"
    exec_path = OUT_DIR / "orders_execution_20251009_1120.csv"
    pos_path = OUT_DIR / "positions_end_20251120.csv"
    summary_path = OUT_DIR / "simulation_summary_20251009_1120.json"

    orders_df.to_csv(orders_path, index=False, encoding="utf-8-sig")
    exec_df.to_csv(exec_path, index=False, encoding="utf-8-sig")
    pos_df.to_csv(pos_path, index=False, encoding="utf-8-sig")

    summary = {
        "period_start": dates[0],
        "period_end": dates[-1],
        "trading_days": len(dates),
        "top_strategies": top_strategies,
        "top_k_strategies": top_k,
        "min_votes": min_votes,
        "max_picks": max_picks,
        "max_per_industry": max_per_industry,
        "stop_loss_pct": stop_loss_pct,
        "trailing_stop_pct": trailing_stop_pct,
        "max_hold_days": max_hold_days,
        "total_buy_capital": round(total_buy_capital, 2),
        "realized_pnl": round(realized_pnl, 2),
        "unrealized_pnl": round(unrealized, 2),
        "total_pnl_mtm": round(total_pnl_mtm, 2),
        "return_percent_on_buy_capital": round(return_pct_on_buy_capital, 4),
        "executed_buy_count": int((exec_df.get("side", pd.Series(dtype=str)) == "buy").sum()) if not exec_df.empty else 0,
        "executed_sell_count": int((exec_df.get("side", pd.Series(dtype=str)) == "sell").sum()) if not exec_df.empty else 0,
        "open_positions_end_count": int(open_count),
        "orders_signal_csv": str(orders_path),
        "orders_execution_csv": str(exec_path),
        "positions_end_csv": str(pos_path),
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("simulation done")
    print(f"- summary: {summary_path}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
