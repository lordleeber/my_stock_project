# trading_filter TODO

## 已完成
1. 將舊版 `x1~x30` 策略整理為 `strategyA~strategyI`。
2. 建立共用回測核心：`analysis_randomForest/trading_filter/multi_strategy_backtest.py`。
3. 建立日線快取流程：`analysis_randomForest/trading_filter/cache_daily_quotes.py`。
4. 每個策略皆有可重跑的 `grid_search.py`，並輸出：
   - `grid_results_all.csv`
   - `grid_results_top20.csv`
   - `best_config.json`
5. `strategyD~strategyI` 已完成實作與回測。
6. `README.md` 已更新為策略說明 + 各策略最佳成績比較。

## 下一步（優先順序）
1. 穩定性驗證（優先）
   - 不只看 2025-10-13 ~ 2025-11-20，改做多期間切片回測。
   - 建立固定評估模板：平均報酬、最大回撤、勝率、樣本數。
2. 小樣本防呆（優先）
   - 對高報酬但小樣本策略（如 F/H/I）設定最小成交檔數門檻。
   - 排名時同時考慮 `return_percent` 與 `selected_count`。
3. 交易摩擦成本
   - 納入手續費、交易稅、滑價，避免報酬高估。
4. 參數搜尋治理
   - 對每個策略保留「粗搜 + 細搜」設定，避免過度擬合。
   - 將最佳參數與實驗日期自動寫入單一 summary 檔。
5. 產線化準備
   - 定義每日執行流程（候選池 -> 快取行情 -> 策略 -> 報表）。
   - 整理輸出欄位，對接後續決策或監控頁面。

## 備註
1. 目前高報酬策略多集中在小樣本，不能直接視為可實盤。
2. 後續比較請優先看「跨期間穩定性」而非單一窗口最佳值。
