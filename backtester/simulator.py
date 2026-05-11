from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class CostConfig:
    """台灣股市交易成本設定。

    commission_rate: 買賣雙邊各收一次，預設 0.1425‰（券商手續費，可打折）
    tax_rate: 僅賣出時收取，預設 0.3‰（證券交易稅）
    """

    commission_rate: float = 0.001425
    tax_rate: float = 0.003


def build_position_size(
    entry_open: float, max_position_amount: float, shares_per_lot: int
) -> tuple[int, float]:
    """依可用資金與進場開盤價計算買入股數與實際使用資金。

    台灣股市以「股」為單位（非張），此函式直接以股數計算，
    不受最小一張（1000 股）限制，適用於回測的靈活倉位設定。
    回傳 (股數, 實際使用資金)，股數最少為 1。
    """
    # 依預算決定持股數，不限制最小一張。
    shares = int(max_position_amount // entry_open)
    shares = max(shares, 1)
    return shares, float(shares * entry_open)


def check_entry_allowed(
    row: pd.Series, entry_open: float, entry_rule: dict[str, Any]
) -> tuple[bool, str]:
    """依進場規則判斷是否允許進場，回傳 (是否進場, 原因說明)。

    支援三種規則類型：
      - "all"：永不進場（用於測試或停用策略）
      - "target_above_entry_ratio"：預測目標價 ≥ 進場價 × ratio 才進場
      - "pullback_from_ref_close"：進場開盤價 ≤ 前收盤 × ratio（回檔進場過濾）
    """
    rule_type = entry_rule.get("type", "all")
    if rule_type == "all":
        # "all" 規則表示停用進場，通常用於純空倉測試
        return False, "entry_rule_all_not_allowed"

    if rule_type == "target_above_entry_ratio":
        # 確認模型預測的目標價有足夠的上漲空間才進場，過濾低潛力股
        ratio = float(entry_rule.get("ratio", 1.0))
        target_price = float(row.get("predict_target_price", np.nan))
        if np.isnan(target_price):
            return False, "skip_no_target"
        return target_price >= entry_open * ratio, f"entry_target_ge_{ratio}"

    if rule_type == "pullback_from_ref_close":
        # 只在股價回檔到前收盤 × ratio 以內才進場，避免追高
        ratio = float(entry_rule.get("ratio", 1.0))
        ref_close = float(row.get("close", np.nan))
        if np.isnan(ref_close):
            return False, "skip_no_ref_close"
        return entry_open <= ref_close * ratio, f"entry_pullback_le_{ratio}"

    # 未知規則預設允許進場，方便新規則開發時的快速測試
    return True, "entry_unknown_rule_default_true"


def resolve_take_profit_price(
    row: pd.Series, entry_open: float, tp_rule: dict[str, Any]
) -> float | None:
    """依停利規則解析目標出場價，無法計算時回傳 None（表示不設停利）。

    支援三種停利類型：
      - "target_price"：直接使用模型預測的目標價
      - "fixed_pct"：進場價 × (1 + pct)，固定百分比停利
      - "target_price_if_above_entry"：目標價需高於進場價才啟用，否則不設停利
    """
    tp_type = tp_rule.get("type", "target_price")
    if tp_type == "target_price":
        # 直接採用 EPS 模型預測的目標價作為停利點
        v = float(row.get("predict_target_price", np.nan))
        return None if np.isnan(v) else v
    if tp_type == "fixed_pct":
        # 固定比例停利，例如 pct=0.1 表示漲 10% 出場
        return entry_open * (1.0 + float(tp_rule.get("pct", 0.0)))
    if tp_type == "target_price_if_above_entry":
        # 目標價若低於進場價（模型看錯方向），則不設停利，改以停損保護
        v = float(row.get("predict_target_price", np.nan))
        if np.isnan(v) or v <= entry_open:
            return None
        return v
    return None


def _cost_amount(
    entry_price: float, exit_price: float, shares: int, cost_cfg: CostConfig
) -> float:
    buy = entry_price * shares
    sell = exit_price * shares
    commission = (buy + sell) * cost_cfg.commission_rate
    tax = sell * cost_cfg.tax_rate
    return float(commission + tax)


def simulate_one(
    row: pd.Series,
    quote_df: pd.DataFrame,
    strategy_name: str,
    entry_rule: dict[str, Any],
    take_profit_rule: dict[str, Any],
    exit_rule: dict[str, Any],
    cost_cfg: CostConfig,
    position_cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    symbol = str(row["symbol"]).strip()
    signal_entry_dt = pd.to_datetime(row["entry_date"])
    base = {
        "symbol": symbol,
        "strategy_name": strategy_name,
        "signal_entry_date": signal_entry_dt.strftime("%Y-%m-%d"),
        "target_price": float(row.get("predict_target_price", np.nan)),
    }

    sym_quotes = quote_df[quote_df["symbol"] == symbol].copy()
    sym_quotes = (
        sym_quotes[sym_quotes["date"] >= signal_entry_dt]
        .sort_values("date")
        .reset_index(drop=True)
    )
    if sym_quotes.empty:
        return {
            **base,
            "status": "no_quote_in_window",
            "exit_reason": "no_quote_in_window",
        }

    actual_entry_row = sym_quotes.iloc[0]
    actual_entry_dt = pd.to_datetime(actual_entry_row["date"])
    if actual_entry_dt < signal_entry_dt:
        return {
            **base,
            "status": "lookahead_violation",
            "exit_reason": "actual_entry_before_signal_entry",
            "actual_entry_date": actual_entry_dt.strftime("%Y-%m-%d"),
        }

    entry_open = (
        float(actual_entry_row["open"])
        if pd.notna(actual_entry_row["open"])
        else np.nan
    )
    if np.isnan(entry_open):
        return {
            **base,
            "status": "no_entry_open",
            "exit_reason": "no_entry_open",
            "actual_entry_date": actual_entry_dt.strftime("%Y-%m-%d"),
        }

    entry_ok, entry_reason = check_entry_allowed(
        row=row, entry_open=entry_open, entry_rule=entry_rule
    )
    if not entry_ok:
        return {
            **base,
            "status": "skipped",
            "actual_entry_date": actual_entry_dt.strftime("%Y-%m-%d"),
            "exit_reason": entry_reason,
            "entry_price": entry_open,
        }

    pos = position_cfg or {"shares_per_lot": 1000, "max_position_amount": 200000}
    shares_per_lot = int(pos.get("shares_per_lot", 1000))
    max_position_amount = float(pos.get("max_position_amount", 200000))
    shares_bought, capital_used = build_position_size(
        entry_open, max_position_amount, shares_per_lot
    )

    # --- 出場條件初始化 ---
    stop_loss_pct = float(exit_rule.get("stop_loss_pct", 0.05))
    # 固定停損價：進場後永遠不上移，僅作為底線保護
    fixed_stop = entry_open * (1.0 - stop_loss_pct)
    trailing_stop_pct = exit_rule.get("trailing_stop_pct")
    trailing_stop_pct = None if trailing_stop_pct is None else float(trailing_stop_pct)
    max_hold_days = int(exit_rule.get("max_hold_days", 20))
    # 同日同時觸碰停損與停利時的處理優先順序
    prefer_stop_when_both = bool(exit_rule.get("prefer_stop_when_both", True))
    take_profit_price = resolve_take_profit_price(
        row=row, entry_open=entry_open, tp_rule=take_profit_rule
    )
    # 追蹤最高價，用於計算移動停損（trailing stop）
    highest_high = entry_open

    q = sym_quotes.reset_index(drop=True)
    for i, day in q.iterrows():
        day_high = float(day["high"]) if pd.notna(day["high"]) else np.nan
        day_low = float(day["low"]) if pd.notna(day["low"]) else np.nan
        day_close = float(day["close"]) if pd.notna(day["close"]) else np.nan
        day_date = pd.to_datetime(day["date"]).strftime("%Y-%m-%d")

        # 更新歷史最高價（只在有效高價時更新，避免資料缺漏導致停損下移）
        if pd.notna(day_high):
            highest_high = max(highest_high, day_high)

        # 有效停損 = max(固定停損, 移動停損)；移動停損只升不降
        effective_stop = fixed_stop
        if trailing_stop_pct is not None:
            # 移動停損：從歷史最高價回撤 trailing_stop_pct
            trailing_stop = highest_high * (1.0 - trailing_stop_pct)
            effective_stop = max(effective_stop, trailing_stop)

        # 當日低價穿破有效停損線 → 觸發停損
        hit_sl = pd.notna(day_low) and day_low <= effective_stop
        # 當日高價達到停利目標 → 觸發停利
        hit_tp = (
            (take_profit_price is not None)
            and pd.notna(day_high)
            and day_high >= take_profit_price
        )

        if hit_sl and hit_tp:
            # 同日同時觸碰兩個條件：依 prefer_stop_when_both 決定優先順序
            # 保守假設（prefer_stop=True）：開盤跳空後先跌破停損再反彈至停利，以停損價出場
            if prefer_stop_when_both:
                exit_reason = "both_hit_same_day_stop_first"
                exit_price = effective_stop
            else:
                exit_reason = "both_hit_same_day_target_first"
                exit_price = float(take_profit_price)
            return _sold_row(
                base=base,
                entry_reason=entry_reason,
                actual_entry_dt=actual_entry_dt,
                entry_open=entry_open,
                exit_date=day_date,
                exit_price=exit_price,
                shares_bought=shares_bought,
                capital_used=capital_used,
                stop_price=effective_stop,
                take_profit_price=take_profit_price,
                exit_reason=exit_reason,
                cost_cfg=cost_cfg,
            )

        if hit_sl:
            return _sold_row(
                base=base,
                entry_reason=entry_reason,
                actual_entry_dt=actual_entry_dt,
                entry_open=entry_open,
                exit_date=day_date,
                exit_price=effective_stop,
                shares_bought=shares_bought,
                capital_used=capital_used,
                stop_price=effective_stop,
                take_profit_price=take_profit_price,
                exit_reason="stop_loss",
                cost_cfg=cost_cfg,
            )

        if hit_tp:
            return _sold_row(
                base=base,
                entry_reason=entry_reason,
                actual_entry_dt=actual_entry_dt,
                entry_open=entry_open,
                exit_date=day_date,
                exit_price=float(take_profit_price),
                shares_bought=shares_bought,
                capital_used=capital_used,
                stop_price=effective_stop,
                take_profit_price=take_profit_price,
                exit_reason="hit_target_price",
                cost_cfg=cost_cfg,
            )

        # 時間停損：持有超過 max_hold_days 個交易日，以收盤價強制出場
        # i 從 0 開始，第 max_hold_days 天（索引 max_hold_days-1）結束時出場
        if i + 1 >= max_hold_days:
            exit_price = day_close
            return _sold_row(
                base=base,
                entry_reason=entry_reason,
                actual_entry_dt=actual_entry_dt,
                entry_open=entry_open,
                exit_date=day_date,
                exit_price=exit_price,
                shares_bought=shares_bought,
                capital_used=capital_used,
                stop_price=effective_stop,
                take_profit_price=take_profit_price,
                exit_reason=f"time_stop_{max_hold_days}d",
                cost_cfg=cost_cfg,
            )

    # 迴圈結束但未觸發任何出場條件：行情資料在 end_date 前截止（資料不足）
    last = q.tail(1).iloc[0]
    last_close = float(last["close"]) if pd.notna(last["close"]) else np.nan
    last_date = pd.to_datetime(last["date"]).strftime("%Y-%m-%d")
    gross_pnl = (
        (last_close - entry_open) * shares_bought if pd.notna(last_close) else np.nan
    )
    total_cost = (
        _cost_amount(entry_open, last_close, shares_bought, cost_cfg)
        if pd.notna(last_close)
        else np.nan
    )
    net_pnl = gross_pnl - total_cost if pd.notna(gross_pnl) else np.nan
    net_return_pct = (
        (net_pnl / capital_used * 100.0)
        if capital_used > 0 and pd.notna(net_pnl)
        else np.nan
    )
    return {
        **base,
        "status": "open_until_end",
        "entry_reason": entry_reason,
        "actual_entry_date": actual_entry_dt.strftime("%Y-%m-%d"),
        "exit_reason": "not_hit_until_end",
        "exit_date": last_date,
        "entry_price": entry_open,
        "exit_price": last_close,
        "shares_bought": shares_bought,
        "capital_used": capital_used,
        "stop_price": np.nan,
        "take_profit_price": take_profit_price,
        "gross_pnl": gross_pnl,
        "total_cost": total_cost,
        "net_pnl": net_pnl,
        "return_pct": net_return_pct,
    }


def _sold_row(
    *,
    base: dict[str, Any],
    entry_reason: str,
    actual_entry_dt: pd.Timestamp,
    entry_open: float,
    exit_date: str,
    exit_price: float,
    shares_bought: int,
    capital_used: float,
    stop_price: float,
    take_profit_price: float | None,
    exit_reason: str,
    cost_cfg: CostConfig,
) -> dict[str, Any]:
    gross_pnl = (exit_price - entry_open) * shares_bought
    total_cost = _cost_amount(entry_open, exit_price, shares_bought, cost_cfg)
    net_pnl = gross_pnl - total_cost
    net_return_pct = (net_pnl / capital_used * 100.0) if capital_used > 0 else np.nan
    return {
        **base,
        "status": "sold",
        "entry_reason": entry_reason,
        "actual_entry_date": actual_entry_dt.strftime("%Y-%m-%d"),
        "exit_reason": exit_reason,
        "exit_date": exit_date,
        "entry_price": entry_open,
        "exit_price": exit_price,
        "shares_bought": shares_bought,
        "capital_used": capital_used,
        "stop_price": stop_price,
        "take_profit_price": take_profit_price,
        "gross_pnl": gross_pnl,
        "total_cost": total_cost,
        "net_pnl": net_pnl,
        "return_pct": net_return_pct,
    }


def aggregate_monthly(trades: pd.DataFrame) -> pd.DataFrame:
    """將單月所有交易彙整為一列統計摘要。

    trade status 分類：
      - "sold"：已平倉（觸發 SL/TP/時間停損）
      - "open_until_end"：持有至行情資料結束仍未出場
      - "skipped"：進場條件不符，未建倉
      - "lookahead_violation"：實際進場日早於訊號日，資料異常
    財務統計僅計算 sold 交易，open_until_end 以末日收盤為未實現損益。
    """
    sold = trades[trades["status"] == "sold"].copy()
    open_until_end = trades[trades["status"] == "open_until_end"].copy()
    skipped = trades[trades["status"] == "skipped"].copy()
    lookahead = trades[trades["status"] == "lookahead_violation"].copy()

    total_capital = float(sold["capital_used"].sum()) if not sold.empty else 0.0
    gross_pnl = float(sold["gross_pnl"].sum()) if not sold.empty else 0.0
    total_cost = float(sold["total_cost"].sum()) if not sold.empty else 0.0
    net_pnl = float(sold["net_pnl"].sum()) if not sold.empty else 0.0
    return_pct = (net_pnl / total_capital * 100.0) if total_capital > 0 else 0.0

    stop_loss_count = (
        int((sold.get("exit_reason", pd.Series(dtype=str)) == "stop_loss").sum())
        if not sold.empty
        else 0
    )
    stop_loss_ratio = (stop_loss_count / len(sold)) if len(sold) > 0 else np.nan

    row = {
        "total_picks": int(len(trades)),
        "entered_count": int((trades["status"].isin(["sold", "open_until_end"])).sum()),
        "skipped_count": int(len(skipped)),
        "sold_count": int(len(sold)),
        "open_until_end_count": int(len(open_until_end)),
        "lookahead_violation_count": int(len(lookahead)),
        "sold_win_count": int((sold["net_pnl"] > 0).sum()) if not sold.empty else 0,
        "sold_loss_count": int((sold["net_pnl"] < 0).sum()) if not sold.empty else 0,
        "stop_loss_count": stop_loss_count,
        "stop_loss_ratio": round(float(stop_loss_ratio), 6)
        if np.isfinite(stop_loss_ratio)
        else np.nan,
        "total_capital": round(total_capital, 2),
        "gross_pnl": round(gross_pnl, 2),
        "total_cost": round(total_cost, 2),
        "net_pnl": round(net_pnl, 2),
        "return_pct": round(return_pct, 4),
    }
    return pd.DataFrame([row])


def build_equity_curve(trades: pd.DataFrame) -> pd.DataFrame:
    x = trades[trades["status"].isin(["sold", "open_until_end"])].copy()
    if x.empty:
        return pd.DataFrame(columns=["date", "daily_net_pnl", "cum_net_pnl"])
    x["date"] = pd.to_datetime(x["exit_date"], errors="coerce")
    x = x.dropna(subset=["date"]).copy()
    daily = (
        x.groupby("date", as_index=False)["net_pnl"]
        .sum()
        .rename(columns={"net_pnl": "daily_net_pnl"})
    )
    daily = daily.sort_values("date").reset_index(drop=True)
    daily["cum_net_pnl"] = daily["daily_net_pnl"].cumsum()
    daily["date"] = daily["date"].dt.strftime("%Y-%m-%d")
    return daily
