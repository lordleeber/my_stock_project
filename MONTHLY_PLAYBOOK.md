# Monthly Playbook

每月公告日後一天的標準作業流程：跑 EPS 模型、產出選股名單、重訓 selection model。

> 資料管線（scraper / processor / importer / calculator）由 launchd 自動排程，不在本 playbook 範圍。詳見 [`schedules/CLAUDE.md`](schedules/CLAUDE.md)。

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
YEAR=2026
MONTH=04           # 目標月（兩位數）
PREV_MONTH=03      # 上一個月（重訓 selection model 用）
PREV_YEAR=2026     # 若目標月是 01，PREV_YEAR=YYYY-1、PREV_MONTH=12

# ① EPS 模型（含 prepare → train → evaluate → predict）
venv/bin/python3 train_eps/run_pipeline.py --year $YEAR --month $MONTH

# ② strategies 本月候選（cutoff = M/10 或 M/15）
venv/bin/python3 strategies/step1_prepare_data.py      --year $YEAR --month $MONTH
venv/bin/python3 strategies/step2_finalize_strategy.py --year $YEAR --month $MONTH

# ③ 重建 fwd_return ground truth（現在 M-1 的 exit_date 才能定義出來）
venv/bin/python3 strategies/step3_analyze_feature_returns.py

# ④ 訓 cutoff = M-1 的 selection model（用最新 ground truth）
venv/bin/python3 strategies/step4_train_selection_model.py \
  --cutoff-year $PREV_YEAR --cutoff-month $PREV_MONTH

# ⑤ 對本月候選打分，產出最終選股名單
venv/bin/python3 strategies/step5_score_and_publish.py --year $YEAR --month $MONTH
```

完成後可選：
```bash
# ⑥ 延長 rolling 回測曲線到 M-1（觀察用）
venv/bin/python3 backtester/run_rolling.py \
  --start_year 2022 --start_month 7 \
  --end_year $PREV_YEAR --end_month $PREV_MONTH \
  --top-n 10 --position-amount 100000
```

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
step4       訓 cutoff=M-1 的新模型
                            │
                            ▼
step5(M)    walk-forward 自動挑到剛訓好的 M-1 模型
```

> 跳過 step3 / step4 也能跑出 step5 名單，但 step5 會退回去用更舊的 cutoff（例如 M-2、M-3），喪失最新一個月的訓練訊號。

---

## 主要產出

| 階段 | 產出 |
|---|---|
| ① train_eps | `models_eps/<YEAR>/<MONTH>/predictions_results.csv`（每檔 EPS delta 預測） |
| ② strategies step1+2 | `strategies/output/<YEAR>/<MONTH>/dataset_strategy.csv`、`trade_candidates.csv` |
| ③ step3 | `strategies/output/feature_return_analysis.csv`（含到 M-1 的 fwd_return） |
| ④ step4 | `models_selection/<PREV_YEAR>/<PREV_MONTH>/selection_model.pkl` + `feature_importance.csv` + `latest.json` |
| ⑤ step5 | `models_selection/<YEAR>/<MONTH>/candidates_scored.csv`（**最終選股名單**） |

選股建議：**`candidates_scored.csv` 依 `ml_rank` 取 top-10 等權買進，於 `entry_date` 開盤建倉**。

---

## 特殊月份對照

### 04 月（4/11）
- 新到資料：3 月營收 + **前年年報**
- 04 模型可用 Q4 為 anchor（含 Q4 完整 XBRL），比 03 模型多 2 個 XBRL 特徵
- 重訓 selection model cutoff = 03

### 05 月（5/16，因 5/15 是 Q1 季報日）
- 新到資料：4 月營收 + **Q1 季報**
- 05 模型 anchor 從 Q4 切換到 **Q1**，所有後續 06、07 月模型也以 Q1 為 anchor
- 重訓 selection model cutoff = 04

### 08 月（8/16）
- 新到資料：7 月營收 + **Q2 季報**
- 08 模型 anchor 切換到 **Q2**
- 重訓 selection model cutoff = 07

### 11 月（11/16）
- 新到資料：10 月營收 + **Q3 季報**
- 11 模型 anchor 切換到 **Q3**
- 重訓 selection model cutoff = 10

### 跨年的 01 月
- `PREV_YEAR = YYYY-1`、`PREV_MONTH = 12`
- 訓 cutoff = (YYYY-1)/12 的 selection model

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

monthly_update（營收）的 launchd 排在每月 1–15 日；如果手動補 monthly：
```bash
./schedules/monthly_update.sh
```

季報 XBRL：
- 公告期內由 launchd 每天跑 `xbrl_scrape_daily.sh`，持續累積 raw 但不入庫
- 公告期末（或要更新 DB 時）手動跑全鏈路：
```bash
./schedules/xbrl_run_pipeline.sh           # 視窗內依今天日期決定季別
./schedules/xbrl_run_pipeline.sh 2026Q1    # 直接指定季別（補跑或視窗外）
```

---

## Walk-forward 時序圖（以 04 月為例）

```
4/10 (Fri)    cutoff_date — 3 月營收 + 2025 年報全數公告完成
4/10 22:00    daily_update.sh 跑完，DB 有 4/10 收盤 + 籌碼
4/11 (Sat)    本 playbook 標準流程：
              ├── train_eps 04
              ├── strategies step1+2 04
              ├── strategies step3 (現在能算出 03 月的 fwd_return)
              ├── strategies step4 cutoff=03
              └── strategies step5 04 → 名單出爐
4/13 (Mon)    名單按開盤價建倉 (entry_date)
              ...持有約 25 個交易日 (依 5 月 entry 而定) ...
5/15 (Fri)    Q1 季報日 → cutoff_date
5/15 開盤      上一月 cohort 平倉 (5/15 開盤等於下一輪 entry 前一交易日)
5/16 (Sat)    跑 5 月份 playbook → 訓 cutoff=04 的 selection model、出 5 月名單
```

---

## 常見問題

### Q1: 為什麼 step5 顯示 `model used: 2026/02` 而不是最新？
A: 你跳過了 step3 + step4。`models_selection/2026/03/` 可能只有 `candidates_scored.csv` 沒有 `selection_model.pkl`。step5 的 walk-forward 規則是「最新有 pkl 的 cutoff < 目標月」。

### Q2: train_eps 同一個月份重跑兩次，model MAE 一樣是不是 bug？
A: 不是。`prepare_data` 用 PIT cutoff（M/10 或 M/15）截斷資料，固定 `seed=42`，相同輸入 → 相同模型。MAE 數字相同就代表 PIT 行為正確。

### Q3: 如果某天忘了跑，事後補做有差嗎？
A: 沒差。所有指令都是 idempotent + PIT，過幾天再補跑會得到完全相同的 EPS 模型；selection model 也會是相同模型，不受跑的時點影響。**唯一例外是 step5**：若中間有更新過 selection model，補跑出的名單可能與當天不同。

### Q4: 新增 PREV_YEAR / PREV_MONTH 的計算？
- 目標月為 01：PREV_YEAR = YYYY-1、PREV_MONTH = 12
- 其他月：PREV_YEAR = YYYY、PREV_MONTH = MONTH-1
