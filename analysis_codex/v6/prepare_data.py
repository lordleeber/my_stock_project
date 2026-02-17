import argparse
import os
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text


FEATURES = [
    "q2_eps",
    "ly_q3_eps",
    "q2_margin",
    "q2_ocf_ratio",
    "q2_re_ratio",
    "rev_trend_m8_m7",
    "rev_trend_m9_m8",
    "margin_momentum",
    "q2_roe",
    "q2_debt_ratio",
    "q2_non_op_ratio",
]
TARGET = "target_eps"
TARGET_DELTA = "delta_eps"

KEEP_OPTIONAL = [
    "symbol",
    "name",
    "q3_date",
    "q3_close",
    "pe_current",
    "prev_q4_eps",
    "q1_eps",
    "q2_eps_official",
    "ttm_eps_official",
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
    parser = argparse.ArgumentParser(description="Prepare v6 dataset for analysis_codex from DB.")
    parser.add_argument("--start-year", type=int, default=2020)
    parser.add_argument("--end-year", type=int, default=2025)
    parser.add_argument("--market", type=str, default="sii")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def fetch_one_year(conn, year: int, market: str) -> pd.DataFrame:
    q1_str = f"{year}Q1"
    q2_str = f"{year}Q2"
    q3_str = f"{year}Q3"
    prev_q4_str = f"{year - 1}Q4"
    ly_q3_str = f"{year - 1}Q3"

    m7 = f"{year}M07"
    m8 = f"{year}M08"
    m9 = f"{year}M09"

    month_start = f"{year}-09-01"
    month_end = f"{year}-09-30"

    query = f"""
    WITH q2_data AS (
        SELECT
            i.symbol,
            i.name,
            i.revenue_q AS q2_rev,
            i.net_income_q AS q2_ni,
            i.eps_q AS q2_eps,
            i.net_income_q / NULLIF(i.revenue_q, 0) AS q2_margin,
            i.non_operating_income_q / NULLIF(i.pretax_income_q, 0) AS q2_non_op_ratio,
            i.net_income_q / NULLIF(b.total_equity, 0) AS q2_roe,
            b.total_liabilities / NULLIF(b.total_assets, 0) AS q2_debt_ratio,
            b.share_capital AS capital,
            b.retained_earnings AS q2_retained_earnings,
            c.cash_flow_operating_q AS q2_ocf
        FROM income_statement i
        JOIN balance_sheet b ON i.symbol = b.symbol AND i.date = b.date
        JOIN cash_flow c ON i.symbol = c.symbol AND i.date = c.date
        WHERE i.date = '{q2_str}' AND i.market = '{market}'
    ),
    q1_data AS (
        SELECT symbol,
               net_income_q / NULLIF(revenue_q, 0) AS q1_margin
        FROM income_statement
        WHERE date = '{q1_str}' AND market = '{market}'
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
    eps_hist AS (
        SELECT
            qr.symbol,
            qr.eps_q AS target_eps,
            (SELECT eps_q FROM quarterly_reports WHERE symbol = qr.symbol AND date = '{ly_q3_str}' AND market = '{market}') AS ly_q3_eps,
            (SELECT eps_q FROM quarterly_reports WHERE symbol = qr.symbol AND date = '{prev_q4_str}' AND market = '{market}') AS prev_q4_eps,
            (SELECT eps_q FROM quarterly_reports WHERE symbol = qr.symbol AND date = '{q1_str}' AND market = '{market}') AS q1_eps,
            (SELECT eps_q FROM quarterly_reports WHERE symbol = qr.symbol AND date = '{q2_str}' AND market = '{market}') AS q2_eps_official
        FROM quarterly_reports qr
        WHERE qr.date = '{q3_str}' AND qr.market = '{market}'
    ),
    market_snapshot AS (
        SELECT DISTINCT ON (dq.symbol)
               dq.symbol,
               dq.date AS q3_date,
               dq.close AS q3_close,
               pr.pe_ratio AS pe_current
        FROM daily_quotes dq
        LEFT JOIN pe_ratio pr
               ON pr.symbol = dq.symbol
              AND pr.market = dq.market
              AND pr.date = dq.date
        WHERE dq.market = '{market}'
          AND dq.date >= '{month_start}'
          AND dq.date <= '{month_end}'
        ORDER BY dq.symbol, dq.date DESC
    )
    SELECT
        {year} AS year,
        q2.*,
        q1.q1_margin,
        m.rev_m7,
        m.rev_m8,
        m.rev_m9,
        e.target_eps,
        e.ly_q3_eps,
        e.prev_q4_eps,
        e.q1_eps,
        e.q2_eps_official,
        ms.q3_date,
        ms.q3_close,
        ms.pe_current
    FROM q2_data q2
    LEFT JOIN q1_data q1 ON q2.symbol = q1.symbol
    JOIN this_monthly m ON q2.symbol = m.symbol
    JOIN eps_hist e ON q2.symbol = e.symbol
    LEFT JOIN market_snapshot ms ON q2.symbol = ms.symbol
    """

    return pd.read_sql(query, conn)


def main() -> None:
    args = parse_args()
    if args.start_year > args.end_year:
        raise ValueError("start-year must be <= end-year")

    engine = create_engine(get_db_url())
    frames = []

    with engine.connect() as conn:
        conn.execute(text("SET max_parallel_workers_per_gather = 0"))

        for year in range(args.start_year, args.end_year + 1):
            print(f"fetching v6 data: year={year}, market={args.market}")
            df_year = fetch_one_year(conn, year=year, market=args.market)
            if not df_year.empty:
                frames.append(df_year)

    if not frames:
        raise RuntimeError("No data fetched from DB. Check DB env, year range, and market.")

    df = pd.concat(frames, ignore_index=True)
    df = df.replace([np.inf, -np.inf], np.nan)
    df = df.dropna(subset=["q2_ni", TARGET, "year", "q2_eps"])

    df["q2_ocf_ratio"] = (df["q2_ocf"] / df["q2_ni"].replace(0, 1e-9)).clip(-5, 5)
    df["q2_re_ratio"] = df["q2_retained_earnings"] / df["capital"].replace(0, 1e-9)
    df["rev_trend_m8_m7"] = (df["rev_m8"] / df["rev_m7"].replace(0, 1e-9)) - 1
    df["rev_trend_m9_m8"] = (df["rev_m9"] / df["rev_m8"].replace(0, 1e-9)) - 1
    df["margin_momentum"] = df["q2_margin"] - df["q1_margin"].fillna(df["q2_margin"])

    df[TARGET_DELTA] = df[TARGET] - df["q2_eps"]

    # 固定化估值鏈路需要的官方 TTM
    df["ttm_eps_official"] = (
        df["prev_q4_eps"].fillna(0)
        + df["q1_eps"].fillna(0)
        + df["q2_eps_official"].fillna(0)
        + df[TARGET].fillna(0)
    )

    for feature_name in FEATURES:
        df[feature_name] = df[feature_name].fillna(0)

    keep_cols = [c for c in (KEEP_OPTIONAL + ["year"] + FEATURES + [TARGET, TARGET_DELTA]) if c in df.columns]
    out_df = df[keep_cols].copy()
    out_df["year"] = out_df["year"].astype(int)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(args.output, index=False)

    print("v6 prepare_data completed")
    print(f"- db_host: {os.getenv('DB_HOST', 'db')}")
    print(f"- year range: {args.start_year}-{args.end_year}")
    print(f"- market: {args.market}")
    print(f"- output: {args.output}")
    print(f"- rows: {len(out_df)}")


if __name__ == "__main__":
    main()
