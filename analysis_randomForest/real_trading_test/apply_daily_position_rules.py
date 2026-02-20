import argparse
import json
from pathlib import Path

import pandas as pd
import requests


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply daily position rules: avoid rebuy + emit sell/buy orders.")
    parser.add_argument("--actions-csv", type=Path, required=True)
    parser.add_argument("--positions-csv", type=Path, required=True)
    parser.add_argument("--decision-date", type=str, required=True)
    parser.add_argument("--api-base", type=str, default="http://100.103.191.79:8000")
    parser.add_argument("--market", type=str, default="sii")
    parser.add_argument("--stop-loss-pct", type=float, default=0.11)
    parser.add_argument("--trailing-stop-pct", type=float, default=0.06)
    parser.add_argument("--max-hold-days", type=int, default=15)
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parent)
    return parser.parse_args()


def fetch_quotes(api_base: str, market: str, symbols: list[str], date: str) -> pd.DataFrame:
    rows = []
    for s in symbols:
        resp = requests.get(
            f"{api_base}/raw/daily-quotes",
            params={
                "market": market,
                "symbol": s,
                "start_date": date,
                "end_date": date,
                "limit": 5,
                "offset": 0,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        if data:
            rows.extend(data)
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    actions = pd.read_csv(args.actions_csv)
    positions = pd.read_csv(args.positions_csv)
    actions["symbol"] = actions["symbol"].astype(str).str.strip()
    positions["symbol"] = positions["symbol"].astype(str).str.strip()

    open_pos = positions[positions["status"] == "open"].copy()
    held_symbols = set(open_pos["symbol"].tolist())

    # 1) 新買單：只保留 action=buy 且目前未持有，避免重複買
    buy_orders = actions[(actions["action_now"] == "buy_next_open") & (~actions["symbol"].isin(held_symbols))].copy()
    buy_orders["order_action"] = "buy_next_open"
    buy_orders["order_reason"] = "new_signal_not_held"

    # 2) 持倉賣出判斷：用 decision_date 當天 high/low
    sell_orders = []
    if not open_pos.empty:
        q = fetch_quotes(args.api_base, args.market, sorted(held_symbols), args.decision_date)
        if not q.empty:
            q["symbol"] = q["symbol"].astype(str).str.strip()
            q["high"] = pd.to_numeric(q["high"], errors="coerce")
            q["low"] = pd.to_numeric(q["low"], errors="coerce")
            q["close"] = pd.to_numeric(q["close"], errors="coerce")
            q = q[["symbol", "high", "low", "close"]].copy()
            open_pos = open_pos.merge(q, on="symbol", how="left")

        for _, r in open_pos.iterrows():
            symbol = r["symbol"]
            entry_price = float(r["entry_price"])
            highest_high = float(r["highest_high"]) if pd.notna(r.get("highest_high")) else entry_price
            day_high = float(r["high"]) if pd.notna(r.get("high")) else highest_high
            day_low = float(r["low"]) if pd.notna(r.get("low")) else entry_price
            target_price = float(r["target_price"]) if pd.notna(r.get("target_price")) else None
            holding_days = int(r.get("holding_days", 0)) + 1

            highest_high = max(highest_high, day_high)
            fixed_stop = entry_price * (1.0 - float(args.stop_loss_pct))
            trailing_stop = highest_high * (1.0 - float(args.trailing_stop_pct))
            effective_stop = max(fixed_stop, trailing_stop)

            exit_reason = None
            exit_price = None
            if (target_price is not None) and (day_high >= target_price):
                exit_reason = "hit_target_price"
                exit_price = target_price
            elif day_low <= effective_stop:
                exit_reason = "stop_loss_or_trailing"
                exit_price = effective_stop
            elif holding_days >= int(args.max_hold_days):
                exit_reason = f"time_stop_{int(args.max_hold_days)}d"
                exit_price = float(r["close"]) if pd.notna(r.get("close")) else entry_price

            if exit_reason is not None:
                sell_orders.append(
                    {
                        "symbol": symbol,
                        "order_action": "sell_today",
                        "order_reason": exit_reason,
                        "exit_price_ref": round(float(exit_price), 4),
                        "shares": int(r["shares"]),
                    }
                )
                positions.loc[positions["symbol"] == symbol, "status"] = "closed"
            else:
                positions.loc[positions["symbol"] == symbol, "highest_high"] = highest_high
                positions.loc[positions["symbol"] == symbol, "holding_days"] = holding_days

    sell_df = pd.DataFrame(sell_orders)

    # 寫檔
    tag = args.decision_date.replace("-", "")
    buy_path = args.output_dir / f"orders_buy_{tag}.csv"
    sell_path = args.output_dir / f"orders_sell_{tag}.csv"
    pos_path = args.output_dir / "positions.csv"
    summary_path = args.output_dir / f"daily_position_summary_{tag}.json"

    buy_orders.to_csv(buy_path, index=False, encoding="utf-8-sig")
    sell_df.to_csv(sell_path, index=False, encoding="utf-8-sig")
    positions.to_csv(pos_path, index=False, encoding="utf-8-sig")

    summary = {
        "decision_date": args.decision_date,
        "held_before": int(len(open_pos)),
        "buy_orders_count": int(len(buy_orders)),
        "sell_orders_count": int(len(sell_df)),
        "held_after": int((positions["status"] == "open").sum()),
        "positions_csv": str(pos_path),
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("daily position rules applied")
    print(f"- buy_orders: {buy_path}")
    print(f"- sell_orders: {sell_path}")
    print(f"- positions: {pos_path}")
    print(f"- summary: {summary_path}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
