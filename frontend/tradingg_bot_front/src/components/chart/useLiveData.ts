// useLiveData.ts (drop-in)
import { useEffect, useMemo, useRef, useState } from 'react'
import { api, API_BASE } from '@/lib/api'

type LiveParams = {
  userId?: number
  botId?: number
  pair?: string           // preferred pair from parent (optional)
  timeframe?: string      // preferred timeframe from parent (optional)
  limit?: number
  enabled?: boolean       // gate WS + HTTP activity
}

function toWsOrigin(httpBase: string): string {
  try {
    const u = new URL(httpBase)
    u.protocol = u.protocol === 'https:' ? 'wss:' : 'ws:'
    return u.origin
  } catch {
    const proto = location.protocol === 'https:' ? 'wss://' : 'ws://'
    return proto + location.host
  }
}

export function useLiveData({ userId, botId, pair, timeframe, limit = 300, enabled = true }: LiveParams) {
  // public data
  const [candles, setCandles] = useState<any[]>([])
  const [indicators, setIndicators] = useState<Record<string, any>>({})
  const [signals, setSignals] = useState<Record<string, any>>({})
  const [trades, setTrades] = useState<any[]>([])
  const [pairs, setPairs] = useState<string[]>([])
  const [timeframes, setTimeframes] = useState<string[]>([])
  const [effectiveTimeframe, setEffectiveTimeframe] = useState<string | undefined>(undefined)

  // internal state/refs
  const wsRef = useRef<WebSocket | null>(null)
  const lastMsgAtRef = useRef<number>(0)
  const pollTimerRef = useRef<any>(null)
  const reconnectTimerRef = useRef<any>(null)
  // avoid tight fallback loops when snapshot lacks candles
  const postRefreshOnceRef = useRef<{ key?: string; at?: number }>({})
  // cache of latest series by pair/timeframe for instant switching without extra fetches
  const lastSeriesRef = useRef<any[]>([])
  const seriesIndexRef = useRef<Map<string, any>>(new Map())

  const hasData = (c: any): boolean => {
    return Array.isArray(c?.data) ? c.data.length > 0 : Array.isArray(c) ? c.length > 0 : false
  }

  // single source-of-truth for the pair/tf the hook is using right now
  const pairRef = useRef<string | undefined>(undefined)
  const tfRef = useRef<string | undefined>(undefined)

  // HTTP endpoints require auth; WS does not. Split readiness flags.
  const httpReady = !!userId && !!botId
  const wsReady = !!botId

  // Helper: adopt pair/tf (only when valid) and log it
  const adoptPairTf = (nextPair?: string, nextTf?: string) => {
    const prevKey = pairRef.current && tfRef.current ? `${pairRef.current}|${tfRef.current}` : ''
    if (nextPair) pairRef.current = nextPair
    if (nextTf) tfRef.current = nextTf
    if (pairRef.current || tfRef.current) {
      console.debug('[live] ADOPT pair/tf', { pair: pairRef.current, tf: tfRef.current })
    }
    const newKey = pairRef.current && tfRef.current ? `${pairRef.current}|${tfRef.current}` : ''
    if (newKey && newKey !== prevKey) {
      // render immediately from cache if available (no extra calls)
      const cached = seriesIndexRef.current.get(newKey)
      if (cached) {
        if (hasData(cached.candles)) setCandles(cached.candles)
        if (cached.indicators) setIndicators(cached.indicators)
        if (cached.signals) setSignals(cached.signals)
      }
    }
  }

  const mergeSeriesIndex = (series: any[]) => {
    const arr = Array.isArray(series) ? series : []
    if (!lastSeriesRef.current) lastSeriesRef.current = []
    for (const s of arr) {
      const k = s && s.pair && s.timeframe ? `${s.pair}|${s.timeframe}` : ''
      if (!k) continue
      const prev = seriesIndexRef.current.get(k) || {}
      const merged: any = { ...prev, ...s }
      // Preserve non-empty candles if incoming has no data
      if ('candles' in s) {
        if (!hasData(s.candles) && hasData(prev.candles)) {
          merged.candles = prev.candles
        }
      }
      seriesIndexRef.current.set(k, merged)
    }
  }

  // ---- Initial snapshot & cadence polling ----
  useEffect(() => {
    if (!httpReady || !enabled) return
    let cancelled = false

    const pull = async (reason: string) => {
      // Always use current refs to avoid stale closures
      const p = pairRef.current || pair
      const tf = tfRef.current || timeframe

      console.debug('[live] PULL-SNAPSHOT', { userId, botId, limit, forPair: p, forTf: tf, reason })
      try {
        const res = await api.get(`/users/${userId}/bots/${botId}/analytics/snapshot`, { params: { limit } })
        if (cancelled) return
console.log('[live] SNAPSHOT RESPONSE',p);
        const snap = res.data || {}
  const series = Array.isArray(snap.series) ? snap.series : []
  mergeSeriesIndex(series)
        const ps: string[] = Array.isArray(snap.pairs) ? snap.pairs : []
        const tfs: string[] = Array.isArray(snap.timeframes) ? snap.timeframes : []
        const effTf: string | undefined =
          typeof snap.effective_timeframe === 'string' ? snap.effective_timeframe : undefined

        setPairs(ps)
        setTimeframes(tfs)
        setEffectiveTimeframe(effTf)

        // Decide the active pair/timeframe conservatively:
        // Keep current selection if set; only adopt defaults when nothing selected yet
        let nextPair = pairRef.current || pair
        if (!nextPair && ps.length > 0) nextPair = ps[0]

        let nextTf = tfRef.current || timeframe
        if (!nextTf) nextTf = effTf || tfs[0]
        if (nextPair || nextTf) adoptPairTf(nextPair, nextTf)

        // Find matching series
  const matchKey = (pairRef.current && tfRef.current) ? `${pairRef.current}|${tfRef.current}` : ''
  const match = matchKey ? seriesIndexRef.current.get(matchKey) : undefined

        // Update trades (if present)
        if (snap.trades && Array.isArray(snap.trades)) setTrades(snap.trades)
        else if (snap.trades && Array.isArray(snap.trades?.trades)) setTrades(snap.trades.trades)
        else setTrades([])

        // Primary path: we got candles in snapshot
        if (match?.candles && Array.isArray(match.candles?.data) ? match.candles.data.length > 0 : Array.isArray(match?.candles) && match.candles.length > 0) {
          setCandles(match.candles)
          setIndicators(match.indicators || {})
          setSignals(match.signals || {})
          console.debug('[live] snapshot applied', {
            pair: pairRef.current, tf: tfRef.current,
            dataLen: Array.isArray(match.candles?.data) ? match.candles.data.length : (match.candles?.length ?? 0),
          })
        } else {
          // Fallback: fetch candles directly for the adopted pair/tf
          const pf = pairRef.current
          const tff = tfRef.current
          if (pf && tff) {
            const key = `${pf}|${tff}`
            // Only do a single fallback + one post-refresh per pair/tf within 60s
            const lastKey = postRefreshOnceRef.current.key
            const lastAt = postRefreshOnceRef.current.at || 0
            const withinWindow = Date.now() - lastAt < 60_000
            if (lastKey === key && withinWindow) {
              console.debug('[live] fallback suppressed (recent)', { key })
              return
            }
            console.debug('[live] FALLBACK-CANDLES', { pair: pf, tf: tff })
            try {
              const r2 = await api.get(`/users/${userId}/bots/${botId}/analytics/candles`, {
                params: { pair: pf, timeframe: tff, limit }
              })
              if (!cancelled) {
                const data = r2.data
                const hasData = Array.isArray(data?.data) ? data.data.length > 0 : Array.isArray(data) ? data.length > 0 : false
                if (hasData) {
                  setCandles(data)
                } else {
                  console.debug('[live] fallback returned empty candles; preserving current series')
                }
                // Schedule a single post-refresh snapshot to pick indicators/signals
                postRefreshOnceRef.current = { key, at: Date.now() }
                setTimeout(() => pull('post-candles-refresh'), 1000)
              }
            } catch (e) {
              console.warn('[live] fallback candles error', e)
            }
          } else {
            console.debug('[live] No pair/tf to fallback-fetch.')
          }
        }
      } catch (e) {
        console.debug('[live] snapshot error', e)
      }
    }

    // initial paint
    pull('initial')

    // poll if WS silent >30s (collector cadence ~15–60s)
    pollTimerRef.current = setInterval(() => {
      const silentMs = Date.now() - (lastMsgAtRef.current || 0)
      if (silentMs > 30_000) pull('keepalive')
    }, 10_000)

    return () => {
      clearInterval(pollTimerRef.current)
      pollTimerRef.current = null
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [httpReady, enabled, userId, botId, limit]) // don't depend on pair/timeframe props here (we read via refs)

  // Keep refs aligned to props if parent explicitly controls them
  useEffect(() => {
    if (pair) {
      adoptPairTf(pair, undefined)
    }
  }, [pair])

  useEffect(() => {
    if (timeframe) {
      adoptPairTf(undefined, timeframe)
    }
  }, [timeframe])

  // ---- WebSocket (series only) ----
  useEffect(() => {
    if (!wsReady || !enabled) return

    const origin = toWsOrigin(API_BASE)
    const wsUrl = `${origin}/users/${userId}/bots/${botId}/analytics/ws`

    let ws: WebSocket | null = null
    let closed = false

    const scheduleReconnect = () => {
      if (closed) return
      reconnectTimerRef.current = setTimeout(connect, 2500)
    }

    const connect = () => {
      try {
        ws = new WebSocket(wsUrl)
        wsRef.current = ws
      } catch {
        scheduleReconnect()
        return
      }

      ws.onopen = () => {
        lastMsgAtRef.current = Date.now()
        console.debug('[live] ws open', { url: wsUrl })
      }

      ws.onmessage = (ev) => {
        lastMsgAtRef.current = Date.now()
        try {
          const msg = JSON.parse(ev.data)
          if (msg?.type === 'series' && Array.isArray(msg.updates)) {
            const combos = msg.updates.map((u: any) => `${u.pair}/${u.timeframe}`)
            // Debug all combos server is sending
            console.debug('[live] ws combos', combos)

            const p = pairRef.current
            const tf = tfRef.current
            // merge updates into cache first
            for (const u of msg.updates) {
              const k = u && u.pair && u.timeframe ? `${u.pair}|${u.timeframe}` : ''
              if (!k) continue
              const prev = seriesIndexRef.current.get(k) || {}
              seriesIndexRef.current.set(k, { ...prev, ...u })
            }
            let upd = msg.updates.find((u: any) => (!p || u.pair === p) && (!tf || u.timeframe === tf))
            // If no update matches current selection (e.g., stale/invalid pair/tf), adopt the first update
            if (!upd && msg.updates.length > 0) {
              upd = msg.updates[0]
              adoptPairTf(upd.pair, upd.timeframe)
            }
            if (!upd) return // nothing to apply

            // If we didn't have an adopted pair/tf yet, adopt from the update we chose
            if (!p || !tf) {
              adoptPairTf(upd.pair, upd.timeframe)
            }
            if (upd.candles) {
              const hasData = Array.isArray(upd.candles?.data)
                ? upd.candles.data.length > 0
                : Array.isArray(upd.candles)
                  ? upd.candles.length > 0
                  : false
              if (hasData) {
                setCandles(upd.candles)
              } else {
                // Ignore empty-candle WS frames to avoid wiping the chart during idle/heartbeat updates
                console.debug('[live] ws update contained empty candles; preserving current series')
              }
            }
            if (upd.indicators) setIndicators(upd.indicators)
            if (upd.signals) setSignals(upd.signals)

            const len = Array.isArray(upd.candles?.data) ? upd.candles.data.length : (upd.candles?.length ?? 0)
            console.debug('[live] ws applied', { pair: p, tf, dataLen: len })
          }
        } catch (e) {
          console.debug('[live] ws message parse error', e)
        }
      }

      ws.onclose = () => {
        if (closed) return
        console.debug('[live] ws closed, reconnecting…')
        scheduleReconnect()
      }

      ws.onerror = () => {
        try { ws?.close() } catch {}
      }
    }

    connect()

    return () => {
      closed = true
      try { ws?.close() } catch {}
      clearTimeout(reconnectTimerRef.current)
    }
  }, [wsReady, enabled, userId, botId])

  return useMemo(() => ({
    // data
    candles, indicators, signals, trades,
    // meta to build UI toggles
    pairs, timeframes, effectiveTimeframe,
    // helpers (if a parent wants to force pair/tf)
    setActivePair: (p: string) => adoptPairTf(p, undefined),
    setActiveTimeframe: (tf: string) => adoptPairTf(undefined, tf),
    getActive: () => ({ pair: pairRef.current, timeframe: tfRef.current }),
  }), [candles, indicators, signals, trades, pairs, timeframes, effectiveTimeframe])
}
