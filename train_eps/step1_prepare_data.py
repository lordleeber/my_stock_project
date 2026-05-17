from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Set

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

_HERE = Path(__file__).resolve().parent
ROOT_DIR = _HERE.parent
# 讓本檔同時支援「直接執行」與「被 strategies 反向 import」兩種啟動方式：
# 前者只會把 _HERE 加進 sys.path，後者只會把 ROOT_DIR 加進 sys.path。
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from shared_config import format_quarter, shift_quarter, target_quarter_for_playbook
from common.db import get_db_url

TARGET = "target_eps"
TARGET_DELTA = "delta_eps"
CONTEXT_COLUMNS = ["symbol", "name", "industry"]
MIN_TTM_EPS = 1.0
MARKETS = ("sii", "otc")
START_YEAR = 2020


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
    # 由 (target_year, target_qnum) 推導 anchor / pre_anchor / 去年同期等季度字串。
    # pre_anchor 指「anchor 前一季」（= target 前兩季），用來算 QoQ momentum。
    target_year, target_qnum = target_quarter_for_playbook(execution_year, month)
    anchor_y, anchor_qn = shift_quarter(target_year, target_qnum, -1)
    pre_anchor_y, pre_anchor_qn = shift_quarter(target_year, target_qnum, -2)

    return {
        "target_year": target_year,
        "target_q": format_quarter(target_year, target_qnum),
        "anchor_q": format_quarter(anchor_y, anchor_qn),
        "pre_anchor_q": format_quarter(pre_anchor_y, pre_anchor_qn),
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
    p = argparse.ArgumentParser(
        description="Prepare dataset from PostgreSQL (XBRL only)"
    )
    p.add_argument("--year", type=int, required=True)
    p.add_argument("--month", type=str, required=True, help="01~12")
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
    pre_anchor_q: str,
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
    pre_anchor_acc = pivot_xbrl_codes(
        cf_xbrl,
        date=pre_anchor_q,
        period_type="accumulated",
        account_codes=account_codes,
        symbols=symbols,
    )
    if anchor_acc.empty:
        return pd.DataFrame(columns=["symbol"] + account_codes)

    merged = anchor_acc.merge(
        pre_anchor_acc,
        on="symbol",
        how="left",
        suffixes=("_anchor_acc", "_pre_anchor_acc"),
    )
    out = pd.DataFrame({"symbol": merged["symbol"]})
    for code in account_codes:
        out[code] = pd.to_numeric(
            merged[f"{code}_anchor_acc"], errors="coerce"
        ) - pd.to_numeric(merged[f"{code}_pre_anchor_acc"], errors="coerce")
    return out


def build_xbrl_feature_frame(
    inc_xbrl: pd.DataFrame,
    bs_xbrl: pd.DataFrame,
    cf_xbrl: pd.DataFrame,
    *,
    pre_anchor_q: str,
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
        pre_anchor_q=pre_anchor_q,
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


def fetch_one_year(conn, year: int, market: str, month: str) -> pd.DataFrame:
    """Build one year's training/evaluation row set entirely from XBRL tables.

    Anchor 入庫資料來源（皆 XBRL；舊的 income_statement / balance_sheet / cash_flow
    legacy 表已停更，禁止使用）：
      - 損益表 / 現金股本：quarterly_reports_xbrl (wide-format, period_type='quarter')
      - 資產負債：balance_sheet_xbrl (long-format, period_type='as_of', account_code 取
                  1XXX/2XXX/3XXX/3300)
      - 營業現金流：cash_flow_xbrl (long-format, period_type='accumulated', account_code
                  'AAAA')，逐季差值由 build_cashflow_single_quarter 計算

    語意上維持原版 INNER JOIN（income + BS + CF 三者皆有資料才保留），不對缺資料的 symbol
    做 silent fallback。
    """
    qctx = build_quarter_context(year, month)
    mctx = monthly_context(year, month)
    pre_anchor_q = qctx["pre_anchor_q"]
    anchor_q = qctx["anchor_q"]
    target_q = qctx["target_q"]
    ly_target_q = qctx["ly_target_q"]
    ly_anchor_q = qctx["ly_anchor_q"]

    # ── 1. 主查：quarterly_reports_xbrl + monthly_revenue + eps_hist + stock_info(name)
    sql = f"""
    WITH anchor_inc AS (
      SELECT q.symbol,
             q.revenue_q       AS anchor_rev,
             q.net_income_q    AS anchor_ni,
             q.non_op_income_q,
             q.pretax_income_q,
             q.capital
      FROM quarterly_reports_xbrl q
      WHERE q.date='{anchor_q}' AND q.market='{market}' AND q.period_type='quarter'
    ),
    pre_anchor_inc AS (
      SELECT symbol,
             revenue_q    AS pre_anchor_rev,
             net_income_q AS pre_anchor_ni
      FROM quarterly_reports_xbrl
      WHERE date='{pre_anchor_q}' AND market='{market}' AND period_type='quarter'
    ),
    this_monthly AS (
      SELECT symbol,
             {",".join(mctx["sql_exprs"])}
      FROM monthly_revenue
      WHERE date IN ({",".join([f"'{d}'" for d in mctx["mr_dates"]])})
      GROUP BY symbol
    ),
    eps_hist AS (
      -- 用 CASE-WHEN pivot 從 anchor 期間附近的所有相關季 EPS。
      -- target_q（如 2026Q2）公告日尚未到時，target_eps 自然 NaN，這是 live prediction
      -- 的正常狀態；其餘 ly_target / ly_anchor / pre_anchor / anchor 都是已過去的季，
      -- 任一缺值代表上游 XBRL 入庫真的有洞，會在 labeled_mask 過濾時被處理。
      SELECT symbol,
             MAX(CASE WHEN date='{target_q}'     THEN eps_q END) AS target_eps,
             MAX(CASE WHEN date='{ly_target_q}'  THEN eps_q END) AS ly_target_eps,
             MAX(CASE WHEN date='{ly_anchor_q}'  THEN eps_q END) AS ly_anchor_eps,
             MAX(CASE WHEN date='{pre_anchor_q}' THEN eps_q END) AS pre_anchor_eps,
             MAX(CASE WHEN date='{anchor_q}'     THEN eps_q END) AS anchor_eps
      FROM quarterly_reports_xbrl
      WHERE date IN ('{target_q}','{ly_target_q}','{ly_anchor_q}','{pre_anchor_q}','{anchor_q}')
        AND market='{market}' AND period_type='quarter'
      GROUP BY symbol
    ),
    name_lookup AS (
      SELECT symbol, name FROM stock_info WHERE market='{market}'
    )
    SELECT {qctx["target_year"]} AS year, ai.*,
           n.name,
           pi.pre_anchor_rev, pi.pre_anchor_ni,
           {",".join([f"m.{c}" for c in mctx["month_cols"]])},
           e.target_eps, e.ly_target_eps, e.ly_anchor_eps, e.pre_anchor_eps, e.anchor_eps
    FROM anchor_inc ai
    LEFT JOIN pre_anchor_inc pi ON ai.symbol=pi.symbol
    LEFT JOIN name_lookup n     ON ai.symbol=n.symbol
    JOIN this_monthly m         ON ai.symbol=m.symbol
    LEFT JOIN eps_hist e        ON ai.symbol=e.symbol
    """
    out = pd.read_sql(sql, conn)

    # ── 2. 拉 XBRL long-format（income / BS / CF）— anchor 與 pre_anchor 兩季
    inc_xbrl = pd.read_sql(
        f"SELECT * FROM income_statement_xbrl WHERE date IN ('{pre_anchor_q}','{anchor_q}')",
        conn,
    )
    bs_xbrl = pd.read_sql(
        f"SELECT * FROM balance_sheet_xbrl WHERE date='{anchor_q}'",
        conn,
    )
    cf_xbrl = pd.read_sql(
        f"SELECT * FROM cash_flow_xbrl WHERE date IN ('{pre_anchor_q}','{anchor_q}')",
        conn,
    )

    # ── 3. anchor BS：1XXX/2XXX/3XXX/3300 → total_assets/_liabilities/_equity/retained_earnings
    bs_anchor = pivot_xbrl_codes(
        bs_xbrl,
        date=anchor_q,
        period_type="as_of",
        account_codes=["1XXX", "2XXX", "3XXX", "3300"],
    ).rename(
        columns={
            "1XXX": "total_assets",
            "2XXX": "total_liabilities",
            "3XXX": "total_equity",
            "3300": "anchor_retained_earnings",
        }
    )

    # ── 4. anchor CF：AAAA = 營業活動現金流（accumulated → 單季差值）
    cf_anchor = build_cashflow_single_quarter(
        cf_xbrl,
        pre_anchor_q=pre_anchor_q,
        anchor_q=anchor_q,
        account_codes=["AAAA"],
    ).rename(columns={"AAAA": "anchor_ocf"})

    # ── 5. INNER MERGE：必須同時有 income + BS + CF anchor 資料才保留樣本
    out = out.merge(bs_anchor, on="symbol", how="inner")
    out = out.merge(cf_anchor, on="symbol", how="inner")

    # ── 6. 衍生 ratio（原 SQL 用 NULLIF(.,0)，這裡用 .replace(0, NaN) 等價語意）
    out["anchor_non_op_ratio"] = out["non_op_income_q"] / out[
        "pretax_income_q"
    ].replace(0, np.nan)
    out["anchor_roe"] = out["anchor_ni"] / out["total_equity"].replace(0, np.nan)
    out["anchor_debt_ratio"] = out["total_liabilities"] / out["total_assets"].replace(
        0, np.nan
    )

    # ── 7. XBRL ratio features（xbrl_gross_margin_q / xbrl_op_margin_q / …）
    symbol_universe = set(out["symbol"].astype(str).unique())
    xbrl_features = build_xbrl_feature_frame(
        inc_xbrl,
        bs_xbrl,
        cf_xbrl,
        pre_anchor_q=pre_anchor_q,
        anchor_q=anchor_q,
        symbols=symbol_universe,
    )
    out = out.merge(xbrl_features, on="symbol", how="left")

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

    df["pre_anchor_margin"] = safe_div_positive(
        safe_col(df, "pre_anchor_ni"), safe_col(df, "pre_anchor_rev")
    )
    df["anchor_margin"] = safe_div_positive(df["anchor_ni"], df["anchor_rev"])
    df["anchor_ocf_ratio"] = safe_div_positive(df["anchor_ocf"], df["anchor_ni"]).clip(
        -5, 5
    )
    df["anchor_re_ratio"] = safe_div_positive(
        df["anchor_retained_earnings"], df["capital"]
    )
    df["margin_momentum"] = df["anchor_margin"] - df["pre_anchor_margin"]

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
    # TTM proxy 不再 fillna(0)：缺 EPS 不等於 EPS=0，silent 0-fill 會讓真正資料不齊全
    # 的樣本被誤判為「TTM EPS=0」並 (依 MIN_TTM_EPS 設定) 被當作低 EPS 過濾 / 通過。
    # 改成 NaN 直接落入 ttm_ok=False，被嚴格排除。
    ttm_eps_proxy = (
        safe_col(df, "ly_target_eps")
        + safe_col(df, "pre_anchor_eps")
        + safe_col(df, "anchor_eps")
    )
    ttm_ok = ttm_eps_proxy >= float(MIN_TTM_EPS)
    df = df[ttm_ok.fillna(False)].copy()
    rows_after_filter = len(df)

    labeled_mask = (
        df[TARGET].notna() & df["anchor_eps"].notna() & df[TARGET_DELTA].notna()
    )

    evaluate_cols = [c for c in evaluate_columns if c in df.columns]
    out = df[evaluate_cols].copy()
    out["year"] = out["year"].astype(int)

    # dataset_train：只收有 label 的列（model 訓練必須要 target）
    out_train_src = out.loc[labeled_mask].copy()
    out_train_src = out_train_src[out_train_src["year"].astype(int) <= end_year].copy()
    train_cols = [c for c in train_columns if c in out_train_src.columns]
    out_train = out_train_src[train_cols].copy()

    # dataset_evaluate：除了 labeled 列，**保留 end_year 的 live 列** (target_eps 為 NaN
    # 也照收) — 給 step4 inference 用。
    #
    # 原版本只寫 labeled 列；當 playbook 在 target_quarter 公告日之前跑（例如 5/15 ~ 8/15
    # 之間預測 Q2 EPS，但 Q2 8/15 才公告），end_year 的 row 全 unlabeled 被剔光 →
    # step4 silent fallback 到 max(year)=去年 → 整份預測錯一年。
    eval_mask = labeled_mask | (out["year"].astype(int) == end_year)
    out_debug_src = out.loc[eval_mask].copy()
    out_debug_src = out_debug_src[out_debug_src["year"].astype(int) <= end_year].copy()
    evaluate_labeled_cols = [c for c in evaluate_columns if c in out_debug_src.columns]
    out_debug = out_debug_src[evaluate_labeled_cols].copy()

    output_train.parent.mkdir(parents=True, exist_ok=True)
    out_train.to_csv(output_train, index=False)
    output_evaluate.parent.mkdir(parents=True, exist_ok=True)
    out_debug.to_csv(output_evaluate, index=False)

    print("prepare_data completed")
    print(f"- month: {month}")
    print(f"- markets: {','.join(MARKETS)}")
    print(f"- years: {START_YEAR}~{end_year}")
    print(f"- output_train: {output_train}")
    print(f"- output_evaluate: {output_evaluate}")
    print(f"- min_ttm_eps: {MIN_TTM_EPS}")
    print(f"- rows_before_filter: {rows_before_filter}")
    print(f"- rows_after_filter: {rows_after_filter}")
    print(f"- rows_labeled: {len(out_debug)}")


if __name__ == "__main__":
    main()
