"""Diagnostic: do any regime signals predict next-cohort realized PnL?

Joins per-cohort realized PnL (from backtester rolling output) with regime
features computed on cohort_entry_date:
  - TWII MA20 vs MA60 spread
  - TWII close vs MA20 spread
  - TWII trailing 20d / 60d return
  - TWII trailing 20d realized volatility (annualized)
  - top10 ml_score mean per cohort (model self-confidence)
  - existing Bull/Bear/Sideways label (already in rolling_monthly.csv)

Outputs:
  - prints correlation table and quintile means per signal
  - writes scripts/output/regime_diagnostic.csv (per-cohort joined data)
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from common.db import get_db_url  # noqa: E402

OUT_DIR = ROOT / "scripts" / "output"
OUT_CSV = OUT_DIR / "regime_diagnostic.csv"
TWII_INDEX_NAME = "發行量加權股價指數"


def load_twii() -> pd.DataFrame:
    engine = create_engine(get_db_url())
    with engine.connect() as conn:
        df = pd.read_sql(
            text(
                """
                SELECT date, index_close
                FROM market_indices
                WHERE index_name = :name
                ORDER BY date
                """
            ),
            conn,
            params={"name": TWII_INDEX_NAME},
        )
    df["date"] = pd.to_datetime(df["date"])
    df["index_close"] = pd.to_numeric(df["index_close"], errors="coerce")
    df = df.dropna().drop_duplicates("date").sort_values("date").reset_index(drop=True)
    df["log_ret"] = np.log(df["index_close"]).diff()
    df["ma20"] = df["index_close"].rolling(20, min_periods=10).mean()
    df["ma60"] = df["index_close"].rolling(60, min_periods=20).mean()
    df["ret_20d"] = df["index_close"].pct_change(20)
    df["ret_60d"] = df["index_close"].pct_change(60)
    df["vol_20d_ann"] = df["log_ret"].rolling(20, min_periods=10).std() * np.sqrt(252)
    return df


def features_at(twii: pd.DataFrame, date: str) -> dict:
    sub = twii[twii["date"] <= pd.to_datetime(date)]
    if sub.empty:
        return {}
    row = sub.iloc[-1]
    ma20 = float(row["ma20"])
    ma60 = float(row["ma60"])
    close = float(row["index_close"])
    return {
        "twii_close": close,
        "twii_ma20": ma20,
        "twii_ma60": ma60,
        "ma20_vs_ma60_pct": (ma20 / ma60 - 1) * 100 if ma60 else np.nan,
        "close_vs_ma20_pct": (close / ma20 - 1) * 100 if ma20 else np.nan,
        "ret_20d_pct": float(row["ret_20d"]) * 100
        if pd.notna(row["ret_20d"])
        else np.nan,
        "ret_60d_pct": float(row["ret_60d"]) * 100
        if pd.notna(row["ret_60d"])
        else np.nan,
        "vol_20d_ann_pct": float(row["vol_20d_ann"]) * 100
        if pd.notna(row["vol_20d_ann"])
        else np.nan,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--monthly-csv",
        default=str(
            ROOT
            / "backtester"
            / "output"
            / "sweep_top_n"
            / "top_10"
            / "rolling_monthly.csv"
        ),
        help="rolling_monthly.csv to source per-cohort realized PnL from",
    )
    p.add_argument(
        "--score-csv",
        default=str(ROOT / "scripts" / "output" / "ml_score_distribution.csv"),
        help="per-cohort ml_score distribution (from ml_score_distribution.py)",
    )
    p.add_argument(
        "--top-n",
        type=int,
        default=10,
        help="top_n used in the backtest (for cohort capital baseline)",
    )
    p.add_argument("--position-amount", type=float, default=100_000.0)
    args = p.parse_args()

    monthly = pd.read_csv(args.monthly_csv)
    cohort_rows = monthly.dropna(
        subset=["realized_net_pnl", "cohort_entry_date"]
    ).copy()
    cohort_rows["cohort_entry_date"] = cohort_rows["cohort_entry_date"].astype(str)

    score_df = pd.read_csv(args.score_csv)
    score_df["playbook_date"] = score_df["playbook_date"].astype(str)
    score_df["ym"] = score_df["playbook_date"].str[:7]

    twii = load_twii()

    records = []
    for _, r in cohort_rows.iterrows():
        ce = r["cohort_entry_date"]
        feats = features_at(twii, ce)
        if not feats:
            continue
        cohort_capital = args.top_n * args.position_amount
        ret_pct = float(r["realized_net_pnl"]) / cohort_capital * 100
        rec = {
            "cohort_entry_date": ce,
            "settle_playbook_date": r["playbook_date"],
            "regime_label": r["regime"],
            "realized_pnl": float(r["realized_net_pnl"]),
            "realized_ret_pct": ret_pct,
            **feats,
        }
        match = score_df[score_df["ym"] == ce[:7]]
        if len(match) >= 1:
            rec["score_topN_mean"] = float(match[f"top{args.top_n}_mean"].iloc[0])
            rec["score_median"] = float(match["median"].iloc[0])
            rec["score_p90"] = float(match["p90"].iloc[0])
            rec["score_max"] = float(match["max"].iloc[0])
        records.append(rec)

    df = pd.DataFrame(records).sort_values("cohort_entry_date").reset_index(drop=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_CSV, index=False)

    print(f"=== diagnostic: {len(df)} settled cohorts ===")
    print(f"period: {df['cohort_entry_date'].min()} → {df['cohort_entry_date'].max()}")
    print(
        f"realized_ret_pct: mean={df['realized_ret_pct'].mean():+.3f}%  std={df['realized_ret_pct'].std():+.3f}%"
    )

    signals = [
        "ma20_vs_ma60_pct",
        "close_vs_ma20_pct",
        "ret_20d_pct",
        "ret_60d_pct",
        "vol_20d_ann_pct",
        "score_topN_mean",
        "score_median",
        "score_p90",
        "score_max",
    ]
    signals = [s for s in signals if s in df.columns]

    print("\n=== correlation: signal (at entry) vs realized cohort return ===")
    corr_rows = []
    for s in signals:
        sub = df[[s, "realized_ret_pct"]].dropna()
        if len(sub) < 5:
            continue
        pearson = sub.corr().iloc[0, 1]
        spearman = sub.corr(method="spearman").iloc[0, 1]
        corr_rows.append(
            {"signal": s, "n": len(sub), "pearson": pearson, "spearman": spearman}
        )
    corr_df = pd.DataFrame(corr_rows)
    print(
        corr_df.to_string(
            index=False,
            formatters={"pearson": "{:+.3f}".format, "spearman": "{:+.3f}".format},
        )
    )

    print(
        "\n=== quintile means (Q1 = lowest signal, Q5 = highest) — realized_ret_pct mean ==="
    )
    q_rows = []
    for s in signals:
        sub = df[[s, "realized_ret_pct"]].dropna()
        if len(sub) < 10:
            continue
        try:
            sub["q"] = pd.qcut(
                sub[s], 5, labels=["Q1", "Q2", "Q3", "Q4", "Q5"], duplicates="drop"
            )
        except ValueError:
            continue
        means = sub.groupby("q", observed=True)["realized_ret_pct"].mean()
        row = {"signal": s, "n": len(sub)}
        for q in ["Q1", "Q2", "Q3", "Q4", "Q5"]:
            row[q] = means.get(q, np.nan)
        row["Q5-Q1"] = (
            (row["Q5"] - row["Q1"])
            if pd.notna(row["Q1"]) and pd.notna(row["Q5"])
            else np.nan
        )
        q_rows.append(row)
    q_df = pd.DataFrame(q_rows)
    fmt = q_df.copy()
    for c in ["Q1", "Q2", "Q3", "Q4", "Q5", "Q5-Q1"]:
        if c in fmt.columns:
            fmt[c] = fmt[c].map(lambda x: f"{x:+.2f}%" if pd.notna(x) else "n/a")
    print(fmt.to_string(index=False))

    print("\n=== regime label means ===")
    label_means = df.groupby("regime_label")["realized_ret_pct"].agg(
        ["count", "mean", "std", "min", "max"]
    )
    print(label_means.to_string(float_format=lambda x: f"{x:+.3f}"))

    print(f"\nwrote {OUT_CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
