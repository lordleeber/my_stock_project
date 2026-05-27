import argparse
import os
import sys
import traceback

import pandas as pd
from sqlalchemy import text

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(os.path.dirname(__file__))
from common.schemas import SCHEMA_COLS
from _incremental import get_engine, get_last_processed_date

ERROR_LOG = "/error_valuation_calculator.log"
TABLE = "valuation_daily"


def get_publish_date(q_str):
    """財報官方公佈截止日 (生效日 = publish_date)."""
    year = int(q_str[:4])
    q = q_str[5]
    if q == "1":
        return f"{year}-05-15"
    if q == "2":
        return f"{year}-08-14"
    if q == "3":
        return f"{year}-11-14"
    return f"{year + 1}-03-31"


def _create_table_if_missing(engine):
    with engine.begin() as conn:
        conn.execute(
            text(
                f"""
            CREATE TABLE IF NOT EXISTS {TABLE} (
                date TEXT NOT NULL,
                symbol TEXT NOT NULL,
                close DOUBLE PRECISION,
                ttm_eps_official DOUBLE PRECISION,
                pe_official DOUBLE PRECISION,
                pe_percentile_official DOUBLE PRECISION,
                roe_official DOUBLE PRECISION,
                pced_file TEXT,
                pced_row BIGINT,
                pced_col TEXT,
                PRIMARY KEY (date, symbol)
            )
            """
            )
        )
        conn.execute(
            text(
                f"CREATE INDEX IF NOT EXISTS idx_val_daily_symbol_date ON {TABLE} (symbol, date)"
            )
        )


def compute_new_rows(engine, last_processed):
    """PIT merge_asof: daily price → latest EPS publish_date <= price date.
    Returns DataFrame with pe_calculated, roe_official, pe_official for the
    new date window (or full history if last_processed is None)."""
    df_eps = pd.read_sql(
        "SELECT date, symbol, eps_q, nav_per_share FROM quarterly_reports_xbrl "
        "WHERE period_type = 'quarter' ORDER BY symbol, date",
        engine,
    )
    df_eps = df_eps.sort_values(["symbol", "date"])
    df_eps["ttm_eps_official"] = df_eps.groupby("symbol")["eps_q"].transform(
        lambda x: x.rolling(window=4).sum()
    )
    df_eps["publish_date"] = pd.to_datetime(df_eps["date"].apply(get_publish_date))
    df_eps = df_eps.sort_values("publish_date")

    if last_processed is None:
        df_prices = pd.read_sql(
            "SELECT date, symbol, close FROM daily_quotes ORDER BY symbol, date", engine
        )
        df_official_pe = pd.read_sql(
            "SELECT date, symbol, pe_ratio AS pe_official FROM pe_ratio", engine
        )
    else:
        df_prices = pd.read_sql(
            text(
                "SELECT date, symbol, close FROM daily_quotes "
                "WHERE date > :last ORDER BY symbol, date"
            ),
            engine,
            params={"last": last_processed},
        )
        df_official_pe = pd.read_sql(
            text(
                "SELECT date, symbol, pe_ratio AS pe_official FROM pe_ratio "
                "WHERE date > :last"
            ),
            engine,
            params={"last": last_processed},
        )

    if df_prices.empty:
        return pd.DataFrame()

    df_prices["date_ts"] = pd.to_datetime(df_prices["date"])
    df_prices = df_prices.sort_values("date_ts")

    eps_slim = df_eps[
        ["symbol", "publish_date", "ttm_eps_official", "nav_per_share"]
    ].dropna(subset=["ttm_eps_official"])

    df_combined = pd.merge_asof(
        df_prices,
        eps_slim,
        left_on="date_ts",
        right_on="publish_date",
        by="symbol",
        direction="backward",
    )
    df_combined = df_combined.merge(df_official_pe, on=["symbol", "date"], how="left")
    df_combined = df_combined[df_combined["ttm_eps_official"] > 0].copy()

    df_combined["pe_calculated"] = (
        df_combined["close"] / df_combined["ttm_eps_official"]
    ).round(2)
    df_combined["roe_official"] = (
        df_combined["ttm_eps_official"] / df_combined["nav_per_share"] * 100
    ).round(2)
    return df_combined


def add_pit_expanding_rank(engine, new_df, last_processed):
    """PIT-safe pe_percentile_official: for each row, rank pe_calculated against
    {same symbol's PE values with date <= this row's date}. Implemented via
    pandas expanding().rank(pct=True) over (historical DB PEs ∪ new batch PEs)
    sorted by date, then we filter back to new rows.

    Historical pe_calculated is reconstructed from stored close/ttm_eps_official
    (the table doesn't persist pe_calculated)."""
    if last_processed is None:
        history = pd.DataFrame(columns=["symbol", "date", "pe_calculated"])
    else:
        history = pd.read_sql(
            text(
                "SELECT symbol, date, close, ttm_eps_official FROM valuation_daily "
                "WHERE ttm_eps_official > 0 AND date <= :last"
            ),
            engine,
            params={"last": last_processed},
        )
        history["pe_calculated"] = (
            history["close"] / history["ttm_eps_official"]
        ).round(2)
        history = history[["symbol", "date", "pe_calculated"]]

    new_slim = new_df[["symbol", "date", "pe_calculated"]].copy()
    new_slim["_is_new"] = True
    history = history.copy()
    history["_is_new"] = False

    combined = pd.concat([history, new_slim], ignore_index=True)
    combined = combined.sort_values(["symbol", "date"])
    rank_series = (
        combined.groupby("symbol")["pe_calculated"]
        .expanding()
        .rank(pct=True)
        .reset_index(level=0, drop=True)
    )
    combined["rank_pct"] = rank_series

    new_with_rank = combined[combined["_is_new"]][["symbol", "date", "rank_pct"]]
    out = new_df.merge(new_with_rank, on=["symbol", "date"], how="left")
    out["pe_percentile_official"] = (out["rank_pct"] * 100).round(4)
    return out


def run(force_full=False):
    print(
        "Starting Point-in-Time Valuation Calculator (incremental, PIT expanding rank)..."
    )
    engine = get_engine()

    if force_full:
        with engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS {TABLE}"))
        last_processed = None
        print("Force-full mode: dropped existing table, recomputing all history.")
    else:
        last_processed = get_last_processed_date(engine, TABLE)

    _create_table_if_missing(engine)

    if last_processed is None:
        print("Computing full history...")
    else:
        print(f"Incremental: appending rows with date > {last_processed}")

    df = compute_new_rows(engine, last_processed)
    if df.empty:
        print("No new rows to insert.")
        return

    df = add_pit_expanding_rank(engine, df, last_processed)
    df["date"] = df["date_ts"].dt.strftime("%Y-%m-%d")
    df["pced_file"] = "calculated_pit"
    df["pced_row"] = 0
    df["pced_col"] = "x"

    final_cols = SCHEMA_COLS["valuation_daily"]
    output_df = df[[c for c in final_cols if c in df.columns]]

    if last_processed is not None:
        with engine.begin() as conn:
            conn.execute(
                text(f"DELETE FROM {TABLE} WHERE date > :last"),
                {"last": last_processed},
            )

    output_df.to_sql(TABLE, engine, if_exists="append", index=False, chunksize=5000)

    with engine.connect() as conn:
        total_rows = conn.execute(text(f"SELECT COUNT(*) FROM {TABLE}")).scalar()
        min_date, max_date = conn.execute(
            text(f"SELECT MIN(date), MAX(date) FROM {TABLE}")
        ).fetchone()

    print(
        f"{TABLE}: inserted {len(output_df)} rows; total {total_rows} ({min_date} ~ {max_date})"
    )


def main():
    parser = argparse.ArgumentParser(
        description="Compute valuation_daily incrementally with PIT expanding-rank percentile."
    )
    parser.add_argument(
        "--force-full",
        action="store_true",
        help="Drop output table and recompute full history (used after schema "
        "changes / bug fixes; for the pe_percentile_official PIT migration, "
        "see backfill_pit_percentile.py instead).",
    )
    args = parser.parse_args()
    try:
        run(force_full=args.force_full)
    except Exception as e:
        print(f"Error: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
