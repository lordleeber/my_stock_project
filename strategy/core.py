import pandas as pd
import numpy as np
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Any

@dataclass
class StrategyConfig:
    strategy_mode: str = "shares"  # 'shares' or 'amount'
    capital: float = 100000        # 初始資金 (若 mode=amount) 或 計算 ROI 分母用
    fixed_shares: int = 1000       # 若 mode=shares
    hold_days: int = 3
    allow_pyramiding: bool = True
    only_red_candle: bool = False

@dataclass
class TradeRecord:
    symbol: str
    name: str
    buy_date: Any # datetime.date
    sell_date: Any # datetime.date
    buy_price: float
    sell_price: float
    shares: int
    profit: float
    return_rate: float
    cost: float

@dataclass
class BacktestSummary:
    total_trades: int
    total_profit: float
    total_cost: float
    roi: float
    win_rate: float
    avg_return: float

def run_backtest(df: pd.DataFrame, config: StrategyConfig) -> Dict[str, Any]:
    """
    執行量能爆發策略回測
    """
    if df.empty:
        return {"trades": [], "summary": _empty_summary()}

    # 1. 資料預處理與訊號產生
    df = df.copy()
    if 'date' not in df.columns: # 防呆
        if 'Date' in df.columns: df.rename(columns={'Date': 'date'}, inplace=True)
    
    df['date'] = pd.to_datetime(df['date'])
    df['vma10'] = df['vma10'].fillna(0)
    
    # 核心策略：Volume > 5 * VMA10
    df['is_signal'] = df['volume'] > (df['vma10'] * 5)
    
    # 進階濾網：紅 K
    if config.only_red_candle:
        df['is_signal'] = df['is_signal'] & (df['close'] > df['open'])

    # 為了方便 Pyramiding 檢查，我們不先過濾 signal，而在迴圈中判斷
    # 但為了效能，我們先篩出有訊號的候選者，但必須保留原始 df 供查價
    signals = df[df['is_signal']].copy()
    
    # 排序確保時間順序
    signals = signals.sort_values(by=['date', 'symbol'])
    
    trades: List[TradeRecord] = []
    locked_until: Dict[str, Any] = {} # symbol -> sell_date

    # 2. 執行回測迴圈
    for idx, row in signals.iterrows():
        symbol = row['symbol']
        signal_date = row['date'].date()
        
        # 檢查 Pyramiding (部位鎖定)
        if not config.allow_pyramiding:
            if symbol in locked_until:
                # 若訊號日還在鎖定期間內 (尚未賣出)，則跳過
                # 邏輯：T+1 買，Locked_Until = T+N 賣出日
                # 只要 signal_date < locked_until，表示這筆訊號發生時還沒空手
                if signal_date < locked_until[symbol]:
                    continue

        # 取得該股票完整資料以查找 T+1, T+N
        # 效能優化：這裡如果 df 很大，每次 query 會慢。
        # 實務上可以先 group by symbol，但目前先維持簡單邏輯
        stock_data = df[df['symbol'] == symbol].reset_index(drop=True)
        
        # 找訊號日 index
        sig_idx_list = stock_data.index[stock_data['date'].dt.date == signal_date].tolist()
        if not sig_idx_list: continue
        sig_idx = sig_idx_list[0]
        
        # T+1 買進
        buy_idx = sig_idx + 1
        # T+N 賣出
        sell_idx = sig_idx + 1 + config.hold_days
        
        if buy_idx >= len(stock_data) or sell_idx >= len(stock_data):
            continue
            
        buy_row = stock_data.iloc[buy_idx]
        sell_row = stock_data.iloc[sell_idx]
        
        buy_price = float(buy_row['open'])
        sell_price = float(sell_row['close'])
        
        if buy_price <= 0 or pd.isna(buy_price): continue

        buy_date_dt = buy_row['date'].date()
        sell_date_dt = sell_row['date'].date()

        # 二次檢查 Pyramiding (針對實際買入日)
        if not config.allow_pyramiding:
            if symbol in locked_until:
                if buy_date_dt <= locked_until[symbol]:
                    continue

        # 資金管理
        shares = 0
        if config.strategy_mode == 'shares':
            shares = config.fixed_shares
        elif config.strategy_mode == 'amount':
            shares = int(config.capital // buy_price)
        
        if shares <= 0: continue

        cost = buy_price * shares
        revenue = sell_price * shares
        profit = revenue - cost
        ret = (sell_price - buy_price) / buy_price

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
            cost=cost
        ))
        
        # 更新鎖定狀態
        locked_until[symbol] = sell_date_dt

    # 3. 統計結果
    if not trades:
        return {"trades": [], "summary": _empty_summary()}

    df_trades = pd.DataFrame([asdict(t) for t in trades])
    
    total_profit = df_trades['profit'].sum()
    total_cost = df_trades['cost'].sum()
    avg_return = df_trades['return_rate'].mean()
    win_rate = (df_trades['profit'] > 0).mean() * 100
    
    # ROI 分母選擇：
    # 如果是 Fixed Amount，通常分母應該是「初始本金」(Capital)，因為那是你的總資產。
    # 但如果是 Fixed Shares，分母通常是「總投入成本」(Total Cost)。
    # 這裡為了統一與之前的邏輯，暫時使用 Total Cost，但這在 Fixed Amount 模式下會嚴重高估 ROI (因為資金被重複使用)。
    # 建議：如果 mode=amount，分母 = config.capital
    
    roi_denominator = total_cost
    # if config.strategy_mode == 'amount':
    #     roi_denominator = config.capital * (如果是 Portfolio Backtest 才能這樣算)
    # 目前是 Transaction-based Backtest，用 Total Cost 比較能反映「交易效率」
    
    roi = (total_profit / roi_denominator * 100) if roi_denominator > 0 else 0

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
