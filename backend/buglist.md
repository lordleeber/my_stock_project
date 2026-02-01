# Backend Bug / TODO List

## 待重啟生效的修改

### 1. `/scanner/institutional/{symbol}` 缺少 `foreign_held_shares`
- **狀態**: 程式碼已修改，但容器未 rebuild
- **問題**: API 回傳缺少 `foreign_held_shares` 欄位，前端無法繪製外資總持股線
- **修改內容**: `InstitutionalData` model 已新增 `foreign_held_shares` 欄位，SQL 已 LEFT JOIN `foreign_holding` 表
- **解法**: `docker compose up -d --build backend`

### 2. `/scanner/candlestick/{symbol}` 2867 三商壽 OHLCV 含 NULL
- **狀態**: 已加防護（skip NULL rows），但需確認根本原因
- **問題**: `daily_quotes` 表中 `symbol='2867'` 有部分日期的 OHLCV 欄位為 NULL，導致 `float(None)` 報錯
- **排查 SQL**:
  ```sql
  SELECT date, open, high, low, close, volume
  FROM daily_quotes
  WHERE symbol='2867'
    AND (open IS NULL OR high IS NULL OR low IS NULL OR close IS NULL OR volume IS NULL);
  ```
