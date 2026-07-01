import React, { useEffect, useState, useMemo } from 'react'
import { api } from '@/lib/api'
import { useUI } from '@/stores/ui'
import { useAuth } from '@/stores/auth'
import AnalyticsChart from '@/components/chart/AnalyticsChart'

interface BacktestConfig {
  trading_mode?: string
  timeframe?: string
  stake_currency?: string
  stake_amount?: string | number
  pair_whitelist?: string[]
  pairlists?: Array<{ method: string; pair_whitelist?: string[] }>
  entry_pricing?: { use_order_book?: boolean }
  exit_pricing?: { use_order_book?: boolean }
  [key: string]: any
}

interface BacktestSummary {
  total_trades: number
  winrate: number
  profit_abs_sum: number
  profit_ratio_avg: number
  by_pair?: Record<string, { count: number; profit_ratio_sum: number; profit_abs_sum: number }>
  file?: string
  timeframe?: string
  timerange?: string
}

interface BacktestTrade {
  pair: string
  is_short?: boolean
  open_date?: string
  open_timestamp?: number
  open_rate: number
  close_date?: string
  close_timestamp?: number
  close_rate: number
  profit_ratio: number
  profit_abs: number
  exit_reason?: string
}

export function BacktestNew() {
  const userId = useAuth(s => s.userId)
  const notifySuccess = useUI(s => s.notifySuccess)
  const notifyError = useUI(s => s.notifyError)

  // Config state
  const [cfg, setCfg] = useState<BacktestConfig | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  
  // Run state
  const [running, setRunning] = useState(false)
  const [strategy, setStrategy] = useState<string>('SupplyDemandStructureStrategyHTF_TrendV3')
  const [strategies, setStrategies] = useState<string[]>([])
  const [startDate, setStartDate] = useState<string>('')
  const [endDate, setEndDate] = useState<string>('')
  const [exportTrades, setExportTrades] = useState<boolean>(true)
  
  // Results state
  const [summary, setSummary] = useState<BacktestSummary | null>(null)
  const [trades, setTrades] = useState<BacktestTrade[]>([])
  const [artifacts, setArtifacts] = useState<Array<{ file: string; mtime: number; size: number }>>([])
  const [logs, setLogs] = useState<string[]>([])
  const [activeTab, setActiveTab] = useState<'config' | 'results' | 'trades' | 'logs'>('config')

  // Chart state
  const [selectedPair, setSelectedPair] = useState<string>('')
  
  // Load config
  useEffect(() => {
    const load = async () => {
      try {
        const res = await api.get('/config/backtest')
        setCfg(res.data)
      } catch (e: any) {
        notifyError(e?.response?.data?.detail || e?.message || 'Failed to load config')
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  // Load strategies
  useEffect(() => {
    const load = async () => {
      try {
        const res = await api.get('/config/backtest/strategies')
        const list: string[] = res.data?.strategies || []
        setStrategies(list)
        if (list.length && !list.includes(strategy)) {
          setStrategy(list[0])
        }
      } catch (e: any) {
        console.warn('Failed to load strategies', e)
      }
    }
    load()
  }, [])

  const timerange = useMemo(() => {
    if (!startDate || !endDate) return ''
    const fmt = (s: string) => s.replace(/-/g, '')
    return `${fmt(startDate)}-${fmt(endDate)}`
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
    if (!cfg) return
    setSaving(true)
    try {
      await api.put('/config/backtest', cfg)
      notifySuccess('Configuration saved')
    } catch (e: any) {
      notifyError(e?.response?.data?.detail || e?.message || 'Failed to save')
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
      const exitCode = res.data?.exit_code
      
      if (exitCode === 0) {
        notifySuccess('Backtest completed successfully')
        setSummary(res.data?.latest_summary || null)
        setTrades(Array.isArray(res.data?.latest_trades) ? res.data.latest_trades : [])
        setArtifacts(Array.isArray(res.data?.artifacts) ? res.data.artifacts : [])
        setLogs(Array.isArray(res.data?.logs?.lines) ? res.data.logs.lines : [])
        setActiveTab('results')
      } else {
        notifyError('Backtest finished with errors. Check logs.')
        setLogs(Array.isArray(res.data?.logs?.lines) ? res.data.logs.lines : [])
        setActiveTab('logs')
      }
    } catch (e: any) {
      notifyError(e?.response?.data?.detail || e?.message || 'Failed to run backtest')
    } finally {
      setRunning(false)
    }
  }

  if (loading) {
    return (
      <div className="p-6">
        <div className="text-gray-600">Loading backtest configuration...</div>
      </div>
    )
  }

  if (!cfg) {
    return (
      <div className="p-6">
        <div className="text-red-600">Failed to load configuration</div>
      </div>
    )
  }

  const pairlist = cfg.pairlists?.[0]?.pair_whitelist || cfg.pair_whitelist || []
  const pairText = Array.isArray(pairlist) ? pairlist.join('\n') : ''
  const availablePairs = summary ? Object.keys(summary.by_pair || {}) : []

  return (
    <div className="p-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">Backtest Engine</h1>
        <p className="text-gray-600">Configure and run backtests to validate your trading strategies</p>
      </div>

      {/* Tab Navigation */}
      <div className="mb-6 border-b border-gray-200">
        <nav className="-mb-px flex space-x-8">
          {[
            { key: 'config', label: 'Configuration', icon: '⚙️' },
            { key: 'results', label: 'Results', icon: '📊' },
            { key: 'trades', label: 'Trades', icon: '📈' },
            { key: 'logs', label: 'Logs', icon: '📝' },
          ].map(tab => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key as any)}
              className={`
                whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm
                ${activeTab === tab.key
                  ? 'border-indigo-500 text-indigo-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }
              `}
            >
              <span className="mr-2">{tab.icon}</span>
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      {/* Configuration Tab */}
      {activeTab === 'config' && (
        <div className="space-y-6">
          <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
            <h2 className="text-xl font-semibold mb-4">Strategy & Timeframe</h2>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Strategy</label>
                {strategies.length > 0 ? (
                  <select
                    value={strategy}
                    onChange={e => setStrategy(e.target.value)}
                    className="w-full border border-gray-300 rounded-md px-3 py-2 focus:ring-indigo-500 focus:border-indigo-500"
                  >
                    {strategies.map(s => (
                      <option key={s} value={s}>{s}</option>
                    ))}
                  </select>
                ) : (
                  <input
                    type="text"
                    value={strategy}
                    onChange={e => setStrategy(e.target.value)}
                    className="w-full border border-gray-300 rounded-md px-3 py-2 focus:ring-indigo-500 focus:border-indigo-500"
                  />
                )}
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Timeframe</label>
                <input
                  type="text"
                  value={cfg.timeframe || ''}
                  onChange={e => updateField(['timeframe'], e.target.value)}
                  placeholder="15m, 1h, 4h"
                  className="w-full border border-gray-300 rounded-md px-3 py-2 focus:ring-indigo-500 focus:border-indigo-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Trading Mode</label>
                <select
                  value={cfg.trading_mode || 'spot'}
                  onChange={e => updateField(['trading_mode'], e.target.value)}
                  className="w-full border border-gray-300 rounded-md px-3 py-2 focus:ring-indigo-500 focus:border-indigo-500"
                >
                  <option value="spot">Spot</option>
                  <option value="futures">Futures</option>
                </select>
              </div>
            </div>
          </div>

          <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
            <h2 className="text-xl font-semibold mb-4">Capital & Risk</h2>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Stake Currency</label>
                <input
                  type="text"
                  value={cfg.stake_currency || ''}
                  onChange={e => updateField(['stake_currency'], e.target.value)}
                  placeholder="USDT"
                  className="w-full border border-gray-300 rounded-md px-3 py-2 focus:ring-indigo-500 focus:border-indigo-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Stake Amount</label>
                <input
                  type="text"
                  value={cfg.stake_amount || ''}
                  onChange={e => updateField(['stake_amount'], e.target.value)}
                  placeholder="100"
                  className="w-full border border-gray-300 rounded-md px-3 py-2 focus:ring-indigo-500 focus:border-indigo-500"
                />
              </div>
              <div className="flex items-end">
                <label className="flex items-center space-x-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={exportTrades}
                    onChange={e => setExportTrades(e.target.checked)}
                    className="w-4 h-4 text-indigo-600 border-gray-300 rounded focus:ring-indigo-500"
                  />
                  <span className="text-sm text-gray-700">Export Trades</span>
                </label>
              </div>
            </div>
          </div>

          <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
            <h2 className="text-xl font-semibold mb-4">Time Range</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Start Date</label>
                <input
                  type="date"
                  value={startDate}
                  onChange={e => setStartDate(e.target.value)}
                  className="w-full border border-gray-300 rounded-md px-3 py-2 focus:ring-indigo-500 focus:border-indigo-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">End Date</label>
                <input
                  type="date"
                  value={endDate}
                  onChange={e => setEndDate(e.target.value)}
                  className="w-full border border-gray-300 rounded-md px-3 py-2 focus:ring-indigo-500 focus:border-indigo-500"
                />
              </div>
            </div>
            {timerange && (
              <div className="mt-2 text-sm text-gray-600">
                Timerange: <span className="font-mono font-semibold">{timerange}</span>
              </div>
            )}
          </div>

          <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
            <h2 className="text-xl font-semibold mb-4">Pair Whitelist</h2>
            <textarea
              rows={8}
              value={pairText}
              onChange={e => {
                const lines = e.target.value.split(/\r?\n/).map(s => s.trim()).filter(Boolean)
                updateField(['pair_whitelist'], lines)
                const first = cfg.pairlists?.[0] || { method: 'StaticPairList' }
                const rest = cfg.pairlists?.slice(1) || []
                updateField(['pairlists'], [{ ...first, pair_whitelist: lines }, ...rest])
              }}
              placeholder="BTC/USDT&#10;ETH/USDT&#10;BNB/USDT"
              className="w-full border border-gray-300 rounded-md px-3 py-2 focus:ring-indigo-500 focus:border-indigo-500 font-mono text-sm"
            />
          </div>

          <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
            <h2 className="text-xl font-semibold mb-4">Pricing Options</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="flex items-center space-x-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={cfg.entry_pricing?.use_order_book || false}
                    onChange={e => updateField(['entry_pricing', 'use_order_book'], e.target.checked)}
                    className="w-4 h-4 text-indigo-600 border-gray-300 rounded focus:ring-indigo-500"
                  />
                  <span className="text-sm text-gray-700">Entry: Use Order Book</span>
                </label>
              </div>
              <div>
                <label className="flex items-center space-x-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={cfg.exit_pricing?.use_order_book || false}
                    onChange={e => updateField(['exit_pricing', 'use_order_book'], e.target.checked)}
                    className="w-4 h-4 text-indigo-600 border-gray-300 rounded focus:ring-indigo-500"
                  />
                  <span className="text-sm text-gray-700">Exit: Use Order Book</span>
                </label>
              </div>
            </div>
          </div>

          <div className="flex space-x-4">
            <button
              onClick={save}
              disabled={saving}
              className="px-6 py-2 bg-gray-600 text-white rounded-md hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {saving ? 'Saving...' : 'Save Configuration'}
            </button>
            <button
              onClick={run}
              disabled={running || !timerange}
              className="px-6 py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {running ? 'Running...' : 'Run Backtest'}
            </button>
          </div>
        </div>
      )}

      {/* Results Tab */}
      {activeTab === 'results' && (
        <div className="space-y-6">
          {!summary ? (
            <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-12 text-center">
              <div className="text-gray-400 text-lg mb-2">No results available</div>
              <div className="text-gray-500 text-sm">Run a backtest to see results here</div>
            </div>
          ) : (
            <>
              {/* Summary Stats */}
              <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
                  <div className="text-sm text-gray-600 mb-1">Total Trades</div>
                  <div className="text-2xl font-bold text-gray-900">{summary.total_trades}</div>
                </div>
                <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
                  <div className="text-sm text-gray-600 mb-1">Win Rate</div>
                  <div className={`text-2xl font-bold ${summary.winrate >= 0.5 ? 'text-green-600' : 'text-red-600'}`}>
                    {(summary.winrate * 100).toFixed(2)}%
                  </div>
                </div>
                <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
                  <div className="text-sm text-gray-600 mb-1">Total Profit</div>
                  <div className={`text-2xl font-bold ${summary.profit_abs_sum >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                    {summary.profit_abs_sum.toFixed(4)}
                  </div>
                </div>
                <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
                  <div className="text-sm text-gray-600 mb-1">Avg Profit %</div>
                  <div className={`text-2xl font-bold ${summary.profit_ratio_avg >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                    {(summary.profit_ratio_avg * 100).toFixed(2)}%
                  </div>
                </div>
              </div>

              {/* Chart */}
              {availablePairs.length > 0 && (
                <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
                  <div className="mb-4">
                    <label className="block text-sm font-medium text-gray-700 mb-2">Select Pair to View</label>
                    <select
                      value={selectedPair}
                      onChange={e => setSelectedPair(e.target.value)}
                      className="border border-gray-300 rounded-md px-3 py-2 focus:ring-indigo-500 focus:border-indigo-500"
                    >
                      <option value="">-- Select a pair --</option>
                      {availablePairs.map(pair => (
                        <option key={pair} value={pair}>{pair}</option>
                      ))}
                    </select>
                  </div>
                  {selectedPair && (
                    <div className="text-sm text-gray-600 mb-4">
                      Note: Chart display requires bot configuration. Use the Bots page to load backtest results with full chart support.
                    </div>
                  )}
                </div>
              )}

              {/* Per-Pair Performance */}
              {summary.by_pair && Object.keys(summary.by_pair).length > 0 && (
                <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
                  <h3 className="text-lg font-semibold mb-4">Performance by Pair</h3>
                  <div className="overflow-x-auto">
                    <table className="min-w-full divide-y divide-gray-200">
                      <thead className="bg-gray-50">
                        <tr>
                          <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Pair</th>
                          <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Trades</th>
                          <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Total Profit</th>
                          <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Avg Profit %</th>
                        </tr>
                      </thead>
                      <tbody className="bg-white divide-y divide-gray-200">
                        {Object.entries(summary.by_pair)
                          .sort(([, a], [, b]) => b.profit_abs_sum - a.profit_abs_sum)
                          .map(([pair, stats]) => (
                            <tr key={pair} className="hover:bg-gray-50">
                              <td className="px-4 py-3 whitespace-nowrap text-sm font-medium text-gray-900">{pair}</td>
                              <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-600">{stats.count}</td>
                              <td className={`px-4 py-3 whitespace-nowrap text-sm font-medium ${stats.profit_abs_sum >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                                {stats.profit_abs_sum.toFixed(4)}
                              </td>
                              <td className={`px-4 py-3 whitespace-nowrap text-sm font-medium ${(stats.profit_ratio_sum / stats.count) >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                                {((stats.profit_ratio_sum / stats.count) * 100).toFixed(2)}%
                              </td>
                            </tr>
                          ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Artifacts */}
              {artifacts.length > 0 && (
                <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
                  <h3 className="text-lg font-semibold mb-4">Result Files</h3>
                  <div className="space-y-2">
                    {artifacts.map(a => (
                      <div key={a.file} className="flex items-center justify-between p-3 bg-gray-50 rounded-md">
                        <div className="flex items-center space-x-3">
                          <span className="text-2xl">📦</span>
                          <div>
                            <div className="text-sm font-medium text-gray-900">{a.file}</div>
                            <div className="text-xs text-gray-500">{(a.size / 1024).toFixed(2)} KB</div>
                          </div>
                        </div>
                        <div className="text-xs text-gray-500">
                          {new Date(a.mtime * 1000).toLocaleString()}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* Trades Tab */}
      {activeTab === 'trades' && (
        <div className="space-y-6">
          {trades.length === 0 ? (
            <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-12 text-center">
              <div className="text-gray-400 text-lg mb-2">No trades available</div>
              <div className="text-gray-500 text-sm">Run a backtest to see trades here</div>
            </div>
          ) : (
            <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
              <h3 className="text-lg font-semibold mb-4">Trade History ({trades.length} trades)</h3>
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Pair</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Type</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Open</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Close</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Profit %</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Profit</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Exit Reason</th>
                    </tr>
                  </thead>
                  <tbody className="bg-white divide-y divide-gray-200">
                    {trades.map((t, idx) => (
                      <tr key={idx} className="hover:bg-gray-50">
                        <td className="px-4 py-3 whitespace-nowrap text-sm font-medium text-gray-900">{t.pair}</td>
                        <td className="px-4 py-3 whitespace-nowrap text-sm">
                          <span className={`px-2 py-1 text-xs font-medium rounded ${t.is_short ? 'bg-red-100 text-red-800' : 'bg-green-100 text-green-800'}`}>
                            {t.is_short ? 'SHORT' : 'LONG'}
                          </span>
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-600">
                          <div>{t.open_rate.toFixed(6)}</div>
                          <div className="text-xs text-gray-400">{t.open_date || new Date(t.open_timestamp! * 1000).toISOString().slice(0, 16)}</div>
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-600">
                          <div>{t.close_rate.toFixed(6)}</div>
                          <div className="text-xs text-gray-400">{t.close_date || new Date(t.close_timestamp! * 1000).toISOString().slice(0, 16)}</div>
                        </td>
                        <td className={`px-4 py-3 whitespace-nowrap text-sm font-medium ${t.profit_ratio >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                          {(t.profit_ratio * 100).toFixed(2)}%
                        </td>
                        <td className={`px-4 py-3 whitespace-nowrap text-sm font-medium ${t.profit_abs >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                          {t.profit_abs.toFixed(6)}
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-600">{t.exit_reason || '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Logs Tab */}
      {activeTab === 'logs' && (
        <div className="space-y-6">
          <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
            <h3 className="text-lg font-semibold mb-4">Backtest Logs</h3>
            <div className="bg-gray-900 text-gray-100 rounded-md p-4 overflow-auto" style={{ maxHeight: '600px', fontFamily: 'monospace', fontSize: '12px', whiteSpace: 'pre-wrap' }}>
              {logs.length === 0 ? (
                <div className="text-gray-500">No logs available. Run a backtest to see output.</div>
              ) : (
                logs.join('\n')
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
