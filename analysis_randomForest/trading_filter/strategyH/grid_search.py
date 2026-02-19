import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis_randomForest.trading_filter.multi_strategy_backtest import normalize_quotes, simulate_one  # noqa: E402


BASE_DIR = Path(__file__).resolve().parent
CANDIDATES_PATH = BASE_DIR.parent / "trade_candidates_2025_1013_1120.csv"
QUOTES_CACHE_PATH = BASE_DIR.parent / "daily_quotes_20251013_1120_sii.csv"

OUT_ALL = BASE_DIR / "grid_results_all.csv"
OUT_TOP20 = BASE_DIR / "grid_results_top20.csv"
OUT_BEST = BASE_DIR / "best_config.json"


def build_trade_config(tp_pct: float, sl_pct: float, trailing_pct: float | None, max_hold_days: int) -> dict:
    return {
        "strategy_name": "H_trade_rule",
        "position": {"max_position_amount": 200000.0, "shares_per_lot": 1000},
        "entry_rule": {"type": "all"},
        "take_profit_rule": {"type": "fixed_pct", "pct": tp_pct},
        "exit_rule": {
            "stop_loss_pct": sl_pct,
            "max_hold_days": max_hold_days,
            "trailing_stop_pct": trailing_pct,
            "prefer_stop_when_both": True,
        },
    }


def select_with_portfolio_constraints(
    candidates: pd.DataFrame,
    max_positions: int,
    max_per_industry: int,
    min_volume_lots: float,
    min_upside_ratio: float,
) -> pd.DataFrame:
    df = candidates.copy()
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df["predict_target_price"] = pd.to_numeric(df["predict_target_price"], errors="coerce")
    df["pred_delta_std"] = pd.to_numeric(df["pred_delta_std"], errors="coerce")
    df["volume_lots"] = pd.to_numeric(df["volume_lots"], errors="coerce")
    df["industry"] = df["industry"].fillna("UNKNOWN").astype(str).str.strip()
    df["upside_ratio"] = df["predict_target_price"] / df["close"]
    df = df.replace([np.inf, -np.inf], np.nan)

    # 候選池：先做基本流動性與上漲空間過濾
    pool = df[
        df["upside_ratio"].notna()
        & (df["upside_ratio"] >= min_upside_ratio)
        & df["volume_lots"].notna()
        & (df["volume_lots"] >= min_volume_lots)
    ].copy()

    # 分數：上漲空間越大越好，波動越大越扣分
    std_fallback = pool["pred_delta_std"].median() if not pool.empty else np.nan
    if np.isnan(std_fallback):
        std_fallback = 0.0
    pool["score"] = pool["upside_ratio"] - 0.3 * pool["pred_delta_std"].fillna(std_fallback)
    pool = pool.sort_values(["score", "upside_ratio"], ascending=[False, False]).reset_index(drop=True)

    picked_rows = []
    industry_count: dict[str, int] = {}

    for _, row in pool.iterrows():
        if len(picked_rows) >= max_positions:
            break
        industry = row["industry"]
        now_cnt = industry_count.get(industry, 0)
        if now_cnt >= max_per_industry:
            continue
        picked_rows.append(row)
        industry_count[industry] = now_cnt + 1

    if not picked_rows:
        return pool.head(0).copy()
    return pd.DataFrame(picked_rows).reset_index(drop=True)


def run_one_combo(
    candidates: pd.DataFrame,
    quotes: pd.DataFrame,
    max_positions: int,
    max_per_industry: int,
    min_volume_lots: float,
    min_upside_ratio: float,
    tp_pct: float,
    sl_pct: float,
    trailing_pct: float | None,
    max_hold_days: int,
) -> dict:
    selected = select_with_portfolio_constraints(
        candidates=candidates,
        max_positions=max_positions,
        max_per_industry=max_per_industry,
        min_volume_lots=min_volume_lots,
        min_upside_ratio=min_upside_ratio,
    )
    cfg = build_trade_config(tp_pct=tp_pct, sl_pct=sl_pct, trailing_pct=trailing_pct, max_hold_days=max_hold_days)

    entry_dt = pd.to_datetime("2025-10-13")
    end_dt = pd.to_datetime("2025-11-20")

    rows = []
    for _, row in selected.iterrows():
        rows.append(simulate_one(row=row, quote_df=quotes, entry_date=entry_dt, end_date=end_dt, cfg=cfg))

    out = pd.DataFrame(rows) if rows else pd.DataFrame(columns=["status", "pnl_amount", "capital_used"])
    sold = out[out["status"] == "sold"].copy() if not out.empty else pd.DataFrame()
    open_until_end = out[out["status"] == "open_until_end"].copy() if not out.empty else pd.DataFrame()

    total_capital = float(sold["capital_used"].sum()) if not sold.empty else 0.0
    total_revenue = float(sold["pnl_amount"].sum()) if not sold.empty else 0.0
    return_percent = (total_revenue / total_capital * 100.0) if total_capital > 0 else 0.0

    strategy_name = (
        f"H_n{max_positions}_ind{max_per_industry}_vol{int(min_volume_lots)}"
        f"_up{int(min_upside_ratio*100)}_tp{int(tp_pct*100)}_sl{int(sl_pct*100)}"
        f"_tr{'none' if trailing_pct is None else int(trailing_pct*100)}_h{max_hold_days}"
    )

    return {
        "strategy_name": strategy_name,
        "max_positions": max_positions,
        "max_per_industry": max_per_industry,
        "min_volume_lots": min_volume_lots,
        "min_upside_ratio": min_upside_ratio,
        "tp_pct": tp_pct,
        "sl_pct": sl_pct,
        "trailing_stop_pct": trailing_pct,
        "max_hold_days": max_hold_days,
        "total_picks": int(len(candidates)),
        "selected_count": int(len(selected)),
        "filtered_out_count": int(len(candidates) - len(selected)),
        "entered_count": int((out["status"].isin(["sold", "open_until_end"])).sum()) if not out.empty else 0,
        "sold_count": int(len(sold)),
        "open_until_end_count": int(len(open_until_end)),
        "sold_win_count": int((sold["pnl_amount"] > 0).sum()) if not sold.empty else 0,
        "sold_loss_count": int((sold["pnl_amount"] < 0).sum()) if not sold.empty else 0,
        "total_capital": round(total_capital, 2),
        "total_revenue": round(total_revenue, 2),
        "return_percent": round(return_percent, 4),
    }


def main() -> None:
    candidates = pd.read_csv(CANDIDATES_PATH)
    candidates["symbol"] = candidates["symbol"].astype(str).str.strip()
    quotes = normalize_quotes(pd.read_csv(QUOTES_CACHE_PATH))

    max_positions_grid = [20, 40, 60]
    max_per_industry_grid = [2, 4, 6]
    min_volume_lots_grid = [500.0, 1000.0, 2000.0]
    min_upside_ratio_grid = [1.03, 1.05]
    tp_grid = [0.10, 0.14]
    sl_grid = [0.05, 0.07]
    trailing_grid = [None, 0.05]
    hold_grid = [12, 15]

    total = (
        len(max_positions_grid)
        * len(max_per_industry_grid)
        * len(min_volume_lots_grid)
        * len(min_upside_ratio_grid)
        * len(tp_grid)
        * len(sl_grid)
        * len(trailing_grid)
        * len(hold_grid)
    )
    idx = 0
    all_rows = []

    for npos in max_positions_grid:
        for nind in max_per_industry_grid:
            for min_vol in min_volume_lots_grid:
                for min_up in min_upside_ratio_grid:
                    for tp in tp_grid:
                        for sl in sl_grid:
                            for tr in trailing_grid:
                                for h in hold_grid:
                                    idx += 1
                                    print(
                                        f"[{idx}/{total}] H n={npos} ind={nind} vol={min_vol} "
                                        f"up={min_up} tp={tp} sl={sl} tr={tr} h={h}"
                                    )
                                    all_rows.append(
                                        run_one_combo(
                                            candidates=candidates,
                                            quotes=quotes,
                                            max_positions=npos,
                                            max_per_industry=nind,
                                            min_volume_lots=min_vol,
                                            min_upside_ratio=min_up,
                                            tp_pct=tp,
                                            sl_pct=sl,
                                            trailing_pct=tr,
                                            max_hold_days=h,
                                        )
                                    )

    result_df = pd.DataFrame(all_rows)
    filtered = result_df[result_df["selected_count"] >= 20].copy()
    if filtered.empty:
        filtered = result_df.copy()

    ranked = filtered.sort_values(
        by=["return_percent", "total_revenue", "sold_loss_count"],
        ascending=[False, False, True],
    ).reset_index(drop=True)

    result_df.to_csv(OUT_ALL, index=False, encoding="utf-8-sig")
    ranked.head(20).to_csv(OUT_TOP20, index=False, encoding="utf-8-sig")
    OUT_BEST.write_text(json.dumps(ranked.iloc[0].to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    print("strategyH grid search done")
    print(f"- all: {OUT_ALL}")
    print(f"- top20: {OUT_TOP20}")
    print(f"- best: {OUT_BEST}")


if __name__ == "__main__":
    main()
