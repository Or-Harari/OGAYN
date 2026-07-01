import React, { useEffect, useState } from 'react'
import { api } from '@/lib/api'
import './Markets.css'

interface MarketSnapshot {
  id: number
  timestamp: number
  exchange: string
  symbol: string
  price: number
  volume: number
  atr: number
  spread: number
  funding: number
  scores: {
    liquidity: number
    spread: number
    atr: number
    funding: number
    tickSize: number
  }
  marketQuality: number
  reasons: Record<string, string>
}

interface ScannerStatus {
  running: boolean
  lastRunStartedAt: number | null
  lastRunFinishedAt: number | null
  lastRunError: string | null
}

export function Markets() {
  const [markets, setMarkets] = useState<MarketSnapshot[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [minScore, setMinScore] = useState(70)
  const [limit, setLimit] = useState(50)
  const [searchTerm, setSearchTerm] = useState('')
  const [scannerStatus, setScannerStatus] = useState<ScannerStatus | null>(null)
  const [triggering, setTriggering] = useState(false)
  const [selectedMarket, setSelectedMarket] = useState<MarketSnapshot | null>(null)

  // Edge case validation: ensure valid values before API call
  const getValidatedLimit = () => {
    const val = Number(limit)
    if (!val || isNaN(val) || val < 1) return 1
    if (val > 1000) return 1000
    return Math.floor(val)
  }

  const getValidatedMinScore = () => {
    const val = Number(minScore)
    if (isNaN(val) || val < 0) return 0
    if (val > 100) return 100
    return Math.floor(val)
  }

  const loadMarkets = async () => {
    try {
      setLoading(true)
      setError(null)
      const validLimit = getValidatedLimit()
      const validMinScore = getValidatedMinScore()
      console.log('Loading markets with:', { limit: validLimit, minScore: validMinScore })
      const res = await api.get('/markets/top', {
        params: { limit: validLimit, minScore: validMinScore }
      })
      console.log('Markets loaded:', res.data?.length || 0)
      setMarkets(res.data || [])
    } catch (err: any) {
      setError(err?.response?.data?.detail || err.message || 'Failed to load markets')
    } finally {
      setLoading(false)
    }
  }

  const loadStatus = async () => {
    try {
      const res = await api.get('/markets/scan/status')
      setScannerStatus(res.data)
    } catch (err) {
      // Ignore status errors
    }
  }

  const triggerScan = async () => {
    try {
      setTriggering(true)
      await api.post('/markets/scan/run-once')
      await loadStatus()
      setTimeout(() => loadMarkets(), 2000) // Wait a bit for scan to complete
    } catch (err: any) {
      alert(err?.response?.data?.detail || err.message || 'Failed to trigger scan')
    } finally {
      setTriggering(false)
    }
  }

  useEffect(() => {
    loadMarkets()
    loadStatus()
    const interval = setInterval(() => {
      loadStatus()
    }, 10000) // Poll status every 10s
    return () => clearInterval(interval)
  }, [limit, minScore])

  const filteredMarkets = searchTerm
    ? markets.filter(m => m.symbol.toLowerCase().includes(searchTerm.toLowerCase()))
    : markets

  const formatTime = (ts: number | null) => {
    if (!ts) return 'Never'
    return new Date(ts * 1000).toLocaleString()
  }

  const formatNumber = (n: number, decimals = 2) => {
    if (n >= 1e9) return `${(n / 1e9).toFixed(decimals)}B`
    if (n >= 1e6) return `${(n / 1e6).toFixed(decimals)}M`
    if (n >= 1e3) return `${(n / 1e3).toFixed(decimals)}K`
    return n.toFixed(decimals)
  }

  const getScoreColor = (score: number) => {
    if (score >= 80) return 'score-excellent'
    if (score >= 60) return 'score-good'
    if (score >= 40) return 'score-fair'
    return 'score-poor'
  }

  return (
    <div className="markets-page">
      <div className="markets-header">
        <h1>Market Scanner</h1>
        <div className="scanner-status">
          {scannerStatus && (
            <>
              <span className={scannerStatus.running ? 'status-running' : 'status-idle'}>
                {scannerStatus.running ? '⏳ Scanning...' : '✓ Idle'}
              </span>
              <span className="status-time">
                Last run: {formatTime(scannerStatus.lastRunFinishedAt)}
              </span>
              {scannerStatus.lastRunError && (
                <span className="status-error" title={scannerStatus.lastRunError}>
                  ⚠ Error
                </span>
              )}
            </>
          )}
        </div>
      </div>

      <div className="markets-controls">
        <div className="control-group">
          <label>
            Min Score:
            <input
              type="number"
              min="0"
              max="100"
              value={minScore}
              onChange={e => {
                const val = e.target.value === '' ? 0 : Number(e.target.value)
                setMinScore(val)
              }}
              onBlur={e => {
                const val = Number(e.target.value)
                if (isNaN(val) || val < 0) setMinScore(0)
                else if (val > 100) setMinScore(100)
              }}
            />
          </label>
          <label>
            Limit:
            <input
              type="number"
              min="1"
              max="1000"
              value={limit}
              onChange={e => {
                const val = e.target.value === '' ? 1 : Number(e.target.value)
                setLimit(val)
              }}
              onBlur={e => {
                const val = Number(e.target.value)
                if (isNaN(val) || val < 1) setLimit(1)
                else if (val > 1000) setLimit(1000)
              }}
            />
          </label>
          <div className="preset-buttons">
            <button className={limit === 25 ? 'preset-btn active' : 'preset-btn'} onClick={() => setLimit(25)}>25</button>
            <button className={limit === 50 ? 'preset-btn active' : 'preset-btn'} onClick={() => setLimit(50)}>50</button>
            <button className={limit === 100 ? 'preset-btn active' : 'preset-btn'} onClick={() => setLimit(100)}>100</button>
            <button className={limit === 250 ? 'preset-btn active' : 'preset-btn'} onClick={() => setLimit(250)}>250</button>
            <button className={limit === 1000 ? 'preset-btn active' : 'preset-btn'} onClick={() => setLimit(1000)}>All</button>
          </div>
          <label>
            Search:
            <input
              type="text"
              placeholder="Filter symbols..."
              value={searchTerm}
              onChange={e => setSearchTerm(e.target.value)}
            />
          </label>
        </div>
        <div className="control-actions">
          <span className="result-count">
            Showing {filteredMarkets.length} of {markets.length} markets
          </span>
          <button className="button primary" onClick={loadMarkets} disabled={loading}>
            Refresh
          </button>
          <button className="button secondary" onClick={triggerScan} disabled={triggering}>
            {triggering ? 'Triggering...' : 'Trigger Scan'}
          </button>
        </div>
      </div>

      {error && <div className="error-message">{error}</div>}

      {loading && <div className="loading">Loading markets...</div>}

      {!loading && (
        <div className="markets-content">
          <div className="markets-table-container">
            <table className="markets-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Score</th>
                  <th>Price</th>
                  <th>Volume 24h</th>
                  <th>Open Interest</th>
                  <th>ATR%</th>
                  <th>Spread%</th>
                  <th>Funding%</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {filteredMarkets.map(market => (
                  <tr
                    key={market.id}
                    onClick={() => setSelectedMarket(market)}
                    className={selectedMarket?.id === market.id ? 'selected' : ''}
                  >
                    <td className="symbol-cell">
                      <strong>{market.symbol}</strong>
                    </td>
                    <td>
                      <span className={`score-badge ${getScoreColor(market.marketQuality)}`}>
                        {market.marketQuality}
                      </span>
                    </td>
                    <td>${formatNumber(market.price, 4)}</td>
                    <td className="number-cell">${formatNumber(market.volume)}</td>
                    <td className="number-cell">{market.atr.toFixed(2)}%</td>
                    <td className="number-cell">{market.spread.toFixed(4)}%</td>
                    <td className="number-cell">{(market.funding * 100).toFixed(4)}%</td>
                    <td>
                      <button
                        className="button-link"
                        onClick={(e) => {
                          e.stopPropagation()
                          setSelectedMarket(market)
                        }}
                      >
                        Details
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {filteredMarkets.length === 0 && (
              <div className="empty-state">
                No markets found matching criteria. Try lowering the minimum score or trigger a scan.
              </div>
            )}
          </div>

          {selectedMarket && (
            <div className="market-details">
              <div className="details-header">
                <h2>{selectedMarket.symbol}</h2>
                <button className="close-btn" onClick={() => setSelectedMarket(null)}>×</button>
              </div>

              <div className="details-section">
                <h3>Overall Score: <span className={getScoreColor(selectedMarket.marketQuality)}>{selectedMarket.marketQuality}/100</span></h3>
                <div className="score-breakdown">
                  <div className="score-item">
                    <span className="score-label">Liquidity</span>
                    <div className="score-bar">
                      <div className="score-fill" style={{ width: `${(selectedMarket.scores.liquidity / 30) * 100}%` }}></div>
                    </div>
                    <span className="score-value">{selectedMarket.scores.liquidity}/30</span>
                  </div>
                  <div className="score-item">
                    <span className="score-label">Spread</span>
                    <div className="score-bar">
                      <div className="score-fill" style={{ width: `${(selectedMarket.scores.spread / 20) * 100}%` }}></div>
                    </div>
                    <span className="score-value">{selectedMarket.scores.spread}/20</span>
                  </div>
                  <div className="score-item">
                    <span className="score-label">ATR (Volatility)</span>
                    <div className="score-bar">
                      <div className="score-fill" style={{ width: `${(selectedMarket.scores.atr / 20) * 100}%` }}></div>
                    </div>
                    <span className="score-value">{selectedMarket.scores.atr}/20</span>
                  </div>
                  <div className="score-item">
                    <span className="score-label">Funding</span>
                    <div className="score-bar">
                      <div className="score-fill" style={{ width: `${(selectedMarket.scores.funding / 10) * 100}%` }}></div>
                    </div>
                    <span className="score-value">{selectedMarket.scores.funding}/10</span>
                  </div>
                  <div className="score-item">
                    <span className="score-label">Tick Size</span>
                    <div className="score-bar">
                      <div className="score-fill" style={{ width: `${(selectedMarket.scores.tickSize / 10) * 100}%` }}></div>
                    </div>
                    <span className="score-value">{selectedMarket.scores.tickSize}/10</span>
                  </div>
                </div>
              </div>

              <div className="details-section">
                <h3>Reasons</h3>
                <div className="reasons-list">
                  {Object.entries(selectedMarket.reasons).map(([judge, reason]) => (
                    <div key={judge} className="reason-item">
                      <strong>{judge}:</strong> {reason}
                    </div>
                  ))}
                </div>
              </div>

              <div className="details-section">
                <h3>Market Data</h3>
                <div className="market-data-grid">
                  <div className="data-item">
                    <span className="data-label">Price</span>
                    <span className="data-value">${formatNumber(selectedMarket.price, 4)}</span>
                  </div>
                  <div className="data-item">
                    <span className="data-label">24h Volume</span>
                    <span className="data-value">${formatNumber(selectedMarket.volume)}</span>
                  </div>
                  <div className="data-item">
                    <span className="data-label">ATR %</span>
                    <span className="data-value">{selectedMarket.atr.toFixed(4)}%</span>
                  </div>
                  <div className="data-item">
                    <span className="data-label">Spread %</span>
                    <span className="data-value">{selectedMarket.spread.toFixed(6)}%</span>
                  </div>
                  <div className="data-item">
                    <span className="data-label">Funding Rate</span>
                    <span className="data-value">{(selectedMarket.funding * 100).toFixed(6)}%</span>
                  </div>
                  <div className="data-item">
                    <span className="data-label">Last Updated</span>
                    <span className="data-value">{formatTime(selectedMarket.timestamp)}</span>
                  </div>
                  <div className="data-item">
                    <span className="data-label">Exchange</span>
                    <span className="data-value">{selectedMarket.exchange}</span>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
