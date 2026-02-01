# Backend Bug / TODO List

## 需求：投信累計持股數據

### 背景
前端 InstitutionalChart 需要顯示投信的「總持股數量」折線圖（類似外資的 `foreign_held_shares`）。目前外資持股線已透過 `foreign_holding.foreign_held_shares` 實現，但投信沒有對應的持股數據。

### 現狀
- `foreign_holding` 表只有外資持股欄位，沒有投信持股
- `institutional_investors` 表只有投信每日買賣超（`trust_net`），沒有累計持股

### 期望
請在 `/scanner/institutional/{symbol}` API 回傳中新增 `trust_held_shares` 欄位，方案二擇一：

**方案 A（推薦）：找到投信持股資料來源**
- 如果 TWSE/OTC 有提供投信持股統計，新增爬蟲和資料表
- API 回傳新增 `trust_held_shares` 欄位

**方案 B：用 `trust_net` 累計計算**
- 用 SQL window function 計算 `trust_net` 的 running sum 作為近似持股
- 例如：`SUM(trust_net) OVER (PARTITION BY symbol ORDER BY date) AS trust_held_shares`
- 注意：這只是近似值，起始點不準確

### 前端期望的 API 回應格式
```json
{
  "date": "2025-12-03",
  "foreign_net": 4237572.0,
  "trust_net": 130750.0,
  "foreign_held_shares": 12345678.0,
  "trust_held_shares": 987654.0
}
```

前端收到 `trust_held_shares` 後會自動在投信圖表右軸畫出持股折線，不需要額外修改前端。
