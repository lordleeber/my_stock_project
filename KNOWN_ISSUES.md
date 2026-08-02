# KNOWN_ISSUES.md

已確認、但尚未修復的問題。修好之後把該段整個刪掉,不要留「已解決」的殭屍條目。

---

## 金融業（金控/銀行/保險）季報 XBRL 完全進不了 DB

`processor/quarterly/convert_xbrl.py` 只認一般行業的 TIFRS 科目表（`1XXX` 資產總計、
`4000` 營業收入…）。金融業用的是另一套科目表，整份報表解析不出任何一列，所以就算
raw 抓到了，DB 也不會有資料。

實測 2025Q1~2026Q1 五個季別：`data/raw/xbrl/` 裡有 11~13 檔金控 raw，但
`quarterly_reports_xbrl` / `income_statement_xbrl` 是 **0/14，五季全部掛零**。

連帶影響 `schedules/xbrl_scrape_daily.sh` 的抓取窗口：金融業季報申報期限比一般公司晚
（Q1/Q3 5/30、半年報 8/31，實測 2026Q1 董事會通過日為兆豐金 5/19、國票金 5/20、
元大金 5/22、第一金 5/25、台新金 5/28），必然落在窗口外。但**在 converter 支援金融業
科目表之前，把窗口往後延換不到任何 DB 資料**，而窗口尾端釘在 playbook cutoff 又不該
亂動。要補的順序是：先讓 converter 支援，再用 `backfill_xbrl.sh` 一次性補 raw
（MOPS 的舊季報隨時抓得到，2026-08-01 補 2026Q1 就是現成例子）。
