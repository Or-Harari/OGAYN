// useBotSeries.ts
import { useEffect, useMemo, useRef, useState } from 'react'
import { api, API_BASE } from '@/lib/api'

type SeriesPayload = {
  pair: string
  timeframe: string
  candles?: any
  indicators?: Record<string, any>
  signals?: Record<string, any>
}

type SnapshotRes = {
  pairs?: string[]
  timeframes?: string[]
  effective_timeframe?: string | null
  series?: SeriesPayload[]
  trades?: any[] | { trades?: any[] }
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

export function useBotSeries({
  userId,
  botId,
  selectedPair,
  selectedTf,
}: {
  userId: number
  botId: number
  selectedPair?: string
  selectedTf?: string
}) {
  const [pairs, setPairs] = useState<string[]>([])
  const [timeframes, setTimeframes] = useState<string[]>([])
  const [effectiveTf, setEffectiveTf] = useState<string | undefined>(undefined)

  const [candles, setCandles] = useState<any>([])
  const [indicators, setIndicators] = useState<Record<string, any>>({})
  const [signals, setSignals] = useState<Record<string, any>>({})
  const [trades, setTrades] = useState<any[]>([])

  const wsRef = useRef<WebSocket | null>(null)
  const lastMsgAtRef = useRef<number>(0)
  const reconnectRef = useRef<any>(null)

  // --- Initial snapshot (for configured pairs/tfs) + initial series (if present) ---
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const r = await api.get<SnapshotRes>(`/users/${userId}/bots/${botId}/analytics/snapshot`, { params: { limit: 300 } })
        if (cancelled) return
        const data = r.data || {}
        const ps = Array.isArray(data.pairs) ? data.pairs : []
        const tfs = Array.isArray(data.timeframes) ? data.timeframes : []
        const effTf = typeof data.effective_timeframe === 'string' ? data.effective_timeframe : undefined

        setPairs(ps)
        setTimeframes(tfs)
        setEffectiveTf(effTf)

        // capture trades (if array or inside { trades: [...] })
        const tradesArr = Array.isArray((data as any).trades)
          ? (data as any).trades
          : (data as any)?.trades?.trades || []
        setTrades(Array.isArray(tradesArr) ? tradesArr : [])

        // If a pair/tf already chosen, try to seed candles/indicators/signals from this snapshot
        if (selectedPair && (selectedTf || effTf)) {
          const targetTf = selectedTf || effTf!
          const s = Array.isArray(data.series) ? data.series : []
          const match = s.find(x => x.pair === selectedPair && x.timeframe === targetTf)
          if (match) {
            if (match.candles) setCandles(match.candles)
            setIndicators(match.indicators || {})
            setSignals(match.signals || {})
          }
        }
      } catch (e) {
        // ignore; WS will still pump data when collector ticks
        console.debug('[useBotSeries] snapshot error:', e)
      }
    })()
    return () => { cancelled = true }
  }, [userId, botId, selectedPair, selectedTf])

  // --- WebSocket live updates (single source of truth for ongoing changes) ---
  useEffect(() => {
    if (!userId || !botId) return
    const origin = toWsOrigin(API_BASE)
    const wsUrl = `${origin}/users/${userId}/bots/${botId}/analytics/ws`

    let closed = false

    const connect = () => {
      let ws: WebSocket
      try {
        ws = new WebSocket(wsUrl)
      } catch {
        if (!closed) reconnectRef.current = setTimeout(connect, 2000)
        return
      }
      wsRef.current = ws

      ws.onopen = () => {
        lastMsgAtRef.current = Date.now()
        // no subscription payload needed on your backend
      }

      ws.onmessage = (ev) => {
        lastMsgAtRef.current = Date.now()
        try {
          const msg = JSON.parse(ev.data)
          if (msg?.type === 'series' && Array.isArray(msg.updates)) {
            // find the update matching current selection; if none selected yet, seed from first update
            let wantedPair = selectedPair
            let wantedTf = selectedTf || effectiveTf

            const updForSelection =
              msg.updates.find((u: any) => (!wantedPair || u.pair === wantedPair) && (!wantedTf || u.timeframe === wantedTf))

            const chosen = updForSelection ?? msg.updates[0]
            if (chosen) {
              if (!wantedPair) wantedPair = chosen.pair
              if (!wantedTf) wantedTf = chosen.timeframe
              if (chosen.candles) setCandles(chosen.candles)
              setIndicators(chosen.indicators || {})
              setSignals(chosen.signals || {})
            }
          }
        } catch (e) {
          console.debug('[useBotSeries] ws parse err', e)
        }
      }

      ws.onclose = () => {
        if (!closed) reconnectRef.current = setTimeout(connect, 2500)
      }
      ws.onerror = () => {
        try { ws.close() } catch {}
      }
    }

    connect()
    return () => {
      closed = true
      try { wsRef.current?.close() } catch {}
      clearTimeout(reconnectRef.current)
    }
  }, [userId, botId, selectedPair, selectedTf, effectiveTf])

  return useMemo(() => ({
    pairs, timeframes, effectiveTf,
    candles, indicators, signals, trades,
  }), [pairs, timeframes, effectiveTf, candles, indicators, signals, trades])
}
