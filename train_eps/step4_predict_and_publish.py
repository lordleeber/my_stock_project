import argparse
import pickle
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

from shared_config import parse_playbook_date, target_quarter_for_playbook
from common.db import get_db_url

EXCLUDE_COLUMNS = {
    "symbol",
    "name",
    "industry",
    "year",
    "anchor_quarter",
    "target_eps",
    "delta_eps",
}

PKL_TIMESTAMP_RE = re.compile(r"^(\d{14})_(\d+\.\d+)\.pkl$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Predict EPS delta, write predictions_results.csv, and publish to eps_predictions DB table"
    )
    parser.add_argument(
        "--date",
        type=str,
        required=True,
        help="Playbook release date YYYY-MM-DD (must be canonical: 5/8/11 月為 15 號，其餘月份為 10 號).",
    )
    return parser.parse_args()


def trained_at_date_from_pkl(pkl_name: str) -> str:
    """從 {YYYYMMDDHHMMSS}_{mae}.pkl 抽出 'YYYY-MM-DD'（pkl 實際產生那天，與 playbook_date 區分）。"""
    m = PKL_TIMESTAMP_RE.match(pkl_name)
    if not m:
        raise ValueError(f"Cannot parse trained_at_date from pkl name: {pkl_name}")
    ts = m.group(1)
    return f"{ts[0:4]}-{ts[4:6]}-{ts[6:8]}"


def ensure_eps_predictions_table(engine) -> None:
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
        conn.execute(text(ddl))


def publish_to_db(engine, df_pub: pd.DataFrame, target_quarter: str) -> int:
    """把單一 target_quarter 的預測寫入 eps_predictions：
    DELETE WHERE target_quarter=... → INSERT。
    回傳實際寫入的列數。"""
    ensure_eps_predictions_table(engine)
    payload = df_pub[
        ["target_quarter", "symbol", "predict_eps", "model_version", "created_at"]
    ].copy()
    payload = payload[payload["predict_eps"].notna()]
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM eps_predictions WHERE target_quarter = :tq"),
            {"tq": target_quarter},
        )
        if not payload.empty:
            payload.to_sql(
                "eps_predictions",
                conn,
                if_exists="append",
                index=False,
                method="multi",
                chunksize=1000,
            )
    return len(payload)


def main() -> None:
    args = parse_args()
    playbook_date = args.date
    year, month = parse_playbook_date(playbook_date)
    target_year, qnum = target_quarter_for_playbook(year, month)
    target_quarter = f"{target_year}Q{qnum}"

    input_path = (
        ROOT_DIR / "train_eps" / "output" / playbook_date / "dataset_evaluate.csv"
    ).resolve()
    models_dir = (ROOT_DIR / "models_eps" / playbook_date).resolve()
    output_path = (models_dir / "predictions_results.csv").resolve()

    if not input_path.exists():
        raise FileNotFoundError(f"dataset_evaluate.csv not found: {input_path}")

    candidates = []
    for p in models_dir.glob("*.pkl"):
        m = PKL_TIMESTAMP_RE.match(p.name)
        if m:
            candidates.append((float(m.group(2)), p))
    if not candidates:
        raise FileNotFoundError(
            f"No timestamped model pkl found in {models_dir}\n"
            f"Run: venv/bin/python3 train_eps/step2_train.py --date {playbook_date}"
        )
    model_path = min(candidates, key=lambda x: x[0])[1]
    trained_at_date = trained_at_date_from_pkl(model_path.name)

    with open(model_path, "rb") as f:
        model = pickle.load(f)

    df = pd.read_csv(input_path).replace([np.inf, -np.inf], np.nan)

    # 嚴格檢查：dataset 必須包含本次 playbook 要 predict 的 year（從 --date 解析出來）。
    # 過去版本若資料缺 year，會 silent fallback 到 max(year)，導致 May 2026 用 2025
    # 的 row 預測 2025Q2 而非 2026Q2，整份 predictions 錯一年。
    y = pd.to_numeric(df["year"], errors="coerce")
    valid_years = set(int(v) for v in y.dropna().astype(int).unique())
    if not valid_years:
        raise RuntimeError(f"No valid year values found in: {input_path}")
    if target_year not in valid_years:
        raise RuntimeError(
            f"dataset_evaluate.csv does not contain rows for year={target_year} "
            f"(found years: {sorted(valid_years)}). Re-run step1 prepare_data "
            f"for {playbook_date} — most likely upstream XBRL data for anchor "
            f"quarter is incomplete."
        )
    df = df[y == target_year].copy()

    if hasattr(model, "feature_names_in_"):
        feature_cols = list(model.feature_names_in_)
    else:
        feature_cols = [c for c in df.columns if c not in EXCLUDE_COLUMNS]

    missing = [c for c in feature_cols if c not in df.columns]
    if missing:
        raise RuntimeError(
            f"dataset_evaluate.csv missing feature columns expected by model: {missing}"
        )
    if "anchor_eps" not in df.columns:
        raise RuntimeError(
            f"dataset_evaluate.csv missing required column 'anchor_eps' for predict_eps derivation"
        )

    pred_delta = model.predict(df[feature_cols])

    out = df[["year", "symbol", "name", "industry"]].copy()
    if "target_eps" in df.columns:
        out["y_true"] = df["target_eps"]
    out["anchor_eps"] = df["anchor_eps"].to_numpy(dtype=float)
    out["pred_lgb_delta"] = pred_delta
    out["predict_eps"] = out["anchor_eps"] + out["pred_lgb_delta"]
    out["target_quarter"] = target_quarter
    if "anchor_quarter" in df.columns:
        out["anchor_quarter"] = df["anchor_quarter"].values
    out["playbook_date"] = playbook_date
    out["trained_at_date"] = trained_at_date
    out["model_pkl"] = model_path.name

    output_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(output_path, index=False)

    # ---- DB publish ----
    pub = out[["symbol", "predict_eps"]].copy()
    pub["target_quarter"] = target_quarter
    pub["model_version"] = trained_at_date
    pub["created_at"] = datetime.now()
    engine = create_engine(get_db_url())
    n_written = publish_to_db(engine, pub, target_quarter)

    print("predict_and_publish completed")
    print(f"- playbook_date: {playbook_date}")
    print(f"- target_quarter: {target_quarter}")
    print(f"- model: {model_path}")
    print(f"- trained_at_date: {trained_at_date}")
    print(f"- input: {input_path}")
    print(f"- output: {output_path}")
    print(f"- rows: {len(out)}")
    print(f"- db published to eps_predictions[{target_quarter}]: {n_written} rows")


if __name__ == "__main__":
    main()
