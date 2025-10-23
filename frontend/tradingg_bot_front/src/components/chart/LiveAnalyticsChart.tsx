import * as React from 'react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { createChart, IChartApi, UTCTimestamp } from 'lightweight-charts'
import { API_BASE, api } from '@/lib/api'

type CandleRow = { date: string | number; open: number; high: number; low: number; close: number }

function toWsUrl(httpBase: string): string {
  try {
    const u = new URL(httpBase)
    u.protocol = u.protocol === 'https:' ? 'wss:' : 'ws:'
    return u.origin
  } catch {
    const proto = location.protocol === 'https:' ? 'wss://' : 'ws://'
    return proto + location.host
  }
}

function normalizeCandles(input: any): CandleRow[] {
  try {
    let rows = input
    if (rows && typeof rows === 'object' && 'data' in rows) rows = rows.data
    if (!Array.isArray(rows)) return []
    if (rows.length === 0) return []
    if (typeof rows[0] === 'object' && !Array.isArray(rows[0])) {
      return rows.map((r: any) => ({
        date: typeof r.date === 'number' ? (r.date > 1e12 ? r.date : r.date * 1000) : r.date,
        open: Number(r.open), high: Number(r.high), low: Number(r.low), close: Number(r.close),
      }))
    }
    if (Array.isArray(rows[0])) {
      return rows.map((r: any[]) => ({
        date: (r[0] > 1e12 ? r[0] : r[0] * 1000),
        open: Number(r[1]), high: Number(r[2]), low: Number(r[3]), close: Number(r[4]),
      }))
    }
    return []
  } catch {
    return []
  }
}

export function LiveAnalyticsChart({ userId, botId }: { userId: number; botId: number }) {
  const wrapRef = useRef<HTMLDivElement | null>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRef = useRef<ReturnType<IChartApi['addCandlestickSeries']> | null>(null)
  const [pairs, setPairs] = useState<string[]>([])
  const [timeframes, setTimeframes] = useState<string[]>([])
  const [selectedPair, setSelectedPair] = useState<string | null>(null)
  const [selectedTf, setSelectedTf] = useState<string | null>(null)
  const [noData, setNoData] = useState<boolean>(false)
  const [note, setNote] = useState<string>("")

  useEffect(() => {
    if (!wrapRef.current) return
    const chart = createChart(wrapRef.current, { height: 420 })
    chart.applyOptions({ watermark: { visible: false } as any })
    const series = chart.addCandlestickSeries()
    chartRef.current = chart
    seriesRef.current = series
    return () => { chart.remove() }
  }, [])

  const setSeriesData = (candlesIn: any) => {
    if (!seriesRef.current) return
    const candles = normalizeCandles(candlesIn)
    const data = candles.map((c) => ({
      time: Math.floor((typeof c.date === 'number' ? c.date : new Date(c.date).getTime()) / 1000) as UTCTimestamp,
      open: c.open, high: c.high, low: c.low, close: c.close,
    }))
    seriesRef.current.setData(data)
  }

  useEffect(() => {
    // Initial snapshot
    api.get(`/users/${userId}/bots/${botId}/analytics/snapshot`, { params: { limit: 200 } })
      .then(res => {
        const snap = res.data
        const s = Array.isArray(snap?.series) ? snap.series : []
        const ps: string[] = Array.isArray(snap?.pairs) ? snap.pairs : []
        const tfs: string[] = Array.isArray(snap?.timeframes) ? snap.timeframes : []
        setPairs(ps)
        setTimeframes(tfs)
        const effTf = typeof snap?.effective_timeframe === 'string' ? snap.effective_timeframe : null
        const first = s[0]
        const initPair = first?.pair || ps[0] || null
        const initTf = effTf || first?.timeframe || tfs[0] || null
        setSelectedPair(initPair)
        setSelectedTf(initTf)
        if (first?.candles && initPair === first.pair && initTf === (first.timeframe || initTf)) {
          setSeriesData(first.candles)
          setNoData(false)
          setNote(initTf ? `${initPair} · ${initTf}` : '')
        } else if (initPair && initTf) {
          api.get(`/users/${userId}/bots/${botId}/analytics/candles`, { params: { pair: initPair, timeframe: initTf, limit: 200 } })
            .then(r2 => { setSeriesData(r2.data); setNoData(false); setNote(`${initPair} · ${initTf}`) })
            .catch(() => { setNoData(true); setNote('No candle data') })
        } else {
          setNoData(true)
          setNote('No candle data')
        }
      })
      .catch(() => { /* ignore */ })
  }, [userId, botId])

  // React to selection changes
  useEffect(() => {
    let cancelled = false
    const load = async () => {
      if (!selectedPair || !selectedTf) return
      try {
        const r = await api.get(`/users/${userId}/bots/${botId}/analytics/candles`, { params: { pair: selectedPair, timeframe: selectedTf, limit: 200 } })
        if (cancelled) return
        setSeriesData(r.data)
        setNoData(false)
        setNote(`${selectedPair} · ${selectedTf}`)
      } catch {
        if (cancelled) return
        setNoData(true)
        setNote('No candle data')
      }
    }
    load()
    return () => { cancelled = true }
  }, [selectedPair, selectedTf, userId, botId])

  // Websocket for live updates; only apply if pair/tf matches selection
  useEffect(() => {
    const base = toWsUrl(API_BASE)
    const wsUrl = `${base}/users/${userId}/bots/${botId}/analytics/ws`
    let ws: WebSocket | null = null
    let reconnectTimer: any
    const connect = () => {
      try {
        ws = new WebSocket(wsUrl)
      } catch {
        reconnectTimer = setTimeout(connect, 1500)
        return
      }
      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data)
          if (msg?.type === 'series' && Array.isArray(msg.updates)) {
            const upd = msg.updates.find((u: any) => (!selectedPair || u.pair === selectedPair) && (!selectedTf || u.timeframe === selectedTf))
            if (upd && upd.candles) {
              setSeriesData(upd.candles)
              setNoData(false)
            }
          }
        } catch {}
      }
      ws.onclose = () => { reconnectTimer = setTimeout(connect, 2500) }
      ws.onerror = () => { try { ws?.close() } catch {} }
    }
    connect()
    return () => { try { ws?.close() } catch {}; clearTimeout(reconnectTimer) }
  }, [userId, botId, selectedPair, selectedTf])

  const PairTabs = useMemo(() => (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 8 }}>
      {pairs.map(p => (
        <button key={p}
          onClick={() => setSelectedPair(p)}
          style={{ padding: '4px 8px', borderRadius: 6, border: '1px solid #e5e7eb', background: selectedPair === p ? '#eef2ff' : '#fff', cursor: 'pointer' }}>
          {p}
        </button>
      ))}
    </div>
  ), [pairs, selectedPair])

  const TfTabs = useMemo(() => (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 8 }}>
      {timeframes.map(tf => (
        <button key={tf}
          onClick={() => setSelectedTf(tf)}
          style={{ padding: '4px 8px', borderRadius: 6, border: '1px solid #e5e7eb', background: selectedTf === tf ? '#eef2ff' : '#fff', cursor: 'pointer' }}>
          {tf}
        </button>
      ))}
    </div>
  ), [timeframes, selectedTf])

  return (
    <div>
      <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 6 }}>{note}</div>
      {pairs.length > 1 && PairTabs}
      {timeframes.length > 1 && TfTabs}
      <div ref={wrapRef} style={{ width: '100%', minHeight: 420 }} />
      {noData && (
        <div style={{ fontSize: 12, color: '#6b7280', marginTop: 6 }}>No candle data yet.</div>
      )}
    </div>
  )
}

export default LiveAnalyticsChart
