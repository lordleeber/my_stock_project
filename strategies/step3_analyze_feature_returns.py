"""
分析哪些特徵與實際 1 個月遠期報酬相關。

對每個 playbook date D：
  - 載入 strategies/output/<D>/dataset_strategy.csv（所有候選股的特徵，含技術指標）
  - 以 entry_date 開盤買入，下個 playbook date entry_date 開盤賣出
  - 計算實際報酬，再與各特徵做相關性分析

輸出：
  - strategies/output/feature_return_analysis.csv  （每股每 cohort 的特徵與報酬）
  - strategies/output/feature_correlation.csv       （相關性彙總）
  - 終端機：各特徵的五分位數分析
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import bindparam, create_engine, text

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from common.db import get_db_url

from strategies.feature_engineering import TECHNICAL_FEATURE_COLS, REVENUE_FEATURE_COLS
from strategies.shared_config import (
    MONTH_TO_TARGET_QNUM,
    parse_playbook_date,
    playbook_run_date,
)

STRATEGIES_OUT = (ROOT_DIR / "strategies" / "output").resolve()

START = "2021-08-16"


def _resolve_end() -> str:
    """掃 strategies/output/ 自動算 END = 最後一個可算下月遠期報酬的 cohort。

    遠期報酬需要「下個 cohort 的 entry_date」，所以 END = 倒數第二個 dataset_strategy.csv 存在的 cohort。

    例：今天 2026-05-22，strategies/output/ 最新兩個 cohort 是 2026-04-11 和 2026-05-16。
        2026-05-16 的下個是 2026-06-11（尚未產出，月營收 6/10 才公告），剔除；
        2026-04-11 的下個是 2026-05-16（已存在），留下 → END = 2026-04-11。
        等 6/11 跑完 2026-06-11 的 step1+2，重跑 step3 會自動推進到 END = 2026-05-16。
    """
    if not STRATEGIES_OUT.exists():
        raise SystemExit(f"strategies/output not found: {STRATEGIES_OUT}")
    cohorts: list[str] = []
    for d in STRATEGIES_OUT.iterdir():
        if not (d.is_dir() and (d / "dataset_strategy.csv").exists()):
            continue
        try:
            parse_playbook_date(d.name)
        except ValueError:
            continue
        cohorts.append(d.name)
    if len(cohorts) < 2:
        raise SystemExit(
            "Need ≥2 cohorts with dataset_strategy.csv to compute fwd_return; "
            f"found {len(cohorts)} in {STRATEGIES_OUT}"
        )
    cohorts.sort()
    return cohorts[-2]


END = _resolve_end()

FEATURE_COLS = (
    [
        "base_eps_growth_pct",
        "ml_eps_delta_pct",
        "eps_growth_total_pct",
        "pe_current",
        "ttm_eps",
        "volume_lots",
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
    ]
    + TECHNICAL_FEATURE_COLS
    + REVENUE_FEATURE_COLS
)


def playbook_dates_in_range(start: str, end: str) -> list[str]:
    """產生 [start, end] 區間內所有 canonical playbook run dates。"""
    sy, sm = parse_playbook_date(start)
    ey, em = parse_playbook_date(end)
    out: list[str] = []
    y, m = sy, int(sm)
    while (y, m) <= (ey, int(em)):
        mm = f"{m:02d}"
        if mm in MONTH_TO_TARGET_QNUM:
            out.append(playbook_run_date(y, mm))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return out


def next_playbook_date(playbook_date: str) -> str:
    y, m = parse_playbook_date(playbook_date)
    nm = int(m) + 1
    ny = y
    if nm > 12:
        nm = 1
        ny += 1
    return playbook_run_date(ny, f"{nm:02d}")


def load_strategy(playbook_date: str) -> pd.DataFrame | None:
    p = STRATEGIES_OUT / playbook_date / "dataset_strategy.csv"
    if not p.exists():
        return None
    df = pd.read_csv(p)
    df["symbol"] = df["symbol"].astype(str).str.strip()
    return df


def prev_trading_day(engine, date_str: str) -> str:
    """Return the last trading day strictly before date_str.

    若 daily_quotes 沒有 < date_str 的資料，直接 raise — 不要 silent fallback
    到 date_str 本身（會是同一天甚至未來日，下游 exit_open 撈出的價格錯誤）。
    """
    stmt = text("SELECT MAX(date) FROM daily_quotes WHERE date < :d")
    with engine.connect() as conn:
        result = conn.execute(stmt, {"d": date_str}).scalar()
    if not result:
        raise RuntimeError(
            f"daily_quotes 沒有 < {date_str} 的交易日資料 — "
            "可能 DB 未匯入該日期之前的報價，無法決定 exit_date。"
        )
    return str(result)


def fetch_open_prices(engine, symbols: list[str], date_str: str) -> dict[str, float]:
    """Return {symbol: open_price} for the first trading day on or after date_str."""
    from datetime import date, timedelta

    end_date = (date.fromisoformat(date_str) + timedelta(days=7)).strftime("%Y-%m-%d")
    stmt = text(
        """
        WITH ranked AS (
            SELECT symbol, date, open,
                   ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date ASC) AS rn
            FROM daily_quotes
            WHERE symbol IN :symbols
              AND date >= :date_str
              AND date <= :end_date
              AND open IS NOT NULL AND open > 0
        )
        SELECT symbol, open FROM ranked WHERE rn = 1
        """
    ).bindparams(bindparam("symbols", expanding=True))
    with engine.connect() as conn:
        df = pd.read_sql(
            stmt,
            conn,
            params={"symbols": symbols, "date_str": date_str, "end_date": end_date},
        )
    if df.empty:
        return {}
    df["symbol"] = df["symbol"].astype(str).str.strip()
    return dict(zip(df["symbol"], pd.to_numeric(df["open"], errors="coerce")))


def main() -> None:
    records: list[dict] = []
    engine = create_engine(get_db_url())

    for d in playbook_dates_in_range(START, END):
        year, month_s = parse_playbook_date(d)
        next_d = next_playbook_date(d)

        # END 已 auto-detect 到倒數第二個 cohort（_resolve_end），所以區間內每個 cohort
        # 與其下一個 cohort 的 dataset_strategy.csv 都應存在；中間缺檔代表 step1+2 沒跑齊，
        # 直接 raise 不要 silent skip 製造資料漏洞。
        ds = load_strategy(d)
        if ds is None or ds.empty:
            raise SystemExit(
                f"[FAIL] {d}: dataset_strategy.csv missing or empty — "
                f"run strategies/step1_prepare_data.py --date {d}"
            )

        if "entry_date" not in ds.columns or ds["entry_date"].isna().all():
            raise SystemExit(
                f"[FAIL] {d}: entry_date missing in dataset_strategy.csv — "
                f"step1 output is corrupt, re-run for this date"
            )

        entry_str = str(ds["entry_date"].iloc[0])

        # 出場日 = 下一個 playbook date 的 entry_date 前一個交易日
        ds_next = load_strategy(next_d)
        if ds_next is None or ds_next.empty or "entry_date" not in ds_next.columns:
            raise SystemExit(
                f"[FAIL] {d}: next-cohort dataset_strategy.csv missing at {next_d} — "
                f"run strategies/step1_prepare_data.py --date {next_d}"
            )
        exit_str = prev_trading_day(engine, str(ds_next["entry_date"].iloc[0]))

        symbols = ds["symbol"].tolist()
        entry_opens = fetch_open_prices(engine, symbols, entry_str)
        exit_opens = fetch_open_prices(engine, symbols, exit_str)

        hit = 0
        for _, row in ds.iterrows():
            sym = row["symbol"]
            entry_open = entry_opens.get(sym)
            exit_open = exit_opens.get(sym)
            if not entry_open or not exit_open or entry_open <= 0:
                continue
            fwd_return = (exit_open - entry_open) / entry_open * 100.0
            rec = {
                "playbook_date": d,
                "year": year,
                "month": month_s,
                "symbol": sym,
                "entry_date": entry_str,
                "exit_date": exit_str,
                "entry_open": round(entry_open, 2),
                "exit_open": round(exit_open, 2),
                "fwd_return_pct": round(fwd_return, 4),
            }
            for feat in FEATURE_COLS:
                if feat in row.index:
                    rec[feat] = row[feat]
            records.append(rec)
            hit += 1

        print(
            f"[{d}] entry={entry_str} exit={exit_str}  candidates={len(ds)}  matched={hit}"
        )

    if not records:
        print("No records collected.")
        return

    df = pd.DataFrame(records)
    all_features = [c for c in FEATURE_COLS if c in df.columns]

    # ── Feature correlation table ────────────────────────────────────────────
    corr_rows = []
    for feat in all_features:
        col = pd.to_numeric(df[feat], errors="coerce")
        valid = df[col.notna()].copy()
        valid["_feat"] = col[col.notna()]
        if valid.empty or valid["_feat"].std() == 0:
            continue
        pearson = valid["_feat"].corr(valid["fwd_return_pct"])
        spearman = valid["_feat"].corr(valid["fwd_return_pct"], method="spearman")
        corr_rows.append(
            {
                "feature": feat,
                "n": len(valid),
                "pearson_r": round(pearson, 4),
                "spearman_r": round(spearman, 4),
            }
        )

    corr_df = pd.DataFrame(corr_rows).sort_values("spearman_r", ascending=False)

    print("\n" + "=" * 60)
    print("Feature vs 1-Month Forward Return Correlation")
    print("=" * 60)
    print(corr_df.to_string(index=False))

    # ── Quintile analysis ───────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("Quintile Analysis (Q1=lowest, Q5=highest feature value)")
    print("=" * 60)
    for feat in corr_df["feature"].tolist():
        col = pd.to_numeric(df[feat], errors="coerce")
        valid = df[col.notna()].copy()
        valid["_feat"] = col[col.notna()]
        if len(valid) < 20:
            continue
        try:
            valid["quintile"] = pd.qcut(
                valid["_feat"],
                5,
                labels=["Q1", "Q2", "Q3", "Q4", "Q5"],
                duplicates="drop",
            )
        except Exception:
            continue
        qt = (
            valid.groupby("quintile", observed=True)["fwd_return_pct"]
            .agg(["mean", "median", "count"])
            .round(3)
        )
        print(f"\n{feat}:")
        print(qt.to_string())

    # ── Save outputs ────────────────────────────────────────────────────────
    df.to_csv(
        STRATEGIES_OUT / "feature_return_analysis.csv",
        index=False,
        encoding="utf-8-sig",
    )
    corr_df.to_csv(
        STRATEGIES_OUT / "feature_correlation.csv", index=False, encoding="utf-8-sig"
    )
    print("\nSaved:")
    print(f"  {STRATEGIES_OUT / 'feature_return_analysis.csv'}  ({len(df)} rows)")
    print(f"  {STRATEGIES_OUT / 'feature_correlation.csv'}")


if __name__ == "__main__":
    main()
