import { NextRequest, NextResponse } from 'next/server'
import fs from 'fs'
import path from 'path'

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url)
  const year = Number(searchParams.get('year'))
  const month = Number(searchParams.get('month'))

  if (!year || !month) {
    return NextResponse.json({ detail: 'year and month are required' }, { status: 400 })
  }

  const csvPath = path.join(process.cwd(), '..', 'backtester', 'output', 'rolling', 'rolling_monthly.csv')

  try {
    const text = fs.readFileSync(csvPath, 'utf-8')
    const lines = text.split('\n').filter(l => l.trim())
    const headers = lines[0].replace(/^\uFEFF/, '').split(',')
    const yearIdx = headers.indexOf('year')
    const monthIdx = headers.indexOf('month')
    const regimeIdx = headers.indexOf('regime')

    const row = lines.slice(1).find(line => {
      const cols = line.split(',')
      return Number(cols[yearIdx]) === year && Number(cols[monthIdx]) === month
    })

    if (!row) return NextResponse.json({ regime: null })
    const regime = row.split(',')[regimeIdx]?.trim() ?? null
    return NextResponse.json({ regime })
  } catch {
    return NextResponse.json({ regime: null })
  }
}
