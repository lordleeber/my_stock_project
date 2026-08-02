# KNOWN_ISSUES.md

已確認、但尚未修復的問題。修好之後把該段整個刪掉,不要留「已解決」的殭屍條目。

---

## 金融類股不在資料與選股範圍內（刻意的，不打算修）

`processor/quarterly/convert_xbrl.py` 只認一般行業的 TIFRS 科目表，金融業（金控/銀行/
保險）用的是另一套，整份報表解析不出任何一列 —— 五季實測 raw 有 11~13 檔金控、
`quarterly_reports_xbrl` 0 檔。step1 從該表起手，所以金融股也不會進選股宇宙。

記在這裡只為兩件事：別把它當 bug 去修；`schedules/xbrl_scrape_daily.sh` 的窗口也
**不需要**為金融業較晚的申報期限（Q1/Q3 5/30、半年報 8/31）往後延。
