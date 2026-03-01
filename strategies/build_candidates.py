import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import bindparam, create_engine, text

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from train_eps import prepare_data as tp


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build trade candidates using year/month paths.")
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=str, required=True, help="e.g. 09")
    parser.add_argument("--min-volume-lots", type=float, default=200.0)
    parser.add_argument("--max-atr20-pct", type=float, default=6.0)
    parser.add_argument("--top-entry-score-pct", type=float, default=1.0, help="0~1, 1.0 means keep all")
    return parser.parse_args()


def strategy_release_and_entry_dates(year: int, month: str) -> tuple[date, date]:
    m_int = int(month)
    release_day = 15 if m_int in {5, 8, 11} else 10
    release_dt = date(year, m_int, release_day)
    earliest_entry_dt = release_dt + timedelta(days=1)
    return release_dt, earliest_entry_dt


def zscore_series(v: pd.Series) -> pd.Series:
    x = pd.to_numeric(v, errors="coerce")
    mu = float(x.mean(skipna=True)) if not x.dropna().empty else 0.0
    sigma = float(x.std(skipna=True, ddof=0)) if not x.dropna().empty else 0.0
    if not np.isfinite(sigma) or sigma <= 0:
        return pd.Series(0.0, index=x.index)
    return (x - mu) / sigma


def fetch_market_features(conn, symbol_date_df: pd.DataFrame) -> pd.DataFrame:
    base = symbol_date_df.copy()
    base["symbol"] = base["symbol"].astype(str).str.strip()
    base["q3_date"] = pd.to_datetime(base["q3_date"], errors="coerce")
    base["q3_close"] = pd.to_numeric(base["q3_close"], errors="coerce")
    base = base.dropna(subset=["symbol", "q3_date"]).drop_duplicates(subset=["symbol", "q3_date"])
    if base.empty:
        return pd.DataFrame(columns=["symbol", "q3_date", "ma60", "atr20_pct", "foreign_net_20d_lots", "inst_net_20d_lots", "close_vs_ma60"])

    symbols = sorted(base["symbol"].unique().tolist())
    min_date = base["q3_date"].min()
    max_date = base["q3_date"].max()
    start_date = (min_date - pd.Timedelta(days=180)).strftime("%Y-%m-%d")
    end_date = max_date.strftime("%Y-%m-%d")

    stmt_ti = text(
        """
        SELECT symbol, date, ma60
        FROM technical_indicators
        WHERE symbol IN :symbols
          AND date >= :start_date
          AND date <= :end_date
        """
    ).bindparams(bindparam("symbols", expanding=True))
    ti = pd.read_sql(stmt_ti, conn, params={"symbols": symbols, "start_date": start_date, "end_date": end_date})
    if not ti.empty:
        ti["symbol"] = ti["symbol"].astype(str).str.strip()
        ti["date"] = pd.to_datetime(ti["date"], errors="coerce")
        ti["ma60"] = pd.to_numeric(ti["ma60"], errors="coerce")
        ti = ti.dropna(subset=["symbol", "date"]).drop_duplicates(subset=["symbol", "date"], keep="last")

    stmt_dq = text(
        """
        SELECT symbol, date, high, low, close
        FROM daily_quotes
        WHERE symbol IN :symbols
          AND date >= :start_date
          AND date <= :end_date
        """
    ).bindparams(bindparam("symbols", expanding=True))
    dq = pd.read_sql(stmt_dq, conn, params={"symbols": symbols, "start_date": start_date, "end_date": end_date})
    atr = pd.DataFrame(columns=["symbol", "date", "atr20_pct"])
    if not dq.empty:
        dq["symbol"] = dq["symbol"].astype(str).str.strip()
        dq["date"] = pd.to_datetime(dq["date"], errors="coerce")
        for c in ["high", "low", "close"]:
            dq[c] = pd.to_numeric(dq[c], errors="coerce")
        dq = dq.dropna(subset=["symbol", "date"]).sort_values(["symbol", "date"]).reset_index(drop=True)
        dq["prev_close"] = dq.groupby("symbol")["close"].shift(1)
        tr_1 = dq["high"] - dq["low"]
        tr_2 = (dq["high"] - dq["prev_close"]).abs()
        tr_3 = (dq["low"] - dq["prev_close"]).abs()
        dq["tr"] = pd.concat([tr_1, tr_2, tr_3], axis=1).max(axis=1, skipna=True)
        dq["atr20"] = dq.groupby("symbol")["tr"].transform(lambda s: s.rolling(20, min_periods=20).mean())
        dq["atr20_pct"] = (dq["atr20"] / dq["close"]) * 100.0
        atr = dq[["symbol", "date", "atr20_pct"]].drop_duplicates(subset=["symbol", "date"], keep="last")

    stmt_ii = text(
        """
        SELECT symbol, date, foreign_net, trust_net, dealer_net
        FROM institutional_investors
        WHERE symbol IN :symbols
          AND date >= :start_date
          AND date <= :end_date
        """
    ).bindparams(bindparam("symbols", expanding=True))
    ii = pd.read_sql(stmt_ii, conn, params={"symbols": symbols, "start_date": start_date, "end_date": end_date})
    chip = pd.DataFrame(columns=["symbol", "date", "foreign_net_20d_lots", "inst_net_20d_lots"])
    if not ii.empty:
        ii["symbol"] = ii["symbol"].astype(str).str.strip()
        ii["date"] = pd.to_datetime(ii["date"], errors="coerce")
        for c in ["foreign_net", "trust_net", "dealer_net"]:
            ii[c] = pd.to_numeric(ii[c], errors="coerce").fillna(0.0)
        ii["inst_net"] = ii["trust_net"] + ii["dealer_net"]
        ii = ii.dropna(subset=["symbol", "date"]).sort_values(["symbol", "date"]).reset_index(drop=True)
        ii["foreign_net_20d"] = ii.groupby("symbol")["foreign_net"].transform(lambda s: s.rolling(20, min_periods=20).sum())
        ii["inst_net_20d"] = ii.groupby("symbol")["inst_net"].transform(lambda s: s.rolling(20, min_periods=20).sum())
        ii["foreign_net_20d_lots"] = ii["foreign_net_20d"] / 1000.0
        ii["inst_net_20d_lots"] = ii["inst_net_20d"] / 1000.0
        chip = ii[["symbol", "date", "foreign_net_20d_lots", "inst_net_20d_lots"]].drop_duplicates(subset=["symbol", "date"], keep="last")

    out = base[["symbol", "q3_date", "q3_close"]].rename(columns={"q3_date": "date"}).copy()
    if not ti.empty:
        out = out.merge(ti[["symbol", "date", "ma60"]], on=["symbol", "date"], how="left")
    else:
        out["ma60"] = np.nan
    if not atr.empty:
        out = out.merge(atr, on=["symbol", "date"], how="left")
    else:
        out["atr20_pct"] = np.nan
    if not chip.empty:
        out = out.merge(chip, on=["symbol", "date"], how="left")
    else:
        out["foreign_net_20d_lots"] = np.nan
        out["inst_net_20d_lots"] = np.nan

    out["close_vs_ma60"] = out["q3_close"] / out["ma60"] - 1.0
    out["q3_date"] = out["date"].dt.strftime("%Y-%m-%d")
    return out[["symbol", "q3_date", "ma60", "atr20_pct", "foreign_net_20d_lots", "inst_net_20d_lots", "close_vs_ma60"]]


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
    pred_year = pred.copy()
    ds_year = ds.copy()

    selected_data_year = None
    if "year" in pred.columns:
        py = pd.to_numeric(pred["year"], errors="coerce")
        pred_valid = py.dropna().astype(int)
        if not pred_valid.empty:
            selected_data_year = int(pred_valid.max())
            pred_year = pred[py == selected_data_year].copy()

    if selected_data_year is not None and "year" in ds.columns:
        dy = pd.to_numeric(ds["year"], errors="coerce")
        ds_year = ds[dy == selected_data_year].copy()
    elif "year" in ds.columns:
        dy = pd.to_numeric(ds["year"], errors="coerce")
        ds_valid = dy.dropna().astype(int)
        if not ds_valid.empty:
            selected_data_year = int(ds_valid.max())
            ds_year = ds[dy == selected_data_year].copy()

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
    pred_col = "pred_lgb_delta"
    if pred_col not in df.columns:
        raise RuntimeError(f"missing required prediction column: {pred_col}")
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

    with create_engine(tp.get_db_url()).connect() as conn:
        market_feat = fetch_market_features(conn, df[["symbol", "q3_date", "q3_close"]])
    df = df.merge(market_feat, on=["symbol", "q3_date"], how="left")

    df["q3_close"] = pd.to_numeric(df["q3_close"], errors="coerce")
    df["ma60"] = pd.to_numeric(df.get("ma60"), errors="coerce")
    df["atr20_pct"] = pd.to_numeric(df.get("atr20_pct"), errors="coerce")
    df["foreign_net_20d_lots"] = pd.to_numeric(df.get("foreign_net_20d_lots"), errors="coerce")
    df["inst_net_20d_lots"] = pd.to_numeric(df.get("inst_net_20d_lots"), errors="coerce")

    vol_ok = df["volume_lots"] >= float(args.min_volume_lots)
    forward_not_worse = df["ttm_eps_forward_live"] >= df["ttm_eps_official_live"]
    has_market_features = df[["q3_close", "ma60", "atr20_pct", "foreign_net_20d_lots", "inst_net_20d_lots"]].notna().all(axis=1)
    close_above_ma60 = df["q3_close"] > df["ma60"]
    foreign_buy_20d_ok = df["foreign_net_20d_lots"] > 0
    inst_buy_20d_ok = df["inst_net_20d_lots"] > 0
    atr20_ok = df["atr20_pct"] <= float(args.max_atr20_pct)

    print("filter stats (cumulative):")
    total_rows = len(df)
    keep = pd.Series(True, index=df.index)
    for name, mask in [
        ("has_market_features", has_market_features),
        ("volume_lots >= min", vol_ok),
        ("ttm_forward >= ttm_official", forward_not_worse),
        ("close > ma60", close_above_ma60),
        ("foreign_net_20d_lots > 0", foreign_buy_20d_ok),
        ("inst_net_20d_lots > 0", inst_buy_20d_ok),
        ("atr20_pct <= max", atr20_ok),
    ]:
        keep = keep & mask.fillna(False)
        print(f"- {name}: {int(keep.sum())}/{total_rows}")

    out = df[keep].copy()

    if not out.empty:
        out["pred_upside_pct"] = (out["predict_target_price_live"] - out["q3_close"]) / out["q3_close"] * 100.0
        out["chip_score_raw"] = out["foreign_net_20d_lots"] + out["inst_net_20d_lots"]
        out["pred_upside_z"] = zscore_series(out["pred_upside_pct"])
        out["chip_score_z"] = zscore_series(out["chip_score_raw"])
        out["tech_score_z"] = zscore_series(out["close_vs_ma60"])
        out["vol_penalty_z"] = zscore_series(out["atr20_pct"])
        out["entry_score"] = out["pred_upside_z"] + out["chip_score_z"] + out["tech_score_z"] - out["vol_penalty_z"]

        top_pct = float(args.top_entry_score_pct)
        if top_pct <= 0 or top_pct > 1:
            raise ValueError("--top-entry-score-pct must be within (0, 1]")
        if top_pct < 1.0:
            top_n = max(1, int(np.ceil(len(out) * top_pct)))
            out = out.nlargest(top_n, "entry_score").copy()
            print(f"- top entry_score selected: {len(out)} rows (pct={top_pct})")

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
    if selected_data_year is not None:
        print(f"- data_year_selected: {selected_data_year}")
    print(f"- output: {output_path}")
    print(f"- rows: {len(out)}")


if __name__ == "__main__":
    main()
