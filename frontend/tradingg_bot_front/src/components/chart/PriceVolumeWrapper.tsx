import React, { useEffect, useMemo, useRef, useState } from 'react'
import {
  Chart,
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  TimeScale,
  TimeScaleFitContentTrigger,
  Pane,
  PriceScale,
  Markers,
} from 'lightweight-charts-react-components'
import { UTCTimestamp } from 'lightweight-charts'
import './PriceVolumeWrapper.css'

// ----------------- helpers -----------------

export type CandleRow = { date: number | string; open: number; high: number; low: number; close: number; volume?: number }

function normalizeCandles(input: any): CandleRow[] {
  try {
    const hasDataObj = input && typeof input === 'object' && 'data' in input
    const cols: string[] | undefined = hasDataObj
      ? (Array.isArray((input as any).columns) ? (input as any).columns
        : Array.isArray((input as any).all_columns) ? (input as any).all_columns
        : undefined)
      : undefined
    const colsL = cols?.map((c) => String(c).toLowerCase())

    let rows = hasDataObj ? (input as any).data : input
    if (!Array.isArray(rows) || rows.length === 0) return []

    const parseDateMs = (d: any): number => {
      if (typeof d === 'number') return d > 1e12 ? d : d * 1000
      const ms = Date.parse(String(d))
      return Number.isFinite(ms) ? ms : NaN
    }

    if (typeof rows[0] === 'object' && !Array.isArray(rows[0])) {
      return rows
        .map((r: any) => {
          const ms = parseDateMs(r?.date)
          const vol = r?.volume != null ? Number(r.volume) : undefined
          return { date: ms, open: Number(r.open), high: Number(r.high), low: Number(r.low), close: Number(r.close), volume: vol }
        })
        .filter((x) => Number.isFinite(x.date))
    }

    if (Array.isArray(rows[0])) {
      const idxOf = (names: string[] | string, fallback: number): number => {
        if (!colsL) return fallback
        const arr = Array.isArray(names) ? names : [names]
        for (const n of arr) {
          const i = colsL.findIndex((c) => c === n)
          if (i >= 0) return i
        }
        return fallback
      }
      const di = idxOf(['date', 'timestamp', 'time'], 0)
      const oi = idxOf('open', 1)
      const hi = idxOf('high', 2)
      const li = idxOf('low', 3)
      const ci = idxOf('close', 4)
      const vi = idxOf('volume', 5)

      return rows
        .map((r: any[]) => {
          const d0 = r?.[di]
          const ms = parseDateMs(d0)
          const vol = vi != null && vi >= 0 ? (r?.[vi] != null ? Number(r?.[vi]) : undefined) : undefined
          return { date: ms, open: Number(r?.[oi]), high: Number(r?.[hi]), low: Number(r?.[li]), close: Number(r?.[ci]), volume: vol }
        })
        .filter((x) => Number.isFinite(x.date))
    }

    return []
  } catch {
    return []
  }
}

// ----------------- props -----------------

export type PriceVolumeWrapperProps = {
  candles: any
  height?: number
  fitContent?: boolean
  volumeOnSeparatePane?: boolean
  indicators?: Record<string, any>
  signals?: Record<string, any>
  trades?: any[]
  visibleIndicators?: Record<string, boolean>
  showSignals?: boolean
  seriesKey?: string
  minWidth?: number
}

// ----------------- component -----------------

export default function PriceVolumeWrapper({
  candles,
  height = 420,
  fitContent = true,
  volumeOnSeparatePane = true,
  indicators = {},
  signals = {},
  trades = [],
  visibleIndicators = {},
  showSignals = true,
  seriesKey,
  minWidth = 320,
}: PriceVolumeWrapperProps) {
  const wrapRef = useRef<HTMLDivElement | null>(null)
  const [containerWidth, setContainerWidth] = useState<number>(0)

  useEffect(() => {
    if (!wrapRef.current) return
    const el = wrapRef.current
    const RO = (window as any).ResizeObserver
    const ro = RO
      ? new RO((entries: any[]) => {
          try {
            const rect = entries[0]?.contentRect || el.getBoundingClientRect()
            setContainerWidth(Math.max(minWidth, Math.floor(rect.width)))
          } catch {}
        })
      : null
    try {
      if (ro) ro.observe(el)
      const rect = el.getBoundingClientRect()
      setContainerWidth(Math.max(minWidth, Math.floor(rect.width)))
    } catch {}
    return () => {
      try {
        ro && ro.disconnect?.()
      } catch {}
    }
  }, [minWidth])

  const containerRef = useRef<HTMLDivElement | null>(null)

  // logo-hiding effect omitted for brevity (kept identical to your version)
  useEffect(() => {
    if (typeof document === 'undefined') return
    let observer: MutationObserver | null = null
    const styleTag = document.createElement('style')
    styleTag.setAttribute('data-analyticschart-tvlogo', '1')
    styleTag.textContent = `#tv-attr-logo { display: none !important; opacity: 0 !important; visibility: hidden !important; }`
    document.head.appendChild(styleTag)

    const tryHide = (): boolean => {
      try {
        const scope = containerRef.current ?? document.body
        const el = scope?.querySelector?.('#tv-attr-logo') || document.getElementById('tv-attr-logo')
        if (el) {
          const h = el as HTMLElement
          h.style.display = 'none'
          h.style.opacity = '0'
          h.style.visibility = 'hidden'
          try {
            h.parentElement?.removeChild(h)
          } catch {}
          return true
        }
      } catch {}
      return false
    }

    const t0 = setTimeout(tryHide, 0)
    const t1 = setTimeout(tryHide, 250)
    const t2 = setTimeout(tryHide, 750)

    const root = containerRef.current ?? document.body
    try {
      observer = new MutationObserver(() => {
        if (tryHide()) {
          observer?.disconnect()
          observer = null
        }
      })
      observer.observe(root, { childList: true, subtree: true })
    } catch {}

    return () => {
      clearTimeout(t0 as any)
      clearTimeout(t1 as any)
      clearTimeout(t2 as any)
      try {
        observer?.disconnect()
      } catch {}
      try {
        const s = document.head.querySelector('style[data-analyticschart-tvlogo="1"]')
        if (s) s.parentElement?.removeChild(s)
      } catch {}
    }
  }, [seriesKey, height])

  const rows = useMemo(() => normalizeCandles(candles), [candles])

  const ohlc = useMemo(
    () =>
      rows.map((c) => {
        const ms = typeof c.date === 'number' ? c.date : Date.parse(String(c.date))
        const t = Math.floor(ms / 1000) as UTCTimestamp
        return { time: t, open: c.open, high: c.high, low: c.low, close: c.close }
      }),
    [rows],
  )

  const volume = useMemo(
    () =>
      rows.map((c) => {
        const ms = typeof c.date === 'number' ? c.date : Date.parse(String(c.date))
        const t = Math.floor(ms / 1000) as UTCTimestamp
        const up = (c.close ?? 0) >= (c.open ?? 0)
        return { time: t, value: Math.max(0, c.volume ?? 0), color: up ? '#16a34a' : '#ef4444' }
      }),
    [rows],
  )

  const times = useMemo(() => ohlc.map((d) => d.time as UTCTimestamp), [ohlc])
  const indicatorNames = useMemo(() => Object.keys(indicators || {}), [indicators])
  const visibleNames = useMemo(
    () => indicatorNames.filter((n) => visibleIndicators?.[n] !== false),
    [indicatorNames, visibleIndicators],
  )

  // Removed price series ref; not needed with declarative components
  // Removed volume series ref; using declarative PriceScale instead of imperative API

  // markers memo left identical to your version
  const markers = useMemo(() => {
    const n = times.length
    if (n === 0) return [] as any[]
    const toBool = (v: any) => v === true || v === 1 || v === '1' || v === 'true'
    const align = (arr: any[]): any[] =>
      arr && arr.length === n
        ? arr
        : Array.isArray(arr)
        ? arr.length > n
          ? arr.slice(arr.length - n)
          : [...arr, ...Array(n - arr.length).fill(false)]
        : Array(n).fill(false)

    const buyArr = Array.isArray((signals as any)?.enter_long)
      ? (signals as any).enter_long
      : Array.isArray((signals as any)?.buy)
      ? (signals as any).buy
      : []
    const sellArr = Array.isArray((signals as any)?.exit_long)
      ? (signals as any).exit_long
      : Array.isArray((signals as any)?.sell)
      ? (signals as any).sell
      : []
    const buys = align(buyArr).map(toBool)
    const sells = align(sellArr).map(toBool)
    const sigMarkers: any[] = []
    if (showSignals) {
      for (let i = 0; i < n; i++) {
        const t = times[i]
        if (sells[i])
          sigMarkers.push({ time: t, position: 'aboveBar', color: '#ef4444', shape: 'circle', text: 'EXIT' })
        if (buys[i])
          sigMarkers.push({ time: t, position: 'belowBar', color: '#16a34a', shape: 'circle', text: 'ENTRY' })
      }
    }

    const entArr = align(Array.isArray((signals as any)?.enter_long) ? (signals as any).enter_long : [])
    const exArr = align(Array.isArray((signals as any)?.exit_long) ? (signals as any).exit_long : [])
    const entTagsRaw = Array.isArray((signals as any)?.enter_tag) ? (signals as any).enter_tag : []
    const exTagsRaw = Array.isArray((signals as any)?.exit_tag) ? (signals as any).exit_tag : []
    const entTags = align(entTagsRaw)
    const exTags = align(exTagsRaw)
    const entex: any[] = []

    const arr: number[] = times as any
    const tset = new Set<number>(arr)
    const toSec = (v: any): number | undefined => {
      if (v == null) return undefined
      if (typeof v === 'number') return v > 1e12 ? Math.floor(v / 1000) : Math.floor(v)
      const ms = Date.parse(v)
      return Number.isFinite(ms) ? Math.floor(ms / 1000) : undefined
    }
    const nearest = (x: number): UTCTimestamp => {
      let lo = 0,
        hi = arr.length - 1
      if (x <= arr[lo]) return arr[lo] as any
      if (x >= arr[hi]) return arr[hi] as any
      while (lo <= hi) {
        const m = (lo + hi) >> 1,
          v = arr[m]
        if (v === x) return v as any
        if (v < x) lo = m + 1
        else hi = m - 1
      }
      const a = arr[hi],
        b = arr[lo]
      return (x - a <= b - x ? a : b) as any
    }
    const snap = (sec?: number) => (sec == null ? undefined : tset.has(sec) ? (sec as any) : nearest(sec))
    const tradeMarkers: any[] = []
    for (const tr of trades || []) {
      const isShort = !!tr?.is_short
      const entrySec = toSec(tr?.open_timestamp) ?? toSec(tr?.open_date)
      const exitSec = toSec(tr?.close_timestamp) ?? toSec(tr?.close_date)
      const pr =
        typeof tr?.profit_ratio === 'number'
          ? tr.profit_ratio
          : tr?.profit_ratio != null
          ? parseFloat(tr.profit_ratio)
          : undefined
      const et = snap(entrySec)
      if (et)
        tradeMarkers.push({
          time: et,
          position: isShort ? 'aboveBar' : 'belowBar',
          shape: isShort ? 'arrowDown' : 'arrowUp',
          color: isShort ? '#ef4444' : '#16a34a',
          text: `ENTRY${tr?.pair ? ' ' + tr.pair : ''}${tr?.open_rate ? ` @ ${tr.open_rate}` : ''}`,
        })
      if (exitSec != null) {
        const xt = snap(exitSec)
        if (xt) {
          const color = typeof pr === 'number' ? (pr >= 0 ? '#16a34a' : '#ef4444') : '#9ca3af'
          const pct = typeof pr === 'number' ? ` ${(pr * 100).toFixed(2)}%` : ''
          tradeMarkers.push({
            time: xt,
            position: 'aboveBar',
            shape: 'circle',
            color,
            text: `EXIT${pct}${tr?.close_rate ? ` @ ${tr.close_rate}` : ''}`,
          })
        }
      }
    }
    return [...entex, ...sigMarkers, ...tradeMarkers].sort((a, b) => (a.time as number) - (b.time as number))
  }, [times, showSignals, JSON.stringify(signals), JSON.stringify(trades)])

  const chartKey = useMemo(() => `${seriesKey || 'pv'}-${containerWidth}`, [seriesKey, containerWidth])

  // Removed imperative priceScale applyOptions; handled below with <PriceScale> components

  return (
    <div
      ref={(el) => {
        wrapRef.current = el
        containerRef.current = el
      }}
      style={{ width: '100%', height: '100%' }}
    >
      <Chart
        key={chartKey}
        options={{
          height,
          layout: { textColor: 'white' as any, background: {  color: 'rgba(46, 46, 58, 1)' as any } },
            grid: {
    vertLines: {
      color: 'rgba(105, 109, 110, 0.5)',   // vertical grid line colour
    },
    horzLines: {
      color: 'rgba(105, 109, 110, 0.5)',   // horizontal grid line colour
    },
  },
          width: containerWidth,
          timeScale: { timeVisible: true },
        }}
      >
        <>
          {/* MAIN PRICE PANE */}
          <Pane stretchFactor={volumeOnSeparatePane ? 4 : 3}>
            <PriceScale
              id="right"
              options={{
                scaleMargins: volumeOnSeparatePane
                  ? { top: 0.1, bottom: 0.1 }
                  : { top: 0.05, bottom: 0.3 }, // leave bottom space when overlaying volume
              }}
            />

            <CandlestickSeries
              data={ohlc}
              options={{
                upColor: '#26a69a',
                downColor: '#ef5350',
                borderVisible: false,
                wickUpColor: '#26a69a',
                wickDownColor: '#ef5350',
                priceScaleId: 'right',
              }}
            >
              <Markers markers={markers as any} />
            </CandlestickSeries>

            {visibleNames.map((name, i) => {
              const vals: Array<number | null> = Array.isArray((indicators as any)[name])
                ? (indicators as any)[name]
                : []
              const data = times
                .map((t, idx) => {
                  const v = vals[idx]
                  if (v == null) return null
                  const num = Number(v)
                  if (!Number.isFinite(num)) return null
                  return { time: t, value: num }
                })
                .filter(Boolean) as any

              const colors = ['#2563eb', '#16a34a', '#f97316', '#9333ea', '#059669', '#dc2626', '#0ea5e9', '#a16207']

              return (
                <LineSeries
                  key={name}
                  data={data}
                  
                  options={{title: name, color: colors[i % colors.length], lineWidth: 2, priceScaleId: 'right' }}
                />
              )
            })}

            {/* VOLUME OVERLAY MODE */}

          </Pane>

          {/* SEPARATE VOLUME PANE */}
  
       
            <Pane  stretchFactor={1}>
              {/* Configure the volume pane overlay scale margins declaratively */}
              <HistogramSeries
                data={volume}
                options={{
                  title: 'Volume',
                  priceScaleId: 'right',
                  priceFormat: { type: 'volume' },
                }}
              />
            <PriceScale id="right" options={{ scaleMargins: { top: 0, bottom: 0 } }} />

            </Pane>
          
   
        </>

        <TimeScale>
          {fitContent && <TimeScaleFitContentTrigger deps={[ohlc.length]} />}
        </TimeScale>
      </Chart>
    </div>
  )
}
