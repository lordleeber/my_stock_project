import pandas as pd
import numpy as np
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Any

@dataclass
class StrategyConfig:
    strategy_mode: str = "shares"  # 'shares' or 'amount'
    capital: float = 100000        # 初始資金
    fixed_shares: int = 1000       # 固定股數
    hold_days: int = 3             # 持有天數
    allow_pyramiding: bool = True  # 允許加碼
    only_red_candle: bool = False  # 紅K濾網
    commission_rate: float = 0.001425 # 手續費
    tax_rate: float = 0.003           # 證交稅
    # 停損停利 (0.0 為不啟用)
    take_profit_pct: float = 0.0 # e.g., 0.1 for 10%
    stop_loss_pct: float = 0.0   # e.g., 0.05 for 5%

@dataclass
# ... (TradeRecord definition)

# ... (Inside run_backtest loop)
        # 最晚賣出日 (T+1+Hold)
        max_sell_idx = sig_idx + 1 + config.hold_days
        # 確保不越界
        max_sell_idx = min(max_sell_idx, len(stock_data) - 1)
        
        target_tp = buy_price * (1 + config.take_profit_pct) if config.take_profit_pct > 0 else None
        target_sl = buy_price * (1 - config.stop_loss_pct) if config.stop_loss_pct > 0 else None
        
        found_exit = False
        
        # 從買進當天收盤開始檢查 (T+1 ~ T+N)
        for i in range(buy_idx, max_sell_idx + 1):
            curr_row = stock_data.iloc[i]
            close_p = float(curr_row['close'])
            
            # 檢查停利 (Take Profit)
            if target_tp and close_p >= target_tp:
                sell_price = close_p
                sell_date_dt = curr_row['date'].date()
                exit_reason = "take_profit"
                found_exit = True
                break
            
            # 檢查停損 (Stop Loss)
            if target_sl and close_p <= target_sl:
                sell_price = close_p
                sell_date_dt = curr_row['date'].date()
                exit_reason = "stop_loss"
                found_exit = True
                break
        
        # 時間到強制賣出
        if not found_exit:
            last_row = stock_data.iloc[max_sell_idx]
            sell_price = float(last_row['close'])
            sell_date_dt = last_row['date'].date()
            exit_reason = "time_exit"

        # 資金管理
        shares = 0
        if config.strategy_mode == 'shares':
            shares = config.fixed_shares
        elif config.strategy_mode == 'amount':
            shares = int(config.capital // buy_price)
        
        if shares <= 0: continue

        # 成本與損益計算
        buy_commission = buy_price * shares * config.commission_rate
        total_buy_cost = (buy_price * shares) + buy_commission

        sell_commission = sell_price * shares * config.commission_rate
        sell_tax = sell_price * shares * config.tax_rate
        net_sell_revenue = (sell_price * shares) - sell_commission - sell_tax

        profit = net_sell_revenue - total_buy_cost
        ret = profit / total_buy_cost

        trades.append(TradeRecord(
            symbol=symbol,
            name=row['name'],
            buy_date=buy_date_dt,
            sell_date=sell_date_dt,
            buy_price=buy_price,
            sell_price=sell_price,
            shares=shares,
            profit=profit,
            return_rate=ret * 100,
            cost=total_buy_cost,
            commission=buy_commission + sell_commission,
            tax=sell_tax,
            exit_reason=exit_reason
        ))
        
        locked_until[symbol] = sell_date_dt

    # 3. 統計結果
    if not trades:
        return {"trades": [], "summary": _empty_summary()}

    df_trades = pd.DataFrame([asdict(t) for t in trades])
    
    total_profit = df_trades['profit'].sum()
    total_cost = df_trades['cost'].sum()
    avg_return = df_trades['return_rate'].mean()
    win_rate = (df_trades['profit'] > 0).mean() * 100
    
    roi = (total_profit / total_cost * 100) if total_cost > 0 else 0

    summary = BacktestSummary(
        total_trades=len(trades),
        total_profit=total_profit,
        total_cost=total_cost,
        roi=roi,
        win_rate=win_rate,
        avg_return=avg_return
    )

    return {"trades": trades, "summary": summary}

def _empty_summary():
    return BacktestSummary(0, 0.0, 0.0, 0.0, 0.0, 0.0)