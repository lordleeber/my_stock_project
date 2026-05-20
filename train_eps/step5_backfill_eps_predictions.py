"""一次性回填 eps_predictions 資料表：掃 models_eps/**/predictions_results.csv，
推導 predict_eps 後 bulk-insert 進 DB。

同一 (symbol, target_quarter) 跨月出現多個預測時，取 latest trained_at_month
（tie 時用 trained_at_date 細分）。

舊版 CSV（無 anchor_eps / predict_eps / trained_at_date）會：
  - 用 anchor_quarter join quarterly_reports_xbrl.eps_q 反推 anchor_eps
  - predict_eps = anchor_eps + pred_lgb_delta
  - trained_at_date 從 model_pkl 檔名時間戳推回

用法：
  venv/bin/python3 train_eps/step5_backfill_eps_predictions.py
  venv/bin/python3 train_eps/step5_backfill_eps_predictions.py --dry-run
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

_HERE = Path(__file__).resolve().parent
ROOT_DIR = _HERE.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from common.db import get_db_url

PKL_TIMESTAMP_RE = re.compile(r"^(\d{14})_(\d+\.\d+)\.pkl$")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Backfill eps_predictions from CSVs.")
    p.add_argument("--dry-run", action="store_true", help="不寫 DB，只印出結果統計")
    return p.parse_args()


def trained_at_date_from_pkl(pkl_name: str) -> str | None:
    if not isinstance(pkl_name, str):
        return None
    m = PKL_TIMESTAMP_RE.match(pkl_name)
    if not m:
        return None
    ts = m.group(1)
    return f"{ts[0:4]}/{ts[4:6]}/{ts[6:8]}"


def load_anchor_eps_lookup(engine) -> pd.DataFrame:
    """讀 quarterly_reports_xbrl.eps_q 作為 anchor_eps 的反推來源。"""
    sql = (
        "SELECT date AS anchor_quarter, symbol, eps_q AS anchor_eps_db "
        "FROM quarterly_reports_xbrl WHERE period_type = 'quarter'"
    )
    return pd.read_sql(sql, engine)


def gather_csvs() -> list[Path]:
    base = ROOT_DIR / "models_eps"
    if not base.exists():
        return []
    return sorted(base.glob("*/*/predictions_results.csv"))


def normalize_one_csv(path: Path, anchor_lookup: pd.DataFrame) -> pd.DataFrame:
    df = pd.read_csv(path)
    if "symbol" not in df.columns or "target_quarter" not in df.columns:
        raise RuntimeError(f"{path}: missing required columns symbol/target_quarter")

    df["symbol"] = df["symbol"].astype(str).str.zfill(4)

    if "anchor_quarter" not in df.columns:
        raise RuntimeError(
            f"{path}: missing anchor_quarter — cannot derive/verify anchor_eps"
        )
    df = df.merge(anchor_lookup, on=["symbol", "anchor_quarter"], how="left")
    if "anchor_eps" in df.columns:
        df["anchor_eps"] = df["anchor_eps"].fillna(df["anchor_eps_db"])
    else:
        df["anchor_eps"] = df["anchor_eps_db"]
    df = df.drop(columns=["anchor_eps_db"], errors="ignore")

    if "predict_eps" not in df.columns or df["predict_eps"].isna().all():
        if "pred_lgb_delta" not in df.columns:
            raise RuntimeError(f"{path}: missing pred_lgb_delta")
        df["predict_eps"] = pd.to_numeric(df["anchor_eps"], errors="coerce") + pd.to_numeric(
            df["pred_lgb_delta"], errors="coerce"
        )

    if "trained_at_date" not in df.columns or df["trained_at_date"].isna().all():
        if "model_pkl" not in df.columns:
            raise RuntimeError(f"{path}: missing model_pkl — cannot derive trained_at_date")
        df["trained_at_date"] = df["model_pkl"].map(trained_at_date_from_pkl)

    if "trained_at_month" not in df.columns:
        # 從路徑推回：models_eps/<year>/<month>/predictions_results.csv
        df["trained_at_month"] = f"{path.parent.parent.name}/{path.parent.name}"

    return df[
        ["symbol", "target_quarter", "predict_eps", "trained_at_month", "trained_at_date"]
    ]


def dedup_latest(combined: pd.DataFrame) -> pd.DataFrame:
    """同一 (symbol, target_quarter) 多筆時，取 latest trained_at_month；tie 用 trained_at_date。"""
    combined = combined.dropna(subset=["predict_eps"]).copy()
    combined["_sort_key"] = (
        combined["trained_at_month"].fillna("") + "|" + combined["trained_at_date"].fillna("")
    )
    combined = combined.sort_values("_sort_key").drop_duplicates(
        subset=["symbol", "target_quarter"], keep="last"
    )
    return combined.drop(columns="_sort_key")


def main() -> None:
    args = parse_args()

    csvs = gather_csvs()
    print(f"Found {len(csvs)} predictions_results.csv files.")

    engine = create_engine(get_db_url())

    if csvs:
        anchor_lookup = load_anchor_eps_lookup(engine)
        print(
            f"Loaded {len(anchor_lookup)} anchor_eps lookup rows from quarterly_reports_xbrl."
        )
        frames: list[pd.DataFrame] = []
        for p in csvs:
            try:
                frames.append(normalize_one_csv(p, anchor_lookup))
            except Exception as e:
                raise RuntimeError(f"Failed to normalize {p}: {e}") from e
        combined = pd.concat(frames, ignore_index=True)
        print(f"Combined raw rows: {len(combined)}")

        deduped = dedup_latest(combined)
        print(f"After dedup (latest per symbol+target_quarter): {len(deduped)}")

        deduped = deduped.rename(columns={"trained_at_date": "model_version"})
        deduped["created_at"] = datetime.now()
        payload = deduped[
            ["target_quarter", "symbol", "predict_eps", "model_version", "created_at"]
        ]
    else:
        print(
            "No CSVs found — will (re)create empty eps_predictions table so that "
            "calculate_valuation.py runs cleanly."
        )
        payload = pd.DataFrame(
            columns=[
                "target_quarter",
                "symbol",
                "predict_eps",
                "model_version",
                "created_at",
            ]
        )

    if args.dry_run:
        print("[dry-run] not writing DB")
        print(payload.head(10))
        return

    ddl = """
    CREATE TABLE IF NOT EXISTS eps_predictions (
        target_quarter TEXT NOT NULL,
        symbol TEXT NOT NULL,
        predict_eps DOUBLE PRECISION,
        model_version TEXT,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (target_quarter, symbol)
    )
    """
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS eps_predictions"))
        conn.execute(text(ddl))
        if not payload.empty:
            payload.to_sql(
                "eps_predictions",
                conn,
                if_exists="append",
                index=False,
                method="multi",
                chunksize=1000,
            )
    print(f"Backfilled eps_predictions with {len(payload)} rows.")


if __name__ == "__main__":
    main()
