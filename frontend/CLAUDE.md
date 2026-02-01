# Frontend Project Guide

## Overview

Taiwan stock analysis dashboard built with Next.js 16 + TypeScript + Tailwind CSS 4. Single-page app with 3 tabs: Dashboard, Backtest, Volume Scanner. Uses lightweight-charts v5 for financial charts.

## Architecture

All UI lives in a single page component. No routing, no global state management — just React `useState` in `page.tsx`.

```
src/app/
├── page.tsx                         # Main page (all 3 tabs, all state)
├── components/
│   ├── CandlestickChart.tsx         # K-line chart (OHLCV + MA lines)
│   └── InstitutionalChart.tsx       # Foreign/Trust investor buy/sell charts
├── layout.tsx                       # Root layout (fonts, metadata)
└── globals.css                      # Global styles
```

## Backend API

Backend URL is configured via `NEXT_PUBLIC_API_URL` env var (default: `http://localhost:8000`). Remote backend via Tailscale: `http://100.103.191.79:8000`.

### Endpoints used by frontend

| Endpoint | Purpose |
|----------|---------|
| `GET /scanner/volume-spike?date=&min_volume=&volume_ratio=` | Scan for volume spike stocks |
| `GET /scanner/candlestick/{symbol}?date=&days_before=90&days_after=90` | OHLCV + MA data for chart |
| `GET /scanner/institutional/{symbol}?date=&days_before=90&days_after=90` | Foreign/Trust net buy/sell + foreign held shares |
| `POST /backtest/run` | Run backtest strategy |
| `GET /health` | Health check |

### Important: volume unit is always 股 (shares) from API, frontend converts to 張 (lots, ÷1000)

## Key Implementation Details

### lightweight-charts v5 API
This project uses **v5** which has a different API from v4:
- `chart.addSeries(CandlestickSeries, options)` — NOT `chart.addCandlestickSeries()`
- `chart.addSeries(LineSeries, options)` — NOT `chart.addLineSeries()`
- `chart.addSeries(HistogramSeries, options)` — NOT `chart.addHistogramSeries()`
- Import series types: `import { createChart, CandlestickSeries, LineSeries, HistogramSeries } from "lightweight-charts"`

### CandlestickChart.tsx
- Taiwan convention: red = up, green = down
- MA lines: MA5 (orange), MA10 (blue), MA20 (red), MA60 (purple)
- All MA lines have `lastValueVisible: false, priceLineVisible: false` to hide horizontal dashed lines
- Volume histogram on left price scale, unit = 張
- Scan date highlighted with yellow semi-transparent HistogramSeries on a hidden "highlight" price scale
- Visible range: ±60 bars centered on scan date using `setVisibleLogicalRange`
- Mouse wheel scroll/zoom disabled
- Accepts `darkMode` prop for theme switching

### InstitutionalChart.tsx
- Two sub-charts: foreign investor net (upper) and investment trust net (lower)
- Each is an independent `createChart` instance
- Buy (positive) = red, Sell (negative) = green
- Foreign chart shows `foreign_held_shares` as orange line on right axis (when data available)
- Trust chart is prepared for `trust_held_shares` (pending backend support, see backend/buglist.md)
- Same highlight/range/scroll behavior as CandlestickChart
- Accepts `darkMode` prop

### Data merging (page.tsx)
Institutional data from API may have missing dates (days with no institutional trading). Frontend merges using candlestick dates as the base, filling missing dates with 0:
```typescript
const instMap = new Map(instData.map(d => [d.date, d]));
const merged = candleData.map(c => ({
  date: c.date,
  foreign_net: instMap.get(c.date)?.foreign_net ?? 0,
  trust_net: instMap.get(c.date)?.trust_net ?? 0,
  foreign_held_shares: instMap.get(c.date)?.foreign_held_shares ?? null,
}));
```

### Dark mode
- Controlled by `darkMode` state in page.tsx
- Toggle button in top-right corner
- Passed as prop to chart components which recreate charts with new colors
- Chart colors: bg `#1f2937`, text `#d1d5db`, grid `#374151`

### Scanner defaults
- Min volume: 5,000 張 (stored as 5,000,000 股 internally)
- Volume ratio: 4x
- All charts auto-expand on scan (not lazy-loaded)

## Running

```bash
# Via start script (recommended, handles rebuild + Tailscale check)
./start.sh

# Manual
docker compose up -d --build frontend

# Dev mode (no Docker)
npm install && npm run dev
```

## Scope

This is the frontend project only. Do NOT modify backend files (`backend/`, `scanner/`, `scraper/`, `importer/`, `processor/`). If you need backend changes, document requirements in `backend/buglist.md`.
