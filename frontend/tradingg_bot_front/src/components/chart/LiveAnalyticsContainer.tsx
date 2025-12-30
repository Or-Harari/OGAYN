// LiveAnalyticsContainer.tsx
import React, { useEffect, useState, useMemo } from 'react'
import AnalyticsChart from './AnalyticsChart'
import PriceVolumeWrapper from './PriceVolumeWrapper'
import { useLiveData } from './useLiveData'

type Props = {
  userId?: number
  botId: number
  pair?: string
  timeframe?: string
  showSelectors?: boolean
  enabled?: boolean
  /** Use new React wrapper based price+volume component for main pane */
  useWrapperChart?: boolean
  pollingSec?: number
  onOpenTrades?: (trades: any[]) => void
}

export default function LiveAnalyticsContainer({ userId, botId, pair: pairProp, timeframe: tfProp, showSelectors = true, enabled = true, useWrapperChart = true, pollingSec = 1, onOpenTrades }: Props) {
  const [localPair, setLocalPair] = useState<string | undefined>(undefined)
  const [localTf, setLocalTf] = useState<string | undefined>(undefined)
  const pair = pairProp ?? localPair
  const tf = tfProp ?? localTf
  const [intervalSec, setIntervalSec] = useState<number>(pollingSec)

  // Pull full live data including overlays
  const {
    pairs, timeframes, effectiveTimeframe,
    candles, openTrades, indicators, signals, trades,
    setActivePair, setActiveTimeframe,
  } = useLiveData({ userId, botId, pair, timeframe: tf, limit: 300, enabled, pollingSec: intervalSec })

  // reflect external change if parent changes pollingSec
  useEffect(() => { setIntervalSec(pollingSec) }, [pollingSec])

  // Fit the chart only on first non-empty dataset
  const [fitOnce, setFitOnce] = useState(true)
  useEffect(() => {
    const len = Array.isArray((candles as any)?.data) ? (candles as any).data.length : Array.isArray(candles) ? candles.length : 0
    if (fitOnce && len > 0) {
      // flip off on next tick so subsequent updates don't refit
      const t = setTimeout(() => setFitOnce(false), 0)
      return () => clearTimeout(t)
    }
  }, [candles, fitOnce])

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

  // Bubble open trades immediately if caller wants them
  useEffect(() => {
    if (onOpenTrades) onOpenTrades(openTrades || [])
  }, [openTrades, onOpenTrades])

  // overlays UI state
  const [showSignals, setShowSignals] = useState(true)
  const [visibleIndicators, setVisibleIndicators] = useState<Record<string, boolean>>({})
  const indicatorNames = useMemo(() => Object.keys(indicators || {}), [indicators])
  useEffect(() => {
    setVisibleIndicators(prev => {
      const next = { ...prev }
      let changed = false
      for (const n of indicatorNames) if (!(n in next)) { next[n] = false; changed = true }
      for (const k of Object.keys(next)) if (!indicatorNames.includes(k)) { delete next[k]; changed = true }
      return changed ? next : prev
    })
  }, [indicatorNames])

  const combinedTrades = useMemo(() => {
    const arr = [...(openTrades || []), ...(trades || [])]
    return (pair ? arr.filter(t => String(t?.pair) === String(pair)) : arr)
  }, [openTrades, trades, pair])

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

      {/* Interval selector */}
      {showSelectors && (
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center', fontSize: 12 }}>
          <label style={{ fontWeight: 600 }}>Update Interval:</label>
          <select
            value={intervalSec}
            onChange={(e) => setIntervalSec(Number(e.target.value))}
            style={{ padding: '4px 8px', borderRadius: 6, border: '1px solid #e5e7eb' }}
          >
            {[1,5,10,30].map(sec => (
              <option key={sec} value={sec}>{sec}s</option>
            ))}
          </select>
        </div>
      )}

      {useWrapperChart ? (
        <div className="flex flex-col gap-2">
          <PriceVolumeWrapper
            candles={candles}
            indicators={indicators}
            signals={signals}
            trades={combinedTrades}
            visibleIndicators={visibleIndicators}
            showSignals={showSignals}
            seriesKey={`${pair || 'nopair'}-${tf || 'notf'}`}
            height={420}
            fitContent={fitOnce}
          />
          <div style={{ display:'flex', flexWrap:'wrap', gap:12, alignItems:'center', fontSize:12 }}>
            <IndicatorsDropdown
              names={indicatorNames}
              state={visibleIndicators}
              onChange={setVisibleIndicators}
            />
            <label style={{ display:'inline-flex', alignItems:'center', gap:6 }}>
              <input type='checkbox' checked={showSignals} onChange={e=>setShowSignals(e.target.checked)} />
              Show BUY/SELL signals
            </label>
          </div>
          
        </div>
      ) : (
        <AnalyticsChart
          candles={candles}
          seriesKey={`${pair || 'nopair'}-${tf || 'notf'}`}
          height={420}
          fitContent={fitOnce}
        />
      )}
      
    </div>
  )
}

function IndicatorsDropdown({ names, state, onChange }:{ names:string[]; state:Record<string,boolean>; onChange:(v:Record<string,boolean>)=>void }) {
  const [open,setOpen]=useState(false)
  return (
    <div style={{ position:'relative' }}>
      <button type='button' onClick={()=>setOpen(o=>!o)} style={{ padding:'4px 8px', borderRadius:6, border:'1px solid #e5e7eb', background:'#fff' }}>
        Indicators ▾
      </button>
      {open && (
        <div style={{ position:'absolute', top:'calc(100% + 4px)', left:0, zIndex:40, background:'#fff', border:'1px solid #e5e7eb', borderRadius:6, boxShadow:'0 8px 20px rgba(0,0,0,0.08)', minWidth:180, padding:8 }}>
          {names.length===0 ? <div style={{ fontSize:12, color:'#6b7280' }}>No indicators</div> : names.map(n=> (
            <label key={n} style={{ display:'flex', alignItems:'center', gap:8, padding:'4px 2px', fontSize:13 }}>
              <input type='checkbox' checked={state?.[n] !== false} onChange={(e)=>onChange({ ...state, [n]: e.target.checked })} />
              <span>{n}</span>
            </label>
          ))}
        </div>
      )}
    </div>
  )
}
