# Stock Analysis Project

台股月度 EPS 預測 → ML 選股 → 滾動回測 完整流程。

---

## 架構總覽

```
train_eps/        EPS 預測模型訓練與發布
strategies/       ML 選股特徵工程、排名模型訓練
models_selection/ 選股模型（walk-forward，每月一版）
backtester/       滾動投資組合回測
calculator/       DB 衍生表計算（shareholding_concentration 等）
backend/          FastAPI 完整資料端點（本機）
backend_lite/     FastAPI 精簡服務，僅 /selection/score（GCP 用）
frontend/         Next.js 選股查詢 UI（本機 & GCP）
scripts/          GCP 部署與資料上傳腳本
common/           共用 schema、工具模組
```

---

## 核心流程

### 1. EPS 預測（train_eps/）

```bash
# 資料準備 → 訓練 → 發布
venv/bin/python3 train_eps/prepare_data.py   --year 2025 --month 10
venv/bin/python3 train_eps/train.py          --year 2025 --month 10
venv/bin/python3 train_eps/gate_and_publish.py
```

### 2. 策略特徵工程（strategies/）

```bash
# 單月
venv/bin/python3 strategies/prepare_data.py      --year 2025 --month 10
venv/bin/python3 strategies/predict_published.py --year 2025 --month 10
venv/bin/python3 strategies/finalize_strategy.py --year 2025 --month 10

# 批次（歷史資料）
venv/bin/python3 strategies/batch_prepare_data.py
venv/bin/python3 strategies/batch_predict_published.py
venv/bin/python3 strategies/batch_finalize_strategy.py
```

### 3. 選股模型訓練（strategies/）

```bash
# 產生訓練資料
venv/bin/python3 strategies/analyze_feature_returns.py

# Walk-forward 批次訓練（回測用，每月一版）
venv/bin/python3 strategies/batch_train_selection_model.py

# 正式訓練（全資料，production 用）
venv/bin/python3 strategies/train_selection_model.py
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

### 5. 選股查詢 Web UI（frontend/ + backend_lite/）

本機開發：

```bash
# 啟動完整 backend（含 DB 連線）
docker-compose up backend

# 啟動前端
cd frontend && npm run dev
# 開啟 http://localhost:3000
```

---

## GCP 部署

Web UI 部署到 Google Cloud Run，PostgreSQL 維持在本機，模型與 CSV 上傳到 GCS。

```
瀏覽器
  │
  ▼
Cloud Run: frontend（Next.js）
  │  /api/score proxy（server-side）
  ▼
Cloud Run: backend-lite（FastAPI，僅選股 API）
  │
  ▼
Cloud Storage bucket
  ├── strategies/output/<year>/<MM>/dataset_strategy.csv
  └── models_selection/<year>/<MM>/selection_model.pkl
```

### 初次部署

```bash
# 1. 安裝 gcloud CLI 並登入
gcloud auth login
gcloud config set project YOUR_PROJECT_ID

# 2. 開啟必要 API
gcloud services enable run.googleapis.com storage.googleapis.com cloudbuild.googleapis.com

# 3. 一鍵部署（約 5-10 分鐘）
./scripts/deploy_gcp.sh YOUR_PROJECT_ID YOUR_BUCKET_NAME asia-east1
```

### 新增月份資料後更新

```bash
# 只需重新上傳檔案，不用 redeploy
./scripts/upload_to_gcs.sh YOUR_BUCKET_NAME
```

### 費用估算（個人低流量）

| 服務 | 估計費用 |
|------|--------|
| Cloud Run × 2 | 免費（每月 2M requests 免費額度） |
| Cloud Storage（~1-2 GB） | ~$0.04/月 |
| **合計** | **< $1/月** |

---

## 主要輸出

| 類型 | 路徑 |
|------|------|
| EPS 模型 | `models_eps/<year>/<month>/` |
| 月度特徵快照 | `strategies/output/<year>/<month>/dataset_strategy.csv` |
| 選股模型 | `models_selection/<year>/<month>/selection_model.pkl` |
| 回測交易紀錄 | `backtester/output/rolling/rolling_trades.csv` |
| 回測月摘要 | `backtester/output/rolling/rolling_monthly.csv` |
| 回測統計 | `backtester/output/rolling/rolling_summary.json` |

---

## Notes

- 產生的 csv / json / pkl artifacts 不 commit，除非明確要求
- 共用 DB schema 變更請同步更新 `common/schemas.py`
- `backend_lite/` 與 `backend/` 的 `/selection/score` 邏輯需保持同步
- 詳細說明見各子目錄的 `README.md` 與 `CLAUDE.md`
