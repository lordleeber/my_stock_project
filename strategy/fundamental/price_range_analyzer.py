import argparse
import os
import sys
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from common.http_client import fetch_dataframe


def get_20th_business_day(year, month):
    count = 0
    curr = datetime(year, month, 1)
    while count < 20:
        if curr.weekday() < 5:
            count += 1
        if count < 20:
            curr += timedelta(days=1)
    return curr.strftime("%Y-%m-%d")


def quarter_to_effective_date(q_str, market):
    if len(q_str) != 6 or q_str[4] != "Q":
        raise ValueError(f"Invalid quarter format: {q_str}, expected YYYYQ[1-4]")
    year = int(q_str[:4])
    q = q_str[5]
    if q not in {"1", "2", "3", "4"}:
        raise ValueError(f"Invalid quarter format: {q_str}, expected YYYYQ[1-4]")

    if market == "sii":
        if q == "1":
            return f"{year}-05-15"
        if q == "2":
            return f"{year}-08-14"
        if q == "3":
            return f"{year}-11-14"
        return f"{year + 1}-03-31"

    # otc
    if q == "1":
        return get_20th_business_day(year, 6)
    if q == "2":
        return get_20th_business_day(year, 9)
    if q == "3":
        return get_20th_business_day(year, 12)
    return get_20th_business_day(year + 1, 4)


def is_otc_market(market_value):
    if pd.isna(market_value):
        return False
    s = str(market_value).strip().lower()
    return ("otc" in s) or ("tpex" in s) or ("上櫃" in s)


def fetch_range_quotes(start_date, end_date):
    print(f"Fetching quotes (batch): {start_date} ~ {end_date}")
    try:
        df = fetch_dataframe(
            "/raw/daily-quotes",
            {"start_date": start_date, "end_date": end_date, "limit": 5000},
        )
        if not df.empty:
            # Batch mode can return partial rows due to API limit. If range is incomplete, fallback to daily fetch.
            if "date" in df.columns:
                dates = set(df["date"].astype(str))
                if start_date in dates and end_date in dates:
                    print(f"  fetched rows: {len(df)} (batch)")
                    return df
                print("  batch rows incomplete for requested range, fallback to daily fetch")
            else:
                print("  batch rows missing date column, fallback to daily fetch")
    except Exception as e:
        print(f"  batch fetch failed, fallback to daily fetch: {e}")

    all_quotes = []
    current = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)
    while current <= end_dt:
        d_str = current.strftime("%Y-%m-%d")
        df = fetch_dataframe(
            "/raw/daily-quotes",
            {"start_date": d_str, "end_date": d_str, "limit": 5000},
        )
        if not df.empty:
            all_quotes.append(df)
        current += pd.Timedelta(days=1)

    if all_quotes:
        out = pd.concat(all_quotes, ignore_index=True)
        print(f"  fetched rows: {len(out)} (daily fallback)")
        return out
    return pd.DataFrame()


def fetch_quotes_for_symbols(symbols, start_date, end_date):
    print(f"Fetching quotes by symbol: {len(symbols)} symbols, {start_date} ~ {end_date}")
    rows = []
    total = len(symbols)
    for i, sym in enumerate(symbols, start=1):
        df = fetch_dataframe(
            "/raw/daily-quotes",
            {"symbol": sym, "start_date": start_date, "end_date": end_date, "limit": 5000},
        )
        if not df.empty:
            rows.append(df)
        if i % 100 == 0 or i == total:
            print(f"  progress: {i}/{total}")
    if rows:
        out = pd.concat(rows, ignore_index=True)
        print(f"  fetched rows: {len(out)} (symbol mode)")
        return out
    return pd.DataFrame()


def filter_report_by_market(df_report, market):
    # Try to filter by explicit market column if present.
    for col in ["market", "market_bucket"]:
        if col in df_report.columns:
            if col == "market":
                bucket = df_report[col].apply(lambda x: "otc" if is_otc_market(x) else "sii")
                return df_report[bucket == market].copy()
            return df_report[df_report[col] == market].copy()

    # Fallback: infer by stock-info lookup.
    df_info = fetch_dataframe("/raw/stock-info", {"limit": 5000})
    if df_info.empty or "symbol" not in df_info.columns or "market" not in df_info.columns:
        print("Warning: stock-info unavailable; cannot strictly filter by market from report.")
        return df_report.copy()

    df_info = df_info[["symbol", "market"]].copy()
    df_info["symbol"] = df_info["symbol"].astype(str)
    df_info["market_bucket"] = df_info["market"].apply(lambda x: "otc" if is_otc_market(x) else "sii")
    symbols = set(df_info[df_info["market_bucket"] == market]["symbol"])
    return df_report[df_report["symbol"].astype(str).isin(symbols)].copy()


def run_range_analysis(start_date, end_date, report_path, market, start_label=None, end_label=None):
    if not os.path.exists(report_path):
        raise FileNotFoundError(f"Report not found: {report_path}")

    df_report = pd.read_csv(report_path)
    if "symbol" not in df_report.columns:
        raise ValueError("Input report missing required column: symbol")
    df_report["symbol"] = df_report["symbol"].astype(str)
    df_report["_input_order"] = np.arange(len(df_report))
    df_report = filter_report_by_market(df_report, market)
    if df_report.empty:
        raise ValueError(f"No rows left in report after market filter: {market}")

    symbols = sorted(set(df_report["symbol"].astype(str)))
    df_quotes = fetch_quotes_for_symbols(symbols, start_date, end_date)
    if df_quotes.empty:
        # Fallback to legacy wide-range fetch path.
        df_quotes = fetch_range_quotes(start_date, end_date)
    if df_quotes.empty:
        raise ValueError("No quote data fetched for date range.")

    if "symbol" not in df_quotes.columns:
        raise ValueError("Quote data missing required column: symbol")
    df_quotes["symbol"] = df_quotes["symbol"].astype(str)
    df_quotes = df_quotes[df_quotes["symbol"].isin(set(df_report["symbol"]))].copy()
    if df_quotes.empty:
        raise ValueError("No quote rows matched report symbols.")

    for c in ["high", "low", "close"]:
        if c not in df_quotes.columns:
            raise ValueError(f"Quote data missing required column: {c}")
        df_quotes[c] = pd.to_numeric(df_quotes[c], errors="coerce")

    stats = df_quotes.groupby("symbol").agg({"high": "max", "low": "min"}).reset_index()
    stats.columns = ["symbol", "period_high", "period_low"]
    result = pd.merge(df_report, stats, on="symbol", how="inner")

    # start_price: close of the first available quote date in range per symbol
    start_rows = (
        df_quotes.sort_values(["symbol", "date"])
        .groupby("symbol", as_index=False)
        .head(1)[["symbol", "date", "close"]]
        .copy()
    )
    start_rows.columns = ["symbol", "start_date", "start_price"]
    result = pd.merge(result, start_rows, on="symbol", how="left")

    # end_price: close of the last available quote date in range per symbol
    end_rows = (
        df_quotes.sort_values(["symbol", "date"])
        .groupby("symbol", as_index=False)
        .tail(1)[["symbol", "date", "close"]]
        .copy()
    )
    end_rows.columns = ["symbol", "end_date", "end_price"]
    result = pd.merge(result, end_rows, on="symbol", how="left")

    result["max_upside_pct"] = (
        (result["period_high"] - result["start_price"]) / result["start_price"] * 100
    )
    result["max_drawdown_pct"] = (
        (result["period_low"] - result["start_price"]) / result["start_price"] * 100
    )

    float_cols = result.select_dtypes(include=[np.float64, np.float32]).columns
    result[float_cols] = result[float_cols].round(2)

    preferred_cols = [
        "symbol",
        "name",
        "industry",
        "start_date",
        "start_price",
        "end_date",
        "end_price",
        "period_high",
        "period_low",
        "max_upside_pct",
        "max_drawdown_pct",
        "total_score",
    ]
    final_cols = [c for c in preferred_cols if c in result.columns]
    result = result.sort_values("_input_order", ascending=True)
    result = result[final_cols]

    start_part = start_label or start_date
    end_part = end_label or end_date
    report_stem = os.path.splitext(os.path.basename(report_path))[0]
    if report_stem.endswith("_sii") or report_stem.endswith("_otc"):
        report_stem = report_stem.rsplit("_", 1)[0]
    if report_stem.endswith(f"_{start_part}"):
        output_name = f"price_analysis_ref_{report_stem}_{end_part}_{market}.csv"
    else:
        output_name = f"price_analysis_ref_{report_stem}_{start_part}_{end_part}_{market}.csv"
    output_path = os.path.join("strategy", "fundamental", output_name)
    result.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"Done. Output: {output_path}")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Analyze max upside/drawdown for a report over a date range or quarter range."
    )
    parser.add_argument("--start-date", help="Start date in YYYY-MM-DD")
    parser.add_argument("--end-date", help="End date in YYYY-MM-DD")
    parser.add_argument("--start-quarter", help="Start quarter in YYYYQ[1-4]")
    parser.add_argument("--end-quarter", help="End quarter in YYYYQ[1-4]")
    parser.add_argument("--report-path", required=True, help="Path to fundamental report csv")
    parser.add_argument(
        "--market",
        "--martket",
        dest="market",
        required=True,
        choices=["sii", "otc"],
        help="Required. Market bucket to run: sii or otc.",
    )
    args = parser.parse_args()

    has_date_pair = bool(args.start_date and args.end_date)
    has_quarter_pair = bool(args.start_quarter and args.end_quarter)
    if has_date_pair == has_quarter_pair:
        parser.error("Provide either (--start-date and --end-date) OR (--start-quarter and --end-quarter).")
    return args


if __name__ == "__main__":
    args = parse_args()
    start_date = args.start_date
    end_date = args.end_date
    start_label = None
    end_label = None

    if args.start_quarter and args.end_quarter:
        start_date = quarter_to_effective_date(args.start_quarter, args.market)
        end_date = quarter_to_effective_date(args.end_quarter, args.market)
        start_label = args.start_quarter
        end_label = args.end_quarter

    run_range_analysis(
        start_date=start_date,
        end_date=end_date,
        report_path=args.report_path,
        market=args.market,
        start_label=start_label,
        end_label=end_label,
    )
