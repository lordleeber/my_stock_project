"""
Rolling monthly portfolio backtester (Method C).

Logic per month:
  1. Detect market regime (Bull / Sideways / Bear) as of entry_date.
  2. Bear regime → exit ALL current holdings, skip new entries.
  3. Bull / Sideways → normal rolling logic:
       - Stocks in portfolio but NOT in new candidates → exit at entry_date open.
       - Stocks in new candidates but NOT in portfolio → enter at entry_date open.
       - Stocks in both → continue holding, no transaction.
  - Position sizing: fixed amount per stock (default 100,000 TWD).
"""
from __future__ import annotations

import argparse
import json
import pickle
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backtester.data_loader import fetch_quotes_from_db
from backtester.simulator import CostConfig
from backtester.utils import month_iter, normalize_month
from train_eps import prepare_data as tp


@dataclass
class Position:
    symbol: str
    entry_date: str
    entry_price: float
    shares: int
    capital_used: float


def prev_trading_day(date_str: str) -> str:
    """Return the last trading day strictly before date_str."""
    stmt = text("SELECT MAX(date) FROM daily_quotes WHERE date < :d")
    try:
        engine = create_engine(tp.get_db_url())
        with engine.connect() as conn:
            result = conn.execute(stmt, {"d": date_str}).scalar()
        return str(result) if result else date_str
    except Exception:
        return date_str


def detect_market_regime(ref_date: str) -> str:
    """Return 'Bull', 'Bear', or 'Sideways' based on MA20/MA60 of market_indices up to ref_date."""
    stmt = text(
        """
        SELECT date, index_close
        FROM market_indices
        WHERE date <= :ref_date
        ORDER BY date ASC
        """
    )
    try:
        engine = create_engine(tp.get_db_url())
        with engine.connect() as conn:
            idx = pd.read_sql(stmt, conn, params={"ref_date": ref_date})
    except Exception as exc:
        print(f"[WARN] market regime query failed: {exc}")
        return "Sideways"

    if idx.empty:
        return "Sideways"

    idx["date"] = pd.to_datetime(idx["date"], errors="coerce")
    idx["index_close"] = pd.to_numeric(idx["index_close"], errors="coerce")
    idx = idx.dropna(subset=["date", "index_close"]).sort_values("date")
    if idx.empty:
        return "Sideways"

    daily = idx.groupby("date", as_index=False)["index_close"].mean().sort_values("date")
    daily["ma20"] = daily["index_close"].rolling(20, min_periods=10).mean()
    daily["ma60"] = daily["index_close"].rolling(60, min_periods=20).mean()
    latest = daily.iloc[-1]

    ma20 = float(latest.get("ma20", np.nan))
    ma60 = float(latest.get("ma60", np.nan))
    close = float(latest.get("index_close", np.nan))

    if np.isnan(ma20) or np.isnan(ma60):
        return "Sideways"
    if ma20 > ma60:
        return "Bull"
    if ma20 < ma60 and close < ma20:
        return "Bear"
    return "Sideways"


def resolve_model_for_month(models_root: Path, year: int, month: int) -> Path | None:
    """Return the model dir with the latest cutoff strictly before (year, month).
    Falls back to models_root/latest if no versioned model is found."""
    ym = year * 100 + month
    best: tuple[int, Path] | None = None

    for y_dir in sorted(models_root.iterdir()):
        if not y_dir.is_dir() or y_dir.name == "latest":
            continue
        try:
            y = int(y_dir.name)
        except ValueError:
            continue
        for m_dir in sorted(y_dir.iterdir()):
            if not m_dir.is_dir():
                continue
            try:
                m = int(m_dir.name)
            except ValueError:
                continue
            cutoff_ym = y * 100 + m
            if cutoff_ym < ym and (m_dir / "selection_model.pkl").exists():
                if best is None or cutoff_ym > best[0]:
                    best = (cutoff_ym, m_dir)

    if best:
        return best[1]
    latest = models_root / "latest"
    return latest if (latest / "selection_model.pkl").exists() else None


def score_dataset_strategy(ds: pd.DataFrame, model_dir: Path) -> pd.DataFrame:
    """Load model from model_dir and add ml_score column to ds."""
    model_path = model_dir / "selection_model.pkl"
    with open(model_path, "rb") as f:
        payload = pickle.load(f)
    model       = payload["model"]
    feature_cols = payload["feature_cols"]

    for c in feature_cols:
        if c not in ds.columns:
            ds[c] = 0.0
    X = ds[feature_cols].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    ds = ds.copy()
    ds["ml_score"] = model.predict(X)
    return ds


def load_candidates_safe(
    strategies_out: Path, year: int, month: int, models_root: Path
) -> pd.DataFrame | None:
    month_s  = normalize_month(month)
    ds_path  = strategies_out / f"{year:04d}" / month_s / "dataset_strategy.csv"

    if not ds_path.exists():
        return None

    df = pd.read_csv(ds_path)
    df["symbol"]     = df["symbol"].astype(str).str.strip()
    df["entry_date"] = pd.to_datetime(df.get("entry_date"), errors="coerce")
    df = df.dropna(subset=["symbol", "entry_date"])
    if df.empty:
        return None

    # Walk-forward scoring: use the latest model trained before this month.
    model_dir = resolve_model_for_month(models_root, year, month)
    if model_dir is not None:
        try:
            df = score_dataset_strategy(df, model_dir)
            df["_model_used"] = model_dir.name
        except Exception as exc:
            print(f"[WARN] scoring failed for {year}/{month_s}: {exc}")
    else:
        print(f"[WARN] no model found for {year}/{month_s}, falling back to pred_upside_pct")

    return df


def fetch_open_on_date(symbols: list[str], date_str: str) -> dict[str, float]:
    """Fetch open prices for symbols on a given date (with ±5-day buffer for holidays)."""
    if not symbols:
        return {}
    target = pd.to_datetime(date_str)
    buffer_start = (target - pd.Timedelta(days=5)).strftime("%Y-%m-%d")
    buffer_end = (target + pd.Timedelta(days=5)).strftime("%Y-%m-%d")
    try:
        quotes = fetch_quotes_from_db(symbols=symbols, start_date=buffer_start, end_date=buffer_end)
    except Exception as exc:
        print(f"[WARN] fetch_quotes failed for {date_str}: {exc}")
        return {}
    if quotes.empty:
        return {}
    # Use the closest trading day on or after target date.
    quotes = quotes[quotes["date"] >= target].sort_values("date")
    result: dict[str, float] = {}
    for sym, grp in quotes.groupby("symbol"):
        row = grp.iloc[0]
        if pd.notna(row.get("open")):
            result[str(sym).strip()] = float(row["open"])
    return result


def _cost(entry_price: float, exit_price: float, shares: int, cost_cfg: CostConfig) -> float:
    commission = (entry_price * shares + exit_price * shares) * cost_cfg.commission_rate
    tax = exit_price * shares * cost_cfg.tax_rate
    return commission + tax


def _exit_position(
    pos: Position,
    exit_date_str: str,
    exit_price: float | None,
    exit_reason: str,
    cost_cfg: CostConfig,
) -> tuple[dict, float]:
    """Build a trade log row for an exit. Returns (row_dict, net_pnl)."""
    if exit_price is None:
        return {
            "symbol": pos.symbol,
            "entry_date": pos.entry_date,
            "exit_date": exit_date_str,
            "entry_price": pos.entry_price,
            "exit_price": np.nan,
            "shares": pos.shares,
            "capital_used": pos.capital_used,
            "gross_pnl": np.nan,
            "cost": np.nan,
            "net_pnl": np.nan,
            "return_pct": np.nan,
            "exit_reason": "no_quote_on_exit",
        }, 0.0

    gross_pnl = (exit_price - pos.entry_price) * pos.shares
    cost = _cost(pos.entry_price, exit_price, pos.shares, cost_cfg)
    net_pnl = gross_pnl - cost
    return_pct = net_pnl / pos.capital_used * 100.0 if pos.capital_used > 0 else np.nan
    return {
        "symbol": pos.symbol,
        "entry_date": pos.entry_date,
        "exit_date": exit_date_str,
        "entry_price": pos.entry_price,
        "exit_price": exit_price,
        "shares": pos.shares,
        "capital_used": pos.capital_used,
        "gross_pnl": round(gross_pnl, 2),
        "cost": round(cost, 2),
        "net_pnl": round(net_pnl, 2),
        "return_pct": round(return_pct, 4),
        "exit_reason": exit_reason,
    }, net_pnl


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rolling monthly portfolio backtester.")
    parser.add_argument("--start_year", type=int, required=True)
    parser.add_argument("--start_month", type=int, required=True)
    parser.add_argument("--end_year", type=int, required=True)
    parser.add_argument("--end_month", type=int, required=True)
    parser.add_argument("--position-amount", type=float, default=100_000.0, help="Fixed TWD per position (default 100000)")
    parser.add_argument("--commission-rate", type=float, default=0.001425)
    parser.add_argument("--tax-rate", type=float, default=0.003)
    parser.add_argument("--top-n", type=int, default=None, help="Keep only top-N candidates by ml_score (default: no limit)")
    parser.add_argument("--models-root", type=Path, default=None, help="Root dir for selection models (default: models_selection/)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    strategies_out = (Path.cwd() / "strategies" / "output").resolve()
    out_dir = (Path.cwd() / "backtester" / "output" / "rolling").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    cost_cfg = CostConfig(commission_rate=args.commission_rate, tax_rate=args.tax_rate)
    position_amount = args.position_amount
    top_n = args.top_n
    models_root = (
        args.models_root if args.models_root
        else (Path.cwd() / "models_selection").resolve()
    )

    portfolio: dict[str, Position] = {}
    trade_log: list[dict] = []
    monthly_rows: list[dict] = []

    for year, month in month_iter(args.start_year, args.start_month, args.end_year, args.end_month):
        month_s = normalize_month(month)
        candidates_df = load_candidates_safe(strategies_out, year, month, models_root)
        if candidates_df is None:
            print(f"[skip] no candidates: {year}/{month_s}")
            continue

        # All candidates share the same entry_date (first trading day after release).
        entry_date_str = candidates_df["entry_date"].iloc[0].strftime("%Y-%m-%d")
        # Exits happen at the open of the trading day before entry_date.
        exit_date_str = prev_trading_day(entry_date_str)

        # Rank candidates: prefer ml_score if available, else pred_upside_pct.
        candidates_df = candidates_df.copy()
        if "ml_score" in candidates_df.columns:
            candidates_df = candidates_df.sort_values("ml_score", ascending=False)
        elif "predict_target_price" in candidates_df.columns and "close" in candidates_df.columns:
            candidates_df["pred_upside_pct"] = (
                pd.to_numeric(candidates_df["predict_target_price"], errors="coerce")
                - pd.to_numeric(candidates_df["close"], errors="coerce")
            ) / pd.to_numeric(candidates_df["close"], errors="coerce") * 100.0
            candidates_df = candidates_df.sort_values("pred_upside_pct", ascending=False)
        if top_n is not None:
            candidates_df = candidates_df.head(top_n)

        # --- Detect market regime ---
        regime = detect_market_regime(entry_date_str)
        is_bear = regime == "Bear"

        if is_bear:
            # Exit ALL current holdings; skip new entries.
            exit_symbols = sorted(portfolio.keys())
            entry_symbols: list[str] = []
        else:
            new_symbols = set(candidates_df["symbol"].tolist())
            current_symbols = set(portfolio.keys())
            exit_symbols = sorted(current_symbols - new_symbols)
            entry_symbols = sorted(new_symbols - current_symbols)

        # Fetch exit prices at prev trading day; entry prices at entry_date.
        exit_open_prices  = fetch_open_on_date(exit_symbols,  exit_date_str)
        entry_open_prices = fetch_open_on_date(entry_symbols, entry_date_str)

        # --- Process exits ---
        month_realized_pnl = 0.0
        for sym in exit_symbols:
            pos = portfolio.pop(sym)
            exit_reason = "bear_market_exit" if is_bear else "not_reselected"
            row, net_pnl = _exit_position(pos, exit_date_str, exit_open_prices.get(sym), exit_reason, cost_cfg)
            trade_log.append(row)
            month_realized_pnl += net_pnl

        # --- Process entries (skipped entirely in Bear) ---
        month_entries_failed = 0
        for sym in entry_symbols:
            open_price = entry_open_prices.get(sym)
            if open_price is None:
                month_entries_failed += 1
                continue
            shares = max(int(position_amount // open_price), 1)
            capital_used = round(open_price * shares, 2)
            portfolio[sym] = Position(
                symbol=sym,
                entry_date=entry_date_str,
                entry_price=open_price,
                shares=shares,
                capital_used=capital_used,
            )

        portfolio_capital = sum(p.capital_used for p in portfolio.values())
        monthly_rows.append({
            "year": year,
            "month": month_s,
            "exit_date": exit_date_str,
            "entry_date": entry_date_str,
            "regime": regime,
            "holdings_count": len(portfolio),
            "exits": len(exit_symbols),
            "entries": len(entry_symbols),
            "entries_failed_no_quote": month_entries_failed,
            "realized_net_pnl": round(month_realized_pnl, 2),
            "portfolio_capital_deployed": round(portfolio_capital, 2),
        })
        regime_tag = f" [BEAR — all exited]" if is_bear else f" [{regime}]"
        print(
            f"[{year}/{month_s}] entry={entry_date_str}{regime_tag} | "
            f"holdings={len(portfolio)} | exits={len(exit_symbols)} entries={len(entry_symbols)} | "
            f"realized_pnl={month_realized_pnl:+.0f}"
        )

    # --- Close remaining open positions (mark as unrealized) ---
    for sym, pos in portfolio.items():
        trade_log.append({
            "symbol": sym,
            "entry_date": pos.entry_date,
            "exit_date": np.nan,
            "entry_price": pos.entry_price,
            "exit_price": np.nan,
            "shares": pos.shares,
            "capital_used": pos.capital_used,
            "gross_pnl": np.nan,
            "cost": np.nan,
            "net_pnl": np.nan,
            "return_pct": np.nan,
            "exit_reason": "still_open",
        })

    trades_df = pd.DataFrame(trade_log)
    monthly_df = pd.DataFrame(monthly_rows)

    trades_path = out_dir / "rolling_trades.csv"
    monthly_path = out_dir / "rolling_monthly.csv"
    trades_df.to_csv(trades_path, index=False, encoding="utf-8-sig")
    monthly_df.to_csv(monthly_path, index=False, encoding="utf-8-sig")

    # Summary stats (closed trades only — excludes still_open)
    closed = trades_df[trades_df["exit_reason"].isin(["not_reselected", "bear_market_exit"])].copy()
    total_net_pnl = closed["net_pnl"].sum() if not closed.empty else 0.0
    win_count = int((closed["net_pnl"] > 0).sum()) if not closed.empty else 0
    loss_count = int((closed["net_pnl"] < 0).sum()) if not closed.empty else 0

    summary = {
        "start": f"{args.start_year}/{normalize_month(args.start_month)}",
        "end": f"{args.end_year}/{normalize_month(args.end_month)}",
        "position_amount": position_amount,
        "top_n": top_n,
        "cost_config": {"commission_rate": cost_cfg.commission_rate, "tax_rate": cost_cfg.tax_rate},
        "total_closed_trades": int(len(closed)),
        "win_count": win_count,
        "loss_count": loss_count,
        "win_rate": round(win_count / len(closed), 4) if len(closed) > 0 else None,
        "total_net_pnl": round(float(total_net_pnl), 2),
        "still_open_count": int((trades_df["exit_reason"] == "still_open").sum()),
    }
    (out_dir / "rolling_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\nrolling backtest done")
    print(f"- output: {out_dir}")
    print(f"- closed trades: {summary['total_closed_trades']}")
    print(f"- win/loss: {win_count}/{loss_count}")
    print(f"- total net pnl: {total_net_pnl:+.0f} TWD")
    print(f"- still open: {summary['still_open_count']}")


if __name__ == "__main__":
    main()
