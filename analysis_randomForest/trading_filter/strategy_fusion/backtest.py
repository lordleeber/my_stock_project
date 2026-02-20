import argparse
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis_randomForest.trading_filter.multi_strategy_backtest import normalize_quotes, simulate_one


BASE_DIR = Path(__file__).resolve().parent
TRADING_DIR = BASE_DIR.parent
CANDIDATES_PATH = TRADING_DIR / "trade_candidates_2025_1013_1120.csv"
QUOTES_PATH = TRADING_DIR / "daily_quotes_20251013_1120_sii.csv"
OUT_DIR = BASE_DIR / "results"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fusion backtest for strategy A~I")
    parser.add_argument("--entry-date", type=str, default="2025-10-13")
    parser.add_argument("--end-date", type=str, default="2025-11-20")
    parser.add_argument("--score-threshold", type=float, default=0.55)
    parser.add_argument("--max-picks", type=int, default=60)
    parser.add_argument("--max-per-industry", type=int, default=8)
    parser.add_argument("--max-position-amount", type=float, default=200000.0)
    parser.add_argument("--shares-per-lot", type=int, default=1000)
    parser.add_argument("--stop-loss-pct", type=float, default=0.07)
    parser.add_argument("--trailing-stop-pct", type=float, default=0.03)
    parser.add_argument("--max-hold-days", type=int, default=15)
    return parser.parse_args()


def strategy_weights() -> dict[str, float]:
    # 依照各策略歷史表現設定權重；總和會在後續自動正規化。
    return {
        "A": 5.7205,
        "B": 3.7183,
        "C": 7.8458,
        "D": 4.9761,
        "E": 5.4385,
        "F": 12.6613,
        "G": 4.4080,
        "H": 13.4098,
        "I": 12.6594,
    }


def build_fusion_signals(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["upside_ratio"] = out["predict_target_price"] / out["close"]
    out["pred_delta_std"] = pd.to_numeric(out["pred_delta_std"], errors="coerce")
    out["volume_lots"] = pd.to_numeric(out["volume_lots"], errors="coerce")
    out["pred_rf_delta"] = pd.to_numeric(out["pred_rf_delta"], errors="coerce")

    std_q50 = float(out["pred_delta_std"].quantile(0.50))
    std_q60 = float(out["pred_delta_std"].quantile(0.60))
    std_q70 = float(out["pred_delta_std"].quantile(0.70))
    delta_q50 = float(out["pred_rf_delta"].quantile(0.50))
    vol_q50 = float(out["volume_lots"].quantile(0.50))

    # F 的 composite 分數：用量能、上檔空間、波動度（低波動加分）
    vol_rank = out["volume_lots"].rank(pct=True)
    upside_rank = out["upside_ratio"].rank(pct=True)
    inv_std_rank = (1.0 - out["pred_delta_std"].rank(pct=True))
    out["composite_score"] = 0.40 * upside_rank + 0.35 * vol_rank + 0.25 * inv_std_rank
    comp_q60 = float(out["composite_score"].quantile(0.60))

    # A~I 二元訊號（1=通過，0=未通過）
    out["sig_A"] = 1
    out["sig_B"] = (out["pred_delta_std"] <= std_q70).astype(int)
    out["sig_C"] = ((out["upside_ratio"] >= 1.05) & (out["pred_rf_delta"] >= 0.50)).astype(int)
    out["sig_D"] = (out["pred_rf_delta"] >= delta_q50).astype(int)
    out["sig_E"] = (out["pred_delta_std"] <= std_q50).astype(int)
    out["sig_F"] = ((out["composite_score"] >= comp_q60) & (out["upside_ratio"] >= 1.03)).astype(int)
    out["sig_G"] = (out["volume_lots"] >= vol_q50).astype(int)
    out["sig_H"] = ((out["volume_lots"] >= 2000) & (out["upside_ratio"] >= 1.03)).astype(int)
    out["sig_I"] = (
        (out["volume_lots"] >= 1000) & (out["upside_ratio"] >= 1.03) & (out["pred_delta_std"] <= std_q60)
    ).astype(int)
    return out


def apply_fusion_score(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    w = strategy_weights()
    weight_sum = float(sum(w.values()))
    for k in w:
        w[k] = float(w[k] / weight_sum)
    out["fusion_score"] = (
        out["sig_A"] * w["A"]
        + out["sig_B"] * w["B"]
        + out["sig_C"] * w["C"]
        + out["sig_D"] * w["D"]
        + out["sig_E"] * w["E"]
        + out["sig_F"] * w["F"]
        + out["sig_G"] * w["G"]
        + out["sig_H"] * w["H"]
        + out["sig_I"] * w["I"]
    )
    return out


def select_candidates(df: pd.DataFrame, score_threshold: float, max_picks: int, max_per_industry: int) -> pd.DataFrame:
    # 先用 score 門檻初篩，再做產業上限，避免過度集中。
    pool = df[df["fusion_score"] >= score_threshold].copy()
    if pool.empty:
        pool = df.copy()

    pool = pool.sort_values(["fusion_score", "upside_ratio", "volume_lots"], ascending=[False, False, False]).reset_index(
        drop=True
    )

    selected_parts: list[pd.DataFrame] = []
    for _, group in pool.groupby("industry", dropna=False):
        selected_parts.append(group.head(max_per_industry))
    selected = pd.concat(selected_parts, axis=0, ignore_index=True) if selected_parts else pool.head(0).copy()

    selected = selected.sort_values(["fusion_score", "upside_ratio", "volume_lots"], ascending=[False, False, False]).head(
        max_picks
    )
    return selected.reset_index(drop=True)


def make_cfg(args: argparse.Namespace) -> dict:
    return {
        "strategy_name": "fusion_A_to_I_v1",
        "position": {
            "max_position_amount": float(args.max_position_amount),
            "shares_per_lot": int(args.shares_per_lot),
        },
        "entry_rule": {"type": "all"},
        "take_profit_rule": {"type": "target_price_if_above_entry"},
        "exit_rule": {
            "stop_loss_pct": float(args.stop_loss_pct),
            "max_hold_days": int(args.max_hold_days),
            "trailing_stop_pct": float(args.trailing_stop_pct),
            "prefer_stop_when_both": True,
        },
    }


def run_fusion_once(
    candidates: pd.DataFrame,
    quotes: pd.DataFrame,
    entry_date: str,
    end_date: str,
    score_threshold: float,
    max_picks: int,
    max_per_industry: int,
    max_position_amount: float,
    shares_per_lot: int,
    stop_loss_pct: float,
    trailing_stop_pct: float,
    max_hold_days: int,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    df = build_fusion_signals(candidates)
    df = apply_fusion_score(df)
    selected = select_candidates(
        df=df,
        score_threshold=float(score_threshold),
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
    cfg = make_cfg(ns)

    entry_dt = pd.to_datetime(entry_date)
    end_dt = pd.to_datetime(end_date)

    rows = []
    for _, row in selected.iterrows():
        rows.append(simulate_one(row=row, quote_df=quotes, entry_date=entry_dt, end_date=end_dt, cfg=cfg))
    out = pd.DataFrame(rows)
    sold = out[out["status"] == "sold"].copy()
    open_until_end = out[out["status"] == "open_until_end"].copy()
    skipped = out[out["status"] == "skipped"].copy()

    total_capital = float(sold["capital_used"].sum()) if not sold.empty and "capital_used" in sold.columns else 0.0
    total_revenue = float(sold["pnl_amount"].sum()) if not sold.empty and "pnl_amount" in sold.columns else 0.0
    return_percent = (total_revenue / total_capital * 100.0) if total_capital > 0 else 0.0
    win_money = float(sold.loc[sold["pnl_amount"] > 0, "pnl_amount"].sum()) if not sold.empty else 0.0
    loss_money = float(sold.loc[sold["pnl_amount"] < 0, "pnl_amount"].sum()) if not sold.empty else 0.0

    summary = {
        "strategy_name": cfg["strategy_name"],
        "entry_date": entry_date,
        "end_date": end_date,
        "score_threshold": round(float(score_threshold), 4),
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

    selected, out, summary = run_fusion_once(
        candidates=candidates,
        quotes=quotes,
        entry_date=args.entry_date,
        end_date=args.end_date,
        score_threshold=float(args.score_threshold),
        max_picks=int(args.max_picks),
        max_per_industry=int(args.max_per_industry),
        max_position_amount=float(args.max_position_amount),
        shares_per_lot=int(args.shares_per_lot),
        stop_loss_pct=float(args.stop_loss_pct),
        trailing_stop_pct=float(args.trailing_stop_pct),
        max_hold_days=int(args.max_hold_days),
    )

    selected_path = OUT_DIR / "selected_candidates.csv"
    trade_path = OUT_DIR / "fusion_trade_backtest.csv"
    summary_path = OUT_DIR / "fusion_summary.json"

    selected.to_csv(selected_path, index=False, encoding="utf-8-sig")
    out.to_csv(trade_path, index=False, encoding="utf-8-sig")

    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("fusion backtest done")
    print(f"- selected: {selected_path}")
    print(f"- trades: {trade_path}")
    print(f"- summary: {summary_path}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
