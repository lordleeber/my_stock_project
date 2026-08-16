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

## `quarterly_reports_xbrl` 的 12 個 `*_acc_ly` / `*_acc_yoy` 欄位全表 NULL

`processor/quarterly/convert_quarterly_reports_xbrl.py::build_experiment_row` 裡：

```python
prev_inc_a, _ = read_wide_code_map(prev_inc_a_path, symbol)
```

`read_wide_code_map()` 回傳的是 **dict**，這行卻拿它解包成兩個變數。損益表的寬列
一定不只 2 個科目，所以每次都拋 `ValueError: too many values to unpack`，被下一行的
`except ValueError: prev_inc_a = {}` 接掉 —— `prev_inc_a` **恆為空 dict**，去年同季
的基準永遠取不到。

實測（2026-08-16）：全部 26 季 × 兩種 `period_type`，以下 12 欄 100% NULL。

```
revenue_acc_ly / revenue_acc_yoy          op_income_acc_ly / op_income_acc_yoy
non_op_income_acc_ly / non_op_income_acc_yoy   pretax_income_acc_ly / pretax_income_acc_yoy
net_income_acc_ly / net_income_acc_yoy    eps_acc_ly / eps_acc_yoy
```

`BACKFILL_QUARTERS`（2020Q1~Q4）本來要從舊版 `quarterly_reports` 補，但那張表與它的
processed CSV 都已隨舊季報流程 deprecated 掉，所以連那四季也是空的。

**下游影響**：`strategies/step1_prepare_data.py:163` 把 `eps_acc_yoy` 與
`revenue_acc_yoy` 當特徵撈進 dataset —— 這兩個特徵目前恆為 NULL，等於沒作用。

沒有在修個體財報的 PR 裡一併處理，是因為修它會同時改動 12 個欄位的值與 2 個 ML
特徵，必須連帶重跑選股模型與回測驗證，跟「報表別判讀」是兩件事。修的時候注意：
轉換戶去年同季的報表別可能與本季不同（合併 ↔ 個體），`net_income_acc_ly` 取哪個
科目要依**該季自己的** `report_category` 決定，不能沿用本季的。

---

## `shareholding` 的 2026-07-09 是部分快照（1849 檔，其他日期 ~2952）

那一週的 TDCC 快照原本整份漏掉（7/10 週五休市 → 基準日順延到週四 → 7/12 沒抓到 →
7/19 抓到的已是 7/17），**已於 2026-08-10 回補入庫**。但回補只能逐檔爬歷史查詢頁
（TDCC OpenData 沒有歷史），股票清單用 `active_stocks.txt` 的 1849 檔，所以這一天
**永遠會比鄰近日期少約 1100 檔**：

```
2026-07-03  2952
2026-07-09  1849   ← 回補，部分快照
2026-07-17  2955
```

殘留影響只有一處：那 ~1100 檔沒補到的股票，它們 **2026-07-17 那列的 `*_wow` 仍是
14 天差分冒充週差分**（LAG 跳過 07-09 直接接到 07-03）。有補到的 1849 檔已是正確的
週差分。實測沒有任何 cohort 的 top-2 會讀到 07-17 那列，所以目前無下游影響。

受影響的 **cohort 2026-07-11（cutoff 07-10）已確認完全修復**：359 檔全部在 07-09
有 concentration，`step1` 取到的最新兩筆從錯誤的 `07-03 + 06-26` 回到正確的
`07-09 + 07-03`。

回補流程記在 `scraper/weekly/merge_shareholding.py` 的 docstring（fetch → merge →
convert → import → `--force-full`）。漏抓機制本身已於 2026-08-08 修掉，見
`scraper/weekly/check_outputs.py` 的新鮮度 + 連續性 gate。
