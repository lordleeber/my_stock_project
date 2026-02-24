import argparse
import os
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from sqlalchemy import create_engine, text

# 04/10 or 04/15 視角 -> anchor_eps=Q4EPS (年報出爐) + 01,02,03月營收，預測本年度 Q1 EPS
FEATURES = [
    "anchor_eps",
    "ly_q1_eps",
    "q4_yoy_eps",
    "q4_margin",
    "q4_ocf_ratio",
    "q4_re_ratio",
    "rev_yoy_m03_quantile",
    "rev_yoy_m01_m02_m03_quantile",
    "margin_momentum",
    "q4_roe",
    "q4_debt_ratio",
    "q4_non_op_ratio",
    "ly_seasonality",
]
TARGET = "target_eps"
TARGET_DELTA = "delta_eps"

KEEP_OPTIONAL = [
    "symbol", "name", "industry", "target_date", "target_close", "target_volume", "pe_current",
    "prev_q4_eps", "q2_eps", "q3_eps", "ttm_eps_official", "feature_cutoff_date",
]

DEFAULT_OUTPUT_TRAIN = Path(__file__).resolve().parent / "dataset_train.csv"
DEFAULT_OUTPUT_META = Path(__file__).resolve().parent / "dataset_meta.csv"
DEFAULT_OUTPUT_EVALUATE = Path(__file__).resolve().parent / "dataset_evaluate.csv"


def get_db_url() -> str:
    return f"postgresql://{os.getenv('DB_USER','user')}:{os.getenv('DB_PASSWORD','password')}@{os.getenv('DB_HOST','db')}:{os.getenv('DB_PORT','5432')}/{os.getenv('DB_NAME','stock_db')}"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Prepare v10_t4 dataset (04月視角) from DB.")
    p.add_argument("--start-year", type=int, default=2020)
    p.add_argument("--end-year", type=int, default=2025)
    p.add_argument("--market", type=str, default="sii", choices=["sii", "otc"])
    p.add_argument("--data-source", type=str, choices=["db", "api"], default="db")
    p.add_argument("--api-base", type=str, default=os.getenv("BACKEND_API_BASE", "http://100.103.191.79:8000"))
    p.add_argument("--apply-trading-filter", action="store_true")
    p.add_argument("--min-ttm-eps", type=float, default=2.0)
    p.add_argument("--min-volume-lots", type=float, default=500.0)
    p.add_argument("--output-train", type=Path, default=DEFAULT_OUTPUT_TRAIN)
    p.add_argument("--output-meta", type=Path, default=DEFAULT_OUTPUT_META)
    p.add_argument("--output-evaluate", type=Path, default=DEFAULT_OUTPUT_EVALUATE)
    return p.parse_args()


def add_industry_zscore(df: pd.DataFrame, col: str, out_col: str) -> None:
    g = df.groupby(["year", "industry"])[col]
    mean = g.transform("mean")
    std = g.transform("std").replace(0, np.nan)
    df[out_col] = ((df[col] - mean) / std).replace([np.inf, -np.inf], np.nan).fillna(0)


def add_cross_section_quantile(df: pd.DataFrame, z_col: str, out_col: str) -> None:
    group_cols = ["year", "industry"]
    ranks = df.groupby(group_cols)[z_col].rank(method="average", pct=True).fillna(0.5)
    df[out_col] = np.ceil(ranks * 10.0).clip(1.0, 10.0) / 10.0


def fetch_all_rows_api(api_base: str, path: str, params: dict, limit: int = 5000) -> pd.DataFrame:
    rows: list[dict] = []
    offset = 0
    while True:
        q = dict(params)
        q["limit"] = limit
        q["offset"] = offset
        resp = requests.get(f"{api_base.rstrip('/')}{path}", params=q, timeout=60)
        resp.raise_for_status()
        chunk = resp.json()
        if not chunk:
            break
        rows.extend(chunk)
        if len(chunk) < limit:
            break
        offset += limit
    return pd.DataFrame(rows)


def safe_col(df: pd.DataFrame, col: str) -> pd.Series:
    return df[col] if col in df.columns else pd.Series([np.nan] * len(df), index=df.index)


def fetch_one_year_api(api_base: str, year: int, market: str) -> pd.DataFrame:
    q1 = f"{year}Q1"
    ly_q1 = f"{year-1}Q1"
    q4_anchor = f"{year-1}Q4"
    ly_q4_anchor = f"{year-2}Q4"
    q3_for_mom = f"{year-1}Q3"
    
    m01, m02, m03 = f"{year}M01", f"{year}M02", f"{year}M03"
    ly_m01, ly_m02, ly_m03 = f"{year-1}M01", f"{year-1}M02", f"{year-1}M03"
    
    month_start, month_end = f"{year}-04-01", f"{year}-04-30"
    cutoff = f"{year}-04-10"

    inc_q4 = fetch_all_rows_api(api_base, "/raw/income-statements", {"start_date": q4_anchor, "end_date": q4_anchor, "market": market})
    inc_q3 = fetch_all_rows_api(api_base, "/raw/income-statements", {"start_date": q3_for_mom, "end_date": q3_for_mom, "market": market})
    bs_q4 = fetch_all_rows_api(api_base, "/raw/balance-sheets", {"start_date": q4_anchor, "end_date": q4_anchor, "market": market})
    cf_q4 = fetch_all_rows_api(api_base, "/raw/cash-flows", {"start_date": q4_anchor, "end_date": q4_anchor, "market": market})
    qr = fetch_all_rows_api(api_base, "/raw/quarterly-reports", {"start_date": ly_q4_anchor, "end_date": q1, "market": market})
    mr = fetch_all_rows_api(api_base, "/raw/monthly-revenue", {"start_date": ly_m01, "end_date": m03})
    dq = fetch_all_rows_api(api_base, "/raw/daily-quotes", {"start_date": month_start, "end_date": month_end, "market": market})
    pe = fetch_all_rows_api(api_base, "/raw/pe-ratio", {"start_date": month_start, "end_date": month_end, "market": market})

    if inc_q4.empty:
        return pd.DataFrame()

    q4_data = inc_q4.copy()
    if not bs_q4.empty:
        q4_data = q4_data.merge(
            bs_q4[["symbol", "date", "total_equity", "total_liabilities", "total_assets", "share_capital", "retained_earnings"]],
            on=["symbol", "date"],
            how="left",
        )
    if not cf_q4.empty:
        q4_data = q4_data.merge(cf_q4[["symbol", "date", "cash_flow_operating_q"]], on=["symbol", "date"], how="left")
    q4_data = q4_data.rename(columns={"revenue_q": "q4_rev", "net_income_q": "q4_ni", "share_capital": "capital", "retained_earnings": "q4_retained_earnings", "cash_flow_operating_q": "q4_ocf"})
    q4_data["q4_eps"] = safe_col(q4_data, "eps_q")
    q4_data["q4_margin"] = safe_col(q4_data, "q4_ni") / safe_col(q4_data, "q4_rev").replace(0, np.nan)
    q4_data["q4_non_op_ratio"] = safe_col(q4_data, "non_operating_income_q") / safe_col(q4_data, "pretax_income_q").replace(0, np.nan)
    q4_data["q4_roe"] = safe_col(q4_data, "q4_ni") / safe_col(q4_data, "total_equity").replace(0, np.nan)
    q4_data["q4_debt_ratio"] = safe_col(q4_data, "total_liabilities") / safe_col(q4_data, "total_assets").replace(0, np.nan)
    q4_data = q4_data[["symbol", "name", "q4_rev", "q4_ni", "q4_eps", "q4_margin", "q4_non_op_ratio", "q4_roe", "q4_debt_ratio", "capital", "q4_retained_earnings", "q4_ocf"]]

    q3_data = pd.DataFrame(columns=["symbol", "q3_margin"])
    if not inc_q3.empty:
        q3_data = inc_q3[["symbol", "revenue_q", "net_income_q"]].copy()
        q3_data["q3_margin"] = q3_data["net_income_q"] / q3_data["revenue_q"].replace(0, np.nan)
        q3_data = q3_data[["symbol", "q3_margin"]]

    this_monthly = pd.DataFrame(columns=["symbol", "rev_m01", "rev_m02", "rev_m03", "rev_m01_ly", "rev_m02_ly", "rev_m03_ly"])
    if not mr.empty:
        if "market" in mr.columns:
            mr = mr[mr["market"].astype(str).str.upper() == market.upper()].copy()
        mr2 = mr[mr["date"].isin([m01, m02, m03, ly_m01, ly_m02, ly_m03])].copy()
        if not mr2.empty:
            pvt = mr2.pivot_table(index="symbol", columns="date", values="revenue_current", aggfunc="last").reset_index()
            this_monthly = pvt.rename(columns={m01: "rev_m01", m02: "rev_m02", m03: "rev_m03", ly_m01: "rev_m01_ly", ly_m02: "rev_m02_ly", ly_m03: "rev_m03_ly"})
            for c in ["rev_m01", "rev_m02", "rev_m03", "rev_m01_ly", "rev_m02_ly", "rev_m03_ly"]:
                if c not in this_monthly.columns:
                    this_monthly[c] = np.nan
            this_monthly = this_monthly[["symbol", "rev_m01", "rev_m02", "rev_m03", "rev_m01_ly", "rev_m02_ly", "rev_m03_ly"]]

    eps_hist = pd.DataFrame(columns=["symbol", "target_eps", "ly_q1_eps", "ly_q4_eps", "prev_q4_eps", "q2_eps", "q3_eps", "q4_eps_official"])
    if not qr.empty:
        qr2 = qr[qr["date"].isin([q1, ly_q1, ly_q4_anchor, f"{year-2}Q4", f"{year-1}Q2", q3_for_mom, q4_anchor])].copy()
        p = qr2.pivot_table(index="symbol", columns="date", values="eps_q", aggfunc="last").reset_index()
        eps_hist = p.rename(columns={q1: "target_eps", ly_q1: "ly_q1_eps", ly_q4_anchor: "ly_q4_eps", f"{year-2}Q4": "prev_q4_eps", f"{year-1}Q2": "q2_eps", q3_for_mom: "q3_eps", q4_anchor: "q4_eps_official"})
        for c in ["target_eps", "ly_q1_eps", "ly_q4_eps", "prev_q4_eps", "q2_eps", "q3_eps", "q4_eps_official"]:
            if c not in eps_hist.columns:
                eps_hist[c] = np.nan
        eps_hist = eps_hist[["symbol", "target_eps", "ly_q1_eps", "ly_q4_eps", "prev_q4_eps", "q2_eps", "q3_eps", "q4_eps_official"]]

    market_snapshot = pd.DataFrame(columns=["symbol", "target_date", "target_close", "target_volume", "pe_current"])
    if not dq.empty:
        dq2 = dq.copy()
        dq2["date"] = pd.to_datetime(dq2["date"], errors="coerce")
        if not pe.empty:
            pe2 = pe[["symbol", "date", "market", "pe_ratio"]].copy()
            pe2["date"] = pd.to_datetime(pe2["date"], errors="coerce")
            dq2 = dq2.merge(pe2, on=["symbol", "date", "market"], how="left")
        else:
            dq2["pe_ratio"] = np.nan
        dq2 = dq2.sort_values(["symbol", "date"]).dropna(subset=["date"]).groupby("symbol", as_index=False).tail(1)
        market_snapshot = dq2.rename(columns={"date": "target_date", "close": "target_close", "volume": "target_volume", "pe_ratio": "pe_current"})
        market_snapshot["target_date"] = market_snapshot["target_date"].dt.strftime("%Y-%m-%d")
        market_snapshot = market_snapshot[["symbol", "target_date", "target_close", "target_volume", "pe_current"]]

    out = q4_data.merge(q3_data, on="symbol", how="left")
    out = out.merge(this_monthly, on="symbol", how="inner")
    out = out.merge(eps_hist, on="symbol", how="inner")
    out = out.merge(market_snapshot, on="symbol", how="left")
    out["year"] = year
    out["feature_cutoff_date"] = cutoff
    return out


def fetch_one_year(conn, year: int, market: str) -> pd.DataFrame:
    q1 = f"{year}Q1"
    ly_q1 = f"{year-1}Q1"
    q4_anchor = f"{year-1}Q4"
    ly_q4_anchor = f"{year-2}Q4"
    q3_for_mom = f"{year-1}Q3"
    prev_q4_eps = f"{year-2}Q4"
    q2_eps = f"{year-1}Q2"
    
    m01, m02, m03 = f"{year}M01", f"{year}M02", f"{year}M03"
    ly_m01, ly_m02, ly_m03 = f"{year-1}M01", f"{year-1}M02", f"{year-1}M03"
    
    month_start, month_end = f"{year}-04-01", f"{year}-04-30"
    cutoff = f"{year}-04-10"

    sql = f"""
    WITH q4_data AS (
      SELECT i.symbol, i.name, i.revenue_q AS q4_rev, i.net_income_q AS q4_ni, i.eps_q AS q4_eps,
             i.net_income_q/NULLIF(i.revenue_q,0) AS q4_margin,
             i.non_operating_income_q/NULLIF(i.pretax_income_q,0) AS q4_non_op_ratio,
             i.net_income_q/NULLIF(b.total_equity,0) AS q4_roe,
             b.total_liabilities/NULLIF(b.total_assets,0) AS q4_debt_ratio,
             b.share_capital AS capital, b.retained_earnings AS q4_retained_earnings,
             c.cash_flow_operating_q AS q4_ocf
      FROM income_statement i
      JOIN balance_sheet b ON i.symbol=b.symbol AND i.date=b.date
      JOIN cash_flow c ON i.symbol=c.symbol AND i.date=c.date
      WHERE i.date='{q4_anchor}' AND i.market='{market}'
    ),
    q3_data AS (
      SELECT symbol, net_income_q/NULLIF(revenue_q,0) AS q3_margin
      FROM income_statement WHERE date='{q3_for_mom}' AND market='{market}'
    ),
    this_monthly AS (
      SELECT symbol,
             MAX(CASE WHEN date='{m01}' THEN revenue_current END) AS rev_m01,
             MAX(CASE WHEN date='{m02}' THEN revenue_current END) AS rev_m02,
             MAX(CASE WHEN date='{m03}' THEN revenue_current END) AS rev_m03,
             MAX(CASE WHEN date='{ly_m01}' THEN revenue_current END) AS rev_m01_ly,
             MAX(CASE WHEN date='{ly_m02}' THEN revenue_current END) AS rev_m02_ly,
             MAX(CASE WHEN date='{ly_m03}' THEN revenue_current END) AS rev_m03_ly
      FROM monthly_revenue
      WHERE date IN ('{m01}','{m02}','{m03}','{ly_m01}','{ly_m02}','{ly_m03}')
      GROUP BY symbol
    ),
    eps_hist AS (
      SELECT qr.symbol, qr.eps_q AS target_eps,
             (SELECT eps_q FROM quarterly_reports WHERE symbol=qr.symbol AND date='{ly_q1}' AND market='{market}') AS ly_q1_eps,
             (SELECT eps_q FROM quarterly_reports WHERE symbol=qr.symbol AND date='{ly_q4_anchor}' AND market='{market}') AS ly_q4_eps,
             (SELECT eps_q FROM quarterly_reports WHERE symbol=qr.symbol AND date='{prev_q4_eps}' AND market='{market}') AS prev_q4_eps,
             (SELECT eps_q FROM quarterly_reports WHERE symbol=qr.symbol AND date='{q2_eps}' AND market='{market}') AS q2_eps,
             (SELECT eps_q FROM quarterly_reports WHERE symbol=qr.symbol AND date='{q3_for_mom}' AND market='{market}') AS q3_eps,
             (SELECT eps_q FROM quarterly_reports WHERE symbol=qr.symbol AND date='{q4_anchor}' AND market='{market}') AS q4_eps_official
      FROM quarterly_reports qr WHERE qr.date='{q1}' AND qr.market='{market}'
    ),
    market_snapshot AS (
      SELECT DISTINCT ON (dq.symbol) dq.symbol, dq.date AS target_date, dq.close AS target_close, dq.volume AS target_volume, pr.pe_ratio AS pe_current
      FROM daily_quotes dq
      LEFT JOIN pe_ratio pr ON pr.symbol=dq.symbol AND pr.market=dq.market AND pr.date=dq.date
      WHERE dq.market='{market}' AND dq.date>='{month_start}' AND dq.date<='{month_end}'
      ORDER BY dq.symbol, dq.date DESC
    )
    SELECT {year} AS year, '{cutoff}' AS feature_cutoff_date, q4.*, q3.q3_margin,
           m.rev_m01,m.rev_m02,m.rev_m03,m.rev_m01_ly,m.rev_m02_ly,m.rev_m03_ly,
           e.target_eps,e.ly_q1_eps,e.ly_q4_eps,e.prev_q4_eps,e.q2_eps,e.q3_eps,e.q4_eps_official,
           ms.target_date,ms.target_close,ms.target_volume,ms.pe_current
    FROM q4_data q4
    LEFT JOIN q3_data q3 ON q4.symbol=q3.symbol
    JOIN this_monthly m ON q4.symbol=m.symbol
    JOIN eps_hist e ON q4.symbol=e.symbol
    LEFT JOIN market_snapshot ms ON q4.symbol=ms.symbol
    """
    return pd.read_sql(sql, conn)


def main() -> None:
    args = parse_args()
    if args.start_year > args.end_year:
        raise ValueError("start-year must be <= end-year")

    frames = []
    if args.data_source == "db":
        engine = create_engine(get_db_url())
        with engine.connect() as conn:
            conn.execute(text("SET max_parallel_workers_per_gather = 0"))
            for year in range(args.start_year, args.end_year + 1):
                print(f"fetching v10(04) data from db: year={year}, market={args.market}")
                y = fetch_one_year(conn, year, args.market)
                if not y.empty:
                    frames.append(y)
            try:
                industry_df = pd.read_sql(f"SELECT symbol, industry FROM stock_info WHERE market = '{args.market}'", conn)
            except Exception:
                industry_df = pd.DataFrame(columns=["symbol", "industry"])
    else:
        for year in range(args.start_year, args.end_year + 1):
            print(f"fetching v10(04) data from api: year={year}, market={args.market}")
            y = fetch_one_year_api(args.api_base, year, args.market)
            if not y.empty:
                frames.append(y)
        try:
            industry_df = fetch_all_rows_api(args.api_base, "/raw/stock-info", {"market": args.market})
            if not industry_df.empty:
                industry_df = industry_df[["symbol", "industry"]].drop_duplicates("symbol")
            else:
                industry_df = pd.DataFrame(columns=["symbol", "industry"])
        except Exception:
            industry_df = pd.DataFrame(columns=["symbol", "industry"])

    if not frames:
        raise RuntimeError("No data fetched. Check data source settings, year range, and market.")

    df = pd.concat(frames, ignore_index=True)
    if not industry_df.empty:
        df = df.merge(industry_df, on="symbol", how="left")
    df["industry"] = df.get("industry", pd.Series(index=df.index)).fillna("unknown")

    df = df.replace([np.inf, -np.inf], np.nan).dropna(subset=["q4_ni", TARGET, "year", "q4_eps"])
    
    if "q3_margin" not in df.columns:
        raise RuntimeError("Missing required column: q3_margin")
    missing_q3_margin = df["q3_margin"].isna()
    if missing_q3_margin.any():
        sample_rows = df.loc[missing_q3_margin, ["year", "symbol"]].head(10)
        raise RuntimeError(
            "q3_margin has missing values. "
            f"missing_count={int(missing_q3_margin.sum())}, sample={sample_rows.to_dict(orient='records')}"
        )

    df["anchor_eps"] = df["q4_eps"]

    df["q4_ocf_ratio"] = (df["q4_ocf"] / df["q4_ni"].replace(0, 1e-9)).clip(-5, 5)
    df["q4_re_ratio"] = df["q4_retained_earnings"] / df["capital"].replace(0, 1e-9)
    df["margin_momentum"] = df["q4_margin"] - df["q3_margin"]

    df["rev_yoy_m03"] = (df["rev_m03"] / df["rev_m03_ly"].replace(0, 1e-9)) - 1
    
    # 計算整個 Q1 累計營收 YoY
    df["rev_q1"] = df["rev_m01"].fillna(0) + df["rev_m02"].fillna(0) + df["rev_m03"].fillna(0)
    df["rev_q1_ly"] = df["rev_m01_ly"].fillna(0) + df["rev_m02_ly"].fillna(0) + df["rev_m03_ly"].fillna(0)
    df["rev_yoy_m01_m02_m03"] = (df["rev_q1"] / df["rev_q1_ly"].replace(0, 1e-9)) - 1

    add_industry_zscore(df, "rev_yoy_m03", "rev_yoy_m03_z")
    add_industry_zscore(df, "rev_yoy_m01_m02_m03", "rev_yoy_m01_m02_m03_z")
    add_cross_section_quantile(df, "rev_yoy_m03_z", "rev_yoy_m03_quantile")
    add_cross_section_quantile(df, "rev_yoy_m01_m02_m03_z", "rev_yoy_m01_m02_m03_quantile")

    df["ly_seasonality"] = (df["ly_q1_eps"] / df["ly_q4_eps"].replace(0, 1e-9)).clip(-5, 5)
    df["q4_yoy_eps"] = ((df["q4_eps"] / df["ly_q4_eps"].replace(0, 1e-9)) - 1).clip(-5, 5)

    df[TARGET_DELTA] = df[TARGET] - df["q4_eps"]
    
    df["ttm_eps_official"] = (
        df["q1_eps"].fillna(0) if "q1_eps" in df.columns else df["ly_q1_eps"].fillna(0)
        + df["q2_eps"].fillna(0)
        + df["q3_eps"].fillna(0)
        + df["q4_eps_official"].fillna(0)
    )

    rows_before_filter = len(df)
    if args.apply_trading_filter:
        ttm_ok = df["ttm_eps_official"] >= float(args.min_ttm_eps)
        vol_ok = (df["target_volume"].fillna(0) / 1000.0) >= float(args.min_volume_lots)
        df = df[ttm_ok & vol_ok].copy()

    for c in FEATURES:
        df[c] = df[c].fillna(0)

    keep = [c for c in (KEEP_OPTIONAL + ["year"] + FEATURES + [TARGET, TARGET_DELTA]) if c in df.columns]
    out = df[keep].copy()
    out["year"] = out["year"].astype(int)

    train_cols = [c for c in (["year"] + FEATURES + [TARGET, TARGET_DELTA]) if c in out.columns]
    out_train = out[train_cols].copy()

    meta_cols = [c for c in (KEEP_OPTIONAL + ["year", TARGET, TARGET_DELTA]) if c in out.columns]
    out_meta = out[meta_cols].copy()

    out_debug = out.copy()

    args.output_train.parent.mkdir(parents=True, exist_ok=True)
    out_train.to_csv(args.output_train, index=False)
    args.output_meta.parent.mkdir(parents=True, exist_ok=True)
    out_meta.to_csv(args.output_meta, index=False)
    args.output_evaluate.parent.mkdir(parents=True, exist_ok=True)
    out_debug.to_csv(args.output_evaluate, index=False)

    print("v10(04) prepare_data completed")
    print(f"- data_source: {args.data_source}")
    if args.data_source == "api":
        print(f"- api_base: {args.api_base}")
    print(f"- output_train: {args.output_train}")
    print(f"- output_meta: {args.output_meta}")
    print(f"- output_evaluate: {args.output_evaluate}")
    print(f"- apply_trading_filter: {args.apply_trading_filter}")
    if args.apply_trading_filter:
        print(f"- min_ttm_eps: {args.min_ttm_eps}")
        print(f"- min_volume_lots: {args.min_volume_lots}")
        print(f"- rows_before_filter: {rows_before_filter}")
    print(f"- rows: {len(out_debug)}")


if __name__ == "__main__":
    main()
