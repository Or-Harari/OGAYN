import * as React from 'react'
import { useEffect, useRef, useState } from 'react'
import { createChart, IChartApi, UTCTimestamp } from 'lightweight-charts'
import { API_BASE, api } from '@/lib/api'

type CandleRow = { date: string; open: number; high: number; low: number; close: number }

function toWsUrl(httpBase: string): string {
  try {
    const u = new URL(httpBase)
    u.protocol = u.protocol === 'https:' ? 'wss:' : 'ws:'
    return u.origin
  } catch {
    // Fallback to current location
    const proto = location.protocol === 'https:' ? 'wss://' : 'ws://'
    const host = location.host
    return proto + host
  }
}

export function LiveAnalyticsChart({ userId, botId }: { userId: number; botId: number }) {
  const wrapRef = useRef<HTMLDivElement | null>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRef = useRef<ReturnType<IChartApi['addCandlestickSeries']> | null>(null)
  const [pair, setPair] = useState<string | null>(null)
  const [timeframe, setTimeframe] = useState<string | null>(null)
  const [noData, setNoData] = useState<boolean>(false)

  useEffect(() => {
    if (!wrapRef.current) return
    const chart = createChart(wrapRef.current, { height: 420 })
    const series = chart.addCandlestickSeries()
    chartRef.current = chart
    seriesRef.current = series

    let ws: WebSocket | null = null
    let reconnectTimer: any

    const setSeriesData = (candles: CandleRow[]) => {
      if (!seriesRef.current) return
      const data = candles.map((c) => ({
        time: Math.floor(new Date(c.date).getTime() / 1000) as UTCTimestamp,
        open: c.open, high: c.high, low: c.low, close: c.close,
      }))
      seriesRef.current.setData(data)
    }
    const setTradeMarkers = (snap: any) => {
      try {
        if (!seriesRef.current) return
        const trades = Array.isArray(snap?.trades) ? snap.trades : []
        const selPair = pair || (Array.isArray(snap?.pairs) ? snap.pairs[0] : null)
        const markers: any[] = []
        trades.filter((t: any) => !selPair || t.pair === selPair).forEach((t: any) => {
          const openTs = t.open_date || t.open_timestamp || t.open_time
          const closeTs = t.close_date || t.close_timestamp || t.close_time
          if (openTs) {
            const time = Math.floor(new Date(openTs).getTime() / 1000) as UTCTimestamp
            markers.push({ time, position: 'belowBar', color: '#16a34a', shape: 'arrowUp', text: 'BUY' })
          }
          if (closeTs) {
            const time = Math.floor(new Date(closeTs).getTime() / 1000) as UTCTimestamp
            markers.push({ time, position: 'aboveBar', color: '#ef4444', shape: 'arrowDown', text: 'SELL' })
          }
        })
        if (markers.length) seriesRef.current.setMarkers(markers)
      } catch {}
    }

    // Initial snapshot
    api.get(`/users/${userId}/bots/${botId}/analytics/snapshot`, { params: { limit: 200 } })
      .then(res => {
        const snap = res.data
        const s = Array.isArray(snap?.series) ? snap.series : []
        const first = s[0]
        if (first) {
          setPair(first.pair)
          setTimeframe(first.timeframe)
          setSeriesData(first.candles || [])
          setTradeMarkers(snap)
          setNoData(false)
        } else {
          setNoData(true)
        }
      })
      .catch(() => { /* ignore */ })

    // Live updates (best-effort)
    const base = toWsUrl(API_BASE)
    const wsUrl = `${base}/users/${userId}/bots/${botId}/analytics/ws`
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
            const p = pair
            const tf = timeframe
            // Prefer matching pair/timeframe; else use first update
            let upd = msg.updates.find((u: any) => (!p || u.pair === p) && (!tf || u.timeframe === tf))
            if (!upd && msg.updates.length > 0) upd = msg.updates[0]
            if (upd && Array.isArray(upd.candles)) {
              setSeriesData(upd.candles)
              if (!pair) setPair(upd.pair)
              if (!timeframe) setTimeframe(upd.timeframe)
              setNoData(false)
            }
          }
        } catch { /* ignore */ }
      }
      ws.onclose = () => { reconnectTimer = setTimeout(connect, 1500) }
      ws.onerror = () => { try { ws?.close() } catch {} }
    }
    connect()

    return () => {
      try { ws?.close() } catch {}
      clearTimeout(reconnectTimer)
      chart.remove()
    }
  }, [userId, botId])

  return (
    <div>
      <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 6 }}>
        {pair && timeframe ? `${pair} · ${timeframe}` : 'Loading series…'}
      </div>
      <div ref={wrapRef} style={{ width: '100%', minHeight: 420 }} />
      {noData && (
        <div style={{ fontSize: 12, color: '#6b7280', marginTop: 6 }}>
          No candle data yet.
        </div>
      )}
    </div>
  )
}

export default LiveAnalyticsChart
