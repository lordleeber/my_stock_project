"""
深度學習股票交易系統配置
"""

# 資料庫設定
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'user': 'user',
    'password': 'password',
    'database': 'stock_db'
}

# 股票設定
SYMBOL = '2330'  # 台積電
STOCK_NAME = 'TSMC'

# 交易設定
SHARES_PER_TRADE = 1000  # 1張 = 1000股
COMMISSION_RATE = 0.001425  # 手續費 0.1425%
TAX_RATE = 0.003  # 證交稅 0.3%

# 數據設定
TRAIN_START_DATE = '2025-01-01'
TRAIN_END_DATE = '2025-10-31'
TEST_START_DATE = '2025-11-01'
TEST_END_DATE = '2026-01-29'

SEQUENCE_LENGTH = 20  # 使用過去20天的數據
PREDICTION_HORIZON = 5  # 預測未來5天

# 特徵設定
FEATURES = [
    # 價格相關
    'close', 'open', 'high', 'low', 'volume',
    # 技術指標
    'ma5', 'ma10', 'ma20', 'ma60',
    'vma5', 'vma10', 'vma20',
    'rsi', 'macd', 'macd_signal',
    # 價格變化率
    'return_1d', 'return_5d',
    'volume_ratio'
]

# 模型設定
MODEL_CONFIG = {
    'input_size': None,  # 會根據特徵數量自動設定
    'hidden_size': 128,
    'num_layers': 2,
    'dropout': 0.3,
    'output_size': 1
}

# 訓練設定
TRAINING_CONFIG = {
    'batch_size': 32,
    'epochs': 100,
    'learning_rate': 0.001,
    'weight_decay': 1e-5,
    'early_stopping_patience': 10,
    'device': 'cuda'  # 如果有GPU用'cuda'，否則用'cpu'
}

# 標籤定義設定
LABEL_CONFIG = {
    'method': 'future_return',  # 'future_return' or 'future_trend'
    'threshold': 0.02,  # 2% 報酬門檻
    'days': 5  # 未來5天
}
