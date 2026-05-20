# Backtester

Rolling monthly portfolio backtester. Consumes monthly strategy outputs from `strategies/`,
applies walk-forward ML scoring, and simulates buy/sell decisions using real historical prices.

---

## Pipeline Overview

```
strategies/output/<YYYY-MM-DD>/dataset_strategy.csv
      ↓
run_rolling.py    walk-forward 打分 → 市場判斷 → 調整持倉 → 記錄損益
      ↓
backtester/output/rolling/
  rolling_trades.csv     每筆交易紀錄
  rolling_monthly.csv    每月摘要
  rolling_summary.json   整體統計
```

---

## Rolling Portfolio 邏輯（每月）

1. 讀取當月 `dataset_strategy.csv`，用 walk-forward 模型即時打分（`ml_score`）
2. 取 top-N 候選股（`--top-n`）
3. 完整月度輪倉（不依市場狀態調整行為）：
   - 全部持倉於前一交易日開盤平倉
   - 當月 top-N 候選於 entry_date 開盤建倉
4. 市場狀態（regime）僅作為記錄欄位寫入 `rolling_monthly.csv`，**不影響進出場決策**

所有買賣價格使用 DB 真實開盤價（`daily_quotes.open`）。

---

## 市場狀態判斷（僅供記錄）

來源：`market_indices` 表（大盤指數）。回測會在 `rolling_monthly.csv` 的 `regime` 欄位標記每月狀態，方便事後分析績效與市場環境的相關性，但不會改變進出場行為。

| 狀態 | 條件 |
|------|------|
| Bull | MA20 > MA60 |
| Bear | MA20 < MA60 且 close < MA20 |
| Sideways | 其他 |

> 歷史版本曾在 Bear 月份「全部出場、空手等」，現已移除 — 因為實測下 Bear 月份平均仍有正期望報酬，跳過反而錯失收益。

---

## Walk-Forward 模型選擇

Target playbook_date D → 使用 `models_selection/<YYYY-MM-DD>/` 中 `train_through_playbook_date < D` 的最新模型。
例如：target 2024-07-11 → 用 `models_selection/2024-06-11/`（若存在）。

若無任何 versioned 模型，fallback 到 `models_selection/latest/`。

---

## 交易成本

| 項目 | 預設值 |
|------|--------|
| 手續費（買 + 賣） | 0.1425%（各單邊） |
| 證交稅（賣方） | 0.3% |

---

## Files

| 檔案 | 說明 |
|------|------|
| `run_rolling.py` | 主回測程式 |
| `summarize_range.py` | 回測結果統計摘要 |
| `data_loader.py` | DB 行情查詢 |
| `simulator.py` | 交易成本計算 |

---

## Usage

### 回測
```bash
venv/bin/python3 backtester/run_rolling.py \
  --start-date 2022-07-11 \
  --end-date 2025-10-11 \
  --top-n 10
```

### 查看結果
```bash
venv/bin/python3 backtester/summarize_range.py
venv/bin/python3 backtester/summarize_range.py --show-monthly
```

### 當月推薦（production）
```bash
venv/bin/python3 strategies/step5_score_and_publish.py --date 2025-10-11
```

### 參數說明

| 參數 | 預設 | 說明 |
|------|------|------|
| `--start-date` | 必填 | 回測起始 playbook_date（YYYY-MM-DD，canonical playbook release date） |
| `--end-date` | auto-detect | 回測結束 playbook_date；省略則自動取最新 candidates_scored + DB 報價覆蓋的那天 |
| `--top-n` | 無限制 | 每 playbook 取前 N 名候選股 |
| `--position-amount` | 100,000 | 每檔固定投入金額（TWD） |
| `--models-root` | `models_selection/` | ML 模型根目錄 |
| `--commission-rate` | 0.001425 | 手續費率 |
| `--tax-rate` | 0.003 | 證交稅率 |

---

## Output

### rolling_trades.csv
每筆已結清或仍持有的交易紀錄。

| 欄位 | 說明 |
|------|------|
| `symbol` | 股票代號 |
| `entry_date` / `exit_date` | 進出場日期 |
| `entry_price` / `exit_price` | 進出場價格 |
| `shares` | 股數 |
| `gross_pnl` | 毛損益 |
| `cost` | 手續費 + 稅 |
| `net_pnl` | 淨損益 |
| `return_pct` | 報酬率（% of capital_used） |
| `exit_reason` | `monthly_rotation` / `still_open` |

### rolling_monthly.csv
每月持倉狀況與損益摘要。
