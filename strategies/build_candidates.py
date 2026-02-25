import argparse
from pathlib import Path

import pandas as pd
import requests


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build trade candidates using market/year/month paths.")
    parser.add_argument("--market", type=str, default="sii", choices=["sii", "otc"])
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=str, required=True, help="e.g. 09")
    parser.add_argument("--min-ttm-eps", type=float, default=2.0)
    parser.add_argument("--min-volume-lots", type=float, default=500.0)
    parser.add_argument("--api-base", type=str, default="http://100.103.191.79:8000")
    return parser.parse_args()


def fetch_revenue_publish_dates(
    api_base: str,
    market: str,
    year: int,
    month: str,
    symbols: list[str],
    fallback_day: str = "10",
) -> dict[str, str]:
    """
    Fetch the actual publish date (publish_time) of monthly revenue for each symbol.

    month=09 means the strategy uses August monthly revenue (published in early September).
    We query start_date=YYYY-1M{prev_month}M, i.e. 2025M08.

    NOTE: The API requires a 'symbol' parameter to return results;
          querying by market only returns an empty list.
          We therefore query each symbol individually.

    Returns:
        dict[symbol → "YYYY-MM-DD"]
        Fallback to {year}-{month}-{fallback_day} if not found.
    """
    # compute the revenue month: model month 09 → 8月營收 → 2025M08
    rev_month = int(month) - 1
    if rev_month == 0:
        rev_year = year - 1
        rev_month = 12
    else:
        rev_year = year
    date_str = f"{rev_year}M{rev_month:02d}"

    fallback = f"{year}-{month}-{fallback_day}"
    result: dict[str, str] = {}
    found = 0

    for sym in symbols:
        try:
            resp = requests.get(
                f"{api_base.rstrip('/')}/raw/monthly-revenue",
                params={"start_date": date_str, "end_date": date_str, "symbol": sym, "limit": 5},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            result[sym] = fallback
            continue

        if not data:
            result[sym] = fallback
            continue

        pt = data[0].get("publish_time")
        if pt:
            pt_str = str(pt).strip()
            if len(pt_str) == 8 and pt_str.isdigit():
                result[sym] = f"{pt_str[:4]}-{pt_str[4:6]}-{pt_str[6:8]}"
                found += 1
            else:
                result[sym] = fallback
        else:
            result[sym] = fallback

    print(f"[info] publish_date: {found}/{len(symbols)} symbols found (revenue month: {date_str}), fallback={fallback}")
    return result


def main() -> None:
    args = parse_args()
    market = args.market
    year = int(args.year)
    month = str(args.month).zfill(2)

    default_pred = (Path.cwd() / "strategies" / market / f"{year:04d}" / month / "predictions_published.csv").resolve()
    default_ds = (Path.cwd() / "train_eps" / market / f"{year:04d}" / month / "dataset_evaluate.csv").resolve()
    output_path = (Path.cwd() / "strategies" / market / f"{year:04d}" / month / "trade_candidates.csv").resolve()

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
        "ly_q2_eps",
        "ly_q3_eps",
        "prev_q4_eps",
        "q1_eps",
        "q2_eps",
        "q2_eps_official",
    ]
    ds_year = ds_year[[c for c in use_cols if c in ds_year.columns]].copy()

    df = pred_year.merge(ds_year, on="symbol", how="left", suffixes=("", "_ds"))
    df["symbol"] = df["symbol"].astype(str).str.strip()

    anchor = pd.to_numeric(df.get("anchor_eps", 0), errors="coerce")
    pred_delta = pd.to_numeric(df["pred_rf_delta"], errors="coerce")
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
    if month in {"05", "06", "07"}:
        oldest_q_eps = pd.to_numeric(df.get("ly_q2_eps", float("nan")), errors="coerce")
    else:  # 08, 09, 10
        oldest_q_eps = pd.to_numeric(df.get("ly_q3_eps", float("nan")), errors="coerce")

    df["ttm_eps_forward_live"] = df["ttm_eps_official_live"] - oldest_q_eps + df["predict_target_eps"]

    df["predict_target_price_live"] = pd.to_numeric(df.get("pe_current"), errors="coerce") * df["predict_target_eps"]
    df["volume_lots"] = pd.to_numeric(df.get("target_volume", df.get("q3_volume")), errors="coerce") / 1000.0

    ttm_ok = df["ttm_eps_forward_live"] >= float(args.min_ttm_eps)
    vol_ok = df["volume_lots"] >= float(args.min_volume_lots)
    forward_not_worse = df["ttm_eps_forward_live"] >= df["ttm_eps_official_live"]

    out = df[ttm_ok & vol_ok & forward_not_worse].copy()
    out = out.sort_values(["symbol"]).reset_index(drop=True)
    out = out.rename(
        columns={
            "q3_date": "date",
            "q3_close": "close",
            "q3_volume": "volume",
            "predict_target_price_live": "predict_target_price",
        }
    )

    # ── 新增：取得各股實際月營收公布日（消除前視偏差） ──────────────────────────
    symbols = out["symbol"].astype(str).str.strip().tolist()
    publish_dates = fetch_revenue_publish_dates(
        api_base=args.api_base,
        market=market,
        year=year,
        month=month,
        symbols=symbols,
    )
    out["revenue_publish_date"] = out["symbol"].astype(str).str.strip().map(publish_dates)
    # ──────────────────────────────────────────────────────────────────────────────

    num_cols = out.select_dtypes(include=["number"]).columns.tolist()
    if num_cols:
        out[num_cols] = out[num_cols].round(2)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(output_path, index=False)

    print("build_candidates done")
    print(f"- market: {market}")
    print(f"- year: {year}")
    print(f"- month: {month}")
    print(f"- predictions: {pred_path}")
    print(f"- dataset: {ds_path}")
    print(f"- output: {output_path}")
    print(f"- rows: {len(out)}")
    if "revenue_publish_date" in out.columns:
        print(f"- publish_date distribution:\n{out['revenue_publish_date'].value_counts().to_string()}")


if __name__ == "__main__":
    main()
