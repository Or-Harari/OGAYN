// LiveAnalyticsContainer.tsx
import React, { useEffect, useState } from 'react'
import AnalyticsChart from './AnalyticsChart'
import { useLiveData } from './useLiveData'

type Props = {
  userId?: number
  botId: number
  pair?: string
  timeframe?: string
  showSelectors?: boolean
  enabled?: boolean
}

export default function LiveAnalyticsContainer({ userId, botId, pair: pairProp, timeframe: tfProp, showSelectors = true, enabled = true }: Props) {
  const [localPair, setLocalPair] = useState<string | undefined>(undefined)
  const [localTf, setLocalTf] = useState<string | undefined>(undefined)
  const pair = pairProp ?? localPair
  const tf = tfProp ?? localTf

  const {
    pairs, timeframes, effectiveTimeframe,
    candles, indicators, signals, trades,
    setActivePair, setActiveTimeframe,
  } = useLiveData({ userId, botId, pair, timeframe: tf, limit: 300, enabled })

  // Fit the chart only on first non-empty dataset
  const [fitOnce, setFitOnce] = React.useState(true)
  React.useEffect(() => {
    const len = Array.isArray((candles as any)?.data) ? (candles as any).data.length : Array.isArray(candles) ? candles.length : 0
    if (fitOnce && len > 0) {
      // flip off on next tick so subsequent updates don't refit
      const t = setTimeout(() => setFitOnce(false), 0)
      return () => clearTimeout(t)
    }
  }, [indicators,candles, fitOnce])

  // Initialize selection from configured values only (no REST /candles; no hardcoded defaults)
  useEffect(() => {
    // Only adopt when parent provides an explicit pair; do not auto-pick defaults
    if (pairProp) {
      setActivePair(pairProp)
    }
  }, [pairs, pairProp, setActivePair])

  useEffect(() => {
    // Only adopt when parent provides an explicit timeframe; do not auto-pick defaults
    if (tfProp) {
      setActiveTimeframe(tfProp)
    }
  }, [tfProp, setActiveTimeframe])

  return (
    <div className="space-y-3">
      {/* Pair picker: configured pairs only */}
      {showSelectors && pairs?.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {pairs.map(p => (
            <button
              key={p}
              onClick={() => { setLocalPair(p); setActivePair(p) }}
              className={`px-2 py-1 rounded border ${pair === p ? 'bg-indigo-50 border-indigo-300' : 'bg-white border-gray-200'}`}
            >
              {p}
            </button>
          ))}
        </div>
      )}

      {/* Timeframe picker: configured or strategy-effective */}
      {showSelectors && ((timeframes?.length ?? 0) > 0 || effectiveTimeframe) && (
        <div className="flex flex-wrap gap-2">
          {[...(effectiveTimeframe && !(timeframes||[]).includes(effectiveTimeframe) ? [effectiveTimeframe] : []), ...(timeframes || [])]
            .filter((v, i, a) => a.indexOf(v) === i)
            .map(t => (
              <button
                key={t}
                onClick={() => { setLocalTf(t); setActiveTimeframe(t) }}
                className={`px-2 py-1 rounded border ${tf === t ? 'bg-indigo-50 border-indigo-300' : 'bg-white border-gray-200'}`}
              >
                {t}
              </button>
            ))
          }
        </div>
      )}

      <AnalyticsChart
        candles={candles}
        indicators={indicators}
        signals={signals}
        trades={Array.isArray(trades) && (pair || '').length > 0 ? trades.filter((t: any) => String(t?.pair) === String(pair)) : trades}
        showOscPane={true}
        height={420}
        oscHeight={160}
        fitContent={fitOnce}
      />
    </div>
  )
}
