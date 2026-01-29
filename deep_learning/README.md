# 深度學習股票交易系統

使用 LSTM 深度學習模型預測台積電（2330）每日持有決策。

## 系統特點

- **標的**：台積電（2330）
- **策略**：每天預測該持有或不持有
- **交易規則**：
  - 預測持有 → 買入1張（1000股）
  - 預測不持有 → 賣出全部
- **模型**：LSTM + 全連接層
- **特徵**：技術指標（MA, RSI, MACD等）+ 成交量 + 價格變化

## 目錄結構

```
deep_learning/
├── config.py              # 配置文件
├── train.py               # 訓練腳本
├── backtest.py            # 回測腳本
├── requirements.txt       # 依賴套件
├── data/                  # 數據處理模組
│   ├── data_loader.py     # 從DB加載數據
│   ├── feature_engineering.py  # 特徵工程
│   └── dataset.py         # PyTorch Dataset
├── models/                # 模型模組
│   ├── lstm_model.py      # LSTM模型定義
│   └── saved/             # 保存的模型和結果
└── README.md             # 說明文件
```

## 安裝

```bash
cd deep_learning
pip install -r requirements.txt
```

## 使用步驟

### 1. 配置參數

編輯 `config.py` 調整：
- 訓練/測試期間
- 模型超參數
- 標籤定義方法

### 2. 訓練模型

```bash
python train.py
```

訓練過程會：
- 從資料庫加載台積電數據
- 生成特徵和標籤
- 訓練 LSTM 模型
- 保存最佳模型到 `models/saved/best_model.pth`
- 生成訓練歷史圖表

### 3. 回測

```bash
python backtest.py
```

回測會：
- 加載訓練好的模型
- 在測試集上進行模擬交易
- 計算績效指標
- 生成交易圖表

### 4. 查看結果

結果保存在 `models/saved/`：
- `best_model.pth` - 最佳模型
- `training_history.png` - 訓練歷史
- `backtest_results.png` - 回測結果圖
- `backtest_trades.csv` - 交易明細

## 配置說明

### 數據期間
```python
TRAIN_START_DATE = '2025-01-01'
TRAIN_END_DATE = '2025-10-31'    # 訓練集
TEST_START_DATE = '2025-11-01'
TEST_END_DATE = '2026-01-29'     # 測試集
```

### 特徵設定
```python
FEATURES = [
    'close', 'open', 'high', 'low', 'volume',
    'ma5', 'ma10', 'ma20', 'ma60',
    'vma5', 'vma10', 'vma20',
    'rsi', 'macd', 'macd_signal',
    'return_1d', 'return_5d',
    'volume_ratio'
]
```

### 標籤定義
```python
LABEL_CONFIG = {
    'method': 'future_return',  # 未來報酬法
    'threshold': 0.02,           # 2% 門檻
    'days': 5                    # 未來5天
}
```

## 模型架構

```
Input (20 days × 17 features)
    ↓
LSTM Layer 1 (128 units)
    ↓
Dropout (0.3)
    ↓
LSTM Layer 2 (128 units)
    ↓
Dropout (0.3)
    ↓
Fully Connected (64 units) + ReLU
    ↓
Fully Connected (32 units) + ReLU
    ↓
Output (1 unit) + Sigmoid
    ↓
Probability (0~1)
```

## 績效指標

- **Total Trades**: 總交易次數
- **Win Rate**: 勝率
- **Total Profit**: 總獲利
- **Avg Profit/Trade**: 平均每筆獲利
- **Max Drawdown**: 最大回撤

## 注意事項

1. **數據要求**：需要有完整的技術指標數據
2. **GPU加速**：如果有GPU，訓練會快很多
3. **過擬合風險**：注意訓練集和測試集的表現差異
4. **交易成本**：已考慮手續費0.1425%和證交稅0.3%
5. **實際應用**：回測結果僅供參考，實際交易需謹慎

## 進階調整

### 調整標籤定義
嘗試不同的標籤方法：
```python
# 方法1: 未來報酬法（當前）
LABEL_CONFIG = {'method': 'future_return', 'threshold': 0.02, 'days': 5}

# 方法2: 未來趨勢法
LABEL_CONFIG = {'method': 'future_trend', 'days': 5}
```

### 調整模型架構
在 `config.py` 中修改：
```python
MODEL_CONFIG = {
    'hidden_size': 256,    # 增加隱藏層大小
    'num_layers': 3,       # 增加LSTM層數
    'dropout': 0.4,        # 調整Dropout
}
```

### 調整訓練參數
```python
TRAINING_CONFIG = {
    'batch_size': 64,      # 調整批次大小
    'epochs': 200,         # 增加訓練輪數
    'learning_rate': 0.0001,  # 調整學習率
}
```

## Troubleshooting

### 問題1: CUDA out of memory
```python
# 減小批次大小
TRAINING_CONFIG['batch_size'] = 16
```

### 問題2: 訓練不收斂
```python
# 降低學習率
TRAINING_CONFIG['learning_rate'] = 0.0001
```

### 問題3: 過擬合
```python
# 增加Dropout
MODEL_CONFIG['dropout'] = 0.5
# 增加weight decay
TRAINING_CONFIG['weight_decay'] = 1e-4
```

## 未來改進

- [ ] 多股票擴展
- [ ] 加入更多特徵（基本面、法人）
- [ ] 嘗試 Transformer 架構
- [ ] 加入注意力機制
- [ ] 實作強化學習版本
- [ ] 加入風險管理模組
