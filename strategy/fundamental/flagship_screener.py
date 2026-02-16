import argparse
import os
import sys
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

# Add project root to import path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from common.http_client import fetch_dataframe, fetch_json
from strategy.fundamental.screener_base import build_ttm_eps_for_quarter, fetch_pe_ratio_for_date


MIN_SUPPORTED_QUARTER = "2020Q4"


def get_20th_business_day(year, month):
    count = 0
    curr = datetime(year, month, 1)
    while count < 20:
        if curr.weekday() < 5:
            count += 1
        if count < 20:
            curr += timedelta(days=1)
    return curr.strftime("%Y-%m-%d")


def score_linear(val, min_val, max_val):
    if pd.isna(val):
        return 0
    if val <= min_val:
        return 0
    if val >= max_val:
        return 100
    return round(float((val - min_val) / (max_val - min_val) * 100), 2)


def is_regular_stock(symbol):
    s = str(symbol).strip()
    return s.isdigit() and len(s) == 4 and not s.startswith(("00", "02", "91", "01"))


def is_otc_market(market_value):
    if pd.isna(market_value):
        return False
    s = str(market_value).strip().lower()
    return ("otc" in s) or ("tpex" in s) or ("上櫃" in s)


def fetch_quotes_with_fallback(sim_date, max_forward_days=10):
    df_p = fetch_dataframe(
        "/raw/daily-quotes",
        {"start_date": sim_date, "end_date": sim_date, "limit": 5000},
    )
    actual_date = sim_date
    if df_p.empty:
        curr = datetime.strptime(sim_date, "%Y-%m-%d")
        for _ in range(max_forward_days):
            curr += timedelta(days=1)
            d_str = curr.strftime("%Y-%m-%d")
            df_p = fetch_dataframe(
                "/raw/daily-quotes",
                {"start_date": d_str, "end_date": d_str, "limit": 5000},
            )
            if not df_p.empty:
                actual_date = d_str
                break
    return df_p, actual_date


def fetch_pe_ratio_with_fallback(sim_date, max_forward_days=10):
    df_pe = fetch_pe_ratio_for_date(fetch_dataframe, sim_date)
    actual_date = sim_date
    if df_pe.empty:
        curr = datetime.strptime(sim_date, "%Y-%m-%d")
        for _ in range(max_forward_days):
            curr += timedelta(days=1)
            d_str = curr.strftime("%Y-%m-%d")
            df_pe = fetch_pe_ratio_for_date(fetch_dataframe, d_str)
            if not df_pe.empty:
                actual_date = d_str
                break
    return df_pe, actual_date


def get_config_for_quarter(q_str):
    year = int(q_str[:4])
    q = q_str[4:]
    if q == "Q1":
        sim_dates = {"sii": f"{year}-05-15", "otc": get_20th_business_day(year, 6)}
        rev_months = [f"{year}M03", f"{year}M04", f"{year}M05"]
    elif q == "Q2":
        sim_dates = {"sii": f"{year}-08-14", "otc": get_20th_business_day(year, 9)}
        rev_months = [f"{year}M06", f"{year}M07", f"{year}M08"]
    elif q == "Q3":
        sim_dates = {"sii": f"{year}-11-14", "otc": get_20th_business_day(year, 12)}
        rev_months = [f"{year}M09", f"{year}M10", f"{year}M11"]
    elif q == "Q4":
        sim_dates = {"sii": f"{year + 1}-03-31", "otc": get_20th_business_day(year + 1, 4)}
        rev_months = [f"{year + 1}M01", f"{year + 1}M02", f"{year + 1}M03"]
    else:
        return None, None
    return sim_dates, rev_months


def quarter_to_index(q_str):
    year = int(q_str[:4])
    quarter = int(q_str[-1])
    return year * 4 + quarter


def is_supported_quarter(q_str):
    return quarter_to_index(q_str) >= quarter_to_index(MIN_SUPPORTED_QUARTER)


def process_quarter(q_str, market_filter=None):
    if not is_supported_quarter(q_str):
        print(f"  [略過] {q_str} 不支援，最早可用季度為 {MIN_SUPPORTED_QUARTER}")
        return

    sim_dates, rev_months = get_config_for_quarter(q_str)
    print(f">>> 正在處理 {q_str} (分市場生效日 + 重試機制)...")
    try:
        df_q = fetch_dataframe(
            "/raw/quarterly-reports", {"start_date": q_str, "end_date": q_str, "limit": 3000}
        )
        df_cf = fetch_dataframe(
            "/raw/cash-flows", {"start_date": q_str, "end_date": q_str, "limit": 3000}
        )
        df_info = fetch_dataframe("/raw/stock-info", {"limit": 5000})
        df_ttm = build_ttm_eps_for_quarter(q_str, fetch_dataframe).rename(
            columns={"eps_ttm": "ttm_eps"}
        )

        all_rev = []
        for m in rev_months:
            r = fetch_json("/raw/monthly-revenue", {"start_date": m, "end_date": m, "limit": 3000})
            if r:
                all_rev.extend(r)
        df_r = pd.DataFrame(all_rev)

        if df_q.empty or df_r.empty:
            return

        # Allow degraded run when optional endpoints fail.
        if df_cf.empty or "cash_flow_operating" not in df_cf.columns:
            df_cf = pd.DataFrame(columns=["symbol", "cash_flow_operating"])
        if df_info.empty or "industry" not in df_info.columns:
            df_info = pd.DataFrame(columns=["symbol", "industry"])

        for d in [df_q, df_cf, df_r, df_info, df_ttm]:
            if "symbol" in d.columns:
                d["symbol"] = d["symbol"].astype(str)

        if "market" in df_q.columns:
            df_q["market_bucket"] = df_q["market"].apply(lambda x: "otc" if is_otc_market(x) else "sii")
        else:
            df_q["market_bucket"] = "sii"

        if market_filter in {"sii", "otc"}:
            df_q = df_q[df_q["market_bucket"] == market_filter].copy()
        if df_q.empty:
            print(f"  [略過] {q_str} 無符合 market={market_filter} 的資料")
            return

        target_symbols = df_q[["symbol", "market_bucket"]].drop_duplicates()

        df_price_frames = []
        for bucket in ["sii", "otc"]:
            sim_date = sim_dates.get(bucket)
            if not sim_date:
                continue

            df_p_bucket, actual_date = fetch_quotes_with_fallback(sim_date, max_forward_days=10)
            if df_p_bucket.empty:
                continue

            if "symbol" not in df_p_bucket.columns:
                continue

            df_pe_bucket, pe_date = fetch_pe_ratio_with_fallback(sim_date, max_forward_days=10)

            df_p_bucket["symbol"] = df_p_bucket["symbol"].astype(str)
            df_p_bucket = df_p_bucket[df_p_bucket["symbol"].apply(is_regular_stock)].copy()
            if df_p_bucket.empty:
                continue

            if "name" not in df_p_bucket.columns:
                df_p_bucket["name"] = ""
            if "close" not in df_p_bucket.columns:
                df_p_bucket["close"] = np.nan
            if "pe_ratio" not in df_p_bucket.columns:
                df_p_bucket["pe_ratio"] = np.nan

            # Use /raw/pe-ratio as primary source of PE, fallback to daily-quotes PE.
            if not df_pe_bucket.empty and "symbol" in df_pe_bucket.columns and "pe_ratio" in df_pe_bucket.columns:
                df_pe_bucket["symbol"] = df_pe_bucket["symbol"].astype(str)
                df_pe_bucket["pe_ratio"] = pd.to_numeric(df_pe_bucket["pe_ratio"], errors="coerce")
                df_pe_bucket = df_pe_bucket[["symbol", "pe_ratio"]].drop_duplicates("symbol")
                df_p_bucket = pd.merge(
                    df_p_bucket,
                    df_pe_bucket.rename(columns={"pe_ratio": "pe_ratio_api"}),
                    on="symbol",
                    how="left",
                )
                df_p_bucket["pe_ratio"] = np.where(
                    df_p_bucket["pe_ratio_api"].notna(),
                    df_p_bucket["pe_ratio_api"],
                    pd.to_numeric(df_p_bucket["pe_ratio"], errors="coerce"),
                )
                df_p_bucket = df_p_bucket.drop(columns=["pe_ratio_api"], errors="ignore")
                _ = pe_date

            df_p_bucket["market_bucket"] = bucket
            df_p_bucket["price_date"] = actual_date
            df_price_frames.append(df_p_bucket[["symbol", "name", "close", "pe_ratio", "market_bucket", "price_date"]])

        if not df_price_frames:
            return

        df_p = pd.concat(df_price_frames, ignore_index=True)
        df_p = pd.merge(df_p, target_symbols, on=["symbol", "market_bucket"], how="inner")
        if df_p.empty:
            return

        df_r["yoy_pct"] = pd.to_numeric(df_r["yoy_pct"], errors="coerce")
        rev_trend = (
            df_r.sort_values(["symbol", "date"])
            .groupby("symbol")
            .agg({"yoy_pct": ["mean", "last"]})
            .reset_index()
        )
        rev_trend.columns = ["symbol", "rev_avg_3m", "rev_latest_yoy"]

        df_q_base = df_q.drop(columns=["name", "market"], errors="ignore")
        df = pd.merge(df_p, df_q_base, on=["symbol", "market_bucket"], how="left")
        df = pd.merge(df, df_cf[["symbol", "cash_flow_operating"]], on="symbol", how="left")
        df = pd.merge(df, rev_trend, on="symbol", how="left")
        df = pd.merge(df, df_info[["symbol", "industry"]], on="symbol", how="left")
        # Keep only symbols with complete 4-quarter TTM EPS.
        df = pd.merge(df, df_ttm, on="symbol", how="inner")
        if df.empty:
            print(f"  [略過] {q_str} 無完整 TTM EPS 資料")
            return

        num_cols = [
            "revenue",
            "op_income",
            "net_income",
            "eps",
            "eps_yoy",
            "equity_to_assets_ratio",
            "pe_ratio",
            "rev_avg_3m",
            "cash_flow_operating",
            "close",
            "ttm_eps",
        ]
        for c in num_cols:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)

        df["op_margin"] = np.where(df["revenue"] > 0, (df["op_income"] / df["revenue"]) * 100, 0)
        df["cash_quality"] = np.where(df["net_income"] > 0, df["cash_flow_operating"] / df["net_income"], 0)

        df_valid_pe = df[df["pe_ratio"] > 0].copy()
        ind_pe_map = df_valid_pe.groupby("industry")["pe_ratio"].median().to_dict()

        def calc_value_score(row):
            pe = row["pe_ratio"]
            ind = str(row["industry"])
            base_pe = ind_pe_map.get(ind, 12)
            v_score = score_linear(1.5 - (pe / base_pe), 0, 1.0) if pe > 0 else 0
            return v_score

        df["value_score"] = df.apply(calc_value_score, axis=1)
        df["growth_score"] = df["eps_yoy"].apply(lambda x: score_linear(x, 0, 50))
        df["momentum_score"] = df["rev_avg_3m"].apply(lambda x: score_linear(x, 0, 20))
        df["quality_score"] = df["cash_quality"].apply(lambda x: score_linear(x, 0.5, 1.2))
        df["profit_score"] = df["op_margin"].apply(lambda x: score_linear(x, 5, 25))
        df["safety_score"] = df["equity_to_assets_ratio"].apply(lambda x: score_linear(x, 20, 60))

        df["total_score"] = (
            (df["growth_score"] * 0.25)
            + (df["momentum_score"] * 0.20)
            + (df["quality_score"] * 0.20)
            + (df["profit_score"] * 0.15)
            + (df["safety_score"] * 0.10)
            + (df["value_score"] * 0.10)
        )

        float_cols = df.select_dtypes(include=[np.float64, np.float32]).columns
        df[float_cols] = df[float_cols].round(2)

        df = df.rename(columns={"close": "market_price", "rev_avg_3m": "avg_revenue_yoy_3m"})
        df["report_quarter"] = q_str

        final_cols = [
            "symbol",
            "name",
            "industry",
            "price_date",
            "market_price",
            "ttm_eps",
            "report_quarter",
            "pe_ratio",
            "value_score",
            "eps_yoy",
            "growth_score",
            "avg_revenue_yoy_3m",
            "momentum_score",
            "op_margin",
            "profit_score",
            "cash_quality",
            "quality_score",
            "equity_to_assets_ratio",
            "safety_score",
            "total_score",
        ]
        final_cols = [c for c in final_cols if c in df.columns]

        final_df = df[final_cols].sort_values("total_score", ascending=False)
        if market_filter in {"sii", "otc"}:
            filename = f"flagship_report_{q_str}_{market_filter}.csv"
        else:
            filename = f"flagship_report_{q_str}.csv"
        output_path = os.path.join("strategy", "fundamental", filename)
        final_df.to_csv(output_path, index=False, encoding="utf-8-sig")
        print(f"  [完成] {output_path}")

    except Exception as e:
        print(f"  [失敗] {q_str} 異常: {e}")


def parse_args():
    parser = argparse.ArgumentParser(description="Run flagship fundamental screener by quarter.")
    parser.add_argument(
        "--quarter",
        action="append",
        required=True,
        help="Target quarter like 2020Q4. 2020Q1~2020Q3 are not allowed. Can be provided multiple times.",
    )
    parser.add_argument(
        "--market",
        "--martket",
        dest="market",
        required=True,
        choices=["sii", "otc"],
        help="Required. Market bucket to run: sii or otc.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    target_quarters = args.quarter
    for q in target_quarters:
        process_quarter(q, market_filter=args.market)
