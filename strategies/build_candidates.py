import argparse
from datetime import date, timedelta
from pathlib import Path

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build trade candidates using year/month paths.")
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=str, required=True, help="e.g. 09")
    parser.add_argument("--min-volume-lots", type=float, default=200.0)
    return parser.parse_args()


def strategy_release_and_entry_dates(year: int, month: str) -> tuple[date, date]:
    m_int = int(month)
    release_day = 15 if m_int in {5, 8, 11} else 10
    release_dt = date(year, m_int, release_day)
    earliest_entry_dt = release_dt + timedelta(days=1)
    return release_dt, earliest_entry_dt


def main() -> None:
    args = parse_args()
    year = int(args.year)
    month = str(args.month).zfill(2)

    default_pred = (Path.cwd() / "strategies" / "output" / f"{year:04d}" / month / "predictions_published.csv").resolve()
    default_ds = (Path.cwd() / "strategies" / "output" / f"{year:04d}" / month / "dataset_strategy.csv").resolve()
    output_path = (Path.cwd() / "strategies" / "output" / f"{year:04d}" / month / "trade_candidates.csv").resolve()

    pred_path = default_pred
    ds_path = default_ds
    if not pred_path.exists():
        raise FileNotFoundError(f"predictions not found: {pred_path}")
    if not ds_path.exists():
        raise FileNotFoundError(f"dataset not found: {ds_path}")

    pred = pd.read_csv(pred_path)
    ds = pd.read_csv(ds_path)

    pred_year = pred[pred["fold"] == f"year_{year}"].copy()
    ds_year = ds[ds["year"].astype(int) == year].copy()

    use_cols = [
        "symbol",
        "name",
        "industry",
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
        "q1_eps",
        "q2_eps",
    ]
    ds_year = ds_year[[c for c in use_cols if c in ds_year.columns]].copy()

    df = pred_year.merge(ds_year, on="symbol", how="left", suffixes=("", "_ds"))
    # Keep a single set of display columns; drop duplicated *_ds columns from merge.
    for col in ["name", "industry"]:
        ds_col = f"{col}_ds"
        if col not in df.columns and ds_col in df.columns:
            df[col] = df[ds_col]
        if ds_col in df.columns:
            df = df.drop(columns=[ds_col])
    df["symbol"] = df["symbol"].astype(str).str.strip()

    anchor = pd.to_numeric(df.get("anchor_eps", 0), errors="coerce")
    pred_col = "pred_lgb_delta" if "pred_lgb_delta" in df.columns else "pred_rf_delta"
    pred_delta = pd.to_numeric(df[pred_col], errors="coerce")
    df["predict_target_eps"] = anchor + pred_delta

    # 統一讀取 prepare_data.py 已嚴謹計算好的最近四季真實 EPS
    df["ttm_eps_official_live"] = pd.to_numeric(df.get("ttm_eps_official", 0), errors="coerce")

    # 為什麼不直接用 evaluate.py 或 predict_published.py 裡算好的 ttm_eps_forward？
    #
    # evaluate.py（回測用）的公式是：
    #   ttm_forward = ttm_official - target_eps（真實季EPS）+ pred_eps
    # 這公式在回測時可以用，因為訓練資料裡有「已知的真實 target_eps」可以拿來相減。
    # 但在此處（真實預測階段），「target_eps 尚未公布」，根本無法取得，
    # 所以不能重用 evaluate 的公式或其輸出欄位。
    #
    # predict_published.py 輸出的 predictions_published.csv 也沒有計算 ttm_eps_forward，
    # 它只輸出 pred_rf_delta（預測 EPS 變化量），需要在此處自行合成 Forward TTM。
    #
    # 正確做法：
    #   TTM 是最近四季加總，預測本季後，應「替換掉最舊的那一季（LY-Qx）」来得到 Forward TTM。
    # 月份視角決定「最舊一季」:
    #   05~07 預測 Q2 → TTM = [LY-Q2, LY-Q3, LY-Q4, Q1]    → 替換最舊一季 ly_q2_eps
    #   08~10 預測 Q3 → TTM = [LY-Q3, LY-Q4,  Q1,  Q2]    → 替換最舊一季 ly_q3_eps
    #   11~01 預測 Q4 → TTM = [LY-Q4,  Q1,   Q2,  Q3]    → 替換最舊一季 ly_q4_eps
    #   04    預測 Q1 → TTM = [LY-Q1, LY-Q2, LY-Q3, LY-Q4] → 替換最舊一季 ly_q1_eps
    if month in {"05", "06", "07"}:
        oldest_q_eps = pd.to_numeric(df.get("ly_q2_eps", float("nan")), errors="coerce")
    elif month in {"08", "09", "10"}:
        oldest_q_eps = pd.to_numeric(df.get("ly_q3_eps", float("nan")), errors="coerce")
    elif month in {"11", "12", "01"}:
        oldest_q_eps = pd.to_numeric(df.get("ly_q4_eps", float("nan")), errors="coerce")
    else:
        oldest_q_eps = pd.to_numeric(df.get("ly_q1_eps", float("nan")), errors="coerce")

    df["ttm_eps_forward_live"] = df["ttm_eps_official_live"] - oldest_q_eps + df["predict_target_eps"]

    df["predict_target_price_live"] = pd.to_numeric(df.get("pe_current"), errors="coerce") * df["predict_target_eps"]
    df["volume_lots"] = pd.to_numeric(df.get("target_volume", df.get("q3_volume")), errors="coerce") / 1000.0

    vol_ok = df["volume_lots"] >= float(args.min_volume_lots)
    forward_not_worse = df["ttm_eps_forward_live"] >= df["ttm_eps_official_live"]

    out = df[vol_ok & forward_not_worse].copy()
    out = out.sort_values(["symbol"]).reset_index(drop=True)
    if "fold" in out.columns:
        out = out.drop(columns=["fold"])
    out = out.rename(
        columns={
            "q3_date": "date",
            "q3_close": "close",
            "q3_volume": "volume",
            "predict_target_price_live": "predict_target_price",
        }
    )

    _, earliest_entry_dt = strategy_release_and_entry_dates(year, month)
    out["entry_date"] = earliest_entry_dt.strftime("%Y-%m-%d")

    minimal_cols = ["symbol", "predict_target_price", "close", "entry_date"]
    out = out[[c for c in minimal_cols if c in out.columns]].copy()

    num_cols = out.select_dtypes(include=["number"]).columns.tolist()
    if num_cols:
        out[num_cols] = out[num_cols].round(2)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(output_path, index=False)

    print("build_candidates done")
    print(f"- year: {year}")
    print(f"- month: {month}")
    print(f"- predictions: {pred_path}")
    print(f"- dataset: {ds_path}")
    print(f"- output: {output_path}")
    print(f"- rows: {len(out)}")


if __name__ == "__main__":
    main()
