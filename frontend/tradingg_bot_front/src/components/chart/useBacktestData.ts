// useBacktestData.ts (parity snapshot)
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export function useBacktestData(params: {
  userId: number;
  botId: number;
  pair: string;
  timeframe: string;
  timerange: string;
  limit?: number;
  fromTs?: number; // optional unix seconds to slice from (inclusive)
  toTs?: number;   // optional unix seconds to slice to (inclusive)
  enabled?: boolean; // when false, skip any backend calls
}) {
  const { userId, botId, pair, timeframe, timerange, limit = 3000, fromTs, toTs, enabled = true } = params;
  const [state, setState] = useState<{ candles: any; indicators: any; signals: any; trades: any[] }>({
    candles: [], indicators: {}, signals: {}, trades: [],
  });

  useEffect(() => {
    if (!enabled) return;
    if (!userId || !botId || !pair || !timeframe || !timerange) return;

    // Basic timeframe sanity: prevent accidental 1m spam if not requested
    const tf = String(timeframe).toLowerCase();
    if (!['1m','3m','5m','15m','30m','1h','4h','1d'].includes(tf)) return;

    let cancelled = false;
    let cooldown = false;
    (async () => {
      // Derive a download timerange that matches the chart window when available
      const toYmd = (ts: number): string => {
        // Format UTC YYYYMMDD
        const d = new Date(ts * 1000)
        const y = d.getUTCFullYear()
        const m = String(d.getUTCMonth() + 1).padStart(2, '0')
        const day = String(d.getUTCDate()).padStart(2, '0')
        return `${y}${m}${day}`
      }
      let dlTimerange = timerange
      if (typeof fromTs === 'number' || typeof toTs === 'number') {
        try {
          const fromStr = typeof fromTs === 'number' ? toYmd(fromTs) : undefined
          const toStr = typeof toTs === 'number' ? toYmd(toTs) : undefined
          if (fromStr && toStr) dlTimerange = `${fromStr}-${toStr}`
          else if (fromStr) dlTimerange = `${fromStr}-`
          // If only toTs is present, keep original timerange (avoid generating unsupported "-YYYYMMDD")
        } catch {
          // fall back to provided timerange
        }
      }

      try {
        await api.post(`/users/${userId}/bots/${botId}/data/download`, {
          timerange: dlTimerange, pairs: [pair], timeframes: [timeframe], sync: true,
        });
      } catch (e) {
        // If download fails, still attempt parity snapshot (may have cached data)
      }
      let r: any;
      try {
        r = await api.get(`/users/${userId}/bots/${botId}/analytics/snapshot/parity`, {
          params: { limit, timeframe, pairs: pair, from_ts: fromTs, to_ts: toTs },
        });
      } catch (e) {
        // On 5xx errors, abort without state update to prevent retry storm.
        cooldown = true;
        return;
      }
      const series = Array.isArray(r.data?.series) ? r.data.series : [];
      const match = series.find((s: any) => s.pair === pair && s.timeframe === timeframe) || series[0];
      if (!cancelled && match) {
        setState({
          candles: match.candles || [],
          indicators: match.indicators || {},
          signals: match.signals || {},
          trades: (r.data?.trades || []),
        });
      }
    })().catch(() => {});
    return () => { cancelled = true; };
  }, [enabled, userId, botId, pair, timeframe, timerange, limit, fromTs, toTs]);

  return state; // { candles, indicators, signals, trades }
}
