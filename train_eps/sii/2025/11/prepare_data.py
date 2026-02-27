import argparse
import os
from pathlib import Path
from typing import Optional, Set

import numpy as np
import pandas as pd
import requests
from sqlalchemy import create_engine, text


# November (around 11/15) setup:
# - Use Q3 EPS as anchor (`anchor_eps`).
# - Predict full-year EPS for `year`; the target quarter key is `f"{year}Q4"`.
# - Example: predicting 2024 full-year EPS uses `year=2024`.
MODEL_FEATURES = [
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
    # XBRL-enriched features (Q3 snapshot for November prediction)
    "xbrl_gross_margin_q",
    "xbrl_op_margin_q",
    "xbrl_rd_ratio_q",
    "xbrl_tax_rate_q",
    "xbrl_current_ratio",
    "xbrl_cash_to_assets",
    "xbrl_cfo_to_ni_q",
    "xbrl_capex_to_revenue_q",
]
TARGET = "target_eps"
TARGET_DELTA = "delta_eps"

CONTEXT_COLUMNS = ["symbol", "name", "industry"]

TRAIN_COLUMNS = ["year"] + MODEL_FEATURES + [TARGET, TARGET_DELTA]
EVALUATE_COLUMNS = CONTEXT_COLUMNS + ["year"] + MODEL_FEATURES + [TARGET, TARGET_DELTA]

DEFAULT_OUTPUT_TRAIN = Path(__file__).resolve().parent / "dataset_train.csv"
DEFAULT_OUTPUT_EVALUATE = Path(__file__).resolve().parent / "dataset_evaluate.csv"


def get_db_url() -> str:
    return f"postgresql://{os.getenv('DB_USER','user')}:{os.getenv('DB_PASSWORD','password')}@{os.getenv('DB_HOST','db')}:{os.getenv('DB_PORT','5432')}/{os.getenv('DB_NAME','stock_db')}"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Prepare v10_t4 dataset (November view) from DB/API.")
    p.add_argument("--start-year", type=int, default=2020)
    p.add_argument("--end-year", type=int, default=2024)
    p.add_argument("--market", type=str, default="sii", choices=["sii", "otc"])
    p.add_argument("--data-source", type=str, choices=["db", "api"], default="db")
    p.add_argument("--api-base", type=str, default=os.getenv("BACKEND_API_BASE", "http://100.103.191.79:8000"))
    p.add_argument("--apply-trading-filter", action="store_true")
    p.add_argument("--min-ttm-eps", type=float, default=2.0)
    p.add_argument("--output-train", type=Path, default=DEFAULT_OUTPUT_TRAIN)
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


def normalize_api_chunk(payload: object) -> list[dict]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("value", "data", "items", "results", "rows"):
            v = payload.get(key)
            if isinstance(v, list):
                return v
    raise ValueError(f"Unexpected API payload shape: {type(payload)}")


def fetch_all_rows_api(api_base: str, path: str, params: dict, limit: int = 5000) -> pd.DataFrame:
    rows: list[dict] = []
    offset = 0
    while True:
        q = dict(params)
        q["limit"] = limit
        q["offset"] = offset
        resp = requests.get(f"{api_base.rstrip('/')}{path}", params=q, timeout=60)
        resp.raise_for_status()
        chunk = normalize_api_chunk(resp.json())
        if not chunk:
            break
        rows.extend(chunk)
        if len(chunk) < limit:
            break
        offset += limit
    return pd.DataFrame(rows)


def safe_col(df: pd.DataFrame, col: str) -> pd.Series:
    return df[col] if col in df.columns else pd.Series([np.nan] * len(df), index=df.index)


def safe_div_positive(numer: pd.Series, denom: pd.Series) -> pd.Series:
    numer_v = pd.to_numeric(numer, errors="coerce")
    denom_v = pd.to_numeric(denom, errors="coerce")
    return numer_v / denom_v.where(denom_v > 0)


def filter_xbrl_symbols(df: pd.DataFrame, symbols: Optional[Set[str]]) -> pd.DataFrame:
    if df.empty or not symbols or "symbol" not in df.columns:
        return df
    return df[df["symbol"].astype(str).isin(symbols)].copy()


def ensure_xbrl_value(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        out = df.copy()
        out["_value"] = pd.Series(dtype=float)
        return out
    out = df.copy()
    if "value_num" in out.columns:
        out["_value"] = pd.to_numeric(out["value_num"], errors="coerce")
    else:
        out["_value"] = pd.Series(np.nan, index=out.index, dtype=float)
    if "value_text" in out.columns:
        out["_value"] = out["_value"].fillna(pd.to_numeric(out["value_text"], errors="coerce"))
    return out


def pivot_xbrl_codes(
    df: pd.DataFrame,
    *,
    date: str,
    period_type: str,
    account_codes: list[str],
    symbols: Optional[Set[str]] = None,
) -> pd.DataFrame:
    required = {"date", "symbol", "period_type", "account_code"}
    if df.empty or not required.issubset(df.columns):
        return pd.DataFrame(columns=["symbol"] + account_codes)

    x = ensure_xbrl_value(df)
    x = filter_xbrl_symbols(x, symbols)
    x["date"] = x["date"].astype(str)
    x["period_type"] = x["period_type"].astype(str)
    x["account_code"] = x["account_code"].astype(str)
    x = x[
        (x["date"] == str(date))
        & (x["period_type"] == str(period_type))
        & (x["account_code"].isin(account_codes))
    ]
    if x.empty:
        return pd.DataFrame(columns=["symbol"] + account_codes)

    pvt = x.pivot_table(index="symbol", columns="account_code", values="_value", aggfunc="last").reset_index()
    for code in account_codes:
        if code not in pvt.columns:
            pvt[code] = np.nan
    return pvt[["symbol"] + account_codes]


def build_cashflow_single_quarter(
    cf_xbrl: pd.DataFrame,
    *,
    q2: str,
    q3: str,
    account_codes: list[str],
    symbols: Optional[Set[str]] = None,
) -> pd.DataFrame:
    q3_acc = pivot_xbrl_codes(cf_xbrl, date=q3, period_type="accumulated", account_codes=account_codes, symbols=symbols)
    q2_acc = pivot_xbrl_codes(cf_xbrl, date=q2, period_type="accumulated", account_codes=account_codes, symbols=symbols)
    if q3_acc.empty:
        return pd.DataFrame(columns=["symbol"] + account_codes)

    m = q3_acc.merge(q2_acc, on="symbol", how="left", suffixes=("_q3acc", "_q2acc"))
    out = pd.DataFrame({"symbol": m["symbol"]})
    for code in account_codes:
        out[code] = pd.to_numeric(m[f"{code}_q3acc"], errors="coerce") - pd.to_numeric(m[f"{code}_q2acc"], errors="coerce")
    return out


def build_xbrl_feature_frame(
    inc_xbrl: pd.DataFrame,
    bs_xbrl: pd.DataFrame,
    cf_xbrl: pd.DataFrame,
    *,
    q2: str,
    q3: str,
    symbols: Optional[Set[str]] = None,
) -> pd.DataFrame:
    inc_codes = ["4000", "5900", "6300", "6900", "7900", "7950", "8200"]
    bs_codes = ["1100", "11XX", "21XX", "1XXX"]
    cf_codes = ["AAAA", "B02700"]

    inc_q3 = pivot_xbrl_codes(inc_xbrl, date=q3, period_type="quarter", account_codes=inc_codes, symbols=symbols)
    bs_q3 = pivot_xbrl_codes(bs_xbrl, date=q3, period_type="as_of", account_codes=bs_codes, symbols=symbols)
    cf_q3 = build_cashflow_single_quarter(cf_xbrl, q2=q2, q3=q3, account_codes=cf_codes, symbols=symbols)

    x = inc_q3.merge(bs_q3, on="symbol", how="outer").merge(cf_q3, on="symbol", how="outer")
    if x.empty:
        return pd.DataFrame(
            columns=[
                "symbol",
                "xbrl_gross_margin_q",
                "xbrl_op_margin_q",
                "xbrl_rd_ratio_q",
                "xbrl_tax_rate_q",
                "xbrl_current_ratio",
                "xbrl_cash_to_assets",
                "xbrl_cfo_to_ni_q",
                "xbrl_capex_to_revenue_q",
            ]
        )

    x["xbrl_gross_margin_q"] = safe_div_positive(x["5900"], x["4000"])
    x["xbrl_op_margin_q"] = safe_div_positive(x["6900"], x["4000"])
    x["xbrl_rd_ratio_q"] = safe_div_positive(x["6300"], x["4000"])
    x["xbrl_tax_rate_q"] = safe_div_positive(x["7950"], x["7900"]).clip(0, 1)
    x["xbrl_current_ratio"] = safe_div_positive(x["11XX"], x["21XX"]).clip(0, 20)
    x["xbrl_cash_to_assets"] = safe_div_positive(x["1100"], x["1XXX"]).clip(0, 1)
    x["xbrl_cfo_to_ni_q"] = safe_div_positive(x["AAAA"], x["8200"]).clip(-10, 10)
    x["xbrl_capex_to_revenue_q"] = safe_div_positive(x["B02700"].abs(), x["4000"]).clip(0, 10)

    feature_cols = [
        "xbrl_gross_margin_q",
        "xbrl_op_margin_q",
        "xbrl_rd_ratio_q",
        "xbrl_tax_rate_q",
        "xbrl_current_ratio",
        "xbrl_cash_to_assets",
        "xbrl_cfo_to_ni_q",
        "xbrl_capex_to_revenue_q",
    ]
    return x[["symbol"] + feature_cols]


def fetch_one_year_api(api_base: str, year: int, market: str) -> pd.DataFrame:
    q2, q3, q4 = f"{year}Q2", f"{year}Q3", f"{year}Q4"
    lyq4, lyq3 = f"{year-1}Q4", f"{year-1}Q3"
    
    m9, m10 = f"{year}M09", f"{year}M10"
    ly_m9, ly_m10 = f"{year-1}M09", f"{year-1}M10"
    
    cutoff = f"{year}-11-15"

    inc_q3 = fetch_all_rows_api(api_base, "/raw/income-statements", {"start_date": q3, "end_date": q3, "market": market})
    inc_q2 = fetch_all_rows_api(api_base, "/raw/income-statements", {"start_date": q2, "end_date": q2, "market": market})
    bs_q3 = fetch_all_rows_api(api_base, "/raw/balance-sheets", {"start_date": q3, "end_date": q3, "market": market})
    cf_q3 = fetch_all_rows_api(api_base, "/raw/cash-flows", {"start_date": q3, "end_date": q3, "market": market})
    # target eps is q4 here, and history needs lyq4, lyq3, q2
    qr = fetch_all_rows_api(api_base, "/raw/quarterly-reports", {"start_date": lyq3, "end_date": q4, "market": market})
    mr = fetch_all_rows_api(api_base, "/raw/monthly-revenue", {"start_date": ly_m9, "end_date": m10})

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

    q2_data = pd.DataFrame(columns=["symbol", "q2_margin", "q2_rev", "q2_ni"])
    if not inc_q2.empty:
        q2_data = inc_q2[["symbol", "revenue_q", "net_income_q"]].copy()
        q2_data = q2_data.rename(columns={"revenue_q": "q2_rev", "net_income_q": "q2_ni"})
        q2_data["q2_margin"] = safe_div_positive(q2_data["q2_ni"], q2_data["q2_rev"])
        q2_data = q2_data[["symbol", "q2_margin", "q2_rev", "q2_ni"]]

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

    eps_hist = pd.DataFrame(columns=["symbol", "target_eps", "ly_q4_eps", "ly_q3_eps", "q2_eps", "q3_eps_official"])
    if not qr.empty:
        qr2 = qr[qr["date"].isin([q4, lyq4, lyq3, q2, q3])].copy()
        p = qr2.pivot_table(index="symbol", columns="date", values="eps_q", aggfunc="last").reset_index()
        eps_hist = p.rename(columns={q4: "target_eps", lyq4: "ly_q4_eps", lyq3: "ly_q3_eps", q2: "q2_eps", q3: "q3_eps_official"})
        for c in ["target_eps", "ly_q4_eps", "ly_q3_eps", "q2_eps", "q3_eps_official"]:
            if c not in eps_hist.columns:
                eps_hist[c] = np.nan
        eps_hist = eps_hist[["symbol", "target_eps", "ly_q4_eps", "ly_q3_eps", "q2_eps", "q3_eps_official"]]

    out = q3_data.merge(q2_data, on="symbol", how="left")
    out = out.merge(this_monthly, on="symbol", how="inner")
    out = out.merge(eps_hist, on="symbol", how="inner")

    # XBRL details: add richer statement structure and convert cash-flow accumulated -> single quarter.
    symbol_universe = set(out["symbol"].astype(str).unique())
    try:
        inc_xbrl = fetch_all_rows_api(
            api_base,
            "/raw/income-statements-xbrl",
            {"start_date": q2, "end_date": q3},
        )
        bs_xbrl = fetch_all_rows_api(
            api_base,
            "/raw/balance-sheets-xbrl",
            {"start_date": q3, "end_date": q3},
        )
        cf_xbrl = fetch_all_rows_api(
            api_base,
            "/raw/cash-flows-xbrl",
            {"start_date": q2, "end_date": q3},
        )
        xbrl_features = build_xbrl_feature_frame(
            inc_xbrl,
            bs_xbrl,
            cf_xbrl,
            q2=q2,
            q3=q3,
            symbols=symbol_universe,
        )
        out = out.merge(xbrl_features, on="symbol", how="left")
    except Exception as e:
        print(f"[WARN] skip XBRL feature merge (api) year={year} market={market}: {e}")

    out["year"] = year
    out["feature_cutoff_date"] = cutoff
    return out


def fetch_one_year(conn, year: int, market: str) -> pd.DataFrame:
    q2, q3, q4 = f"{year}Q2", f"{year}Q3", f"{year}Q4"
    lyq4, lyq3 = f"{year-1}Q4", f"{year-1}Q3"
    
    m9, m10 = f"{year}M09", f"{year}M10"
    ly_m9, ly_m10 = f"{year-1}M09", f"{year-1}M10"
    
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
      SELECT
        symbol,
        revenue_q AS q2_rev,
        net_income_q AS q2_ni,
        CASE WHEN revenue_q > 0 THEN net_income_q/revenue_q END AS q2_margin
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
             (SELECT eps_q FROM quarterly_reports WHERE symbol=qr.symbol AND date='{q2}' AND market='{market}') AS q2_eps,
             (SELECT eps_q FROM quarterly_reports WHERE symbol=qr.symbol AND date='{q3}' AND market='{market}') AS q3_eps_official
      FROM quarterly_reports qr WHERE qr.date='{q4}' AND qr.market='{market}'
    )
    SELECT {year} AS year, '{cutoff}' AS feature_cutoff_date, q3.*, q2.q2_margin, q2.q2_rev, q2.q2_ni,
           m.rev_m9,m.rev_m10,m.rev_m9_ly,m.rev_m10_ly,
           e.target_eps,e.ly_q4_eps,e.ly_q3_eps,e.q2_eps,e.q3_eps_official
    FROM q3_data q3
    LEFT JOIN q2_data q2 ON q3.symbol=q2.symbol
    JOIN this_monthly m ON q3.symbol=m.symbol
    JOIN eps_hist e ON q3.symbol=e.symbol
    """
    out = pd.read_sql(sql, conn)

    # XBRL details: add richer statement structure and convert cash-flow accumulated -> single quarter.
    symbol_universe = set(out["symbol"].astype(str).unique())
    try:
        inc_xbrl = pd.read_sql(
            f"""
            SELECT * FROM income_statement_xbrl
            WHERE date IN ('{q2}','{q3}')
              AND symbol IN (SELECT symbol FROM stock_info WHERE market = '{market}')
            """,
            conn,
        )
        bs_xbrl = pd.read_sql(
            f"""
            SELECT * FROM balance_sheet_xbrl
            WHERE date = '{q3}'
              AND symbol IN (SELECT symbol FROM stock_info WHERE market = '{market}')
            """,
            conn,
        )
        cf_xbrl = pd.read_sql(
            f"""
            SELECT * FROM cash_flow_xbrl
            WHERE date IN ('{q2}','{q3}')
              AND symbol IN (SELECT symbol FROM stock_info WHERE market = '{market}')
            """,
            conn,
        )
        xbrl_features = build_xbrl_feature_frame(
            inc_xbrl,
            bs_xbrl,
            cf_xbrl,
            q2=q2,
            q3=q3,
            symbols=symbol_universe,
        )
        out = out.merge(xbrl_features, on="symbol", how="left")
    except Exception as e:
        print(f"[WARN] skip XBRL feature merge (db) year={year} market={market}: {e}")

    return out


def main() -> None:
    args = parse_args()
    if args.start_year > args.end_year:
        raise ValueError("start-year must be <= end-year")
    fetch_years = list(range(args.start_year, args.end_year + 1))

    frames = []
    if args.data_source == "db":
        engine = create_engine(get_db_url())
        with engine.connect() as conn:
            conn.execute(text("SET max_parallel_workers_per_gather = 0"))
            for year in fetch_years:
                print(f"fetching v10(11) data from db: year={year}, market={args.market}")
                y = fetch_one_year(conn, year, args.market)
                if not y.empty:
                    frames.append(y)
            try:
                industry_df = pd.read_sql(f"SELECT symbol, industry FROM stock_info WHERE market = '{args.market}'", conn)
            except Exception:
                industry_df = pd.DataFrame(columns=["symbol", "industry"])
    else:
        for year in fetch_years:
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

    df = df.replace([np.inf, -np.inf], np.nan)
    
    # Use published Q3 EPS as anchor for Q4/full-year target construction.
    df["anchor_eps"] = df["q3_eps"]

    df["q2_margin"] = safe_div_positive(safe_col(df, "q2_ni"), safe_col(df, "q2_rev"))
    df["q3_margin"] = safe_div_positive(df["q3_ni"], df["q3_rev"])
    df["q3_ocf_ratio"] = safe_div_positive(df["q3_ocf"], df["q3_ni"]).clip(-5, 5)
    df["q3_re_ratio"] = safe_div_positive(df["q3_retained_earnings"], df["capital"])
    df["margin_momentum"] = df["q3_margin"] - df["q2_margin"]

    df["rev_yoy_m10"] = safe_div_positive(df["rev_m10"], df["rev_m10_ly"]) - 1
    df["rev_mom_m10_m9"] = safe_div_positive(df["rev_m10"], df["rev_m9"]) - 1

    add_industry_zscore(df, "rev_yoy_m10", "rev_yoy_m10_z")
    add_industry_zscore(df, "rev_mom_m10_m9", "rev_mom_m10_m9_z")

    # Use quantile features consistently across pipeline versions.
    add_cross_section_quantile(df, "rev_yoy_m10_z", "rev_yoy_m10_quantile")
    add_cross_section_quantile(df, "rev_mom_m10_m9_z", "rev_mom_m10_m9_quantile")

    # Company-level seasonality: last year's Q4/Q3 EPS ratio.
    df["ly_seasonality"] = safe_div_positive(df["ly_q4_eps"], df["ly_q3_eps"]).clip(-5, 5)
    df["q3_yoy_eps"] = (safe_div_positive(df["q3_eps"], df["ly_q3_eps"]) - 1).clip(-5, 5)

    df[TARGET_DELTA] = df[TARGET] - df["anchor_eps"]
    
    rows_before_filter = len(df)
    if args.apply_trading_filter:
        ttm_eps_proxy = (
            safe_col(df, "ly_q4_eps").fillna(0)
            + safe_col(df, "q2_eps").fillna(0)
            + safe_col(df, "q3_eps_official").fillna(0)
        )
        ttm_ok = ttm_eps_proxy >= float(args.min_ttm_eps)
        df = df[ttm_ok].copy()

    labeled_mask = (
        df[TARGET].notna()
        & df["anchor_eps"].notna()
        & df[TARGET_DELTA].notna()
    )

    evaluate_cols = [c for c in EVALUATE_COLUMNS if c in df.columns]
    out = df[evaluate_cols].copy()
    out["year"] = out["year"].astype(int)

    out_labeled = out.loc[labeled_mask].copy()
    out_labeled = out_labeled[out_labeled["year"].astype(int) <= int(args.end_year)].copy()

    train_cols = [c for c in TRAIN_COLUMNS if c in out_labeled.columns]
    out_train = out_labeled[train_cols].copy()

    evaluate_labeled_cols = [c for c in EVALUATE_COLUMNS if c in out_labeled.columns]
    out_debug = out_labeled[evaluate_labeled_cols].copy()

    args.output_train.parent.mkdir(parents=True, exist_ok=True)
    out_train.to_csv(args.output_train, index=False)
    args.output_evaluate.parent.mkdir(parents=True, exist_ok=True)
    out_debug.to_csv(args.output_evaluate, index=False)

    print("v10(11) prepare_data completed")
    print(f"- data_source: {args.data_source}")
    if args.data_source == "api":
        print(f"- api_base: {args.api_base}")
    print(f"- output_train: {args.output_train}")
    print(f"- output_evaluate: {args.output_evaluate}")
    print(f"- apply_trading_filter: {args.apply_trading_filter}")
    if args.apply_trading_filter:
        print(f"- min_ttm_eps: {args.min_ttm_eps}")
        print(f"- rows_before_filter: {rows_before_filter}")
    print(f"- rows_labeled: {len(out_debug)}")


if __name__ == "__main__":
    main()
