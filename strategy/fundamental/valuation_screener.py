import argparse
import os
import sys
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from common.http_client import fetch_dataframe, fetch_json
from strategy.fundamental.screener_base import calculate_ttm_eps


MIN_SUPPORTED_QUARTER = "2020Q4"


DEFAULT_CONFIG = {"pe": 0.30, "pb": 0.25, "peg": 0.25, "dividend": 0.20, "max_pe": 18}
INDUSTRY_VALUATION_CONFIG = {
    "半導體": {"pe": 0.25, "pb": 0.15, "peg": 0.45, "dividend": 0.15, "max_pe": 25},
    "電子": {"pe": 0.25, "pb": 0.20, "peg": 0.40, "dividend": 0.15, "max_pe": 20},
    "金融保險": {"pe": 0.15, "pb": 0.50, "peg": 0.05, "dividend": 0.30, "max_pe": 12},
    "營建": {"pe": 0.10, "pb": 0.60, "peg": 0.05, "dividend": 0.25, "max_pe": 10},
    "航運": {"pe": 0.20, "pb": 0.45, "peg": 0.10, "dividend": 0.25, "max_pe": 12},
    "食品": {"pe": 0.25, "pb": 0.35, "peg": 0.15, "dividend": 0.25, "max_pe": 15},
}


def is_otc_market(market_value):
    if pd.isna(market_value):
        return False
    s = str(market_value).strip().lower()
    return ("otc" in s) or ("tpex" in s) or ("上櫃" in s)


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
    year = int(q_str[:4])
    q = q_str[-1]
    if market == "sii":
        if q == "1":
            return f"{year}-05-15"
        if q == "2":
            return f"{year}-08-14"
        if q == "3":
            return f"{year}-11-14"
        return f"{year + 1}-03-31"
    if q == "1":
        return get_20th_business_day(year, 6)
    if q == "2":
        return get_20th_business_day(year, 9)
    if q == "3":
        return get_20th_business_day(year, 12)
    return get_20th_business_day(year + 1, 4)


def get_latest_quarters(n=4):
    today = datetime.now()
    year, month = today.year, today.month
    if month >= 11:
        latest = (year, 3)
    elif month >= 8:
        latest = (year, 2)
    elif month >= 5:
        latest = (year, 1)
    elif month >= 4:
        latest = (year - 1, 4)
    else:
        latest = (year - 1, 3)

    quarters = []
    y, q = latest
    for _ in range(n):
        quarters.append(f"{y}Q{q}")
        q -= 1
        if q == 0:
            q = 4
            y -= 1
    return quarters


def quarter_to_index(q_str):
    year = int(q_str[:4])
    quarter = int(q_str[-1])
    return year * 4 + quarter


def is_supported_quarter(q_str):
    return quarter_to_index(q_str) >= quarter_to_index(MIN_SUPPORTED_QUARTER)


def get_prev_quarter(q_str):
    year = int(q_str[:4])
    quarter = int(q_str[-1])
    if quarter == 1:
        return f"{year - 1}Q4"
    return f"{year}Q{quarter - 1}"


def get_trailing_quarters(target_quarter, n=4):
    quarters = [target_quarter]
    while len(quarters) < n:
        quarters.append(get_prev_quarter(quarters[-1]))
    return quarters


def fetch_valuation_analysis_for_date(target_date):
    if not target_date:
        return pd.DataFrame(columns=["symbol", "pe_ratio", "pe_percentile"])
    try:
        df = fetch_dataframe(
            "/raw/valuation-analysis",
            {"start_date": target_date, "end_date": target_date, "limit": 5000},
        )
        if df.empty or "symbol" not in df.columns:
            return pd.DataFrame(columns=["symbol", "pe_ratio", "pe_percentile"])

        if "pe_ratio_from_pe_table" not in df.columns:
            df["pe_ratio_from_pe_table"] = np.nan
        if "pe_percentile" not in df.columns:
            df["pe_percentile"] = np.nan

        df["symbol"] = df["symbol"].astype(str)
        df["pe_ratio_from_pe_table"] = pd.to_numeric(df["pe_ratio_from_pe_table"], errors="coerce")
        df["pe_percentile"] = pd.to_numeric(df["pe_percentile"], errors="coerce")

        out = df[["symbol", "pe_ratio_from_pe_table", "pe_percentile"]].drop_duplicates("symbol")
        out = out.rename(columns={"pe_ratio_from_pe_table": "pe_ratio"})
        return out
    except Exception:
        return pd.DataFrame(columns=["symbol", "pe_ratio", "pe_percentile"])


def fetch_dividend_proxy_for_symbols(symbols, end_date, start_date="2020-01-01"):
    if not end_date or not symbols:
        return pd.DataFrame(columns=["symbol", "cash_dividend"])
    rows = []
    for sym in sorted(set(str(s) for s in symbols)):
        try:
            df = fetch_dataframe(
                "/raw/dividend",
                {"start_date": start_date, "end_date": end_date, "symbol": sym, "limit": 5000},
            )
            if df.empty or "rights_dividend_value" not in df.columns:
                continue
            df["date"] = pd.to_datetime(df.get("date"), errors="coerce")
            df["rights_dividend_value"] = pd.to_numeric(df["rights_dividend_value"], errors="coerce").fillna(0)
            latest = df.sort_values("date", ascending=False).head(1)
            if latest.empty:
                continue
            rows.append({"symbol": sym, "cash_dividend": float(latest["rights_dividend_value"].iloc[0])})
        except Exception:
            continue
    if not rows:
        return pd.DataFrame(columns=["symbol", "cash_dividend"])
    return pd.DataFrame(rows).drop_duplicates("symbol")


def fetch_all_data(target_quarter=None, market_filter=None):
    if target_quarter:
        quarters = get_trailing_quarters(target_quarter, 4)
        latest_date = quarter_to_effective_date(target_quarter, market_filter)
    else:
        quarters = get_latest_quarters(4)
        latest_data = fetch_json(
            "/raw/daily-quotes",
            {"start_date": "2025-01-01", "end_date": "2026-12-31", "limit": 1},
        )
        latest_date = latest_data[0]["date"] if latest_data else None

    all_income = []
    for q in quarters:
        df = fetch_dataframe("/raw/income-statements", {"start_date": q, "end_date": q, "limit": 3000})
        if not df.empty:
            df["quarter"] = q
            all_income.append(df)
    df_income_all = pd.concat(all_income, ignore_index=True) if all_income else pd.DataFrame()

    bs_stmt = fetch_dataframe(
        "/raw/balance-sheets",
        {"start_date": quarters[0], "end_date": quarters[0], "limit": 3000},
    )
    cf_stmt = fetch_dataframe(
        "/raw/cash-flows",
        {"start_date": quarters[0], "end_date": quarters[0], "limit": 3000},
    )
    p_data = fetch_dataframe(
        "/raw/daily-quotes",
        {"start_date": latest_date, "end_date": latest_date, "limit": 5000},
    )
    info = fetch_dataframe("/raw/stock-info", {"limit": 5000})
    return df_income_all, bs_stmt, cf_stmt, p_data, info, latest_date, quarters[0]


def get_industry_config(industry):
    if pd.isna(industry):
        return DEFAULT_CONFIG
    s = str(industry)
    for key, config in INDUSTRY_VALUATION_CONFIG.items():
        if key in s:
            return config
    return DEFAULT_CONFIG


def calculate_fair_prices(df, industry_pe, industry_pb):
    rows = []
    for _, row in df.iterrows():
        symbol = row["symbol"]
        industry = row.get("industry", "")
        config = get_industry_config(industry)

        eps_ttm = row.get("eps_ttm", 0)
        nav = row.get("nav_per_share", 0)
        eps_growth = row.get("eps_growth", 0)
        dividend = row.get("cash_dividend", 0)

        base_pe = min(industry_pe.get(industry, 15), config["max_pe"])
        base_pb = industry_pb.get(industry, 1.5)

        fair_pe = eps_ttm * base_pe if eps_ttm > 0 else 0
        fair_pb = nav * base_pb if nav > 0 else 0
        if eps_growth and eps_growth > 5 and eps_ttm > 0:
            fair_peg = eps_ttm * min(eps_growth, 30)
        else:
            fair_peg = fair_pe
        fair_price_from_dividend = dividend / 0.05 if dividend > 0 else 0

        rows.append(
            {
                "symbol": symbol,
                "fair_pe": round(fair_pe, 2),
                "fair_pb": round(fair_pb, 2),
                "fair_peg": round(fair_peg, 2),
                "fair_price_from_dividend": round(fair_price_from_dividend, 2),
                "valuation_method": (
                    f"PE:{config['pe']:.0%}/PB:{config['pb']:.0%}/"
                    f"PEG:{config['peg']:.0%}/DIV:{config['dividend']:.0%}"
                ),
            }
        )
    return pd.DataFrame(rows)


def calculate_pe_percentile(df, hist_pe):
    if hist_pe.empty:
        df["pe_percentile"] = np.nan
        df["pe_zone"] = "無資料"
        return df

    df = pd.merge(df, hist_pe, on="symbol", how="left")
    df["pe_percentile"] = np.where(
        (df["pe_max"] > df["pe_min"]) & (df["pe_ratio"] > 0),
        (df["pe_ratio"] - df["pe_min"]) / (df["pe_max"] - df["pe_min"]) * 100,
        np.nan,
    )

    def zone(v):
        if pd.isna(v):
            return "無資料"
        if v <= 20:
            return "極度低估"
        if v <= 40:
            return "相對低估"
        if v <= 60:
            return "合理區間"
        if v <= 80:
            return "相對高估"
        return "極度高估"

    df["pe_zone"] = df["pe_percentile"].apply(zone)
    return df


def apply_pe_zone(df):
    if "pe_percentile" not in df.columns:
        df["pe_percentile"] = np.nan

    def zone(v):
        if pd.isna(v):
            return "無資料"
        if v <= 20:
            return "極度低估"
        if v <= 40:
            return "低估"
        if v <= 60:
            return "合理"
        if v <= 80:
            return "偏高"
        return "極度高估"

    df["pe_zone"] = df["pe_percentile"].apply(zone)
    return df


def run_valuation(market_filter, target_quarter=None):
    if target_quarter and not is_supported_quarter(target_quarter):
        print(f"不支援 {target_quarter}，最早可用季度為 {MIN_SUPPORTED_QUARTER}")
        return

    df_income_all, df_bs, df_cf, df_p, df_info, latest_date, quarter = fetch_all_data(target_quarter, market_filter)
    if df_p.empty:
        print("無法取得價格資料")
        return

    for d in [df_income_all, df_bs, df_cf, df_p, df_info]:
        if not d.empty and "symbol" in d.columns:
            d["symbol"] = d["symbol"].astype(str)

    ttm_eps = calculate_ttm_eps(df_income_all)
    if ttm_eps.empty:
        print("無完整 TTM EPS 資料，停止執行")
        return

    if "market" in df_p.columns:
        df_p["market_bucket"] = df_p["market"].apply(lambda x: "otc" if is_otc_market(x) else "sii")
    else:
        df_p["market_bucket"] = "sii"
    df_p = df_p[df_p["market_bucket"] == market_filter].copy()
    if df_p.empty:
        print(f"無符合 market={market_filter} 的價格資料")
        return

    # Strict PE source: /raw/valuation-analysis only.
    df_p["pe_ratio"] = np.nan
    df_p["pe_percentile"] = np.nan

    valuation_df = fetch_valuation_analysis_for_date(latest_date)
    if not valuation_df.empty:
        df_p = pd.merge(
            df_p,
            valuation_df.rename(columns={"pe_ratio": "pe_ratio_api", "pe_percentile": "pe_percentile_api"}),
            on="symbol",
            how="left",
        )
        df_p["pe_ratio"] = pd.to_numeric(df_p["pe_ratio_api"], errors="coerce")
        df_p["pe_percentile"] = pd.to_numeric(df_p["pe_percentile_api"], errors="coerce")
        df_p = df_p.drop(columns=["pe_ratio_api"], errors="ignore")
        df_p = df_p.drop(columns=["pe_percentile_api"], errors="ignore")

    df = pd.merge(df_p[["symbol", "name", "close", "pe_ratio", "pe_percentile"]], ttm_eps, on="symbol", how="inner")
    info_cols = ["symbol", "industry"] + (["market"] if "market" in df_info.columns else [])
    df = pd.merge(df, df_bs[["symbol", "nav_per_share"]], on="symbol", how="left")
    df = pd.merge(df, df_info[info_cols], on="symbol", how="left")

    dividends = fetch_dividend_proxy_for_symbols(df["symbol"].astype(str).unique().tolist(), latest_date)
    if not dividends.empty:
        df = pd.merge(df, dividends, on="symbol", how="left")
    else:
        df["cash_dividend"] = 0

    for c in ["close", "pe_ratio", "eps_ttm", "nav_per_share", "cash_dividend", "eps_growth"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)

    df = df[(df["nav_per_share"] > 0) & (df["close"] > 0)].copy()
    industry_pe = df[df["pe_ratio"] > 0].groupby("industry")["pe_ratio"].median().to_dict()
    df["pb_ratio"] = df["close"] / df["nav_per_share"]
    industry_pb = (
        df[(df["pb_ratio"] > 0) & np.isfinite(df["pb_ratio"])]
        .groupby("industry")["pb_ratio"]
        .median()
        .to_dict()
    )

    fair_prices = calculate_fair_prices(df, industry_pe, industry_pb)
    df = pd.merge(df, fair_prices, on="symbol", how="left")
    df = apply_pe_zone(df)

    df["roe_annual"] = np.where(df["nav_per_share"] > 0, (df["eps_ttm"] / df["nav_per_share"]) * 100, 0)
    df["peg_ratio"] = np.where(
        (df["eps_growth"] > 0) & (df["pe_ratio"] > 0),
        df["pe_ratio"] / df["eps_growth"],
        np.nan,
    )

    undervalued = df[(df["eps_ttm"] > 0) & (df["roe_annual"] > 8) & (df["pe_ratio"] > 0)].copy()
    undervalued["quality_flag"] = ""
    undervalued.loc[undervalued["peg_ratio"] < 1, "quality_flag"] += "PEG<1 "
    undervalued.loc[undervalued["pe_zone"] == "極度低估", "quality_flag"] += "歷史低點 "
    undervalued.loc[undervalued["roe_annual"] > 15, "quality_flag"] += "高ROE "

    undervalued["_pe_rank"] = undervalued["pe_percentile"].fillna(9999)
    undervalued["_peg_rank"] = undervalued["peg_ratio"].fillna(9999)
    undervalued = undervalued.sort_values(
        ["_pe_rank", "_peg_rank", "roe_annual"],
        ascending=[True, True, False],
    ).drop(columns=["_pe_rank", "_peg_rank"])
    undervalued["price_date"] = latest_date
    undervalued["report_quarter"] = quarter
    undervalued["market"] = market_filter
    undervalued = undervalued.rename(columns={"close": "market_price"})

    out_cols = [
        "symbol",
        "name",
        "industry",
        "market",
        "price_date",
        "market_price",
        "eps_ttm",
        "eps_growth",
        "pe_ratio",
        "peg_ratio",
        "nav_per_share",
        "roe_annual",
        "pe_zone",
        "pe_percentile",
        "fair_pe",
        "fair_pb",
        "fair_peg",
        "fair_price_from_dividend",
        "valuation_method",
        "quality_flag",
        "report_quarter",
    ]
    out_cols = [c for c in out_cols if c in undervalued.columns]
    out_df = undervalued[out_cols].copy()
    float_cols = out_df.select_dtypes(include=[np.floating]).columns
    out_df[float_cols] = out_df[float_cols].round(2)

    out_path = os.path.join("strategy", "fundamental", f"valuation_report_{quarter}_{market_filter}.csv")
    out_df.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"完成，輸出: {out_path}，共 {len(undervalued)} 檔")


def parse_args():
    parser = argparse.ArgumentParser(description="Run valuation screener by market.")
    parser.add_argument(
        "--quarter",
        required=True,
        help="Target quarter like 2020Q4. Earliest allowed quarter is 2020Q4.",
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
    run_valuation(args.market, args.quarter)
