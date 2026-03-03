# Idea 01: 規則式多因子策略（v1）

## 策略定位
- 類型：規則式選股 + 參數優化。
- 核心目標：避免無差別進場，降低停損占比，維持可解釋性。

## 訊號與因子
- EPS 預估相對優勢：`ttm_eps_forward_live` 相對 `ttm_eps_official_live`。
- 籌碼動能：
  - `foreign_net_20d_lots = rolling_sum20(foreign_net) / 1000`
  - `inst_net_20d_lots = rolling_sum20(trust_net + dealer_net) / 1000`
- 技術位置：`close_vs_ma60 = close / ma60 - 1`
- 波動風險：`atr20_pct = atr20 / close * 100`
- 流動性：`volume_lots`

## 進場邏輯（硬過濾）
- `volume_lots >= 200`
- `ttm_eps_forward_live >= ttm_eps_official_live`
- `close > ma60`
- `foreign_net_20d_lots > 0`
- `inst_net_20d_lots > 0`
- `atr20_pct <= atr_threshold`
- 缺值處理：任一關鍵因子缺值則不進場。

## 候選排序（軟排序）
- `entry_score = pred_upside_z + chip_score + tech_score - vol_penalty`
- 只保留高分區間（Top N 或 Top %）。

## 風控與優化邏輯
- 禁用 `entry_rule=all`。
- 最佳化目標不是只看報酬，必須同時懲罰高風險配置。
- 約束重點：
  - 最小成交筆數（避免只有極少數交易）
  - `stop_loss_ratio` 上限
  - 高回撤懲罰
- 輸出保留 Top-K 以利人工比對。

## 預期行為
- 相較無差別進場，停損占比下降。
- 若成交筆數過低，代表過濾過嚴，需進入 v2 做可交易性補強。
