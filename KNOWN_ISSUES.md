# KNOWN_ISSUES.md

已確認、但尚未修復的問題。修好之後把該段整個刪掉,不要留「已解決」的殭屍條目。

---

## 金融類股不在資料與選股範圍內（刻意的，不打算修）

`processor/quarterly/convert_xbrl.py` 只認一般行業的 TIFRS 科目表，金融業（金控/銀行/
保險）用的是另一套，整份報表解析不出任何一列 —— 五季實測 raw 有 11~13 檔金控、
`quarterly_reports_xbrl` 0 檔。step1 從該表起手，所以金融股也不會進選股宇宙。

記在這裡只為兩件事：別把它當 bug 去修；`schedules/xbrl_scrape_daily.sh` 的窗口也
**不需要**為金融業較晚的申報期限（Q1/Q3 5/30、半年報 8/31）往後延。

---

## `shareholding` 缺 2026-07-09 一週（尚未回補）

DB 的 `shareholding` / `shareholding_concentration` 從 2026-07-03 直接跳到 2026-07-17，
中間那週的 TDCC 快照（基準日 **2026-07-09**，因為 7/10 週五休市而順延到週四）從未入庫，
`data/raw/shareholding/2026/` 也沒有對應檔案。

**漏掉的機制已於 2026-08-08 修掉**（`scraper/weekly/check_outputs.py` 的新鮮度檢查，
見該檔的區塊註解與 `scraper/tests/test_check_weekly_freshness.py`），所以**不會再發生**；
這裡記的是**已經漏掉的那一週還沒補回來**。

實測影響（2026-08-08 查證）：

- **cohort 2026-07-11（cutoff 07-10）**：`step1_prepare_data.py` 取 `date <= cutoff` 的最新
  兩筆 concentration，實際拿到 `07-03 + 06-26`，正確應為 `07-09 + 07-03`。8 個籌碼特徵
  整週落後，`large_holder_two_week_up` 的兩週配對也錯。
- **cohort 2026-08-11（cutoff 08-10）**：取到 `08-07 + 07-31`，**不受影響**。
- `shareholding_concentration` 在 2026-07-17 那列的 `*_wow` 是拿 07-03 當 LAG 基準
  （14 天差分冒充週差分），但沒有任何 cohort 的 top-2 會讀到它。

**性質是「資料較舊」，不是 look-ahead** —— PIT 上偏保守，不是洩漏，所以嚴重度低於
`strategies/CLAUDE.md` 記的 entry_date 事件。

回補成本（評估過但尚未執行）：TDCC OpenData（`getOD.ashx?id=1-5`）只給最新一週，
歷史只能走 `scraper/weekly/fetch_tdcc_history.py` 的**逐檔查詢**（每檔 sleep 1–2 秒，
2952 檔約 75 分鐘），而且輸出是 per-stock 格式（`序,持股分級,人數,股數,占集保庫存數比例(%)`
外加一列「合計」），要另寫轉檔才能餵給 `convert_shareholding.py` 的 bulk 格式。
另外原始 bulk 檔有 4001 個 symbol、DB 匯入後 2952，逐檔重建**無論如何都是部分快照**。
回補後還要 `--force-full` 重算 `shareholding_concentration`（incremental 只 append
`date > last_processed`，回填早於 07-31 的日期不會被吸收），再重跑 cohort 2026-07-11 的
step1+step2 與 step3。2026-08-08 單檔實測（2330 / 20260709）確認資料**取得到**。
