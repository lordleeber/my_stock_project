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
        "strategy_name": "F_trade_rule",
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


def _rank01(s: pd.Series) -> pd.Series:
    return s.rank(pct=True, method="average")


def add_relative_strength_features(candidates: pd.DataFrame) -> pd.DataFrame:
    out = candidates.copy()
    out["close"] = pd.to_numeric(out["close"], errors="coerce")
    out["predict_target_price"] = pd.to_numeric(out["predict_target_price"], errors="coerce")
    out["pred_rf_delta"] = pd.to_numeric(out["pred_rf_delta"], errors="coerce")
    out["pred_delta_std"] = pd.to_numeric(out["pred_delta_std"], errors="coerce")
    out["volume_lots"] = pd.to_numeric(out["volume_lots"], errors="coerce")

    out["upside_ratio"] = out["predict_target_price"] / out["close"]
    out["upside_ratio"] = out["upside_ratio"].replace([np.inf, -np.inf], np.nan)

    out["r_up"] = _rank01(out["upside_ratio"])
    out["r_delta"] = _rank01(out["pred_rf_delta"])
    out["r_vol"] = _rank01(np.log1p(out["volume_lots"].clip(lower=0)))
    out["r_conf"] = _rank01((-out["pred_delta_std"]).fillna(-999))
    return out


def build_rs_score(df: pd.DataFrame, rs_mode: str) -> pd.Series:
    if rs_mode == "upside_only":
        return df["r_up"]
    if rs_mode == "upside_plus_delta":
        return 0.7 * df["r_up"] + 0.3 * df["r_delta"]
    # composite
    return 0.45 * df["r_up"] + 0.25 * df["r_delta"] + 0.15 * df["r_vol"] + 0.15 * df["r_conf"]


def run_one_combo(
    candidates: pd.DataFrame,
    quotes: pd.DataFrame,
    rs_mode: str,
    top_quantile: float,
    min_upside_ratio: float,
    tp_pct: float,
    sl_pct: float,
    trailing_pct: float | None,
    max_hold_days: int,
) -> dict:
    entry_dt = pd.to_datetime("2025-10-13")
    end_dt = pd.to_datetime("2025-11-20")

    feat = add_relative_strength_features(candidates)
    feat["rs_score"] = build_rs_score(feat, rs_mode=rs_mode)

    valid = feat["upside_ratio"].notna() & feat["rs_score"].notna()
    if valid.any():
        threshold = float(feat.loc[valid, "rs_score"].quantile(top_quantile))
    else:
        threshold = 1.0

    selected_mask = (
        valid
        & (feat["upside_ratio"] >= min_upside_ratio)
        & (feat["rs_score"] >= threshold)
    )
    selected = feat[selected_mask].copy()

    cfg = build_trade_config(
        tp_pct=tp_pct,
        sl_pct=sl_pct,
        trailing_pct=trailing_pct,
        max_hold_days=max_hold_days,
    )

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
        f"F_{rs_mode}_q{int(top_quantile*100)}_u{int(min_upside_ratio*100)}"
        f"_tp{int(tp_pct*100)}_sl{int(sl_pct*100)}_tr"
        f"{'none' if trailing_pct is None else int(trailing_pct*100)}_h{max_hold_days}"
    )

    return {
        "strategy_name": strategy_name,
        "rs_mode": rs_mode,
        "top_quantile": top_quantile,
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

    rs_mode_grid = ["upside_only", "upside_plus_delta", "composite"]
    top_quantile_grid = [0.50, 0.60, 0.70, 0.80]
    min_upside_ratio_grid = [1.03, 1.05, 1.08]
    tp_grid = [0.10, 0.12, 0.14]
    sl_grid = [0.05, 0.07]
    trail_grid = [None, 0.05]
    hold_grid = [12, 15]

    total = (
        len(rs_mode_grid)
        * len(top_quantile_grid)
        * len(min_upside_ratio_grid)
        * len(tp_grid)
        * len(sl_grid)
        * len(trail_grid)
        * len(hold_grid)
    )
    idx = 0
    all_rows = []

    for rs_mode in rs_mode_grid:
        for q in top_quantile_grid:
            for u in min_upside_ratio_grid:
                for tp in tp_grid:
                    for sl in sl_grid:
                        for tr in trail_grid:
                            for h in hold_grid:
                                idx += 1
                                print(f"[{idx}/{total}] F {rs_mode} q={q} u={u} tp={tp} sl={sl} tr={tr} h={h}")
                                all_rows.append(
                                    run_one_combo(
                                        candidates=candidates,
                                        quotes=quotes,
                                        rs_mode=rs_mode,
                                        top_quantile=q,
                                        min_upside_ratio=u,
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

    print("strategyF grid search ready/done")
    print(f"- all: {OUT_ALL}")
    print(f"- top20: {OUT_TOP20}")
    print(f"- best: {OUT_BEST}")


if __name__ == "__main__":
    main()

