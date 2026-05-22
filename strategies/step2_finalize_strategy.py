"""
合併 EPS 預測、解析進場日並補充技術指標，完成當月策略資料集。

讀取：
  strategies/output/<YYYY-MM-DD>/dataset_strategy.csv
  models_eps/<YYYY-MM-DD>/predictions_results.csv

寫入：
  strategies/output/<YYYY-MM-DD>/dataset_strategy.csv  （原地更新，新增欄位）
  strategies/output/<YYYY-MM-DD>/trade_candidates.csv  （供 run_rolling.py 使用）

用法：
  venv/bin/python3 strategies/step2_finalize_strategy.py --date 2025-10-11
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from common.db import get_db_url
from strategies.shared_config import (
    cutoff_date_from_playbook,
    latest_playbook_date,
    year_month_from_playbook,
)

from strategies.feature_engineering import (
    fetch_technical_features,
    TECHNICAL_FEATURE_COLS,
    fetch_revenue_features,
    REVENUE_FEATURE_COLS,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Finalize strategy dataset and produce trade candidates."
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Playbook release date YYYY-MM-DD（省略則用 latest_playbook_date()）",
    )
    parser.add_argument(
        "--entry-date",
        type=str,
        default=None,
        help=(
            "YYYY-MM-DD override：跳過 daily_quotes 下個交易日驗證，直接使用此日期。"
            "用於 DB 尚未匯入下個交易日報價時提前產出 picks。"
            "技術/營收特徵仍以 <=entry_date 撈最新一筆，內容與 cutoff_date 一致。"
        ),
    )
    return parser.parse_args()


def resolve_entry_date(engine, earliest: date) -> str:
    """回傳 earliest 當天或之後第一個實際交易日。

    若 daily_quotes 沒有 >= earliest 的資料（通常代表 DB 還沒更新到該日期），
    直接 raise — 不要 silent fallback 到 calendar date，否則後續所有 quote /
    technical lookup 都會錯到非交易日。
    """
    earliest_str = earliest.strftime("%Y-%m-%d")
    stmt = text("SELECT MIN(date) FROM daily_quotes WHERE date >= :d")
    with engine.connect() as conn:
        row = conn.execute(stmt, {"d": earliest_str}).fetchone()
    if not (row and row[0]):
        raise RuntimeError(
            f"daily_quotes 沒有 >= {earliest_str} 的交易日資料 — "
            "可能 DB 未匯入該日期之後的報價，請先補資料再執行。"
        )
    return str(row[0])


def compute_eps_growth_components(df: pd.DataFrame, month: str) -> pd.DataFrame:
    """拆解預期 TTM EPS 成長為 base effect + ML 預測兩個獨立特徵。

    舊版 `pred_upside_pct` 公式代數展開為（close 完全消掉，本質不是 price upside）：
        pred_upside_pct = 100 × (anchor_eps − ttm_rolloff_eps) / ttm_eps     # base
                       + 100 × pred_lgb_delta / ttm_eps                       # ml

    其中 ttm_rolloff_eps 是這次 playbook 的 TTM 視窗即將踢出去的那季 EPS
    （月份對應與 step1 compute_ttm_eps_by_month 一致；rolloff 為負 = 去年同
    季虧損，會機械式拉高 base 項）。

    舊欄位把兩項加在一起 → 排序由 magnitude 大很多的 base 主導，selection
    model 看似倚重 ML 訊號實際上學的是 base effect。tools 中 audit 結論：
    58 cohort Spearman(pred_upside_pct, ml_component) median ≈ 0.034，
    base 解釋 ~85% 的排序變異。拆成兩欄位後 selection model 看到的訊號可
    歸因（哪部分是會計、哪部分是 EPS model）。
    """
    df = df.copy()

    if month in {"05", "06", "07"}:
        rolloff = pd.to_numeric(df.get("ly_q2_eps"), errors="coerce")
    elif month in {"08", "09", "10"}:
        rolloff = pd.to_numeric(df.get("ly_q3_eps"), errors="coerce")
    elif month in {"11", "12", "01"}:
        rolloff = pd.to_numeric(df.get("ly_q4_eps"), errors="coerce")
    else:
        rolloff = pd.to_numeric(df.get("ly_q1_eps"), errors="coerce")

    anchor = pd.to_numeric(df.get("anchor_eps"), errors="coerce")
    pred_delta = pd.to_numeric(df.get("pred_lgb_delta"), errors="coerce")
    ttm = pd.to_numeric(df.get("ttm_eps"), errors="coerce")

    df["base_eps_growth_pct"] = 100.0 * (anchor - rolloff) / ttm
    df["ml_eps_delta_pct"] = 100.0 * pred_delta / ttm
    # base / ml 兩特徵 Spearman ≈ −0.5（高 base 通常伴隨負 ml；ML model 對極端
    # anchor 預測 mean reversion）。LightGBM 學「兩特徵的和」靠 tree splits
    # 拼湊需要更多分裂、效率較差，所以額外提供加總後的 smoothed 訊號，讓
    # selection model 自己決定 weight。
    df["eps_growth_total_pct"] = df["base_eps_growth_pct"] + df["ml_eps_delta_pct"]
    return df


def main() -> None:
    args = parse_args()
    playbook_date = args.date or latest_playbook_date()
    if args.date is None:
        print(
            f"[auto] --date 未指定，使用最新 canonical playbook date: {playbook_date}"
        )
    year, month = year_month_from_playbook(playbook_date)
    cutoff_date = cutoff_date_from_playbook(playbook_date)

    out_dir = (ROOT_DIR / "strategies" / "output" / playbook_date).resolve()
    strategy_path = out_dir / "dataset_strategy.csv"
    pred_path = (
        ROOT_DIR / "models_eps" / playbook_date / "predictions_results.csv"
    ).resolve()
    candidates_path = out_dir / "trade_candidates.csv"

    if not strategy_path.exists():
        raise FileNotFoundError(
            f"dataset_strategy.csv not found: {strategy_path}\nRun prepare_data.py first."
        )
    if not pred_path.exists():
        raise FileNotFoundError(
            f"predictions_results.csv not found: {pred_path}\nRun predict_and_publish.py first."
        )

    ds = pd.read_csv(strategy_path)
    pred = pd.read_csv(pred_path)

    ds["symbol"] = ds["symbol"].astype(str).str.strip()
    pred["symbol"] = pred["symbol"].astype(str).str.strip()

    # 刪除先前計算過的欄位，確保重跑時結果一致（idempotent）。
    RECOMPUTED_COLS = (
        [
            "pred_lgb_delta",
            "base_eps_growth_pct",
            "ml_eps_delta_pct",
            "eps_growth_total_pct",
            "entry_date",
        ]
        + TECHNICAL_FEATURE_COLS
        + REVENUE_FEATURE_COLS
    )
    ds = ds.drop(columns=[c for c in RECOMPUTED_COLS if c in ds.columns])

    # 只保留預測檔的 pred_lgb_delta（其他欄位已在 ds 中）。
    pred_cols = ["symbol", "pred_lgb_delta"]
    pred_merge = pred[[c for c in pred_cols if c in pred.columns]].drop_duplicates(
        "symbol"
    )

    df = ds.merge(pred_merge, on="symbol", how="left")
    df = compute_eps_growth_components(df, month)

    # 解析進場日。
    engine = create_engine(get_db_url())
    if args.entry_date:
        try:
            datetime.strptime(args.entry_date, "%Y-%m-%d")
        except ValueError as exc:
            raise SystemExit(f"--entry-date 格式錯誤，需 YYYY-MM-DD: {exc}") from exc
        entry_date_str = args.entry_date
        print(f"entry_date: {entry_date_str} (override via --entry-date)")
    else:
        # cutoff_date = 公告日；下一個交易日（含當天）作為進場日候選。
        # daily_quotes 查詢用 `>= cutoff + 1 day` 找下個實際交易日。
        earliest = date.fromisoformat(cutoff_date) + timedelta(days=1)
        entry_date_str = resolve_entry_date(engine, earliest)
        print(f"entry_date: {entry_date_str}")
    df["entry_date"] = entry_date_str

    # 撈取 entry_date 的技術指標特徵。
    symbols = df["symbol"].tolist()
    close_s = pd.to_numeric(df.set_index("symbol")["close"], errors="coerce")
    # volume_lots 在 csv 內為單位「張」，技術指標 vma* 以「股」為單位，這裡轉回股數。
    volume_s = (
        pd.to_numeric(df.set_index("symbol")["volume_lots"], errors="coerce") * 1000.0
    )
    tech = fetch_technical_features(
        symbols, entry_date_str, close_series=close_s, volume_series=volume_s
    )
    # 刪除 df 中已存在的技術指標欄位，避免重複。
    existing_tech = [c for c in TECHNICAL_FEATURE_COLS if c in df.columns]
    if existing_tech:
        df = df.drop(columns=existing_tech)
    df = df.merge(tech, on="symbol", how="left")
    print(f"Technical features added: {len(TECHNICAL_FEATURE_COLS)} cols")

    # 撈取 entry_date 的月營收特徵（透過 publish_time 過濾，確保 PIT 安全）。
    rev = fetch_revenue_features(symbols, entry_date_str)
    existing_rev = [c for c in REVENUE_FEATURE_COLS if c in df.columns]
    if existing_rev:
        df = df.drop(columns=existing_rev)
    df = df.merge(rev, on="symbol", how="left")
    n_rev = df[REVENUE_FEATURE_COLS].notna().any(axis=1).sum()
    print(
        f"Revenue features added: {len(REVENUE_FEATURE_COLS)} cols  ({n_rev}/{len(df)} symbols with data)"
    )

    # close / ttm_eps / volume_lots 由 step1 emit 為 canonical 欄位，
    # step2 不再加同義別名（避免兩個入口同一份資料）。

    # 寫入更新後的 dataset_strategy.csv。
    df.to_csv(strategy_path, index=False, encoding="utf-8-sig")
    print(f"dataset_strategy.csv updated: {strategy_path}  ({len(df)} rows)")

    # 寫入 trade_candidates.csv。排序語意保留為「下季 TTM EPS 預期成長 > 0」
    # （= base + ml > 0，與舊版 pred_upside_pct > 0 數學等價），但同時暴露
    # base / ml 兩欄方便歸因。
    tc_cols = [
        "symbol",
        "close",
        "entry_date",
        "base_eps_growth_pct",
        "ml_eps_delta_pct",
        "eps_growth_total_pct",
    ]
    tc = df[[c for c in tc_cols if c in df.columns]].copy()
    valid = (
        tc["base_eps_growth_pct"].notna()
        & tc["ml_eps_delta_pct"].notna()
        & tc["close"].notna()
        & tc["close"].gt(0)
        & tc["eps_growth_total_pct"].gt(0)
    )
    tc = tc[valid].sort_values("eps_growth_total_pct", ascending=False).reset_index(drop=True)
    tc.to_csv(candidates_path, index=False, encoding="utf-8-sig")

    print(f"trade_candidates.csv written: {candidates_path}  ({len(tc)} rows)")
    print("\nTop 10 by eps_growth_total_pct (= base + ml):")
    print(tc.head(10).to_string(index=False))

    print("\nfinalize_strategy done")
    print(f"- playbook_date: {playbook_date}  (cutoff_date {cutoff_date})")
    print(f"- year/month: {year}/{month}")
    print(f"- strategy rows: {len(df)}")
    print(f"- trade_candidates rows: {len(tc)}")


if __name__ == "__main__":
    main()
