# Stock Analysis Project

台股月度 EPS 預測 → ML 選股 → 滾動回測 完整流程。

> **每月公告日後的標準作業流程** → 參見 [`MONTHLY_PLAYBOOK.md`](MONTHLY_PLAYBOOK.md)

---

## 架構總覽

```
train_eps/        EPS 預測模型訓練與發布
strategies/       ML 選股特徵工程、排名模型訓練
models_selection/ 選股模型（walk-forward，每月一版）
backtester/       滾動投資組合回測
calculator/       DB 衍生表計算（technical_indicators / shareholding_concentration / valuation_daily 等）
scripts/          GCP 部署與資料上傳腳本
common/           共用 schema、工具模組
```

---

## 核心流程

### 1. EPS 預測（train_eps/）

```bash
# 資料準備 → 訓練 → 評估 → 發布（或一鍵執行）
# --date 必須是 canonical playbook release date = cutoff（公告日）+1
# 5/8/11 月為 16 號，其餘月份為 11 號
venv/bin/python3 train_eps/step1_prepare_data.py        --date 2025-10-11
venv/bin/python3 train_eps/step2_train.py               --date 2025-10-11
venv/bin/python3 train_eps/step3_evaluate.py            --date 2025-10-11
venv/bin/python3 train_eps/step4_predict_and_publish.py --date 2025-10-11
venv/bin/python3 train_eps/run_pipeline.py              --date 2025-10-11
```

### 2. 策略特徵工程（strategies/）

```bash
# 單月
venv/bin/python3 strategies/step1_prepare_data.py      --year 2025 --month 10
venv/bin/python3 strategies/step2_finalize_strategy.py --year 2025 --month 10

# 批次（歷史資料）
venv/bin/python3 strategies/step1_batch_prepare_data.py
venv/bin/python3 strategies/step2_batch_finalize_strategy.py
```

### 3. 選股模型訓練（strategies/）

```bash
# 產生訓練資料
venv/bin/python3 strategies/step3_analyze_feature_returns.py

# Walk-forward 批次訓練（回測用，每月一版）
venv/bin/python3 strategies/step4_batch_train_selection_model.py

# 正式訓練（全資料，production 用）
venv/bin/python3 strategies/step4_train_selection_model.py
```

### 4. 滾動回測（backtester/）

```bash
venv/bin/python3 backtester/run_rolling.py \
  --start_year 2022 --start_month 7 \
  --end_year 2025 --end_month 10 \
  --top-n 10 --position-amount 100000

# 查看結果
venv/bin/python3 backtester/summarize_range.py

# 當月推薦（production）
venv/bin/python3 backtester/score_candidates.py --year 2025 --month 10
```

---

## Walk-Forward 設計

- 模型位置：`models_selection/<cutoff_year>/<cutoff_month>/selection_model.pkl`
- 回測月份 M 使用 cutoff < M 的最新模型，避免 look-ahead bias
- 例：回測 2025/03 → 使用 `models_selection/2025/02/`

---

---

## 主要輸出

| 類型 | 路徑 |
|------|------|
| EPS 模型 | `models_eps/<YYYY-MM-DD>/`（playbook release date） |
| 月度特徵快照 | `strategies/output/<year>/<month>/dataset_strategy.csv` |
| 選股模型 | `models_selection/<year>/<month>/selection_model.pkl` |
| 回測交易紀錄 | `backtester/output/rolling/rolling_trades.csv` |
| 回測月摘要 | `backtester/output/rolling/rolling_monthly.csv` |
| 回測統計 | `backtester/output/rolling/rolling_summary.json` |

---

## Notes

- 產生的 csv / json / pkl artifacts 不 commit，除非明確要求
- 共用 DB schema 變更請同步更新 `common/schemas.py`
- 季報資料一律走 XBRL（`*_xbrl` 表）。舊版季報 pipeline 已停用並移到各模組 `_deprecated/`，DB 舊表保留為 archive。
  - 公告期內每日 scrape：`./schedules/xbrl_scrape_daily.sh`（launchd 自動執行；不入庫）
  - 公告期末/補資料入庫：`./schedules/xbrl_process_import.sh [YYYYQX]`（process→import；前提是 raw 已存在）
- 詳細說明見各子目錄的 `README.md` 與 `CLAUDE.md`
