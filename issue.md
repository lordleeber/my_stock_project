# 開發與資料抓取問題紀錄 (Issue Log)

## 1. OTC 指數抓取失敗 (2026-02-07)

### 問題描述
無法透過自動化的 `scraper-daily` 流程抓取櫃買中心 (TPEx) 的指數行情數據，導致 `data_quality_checker.py` 持續回報 `market_indices/otc.csv` 檔案缺失。

### 嘗試過的方案與結果
1.  **直接模擬 URL 下載**：嘗試使用 `requests` 存取 `control_result.php?&o=csv`，回傳 404 或 Session 錯誤。
2.  **整合 API 邏輯**：將 `scripts/fetch_tpex_index_summary.py` 的邏輯整合入 `scraper/fetch_daily_otc.py`。
3.  **掛載目錄執行**：使用 `docker compose run -v` 掛載本地修正後的代碼執行。
    *   **結果**：Scraper 啟動後完全跳過「指數行情」類別，未嘗試執行抓取動作。

### 潛在原因分析
*   **容器代碼固化**：Docker 鏡像在構建時已將舊版 `fetch_daily_otc.py` 存入 `/app/scraper/`。在容器執行時，Python 可能優先載入內建路徑而非掛載目錄的路徑。
*   **類別遍歷缺失**：`scraper/main.py` 呼叫 `run_scraper` 時，可能因為 Python 模組快取機制，讀取到的是舊的 `CATEGORY_DIC` (不含「指數行情」)。

### 臨時解決方案
使用現有的 `scripts/fetch_tpex_index_summary.py` 手動下載資料至預期的 `data/raw/market_indices/` 目錄。

---

## 2. 大規模刪除後的索引遺失誤報 (2026-02-07)

### 問題描述
執行資料庫清理 (刪除特別股與 ETF) 後，自動化監控機制 `gemini-cli` 發布了 `abe7de5` commit，宣稱多個關鍵索引遺失並進行了重建。

### 分析
*   **技術事實**：`DELETE` 指令不會導致 `DROP INDEX`。
*   **誤判原因**：推測是大規模刪除導致資料庫鎖定或效能劇降，監控腳本在掃描 `pg_indexes` 時發生超時或讀取失敗，進而判定索引遺失。

### 狀態
✅ 索引已重建完成，目前效能正常。

---

## 3. SII 信用交易與借券格式解析失效 (2026-02-07)

### 問題描述
證交所 (SII) 的 `margin_trading` 與 `margin_sbl` CSV 採用跨列標題格式（第 1 行分類，第 2 行子標題），導致 `processor` 原本的單列讀取邏輯失效，欄位映射全為 NULL。

### 解決方案
✅ 已重構 `processor/utils.py` 加入 `read_raw_csv` 標題合併邏輯，目前已修復並通過 2026-01-30 以後的品質檢查。
