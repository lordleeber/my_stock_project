from __future__ import annotations

import pandas as pd

from backtester.engine import BacktestConfig, run_backtest


def build_signals_from_revenue_announcements(
    announcements_df: pd.DataFrame,
    window_start: str,
    window_end: str,
    min_score: float | None = None,
) -> pd.DataFrame:
    # announcements_df 至少需要: symbol, announce_date
    # 可選: model_action( buy/watch/sell ), score
    df = announcements_df.copy()
    df["symbol"] = df["symbol"].astype(str).str.strip()
    df["announce_date"] = pd.to_datetime(df["announce_date"], errors="coerce")
    df = df.dropna(subset=["symbol", "announce_date"]).copy()

    ws = pd.to_datetime(window_start)
    we = pd.to_datetime(window_end)
    df = df[(df["announce_date"] >= ws) & (df["announce_date"] <= we)].copy()

    if "model_action" in df.columns:
        df["model_action"] = df["model_action"].astype(str).str.lower().str.strip()
        df = df[df["model_action"] == "buy"].copy()
    if min_score is not None and "score" in df.columns:
        df["score"] = pd.to_numeric(df["score"], errors="coerce")
        df = df[df["score"] >= float(min_score)].copy()

    out = pd.DataFrame(
        {
            "symbol": df["symbol"],
            "signal_date": df["announce_date"].dt.strftime("%Y-%m-%d"),
            "side": "buy",
            "reason": "revenue_announcement_signal",
        }
    )
    return out.drop_duplicates(subset=["symbol", "signal_date", "side"]).reset_index(drop=True)


def run_revenue_window_backtest(
    announcements_df: pd.DataFrame,
    quotes_df: pd.DataFrame,
    cfg: BacktestConfig,
    window_start: str,
    window_end: str,
    min_score: float | None = None,
):
    signals = build_signals_from_revenue_announcements(
        announcements_df=announcements_df,
        window_start=window_start,
        window_end=window_end,
        min_score=min_score,
    )
    return run_backtest(signals_df=signals, quotes_df=quotes_df, cfg=cfg), signals
