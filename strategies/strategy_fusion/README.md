# strategy_fusion

? A~I ????嚗1嚗??格??舀????亦??末?游??????賂???桐???閬??葫??
## ?詨???
- 撠?瑼蟡典遣蝡?`sig_A ~ sig_I` 銋???0/1嚗?- 閮?甈?靘?A~I ?風?脫?雿?`return_percent` 甇????????- ?Ｙ? `fusion_score` 敺??脰?嚗?  - `score_threshold` ?瑼駁?瞈?  - `max_per_industry` ?Ｘ平銝?
  - `max_picks` 蝮賣??訾???- ?詨?∠巨敺??函絞銝?箏閬??葫嚗???+ 蝘餃??? + ???箏嚗?
## ?身?葫閮剖?
- `entry_rule`: ?券脣嚗all`嚗?- `take_profit_rule`: `target_price_if_above_entry`
- `stop_loss_pct`: `0.07`
- `trailing_stop_pct`: `0.03`
- `max_hold_days`: `15`
- `max_position_amount`: `200000`

## ?瑁??孵?
```bash
.\.venv\Scripts\python.exe strategies/strategy_fusion/backtest.py
```

## Fusion v2嚗op-K 蝑?豢??剁?
- ?? `strategyA~I/best_config.json` 霈瘥??亦?甇瑕銵函??- ?蕪 `entered_count` 憭芸????亙?嚗???`K` ???乓?- ?券?蝑??蟡剁?`sig_A~sig_I`嚗?∴????舀?????亙像?毽??
?瑁?嚗?```bash
.\.venv\Scripts\python.exe strategies/strategy_fusion/v2_selector_backtest.py --top-k-strategies 3 --min-strategy-entered 20 --min-votes 2
```

頛詨嚗?- `strategies/strategy_fusion/results_v2/selected_candidates_v2.csv`
- `strategies/strategy_fusion/results_v2/fusion_v2_trade_backtest.csv`
- `strategies/strategy_fusion/results_v2/fusion_v2_summary.json`

v2 Optuna 隤踹?嚗?```bash
.\.venv\Scripts\python.exe strategies/strategy_fusion/optuna_search_v2.py --n-trials 500 --min-entered-count 20
```

v2 Optuna 頛詨嚗?- `strategies/strategy_fusion/results_v2/optuna_v2_results_all.csv`
- `strategies/strategy_fusion/results_v2/optuna_v2_results_top20.csv`
- `strategies/strategy_fusion/results_v2/optuna_v2_best_config.json`
- `strategies/strategy_fusion/results_v2/optuna_v2_study_summary.json`

## 頛詨瑼?
- `strategies/strategy_fusion/results/selected_candidates.csv`
- `strategies/strategy_fusion/results/fusion_trade_backtest.csv`
- `strategies/strategy_fusion/results/fusion_summary.json`

## 瘜冽?鈭?
- ????洵銝?????臬???蝔??舀?頛???銝誨銵冽?蝯?雿喳??詻?- 銝?甇亙遣霅堆??????瑼餅??`grid/optuna` ??嚗??臬摰潦?

