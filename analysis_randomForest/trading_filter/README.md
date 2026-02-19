# trading_filter

這個資料夾是針對 `2025-10-13 ~ 2025-11-20` 的交易回測實驗，基礎股票池來自：
- `analysis_randomForest/trading_filter/trade_candidates_2025_1013_1120.csv`
- `analysis_randomForest/trading_filter/daily_quotes_20251013_1120_sii.csv`

## 主要檔案
- `analysis_randomForest/trading_filter/build_candidates.py`: 建立候選股票池
- `analysis_randomForest/trading_filter/cache_daily_quotes.py`: 快取日線資料
- `analysis_randomForest/trading_filter/multi_strategy_backtest.py`: 共用回測核心
- `analysis_randomForest/trading_filter/strategyA` ~ `analysis_randomForest/trading_filter/strategyI`: 各策略網格搜尋
- `analysis_randomForest/trading_filter/todo.md`: 待辦事項

## 策略重點（A~I）
- A: 固定停利停損 + 時間出場（全進場）
- B: A + 移動停損
- C: 進場過濾（回檔/條件進場）+ 目標價停利
- D: 分批停利 + 剩餘部位動態出場
- E: ATR 波動度自適應停利停損
- F: 相對強弱分數篩選後再交易
- G: 分時段（早/晚）不同停利停損
- H: 投組層級限制（最多持股數、單產業上限）
- I: 信心加權配資（高分多配，低分少配）

## 目前最佳結果（各策略 best_config）
- A: `A_tp15_sl10_h15`, `return_percent=5.7205`, `total_revenue=1175225.72`
- B: `B_tp14_sl5_tr8_h12`, `return_percent=3.7183`, `total_revenue=763883.56`
- C: `C_pullback_from_ref_close_0.93_tpTarget_sl6_h15`, `return_percent=7.8458`, `total_revenue=287869.5`（僅 29 檔成交）
- D: `D_tp1_10_tp2_none_part_30_sl_7_tr_3_h_15`, `return_percent=4.9761`, `total_revenue=1022291.08`
- E: `E_atr3_tp30_sl20_trnone_h15`, `return_percent=5.4385`, `total_revenue=1117293.0`
- F: `F_composite_q60_u103_tp14_sl7_trnone_h15`, `return_percent=12.6613`, `total_revenue=58090.0`（僅 5 檔）
- G: `G_sw5_etp10_esl5_ltp14_lsl7_trnone_h15`, `return_percent=4.4080`, `total_revenue=905580.89`
- H: `H_n20_ind2_vol2000_up103_tp14_sl7_trnone_h15`, `return_percent=13.4098`, `total_revenue=58440.0`（僅 4 檔）
- I: `I_vol1000_up103_std60_g70_a100-300_tp14_sl7_trnone_h15`, `return_percent=12.6594`, `total_revenue=57998.3`（僅 5 檔）

## 解讀原則
- `return_percent` 高不一定代表可實務化，需看 `selected_count/entered_count`。
- F/H/I 報酬率高，但樣本非常小，穩定性風險較高。
- 若偏向全股票池穩定性，可優先比較 A/D/E/G。
