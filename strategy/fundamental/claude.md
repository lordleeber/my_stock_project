# Fundamental Analysis Specialist - AI Assistant Insights

這份文件記錄了基本面選股模組（`strategy/fundamental/`）的開發心得、邏輯演進與實戰教訓，供後續 AI 助理參考。

## 核心選股哲學：Quality + Growth + Value + Timing
基本面分析不應只是看「低 PE」，而是一個 360 度的體質稽核過程。我們的策略演進從 1.0 (簡單篩選) 到 4.5 (旗艦級) 確立了以下核心維度：

1. **獲利品質 (Quality)**: 利用 `營業現金流 / 稅後淨利` 驗證獲利真偽。指標 > 0.8 是底線，> 1.0 是極品。
2. **成長動能 (Growth)**: 要求 `EPS YoY > 20%`。
3. **安全邊際 (Value)**: 嚴格控制 `PE < 15~18`。
4. **資本實力 (Solidity)**: 使用 `權益比率 (Equity to Assets Ratio) > 40%` 確保公司不靠過度舉債經營。
5. **動能接棒 (Timing)**: 這是本系統的靈魂。財報是落後指標，必須搭配「最新月營收」來確認動能是否延續。

## 絕對禁忌：Look-ahead Bias (看後照鏡開車)
在開發 `backtest_report.py` 與 `flagship_screener.py` 時，曾犯過使用「未來營收」來判斷「過去財報」的錯誤。
- **正確邏輯**：當 2025Q3 財報在 11/14 公告時，專家只能看到 8、9、10 月的營收。
- **實作建議**：任何回測或歷史模擬，必須嚴格鎖定 API 請求的 `end_date` 為決策日當天。

## 數據處理心得 (Technical Gotchas)
1. **API 穩定性**：大批量抓取 `/raw/daily-quotes` 曾導致 500 錯誤，原因是資料庫中存在 `NaN` 或 `Infinity`。後端修復後，前端仍需對數值進行 `pd.to_numeric(errors='coerce')` 處理。
2. **OTC 與 SII 的差異**：
   - 上櫃 (OTC) 財報格式與上市 (SII) 不同，容易發生欄位偏移。
   - 務必檢查 `name` 或 `eps` 是否為空，來判定資料解析是否成功。
3. **數值清理**：
   - 營建股營收會有誇張的 YoY (如 1,000,000%)，計算平均值時需注意離群值影響。
   - PE 比為 0 或負數代表虧損，應在首層過濾直接剔除。

## 關鍵指標公式表 (Domain Knowledge)
- **年化 ROE**: `(單季 EPS / 每股淨值) * 4 * 100` (用於預估)
- **獲利含金量**: `營業現金流 / 稅後淨利`
- **本業獲利比**: `營業利益 / 稅前淨利`
- **權益比率**: `100 - 負債比` (API 已提供 `equity_to_assets_ratio`)

## 估值系統 3.0 重大改進 (2026-02-10)

### 問題診斷
舊版估值系統 (2.x) 存在以下問題：
1. **EPS 年化假設錯誤**: `eps * 4` 假設每季獲利相同，營建業/零售業嚴重失真
2. **產業 PE 一刀切**: 同產業成長性差異大，卻用同一 PE 基準
3. **葛拉漢公式過時**: 22.5 常數是 1970 年代假設
4. **缺少成長因子**: 無法區分成長股與價值股

### 改進內容

#### 1. TTM EPS (近四季加總)
```python
# 舊版：單季年化
eps_annual = eps * 4  # 錯誤！

# 新版：取得近四季 EPS 加總
eps_ttm = eps_q1 + eps_q2 + eps_q3 + eps_q4  # 正確
```

#### 2. PEG Ratio (成長調整估值)
```python
# PEG = PE / EPS成長率
# PEG < 1 表示低估（成長率高於 PE）
peg_ratio = pe_ratio / eps_growth
fair_peg = eps_ttm * min(eps_growth, 30)  # 成長率上限 30%
```

#### 3. 分產業估值策略
| 產業類型 | PE 權重 | PB 權重 | PEG 權重 | 殖利率權重 | PE 上限 |
|----------|---------|---------|----------|------------|---------|
| 金融業   | 15%     | 45%     | 10%      | 30%        | 15      |
| 營建業   | 10%     | 60%     | 5%       | 25%        | 10      |
| 半導體   | 25%     | 15%     | 45%      | 15%        | 25      |
| 傳產穩定 | 30%     | 25%     | 20%      | 25%        | 18      |
| 景氣循環 | 20%     | 45%     | 10%      | 25%        | 12      |

#### 4. 歷史 PE 區間
```python
# 計算當前 PE 在歷史區間的位置
pe_percentile = (current_pe - pe_min) / (pe_max - pe_min) * 100

# 分類
# <= 20%: 極度低估
# 21-40%: 相對低估
# 41-60%: 合理區間
# 61-80%: 相對高估
# > 80%:  極度高估
```

#### 5. 品質標記 (quality_flag)
自動標記優質股票：
- `PEG<1`: 成長率高於 PE，低估
- `歷史低點`: PE 在近年最低區間
- `高ROE`: ROE > 15%

### 輸出欄位說明
| 欄位 | 說明 |
|------|------|
| `eps_ttm` | 近四季 EPS 加總 |
| `eps_growth` | EPS YoY 成長率 (%) |
| `peg_ratio` | PE / 成長率 |
| `pe_zone` | 歷史 PE 區間位置 |
| `fair_pe/pb/peg/dividend` | 各估值法計算的合理價 |
| `valuation_method` | 該產業使用的權重配置 |
| `quality_flag` | 優質股標記 |

## 共用模組改進 (2026-02-10)

### common/http_client.py
- 自動重試機制 (500/502/503/504 錯誤重試 3 次)
- 指數退避 (0.5s → 1s → 2s)
- 全域 Session 複用 TCP 連線

### common/constants.py
- 統一 API_BASE 配置
- HTTP_TIMEOUT / HTTP_RETRIES 參數化

## 未來優化方向
- ✅ ~~同業對比~~: 已實作分產業估值
- ✅ ~~除權息邏輯~~: 已加入殖利率估值
- **自由現金流 (FCF)**: 目前僅使用 OCF，未來應加入 CAPEX 計算 FCF
- **動態 PE 上限**: 根據利率環境調整合理 PE 範圍
- **機構持股變化**: 加入法人買賣超作為輔助指標

---
*Updated by Claude (Fundamental Analysis Specialist) - 2026-02-10*

---

## 變更紀錄（2026-02-15）

### 1) `flagship_screener.py` 新規則
- `--quarter` 為必填，不填會直接中止。
- `--market/--martket` 為必填，必須指定 `sii` 或 `otc`。
- 最早允許季度為 `2020Q4`（`2020Q1~2020Q3` 不允許）。
- 已改為分市場生效日：
  - `SII`: `Q1=05/15`, `Q2=08/14`, `Q3=11/14`, `Q4=次年03/31`
  - `OTC`: `Q1=6月第20個工作日`, `Q2=9月第20個工作日`, `Q3=12月第20個工作日`, `Q4=次年4月第20個工作日`
- `PE` 優先使用 `/raw/pe-ratio`，`/raw/daily-quotes` 僅作備援。
- `annual_eps` 優先使用 `TTM EPS`；不再使用估算係數因子做主估值。
- 無完整 `TTM EPS` 的股票會被排除（不再用 `eps*4` 補估）。

### 2) `valuation_screener.py` 新規則
- `--quarter` 為必填，不填會直接中止。
- `--market/--martket` 為必填，必須指定 `sii` 或 `otc`。
- 最早允許季度為 `2020Q4`。
- 估值結果依市場分流輸出：
  - `strategy/fundamental/undervalued_picks_<quarter>_<market>.csv`
- 無完整 `TTM EPS` 資料時會中止，不再 fallback `eps*4`。

### 3) 共用模組
- 新增 `strategy/fundamental/screener_base.py` 共用函式：
  - `calculate_ttm_eps()`
  - `build_ttm_eps_for_quarter()`
  - `fetch_pe_ratio_for_date()`
- `flagship_screener.py` 與 `valuation_screener.py` 已改為共用此模組。

## Update 2026-02-16 (Price Range Analyzer)
- `price_range_analyzer.py` now supports required CLI params:
  - `--report-path`
  - `--market/--martket {sii,otc}`
  - either `--start-date --end-date` or `--start-quarter --end-quarter`
- Output file naming updated to include report reference:
  - `price_analysis_ref_<report_stem>_<start>_<end>_<market>.csv`
- Removed `predict_price` usage from analyzer output.
- Output columns updated:
  - `price_date -> start_date`
  - `market_price -> start_price`
  - added `end_date`, `end_price`
- Fixed quote-fetch completeness issue:
  - old behavior: range-wide query could be truncated by API `limit`, causing invalid `period_high/period_low`
  - new behavior: fetch quotes by symbol in report first, then fallback to range mode only if needed
  - this ensures `period_high`/`period_low` are computed from complete symbol-level data
- `/raw/daily-quotes` request `limit` adjusted to `5000` for stability.

## Update 2026-02-16 (Flagship)
- Removed `predict_price` from `flagship_screener.py` output and value-score path.
