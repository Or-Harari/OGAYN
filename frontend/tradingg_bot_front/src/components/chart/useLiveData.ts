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
  pollingSec?: number     // snapshot polling cadence in seconds (defaults to 1s)
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

export function useLiveData({ userId, botId, pair, timeframe, limit = 300, enabled = true, pollingSec = 1 }: LiveParams) {
  // public data
  const [candles, setCandles] = useState<any[]>([])
  const [indicators, setIndicators] = useState<Record<string, any>>({})
  const [signals, setSignals] = useState<Record<string, any>>({})
  const [trades, setTrades] = useState<any[]>([])
  const [openTrades, setOpenTrades] = useState<any[]>([])
  const [pairs, setPairs] = useState<string[]>([])
  const [timeframes, setTimeframes] = useState<string[]>([])
  const [effectiveTimeframe, setEffectiveTimeframe] = useState<string | undefined>(undefined)

  // internal state/refs
  const wsRef = useRef<WebSocket | null>(null)
  const lastMsgAtRef = useRef<number>(0)
  const pollTimerRef = useRef<any>(null)
  const reconnectTimerRef = useRef<any>(null)
  const pullingRef = useRef<boolean>(false)
  // sequential fetch guard to avoid race conditions on rapid switching
  const lastFetchIdRef = useRef<number>(0)

  const hasData = (c: any): boolean => {
    return Array.isArray(c?.data) ? c.data.length > 0 : Array.isArray(c) ? c.length > 0 : false
  }

  // single source-of-truth for the pair/tf the hook is using right now
  const pairRef = useRef<string | undefined>(undefined)
  const tfRef = useRef<string | undefined>(undefined)

  // HTTP endpoints require auth; WS does not. Split readiness flags.
  const httpReady = !!userId && !!botId
  const wsReady = !!botId

  // Helper: direct fetch for candles for current active pair/tf when cache misses
  const fetchCandlesDirect = async (p?: string, tf?: string) => {
    if (!httpReady || !enabled) return
    if (!p || !tf) return
    try {
      const fetchId = ++lastFetchIdRef.current
      const r2 = await api.get(`/users/${userId}/bots/${botId}/analytics/candles`, {
        params: { pair: p, timeframe: tf, limit }
      })
      const data = r2.data
      const ok = Array.isArray(data?.data) ? data.data.length > 0 : Array.isArray(data) ? data.length > 0 : false
      if (ok) {
        // ensure response is still relevant for current selection and latest request
        if (fetchId !== lastFetchIdRef.current) return
        if (pairRef.current !== p || tfRef.current !== tf) return
        setCandles(data)
        let inds: Record<string, any> | undefined
        let sigs: Record<string, any> | undefined
        try {
          const extracted = extractOverlaysFromCandles(data)
          inds = extracted.indicators
          sigs = extracted.signals
          if (inds) setIndicators(inds)
          if (sigs) setSignals(sigs)
        } catch {}
      }
    } catch (e) {
      console.debug('[live] direct candles fetch error', e)
    }
  }

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
      // clear any stale view immediately while we resolve the proper dataset
      setCandles([])
      // Always fetch fresh candles for the new selection
      fetchCandlesDirect(pairRef.current, tfRef.current)
    }
  }

  // cache removed

  // Build indicators and signals from a candles response when snapshot doesn't carry overlays
  function extractOverlaysFromCandles(resp: any): { indicators: Record<string, any>, signals: Record<string, any> } {
    const rows: any[] = Array.isArray(resp?.data) ? resp.data : []
    const cols: string[] = Array.isArray(resp?.columns) ? resp.columns : (Array.isArray(resp?.all_columns) ? resp.all_columns : [])
    const idx: Record<string, number> = {}
    cols.forEach((c, i) => { idx[String(c).toLowerCase()] = i })
    const gi = (name: string): number => (idx.hasOwnProperty(name) ? idx[name] : -1)
    const pickNum = (r: any[], i: number) => (i >= 0 && r[i] != null ? Number(r[i]) : null)
    const pickBool = (r: any[], i: number) => (i >= 0 ? (r[i] === 1 || r[i] === true || r[i] === '1' || r[i] === 'true') : false)
    const pickStr = (r: any[], i: number) => (i >= 0 && r[i] != null ? String(r[i]) : '')

    const lineNames = ['pivot_low','pivot_high','valid_low','valid_high','zone_low','zone_high','target_high','target_low']
    const indicators: Record<string, any> = {}
    for (const name of lineNames) {
      const ii = gi(name)
      if (ii >= 0) indicators[name] = rows.map((r) => pickNum(r, ii))
    }

    // signals
    const enterLongIdx = gi('enter_long')
    const exitLongIdx = gi('exit_long')
    const enterShortIdx = gi('enter_short')
    const exitShortIdx = gi('exit_short')
    const enterTagIdx = gi('enter_tag')
    const exitTagIdx = gi('exit_tag')
    const signals: Record<string, any> = {
      enter_long: rows.map((r) => pickBool(r, enterLongIdx)),
      exit_long: rows.map((r) => pickBool(r, exitLongIdx)),
    }
    if (enterShortIdx >= 0) signals.enter_short = rows.map((r) => pickBool(r, enterShortIdx))
    if (exitShortIdx >= 0) signals.exit_short = rows.map((r) => pickBool(r, exitShortIdx))
    if (enterTagIdx >= 0) signals.enter_tag = rows.map((r) => pickStr(r, enterTagIdx))
    if (exitTagIdx >= 0) signals.exit_tag = rows.map((r) => pickStr(r, exitTagIdx))

    return { indicators, signals }
  }

  // ---- Initial snapshot & cadence polling ----
  useEffect(() => {
    if (!httpReady || !enabled) return
    let cancelled = false

    const pull = async (reason: string) => {
      if (pullingRef.current) return
      pullingRef.current = true
      // Always use current refs to avoid stale closures
      const p = pairRef.current || pair
      const tf = tfRef.current || timeframe

      console.debug('[live] PULL-SNAPSHOT', { userId, botId, limit, forPair: p, forTf: tf, reason })
      try {
        const res = await api.get(`/users/${userId}/bots/${botId}/analytics/snapshot`, { params: { limit } })
        if (cancelled) return
        // capture last msg time for keepalive logic
        const snap = res.data || {}
        const ps: string[] = Array.isArray(snap.pairs) ? snap.pairs : []
        const tfs: string[] = Array.isArray(snap.timeframes) ? snap.timeframes : []
        const effTf: string | undefined =
          typeof snap.effective_timeframe === 'string' ? snap.effective_timeframe : undefined

        // Decide the active pair/timeframe conservatively:
        // Keep current selection if set; only adopt defaults when nothing selected yet
        let nextPair = pairRef.current || pair
        if (!nextPair && ps.length > 0) nextPair = ps[0]

        let nextTf = tfRef.current || timeframe
        if (!nextTf) nextTf = effTf || tfs[0]
        if (nextPair || nextTf) adoptPairTf(nextPair, nextTf)

        // Trades only (candles fetched separately on adopt)
        const snapTrades = snap.trades && Array.isArray(snap.trades?.trades) ? snap.trades.trades : (Array.isArray(snap.trades) ? snap.trades : [])
        if (Array.isArray(snapTrades)) setTrades(snapTrades)
        else setTrades([])
        if (Array.isArray(snap.open_trades)) setOpenTrades(snap.open_trades)
        else setOpenTrades([])
      } catch (e) {
        console.debug('[live] snapshot error', e)
      } finally {
        pullingRef.current = false
      }
    }

    // initial paint
    pull('initial')

    // steady polling on user-selected cadence (seconds)
    const every = Math.max(1, Math.floor(pollingSec || 1)) * 1000
    pollTimerRef.current = setInterval(() => {
      pull('interval')
    }, every)

    return () => {
      clearInterval(pollTimerRef.current)
      pollTimerRef.current = null
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [httpReady, enabled, userId, botId, limit, pollingSec]) // don't depend on pair/timeframe props here (we read via refs)

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
            // Do not update candles from WS to avoid mixing; rely on /candles fetches only
            //if (upd.indicators) setIndicators(upd.indicators)
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
    candles, indicators, signals, trades, openTrades,
    // meta to build UI toggles
    pairs, timeframes, effectiveTimeframe,
    // helpers (if a parent wants to force pair/tf)
    setActivePair: (p: string) => adoptPairTf(p, undefined),
    setActiveTimeframe: (tf: string) => adoptPairTf(undefined, tf),
    getActive: () => ({ pair: pairRef.current, timeframe: tfRef.current }),
  }), [candles, indicators, signals, trades, openTrades, pairs, timeframes, effectiveTimeframe])
}
