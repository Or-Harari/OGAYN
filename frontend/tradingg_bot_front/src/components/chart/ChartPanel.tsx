import * as React from 'react'
import { createChart, IChartApi, UTCTimestamp } from 'lightweight-charts'
import { useEffect, useRef } from 'react'
import { api } from '@/lib/api'

interface CandleRow {
  date: string
  open: number
  high: number
  low: number
  close: number
}

export function ChartPanel() {
  const wrapRef = useRef<HTMLDivElement | null>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRef = useRef<ReturnType<IChartApi['addCandlestickSeries']> | null>(null)

  useEffect(() => {
    if (!wrapRef.current) return
    const chart = createChart(wrapRef.current, { height: 420 })
    const series = chart.addCandlestickSeries()
    chartRef.current = chart
    seriesRef.current = series

    const userId = 1
    const botId = 1
    api.get(`/users/${userId}/bots/${botId}/analytics/snapshot`, { params: { limit: 200 } })
      .then(res => {
        const snap = res.data
        const anySeries = snap?.series || snap?.candles || []
        const first = Array.isArray(anySeries) ? anySeries[0] : null
        const candles: CandleRow[] = first?.candles || first || []
        const data = candles.map((c: CandleRow) => ({
          time: Math.floor(new Date(c.date).getTime() / 1000) as UTCTimestamp,
          open: c.open, high: c.high, low: c.low, close: c.close,
        }))
        series.setData(data)
      })
      .catch(() => {})

    const wsUrl = (location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + `/users/${userId}/bots/${botId}/analytics/ws`
    let ws: WebSocket | null = null
    let timer: any
    const connect = () => {
      ws = new WebSocket(wsUrl)
      ws.onopen = () => { /* keepalive */ }
      ws.onmessage = ev => {
        try {
          const msg = JSON.parse(ev.data)
          if (msg?.type === 'candle' && seriesRef.current) {
            const c = msg.data
            seriesRef.current.update({
              time: Math.floor(new Date(c.date).getTime() / 1000) as UTCTimestamp,
              open: c.open, high: c.high, low: c.low, close: c.close,
            })
          }
        } catch {}
      }
      ws.onclose = () => { timer = setTimeout(connect, 1500) }
      ws.onerror = () => { ws?.close() }
    }
    connect()
    return () => {
      ws?.close()
      clearTimeout(timer)
      chart.remove()
    }
  }, [])

  return <div className="chart" ref={wrapRef} />
}
