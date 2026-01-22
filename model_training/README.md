# Model Training (模型訓練模組)

本模組負責訓練機器學習/深度學習模型，旨在增強傳統交易策略的效能。目前的開發重點是 **訊號過濾器 (Signal Filter)**。

## 專案目標：AI 訊號過濾器

將傳統的「量能爆發」策略與 AI 模型結合。當傳統策略發出買進訊號時，利用 AI 模型進行二次確認，預測該訊號的獲利機率。只有當 AI 信心度 (Confidence Score) 超過門檻時，才真正執行交易。

### 核心流程 (Pipeline)

1.  **資料準備 (Data Preparation)**
    *   **來源**: `data/processed/daily_quotes` (已清洗的 Parquet 資料)。
    *   **特徵工程 (Feature Engineering)**:
        *   計算技術指標: RSI, KD, MACD, Bollinger Bands。
        *   時間序列特徵: 過去 N 天的 Return, Volume Change。
        *   大盤狀態: 加權指數的 Trend。
    *   **標註 (Labeling)**:
        *   針對每一個「爆量紅 K」訊號，計算未來 N 天 (例如 3 天) 的最大漲幅或收盤漲幅。
        *   定義正樣本 (Positive): 未來 3 天漲幅 > 2% (或其他門檻)。
        *   定義負樣本 (Negative): 否則。

2.  **模型訓練 (Training)**
    *   **模型架構**: 
        *   **LSTM / GRU**: 適合處理時間序列 (Sequence Data)。
        *   **XGBoost / LightGBM**: 適合處理表格型特徵 (Tabular Data)，訓練快且效果好。
    *   **輸入**: 訊號發生當下的特徵向量。
    *   **輸出**: 機率值 (0.0 ~ 1.0)，代表獲利的可能性。

3.  **模型部署 (Inference)**
    *   將訓練好的模型匯出 (如 `.pth`, `.joblib`)。
    *   整合至 `strategy/core.py`，在產生訊號時呼叫模型進行過濾。

## 目錄結構規劃
```
model_training/
├── features/       # 特徵工程腳本
├── models/         # 模型定義 (PyTorch/Sklearn)
├── training/       # 訓練腳本 (Train/Valid/Test Split)
├── artifacts/      # 存放訓練好的模型檔案
└── README.md       # 本文件
```

## 待辦事項
- [ ] 實作特徵工程腳本 (計算 RSI, MACD 等)。
- [ ] 實作資料標註腳本 (產生 X, y)。
- [ ] 建立基礎模型 (建議先從 Random Forest 或 XGBoost 開始，再嘗試 LSTM)。
- [ ] 訓練並評估模型準確度 (Accuracy/Precision/Recall)。
