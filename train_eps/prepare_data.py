from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Optional, Set

import numpy as np
import pandas as pd
import requests
from sqlalchemy import create_engine, text

TARGET = "target_eps"
TARGET_DELTA = "delta_eps"
CONTEXT_COLUMNS = ["symbol", "name", "industry"]
MIN_TTM_EPS = 1.0
API_BASE = os.getenv("BACKEND_API_BASE", "http://100.103.191.79:8000")
MARKETS = ("sii", "otc")
START_YEAR = 2020
APPLY_TRADING_FILTER = True


def get_db_url() -> str:
    return "postgresql://user:password@localhost:5432/stock_db"


def normalize_month(month: str) -> str:
    m = str(month).zfill(2)
    if m not in {"11", "12", "01"}:
        raise ValueError("--month 目前僅支援 11/12/01")
    return m


def model_features_for_month(month: str) -> list[str]:
    common = [
        "anchor_eps",  # Published Q3 EPS used as anchor
        "ly_q4_eps",  # Last-year full-year EPS (Q4)
        "q3_yoy_eps",  # Q3 EPS year-over-year growth
        "q3_margin",  # Q3 net income margin
        "q3_ocf_ratio",  # Q3 operating cash flow to net income ratio
        "q3_re_ratio",  # Q3 retained earnings to capital ratio
        "margin_momentum",  # Q3 margin minus Q2 margin
        "q3_roe",  # Q3 return on equity
        "q3_debt_ratio",  # Q3 debt-to-assets ratio
        "q3_non_op_ratio",  # Q3 non-operating income to pre-tax income ratio
        "ly_seasonality",  # Last-year Q4/Q3 EPS seasonality ratio
        "xbrl_gross_margin_q",  # XBRL gross margin (single quarter)
        "xbrl_op_margin_q",  # XBRL operating margin (single quarter)
        "xbrl_rd_ratio_q",  # XBRL R&D expense to revenue ratio (single quarter)
        "xbrl_tax_rate_q",  # XBRL effective tax rate (single quarter)
        "xbrl_current_ratio",  # XBRL current ratio
        "xbrl_cash_to_assets",  # XBRL cash to total assets ratio
        "xbrl_cfo_to_ni_q",  # XBRL operating cash flow to net income ratio (single quarter)
        "xbrl_capex_to_revenue_q",  # XBRL capex to revenue ratio (single quarter)
    ]

    if month == "11":
        monthly = [
            "rev_yoy_m10_quantile",  # Industry-relative YoY revenue growth quantile at M10
            "rev_mom_m10_m9_quantile",  # Industry-relative MoM revenue growth quantile (M10 vs M9)
        ]
    elif month == "12":
        monthly = [
            "rev_yoy_m10_quantile",  # Industry-relative YoY revenue growth quantile at M10
            "rev_mom_m10_m9_quantile",  # Industry-relative MoM revenue growth quantile (M10 vs M9)
            "rev_yoy_m11_quantile",  # Industry-relative YoY revenue growth quantile at M11
            "rev_mom_m11_m10_quantile",  # Industry-relative MoM revenue growth quantile (M11 vs M10)
        ]
    else:  # month == "01"
        monthly = [
            "rev_yoy_m11_quantile",  # Industry-relative YoY revenue growth quantile at M11
            "rev_mom_m11_m10_quantile",  # Industry-relative MoM revenue growth quantile (M11 vs M10)
            "rev_yoy_m12_quantile",  # Industry-relative YoY revenue growth quantile at M12
            "rev_mom_m12_m11_quantile",  # Industry-relative MoM revenue growth quantile (M12 vs M11)
        ]

    return [
        common[0],
        common[1],
        common[2],
        common[3],
        common[4],
        common[5],
        *monthly,
        *common[6:],
    ]


def monthly_context(year: int, month: str) -> dict:
    if month == "11":
        m9, m10 = f"{year}M09", f"{year}M10"
        ly_m9, ly_m10 = f"{year-1}M09", f"{year-1}M10"
        return {
            "mr_dates": [m9, m10, ly_m9, ly_m10],
            "mr_start": ly_m9,
            "mr_end": m10,
            "month_cols": ["rev_m9", "rev_m10", "rev_m9_ly", "rev_m10_ly"],
            "rename_map": {m9: "rev_m9", m10: "rev_m10", ly_m9: "rev_m9_ly", ly_m10: "rev_m10_ly"},
            "sql_exprs": [
                f"MAX(CASE WHEN date='{m9}' THEN revenue_current END) AS rev_m9",
                f"MAX(CASE WHEN date='{m10}' THEN revenue_current END) AS rev_m10",
                f"MAX(CASE WHEN date='{ly_m9}' THEN revenue_current END) AS rev_m9_ly",
                f"MAX(CASE WHEN date='{ly_m10}' THEN revenue_current END) AS rev_m10_ly",
            ],
            "feature_mode": "11",
        }
    if month == "12":
        m9, m10, m11 = f"{year}M09", f"{year}M10", f"{year}M11"
        ly_m10, ly_m11 = f"{year-1}M10", f"{year-1}M11"
        return {
            "mr_dates": [m9, m10, m11, ly_m10, ly_m11],
            "mr_start": ly_m10,
            "mr_end": m11,
            "month_cols": ["rev_m9", "rev_m10", "rev_m11", "rev_m10_ly", "rev_m11_ly"],
            "rename_map": {
                m9: "rev_m9",
                m10: "rev_m10",
                m11: "rev_m11",
                ly_m10: "rev_m10_ly",
                ly_m11: "rev_m11_ly",
            },
            "sql_exprs": [
                f"MAX(CASE WHEN date='{m9}' THEN revenue_current END) AS rev_m9",
                f"MAX(CASE WHEN date='{m10}' THEN revenue_current END) AS rev_m10",
                f"MAX(CASE WHEN date='{m11}' THEN revenue_current END) AS rev_m11",
                f"MAX(CASE WHEN date='{ly_m10}' THEN revenue_current END) AS rev_m10_ly",
                f"MAX(CASE WHEN date='{ly_m11}' THEN revenue_current END) AS rev_m11_ly",
            ],
            "feature_mode": "12",
        }

    m10, m11, m12 = f"{year}M10", f"{year}M11", f"{year}M12"
    ly_m11, ly_m12 = f"{year-1}M11", f"{year-1}M12"
    return {
        "mr_dates": [m10, m11, m12, ly_m11, ly_m12],
        "mr_start": ly_m11,
        "mr_end": m12,
        "month_cols": ["rev_m10", "rev_m11", "rev_m12", "rev_m11_ly", "rev_m12_ly"],
        "rename_map": {
            m10: "rev_m10",
            m11: "rev_m11",
            m12: "rev_m12",
            ly_m11: "rev_m11_ly",
            ly_m12: "rev_m12_ly",
        },
        "sql_exprs": [
            f"MAX(CASE WHEN date='{m10}' THEN revenue_current END) AS rev_m10",
            f"MAX(CASE WHEN date='{m11}' THEN revenue_current END) AS rev_m11",
            f"MAX(CASE WHEN date='{m12}' THEN revenue_current END) AS rev_m12",
            f"MAX(CASE WHEN date='{ly_m11}' THEN revenue_current END) AS rev_m11_ly",
            f"MAX(CASE WHEN date='{ly_m12}' THEN revenue_current END) AS rev_m12_ly",
        ],
        "feature_mode": "01",
    }


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Shared prepare dataset from DB/API")
    p.add_argument("--year", type=int, required=True)
    p.add_argument("--month", type=str, required=True, help="11/12/01")
    p.add_argument("--data-source", type=str, choices=["db", "api"], default="db")
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
    if col not in df.columns:
        raise KeyError(f"Required column missing: {col}")
    return df[col]


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


def fetch_one_year_api(api_base: str, year: int, market: str, month: str) -> pd.DataFrame:
    q2, q3, q4 = f"{year}Q2", f"{year}Q3", f"{year}Q4"
    lyq4, lyq3 = f"{year-1}Q4", f"{year-1}Q3"
    mctx = monthly_context(year, month)

    inc_q3 = fetch_all_rows_api(api_base, "/raw/income-statements", {"start_date": q3, "end_date": q3, "market": market})
    inc_q2 = fetch_all_rows_api(api_base, "/raw/income-statements", {"start_date": q2, "end_date": q2, "market": market})
    bs_q3 = fetch_all_rows_api(api_base, "/raw/balance-sheets", {"start_date": q3, "end_date": q3, "market": market})
    cf_q3 = fetch_all_rows_api(api_base, "/raw/cash-flows", {"start_date": q3, "end_date": q3, "market": market})
    qr = fetch_all_rows_api(api_base, "/raw/quarterly-reports", {"start_date": lyq3, "end_date": q4, "market": market})
    mr = fetch_all_rows_api(api_base, "/raw/monthly-revenue", {"start_date": mctx["mr_start"], "end_date": mctx["mr_end"]})

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
    q3_data["q3_margin"] = safe_col(q3_data, "q3_ni") / safe_col(q3_data, "q3_rev").replace(0, np.nan)
    q3_data["q3_non_op_ratio"] = safe_col(q3_data, "non_operating_income_q") / safe_col(q3_data, "pretax_income_q").replace(0, np.nan)
    q3_data["q3_roe"] = safe_col(q3_data, "q3_ni") / safe_col(q3_data, "total_equity").replace(0, np.nan)
    q3_data["q3_debt_ratio"] = safe_col(q3_data, "total_liabilities") / safe_col(q3_data, "total_assets").replace(0, np.nan)
    q3_data = q3_data[["symbol", "name", "q3_rev", "q3_ni", "q3_margin", "q3_non_op_ratio", "q3_roe", "q3_debt_ratio", "capital", "q3_retained_earnings", "q3_ocf"]]

    q2_data = pd.DataFrame(columns=["symbol", "q2_margin", "q2_rev", "q2_ni"])
    if not inc_q2.empty:
        q2_data = inc_q2[["symbol", "revenue_q", "net_income_q"]].copy()
        q2_data = q2_data.rename(columns={"revenue_q": "q2_rev", "net_income_q": "q2_ni"})
        q2_data["q2_margin"] = safe_div_positive(q2_data["q2_ni"], q2_data["q2_rev"])
        q2_data = q2_data[["symbol", "q2_margin", "q2_rev", "q2_ni"]]

    this_monthly = pd.DataFrame(columns=["symbol"] + mctx["month_cols"])
    if not mr.empty:
        if "market" in mr.columns:
            mr = mr[mr["market"].astype(str).str.upper() == market.upper()].copy()
        mr2 = mr[mr["date"].isin(mctx["mr_dates"])].copy()
        if not mr2.empty:
            pvt = mr2.pivot_table(index="symbol", columns="date", values="revenue_current", aggfunc="last").reset_index()
            this_monthly = pvt.rename(columns=mctx["rename_map"])
            for c in mctx["month_cols"]:
                if c not in this_monthly.columns:
                    this_monthly[c] = np.nan
            this_monthly = this_monthly[["symbol"] + mctx["month_cols"]]

    eps_hist = pd.DataFrame(columns=["symbol", "target_eps", "ly_q4_eps", "ly_q3_eps", "q2_eps", "q3_eps"])
    if not qr.empty:
        qr2 = qr[qr["date"].isin([q4, lyq4, lyq3, q2, q3])].copy()
        p = qr2.pivot_table(index="symbol", columns="date", values="eps_q", aggfunc="last").reset_index()
        eps_hist = p.rename(columns={q4: "target_eps", lyq4: "ly_q4_eps", lyq3: "ly_q3_eps", q2: "q2_eps", q3: "q3_eps"})
        for c in ["target_eps", "ly_q4_eps", "ly_q3_eps", "q2_eps", "q3_eps"]:
            if c not in eps_hist.columns:
                eps_hist[c] = np.nan
        eps_hist = eps_hist[["symbol", "target_eps", "ly_q4_eps", "ly_q3_eps", "q2_eps", "q3_eps"]]

    out = q3_data.merge(q2_data, on="symbol", how="left")
    out = out.merge(this_monthly, on="symbol", how="inner")
    out = out.merge(eps_hist, on="symbol", how="inner")

    symbol_universe = set(out["symbol"].astype(str).unique())
    try:
        inc_xbrl = fetch_all_rows_api(api_base, "/raw/income-statements-xbrl", {"start_date": q2, "end_date": q3})
        bs_xbrl = fetch_all_rows_api(api_base, "/raw/balance-sheets-xbrl", {"start_date": q3, "end_date": q3})
        cf_xbrl = fetch_all_rows_api(api_base, "/raw/cash-flows-xbrl", {"start_date": q2, "end_date": q3})
        xbrl_features = build_xbrl_feature_frame(inc_xbrl, bs_xbrl, cf_xbrl, q2=q2, q3=q3, symbols=symbol_universe)
        out = out.merge(xbrl_features, on="symbol", how="left")
    except Exception as e:
        print(f"[WARN] skip XBRL feature merge (api) year={year} market={market}: {e}")

    out["year"] = year
    return out


def fetch_one_year(conn, year: int, market: str, month: str) -> pd.DataFrame:
    q2, q3, q4 = f"{year}Q2", f"{year}Q3", f"{year}Q4"
    lyq4, lyq3 = f"{year-1}Q4", f"{year-1}Q3"
    mctx = monthly_context(year, month)

    sql = f"""
    WITH q3_data AS (
      SELECT i.symbol, i.name, i.revenue_q AS q3_rev, i.net_income_q AS q3_ni,
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
             {','.join(mctx['sql_exprs'])}
      FROM monthly_revenue
      WHERE date IN ({','.join([f"'{d}'" for d in mctx['mr_dates']])})
      GROUP BY symbol
    ),
    eps_hist AS (
      SELECT qr.symbol, qr.eps_q AS target_eps,
             (SELECT eps_q FROM quarterly_reports WHERE symbol=qr.symbol AND date='{lyq4}' AND market='{market}') AS ly_q4_eps,
             (SELECT eps_q FROM quarterly_reports WHERE symbol=qr.symbol AND date='{lyq3}' AND market='{market}') AS ly_q3_eps,
             (SELECT eps_q FROM quarterly_reports WHERE symbol=qr.symbol AND date='{q2}' AND market='{market}') AS q2_eps,
             (SELECT eps_q FROM quarterly_reports WHERE symbol=qr.symbol AND date='{q3}' AND market='{market}') AS q3_eps
      FROM quarterly_reports qr WHERE qr.date='{q4}' AND qr.market='{market}'
    )
    SELECT {year} AS year, q3.*, q2.q2_margin, q2.q2_rev, q2.q2_ni,
           {','.join([f'm.{c}' for c in mctx['month_cols']])},
           e.target_eps,e.ly_q4_eps,e.ly_q3_eps,e.q2_eps,e.q3_eps
    FROM q3_data q3
    LEFT JOIN q2_data q2 ON q3.symbol=q2.symbol
    JOIN this_monthly m ON q3.symbol=m.symbol
    JOIN eps_hist e ON q3.symbol=e.symbol
    """
    out = pd.read_sql(sql, conn)

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
        xbrl_features = build_xbrl_feature_frame(inc_xbrl, bs_xbrl, cf_xbrl, q2=q2, q3=q3, symbols=symbol_universe)
        out = out.merge(xbrl_features, on="symbol", how="left")
    except Exception as e:
        print(f"[WARN] skip XBRL feature merge (db) year={year} market={market}: {e}")

    return out


def add_month_features(df: pd.DataFrame, month: str) -> None:
    if month == "11":
        df["rev_yoy_m10"] = safe_div_positive(df["rev_m10"], df["rev_m10_ly"]) - 1
        df["rev_mom_m10_m9"] = safe_div_positive(df["rev_m10"], df["rev_m9"]) - 1
        add_industry_zscore(df, "rev_yoy_m10", "rev_yoy_m10_z")
        add_industry_zscore(df, "rev_mom_m10_m9", "rev_mom_m10_m9_z")
        add_cross_section_quantile(df, "rev_yoy_m10_z", "rev_yoy_m10_quantile")
        add_cross_section_quantile(df, "rev_mom_m10_m9_z", "rev_mom_m10_m9_quantile")
        return

    if month == "12":
        df["rev_yoy_m10"] = safe_div_positive(df["rev_m10"], df["rev_m10_ly"]) - 1
        df["rev_mom_m10_m9"] = safe_div_positive(df["rev_m10"], df["rev_m9"]) - 1
        df["rev_yoy_m11"] = safe_div_positive(df["rev_m11"], df["rev_m11_ly"]) - 1
        df["rev_mom_m11_m10"] = safe_div_positive(df["rev_m11"], df["rev_m10"]) - 1
        add_industry_zscore(df, "rev_yoy_m10", "rev_yoy_m10_z")
        add_industry_zscore(df, "rev_mom_m10_m9", "rev_mom_m10_m9_z")
        add_industry_zscore(df, "rev_yoy_m11", "rev_yoy_m11_z")
        add_industry_zscore(df, "rev_mom_m11_m10", "rev_mom_m11_m10_z")
        add_cross_section_quantile(df, "rev_yoy_m10_z", "rev_yoy_m10_quantile")
        add_cross_section_quantile(df, "rev_mom_m10_m9_z", "rev_mom_m10_m9_quantile")
        add_cross_section_quantile(df, "rev_yoy_m11_z", "rev_yoy_m11_quantile")
        add_cross_section_quantile(df, "rev_mom_m11_m10_z", "rev_mom_m11_m10_quantile")
        return

    df["rev_yoy_m11"] = safe_div_positive(df["rev_m11"], df["rev_m11_ly"]) - 1
    df["rev_mom_m11_m10"] = safe_div_positive(df["rev_m11"], df["rev_m10"]) - 1
    df["rev_yoy_m12"] = safe_div_positive(df["rev_m12"], df["rev_m12_ly"]) - 1
    df["rev_mom_m12_m11"] = safe_div_positive(df["rev_m12"], df["rev_m11"]) - 1
    add_industry_zscore(df, "rev_yoy_m11", "rev_yoy_m11_z")
    add_industry_zscore(df, "rev_mom_m11_m10", "rev_mom_m11_m10_z")
    add_industry_zscore(df, "rev_yoy_m12", "rev_yoy_m12_z")
    add_industry_zscore(df, "rev_mom_m12_m11", "rev_mom_m12_m11_z")
    add_cross_section_quantile(df, "rev_yoy_m11_z", "rev_yoy_m11_quantile")
    add_cross_section_quantile(df, "rev_mom_m11_m10_z", "rev_mom_m11_m10_quantile")
    add_cross_section_quantile(df, "rev_yoy_m12_z", "rev_yoy_m12_quantile")
    add_cross_section_quantile(df, "rev_mom_m12_m11_z", "rev_mom_m12_m11_quantile")


def main() -> None:
    args = parse_args()
    month = normalize_month(args.month)
    end_year = int(args.year)
    model_features = model_features_for_month(month)

    month_dir = (Path(__file__).resolve().parent / "output" / str(end_year) / month).resolve()
    output_train = month_dir / "dataset_train.csv"
    output_evaluate = month_dir / "dataset_evaluate.csv"

    train_columns = ["year"] + model_features + [TARGET, TARGET_DELTA]
    evaluate_columns = CONTEXT_COLUMNS + ["year"] + model_features + [TARGET, TARGET_DELTA]

    fetch_years = list(range(START_YEAR, end_year + 1))
    frames: list[pd.DataFrame] = []

    if args.data_source == "db":
        engine = create_engine(get_db_url())
        with engine.connect() as conn:
            conn.execute(text("SET max_parallel_workers_per_gather = 0"))
            for year in fetch_years:
                for market in MARKETS:
                    print(f"fetching data from db: year={year}, market={market}, month={month}")
                    y = fetch_one_year(conn, year, market, month)
                    if not y.empty:
                        frames.append(y)
            industry_parts: list[pd.DataFrame] = []
            for market in MARKETS:
                part = pd.read_sql(f"SELECT symbol, industry FROM stock_info WHERE market = '{market}'", conn)
                if not part.empty:
                    industry_parts.append(part[["symbol", "industry"]])
    else:
        for year in fetch_years:
            for market in MARKETS:
                print(f"fetching data from api: year={year}, market={market}, month={month}")
                y = fetch_one_year_api(API_BASE, year, market, month)
                if not y.empty:
                    frames.append(y)
        industry_parts = []
        for market in MARKETS:
            part = fetch_all_rows_api(API_BASE, "/raw/stock-info", {"market": market})
            if not part.empty and "symbol" in part.columns:
                if "industry" not in part.columns:
                    part["industry"] = np.nan
                industry_parts.append(part[["symbol", "industry"]])

    if not industry_parts:
        industry_df = pd.DataFrame(columns=["symbol", "industry"])
    else:
        industry_df = pd.concat(industry_parts, ignore_index=True).drop_duplicates("symbol")

    if not frames:
        raise RuntimeError("No data fetched. Check data source settings and year range.")

    df = pd.concat(frames, ignore_index=True)
    if not industry_df.empty:
        df = df.merge(industry_df, on="symbol", how="left")
    df["industry"] = df.get("industry", pd.Series(index=df.index)).fillna("unknown")
    df = df.replace([np.inf, -np.inf], np.nan)

    df["anchor_eps"] = df["q3_eps"]
    df["q2_margin"] = safe_div_positive(safe_col(df, "q2_ni"), safe_col(df, "q2_rev"))
    df["q3_margin"] = safe_div_positive(df["q3_ni"], df["q3_rev"])
    df["q3_ocf_ratio"] = safe_div_positive(df["q3_ocf"], df["q3_ni"]).clip(-5, 5)
    df["q3_re_ratio"] = safe_div_positive(df["q3_retained_earnings"], df["capital"])
    df["margin_momentum"] = df["q3_margin"] - df["q2_margin"]

    add_month_features(df, month)

    df["ly_seasonality"] = safe_div_positive(df["ly_q4_eps"], df["ly_q3_eps"]).clip(-5, 5)
    df["q3_yoy_eps"] = (safe_div_positive(df["q3_eps"], df["ly_q3_eps"]) - 1).clip(-5, 5)
    df[TARGET_DELTA] = df[TARGET] - df["anchor_eps"]

    rows_before_filter = len(df)
    ttm_eps_proxy = safe_col(df, "ly_q4_eps").fillna(0) + safe_col(df, "q2_eps").fillna(0) + safe_col(df, "q3_eps").fillna(0)
    ttm_ok = ttm_eps_proxy >= float(MIN_TTM_EPS)
    df = df[ttm_ok].copy()
    rows_after_filter = len(df)

    labeled_mask = df[TARGET].notna() & df["anchor_eps"].notna() & df[TARGET_DELTA].notna()

    evaluate_cols = [c for c in evaluate_columns if c in df.columns]
    out = df[evaluate_cols].copy()
    out["year"] = out["year"].astype(int)

    out_labeled = out.loc[labeled_mask].copy()
    out_labeled = out_labeled[out_labeled["year"].astype(int) <= end_year].copy()

    train_cols = [c for c in train_columns if c in out_labeled.columns]
    out_train = out_labeled[train_cols].copy()

    evaluate_labeled_cols = [c for c in evaluate_columns if c in out_labeled.columns]
    out_debug = out_labeled[evaluate_labeled_cols].copy()

    output_train.parent.mkdir(parents=True, exist_ok=True)
    out_train.to_csv(output_train, index=False)
    output_evaluate.parent.mkdir(parents=True, exist_ok=True)
    out_debug.to_csv(output_evaluate, index=False)

    print("prepare_data completed")
    print(f"- data_source: {args.data_source}")
    print(f"- month: {month}")
    print(f"- markets: {','.join(MARKETS)}")
    print(f"- years: {START_YEAR}~{end_year}")
    if args.data_source == "api":
        print(f"- api_base: {API_BASE}")
    print(f"- output_train: {output_train}")
    print(f"- output_evaluate: {output_evaluate}")
    print(f"- apply_trading_filter: {APPLY_TRADING_FILTER}")
    print(f"- min_ttm_eps: {MIN_TTM_EPS}")
    print(f"- rows_before_filter: {rows_before_filter}")
    print(f"- rows_after_filter: {rows_after_filter}")
    print(f"- rows_labeled: {len(out_debug)}")


if __name__ == "__main__":
    main()
