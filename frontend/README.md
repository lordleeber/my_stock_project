# Stock Analysis Frontend (前端視覺化儀表板)

使用 Next.js + TypeScript + Tailwind CSS 打造的現代化股票分析介面。

## 畫面功能

### Dashboard
- **市場排行榜**: 動態顯示所選日期的股票表現。
- **多指標選擇**: 支援 成交量、KD、RSI、MA 移動平均線。
- **靈活排序**: 支援遞增與遞減排序，快速篩選出強勢股或超賣股。

### 策略回測
- **參數設定**: 日期範圍、持有天數、停損停利設定。
- **回測結果**: 顯示總損益、報酬率、勝率、平均報酬。
- **交易明細**: 完整交易記錄與個別損益。

### 爆量掃描器 🆕
- **智能掃描**: 自動偵測異常放量股票。
- **參數調整**: 成交量門檻（張）、爆量倍數可自訂。
- **互動 K 線圖**: 專業金融圖表，含 MA5/10/20/60 均線與成交量（張）。
- **圖表預設展開**: 掃描結果全部自動顯示 K 線圖。

### 其他特色
- **響應式設計**: 支援手機與桌機瀏覽。
- **Tab 切換**: 快速在不同功能間切換。

## 技術棧
- **Next.js 16**: 採用 App Router + Turbopack。
- **React 19**: 最新版本，支援更好的效能。
- **TypeScript**: 嚴格型別定義，確保數據處理安全。
- **Tailwind CSS 4**: 快速建構專業美觀的介面。
- **lightweight-charts**: TradingView 專業金融圖表庫。
- **Docker**: 基於 Alpine Linux 的輕量化執行環境。

## 如何啟動
```bash
docker compose up backend frontend
```
訪問 `http://localhost:3000` 開始使用。
## 🆕 爆量掃描器使用

### 本地啟動

```bash
# 啟動 backend + frontend
docker compose up -d backend frontend

# 開啟瀏覽器
open http://localhost:3000
```

### 遠端啟動 (使用 Tailscale)

如需在另一台電腦執行 Frontend 連接此電腦的 Backend：

```bash
# 在另一台電腦上
cd frontend

# 快速啟動 (推薦)
./start.sh

# 或手動啟動
docker compose up -d
```

詳細設定請參考: [SETUP_REMOTE.md](SETUP_REMOTE.md)

### 使用步驟

1. 切換到「**爆量掃描器**」tab
2. 選擇掃描日期 (例如: 2025-10-03)
3. 調整參數 (選填):
   - 最小成交量: 預設 5,000 張
   - 爆量倍數: 預設 4 倍
4. 點擊「**開始掃描**」
5. 查看結果列表（圖表預設全部展開）

### K 線圖功能

- **台灣慣例**: 紅漲綠跌
- **技術指標**: MA5/10/20/60 均線（無水平虛線干擾）
- **成交量**: 底部柱狀圖，左側顯示單位（張）
- **掃描日標記**: 黃色半透明背景 highlight
- **可視範圍**: 掃描日 ±60 bars（資料讀取 ±90 天）
- **滾輪鎖定**: 已禁用滑鼠滾輪縮放，避免誤觸

## 開發模式

```bash
# 安裝依賴
npm install

# 啟動開發伺服器 (hot reload)
npm run dev

# 建置 production
npm run build

# 啟動 production 伺服器
npm start
```

## 環境變數

```bash
# Backend API 位址
NEXT_PUBLIC_API_URL=http://localhost:8000

# 使用 Tailscale IP (遠端連線)
NEXT_PUBLIC_API_URL=http://100.103.191.79:8000
```

## 元件結構

```
src/app/
├── page.tsx                    # 主頁面 (含 3 個 tabs)
├── components/
│   └── CandlestickChart.tsx    # K 線圖元件
├── layout.tsx                  # Root layout
└── globals.css                 # 全域樣式
```

## 故障排除

### Frontend 無法連接 Backend

```bash
# 檢查 Backend 是否運行
curl http://localhost:8000/health

# 檢查環境變數
docker compose config | grep NEXT_PUBLIC_API_URL

# 重建容器
docker compose down
docker compose up -d --build
```

### K 線圖無法顯示

1. 打開瀏覽器開發者工具 (F12)
2. 查看 Console 是否有錯誤
3. 查看 Network tab，確認 API 請求成功
4. 確認掃描日期有資料

### 效能問題

如果掃描結果過多 (50+ 支股票)：
- 所有圖表會同時載入，可能較慢
- 可調高「最小成交量」或「爆量倍數」減少結果數量
