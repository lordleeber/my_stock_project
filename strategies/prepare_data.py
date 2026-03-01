from __future__ import annotations

import argparse
import calendar
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import create_engine

# Ensure repo root is importable when running this script directly.
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from train_eps import prepare_data as tp


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare strategy inference dataset from DB.")
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=str, required=True, help="01~12")
    return parser.parse_args()


def model_release_date(year: int, month: str) -> str:
    m = int(month)
    # Release day convention: 05/08/11 on 15th, others on 10th.
    day = 15 if m in {5, 8, 11} else 10
    day = min(day, calendar.monthrange(year, m)[1])
    return f"{year:04d}-{m:02d}-{day:02d}"


def fetch_one_year_live(conn, year: int, market: str, month: str, cutoff_date: str) -> pd.DataFrame:
    qctx = tp.build_quarter_context(year, month)
    mctx = tp.monthly_context(year, month)

    target_year = qctx["target_year"]
    target_q = qctx["target_q"]
    prev_q = qctx["prev_q"]
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
    WITH anchor_data AS (
      SELECT
        '{market}' AS market,
        i.symbol,
        i.name,
        i.revenue_q AS anchor_rev,
        i.net_income_q AS anchor_ni,
        i.net_income_q / NULLIF(i.revenue_q, 0) AS anchor_margin,
        i.non_operating_income_q / NULLIF(i.pretax_income_q, 0) AS anchor_non_op_ratio,
        i.net_income_q / NULLIF(b.total_equity, 0) AS anchor_roe,
        b.total_liabilities / NULLIF(b.total_assets, 0) AS anchor_debt_ratio,
        b.share_capital AS capital,
        b.retained_earnings AS anchor_retained_earnings,
        c.cash_flow_operating_q AS anchor_ocf
      FROM income_statement i
      JOIN balance_sheet b ON i.symbol = b.symbol AND i.date = b.date
      JOIN cash_flow c ON i.symbol = c.symbol AND i.date = c.date
      WHERE i.date = '{anchor_q}' AND i.market = '{market}'
    ),
    prev_data AS (
      SELECT
        symbol,
        revenue_q AS prev_rev,
        net_income_q AS prev_ni,
        CASE WHEN revenue_q > 0 THEN net_income_q / revenue_q END AS prev_margin
      FROM income_statement
      WHERE date = '{prev_q}' AND market = '{market}'
    ),
    this_monthly AS (
      SELECT symbol, {','.join(mctx['sql_exprs'])}
      FROM monthly_revenue
      WHERE date IN ({','.join([f"'{d}'" for d in mctx['mr_dates']])})
      GROUP BY symbol
    ),
    eps_hist AS (
      SELECT
        qr.symbol,
        MAX(CASE WHEN qr.date = '{target_q}' THEN qr.eps_q END) AS target_eps,
        MAX(CASE WHEN qr.date = '{ly_target_q}' THEN qr.eps_q END) AS ly_target_eps,
        MAX(CASE WHEN qr.date = '{ly_anchor_q}' THEN qr.eps_q END) AS ly_anchor_eps,
        MAX(CASE WHEN qr.date = '{prev_q}' THEN qr.eps_q END) AS prev_eps,
        MAX(CASE WHEN qr.date = '{anchor_q}' THEN qr.eps_q END) AS anchor_eps,
        MAX(CASE WHEN qr.date = '{ly_q1}' THEN qr.eps_q END) AS ly_q1_eps,
        MAX(CASE WHEN qr.date = '{ly_q2}' THEN qr.eps_q END) AS ly_q2_eps,
        MAX(CASE WHEN qr.date = '{ly_q3}' THEN qr.eps_q END) AS ly_q3_eps,
        MAX(CASE WHEN qr.date = '{ly_q4}' THEN qr.eps_q END) AS ly_q4_eps,
        MAX(CASE WHEN qr.date = '{ly_q4}' THEN qr.eps_q END) AS prev_q4_eps,
        MAX(CASE WHEN qr.date = '{q1}' THEN qr.eps_q END) AS q1_eps,
        MAX(CASE WHEN qr.date = '{q2}' THEN qr.eps_q END) AS q2_eps
      FROM quarterly_reports qr
      WHERE qr.market = '{market}'
        AND qr.date IN ('{target_q}','{ly_target_q}','{ly_anchor_q}','{prev_q}','{anchor_q}','{ly_q1}','{ly_q2}','{ly_q3}','{ly_q4}','{q1}','{q2}')
      GROUP BY qr.symbol
    ),
    quote_latest AS (
      SELECT symbol, q3_date, q3_close, q3_volume
      FROM (
        SELECT
          d.symbol,
          d.date AS q3_date,
          d.close AS q3_close,
          d.volume AS q3_volume,
          ROW_NUMBER() OVER (PARTITION BY d.symbol ORDER BY d.date DESC) AS rn
        FROM daily_quotes d
        JOIN anchor_data a ON a.symbol = d.symbol
        WHERE d.market = '{market}' AND d.date <= '{cutoff_date}'
      ) z
      WHERE z.rn = 1
    )
    SELECT
      {target_year} AS year,
      a.*,
      p.prev_margin,
      p.prev_rev,
      p.prev_ni,
      {','.join([f'm.{c}' for c in mctx['month_cols']])},
      e.ly_target_eps,
      e.ly_anchor_eps,
      e.prev_eps,
      e.anchor_eps,
      e.target_eps,
      e.ly_q1_eps,
      e.ly_q2_eps,
      e.ly_q3_eps,
      e.ly_q4_eps,
      e.prev_q4_eps,
      e.q1_eps,
      e.q2_eps,
      q.q3_date,
      q.q3_close,
      q.q3_volume
    FROM anchor_data a
    LEFT JOIN prev_data p ON a.symbol = p.symbol
    JOIN this_monthly m ON a.symbol = m.symbol
    JOIN eps_hist e ON a.symbol = e.symbol
    LEFT JOIN quote_latest q ON a.symbol = q.symbol
    """
    t0 = time.perf_counter()
    out = pd.read_sql(sql, conn)
    print(f"[timing] main_sql {market} {year}/{month}: {time.perf_counter() - t0:.2f}s, rows={len(out)}")

    for c in mctx["month_cols"]:
        if c not in out.columns:
            out[c] = np.nan

    symbol_universe = set(out["symbol"].astype(str).unique())
    try:
        inc_codes = ["4000", "5900", "6300", "6900", "7900", "7950", "8200"]
        bs_codes = ["1100", "11XX", "21XX", "1XXX"]
        cf_codes = ["AAAA", "B02700"]

        t1 = time.perf_counter()
        inc_xbrl = pd.read_sql(
            f"""
            SELECT symbol, date, period_type, account_code, value_num, value_text
            FROM income_statement_xbrl
            WHERE date IN ('{prev_q}', '{anchor_q}')
              AND account_code IN ({','.join([f"'{c}'" for c in inc_codes])})
              AND symbol IN (SELECT symbol FROM stock_info WHERE market = '{market}')
            """,
            conn,
        )
        bs_xbrl = pd.read_sql(
            f"""
            SELECT symbol, date, period_type, account_code, value_num, value_text
            FROM balance_sheet_xbrl
            WHERE date = '{anchor_q}'
              AND account_code IN ({','.join([f"'{c}'" for c in bs_codes])})
              AND symbol IN (SELECT symbol FROM stock_info WHERE market = '{market}')
            """,
            conn,
        )
        cf_xbrl = pd.read_sql(
            f"""
            SELECT symbol, date, period_type, account_code, value_num, value_text
            FROM cash_flow_xbrl
            WHERE date IN ('{prev_q}', '{anchor_q}')
              AND account_code IN ({','.join([f"'{c}'" for c in cf_codes])})
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
            q2=prev_q,
            q3=anchor_q,
            symbols=symbol_universe,
        )
        t2 = time.perf_counter()
        out = out.merge(xbrl_features, on="symbol", how="left")
        print(f"[timing] xbrl_merge {market} {year}/{month}: {time.perf_counter() - t2:.2f}s")
    except Exception as exc:
        print(f"[WARN] skip XBRL feature merge (db) year={year} market={market}: {exc}")

    return out


def compute_ttm_official(df: pd.DataFrame, month: str) -> pd.Series:
    if month in {"05", "06", "07"}:
        cols = ["ly_q2_eps", "ly_q3_eps", "prev_q4_eps", "q1_eps"]
    elif month in {"08", "09", "10"}:
        cols = ["ly_q3_eps", "prev_q4_eps", "q1_eps", "q2_eps"]
    elif month in {"11", "12", "01"}:
        cols = ["ly_q4_eps", "q1_eps", "q2_eps", "anchor_eps"]
    elif month == "04":
        cols = ["ly_q1_eps", "ly_q2_eps", "ly_q3_eps", "ly_q4_eps"]
    else:
        return pd.Series(np.nan, index=df.index)
    return sum(pd.to_numeric(df.get(c), errors="coerce") for c in cols)


def main() -> None:
    args = parse_args()
    month = tp.normalize_month(args.month)
    if month in {"02", "03"}:
        raise RuntimeError(f"{month} 月暫不訓練/不推論")

    year = int(args.year)
    cutoff_date = model_release_date(year, month)
    model_features = tp.model_features_for_month(month)

    output_dir = (Path(__file__).resolve().parent / "output" / str(year) / month).resolve()
    model_output_path = output_dir / "dataset_model_input.csv"
    strategy_output_path = output_dir / "dataset_strategy.csv"

    frames: list[pd.DataFrame] = []
    t_all = time.perf_counter()
    engine = create_engine(tp.get_db_url())
    with engine.connect() as conn:
        for market in tp.MARKETS:
            t_market = time.perf_counter()
            print(f"[start] fetch db: year={year}, market={market}, month={month}")
            y = fetch_one_year_live(conn, year, market, month, cutoff_date)
            if not y.empty:
                frames.append(y)
            print(f"[done] fetch db: year={year}, market={market}, month={month}, elapsed={time.perf_counter() - t_market:.2f}s")

        industry_parts: list[pd.DataFrame] = []
        for market in tp.MARKETS:
            part = pd.read_sql(f"SELECT symbol, industry FROM stock_info WHERE market = '{market}'", conn)
            if not part.empty:
                industry_parts.append(part[["symbol", "industry"]])

    if not frames:
        raise RuntimeError("No inference data fetched from DB.")

    df = pd.concat(frames, ignore_index=True)
    if industry_parts:
        industry_df = pd.concat(industry_parts, ignore_index=True).drop_duplicates("symbol")
        df = df.merge(industry_df, on="symbol", how="left")
    df["industry"] = df.get("industry", pd.Series(index=df.index)).fillna("unknown")

    df = df.replace([np.inf, -np.inf], np.nan)
    df["prev_margin"] = tp.safe_div_positive(df["prev_ni"], df["prev_rev"])
    df["anchor_margin"] = tp.safe_div_positive(df["anchor_ni"], df["anchor_rev"])
    df["anchor_ocf_ratio"] = tp.safe_div_positive(df["anchor_ocf"], df["anchor_ni"]).clip(-5, 5)
    df["anchor_re_ratio"] = tp.safe_div_positive(df["anchor_retained_earnings"], df["capital"])
    df["margin_momentum"] = df["anchor_margin"] - df["prev_margin"]
    tp.add_month_features(df, month)

    df["ly_seasonality"] = tp.safe_div_positive(df["ly_target_eps"], df["ly_anchor_eps"]).clip(-5, 5)
    df["anchor_yoy_eps"] = (tp.safe_div_positive(df["anchor_eps"], df["ly_anchor_eps"]) - 1).clip(-5, 5)

    df["ttm_eps_official"] = compute_ttm_official(df, month)
    df["target_eps"] = pd.to_numeric(df.get("target_eps"), errors="coerce")
    df["delta_eps"] = df["target_eps"] - pd.to_numeric(df.get("anchor_eps"), errors="coerce")
    df["q2_eps_official"] = pd.to_numeric(df.get("q2_eps"), errors="coerce")
    df["target_volume"] = pd.to_numeric(df.get("q3_volume"), errors="coerce")
    df["pe_current"] = tp.safe_div_positive(df.get("q3_close"), df["ttm_eps_official"])
    df["feature_cutoff_date"] = cutoff_date

    rows_before_ttm_filter = len(df)
    ttm_eps_proxy = (
        pd.to_numeric(df.get("ly_target_eps"), errors="coerce").fillna(0)
        + pd.to_numeric(df.get("prev_eps"), errors="coerce").fillna(0)
        + pd.to_numeric(df.get("anchor_eps"), errors="coerce").fillna(0)
    )
    df = df[ttm_eps_proxy >= float(tp.MIN_TTM_EPS)].copy()
    rows_after_ttm_filter = len(df)

    for c in model_features:
        if c not in df.columns:
            df[c] = np.nan

    # Keep only fields used by build_candidates.py.
    strategy_cols = [
        "symbol",
        "name",
        "industry",
        "year",
        "anchor_eps",
        "pe_current",
        "ttm_eps_official",
        "target_volume",
        "q3_volume",
        "q3_date",
        "q3_close",
        "ly_q1_eps",
        "ly_q2_eps",
        "ly_q3_eps",
        "ly_q4_eps",
        "prev_q4_eps",
        "q1_eps",
        "q2_eps",
    ]
    strategy_existing = [c for c in strategy_cols if c in df.columns]
    strategy_out = df[strategy_existing].copy().sort_values(["symbol"]).reset_index(drop=True)

    # Enforce exact alignment with train_eps evaluate schema:
    # copy train_eps/output/<year>/<month>/dataset_evaluate.csv and remove labels.
    train_eval_path = (ROOT_DIR / "train_eps" / "output" / str(year) / month / "dataset_evaluate.csv").resolve()
    model_source = "train_eps/output dataset_evaluate.csv"
    if not train_eval_path.exists():
        raise FileNotFoundError(f"train_eps evaluate dataset not found: {train_eval_path}")
    train_eval = pd.read_csv(train_eval_path)
    selected_model_year = None
    if "year" in train_eval.columns:
        y = pd.to_numeric(train_eval["year"], errors="coerce")
        valid_years = y.dropna().astype(int)
        if valid_years.empty:
            raise RuntimeError(f"No valid year values found in: {train_eval_path}")
        selected_model_year = int(valid_years.max())
        train_eval = train_eval[y == selected_model_year].copy()
    model_out = train_eval.drop(columns=["target_eps", "delta_eps"], errors="ignore")
    model_out = model_out.sort_values(["symbol"]).reset_index(drop=True)

    output_dir.mkdir(parents=True, exist_ok=True)
    model_out.to_csv(model_output_path, index=False)
    strategy_out.to_csv(strategy_output_path, index=False)

    print("prepare_data (strategies) completed")
    print(f"- year: {year}")
    print(f"- month: {month}")
    print(f"- cutoff_date: {cutoff_date}")
    print(f"- model_output: {model_output_path}")
    print(f"- strategy_output: {strategy_output_path}")
    print(f"- model_source: {model_source}")
    if selected_model_year is not None:
        print(f"- model_input_year_selected: {selected_model_year}")
    print(f"- rows_model: {len(model_out)}")
    print(f"- rows_strategy: {len(strategy_out)}")
    print(f"- rows_before_ttm_filter: {rows_before_ttm_filter}")
    print(f"- rows_after_ttm_filter: {rows_after_ttm_filter}")
    print(f"- min_ttm_eps: {tp.MIN_TTM_EPS} (train_eps proxy: ly_target_eps + prev_eps + anchor_eps)")
    print(f"- model_feature_count: {len(model_features)}")
    print(f"- elapsed_total_sec: {time.perf_counter() - t_all:.2f}")


if __name__ == "__main__":
    main()
