from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import bindparam, create_engine, text

# 確保可以從此腳本直接執行時匯入 repo 根目錄
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from common.db import get_db_url
from strategies.shared_config import (
    cutoff_date_from_playbook,
    latest_playbook_date,
    year_month_from_playbook,
)
from train_eps import step1_prepare_data as tp


# Pseudo-TTM = ly_target_eps + pre_anchor_eps + anchor_eps
# （兩個最近季 + 同期去年 target 季當 TTM 近似，並非連續 3 季）。
# strategies 採比 train_eps 寬鬆的門檻，保留更大的候選股宇宙。
MIN_PSEUDO_TTM_EPS = 2.0
# 流動性門檻：近 20 個交易日均量（張）。2026-07 起取代舊「單日 quote_volume > 500 張」——
# 單日 snapshot 對量能剛好安靜/爆量一天的股票雜訊太大（例：3147 於 2026-07 cohort
# 因 quote_date 當日僅 151 張被剔除，但其 20 日均量 >1000 張）。
# 單日 volume_lots 仍保留為 ranker 特徵，此門檻只影響候選宇宙。
MIN_AVG20_VOLUME_LOTS = 400.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare strategy inference dataset from DB."
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help=(
            "Playbook release date YYYY-MM-DD（cutoff 公告日 +1）。5/8/11 月為 16 號，"
            "其餘月份為 11 號。省略則自動鎖到 latest_playbook_date()。"
        ),
    )
    return parser.parse_args()


def fetch_valuation_features(
    engine, symbols: list[str], cutoff_date: str
) -> pd.DataFrame:
    """從 valuation_daily 撈取 ROE 與 PE 百分位（TTM 基礎，依日期 PIT 對齊）。"""
    if not symbols:
        return pd.DataFrame(
            columns=["symbol", "roe_official", "pe_percentile_official"]
        )
    stmt = text(
        """
        WITH latest AS (
            SELECT symbol, roe_official, pe_percentile_official,
                   ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) AS rn
            FROM valuation_daily
            WHERE symbol IN :symbols AND date <= :cutoff_date
        )
        SELECT symbol, roe_official, pe_percentile_official FROM latest WHERE rn = 1
        """
    ).bindparams(bindparam("symbols", expanding=True))
    with engine.connect() as conn:
        df = pd.read_sql(
            stmt, conn, params={"symbols": symbols, "cutoff_date": cutoff_date}
        )
    df["symbol"] = df["symbol"].astype(str).str.strip()
    return df


def fetch_market_sentiment_features(
    engine, symbols: list[str], cutoff_date: str
) -> pd.DataFrame:
    """撈取自營商持股、融資壓力與借券相關特徵。"""
    if not symbols:
        return pd.DataFrame(
            columns=[
                "symbol",
                "dealer_held_ratio",
                "margin_usage_ratio",
                "short_cover_pressure",
                "sbl_sell_repay_ratio",
            ]
        )

    stmt_dealer = text(
        """
        WITH latest AS (
            SELECT symbol, dealer_held_ratio,
                   ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) AS rn
            FROM dealer_holding
            WHERE symbol IN :symbols AND date <= :cutoff_date
        )
        SELECT symbol, dealer_held_ratio FROM latest WHERE rn = 1
        """
    ).bindparams(bindparam("symbols", expanding=True))

    stmt_margin = text(
        """
        WITH latest AS (
            SELECT symbol, margin_usage_ratio, short_cover_pressure,
                   ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) AS rn
            FROM margin_pressure_analysis
            WHERE symbol IN :symbols AND date <= :cutoff_date
        )
        SELECT symbol, margin_usage_ratio, short_cover_pressure FROM latest WHERE rn = 1
        """
    ).bindparams(bindparam("symbols", expanding=True))

    stmt_sbl = text(
        """
        WITH latest AS (
            SELECT symbol, sbl_sell_repay_ratio,
                   ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) AS rn
            FROM short_interest_analysis
            WHERE symbol IN :symbols AND date <= :cutoff_date
        )
        SELECT symbol, sbl_sell_repay_ratio FROM latest WHERE rn = 1
        """
    ).bindparams(bindparam("symbols", expanding=True))

    params = {"symbols": symbols, "cutoff_date": cutoff_date}
    with engine.connect() as conn:
        dealer = pd.read_sql(stmt_dealer, conn, params=params)
        margin = pd.read_sql(stmt_margin, conn, params=params)
        sbl = pd.read_sql(stmt_sbl, conn, params=params)

    for df_ in [dealer, margin, sbl]:
        df_["symbol"] = df_["symbol"].astype(str).str.strip()

    out = pd.DataFrame({"symbol": symbols})
    out = out.merge(dealer, on="symbol", how="left")
    out = out.merge(margin, on="symbol", how="left")
    out = out.merge(sbl, on="symbol", how="left")
    return out


def fetch_fundamental_features(
    engine, symbols: list[str], anchor_q: str
) -> pd.DataFrame:
    """從 quarterly_reports_xbrl 在 anchor_q 撈取財報品質指標（PIT 對齊）。"""
    if not symbols:
        return pd.DataFrame(
            columns=[
                "symbol",
                "nav_per_share",
                "current_ratio",
                "eps_acc_yoy",
                "revenue_acc_yoy",
            ]
        )
    stmt = text(
        """
        SELECT symbol, nav_per_share, current_ratio, eps_acc_yoy, revenue_acc_yoy
        FROM quarterly_reports_xbrl
        WHERE symbol IN :symbols AND date = :anchor_q AND period_type = 'quarter'
        """
    ).bindparams(bindparam("symbols", expanding=True))
    with engine.connect() as conn:
        df = pd.read_sql(stmt, conn, params={"symbols": symbols, "anchor_q": anchor_q})
    df["symbol"] = df["symbol"].astype(str).str.strip()
    return df


def fetch_chipflow_features(
    engine, symbols: list[str], cutoff_date: str
) -> pd.DataFrame:
    """撈取外資／投信持股比例與股權集中度特徵。"""
    if not symbols:
        return pd.DataFrame(
            columns=[
                "symbol",
                "foreign_held_ratio",
                "trust_held_ratio",
                "large_holder_ratio",
                "large_holder_ratio_wow",
                "large_holder_two_week_up",
                "mid_holder_ratio",
                "mid_holder_ratio_wow",
                "small_holder_ratio",
                "small_holder_ratio_wow",
                "concentration_spread",
                "concentration_spread_wow",
            ]
        )

    stmt_foreign = text(
        """
        WITH latest AS (
            SELECT symbol, foreign_held_ratio,
                   ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) AS rn
            FROM foreign_holding
            WHERE symbol IN :symbols AND date <= :cutoff_date
        )
        SELECT symbol, foreign_held_ratio FROM latest WHERE rn = 1
        """
    ).bindparams(bindparam("symbols", expanding=True))

    stmt_trust = text(
        """
        WITH latest AS (
            SELECT symbol, trust_held_ratio,
                   ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) AS rn
            FROM trust_holding
            WHERE symbol IN :symbols AND date <= :cutoff_date
        )
        SELECT symbol, trust_held_ratio FROM latest WHERE rn = 1
        """
    ).bindparams(bindparam("symbols", expanding=True))

    stmt_sc = text(
        """
        WITH ranked AS (
            SELECT symbol,
                   large_holder_ratio, large_holder_ratio_wow,
                   mid_holder_ratio, mid_holder_ratio_wow,
                   small_holder_ratio, small_holder_ratio_wow,
                   concentration_spread, concentration_spread_wow,
                   ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) AS rn
            FROM shareholding_concentration
            WHERE symbol IN :symbols AND date <= :cutoff_date
        )
        SELECT symbol,
               MAX(CASE WHEN rn = 1 THEN large_holder_ratio END)     AS large_holder_ratio,
               MAX(CASE WHEN rn = 1 THEN large_holder_ratio_wow END) AS large_holder_ratio_wow,
               CASE
                   WHEN MAX(CASE WHEN rn = 1 THEN large_holder_ratio_wow END) > 0
                    AND MAX(CASE WHEN rn = 2 THEN large_holder_ratio_wow END) > 0
                   THEN 1 ELSE 0
               END AS large_holder_two_week_up,
               MAX(CASE WHEN rn = 1 THEN mid_holder_ratio END)       AS mid_holder_ratio,
               MAX(CASE WHEN rn = 1 THEN mid_holder_ratio_wow END)   AS mid_holder_ratio_wow,
               MAX(CASE WHEN rn = 1 THEN small_holder_ratio END)     AS small_holder_ratio,
               MAX(CASE WHEN rn = 1 THEN small_holder_ratio_wow END) AS small_holder_ratio_wow,
               MAX(CASE WHEN rn = 1 THEN concentration_spread END)   AS concentration_spread,
               MAX(CASE WHEN rn = 1 THEN concentration_spread_wow END) AS concentration_spread_wow
        FROM ranked WHERE rn <= 2
        GROUP BY symbol
        """
    ).bindparams(bindparam("symbols", expanding=True))

    params = {"symbols": symbols, "cutoff_date": cutoff_date}
    with engine.connect() as conn:
        foreign = pd.read_sql(stmt_foreign, conn, params=params)
        trust = pd.read_sql(stmt_trust, conn, params=params)
        sc = pd.read_sql(stmt_sc, conn, params=params)

    for df_ in [foreign, trust, sc]:
        df_["symbol"] = df_["symbol"].astype(str).str.strip()

    out = pd.DataFrame({"symbol": symbols})
    out = out.merge(foreign, on="symbol", how="left")
    out = out.merge(trust, on="symbol", how="left")
    out = out.merge(sc, on="symbol", how="left")
    return out


def fetch_one_year_live(
    conn, year: int, market: str, month: str, cutoff_date: str
) -> pd.DataFrame:
    qctx = tp.build_quarter_context(year, month)
    mctx = tp.monthly_context(year, month)

    target_year = qctx["target_year"]
    target_q = qctx["target_q"]
    pre_anchor_q = qctx["pre_anchor_q"]
    anchor_q = qctx["anchor_q"]
    ly_target_q = qctx["ly_target_q"]
    ly_anchor_q = qctx["ly_anchor_q"]

    ly_q1 = f"{target_year - 1}Q1"
    ly_q2 = f"{target_year - 1}Q2"
    ly_q3 = f"{target_year - 1}Q3"
    ly_q4 = f"{target_year - 1}Q4"
    q1 = f"{target_year}Q1"
    q2 = f"{target_year}Q2"

    sql = f"""
    WITH bs_anchor AS (
      SELECT
        symbol,
        MAX(CASE WHEN account_code = '1XXX' THEN value_num END) AS total_assets,
        MAX(CASE WHEN account_code = '2XXX' THEN value_num END) AS total_liabilities,
        MAX(CASE WHEN account_code = '3XXX' THEN value_num END) AS total_equity,
        MAX(CASE WHEN account_code = '3300' THEN value_num END) AS retained_earnings
      FROM balance_sheet_xbrl
      WHERE date = '{anchor_q}'
        AND period_type = 'as_of'
        AND account_code IN ('1XXX', '2XXX', '3XXX', '3300')
      GROUP BY symbol
    ),
    cf_anchor AS (
      SELECT
        acc_anchor.symbol,
        CASE
          WHEN RIGHT('{anchor_q}', 2) = 'Q1' THEN acc_anchor.ocf_acc
          ELSE acc_anchor.ocf_acc - COALESCE(acc_pre_anchor.ocf_acc, 0)
        END AS anchor_ocf
      FROM (
        SELECT symbol, value_num AS ocf_acc
        FROM cash_flow_xbrl
        WHERE date = '{anchor_q}' AND period_type = 'accumulated' AND account_code = 'AAAA'
      ) acc_anchor
      LEFT JOIN (
        SELECT symbol, value_num AS ocf_acc
        FROM cash_flow_xbrl
        WHERE date = '{pre_anchor_q}' AND period_type = 'accumulated' AND account_code = 'AAAA'
      ) acc_pre_anchor ON acc_anchor.symbol = acc_pre_anchor.symbol
    ),
    anchor_data AS (
      SELECT
        '{market}' AS market,
        q.symbol,
        si.name,
        q.revenue_q AS anchor_rev,
        q.net_income_q AS anchor_ni,
        q.net_income_q / NULLIF(q.revenue_q, 0) AS anchor_margin,
        q.non_op_income_q / NULLIF(q.pretax_income_q, 0) AS anchor_non_op_ratio,
        q.net_income_q / NULLIF(bs.total_equity, 0) AS anchor_roe,
        bs.total_liabilities / NULLIF(bs.total_assets, 0) AS anchor_debt_ratio,
        q.capital,
        bs.retained_earnings AS anchor_retained_earnings,
        cf.anchor_ocf
      FROM quarterly_reports_xbrl q
      LEFT JOIN stock_info si ON q.symbol = si.symbol
      LEFT JOIN bs_anchor bs ON q.symbol = bs.symbol
      LEFT JOIN cf_anchor cf ON q.symbol = cf.symbol
      WHERE q.date = '{anchor_q}'
        AND q.period_type = 'quarter'
        AND COALESCE(si.market, q.market) = '{market}'
    ),
    pre_anchor_data AS (
      SELECT
        symbol,
        revenue_q AS pre_anchor_rev,
        net_income_q AS pre_anchor_ni,
        CASE WHEN revenue_q > 0 THEN net_income_q / revenue_q END AS pre_anchor_margin
      FROM quarterly_reports_xbrl
      WHERE date = '{pre_anchor_q}' AND period_type = 'quarter'
    ),
    this_monthly AS (
      SELECT symbol, {",".join(mctx["sql_exprs"])}
      FROM monthly_revenue
      WHERE date IN ({",".join([f"'{d}'" for d in mctx["mr_dates"]])})
      GROUP BY symbol
    ),
    eps_hist AS (
      SELECT
        qr.symbol,
        MAX(CASE WHEN qr.date = '{target_q}' THEN qr.eps_q END) AS target_eps,
        MAX(CASE WHEN qr.date = '{ly_target_q}' THEN qr.eps_q END) AS ly_target_eps,
        MAX(CASE WHEN qr.date = '{ly_anchor_q}' THEN qr.eps_q END) AS ly_anchor_eps,
        MAX(CASE WHEN qr.date = '{pre_anchor_q}' THEN qr.eps_q END) AS pre_anchor_eps,
        MAX(CASE WHEN qr.date = '{anchor_q}' THEN qr.eps_q END) AS anchor_eps,
        MAX(CASE WHEN qr.date = '{ly_q1}' THEN qr.eps_q END) AS ly_q1_eps,
        MAX(CASE WHEN qr.date = '{ly_q2}' THEN qr.eps_q END) AS ly_q2_eps,
        MAX(CASE WHEN qr.date = '{ly_q3}' THEN qr.eps_q END) AS ly_q3_eps,
        MAX(CASE WHEN qr.date = '{ly_q4}' THEN qr.eps_q END) AS ly_q4_eps,
        MAX(CASE WHEN qr.date = '{q1}' THEN qr.eps_q END) AS ty_q1_eps,
        MAX(CASE WHEN qr.date = '{q2}' THEN qr.eps_q END) AS ty_q2_eps
      FROM quarterly_reports_xbrl qr
      WHERE qr.market = '{market}'
        AND qr.period_type = 'quarter'
        AND qr.date IN ('{target_q}','{ly_target_q}','{ly_anchor_q}','{pre_anchor_q}','{anchor_q}','{ly_q1}','{ly_q2}','{ly_q3}','{ly_q4}','{q1}','{q2}')
      GROUP BY qr.symbol
    ),
    quote_latest AS (
      -- 最新一筆 daily_quotes（在 cutoff_date 當天或之前）＋近 20 個交易日均量；
      -- 與真正季度 (ly_q*/ty_q*) 無關，原 q3_* 命名沿用 deprecated。
      -- avg_volume_20d = 最近 20 筆交易日列的平均（上市未滿 20 日者取現有筆數平均），
      -- 僅供流動性 filter 使用；rn=1 的單日 snapshot 欄位語意與舊版完全相同。
      SELECT
        symbol,
        MAX(CASE WHEN rn = 1 THEN quote_date END)    AS quote_date,
        MAX(CASE WHEN rn = 1 THEN close END)         AS close,
        MAX(CASE WHEN rn = 1 THEN quote_volume END)  AS quote_volume,
        AVG(quote_volume)                            AS avg_volume_20d
      FROM (
        SELECT
          d.symbol,
          d.date AS quote_date,
          d.close AS close,
          d.volume AS quote_volume,
          ROW_NUMBER() OVER (PARTITION BY d.symbol ORDER BY d.date DESC) AS rn
        FROM daily_quotes d
        JOIN anchor_data a ON a.symbol = d.symbol
        WHERE d.market = '{market}' AND d.date <= '{cutoff_date}'
      ) z
      WHERE z.rn <= 20
      GROUP BY symbol
    )
    SELECT
      {target_year} AS year,
      a.*,
      p.pre_anchor_margin,
      p.pre_anchor_rev,
      p.pre_anchor_ni,
      {",".join([f"m.{c}" for c in mctx["month_cols"]])},
      e.ly_target_eps,
      e.ly_anchor_eps,
      e.pre_anchor_eps,
      e.anchor_eps,
      e.target_eps,
      e.ly_q1_eps,
      e.ly_q2_eps,
      e.ly_q3_eps,
      e.ly_q4_eps,
      e.ty_q1_eps,
      e.ty_q2_eps,
      q.quote_date,
      q.close,
      q.quote_volume,
      q.avg_volume_20d
    FROM anchor_data a
    LEFT JOIN pre_anchor_data p ON a.symbol = p.symbol
    JOIN this_monthly m ON a.symbol = m.symbol
    JOIN eps_hist e ON a.symbol = e.symbol
    LEFT JOIN quote_latest q ON a.symbol = q.symbol
    """
    t0 = time.perf_counter()
    out = pd.read_sql(sql, conn)
    print(
        f"[timing] main_sql {market} {year}/{month}: {time.perf_counter() - t0:.2f}s, rows={len(out)}"
    )

    for c in mctx["month_cols"]:
        if c not in out.columns:
            out[c] = np.nan

    symbol_universe = set(out["symbol"].astype(str).unique())
    # XBRL feature merge 不再用 try/except 包裹 — 失敗應直接 propagate。
    # 過去 silent skip 會讓樣本少掉 xbrl_* 特徵卻照常進 dataset_strategy.csv，
    # 屬於 silent feature degradation（與 train_eps 0049435 同類問題）。
    inc_codes = ["4000", "5900", "6300", "6900", "7900", "7950", "8200"]
    bs_codes = ["1100", "11XX", "21XX", "1XXX"]
    cf_codes = ["AAAA", "B02700"]

    t1 = time.perf_counter()
    inc_xbrl = pd.read_sql(
        f"""
        SELECT symbol, date, period_type, account_code, value_num, value_text
        FROM income_statement_xbrl
        WHERE date IN ('{pre_anchor_q}', '{anchor_q}')
          AND account_code IN ({",".join([f"'{c}'" for c in inc_codes])})
          AND symbol IN (SELECT symbol FROM stock_info WHERE market = '{market}')
        """,
        conn,
    )
    bs_xbrl = pd.read_sql(
        f"""
        SELECT symbol, date, period_type, account_code, value_num, value_text
        FROM balance_sheet_xbrl
        WHERE date = '{anchor_q}'
          AND account_code IN ({",".join([f"'{c}'" for c in bs_codes])})
          AND symbol IN (SELECT symbol FROM stock_info WHERE market = '{market}')
        """,
        conn,
    )
    cf_xbrl = pd.read_sql(
        f"""
        SELECT symbol, date, period_type, account_code, value_num, value_text
        FROM cash_flow_xbrl
        WHERE date IN ('{pre_anchor_q}', '{anchor_q}')
          AND account_code IN ({",".join([f"'{c}'" for c in cf_codes])})
          AND symbol IN (SELECT symbol FROM stock_info WHERE market = '{market}')
        """,
        conn,
    )
    print(
        f"[timing] xbrl_fetch {market} {year}/{month}: {time.perf_counter() - t1:.2f}s "
        f"(inc={len(inc_xbrl)}, bs={len(bs_xbrl)}, cf={len(cf_xbrl)})"
    )
    xbrl_features = tp.build_xbrl_feature_frame(
        inc_xbrl,
        bs_xbrl,
        cf_xbrl,
        pre_anchor_q=pre_anchor_q,
        anchor_q=anchor_q,
        symbols=symbol_universe,
    )
    t2 = time.perf_counter()
    out = out.merge(xbrl_features, on="symbol", how="left")
    print(
        f"[timing] xbrl_merge {market} {year}/{month}: {time.perf_counter() - t2:.2f}s"
    )

    return out


def compute_ttm_eps_by_month(df: pd.DataFrame, month: str) -> pd.Series:
    if month in {"02", "03", "04"}:
        cols = ["ly_q1_eps", "ly_q2_eps", "ly_q3_eps", "ly_q4_eps"]
    elif month in {"05", "06", "07"}:
        cols = ["ly_q2_eps", "ly_q3_eps", "ly_q4_eps", "ty_q1_eps"]
    elif month in {"08", "09", "10"}:
        cols = ["ly_q3_eps", "ly_q4_eps", "ty_q1_eps", "ty_q2_eps"]
    elif month in {"11", "12", "01"}:
        cols = ["ly_q4_eps", "ty_q1_eps", "ty_q2_eps", "anchor_eps"]
    else:
        return pd.Series(np.nan, index=df.index)
    return sum(pd.to_numeric(df.get(c), errors="coerce") for c in cols)


def main() -> None:
    args = parse_args()
    playbook_date = args.date or latest_playbook_date()
    if args.date is None:
        print(
            f"[auto] --date 未指定，使用最新 canonical playbook date: {playbook_date}"
        )
    year, month = year_month_from_playbook(playbook_date)
    cutoff_date = cutoff_date_from_playbook(playbook_date)
    model_features = tp.model_features_for_month(month)

    output_dir = (Path(__file__).resolve().parent / "output" / playbook_date).resolve()
    strategy_output_path = output_dir / "dataset_strategy.csv"

    frames: list[pd.DataFrame] = []
    t_all = time.perf_counter()
    engine = create_engine(get_db_url())
    with engine.connect() as conn:
        for market in tp.MARKETS:
            t_market = time.perf_counter()
            print(f"[start] fetch db: year={year}, market={market}, month={month}")
            y = fetch_one_year_live(conn, year, market, month, cutoff_date)
            if not y.empty:
                frames.append(y)
            print(
                f"[done] fetch db: year={year}, market={market}, month={month}, elapsed={time.perf_counter() - t_market:.2f}s"
            )

        industry_parts: list[pd.DataFrame] = []
        for market in tp.MARKETS:
            part = pd.read_sql(
                f"SELECT symbol, industry FROM stock_info WHERE market = '{market}'",
                conn,
            )
            if not part.empty:
                industry_parts.append(part[["symbol", "industry"]])

    if not frames:
        raise RuntimeError("No inference data fetched from DB.")

    df = pd.concat(frames, ignore_index=True)
    if industry_parts:
        industry_df = pd.concat(industry_parts, ignore_index=True).drop_duplicates(
            "symbol"
        )
        df = df.merge(industry_df, on="symbol", how="left")
    df["industry"] = df.get("industry", pd.Series(index=df.index)).fillna("unknown")

    df = df.replace([np.inf, -np.inf], np.nan)
    df["pre_anchor_margin"] = tp.safe_div_positive(
        df["pre_anchor_ni"], df["pre_anchor_rev"]
    )
    df["anchor_margin"] = tp.safe_div_positive(df["anchor_ni"], df["anchor_rev"])
    df["anchor_ocf_ratio"] = tp.safe_div_positive(
        df["anchor_ocf"], df["anchor_ni"]
    ).clip(-5, 5)
    df["anchor_re_ratio"] = tp.safe_div_positive(
        df["anchor_retained_earnings"], df["capital"]
    )
    df["margin_momentum"] = df["anchor_margin"] - df["pre_anchor_margin"]
    tp.add_month_features(df, month)

    df["ly_seasonality"] = tp.safe_div_positive(
        df["ly_target_eps"], df["ly_anchor_eps"]
    ).clip(-5, 5)
    df["anchor_yoy_eps"] = (
        tp.safe_div_positive(df["anchor_eps"], df["ly_anchor_eps"]) - 1
    ).clip(-5, 5)

    df["ttm_eps"] = compute_ttm_eps_by_month(df, month)
    df["target_eps"] = pd.to_numeric(df.get("target_eps"), errors="coerce")
    df["delta_eps"] = df["target_eps"] - pd.to_numeric(
        df.get("anchor_eps"), errors="coerce"
    )
    df["volume_lots"] = pd.to_numeric(df.get("quote_volume"), errors="coerce") / 1000.0
    df["avg_volume_lots_20d"] = (
        pd.to_numeric(df.get("avg_volume_20d"), errors="coerce") / 1000.0
    )
    df["pe_current"] = tp.safe_div_positive(df.get("close"), df["ttm_eps"])
    df["feature_cutoff_date"] = cutoff_date

    rows_before_pseudo_ttm_filter = len(df)
    # 不再 fillna(0)：缺 EPS ≠ EPS=0，silent 0-fill 會讓三季中只要有一季是 NaN
    # 的樣本被當作該季 EPS=0 計入 pseudo-TTM，可能誤判通過 MIN_PSEUDO_TTM_EPS。
    # NaN 經 sum 傳遞後產生 NaN；用 .fillna(False) 讓 NaN row 直接 fail filter。
    pseudo_ttm_eps_sum = (
        pd.to_numeric(df.get("ly_target_eps"), errors="coerce")
        + pd.to_numeric(df.get("pre_anchor_eps"), errors="coerce")
        + pd.to_numeric(df.get("anchor_eps"), errors="coerce")
    )
    df = df[(pseudo_ttm_eps_sum >= MIN_PSEUDO_TTM_EPS).fillna(False)].copy()
    rows_after_pseudo_ttm_filter = len(df)

    volume_ok = (
        pd.to_numeric(df.get("avg_volume_lots_20d"), errors="coerce")
        >= MIN_AVG20_VOLUME_LOTS
    )
    df = df[volume_ok.fillna(False)].copy()
    rows_after_volume_filter = len(df)

    # 不再 silent 補 NaN：model_features 都應該由前面的 SQL / add_month_features /
    # XBRL merge / Python 計算產生。若到這裡仍缺欄，代表上游 schema bug，
    # 該欄會 silent 變 NaN 進入 dataset_strategy.csv，掩蓋真正的問題。
    missing_model_features = [c for c in model_features if c not in df.columns]
    if missing_model_features:
        raise RuntimeError(
            f"step1 缺 train_eps model_features 欄位：{missing_model_features}。"
            "可能 SQL 沒回該欄、add_month_features 漏處理該月份、或 XBRL merge 沒產生 xbrl_* 欄。"
            "請修正上游後重跑，不要 silent 補 NaN。"
        )

    # 撈取籌碼流向特徵（外資／投信持股 + 股權集中度）
    symbols = df["symbol"].astype(str).str.strip().unique().tolist()
    chipflow = fetch_chipflow_features(engine, symbols, cutoff_date)
    df = df.merge(chipflow, on="symbol", how="left")

    # 撈取估值特徵（ROE、PE 百分位）
    valuation = fetch_valuation_features(engine, symbols, cutoff_date)
    df = df.merge(valuation, on="symbol", how="left")

    # 撈取市場情緒特徵（自營商持股、融資壓力、借券）
    sentiment = fetch_market_sentiment_features(engine, symbols, cutoff_date)
    df = df.merge(sentiment, on="symbol", how="left")

    # 撈取財報品質特徵（以 anchor_q 為基準，PIT 對齊）
    anchor_q = tp.build_quarter_context(year, month)["anchor_q"]
    fundamental = fetch_fundamental_features(engine, symbols, anchor_q)
    df = df.merge(fundamental, on="symbol", how="left")
    df["pb_ratio"] = tp.safe_div_positive(
        pd.to_numeric(df.get("close"), errors="coerce"),
        pd.to_numeric(df.get("nav_per_share"), errors="coerce"),
    )

    strategy_cols = [
        "symbol",
        "name",
        "industry",
        "year",
        "anchor_eps",
        "pe_current",
        "ttm_eps",
        "volume_lots",
        "avg_volume_lots_20d",
        "quote_date",
        "close",
        "ly_q1_eps",
        "ly_q2_eps",
        "ly_q3_eps",
        "ly_q4_eps",
        "ty_q1_eps",
        "ty_q2_eps",
        # 籌碼流向
        "foreign_held_ratio",
        "trust_held_ratio",
        "large_holder_ratio",
        "large_holder_ratio_wow",
        "large_holder_two_week_up",
        "mid_holder_ratio",
        "mid_holder_ratio_wow",
        "small_holder_ratio",
        "small_holder_ratio_wow",
        "concentration_spread",
        "concentration_spread_wow",
        # 估值
        "roe_official",
        "pe_percentile_official",
        # 市場情緒
        "dealer_held_ratio",
        "margin_usage_ratio",
        "short_cover_pressure",
        "sbl_sell_repay_ratio",
        # 財報品質
        "anchor_debt_ratio",
        "pb_ratio",
        "current_ratio",
        "eps_acc_yoy",
        "revenue_acc_yoy",
    ]
    strategy_existing = [c for c in strategy_cols if c in df.columns]
    strategy_out = (
        df[strategy_existing].copy().sort_values(["symbol"]).reset_index(drop=True)
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    strategy_out.to_csv(strategy_output_path, index=False)

    print("prepare_data (strategies) completed")
    print(f"- playbook_date: {playbook_date}")
    print(f"- cutoff_date: {cutoff_date}")
    print(f"- year/month: {year}/{month}")
    print(f"- strategy_output: {strategy_output_path}")
    print(f"- rows_strategy: {len(strategy_out)}")
    print(f"- rows_before_pseudo_ttm_filter: {rows_before_pseudo_ttm_filter}")
    print(f"- rows_after_pseudo_ttm_filter: {rows_after_pseudo_ttm_filter}")
    print(f"- rows_after_volume_filter: {rows_after_volume_filter}")
    print(
        f"- min_pseudo_ttm_eps: {MIN_PSEUDO_TTM_EPS} "
        f"(pseudo-TTM sum = ly_target_eps + pre_anchor_eps + anchor_eps)"
    )
    print(f"- min_avg20_volume_lots: {MIN_AVG20_VOLUME_LOTS} (近 20 交易日均量)")
    print(f"- model_feature_count: {len(model_features)}")
    print(f"- elapsed_total_sec: {time.perf_counter() - t_all:.2f}")


if __name__ == "__main__":
    main()
