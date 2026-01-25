# Stock Analysis Frontend (前端視覺化儀表板)

使用 Next.js + TypeScript + Tailwind CSS 打造的現代化股票分析介面。

## 畫面功能
- **市場排行榜**: 動態顯示所選日期的股票表現。
- **多指標選擇**: 支援 成交量、KD、RSI、MA 移動平均線。
- **靈活排序**: 支援遞增與遞減排序，快速篩選出強勢股或超賣股。
- **響應式設計**: 支援手機與桌機瀏覽。

## 技術棧
- **Next.js 15**: 採用 App Router。
- **TypeScript**: 嚴格型別定義，確保數據處理安全。
- **Tailwind CSS**: 快速建構專業美觀的介面。
- **Docker**: 基於 Alpine Linux 的輕量化執行環境。

## 如何啟動
```bash
docker compose up backend frontend
```
訪問 `http://localhost:3000` 開始使用。