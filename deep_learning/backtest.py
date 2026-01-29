"""
模型回測腳本
"""
import torch
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import joblib
from datetime import datetime

from data.data_loader import load_stock_data, add_derived_features
from data.feature_engineering import prepare_features, create_sequences
from data.dataset import StockDataset
from models.lstm_model import StockLSTM
from config import *

def calculate_transaction_cost(price, shares, is_buy):
    """
    計算交易成本
    
    Args:
        price: 股價
        shares: 股數
        is_buy: 是否為買入
    
    Returns:
        總成本（含手續費和證交稅）
    """
    commission = price * shares * COMMISSION_RATE
    
    if is_buy:
        # 買入只有手續費
        return price * shares + commission
    else:
        # 賣出有手續費和證交稅
        tax = price * shares * TAX_RATE
        return price * shares - commission - tax

def backtest_model(model, test_df, scaler, device):
    """
    回測模型
    
    Args:
        model: 訓練好的模型
        test_df: 測試數據
        scaler: 特徵標準化器
        device: 計算設備
    
    Returns:
        results: 回測結果DataFrame
        metrics: 績效指標字典
    """
    model.eval()
    
    # 準備特徵
    features = prepare_features(test_df, FEATURES)
    features_norm = scaler.transform(features)
    features_norm = pd.DataFrame(features_norm, columns=features.columns, index=features.index)
    
    # 創建一個虛擬標籤（用於create_sequences，實際不使用）
    dummy_labels = pd.Series([0] * len(test_df), index=test_df.index)
    
    # 創建序列
    X, _, seq_indices = create_sequences(features_norm, dummy_labels, SEQUENCE_LENGTH)
    
    # 預測
    predictions = []
    with torch.no_grad():
        for i in range(len(X)):
            x = torch.FloatTensor(X[i:i+1]).to(device)
            pred = model(x).cpu().item()
            predictions.append(pred)
    
    # 創建結果DataFrame
    results = test_df.loc[seq_indices].copy()
    results['prediction_prob'] = predictions
    results['prediction'] = (np.array(predictions) > 0.5).astype(int)
    
    # 模擬交易
    cash = 0  # 現金
    position = 0  # 持倉股數
    buy_price = 0  # 買入價格
    trades = []  # 交易記錄
    
    portfolio_values = []  # 組合價值
    
    for idx, row in results.iterrows():
        date = row['date']
        close_price = row['close']
        should_hold = row['prediction']
        
        # 計算當前組合價值
        current_value = cash + position * close_price
        portfolio_values.append(current_value)
        
        # 交易邏輯
        if should_hold == 1 and position == 0:
            # 買入1張
            cost = calculate_transaction_cost(close_price, SHARES_PER_TRADE, is_buy=True)
            cash -= cost
            position = SHARES_PER_TRADE
            buy_price = close_price
            
            trades.append({
                'date': date,
                'action': 'BUY',
                'price': close_price,
                'shares': SHARES_PER_TRADE,
                'cost': cost,
                'cash': cash,
                'position': position
            })
            
        elif should_hold == 0 and position > 0:
            # 賣出全部
            revenue = calculate_transaction_cost(close_price, position, is_buy=False)
            profit = revenue - (buy_price * position + calculate_transaction_cost(buy_price, position, is_buy=True) - buy_price * position)
            cash += revenue
            
            trades.append({
                'date': date,
                'action': 'SELL',
                'price': close_price,
                'shares': position,
                'revenue': revenue,
                'profit': profit,
                'cash': cash,
                'position': 0
            })
            
            position = 0
            buy_price = 0
    
    # 最後如果還有持倉，按最後收盤價賣出
    if position > 0:
        last_price = results.iloc[-1]['close']
        last_date = results.iloc[-1]['date']
        revenue = calculate_transaction_cost(last_price, position, is_buy=False)
        profit = revenue - (buy_price * position + calculate_transaction_cost(buy_price, position, is_buy=True) - buy_price * position)
        cash += revenue
        
        trades.append({
            'date': last_date,
            'action': 'SELL',
            'price': last_price,
            'shares': position,
            'revenue': revenue,
            'profit': profit,
            'cash': cash,
            'position': 0
        })
    
    results['portfolio_value'] = portfolio_values
    
    # 計算績效指標
    trades_df = pd.DataFrame(trades)
    
    if len(trades_df) > 0:
        buy_trades = trades_df[trades_df['action'] == 'BUY']
        sell_trades = trades_df[trades_df['action'] == 'SELL']
        
        total_trades = len(sell_trades)
        if total_trades > 0:
            total_profit = sell_trades['profit'].sum()
            win_trades = (sell_trades['profit'] > 0).sum()
            win_rate = win_trades / total_trades if total_trades > 0 else 0
            avg_profit = sell_trades['profit'].mean()
            max_profit = sell_trades['profit'].max()
            max_loss = sell_trades['profit'].min()
        else:
            total_profit = 0
            win_rate = 0
            avg_profit = 0
            max_profit = 0
            max_loss = 0
        
        final_value = portfolio_values[-1]
        
        # 計算最大回撤
        portfolio_series = pd.Series(portfolio_values)
        running_max = portfolio_series.expanding().max()
        drawdown = (portfolio_series - running_max) / running_max
        max_drawdown = drawdown.min()
        
        metrics = {
            'total_trades': total_trades,
            'win_rate': win_rate,
            'total_profit': total_profit,
            'avg_profit_per_trade': avg_profit,
            'max_profit': max_profit,
            'max_loss': max_loss,
            'final_portfolio_value': final_value,
            'final_cash': cash,
            'max_drawdown': max_drawdown
        }
    else:
        metrics = {
            'total_trades': 0,
            'win_rate': 0,
            'total_profit': 0,
            'avg_profit_per_trade': 0,
            'max_profit': 0,
            'max_loss': 0,
            'final_portfolio_value': 0,
            'final_cash': 0,
            'max_drawdown': 0
        }
    
    return results, trades_df, metrics

def plot_backtest_results(results, trades_df, save_path='backtest_results.png'):
    """繪製回測結果"""
    fig, axes = plt.subplots(3, 1, figsize=(15, 12))
    
    # 1. 股價和交易點
    ax1 = axes[0]
    ax1.plot(results['date'], results['close'], label='Close Price', alpha=0.7)
    
    if len(trades_df) > 0:
        buy_trades = trades_df[trades_df['action'] == 'BUY']
        sell_trades = trades_df[trades_df['action'] == 'SELL']
        
        ax1.scatter(buy_trades['date'], buy_trades['price'], 
                   color='green', marker='^', s=100, label='Buy', zorder=5)
        ax1.scatter(sell_trades['date'], sell_trades['price'], 
                   color='red', marker='v', s=100, label='Sell', zorder=5)
    
    ax1.set_title('Stock Price and Trading Signals')
    ax1.set_xlabel('Date')
    ax1.set_ylabel('Price')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    # 2. 預測機率
    ax2 = axes[1]
    ax2.plot(results['date'], results['prediction_prob'], label='Hold Probability', alpha=0.7)
    ax2.axhline(y=0.5, color='r', linestyle='--', label='Threshold')
    ax2.fill_between(results['date'], 0, results['prediction_prob'], 
                     where=(results['prediction_prob'] > 0.5), alpha=0.3, color='green', label='Hold')
    ax2.fill_between(results['date'], 0, results['prediction_prob'], 
                     where=(results['prediction_prob'] <= 0.5), alpha=0.3, color='red', label='Not Hold')
    ax2.set_title('Model Prediction Probability')
    ax2.set_xlabel('Date')
    ax2.set_ylabel('Probability')
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    
    # 3. 組合價值
    ax3 = axes[2]
    ax3.plot(results['date'], results['portfolio_value'], label='Portfolio Value', linewidth=2)
    ax3.set_title('Portfolio Value Over Time')
    ax3.set_xlabel('Date')
    ax3.set_ylabel('Value (NT$)')
    ax3.legend()
    ax3.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(save_path)
    print(f"Backtest results plot saved to {save_path}")
    plt.close()

def main():
    print("="*60)
    print("台積電深度學習交易系統 - 回測")
    print("="*60)
    
    # 設定device
    device = torch.device('cuda' if torch.cuda.is_available() and TRAINING_CONFIG['device'] == 'cuda' else 'cpu')
    print(f"\nUsing device: {device}")
    
    # 1. 加載模型
    print("\n[1/4] Loading model...")
    input_size = len(FEATURES)
    model = StockLSTM(
        input_size=input_size,
        hidden_size=MODEL_CONFIG['hidden_size'],
        num_layers=MODEL_CONFIG['num_layers'],
        dropout=MODEL_CONFIG['dropout']
    ).to(device)
    
    checkpoint = torch.load('models/saved/best_model.pth', map_location=device)
    model.load_state_dict(checkpoint['model_state_dict'])
    print(f"Model loaded from epoch {checkpoint['epoch']}")
    print(f"Validation loss: {checkpoint['val_loss']:.4f}")
    
    # 2. 加載scaler
    print("\n[2/4] Loading scaler...")
    scaler = joblib.load('models/saved/scaler.pkl')
    
    # 3. 加載測試數據
    print("\n[3/4] Loading test data...")
    test_df = load_stock_data(SYMBOL, TEST_START_DATE, TEST_END_DATE)
    test_df = add_derived_features(test_df)
    print(f"Test data: {len(test_df)} days")
    
    # 4. 回測
    print("\n[4/4] Running backtest...")
    results, trades_df, metrics = backtest_model(model, test_df, scaler, device)
    
    # 打印結果
    print("\n" + "="*60)
    print("BACKTEST RESULTS")
    print("="*60)
    print(f"Test Period: {TEST_START_DATE} ~ {TEST_END_DATE}")
    print(f"Total Trading Days: {len(results)}")
    print("-"*60)
    print(f"Total Trades: {metrics['total_trades']}")
    print(f"Win Rate: {metrics['win_rate']*100:.2f}%")
    print(f"Total Profit: NT$ {metrics['total_profit']:,.0f}")
    print(f"Avg Profit/Trade: NT$ {metrics['avg_profit_per_trade']:,.0f}")
    print(f"Max Profit: NT$ {metrics['max_profit']:,.0f}")
    print(f"Max Loss: NT$ {metrics['max_loss']:,.0f}")
    print(f"Final Portfolio Value: NT$ {metrics['final_portfolio_value']:,.0f}")
    print(f"Final Cash: NT$ {metrics['final_cash']:,.0f}")
    print(f"Max Drawdown: {metrics['max_drawdown']*100:.2f}%")
    print("="*60)
    
    # 保存結果
    results.to_csv('models/saved/backtest_results.csv', index=False)
    if len(trades_df) > 0:
        trades_df.to_csv('models/saved/backtest_trades.csv', index=False)
    
    # 繪製圖表
    plot_backtest_results(results, trades_df, 'models/saved/backtest_results.png')
    
    print("\nResults saved to models/saved/")

if __name__ == "__main__":
    main()
