import * as React from 'react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { createChart, IChartApi, ISeriesApi, SeriesMarker, UTCTimestamp } from 'lightweight-charts'
import { api } from '@/lib/api'

// Convert inputs to finite numbers; returns NaN for null/undefined/NaN/Inf or non-parsable
function toFiniteNumber(v: any): number {
  if (typeof v === 'number') return Number.isFinite(v) ? v : NaN
  const n = parseFloat(v)
  return Number.isFinite(n) ? n : NaN
}

// Safely unwrap JSON that may arrive as an object, a JSON string, or double-encoded JSON string
function unwrapJsonLike(input: any, maxDepth = 3): any {
  let v: any = input
  for (let i = 0; i < maxDepth && typeof v === 'string'; i++) {
    try {
      let s = v
      // Strip BOM and whitespace which can break JSON.parse in some environments
      if (s && s.charCodeAt && s.charCodeAt(0) === 0xFEFF) s = s.slice(1)
      s = String(s).trim()
      v = JSON.parse(s)
    } catch {
      // If parsing fails, stop unwrapping and return best-effort original
      break
    }
  }
  return v
}

// If backend accidentally includes extra logs around JSON, try to extract the first JSON object/array
function extractLooseJson(input: string): any {
  try {
    // Quick path: trimmed string parses
    const t = String(input || '').trim()
    return JSON.parse(t)
  } catch {}
  try {
    const s = String(input || '')
    const objStart = s.indexOf('{')
    const objEnd = s.lastIndexOf('}')
    if (objStart !== -1 && objEnd !== -1 && objEnd > objStart) {
      const slice = s.slice(objStart, objEnd + 1)
      return JSON.parse(slice)
    }
  } catch {}
  try {
    const s = String(input || '')
    const arrStart = s.indexOf('[')
    const arrEnd = s.lastIndexOf(']')
    if (arrStart !== -1 && arrEnd !== -1 && arrEnd > arrStart) {
      const slice = s.slice(arrStart, arrEnd + 1)
      return JSON.parse(slice)
    }
  } catch {}
  return input
}

// Basic candle shape supported by backend snapshot
function normalizeCandles(input: any): Array<{ date: number | string; date_ts?: number; open: number; high: number; low: number; close: number }> {
  try {
    let rows = input
    if (rows && typeof rows === 'object' && 'data' in rows) rows = rows.data
    if (!Array.isArray(rows)) return []
    if (rows.length === 0) return []
    if (typeof rows[0] === 'object' && !Array.isArray(rows[0])) {
      return rows.map((r: any) => {
        // Prefer epoch seconds if provided from backend
        const tsSec = typeof r.date_ts === 'number' && Number.isFinite(r.date_ts) ? r.date_ts : undefined
        return {
          date: tsSec != null ? tsSec * 1000 : (typeof r.date === 'number' ? (r.date > 1e12 ? r.date : r.date * 1000) : r.date),
          date_ts: tsSec,
          open: toFiniteNumber(r.open),
          high: toFiniteNumber(r.high),
          low: toFiniteNumber(r.low),
          close: toFiniteNumber(r.close),
        }
      })
    }
    if (Array.isArray(rows[0])) {
      return rows.map((r: any[]) => ({
        date: (r[0] > 1e12 ? r[0] : r[0] * 1000),
        open: toFiniteNumber(r[1]),
        high: toFiniteNumber(r[2]),
        low: toFiniteNumber(r[3]),
        close: toFiniteNumber(r[4]),
      }))
    }
    return []
  } catch {
    return []
  }
}

const palette = ['#2563eb', '#16a34a', '#f97316', '#9333ea', '#059669', '#dc2626', '#0ea5e9', '#a16207']
const isOscillator = (name: string) => /rsi|stoch|cci|mfi|macd|ao|awesome|osc/i.test(name)

export type BackstageSelection = { pair: string | null; timeframe: string | null; timerange: string }

export function BackstagePanel({
  userId,
  botId,
  initialPairs,
  initialTimeframes,
  defaultSelection,
  onSelectionChange,
  autoLoad = false,
}: {
  userId: number
  botId: number
  initialPairs: string[]
  initialTimeframes: string[]
  defaultSelection?: Partial<BackstageSelection>
  onSelectionChange?: (sel: BackstageSelection) => void
  autoLoad?: boolean
}) {
  const wrapRef = useRef<HTMLDivElement | null>(null)
  const oscWrapRef = useRef<HTMLDivElement | null>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const indicatorSeriesRef = useRef<Map<string, ISeriesApi<'Line'>>>(new Map())
  const oscChartRef = useRef<IChartApi | null>(null)
  const oscSeriesRef = useRef<Map<string, ISeriesApi<'Line'>>>(new Map())
  const lastTimesRef = useRef<UTCTimestamp[]>([])
  const lastIndicatorsRef = useRef<Record<string, any[]>>({})
  const lastCandlesRef = useRef<any[] | null>(null)

  const [pairs, setPairs] = useState<string[]>([])
  const [timeframes, setTimeframes] = useState<string[]>([])
  const [selectedPair, setSelectedPair] = useState<string | null>(defaultSelection?.pair ?? null)
  const [selectedTf, setSelectedTf] = useState<string | null>(defaultSelection?.timeframe ?? null)
  const [timerange, setTimerange] = useState<string>(defaultSelection?.timerange ?? '-30d')
  const [loading, setLoading] = useState<boolean>(false)
  const [error, setError] = useState<string | null>(null)
  const [note, setNote] = useState<string>('')
  const [availableIndicators, setAvailableIndicators] = useState<string[]>([])
  const [visibleIndicators, setVisibleIndicators] = useState<Record<string, boolean>>({})
  const [showOscPane, setShowOscPane] = useState<boolean>(false)
  const initialLoadDoneRef = useRef<boolean>(false)
  const [chartReady, setChartReady] = useState<boolean>(false)

  useEffect(() => {

    if (!wrapRef.current) return
    const chart = createChart(wrapRef.current, { height: 420 })
  chart.applyOptions({ })
  const series = chart.addSeries({ type: 'Candlestick', upColor: '#26a69a', downColor: '#ef5350', borderVisible: false,
  wickUpColor: '#26a69a', wickDownColor: '#ef5350'} as any)
    chartRef.current = chart
  seriesRef.current = series as ISeriesApi<'Candlestick'>
    const a = document.querySelectorAll('#tv-attr-logo')
    if(a){
      a.forEach(el => el.remove());
    }

  setChartReady(true)
    let osc: IChartApi | null = null
    if (oscWrapRef.current) {
  osc = createChart(oscWrapRef.current, { height: 160 })
  osc.applyOptions({ })
      oscChartRef.current = osc
      const as = document.querySelectorAll('#tv-attr-logo')
      if(as){
        as.forEach(el => el.remove());
      }
    }
    // Resize observer to keep chart width in sync with container
    let ro: ResizeObserver | null = null
    try {
      if ('ResizeObserver' in window) {
        ro = new ResizeObserver(() => {
          try {
            const el = wrapRef.current
            if (el && chartRef.current) {
              const rect = el.getBoundingClientRect()
              chartRef.current.resize(Math.max(100, Math.floor(rect.width)), 420)
            }
          } catch {}
        })
        if (wrapRef.current) ro.observe(wrapRef.current)
      }
    } catch {}
    return () => { if (ro && wrapRef.current) try { ro.unobserve(wrapRef.current) } catch {}; chart.remove(); if (osc) osc.remove() }
  }, [showOscPane])

  useEffect(() => {
    // initialize available selections
    const ps = Array.isArray(initialPairs) && initialPairs.length ? initialPairs : ['BTC/USDT', 'ETH/USDT']
    const tfs = Array.isArray(initialTimeframes) && initialTimeframes.length ? initialTimeframes : ['5m', '15m', '1h']
    setPairs(ps)
    setTimeframes(tfs)
    setSelectedPair((prev) => prev || (defaultSelection?.pair ?? (ps.includes('BTC/USDT') ? 'BTC/USDT' : ps[0] || null)))
    setSelectedTf((prev) => prev || (defaultSelection?.timeframe ?? (tfs.includes('5m') ? '5m' : tfs[0] || null)))
    setTimerange((prev) => prev || defaultSelection?.timerange || '-30d')
  }, [initialPairs?.join(','), initialTimeframes?.join(',')])

  // Auto-load once when selection ready
  useEffect(() => {
    if (initialLoadDoneRef.current) return
    if (!autoLoad) return
    if (selectedPair && selectedTf && timerange && chartReady) {
      initialLoadDoneRef.current = true
      loadParity()
    }
  }, [selectedPair, selectedTf, timerange, chartReady, autoLoad])

  // notify parent of selection changes
  useEffect(() => {
    onSelectionChange?.({ pair: selectedPair, timeframe: selectedTf, timerange })
  }, [selectedPair, selectedTf, timerange])

  const ensureLineSeries = (name: string, idx: number) => {
    const useOsc = showOscPane && isOscillator(name)
    const targetChart = useOsc ? oscChartRef.current : chartRef.current
    if (!targetChart) return null
    const map = useOsc ? oscSeriesRef.current : indicatorSeriesRef.current
    let s = map.get(name)
    if (!s) {
  s = targetChart.addSeries({ type: 'Line', color: palette[idx % palette.length], lineWidth: 2 } as any)
      map.set(name, s)
    }
    return s
  }

  const setSeriesData = (candlesIn: any) => {
    // If series isn't ready yet, buffer for later
    if (!seriesRef.current) {
      console.log('Buffering candles for later:', candlesIn)
      try { lastCandlesRef.current = Array.isArray(candlesIn) ? candlesIn : (candlesIn?.data || candlesIn) } catch {}
      return
    }
    
    const candles = normalizeCandles(candlesIn)
    // Build, sort ascending by time, and de-duplicate timestamps
    let data = candles.map((c) => {
      let tsMs: number
      if (typeof c.date === 'number') {
        // Support seconds or milliseconds
        tsMs = c.date > 1e12 ? c.date : c.date * 1000
      } else {
        // Robustly parse common timestamp strings like "YYYY-MM-DD HH:mm:ss+00:00"
        // Normalize space to 'T' and convert "+00:00" to "Z" for strict ISO parsing
        const raw = String(c.date)
        let iso = raw.includes('T') ? raw : raw.replace(' ', 'T')
        iso = iso.replace(/\+00:00$/, 'Z')
        const parsed = Date.parse(iso)
        tsMs = Number.isFinite(parsed) ? parsed : NaN
      }
      const time = Number.isFinite(tsMs) ? (Math.floor(tsMs / 1000) as UTCTimestamp) : (NaN as unknown as UTCTimestamp)
      const o = c.open, h = c.high, l = c.low, cl = c.close
      return { time, open: o, high: h, low: l, close: cl }
    })
    // Filter out rows with invalid time or non-finite OHLC values
    data = data
      .filter(d => Number.isFinite(d.time as number) && Number.isFinite(d.open) && Number.isFinite(d.high) && Number.isFinite(d.low) && Number.isFinite(d.close))
      .sort((a, b) => (a.time as number) - (b.time as number))
    const dedup: typeof data = []
    let prev: number | null = null
    for (const d of data) {
      const t = d.time as number
      if (prev === t) continue
      dedup.push(d)
      prev = t
    }
    console.log('Setting series data, candles:', dedup)
    seriesRef.current.setData(dedup)
    lastTimesRef.current = dedup.map(d => d.time)
    lastCandlesRef.current = candlesIn
    try { chartRef.current?.timeScale().fitContent() } catch {}
  }

  // If candles were buffered before the chart was ready, apply them now
  useEffect(() => {
    if (!chartReady || !seriesRef.current) return
    if (lastCandlesRef.current) {
      const buf = lastCandlesRef.current
      lastCandlesRef.current = null
      setSeriesData(buf)
    }
  }, [chartReady])

  const setIndicators = (indicators: Record<string, any>) => {
    if (!indicators || !chartRef.current) return
    const times = lastTimesRef.current
    const names = Object.keys(indicators || {})
    setAvailableIndicators(names)
    setVisibleIndicators(prev => {
      const next = { ...prev }
      let changed = false
      names.forEach(n => { if (!(n in next)) { next[n] = true; changed = true } })
      for (const k of Object.keys(next)) {
        if (!names.includes(k)) { delete next[k]; changed = true }
      }
      return changed ? next : prev
    })
    lastIndicatorsRef.current = indicators || {}
    names.forEach((name, i) => {
      if (visibleIndicators && visibleIndicators[name] === false) return
      const values: Array<number | null> = Array.isArray(indicators[name]) ? indicators[name] : []
      const s = ensureLineSeries(name, i)
      if (!s) return
      const data = times.map((t, idx) => {
        const v = values[idx]
        if (v == null) return null
        const num = Number(v)
        if (!Number.isFinite(num)) return null
        return { time: t as UTCTimestamp, value: num }
      }).filter(Boolean) as any
      s.setData(data)
    })
    const current = new Set(names)
    for (const [name, s] of indicatorSeriesRef.current.entries()) {
      if (!current.has(name) || visibleIndicators[name] === false) {
        try { chartRef.current?.removeSeries(s) } catch {}
        indicatorSeriesRef.current.delete(name)
      }
    }
    if (oscChartRef.current) {
      for (const [name, s] of oscSeriesRef.current.entries()) {
        if (!current.has(name) || visibleIndicators[name] === false) {
          try { oscChartRef.current?.removeSeries(s) } catch {}
          oscSeriesRef.current.delete(name)
        }
      }
    }
  }


const toUtcSeconds = (t: number): UTCTimestamp => {
  // If milliseconds (e.g., 1698259200000), convert to seconds
  return (t > 4_000_000_000 ? Math.floor(t / 1000) : t) as UTCTimestamp;
};
type Marker = SeriesMarker<UTCTimestamp>;

const buildSignalMarkers = (signals: Record<string, any>, times: UTCTimestamp[]): Marker[] => {
  const n = times.length;
  const toBool = (v: any) => v === true || v === 1 || v === '1' || v === 'true';
  const buyArr  = Array.isArray(signals?.enter_long) ? signals.enter_long
                : Array.isArray(signals?.buy)        ? signals.buy : [];
  const sellArr = Array.isArray(signals?.exit_long)  ? signals.exit_long
                : Array.isArray(signals?.sell)       ? signals.sell : [];

  const buys  = Array.from({ length: n }, (_, i) => toBool(buyArr?.[i]));
  const sells = Array.from({ length: n }, (_, i) => toBool(sellArr?.[i]));

  const markers: Marker[] = [];
  for (let i = 0; i < n; i++) {
    const t = times[i];
    if (sells[i]) {
      markers.push({ time: t, position: 'aboveBar', color: '#ef4444', shape: 'arrowDown', text: 'SELL' });
    }
    if (buys[i]) {
      markers.push({ time: t, position: 'belowBar', color: '#16a34a', shape: 'arrowUp', text: 'BUY' });
    }
  }
  return markers;
};

const buildTradeMarkers = (trades: Array<Record<string, any>>, times: UTCTimestamp[]): Marker[] => {
  const arr = times as number[];
  const tset = new Set<number>(arr);
  const toSec = (v: any): number | undefined => {
    if (v == null) return undefined;
    if (typeof v === 'number') return v > 1e12 ? Math.floor(v / 1000) : Math.floor(v);
    const ms = Date.parse(v); return Number.isFinite(ms) ? Math.floor(ms / 1000) : undefined;
  };
  const nearest = (x: number): UTCTimestamp => {
    let lo = 0, hi = arr.length - 1;
    if (x <= arr[lo]) return arr[lo] as UTCTimestamp;
    if (x >= arr[hi]) return arr[hi] as UTCTimestamp;
    while (lo <= hi) {
      const m = (lo + hi) >> 1, v = arr[m];
      if (v === x) return v as UTCTimestamp;
      if (v < x) lo = m + 1; else hi = m - 1;
    }
    const a = arr[hi], b = arr[lo];
    return (x - a <= b - x ? a : b) as UTCTimestamp;
  };
  const snap = (sec?: number) =>
    sec == null ? undefined : (tset.has(sec) ? (sec as unknown as UTCTimestamp) : nearest(sec));

  const markers: Marker[] = [];
  for (const tr of trades || []) {
    const isShort = !!tr?.is_short;
    const entrySec = toSec(tr?.open_timestamp) ?? toSec(tr?.open_date);
    const exitSec  = toSec(tr?.close_timestamp) ?? toSec(tr?.close_date);
    const pr = typeof tr?.profit_ratio === 'number'
      ? tr.profit_ratio
      : (tr?.profit_ratio != null ? parseFloat(tr.profit_ratio) : undefined);

    const et = snap(entrySec);
    if (et) {
      markers.push({
        time: et,
        position: isShort ? 'aboveBar' : 'belowBar',
        shape: isShort ? 'arrowDown' : 'arrowUp',
        color: isShort ? '#ef4444' : '#16a34a',
        text: `ENTRY${tr?.pair ? ' ' + tr.pair : ''}${tr?.open_rate ? ` @ ${tr.open_rate}` : ''}`,
      });
    }
    if (exitSec != null) {
      const xt = snap(exitSec);
      if (xt) {
        const color = typeof pr === 'number' ? (pr >= 0 ? '#16a34a' : '#ef4444') : '#9ca3af';
        const pct = typeof pr === 'number' ? ` ${(pr * 100).toFixed(2)}%` : '';
        markers.push({
          time: xt,
          position: 'aboveBar',
          shape: 'circle',
          color,
          text: `EXIT${pct}${tr?.close_rate ? ` @ ${tr.close_rate}` : ''}`,
        });
      }
    }
  }
  return markers;
};

// Final single setter
const setAllMarkers = (signals: Record<string, any>, trades: Array<Record<string, any>>) => {
  const series = seriesRef.current;
  const times = lastTimesRef.current as UTCTimestamp[] | undefined;
  if (!series || !times || times.length === 0) { try { (series as any)?.setMarkers?.([]); } catch {} return; }

  const sig = buildSignalMarkers(signals, times);
  const trd = buildTradeMarkers(trades, times);

  // tie-breaker ordering (so belowBar arrows render “under” the exit circles, etc.)
  const orderWeight = (m: Marker) => {
    // lower weight drawn first
    // entries below, then buy signals below, then sells above, then exit circles above
    const isCircle = m.shape === 'circle';
    const above = m.position === 'aboveBar';
    if (!above && m.shape === 'arrowUp' && (m.text?.startsWith('ENTRY') ?? false)) return 0;
    if (!above && m.shape === 'arrowUp') return 1;
    if (above && m.shape === 'arrowDown') return 2;
    if (above && isCircle) return 3;
    return 5;
  };

  const all = [...sig, ...trd]
    .sort((a, b) => (a.time as number) - (b.time as number) || orderWeight(a) - orderWeight(b));

  try {
    (series as any).setMarkers?.([]);     // clear
    (series as any).setMarkers?.(all);    // set both
  } catch (e) {
    console.error('[markers] setAllMarkers failed:', e);
  }
};




  useEffect(() => {
    // Re-apply visibility when toggles or pane mode changes using last indicators
    const inds = lastIndicatorsRef.current
    if (!inds || Object.keys(inds).length === 0) return
    // Clear existing indicator series
    for (const s of indicatorSeriesRef.current.values()) {
      try { chartRef.current?.removeSeries(s) } catch {}
    }
    indicatorSeriesRef.current.clear()
    if (oscChartRef.current) {
      for (const s of oscSeriesRef.current.values()) {
        try { oscChartRef.current?.removeSeries(s) } catch {}
      }
      oscSeriesRef.current.clear()
    }
    // Redraw according to current visibility without changing state
    const names = Object.keys(inds)
    console.log('Redrawing indicators:', names, 'visible:', visibleIndicators, 'indicators:', lastIndicatorsRef.current)
    const times = lastTimesRef.current
    names.forEach((name, i) => {
      if (visibleIndicators && visibleIndicators[name] === false) return
      const values: Array<number | null> = Array.isArray(inds[name]) ? inds[name] : []
      const s = ensureLineSeries(name, i)
      if (!s) return
      const data = times.map((t, idx) => {
        const v = values[idx]
        if (v == null) return null
        const num = Number(v)
        if (!Number.isFinite(num)) return null
        return { time: t as UTCTimestamp, value: num }
      }).filter(Boolean) as any
      s.setData(data)
    })
  }, [visibleIndicators, showOscPane])

  const loadParity = async () => {
    if (!userId || !botId || !selectedPair || !selectedTf) return
    setLoading(true)
    setError(null)
    try {
      // 1) Ensure data on disk
      await api.post(`/users/${userId}/bots/${botId}/data/download`, {
        timerange: timerange || '-30d',
        pairs: [selectedPair],
        timeframes: [selectedTf],
        sync: true,
      })
      // 2) Fetch parity snapshot for selection
      const res = await api.get(`/users/${userId}/bots/${botId}/analytics/snapshot/parity`, {
        params: { limit: 3000, timeframe: selectedTf, pairs: selectedPair },
      })

      // Normalize response: backend may return JSON text, or even double-encoded JSON.
      // Start with raw axios data (already parsed object or string), then unwrap up to 3 times if it's a string.
      let snap: any = unwrapJsonLike(res.data, 3)
      if (typeof snap === 'string') {
        // Last-resort loose extraction
        snap = extractLooseJson(snap)
      }
      const s = Array.isArray((snap as any)?.series) ? (snap as any).series : []

      if (!s.length) {
        setNote('No series in snapshot')
        try { seriesRef.current?.setData([] as any) } catch {}
        setIndicators({})
        return
      }
      const selPair = String(selectedPair)
      const selTf = String(selectedTf)
      const matchExact = s.find((x: any) => String(x.pair) === selPair && String(x.timeframe) === selTf)
      const matchPair = matchExact || s.find((x: any) => String(x.pair) === selPair)
      const matchTf = matchPair || s.find((x: any) => String(x.timeframe) === selTf)
      const match = matchTf || s[0]

      if (match && Array.isArray(match.candles) && match.candles.length) {
              console.log('Loaded parity snapshot:', match)

        setSeriesData(match.candles)
        setIndicators(match.indicators || {})
        setNote(`${selectedPair} · ${selectedTf}`)
      } else {
        console.log('Loaded parity snapshot (no candle data for selection):', match)
        setNote('No candle data')
        try { seriesRef.current?.setData([] as any) } catch {}
        setIndicators(match?.indicators || {})
      }

    } catch (e: any) {
      const msg = e?.response?.data?.detail || e?.message || 'Failed to load parity snapshot'
      setError(String(msg))
    } finally {
      setLoading(false)
    }
  }

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
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center', marginBottom: 8 }}>
        <label><strong>Timerange</strong></label>
        <input value={timerange} onChange={(e) => setTimerange(e.target.value)} placeholder="e.g. -30d or 20240101-20241024" style={{ padding: 6, borderRadius: 6, border: '1px solid #e5e7eb' }} />
        <button onClick={loadParity} disabled={loading || !selectedPair || !selectedTf} style={{ padding: '6px 10px', borderRadius: 6, border: '1px solid #2563eb', background: loading ? '#dbeafe' : '#2563eb', color: '#fff' }}>{loading ? 'Loading…' : 'Load'}</button>
        <label style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12 }}>
          <input type="checkbox" checked={showOscPane} onChange={(e) => setShowOscPane(e.target.checked)} />
          Oscillators on separate pane
        </label>
      </div>
      {pairs.length > 0 && PairTabs}
      {timeframes.length > 0 && TfTabs}
      <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 6 }}>{note}</div>
      <div ref={wrapRef} style={{ width: '100%', minHeight: 420 }} />
      {showOscPane && (
        <div ref={oscWrapRef} style={{ width: '100%', minHeight: 160, marginTop: 8 }} />
      )}
      {error && (
        <div style={{ marginTop: 8, color: '#dc2626' }}>{error}</div>
      )}
    </div>
  )
}

export default BackstagePanel
