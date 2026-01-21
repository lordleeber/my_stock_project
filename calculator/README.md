# Stock Indicator Calculator (指標運算模組)

本模組負責從資料庫讀取歷史收盤價，並預先計算多種常用的技術指標，存回 `technical_indicators` 表格中，以提升 API 查詢效率。

## 實作指標
- **Moving Average (MA)**: 包含 5, 10, 20, 60, 120, 240 日價格均線。
- **Volume Moving Average (VMA)**: 包含 5, 10, 20, 60, 120, 240 日成交量均線。

## 核心邏輯
- 採用 **Pandas 向量化運算 (Vectorized Operations)**，效率極高。
- 使用 **Grouped apply**：針對不同股票代號 (Symbol) 獨立計算時間序列指標。
- 支援全量重算：確保歷史資料的連續性。

## 如何使用
透過 Docker Compose 執行計算任務：
```bash
docker-compose up --build calculator
```
