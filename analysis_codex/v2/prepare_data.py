import argparse
import os
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine


# V2 使用的核心特徵
FEATURES = ["q2_eps", "q2_margin", "ly_q3_eps", "rev_yoy_m7"]
TARGET = "target_eps"
KEEP_OPTIONAL = ["symbol", "name", "q2_rev", "rev_m7", "rev_m8", "rev_m9", "market"]

DEFAULT_OUTPUT = Path(__file__).resolve().parent / "dataset.csv"


def get_db_url() -> str:
    user = os.getenv("DB_USER", "user")
    password = os.getenv("DB_PASSWORD", "password")
    host = os.getenv("DB_HOST", "db")
    port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME", "stock_db")
    return f"postgresql://{user}:{password}@{host}:{port}/{db_name}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare v2 dataset for analysis_codex from DB.")
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
    ly_m7 = f"{year - 1}M07"

    query = f"""
    WITH q2_data AS (
        SELECT symbol, name, market,
               eps_q AS q2_eps,
               revenue_q AS q2_rev,
               net_income_q / NULLIF(revenue_q, 0) AS q2_margin
        FROM income_statement
        WHERE date = '{q2_str}' AND market = '{market}'
    ),
    ly_data AS (
        SELECT symbol, eps_q AS ly_q3_eps
        FROM quarterly_reports
        WHERE date = '{ly_q3_str}' AND market = '{market}'
    ),
    this_rev AS (
        SELECT symbol,
               MAX(CASE WHEN date = '{m7}' THEN revenue_current END) AS rev_m7,
               MAX(CASE WHEN date = '{m8}' THEN revenue_current END) AS rev_m8,
               MAX(CASE WHEN date = '{m9}' THEN revenue_current END) AS rev_m9
        FROM monthly_revenue
        WHERE date IN ('{m7}', '{m8}', '{m9}')
        GROUP BY symbol
    ),
    last_rev AS (
        SELECT symbol,
               MAX(CASE WHEN date = '{ly_m7}' THEN revenue_current END) AS ly_rev_m7
        FROM monthly_revenue
        WHERE date = '{ly_m7}'
        GROUP BY symbol
    ),
    target AS (
        SELECT symbol, eps_q AS target_eps
        FROM quarterly_reports
        WHERE date = '{q3_str}' AND market = '{market}'
    )
    SELECT {year} AS year, q2.*,
           ly.ly_q3_eps,
           t.target_eps,
           r.rev_m7, r.rev_m8, r.rev_m9,
           (r.rev_m7 / NULLIF(lr.ly_rev_m7, 0) - 1) AS rev_yoy_m7
    FROM q2_data q2
    JOIN ly_data ly ON q2.symbol = ly.symbol
    JOIN this_rev r ON q2.symbol = r.symbol
    JOIN last_rev lr ON q2.symbol = lr.symbol
    JOIN target t ON q2.symbol = t.symbol
    """

    return pd.read_sql(query, engine)


def main() -> None:
    args = parse_args()

    if args.start_year > args.end_year:
        raise ValueError("start-year must be <= end-year")

    engine = create_engine(get_db_url())
    frames = []

    for year in range(args.start_year, args.end_year + 1):
        print(f"fetching v2 data: year={year}, market={args.market}")
        df_year = fetch_one_year(engine, year=year, market=args.market)
        if not df_year.empty:
            frames.append(df_year)

    if not frames:
        raise RuntimeError("No data fetched from DB. Check DB env, year range, and market.")

    df = pd.concat(frames, ignore_index=True)
    df = df.dropna(subset=[TARGET, "year"])

    for feature_name in FEATURES:
        df[feature_name] = df[feature_name].fillna(0)

    keep_cols = [c for c in (KEEP_OPTIONAL + ["year"] + FEATURES + [TARGET]) if c in df.columns]
    out_df = df[keep_cols].copy()
    out_df["year"] = out_df["year"].astype(int)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(args.output, index=False)

    print("v2 prepare_data completed")
    print(f"- db_host: {os.getenv('DB_HOST', 'db')}")
    print(f"- year range: {args.start_year}-{args.end_year}")
    print(f"- market: {args.market}")
    print(f"- output: {args.output}")
    print(f"- rows: {len(out_df)}")


if __name__ == "__main__":
    main()
