import argparse
import os
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import create_engine


FEATURES = ["q2_rev", "q2_margin", "q2_eps", "q3_rev_total"]
TARGET = "target_eps"
KEEP_OPTIONAL = ["symbol", "name", "naive_pred_eps", "year", "market"]

DEFAULT_OUTPUT = Path(__file__).resolve().parent / "dataset.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare v1 dataset for analysis_codex from DB.")
    parser.add_argument("--year", type=int, default=2024, help="Target year to build V1 training rows.")
    parser.add_argument("--market", type=str, default="sii", help="Market filter, e.g. sii or otc.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def get_db_url() -> str:
    user = os.getenv("DB_USER", "user")
    password = os.getenv("DB_PASSWORD", "password")
    host = os.getenv("DB_HOST", "db")
    port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME", "stock_db")
    return f"postgresql://{user}:{password}@{host}:{port}/{db_name}"


def prepare_from_db(year: int, market: str) -> pd.DataFrame:
    q2_str, q3_str = f"{year}Q2", f"{year}Q3"
    m7, m8, m9 = f"{year}M07", f"{year}M08", f"{year}M09"

    query = f"""
    WITH q2_data AS (
        SELECT i.symbol, i.name, i.market, i.revenue_q AS q2_rev,
               i.net_income_q / NULLIF(i.revenue_q, 0) AS q2_margin,
               i.eps_q AS q2_eps, b.share_capital AS capital
        FROM income_statement i
        JOIN balance_sheet b ON i.symbol = b.symbol AND i.date = b.date
        WHERE i.date = '{q2_str}' AND i.market = '{market}'
    ),
    q3_rev AS (
        SELECT symbol, SUM(revenue_current) AS q3_rev_total
        FROM monthly_revenue
        WHERE date IN ('{m7}', '{m8}', '{m9}')
        GROUP BY symbol
    ),
    q3_target AS (
        SELECT symbol, eps_q AS target_eps
        FROM quarterly_reports
        WHERE date = '{q3_str}' AND market = '{market}'
    )
    SELECT q2.symbol, q2.name, q2.market, q2.q2_rev, q2.q2_margin, q2.q2_eps,
           q2.capital, r.q3_rev_total, t.target_eps
    FROM q2_data q2
    JOIN q3_rev r ON q2.symbol = r.symbol
    JOIN q3_target t ON q2.symbol = t.symbol
    """

    engine = create_engine(get_db_url())
    df = pd.read_sql(query, engine)
    df["year"] = year
    df["naive_pred_eps"] = (df["q3_rev_total"] * df["q2_margin"]) / (df["capital"] / 10)
    return df


def main() -> None:
    args = parse_args()
    df = prepare_from_db(year=args.year, market=args.market)
    df = df.replace([np.inf, -np.inf], np.nan).dropna(subset=[TARGET])
    for col in FEATURES:
        df[col] = df[col].fillna(0)

    keep_cols = [c for c in KEEP_OPTIONAL + FEATURES + [TARGET] if c in df.columns]
    out_df = df[keep_cols].copy()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(args.output, index=False)

    print("v1 prepare_data completed")
    print(f"- db_host: {os.getenv('DB_HOST', 'db')}")
    print(f"- year: {args.year}")
    print(f"- market: {args.market}")
    print(f"- output: {args.output}")
    print(f"- rows: {len(out_df)}")


if __name__ == "__main__":
    main()
