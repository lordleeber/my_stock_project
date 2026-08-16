# Scraper Module Guide

Scraper 已改成與 processor 一致的頻率分層：`daily/`, `weekly/`, `monthly/`, `quarterly/`。

## Entry Points

- `scraper/scraper_daily.py`
- `scraper/scraper_weekly.py`
- `scraper/scraper_monthly.py`
- 季報：**沒有頂層 orchestrator**。`scraper-quarterly` service 沒有預設 command，callers 須直接指定 `python3 scraper/quarterly/fetch_xbrl.py --year ... --quarter ...`（一般經由 `schedules/xbrl_scrape_daily.sh`）。

Backward compatibility:
- `scraper/check_daily_outputs.py`, `scraper/check_weekly_outputs.py`, `scraper/check_monthly_outputs.py` 目前是新分層 checker 的 wrapper。
- 舊的季報抓取（`scraper/scraper_quarterly.py`、`scraper/check_quarterly_outputs.py`、`scraper/quarterly/fetch_quarterly_reports.py`、`scraper/quarterly/check_outputs.py`）已 deprecated，移到 `scraper/_deprecated/` 與 `scraper/quarterly/_deprecated/`。

### 🔴 STRICT IMAGE REBUILD RULE (CORE MANDATE)

`scraper` services (daily, weekly, monthly, quarterly) do not mount source code into `/app`. After any code change in `scraper/` or `common/`, you **MUST** rebuild before running:

```bash
docker compose build scraper-daily scraper-weekly scraper-monthly scraper-quarterly
```

If you skip rebuild, container runtime may execute stale code even when host files look updated.

## Folder Layout

- `daily/`
  - `fetch_daily_sii.py`, `fetch_daily_otc.py`: daily 市場資料抓取
  - `fetch_ex_dividend.py`, `fetch_capital_reduction.py`, `fetch_par_value_change.py`: 每日公告資料抓取
  - `check_outputs.py`: daily 輸出完整性檢查

- `weekly/`
  - `fetch_tdcc.py`: TDCC OpenData 單次抓取（使用 `curl`），bulk 格式，**只有最新一週**
  - `fetch_tdcc_history.py`: 逐檔爬 TDCC 歷史查詢頁，**per-stock 格式**，回補用
  - `merge_shareholding.py`: 把 per-stock 檔合併回 bulk 格式，餵給 processor（見下方「回補一週」）。
    **輸出檔已存在時預設拒寫**，理由見該節「要點」的 `--force` 那條
  - `check_outputs.py`: weekly 輸出檢查

- `monthly/`
  - `fetch_monthly_revenue.py`: 月營收抓取
  - `fetch_stock_info.py`, `fetch_stock_tags.py`, `generate_active_stocks.py`: 月度/輔助基礎資料抓取與產生
  - `check_outputs.py`: monthly 輸出檢查

- `quarterly/`
  - `fetch_xbrl.py`: 季報 XBRL 抓取（MOPS XBRL HTML），輸出到 `data/raw/xbrl/YYYY/YYYYQX/`。
    **合併(C)抓不到會自動退到個體(A)**，見下方「合併財報 vs 個體財報」
  - `_deprecated/`: 已停用的舊版季報抓取（`fetch_quarterly_reports.py`、`check_outputs.py`）

## Required Env Vars

- Daily
  - `START_DATE`, `END_DATE`（可省略，省略時抓今天）
  - `MARKET_TYPE` (`SII`/`OTC`/`ALL`)

- Weekly
  - optional: `TDCC_DATE`（YYYYMMDD）。語意是「斷言這一份」：對 `fetch_tdcc.py`
    是**斷言 API 回來的就是這一天**（不符即拒寫並回非 0），對 `check_outputs.py`
    是**指定要驗證硬碟上的哪一份**（此時跳過新鮮度檢查）。
    **不能用來回補歷史** —— OpenData endpoint 沒有日期參數，永遠只回最新一週，
    強行指定舊日期只會把本週資料存成舊檔名。回補走 `weekly/fetch_tdcc_history.py`
    +`weekly/merge_shareholding.py`，見上方「回補漏掉的一週 shareholding」。
  - optional: `ALLOW_STALE_TDCC=1`（放行新鮮度告警，農曆年那週用）
  - 這兩個都已在 `docker-compose.yml` 的 `scraper-weekly` 宣告；compose 不會自動
    把 host 環境變數帶進 container，少了宣告就等於這兩個旋鈕不存在。
  - `scraper_weekly.py` 固定輸出到 `/app/data/raw/shareholding`

- Monthly
  - required: `REVENUE_YEAR`, `REVENUE_MONTH`

- Quarterly XBRL
  - 由 `fetch_xbrl.py` 直接吃 `--year` / `--quarter` 參數（不再使用 `REPORT_YEAR`/`REPORT_QUARTER` 環境變數）。一般透過 `schedules/xbrl_scrape_daily.sh` 觸發。
  - 另有兩個**只給回補用**的旗標，日常排程不要帶：
    - `--run-date YYYYMMDD`：覆寫檔名後綴。這個後綴就是 processor 讀出來的
      `publish_time`，回補歷史季別時必須指定該季**申報期限**，否則 2020Q1 會冒出
      一批 2026 年的 publish_time，與該季既有資料（整季統一）自相矛盾。
    - `--report-id {auto,C,A}`：`auto`（預設）= C 抓不到再退 A。回補早已過申報期限
      的歷史季別時 C 必定不存在，直接指定 `A` 可省一半請求。

## Raw Output Paths (current)

- Daily categories: `data/raw/<category>/YYYY/YYYYMMDD/{sii,otc}.csv`
- Monthly revenue:
  - snapshot: `data/raw/monthly_revenue/YYYY/YYYYMXX/tmp.csv` (overwritten each run)
  - cumulative: `data/raw/monthly_revenue/YYYY/YYYYMXX/market.csv` (append only newly published rows)
- Quarterly XBRL: `data/raw/xbrl/YYYY/YYYYQX/YYYYQX_<symbol>_YYYYMMDD.html`（flat：每檔直接寫入季別目錄，無 per-symbol 子目錄）

> Legacy raw paths（不再寫入，僅作 archive）: `data/raw/quarterly_reports/`、`data/raw/income_statement/`、`data/raw/balance_sheet/`、`data/raw/cash_flow/`
- Weekly shareholding: `data/raw/shareholding/YYYY/TDCC_OD_1-5_YYYYMMDD.csv`
- Weekly shareholding（回補中間態，per-stock）: `data/raw/shareholding_div/date=YYYYMMDD/<symbol>.csv`
  —— `fetch_tdcc_history.py` 的輸出，經 `merge_shareholding.py` 合併後才變成上面那個 bulk 檔。
  刻意分開兩棵樹：混在一起會讓人誤以為該週已經有可用資料。

## Commands

```bash
# daily
START_DATE=20260201 END_DATE=20260201 docker compose run --rm scraper-daily

# weekly
docker compose run --rm scraper-weekly

# monthly
REVENUE_YEAR=2026 REVENUE_MONTH=1 docker compose run --rm scraper-monthly

# quarterly XBRL（一般用 schedules/xbrl_scrape_daily.sh，下面是直接呼叫的 fallback）
docker compose run --rm scraper-quarterly \
    python3 scraper/quarterly/fetch_xbrl.py --year 2025 --quarter 4
```

### 回補漏掉的一週 shareholding

新鮮度／連續性 gate 響了、確認某週真的漏掉時走這條。**OpenData endpoint 沒有日期
參數**（`TDCC_DATE` 只是斷言，不能拿來指定歷史），唯一的歷史來源是逐檔查詢頁。

```bash
# 1. 逐檔爬（~1.4 秒/檔，1849 檔約 55 分鐘；可中斷續跑，已存在的檔會 skip）
docker compose run --rm \
  -v "$PWD/active_stocks.txt:/app/active_stocks.txt:ro" \
  --entrypoint "" scraper-weekly \
  python scraper/weekly/fetch_tdcc_history.py \
    --date YYYYMMDD --file /app/active_stocks.txt --no-verify

# 2. 合併成 bulk（純 stdlib，host 直接跑）
venv/bin/python3 scraper/weekly/merge_shareholding.py --date YYYYMMDD

# 3. 接回常規 pipeline
docker compose run --rm -e START_DATE=YYYYMMDD -e END_DATE=YYYYMMDD \
  processor python convert_weekly.py
docker compose run --rm -e START_DATE=YYYYMMDD -e END_DATE=YYYYMMDD \
  importer python import_weekly.py
docker compose run --rm calculator \
  python calculate_shareholding_concentration.py --force-full
```

要點：

- **第 3 步的 `--force-full` 不能省**：concentration 的 incremental 只 append
  `date > last_processed`，回填一個早於現有 max 的日期不會被吸收。代價是重建整張表
  （~777k 列），順帶會把任何落後的日期一併補算。
- **`--file` 用 `active_stocks.txt`**（repo 根目錄，月更）。它比 bulk 檔的 symbol 數少
  （1849 vs ~2952），所以回補出來**必然是部分快照** —— 這是 TDCC 的限制，不是 bug。
  該檔涵蓋了選股宇宙，實測對受影響 cohort 是 100% 覆蓋。
- **每檔必須湊滿 15 個分級**，`merge_shareholding.py` 會把不足的整檔剔除並列名。
  這是刻意的：`audit_shareholding.py` 要求每個 symbol 剛好 15 列，缺一列會讓**整個
  日期**硬失敗，寧可少幾檔也不要整批卡住。查詢頁的「合　計」與「差異數調整（說明4）」
  這類非分級列不在 mapping 裡，會自動被丟掉。
- **第 2 步不會覆寫既有的 bulk 檔**，已存在就印出該檔的 symbol 數並 exit 1。因為那份
  很可能是 OpenData 抓回來的完整快照（~2952 檔），而回補產出的只有 1849 檔；raw 檔
  又是 `audit_shareholding.py` 回讀 lineage 的唯一來源，蓋掉就無法從 `data/processed`
  還原。最容易誤觸的路徑是：為了驗單一檔而留下 `date=YYYYMMDD/<symbol>.csv`，之後
  一次 `--all` 把那週的好檔改寫成 15 列。
  - 真的要換（例如補抓了更多 symbol 後重新合併）才加 `--force`，而且**只能搭
    `--date`**；`--all --force` 會直接被拒絕，避免一個旗標放行整棵樹。
  - `--force` 時若新快照的 symbol 數比舊的少，會另外印一行警告。
- 完整案例見 `KNOWN_ISSUES.md` 的 2026-07-09 那筆。

## Notes

- 這次重構目標是「入口與分層一致化」。既有抓取邏輯（TWSE/TPEx/MOPS/TDCC）保持不變。
- daily/weekly/monthly 入口會在抓取完成後自動執行對應 `check_outputs`；quarterly XBRL 目前沒有 check_outputs（後續可補）。
- `daily/check_outputs.py` 偵測到 missing raw 檔時：寫入 `error_scraper.log` 並讓 `scraper_daily.py` 回傳 `exit 1`，讓 `daily_update.sh` 因 `set -e` 中斷，觸發後續 retry。**不再靜默通過**（避免 TWSE 暫時回 empty 時整條 pipeline 假成功而落漏資料）。
- `weekly/check_outputs.py` 除了驗檔案存在，還驗**快照新鮮度**：最新的
  `TDCC_OD_1-5_YYYYMMDD.csv` 日期必須落在 `[today-7, today-1]`，否則寫入
  `error_scraper.log` 並讓 `scraper_weekly.py` 回傳 `exit 1`（與 daily 同慣例），
  `weekly_update.sh` 因 `set -e` 中斷，`stock-weekly-update.service` 的
  `OnFailure=stock-notify@` 就會推播，由人工介入。
  - 為什麼需要：`fetch_tdcc.py` 打的 OpenData endpoint **沒有日期參數**，永遠只回
    最新一週。TDCC 延遲發布時它會抓回上週那份、覆寫同名舊檔，而舊版檢查只看
    「最新檔存在且 >10 bytes」、`weekly_update.sh` 又從最新檔名反推 `TARGET_DATE`，
    於是整條 pipeline 靜默通過，該週就這樣掉了（2026-07-09 就是這樣掉的，見
    `KNOWN_ISSUES.md`）。TDCC OpenData 不提供歷史，補救只能逐檔爬歷史查詢頁 ——
    流程見上方「回補漏掉的一週 shareholding」（1849 檔約 55 分鐘，且必然是部分快照）。
  - 檢查刻意**不預測 TDCC 會選週五還是週四**（實測 52 份裡 45 週五、7 週四，
    且 2026-02-13 週五休市仍照發週五），只斷言新鮮度 —— 所以不必維護交易日曆。
  - 指定 `TDCC_DATE` 時跳過新鮮度檢查（刻意鎖定硬碟上某一份來重驗）。
  - 農曆年整週休市時 TDCC 確實沒有快照，會告警一次（一整年只有這一次），
    確認後用 `ALLOW_STALE_TDCC=1 ./schedules/weekly_update.sh` 放行。
  - **另外驗連續性**：相鄰兩份快照間隔 > `MAX_SNAPSHOT_GAP_DAYS`（9 天）就告警。
    新鮮度只看最新那一份，有個結構性盲點——缺口一旦被下一週的快照蓋過去就永遠
    看不見了（7/12 告警若被錯過，7/19 抓到 7/17 就會安靜通過，7/09 永久消失）。
    - 門檻怎麼來的：實測 52 份的間隔分布是 6 天 ×6、7 天 ×37、8 天 ×8、13 天 ×1
      （13 天那次是農曆年）；漏一週會變成 14 天。取 9 天，正常週零誤報。
    - 只回看 `CONTINUITY_LOOKBACK_DAYS`（30 天 ≈ 4 個週日）。TDCC OpenData 沒有
      歷史，舊缺口補不回來，每週重報只會變成長期雜訊、最後被忽略——那就跟沒有
      gate 一樣了。用途是「讓被錯過的那次告警再有幾次機會」，不是清點歷史。
  - 未來日期的檔案（手動 cp 錯之類）會被排除在 latest 候選之外並**單獨指名回報**，
    不會像以前那樣被選成 latest 把 gate 永久卡死。
  - gate 只擋 shareholding 分支：`weekly_update.sh` 的除權息 process+import 與
    TDCC 無關，會照跑到底，最後才依兩條分支的成敗決定退出碼。
  - `ALLOW_STALE_TDCC=1` 放行時會在 log 寫下 `Waived by ALLOW_STALE_TDCC=1:` 區塊
    （不只印 stdout）——刻意跳過的那一週必須留得下紀錄，否則幾個月後回頭查籌碼
    缺口時，這份 log 反而看不出是誰知情跳過的。
  - log 裡 `Problems:` / `Waived by ...:` 的每一筆都以**真實路徑**開頭、後接原因，
    可以直接拿去 `ls`；不再混入 `<year>/TDCC_OD_1-5_YYYYMMDD.csv` 這種佔位字串。
  - `normalize_tdcc_date()` / `fail_if_problems()` 由 `scraper_weekly.py` 與
    `check_outputs.main()` 共用，兩個 entrypoint 對同一個輸入行為一致。
  - 檔名日期解析集中在 `_snapshot_date()`，`99999999` / `20261332` 這種過得了
    `\d{8}` 卻不是合法日期的值一律 fail-closed，不會讓 checker 直接 traceback。
  - 錯誤寫入走 `common/error_log.py`，**寫不進去也不會拋例外**（見該檔 docstring
    與 `RESTORE.md` §落差4）：壞掉的若是錯誤處理器，gate 反而會失效。
  - 測試：`venv/bin/python3 scraper/tests/test_check_weekly_freshness.py`（含 2026-07-12
    那次真實漏抓的重演，以及一整年逐週日重播）。
- `monthly/check_outputs.py` 目前會同時檢查 `tmp.csv` 與 `market.csv`。
- `fetch_monthly_revenue.py` 會把每次抓到的 `tmp.csv` 逐筆合併到 `market.csv`，並寫入 `publish_time`（預設當天 `YYYYMMDD`，可由 `PUBLISH_TIME` 覆寫）。
- `scraper/Dockerfile` 已內建 `curl`（供 `weekly/fetch_tdcc.py` 使用）。
- `fetch_xbrl.py` 用**正向驗證**決定能不能存檔（`validate_report()`）：回應必須 ≥ 100 KB 且帶 XBRL namespace（`xbrl.org/2003/instance` 或 `2013/inlineXBRL`），否則一律視為失敗。門檻是 2026-08-01 對 `data/raw/xbrl` 全量 41,158 檔校準出來的——最小的正常報表 351 KB、沒有任何一份 < 200 KB，而 MOPS 的安全性阻擋頁 800 bytes、「檔案不存在!」97 bytes。
  - 之所以不是逐條列舉錯誤頁字樣：舊版就是這樣做，兩個 marker 各差一個字（`the`/`this`、`執行`/`呈現`），2026Q2 因此存進 1,805 個阻擋頁。要改判斷條件請維持正向驗證的形式，不要退回窮舉錯誤訊息。
  - `classify_failure_reason()` 只負責把失敗原因寫清楚（`rate_limit` / `page_not_accessible` / `report_not_published`），漏判不會讓壞資料落地。
  - `load_existing_report_names()` 只把**通過驗證**的檔案列入 dedupe key，所以存壞的檔案下次執行會自動重抓，不會像舊版那樣錯一次就永遠 SKIP。
  - 重抓成功後 `purge_invalid_siblings()` 會刪掉同 symbol 的舊壞檔。**這步不能省**：processor 的 `collect_strict_html_per_symbol()` 對同季同 symbol 出現兩個 html 是直接 raise、整季轉檔中止，所以「重抓」和「清掉舊檔」必須成對出現。
  - 連續 `RATE_LIMIT_ABORT_STREAK`（5）次 `rate_limit` 就**中止本次執行**並回傳非 0。2026-07-02 的事故就是被擋之後仍一路跑完 1,800 個 symbol，把整季寫成阻擋頁。
  - 退出碼由 `decide_exit_code()` 決定：「有嘗試抓取、沒有任何一次成功、且失敗全都不是良性原因」才回非 0。舊版 `0 if ok > 0 else 1` 把 `skipped_exists` 算進 ok，只要目錄有舊檔就永遠 exit 0，MOPS 改版會靜悄悄停擺而不觸發 systemd 通知。
  - 申報期限前來抓會大量收到 `report_not_published`（例如 8/14 前抓 Q2），這是正常的、不會告警，等排程逐日補齊即可。
  - 測試：`scraper/tests/test_fetch_xbrl.py`。專案沒裝 pytest、CI 也只跑 ruff，所以本檔可直接執行：`venv/bin/python3 scraper/tests/test_fetch_xbrl.py`。

### 合併財報 vs 個體財報（`REPORT_ID`）

MOPS `t164sb01` 的 `REPORT_ID` 有兩種：`C` = 合併財報、`A` = 個體財報。**台灣規定無子公司者免編合併財務報表、以個體財報申報**，這類公司對 `C` 查詢一律回 97 bytes 的「檔案不存在!」。

舊版把 `REPORT_ID` 寫死成 `C`，於是它們從 2020 年起完全不在資料庫裡。2026-08-16 實測：`active_stocks.txt` 裡抓不到 C 的非金融公司有 167 檔，其中 **165 檔只有個體財報**，佔選股宇宙約 10%（台灣高鐵、寶雅、全國電、采鈺、精材、昇佳電子、宏捷科、福懋科、星宇航空、長榮航太…）。

現在的行為（`REPORT_ID_FALLBACK_CHAIN`）：

- 先打 `C`；**只有**失敗原因是 `report_not_published` 才退到 `A` 再打一次。
  `rate_limit` / `page_not_accessible` 是站方狀態，換 `REPORT_ID` 照樣被擋，還會拖慢 `RATE_LIMIT_ABORT_STREAK` 收手，所以不 fallback。
- 兩次請求之間一樣 sleep `FETCH_INTERVAL_SECONDS`（3 秒），否則這些 symbol 的瞬時請求速率會是別人的兩倍。
- 合併命中就**不會**多打 A —— 絕大多數 symbol 走這條，多打一次等於整季請求量翻倍。
- 存檔狀態：合併是 `ok`（刻意不改，既有 log 都吃這個字），個體是 `ok_a`，讓收尾統計看得出這一季有幾檔靠 fallback 收進來。計數與退出碼一律走 `is_saved_status()`。

**檔名格式不變**（`YYYYQX_<symbol>_YYYYMMDD.html`，不編報表別）。C 與 A 對同一 symbol 同一季互斥（2330／富邦金雙向實測），永遠只會存一份，所以 processor 的「同季同 symbol 出現兩個 html 就 raise」不受影響。報表別由內容自帶的 `tifrs-notes:ReportCategory`（`Consolidated report` / `Individual report`）判讀，不靠檔名。

> 金融業（金控/銀行/保險）**不在**這件事的範圍內：它們是有合併財報的（走 `C` 抓得到），不進資料庫的原因是 processor 只認一般業 TIFRS 科目表 —— 見 `KNOWN_ISSUES.md`。另外它們的半年報申報期限是 8/31，8 月中來抓 Q2 收到 `report_not_published` 是正常的。
