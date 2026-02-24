import argparse
import os
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from sqlalchemy import create_engine, text


# 11/15 視角 -> anchor_eps=Q3EPS + 10月營收，預測 Q4 EPS (或是年度 EPS 的代替)，含同比與產業標準化
# 設定預測目標：此處為預測當年度 Q4，所以對應財報日期是 f"{year}Q4"，不過由於 Q4 財報常常是在隔年 Q1 出，
# 預測期間 (預測 2024 這年) 時，我們抓 `year`=2024。
FEATURES = [
    "anchor_eps",
    "ly_q4_eps",
    "q3_yoy_eps",
    "q3_margin",
    "q3_ocf_ratio",
    "q3_re_ratio",
    "rev_yoy_m10_quantile",
    "rev_mom_m10_m9_quantile",
    "margin_momentum",
    "q3_roe",
    "q3_debt_ratio",
    "q3_non_op_ratio",
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
    p = argparse.ArgumentParser(description="Prepare v10_t4 dataset (11月視角) from DB.")
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
    q2, q3, q4 = f"{year}Q2", f"{year}Q3", f"{year}Q4"
    lyq4, lyq3 = f"{year-1}Q4", f"{year-1}Q3"
    prev_q4_str = f"{year-1}Q4"
    
    m9, m10 = f"{year}M09", f"{year}M10"
    ly_m9, ly_m10 = f"{year-1}M09", f"{year-1}M10"
    
    month_start, month_end = f"{year}-11-01", f"{year}-11-30"
    cutoff = f"{year}-11-15"

    inc_q3 = fetch_all_rows_api(api_base, "/raw/income-statements", {"start_date": q3, "end_date": q3, "market": market})
    inc_q2 = fetch_all_rows_api(api_base, "/raw/income-statements", {"start_date": q2, "end_date": q2, "market": market})
    bs_q3 = fetch_all_rows_api(api_base, "/raw/balance-sheets", {"start_date": q3, "end_date": q3, "market": market})
    cf_q3 = fetch_all_rows_api(api_base, "/raw/cash-flows", {"start_date": q3, "end_date": q3, "market": market})
    # target eps is q4 here, and history needs lyq4, lyq3, q2
    qr = fetch_all_rows_api(api_base, "/raw/quarterly-reports", {"start_date": lyq3, "end_date": q4, "market": market})
    mr = fetch_all_rows_api(api_base, "/raw/monthly-revenue", {"start_date": ly_m9, "end_date": m10})
    dq = fetch_all_rows_api(api_base, "/raw/daily-quotes", {"start_date": month_start, "end_date": month_end, "market": market})
    pe = fetch_all_rows_api(api_base, "/raw/pe-ratio", {"start_date": month_start, "end_date": month_end, "market": market})

    if inc_q3.empty:
        return pd.DataFrame()

    q3_data = inc_q3.copy()
    if not bs_q3.empty:
        q3_data = q3_data.merge(
            bs_q3[["symbol", "date", "total_equity", "total_liabilities", "total_assets", "share_capital", "retained_earnings"]],
            on=["symbol", "date"],
            how="left",
        )
    if not cf_q3.empty:
        q3_data = q3_data.merge(cf_q3[["symbol", "date", "cash_flow_operating_q"]], on=["symbol", "date"], how="left")
    q3_data = q3_data.rename(columns={"revenue_q": "q3_rev", "net_income_q": "q3_ni", "share_capital": "capital", "retained_earnings": "q3_retained_earnings", "cash_flow_operating_q": "q3_ocf"})
    q3_data["q3_eps"] = safe_col(q3_data, "eps_q")
    q3_data["q3_margin"] = safe_col(q3_data, "q3_ni") / safe_col(q3_data, "q3_rev").replace(0, np.nan)
    q3_data["q3_non_op_ratio"] = safe_col(q3_data, "non_operating_income_q") / safe_col(q3_data, "pretax_income_q").replace(0, np.nan)
    q3_data["q3_roe"] = safe_col(q3_data, "q3_ni") / safe_col(q3_data, "total_equity").replace(0, np.nan)
    q3_data["q3_debt_ratio"] = safe_col(q3_data, "total_liabilities") / safe_col(q3_data, "total_assets").replace(0, np.nan)
    q3_data = q3_data[["symbol", "name", "q3_rev", "q3_ni", "q3_eps", "q3_margin", "q3_non_op_ratio", "q3_roe", "q3_debt_ratio", "capital", "q3_retained_earnings", "q3_ocf"]]

    q2_data = pd.DataFrame(columns=["symbol", "q2_margin"])
    if not inc_q2.empty:
        q2_data = inc_q2[["symbol", "revenue_q", "net_income_q"]].copy()
        q2_data["q2_margin"] = q2_data["net_income_q"] / q2_data["revenue_q"].replace(0, np.nan)
        q2_data = q2_data[["symbol", "q2_margin"]]

    this_monthly = pd.DataFrame(columns=["symbol", "rev_m9", "rev_m10", "rev_m9_ly", "rev_m10_ly"])
    if not mr.empty:
        if "market" in mr.columns:
            mr = mr[mr["market"].astype(str).str.upper() == market.upper()].copy()
        mr2 = mr[mr["date"].isin([m9, m10, ly_m9, ly_m10])].copy()
        if not mr2.empty:
            pvt = mr2.pivot_table(index="symbol", columns="date", values="revenue_current", aggfunc="last").reset_index()
            this_monthly = pvt.rename(columns={m9: "rev_m9", m10: "rev_m10", ly_m9: "rev_m9_ly", ly_m10: "rev_m10_ly"})
            for c in ["rev_m9", "rev_m10", "rev_m9_ly", "rev_m10_ly"]:
                if c not in this_monthly.columns:
                    this_monthly[c] = np.nan
            this_monthly = this_monthly[["symbol", "rev_m9", "rev_m10", "rev_m9_ly", "rev_m10_ly"]]

    eps_hist = pd.DataFrame(columns=["symbol", "target_eps", "ly_q4_eps", "ly_q3_eps", "prev_q4_eps", "q2_eps", "q3_eps_official"])
    if not qr.empty:
        qr2 = qr[qr["date"].isin([q4, lyq4, lyq3, prev_q4_str, q2, q3])].copy()
        p = qr2.pivot_table(index="symbol", columns="date", values="eps_q", aggfunc="last").reset_index()
        eps_hist = p.rename(columns={q4: "target_eps", lyq4: "ly_q4_eps", lyq3: "ly_q3_eps", prev_q4_str: "prev_q4_eps", q2: "q2_eps", q3: "q3_eps_official"})
        for c in ["target_eps", "ly_q4_eps", "ly_q3_eps", "prev_q4_eps", "q2_eps", "q3_eps_official"]:
            if c not in eps_hist.columns:
                eps_hist[c] = np.nan
        eps_hist = eps_hist[["symbol", "target_eps", "ly_q4_eps", "ly_q3_eps", "prev_q4_eps", "q2_eps", "q3_eps_official"]]

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

    out = q3_data.merge(q2_data, on="symbol", how="left")
    out = out.merge(this_monthly, on="symbol", how="inner")
    out = out.merge(eps_hist, on="symbol", how="inner")
    out = out.merge(market_snapshot, on="symbol", how="left")
    out["year"] = year
    out["feature_cutoff_date"] = cutoff
    return out


def fetch_one_year(conn, year: int, market: str) -> pd.DataFrame:
    q2, q3, q4 = f"{year}Q2", f"{year}Q3", f"{year}Q4"
    lyq4, lyq3 = f"{year-1}Q4", f"{year-1}Q3"
    prev_q4_str = f"{year-1}Q4"
    
    m9, m10 = f"{year}M09", f"{year}M10"
    ly_m9, ly_m10 = f"{year-1}M09", f"{year-1}M10"
    
    month_start, month_end = f"{year}-11-01", f"{year}-11-30"
    cutoff = f"{year}-11-15"

    sql = f"""
    WITH q3_data AS (
      SELECT i.symbol, i.name, i.revenue_q AS q3_rev, i.net_income_q AS q3_ni, i.eps_q AS q3_eps,
             i.net_income_q/NULLIF(i.revenue_q,0) AS q3_margin,
             i.non_operating_income_q/NULLIF(i.pretax_income_q,0) AS q3_non_op_ratio,
             i.net_income_q/NULLIF(b.total_equity,0) AS q3_roe,
             b.total_liabilities/NULLIF(b.total_assets,0) AS q3_debt_ratio,
             b.share_capital AS capital, b.retained_earnings AS q3_retained_earnings,
             c.cash_flow_operating_q AS q3_ocf
      FROM income_statement i
      JOIN balance_sheet b ON i.symbol=b.symbol AND i.date=b.date
      JOIN cash_flow c ON i.symbol=c.symbol AND i.date=c.date
      WHERE i.date='{q3}' AND i.market='{market}'
    ),
    q2_data AS (
      SELECT symbol, net_income_q/NULLIF(revenue_q,0) AS q2_margin
      FROM income_statement WHERE date='{q2}' AND market='{market}'
    ),
    this_monthly AS (
      SELECT symbol,
             MAX(CASE WHEN date='{m9}' THEN revenue_current END) AS rev_m9,
             MAX(CASE WHEN date='{m10}' THEN revenue_current END) AS rev_m10,
             MAX(CASE WHEN date='{ly_m9}' THEN revenue_current END) AS rev_m9_ly,
             MAX(CASE WHEN date='{ly_m10}' THEN revenue_current END) AS rev_m10_ly
      FROM monthly_revenue
      WHERE date IN ('{m9}','{m10}','{ly_m9}','{ly_m10}')
      GROUP BY symbol
    ),
    eps_hist AS (
      SELECT qr.symbol, qr.eps_q AS target_eps,
             (SELECT eps_q FROM quarterly_reports WHERE symbol=qr.symbol AND date='{lyq4}' AND market='{market}') AS ly_q4_eps,
             (SELECT eps_q FROM quarterly_reports WHERE symbol=qr.symbol AND date='{lyq3}' AND market='{market}') AS ly_q3_eps,
             (SELECT eps_q FROM quarterly_reports WHERE symbol=qr.symbol AND date='{prev_q4_str}' AND market='{market}') AS prev_q4_eps,
             (SELECT eps_q FROM quarterly_reports WHERE symbol=qr.symbol AND date='{q2}' AND market='{market}') AS q2_eps,
             (SELECT eps_q FROM quarterly_reports WHERE symbol=qr.symbol AND date='{q3}' AND market='{market}') AS q3_eps_official
      FROM quarterly_reports qr WHERE qr.date='{q4}' AND qr.market='{market}'
    ),
    market_snapshot AS (
      SELECT DISTINCT ON (dq.symbol) dq.symbol, dq.date AS target_date, dq.close AS target_close, dq.volume AS target_volume, pr.pe_ratio AS pe_current
      FROM daily_quotes dq
      LEFT JOIN pe_ratio pr ON pr.symbol=dq.symbol AND pr.market=dq.market AND pr.date=dq.date
      WHERE dq.market='{market}' AND dq.date>='{month_start}' AND dq.date<='{month_end}'
      ORDER BY dq.symbol, dq.date DESC
    )
    SELECT {year} AS year, '{cutoff}' AS feature_cutoff_date, q3.*, q2.q2_margin,
           m.rev_m9,m.rev_m10,m.rev_m9_ly,m.rev_m10_ly,
           e.target_eps,e.ly_q4_eps,e.ly_q3_eps,e.prev_q4_eps,e.q2_eps,e.q3_eps_official,
           ms.target_date,ms.target_close,ms.target_volume,ms.pe_current
    FROM q3_data q3
    LEFT JOIN q2_data q2 ON q3.symbol=q2.symbol
    JOIN this_monthly m ON q3.symbol=m.symbol
    JOIN eps_hist e ON q3.symbol=e.symbol
    LEFT JOIN market_snapshot ms ON q3.symbol=ms.symbol
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
                print(f"fetching v10(11) data from db: year={year}, market={args.market}")
                y = fetch_one_year(conn, year, args.market)
                if not y.empty:
                    frames.append(y)
            try:
                industry_df = pd.read_sql(f"SELECT symbol, industry FROM stock_info WHERE market = '{args.market}'", conn)
            except Exception:
                industry_df = pd.DataFrame(columns=["symbol", "industry"])
    else:
        for year in range(args.start_year, args.end_year + 1):
            print(f"fetching v10(11) data from api: year={year}, market={args.market}")
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

    df = df.replace([np.inf, -np.inf], np.nan).dropna(subset=["q3_ni", TARGET, "year", "q3_eps"])
    
    if "q2_margin" not in df.columns:
        raise RuntimeError("Missing required column: q2_margin")
    missing_q2_margin = df["q2_margin"].isna()
    if missing_q2_margin.any():
        sample_rows = df.loc[missing_q2_margin, ["year", "symbol"]].head(10)
        raise RuntimeError(
            "q2_margin has missing values. "
            f"missing_count={int(missing_q2_margin.sum())}, sample={sample_rows.to_dict(orient='records')}"
        )

    # anchor_eps = q3_eps（Q3財報模型統一命名）
    df["anchor_eps"] = df["q3_eps"]

    df["q3_ocf_ratio"] = (df["q3_ocf"] / df["q3_ni"].replace(0, 1e-9)).clip(-5, 5)
    df["q3_re_ratio"] = df["q3_retained_earnings"] / df["capital"].replace(0, 1e-9)
    df["margin_momentum"] = df["q3_margin"] - df["q2_margin"]

    df["rev_yoy_m10"] = (df["rev_m10"] / df["rev_m10_ly"].replace(0, 1e-9)) - 1
    df["rev_mom_m10_m9"] = (df["rev_m10"] / df["rev_m9"].replace(0, 1e-9)) - 1

    add_industry_zscore(df, "rev_yoy_m10", "rev_yoy_m10_z")
    add_industry_zscore(df, "rev_mom_m10_m9", "rev_mom_m10_m9_z")

    # 主流程統一使用 quantile 特徵
    add_cross_section_quantile(df, "rev_yoy_m10_z", "rev_yoy_m10_quantile")
    add_cross_section_quantile(df, "rev_mom_m10_m9_z", "rev_mom_m10_m9_quantile")

    # 公司層級季節性：去年 Q4 / Q3 EPS 比值
    df["ly_seasonality"] = (df["ly_q4_eps"] / df["ly_q3_eps"].replace(0, 1e-9)).clip(-5, 5)
    df["q3_yoy_eps"] = ((df["q3_eps"] / df["ly_q3_eps"].replace(0, 1e-9)) - 1).clip(-5, 5)

    df[TARGET_DELTA] = df[TARGET] - df["q3_eps"]
    
    # 11 月視角僅能使用已公告到 Q3 的資訊
    df["ttm_eps_official"] = (
        df["prev_q4_eps"].fillna(0)
        + df["q1_eps"].fillna(0)
        + df["q2_eps"].fillna(0)
        + df["q3_eps_official"].fillna(0)
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

    print("v10(11) prepare_data completed")
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
