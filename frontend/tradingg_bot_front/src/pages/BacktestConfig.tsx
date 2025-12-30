import React, { useEffect, useState } from 'react'
import { api } from '@/lib/api'
import { useUI } from '@/stores/ui'

export function BacktestConfig() {
  const notifySuccess = useUI(s => s.notifySuccess)
  const notifyError = useUI(s => s.notifyError)
  const [cfg, setCfg] = useState<any | null>(null)
  const [saving, setSaving] = useState(false)
  const [running, setRunning] = useState(false)
  const [timerange, setTimerange] = useState<string>("")
  const [exportTrades, setExportTrades] = useState<boolean>(true)
  const [strategy, setStrategy] = useState<string>("SupplyDemandStructureStrategyHTF_TrendV3")
  const [strategies, setStrategies] = useState<string[]>([])
  const [startDate, setStartDate] = useState<string>("")
  const [endDate, setEndDate] = useState<string>("")
  const [artifacts, setArtifacts] = useState<Array<{file:string; mtime:number; size:number}>>([])
  const [latestSummary, setLatestSummary] = useState<any | null>(null)
  const [latestTrades, setLatestTrades] = useState<any[]>([])
  const [logs, setLogs] = useState<string[]>([])

  const load = async () => {
    try {
      const res = await api.get('/config/backtest')
      setCfg(res.data)
    } catch (e: any) {
      notifyError(e?.response?.data?.detail || e?.message || 'Failed to load backtest config')
    }
  }

  useEffect(() => { load() }, [])

  useEffect(() => {
    // Load available strategies from isolated bt-userdir
    (async () => {
      try {
        const res = await api.get('/config/backtest/strategies')
        const list: string[] = res.data?.strategies || []
        setStrategies(list)
        if (list.length && !list.includes(strategy)) {
          setStrategy(list[0])
        }
      } catch (e: any) {
        // Non-fatal; keep manual entry
        console.warn('Failed to load strategies', e)
      }
    })()
  }, [])

  // Build timerange string when date pickers change
  useEffect(() => {
    const fmt = (s: string) => s ? s.split('-').join('') : ''
    if (startDate && endDate) {
      setTimerange(`${fmt(startDate)}-${fmt(endDate)}`)
    } else {
      setTimerange("")
    }
  }, [startDate, endDate])

  const updateField = (path: string[], value: any) => {
    setCfg((prev: any) => {
      const next = { ...(prev || {}) }
      let obj = next
      for (let i = 0; i < path.length - 1; i++) {
        const k = path[i]
        obj[k] = obj[k] || {}
        obj = obj[k]
      }
      obj[path[path.length - 1]] = value
      return next
    })
  }

  const save = async () => {
    setSaving(true)
    try {
      await api.put('/config/backtest', cfg)
      notifySuccess('Backtest config saved')
    } catch (e: any) {
      notifyError(e?.response?.data?.detail || e?.message || 'Failed to save backtest config')
    } finally {
      setSaving(false)
    }
  }

  const run = async () => {
    setRunning(true)
    try {
      const payload: any = {
        strategy,
        timerange: timerange || undefined,
        export_trades: exportTrades,
      }
      const res = await api.post('/config/backtest/run', payload)
      const exit = res.data?.exit_code
      if (exit === 0) {
        notifySuccess('Backtest completed successfully')
        // Capture artifacts, summary, trades, logs for UI
        const arts = Array.isArray(res.data?.artifacts) ? res.data.artifacts : []
        setArtifacts(arts)
        setLatestSummary(res.data?.latest_summary || null)
        setLatestTrades(Array.isArray(res.data?.latest_trades) ? res.data.latest_trades : [])
        const lines = Array.isArray(res.data?.logs?.lines) ? res.data.logs.lines : []
        setLogs(lines)
      } else {
        notifyError('Backtest finished with errors. See logs')
        console.error('Backtest error', res.data)
        const lines = Array.isArray(res.data?.logs?.lines) ? res.data.logs.lines : []
        setLogs(lines)
      }
    } catch (e: any) {
      notifyError(e?.response?.data?.detail || e?.message || 'Failed to run backtest')
    } finally {
      setRunning(false)
    }
  }

  if (!cfg) return <div style={{ padding: 16 }}>Loading…</div>

  const pairlist = cfg.pairlists?.[0]?.pair_whitelist || cfg.pairlist?.pair_whitelist || cfg.pair_whitelist || []
  const pairText = Array.isArray(pairlist) ? pairlist.join('\n') : ''

  return (
    <div style={{ padding: 16 }}>
      <h2>Isolated Backtest Configuration</h2>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <div>
          <label>Trading Mode</label>
          <select value={cfg.trading_mode || 'spot'} onChange={e => updateField(['trading_mode'], e.target.value)}>
            <option value="spot">Spot</option>
            <option value="futures">Futures</option>
          </select>
        </div>
        <div>
          <label>Timeframe</label>
          <input type="text" value={cfg.timeframe || ''} onChange={e => updateField(['timeframe'], e.target.value)} />
        </div>
        <div>
          <label>Stake Currency</label>
          <input type="text" value={cfg.stake_currency || ''} onChange={e => updateField(['stake_currency'], e.target.value)} />
        </div>
        <div>
          <label>Stake Amount</label>
          <input type="text" value={cfg.stake_amount || ''} onChange={e => updateField(['stake_amount'], e.target.value)} />
        </div>
        <div style={{ gridColumn: '1 / span 2' }}>
          <label>Pair Whitelist (one per line)</label>
          <textarea rows={6} value={pairText} onChange={e => {
            const lines = e.target.value.split(/\r?\n/).map(s => s.trim()).filter(Boolean)
            // update at all common locations to satisfy different versions
            updateField(['pair_whitelist'], lines)
            updateField(['pairlist'], { ...(cfg.pairlist || {}), method: 'StaticPairList', pair_whitelist: lines })
            const first = cfg.pairlists && cfg.pairlists.length ? cfg.pairlists[0] : { method: 'StaticPairList' }
            const rest = cfg.pairlists && cfg.pairlists.length > 1 ? cfg.pairlists.slice(1) : []
            const updated = [{ ...first, pair_whitelist: lines }, ...rest]
            updateField(['pairlists'], updated)
          }} />
        </div>
        <div>
          <label>Entry Pricing: use_order_book</label>
          <input type="checkbox" checked={cfg.entry_pricing?.use_order_book || false} onChange={e => updateField(['entry_pricing', 'use_order_book'], e.target.checked)} />
        </div>
        <div>
          <label>Exit Pricing: use_order_book</label>
          <input type="checkbox" checked={cfg.exit_pricing?.use_order_book || false} onChange={e => updateField(['exit_pricing', 'use_order_book'], e.target.checked)} />
        </div>
        <div>
          <label>Strategy Class</label>
          {strategies.length > 0 ? (
            <select value={strategy} onChange={e => setStrategy(e.target.value)}>
              {strategies.map(s => (<option key={s} value={s}>{s}</option>))}
            </select>
          ) : (
            <input type="text" value={strategy} onChange={e => setStrategy(e.target.value)} />
          )}
        </div>
        <div>
          <label>Start Date</label>
          <input type="date" value={startDate} onChange={e => setStartDate(e.target.value)} />
        </div>
        <div>
          <label>End Date</label>
          <input type="date" value={endDate} onChange={e => setEndDate(e.target.value)} />
        </div>
        <div>
          <label>Export trades</label>
          <input type="checkbox" checked={exportTrades} onChange={e => setExportTrades(e.target.checked)} />
        </div>
      </div>
      <div style={{ marginTop: 16 }}>
        <button onClick={save} disabled={saving} style={{ padding: '6px 12px', marginRight: 8 }}>{saving ? 'Saving…' : 'Save'}</button>
        <button onClick={run} disabled={running} style={{ padding: '6px 12px' }}>{running ? 'Running…' : 'Run Backtest'}</button>
      </div>

      {/* Results & Logs */}
      <div style={{ marginTop: 24, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <div>
          <h3 style={{ margin: '8px 0' }}>Latest Summary</h3>
          {latestSummary ? (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, fontSize: 14 }}>
              <div><strong>Total Trades:</strong> {latestSummary.total_trades ?? 0}</div>
              <div><strong>Winrate:</strong> {((latestSummary.winrate ?? 0) * 100).toFixed(2)}%</div>
              <div><strong>Profit (abs):</strong> {Number(latestSummary.profit_abs_sum ?? 0).toFixed(4)}</div>
              <div><strong>Avg Profit Ratio:</strong> {Number(latestSummary.profit_ratio_avg ?? 0).toFixed(4)}</div>
              <div><strong>Timeframe:</strong> {latestSummary.timeframe ?? '-'}</div>
              <div><strong>Timerange:</strong> {latestSummary.timerange ?? '-'}</div>
              <div style={{ gridColumn: '1 / span 2' }}><strong>File:</strong> {latestSummary.file ?? '-'}</div>
            </div>
          ) : (
            <div style={{ fontSize: 14, color: '#6b7280' }}>Run a backtest to see a summary.</div>
          )}

          <h3 style={{ margin: '16px 0 8px' }}>Artifacts</h3>
          {artifacts.length ? (
            <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
              {artifacts.map(a => (
                <li key={a.file} style={{ padding: '4px 6px', borderBottom: '1px solid #eee', fontSize: 13 }}>
                  <span style={{ fontWeight: 600 }}>{a.file}</span>
                  <span style={{ color: '#6b7280', marginLeft: 8 }}>size: {a.size}</span>
                </li>
              ))}
            </ul>
          ) : (
            <div style={{ fontSize: 13, color: '#6b7280' }}>No artifacts yet.</div>
          )}
        </div>

        <div>
          <h3 style={{ margin: '8px 0' }}>Logs</h3>
          <div style={{ border: '1px solid #e5e7eb', borderRadius: 6, padding: 8, height: 220, overflow: 'auto', background: '#f9fafb', fontSize: 12, whiteSpace: 'pre-wrap' }}>
            {logs.length ? logs.join('\n') : 'No logs available yet.'}
          </div>
        </div>
      </div>

      <div style={{ marginTop: 24 }}>
        <h3 style={{ margin: '8px 0' }}>Trades</h3>
        {latestTrades && latestTrades.length ? (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
              <thead>
                <tr>
                  {['pair','is_short','open_date','open_rate','close_date','close_rate','profit_ratio','profit_abs','exit_reason'].map(h => (
                    <th key={h} style={{ textAlign: 'left', padding: 6, borderBottom: '1px solid #e5e7eb' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {latestTrades.map((t, idx) => (
                  <tr key={idx}>
                    <td style={{ padding: 6, borderBottom: '1px solid #f1f5f9' }}>{t.pair}</td>
                    <td style={{ padding: 6, borderBottom: '1px solid #f1f5f9' }}>{t.is_short ? 'short' : 'long'}</td>
                    <td style={{ padding: 6, borderBottom: '1px solid #f1f5f9' }}>{t.open_date || t.open_timestamp}</td>
                    <td style={{ padding: 6, borderBottom: '1px solid #f1f5f9' }}>{t.open_rate}</td>
                    <td style={{ padding: 6, borderBottom: '1px solid #f1f5f9' }}>{t.close_date || t.close_timestamp}</td>
                    <td style={{ padding: 6, borderBottom: '1px solid #f1f5f9' }}>{t.close_rate}</td>
                    <td style={{ padding: 6, borderBottom: '1px solid #f1f5f9' }}>{(Number(t.profit_ratio || 0) * 100).toFixed(2)}%</td>
                    <td style={{ padding: 6, borderBottom: '1px solid #f1f5f9' }}>{Number(t.profit_abs || 0).toFixed(6)}</td>
                    <td style={{ padding: 6, borderBottom: '1px solid #f1f5f9' }}>{t.exit_reason || '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div style={{ fontSize: 13, color: '#6b7280' }}>No trades yet. Run a backtest to populate.</div>
        )}
      </div>
    </div>
  )
}
