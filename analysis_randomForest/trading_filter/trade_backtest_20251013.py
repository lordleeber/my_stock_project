import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import requests


DEFAULT_INPUT = Path(__file__).resolve().parent / "trade_candidates_2025_1013_1120.csv"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "results"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Simple trade backtest for selected candidates.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--entry-date", type=str, default="2025-10-13")
    parser.add_argument("--end-date", type=str, default="2025-11-20")
    parser.add_argument("--market", type=str, default="sii")
    parser.add_argument("--stop-loss-pct", type=float, default=0.05)
    parser.add_argument("--shares-per-lot", type=int, default=1000)
    parser.add_argument("--api-base", type=str, default="http://100.103.191.79:8000")
    return parser.parse_args()


def fetch_daily_quotes(api_base: str, market: str, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    url = f"{api_base}/raw/daily-quotes"
    params = {
        "market": market,
        "symbol": symbol,
        "start_date": start_date,
        "end_date": end_date,
        "limit": 500,
    }
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    payload = resp.json()
    if not payload:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close"])

    q = pd.DataFrame(payload)
    q["date"] = pd.to_datetime(q["date"], errors="coerce")
    for c in ["open", "high", "low", "close"]:
        q[c] = pd.to_numeric(q[c], errors="coerce")
    return q.sort_values("date").reset_index(drop=True)


def simulate_one(symbol: str, target_price: float, quote_df: pd.DataFrame, entry_date: pd.Timestamp, end_date: pd.Timestamp, stop_loss_pct: float, shares_per_lot: int) -> dict:
    base = {
        "symbol": symbol,
        "target_price": float(target_price) if pd.notna(target_price) else np.nan,
        "entry_date": entry_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d"),
    }

    if pd.isna(target_price) or float(target_price) <= 0:
        return {**base, "status": "invalid_target", "exit_reason": "invalid_target", "exit_date": None, "entry_open": np.nan, "stop_price": np.nan, "exit_price": np.nan, "pnl_per_lot": np.nan, "return_pct": np.nan}

    q = quote_df[(quote_df["date"] >= entry_date) & (quote_df["date"] <= end_date)].copy()
    if q.empty:
        return {**base, "status": "no_quote_in_window", "exit_reason": "no_quote_in_window", "exit_date": None, "entry_open": np.nan, "stop_price": np.nan, "exit_price": np.nan, "pnl_per_lot": np.nan, "return_pct": np.nan}

    e = q[q["date"] == entry_date]
    if e.empty or pd.isna(e.iloc[0]["open"]):
        return {**base, "status": "no_entry_open", "exit_reason": "no_entry_open", "exit_date": None, "entry_open": np.nan, "stop_price": np.nan, "exit_price": np.nan, "pnl_per_lot": np.nan, "return_pct": np.nan}

    entry_open = float(e.iloc[0]["open"])
    stop_price = entry_open * (1.0 - stop_loss_pct)
    tp_price = float(target_price)

    for _, row in q.iterrows():
        day_low = float(row["low"]) if pd.notna(row["low"]) else np.nan
        day_high = float(row["high"]) if pd.notna(row["high"]) else np.nan
        day_date = row["date"].strftime("%Y-%m-%d")

        hit_sl = pd.notna(day_low) and day_low <= stop_price
        hit_tp = pd.notna(day_high) and day_high >= tp_price

        if hit_sl and hit_tp:
            exit_price = stop_price
            pnl = (exit_price - entry_open) * shares_per_lot
            ret = (exit_price / entry_open - 1.0) * 100.0
            return {**base, "status": "sold", "exit_reason": "both_hit_same_day_stop_first", "exit_date": day_date, "entry_open": entry_open, "stop_price": stop_price, "exit_price": exit_price, "pnl_per_lot": pnl, "return_pct": ret}
        if hit_sl:
            exit_price = stop_price
            pnl = (exit_price - entry_open) * shares_per_lot
            ret = (exit_price / entry_open - 1.0) * 100.0
            return {**base, "status": "sold", "exit_reason": "stop_loss", "exit_date": day_date, "entry_open": entry_open, "stop_price": stop_price, "exit_price": exit_price, "pnl_per_lot": pnl, "return_pct": ret}
        if hit_tp:
            exit_price = tp_price
            pnl = (exit_price - entry_open) * shares_per_lot
            ret = (exit_price / entry_open - 1.0) * 100.0
            return {**base, "status": "sold", "exit_reason": "take_profit", "exit_date": day_date, "entry_open": entry_open, "stop_price": stop_price, "exit_price": exit_price, "pnl_per_lot": pnl, "return_pct": ret}

    end_rows = q[q["date"] == end_date]
    if not end_rows.empty and pd.notna(end_rows.iloc[0]["close"]):
        mark_price = float(end_rows.iloc[0]["close"])
        mark_date = end_date.strftime("%Y-%m-%d")
    else:
        last_row = q.dropna(subset=["close"]).tail(1)
        mark_price = float(last_row.iloc[0]["close"]) if not last_row.empty else np.nan
        mark_date = last_row.iloc[0]["date"].strftime("%Y-%m-%d") if not last_row.empty else None

    pnl = (mark_price - entry_open) * shares_per_lot if pd.notna(mark_price) else np.nan
    ret = (mark_price / entry_open - 1.0) * 100.0 if pd.notna(mark_price) and entry_open != 0 else np.nan
    return {**base, "status": "open_until_end", "exit_reason": "not_hit_until_end", "exit_date": mark_date, "entry_open": entry_open, "stop_price": stop_price, "exit_price": mark_price, "pnl_per_lot": pnl, "return_pct": ret}


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    picks = pd.read_csv(args.input).copy()
    picks["symbol"] = picks["symbol"].astype(str).str.strip()
    if "predict_target_price" not in picks.columns:
        raise ValueError("input must contain predict_target_price")

    entry_date = pd.to_datetime(args.entry_date)
    end_date = pd.to_datetime(args.end_date)
    target_map = picks.set_index("symbol")["predict_target_price"].to_dict()

    rows = []
    symbols = picks["symbol"].dropna().unique().tolist()
    for i, symbol in enumerate(symbols, start=1):
        print(f"[{i}/{len(symbols)}] {symbol}")
        try:
            q = fetch_daily_quotes(args.api_base, args.market, symbol, args.entry_date, args.end_date)
            row = simulate_one(symbol, target_map.get(symbol, np.nan), q, entry_date, end_date, args.stop_loss_pct, args.shares_per_lot)
        except Exception as exc:
            row = {"symbol": symbol, "target_price": target_map.get(symbol, np.nan), "entry_date": args.entry_date, "end_date": args.end_date, "status": "error", "exit_reason": str(exc), "exit_date": None, "entry_open": np.nan, "stop_price": np.nan, "exit_price": np.nan, "pnl_per_lot": np.nan, "return_pct": np.nan}
        rows.append(row)

    out = pd.DataFrame(rows).sort_values(["status", "return_pct"], ascending=[True, False]).reset_index(drop=True)
    num_cols = out.select_dtypes(include=["number"]).columns.tolist()
    if num_cols:
        out[num_cols] = out[num_cols].round(2)
    sold = out[out["status"] == "sold"].copy()
    not_hit = out[out["status"] == "open_until_end"].copy()

    all_path = args.output_dir / "trade_backtest_20251013_1120_all.csv"
    sold_path = args.output_dir / "trade_backtest_20251013_1120_sold.csv"
    open_path = args.output_dir / "trade_backtest_20251013_1120_open_until_end.csv"
    summary_path = args.output_dir / "trade_backtest_20251013_1120_summary.json"

    out.to_csv(all_path, index=False)
    sold.to_csv(sold_path, index=False)
    not_hit.to_csv(open_path, index=False)

    summary = {
        "total_picks": int(len(out)),
        "sold_count": int(len(sold)),
        "open_until_end_count": int(len(not_hit)),
        "error_count": int((out["status"] == "error").sum()),
        "sold_win_count": int((sold["pnl_per_lot"] > 0).sum()) if not sold.empty else 0,
        "sold_loss_count": int((sold["pnl_per_lot"] < 0).sum()) if not sold.empty else 0,
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print("trade backtest done")
    print(f"- {all_path}")
    print(f"- {sold_path}")
    print(f"- {open_path}")
    print(f"- {summary_path}")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
