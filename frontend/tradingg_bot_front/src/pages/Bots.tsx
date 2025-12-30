import { useEffect, useMemo, useRef, useState } from 'react'
import { useAuth } from '@/stores/auth'
import { useData } from '@/stores/data'
import { api } from '@/lib/api'
import CreateBotForm, { CreateBotFormValues } from '@/components/CreateBotForm'
import BotControls from '@/components/BotControls'
import { useUI } from '@/stores/ui'
import './Bots.css'

// ✅ unified chart + tiny adapters
import AnalyticsChart from '@/components/chart/AnalyticsChart'
import LiveAnalyticsContainer from '@/components/chart/LiveAnalyticsContainer'
import TradesTab from '@/components/TradesTab'

// --- types / helpers moved local (since we removed BackstagePanel import)
type BackstageSelection = { pair: string | null; timerange: string };

const cfgPairs = (cfg: any): string[] =>
  Array.isArray(cfg?.pair_whitelist) ? cfg.pair_whitelist
  : Array.isArray(cfg?.pairs) ? cfg.pairs
  : [];

// Single timeframe precedence: config.timeframe only. If absent, leave empty (no synthetic defaults).
const cfgTimeframes = (cfg: any): string[] =>
  (typeof cfg?.timeframe === 'string' && cfg.timeframe) ? [cfg.timeframe] : [];

type BotStatusPayload = {
  status: string
  pid?: number | null
  config?: string | null
  exit_code?: number | null
  last_error?: string | null
  container?: string | null
}

type BotRuntimeInfo = {
  api_host?: string | null
  api_port?: number | null
  api_base?: string | null
  running?: boolean | null
  config_path?: string | null
  strategy?: string | null
  strategy_path?: string | null
  effective_strategy?: string | null}


export function Bots() {
  const userId = useAuth(s => s.userId)
  const bots = useData(s => s.bots)
  const loadBots = useData(s => s.loadBots)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [details, setDetails] = useState<Record<number, {
    status?: BotStatusPayload | null
    runtime?: BotRuntimeInfo | null
    config?: any | null
    loading?: boolean
    error?: string | null
    starting?: boolean
    stopping?: boolean
    deleting?: boolean
  }>>({})
  const [showCreate, setShowCreate] = useState(false)
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)
  const notifySuccess = useUI(s => s.notifySuccess)
  const notifyError = useUI(s => s.notifyError)
  // Editable bot config form state
  const [formMode, setFormMode] = useState<string>('dryrun')
  const [formStakeCurrency, setFormStakeCurrency] = useState<string>('USDT')
  const [formStakeAmount, setFormStakeAmount] = useState<string>('10')
  const [formPairsText, setFormPairsText] = useState<string>('')
  const [formTradingMode, setFormTradingMode] = useState<'spot' | 'futures'>('spot')
  const [formMarginMode, setFormMarginMode] = useState<string>('cross')
  const [formLiquidationBuffer, setFormLiquidationBuffer] = useState<string>('0.0')
  const [formLeverage, setFormLeverage] = useState<number>(1)
  const [formDryRunWallet, setFormDryRunWallet] = useState<string>('')
  const [strategies, setStrategies] = useState<Array<{ name: string; clazz?: string }>>([])
  const [formStrategyName, setFormStrategyName] = useState<string>('')
  const [formStrategyClazz, setFormStrategyClazz] = useState<string>('')

  // Logs and UI state
  const [rtTail, setRtTail] = useState<number>(500)
  const [btTail, setBtTail] = useState<number>(500)
  const [runtimeLogs, setRuntimeLogs] = useState<string[]>([])
  const [btStatus, setBtStatus] = useState<{ state: string; container?: string | null; started_at?: string | null; finished_at?: string | null; exit_code?: number | null } | null>(null)
  const [autoRefreshLogs, setAutoRefreshLogs] = useState<boolean>(false)
  const [btTimerange, setBtTimerange] = useState<string>('')
  // New date pickers for backtest window
  const [btFromDate, setBtFromDate] = useState<string>('') // YYYY-MM-DD
  const [btToDate, setBtToDate] = useState<string>('')     // YYYY-MM-DD
  const [btStarting, setBtStarting] = useState<boolean>(false)
  const [btResultsFetchedFor, setBtResultsFetchedFor] = useState<string | null>(null)
  const [btFiles, setBtFiles] = useState<Array<{ file: string; mtime: number; size: number }>>([])
  const [btFilesLoading, setBtFilesLoading] = useState<boolean>(false)
  // Live trades refresh state
  const [liveTrades, setLiveTrades] = useState<any[]>([])
  const [liveTradesLoading, setLiveTradesLoading] = useState<boolean>(false)
  const [liveTradesError, setLiveTradesError] = useState<string | null>(null)
  const [liveOpenOrders, setLiveOpenOrders] = useState<any[]>([])
  const [liveOrdersError, setLiveOrdersError] = useState<string | null>(null)
  const [liveSubTab, setLiveSubTab] = useState<'trades' | 'orders' | 'history' | 'performance'>('trades')
  const [liveRefreshKey, setLiveRefreshKey] = useState<number>(0)
  const [livePollSec, setLivePollSec] = useState<number>(1)

  // History & Performance state
  const [historyTrades, setHistoryTrades] = useState<any[]>([])
  const [historyLoading, setHistoryLoading] = useState<boolean>(false)
  const [historyError, setHistoryError] = useState<string | null>(null)
  const [historyDetails, setHistoryDetails] = useState<Record<string | number, any>>({})
  const [perfByPair, setPerfByPair] = useState<any[]>([])
  const [profitSummary, setProfitSummary] = useState<any | null>(null)
  const [historyResetting, setHistoryResetting] = useState<boolean>(false)

  // ✅ Selections
  const [bsSelection, setBsSelection] = useState<BackstageSelection>({ pair: 'BTC/USDT', timerange: '-30d' })
  const [livePair, setLivePair] = useState<string | null>(null)
  const [liveTf, setLiveTf] = useState<string | null>(null)

  // View tabs under the configuration panel
  const [viewTab, setViewTab] = useState<'live'>('live')
  
  // Helpers to persist per-bot UI state
  const viewTabKey = (botId?: number | null) => (botId ? `botViewTab:${botId}` : 'botViewTab')
  const bsSelKey = (botId?: number | null) => (botId ? `backstageSel:${botId}` : 'backstageSel')

  // Format backend/API errors into a readable string (avoids "[object Object]")
  const formatError = (val: any): string => {
    if (val == null) return 'Unknown error'
    if (typeof val === 'string') return val
    if (typeof val === 'object') {
      const cand = (val as any)
      const tryFields = [cand.detail, cand.message, cand.error, cand.msg, cand.reason, cand.title]
      const fld = tryFields.find((v) => typeof v === 'string' && v.length > 0)
      if (fld) return fld as string
      try {
        const s = JSON.stringify(val)
        return s && s !== '{}' ? s : String(val)
      } catch {
        return String(val)
      }
    }
    return String(val)
  }

  const extractError = (e: any): string => {
    const sources = [
      e?.response?.data?.detail,
      e?.response?.data?.error,
      e?.response?.data?.message,
      e?.response?.data,
      e?.message,
      e,
    ]
    for (const s of sources) {
      const m = formatError(s)
      if (m && m !== '[object Object]' && m !== '{}' && m !== 'undefined') return m
    }
    return 'Unexpected error'
  }

  // Restore per-bot persisted UI state when selecting a bot
  useEffect(() => {
    if (!selectedId) return
    try {
      const vt = localStorage.getItem(viewTabKey(selectedId)) as 'live' | null
      if (vt === 'live') setViewTab(vt)
    } catch {}
    try {
      const raw = localStorage.getItem(bsSelKey(selectedId))
      if (raw) {
        const parsed = JSON.parse(raw)
        if (parsed && typeof parsed === 'object') {
          setBsSelection({
            pair: parsed.pair ?? 'BTC/USDT',
            timerange: parsed.timerange ?? '-30d',
          })
        }
      }
    } catch {}
  }, [selectedId])

  // Persist viewTab and Backstage selection on change
  useEffect(() => {
    if (!selectedId) return
    try { localStorage.setItem(viewTabKey(selectedId), viewTab) } catch {}
  }, [viewTab, selectedId])
  useEffect(() => {
    if (!selectedId || !bsSelection) return
    try { localStorage.setItem(bsSelKey(selectedId), JSON.stringify(bsSelection)) } catch {}
  }, [bsSelection, selectedId])

  // Fetch status + runtime + config for each bot on page load (and when bots list changes)
  useEffect(() => {
    const run = async () => {
      if (!userId || bots.length === 0) return
      // mark all as loading
      setDetails(prev => {
        const next = { ...prev }
        bots.forEach(b => { next[b.id] = { ...(next[b.id] || {}), loading: true, error: null } })
        return next
      })
      await Promise.allSettled(bots.map(async (b) => {
        try {
          const [stRes, rtRes, cfgRes] = await Promise.all([
            api.get(`/users/${userId}/bots/${b.id}/status`),
            api.get(`/users/${userId}/bots/${b.id}/runtime`),
            api.get(`/config/bot/${b.id}`),
          ])
          setDetails(prev => ({
            ...prev,
            [b.id]: {
              status: stRes.data as BotStatusPayload,
              runtime: rtRes.data as BotRuntimeInfo,
              config: cfgRes.data,
              loading: false,
              error: null,
            },
          }))
        } catch (e: any) {
          const msg = e?.response?.data?.detail || e?.message || 'Failed to load bot info'
          setDetails(prev => ({ ...prev, [b.id]: { ...(prev[b.id] || {}), loading: false, error: String(msg) } }))
        }
      }))
    }
    run()
  }, [userId, bots])

  const selected = useMemo(() => bots.find(b => b.id === selectedId) || null, [bots, selectedId])

  // Hydrate form from selected bot details
  useEffect(() => {
    const b = selected
    if (!b) return
    const cfg = details[b.id]?.config || {}
    const mode = b.mode || 'dryrun'
    setFormMode(String(mode))
    setFormStakeCurrency(String(cfg.stake_currency ?? 'USDT'))
    setFormStakeAmount(String(cfg.stake_amount ?? '10'))
    const srcPairs: string[] = Array.isArray(cfg.pair_whitelist)
      ? cfg.pair_whitelist
      : (Array.isArray(cfg.pairs) ? cfg.pairs : [])
    setFormPairsText(srcPairs.join(', '))
    setFormTradingMode((cfg.trading_mode as 'spot' | 'futures') || 'spot')
    setFormMarginMode(String(cfg.margin_mode ?? 'cross'))
    setFormLiquidationBuffer(String(cfg.liquidation_buffer ?? '0.0'))
  setFormLeverage(Number(cfg.leverage ?? 1) || 1)
  setFormDryRunWallet(String(cfg.dry_run_wallet ?? ''))
    const act = cfg?.strategy as any
    setFormStrategyName(String(act ?? ''))
  }, [selected, details])

  // Load strategies list for selection
  useEffect(() => {
    const run = async () => {
      if (!userId || !selected) return
      try {
        const res = await api.get(`/users/${userId}/strategies`)
        const arr = Array.isArray(res.data) ? res.data : []
        // Backend returns a list of strategy names (strings). Normalize to objects with a name field.
        const normalized = arr.map((it: any) => (typeof it === 'string' ? { name: it } : it))
        setStrategies(normalized)
      } catch (e) {
        // ignore silently; dropdown will be empty
      }
    }
    run()
  }, [userId, selected?.id])

  const handleCreateBot = async (values: CreateBotFormValues) => {
    if (!userId) return
    setCreating(true)
    setCreateError(null)
    try {
      const res = await api.post(`/users/${userId}/bots`, values)
      const created = res.data
      // Refresh bots list
      await loadBots(userId)
      setShowCreate(false)
      if (created?.id) setSelectedId(created.id)
      notifySuccess('Bot created successfully')
    } catch (e: any) {
      const msg = extractError(e) || 'Failed to create bot'
      setCreateError(msg)
      notifyError(msg)
    } finally {
      setCreating(false)
    }
  }

  const refreshBotDetails = async (botId: number) => {
    if (!userId) return
    try {
      setDetails(prev => ({ ...prev, [botId]: { ...(prev[botId] || {}), loading: true, error: null } }))
      const [stRes, rtRes, cfgRes] = await Promise.all([
        api.get(`/users/${userId}/bots/${botId}/status`),
        api.get(`/users/${userId}/bots/${botId}/runtime`),
        api.get(`/config/bot/${botId}`),
      ])
      setDetails(prev => ({
        ...prev,
        [botId]: {
          status: stRes.data as BotStatusPayload,
          runtime: rtRes.data as BotRuntimeInfo,
          config: cfgRes.data,
          loading: false,
          error: null,
        },
      }))
    } catch (e: any) {
      const msg = extractError(e) || 'Failed to load bot info'
      setDetails(prev => ({ ...prev, [botId]: { ...(prev[botId] || {}), loading: false, error: msg } }))
    }
  }

  const handleStartBot = async (botId: number) => {
    if (!userId) return
    setDetails(prev => ({ ...prev, [botId]: { ...(prev[botId] || {}), starting: true, error: null } }))
    try {
      await api.post(`/users/${userId}/bots/${botId}/start`)
      await refreshBotDetails(botId)
      notifySuccess('Bot started')
    } catch (e: any) {
      const msg = extractError(e) || 'Failed to start bot'
      setDetails(prev => ({ ...prev, [botId]: { ...(prev[botId] || {}), error: msg } }))
      notifyError(msg)
    } finally {
      setDetails(prev => ({ ...prev, [botId]: { ...(prev[botId] || {}), starting: false } }))
    }
  }

  const handleStopBot = async (botId: number) => {
    if (!userId) return
    setDetails(prev => ({ ...prev, [botId]: { ...(prev[botId] || {}), stopping: true, error: null } }))
    try {
      await api.post(`/users/${userId}/bots/${botId}/stop`)
      await refreshBotDetails(botId)
      notifySuccess('Bot stopped')
    } catch (e: any) {
      const msg = extractError(e) || 'Failed to stop bot'
      setDetails(prev => ({ ...prev, [botId]: { ...(prev[botId] || {}), error: msg } }))
      notifyError(msg)
    } finally {
      setDetails(prev => ({ ...prev, [botId]: { ...(prev[botId] || {}), stopping: false } }))
    }
  }

  const handleDeleteBot = async (botId: number) => {
    if (!userId) return
    const ok = window.confirm('Are you sure you want to delete this bot? This cannot be undone.')
    if (!ok) return
    setDetails(prev => ({ ...prev, [botId]: { ...(prev[botId] || {}), deleting: true, error: null } }))
    try {
      await api.delete(`/users/${userId}/bots/${botId}`)
      await loadBots(userId)
      // If the deleted bot was selected, clear selection so effect picks the first available
      setDetails(prev => {
        const next = { ...prev }
        delete next[botId]
        return next
      })
      if (selectedId === botId) {
        setSelectedId(null)
      }
      notifySuccess('Bot deleted')
    } catch (e: any) {
      const msg = extractError(e) || 'Failed to delete bot'
      setDetails(prev => ({ ...prev, [botId]: { ...(prev[botId] || {}), error: msg } }))
      notifyError(msg)
    } finally {
      setDetails(prev => ({ ...prev, [botId]: { ...(prev[botId] || {}), deleting: false } }))
    }
  }

  const handleSaveConfig = async (botId: number) => {
    if (!userId) return
    try {
      // Mode update if changed
      const bot = bots.find(b => b.id === botId)
      if (bot && (bot.mode || 'dryrun') !== formMode) {
        await api.patch(`/users/${userId}/bots/${botId}/mode`, { mode: formMode })
      }
      // Prepare non-strategy config payload
      const pairs = formPairsText
        .split(/[\n,]/)
        .map(s => s.trim().toUpperCase())
        .filter(Boolean)
      const payload: any = {
        stake_currency: formStakeCurrency,
        stake_amount: isNaN(Number(formStakeAmount)) ? formStakeAmount : Number(formStakeAmount),
        pair_whitelist: pairs,
        trading_mode: formTradingMode,
      }
      if (formTradingMode === 'futures') {
        if (formMarginMode) payload.margin_mode = formMarginMode
        if (formLiquidationBuffer) payload.liquidation_buffer = Number(formLiquidationBuffer)
        if (formLeverage) payload.leverage = formLeverage
      }
      // dry_run_wallet applies only to dryrun mode; allow numeric or leave string (e.g. mapping JSON in future)
      if (bot?.mode === 'dryrun' && formDryRunWallet.trim()) {
        const raw = formDryRunWallet.trim()
        const num = Number(raw)
        payload.dry_run_wallet = isNaN(num) ? raw : num
      }
  await api.patch(`/users/${userId}/bots/${botId}/config`, payload)
      // Strategy update if changed
      const botAct = (bot as any)?.strategy || ''
      const curName = botAct || ''
      if (formStrategyName !== curName) {
        const body = { strategy: formStrategyName || null }
        await api.patch(`/users/${userId}/bots/${botId}/strategy`, body)
      }
      await refreshBotDetails(botId)
      notifySuccess('Configuration saved')
    } catch (e: any) {
      notifyError(extractError(e) || 'Failed to save configuration')
    }
  }

  // live trades now sourced from snapshot via LiveAnalyticsContainer -> onOpenTrades callback

  // Toggle bot run mode (dryrun/live). Disable while running; requires Stop first.
  const handleSetRunMode = async (botId: number, mode: 'dryrun' | 'live') => {
    if (!userId) return
    const d = details[botId]
    const running = !!d?.runtime?.running
    if (running) {
      notifyError('Stop the bot before changing run mode')
      return
    }
    try {
      await api.patch(`/users/${userId}/bots/${botId}/mode`, { mode })
      await refreshBotDetails(botId)
      notifySuccess(`Mode set to ${mode}`)
    } catch (e: any) {
      notifyError(extractError(e) || 'Failed to set mode')
    }
  }

  // Fetchers for logs and backtest status
  const fetchRuntimeLogs = async (botId: number, tail = rtTail) => {
    if (!userId) return
    try {
      const res = await api.get(`/users/${userId}/bots/${botId}/logs`, { params: { tail } })
      const lines: string[] = Array.isArray(res.data?.lines) ? res.data.lines : []
      setRuntimeLogs(lines)
    } catch {}
  }

  // Derive open orders directly from snapshot open_trades (via LiveAnalyticsContainer -> onOpenTrades)
  useEffect(() => {
    try {
      const out: any[] = []
      const trades = Array.isArray(liveTrades) ? liveTrades : []
      for (const t of trades) {
        const tradeId = t?.trade_id ?? t?.id ?? t?.tradeId
        const orders = Array.isArray(t?.orders) ? t.orders : []
        for (const o of orders) {
          const status = String(o?.status ?? o?.order_status ?? '').toLowerCase()
          const isOpen = status === 'open' || o?.is_open === true
          if (isOpen) {
            out.push({ ...o, trade_id: tradeId, pair: o?.pair || t?.pair })
          }
        }
      }

      setLiveOpenOrders(out)
      setLiveOrdersError(null)
    } catch {
      // leave as-is on parse error
    }
  }, [liveTrades])

  const cancelOpenOrder = async (botId: number, tradeId: number | string) => {
    if (!userId || tradeId == null) return
    try {
      await api.delete(`/users/${userId}/bots/${botId}/proxy/freqtrade/trades/${tradeId}/open-order`)
      // Optimistically update UI and force an immediate snapshot refresh
      setLiveOpenOrders(prev => prev.filter(o => (o?.trade_id ?? o?.tradeId ?? o?.trade) !== tradeId))
      setLiveRefreshKey(k => k + 1)
      notifySuccess('Order canceled')
    } catch (e: any) {
      notifyError(e?.response?.data?.detail || e?.message || 'Failed to cancel order')
    }
  }

  // Trades History & Performance fetchers
  const fetchTradesHistory = async (botId: number, limit = 500) => {
    if (!userId || !selected) return
    setHistoryLoading(true)
    setHistoryError(null)
    try {
      // Use backend route reading SQLite directly; mode follows selected bot mode
      const mode = String(selected.mode || 'all').toLowerCase()
      const res = await api.get(`/users/${userId}/bots/${botId}/trades-history`, { params: { mode, limit } })
      const arr = Array.isArray(res.data) ? res.data : []
      setHistoryTrades(arr)
    } catch (e: any) {
      setHistoryError(extractError(e))
      setHistoryTrades([])
    } finally {
      setHistoryLoading(false)
    }
  }

  const loadTradeDetails = async (botId: number, tradeId: number | string) => {
    if (!userId || tradeId == null) return
    try {
      // Normalize id when coming from SQLite (e.g., 'dryrun:123')
      const tid = (typeof tradeId === 'string' && tradeId.includes(':')) ? (tradeId.split(':').pop() || tradeId) : tradeId
      const res = await api.get(`/users/${userId}/bots/${botId}/proxy/freqtrade/trade/${tid}`)
      setHistoryDetails(prev => ({ ...prev, [tradeId]: res.data }))
    } catch (e) {
      // keep silent; user can retry
    }
  }

  const fetchPerformance = async (botId: number) => {
    if (!userId) return
    try {
      const res = await api.get(`/users/${userId}/bots/${botId}/proxy/freqtrade/performance`)
      const arr = Array.isArray(res.data) ? res.data : (Array.isArray(res.data?.performance) ? res.data.performance : [])
      setPerfByPair(arr)
    } catch (e) {
      setPerfByPair([])
    }
  }

  const fetchProfit = async (botId: number) => {
    if (!userId) return
    try {
      const res = await api.get(`/users/${userId}/bots/${botId}/proxy/freqtrade/profit`)
      setProfitSummary(res.data || null)
    } catch (e) {
      setProfitSummary(null)
    }
  }

  const resetDryrunTrades = async (botId: number) => {
    if (!userId || !selected) return
    if (String(selected.mode).toLowerCase() !== 'dryrun') {
      notifyError('Reset is only available in dryrun mode')
      return
    }
    const running = !!details[botId]?.runtime?.running
    if (running) {
      notifyError('Stop the bot before resetting dryrun trades')
      return
    }
    const ok = window.confirm('Delete ALL dryrun trades and performance data? This cannot be undone.')
    if (!ok) return
    try {
      setHistoryResetting(true)
      const res = await api.post(`/users/${userId}/bots/${botId}/dryrun/reset`)
      const removed = Array.isArray(res.data?.removed) ? res.data.removed : []
      if (removed.length === 0) {
        notifyError('Dryrun reset did not remove any DB files. Ensure the bot is stopped and try again.')
      } else {
        notifySuccess('Dryrun trades reset')
      }
      setHistoryDetails({})
      await fetchTradesHistory(botId)
      // Refresh performance summary as well
      await fetchPerformance(botId)
      await fetchProfit(botId)
    } catch (e: any) {
      notifyError(extractError(e) || 'Failed to reset dryrun trades')
    } finally {
      setHistoryResetting(false)
    }
  }

  // Fetch history/performance when tab changes
  useEffect(() => {
    if (!selected) return
    if (liveSubTab === 'history') {
      fetchTradesHistory(selected.id)
    } else if (liveSubTab === 'performance') {
      fetchPerformance(selected.id)
      fetchProfit(selected.id)
    }
  }, [liveSubTab, selected?.id])

  // Fallback: derive performance summary from history when API returns empty/zeros
  useEffect(() => {
    try {
      const rows = Array.isArray(historyTrades) ? historyTrades : []
      if (!rows.length) return
      // Closed trades only
      const closed = rows.filter(r => String(r.status || '').toLowerCase() === 'closed' || !!r.close_date)
      if (!closed.length) return
      const sumAbs = closed.reduce((acc, r) => acc + Number((r.profit_abs ?? r.close_profit_abs ?? r.realized_profit ?? 0)), 0)
      const ratios: number[] = closed.map(r => Number((r.profit_ratio ?? r.close_profit ?? 0))).filter(n => !isNaN(n))
      const avgRatio = ratios.length ? (ratios.reduce((a, b) => a + b, 0) / ratios.length) : 0
      // Avg duration (ms)
      const durationsMs: number[] = closed.map(r => {
        try {
          const od = r.open_date ? new Date(r.open_date).getTime() : NaN
          const cd = r.close_date ? new Date(r.close_date).getTime() : NaN
          return (!isNaN(od) && !isNaN(cd)) ? Math.max(0, cd - od) : NaN
        } catch {
          return NaN
        }
      }).filter(n => !isNaN(n) && isFinite(n))
      const avgMs = durationsMs.length ? (durationsMs.reduce((a,b)=>a+b,0) / durationsMs.length) : 0
      const avgDuration = avgMs ? `${Math.round(avgMs/3600000)}h ${Math.round((avgMs%3600000)/60000)}m` : '-'
      const derivedSummary = {
        profit_abs: sumAbs,
        profit_ratio: avgRatio,
        total_trades: closed.length,
        avg_profit_ratio: avgRatio,
        avg_duration: avgDuration,
      }
      // Only update if API summary is missing or zeros
      const ps = profitSummary
      const isMissing = !ps
      if (isMissing) setProfitSummary(derivedSummary)
      // Derive per-pair performance when API is empty
      if ((!perfByPair || perfByPair.length === 0)) {
        const byPair: Record<string, { profit_abs: number; profit_ratio_sum: number; count: number }> = {}
        for (const r of closed) {
          const p = String(r.pair || '-')
          const pa = Number((r.profit_abs ?? r.close_profit_abs ?? r.realized_profit ?? 0)) || 0
          const pr = Number((r.profit_ratio ?? r.close_profit ?? 0)) || 0
          byPair[p] = byPair[p] || { profit_abs: 0, profit_ratio_sum: 0, count: 0 }
          byPair[p].profit_abs += pa
          byPair[p].profit_ratio_sum += pr
          byPair[p].count += 1
        }
        const derivedPerf = Object.entries(byPair).map(([pair, v]) => ({
          pair,
          profit_abs: v.profit_abs,
          profit_ratio: v.count ? v.profit_ratio_sum / v.count : 0,
          trades: v.count,
        }))
        setPerfByPair(derivedPerf)
      }
    } catch {}
  }, [historyTrades])
  const closeTrade = async (botId: number, tradeId: number | string, mode: 'market' | 'limit') => {
    if (!userId || tradeId == null) return
    try {
      // Canonical Freqtrade endpoint: POST /api/v1/forceexit
      // Params: tradeid, ordertype ('market' | 'limit'), [amount]
      await api.post(`/users/${userId}/bots/${botId}/proxy/freqtrade/forceexit`, {
        tradeid: tradeId,
        ordertype: mode,
      })
      // Optimistic UI: remove trade from list and refresh snapshot
      setLiveTrades(prev => prev.filter(t => (t?.trade_id ?? t?.id ?? t?.tradeId) !== tradeId))
      setLiveRefreshKey(k => k + 1)
      notifySuccess(`Trade closed by ${mode}`)
    } catch (e: any) {
      notifyError(e?.response?.data?.detail || e?.message || `Failed to close trade (${mode})`)
    }
  }

  const deleteTrade = async (botId: number, tradeId: number | string) => {
    if (!userId || tradeId == null) return
    const ok = window.confirm('Delete this trade from bot state? This cannot be undone.')
    if (!ok) return
    const tryPaths: Array<string> = [
      `/users/${userId}/bots/${botId}/proxy/freqtrade/trades/${tradeId}`,
      `/users/${userId}/bots/${botId}/proxy/freqtrade/trades/${tradeId}/delete`,
    ]
    let lastErr: any = null
    for (const path of tryPaths) {
      try {
        await api.delete(path)
        setLiveTrades(prev => prev.filter(t => (t?.trade_id ?? t?.id ?? t?.tradeId) !== tradeId))
        setLiveRefreshKey(k => k + 1)
        notifySuccess('Trade deleted')
        return
      } catch (e: any) {
        lastErr = e
        const code = e?.response?.status
        if (code !== 405 && code !== 404) break
      }
    }
    notifyError(lastErr?.response?.data?.detail || lastErr?.message || 'Failed to delete trade')
  }

  const closeAllTrades = async (botId: number, mode: 'market' | 'limit') => {
    if (!userId) return
    const ok = window.confirm(`Close ALL open trades by ${mode}?`)
    if (!ok) return
    try {
      // Canonical bulk-close: POST /api/v1/forceexit with tradeid='all'
      await api.post(`/users/${userId}/bots/${botId}/proxy/freqtrade/forceexit`, {
        tradeid: 'all',
        ordertype: mode,
      })
      setLiveTrades([])
      setLiveRefreshKey(k => k + 1)
      notifySuccess(`All trades closed by ${mode}`)
    } catch (e: any) {
      notifyError(e?.response?.data?.detail || e?.message || `Failed to close all trades (${mode})`)
    }
  }


  // Backstage polling removed per revert

  // Reset backtest UI bits when switching selection
  useEffect(() => {
    setBtTimerange('')
    setBtResultsFetchedFor(null)
    setBtStarting(false)
    setBtFromDate('')
    setBtToDate('')
  }, [selectedId])

  // Backstage auto-fetch removed per revert

  // ✅ init live/backstage selections when bot/config available
  useEffect(() => {
    if (!selected) return
    const cfg = details[selected.id]?.config || {}
    const ps = cfgPairs(cfg)
    const tfs = cfgTimeframes(cfg)
    console.log(cfg)
    setLivePair(prev => {
      if (!ps.length) return null
      if (!prev) return ps[0]
      return ps.includes(prev) ? prev : ps[0]
    })
    setLiveTf(prev => {
      if (!tfs.length) return null
      if (!prev) return tfs[0]
      return tfs.includes(prev) ? prev : tfs[0]
    })

    setBsSelection(prev => ({
      pair: prev?.pair ?? ps[0],
      timerange: prev?.timerange ?? '-30d',
    }))
  }, [selected?.id, details[selected?.id || -1]?.config])

  return (
    <div >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
        <h2 style={{ margin: 0 }}>Bots</h2>
        <button
          onClick={() => setShowCreate(true)}
          style={{ padding: '8px 12px', borderRadius: 6, border: '1px solid #2563eb', background: '#2563eb', color: '#fff', cursor: 'pointer' }}
        >
          + Create Bot
        </button>
      </div>
      {/* Create Bot Modal */}
      {showCreate && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 40 }}>
          <div style={{ background: '#fff', borderRadius: 10, padding: 16, width: 'min(92vw, 520px)', boxShadow: '0 10px 30px rgba(0,0,0,0.2)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
              <h3 style={{ margin: 0 }}>Create a new bot</h3>
              <button onClick={() => setShowCreate(false)} style={{ border: 'none', background: 'transparent', fontSize: 20, lineHeight: 1, cursor: 'pointer' }}>&times;</button>
            </div>
            <CreateBotForm
              onSubmit={handleCreateBot}
              onCancel={() => setShowCreate(false)}
              submitting={creating}
            />
            {createError && <div style={{ marginTop: 10, color: '#dc2626' }}>{createError}</div>}
          </div>
        </div>
      )}
      {bots.length === 0 ? (
        <div>No bots yet.</div>
      ) : (
        <div>
          {/* Tabs */}
          <div style={{ display: 'flex', gap: 8, borderBottom: '1px solid #e5e7eb', marginBottom: 12, flexWrap:'wrap' }}>
            {bots.map(b => (
              <button
                key={b.id}
                onClick={() => setSelectedId(b.id)}
                style={{
                  padding: '8px 12px',
                  border: '1px solid #e5e7eb',
                  borderBottom: selectedId === b.id ? '2px solid #3b82f6' : '1px solid #e5e7eb',
                  borderRadius: '6px 6px 0 0',
                  background: selectedId === b.id ? '#f0f7ff' : '#fff',
                  cursor: 'pointer',
                }}
              >
                {b.name}
              </button>
            ))}
          </div>
          {/* Selected bot panel */}
          {selected && (
            <div style={{ border: '1px solid #e5e7eb', borderRadius: 8, padding: 12 }}>
              {/* Actions (Delete only; Start/Stop moved into Live tab) */}
              <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginBottom: 10, flexWrap: 'wrap' }}>
                <div>{selected.id}-{selected.name}</div><div></div>
                {(() => {
                  const d = details[selected.id]
                  const starting = !!d?.starting
                  const stopping = !!d?.stopping
                  const deleting = !!d?.deleting
                  return (
                    <>
                      <button
                        onClick={() => handleDeleteBot(selected.id)}
                        disabled={starting || stopping || deleting}
                        style={{ padding: '6px 10px', borderRadius: 6, border: '1px solid #6b7280', background: deleting ? '#f3f4f6' : '#fff', color: '#374151', cursor: starting || stopping || deleting ? 'not-allowed' : 'pointer' }}
                      >
                        {deleting ? 'Deleting…' : 'Delete'}
                      </button>
                    </>
                  )
                })()}
              </div>
              {/* Configuration editor */}
              <div style={{ marginTop: 16, paddingTop: 12, borderTop: '1px solid #e5e7eb' }}>
                <h4 style={{ margin: '0 0 8px 0' }}>Configuration</h4>
                {(() => {
                  const running = !!details[selected.id]?.runtime?.running
                  const mode = String(selected.mode || '').toLowerCase()
                  const locked = running && (mode === 'live' || mode === 'dryrun')
                  const disabledProps = { disabled: locked }
                  return (
                <>
                <div style={{ display: 'grid', gridTemplateColumns: '160px 1fr', rowGap: 8, columnGap: 12 }}>
                  {/* Strategy selection */}
                  <label><strong>Strategy</strong></label>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                    <select {...disabledProps} value={formStrategyName} onChange={(e) => setFormStrategyName(e.target.value)} style={{ padding: 6, borderRadius: 6, border: '1px solid #e5e7eb' }}>
                      <option value="">-- select by name --</option>
                      {strategies ? strategies.map((s) => (
                        <option className='sss' key={s.name} value={s.name}>{s.name}</option>
                      )) : null}
                    </select>
                    <input
                      placeholder="or enter class path"
                      value={formStrategyClazz}
                      onChange={(e) => setFormStrategyClazz(e.target.value)} {...disabledProps}
                      style={{ padding: 6, borderRadius: 6, border: '1px solid #e5e7eb', flex: 1 }}
                    />
                  </div>

                  <label><strong>Trading Mode</strong></label>
                  <select {...disabledProps} value={formTradingMode} onChange={(e) => setFormTradingMode(e.target.value as any)} style={{ padding: 6, borderRadius: 6, border: '1px solid #e5e7eb' }}>
                    <option value="spot">spot</option>
                    <option value="futures">futures</option>
                  </select>

                  {formTradingMode === 'futures' && (
                    <>
                      <label><strong>Margin Mode</strong></label>
                      <select {...disabledProps} value={formMarginMode} onChange={(e) => setFormMarginMode(e.target.value)} style={{ padding: 6, borderRadius: 6, border: '1px solid #e5e7eb' }}>
                        <option value="cross">cross</option>
                        <option value="isolated">isolated</option>
                      </select>

                      <label><strong>Liquidation Buffer</strong></label>
                      <input {...disabledProps} value={formLiquidationBuffer} onChange={(e) => setFormLiquidationBuffer(e.target.value)} style={{ padding: 6, borderRadius: 6, border: '1px solid #e5e7eb' }} />

                      <label><strong>Leverage (1-25)</strong></label>
                      <input
                        type="number"
                        min={1}
                        max={25}
                        step={1}
                        {...disabledProps}
                        value={formLeverage}
                        onChange={(e) => setFormLeverage(Math.max(1, Math.min(25, Number(e.target.value) || 1)))}
                        style={{ padding: 6, borderRadius: 6, border: '1px solid #e5e7eb' }}
                      />
                    </>
                  )}

                  <label><strong>Stake Currency</strong></label>
                  <input {...disabledProps} value={formStakeCurrency} onChange={(e) => setFormStakeCurrency(e.target.value)} style={{ padding: 6, borderRadius: 6, border: '1px solid #e5e7eb' }} />

                  <label><strong>Stake Amount</strong></label>
                  <input {...disabledProps} value={formStakeAmount} onChange={(e) => setFormStakeAmount(e.target.value)} style={{ padding: 6, borderRadius: 6, border: '1px solid #e5e7eb' }} />

                  {selected?.mode === 'dryrun' && (
                    <>
                      <label><strong>Dry-run Wallet</strong></label>
                      <input
                        {...disabledProps}
                        value={formDryRunWallet}
                        onChange={(e) => setFormDryRunWallet(e.target.value)}
                        placeholder="e.g. 1000"
                        style={{ padding: 6, borderRadius: 6, border: '1px solid #e5e7eb' }}
                      />
                    </>
                  )}

                  <label><strong>Pair Whitelist</strong></label>
                  <textarea {...disabledProps} value={formPairsText} onChange={(e) => setFormPairsText(e.target.value)} rows={3} placeholder="BTC/USDT, ETH/USDT" style={{ padding: 6, borderRadius: 6, border: '1px solid #e5e7eb', resize: 'vertical' }} />
                </div>
                <div style={{ marginTop: 10, display: 'flex', justifyContent: 'flex-end' }}>
                  <button disabled={locked} onClick={() => handleSaveConfig(selected.id)} style={{ padding: '8px 12px', borderRadius: 6, border: '1px solid #2563eb', background: locked ? '#dbeafe' : '#2563eb', color: '#fff', cursor: locked ? 'not-allowed' : 'pointer' }}>
                    Save Configuration
                  </button>
                </div>
                </>
                  )
                })()}
              </div>

              {/* Analytics tabbed view */}
              <div style={{ marginTop: 16, paddingTop: 12, borderTop: '1px solid #e5e7eb' }}>
                <div style={{ display: 'flex', gap: 8, marginBottom: 10, borderBottom: '1px solid #e5e7eb' }}>
                  <button style={{ padding: '6px 10px', borderRadius: '6px 6px 0 0', border: '1px solid #e5e7eb', borderBottom: '2px solid #3b82f6', background: '#f0f7ff' }}>Live/Dryrun</button>
                </div>

                {viewTab === 'live' && (
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
                      <h4 style={{ margin: '0 0 8px 0' }}>Live/Dryrun Analytics</h4>
                      {(() => {
                        const d = details[selected.id]
                        const running = !!d?.runtime?.running
                        const starting = !!d?.starting
                        const stopping = !!d?.stopping
                        return (
                          <div style={{ display: 'inline-flex', gap: 8, alignItems: 'center' }}>
                            {/* Run mode toggle */}
                            <div style={{ display: 'inline-flex', gap: 6, alignItems: 'center', border: '1px solid #e5e7eb', borderRadius: 6, padding: '2px 4px' }}>
                              <button
                                onClick={() => handleSetRunMode(selected.id, 'dryrun')}
                                disabled={running}
                                style={{ padding: '4px 8px', borderRadius: 4, border: '1px solid #e5e7eb', background: (selected.mode === 'dryrun') ? '#eef2ff' : '#fff' }}
                              >
                                Dryrun
                              </button>
                              <button
                                onClick={() => handleSetRunMode(selected.id, 'live')}
                                disabled={running}
                                style={{ padding: '4px 8px', borderRadius: 4, border: '1px solid #e5e7eb', background: (selected.mode === 'live') ? '#eef2ff' : '#fff' }}
                              >
                                Live
                              </button>
                            </div>
                            {!running ? (
                              <button
                                onClick={() => handleStartBot(selected.id)}
                                disabled={starting}
                                style={{ padding: '6px 10px', borderRadius: 6, border: '1px solid #16a34a', background: starting ? '#dcfce7' : '#16a34a', color: '#fff' }}
                              >
                                {starting ? 'Starting…' : 'Start Dryrun/Live'}
                              </button>
                            ) : (
                              <button
                                onClick={() => handleStopBot(selected.id)}
                                disabled={stopping}
                                style={{ padding: '6px 10px', borderRadius: 6, border: '1px solid #ef4444', background: stopping ? '#fee2e2' : '#ef4444', color: '#fff' }}
                              >
                                {stopping ? 'Stopping…' : 'Stop'}
                              </button>
                            )}
                            {/* Polling interval selector for live updates */}
                            <div style={{ display: 'inline-flex', gap: 6, alignItems: 'center', border: '1px solid #e5e7eb', borderRadius: 6, padding: '2px 4px' }}>
                              <label style={{ fontSize: 12, color: '#374151' }}>Update:</label>
                              <select value={livePollSec} onChange={(e) => setLivePollSec(Number(e.target.value))} style={{ padding: '4px 6px', borderRadius: 6, border: '1px solid #e5e7eb' }}>
                                {[1,5,10,30].map(sec => <option key={sec} value={sec}>{sec}s</option>)}
                              </select>
                            </div>
                            {/* Freqtrade bot controls */}
                            <BotControls userId={userId!} botId={selected.id} />
                          </div>
                        )
                      })()}
                    </div>

                    {/* Live selectors */}
                    {(() => {
                      const cfg = details[selected.id]?.config || {}
                      // Live tab: show configured pairs from bot config
                      const ps = cfgPairs(cfg)
                      const tfs = liveTf
                      const PairTabs = (
                        ps.length > 1 && (
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 8 }}>
                            {ps.map((p: string) => (
                              <button key={p}
                                onClick={() => { setLivePair(p); }}
                                style={{ padding: '4px 8px', borderRadius: 6, border: '1px solid #e5e7eb', background: livePair === p ? '#eef2ff' : '#fff', cursor: 'pointer' }}>
                                {p}
                              </button>
                            ))}
                          </div>
                        )
                      )

                      const TfTabs = (
                        tfs ? (
                          <div style={{ fontSize: 14 ,letterSpacing: '0.0em' }}>
                            {tfs ? (
                              <p style={{ display: 'inline-block', padding: '4px 8px', borderRadius: 6, color: '#6b7280' }}>
                                Timeframe: <span style={{color:'black', fontWeight:'600'}}>{tfs}</span>
                              </p>
                            ) : (
                              <p style={{ display: 'inline-block', padding: '4px 8px', borderRadius: 6, color: '#dc2626' }}>No timeframe configured</p>
                            )}
                          </div>
                        ) : null
                      )

                      return (
                        <>
                          {PairTabs}
                          {TfTabs}
                        </>
                      )
                    })()}
  
  <div>{details[selected.id]!==null? details[selected.id]?.runtime?.running?.toString() : null}</div>
  
  
       
       {/* Chart */}
                    <LiveAnalyticsContainer
                      key={liveRefreshKey}
                      userId={userId ?? undefined}
                      botId={selected.id}
                      pair={livePair ?? undefined}
                      timeframe={liveTf ?? undefined}
                      showSelectors={false}
                      enabled={!!details[selected.id]?.runtime?.running}
                      pollingSec={livePollSec}
                      onOpenTrades={(t) => setLiveTrades(Array.isArray(t) ? t : [])}
                    />

                  <TradesTab
                    setLiveSubTab={setLiveSubTab}
                    cancelOpenOrder={cancelOpenOrder}
                    selected={selected}
                    liveTrades={liveTrades}
                    liveTradesError={liveTradesError}
                    liveSubTab={liveSubTab}
                    liveTradesLoading={liveTradesLoading}
                    liveOpenOrders={liveOpenOrders}
                    liveOrdersError={liveOrdersError}
                    setLiveRefreshKey={setLiveRefreshKey}
                    closeTrade={closeTrade}
                    deleteTrade={deleteTrade}
                    closeAllTrades={closeAllTrades}
                    historyTrades={historyTrades}
                    historyLoading={historyLoading}
                    historyError={historyError}
                    historyDetails={historyDetails}
                    loadTradeDetails={loadTradeDetails}
                    resetDryrunTrades={resetDryrunTrades}
                    historyResetting={historyResetting}
                    perfByPair={perfByPair}
                    profitSummary={profitSummary}
                  />
                  </div>

                  
                )}

                {/* Backstage tab removed per revert */}
              </div>

              

              {/* Runtime Logs */}
              <div style={{ marginTop: 16, paddingTop: 12, borderTop: '1px solid #e5e7eb' }}>
                <h4 style={{ margin: '0 0 8px 0' }}>Runtime Logs</h4>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8, flexWrap: 'wrap' }}>
                  <label>Tail:</label>
                  {[200, 500, 1000].map(n => (
                    <button key={n} onClick={() => { setRtTail(n); fetchRuntimeLogs(selected.id, n) }}
                      style={{ padding: '4px 8px', borderRadius: 6, border: rtTail === n ? '2px solid #3b82f6' : '1px solid #e5e7eb', background: rtTail === n ? '#eef2ff' : '#fff' }}>{n}</button>
                  ))}
                  <button onClick={() => fetchRuntimeLogs(selected.id)} style={{ padding: '4px 8px', borderRadius: 6, border: '1px solid #e5e7eb', background: '#fff' }}>Refresh</button>
                  <label style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                    <input type="checkbox" checked={autoRefreshLogs} onChange={(e) => setAutoRefreshLogs(e.target.checked)} />
                    Auto-refresh
                  </label>
                </div>
                <pre style={{ background: '#0b1020', color: '#d1d5db', padding: 8, borderRadius: 8, maxHeight: 240, overflow: 'auto' }}>
                  {runtimeLogs.length ? runtimeLogs.join('\n') : 'No logs yet.'}
                </pre>
              </div>
              {/* Errors / Loading */}
              {details[selected.id]?.status?.last_error && (
                <div style={{ marginTop: 8, color: '#dc2626' }}>
                  {String(details[selected.id]?.status?.last_error)}
                </div>
              )}
              {details[selected.id]?.loading && <div style={{ marginTop: 8, color: '#6b7280' }}>Loading details…</div>}
              {details[selected.id]?.error && <div style={{ marginTop: 8, color: '#dc2626' }}>{formatError(details[selected.id]?.error)}</div>}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
