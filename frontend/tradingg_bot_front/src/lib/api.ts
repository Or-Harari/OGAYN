import axios from 'axios'

export const API_BASE = ((): string => {
  // Use environment variable if set, otherwise use relative path '/api' for production
  const env = (import.meta as any).env
  const apiBase = env?.VITE_API_BASE
  
  if (apiBase) {
    return apiBase
  }
  
  // In production, use relative path (nginx will proxy /api to backend)
  // In development, this can be configured via vite proxy or VITE_API_BASE env var
  return '/api'
})()

export const api = axios.create({
  baseURL: API_BASE,
})

export function setAuthToken(token: string | null) {
  if (token) {
    api.defaults.headers.common['Authorization'] = `Bearer ${token}`
    localStorage.setItem('auth_token', token)
  } else {
    delete api.defaults.headers.common['Authorization']
    localStorage.removeItem('auth_token')
  }
}

// restore token on load
const existing = localStorage.getItem('auth_token')
if (existing) setAuthToken(existing)

// Global response interceptor: on 401/403, clear token and redirect to login
api.interceptors.response.use(
  (resp) => resp,
  (error) => {
    const status = error?.response?.status
    // Only treat 401 (unauthenticated) as a reason to log out and redirect.
    if (status === 401) {
      try {
        setAuthToken(null)
      } catch {}
      try {
        // Preserve current location in query for optional return-after-login
        const loc = typeof window !== 'undefined' ? window.location.pathname + window.location.search : ''
        const loginUrl = '/login' + (loc && loc !== '/login' ? `?next=${encodeURIComponent(loc)}` : '')
        if (typeof window !== 'undefined') window.location.assign(loginUrl)
      } catch {}
    }
    // 403 (forbidden) should not force logout; callers can handle per-view.
    return Promise.reject(error)
  }
)

// Scanner API types
export interface ScoringWeights {
  liquidity: number
  volatility: number
  spread: number
  funding: number
  tradeCount: number
  recentActivity: number
}

export interface ScoringThresholds {
  minQuoteVolume24h: number
  excellentQuoteVolume24h: number
  minAtrPct: number
  idealAtrPctLow: number
  idealAtrPctHigh: number
  maxAtrPct: number
  maxSpreadPct: number
  maxSpreadToAtrRatio: number
  normalFundingAbs: number
  maxFundingAbs: number
}

export interface RecentActivityConfig {
  enabled: boolean
  primaryWindow: '1h' | '4h' | '1d'
  secondaryWindow: '1h' | '4h' | '1d'
  use1d: boolean
  staleAfterSeconds: number
}

export interface RecentActivityThresholds {
  minQuoteVolume1h: number
  excellentQuoteVolume1h: number
  minQuoteVolume4h: number
  excellentQuoteVolume4h: number
  minQuoteVolume1d: number
  excellentQuoteVolume1d: number
  minTrades1h: number
  excellentTrades1h: number
  minTrades4h: number
  excellentTrades4h: number
}

export interface ScannerConfig {
  id?: number
  user_id?: number
  name: string
  exchange: string
  market_type: string
  enabled: boolean
  interval_minutes: number
  quote_asset: string
  max_pairs: number
  min_market_score: number
  include_symbols: string[]
  exclude_symbols: string[]
  scoring_weights: ScoringWeights
  scoring_thresholds: ScoringThresholds
  recent_activity: RecentActivityConfig
  recent_activity_thresholds: RecentActivityThresholds
  output_base_path?: string
  created_at?: string
  updated_at?: string
  last_run_at?: number
}

export interface CacheStatus {
  fetcher_type?: string
  running: boolean
  connected?: boolean
  fetch_interval_minutes: number
  last_fetch_at: number | null
  last_error: string | null
  message_count?: number
  reconnect_count?: number
  last_save_time?: number
  cached_symbols?: number
  save_interval?: number
  in_memory_symbols?: number
  in_memory_tickers?: number
  futures_symbols?: number
  spot_symbols?: number
  kline_stream_symbols?: number
  ws_connections?: number
  recent_activity?: {
    enabled: boolean
    windows: string[]
    sourcePreference: string
    allowRestFallback: boolean
    futuresKlineTopN: number
    staleAfterSeconds: number
    futuresUniverseRefreshSeconds: number
    futuresKlineChunkSize: number
  }
  cache: {
    total_entries: number
    latest_timestamp: number | null
    cache_snapshots: number
    age_seconds: number | null
  }
}

export interface SchedulerStatus {
  running: boolean
  active_scanners: number
  scanner_ids: number[]
}

export interface ScannerRecentActivityEntry {
  symbol: string
  market_type: 'spot' | 'futures' | string
  source: string | null
  mode: 'rolling' | 'candle' | string | null
  updated_at: number | null
  stale_after_seconds: number | null
  window: '1h' | '4h' | '1d' | string
  quote_volume: number | null
  trade_count: number | null
  window_updated_at: number | null
  stale: boolean
}

export interface ScannerRecentActivityResponse {
  scanner_id: number
  scanner_name: string
  market_type: 'spot' | 'futures' | string
  window: '1h' | '4h' | '1d' | string
  cache_timestamp: number | null
  count: number
  by_symbol: Record<string, ScannerRecentActivityEntry>
}

// Scanner API methods
export const scannerApi = {
  // List user scanners
  list: async (userId: number) => {
    const res = await api.get(`/scanners/users/${userId}/scanners`)
    return res.data as ScannerConfig[]
  },

  // Get scanner by ID
  get: async (userId: number, scannerId: number) => {
    const res = await api.get(`/scanners/users/${userId}/scanners/${scannerId}`)
    return res.data as ScannerConfig
  },

  // Create scanner
  create: async (userId: number, config: Omit<ScannerConfig, 'id' | 'user_id' | 'created_at' | 'updated_at' | 'output_base_path'>) => {
    const res = await api.post(`/scanners/users/${userId}/scanners`, config)
    return res.data as ScannerConfig
  },

  // Update scanner
  update: async (userId: number, scannerId: number, config: Partial<Omit<ScannerConfig, 'id' | 'user_id' | 'created_at' | 'updated_at' | 'output_base_path'>>) => {
    const res = await api.put(`/scanners/users/${userId}/scanners/${scannerId}`, config)
    return res.data as ScannerConfig
  },

  // Delete scanner
  delete: async (userId: number, scannerId: number) => {
    await api.delete(`/scanners/users/${userId}/scanners/${scannerId}`)
  },

  // Get latest results (deprecated - use getOutputs instead)
  getResults: async (userId: number, scannerId: number, limit: number = 50, minScore?: number) => {
    const params = new URLSearchParams({ limit: limit.toString() })
    if (minScore !== undefined) params.set('min_score', minScore.toString())
    const res = await api.get(`/scanners/users/${userId}/scanners/${scannerId}/results/latest?${params}`)
    return res.data
  },

  // Get scanner outputs (current filtered symbols)
  getOutputs: async (userId: number, scannerId: number, limit?: number) => {
    const params = limit ? new URLSearchParams({ limit: limit.toString() }) : ''
    const res = await api.get(`/scanners/users/${userId}/scanners/${scannerId}/outputs${params ? '?' + params : ''}`)
    return res.data
  },

  // Get scanner recent activity from latest cache snapshot
  getRecentActivity: async (
    userId: number,
    scannerId: number,
    window: '1h' | '4h' | '1d' = '1h',
    symbols?: string[],
    limit?: number,
  ): Promise<ScannerRecentActivityResponse> => {
    const params = new URLSearchParams({ window })
    if (symbols && symbols.length > 0) {
      params.set('symbols', symbols.join(','))
    }
    if (typeof limit === 'number') {
      params.set('limit', String(limit))
    }
    const res = await api.get(`/scanners/users/${userId}/scanners/${scannerId}/recent-activity?${params.toString()}`)
    return res.data as ScannerRecentActivityResponse
  },

  // Get pairlist
  getPairlist: async (userId: number, scannerId: number) => {
    const res = await api.get(`/scanners/users/${userId}/scanners/${scannerId}/pairlist`)
    return res.data as { pairs: string[], refresh_period: number }
  },

  // Run scanner now
  runNow: async (userId: number, scannerId: number) => {
    const res = await api.post(`/scanners/users/${userId}/scanners/${scannerId}/run`)
    return res.data
  },

  // Run all scanners
  runAll: async () => {
    const res = await api.post('/scanners/run-multi')
    return res.data
  },

  // Get scanner status
  getStatus: async () => {
    const res = await api.get('/scanners/status')
    return res.data
  },

  // Get fetcher status
  getFetcherStatus: async (): Promise<CacheStatus> => {
    const res = await api.get('/scanners/status/fetcher')
    return res.data
  },

  // Get scheduler status
  getSchedulerStatus: async (): Promise<SchedulerStatus> => {
    const res = await api.get('/scanners/status/scheduler')
    return res.data
  },
}
