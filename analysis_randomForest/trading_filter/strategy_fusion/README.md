# strategy_fusion

這是 A~I 的融合版（v1），目標是把各策略的偏好整合成一個分數，再用單一投組規則回測。

## 核心做法
- 對每檔股票建立 `sig_A ~ sig_I` 九個訊號（0/1）。
- 訊號權重依 A~I 的歷史最佳 `return_percent` 正規化後加權。
- 產生 `fusion_score` 後，進行：
  - `score_threshold` 門檻過濾
  - `max_per_industry` 產業上限
  - `max_picks` 總檔數上限
- 選出股票後，用統一出場規則回測（停損 + 移動停損 + 時間出場）。

## 預設回測設定
- `entry_rule`: 全進場（`all`）
- `take_profit_rule`: `target_price_if_above_entry`
- `stop_loss_pct`: `0.07`
- `trailing_stop_pct`: `0.03`
- `max_hold_days`: `15`
- `max_position_amount`: `200000`

## 執行方式
```bash
.\.venv\Scripts\python.exe analysis_randomForest/trading_filter/strategy_fusion/backtest.py
```

## Fusion v2（Top-K 策略選擇器）
- 先從 `strategyA~I/best_config.json` 讀每個策略的歷史表現。
- 過濾 `entered_count` 太小的策略後，挑前 `K` 名策略。
- 用這些策略的投票（`sig_A~sig_I`）選股，而不是把所有策略平均混合。

執行：
```bash
.\.venv\Scripts\python.exe analysis_randomForest/trading_filter/strategy_fusion/v2_selector_backtest.py --top-k-strategies 3 --min-strategy-entered 20 --min-votes 2
```

輸出：
- `analysis_randomForest/trading_filter/strategy_fusion/results_v2/selected_candidates_v2.csv`
- `analysis_randomForest/trading_filter/strategy_fusion/results_v2/fusion_v2_trade_backtest.csv`
- `analysis_randomForest/trading_filter/strategy_fusion/results_v2/fusion_v2_summary.json`

v2 Optuna 調參：
```bash
.\.venv\Scripts\python.exe analysis_randomForest/trading_filter/strategy_fusion/optuna_search_v2.py --n-trials 500 --min-entered-count 20
```

v2 Optuna 輸出：
- `analysis_randomForest/trading_filter/strategy_fusion/results_v2/optuna_v2_results_all.csv`
- `analysis_randomForest/trading_filter/strategy_fusion/results_v2/optuna_v2_results_top20.csv`
- `analysis_randomForest/trading_filter/strategy_fusion/results_v2/optuna_v2_best_config.json`
- `analysis_randomForest/trading_filter/strategy_fusion/results_v2/optuna_v2_study_summary.json`

## 輸出檔案
- `analysis_randomForest/trading_filter/strategy_fusion/results/selected_candidates.csv`
- `analysis_randomForest/trading_filter/strategy_fusion/results/fusion_trade_backtest.csv`
- `analysis_randomForest/trading_filter/strategy_fusion/results/fusion_summary.json`

## 注意事項
- 這是融合版第一版，重點是先打通流程與可比較結果，不代表最終最佳參數。
- 下一步建議：把權重與門檻改為 `grid/optuna` 搜尋，而不是固定值。
