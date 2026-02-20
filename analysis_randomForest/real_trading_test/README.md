# real_trading_test

這個資料夾是「接近實盤」的測試區。
目標是用固定日期的可得資料產生訊號，再依規則模擬買賣。

## 檔案與流程

1. 產生 2025-10-09 候選清單（含當日 close/volume/pe）
- `build_trade_candidates_2025_1009.py`
- 輸出：`trade_candidates_2025_1009.csv`

2. 用 fusion v2 參數做單日推論（只決定買/不買）
- `run_fusion_v2_inference.py`
- 輸出：
- `fusion_v2_actions_2025_1009.csv`
- `fusion_v2_buy_list_2025_1009.csv`
- `fusion_v2_watch_list_2025_1009.csv`
- `fusion_v2_inference_summary_2025_1009.json`

3. 快取候選股票日線（10/09~11/20）
- `cache_candidate_daily_quotes.py`
- 輸出目錄：`daily_cache_20251009_1120/`
- 每日檔：`quotes_YYYYMMDD.csv`
- 合併檔：`all_quotes.csv`

4. 滾動式模擬（每日判斷，隔天 open 成交，持倉防重複買入）
- `simulate_fusion_v2_20251009_1120.py`
- 輸出目錄：`sim_20251009_1120/`
- 重點輸出：
- `simulation_summary_20251009_1120.json`
- `orders_signal_20251009_1120.csv`
- `orders_execution_20251009_1120.csv`
- `positions_end_20251120.csv`

5. 一次訊號回測（只用 10/09 訊號，10/13 開盤買，跑到 11/20）
- `backtest_one_shot_1009_signal_1013_1120.py`
- 輸出目錄：`one_shot_1009_to_1120/`
- 重點輸出：
- `summary_one_shot_1009_signal_1013_1120.json`
- `trades_one_shot_1009_signal_1013_1120.csv`

## 快速指令

```bash
.\.venv\Scripts\python.exe analysis_randomForest/real_trading_test/build_trade_candidates_2025_1009.py
.\.venv\Scripts\python.exe analysis_randomForest/real_trading_test/run_fusion_v2_inference.py
.\.venv\Scripts\python.exe analysis_randomForest/real_trading_test/cache_candidate_daily_quotes.py
.\.venv\Scripts\python.exe analysis_randomForest/real_trading_test/simulate_fusion_v2_20251009_1120.py
.\.venv\Scripts\python.exe analysis_randomForest/real_trading_test/backtest_one_shot_1009_signal_1013_1120.py
```

## 目前結果摘要

- 一次訊號版（10/09 訊號 -> 10/13 進場 -> 11/20）：
- `return_percent = 4.1539%`

- 滾動式版（每日訊號 + 隔天 open 成交 + 持倉管理）：
- `return_percent_on_buy_capital = 1.7805%`

## 注意

- 單日推論只會輸出「買/不買」，不會直接輸出賣出結果。
- 賣出結果必須結合之後每天的行情資料與出場規則才會產生。
