import { useEffect, useMemo, useRef, useState } from 'react'
import { useAuth } from '@/stores/auth'
import { useData } from '@/stores/data'
import { api } from '@/lib/api'
import CreateBotForm, { CreateBotFormValues } from '@/components/CreateBotForm'
import { useUI } from '@/stores/ui'
import './Bots.css'

// ✅ unified chart + tiny adapters
import AnalyticsChart from '@/components/chart/AnalyticsChart'
import { useBacktestData } from '@/components/chart/useBacktestData'
import LiveAnalyticsContainer from '@/components/chart/LiveAnalyticsContainer'

// --- types / helpers moved local (since we removed BackstagePanel import)
type BackstageSelection = { pair: string | null; timeframe: string | null; timerange: string };

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
  effective_strategy?: string | null
  active_strategy?: { name?: string; clazz?: string } | null
}

export type BotBacktestResults = {
  trades: any[]
  summary: { total_trades?: number; winrate?: number; profit_abs_sum?: number; profit_ratio_avg?: number; by_pair?: Record<string, any>; file?: string }
} 

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

  // Logs and backtest UI state
  const [rtTail, setRtTail] = useState<number>(500)
  const [btTail, setBtTail] = useState<number>(500)
  const [runtimeLogs, setRuntimeLogs] = useState<string[]>([])
  const [backtestLogs, setBacktestLogs] = useState<string[]>([])
  const [btStatus, setBtStatus] = useState<{ state: string; container?: string | null; started_at?: string | null; finished_at?: string | null; exit_code?: number | null } | null>(null)
  const [autoRefreshLogs, setAutoRefreshLogs] = useState<boolean>(false)
  // Backstage/backtest controls
  const [btTimerange, setBtTimerange] = useState<string>('')
  // New date pickers for backtest window
  const [btFromDate, setBtFromDate] = useState<string>('') // YYYY-MM-DD
  const [btToDate, setBtToDate] = useState<string>('')     // YYYY-MM-DD
  const [btResults, setBtResults] = useState<BotBacktestResults | null>(null)
  const [btStarting, setBtStarting] = useState<boolean>(false)
  const [btResultsFetchedFor, setBtResultsFetchedFor] = useState<string | null>(null)
  const [btFiles, setBtFiles] = useState<Array<{ file: string; mtime: number; size: number }>>([])
  const [btFilesLoading, setBtFilesLoading] = useState<boolean>(false)
  // Live trades refresh state
  const [liveTrades, setLiveTrades] = useState<any[]>([])
  const [liveTradesLoading, setLiveTradesLoading] = useState<boolean>(false)
  const [liveTradesError, setLiveTradesError] = useState<string | null>(null)
  const [liveRefreshKey, setLiveRefreshKey] = useState<number>(0)

  // ✅ Selections
  const [bsSelection, setBsSelection] = useState<BackstageSelection>({ pair: 'BTC/USDT', timeframe: '5m', timerange: '-30d' })
  const [livePair, setLivePair] = useState<string | null>(null)
  const [liveTf, setLiveTf] = useState<string | null>(null)

  // View tabs under the configuration panel
  const [viewTab, setViewTab] = useState<'live' | 'backstage'>('live')
  
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
      const vt = localStorage.getItem(viewTabKey(selectedId)) as 'live' | 'backstage' | null
      if (vt === 'live' || vt === 'backstage') setViewTab(vt)
    } catch {}
    try {
      const raw = localStorage.getItem(bsSelKey(selectedId))
      if (raw) {
        const parsed = JSON.parse(raw)
        if (parsed && typeof parsed === 'object') {
          setBsSelection({
            pair: parsed.pair ?? 'BTC/USDT',
            timeframe: parsed.timeframe ?? '5m',
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
            api.get(`config/config/bot/${b.id}`),
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
        api.get(`config/config/bot/${botId}`),
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
      const botAct = (bot as any)?.active_strategy || {}
      const curName = botAct?.name || ''
      const curClazz = botAct?.clazz || ''
      if (formStrategyName !== curName || (formStrategyClazz || '') !== (curClazz || '')) {
        const body = { active_strategy: { name: formStrategyName || null, clazz: formStrategyClazz || null } }
        await api.patch(`/users/${userId}/bots/${botId}/strategy`, body)
      }
      await refreshBotDetails(botId)
      notifySuccess('Configuration saved')
    } catch (e: any) {
      notifyError(extractError(e) || 'Failed to save configuration')
    }
  }

  const fetchLiveTrades = async (botId: number, mode: 'all' | 'live' | 'dryrun' = 'all') => {
    if (!userId) return
    setLiveTradesLoading(true)
    setLiveTradesError(null)
    try {
      const res = await api.get(`/users/${userId}/bots/${botId}/trades-history`, { params: { mode, limit: 500 } })
      const arr = Array.isArray(res.data) ? res.data : []
      setLiveTrades(arr)
    } catch (e: any) {
      setLiveTradesError(extractError(e) || 'Failed to load trades')
      setLiveTrades([])
    } finally {
      setLiveTradesLoading(false)
    }
  }

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
  const fetchBacktestStatus = async (botId: number) => {
    if (!userId) return
    try {
      const res = await api.get(`/users/${userId}/bots/${botId}/backtest/status`)
      setBtStatus(res.data || null)
    } catch {}
  }
  const fetchBacktestResults = async (botId: number, limit = 200) => {
    if (!userId) return
    try {
      const res = await api.get(`/users/${userId}/bots/${botId}/backtest/results`, { params: { limit_trades: limit } })
      if(res.data){
        console.log('Backtest results:', res)
      }
        setBtResults(res.data || null)
        // Note: Do NOT set btResultsFetchedFor here. The polling effect will set a stable mark
        // based on finished_at to avoid re-fetch loops.
    } catch {}
  }
  const fetchBacktestList = async (botId: number) => {
    if (!userId) return
    setBtFilesLoading(true)
    try {
      const res = await api.get(`/users/${userId}/bots/${botId}/backtest/list`)
      const items = Array.isArray(res.data?.items) ? res.data.items : []
      setBtFiles(items)
    } catch {
      setBtFiles([])
    } finally {
      setBtFilesLoading(false)
    }
  }
  const fetchBacktestResultFile = async (botId: number, file: string, limit = 200) => {
    if (!userId) return
    try {
      const res = await api.get(`/users/${userId}/bots/${botId}/backtest/result`, { params: { file, limit_trades: limit } })
      setBtResults(res.data || null)
      setBtResultsFetchedFor(`${botId}:${file}`)
    } catch {}
  }
  const fetchBacktestLogs = async (botId: number, tail = btTail) => {
    if (!userId) return
    try {
      const res = await api.get(`/users/${userId}/bots/${botId}/backtest/logs`, { params: { tail } })
      const lines: string[] = Array.isArray(res.data?.lines) ? res.data.lines : []
      setBacktestLogs(lines)
    } catch {}
  }
  const handleRunBacktest = async (botId: number) => {
    if (!userId) return
    setBtStarting(true)
      setBtResults(null)
      setBtResultsFetchedFor(null) // reset guard so we fetch fresh results when backtest completes
    try {
      // Build timerange from date pickers (YYYYMMDD-YYYYMMDD)
  const toYmd = (iso: string): string => iso ? iso.split('-').join('') : ''
      const hasFrom = btFromDate && btFromDate.length === 10
      const hasTo = btToDate && btToDate.length === 10
      if (!hasFrom || !hasTo) {
        notifyError('Please select both From and To dates for the backtest')
        return
      }
      const pickTimerange = `${toYmd(btFromDate)}-${toYmd(btToDate)}`
      const exportName = `backstage-${Date.now()}`
      // Resolve an effective strategy for the backtest request:
      // 1) Prefer the currently chosen form fields (not necessarily saved yet)
      // 2) Fall back to runtime.effective_strategy (composed)
      // 3) Do not send placeholder values
      const rawClazz = (formStrategyClazz || '').trim()
      const rawName = (formStrategyName || '').trim()
      const runtimeEff = (details[botId]?.runtime?.effective_strategy || details[botId]?.runtime?.strategy || '').trim()
      const pickFromForm = rawClazz || rawName
      // Normalize class: strip .py and dotted path, keeping the class name only
      const normalizeClass = (s: string) => {
        if (!s) return ''
        let x = s.replace(/\.py$/i, '')
        if (x.includes('.')) x = x.split('.').pop() || x
        return x
      }
      let effStrategy = pickFromForm ? normalizeClass(pickFromForm) : normalizeClass(runtimeEff)
      if (!effStrategy || effStrategy === '__SET_YOUR_STRATEGY__') {
        effStrategy = undefined as any
      }
      const body: any = {
        strategy: effStrategy,
        timerange: pickTimerange,
        export: 'trades',
        export_filename: exportName,
      }
      // When coming from Backstage selection, include pair/timeframe overrides
  // Do NOT override pair/timeframe here – backtest should run for all whitelisted pairs
      await api.post(`/users/${userId}/bots/${botId}/backtest`, body)
      // Status/logs polling loop (existing auto refresh will also pick it up)
      await fetchBacktestStatus(botId)
      await fetchBacktestLogs(botId)
      notifySuccess('Backtest started')
    } catch (e: any) {
      notifyError(extractError(e) || 'Failed to start backtest')
    } finally {
      setBtStarting(false)
    }
  }

  // Stable polling: single lifecycle per run; permanently stop after completion
  const btStoppedRef = useRef<Record<number, boolean>>({})
  useEffect(() => {
    if (!selectedId || viewTab !== 'backstage') return
    if (btStoppedRef.current[selectedId]) return

    let interval: any
    const finishedAt = btStatus?.finished_at || ''
    const doneMark = `done:${selectedId}:${finishedAt}`
    const alreadyFetched = btStatus?.state === 'done' && btResultsFetchedFor === doneMark

    const tick = () => {
      if (btStatus?.state === 'running') {
        fetchBacktestStatus(selectedId).catch(()=>{})
        fetchBacktestLogs(selectedId).catch(()=>{})
      } else if (btStatus?.state === 'done') {
        if (!alreadyFetched) {
          fetchBacktestResults(selectedId).then(() => setBtResultsFetchedFor(doneMark))
        }
        btStoppedRef.current[selectedId] = true
        if (interval) clearInterval(interval)
      }
    }
    // initial tick
    tick()
    if (btStatus?.state === 'running') {
      interval = setInterval(tick, 4000)
    }
    return () => { if (interval) clearInterval(interval) }
  }, [selectedId, viewTab, btStatus?.state, btStatus?.finished_at, btResultsFetchedFor])

  // Reset backtest UI bits when switching selection
  useEffect(() => {
    setBtTimerange('')
    setBtResults(null)
    setBtResultsFetchedFor(null)
    setBtStarting(false)
    setBtFromDate('')
    setBtToDate('')
  }, [selectedId])

  // When entering Backstage tab, fetch latest backtest results once
  useEffect(() => {
    if (!selectedId || viewTab !== 'backstage') return
    if (!btResults) {
      fetchBacktestResults(selectedId).catch(() => {})
    }
  }, [viewTab, selectedId])

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
      timeframe: prev?.timeframe ?? tfs[0],
      timerange: prev?.timerange ?? '-30d',
    }))
  }, [selected?.id, details[selected?.id || -1]?.config])

  // ✅ normalized data for unified chart
  // Live data is handled inside LiveAnalyticsContainer to keep a single WS connection.

  const backtestData = useBacktestData({
    userId: userId as number,
    botId: selected?.id as number,
    pair: bsSelection.pair || '',
    timeframe: bsSelection.timeframe || '',
    timerange: bsSelection.timerange || '-30d',
  enabled: viewTab === 'backstage' && !!btResults && btStatus?.state === 'done',
    ...(() => {
      // Compute precise candle window from selected backtest trades (for the chosen pair), capped to ~1 year
      const trades = btResults?.trades || []
      const selPair = bsSelection.pair || ''
      const tf = (bsSelection.timeframe || '5m').toLowerCase()

      const tfToSec = (s: string): number => {
        const m = s.match(/^(\d+)([mhdw])$/i)
        if (!m) return 300
        const n = parseInt(m[1], 10)
        const unit = m[2].toLowerCase()
        if (unit === 'm') return n * 60
        if (unit === 'h') return n * 3600
        if (unit === 'd') return n * 86400
        if (unit === 'w') return n * 7 * 86400
        return 300
      }
      const toSec = (v: any): number | undefined => {
        if (v == null) return undefined
        if (typeof v === 'number') return v > 1e12 ? Math.floor(v / 1000) : Math.floor(v)
        const ms = Date.parse(String(v))
        return Number.isFinite(ms) ? Math.floor(ms / 1000) : undefined
      }

      const relevant = trades.filter(t => !selPair || String(t?.pair) === selPair)
      let minS: number | undefined
      let maxS: number | undefined
      for (const t of relevant) {
        const o = toSec(t?.open_timestamp) ?? toSec(t?.open_date)
        const c = toSec(t?.close_timestamp) ?? toSec(t?.close_date)
        const a = [o, c].filter((x): x is number => typeof x === 'number')
        for (const s of a) {
          if (minS == null || s < minS) minS = s
          if (maxS == null || s > maxS) maxS = s
        }
      }
      const tfSec = tfToSec(tf)
      const pad = Math.max(tfSec * 50, 0) // add ~50 candles padding on both sides
      const YEAR = 366 * 86400

      if (minS != null && maxS != null && maxS >= minS) {
        let fromTs = Math.max(0, minS - pad)
        let toTs = maxS + pad
        // Cap to ~1 year window ending at toTs
        if (toTs - fromTs > YEAR) {
          fromTs = Math.max(0, toTs - YEAR)
        }
        // Compute a matching limit with small margin, minimum 200
        const limit = Math.max(200, Math.ceil((toTs - fromTs) / tfSec) + 20)
        return { limit, fromTs, toTs }
      }
      // Fallback: compute from timerange if possible to get a tighter limit
      try {
        const tr = (bsSelection.timerange || '').trim()
        const m = tr.match(/^(\d{8})-(\d{8})?$/)
        if (m) {
          const parseYmd = (s: string): number => {
            const y = parseInt(s.slice(0, 4), 10)
            const mo = parseInt(s.slice(4, 6), 10) - 1
            const d = parseInt(s.slice(6, 8), 10)
            return Math.floor(Date.UTC(y, mo, d) / 1000)
          }
          const fromTs = parseYmd(m[1])
          const toTs = m[2] ? (parseYmd(m[2]) + 86399) : Math.floor(Date.now() / 1000)
          const span = Math.min(YEAR, Math.max(0, toTs - fromTs))
          const limit = Math.max(200, Math.ceil(span / tfSec) + 20)
          return { limit, fromTs, toTs }
        }
      } catch {}
      // Default
      return { limit: 3000 as number }
    })(),
  })

    // Coerce Backstage selection to valid pairs/timeframes when results or config change
    useEffect(() => {
      if (!selected) return
      const cfg = details[selected.id]?.config || {}
      const cfgPs = cfgPairs(cfg)
      const byPair = btResults?.summary?.by_pair || null
      const ps = byPair ? Object.keys(byPair) : cfgPs
      const tfs = cfgTimeframes(cfg)
      // Prefer timeframe from backtest results when available
      const btTf = (btResults?.summary as any)?.timeframe as string | undefined
      if (!ps.length || !tfs.length) return
      setBsSelection(prev => {
        const cur = prev || { pair: null as any, timeframe: null as any, timerange: '-30d' }
        const nextPair = cur.pair && ps.includes(cur.pair) ? cur.pair : ps[0]
        // If backtest timeframe is known, prefer it; otherwise coerce to first configured timeframe
        const desiredTf = btTf && typeof btTf === 'string' ? btTf : tfs[0]
        const nextTf = desiredTf
        if (cur.pair === nextPair && cur.timeframe === nextTf) return cur
        return { ...cur, pair: nextPair, timeframe: nextTf, timerange: cur.timerange || '-30d' }
      })
    }, [selected?.id, btResults, details[selected?.id || -1]?.config])

    // Filter trades from backtest results to the selected pair (Backstage)
    const backstageTrades = useMemo(() => {
      const all = btResults?.trades || []
      const p = bsSelection.pair
      return p ? all.filter(t => String(t?.pair) === p) : all
    }, [btResults?.trades, bsSelection.pair])

  return (
    <div>
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
              <div className='details-bot' style={{ display: 'grid', gridTemplateColumns: '160px 1fr', rowGap: 6 }}>
                {/* Hide raw mode when backend reports 'backstage' to avoid confusion */}
                {selected.mode && selected.mode !== 'backstage' ? (
                  <>
                    <div><strong>Mode</strong></div><div>{selected.mode}</div>
                  </>
                ) : null}
                {/* Live runtime/status from backend */}
                <div><strong>Status</strong></div><div>{details[selected.id]?.status?.status ?? selected.status}</div>
                <div><strong>PID</strong></div><div>{details[selected.id]?.status?.pid ?? selected.pid ?? '-'}</div>
                <div><strong>Container</strong></div><div>{details[selected.id]?.status?.container ?? '-'}</div>
      
                {/* Config summary */}
                <div><strong>Strategy</strong></div>
                {(() => {
                  const cfgStrat = String(details[selected.id]?.config?.strategy ?? '').trim()
                  const activeName = selected.active_strategy?.name || ''
                  const activeClazz = selected.active_strategy?.clazz || ''
                  const runtimeEff = String(details[selected.id]?.runtime?.effective_strategy ?? '').trim()
                  const display = cfgStrat || activeName || activeClazz || runtimeEff || '-'
                  return <div>{display}</div>
                })()}
                <div><strong>Trading Mode</strong></div><div>{String(details[selected.id]?.config?.trading_mode ?? '-')}</div>
                <div><strong>Stake Currency</strong></div><div>{String(details[selected.id]?.config?.stake_currency ?? '-')}</div>
                <div><strong>Pairs</strong></div>
                <div>{Array.isArray(details[selected.id]?.config?.pairs) ? (details[selected.id]?.config?.pairs as string[]).join(', ') : '-'}</div>
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
                  <button onClick={() => setViewTab('live')} style={{ padding: '6px 10px', borderRadius: '6px 6px 0 0', border: '1px solid #e5e7eb', borderBottom: viewTab==='live' ? '2px solid #3b82f6' : '1px solid #e5e7eb', background: viewTab==='live' ? '#f0f7ff' : '#fff' }}>Live/Dryrun</button>
                  <button onClick={() => setViewTab('backstage')} style={{ padding: '6px 10px', borderRadius: '6px 6px 0 0', border: '1px solid #e5e7eb', borderBottom: viewTab==='backstage' ? '2px solid #3b82f6' : '1px solid #e5e7eb', background: viewTab==='backstage' ? '#f0f7ff' : '#fff' }}>Backstage</button>
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
                            <button
                              onClick={() => setLiveRefreshKey(k => k + 1)}
                              style={{ padding: '6px 10px', borderRadius: 6, border: '1px solid #6b7280', background: '#fff' }}
                            >
                              Refresh Candles
                            </button>
                            <button
                              onClick={() => fetchLiveTrades(selected.id, 'all')}
                              disabled={liveTradesLoading}
                              style={{ padding: '6px 10px', borderRadius: 6, border: '1px solid #2563eb', background: liveTradesLoading ? '#dbeafe' : '#2563eb', color: '#fff' }}
                            >
                              {liveTradesLoading ? 'Refreshing…' : 'Refresh Trades'}
                            </button>
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
                            {ps.map(p => (
                              <button key={p}
                                onClick={() => setLivePair(p)}
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

                                <LiveAnalyticsContainer
                                  key={liveRefreshKey}
                                  userId={userId ?? undefined}
                                  botId={selected.id}
                                  pair={livePair ?? undefined}
                                  timeframe={liveTf ?? undefined}
                                  showSelectors={false}
                                  enabled={!!details[selected.id]?.runtime?.running}
                                />

                  </div>
                )}

                {viewTab === 'backstage' && (
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
                      <h4 style={{ margin: '0 0 8px 0' }}>Backstage (Parity Snapshot)</h4>
                      <div style={{ display: 'inline-flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                        <label><strong>Backtest dates</strong></label>
                        <input type="date" value={btFromDate} onChange={(e) => setBtFromDate(e.target.value)} style={{ padding: 6, borderRadius: 6, border: '1px solid #e5e7eb' }} />
                        <span>to</span>
                        <input type="date" value={btToDate} onChange={(e) => setBtToDate(e.target.value)} style={{ padding: 6, borderRadius: 6, border: '1px solid #e5e7eb' }} />
                        <button onClick={() => handleRunBacktest(selected.id)} disabled={btStarting} style={{ padding: '6px 10px', borderRadius: 6, border: '1px solid #2563eb', background: btStarting ? '#dbeafe' : '#2563eb', color: '#fff' }}>{btStarting ? 'Starting…' : 'Start Backtest'}</button>
                      </div>
                    </div>

                    {/* Backstage selectors */}
                    {(() => {
                      const cfg = details[selected.id]?.config || {}
                      // Restrict Backstage pair tabs to those present in the selected backtest result when available
                      const byPair = btResults?.summary?.by_pair || null
                      const ps = byPair ? Object.keys(byPair) : cfgPairs(cfg)
                      const tfs = cfgTimeframes(cfg)

                      const PairTabs = (
                        ps.length > 0 && (
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 8 }}>
                            {ps.map(p => (
                              <button key={p}
                                onClick={() => setBsSelection(s => ({ ...s, pair: p }))}
                                style={{ padding: '4px 8px', borderRadius: 6, border: '1px solid #e5e7eb', background: bsSelection.pair === p ? '#eef2ff' : '#fff', cursor: 'pointer' }}>
                                {p}
                              </button>
                            ))}
                          </div>
                        )
                      )

                      // Remove timeframe selector from Backstage panel – timeframe is controlled via Configuration
                      const TfTabs = (
                        tfs.length > 0 ? (
                          <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 6 }}>
                            Timeframe: {tfs[0]}
                          </div>
                        ) : (
                          <div style={{ fontSize: 12, color: '#dc2626', marginBottom: 6 }}>
                            No timeframe configured
                          </div>
                        )
                      )

                      return (
                        <>
                          {PairTabs}
                          {TfTabs}
                          {/* Timerange input removed – using date pickers in the Backtest header */}
                          <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 6 }}>
                            {bsSelection.pair && bsSelection.timeframe ? `${bsSelection.pair} · ${bsSelection.timeframe}` : ''}
                          </div>
                        </>
                      )
                    })()}

                    {/* Loading overlays for chart */}
                    {(() => {
                      const running = btStatus?.state && btStatus.state !== 'done' && btStatus.state !== 'idle'
                      const fetching = btStatus?.state === 'done' && !btResults
                      if (!running && !fetching) return null
                      return (
                        <div style={{ padding: 8, marginBottom: 8, color: '#374151', background: '#f3f4f6', border: '1px solid #e5e7eb', borderRadius: 6 }}>
                          {running ? 'Backtest running…' : 'Fetching latest results…'}
                        </div>
                      )
                    })()}

                    <AnalyticsChart
                      candles={backtestData.candles}
                      indicators={backtestData.indicators}
                      signals={backtestData.signals}
                      trades={(btResults ? backstageTrades : backtestData.trades)}
                      showOscPane
                      height={420}
                      oscHeight={160}
                    />

                    {/* Live Trades Table */}
                    <div style={{ marginTop: 12 }}>
                      <h5 style={{ margin: '0 0 6px 0' }}>Recent Trades ({liveTrades.length})</h5>
                      {liveTradesError && <div style={{ color: '#dc2626', marginBottom: 6 }}>{liveTradesError}</div>}
                      {liveTrades.length === 0 && !liveTradesLoading && <div style={{ fontSize: 12, color: '#6b7280' }}>No trades yet or not fetched.</div>}
                      {liveTrades.length > 0 && (
                        <div style={{ maxHeight: 260, overflow: 'auto', border: '1px solid #e5e7eb', borderRadius: 6 }}>
                          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                            <thead>
                              <tr>
                                <th style={{ textAlign: 'left', padding: 6, borderBottom: '1px solid #e5e7eb' }}>Pair</th>
                                <th style={{ textAlign: 'right', padding: 6, borderBottom: '1px solid #e5e7eb' }}>Open Time</th>
                                <th style={{ textAlign: 'right', padding: 6, borderBottom: '1px solid #e5e7eb' }}>Close Time</th>
                                <th style={{ textAlign: 'right', padding: 6, borderBottom: '1px solid #e5e7eb' }}>Profit Ratio</th>
                                <th style={{ textAlign: 'right', padding: 6, borderBottom: '1px solid #e5e7eb' }}>Profit Abs</th>
                                <th style={{ textAlign: 'left', padding: 6, borderBottom: '1px solid #e5e7eb' }}>Status</th>
                                <th style={{ textAlign: 'left', padding: 6, borderBottom: '1px solid #e5e7eb' }}>Reason</th>
                              </tr>
                            </thead>
                            <tbody>
                              {liveTrades
                                .filter(t => !livePair || String(t?.pair) === livePair)
                                .slice(-100)
                                .reverse()
                                .map((t, idx) => (
                                  <tr key={idx}>
                                    <td style={{ padding: 6, borderBottom: '1px solid #f3f4f6' }}>{t.pair || '-'}</td>
                                    <td style={{ padding: 6, textAlign: 'right', borderBottom: '1px solid #f3f4f6' }}>{t.open_date ? new Date(t.open_date).toLocaleString() : '-'}</td>
                                    <td style={{ padding: 6, textAlign: 'right', borderBottom: '1px solid #f3f4f6' }}>{t.close_date ? new Date(t.close_date).toLocaleString() : '-'}</td>
                                    <td style={{ padding: 6, textAlign: 'right', borderBottom: '1px solid #f3f4f6' }}>{(Number(t.profit_ratio || 0)).toFixed(4)}</td>
                                    <td style={{ padding: 6, textAlign: 'right', borderBottom: '1px solid #f3f4f6' }}>{(Number(t.profit_abs || 0)).toFixed(4)}</td>
                                    <td style={{ padding: 6, borderBottom: '1px solid #f3f4f6' }}>{t.status || '-'}</td>
                                    <td style={{ padding: 6, borderBottom: '1px solid #f3f4f6' }}>{t.sell_reason || '-'}</td>
                                  </tr>
                                ))}
                            </tbody>
                          </table>
                        </div>
                      )}
                    </div>
                  </div>
                )}
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

              {/* Backtest Status & Logs */}
              <div style={{ marginTop: 16, paddingTop: 12, borderTop: '1px solid #e5e7eb' }}>
                <h4 style={{ margin: '0 0 8px 0' }}>Backtest</h4>
                <div style={{ display: 'grid', gridTemplateColumns: '160px 1fr', rowGap: 6 }}>
                  <div><strong>Status</strong></div><div>{btStatus?.state ?? 'idle'}</div>
                  <div><strong>Container</strong></div><div>{btStatus?.container ?? '-'}</div>
                  <div><strong>Started</strong></div><div>{btStatus?.started_at ?? '-'}</div>
                  <div><strong>Finished</strong></div><div>{btStatus?.finished_at ?? '-'}</div>
                  <div><strong>Exit Code</strong></div><div>{btStatus?.exit_code ?? '-'}</div>
                </div>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center', margin: '8px 0', flexWrap: 'wrap' }}>
                  <label>Tail:</label>
                  {[200, 500, 1000].map(n => (
                    <button key={n} onClick={() => { setBtTail(n); fetchBacktestLogs(selected.id, n) }}
                      style={{ padding: '4px 8px', borderRadius: 6, border: btTail === n ? '2px solid #3b82f6' : '1px solid #e5e7eb', background: btTail === n ? '#eef2ff' : '#fff' }}>{n}</button>
                  ))}
                  <button onClick={() => { fetchBacktestStatus(selected.id); fetchBacktestLogs(selected.id) }} style={{ padding: '4px 8px', borderRadius: 6, border: '1px solid #e5e7eb', background: '#fff' }}>Refresh</button>
                  <button onClick={() => fetchBacktestResults(selected.id)}>Fetch Latest Results</button>
                  <button onClick={() => fetchBacktestList(selected.id)} disabled={btFilesLoading}>{btFilesLoading ? 'Loading list…' : 'List Results'}</button>
                </div>
                {btFiles.length > 0 && (
                  <div style={{ margin: '8px 0' }}>
                    <div style={{ fontWeight: 600, marginBottom: 6 }}>Available Results</div>
                    <div style={{ maxHeight: 160, overflow: 'auto', border: '1px solid #e5e7eb', borderRadius: 6 }}>
                      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                        <thead>
                          <tr>
                            <th style={{ textAlign: 'left', padding: 6, borderBottom: '1px solid #e5e7eb' }}>File</th>
                            <th style={{ textAlign: 'right', padding: 6, borderBottom: '1px solid #e5e7eb' }}>Size</th>
                            <th style={{ textAlign: 'left', padding: 6, borderBottom: '1px solid #e5e7eb' }}>Modified</th>
                            <th style={{ padding: 6, borderBottom: '1px solid #e5e7eb' }}></th>
                          </tr>
                        </thead>
                        <tbody>
                          {btFiles.map((f, idx) => (
                            <tr key={idx}>
                              <td style={{ padding: 6, borderBottom: '1px solid #f3f4f6' }}>{f.file}</td>
                              <td style={{ padding: 6, textAlign: 'right', borderBottom: '1px solid #f3f4f6' }}>{(f.size/1024).toFixed(1)} KB</td>
                              <td style={{ padding: 6, borderBottom: '1px solid #f3f4f6' }}>{new Date(f.mtime * 1000).toLocaleString()}</td>
                              <td style={{ padding: 6, borderBottom: '1px solid #f3f4f6' }}>
                                <button onClick={() => fetchBacktestResultFile(selected.id, f.file)} style={{ padding: '4px 8px', borderRadius: 6, border: '1px solid #e5e7eb', background: '#fff' }}>Load</button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
                <pre style={{ background: '#0b1020', color: '#d1d5db', padding: 8, borderRadius: 8, maxHeight: 240, overflow: 'auto' }}>
                  {backtestLogs.length ? backtestLogs.join('\n') : 'No backtest logs yet.'}
                </pre>
                {btResults && (
                  <div style={{ marginTop: 12 }}>
                    <h5 style={{ margin: '8px 0' }}>Results Summary</h5>
                    <div style={{ display: 'grid', gridTemplateColumns: '200px 1fr', rowGap: 6 }}>
                      <div>'summary', {JSON.stringify(btResults.summary)}</div>
                      <div><strong>Total trades</strong></div><div>{btResults?.summary?.total_trades ?? 0}</div>
                      <div><strong>Winrate</strong></div><div>{((btResults.summary?.winrate ?? 0) * 100).toFixed(1)}%</div>
                      <div><strong>PnL (abs)</strong></div><div>{(btResults.summary?.profit_abs_sum ?? 0).toFixed(4)}</div>
                      <div><strong>Avg Profit Ratio</strong></div><div>{(btResults.summary?.profit_ratio_avg ?? 0).toFixed(4)}</div>
                      <div><strong>File</strong></div><div>{btResults.summary?.file ?? '-'}</div>
                    </div>
                    <h5 style={{ margin: '12px 0 6px 0' }}>Latest Trades</h5>
                    <div style={{ overflowX: 'auto' }}>
                      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                        <thead>
                          <tr>
                            <th style={{ textAlign: 'left', borderBottom: '1px solid #e5e7eb', padding: 6 }}>Pair</th>
                            <th style={{ textAlign: 'right', borderBottom: '1px solid #e5e7eb', padding: 6 }}>Profit Ratio</th>
                            <th style={{ textAlign: 'right', borderBottom: '1px solid #e5e7eb', padding: 6 }}>Profit Abs</th>
                            <th style={{ textAlign: 'left', borderBottom: '1px solid #e5e7eb', padding: 6 }}>Status</th>
                            <th style={{ textAlign: 'left', borderBottom: '1px solid #e5e7eb', padding: 6 }}>Reason</th>
                          </tr>
                        </thead>
                        <tbody>
                          {(btResults.trades || []).map((t, idx) => (
                            <tr key={idx}>
                              <td style={{ padding: 6, borderBottom: '1px solid #f3f4f6' }}>{t.pair || '-'}</td>
                              <td style={{ padding: 6, textAlign: 'right', borderBottom: '1px solid #f3f4f6' }}>{(Number(t.profit_ratio || 0)).toFixed(4)}</td>
                              <td style={{ padding: 6, textAlign: 'right', borderBottom: '1px solid #f3f4f6' }}>{(Number(t.profit_abs || 0)).toFixed(4)}</td>
                              <td style={{ padding: 6, borderBottom: '1px solid #f3f4f6' }}>{t.status || '-'}</td>
                              <td style={{ padding: 6, borderBottom: '1px solid #f3f4f6' }}>{t.sell_reason || '-'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
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
