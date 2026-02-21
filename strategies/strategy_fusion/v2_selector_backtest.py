import argparse
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from strategies.multi_strategy_backtest import normalize_quotes, simulate_one
from strategies.strategy_fusion.backtest import build_fusion_signals


BASE_DIR = Path(__file__).resolve().parent
TRADING_DIR = BASE_DIR.parent
CANDIDATES_PATH = TRADING_DIR / "sii" / "2025" / "10" / "trade_candidates.csv"
QUOTES_PATH = TRADING_DIR / "sii" / "2025" / "10" / "daily_quotes_20251013_1120_sii.csv"
OUT_DIR = BASE_DIR / "results_v2"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fusion v2: top-k strategy selector + combiner")
    parser.add_argument("--entry-date", type=str, default="2025-10-13")
    parser.add_argument("--end-date", type=str, default="2025-11-20")
    parser.add_argument("--top-k-strategies", type=int, default=3)
    parser.add_argument("--min-strategy-entered", type=int, default=20)
    parser.add_argument("--min-votes", type=int, default=2)
    parser.add_argument("--max-picks", type=int, default=40)
    parser.add_argument("--max-per-industry", type=int, default=8)
    parser.add_argument("--max-position-amount", type=float, default=200000.0)
    parser.add_argument("--shares-per-lot", type=int, default=1000)
    parser.add_argument("--stop-loss-pct", type=float, default=0.05)
    parser.add_argument("--trailing-stop-pct", type=float, default=0.03)
    parser.add_argument("--max-hold-days", type=int, default=15)
    return parser.parse_args()


def load_strategy_strength() -> pd.DataFrame:
    rows = []
    for s in list("ABCDEFGHI"):
        path = TRADING_DIR / f"strategy{s}" / "best_config.json"
        if not path.exists():
            continue
        obj = json.loads(path.read_text(encoding="utf-8"))
        rows.append(
            {
                "strategy": s,
                "return_percent": float(obj.get("return_percent", 0.0)),
                "entered_count": int(obj.get("entered_count", 0)),
                "strategy_name": str(obj.get("strategy_name", "")),
            }
        )
    return pd.DataFrame(rows)


def pick_top_strategies(df: pd.DataFrame, top_k: int, min_entered: int) -> list[str]:
    if df.empty:
        return []
    usable = df[df["entered_count"] >= min_entered].copy()
    if usable.empty:
        usable = df.copy()
    usable = usable.sort_values(["return_percent", "entered_count"], ascending=[False, False])
    return usable.head(top_k)["strategy"].tolist()


def select_by_votes(
    candidates: pd.DataFrame,
    selected_strategies: list[str],
    min_votes: int,
    max_picks: int,
    max_per_industry: int,
) -> pd.DataFrame:
    df = build_fusion_signals(candidates)

    # ??A~I 撠???sig_X ?嗡?瘥?蝑?臬???脣
    sig_cols = [f"sig_{s}" for s in selected_strategies if f"sig_{s}" in df.columns]
    if not sig_cols:
        return df.head(0).copy()

    df["vote_count"] = df[sig_cols].sum(axis=1)
    df["vote_ratio"] = df["vote_count"] / len(sig_cols)
    # ?巨???芸???瞍脩征??瘚???    df["upside_ratio"] = df["predict_target_price"] / df["close"]

    pool = df[df["vote_count"] >= min_votes].copy()
    if pool.empty:
        pool = df[df["vote_count"] >= 1].copy()
    if pool.empty:
        return df.head(0).copy()

    pool = pool.sort_values(["vote_count", "vote_ratio", "upside_ratio", "volume_lots"], ascending=[False, False, False, False])

    picked = []
    industry_count: dict[str, int] = {}
    for _, row in pool.iterrows():
        if len(picked) >= max_picks:
            break
        industry = str(row.get("industry", "UNKNOWN"))
        now = industry_count.get(industry, 0)
        if now >= max_per_industry:
            continue
        picked.append(row)
        industry_count[industry] = now + 1

    return pd.DataFrame(picked).reset_index(drop=True) if picked else pool.head(0).copy()


def make_trade_cfg(args: argparse.Namespace) -> dict:
    return {
        "strategy_name": "fusion_v2_topk_selector",
        "position": {"max_position_amount": float(args.max_position_amount), "shares_per_lot": int(args.shares_per_lot)},
        "entry_rule": {"type": "all"},
        "take_profit_rule": {"type": "target_price_if_above_entry"},
        "exit_rule": {
            "stop_loss_pct": float(args.stop_loss_pct),
            "max_hold_days": int(args.max_hold_days),
            "trailing_stop_pct": float(args.trailing_stop_pct),
            "prefer_stop_when_both": True,
        },
    }


def run_selector_once(
    candidates: pd.DataFrame,
    quotes: pd.DataFrame,
    entry_date: str,
    end_date: str,
    top_k_strategies: int,
    min_strategy_entered: int,
    min_votes: int,
    max_picks: int,
    max_per_industry: int,
    max_position_amount: float,
    shares_per_lot: int,
    stop_loss_pct: float,
    trailing_stop_pct: float,
    max_hold_days: int,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    strength = load_strategy_strength()
    top_strategies = pick_top_strategies(
        df=strength,
        top_k=int(top_k_strategies),
        min_entered=int(min_strategy_entered),
    )

    selected = select_by_votes(
        candidates=candidates,
        selected_strategies=top_strategies,
        min_votes=int(min_votes),
        max_picks=int(max_picks),
        max_per_industry=int(max_per_industry),
    )

    ns = argparse.Namespace(
        max_position_amount=max_position_amount,
        shares_per_lot=shares_per_lot,
        stop_loss_pct=stop_loss_pct,
        trailing_stop_pct=trailing_stop_pct,
        max_hold_days=max_hold_days,
    )
    cfg = make_trade_cfg(ns)
    entry_dt = pd.to_datetime(entry_date)
    end_dt = pd.to_datetime(end_date)
    rows = []
    for _, row in selected.iterrows():
        rows.append(simulate_one(row=row, quote_df=quotes, entry_date=entry_dt, end_date=end_dt, cfg=cfg))
    out = pd.DataFrame(rows)

    sold = out[out["status"] == "sold"].copy() if not out.empty else pd.DataFrame()
    open_until_end = out[out["status"] == "open_until_end"].copy() if not out.empty else pd.DataFrame()
    skipped = out[out["status"] == "skipped"].copy() if not out.empty else pd.DataFrame()

    total_capital = float(sold["capital_used"].sum()) if not sold.empty else 0.0
    total_revenue = float(sold["pnl_amount"].sum()) if not sold.empty else 0.0
    return_percent = (total_revenue / total_capital * 100.0) if total_capital > 0 else 0.0
    win_money = float(sold.loc[sold["pnl_amount"] > 0, "pnl_amount"].sum()) if not sold.empty else 0.0
    loss_money = float(sold.loc[sold["pnl_amount"] < 0, "pnl_amount"].sum()) if not sold.empty else 0.0

    summary = {
        "strategy_name": cfg["strategy_name"],
        "entry_date": entry_date,
        "end_date": end_date,
        "top_strategies": top_strategies,
        "top_k_strategies": int(top_k_strategies),
        "min_strategy_entered": int(min_strategy_entered),
        "min_votes": int(min_votes),
        "max_picks": int(max_picks),
        "max_per_industry": int(max_per_industry),
        "selected_count": int(len(selected)),
        "entered_count": int((out["status"].isin(["sold", "open_until_end"])).sum()) if not out.empty else 0,
        "skipped_count": int(len(skipped)),
        "sold_count": int(len(sold)),
        "open_until_end_count": int(len(open_until_end)),
        "sold_win_count": int((sold["pnl_amount"] > 0).sum()) if not sold.empty else 0,
        "sold_loss_count": int((sold["pnl_amount"] < 0).sum()) if not sold.empty else 0,
        "total_capital": round(total_capital, 2),
        "sold_win_money": round(win_money, 2),
        "sold_losee_money": round(loss_money, 2),
        "total_revenue": round(total_revenue, 2),
        "return_percent": round(return_percent, 4),
        "max_position_amount": float(max_position_amount),
        "shares_per_lot": int(shares_per_lot),
        "stop_loss_pct": float(stop_loss_pct),
        "trailing_stop_pct": float(trailing_stop_pct),
        "max_hold_days": int(max_hold_days),
    }
    return selected, out, summary


def main() -> None:
    args = parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    candidates = pd.read_csv(CANDIDATES_PATH)
    candidates["symbol"] = candidates["symbol"].astype(str).str.strip()
    quotes = normalize_quotes(pd.read_csv(QUOTES_PATH))

    selected, out, summary = run_selector_once(
        candidates=candidates,
        quotes=quotes,
        entry_date=args.entry_date,
        end_date=args.end_date,
        top_k_strategies=int(args.top_k_strategies),
        min_strategy_entered=int(args.min_strategy_entered),
        min_votes=int(args.min_votes),
        max_picks=int(args.max_picks),
        max_per_industry=int(args.max_per_industry),
        max_position_amount=float(args.max_position_amount),
        shares_per_lot=int(args.shares_per_lot),
        stop_loss_pct=float(args.stop_loss_pct),
        trailing_stop_pct=float(args.trailing_stop_pct),
        max_hold_days=int(args.max_hold_days),
    )

    selected_path = OUT_DIR / "selected_candidates_v2.csv"
    trade_path = OUT_DIR / "fusion_v2_trade_backtest.csv"
    summary_path = OUT_DIR / "fusion_v2_summary.json"

    selected.to_csv(selected_path, index=False, encoding="utf-8-sig")
    out.to_csv(trade_path, index=False, encoding="utf-8-sig")

    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("fusion v2 selector done")
    print(f"- selected: {selected_path}")
    print(f"- trades: {trade_path}")
    print(f"- summary: {summary_path}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()


