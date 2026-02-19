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


def build_trade_config(max_position_amount: float, tp_pct: float, sl_pct: float, trailing_pct: float | None, max_hold_days: int) -> dict:
    return {
        "strategy_name": "I_conf_weighted_sizing",
        "position": {"max_position_amount": float(max_position_amount), "shares_per_lot": 1000},
        "entry_rule": {"type": "all"},
        "take_profit_rule": {"type": "fixed_pct", "pct": tp_pct},
        "exit_rule": {
            "stop_loss_pct": sl_pct,
            "max_hold_days": max_hold_days,
            "trailing_stop_pct": trailing_pct,
            "prefer_stop_when_both": True,
        },
    }


def score_candidates(
    candidates: pd.DataFrame,
    min_volume_lots: float,
    min_upside_ratio: float,
    std_penalty: float,
) -> pd.DataFrame:
    df = candidates.copy()
    for c in ["close", "predict_target_price", "pred_rf_delta", "pred_delta_std", "volume_lots"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df["upside_ratio"] = df["predict_target_price"] / df["close"]
    df = df.replace([np.inf, -np.inf], np.nan)

    # 基礎流動性與上漲空間過濾
    pool = df[
        df["upside_ratio"].notna()
        & (df["upside_ratio"] >= min_upside_ratio)
        & df["volume_lots"].notna()
        & (df["volume_lots"] >= min_volume_lots)
    ].copy()

    # 信心分數：預測漲幅與目標價空間加分，預測不確定性扣分
    std_fill = pool["pred_delta_std"].median() if not pool.empty else np.nan
    if np.isnan(std_fill):
        std_fill = 0.0
    pool["pred_delta_std"] = pool["pred_delta_std"].fillna(std_fill)
    pool["pred_rf_delta"] = pool["pred_rf_delta"].fillna(pool["pred_rf_delta"].median())

    pool["score_raw"] = (
        0.6 * (pool["upside_ratio"] - 1.0)
        + 0.4 * pool["pred_rf_delta"]
        - std_penalty * pool["pred_delta_std"]
    )

    # 轉成 0~1，供後續配資映射
    s_min = float(pool["score_raw"].min()) if not pool.empty else 0.0
    s_max = float(pool["score_raw"].max()) if not pool.empty else 0.0
    if s_max > s_min:
        pool["score_norm"] = (pool["score_raw"] - s_min) / (s_max - s_min)
    else:
        pool["score_norm"] = 0.5

    return pool.sort_values(["score_norm", "upside_ratio"], ascending=[False, False]).reset_index(drop=True)


def amount_from_score(score_norm: float, min_amount: float, max_amount: float, gamma: float) -> float:
    x = float(np.clip(score_norm, 0.0, 1.0))
    # gamma < 1 會放大高分與中分差異；gamma > 1 會更保守
    weight = x ** gamma
    return float(min_amount + weight * (max_amount - min_amount))


def run_one_combo(
    candidates: pd.DataFrame,
    quotes: pd.DataFrame,
    min_volume_lots: float,
    min_upside_ratio: float,
    std_penalty: float,
    gamma: float,
    min_amount: float,
    max_amount: float,
    tp_pct: float,
    sl_pct: float,
    trailing_pct: float | None,
    max_hold_days: int,
) -> dict:
    selected = score_candidates(
        candidates=candidates,
        min_volume_lots=min_volume_lots,
        min_upside_ratio=min_upside_ratio,
        std_penalty=std_penalty,
    )

    entry_dt = pd.to_datetime("2025-10-13")
    end_dt = pd.to_datetime("2025-11-20")

    rows = []
    for _, row in selected.iterrows():
        dyn_amount = amount_from_score(
            score_norm=float(row["score_norm"]),
            min_amount=min_amount,
            max_amount=max_amount,
            gamma=gamma,
        )
        cfg = build_trade_config(
            max_position_amount=dyn_amount,
            tp_pct=tp_pct,
            sl_pct=sl_pct,
            trailing_pct=trailing_pct,
            max_hold_days=max_hold_days,
        )
        rows.append(simulate_one(row=row, quote_df=quotes, entry_date=entry_dt, end_date=end_dt, cfg=cfg))

    out = pd.DataFrame(rows) if rows else pd.DataFrame(columns=["status", "pnl_amount", "capital_used"])
    sold = out[out["status"] == "sold"].copy() if not out.empty else pd.DataFrame()
    open_until_end = out[out["status"] == "open_until_end"].copy() if not out.empty else pd.DataFrame()

    total_capital = float(sold["capital_used"].sum()) if not sold.empty else 0.0
    total_revenue = float(sold["pnl_amount"].sum()) if not sold.empty else 0.0
    return_percent = (total_revenue / total_capital * 100.0) if total_capital > 0 else 0.0

    strategy_name = (
        f"I_vol{int(min_volume_lots)}_up{int(min_upside_ratio*100)}"
        f"_std{int(std_penalty*100)}_g{int(gamma*100)}"
        f"_a{int(min_amount/1000)}-{int(max_amount/1000)}"
        f"_tp{int(tp_pct*100)}_sl{int(sl_pct*100)}"
        f"_tr{'none' if trailing_pct is None else int(trailing_pct*100)}_h{max_hold_days}"
    )

    return {
        "strategy_name": strategy_name,
        "min_volume_lots": min_volume_lots,
        "min_upside_ratio": min_upside_ratio,
        "std_penalty": std_penalty,
        "gamma": gamma,
        "min_amount": min_amount,
        "max_amount": max_amount,
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

    min_volume_lots_grid = [500.0, 1000.0]
    min_upside_ratio_grid = [1.03]
    std_penalty_grid = [0.2, 0.4, 0.6]
    gamma_grid = [0.7, 1.0, 1.3]
    min_amount_grid = [50000.0, 100000.0]
    max_amount_grid = [200000.0, 300000.0]
    tp_grid = [0.10, 0.14]
    sl_grid = [0.05, 0.07]
    trailing_grid = [None, 0.05]
    hold_grid = [12, 15]

    total = (
        len(min_volume_lots_grid)
        * len(min_upside_ratio_grid)
        * len(std_penalty_grid)
        * len(gamma_grid)
        * len(min_amount_grid)
        * len(max_amount_grid)
        * len(tp_grid)
        * len(sl_grid)
        * len(trailing_grid)
        * len(hold_grid)
    )
    idx = 0
    all_rows = []

    for min_vol in min_volume_lots_grid:
        for min_up in min_upside_ratio_grid:
            for std_p in std_penalty_grid:
                for gamma in gamma_grid:
                    for min_amt in min_amount_grid:
                        for max_amt in max_amount_grid:
                            if max_amt <= min_amt:
                                continue
                            for tp in tp_grid:
                                for sl in sl_grid:
                                    for tr in trailing_grid:
                                        for h in hold_grid:
                                            idx += 1
                                            print(
                                                f"[{idx}/{total}] I vol={min_vol} up={min_up} std={std_p} "
                                                f"gamma={gamma} amt={min_amt}-{max_amt} tp={tp} sl={sl} tr={tr} h={h}"
                                            )
                                            all_rows.append(
                                                run_one_combo(
                                                    candidates=candidates,
                                                    quotes=quotes,
                                                    min_volume_lots=min_vol,
                                                    min_upside_ratio=min_up,
                                                    std_penalty=std_p,
                                                    gamma=gamma,
                                                    min_amount=min_amt,
                                                    max_amount=max_amt,
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

    print("strategyI grid search done")
    print(f"- all: {OUT_ALL}")
    print(f"- top20: {OUT_TOP20}")
    print(f"- best: {OUT_BEST}")


if __name__ == "__main__":
    main()
