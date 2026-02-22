import argparse
import os
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from sqlalchemy import create_engine, text


# v10: 5/14 視角 -> Q1 + 4月營收，anchor = q1_eps
FEATURES = [
    "anchor_eps",
    "ly_q3_eps",
    "q1_margin",
    "q1_ocf_ratio",
    "q1_re_ratio",
    "rev_yoy_m4_quantile",
    "margin_momentum",
    "q1_roe",
    "q1_debt_ratio",
    "q1_non_op_ratio",
    "ly_seasonality",
]
TARGET = "target_eps"
TARGET_DELTA = "delta_eps"

KEEP_OPTIONAL = [
    "symbol", "name", "industry", "q3_date", "q3_close", "q3_volume", "pe_current",
    "prev_q4_eps", "q1_eps", "q2_eps_official", "ttm_eps_official", "feature_cutoff_date",
]

DEFAULT_OUTPUT_TRAIN = Path(__file__).resolve().parent / "dataset_train.csv"
DEFAULT_OUTPUT_META = Path(__file__).resolve().parent / "dataset_meta.csv"
DEFAULT_OUTPUT_EVALUATE = Path(__file__).resolve().parent / "dataset_evaluate.csv"


def get_db_url() -> str:
    user = os.getenv("DB_USER", "user")
    password = os.getenv("DB_PASSWORD", "password")
    host = os.getenv("DB_HOST", "db")
    port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME", "stock_db")
    return f"postgresql://{user}:{password}@{host}:{port}/{db_name}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare v10 dataset (5月視角) from DB or API.")
    parser.add_argument("--start-year", type=int, default=2020)
    parser.add_argument("--end-year", type=int, default=2025)
    parser.add_argument("--market", type=str, default="sii", choices=["sii", "otc"])
    parser.add_argument("--data-source", type=str, choices=["db", "api"], default="db")
    parser.add_argument("--api-base", type=str, default=os.getenv("BACKEND_API_BASE", "http://100.103.191.79:8000"))
    parser.add_argument("--apply-trading-filter", action="store_true")
    parser.add_argument("--min-ttm-eps", type=float, default=2.0)
    parser.add_argument("--min-volume-lots", type=float, default=500.0)
    parser.add_argument("--output-train", type=Path, default=DEFAULT_OUTPUT_TRAIN)
    parser.add_argument("--output-meta", type=Path, default=DEFAULT_OUTPUT_META)
    parser.add_argument("--output-evaluate", type=Path, default=DEFAULT_OUTPUT_EVALUATE)
    return parser.parse_args()


def add_industry_zscore(df: pd.DataFrame, col: str, out_col: str) -> None:
    grp = df.groupby(["year", "industry"])[col]
    mean = grp.transform("mean")
    std = grp.transform("std").replace(0, np.nan)
    df[out_col] = ((df[col] - mean) / std).replace([np.inf, -np.inf], np.nan).fillna(0)


def add_cross_section_quantile(df: pd.DataFrame, z_col: str, out_col: str) -> None:
    ranks = df.groupby(["year", "industry"])[z_col].rank(method="average", pct=True).fillna(0.5)
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
    q1, q2, q3 = f"{year}Q1", f"{year}Q2", f"{year}Q3"
    p4, lyq3 = f"{year-1}Q4", f"{year-1}Q3"
    lyq2, lyq1 = f"{year-1}Q2", f"{year-1}Q1"
    m4, ly_m4 = f"{year}M04", f"{year-1}M04"
    month_start, month_end = f"{year}-09-01", f"{year}-09-30"
    cutoff = f"{year}-05-14"

    inc_q1 = fetch_all_rows_api(api_base, "/raw/income-statements", {"start_date": q1, "end_date": q1, "market": market})
    bs_q1  = fetch_all_rows_api(api_base, "/raw/balance-sheets",    {"start_date": q1, "end_date": q1, "market": market})
    cf_q1  = fetch_all_rows_api(api_base, "/raw/cash-flows",        {"start_date": q1, "end_date": q1, "market": market})
    qr     = fetch_all_rows_api(api_base, "/raw/quarterly-reports", {"start_date": lyq1, "end_date": q3, "market": market})
    mr     = fetch_all_rows_api(api_base, "/raw/monthly-revenue",   {"start_date": ly_m4, "end_date": m4})
    dq     = fetch_all_rows_api(api_base, "/raw/daily-quotes",      {"start_date": month_start, "end_date": month_end, "market": market})
    pe     = fetch_all_rows_api(api_base, "/raw/pe-ratio",          {"start_date": month_start, "end_date": month_end, "market": market})

    if inc_q1.empty:
        return pd.DataFrame()

    q1_df = inc_q1.copy()
    if not bs_q1.empty:
        q1_df = q1_df.merge(
            bs_q1[["symbol", "date", "total_equity", "total_liabilities", "total_assets", "share_capital", "retained_earnings"]],
            on=["symbol", "date"], how="left",
        )
    if not cf_q1.empty:
        q1_df = q1_df.merge(cf_q1[["symbol", "date", "cash_flow_operating_q"]], on=["symbol", "date"], how="left")
    q1_df = q1_df.rename(columns={
        "share_capital": "capital",
        "retained_earnings": "q1_retained_earnings",
        "cash_flow_operating_q": "q1_ocf",
        "revenue_q": "q1_rev",
        "net_income_q": "q1_ni",
    })
    q1_df["q1_eps"]    = safe_col(q1_df, "eps_q")
    q1_df["q1_margin"] = safe_col(q1_df, "q1_ni") / safe_col(q1_df, "q1_rev").replace(0, np.nan)
    q1_df["q1_non_op_ratio"] = safe_col(q1_df, "non_operating_income_q") / safe_col(q1_df, "pretax_income_q").replace(0, np.nan)
    q1_df["q1_roe"]        = safe_col(q1_df, "q1_ni") / safe_col(q1_df, "total_equity").replace(0, np.nan)
    q1_df["q1_debt_ratio"] = safe_col(q1_df, "total_liabilities") / safe_col(q1_df, "total_assets").replace(0, np.nan)
    q1_df = q1_df[["symbol", "name", "q1_rev", "q1_ni", "q1_eps", "q1_margin", "q1_non_op_ratio",
                   "q1_roe", "q1_debt_ratio", "capital", "q1_retained_earnings", "q1_ocf"]]

    # 月營收
    this_monthly = pd.DataFrame(columns=["symbol", "rev_m4", "rev_m4_ly"])
    if not mr.empty:
        if "market" in mr.columns:
            mr = mr[mr["market"].astype(str).str.upper() == market.upper()].copy()
        mr2 = mr[mr["date"].isin([m4, ly_m4])].copy()
        if not mr2.empty:
            pivot = mr2.pivot_table(index="symbol", columns="date", values="revenue_current", aggfunc="last").reset_index()
            this_monthly = pivot.rename(columns={m4: "rev_m4", ly_m4: "rev_m4_ly"})
            for c in ["rev_m4", "rev_m4_ly"]:
                if c not in this_monthly.columns:
                    this_monthly[c] = np.nan
            this_monthly = this_monthly[["symbol", "rev_m4", "rev_m4_ly"]]

    # EPS 歷史
    eps_hist = pd.DataFrame(columns=["symbol", "target_eps", "ly_q3_eps", "ly_q2_eps", "ly_q1_eps", "prev_q4_eps", "q1_eps_official", "q2_eps_official"])
    if not qr.empty:
        qr2 = qr[qr["date"].isin([q3, lyq3, lyq2, lyq1, p4, q1, q2])].copy()
        p = qr2.pivot_table(index="symbol", columns="date", values="eps_q", aggfunc="last").reset_index()
        eps_hist = p.rename(columns={
            q3: "target_eps", lyq3: "ly_q3_eps", lyq2: "ly_q2_eps", lyq1: "ly_q1_eps",
            p4: "prev_q4_eps", q1: "q1_eps_official", q2: "q2_eps_official",
        })
        for c in ["target_eps", "ly_q3_eps", "ly_q2_eps", "ly_q1_eps", "prev_q4_eps", "q1_eps_official", "q2_eps_official"]:
            if c not in eps_hist.columns:
                eps_hist[c] = np.nan
        eps_hist = eps_hist[["symbol", "target_eps", "ly_q3_eps", "ly_q2_eps", "ly_q1_eps", "prev_q4_eps", "q1_eps_official", "q2_eps_official"]]

    # 市場快照（Q3 期間）
    market_snapshot = pd.DataFrame(columns=["symbol", "q3_date", "q3_close", "q3_volume", "pe_current"])
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
        market_snapshot = dq2.rename(columns={"date": "q3_date", "close": "q3_close", "volume": "q3_volume", "pe_ratio": "pe_current"})
        market_snapshot["q3_date"] = market_snapshot["q3_date"].dt.strftime("%Y-%m-%d")
        market_snapshot = market_snapshot[["symbol", "q3_date", "q3_close", "q3_volume", "pe_current"]]

    out = q1_df.merge(this_monthly, on="symbol", how="inner")
    out = out.merge(eps_hist, on="symbol", how="inner")
    out = out.merge(market_snapshot, on="symbol", how="left")
    out["year"] = year
    out["feature_cutoff_date"] = cutoff
    return out


def fetch_one_year(conn, year: int, market: str) -> pd.DataFrame:
    q1, q2, q3 = f"{year}Q1", f"{year}Q2", f"{year}Q3"
    p4, lyq3 = f"{year-1}Q4", f"{year-1}Q3"
    lyq2, lyq1 = f"{year-1}Q2", f"{year-1}Q1"
    m4, ly_m4 = f"{year}M04", f"{year-1}M04"
    month_start, month_end = f"{year}-09-01", f"{year}-09-30"
    cutoff = f"{year}-05-14"

    sql = f"""
    WITH q1_data AS (
      SELECT i.symbol, i.name, i.revenue_q AS q1_rev, i.net_income_q AS q1_ni, i.eps_q AS q1_eps,
             i.net_income_q/NULLIF(i.revenue_q,0) AS q1_margin,
             i.non_operating_income_q/NULLIF(i.pretax_income_q,0) AS q1_non_op_ratio,
             i.net_income_q/NULLIF(b.total_equity,0) AS q1_roe,
             b.total_liabilities/NULLIF(b.total_assets,0) AS q1_debt_ratio,
             b.share_capital AS capital, b.retained_earnings AS q1_retained_earnings,
             c.cash_flow_operating_q AS q1_ocf
      FROM income_statement i
      JOIN balance_sheet b ON i.symbol=b.symbol AND i.date=b.date
      JOIN cash_flow c ON i.symbol=c.symbol AND i.date=c.date
      WHERE i.date='{q1}' AND i.market='{market}'
    ),
    this_monthly AS (
      SELECT symbol,
             MAX(CASE WHEN date='{m4}' THEN revenue_current END) AS rev_m4,
             MAX(CASE WHEN date='{ly_m4}' THEN revenue_current END) AS rev_m4_ly
      FROM monthly_revenue
      WHERE date IN ('{m4}','{ly_m4}')
      GROUP BY symbol
    ),
    eps_hist AS (
      SELECT qr.symbol, qr.eps_q AS target_eps,
             (SELECT eps_q FROM quarterly_reports WHERE symbol=qr.symbol AND date='{lyq3}' AND market='{market}') AS ly_q3_eps,
             (SELECT eps_q FROM quarterly_reports WHERE symbol=qr.symbol AND date='{lyq2}' AND market='{market}') AS ly_q2_eps,
             (SELECT eps_q FROM quarterly_reports WHERE symbol=qr.symbol AND date='{lyq1}' AND market='{market}') AS ly_q1_eps,
             (SELECT eps_q FROM quarterly_reports WHERE symbol=qr.symbol AND date='{p4}' AND market='{market}') AS prev_q4_eps,
             (SELECT eps_q FROM quarterly_reports WHERE symbol=qr.symbol AND date='{q1}' AND market='{market}') AS q1_eps_official,
             (SELECT eps_q FROM quarterly_reports WHERE symbol=qr.symbol AND date='{q2}' AND market='{market}') AS q2_eps_official
      FROM quarterly_reports qr WHERE qr.date='{q3}' AND qr.market='{market}'
    ),
    market_snapshot AS (
      SELECT DISTINCT ON (dq.symbol) dq.symbol, dq.date AS q3_date, dq.close AS q3_close, dq.volume AS q3_volume, pr.pe_ratio AS pe_current
      FROM daily_quotes dq
      LEFT JOIN pe_ratio pr ON pr.symbol=dq.symbol AND pr.market=dq.market AND pr.date=dq.date
      WHERE dq.market='{market}' AND dq.date>='{month_start}' AND dq.date<='{month_end}'
      ORDER BY dq.symbol, dq.date DESC
    )
    SELECT {year} AS year, '{cutoff}' AS feature_cutoff_date, q1.*, m.rev_m4, m.rev_m4_ly,
           e.target_eps, e.ly_q3_eps, e.ly_q2_eps, e.ly_q1_eps, e.prev_q4_eps, e.q1_eps_official, e.q2_eps_official,
           ms.q3_date, ms.q3_close, ms.q3_volume, ms.pe_current
    FROM q1_data q1
    JOIN this_monthly m ON q1.symbol=m.symbol
    JOIN eps_hist e ON q1.symbol=e.symbol
    LEFT JOIN market_snapshot ms ON q1.symbol=ms.symbol
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
                print(f"fetching v10(05) data from db: year={year}, market={args.market}")
                df_year = fetch_one_year(conn, year=year, market=args.market)
                if not df_year.empty:
                    frames.append(df_year)
            try:
                industry_df = pd.read_sql(
                    "SELECT symbol, industry FROM stock_info WHERE market = :market",
                    conn, params={"market": args.market},
                )
            except Exception:
                industry_df = pd.DataFrame(columns=["symbol", "industry"])
    else:
        for year in range(args.start_year, args.end_year + 1):
            print(f"fetching v10(05) data from api: year={year}, market={args.market}")
            df_year = fetch_one_year_api(args.api_base, year=year, market=args.market)
            if not df_year.empty:
                frames.append(df_year)
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

    df = df.replace([np.inf, -np.inf], np.nan).dropna(subset=["q1_ni", TARGET, "year", "q1_eps"])

    # anchor_eps = q1_eps（5/6/7月視角模型統一命名）
    df["anchor_eps"] = df["q1_eps"]

    df["q1_ocf_ratio"]  = (df["q1_ocf"] / df["q1_ni"].replace(0, 1e-9)).clip(-5, 5)
    df["q1_re_ratio"]   = df["q1_retained_earnings"] / df["capital"].replace(0, 1e-9)

    # margin_momentum：Q1 vs 去年Q1（無法取 Q4 前期，改用 YoY 對比）
    df["margin_momentum"] = df["q1_margin"] - df.groupby(["industry", "year"])["q1_margin"].transform("mean")

    # 月營收工程：4月 YoY + 產業標準化
    df["rev_yoy_m4"] = (df["rev_m4"] / df["rev_m4_ly"].replace(0, 1e-9)) - 1
    add_industry_zscore(df, "rev_yoy_m4", "rev_yoy_m4_z")
    add_cross_section_quantile(df, "rev_yoy_m4_z", "rev_yoy_m4_quantile")

    # 公司層級季節性：去年 Q3 / Q1 EPS 比值
    df["ly_seasonality"] = (df["ly_q3_eps"] / df["ly_q1_eps"].replace(0, 1e-9)).clip(-5, 5)

    df[TARGET_DELTA] = df[TARGET] - df["q1_eps"]
    df["ttm_eps_official"] = (
        df["prev_q4_eps"].fillna(0)
        + df["q1_eps_official"].fillna(0)
        + df["q2_eps_official"].fillna(0)
        + df[TARGET].fillna(0)
    )

    rows_before_filter = len(df)
    if args.apply_trading_filter:
        ttm_ok = df["ttm_eps_official"] >= float(args.min_ttm_eps)
        vol_ok = (df["q3_volume"].fillna(0) / 1000.0) >= float(args.min_volume_lots)
        df = df[ttm_ok & vol_ok].copy()

    for feature_name in FEATURES:
        df[feature_name] = df[feature_name].fillna(0)

    keep_cols = [c for c in (KEEP_OPTIONAL + ["year"] + FEATURES + [TARGET, TARGET_DELTA]) if c in df.columns]
    out_df = df[keep_cols].copy()
    out_df["year"] = out_df["year"].astype(int)

    train_cols = [c for c in (["year"] + FEATURES + [TARGET, TARGET_DELTA]) if c in out_df.columns]
    out_train = out_df[train_cols].copy()

    meta_cols = [c for c in (KEEP_OPTIONAL + ["year", TARGET, TARGET_DELTA]) if c in out_df.columns]
    out_meta = out_df[meta_cols].copy()

    out_debug = out_df.copy()

    args.output_train.parent.mkdir(parents=True, exist_ok=True)
    out_train.to_csv(args.output_train, index=False)
    args.output_meta.parent.mkdir(parents=True, exist_ok=True)
    out_meta.to_csv(args.output_meta, index=False)
    args.output_evaluate.parent.mkdir(parents=True, exist_ok=True)
    out_debug.to_csv(args.output_evaluate, index=False)

    print("v10(05) prepare_data completed")
    print(f"- data_source: {args.data_source}")
    print(f"- output_train: {args.output_train}")
    print(f"- output_meta: {args.output_meta}")
    print(f"- output_evaluate: {args.output_evaluate}")
    print(f"- apply_trading_filter: {args.apply_trading_filter}")
    if args.apply_trading_filter:
        print(f"- min_ttm_eps: {args.min_ttm_eps}")
        print(f"- rows_before_filter: {rows_before_filter}")
    print(f"- rows: {len(out_df)}")


if __name__ == "__main__":
    main()
