'use client'

import { useState, useEffect } from 'react'

interface ScoredStock {
  ml_rank: number
  ml_score: number
  symbol: string
  name: string | null
  pred_upside_pct: number | null
  pe_current: number | null
  ttm_eps: number | null
  volume_lots: number | null
  entry_date: string | null
  entry_price: number | null
  exit_date: string | null
  exit_price: number | null
  net_pnl: number | null
  model_used: string
}

const API_BASE = ''  // uses Next.js API route proxy at /api/score

const currentYear = new Date().getFullYear()
const years = Array.from({ length: currentYear - 2021 }, (_, i) => 2022 + i)
const months = Array.from({ length: 12 }, (_, i) => i + 1)

function fmt(v: number | null, decimals = 2): string {
  if (v === null || v === undefined) return '-'
  return v.toFixed(decimals)
}

export default function Home() {
  const [year, setYear] = useState(2024)
  const [month, setMonth] = useState(7)
  const [isLoading, setIsLoading] = useState(false)
  const [results, setResults] = useState<ScoredStock[]>([])
  const [prevResults, setPrevResults] = useState<ScoredStock[]>([])
  const [modelUsed, setModelUsed] = useState<string | null>(null)
  const [regime, setRegime] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [dark, setDark] = useState(false)

  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark)
  }, [dark])

  async function handleQuery() {
    setIsLoading(true)
    setError(null)
    setResults([])
    setPrevResults([])
    setModelUsed(null)
    setRegime(null)

    const prevMonth = month === 1 ? 12 : month - 1
    const prevYear = month === 1 ? year - 1 : year

    try {
      const [res, prevRes, regimeRes] = await Promise.all([
        fetch(`${API_BASE}/api/score?year=${year}&month=${month}`),
        fetch(`${API_BASE}/api/score?year=${prevYear}&month=${prevMonth}`).catch(() => null),
        fetch(`${API_BASE}/api/regime?year=${year}&month=${month}`).catch(() => null),
      ])

      if (!res.ok) {
        const body = await res.json().catch(() => ({ detail: res.statusText }))
        throw new Error(body.detail ?? res.statusText)
      }
      const data: ScoredStock[] = await res.json()
      setResults(data)
      if (data.length > 0) setModelUsed(data[0].model_used)

      if (prevRes && prevRes.ok) {
        const prevData: ScoredStock[] = await prevRes.json().catch(() => [])
        setPrevResults(prevData)
      }

      if (regimeRes && regimeRes.ok) {
        const regimeData = await regimeRes.json().catch(() => ({}))
        setRegime(regimeData.regime ?? null)
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setIsLoading(false)
    }
  }

  const prevMonth = month === 1 ? 12 : month - 1
  const prevYear = month === 1 ? year - 1 : year

  return (
    <main className="min-h-screen bg-gray-50 dark:bg-gray-900 p-6 transition-colors">
      <div className="max-w-5xl mx-auto">

        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-bold text-gray-800 dark:text-gray-100">股票選股模型查詢</h1>
          <button
            onClick={() => setDark(d => !d)}
            className="p-2 rounded-full text-gray-500 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors"
            title={dark ? '切換白天模式' : '切換黑夜模式'}
          >
            {dark ? '☀️' : '🌙'}
          </button>
        </div>

        {/* Controls */}
        <div className="flex items-center gap-4 mb-4">
          <div className="flex items-center gap-2">
            <label className="text-sm font-medium text-gray-700 dark:text-gray-300">年份</label>
            <select
              value={year}
              onChange={e => setYear(Number(e.target.value))}
              className="border border-gray-300 dark:border-gray-600 rounded px-3 py-1.5 text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              {years.map(y => (
                <option key={y} value={y}>{y}</option>
              ))}
            </select>
          </div>

          <div className="flex items-center gap-2">
            <label className="text-sm font-medium text-gray-700 dark:text-gray-300">月份</label>
            <select
              value={month}
              onChange={e => setMonth(Number(e.target.value))}
              className="border border-gray-300 dark:border-gray-600 rounded px-3 py-1.5 text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              {months.map(m => (
                <option key={m} value={m}>{String(m).padStart(2, '0')}</option>
              ))}
            </select>
            <button
              onClick={() => {
                if (month === 1) { setMonth(12); setYear(y => y - 1) }
                else setMonth(m => m - 1)
              }}
              className="px-2 py-1 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700"
            >‹</button>
            <button
              onClick={() => {
                if (month === 12) { setMonth(1); setYear(y => y + 1) }
                else setMonth(m => m + 1)
              }}
              className="px-2 py-1 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700"
            >›</button>
          </div>

          <button
            onClick={handleQuery}
            disabled={isLoading}
            className="bg-blue-600 hover:bg-blue-700 disabled:bg-blue-300 text-white text-sm font-medium px-5 py-1.5 rounded transition-colors"
          >
            {isLoading ? '查詢中...' : '查詢'}
          </button>
        </div>

        {/* Regime notice */}
        {regime && (() => {
          const regimeMap: Record<string, { label: string; desc: string; color: string }> = {
            Bull:     { label: '牛市',  desc: '趨勢向上，正常建倉',   color: 'text-red-500' },
            Sideways: { label: '盤整',  desc: '震盪整理，酌量建倉',   color: 'text-yellow-500' },
            Bear:     { label: '熊市',  desc: '趨勢向下，不建倉',     color: 'text-green-600' },
          }
          const info = regimeMap[regime]
          if (!info) return null
          return (
            <p className={`text-sm font-medium mb-3 ${info.color}`}>
              市場狀態：{info.label}　{info.desc}
            </p>
          )
        })()}

        {/* Error */}
        {error && (
          <div className="bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-700 text-red-700 dark:text-red-400 text-sm rounded p-3 mb-4">
            {error}
          </div>
        )}

        {/* Previous month completed trades */}
        {prevResults.length > 0 && (() => {
          const completedTrades = prevResults.filter(r => r.entry_price !== null && r.exit_price !== null)
          if (completedTrades.length === 0) return null
          const firstPrev = completedTrades.find(r => r.entry_date && r.exit_date)
          const prevEntryLabel = firstPrev?.entry_date
            ? `買進價(${firstPrev.entry_date.slice(5).replace('-', '/')}開盤)`
            : '買進價'
          const prevExitLabel = firstPrev?.exit_date
            ? `賣出價(${firstPrev.exit_date.slice(5).replace('-', '/')}開盤)`
            : '賣出價'
          const prevTotal = completedTrades.reduce((sum, r) => sum + (r.net_pnl ?? 0), 0)
          return (
            <div className="mb-6">
              <div className="flex items-center gap-3 mb-2">
                <h2 className="text-sm font-semibold text-gray-600 dark:text-gray-400">
                  {prevYear}/{String(prevMonth).padStart(2, '0')} 已完成交易
                </h2>
                {prevTotal !== 0 && (
                  <span className={`text-sm font-medium ${prevTotal > 0 ? 'text-red-500' : 'text-green-500'}`}>
                    淨利合計: {prevTotal.toLocaleString('zh-TW', { maximumFractionDigits: 0 })}
                  </span>
                )}
              </div>
              <div className="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-700 shadow-sm">
                <table className="w-full text-sm text-left">
                  <thead className="bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 uppercase text-xs">
                    <tr>
                      <th className="px-4 py-2">排名</th>
                      <th className="px-4 py-2">代號</th>
                      <th className="px-4 py-2">名稱</th>
                      <th className="px-4 py-2 text-right">ML分數</th>
                      <th className="px-4 py-2 text-right">預期漲幅%</th>
                      <th className="px-4 py-2 text-right">現值PE</th>
                      <th className="px-4 py-2 text-right">TTM EPS</th>
                      <th className="px-4 py-2 text-right">日成交張數</th>
                      <th className="px-4 py-2 text-right">{prevEntryLabel}</th>
                      <th className="px-4 py-2 text-right">{prevExitLabel}</th>
                      <th className="px-4 py-2 text-right">淨利</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100 dark:divide-gray-700 bg-white dark:bg-gray-900">
                    {completedTrades.map(row => (
                      <tr key={row.symbol} className="hover:bg-gray-50 dark:hover:bg-gray-800">
                        <td className="px-4 py-1.5 font-medium text-gray-700 dark:text-gray-300">{row.ml_rank}</td>
                        <td className="px-4 py-1.5 font-mono text-blue-700 dark:text-blue-400">{row.symbol}</td>
                        <td className="px-4 py-1.5 text-gray-800 dark:text-gray-200">{row.name ?? '-'}</td>
                        <td className="px-4 py-1.5 text-right tabular-nums text-gray-800 dark:text-gray-200">{fmt(row.ml_score)}</td>
                        <td className={`px-4 py-1.5 text-right tabular-nums ${row.pred_upside_pct !== null && row.pred_upside_pct > 0 ? 'text-red-500' : 'text-green-500'}`}>
                          {fmt(row.pred_upside_pct)}
                        </td>
                        <td className="px-4 py-1.5 text-right tabular-nums text-gray-800 dark:text-gray-200">{fmt(row.pe_current)}</td>
                        <td className="px-4 py-1.5 text-right tabular-nums text-gray-800 dark:text-gray-200">{fmt(row.ttm_eps)}</td>
                        <td className="px-4 py-1.5 text-right tabular-nums text-gray-800 dark:text-gray-200">{row.volume_lots !== null ? Math.round(row.volume_lots).toLocaleString('zh-TW') : '-'}</td>
                        <td className="px-4 py-1.5 text-right tabular-nums text-gray-800 dark:text-gray-200" title={row.entry_date ?? ''}>{fmt(row.entry_price)}</td>
                        <td className="px-4 py-1.5 text-right tabular-nums text-gray-800 dark:text-gray-200" title={row.exit_date ?? ''}>{fmt(row.exit_price)}</td>
                        <td className={`px-4 py-1.5 text-right tabular-nums ${row.net_pnl !== null && row.net_pnl > 0 ? 'text-red-500' : row.net_pnl !== null && row.net_pnl < 0 ? 'text-green-500' : 'text-gray-800 dark:text-gray-200'}`}>
                          {row.net_pnl !== null ? row.net_pnl.toLocaleString('zh-TW', { maximumFractionDigits: 0 }) : '-'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )
        })()}

        {/* Status bar */}
        {modelUsed && (
          <p className="text-sm text-gray-500 dark:text-gray-400 mb-3">
            使用模型: <span className="font-medium text-gray-700 dark:text-gray-200">{modelUsed}</span>
            &nbsp;·&nbsp;共 {results.length} 檔
          </p>
        )}

        {/* Current month results table */}
        {results.length > 0 && (() => {
          const firstTrade = results.find(r => r.entry_date)
          const entryLabel = firstTrade?.entry_date
            ? `買進價(${firstTrade.entry_date.slice(5).replace('-', '/')}開盤)`
            : '買進價'
          return (
          <div className="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-700 shadow-sm">
            <table className="w-full text-sm text-left">
              <thead className="bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 uppercase text-xs">
                <tr>
                  <th className="px-4 py-3">排名</th>
                  <th className="px-4 py-3">代號</th>
                  <th className="px-4 py-3">名稱</th>
                  <th className="px-4 py-3 text-right">ML分數</th>
                  <th className="px-4 py-3 text-right">預期漲幅%</th>
                  <th className="px-4 py-3 text-right">現值PE</th>
                  <th className="px-4 py-3 text-right">TTM EPS</th>
                  <th className="px-4 py-3 text-right">日成交張數</th>
                  <th className="px-4 py-3 text-right">{entryLabel}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-700 bg-white dark:bg-gray-900">
                {results.map(row => (
                  <tr key={row.symbol} className="hover:bg-gray-50 dark:hover:bg-gray-800">
                    <td className="px-4 py-2 font-medium text-gray-700 dark:text-gray-300">{row.ml_rank}</td>
                    <td className="px-4 py-2 font-mono text-blue-700 dark:text-blue-400">{row.symbol}</td>
                    <td className="px-4 py-2 text-gray-800 dark:text-gray-200">{row.name ?? '-'}</td>
                    <td className="px-4 py-2 text-right tabular-nums text-gray-800 dark:text-gray-200">{fmt(row.ml_score)}</td>
                    <td className={`px-4 py-2 text-right tabular-nums ${row.pred_upside_pct !== null && row.pred_upside_pct > 0 ? 'text-red-500' : 'text-green-500'}`}>
                      {fmt(row.pred_upside_pct)}
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums text-gray-800 dark:text-gray-200">{fmt(row.pe_current)}</td>
                    <td className="px-4 py-2 text-right tabular-nums text-gray-800 dark:text-gray-200">{fmt(row.ttm_eps)}</td>
                    <td className="px-4 py-2 text-right tabular-nums text-gray-800 dark:text-gray-200">{row.volume_lots !== null ? Math.round(row.volume_lots).toLocaleString('zh-TW') : '-'}</td>
                    <td className="px-4 py-2 text-right tabular-nums text-gray-800 dark:text-gray-200" title={row.entry_date ?? ''}>{fmt(row.entry_price)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          )
        })()}

        {!isLoading && results.length === 0 && !error && modelUsed === null && (
          <p className="text-sm text-gray-400 dark:text-gray-500 mt-8 text-center">選擇年月後點擊查詢</p>
        )}
      </div>
    </main>
  )
}
