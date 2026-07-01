import { useEffect, useState } from 'react'
import { useAuth } from '@/stores/auth'
import { scannerApi, ScannerConfig, CacheStatus, SchedulerStatus, ScannerRecentActivityEntry } from '@/lib/api'

const DEFAULT_WEIGHTS = {
  liquidity: 30,
  volatility: 25,
  spread: 25,
  funding: 10,
  tradeCount: 10,
  recentActivity: 0,
}

const DEFAULT_THRESHOLDS = {
  minQuoteVolume24h: 30000000,
  excellentQuoteVolume24h: 500000000,
  minAtrPct: 0.5,
  idealAtrPctLow: 1.0,
  idealAtrPctHigh: 3.0,
  maxAtrPct: 6.0,
  maxSpreadPct: 0.1,
  maxSpreadToAtrRatio: 0.1,
  normalFundingAbs: 0.0001,
  maxFundingAbs: 0.001
}

const DEFAULT_RECENT_ACTIVITY = {
  enabled: true,
  primaryWindow: '1h' as '1h' | '4h' | '1d',
  secondaryWindow: '4h' as '1h' | '4h' | '1d',
  use1d: true,
  staleAfterSeconds: 180,
}

const DEFAULT_RECENT_ACTIVITY_THRESHOLDS = {
  minQuoteVolume1h: 1000000,
  excellentQuoteVolume1h: 25000000,
  minQuoteVolume4h: 5000000,
  excellentQuoteVolume4h: 100000000,
  minQuoteVolume1d: 20000000,
  excellentQuoteVolume1d: 500000000,
  minTrades1h: 500,
  excellentTrades1h: 10000,
  minTrades4h: 1500,
  excellentTrades4h: 30000,
}

export function Scanners() {
  const userId = useAuth(s => s.userId)
  const [scanners, setScanners] = useState<ScannerConfig[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedScanner, setSelectedScanner] = useState<number | null>(null)
  const [showCreateForm, setShowCreateForm] = useState(false)
  const [outputs, setOutputs] = useState<any>(null)
  const [pairlist, setPairlist] = useState<any>(null)
  const [activityWindow, setActivityWindow] = useState<'1h' | '4h' | '1d'>('1h')
  const [recentActivityBySymbol, setRecentActivityBySymbol] = useState<Record<string, ScannerRecentActivityEntry>>({})
  
  // Form state
  const [formName, setFormName] = useState('')
  const [formExchange, setFormExchange] = useState('binance')
  const [formMarketType, setFormMarketType] = useState('futures')
  const [formEnabled, setFormEnabled] = useState(true)
  const [formInterval, setFormInterval] = useState(5)
  const [formQuoteAsset, setFormQuoteAsset] = useState('USDT')
  const [formMaxPairs, setFormMaxPairs] = useState(30)
  const [formMinScore, setFormMinScore] = useState(70)
  const [formExcludeSymbols, setFormExcludeSymbols] = useState('')
  const [formWeights, setFormWeights] = useState(DEFAULT_WEIGHTS)
  const [formThresholds, setFormThresholds] = useState(DEFAULT_THRESHOLDS)
  const [formRecentActivity, setFormRecentActivity] = useState(DEFAULT_RECENT_ACTIVITY)
  const [formRecentActivityThresholds, setFormRecentActivityThresholds] = useState(DEFAULT_RECENT_ACTIVITY_THRESHOLDS)
  const [cacheStatus, setCacheStatus] = useState<CacheStatus | null>(null)
  const [schedulerStatus, setSchedulerStatus] = useState<SchedulerStatus | null>(null)

  useEffect(() => {
    if (userId) {
      loadScanners()
      loadSystemStatus()
      // Auto-refresh system status every 10 seconds
      const interval = setInterval(loadSystemStatus, 10000)
      return () => clearInterval(interval)
    }
  }, [userId])

  const loadSystemStatus = async () => {
    try {
      const [cache, scheduler] = await Promise.all([
        scannerApi.getFetcherStatus(),
        scannerApi.getSchedulerStatus()
      ])
      setCacheStatus(cache)
      setSchedulerStatus(scheduler)
    } catch (error) {
      console.error('Failed to load system status:', error)
    }
  }

  const loadScanners = async () => {
    if (!userId) return
    try {
      setLoading(true)
      const data = await scannerApi.list(userId)
      setScanners(data)
    } catch (err) {
      console.error('Failed to load scanners:', err)
    } finally {
      setLoading(false)
    }
  }

  const loadScannerDetails = async (scannerId: number) => {
    if (!userId) return
    try {
      const [outputsData, pairlistData] = await Promise.all([
        scannerApi.getOutputs(userId, scannerId).catch(() => ({ outputs: [] })),
        scannerApi.getPairlist(userId, scannerId).catch(() => ({ pairs: [] }))
      ])
      setOutputs(outputsData)
      setPairlist(pairlistData)

      const outputSymbols = (outputsData?.outputs || []).map((o: any) => String(o.symbol || '').toUpperCase()).filter(Boolean)
      if (outputSymbols.length > 0) {
        const activityData = await scannerApi
          .getRecentActivity(userId, scannerId, activityWindow, outputSymbols)
          .catch(() => ({ by_symbol: {} } as any))
        setRecentActivityBySymbol(activityData.by_symbol || {})
      } else {
        setRecentActivityBySymbol({})
      }
    } catch (err) {
      console.error('Failed to load scanner details:', err)
    }
  }

  const loadRecentActivity = async (scannerId: number, symbols: string[]) => {
    if (!userId) return
    try {
      if (symbols.length === 0) {
        setRecentActivityBySymbol({})
        return
      }
      const activityData = await scannerApi.getRecentActivity(userId, scannerId, activityWindow, symbols)
      setRecentActivityBySymbol(activityData.by_symbol || {})
    } catch (err) {
      console.error('Failed to load recent activity:', err)
      setRecentActivityBySymbol({})
    }
  }

  const handleSelectScanner = (scannerId: number) => {
    setSelectedScanner(scannerId)
    setOutputs(null)
    setPairlist(null)
    setRecentActivityBySymbol({})
    // Load scanner configuration into form immediately
    const scanner = scanners.find(s => s.id === scannerId)
    if (scanner) {
      loadScannerToForm(scanner)
    }
    loadScannerDetails(scannerId)
  }

  const resetForm = () => {
    setFormName('')
    setFormExchange('binance')
    setFormMarketType('futures')
    setFormEnabled(true)
    setFormInterval(5)
    setFormQuoteAsset('USDT')
    setFormMaxPairs(30)
    setFormMinScore(70)
    setFormExcludeSymbols('')
    setFormWeights(DEFAULT_WEIGHTS)
    setFormThresholds(DEFAULT_THRESHOLDS)
    setFormRecentActivity(DEFAULT_RECENT_ACTIVITY)
    setFormRecentActivityThresholds(DEFAULT_RECENT_ACTIVITY_THRESHOLDS)
  }

  const loadScannerToForm = (scanner: ScannerConfig) => {
    setFormName(scanner.name)
    setFormExchange(scanner.exchange)
    setFormMarketType(scanner.market_type)
    setFormEnabled(scanner.enabled)
    setFormInterval(scanner.interval_minutes)
    setFormQuoteAsset(scanner.quote_asset)
    setFormMaxPairs(scanner.max_pairs)
    setFormMinScore(scanner.min_market_score)
    setFormExcludeSymbols(scanner.exclude_symbols.join(', '))
    setFormWeights({ ...DEFAULT_WEIGHTS, ...scanner.scoring_weights })
    setFormThresholds({ ...DEFAULT_THRESHOLDS, ...scanner.scoring_thresholds })
    setFormRecentActivity({ ...DEFAULT_RECENT_ACTIVITY, ...(scanner.recent_activity || {}) })
    setFormRecentActivityThresholds({ ...DEFAULT_RECENT_ACTIVITY_THRESHOLDS, ...(scanner.recent_activity_thresholds || {}) })
  }

  const handleCreate = async () => {
    if (!userId || !formName.trim()) return
    try {
      const config = {
        name: formName.trim(),
        exchange: formExchange,
        market_type: formMarketType,
        enabled: formEnabled,
        interval_minutes: formInterval,
        quote_asset: formQuoteAsset,
        max_pairs: formMaxPairs,
        min_market_score: formMinScore,
        include_symbols: [],
        exclude_symbols: formExcludeSymbols.split(',').map(s => s.trim()).filter(Boolean),
        scoring_weights: formWeights,
        scoring_thresholds: formThresholds,
        recent_activity: formRecentActivity,
        recent_activity_thresholds: formRecentActivityThresholds,
      }
      console.log('[DEBUG] Sending create config:', config)
      console.log('[DEBUG] recent_activity:', config.recent_activity)
      await scannerApi.create(userId, config)
      await loadScanners()
      setShowCreateForm(false)
      resetForm()
    } catch (err: any) {
      alert(`Failed to create scanner: ${err.response?.data?.detail || err.message}`)
    }
  }

  const handleUpdate = async () => {
    if (!userId || !selectedScanner) return
    try {
      const config = {
        name: formName.trim(),
        exchange: formExchange,
        market_type: formMarketType,
        enabled: formEnabled,
        interval_minutes: formInterval,
        quote_asset: formQuoteAsset,
        max_pairs: formMaxPairs,
        min_market_score: formMinScore,
        exclude_symbols: formExcludeSymbols.split(',').map(s => s.trim()).filter(Boolean),
        scoring_weights: formWeights,
        scoring_thresholds: formThresholds,
        recent_activity: formRecentActivity,
        recent_activity_thresholds: formRecentActivityThresholds,
      }
      console.log('[DEBUG] Sending update config:', config)
      console.log('[DEBUG] recent_activity:', config.recent_activity)
      await scannerApi.update(userId, selectedScanner, config)
      await loadScanners()
      alert('Scanner updated successfully!')
    } catch (err: any) {
      alert(`Failed to update scanner: ${err.response?.data?.detail || err.message}`)
    }
  }

  const handleDelete = async (scannerId: number) => {
    if (!userId) return
    if (!confirm('Are you sure you want to delete this scanner?')) return
    try {
      await scannerApi.delete(userId, scannerId)
      await loadScanners()
      if (selectedScanner === scannerId) {
        setSelectedScanner(null)
        setOutputs(null)
        setPairlist(null)
      }
    } catch (err: any) {
      alert(`Failed to delete scanner: ${err.response?.data?.detail || err.message}`)
    }
  }

  const handleRunNow = async (scannerId: number) => {
    if (!userId) return
    try {
      const result = await scannerApi.runNow(userId, scannerId)
      // Backend returns: outputSymbols, symbolsProcessed (camelCase)
      const outputCount = result.outputSymbols || result.symbolsProcessed || 0
      alert(`Scanner run completed: ${outputCount} top symbols selected`)
      // Refresh scanner list to update last_run_at timestamp
      await loadScanners()
      if (selectedScanner === scannerId) {
        loadScannerDetails(scannerId)
      }
    } catch (err: any) {
      alert(`Failed to run scanner: ${err.response?.data?.detail || err.message}`)
    }
  }

  const selectedScannerData = scanners.find(s => s.id === selectedScanner)

  useEffect(() => {
    if (!selectedScanner || !outputs?.outputs || outputs.outputs.length === 0) return
    const symbols = outputs.outputs.map((o: any) => String(o.symbol || '').toUpperCase()).filter(Boolean)
    loadRecentActivity(selectedScanner, symbols)
  }, [activityWindow, selectedScanner])

  const formatAge = (seconds: number | null) => {
    if (seconds === null) return 'N/A'
    if (seconds < 60) return `${seconds}s ago`
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
    return `${Math.floor(seconds / 3600)}h ago`
  }

  return (
    <div style={{ padding: 24, maxWidth: 1800, margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <h1 style={{ margin: 0 }}>Market Scanners</h1>
        <button 
          onClick={() => { 
            resetForm()
            setShowCreateForm(true)
            setSelectedScanner(null)
          }} 
          style={{ padding: '8px 16px', borderRadius: 6, border: '1px solid #2563eb', background: '#2563eb', color: '#fff', cursor: 'pointer' }}
        >
          Create Scanner
        </button>
      </div>

      {/* System Status Bar */}
      {(cacheStatus || schedulerStatus) && (
        <div style={{ 
          background: '#1a1a2e', 
          padding: '12px 16px', 
          marginBottom: '20px', 
          borderRadius: '8px',
          display: 'flex',
          gap: '24px',
          fontSize: '13px',
          color: '#a0a0b0'
        }}>
          {cacheStatus && (
            <div style={{ display: 'flex', gap: '16px', flex: 1 }}>
              <div>
                <strong style={{ color: '#fff' }}>Market Data Cache:</strong>
                <span style={{ marginLeft: '8px', color: cacheStatus.cache.latest_timestamp ? '#4ade80' : '#ef4444' }}>
                  {cacheStatus.cache.latest_timestamp ? '● Active' : '● Waiting'}
                </span>
              </div>
              {cacheStatus.cache.latest_timestamp && (
                <>
                  <div>
                    <strong>Last Update:</strong> {formatAge(cacheStatus.cache.age_seconds)}
                  </div>
                  <div>
                    <strong>Symbols:</strong> {Math.floor(cacheStatus.cache.total_entries / (cacheStatus.cache.cache_snapshots || 1))}
                  </div>
                  <div>
                    <strong>Interval:</strong> {cacheStatus.fetch_interval_minutes}m
                  </div>
                  {typeof cacheStatus.futures_symbols === 'number' && typeof cacheStatus.spot_symbols === 'number' && (
                    <div>
                      <strong>Futures/Spot:</strong> {cacheStatus.futures_symbols}/{cacheStatus.spot_symbols}
                    </div>
                  )}
                  {typeof cacheStatus.kline_stream_symbols === 'number' && (
                    <div>
                      <strong>Kline Universe:</strong> {cacheStatus.kline_stream_symbols}
                    </div>
                  )}
                  {typeof cacheStatus.ws_connections === 'number' && (
                    <div>
                      <strong>WS Conns:</strong> {cacheStatus.ws_connections}
                    </div>
                  )}
                  {typeof cacheStatus.reconnect_count === 'number' && (
                    <div>
                      <strong>Reconnects:</strong> {cacheStatus.reconnect_count}
                    </div>
                  )}
                  {cacheStatus.recent_activity && (
                    <div>
                      <strong>Recent Activity:</strong> {cacheStatus.recent_activity.windows.join('/')} · {cacheStatus.recent_activity.sourcePreference} · {cacheStatus.recent_activity.allowRestFallback ? 'REST fallback on' : 'REST fallback off'}
                    </div>
                  )}
                </>
              )}
              {cacheStatus.last_error && (
                <div style={{ color: '#ef4444' }}>
                  <strong>Error:</strong> {cacheStatus.last_error.substring(0, 50)}...
                </div>
              )}
            </div>
          )}
          {schedulerStatus && (
            <div style={{ display: 'flex', gap: '16px' }}>
              <div>
                <strong style={{ color: '#fff' }}>Scheduler:</strong>
                <span style={{ marginLeft: '8px', color: schedulerStatus.running ? '#4ade80' : '#ef4444' }}>
                  {schedulerStatus.running ? '● Running' : '● Stopped'}
                </span>
              </div>
              <div>
                <strong>Active:</strong> {schedulerStatus.active_scanners} scanner{schedulerStatus.active_scanners !== 1 ? 's' : ''}
              </div>
            </div>
          )}
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '300px 1fr', gap: 24 }}>
        {/* Scanner List */}
        <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8, padding: 16, height: 'fit-content' }}>
          <h3 style={{ margin: '0 0 16px 0', fontSize: 16 }}>Your Scanners</h3>
          {loading ? (
            <div>Loading...</div>
          ) : scanners.length === 0 ? (
            <div style={{ color: '#6b7280', fontSize: 14 }}>No scanners yet. Create one to get started.</div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {scanners.map(scanner => {
                const lastRunAge = scanner.last_run_at 
                  ? Math.floor(Date.now() / 1000) - scanner.last_run_at 
                  : null
                return (
                  <div 
                    key={scanner.id}
                    onClick={() => {
                      handleSelectScanner(scanner.id!)
                      setShowCreateForm(false)
                    }}
                    style={{
                      padding: 12,
                      border: selectedScanner === scanner.id ? '2px solid #2563eb' : '1px solid #e5e7eb',
                      borderRadius: 6,
                      cursor: 'pointer',
                      background: selectedScanner === scanner.id ? '#eff6ff' : '#fff'
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                      <div style={{ flex: 1 }}>
                        <div style={{ fontWeight: 600, fontSize: 14 }}>{scanner.name}</div>
                        <div style={{ fontSize: 11, color: '#6b7280', marginTop: 2 }}>
                          {scanner.exchange} · {scanner.market_type}
                        </div>
                        {lastRunAge !== null && (
                          <div style={{ fontSize: 10, color: '#9ca3af', marginTop: 4 }}>
                            Last run: {formatAge(lastRunAge)}
                          </div>
                        )}
                        {lastRunAge === null && (
                          <div style={{ fontSize: 10, color: '#f59e0b', marginTop: 4 }}>
                            Never run
                          </div>
                        )}
                      </div>
                      <div style={{
                        width: 8,
                        height: 8,
                        borderRadius: '50%',
                        background: scanner.enabled ? '#10b981' : '#ef4444',
                        flexShrink: 0,
                        marginTop: 4
                      }} />
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* Main Content */}
        <div>
          {showCreateForm ? (
            <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8, padding: 24 }}>
              <h2 style={{ margin: '0 0 24px 0' }}>Create New Scanner</h2>
              <ScannerForm
                formName={formName}
                setFormName={setFormName}
                formExchange={formExchange}
                setFormExchange={setFormExchange}
                formMarketType={formMarketType}
                setFormMarketType={setFormMarketType}
                formEnabled={formEnabled}
                setFormEnabled={setFormEnabled}
                formInterval={formInterval}
                setFormInterval={setFormInterval}
                formQuoteAsset={formQuoteAsset}
                setFormQuoteAsset={setFormQuoteAsset}
                formMaxPairs={formMaxPairs}
                setFormMaxPairs={setFormMaxPairs}
                formMinScore={formMinScore}
                setFormMinScore={setFormMinScore}
                formExcludeSymbols={formExcludeSymbols}
                setFormExcludeSymbols={setFormExcludeSymbols}
                formWeights={formWeights}
                setFormWeights={setFormWeights}
                formThresholds={formThresholds}
                setFormThresholds={setFormThresholds}
                formRecentActivity={formRecentActivity}
                setFormRecentActivity={setFormRecentActivity}
                formRecentActivityThresholds={formRecentActivityThresholds}
                setFormRecentActivityThresholds={setFormRecentActivityThresholds}
                onSubmit={handleCreate}
                onCancel={() => {
                  setShowCreateForm(false)
                  resetForm()
                }}
                submitLabel="Create Scanner"
              />
            </div>
          ) : selectedScannerData ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
              {/* Scanner Details */}
              <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8, padding: 24 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
                  <div>
                    <h2 style={{ margin: 0, fontSize: 20 }}>{selectedScannerData.name}</h2>
                    <p style={{ margin: '4px 0 0 0', fontSize: 13, color: '#6b7280' }}>
                      Scanner Configuration · {selectedScannerData.exchange} · {selectedScannerData.market_type}
                    </p>
                  </div>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button
                      onClick={() => handleRunNow(selectedScannerData.id!)}
                      style={{ padding: '6px 12px', borderRadius: 6, border: '1px solid #10b981', background: '#10b981', color: '#fff', cursor: 'pointer' }}
                    >
                      Run Now
                    </button>
                    <button
                      onClick={() => handleDelete(selectedScannerData.id!)}
                      style={{ padding: '6px 12px', borderRadius: 6, border: '1px solid #ef4444', background: '#fff', color: '#ef4444', cursor: 'pointer' }}
                    >
                      Delete
                    </button>
                  </div>
                </div>

                <ScannerForm
                  formName={formName}
                  setFormName={setFormName}
                  formExchange={formExchange}
                  setFormExchange={setFormExchange}
                  formMarketType={formMarketType}
                  setFormMarketType={setFormMarketType}
                  formEnabled={formEnabled}
                  setFormEnabled={setFormEnabled}
                  formInterval={formInterval}
                  setFormInterval={setFormInterval}
                  formQuoteAsset={formQuoteAsset}
                  setFormQuoteAsset={setFormQuoteAsset}
                  formMaxPairs={formMaxPairs}
                  setFormMaxPairs={setFormMaxPairs}
                  formMinScore={formMinScore}
                  setFormMinScore={setFormMinScore}
                  formExcludeSymbols={formExcludeSymbols}
                  setFormExcludeSymbols={setFormExcludeSymbols}
                  formWeights={formWeights}
                  setFormWeights={setFormWeights}
                  formThresholds={formThresholds}
                  setFormThresholds={setFormThresholds}
                  formRecentActivity={formRecentActivity}
                  setFormRecentActivity={setFormRecentActivity}
                  formRecentActivityThresholds={formRecentActivityThresholds}
                  setFormRecentActivityThresholds={setFormRecentActivityThresholds}
                  onSubmit={handleUpdate}
                  onCancel={() => loadScannerToForm(selectedScannerData)}
                  submitLabel="Update Scanner"
                />
              </div>

              {/* Scanner Outputs */}
              {outputs && outputs.outputs && outputs.outputs.length > 0 && (
                <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8, padding: 24 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                    <h3 style={{ margin: 0 }}>Top Symbols ({outputs.count} selected)</h3>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <label style={{ fontSize: 12, color: '#6b7280' }}>Activity Window</label>
                        <select
                          value={activityWindow}
                          onChange={e => setActivityWindow(e.target.value as '1h' | '4h' | '1d')}
                          style={{ fontSize: 12, padding: '4px 8px', borderRadius: 6, border: '1px solid #d1d5db' }}
                        >
                          <option value="1h">1h</option>
                          <option value="4h">4h</option>
                          <option value="1d">1d</option>
                        </select>
                      </div>
                      {outputs.generated_at && (
                        <span style={{ fontSize: 12, color: '#6b7280' }}>
                          Last updated: {formatAge(Math.floor(Date.now() / 1000) - outputs.generated_at)}
                        </span>
                      )}
                    </div>
                  </div>
                  <div style={{ overflowX: 'auto' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                      <thead>
                        <tr style={{ borderBottom: '2px solid #e5e7eb', background: '#f9fafb' }}>
                          <th style={{ padding: '10px 8px', textAlign: 'left' }}>Rank</th>
                          <th style={{ padding: '10px 8px', textAlign: 'left' }}>Symbol</th>
                          <th style={{ padding: '10px 8px', textAlign: 'right' }}>Activity {activityWindow}</th>
                          <th style={{ padding: '10px 8px', textAlign: 'left' }}>Hard Filters</th>
                          <th style={{ padding: '10px 8px', textAlign: 'right' }}>Score</th>
                          <th style={{ padding: '10px 8px', textAlign: 'right' }}>Price</th>
                          <th style={{ padding: '10px 8px', textAlign: 'right' }}>Volume 24h</th>
                          <th style={{ padding: '10px 8px', textAlign: 'right' }}>ATR%</th>
                          <th style={{ padding: '10px 8px', textAlign: 'right' }}>Spread%</th>
                          <th style={{ padding: '10px 8px', textAlign: 'right' }}>Funding%</th>
                        </tr>
                      </thead>
                      <tbody>
                        {outputs.outputs.map((output: any) => {
                          const activity = recentActivityBySymbol[String(output.symbol || '').toUpperCase()]
                          const qv = activity?.quote_volume
                          const tc = activity?.trade_count
                          const stale = activity?.stale
                          return (
                          <tr key={output.id} style={{ borderBottom: '1px solid #f3f4f6' }}>
                            <td style={{ padding: 8, color: '#6b7280', fontSize: 12 }}>#{output.rank}</td>
                            <td style={{ padding: 8, fontWeight: 600, color: '#111827' }}>{output.symbol}</td>
                            <td style={{ padding: 8, textAlign: 'right', fontFamily: 'monospace', fontSize: 12 }}>
                              {qv != null || tc != null ? (
                                <span title={activity?.mode ? `mode=${activity.mode}` : undefined} style={{ color: stale ? '#b45309' : '#111827' }}>
                                  {(qv != null ? '$' + (qv / 1000000).toFixed(1) + 'M' : 'N/A')} · {(tc != null ? tc.toLocaleString() : 'N/A')}
                                  {stale ? ' (stale)' : ''}
                                </span>
                              ) : (
                                <span style={{ color: '#9ca3af' }}>N/A</span>
                              )}
                            </td>
                            <td style={{ padding: 8 }}>
                              <span
                                title={output.reasons?.hard_filters || 'No hard filter details'}
                                style={{
                                  padding: '3px 8px',
                                  borderRadius: 4,
                                  background: '#d1fae5',
                                  color: '#065f46',
                                  fontSize: 11,
                                  fontWeight: 600
                                }}
                              >
                                PASS
                              </span>
                            </td>
                            <td style={{ padding: 8, textAlign: 'right' }}>
                              <span style={{
                                padding: '3px 10px',
                                borderRadius: 4,
                                background: output.total_score >= 80 ? '#d1fae5' : output.total_score >= 60 ? '#fef3c7' : '#fee2e2',
                                color: output.total_score >= 80 ? '#065f46' : output.total_score >= 60 ? '#92400e' : '#991b1b',
                                fontSize: 12,
                                fontWeight: 600
                              }}>
                                {output.total_score}
                              </span>
                            </td>
                            <td style={{ padding: 8, textAlign: 'right', fontFamily: 'monospace' }}>${output.price?.toFixed(4)}</td>
                            <td style={{ padding: 8, textAlign: 'right', fontFamily: 'monospace' }}>${(output.volume / 1000000).toFixed(1)}M</td>
                            <td style={{ padding: 8, textAlign: 'right', fontFamily: 'monospace', color: output.atr > 3 ? '#dc2626' : '#059669' }}>{output.atr?.toFixed(2)}%</td>
                            <td style={{ padding: 8, textAlign: 'right', fontFamily: 'monospace', color: output.spread > 0.05 ? '#dc2626' : '#059669' }}>{output.spread?.toFixed(4)}%</td>
                            <td style={{ padding: 8, textAlign: 'right', fontFamily: 'monospace' }}>{output.funding ? (output.funding * 100).toFixed(4) + '%' : 'N/A'}</td>
                          </tr>
                        )})}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Pairlist for Bots */}
              {pairlist && pairlist.pairs && pairlist.pairs.length > 0 && (
                <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8, padding: 24 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                    <h3 style={{ margin: 0 }}>Trading Pairs ({pairlist.pairs.length})</h3>
                    <span style={{ fontSize: 12, color: '#6b7280' }}>For use with Freqtrade RemotePairList</span>
                  </div>
                  <div style={{ 
                    maxHeight: 200, 
                    overflow: 'auto', 
                    background: '#f9fafb', 
                    padding: 12, 
                    borderRadius: 6,
                    fontSize: 13,
                    fontFamily: 'monospace',
                    border: '1px solid #e5e7eb'
                  }}>
                    {pairlist.pairs.join(', ')}
                  </div>
                </div>
              )}

              {/* Empty State */}
              {(!outputs || !outputs.outputs || outputs.outputs.length === 0) && (
                <div style={{ 
                  background: '#fff', 
                  border: '1px solid #e5e7eb', 
                  borderRadius: 8, 
                  padding: 48, 
                  textAlign: 'center',
                  color: '#6b7280'
                }}>
                  <div style={{ fontSize: 48, marginBottom: 16 }}>📈</div>
                  <div style={{ fontSize: 16, marginBottom: 8 }}>No results yet</div>
                  <div style={{ fontSize: 14 }}>Click "Run Now" to scan the market</div>
                </div>
              )}
            </div>
          ) : (
            <div style={{ 
              background: '#fff', 
              border: '1px solid #e5e7eb', 
              borderRadius: 8, 
              padding: 48, 
              textAlign: 'center',
              color: '#6b7280'
            }}>
              <div style={{ fontSize: 48, marginBottom: 16 }}>📊</div>
              <div style={{ fontSize: 16 }}>Select a scanner or create a new one</div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

interface ScannerFormProps {
  formName: string
  setFormName: (v: string) => void
  formExchange: string
  setFormExchange: (v: string) => void
  formMarketType: string
  setFormMarketType: (v: string) => void
  formEnabled: boolean
  setFormEnabled: (v: boolean) => void
  formInterval: number
  setFormInterval: (v: number) => void
  formQuoteAsset: string
  setFormQuoteAsset: (v: string) => void
  formMaxPairs: number
  setFormMaxPairs: (v: number) => void
  formMinScore: number
  setFormMinScore: (v: number) => void
  formExcludeSymbols: string
  setFormExcludeSymbols: (v: string) => void
  formWeights: typeof DEFAULT_WEIGHTS
  setFormWeights: (v: typeof DEFAULT_WEIGHTS) => void
  formThresholds: typeof DEFAULT_THRESHOLDS
  setFormThresholds: (v: typeof DEFAULT_THRESHOLDS) => void
  formRecentActivity: typeof DEFAULT_RECENT_ACTIVITY
  setFormRecentActivity: (v: typeof DEFAULT_RECENT_ACTIVITY) => void
  formRecentActivityThresholds: typeof DEFAULT_RECENT_ACTIVITY_THRESHOLDS
  setFormRecentActivityThresholds: (v: typeof DEFAULT_RECENT_ACTIVITY_THRESHOLDS) => void
  onSubmit: () => void
  onCancel: () => void
  submitLabel: string
}

function ScannerForm(props: ScannerFormProps) {
  const {
    formName, setFormName,
    formExchange, setFormExchange,
    formMarketType, setFormMarketType,
    formEnabled, setFormEnabled,
    formInterval, setFormInterval,
    formQuoteAsset, setFormQuoteAsset,
    formMaxPairs, setFormMaxPairs,
    formMinScore, setFormMinScore,
    formExcludeSymbols, setFormExcludeSymbols,
    formWeights, setFormWeights,
    formThresholds, setFormThresholds,
    formRecentActivity, setFormRecentActivity,
    formRecentActivityThresholds, setFormRecentActivityThresholds,
    onSubmit, onCancel, submitLabel
  } = props

  const totalWeight =
    Number(formWeights.liquidity || 0) +
    Number(formWeights.volatility || 0) +
    Number(formWeights.spread || 0) +
    Number(formWeights.funding || 0) +
    Number(formWeights.tradeCount || 0) +
    Number(formWeights.recentActivity || 0)

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
      <div>
        <label style={{ display: 'block', fontSize: 12, marginBottom: 4, fontWeight: 600 }}>Scanner Name *</label>
        <input 
          value={formName} 
          onChange={e => setFormName(e.target.value)}
          placeholder="e.g., aggressive-scalper"
          style={{ width: '100%', padding: 8, border: '1px solid #e5e7eb', borderRadius: 6 }}
        />
      </div>

      <div>
        <label style={{ display: 'block', fontSize: 12, marginBottom: 4, fontWeight: 600 }}>Exchange</label>
        <select 
          value={formExchange} 
          onChange={e => setFormExchange(e.target.value)}
          style={{ width: '100%', padding: 8, border: '1px solid #e5e7eb', borderRadius: 6 }}
        >
          <option value="binance">Binance</option>
          <option value="bybit">Bybit</option>
        </select>
      </div>

      <div>
        <label style={{ display: 'block', fontSize: 12, marginBottom: 4, fontWeight: 600 }}>Market Type</label>
        <select 
          value={formMarketType} 
          onChange={e => setFormMarketType(e.target.value)}
          style={{ width: '100%', padding: 8, border: '1px solid #e5e7eb', borderRadius: 6 }}
        >
          <option value="futures">Futures</option>
          <option value="spot">Spot</option>
        </select>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <input 
          type="checkbox" 
          checked={formEnabled} 
          onChange={e => setFormEnabled(e.target.checked)}
        />
        <label style={{ fontSize: 12, fontWeight: 600 }}>Enabled</label>
      </div>

      <div>
        <label style={{ display: 'block', fontSize: 12, marginBottom: 4, fontWeight: 600 }}>Scan Interval (minutes)</label>
        <input 
          type="number" 
          value={formInterval} 
          onChange={e => setFormInterval(Number(e.target.value))}
          min={1}
          style={{ width: '100%', padding: 8, border: '1px solid #e5e7eb', borderRadius: 6 }}
        />
      </div>

      <div>
        <label style={{ display: 'block', fontSize: 12, marginBottom: 4, fontWeight: 600 }}>Quote Asset</label>
        <input 
          value={formQuoteAsset} 
          onChange={e => setFormQuoteAsset(e.target.value)}
          style={{ width: '100%', padding: 8, border: '1px solid #e5e7eb', borderRadius: 6 }}
        />
      </div>

      <div>
        <label style={{ display: 'block', fontSize: 12, marginBottom: 4, fontWeight: 600 }}>Max Pairs</label>
        <input 
          type="number" 
          value={formMaxPairs} 
          onChange={e => setFormMaxPairs(Number(e.target.value))}
          min={1}
          max={500}
          style={{ width: '100%', padding: 8, border: '1px solid #e5e7eb', borderRadius: 6 }}
        />
      </div>

      <div>
        <label style={{ display: 'block', fontSize: 12, marginBottom: 4, fontWeight: 600 }}>Min Market Score</label>
        <input 
          type="number" 
          value={formMinScore} 
          onChange={e => setFormMinScore(Number(e.target.value))}
          min={0}
          max={100}
          style={{ width: '100%', padding: 8, border: '1px solid #e5e7eb', borderRadius: 6 }}
        />
      </div>

      <div style={{ gridColumn: '1 / -1' }}>
        <label style={{ display: 'block', fontSize: 12, marginBottom: 4, fontWeight: 600 }}>Exclude Symbols (comma-separated)</label>
        <input 
          value={formExcludeSymbols} 
          onChange={e => setFormExcludeSymbols(e.target.value)}
          placeholder="e.g., BTCSTUSDT, 1000PEPEUSDT"
          style={{ width: '100%', padding: 8, border: '1px solid #e5e7eb', borderRadius: 6 }}
        />
      </div>

      {/* Scoring Weights */}
      <div style={{ gridColumn: '1 / -1', marginTop: 16 }}>
        <h4 style={{ margin: '0 0 12px 0', fontSize: 14 }}>Scoring Weights</h4>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 }}>
          <div>
            <label style={{ fontSize: 11 }}>Liquidity</label>
            <input 
              type="number" 
              value={formWeights.liquidity} 
              onChange={e => setFormWeights({...formWeights, liquidity: Number(e.target.value)})}
              min={0}
              max={100}
              style={{ width: '100%', padding: 6, border: '1px solid #e5e7eb', borderRadius: 4, fontSize: 13 }}
            />
          </div>
          <div>
            <label style={{ fontSize: 11 }}>Volatility</label>
            <input 
              type="number" 
              value={formWeights.volatility} 
              onChange={e => setFormWeights({...formWeights, volatility: Number(e.target.value)})}
              min={0}
              max={100}
              style={{ width: '100%', padding: 6, border: '1px solid #e5e7eb', borderRadius: 4, fontSize: 13 }}
            />
          </div>
          <div>
            <label style={{ fontSize: 11 }}>Spread</label>
            <input 
              type="number" 
              value={formWeights.spread} 
              onChange={e => setFormWeights({...formWeights, spread: Number(e.target.value)})}
              min={0}
              max={100}
              style={{ width: '100%', padding: 6, border: '1px solid #e5e7eb', borderRadius: 4, fontSize: 13 }}
            />
          </div>
          <div>
            <label style={{ fontSize: 11 }}>Funding</label>
            <input 
              type="number" 
              value={formWeights.funding} 
              onChange={e => setFormWeights({...formWeights, funding: Number(e.target.value)})}
              min={0}
              max={100}
              style={{ width: '100%', padding: 6, border: '1px solid #e5e7eb', borderRadius: 4, fontSize: 13 }}
            />
          </div>
          <div>
            <label style={{ fontSize: 11 }}>Precision (tradeCount compat)</label>
            <input 
              type="number" 
              value={formWeights.tradeCount} 
              onChange={e => setFormWeights({...formWeights, tradeCount: Number(e.target.value)})}
              min={0}
              max={100}
              style={{ width: '100%', padding: 6, border: '1px solid #e5e7eb', borderRadius: 4, fontSize: 13 }}
            />
          </div>
          <div>
            <label style={{ fontSize: 11 }}>Recent Activity</label>
            <input
              type="number"
              value={formWeights.recentActivity}
              onChange={e => setFormWeights({...formWeights, recentActivity: Number(e.target.value)})}
              min={0}
              max={100}
              style={{ width: '100%', padding: 6, border: '1px solid #e5e7eb', borderRadius: 4, fontSize: 13 }}
            />
          </div>
        </div>
        <div style={{ marginTop: 8, fontSize: 12, color: totalWeight > 100 ? '#b45309' : '#6b7280' }}>
          Total weight: {totalWeight}{totalWeight > 100 ? ' (over 100: backend logs warning, no auto-normalization)' : ''}
        </div>
      </div>

      {/* Scoring Thresholds */}
      <div style={{ gridColumn: '1 / -1', marginTop: 16 }}>
        <h4 style={{ margin: '0 0 12px 0', fontSize: 14 }}>Scoring Thresholds</h4>
        <p style={{ margin: '0 0 10px 0', fontSize: 12, color: '#6b7280' }}>
          Funding thresholds use decimal units (example: 0.0001 = 0.01%).
        </p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 }}>
          <div>
            <label style={{ fontSize: 11 }}>Min Quote Volume 24h</label>
            <input 
              type="number" 
              value={formThresholds.minQuoteVolume24h} 
              onChange={e => setFormThresholds({...formThresholds, minQuoteVolume24h: Number(e.target.value)})}
              style={{ width: '100%', padding: 6, border: '1px solid #e5e7eb', borderRadius: 4, fontSize: 13 }}
            />
          </div>
          <div>
            <label style={{ fontSize: 11 }}>Excellent Quote Volume 24h</label>
            <input 
              type="number" 
              value={formThresholds.excellentQuoteVolume24h} 
              onChange={e => setFormThresholds({...formThresholds, excellentQuoteVolume24h: Number(e.target.value)})}
              style={{ width: '100%', padding: 6, border: '1px solid #e5e7eb', borderRadius: 4, fontSize: 13 }}
            />
          </div>
          <div>
            <label style={{ fontSize: 11 }}>Min ATR %</label>
            <input 
              type="number" 
              step="0.1"
              value={formThresholds.minAtrPct} 
              onChange={e => setFormThresholds({...formThresholds, minAtrPct: Number(e.target.value)})}
              style={{ width: '100%', padding: 6, border: '1px solid #e5e7eb', borderRadius: 4, fontSize: 13 }}
            />
          </div>
          <div>
            <label style={{ fontSize: 11 }}>Ideal ATR % Low</label>
            <input 
              type="number" 
              step="0.1"
              value={formThresholds.idealAtrPctLow} 
              onChange={e => setFormThresholds({...formThresholds, idealAtrPctLow: Number(e.target.value)})}
              style={{ width: '100%', padding: 6, border: '1px solid #e5e7eb', borderRadius: 4, fontSize: 13 }}
            />
          </div>
          <div>
            <label style={{ fontSize: 11 }}>Ideal ATR % High</label>
            <input 
              type="number" 
              step="0.1"
              value={formThresholds.idealAtrPctHigh} 
              onChange={e => setFormThresholds({...formThresholds, idealAtrPctHigh: Number(e.target.value)})}
              style={{ width: '100%', padding: 6, border: '1px solid #e5e7eb', borderRadius: 4, fontSize: 13 }}
            />
          </div>
          <div>
            <label style={{ fontSize: 11 }}>Max ATR %</label>
            <input 
              type="number" 
              step="0.1"
              value={formThresholds.maxAtrPct} 
              onChange={e => setFormThresholds({...formThresholds, maxAtrPct: Number(e.target.value)})}
              style={{ width: '100%', padding: 6, border: '1px solid #e5e7eb', borderRadius: 4, fontSize: 13 }}
            />
          </div>
          <div>
            <label style={{ fontSize: 11 }}>Max Spread %</label>
            <input 
              type="number" 
              step="0.01"
              value={formThresholds.maxSpreadPct} 
              onChange={e => setFormThresholds({...formThresholds, maxSpreadPct: Number(e.target.value)})}
              style={{ width: '100%', padding: 6, border: '1px solid #e5e7eb', borderRadius: 4, fontSize: 13 }}
            />
          </div>
          <div>
            <label style={{ fontSize: 11 }}>Max Spread/ATR Ratio</label>
            <input 
              type="number" 
              step="0.01"
              value={formThresholds.maxSpreadToAtrRatio} 
              onChange={e => setFormThresholds({...formThresholds, maxSpreadToAtrRatio: Number(e.target.value)})}
              style={{ width: '100%', padding: 6, border: '1px solid #e5e7eb', borderRadius: 4, fontSize: 13 }}
            />
          </div>
          <div>
            <label style={{ fontSize: 11 }}>Normal Funding Abs (decimal)</label>
            <input 
              type="number" 
              step="0.0001"
              value={formThresholds.normalFundingAbs} 
              onChange={e => setFormThresholds({...formThresholds, normalFundingAbs: Number(e.target.value)})}
              style={{ width: '100%', padding: 6, border: '1px solid #e5e7eb', borderRadius: 4, fontSize: 13 }}
            />
          </div>
          <div>
            <label style={{ fontSize: 11 }}>Max Funding Abs (decimal)</label>
            <input 
              type="number" 
              step="0.0001"
              value={formThresholds.maxFundingAbs} 
              onChange={e => setFormThresholds({...formThresholds, maxFundingAbs: Number(e.target.value)})}
              style={{ width: '100%', padding: 6, border: '1px solid #e5e7eb', borderRadius: 4, fontSize: 13 }}
            />
          </div>
        </div>
      </div>

      {/* Recent Activity Config */}
      <div style={{ gridColumn: '1 / -1', marginTop: 16 }}>
        <h4 style={{ margin: '0 0 12px 0', fontSize: 14 }}>Recent Activity</h4>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <input
              type="checkbox"
              checked={formRecentActivity.enabled}
              onChange={e => setFormRecentActivity({ ...formRecentActivity, enabled: e.target.checked })}
            />
            <label style={{ fontSize: 11 }}>Enabled</label>
          </div>
          <div>
            <label style={{ fontSize: 11 }}>Primary Window</label>
            <select
              value={formRecentActivity.primaryWindow}
              onChange={e => setFormRecentActivity({ ...formRecentActivity, primaryWindow: e.target.value as '1h' | '4h' | '1d' })}
              style={{ width: '100%', padding: 6, border: '1px solid #e5e7eb', borderRadius: 4, fontSize: 13 }}
            >
              <option value="1h">1h</option>
              <option value="4h">4h</option>
              <option value="1d">1d</option>
            </select>
          </div>
          <div>
            <label style={{ fontSize: 11 }}>Secondary Window</label>
            <select
              value={formRecentActivity.secondaryWindow}
              onChange={e => setFormRecentActivity({ ...formRecentActivity, secondaryWindow: e.target.value as '1h' | '4h' | '1d' })}
              style={{ width: '100%', padding: 6, border: '1px solid #e5e7eb', borderRadius: 4, fontSize: 13 }}
            >
              <option value="1h">1h</option>
              <option value="4h">4h</option>
              <option value="1d">1d</option>
            </select>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <input
              type="checkbox"
              checked={formRecentActivity.use1d}
              onChange={e => setFormRecentActivity({ ...formRecentActivity, use1d: e.target.checked })}
            />
            <label style={{ fontSize: 11 }}>Use 1d Window</label>
          </div>
          <div>
            <label style={{ fontSize: 11 }}>Stale After (seconds)</label>
            <input
              type="number"
              min={1}
              value={formRecentActivity.staleAfterSeconds}
              onChange={e => setFormRecentActivity({ ...formRecentActivity, staleAfterSeconds: Number(e.target.value) })}
              style={{ width: '100%', padding: 6, border: '1px solid #e5e7eb', borderRadius: 4, fontSize: 13 }}
            />
          </div>
        </div>
      </div>

      {/* Recent Activity Thresholds */}
      <div style={{ gridColumn: '1 / -1', marginTop: 16 }}>
        <h4 style={{ margin: '0 0 12px 0', fontSize: 14 }}>Recent Activity Thresholds</h4>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 }}>
          <div>
            <label style={{ fontSize: 11 }}>Min Quote Volume 1h</label>
            <input type="number" value={formRecentActivityThresholds.minQuoteVolume1h} onChange={e => setFormRecentActivityThresholds({...formRecentActivityThresholds, minQuoteVolume1h: Number(e.target.value)})} style={{ width: '100%', padding: 6, border: '1px solid #e5e7eb', borderRadius: 4, fontSize: 13 }} />
          </div>
          <div>
            <label style={{ fontSize: 11 }}>Excellent Quote Volume 1h</label>
            <input type="number" value={formRecentActivityThresholds.excellentQuoteVolume1h} onChange={e => setFormRecentActivityThresholds({...formRecentActivityThresholds, excellentQuoteVolume1h: Number(e.target.value)})} style={{ width: '100%', padding: 6, border: '1px solid #e5e7eb', borderRadius: 4, fontSize: 13 }} />
          </div>
          <div>
            <label style={{ fontSize: 11 }}>Min Quote Volume 4h</label>
            <input type="number" value={formRecentActivityThresholds.minQuoteVolume4h} onChange={e => setFormRecentActivityThresholds({...formRecentActivityThresholds, minQuoteVolume4h: Number(e.target.value)})} style={{ width: '100%', padding: 6, border: '1px solid #e5e7eb', borderRadius: 4, fontSize: 13 }} />
          </div>
          <div>
            <label style={{ fontSize: 11 }}>Excellent Quote Volume 4h</label>
            <input type="number" value={formRecentActivityThresholds.excellentQuoteVolume4h} onChange={e => setFormRecentActivityThresholds({...formRecentActivityThresholds, excellentQuoteVolume4h: Number(e.target.value)})} style={{ width: '100%', padding: 6, border: '1px solid #e5e7eb', borderRadius: 4, fontSize: 13 }} />
          </div>
          <div>
            <label style={{ fontSize: 11 }}>Min Quote Volume 1d</label>
            <input type="number" value={formRecentActivityThresholds.minQuoteVolume1d} onChange={e => setFormRecentActivityThresholds({...formRecentActivityThresholds, minQuoteVolume1d: Number(e.target.value)})} style={{ width: '100%', padding: 6, border: '1px solid #e5e7eb', borderRadius: 4, fontSize: 13 }} />
          </div>
          <div>
            <label style={{ fontSize: 11 }}>Excellent Quote Volume 1d</label>
            <input type="number" value={formRecentActivityThresholds.excellentQuoteVolume1d} onChange={e => setFormRecentActivityThresholds({...formRecentActivityThresholds, excellentQuoteVolume1d: Number(e.target.value)})} style={{ width: '100%', padding: 6, border: '1px solid #e5e7eb', borderRadius: 4, fontSize: 13 }} />
          </div>
          <div>
            <label style={{ fontSize: 11 }}>Min Trades 1h</label>
            <input type="number" value={formRecentActivityThresholds.minTrades1h} onChange={e => setFormRecentActivityThresholds({...formRecentActivityThresholds, minTrades1h: Number(e.target.value)})} style={{ width: '100%', padding: 6, border: '1px solid #e5e7eb', borderRadius: 4, fontSize: 13 }} />
          </div>
          <div>
            <label style={{ fontSize: 11 }}>Excellent Trades 1h</label>
            <input type="number" value={formRecentActivityThresholds.excellentTrades1h} onChange={e => setFormRecentActivityThresholds({...formRecentActivityThresholds, excellentTrades1h: Number(e.target.value)})} style={{ width: '100%', padding: 6, border: '1px solid #e5e7eb', borderRadius: 4, fontSize: 13 }} />
          </div>
          <div>
            <label style={{ fontSize: 11 }}>Min Trades 4h</label>
            <input type="number" value={formRecentActivityThresholds.minTrades4h} onChange={e => setFormRecentActivityThresholds({...formRecentActivityThresholds, minTrades4h: Number(e.target.value)})} style={{ width: '100%', padding: 6, border: '1px solid #e5e7eb', borderRadius: 4, fontSize: 13 }} />
          </div>
          <div>
            <label style={{ fontSize: 11 }}>Excellent Trades 4h</label>
            <input type="number" value={formRecentActivityThresholds.excellentTrades4h} onChange={e => setFormRecentActivityThresholds({...formRecentActivityThresholds, excellentTrades4h: Number(e.target.value)})} style={{ width: '100%', padding: 6, border: '1px solid #e5e7eb', borderRadius: 4, fontSize: 13 }} />
          </div>
        </div>
      </div>

      {/* Actions */}
      <div style={{ gridColumn: '1 / -1', marginTop: 24, display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
        <button 
          onClick={onCancel}
          style={{ padding: '8px 16px', borderRadius: 6, border: '1px solid #6b7280', background: '#fff', cursor: 'pointer' }}
        >
          Cancel
        </button>
        <button 
          onClick={onSubmit}
          disabled={!formName.trim()}
          style={{ 
            padding: '8px 16px', 
            borderRadius: 6, 
            border: '1px solid #2563eb', 
            background: formName.trim() ? '#2563eb' : '#e5e7eb', 
            color: '#fff', 
            cursor: formName.trim() ? 'pointer' : 'not-allowed' 
          }}
        >
          {submitLabel}
        </button>
      </div>
    </div>
  )
}
