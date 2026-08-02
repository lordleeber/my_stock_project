# Monthly Playbook

每月公告日後一天的標準作業流程：跑 EPS 模型、產出選股名單、重訓 selection model。

> 資料管線（scraper / processor / importer / calculator）由 systemd 自動排程，不在本 playbook 範圍。詳見 [`schedules/CLAUDE.md`](schedules/CLAUDE.md)。

> **Date narration convention**: CLI / 目錄 / 敘述都用具體 `YYYY-MM-DD`（playbook_date = cutoff +1）。
> - **`cutoff_date`** = target cohort 的 PIT 截斷日（例：cohort 2026-04-11（cutoff 2026-04-10））。
> - **`train_through_playbook_date`** = selection model 訓練資料上界 cohort 的 playbook_date（例：train_through=2026-04-11）。
> - 不要寫「model 的 cutoff_date」— 用 `train_through_playbook_date`。
> 完整規則見 [`strategies/CLAUDE.md` § Date Convention](strategies/CLAUDE.md#date-convention-read-first)（single source of truth）。

---

## 公告日曆（cutoff_date）

| 月份 | cutoff | 公告事件 | train_eps 標的 |
|---|---|---|---|
| 01 | 01/10 | 前年 12 月營收 | 前年 Q4 EPS delta |
| 02 | 02/10 | 1 月營收 | Q1 EPS delta |
| 03 | 03/10 | 2 月營收 | Q1 EPS delta |
| **04** | **04/10** | 3 月營收 + **前年年報（Q4 完整財報）** | Q1 EPS delta |
| **05** | **05/15** | 4 月營收 + **Q1 季報** | Q2 EPS delta |
| 06 | 06/10 | 5 月營收 | Q2 EPS delta |
| 07 | 07/10 | 6 月營收 | Q2 EPS delta |
| **08** | **08/15** | 7 月營收 + **Q2 季報** | Q3 EPS delta |
| 09 | 09/10 | 8 月營收 | Q3 EPS delta |
| 10 | 10/10 | 9 月營收 | Q3 EPS delta |
| **11** | **11/15** | 10 月營收 + **Q3 季報** | Q4 EPS delta |
| 12 | 12/10 | 11 月營收 | Q4 EPS delta |

> 粗體的月份（04 / 05 / 08 / 11）是「**重大資料月**」：除月營收外，還有年報或季報加進特徵集，模型可用的特徵會比相鄰月份多。

---

## 標準作業（公告日當天 22:00 後或隔日清晨跑）

設今天是 **M/cutoff+1**（例如 4/11、5/16、8/16、11/16）。先確認 cutoff 當日的 `daily_update.sh` 已成功（至少 raw + DB 都有資料）。

### 一條龍指令（按順序，一定要 step1+2 早於 step3）

```bash
# DATE: 本月的 canonical playbook_date = cutoff（公告日）+1（5/8/11 月 = 16 號，其餘月份 = 11 號）
# PREV_DATE: 上一個月的 playbook_date（重訓 selection model 用）
# 兩者都由 train_eps/shared_config.py::playbook_run_date 唯一定義。
DATE=2026-04-11
PREV_DATE=2026-03-11

# ① EPS 模型（含 prepare → train → evaluate → predict）
venv/bin/python3 train_eps/run_pipeline.py --date $DATE

# ② strategies 本月候選（cutoff_date = DATE - 1 day）
venv/bin/python3 strategies/step1_prepare_data.py      --date $DATE
venv/bin/python3 strategies/step2_finalize_strategy.py --date $DATE
# ↑ 若 DB 還沒匯入下個交易日報價（典型情境：cutoff 是週五、entry_date 是下週一，
#   在 cutoff+1 週六/週日跑時 DB 還沒 Mon 資料），step2 會 raise。
#   解法：加 --entry-date YYYY-MM-DD 明確指定下個交易日，跳過 DB 驗證。
#   範例：venv/bin/python3 strategies/step2_finalize_strategy.py \
#           --date 2026-05-16 --entry-date 2026-05-18
#   --entry-date 只影響 entry_date 欄位（進場日/報酬錨點）；技術與營收特徵一律以
#   cutoff_date 為 as-of，與此參數無關。

# ③ 重建 fwd_return ground truth（現在 PREV_DATE 的 exit_date 才能定義出來）
venv/bin/python3 strategies/step3_analyze_feature_returns.py

# ④ 訓 train_through=PREV_DATE 的 selection model（用最新 ground truth）
venv/bin/python3 strategies/step4_train_selection_model.py --date $PREV_DATE

# ⑤ 對本月候選打分，產出最終選股名單
venv/bin/python3 strategies/step5_score_and_publish.py --date $DATE
```

完成後可選：
```bash
# ⑥ 延長 rolling 回測曲線到 PREV_DATE（觀察用）
venv/bin/python3 backtester/run_rolling.py \
  --start-date 2022-07-11 \
  --end-date $PREV_DATE \
  --top-n 25 --position-amount 100000
```

> **一次性遷移（2026-06 multi-seed ensemble 上線）**：上面 ④ 的每月
> `step4 --date $PREV_DATE` 只會把**新的那一個 cohort** 訓成 ensemble（預設
> `--n-seeds 10`，seeds 42–51）。但整條 walk-forward 回測要一致，**全部歷史 cohort
> 都得是 10-seed ensemble** —— 2026-06 上線時已對全部 47 個 cohort 做過一次性 batch
> 重訓 + 重評分（本機已完成）。模型 artifact 是 gitignored，所以**全新 checkout、
> 或磁碟上還留著 2026-06 前的單 seed 模型時**，要重建：
> ```bash
> # （可選）先備份舊單 seed 模型，避免直接覆蓋；全新環境沒有舊模型可跳過
> mv models_selection models_selection_pre_ensemble
> venv/bin/python3 strategies/step4_batch_train_selection_model.py   # 預設 --n-seeds 10，重訓全 cohort
> venv/bin/python3 strategies/step5_batch_score_and_publish.py       # 重新評分（寫入 scored_by_ensemble_* 欄）
> venv/bin/python3 backtester/run_rolling.py --start-date 2022-07-11 --top-n 25 --position-amount 100000
> ```
> ⚠️ **不要加 `--skip-existing`**：它會跳過已存在的舊單 seed `selection_model.pkl`、
> 不會覆蓋成 ensemble，導致回測新舊模型混用。詳見 `strategies/CLAUDE.md §
> Multi-seed ensemble` 與記憶 `project_ensemble_validation_2026_06`。

---

## 為什麼順序不能亂

```
step1+2(M)  必須最早跑 ─── 產出 M 的 dataset_strategy.csv（含 entry_date）
                            │
                            ▼ 因為...
step3       需要 M 的 entry_date 來定義 M-1 的 exit_date
                            │
                            ▼ 才能算出...
            M-1 的 fwd_return（被當成 step4 訓練標籤）
                            │
                            ▼
step4       訓 train_through=M-1 的新模型
                            │
                            ▼
step5(M)    walk-forward 自動挑到剛訓好的 train_through=M-1 模型
```

> 跳過 step3 / step4 也能跑出 step5 名單，但 step5 會退回去用更舊的 train_through（例如 M-2、M-3），喪失最新一個月的訓練訊號。

---

## 主要產出

| 階段 | 產出 |
|---|---|
| ① train_eps | `models_eps/<YYYY-MM-DD>/predictions_results.csv`（每檔 EPS delta 預測；目錄即 playbook run date） |
| ② strategies step1+2 | `strategies/output/<DATE>/dataset_strategy.csv`（step5 的輸入）、`trade_candidates.csv`（診斷用，生產流程不讀） |
| ③ step3 | `strategies/output/feature_return_analysis.csv`（含到 PREV_DATE 的 fwd_return） |
| ④ step4 | `models_selection/<PREV_DATE>/selection_model.pkl` + `feature_importance.csv` + `latest.json` |
| ⑤ step5 | `models_selection/<DATE>/candidates_scored.csv`（**最終選股名單**） |

選股建議：**`candidates_scored.csv` 依 `ml_rank` 取 top-25 等權買進，於 `entry_date` 開盤建倉**。

> top-25 落在 2026-06 驗證出的 seed-robust Sharpe 高原（跨 4 個不相交 ensemble，月 Sharpe 在 N≈20-26 升到穩定的 ~0.74，過 ~26 才回落；對比 N=10 的 ~0.67）。詳見 `strategies/CLAUDE.md` 與記憶 `project_ensemble_validation_2026_06`。

---

## 特殊月份對照

### 04 月（DATE = YYYY-04-11）
- 新到資料：3 月營收 + **前年年報**
- 04 模型可用 Q4 為 anchor（含 Q4 完整 XBRL），比 03 模型多 2 個 XBRL 特徵
- 重訓 selection model train_through_playbook_date = (YYYY)-03-11

### 05 月（DATE = YYYY-05-16，因 5/15 是 Q1 季報日）
- 新到資料：4 月營收 + **Q1 季報**
- 05 模型 anchor 從 Q4 切換到 **Q1**，所有後續 06、07 月模型也以 Q1 為 anchor
- 重訓 selection model train_through_playbook_date = (YYYY)-04-11

### 08 月（DATE = YYYY-08-16）
- 新到資料：7 月營收 + **Q2 季報**
- 08 模型 anchor 切換到 **Q2**
- 重訓 selection model train_through_playbook_date = (YYYY)-07-11

### 11 月（DATE = YYYY-11-16）
- 新到資料：10 月營收 + **Q3 季報**
- 11 模型 anchor 切換到 **Q3**
- 重訓 selection model train_through_playbook_date = (YYYY)-10-11

### 跨年的 01 月
- `DATE = YYYY-01-11`、`PREV_DATE = (YYYY-1)-12-11`

---

## 確認資料是否齊備

跑 step1 前可以先檢查 cutoff 當日的 daily_update 有沒有過：

```bash
# 例：cutoff 是 2026-04-10
ls logs/daily_update_20260410_*.log | head -1   # 應有 log
grep "Daily Stock Data Update Completed" logs/daily_update_20260410_*.log
```

若 daily 失敗，先補跑：
```bash
./schedules/daily_update.sh 20260410
```

monthly_update（營收）的 systemd 排在每月 1–15 日；如果手動補 monthly：
```bash
./schedules/monthly_update.sh
```

季報 XBRL：
- 公告期內由 systemd 每天跑 `xbrl_scrape_daily.sh`，持續累積 raw 但不入庫
- 公告期末（或要更新 DB 時）手動跑全鏈路：
```bash
./schedules/xbrl_process_import.sh         # 視窗內依今天日期決定季別
./schedules/xbrl_process_import.sh 2026Q1  # 直接指定季別（補跑或視窗外）
```

---

## Walk-forward 時序圖（以 04 月為例）

```
2026-04-10 (Fri)  cutoff_date — 3 月營收 + 2025 年報全數公告完成
2026-04-10 22:00  daily_update.sh 跑完，DB 有 2026-04-10 收盤 + 籌碼
2026-04-11 (Sat)  本 playbook 標準流程（DATE = 2026-04-11）：
                  ├── train_eps --date 2026-04-11
                  ├── strategies step1+2 --date 2026-04-11
                  ├── strategies step3 (現在能算出 2026-03-11 cohort 的 fwd_return)
                  ├── strategies step4 --date 2026-03-11 (train_through_playbook_date)
                  └── strategies step5 --date 2026-04-11 → 名單出爐
2026-04-13 (Mon)  名單按開盤價建倉 (entry_date)
                  ...持有約 25 個交易日 (依 5 月 entry 而定) ...
2026-05-15 (Fri)  Q1 季報日 → cutoff_date
2026-05-15 開盤    上一月 cohort 平倉 (5/15 開盤 = 下一輪 entry 前一交易日)
2026-05-16 (Sat)  跑 5 月 playbook → 訓 train_through_playbook_date=2026-04-11 的 selection model、出 5 月名單
```

---

## 常見問題

### Q1: 為什麼 step5 顯示 `model used: 2026-02-11` 而不是最新？
A: 你跳過了 step3 + step4。`models_selection/2026-03-11/` 可能只有 `candidates_scored.csv` 沒有 `selection_model.pkl`。step5 的 walk-forward 規則是「最新有 pkl 的 `train_through_playbook_date < 目標 playbook_date`」。

### Q2: train_eps 同一個 `--date` 重跑兩次，model MAE 一樣是不是 bug？
A: 不是。`step1_prepare_data` 用 PIT cutoff（`--date` 那天）截斷資料，固定 `seed=42`，相同輸入 → 相同模型。MAE 數字相同就代表 PIT 行為正確。

### Q3: 如果某天忘了跑，事後補做有差嗎？
A: 沒差。所有指令都是 idempotent + PIT，過幾天再補跑會得到完全相同的 EPS 模型；selection model 也會是相同模型，不受跑的時點影響。**唯一例外是 step5**：若中間有更新過 selection model，補跑出的名單可能與當天不同。

### Q4: PREV_DATE 的計算？
- PREV_DATE = 上一個 canonical playbook_date（直接查 [`MONTHLY_PLAYBOOK` 公告日曆](#公告日曆cutoff_date)）。
- 目標 DATE 是 01-11 → PREV_DATE = (YYYY-1)-12-11
- 目標 DATE 是 11-16 → PREV_DATE = YYYY-10-11
- 一般月 → PREV_DATE 是上個月對應的 11 或 16 號

### Q5: step2 報 `daily_quotes 沒有 >= YYYY-MM-DD 的交易日資料` 怎麼辦？
通常出現在 cutoff+1 當天/隔日提前跑：cutoff 是週五、entry_date 是下週一，DB 還沒匯入下週一的報價。新版（commit 866fc36）刻意 raise，避免舊版 silent fallback 把週末日期當 entry_date。兩種解法：

1. **等今天 daily pipeline 跑完**（推薦，運維乾淨）：等 `./schedules/daily_update.sh YYYYMMDD` 跑完 DB 有下個交易日後重跑 step2，不帶旗標。
2. **`--entry-date` 旗標提前跑**（要立刻產出 picks 時用）：
   ```bash
   venv/bin/python3 strategies/step2_finalize_strategy.py \
     --date 2026-05-16 --entry-date 2026-05-18
   ```
   step2 跳過 DB 驗證。技術/營收特徵以 `cutoff_date` 為 as-of，不受這個參數影響，所以無論何時跑內容都一樣。**但要自己負責確認 `entry_date` 真的是下個交易日**（別填到週六/週日/國定假日），因為它是進場價與 `fwd_return` 的錨點。

### Q6: 用了 `--entry-date` 之後，backtester 還能跑這個月嗎？
不能跑完整 rotation：backtester 的 `auto-detect` 規則要求 `daily_quotes` 必須有 entry_date 之後的列，2026-05-16 在 DB 補上 2026-05-18 之前會被自動跳過。如果強制 `--end-date 2026-05-16`，可以結算上個月的 cohort（PnL 已實現），但本月 cohort 會全部 `entries_failed_no_quote`、無法建倉。完整 rotation 仍需等今天 daily pipeline 完成。
