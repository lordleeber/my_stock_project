"""One-time migration: rewrite valuation_daily.pe_percentile_official under
PIT-safe expanding-rank semantics.

Before: pe_percentile_official ranked each (symbol, date)'s PE against the
        full historical PE distribution _as of compute time_. New later rows
        could shift older rows' rank → backtest drift.

After:  For each (symbol, date), rank PE against {same symbol's PE values
        with date <= this row's date}. Once written, the row is frozen.

calculate_valuation.py already produces this semantics for new rows after the
Phase 1 refactor; this script aligns the historical tail.
"""

import argparse
import os
import sys
import traceback

import pandas as pd
from sqlalchemy import text

sys.path.append(os.path.dirname(__file__))
from _incremental import get_engine

TABLE = "valuation_daily"
TEMP_TABLE = "_pit_percentile_backfill"


def compute_expanding_rank(df):
    """df: columns [symbol, date, pe_calculated]. Returns df with extra
    column pe_percentile_official_new (0..100, rounded 4dp)."""
    df = df.sort_values(["symbol", "date"]).reset_index(drop=True)
    rank_series = (
        df.groupby("symbol")["pe_calculated"]
        .expanding()
        .rank(pct=True)
        .reset_index(level=0, drop=True)
    )
    df["pe_percentile_official_new"] = (rank_series * 100).round(4)
    return df


def run(dry_run=False):
    print(f"Starting PIT percentile backfill on {TABLE}...")
    engine = get_engine()

    print("Loading existing rows (close + ttm_eps_official)...")
    df = pd.read_sql(
        f"SELECT symbol, date, close, ttm_eps_official, pe_percentile_official "
        f"FROM {TABLE} WHERE ttm_eps_official > 0",
        engine,
    )
    print(f"  loaded {len(df)} rows across {df['symbol'].nunique()} symbols")

    df["pe_calculated"] = (df["close"] / df["ttm_eps_official"]).round(2)
    df = compute_expanding_rank(df)

    print(
        "  before: avg(pe_percentile_official) = "
        f"{df['pe_percentile_official'].mean():.4f}"
    )
    print(
        "  after:  avg(pe_percentile_official_new) = "
        f"{df['pe_percentile_official_new'].mean():.4f}"
    )

    drift = (df["pe_percentile_official_new"] - df["pe_percentile_official"]).abs()
    print(f"  per-row |Δ| mean={drift.mean():.4f}, max={drift.max():.4f}")

    sample_symbols = df["symbol"].drop_duplicates().sample(
        min(3, df["symbol"].nunique()), random_state=42
    )
    for sym in sample_symbols:
        sub = df[df["symbol"] == sym].head(5)[
            ["date", "pe_calculated", "pe_percentile_official", "pe_percentile_official_new"]
        ]
        print(f"\n  sample {sym} (earliest 5 rows):")
        print(sub.to_string(index=False))

    if dry_run:
        print("\n[DRY RUN] No writes performed.")
        return

    print(f"\nWriting {TEMP_TABLE} for bulk UPDATE...")
    # valuation_daily has a handful of legitimate (symbol, date) duplicates
    # caused by upstream pe_ratio carrying two pe_official values for the same
    # day (pre/post announcement). All duplicates share the same pe_calculated
    # → same new percentile → safe to dedupe before writing the temp table.
    # Verify the invariant before dedupe — if upstream behavior ever changes
    # so duplicates carry different PEs, dedupe would silently drop the
    # divergent percentile.
    dup_check = (
        df.groupby(["symbol", "date"])["pe_percentile_official_new"].nunique()
    )
    inconsistent = dup_check[dup_check > 1]
    if len(inconsistent) > 0:
        sample = inconsistent.head(5)
        raise AssertionError(
            f"Found {len(inconsistent)} (symbol, date) groups with divergent "
            f"pe_percentile_official_new — dedupe assumption violated. "
            f"Sample:\n{sample}"
        )
    write_df = (
        df[["symbol", "date", "pe_percentile_official_new"]]
        .drop_duplicates(subset=["symbol", "date"])
        .rename(columns={"pe_percentile_official_new": "new_pct"})
    )

    with engine.begin() as conn:
        conn.execute(text(f"DROP TABLE IF EXISTS {TEMP_TABLE}"))
        conn.execute(text(
            f"""
            CREATE TABLE {TEMP_TABLE} (
                symbol TEXT NOT NULL,
                date TEXT NOT NULL,
                new_pct DOUBLE PRECISION,
                PRIMARY KEY (symbol, date)
            )
            """
        ))

    write_df.to_sql(TEMP_TABLE, engine, if_exists="append", index=False, chunksize=10000)

    print(f"Running bulk UPDATE against {TABLE}...")
    with engine.begin() as conn:
        result = conn.execute(text(
            f"""
            UPDATE {TABLE} v
            SET pe_percentile_official = t.new_pct
            FROM {TEMP_TABLE} t
            WHERE v.symbol = t.symbol AND v.date = t.date
            """
        ))
        updated = result.rowcount
        conn.execute(text(f"DROP TABLE {TEMP_TABLE}"))

    print(f"Updated {updated} rows in {TABLE}.")

    with engine.connect() as conn:
        post_avg = conn.execute(text(
            f"SELECT AVG(pe_percentile_official) FROM {TABLE} WHERE ttm_eps_official > 0"
        )).scalar()
    print(f"Post-backfill avg(pe_percentile_official) = {post_avg:.4f}")
    print("Backfill complete.")


def main():
    parser = argparse.ArgumentParser(
        description="One-time PIT-safe backfill of valuation_daily.pe_percentile_official."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute new percentiles and print diagnostics, but do not write to DB.",
    )
    args = parser.parse_args()
    try:
        run(dry_run=args.dry_run)
    except Exception as e:
        print(f"Error: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
