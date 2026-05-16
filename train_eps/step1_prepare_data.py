from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Optional, Set

import numpy as np
import pandas as pd
import requests
from shared_config import format_quarter, shift_quarter, target_quarter_for_playbook
from sqlalchemy import create_engine, text

TARGET = "target_eps"
TARGET_DELTA = "delta_eps"
CONTEXT_COLUMNS = ["symbol", "name", "industry"]
MIN_TTM_EPS = 1.0
API_BASE = os.getenv("BACKEND_API_BASE", "http://100.103.191.79:8000")
MARKETS = ("sii", "otc")
START_YEAR = 2020


def get_db_url() -> str:
    return "postgresql://user:password@localhost:5419/stock_db"


def normalize_month(month: str) -> str:
    m = str(month).zfill(2)
    if m < "01" or m > "12":
        raise ValueError("--month 必須是 01~12")
    return m


def month_shift(year: int, month: int, delta: int) -> tuple[int, int]:
    total = year * 12 + (month - 1) + delta
    return total // 12, (total % 12) + 1


def month_token(year: int, month: int) -> str:
    return f"{year}M{month:02d}"


def feature_months_for_calendar_month(month: str) -> list[int]:
    if month == "01":
        return [10, 11, 12]
    if month == "02":
        return [1]
    if month == "03":
        return [1, 2]
    if month == "04":
        return [1, 2, 3]
    if month == "05":
        return [4]
    if month == "06":
        return [4, 5]
    if month == "07":
        return [4, 5, 6]
    if month == "08":
        return [7]
    if month == "09":
        return [7, 8]
    if month == "10":
        return [7, 8, 9]
    if month == "11":
        return [10]
    if month == "12":
        return [10, 11]
    raise ValueError(f"Unsupported month: {month}")


def build_quarter_context(execution_year: int, month: str) -> dict:
    # Playbook 規則統一在 shared_config.target_quarter_for_playbook，這裡只負責
    # 由 (target_year, target_qnum) 推導 anchor / prev / 去年同期等季度字串。
    target_year, target_qnum = target_quarter_for_playbook(execution_year, month)
    anchor_y, anchor_qn = shift_quarter(target_year, target_qnum, -1)
    prev_y, prev_qn = shift_quarter(target_year, target_qnum, -2)

    return {
        "target_year": target_year,
        "target_q": format_quarter(target_year, target_qnum),
        "anchor_q": format_quarter(anchor_y, anchor_qn),
        "prev_q": format_quarter(prev_y, prev_qn),
        "ly_target_q": format_quarter(target_year - 1, target_qnum),
        "ly_anchor_q": format_quarter(anchor_y - 1, anchor_qn),
    }


def monthly_context(execution_year: int, month: str) -> dict:
    feature_months = feature_months_for_calendar_month(month)
    if not feature_months:
        raise ValueError(f"{month} 月暫不訓練")

    feature_year = execution_year - 1 if month == "01" else execution_year
    col_to_date: dict[str, str] = {}

    for m in feature_months:
        prev_y, prev_m = month_shift(feature_year, m, -1)
        prev_col = f"rev_m{prev_m:02d}"
        curr_col = f"rev_m{m:02d}"
        ly_col = f"rev_m{m:02d}_ly"
        col_to_date.setdefault(prev_col, month_token(prev_y, prev_m))
        col_to_date.setdefault(curr_col, month_token(feature_year, m))
        col_to_date.setdefault(ly_col, month_token(feature_year - 1, m))

    month_cols = list(col_to_date.keys())
    mr_dates = sorted(set(col_to_date.values()))
    date_to_col = {v: k for k, v in col_to_date.items()}
    sql_exprs = [
        f"MAX(CASE WHEN date='{d}' THEN revenue_current END) AS {date_to_col[d]}"
        for d in mr_dates
    ]

    return {
        "feature_months": feature_months,
        "month_cols": month_cols,
        "mr_dates": mr_dates,
        "mr_start": mr_dates[0],
        "mr_end": mr_dates[-1],
        "date_to_col": date_to_col,
        "sql_exprs": sql_exprs,
    }


def model_features_for_month(month: str) -> list[str]:
    common = [
        "anchor_eps",  # 錨點季度已公布每股盈餘
        "ly_target_eps",  # 去年同目標季度每股盈餘
        "anchor_yoy_eps",  # 錨點季度 EPS 年增率（錨點 vs 去年同季）
        "anchor_margin",  # 錨點季度淨利率
        "anchor_ocf_ratio",  # 錨點季度營業現金流對淨利比
        "anchor_re_ratio",  # 錨點季度保留盈餘對資本比
        "margin_momentum",  # 淨利率動能（錨點季度 - 前一季度）
        "anchor_roe",  # 錨點季度股東權益報酬率
        "anchor_debt_ratio",  # 錨點季度負債比率
        "anchor_non_op_ratio",  # 錨點季度業外損益占稅前淨利比
        "ly_seasonality",  # 去年季節性（目標季度 / 錨點季度 EPS）
        "xbrl_gross_margin_q",  # XBRL 單季毛利率
        "xbrl_op_margin_q",  # XBRL 單季營業利益率
        "xbrl_rd_ratio_q",  # XBRL 單季研發費用率
        "xbrl_tax_rate_q",  # XBRL 單季有效稅率
        "xbrl_current_ratio",  # XBRL 流動比率
        "xbrl_cash_to_assets",  # XBRL 現金資產比
        "xbrl_cfo_to_ni_q",  # XBRL 單季營業現金流對淨利比
        "xbrl_capex_to_revenue_q",  # XBRL 單季資本支出對營收比
    ]

    monthly: list[str] = []
    for m in feature_months_for_calendar_month(month):
        _, prev_m = month_shift(2000, m, -1)
        monthly.append(f"rev_yoy_m{m:02d}_quantile")
        monthly.append(f"rev_mom_m{m:02d}_m{prev_m}_quantile")

    return [*common[:6], *monthly, *common[6:]]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Shared prepare dataset from DB/API")
    p.add_argument("--year", type=int, required=True)
    p.add_argument("--month", type=str, required=True, help="01~12")
    p.add_argument("--data-source", type=str, choices=["db", "api"], default="db")
    return p.parse_args()


def add_industry_zscore(df: pd.DataFrame, col: str, out_col: str) -> None:
    g = df.groupby(["year", "industry"])[col]
    mean = g.transform("mean")
    std = g.transform("std").replace(0, np.nan)
    # 保留缺失值供下游模型處理，不填補為 0。
    df[out_col] = ((df[col] - mean) / std).replace([np.inf, -np.inf], np.nan)


def add_cross_section_quantile(df: pd.DataFrame, z_col: str, out_col: str) -> None:
    group_cols = ["year", "industry"]
    # z-score 缺失時保留 NaN，不轉換為固定中位分位數。
    ranks = df.groupby(group_cols)[z_col].rank(method="average", pct=True)
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


def fetch_all_rows_api(
    api_base: str, path: str, params: dict, limit: int = 5000
) -> pd.DataFrame:
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
        out["_value"] = out["_value"].fillna(
            pd.to_numeric(out["value_text"], errors="coerce")
        )
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

    pvt = x.pivot_table(
        index="symbol", columns="account_code", values="_value", aggfunc="last"
    ).reset_index()
    for code in account_codes:
        if code not in pvt.columns:
            pvt[code] = np.nan
    return pvt[["symbol"] + account_codes]


def build_cashflow_single_quarter(
    cf_xbrl: pd.DataFrame,
    *,
    prev_q: str,
    anchor_q: str,
    account_codes: list[str],
    symbols: Optional[Set[str]] = None,
) -> pd.DataFrame:
    anchor_acc = pivot_xbrl_codes(
        cf_xbrl,
        date=anchor_q,
        period_type="accumulated",
        account_codes=account_codes,
        symbols=symbols,
    )
    prev_acc = pivot_xbrl_codes(
        cf_xbrl,
        date=prev_q,
        period_type="accumulated",
        account_codes=account_codes,
        symbols=symbols,
    )
    if anchor_acc.empty:
        return pd.DataFrame(columns=["symbol"] + account_codes)

    merged = anchor_acc.merge(
        prev_acc, on="symbol", how="left", suffixes=("_anchor_acc", "_prev_acc")
    )
    out = pd.DataFrame({"symbol": merged["symbol"]})
    for code in account_codes:
        out[code] = pd.to_numeric(
            merged[f"{code}_anchor_acc"], errors="coerce"
        ) - pd.to_numeric(merged[f"{code}_prev_acc"], errors="coerce")
    return out


def build_xbrl_feature_frame(
    inc_xbrl: pd.DataFrame,
    bs_xbrl: pd.DataFrame,
    cf_xbrl: pd.DataFrame,
    *,
    prev_q: str,
    anchor_q: str,
    symbols: Optional[Set[str]] = None,
) -> pd.DataFrame:
    inc_codes = ["4000", "5900", "6300", "6900", "7900", "7950", "8200"]
    bs_codes = ["1100", "11XX", "21XX", "1XXX"]
    cf_codes = ["AAAA", "B02700"]

    inc_anchor = pivot_xbrl_codes(
        inc_xbrl,
        date=anchor_q,
        period_type="quarter",
        account_codes=inc_codes,
        symbols=symbols,
    )
    bs_anchor = pivot_xbrl_codes(
        bs_xbrl,
        date=anchor_q,
        period_type="as_of",
        account_codes=bs_codes,
        symbols=symbols,
    )
    cf_anchor = build_cashflow_single_quarter(
        cf_xbrl,
        prev_q=prev_q,
        anchor_q=anchor_q,
        account_codes=cf_codes,
        symbols=symbols,
    )

    x = inc_anchor.merge(bs_anchor, on="symbol", how="outer").merge(
        cf_anchor, on="symbol", how="outer"
    )
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
    x["xbrl_capex_to_revenue_q"] = safe_div_positive(x["B02700"].abs(), x["4000"]).clip(
        0, 10
    )

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


def fetch_one_year_api(
    api_base: str, year: int, market: str, month: str
) -> pd.DataFrame:
    qctx = build_quarter_context(year, month)
    mctx = monthly_context(year, month)
    prev_q = qctx["prev_q"]
    anchor_q = qctx["anchor_q"]
    target_q = qctx["target_q"]
    ly_target_q = qctx["ly_target_q"]
    ly_anchor_q = qctx["ly_anchor_q"]

    inc_anchor = fetch_all_rows_api(
        api_base,
        "/raw/income-statements",
        {"start_date": anchor_q, "end_date": anchor_q, "market": market},
    )
    inc_prev = fetch_all_rows_api(
        api_base,
        "/raw/income-statements",
        {"start_date": prev_q, "end_date": prev_q, "market": market},
    )
    bs_anchor = fetch_all_rows_api(
        api_base,
        "/raw/balance-sheets",
        {"start_date": anchor_q, "end_date": anchor_q, "market": market},
    )
    cf_anchor = fetch_all_rows_api(
        api_base,
        "/raw/cash-flows",
        {"start_date": anchor_q, "end_date": anchor_q, "market": market},
    )
    eps_dates = sorted({target_q, ly_target_q, ly_anchor_q, prev_q, anchor_q})
    qr = fetch_all_rows_api(
        api_base,
        "/raw/quarterly-reports",
        {"start_date": eps_dates[0], "end_date": eps_dates[-1], "market": market},
    )
    mr = fetch_all_rows_api(
        api_base,
        "/raw/monthly-revenue",
        {"start_date": mctx["mr_start"], "end_date": mctx["mr_end"]},
    )

    if inc_anchor.empty:
        return pd.DataFrame()

    # 與 DB 路徑保持一致的樣本保留行為：
    # 錨點季度必須同時存在於 income_statement + balance_sheet + cash_flow。
    if bs_anchor.empty or cf_anchor.empty:
        return pd.DataFrame()

    anchor_data = inc_anchor.merge(
        bs_anchor[
            [
                "symbol",
                "date",
                "total_equity",
                "total_liabilities",
                "total_assets",
                "share_capital",
                "retained_earnings",
            ]
        ],
        on=["symbol", "date"],
        how="inner",
    )
    anchor_data = anchor_data.merge(
        cf_anchor[["symbol", "date", "cash_flow_operating_q"]],
        on=["symbol", "date"],
        how="inner",
    )
    if anchor_data.empty:
        return pd.DataFrame()
    anchor_data = anchor_data.rename(
        columns={
            "revenue_q": "anchor_rev",
            "net_income_q": "anchor_ni",
            "share_capital": "capital",
            "retained_earnings": "anchor_retained_earnings",
            "cash_flow_operating_q": "anchor_ocf",
        }
    )
    anchor_data["anchor_margin"] = safe_col(anchor_data, "anchor_ni") / safe_col(
        anchor_data, "anchor_rev"
    ).replace(0, np.nan)
    anchor_data["anchor_non_op_ratio"] = safe_col(
        anchor_data, "non_operating_income_q"
    ) / safe_col(anchor_data, "pretax_income_q").replace(0, np.nan)
    anchor_data["anchor_roe"] = safe_col(anchor_data, "anchor_ni") / safe_col(
        anchor_data, "total_equity"
    ).replace(0, np.nan)
    anchor_data["anchor_debt_ratio"] = safe_col(
        anchor_data, "total_liabilities"
    ) / safe_col(anchor_data, "total_assets").replace(0, np.nan)
    anchor_data = anchor_data[
        [
            "symbol",
            "name",
            "anchor_rev",
            "anchor_ni",
            "anchor_margin",
            "anchor_non_op_ratio",
            "anchor_roe",
            "anchor_debt_ratio",
            "capital",
            "anchor_retained_earnings",
            "anchor_ocf",
        ]
    ]

    prev_data = pd.DataFrame(columns=["symbol", "prev_margin", "prev_rev", "prev_ni"])
    if not inc_prev.empty:
        prev_data = inc_prev[["symbol", "revenue_q", "net_income_q"]].copy()
        prev_data = prev_data.rename(
            columns={"revenue_q": "prev_rev", "net_income_q": "prev_ni"}
        )
        prev_data["prev_margin"] = safe_div_positive(
            prev_data["prev_ni"], prev_data["prev_rev"]
        )
        prev_data = prev_data[["symbol", "prev_margin", "prev_rev", "prev_ni"]]

    this_monthly = pd.DataFrame(columns=["symbol"] + mctx["month_cols"])
    if not mr.empty:
        if "market" in mr.columns:
            mr = mr[mr["market"].astype(str).str.upper() == market.upper()].copy()
        mr2 = mr[mr["date"].isin(mctx["mr_dates"])].copy()
        if not mr2.empty:
            pvt = mr2.pivot_table(
                index="symbol", columns="date", values="revenue_current", aggfunc="last"
            ).reset_index()
            this_monthly = pvt.rename(columns=mctx["date_to_col"])
            for c in mctx["month_cols"]:
                if c not in this_monthly.columns:
                    this_monthly[c] = np.nan
            this_monthly = this_monthly[["symbol"] + mctx["month_cols"]]

    eps_hist = pd.DataFrame(
        columns=[
            "symbol",
            "target_eps",
            "ly_target_eps",
            "ly_anchor_eps",
            "prev_eps",
            "anchor_eps",
        ]
    )
    if not qr.empty:
        qr2 = qr[
            qr["date"].isin([target_q, ly_target_q, ly_anchor_q, prev_q, anchor_q])
        ].copy()
        p = qr2.pivot_table(
            index="symbol", columns="date", values="eps_q", aggfunc="last"
        ).reset_index()
        eps_hist = p.rename(
            columns={
                target_q: "target_eps",
                ly_target_q: "ly_target_eps",
                ly_anchor_q: "ly_anchor_eps",
                prev_q: "prev_eps",
                anchor_q: "anchor_eps",
            }
        )
        for c in [
            "target_eps",
            "ly_target_eps",
            "ly_anchor_eps",
            "prev_eps",
            "anchor_eps",
        ]:
            if c not in eps_hist.columns:
                eps_hist[c] = np.nan
        eps_hist = eps_hist[
            [
                "symbol",
                "target_eps",
                "ly_target_eps",
                "ly_anchor_eps",
                "prev_eps",
                "anchor_eps",
            ]
        ]

    out = anchor_data.merge(prev_data, on="symbol", how="left")
    out = out.merge(this_monthly, on="symbol", how="inner")
    out = out.merge(eps_hist, on="symbol", how="inner")

    symbol_universe = set(out["symbol"].astype(str).unique())
    try:
        inc_xbrl = fetch_all_rows_api(
            api_base,
            "/raw/income-statements-xbrl",
            {"start_date": prev_q, "end_date": anchor_q},
        )
        bs_xbrl = fetch_all_rows_api(
            api_base,
            "/raw/balance-sheets-xbrl",
            {"start_date": anchor_q, "end_date": anchor_q},
        )
        cf_xbrl = fetch_all_rows_api(
            api_base,
            "/raw/cash-flows-xbrl",
            {"start_date": prev_q, "end_date": anchor_q},
        )
        xbrl_features = build_xbrl_feature_frame(
            inc_xbrl,
            bs_xbrl,
            cf_xbrl,
            prev_q=prev_q,
            anchor_q=anchor_q,
            symbols=symbol_universe,
        )
        out = out.merge(xbrl_features, on="symbol", how="left")
    except Exception as e:
        print(f"[WARN] skip XBRL feature merge (api) year={year} market={market}: {e}")

    out["year"] = qctx["target_year"]
    return out


def fetch_one_year(conn, year: int, market: str, month: str) -> pd.DataFrame:
    qctx = build_quarter_context(year, month)
    mctx = monthly_context(year, month)
    prev_q = qctx["prev_q"]
    anchor_q = qctx["anchor_q"]
    target_q = qctx["target_q"]
    ly_target_q = qctx["ly_target_q"]
    ly_anchor_q = qctx["ly_anchor_q"]

    sql = f"""
    WITH anchor_data AS (
      SELECT i.symbol, i.name, i.revenue_q AS anchor_rev, i.net_income_q AS anchor_ni,
             i.net_income_q/NULLIF(i.revenue_q,0) AS anchor_margin,
             i.non_operating_income_q/NULLIF(i.pretax_income_q,0) AS anchor_non_op_ratio,
             i.net_income_q/NULLIF(b.total_equity,0) AS anchor_roe,
             b.total_liabilities/NULLIF(b.total_assets,0) AS anchor_debt_ratio,
             b.share_capital AS capital, b.retained_earnings AS anchor_retained_earnings,
             c.cash_flow_operating_q AS anchor_ocf
      FROM income_statement i
      JOIN balance_sheet b ON i.symbol=b.symbol AND i.date=b.date
      JOIN cash_flow c ON i.symbol=c.symbol AND i.date=c.date
      WHERE i.date='{anchor_q}' AND i.market='{market}'
    ),
    prev_data AS (
      SELECT
        symbol,
        revenue_q AS prev_rev,
        net_income_q AS prev_ni,
        CASE WHEN revenue_q > 0 THEN net_income_q/revenue_q END AS prev_margin
      FROM income_statement WHERE date='{prev_q}' AND market='{market}'
    ),
    this_monthly AS (
      SELECT symbol,
             {",".join(mctx["sql_exprs"])}
      FROM monthly_revenue
      WHERE date IN ({",".join([f"'{d}'" for d in mctx["mr_dates"]])})
      GROUP BY symbol
    ),
    eps_hist AS (
      SELECT qr.symbol, qr.eps_q AS target_eps,
             (SELECT eps_q FROM quarterly_reports_xbrl WHERE symbol=qr.symbol AND date='{ly_target_q}' AND market='{market}' AND period_type='quarter') AS ly_target_eps,
             (SELECT eps_q FROM quarterly_reports_xbrl WHERE symbol=qr.symbol AND date='{ly_anchor_q}' AND market='{market}' AND period_type='quarter') AS ly_anchor_eps,
             (SELECT eps_q FROM quarterly_reports_xbrl WHERE symbol=qr.symbol AND date='{prev_q}' AND market='{market}' AND period_type='quarter') AS prev_eps,
             (SELECT eps_q FROM quarterly_reports_xbrl WHERE symbol=qr.symbol AND date='{anchor_q}' AND market='{market}' AND period_type='quarter') AS anchor_eps
      FROM quarterly_reports_xbrl qr WHERE qr.date='{target_q}' AND qr.market='{market}' AND qr.period_type='quarter'
    )
    SELECT {qctx["target_year"]} AS year, a.*, p.prev_margin, p.prev_rev, p.prev_ni,
           {",".join([f"m.{c}" for c in mctx["month_cols"]])},
           e.target_eps,e.ly_target_eps,e.ly_anchor_eps,e.prev_eps,e.anchor_eps
    FROM anchor_data a
    LEFT JOIN prev_data p ON a.symbol=p.symbol
    JOIN this_monthly m ON a.symbol=m.symbol
    JOIN eps_hist e ON a.symbol=e.symbol
    """
    out = pd.read_sql(sql, conn)

    symbol_universe = set(out["symbol"].astype(str).unique())
    try:
        inc_xbrl = pd.read_sql(
            f"""
            SELECT * FROM income_statement_xbrl
            WHERE date IN ('{prev_q}','{anchor_q}')
              AND symbol IN (SELECT symbol FROM stock_info WHERE market = '{market}')
            """,
            conn,
        )
        bs_xbrl = pd.read_sql(
            f"""
            SELECT * FROM balance_sheet_xbrl
            WHERE date = '{anchor_q}'
              AND symbol IN (SELECT symbol FROM stock_info WHERE market = '{market}')
            """,
            conn,
        )
        cf_xbrl = pd.read_sql(
            f"""
            SELECT * FROM cash_flow_xbrl
            WHERE date IN ('{prev_q}','{anchor_q}')
              AND symbol IN (SELECT symbol FROM stock_info WHERE market = '{market}')
            """,
            conn,
        )
        xbrl_features = build_xbrl_feature_frame(
            inc_xbrl,
            bs_xbrl,
            cf_xbrl,
            prev_q=prev_q,
            anchor_q=anchor_q,
            symbols=symbol_universe,
        )
        out = out.merge(xbrl_features, on="symbol", how="left")
    except Exception as e:
        print(f"[WARN] skip XBRL feature merge (db) year={year} market={market}: {e}")

    return out


def add_month_features(df: pd.DataFrame, month: str) -> None:
    for m in feature_months_for_calendar_month(month):
        _, prev_m = month_shift(2000, m, -1)
        yoy_raw = f"rev_yoy_m{m:02d}"
        mom_raw = f"rev_mom_m{m:02d}_m{prev_m}"
        yoy_z = f"{yoy_raw}_z"
        mom_z = f"{mom_raw}_z"
        yoy_q = f"{yoy_raw}_quantile"
        mom_q = f"{mom_raw}_quantile"

        df[yoy_raw] = safe_div_positive(df[f"rev_m{m:02d}"], df[f"rev_m{m:02d}_ly"]) - 1
        df[mom_raw] = (
            safe_div_positive(df[f"rev_m{m:02d}"], df[f"rev_m{prev_m:02d}"]) - 1
        )
        add_industry_zscore(df, yoy_raw, yoy_z)
        add_industry_zscore(df, mom_raw, mom_z)
        add_cross_section_quantile(df, yoy_z, yoy_q)
        add_cross_section_quantile(df, mom_z, mom_q)


def main() -> None:
    args = parse_args()
    month = normalize_month(args.month)
    end_year = int(args.year)
    model_features = model_features_for_month(month)

    month_dir = (
        Path(__file__).resolve().parent / "output" / str(end_year) / month
    ).resolve()
    output_train = month_dir / "dataset_train.csv"
    output_evaluate = month_dir / "dataset_evaluate.csv"

    # anchor_quarter 是 metadata 欄位（非 feature），各下游 step2/3/4 的
    # EXCLUDE_COLUMNS 已加入忽略，純粹標記該列 anchor_eps 對應的實際季度。
    train_columns = ["year", "anchor_quarter"] + model_features + [TARGET, TARGET_DELTA]
    evaluate_columns = (
        CONTEXT_COLUMNS
        + ["year", "anchor_quarter"]
        + model_features
        + [TARGET, TARGET_DELTA]
    )

    fetch_years = list(range(START_YEAR, end_year + 1))
    frames: list[pd.DataFrame] = []

    if args.data_source == "db":
        engine = create_engine(get_db_url())
        with engine.connect() as conn:
            conn.execute(text("SET max_parallel_workers_per_gather = 0"))
            for year in fetch_years:
                for market in MARKETS:
                    print(
                        f"fetching data from db: year={year}, market={market}, month={month}"
                    )
                    y = fetch_one_year(conn, year, market, month)
                    if not y.empty:
                        frames.append(y)
            industry_parts: list[pd.DataFrame] = []
            for market in MARKETS:
                part = pd.read_sql(
                    f"SELECT symbol, industry FROM stock_info WHERE market = '{market}'",
                    conn,
                )
                if not part.empty:
                    industry_parts.append(part[["symbol", "industry"]])
    else:
        for year in fetch_years:
            for market in MARKETS:
                print(
                    f"fetching data from api: year={year}, market={market}, month={month}"
                )
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
        industry_df = pd.concat(industry_parts, ignore_index=True).drop_duplicates(
            "symbol"
        )

    if not frames:
        raise RuntimeError(
            "No data fetched. Check data source settings and year range."
        )

    df = pd.concat(frames, ignore_index=True)
    if not industry_df.empty:
        df = df.merge(industry_df, on="symbol", how="left")
    df["industry"] = df.get("industry", pd.Series(index=df.index)).fillna("unknown")
    df = df.replace([np.inf, -np.inf], np.nan)

    df["prev_margin"] = safe_div_positive(
        safe_col(df, "prev_ni"), safe_col(df, "prev_rev")
    )
    df["anchor_margin"] = safe_div_positive(df["anchor_ni"], df["anchor_rev"])
    df["anchor_ocf_ratio"] = safe_div_positive(df["anchor_ocf"], df["anchor_ni"]).clip(
        -5, 5
    )
    df["anchor_re_ratio"] = safe_div_positive(
        df["anchor_retained_earnings"], df["capital"]
    )
    df["margin_momentum"] = df["anchor_margin"] - df["prev_margin"]

    add_month_features(df, month)

    df["ly_seasonality"] = safe_div_positive(
        df["ly_target_eps"], df["ly_anchor_eps"]
    ).clip(-5, 5)
    df["anchor_yoy_eps"] = (
        safe_div_positive(df["anchor_eps"], df["ly_anchor_eps"]) - 1
    ).clip(-5, 5)
    df[TARGET_DELTA] = df[TARGET] - df["anchor_eps"]

    # 每列依其 target_year + playbook month 推得 anchor 對應的實際季度
    anchor_year_offset = {
        "02": -1,
        "03": -1,
        "04": -1,
        "05": 0,
        "06": 0,
        "07": 0,
        "08": 0,
        "09": 0,
        "10": 0,
        "11": 0,
        "12": 0,
        "01": 0,
    }
    anchor_q_num = {
        "02": 4,
        "03": 4,
        "04": 4,
        "05": 1,
        "06": 1,
        "07": 1,
        "08": 2,
        "09": 2,
        "10": 2,
        "11": 3,
        "12": 3,
        "01": 3,
    }
    df["anchor_quarter"] = (df["year"].astype(int) + anchor_year_offset[month]).astype(
        str
    ) + f"Q{anchor_q_num[month]}"

    rows_before_filter = len(df)
    ttm_eps_proxy = (
        safe_col(df, "ly_target_eps").fillna(0)
        + safe_col(df, "prev_eps").fillna(0)
        + safe_col(df, "anchor_eps").fillna(0)
    )
    ttm_ok = ttm_eps_proxy >= float(MIN_TTM_EPS)
    df = df[ttm_ok].copy()
    rows_after_filter = len(df)

    labeled_mask = (
        df[TARGET].notna() & df["anchor_eps"].notna() & df[TARGET_DELTA].notna()
    )

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
    print(f"- min_ttm_eps: {MIN_TTM_EPS}")
    print(f"- rows_before_filter: {rows_before_filter}")
    print(f"- rows_after_filter: {rows_after_filter}")
    print(f"- rows_labeled: {len(out_debug)}")


if __name__ == "__main__":
    main()
