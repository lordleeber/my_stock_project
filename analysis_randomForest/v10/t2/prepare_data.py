import argparse
import os
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text


# v10_t2: 9月初視角 -> Q2 + 7/8月，含同比與產業標準化
FEATURES = [
    "q2_eps",
    "ly_q3_eps",
    "q2_margin",
    "q2_ocf_ratio",
    "q2_re_ratio",
    "rev_yoy_m7_z",
    "rev_yoy_m8_z",
    "rev_mom_m8_m7_z",
    "margin_momentum",
    "q2_roe",
    "q2_debt_ratio",
    "q2_non_op_ratio",
]
TARGET = "target_eps"
TARGET_DELTA = "delta_eps"

KEEP_OPTIONAL = [
    "symbol", "name", "industry", "q3_date", "q3_close", "q3_volume", "pe_current",
    "prev_q4_eps", "q1_eps", "q2_eps_official", "ttm_eps_official", "feature_cutoff_date",
]

DEFAULT_OUTPUT = Path(__file__).resolve().parent / "dataset.csv"


def get_db_url() -> str:
    return f"postgresql://{os.getenv('DB_USER','user')}:{os.getenv('DB_PASSWORD','password')}@{os.getenv('DB_HOST','db')}:{os.getenv('DB_PORT','5432')}/{os.getenv('DB_NAME','stock_db')}"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Prepare v10_t2 dataset for analysis_codex from DB.")
    p.add_argument("--start-year", type=int, default=2020)
    p.add_argument("--end-year", type=int, default=2025)
    p.add_argument("--market", type=str, default="sii")
    p.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return p.parse_args()


def add_industry_zscore(df: pd.DataFrame, col: str, out_col: str) -> None:
    g = df.groupby(["year", "industry"])[col]
    mean = g.transform("mean")
    std = g.transform("std").replace(0, np.nan)
    df[out_col] = ((df[col] - mean) / std).replace([np.inf, -np.inf], np.nan).fillna(0)


def fetch_one_year(conn, year: int, market: str) -> pd.DataFrame:
    q1, q2, q3 = f"{year}Q1", f"{year}Q2", f"{year}Q3"
    p4, lyq3 = f"{year-1}Q4", f"{year-1}Q3"
    m7, m8 = f"{year}M07", f"{year}M08"
    ly_m7, ly_m8 = f"{year-1}M07", f"{year-1}M08"
    month_start, month_end = f"{year}-09-01", f"{year}-09-30"
    cutoff = f"{year}-09-10"

    sql = f"""
    WITH q2_data AS (
      SELECT i.symbol, i.name, i.revenue_q AS q2_rev, i.net_income_q AS q2_ni, i.eps_q AS q2_eps,
             i.net_income_q/NULLIF(i.revenue_q,0) AS q2_margin,
             i.non_operating_income_q/NULLIF(i.pretax_income_q,0) AS q2_non_op_ratio,
             i.net_income_q/NULLIF(b.total_equity,0) AS q2_roe,
             b.total_liabilities/NULLIF(b.total_assets,0) AS q2_debt_ratio,
             b.share_capital AS capital, b.retained_earnings AS q2_retained_earnings,
             c.cash_flow_operating_q AS q2_ocf
      FROM income_statement i
      JOIN balance_sheet b ON i.symbol=b.symbol AND i.date=b.date
      JOIN cash_flow c ON i.symbol=c.symbol AND i.date=c.date
      WHERE i.date='{q2}' AND i.market='{market}'
    ),
    q1_data AS (
      SELECT symbol, net_income_q/NULLIF(revenue_q,0) AS q1_margin
      FROM income_statement WHERE date='{q1}' AND market='{market}'
    ),
    this_monthly AS (
      SELECT symbol,
             MAX(CASE WHEN date='{m7}' THEN revenue_current END) AS rev_m7,
             MAX(CASE WHEN date='{m8}' THEN revenue_current END) AS rev_m8,
             MAX(CASE WHEN date='{ly_m7}' THEN revenue_current END) AS rev_m7_ly,
             MAX(CASE WHEN date='{ly_m8}' THEN revenue_current END) AS rev_m8_ly
      FROM monthly_revenue
      WHERE date IN ('{m7}','{m8}','{ly_m7}','{ly_m8}')
      GROUP BY symbol
    ),
    eps_hist AS (
      SELECT qr.symbol, qr.eps_q AS target_eps,
             (SELECT eps_q FROM quarterly_reports WHERE symbol=qr.symbol AND date='{lyq3}' AND market='{market}') AS ly_q3_eps,
             (SELECT eps_q FROM quarterly_reports WHERE symbol=qr.symbol AND date='{p4}' AND market='{market}') AS prev_q4_eps,
             (SELECT eps_q FROM quarterly_reports WHERE symbol=qr.symbol AND date='{q1}' AND market='{market}') AS q1_eps,
             (SELECT eps_q FROM quarterly_reports WHERE symbol=qr.symbol AND date='{q2}' AND market='{market}') AS q2_eps_official
      FROM quarterly_reports qr WHERE qr.date='{q3}' AND qr.market='{market}'
    ),
    market_snapshot AS (
      SELECT DISTINCT ON (dq.symbol) dq.symbol, dq.date AS q3_date, dq.close AS q3_close, dq.volume AS q3_volume, pr.pe_ratio AS pe_current
      FROM daily_quotes dq
      LEFT JOIN pe_ratio pr ON pr.symbol=dq.symbol AND pr.market=dq.market AND pr.date=dq.date
      WHERE dq.market='{market}' AND dq.date>='{month_start}' AND dq.date<='{month_end}'
      ORDER BY dq.symbol, dq.date DESC
    )
    SELECT {year} AS year, '{cutoff}' AS feature_cutoff_date, q2.*, q1.q1_margin,
           m.rev_m7,m.rev_m8,m.rev_m7_ly,m.rev_m8_ly,
           e.target_eps,e.ly_q3_eps,e.prev_q4_eps,e.q1_eps,e.q2_eps_official,
           ms.q3_date,ms.q3_close,ms.q3_volume,ms.pe_current
    FROM q2_data q2
    LEFT JOIN q1_data q1 ON q2.symbol=q1.symbol
    JOIN this_monthly m ON q2.symbol=m.symbol
    JOIN eps_hist e ON q2.symbol=e.symbol
    LEFT JOIN market_snapshot ms ON q2.symbol=ms.symbol
    """
    return pd.read_sql(sql, conn)


def main() -> None:
    args = parse_args()
    if args.start_year > args.end_year:
        raise ValueError("start-year must be <= end-year")

    engine = create_engine(get_db_url())
    frames = []
    with engine.connect() as conn:
        conn.execute(text("SET max_parallel_workers_per_gather = 0"))
        for year in range(args.start_year, args.end_year + 1):
            print(f"fetching v10_t2 data: year={year}, market={args.market}")
            y = fetch_one_year(conn, year, args.market)
            if not y.empty:
                frames.append(y)
        try:
            industry_df = pd.read_sql(f"SELECT symbol, industry FROM stock_info WHERE market = '{args.market}'", conn)
        except Exception:
            industry_df = pd.DataFrame(columns=["symbol", "industry"])

    if not frames:
        raise RuntimeError("No data fetched from DB. Check DB env, year range, and market.")

    df = pd.concat(frames, ignore_index=True)
    if not industry_df.empty:
        df = df.merge(industry_df, on="symbol", how="left")
    df["industry"] = df.get("industry", pd.Series(index=df.index)).fillna("unknown")

    df = df.replace([np.inf, -np.inf], np.nan).dropna(subset=["q2_ni", TARGET, "year", "q2_eps"])

    df["q2_ocf_ratio"] = (df["q2_ocf"] / df["q2_ni"].replace(0, 1e-9)).clip(-5, 5)
    df["q2_re_ratio"] = df["q2_retained_earnings"] / df["capital"].replace(0, 1e-9)
    df["margin_momentum"] = df["q2_margin"] - df["q1_margin"].fillna(df["q2_margin"])

    df["rev_yoy_m7"] = (df["rev_m7"] / df["rev_m7_ly"].replace(0, 1e-9)) - 1
    df["rev_yoy_m8"] = (df["rev_m8"] / df["rev_m8_ly"].replace(0, 1e-9)) - 1
    df["rev_mom_m8_m7"] = (df["rev_m8"] / df["rev_m7"].replace(0, 1e-9)) - 1

    add_industry_zscore(df, "rev_yoy_m7", "rev_yoy_m7_z")
    add_industry_zscore(df, "rev_yoy_m8", "rev_yoy_m8_z")
    add_industry_zscore(df, "rev_mom_m8_m7", "rev_mom_m8_m7_z")

    df[TARGET_DELTA] = df[TARGET] - df["q2_eps"]
    df["ttm_eps_official"] = df["prev_q4_eps"].fillna(0) + df["q1_eps"].fillna(0) + df["q2_eps_official"].fillna(0) + df[TARGET].fillna(0)

    for c in FEATURES:
        df[c] = df[c].fillna(0)

    keep = [c for c in (KEEP_OPTIONAL + ["year"] + FEATURES + [TARGET, TARGET_DELTA]) if c in df.columns]
    out = df[keep].copy()
    out["year"] = out["year"].astype(int)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.output, index=False)

    print("v10_t2 prepare_data completed")
    print(f"- output: {args.output}")
    print(f"- rows: {len(out)}")


if __name__ == "__main__":
    main()
