"""
滾動月度投資組合回測（Method C）。

每月邏輯：
  1. 依 entry_date 偵測市場狀態（Bull / Sideways / Bear）。
  2. Bear 狀態 → 全部出場，跳過新進場。
  3. Bull / Sideways → 完整月度輪倉：
       - 所有現有持倉在 prev_trading_day(entry_date) 開盤出場。
       - 所有新候選股在 entry_date 開盤進場。
  - 沒有「繼續持有」機制：每月完全換倉，與模型的單月持有期最佳化一致，
    且避免 look-ahead bias（出場決策不需要知道下月選股）。
  - 倉位大小：每檔固定金額（預設 100,000 TWD）。
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backtester.data_loader import fetch_quotes_from_db
from backtester.simulator import CostConfig
from backtester.utils import month_iter, normalize_month
from train_eps import prepare_data as tp


@dataclass
class Position:
    """代表一個持倉單位，記錄進場資訊以供後續計算損益。

    capital_used 為實際使用資金（open_price × shares），
    與固定金額（position_amount）可能因取整而略有差異。
    """
    symbol: str
    entry_date: str
    entry_price: float
    shares: int
    capital_used: float


def prev_trading_day(date_str: str) -> str:
    """回傳嚴格早於 date_str 的最後一個交易日。

    用於決定「本月出場日」：新倉在 entry_date 開盤進場，
    舊倉須在 entry_date 前一個交易日開盤出場，
    避免同一天既出場又進場造成資金計算混亂。
    查詢失敗時回傳原始日期作為 fallback，避免整個月跳過。
    """
    stmt = text("SELECT MAX(date) FROM daily_quotes WHERE date < :d")
    try:
        engine = create_engine(tp.get_db_url())
        with engine.connect() as conn:
            result = conn.execute(stmt, {"d": date_str}).scalar()
        return str(result) if result else date_str
    except Exception:
        return date_str


def detect_market_regime(ref_date: str) -> str:
    """依 market_indices 截至 ref_date 的 MA20/MA60 回傳 'Bull'、'Bear' 或 'Sideways'。"""
    stmt = text(
        """
        SELECT date, index_close
        FROM market_indices
        WHERE date <= :ref_date
        ORDER BY date ASC
        """
    )
    try:
        engine = create_engine(tp.get_db_url())
        with engine.connect() as conn:
            idx = pd.read_sql(stmt, conn, params={"ref_date": ref_date})
    except Exception as exc:
        print(f"[WARN] market regime query failed: {exc}")
        return "Sideways"

    if idx.empty:
        return "Sideways"

    idx["date"] = pd.to_datetime(idx["date"], errors="coerce")
    idx["index_close"] = pd.to_numeric(idx["index_close"], errors="coerce")
    idx = idx.dropna(subset=["date", "index_close"]).sort_values("date")
    if idx.empty:
        return "Sideways"

    # 同一天可能有多筆資料（不同指數），取平均後再計算均線
    daily = (
        idx.groupby("date", as_index=False)["index_close"].mean().sort_values("date")
    )
    # MA20：短期趨勢；MA60：中期趨勢；min_periods 允許資料初期均線仍可計算
    daily["ma20"] = daily["index_close"].rolling(20, min_periods=10).mean()
    daily["ma60"] = daily["index_close"].rolling(60, min_periods=20).mean()
    latest = daily.iloc[-1]

    ma20 = float(latest.get("ma20", np.nan))
    ma60 = float(latest.get("ma60", np.nan))
    close = float(latest.get("index_close", np.nan))

    # 均線資料不足（歷史資料太短）→ 預設 Sideways，不影響進場
    if np.isnan(ma20) or np.isnan(ma60):
        return "Sideways"
    # Bull 條件：短均線在長均線之上，市場呈多頭趨勢
    if ma20 > ma60:
        return "Bull"
    # Bear 條件：短均線下穿長均線，且收盤價低於短均線（雙重確認空頭）
    if ma20 < ma60 and close < ma20:
        return "Bear"
    # 其餘（MA20 ≤ MA60 但收盤仍在 MA20 之上）→ 盤整，允許進場但降低信心
    return "Sideways"


def load_candidates_safe(
    models_root: Path, year: int, month: int
) -> pd.DataFrame | None:
    """從 models_selection/<year>/<month>/ 載入預先計算的 candidates_scored.csv。"""
    month_s = normalize_month(month)
    scored_path = models_root / f"{year:04d}" / month_s / "candidates_scored.csv"

    if not scored_path.exists():
        raise FileNotFoundError(
            f"candidates_scored.csv not found: {scored_path}\n"
            f"Run: venv/bin/python3 strategies/step5_score_and_publish.py --year {year} --month {month}"
        )

    df = pd.read_csv(scored_path)
    df["symbol"] = df["symbol"].astype(str).str.strip()
    df["entry_date"] = pd.to_datetime(df.get("entry_date"), errors="coerce")
    df = df.dropna(subset=["symbol", "entry_date"])
    if df.empty:
        return None
    return df


def fetch_open_on_date(symbols: list[str], date_str: str) -> dict[str, float]:
    """撈取指定日期的開盤價（含 ±5 日緩衝以處理假日）。

    回傳 {symbol: open_price} 字典。若某支股票在目標日無行情
    （停牌、假日等），則不出現在結果中，呼叫方需自行處理缺失。
    """
    if not symbols:
        return {}
    target = pd.to_datetime(date_str)
    # 前後各加 5 個日曆日緩衝，確保連假結束後的第一個交易日也能被撈到
    buffer_start = (target - pd.Timedelta(days=5)).strftime("%Y-%m-%d")
    buffer_end = (target + pd.Timedelta(days=5)).strftime("%Y-%m-%d")
    try:
        quotes = fetch_quotes_from_db(
            symbols=symbols, start_date=buffer_start, end_date=buffer_end
        )
    except Exception as exc:
        print(f"[WARN] fetch_quotes failed for {date_str}: {exc}")
        return {}
    if quotes.empty:
        return {}
    # 使用目標日當天或之後最近的交易日（處理目標日為假日的情況）。
    quotes = quotes[quotes["date"] >= target].sort_values("date")
    result: dict[str, float] = {}
    for sym, grp in quotes.groupby("symbol"):
        # 取最近一個有效交易日的開盤價
        row = grp.iloc[0]
        if pd.notna(row.get("open")):
            result[str(sym).strip()] = float(row["open"])
    return result


def _cost(
    entry_price: float, exit_price: float, shares: int, cost_cfg: CostConfig
) -> float:
    """計算單筆交易的總成本（手續費 + 證交稅）。

    台灣股市成本結構：
      - 手續費：買賣雙邊各收一次（commission_rate 套用於買賣金額之和）
      - 證交稅：僅賣出時收取（tax_rate 套用於賣出金額）
    """
    commission = (entry_price * shares + exit_price * shares) * cost_cfg.commission_rate
    tax = exit_price * shares * cost_cfg.tax_rate
    return commission + tax


def _exit_position(
    pos: Position,
    exit_date_str: str,
    exit_price: float | None,
    exit_reason: str,
    cost_cfg: CostConfig,
) -> tuple[dict, float]:
    """建立出場的交易紀錄列，回傳 (row_dict, net_pnl)。"""
    if exit_price is None:
        return {
            "symbol": pos.symbol,
            "entry_date": pos.entry_date,
            "exit_date": exit_date_str,
            "entry_price": pos.entry_price,
            "exit_price": np.nan,
            "shares": pos.shares,
            "capital_used": pos.capital_used,
            "gross_pnl": np.nan,
            "cost": np.nan,
            "net_pnl": np.nan,
            "return_pct": np.nan,
            "exit_reason": "no_quote_on_exit",
        }, 0.0

    gross_pnl = (exit_price - pos.entry_price) * pos.shares
    cost = _cost(pos.entry_price, exit_price, pos.shares, cost_cfg)
    net_pnl = gross_pnl - cost
    return_pct = net_pnl / pos.capital_used * 100.0 if pos.capital_used > 0 else np.nan
    return {
        "symbol": pos.symbol,
        "entry_date": pos.entry_date,
        "exit_date": exit_date_str,
        "entry_price": pos.entry_price,
        "exit_price": exit_price,
        "shares": pos.shares,
        "capital_used": pos.capital_used,
        "gross_pnl": round(gross_pnl, 2),
        "cost": round(cost, 2),
        "net_pnl": round(net_pnl, 2),
        "return_pct": round(return_pct, 4),
        "exit_reason": exit_reason,
    }, net_pnl


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rolling monthly portfolio backtester."
    )
    parser.add_argument("--start_year", type=int, required=True)
    parser.add_argument("--start_month", type=int, required=True)
    parser.add_argument("--end_year", type=int, required=True)
    parser.add_argument("--end_month", type=int, required=True)
    parser.add_argument(
        "--position-amount",
        type=float,
        default=100_000.0,
        help="Fixed TWD per position (default 100000)",
    )
    parser.add_argument("--commission-rate", type=float, default=0.001425)
    parser.add_argument("--tax-rate", type=float, default=0.003)
    parser.add_argument(
        "--top-n",
        type=int,
        default=None,
        help="Keep only top-N candidates by ml_score (default: no limit)",
    )
    parser.add_argument(
        "--models-root",
        type=Path,
        default=None,
        help="Root dir for selection models (default: models_selection/)",
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Print per-month progress"
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    out_dir = (Path.cwd() / "backtester" / "output" / "rolling").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    cost_cfg = CostConfig(commission_rate=args.commission_rate, tax_rate=args.tax_rate)
    position_amount = args.position_amount
    top_n = args.top_n
    models_root = (
        args.models_root
        if args.models_root
        else (Path.cwd() / "models_selection").resolve()
    )

    portfolio: dict[str, Position] = {}
    trade_log: list[dict] = []
    monthly_rows: list[dict] = []

    for year, month in month_iter(
        args.start_year, args.start_month, args.end_year, args.end_month
    ):
        month_s = normalize_month(month)
        try:
            candidates_df = load_candidates_safe(models_root, year, month)
        except FileNotFoundError as exc:
            if args.verbose:
                print(f"[skip] {year}/{month_s}: {exc}")
            continue
        if candidates_df is None:
            if args.verbose:
                print(f"[skip] no candidates: {year}/{month_s}")
            continue

        # 所有候選股共用同一個 entry_date（發布日後第一個交易日）。
        entry_date_str = candidates_df["entry_date"].iloc[0].strftime("%Y-%m-%d")
        # 出場在 entry_date 前一個交易日的開盤執行。
        exit_date_str = prev_trading_day(entry_date_str)

        # 依 ml_score 排序候選股（load_candidates_safe 若無模型會直接拋錯，此處有保證）。
        candidates_df = candidates_df.copy().sort_values("ml_score", ascending=False)
        if top_n is not None:
            candidates_df = candidates_df.head(top_n)

        # --- 偵測市場狀態 ---
        regime = detect_market_regime(entry_date_str)
        is_bear = regime == "Bear"

        if is_bear:
            # 全部出場，跳過新進場。
            exit_symbols = sorted(portfolio.keys())
            entry_symbols: list[str] = []
        else:
            # 完整月度輪倉：全部出場，再全部進場新候選股。
            exit_symbols = sorted(portfolio.keys())
            entry_symbols = sorted(candidates_df["symbol"].tolist())

        # 撈取出場日（前一交易日）與進場日的開盤價。
        exit_open_prices = fetch_open_on_date(exit_symbols, exit_date_str)
        entry_open_prices = fetch_open_on_date(entry_symbols, entry_date_str)

        # --- 處理出場 ---
        month_realized_pnl = 0.0
        for sym in exit_symbols:
            pos = portfolio.pop(sym)
            exit_reason = "bear_market_exit" if is_bear else "monthly_rotation"
            row, net_pnl = _exit_position(
                pos, exit_date_str, exit_open_prices.get(sym), exit_reason, cost_cfg
            )
            trade_log.append(row)
            month_realized_pnl += net_pnl

        # --- 處理進場（Bear 狀態下完全跳過）---
        month_entries_failed = 0
        for sym in entry_symbols:
            open_price = entry_open_prices.get(sym)
            if open_price is None:
                month_entries_failed += 1
                continue
            shares = max(int(position_amount // open_price), 1)
            capital_used = round(open_price * shares, 2)
            portfolio[sym] = Position(
                symbol=sym,
                entry_date=entry_date_str,
                entry_price=open_price,
                shares=shares,
                capital_used=capital_used,
            )

        portfolio_capital = sum(p.capital_used for p in portfolio.values())
        monthly_rows.append(
            {
                "year": year,
                "month": month_s,
                "exit_date": exit_date_str,
                "entry_date": entry_date_str,
                "regime": regime,
                "holdings_count": len(portfolio),
                "exits": len(exit_symbols),
                "entries": len(entry_symbols),
                "entries_failed_no_quote": month_entries_failed,
                "realized_net_pnl": round(month_realized_pnl, 2),
                "portfolio_capital_deployed": round(portfolio_capital, 2),
            }
        )
        if args.verbose:
            regime_tag = " [BEAR — all exited]" if is_bear else f" [{regime}]"
            print(
                f"[{year}/{month_s}] entry={entry_date_str}{regime_tag} | "
                f"holdings={len(portfolio)} | exits={len(exit_symbols)} entries={len(entry_symbols)} | "
                f"realized_pnl={month_realized_pnl:+.0f}"
            )

    # --- 關閉剩餘未平倉部位（標記為未實現）---
    for sym, pos in portfolio.items():
        trade_log.append(
            {
                "symbol": sym,
                "entry_date": pos.entry_date,
                "exit_date": np.nan,
                "entry_price": pos.entry_price,
                "exit_price": np.nan,
                "shares": pos.shares,
                "capital_used": pos.capital_used,
                "gross_pnl": np.nan,
                "cost": np.nan,
                "net_pnl": np.nan,
                "return_pct": np.nan,
                "exit_reason": "still_open",
            }
        )

    trades_df = pd.DataFrame(trade_log)
    monthly_df = pd.DataFrame(monthly_rows)

    trades_path = out_dir / "rolling_trades.csv"
    monthly_path = out_dir / "rolling_monthly.csv"
    trades_df.to_csv(trades_path, index=False, encoding="utf-8-sig")
    monthly_df.to_csv(monthly_path, index=False, encoding="utf-8-sig")

    # 統計摘要（僅計算已平倉交易，排除 still_open）
    closed = trades_df[
        trades_df["exit_reason"].isin(["monthly_rotation", "bear_market_exit"])
    ].copy()
    total_net_pnl = closed["net_pnl"].sum() if not closed.empty else 0.0
    win_count = int((closed["net_pnl"] > 0).sum()) if not closed.empty else 0
    loss_count = int((closed["net_pnl"] < 0).sum()) if not closed.empty else 0

    summary = {
        "start": f"{args.start_year}/{normalize_month(args.start_month)}",
        "end": f"{args.end_year}/{normalize_month(args.end_month)}",
        "position_amount": position_amount,
        "top_n": top_n,
        "cost_config": {
            "commission_rate": cost_cfg.commission_rate,
            "tax_rate": cost_cfg.tax_rate,
        },
        "total_closed_trades": int(len(closed)),
        "win_count": win_count,
        "loss_count": loss_count,
        "win_rate": round(win_count / len(closed), 4) if len(closed) > 0 else None,
        "total_net_pnl": round(float(total_net_pnl), 2),
        "still_open_count": int((trades_df["exit_reason"] == "still_open").sum()),
    }
    (out_dir / "rolling_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    if args.verbose:
        print("\nrolling backtest done")
        print(f"- output: {out_dir}")
        print(f"- closed trades: {summary['total_closed_trades']}")
        print(f"- win/loss: {win_count}/{loss_count}")
        print(f"- total net pnl: {total_net_pnl:+.0f} TWD")
        print(f"- still open: {summary['still_open_count']}")


if __name__ == "__main__":
    main()
