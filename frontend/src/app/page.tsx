'use client'

import { useState } from 'react'

interface ScoredStock {
  ml_rank: number
  ml_score: number
  symbol: string
  name: string | null
  pred_upside_pct: number | null
  pe_current: number | null
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
  const [modelUsed, setModelUsed] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function handleQuery() {
    setIsLoading(true)
    setError(null)
    setResults([])
    setModelUsed(null)
    try {
      const res = await fetch(`${API_BASE}/api/score?year=${year}&month=${month}`)
      if (!res.ok) {
        const body = await res.json().catch(() => ({ detail: res.statusText }))
        throw new Error(body.detail ?? res.statusText)
      }
      const data: ScoredStock[] = await res.json()
      setResults(data)
      if (data.length > 0) setModelUsed(data[0].model_used)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <main className="min-h-screen bg-gray-50 p-6">
      <div className="max-w-5xl mx-auto">
        <h1 className="text-2xl font-bold text-gray-800 mb-6">股票選股模型查詢</h1>

        {/* Controls */}
        <div className="flex items-center gap-4 mb-4">
          <div className="flex items-center gap-2">
            <label className="text-sm font-medium text-gray-700">年份</label>
            <select
              value={year}
              onChange={e => setYear(Number(e.target.value))}
              className="border border-gray-300 rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              {years.map(y => (
                <option key={y} value={y}>{y}</option>
              ))}
            </select>
          </div>

          <div className="flex items-center gap-2">
            <label className="text-sm font-medium text-gray-700">月份</label>
            <select
              value={month}
              onChange={e => setMonth(Number(e.target.value))}
              className="border border-gray-300 rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              {months.map(m => (
                <option key={m} value={m}>{String(m).padStart(2, '0')}</option>
              ))}
            </select>
          </div>

          <button
            onClick={handleQuery}
            disabled={isLoading}
            className="bg-blue-600 hover:bg-blue-700 disabled:bg-blue-300 text-white text-sm font-medium px-5 py-1.5 rounded transition-colors"
          >
            {isLoading ? '查詢中...' : '查詢'}
          </button>
        </div>

        {/* Status bar */}
        {modelUsed && (
          <p className="text-sm text-gray-500 mb-3">
            使用模型: <span className="font-medium text-gray-700">{modelUsed}</span>
            &nbsp;·&nbsp;共 {results.length} 檔
          </p>
        )}

        {/* Error */}
        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded p-3 mb-4">
            {error}
          </div>
        )}

        {/* Results table */}
        {results.length > 0 && (
          <div className="overflow-x-auto rounded-lg border border-gray-200 shadow-sm">
            <table className="w-full text-sm text-left">
              <thead className="bg-gray-100 text-gray-600 uppercase text-xs">
                <tr>
                  <th className="px-4 py-3">排名</th>
                  <th className="px-4 py-3">代號</th>
                  <th className="px-4 py-3">名稱</th>
                  <th className="px-4 py-3 text-right">ML分數</th>
                  <th className="px-4 py-3 text-right">預期漲幅%</th>
                  <th className="px-4 py-3 text-right">現值PE</th>
                  <th className="px-4 py-3 text-right">買進價</th>
                  <th className="px-4 py-3 text-right">賣出價</th>
                  <th className="px-4 py-3 text-right">淨利</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 bg-white">
                {results.map(row => (
                  <tr key={row.symbol} className="hover:bg-gray-50">
                    <td className="px-4 py-2 font-medium text-gray-700">{row.ml_rank}</td>
                    <td className="px-4 py-2 font-mono text-blue-700">{row.symbol}</td>
                    <td className="px-4 py-2 text-gray-800">{row.name ?? '-'}</td>
                    <td className="px-4 py-2 text-right tabular-nums">{fmt(row.ml_score)}</td>
                    <td className={`px-4 py-2 text-right tabular-nums ${row.pred_upside_pct !== null && row.pred_upside_pct > 0 ? 'text-green-600' : 'text-red-500'}`}>
                      {fmt(row.pred_upside_pct)}
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums">{fmt(row.pe_current)}</td>
                    <td className="px-4 py-2 text-right tabular-nums" title={row.entry_date ?? ''}>{fmt(row.entry_price)}</td>
                    <td className="px-4 py-2 text-right tabular-nums" title={row.exit_date ?? ''}>{fmt(row.exit_price)}</td>
                    <td className={`px-4 py-2 text-right tabular-nums ${row.net_pnl !== null && row.net_pnl > 0 ? 'text-green-600' : row.net_pnl !== null && row.net_pnl < 0 ? 'text-red-500' : ''}`}>
                      {row.net_pnl !== null ? row.net_pnl.toLocaleString('zh-TW', { maximumFractionDigits: 0 }) : '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {!isLoading && results.length === 0 && !error && modelUsed === null && (
          <p className="text-sm text-gray-400 mt-8 text-center">選擇年月後點擊查詢</p>
        )}
      </div>
    </main>
  )
}
