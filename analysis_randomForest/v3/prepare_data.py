import argparse
import os
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import create_engine


# V3 使用的核心特徵
FEATURES = [
    "q2_eps",
    "q2_margin",
    "ly_q3_eps",
    "rev_trend_m8_m7",
    "rev_trend_m9_m8",
    "q2_ocf_ratio",
    "q2_re_ratio",
]
TARGET = "target_eps"
KEEP_OPTIONAL = [
    "symbol",
    "name",
    "q2_rev",
    "q2_ni",
    "q2_ocf",
    "q2_retained_earnings",
    "rev_m7",
    "rev_m8",
    "rev_m9",
]

DEFAULT_OUTPUT = Path(__file__).resolve().parent / "dataset.csv"


def get_db_url() -> str:
    user = os.getenv("DB_USER", "user")
    password = os.getenv("DB_PASSWORD", "password")
    host = os.getenv("DB_HOST", "db")
    port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME", "stock_db")
    return f"postgresql://{user}:{password}@{host}:{port}/{db_name}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare v3 dataset for analysis_codex from DB.")
    parser.add_argument("--start-year", type=int, default=2020)
    parser.add_argument("--end-year", type=int, default=2025)
    parser.add_argument("--market", type=str, default="sii")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def fetch_one_year(engine, year: int, market: str) -> pd.DataFrame:
    q2_str = f"{year}Q2"
    q3_str = f"{year}Q3"
    ly_q3_str = f"{year - 1}Q3"

    m7 = f"{year}M07"
    m8 = f"{year}M08"
    m9 = f"{year}M09"

    query = f"""
    WITH q2_fundamental AS (
        SELECT i.symbol, i.name,
               i.revenue_q AS q2_rev,
               i.net_income_q AS q2_ni,
               i.net_income_q / NULLIF(i.revenue_q, 0) AS q2_margin,
               i.eps_q AS q2_eps,
               b.share_capital AS capital,
               b.retained_earnings AS q2_retained_earnings,
               c.cash_flow_operating_q AS q2_ocf
        FROM income_statement i
        JOIN balance_sheet b ON i.symbol = b.symbol AND i.date = b.date
        JOIN cash_flow c ON i.symbol = c.symbol AND i.date = c.date
        WHERE i.date = '{q2_str}' AND i.market = '{market}'
    ),
    this_monthly AS (
        SELECT symbol,
               MAX(CASE WHEN date = '{m7}' THEN revenue_current END) AS rev_m7,
               MAX(CASE WHEN date = '{m8}' THEN revenue_current END) AS rev_m8,
               MAX(CASE WHEN date = '{m9}' THEN revenue_current END) AS rev_m9
        FROM monthly_revenue
        WHERE date IN ('{m7}', '{m8}', '{m9}')
        GROUP BY symbol
    ),
    target_q3 AS (
        SELECT qr.symbol,
               qr.eps_q AS target_eps,
               (SELECT qly.eps_q FROM quarterly_reports qly WHERE qly.symbol = qr.symbol AND qly.date = '{ly_q3_str}' AND qly.market = '{market}') AS ly_q3_eps
        FROM quarterly_reports qr
        WHERE qr.date = '{q3_str}' AND qr.market = '{market}'
    )
    SELECT {year} AS year,
           f.*,
           m.rev_m7, m.rev_m8, m.rev_m9,
           t.ly_q3_eps, t.target_eps
    FROM q2_fundamental f
    JOIN this_monthly m ON f.symbol = m.symbol
    JOIN target_q3 t ON f.symbol = t.symbol
    """

    return pd.read_sql(query, engine)


def main() -> None:
    args = parse_args()

    if args.start_year > args.end_year:
        raise ValueError("start-year must be <= end-year")

    engine = create_engine(get_db_url())
    frames = []

    for year in range(args.start_year, args.end_year + 1):
        print(f"fetching v3 data: year={year}, market={args.market}")
        df_year = fetch_one_year(engine, year=year, market=args.market)
        if not df_year.empty:
            frames.append(df_year)

    if not frames:
        raise RuntimeError("No data fetched from DB. Check DB env, year range, and market.")

    df = pd.concat(frames, ignore_index=True)
    df = df.replace([np.inf, -np.inf], np.nan)
    df = df.dropna(subset=["q2_ni", "q2_ocf", TARGET, "year"])

    # 由原始欄位衍生 V3 特徵
    df["q2_ocf_ratio"] = (df["q2_ocf"] / df["q2_ni"].replace(0, 1e-9)).clip(-5, 5)
    df["q2_re_ratio"] = df["q2_retained_earnings"] / df["capital"].replace(0, 1e-9)
    df["rev_trend_m8_m7"] = (df["rev_m8"] / df["rev_m7"].replace(0, 1e-9)) - 1
    df["rev_trend_m9_m8"] = (df["rev_m9"] / df["rev_m8"].replace(0, 1e-9)) - 1

    for feature_name in FEATURES:
        df[feature_name] = df[feature_name].fillna(0)

    keep_cols = [c for c in (KEEP_OPTIONAL + ["year"] + FEATURES + [TARGET]) if c in df.columns]
    out_df = df[keep_cols].copy()
    out_df["year"] = out_df["year"].astype(int)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(args.output, index=False)

    print("v3 prepare_data completed")
    print(f"- db_host: {os.getenv('DB_HOST', 'db')}")
    print(f"- year range: {args.start_year}-{args.end_year}")
    print(f"- market: {args.market}")
    print(f"- output: {args.output}")
    print(f"- rows: {len(out_df)}")


if __name__ == "__main__":
    main()
