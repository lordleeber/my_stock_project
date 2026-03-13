import { NextRequest, NextResponse } from 'next/server'

// Server-side env var (set at runtime in Cloud Run, not baked into JS bundle)
const BACKEND_URL = process.env.BACKEND_URL ?? 'http://localhost:8000'

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url)
  const year = searchParams.get('year')
  const month = searchParams.get('month')

  if (!year || !month) {
    return NextResponse.json({ detail: 'year and month are required' }, { status: 400 })
  }

  try {
    const res = await fetch(
      `${BACKEND_URL}/selection/score?year=${year}&month=${month}`,
      { cache: 'no-store' },
    )
    const data = await res.json()
    return NextResponse.json(data, { status: res.status })
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e)
    return NextResponse.json({ detail: msg }, { status: 502 })
  }
}
