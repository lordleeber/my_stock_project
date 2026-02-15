import argparse
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from common.http_client import fetch_dataframe
from strategy.fundamental.screener_base import get_trailing_quarters


def print_df_info(title, df):
    print(f"\n=== {title} ===")
    print(f"rows={len(df)} cols={list(df.columns)}")
    if not df.empty:
        print("dtypes:")
        print(df.dtypes.astype(str).to_string())
    else:
        print("dataframe is empty")


def debug_ttm_symbol_issue(target_quarter, endpoint):
    quarters = get_trailing_quarters(target_quarter, n=4)
    print(f"target_quarter={target_quarter}")
    print(f"trailing_quarters={quarters}")
    print(f"endpoint={endpoint}")

    frames = []
    for q in quarters:
        df_tmp = fetch_dataframe(endpoint, {"start_date": q, "end_date": q, "limit": 3000})
        print(f"\nfetch quarter={q} rows={len(df_tmp)}")
        if not df_tmp.empty:
            print(f"columns={list(df_tmp.columns)}")
        if df_tmp.empty or "symbol" not in df_tmp.columns or "eps" not in df_tmp.columns:
            continue
        frames.append(df_tmp[["symbol", "eps"]].assign(quarter=q))

    if not frames:
        print("\nNo usable quarterly frames.")
        return

    df_income_all = pd.concat(frames, ignore_index=True)
    print_df_info("df_income_all(raw)", df_income_all)

    df = df_income_all.copy()
    df["symbol"] = df["symbol"].astype(str)
    df["eps"] = pd.to_numeric(df["eps"], errors="coerce")
    valid = df[df["eps"].notna()].copy()
    print_df_info("valid(non-null eps)", valid)

    counts = valid.groupby("symbol")["eps"].count()
    valid_symbols = counts[counts >= 4].index
    print(f"\nvalid_symbols(>=4 quarters) count={len(valid_symbols)}")

    dfq = valid[valid["symbol"].isin(valid_symbols)].copy()
    dfq = dfq.sort_values(["symbol", "quarter"], ascending=[True, False])
    print_df_info("dfq(sorted)", dfq)

    latest = dfq.drop_duplicates("symbol")[["symbol", "eps"]].rename(columns={"eps": "eps_latest"})
    print_df_info("latest", latest)

    yoy_raw = dfq.groupby("symbol").nth(3)
    print("\n=== yoy_raw = dfq.groupby('symbol').nth(3) ===")
    print(f"type={type(yoy_raw)} rows={len(yoy_raw)}")
    print(f"index_type={type(yoy_raw.index)} index_name={yoy_raw.index.name}")
    if hasattr(yoy_raw.index, "names"):
        print(f"index_names={yoy_raw.index.names}")
    if not yoy_raw.empty:
        print(f"yoy_raw columns={list(yoy_raw.columns)}")

    yoy_base = yoy_raw
    if not yoy_base.empty and "eps" in yoy_base.columns:
        yoy_base = yoy_base[["eps"]]
    yoy_base = yoy_base.reset_index()
    print_df_info("yoy_base after reset_index()", yoy_base)

    if "symbol" not in yoy_base.columns:
        print("symbol column missing after reset_index() -> fallback path triggered")
        yoy_base = yoy_base.rename_axis("symbol").reset_index()
        print_df_info("yoy_base after rename_axis('symbol').reset_index()", yoy_base)
    else:
        print("symbol column exists after reset_index()")

    if "eps" in yoy_base.columns:
        yoy_base = yoy_base.rename(columns={"eps": "eps_yoy_base"})
    print_df_info("yoy_base(final)", yoy_base)

    print("\n=== merge key dtype check ===")
    if "symbol" in latest.columns:
        print(f"latest.symbol dtype={latest['symbol'].dtype}")
    if "symbol" in yoy_base.columns:
        print(f"yoy_base.symbol dtype={yoy_base['symbol'].dtype}")

    try:
        growth = pd.merge(latest, yoy_base, on="symbol", how="left")
        print_df_info("growth(merge result)", growth)
        print("merge success")
    except Exception as e:
        print(f"merge failed: {e}")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Debug symbol/index shape issue in TTM EPS merge."
    )
    parser.add_argument("--quarter", required=True, help="Target quarter, e.g. 2020Q4")
    parser.add_argument(
        "--endpoint",
        default="/raw/income-statements",
        help="Quarterly EPS endpoint. Default: /raw/income-statements",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    debug_ttm_symbol_issue(args.quarter, args.endpoint)
