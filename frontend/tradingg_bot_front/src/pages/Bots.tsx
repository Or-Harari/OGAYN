import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '@/stores/auth'
import { useData } from '@/stores/data'
import { api } from '@/lib/api'
import CreateBotForm, { CreateBotFormValues } from '@/components/CreateBotForm'
import BotControls from '@/components/BotControls'
import PairlistConfig from '@/components/PairlistConfig'
import { useUI } from '@/stores/ui'
import { useEffectivePairs } from '@/hooks/useEffectivePairs'
import './Bots.css'

import LiveAnalyticsContainer from '@/components/chart/LiveAnalyticsContainer'
import TradesPanel from '@/components/TradesPanel'

type BackstageSelection = { pair: string | null; timerange: string };

const cfgPairs = (cfg: any): string[] =>
  Array.isArray(cfg?.pair_whitelist) ? cfg.pair_whitelist
  : Array.isArray(cfg?.pairs) ? cfg.pairs
  : [];

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
}

export function Bots() {
  const navigate = useNavigate()
  const userId = useAuth(s => s.userId)
  const bots = useData(s => s.bots)
  const loadBots = useData(s => s.loadBots)
  const notifySuccess = useUI(s => s.notifySuccess)
  const notifyError = useUI(s => s.notifyError)

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

  // Config form
  const [formMode, setFormMode] = useState<string>('dryrun')
  const [formStakeCurrency, setFormStakeCurrency] = useState<string>('USDT')
  const [formStakeAmount, setFormStakeAmount] = useState<string>('10')
  const [formPairsText, setFormPairsText] = useState<string>('')
  const [formPairBlacklistText, setFormPairBlacklistText] = useState<string>('')
  const [formPairlists, setFormPairlists] = useState<Array<{method: string; [key: string]: any}>>([])
  const [formTradingMode, setFormTradingMode] = useState<'spot' | 'futures'>('spot')
  const [formMarginMode, setFormMarginMode] = useState<string>('cross')
  const [formLiquidationBuffer, setFormLiquidationBuffer] = useState<string>('0.0')
  const [formLeverage, setFormLeverage] = useState<number>(1)
  const [formDryRunWallet, setFormDryRunWallet] = useState<string>('')
  const [formFiatDisplayCurrency, setFormFiatDisplayCurrency] = useState<string>('USD')
  const [formAvailableCapital, setFormAvailableCapital] = useState<string>('')
  // Pricing controls
  const [entryPriceSide, setEntryPriceSide] = useState<'ask'|'bid'|'same'|'other'>('same')
  const [entryUseOrderBook, setEntryUseOrderBook] = useState<boolean>(false)
  const [entryOrderBookTop, setEntryOrderBookTop] = useState<number>(1)
  const [entryPriceLastBalance, setEntryPriceLastBalance] = useState<number>(0)
  const [entryDepthEnabled, setEntryDepthEnabled] = useState<boolean>(false)
  const [entryDepthBidsToAskDelta, setEntryDepthBidsToAskDelta] = useState<number>(0)

  const [exitPriceSide, setExitPriceSide] = useState<'ask'|'bid'|'same'|'other'>('same')
  const [exitUseOrderBook, setExitUseOrderBook] = useState<boolean>(false)
  const [exitOrderBookTop, setExitOrderBookTop] = useState<number>(1)
  const [exitPriceLastBalance, setExitPriceLastBalance] = useState<number>(0)
  const [exitDepthEnabled, setExitDepthEnabled] = useState<boolean>(false)
  const [exitDepthBidsToAskDelta, setExitDepthBidsToAskDelta] = useState<number>(0)
  const [strategies, setStrategies] = useState<Array<{ name: string; clazz?: string }>>([])
  const [formStrategyName, setFormStrategyName] = useState<string>('')
  const [formStrategyClazz, setFormStrategyClazz] = useState<string>('')
  useEffect(() => {
    // Load available strategies for selection
    const run = async () => {
      try {
        const res = await api.get('/config/user/strategies')
        const names: string[] = Array.isArray(res.data?.strategies) ? res.data.strategies : []
        setStrategies(names.map(n => ({ name: n })))
      } catch {}
    }
    run()
  }, [])

  // Logs
  const [rtTail, setRtTail] = useState<number>(500)
  const [runtimeLogs, setRuntimeLogs] = useState<string[]>([])
  const [autoRefreshLogs, setAutoRefreshLogs] = useState<boolean>(false)

  // Live states
  const [liveTrades, setLiveTrades] = useState<any[]>([])
  const [liveTradesLoading, setLiveTradesLoading] = useState<boolean>(false)
  const [liveTradesError, setLiveTradesError] = useState<string | null>(null)
  const [liveOpenOrders, setLiveOpenOrders] = useState<any[]>([])
  const [liveOrdersError, setLiveOrdersError] = useState<string | null>(null)
  const [liveSubTab, setLiveSubTab] = useState<'trades' | 'orders' | 'closed'>('trades')
  const [liveRefreshKey, setLiveRefreshKey] = useState<number>(0)
  const [livePollSec, setLivePollSec] = useState<number>(1)
  const [historyTrades, setHistoryTrades] = useState<any[]>([])
  const [historyLoading, setHistoryLoading] = useState<boolean>(false)
  const [historyError, setHistoryError] = useState<string | null>(null)
  const [historyDetails, setHistoryDetails] = useState<Record<string | number, any>>({})
  const [perfByPair, setPerfByPair] = useState<any[]>([])
  const [profitSummary, setProfitSummary] = useState<any | null>(null)
  const [historyResetting, setHistoryResetting] = useState<boolean>(false)

  const [livePair, setLivePair] = useState<string | null>(null)
  const [liveTf, setLiveTf] = useState<string | null>(null)
  const [viewTab, setViewTab] = useState<'trade' | 'performance' | 'balance' | 'period' | 'config'>('trade')
  const viewTabKey = (botId?: number | null) => (botId ? `botViewTab:${botId}` : 'botViewTab')
  const bsSelKey = (botId?: number | null) => (botId ? `backstageSel:${botId}` : 'backstageSel')

  // Balance & Period
  const [balance, setBalance] = useState<any | null>(null)
  const [balanceLoading, setBalanceLoading] = useState<boolean>(false)
  const [balanceError, setBalanceError] = useState<string | null>(null)
  const [balanceNavigate, setBalanceNavigate] = useState<string | null>(null)
  const [pairProfitMap, setPairProfitMap] = useState<Record<string, number>>({})
  const [periodRows, setPeriodRows] = useState<Array<{ day: string; profit: number; trades: number; inCount: number }>>([])
  // Config Tab local state
  const [configSubTab, setConfigSubTab] = useState<'form'|'raw'>('form')
  const [rawConfigText, setRawConfigText] = useState<string>('')

  // Get effective pairs for selected bot (includes RemotePairList support)
  const selectedConfig = selectedId ? details[selectedId]?.config : null
  const effectivePairs = useEffectivePairs(selectedConfig, userId || undefined)

  const formatError = (val: any): string => {
    if (val == null) return 'Unknown error'
    if (typeof val === 'string') return val
    if (typeof val === 'object') {
      const cand = (val as any)
      const tryFields = [cand.detail, cand.message, cand.error, cand.msg, cand.reason, cand.title]
      const fld = tryFields.find((v) => typeof v === 'string' && v.length > 0)
      if (fld) return fld as string
      try { const s = JSON.stringify(val); return s && s !== '{}' ? s : String(val) } catch { return String(val) }
    }
    return String(val)
  }

  const extractError = (e: any): string => {
    const sources = [e?.response?.data?.detail, e?.response?.data?.error, e?.response?.data?.message, e?.response?.data, e?.message, e]
    for (const s of sources) {
      const m = formatError(s)
      if (m && m !== '[object Object]' && m !== '{}' && m !== 'undefined') return m
    }
    return 'Unexpected error'
  }

  useEffect(() => {
    if (!selectedId) return
    try {
      const vt = localStorage.getItem(viewTabKey(selectedId)) as ('trade'|'performance'|'balance'|'period'|'config'|null)
      if (vt === 'trade' || vt === 'performance' || vt === 'balance' || vt === 'period' || vt === 'config') setViewTab(vt)
    } catch {}
  }, [selectedId])

  useEffect(() => {
    if (!userId) return
    const run = async () => {
      await loadBots(userId)
      try {
        const sid = localStorage.getItem('selected_bot_id')
        if (sid) { const id = Number(sid); if (isFinite(id)) setSelectedId(id); localStorage.removeItem('selected_bot_id') }
      } catch {}
    }
    run()
  }, [userId])

  useEffect(() => {
    const run = async () => {
      if (!userId || bots.length === 0) return
      setDetails(prev => { const next = { ...prev }; bots.forEach(b => { next[b.id] = { ...(next[b.id] || {}), loading: true, error: null } }); return next })
      await Promise.allSettled(bots.map(async (b:any) => {
        try {
          const [stRes, rtRes, cfgRes] = await Promise.all([
            api.get(`/users/${userId}/bots/${b.id}/status`),
            api.get(`/users/${userId}/bots/${b.id}/runtime`),
            api.get(`/config/bot/${b.id}`),
          ])
          setDetails(prev => ({ ...prev, [b.id]: { status: stRes.data, runtime: rtRes.data, config: cfgRes.data, loading: false, error: null } }))
          if (selectedId === b.id) {
            try { setRawConfigText(JSON.stringify(cfgRes.data ?? {}, null, 2)) } catch {}
          }
        } catch (e: any) {
          const msg = extractError(e)
          setDetails(prev => ({ ...prev, [b.id]: { ...(prev[b.id] || {}), loading: false, error: String(msg) } }))
        }
      }))
    }
    run()
  }, [userId, bots])

  const selected = useMemo(() => bots.find((b:any) => b.id === selectedId) || null, [bots, selectedId])

  useEffect(() => {
    const b = selected; if (!b) return
    const cfg = details[b.id]?.config || {}
    const ps = effectivePairs
    const tfs = cfgTimeframes(cfg)
    setLivePair(prev => (!ps.length ? null : (prev && ps.includes(prev)) ? prev : ps[0]))
    setLiveTf(prev => (!tfs.length ? null : (prev && tfs.includes(prev)) ? prev : tfs[0]))
    // Sync config tab form and raw editor
    try {
      setRawConfigText(JSON.stringify(cfg ?? {}, null, 2))
      const tm = String(cfg?.trading_mode || 'spot').toLowerCase()
      setFormTradingMode(tm === 'futures' ? 'futures' : 'spot')
      setFormStakeCurrency(String(cfg?.stake_currency || 'USDT'))
      setFormStakeAmount(String(cfg?.stake_amount ?? '10'))
      const pairs = cfgPairs(cfg)
      setFormPairsText(Array.isArray(pairs) ? pairs.join('\n') : '')
      const blacklist = cfg?.pair_blacklist || []
      setFormPairBlacklistText(Array.isArray(blacklist) ? blacklist.join(', ') : '')
      const pairlists = cfg?.pairlists || []
      setFormPairlists(Array.isArray(pairlists) ? pairlists : [])
      setFormMarginMode(String(cfg?.margin_mode || 'cross'))
      setFormLiquidationBuffer(String(cfg?.liquidation_buffer ?? '0.0'))
      try { setFormLeverage(Number(cfg?.leverage ?? 1) || 1) } catch { setFormLeverage(1) }
      const dw = cfg?.dry_run_wallet
      if (typeof dw === 'object') { try { setFormDryRunWallet(JSON.stringify(dw)) } catch { setFormDryRunWallet('') } }
      else if (dw != null) { setFormDryRunWallet(String(dw)) } else { setFormDryRunWallet('') }
      setFormFiatDisplayCurrency(String(cfg?.fiat_display_currency || 'USD'))
      setFormStrategyName(String(cfg?.strategy || ''))
      try { setFormAvailableCapital(cfg?.available_capital != null ? String(cfg?.available_capital) : '') } catch { setFormAvailableCapital('') }
      const ep = (cfg?.entry_pricing || {})
      setEntryPriceSide((ep?.price_side || 'same') as any)
      setEntryUseOrderBook(!!ep?.use_order_book)
      setEntryOrderBookTop(Number(ep?.order_book_top || 1))
      setEntryPriceLastBalance(Number(ep?.price_last_balance || 0))
      const ed = ep?.check_depth_of_market || {}
      setEntryDepthEnabled(!!ed?.enabled)
      setEntryDepthBidsToAskDelta(Number(ed?.bids_to_ask_delta || 0))
      const xp = (cfg?.exit_pricing || {})
      setExitPriceSide((xp?.price_side || 'same') as any)
      setExitUseOrderBook(!!xp?.use_order_book)
      setExitOrderBookTop(Number(xp?.order_book_top || 1))
      setExitPriceLastBalance(Number(xp?.price_last_balance || 0))
      const xd = xp?.check_depth_of_market || {}
      setExitDepthEnabled(!!xd?.enabled)
      setExitDepthBidsToAskDelta(Number(xd?.bids_to_ask_delta || 0))
    } catch {}
  }, [selected?.id, details[selected?.id || -1]?.config, effectivePairs])

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
          if (isOpen) out.push({ ...o, trade_id: tradeId, pair: o?.pair || t?.pair })
        }
      }
      setLiveOpenOrders(out)
      setLiveOrdersError(null)
    } catch {}
  }, [liveTrades])

  useEffect(() => {
    const trades = Array.isArray(liveTrades) ? liveTrades : []
    const map: Record<string, number> = {}
    for (const t of trades) { const p = String(t?.pair || '-'); const r = Number(t?.profit_ratio || 0) || 0; map[p] = (map[p] || 0) + r }
    setPairProfitMap(map)
  }, [liveTrades])

  const fetchTradesHistory = async (botId: number, limit = 500) => {
    if (!userId || !selected) return
    setHistoryLoading(true); setHistoryError(null)
    try { const mode = String(selected.mode || 'all').toLowerCase(); const res = await api.get(`/users/${userId}/bots/${botId}/trades-history`, { params: { mode, limit } }); setHistoryTrades(Array.isArray(res.data) ? res.data : []) }
    catch (e:any) { setHistoryError(extractError(e)); setHistoryTrades([]) }
    finally { setHistoryLoading(false) }
  }

  const loadTradeDetails = async (botId: number, tradeId: number | string) => {
    if (!userId || tradeId == null) return
    try { const tid = (typeof tradeId === 'string' && tradeId.includes(':')) ? (tradeId.split(':').pop() || tradeId) : tradeId; const res = await api.get(`/users/${userId}/bots/${botId}/proxy/freqtrade/trade/${tid}`); setHistoryDetails(prev => ({ ...prev, [tradeId]: res.data })) } catch {}
  }

  const fetchPerformance = async (botId: number) => {
    if (!userId) return
    try { const res = await api.get(`/users/${userId}/bots/${botId}/performance`); const arr = Array.isArray(res.data) ? res.data : (Array.isArray(res.data?.performance) ? res.data.performance : []); setPerfByPair(arr) } catch { setPerfByPair([]) }
  }

  const fetchProfit = async (botId: number) => {
    if (!userId) return
    try { const res = await api.get(`/users/${userId}/bots/${botId}/profit`); setProfitSummary(res.data || null) } catch { setProfitSummary(null) }
  }

  const fetchBalance = async (botId: number) => {
    if (!userId) return
    setBalanceLoading(true); setBalanceError(null); setBalanceNavigate(null)
    try { const res = await api.get(`/users/${userId}/bots/${botId}/balance`); setBalance(res.data || null) }
    catch (e:any) {
      setBalance(null);
      setBalanceError(extractError(e))
      try {
        const nav = e?.response?.data?.detail?.action?.navigate || e?.response?.data?.action?.navigate
        if (typeof nav === 'string' && nav.length > 0) setBalanceNavigate(nav)
      } catch {}
    }
    finally { setBalanceLoading(false) }
  }

  useEffect(() => {
    if (!selected) return
    if (viewTab === 'trade') {
      if (liveSubTab === 'closed') fetchTradesHistory(selected.id)
    } else if (viewTab === 'performance') {
      fetchPerformance(selected.id)
      fetchProfit(selected.id)
    } else if (viewTab === 'balance') {
      fetchBalance(selected.id)
    } else if (viewTab === 'period') {
      // Period view relies on closed trades history to derive rows
      fetchTradesHistory(selected.id)
    } else if (viewTab === 'config') {
      // Refresh config when entering Config tab
      refreshBotDetails(selected.id)
    }
  }, [viewTab, liveSubTab, selected?.id])

  useEffect(() => {
    try {
      const rows = Array.isArray(historyTrades) ? historyTrades : []
      if (!rows.length) return
      const closed = rows.filter(r => String(r.status || '').toLowerCase() === 'closed' || !!r.close_date)
      if (!closed.length) return
      const sumAbs = closed.reduce((acc, r) => acc + Number((r.profit_abs ?? r.close_profit_abs ?? r.realized_profit ?? 0)), 0)
      const ratios: number[] = closed.map(r => Number((r.profit_ratio ?? r.close_profit ?? 0))).filter(n => !isNaN(n))
      const avgRatio = ratios.length ? (ratios.reduce((a, b) => a + b, 0) / ratios.length) : 0
      const derivedSummary = { profit_abs: sumAbs, profit_ratio: avgRatio, total_trades: closed.length, avg_profit_ratio: avgRatio }
      if (!profitSummary) setProfitSummary(derivedSummary)
      if (!perfByPair || perfByPair.length === 0) {
        const byPair: Record<string, { profit_abs: number; profit_ratio_sum: number; count: number }> = {}
        for (const r of closed) { const p = String(r.pair || '-'); const pa = Number((r.profit_abs ?? r.close_profit_abs ?? r.realized_profit ?? 0)) || 0; const pr = Number((r.profit_ratio ?? r.close_profit ?? 0)) || 0; byPair[p] = byPair[p] || { profit_abs: 0, profit_ratio_sum: 0, count: 0 }; byPair[p].profit_abs += pa; byPair[p].profit_ratio_sum += pr; byPair[p].count += 1 }
        setPerfByPair(Object.entries(byPair).map(([pair, v]) => ({ pair, profit_abs: v.profit_abs, profit_ratio: v.count ? v.profit_ratio_sum / v.count : 0, trades: v.count })))
      }
      const byDay: Record<string, { profit: number; trades: number; inCount: number }> = {}
      for (const r of closed) { const cd = r.close_date ? new Date(r.close_date) : null; const day = cd ? cd.toISOString().slice(0,10) : '-'; const pa = Number((r.profit_abs ?? r.close_profit_abs ?? r.realized_profit ?? 0)) || 0; byDay[day] = byDay[day] || { profit: 0, trades: 0, inCount: 0 }; byDay[day].profit += pa; byDay[day].trades += 1; byDay[day].inCount += Number(r?.entries_count ?? 0) }
      const sortedDays = Object.entries(byDay).sort((a,b) => a[0] < b[0] ? 1 : -1)
      setPeriodRows(sortedDays.map(([day, v]) => ({ day, profit: v.profit, trades: v.trades, inCount: v.inCount })))
    } catch {}
  }, [historyTrades])

  const handleStartBot = async (botId: number) => {
    if (!userId) return
    setDetails(prev => ({ ...prev, [botId]: { ...(prev[botId] || {}), starting: true, error: null } }))
    try { await api.post(`/users/${userId}/bots/${botId}/start`); await refreshBotDetails(botId); notifySuccess('Bot started') }
    catch (e:any) { const msg = extractError(e) || 'Failed to start bot'; setDetails(prev => ({ ...prev, [botId]: { ...(prev[botId] || {}), error: msg } })); notifyError(msg) }
    finally { setDetails(prev => ({ ...prev, [botId]: { ...(prev[botId] || {}), starting: false } })) }
  }

  const handleStopBot = async (botId: number) => {
    if (!userId) return
    setDetails(prev => ({ ...prev, [botId]: { ...(prev[botId] || {}), stopping: true, error: null } }))
    try { await api.post(`/users/${userId}/bots/${botId}/stop`); await refreshBotDetails(botId); notifySuccess('Bot stopped') }
    catch (e:any) { const msg = extractError(e) || 'Failed to stop bot'; setDetails(prev => ({ ...prev, [botId]: { ...(prev[botId] || {}), error: msg } })); notifyError(msg) }
    finally { setDetails(prev => ({ ...prev, [botId]: { ...(prev[botId] || {}), stopping: false } })) }
  }

  const handleDeleteBot = async (botId: number) => {
    if (!userId) return
    const ok = window.confirm('Delete this bot?'); if (!ok) return
    setDetails(prev => ({ ...prev, [botId]: { ...(prev[botId] || {}), deleting: true, error: null } }))
    try { await api.delete(`/users/${userId}/bots/${botId}`); await loadBots(userId); if (selectedId === botId) setSelectedId(null); notifySuccess('Bot deleted') }
    catch (e:any) { const msg = extractError(e) || 'Failed to delete bot'; setDetails(prev => ({ ...prev, [botId]: { ...(prev[botId] || {}), error: msg } })); notifyError(msg) }
    finally { setDetails(prev => ({ ...prev, [botId]: { ...(prev[botId] || {}), deleting: false } })) }
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
      setDetails(prev => ({ ...prev, [botId]: { status: stRes.data, runtime: rtRes.data, config: cfgRes.data, loading: false, error: null } }))
    } catch (e:any) {
      const msg = extractError(e) || 'Failed to load bot info'
      setDetails(prev => ({ ...prev, [botId]: { ...(prev[botId] || {}), loading: false, error: msg } }))
    }
  }

  const handleSetRunMode = async (botId: number, mode: 'dryrun' | 'live') => {
    if (!userId) return
    const d = details[botId]; const running = !!d?.runtime?.running
    if (running) { notifyError('Stop the bot before changing run mode'); return }
    try { await api.patch(`/users/${userId}/bots/${botId}/mode`, { mode }); await refreshBotDetails(botId); notifySuccess(`Mode set to ${mode}`) }
    catch (e:any) { notifyError(extractError(e) || 'Failed to set mode') }
  }

  const fetchRuntimeLogs = async (botId: number, tail = rtTail) => {
    if (!userId) return
    try { const res = await api.get(`/users/${userId}/bots/${botId}/logs`, { params: { tail } }); const lines: string[] = Array.isArray(res.data?.lines) ? res.data.lines : []; setRuntimeLogs(lines) } catch {}
  }

  const cancelOpenOrder = async (botId: number, tradeId: number | string) => {
    if (!userId || tradeId == null) return
    try { await api.delete(`/users/${userId}/bots/${botId}/proxy/freqtrade/trades/${tradeId}/open-order`); setLiveOpenOrders(prev => prev.filter(o => (o?.trade_id ?? o?.tradeId ?? o?.trade) !== tradeId)); setLiveRefreshKey(k => k + 1); notifySuccess('Order canceled') } catch (e:any) { notifyError(extractError(e) || 'Failed to cancel order') }
  }

  const closeTrade = async (botId: number, tradeId: number | string, mode: 'market' | 'limit') => {
    if (!userId || tradeId == null) return
    try { await api.post(`/users/${userId}/bots/${botId}/proxy/freqtrade/forceexit`, { tradeid: tradeId, ordertype: mode }); setLiveTrades(prev => prev.filter(t => (t?.trade_id ?? t?.id ?? t?.tradeId) !== tradeId)); setLiveRefreshKey(k => k + 1); notifySuccess(`Trade closed by ${mode}`) } catch (e:any) { notifyError(extractError(e) || `Failed to close trade (${mode})`) }
  }

  const deleteTrade = async (botId: number, tradeId: number | string) => {
    if (!userId || tradeId == null) return
    const ok = window.confirm('Delete this trade?'); if (!ok) return
    const tryPaths = [
      `/users/${userId}/bots/${botId}/proxy/freqtrade/trades/${tradeId}`,
      `/users/${userId}/bots/${botId}/proxy/freqtrade/trades/${tradeId}/delete`,
    ]
    let lastErr: any = null
    for (const path of tryPaths) {
      try { await api.delete(path); setLiveTrades(prev => prev.filter(t => (t?.trade_id ?? t?.id ?? t?.tradeId) !== tradeId)); setLiveRefreshKey(k => k + 1); notifySuccess('Trade deleted'); return }
      catch (e:any) { lastErr = e; const code = e?.response?.status; if (code !== 405 && code !== 404) break }
    }
    notifyError(extractError(lastErr) || 'Failed to delete trade')
  }

  const closeAllTrades = async (botId: number, mode: 'market' | 'limit') => {
    if (!userId) return
    const ok = window.confirm(`Close ALL open trades by ${mode}?`); if (!ok) return
    try { await api.post(`/users/${userId}/bots/${botId}/proxy/freqtrade/forceexit`, { tradeid: 'all', ordertype: mode }); setLiveTrades([]); setLiveRefreshKey(k => k + 1); notifySuccess(`All trades closed by ${mode}`) } catch (e:any) { notifyError(extractError(e) || `Failed to close all trades (${mode})`) }
  }

  // Sync trades with platform (for live mode bots)
  const syncTradesWithPlatform = async (botId: number) => {
    if (!userId) return
    try {
      const res = await api.post(`/users/${userId}/bots/${botId}/trades/sync`)
      const data = res.data || {}
      if (data.deleted && data.deleted > 0) {
        console.log(`Trade sync: Removed ${data.deleted} orphaned trade(s) from bot ${botId}`)
        // Refresh live trades after sync
        setLiveRefreshKey(k => k + 1)
      }
    } catch (e: any) {
      // Silent fail - don't notify user on background sync errors
      console.error('Trade sync failed:', extractError(e))
    }
  }

  // Periodic trade sync for live mode bots (every 5 minutes)
  useEffect(() => {
    if (!selected || !userId) return
    const isLiveMode = String(selected.mode || '').toLowerCase() === 'live'
    if (!isLiveMode) return

    // Initial sync
    syncTradesWithPlatform(selected.id)

    // Set up periodic sync every 5 minutes
    const intervalId = setInterval(() => {
      syncTradesWithPlatform(selected.id)
    }, 5 * 60 * 1000) // 5 minutes

    return () => clearInterval(intervalId)
  }, [selected?.id, selected?.mode, userId])

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
        <h2 style={{ margin: 0 }}>Bots</h2>
        <button onClick={() => setShowCreate(true)} style={{ padding: '8px 12px', borderRadius: 6, border: '1px solid #2563eb', background: '#2563eb', color: '#fff', cursor: 'pointer' }}>+ Create Bot</button>
      </div>
      {showCreate && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 40 }}>
          <div style={{ background: '#fff', borderRadius: 10, padding: 16, width: 'min(92vw, 520px)', boxShadow: '0 10px 30px rgba(0,0,0,0.2)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
              <h3 style={{ margin: 0 }}>Create a new bot</h3>
              <button onClick={() => setShowCreate(false)} style={{ border: 'none', background: 'transparent', fontSize: 20, lineHeight: 1, cursor: 'pointer' }}>&times;</button>
            </div>
            <CreateBotForm onSubmit={async (values) => { if (!userId) return; setCreating(true); setCreateError(null); try { const res = await api.post(`/users/${userId}/bots`, values); await loadBots(userId); setShowCreate(false); if (res.data?.id) setSelectedId(res.data.id); notifySuccess('Bot created successfully') } catch (e:any) { const msg = extractError(e) || 'Failed to create bot'; setCreateError(msg); notifyError(msg) } finally { setCreating(false) } }} onCancel={() => setShowCreate(false)} submitting={creating} />
            {createError && <div style={{ marginTop: 10, color: '#dc2626' }}>{createError}</div>}
          </div>
        </div>
      )}
      {bots.length === 0 ? (
        <div>No bots yet.</div>
      ) : (
        <div>
          <div style={{ display: 'flex', gap: 8, borderBottom: '1px solid #e5e7eb', marginBottom: 12, flexWrap:'wrap' }}>
            {bots.map((b:any) => (
              <button key={b.id} onClick={() => setSelectedId(b.id)} style={{ padding: '8px 12px', border: '1px solid #e5e7eb', borderBottom: selectedId === b.id ? '2px solid #3b82f6' : '1px solid #e5e7eb', borderRadius: '6px 6px 0 0', background: selectedId === b.id ? '#f0f7ff' : '#fff', cursor: 'pointer' }}>{b.name}</button>
            ))}
          </div>
          {selected && (
            <div style={{ border: '1px solid #e5e7eb', borderRadius: 8, padding: 12 }}>
              <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginBottom: 10, flexWrap: 'wrap' }}>
                <div>{selected.id}-{selected.name}</div>
                <button onClick={() => handleDeleteBot(selected.id)} style={{ padding: '6px 10px', borderRadius: 6, border: '1px solid #6b7280', background: '#fff', color: '#374151' }}>Delete</button>
              </div>

              <div style={{ marginTop: 16, paddingTop: 12, borderTop: '1px solid #e5e7eb' }}>
                <div style={{ display: 'flex', gap: 8, marginBottom: 10, borderBottom: '1px solid #e5e7eb', flexWrap:'wrap' }}>
                  <button onClick={()=>setViewTab('trade')} style={{ padding: '6px 10px', borderRadius: '6px 6px 0 0', border: '1px solid #e5e7eb', borderBottom: viewTab==='trade' ? '2px solid #3b82f6' : '1px solid #e5e7eb', background: viewTab==='trade' ? '#f0f7ff' : '#fff' }}>Trade</button>
                  <button onClick={()=>setViewTab('performance')} style={{ padding: '6px 10px', borderRadius: '6px 6px 0 0', border: '1px solid #e5e7eb', borderBottom: viewTab==='performance' ? '2px solid #3b82f6' : '1px solid #e5e7eb', background: viewTab==='performance' ? '#f0f7ff' : '#fff' }}>Performance</button>
                  <button onClick={()=>setViewTab('balance')} style={{ padding: '6px 10px', borderRadius: '6px 6px 0 0', border: '1px solid #e5e7eb', borderBottom: viewTab==='balance' ? '2px solid #3b82f6' : '1px solid #e5e7eb', background: viewTab==='balance' ? '#f0f7ff' : '#fff' }}>Balance</button>
                  <button onClick={()=>setViewTab('period')} style={{ padding: '6px 10px', borderRadius: '6px 6px 0 0', border: '1px solid #e5e7eb', borderBottom: viewTab==='period' ? '2px solid #3b82f6' : '1px solid #e5e7eb', background: viewTab==='period' ? '#f0f7ff' : '#fff' }}>Period</button>
                  <button onClick={()=>setViewTab('config')} style={{ padding: '6px 10px', borderRadius: '6px 6px 0 0', border: '1px solid #e5e7eb', borderBottom: viewTab==='config' ? '2px solid #3b82f6' : '1px solid #e5e7eb', background: viewTab==='config' ? '#f0f7ff' : '#fff' }}>Config</button>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '320px 1fr', gap: 12 }}>
                  {(() => {
                    const d = details[selected.id]
                    const running = !!d?.runtime?.running
                    const starting = !!d?.starting
                    const stopping = !!d?.stopping
                    const cfg = details[selected.id]?.config || {}
                    const ps = effectivePairs
                    return (
                      <div className="sidebar" style={{ borderRight: '1px solid #e5e7eb', paddingRight: 12 }}>
                        <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8, flexWrap: 'wrap' }}>
                          <div style={{ display: 'inline-flex', gap: 6, alignItems: 'center', border: '1px solid #e5e7eb', borderRadius: 6, padding: '2px 4px' }}>
                            <button onClick={() => handleSetRunMode(selected.id, 'dryrun')} disabled={running} style={{ padding: '4px 8px', borderRadius: 4, border: '1px solid #e5e7eb', background: (selected.mode === 'dryrun') ? '#eef2ff' : '#fff' }}>Dryrun</button>
                            <button onClick={() => handleSetRunMode(selected.id, 'live')} disabled={running} style={{ padding: '4px 8px', borderRadius: 4, border: '1px solid #e5e7eb', background: (selected.mode === 'live') ? '#eef2ff' : '#fff' }}>Live</button>
                          </div>
                          {!running ? (
                            <button onClick={() => handleStartBot(selected.id)} disabled={starting} style={{ padding: '6px 10px', borderRadius: 6, border: '1px solid #16a34a', background: starting ? '#dcfce7' : '#16a34a', color: '#fff' }}>{starting ? 'Starting…' : 'Start'}</button>
                          ) : (
                            <button onClick={() => handleStopBot(selected.id)} disabled={stopping} style={{ padding: '6px 10px', borderRadius: 6, border: '1px solid #ef4444', background: stopping ? '#fee2e2' : '#ef4444', color: '#fff' }}>{stopping ? 'Stopping…' : 'Stop'}</button>
                          )}
                          <div style={{ display: 'inline-flex', gap: 6, alignItems: 'center', border: '1px solid #e5e7eb', borderRadius: 6, padding: '2px 4px' }}>
                            <label style={{ fontSize: 12, color: '#374151' }}>Update:</label>
                            <select value={livePollSec} onChange={(e) => setLivePollSec(Number(e.target.value))} style={{ padding: '4px 6px', borderRadius: 6, border: '1px solid #e5e7eb' }}>{[1,5,10,30].map(sec => <option key={sec} value={sec}>{sec}s</option>)}</select>
                          </div>
                        </div>

                        <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 8 }}>
                          <button title="Open Trades" onClick={() => setLiveSubTab('trades')} style={{ padding: 6, borderRadius: 6, border: '1px solid #e5e7eb', background: liveSubTab==='trades' ? '#eef2ff' : '#fff' }}>Open Trades</button>
                          <button title="Open Orders" onClick={() => setLiveSubTab('orders')} style={{ padding: 6, borderRadius: 6, border: '1px solid #e5e7eb', background: liveSubTab==='orders' ? '#eef2ff' : '#fff' }}>Open Orders</button>
                          <button title="Closed Trades" onClick={() => setLiveSubTab('closed')} style={{ padding: 6, borderRadius: 6, border: '1px solid #e5e7eb', background: liveSubTab==='closed' ? '#eef2ff' : '#fff' }}>Closed Trades</button>
                        </div>

                        <div style={{ border: '1px solid #e5e7eb', borderRadius: 6, overflow: 'hidden' }}>
                          <div style={{ padding: 8, borderBottom: '1px solid #e5e7eb', background: '#f9fafb', fontWeight: 600, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <span>Pairs</span>
                            {(() => {
                              const pairlists = cfg?.pairlists || []
                              const hasRemote = pairlists.some((pl: any) => pl.method === 'RemotePairList' && pl.scanner_id)
                              return hasRemote ? (
                                <span style={{ fontSize: 10, background: '#dbeafe', color: '#1e40af', padding: '2px 6px', borderRadius: 4, fontWeight: 500 }}>
                                  🔄 Scanner
                                </span>
                              ) : null
                            })()}
                          </div>
                          <div style={{ maxHeight: 360, overflow: 'auto' }}>
                            {ps.map((p: string) => { const r = Number(pairProfitMap[p] || 0); const badge = isNaN(r) ? '' : `${(r*100).toFixed(2)}%`; const badgeStyle = r < 0 ? { color: '#dc2626', border: '1px solid #ef4444', borderRadius: 6, padding: '2px 6px' } : { color: '#16a34a', border: '1px solid #16a34a', borderRadius: 6, padding: '2px 6px' }; return (<div key={p} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: 8, borderBottom: '1px solid #f3f4f6', background: livePair === p ? '#eef2ff' : '#fff', cursor: 'pointer' }} onClick={() => setLivePair(p)}><span>{p}</span><span style={badgeStyle}>{badge}</span></div>) })}
                          </div>
                        </div>

                        <div style={{ marginTop: 8 }}>
                          <BotControls userId={userId!} botId={selected.id} />
                        </div>
                      </div>
                    )
                  })()}

                  <div>
                    {viewTab === 'trade' && (
                      <>
                        <LiveAnalyticsContainer key={liveRefreshKey} userId={userId ?? undefined} botId={selected.id} pair={livePair ?? undefined} timeframe={liveTf ?? undefined} showSelectors={false} enabled={!!details[selected.id]?.runtime?.running} pollingSec={livePollSec} onOpenTrades={(t) => setLiveTrades(Array.isArray(t) ? t : [])} />
                        <TradesPanel setLiveSubTab={setLiveSubTab} cancelOpenOrder={cancelOpenOrder} selected={selected} liveTrades={liveTrades} liveTradesError={liveTradesError} liveSubTab={liveSubTab} liveTradesLoading={liveTradesLoading} liveOpenOrders={liveOpenOrders} liveOrdersError={liveOrdersError} setLiveRefreshKey={setLiveRefreshKey} closeTrade={closeTrade} deleteTrade={deleteTrade} closeAllTrades={closeAllTrades} historyTrades={historyTrades} historyLoading={historyLoading} historyError={historyError} historyDetails={historyDetails} loadTradeDetails={loadTradeDetails} resetDryrunTrades={()=>{ if (!selected) return; if (String(selected.mode).toLowerCase() !== 'dryrun') { notifyError('Reset is only available in dryrun mode'); return } }} historyResetting={historyResetting} perfByPair={perfByPair} profitSummary={profitSummary} balance={balance} balanceLoading={balanceLoading} balanceError={balanceError} periodRows={periodRows} />
                      </>
                    )}
                    {viewTab === 'performance' && (
                      <>
                        {profitSummary ? (
                          <div style={{ display:'grid', gridTemplateColumns:'200px 1fr', rowGap:6, marginBottom:8 }}>
                            <div><strong>Total Profit</strong></div><div>{Number(profitSummary?.profit_abs || 0).toFixed(4)} ({((profitSummary?.profit_ratio || 0) * 100).toFixed(2)}%)</div>
                            <div><strong>Closed Trades</strong></div><div>{profitSummary?.total_trades ?? '-'}</div>
                            <div><strong>Avg Profit Ratio</strong></div><div>{Number(profitSummary?.avg_profit_ratio || 0).toFixed(4)}</div>
                            <div><strong>Avg Duration</strong></div><div>{profitSummary?.avg_duration ?? '-'}</div>
                          </div>
                        ) : (
                          <div style={{ fontSize: 12, color:'#6b7280' }}>No profit summary.</div>
                        )}
                        {perfByPair && perfByPair.length > 0 ? (
                          <div style={{ maxHeight: 260, overflow:'auto', border:'1px solid #e5e7eb', borderRadius:6 }}>
                            <table style={{ width:'100%', borderCollapse:'collapse', fontSize:12 }}>
                              <thead>
                                <tr>
                                  <th style={{ textAlign: 'left', padding:6, borderBottom:'1px solid #e5e7eb' }}>Pair</th>
                                  <th style={{ textAlign: 'right', padding:6, borderBottom:'1px solid #e5e7eb' }}>Profit Abs</th>
                                  <th style={{ textAlign: 'right', padding:6, borderBottom:'1px solid #e5e7eb' }}>Profit Ratio</th>
                                  <th style={{ textAlign: 'right', padding:6, borderBottom:'1px solid #e5e7eb' }}>Trades</th>
                                </tr>
                              </thead>
                              <tbody>
                                {perfByPair.map((p: any, idx: number) => (
                                  <tr key={idx}>
                                    <td style={{ padding:6, borderBottom:'1px solid #f3f4f6' }}>{p.pair || '-'}</td>
                                    <td style={{ padding:6, textAlign:'right', borderBottom:'1px solid #f3f4f6' }}>{Number(p.profit_abs || 0).toFixed(4)}</td>
                                    <td style={{ padding:6, textAlign:'right', borderBottom:'1px solid #f3f4f6' }}>{Number(p.profit_ratio || 0).toFixed(4)}</td>
                                    <td style={{ padding:6, textAlign:'right', borderBottom:'1px solid #f3f4f6' }}>{p.trades ?? p.count ?? '-'}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        ) : (
                          <div style={{ fontSize: 12, color:'#6b7280' }}>No performance data.</div>
                        )}
                      </>
                    )}
                    {viewTab === 'balance' && (
                      <>
                        {balanceError && <div style={{ color: '#dc2626', marginBottom: 6 }}>{balanceError}</div>}
                        {balanceError && balanceNavigate && (
                          <div style={{ marginBottom: 6 }}>
                            <button onClick={() => navigate(balanceNavigate!)} style={{ padding:'6px 10px', borderRadius:6, border:'1px solid #2563eb', background:'#2563eb', color:'#fff' }}>Go to Settings</button>
                          </div>
                        )}
                        {balanceLoading && <div style={{ fontSize: 12, color: '#6b7280' }}>Loading balance…</div>}
                        {!balanceLoading && !balance && <div style={{ fontSize: 12, color: '#6b7280' }}>No balance data.</div>}
                        {balance && (
                          <div style={{ maxHeight: 260, overflow:'auto', border:'1px solid #e5e7eb', borderRadius:6 }}>
                            <table style={{ width:'100%', borderCollapse:'collapse', fontSize:12 }}>
                              <thead>
                                <tr>
                                  <th style={{ textAlign:'left', padding:6, borderBottom:'1px solid #e5e7eb' }}>Currency</th>
                                  <th style={{ textAlign:'right', padding:6, borderBottom:'1px solid #e5e7eb' }}>Available</th>
                                  <th style={{ textAlign:'right', padding:6, borderBottom:'1px solid #e5e7eb' }}>in USDT</th>
                                </tr>
                              </thead>
                              <tbody>
                                {(() => {
                                  const rows: Array<{ c:string; a:number; u:number|null }> = []
                                  const cur = (balance as any)?.currencies || (balance as any)?.balance || (balance as any)?.assets || {}
                                  if (Array.isArray(cur)) {
                                    for (const r of cur) rows.push({ c: r?.currency || r?.asset || '-', a: Number(r?.available || r?.free || r?.balance || 0), u: (r?.in_usdt ?? r?.usd ?? null) })
                                  } else if (typeof cur === 'object') {
                                    for (const [k,v] of Object.entries(cur)) { const val:any = v; rows.push({ c: k, a: Number(val?.available || val?.free || (val as any) || 0), u: (val?.in_usdt ?? (val as any)?.usd ?? null) }) }
                                  }
                                  return rows.map((r, idx) => (
                                    <tr key={idx}>
                                      <td style={{ padding:6, borderBottom:'1px solid #f3f4f6' }}>{r.c}</td>
                                      <td style={{ padding:6, textAlign:'right', borderBottom:'1px solid #f3f4f6' }}>{(r.a || 0).toFixed(4)}</td>
                                      <td style={{ padding:6, textAlign:'right', borderBottom:'1px solid #f3f4f6' }}>{r.u != null ? Number(r.u).toFixed(4) : '-'}</td>
                                    </tr>
                                  ))
                                })()}
                              </tbody>
                            </table>
                          </div>
                        )}
                      </>
                    )}
                    {viewTab === 'period' && (
                      <>
                        {periodRows && periodRows.length ? (
                          <div style={{ maxHeight: 300, overflow:'auto', border:'1px solid #e5e7eb', borderRadius:6 }}>
                            <table style={{ width:'100%', borderCollapse:'collapse', fontSize:12 }}>
                              <thead>
                                <tr>
                                  <th style={{ textAlign:'left', padding:6, borderBottom:'1px solid #e5e7eb' }}>Day</th>
                                  <th style={{ textAlign:'right', padding:6, borderBottom:'1px solid #e5e7eb' }}>Profit</th>
                                  <th style={{ textAlign:'right', padding:6, borderBottom:'1px solid #e5e7eb' }}>Trades</th>
                                  <th style={{ textAlign:'right', padding:6, borderBottom:'1px solid #e5e7eb' }}>Entries</th>
                                </tr>
                              </thead>
                              <tbody>
                                {periodRows.map((r, idx) => (
                                  <tr key={idx}>
                                    <td style={{ padding:6, borderBottom:'1px solid #f3f4f6' }}>{r.day}</td>
                                    <td style={{ padding:6, textAlign:'right', borderBottom:'1px solid #f3f4f6' }}>{Number(r.profit||0).toFixed(4)}</td>
                                    <td style={{ padding:6, textAlign:'right', borderBottom:'1px solid #f3f4f6' }}>{r.trades}</td>
                                    <td style={{ padding:6, textAlign:'right', borderBottom:'1px solid #f3f4f6' }}>{r.inCount}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        ) : (
                          <div style={{ fontSize: 12, color:'#6b7280' }}>No period data.</div>
                        )}
                      </>
                    )}
                    {viewTab === 'config' && (() => {
                      const d = details[selected.id]
                      const running = !!d?.runtime?.running
                      const disabled = running
                      const cfg = details[selected.id]?.config || {}
                      const saveRaw = async () => {
                        if (!userId) return
                        if (disabled) { notifyError('Stop the bot before updating config'); return }
                        try {
                          const obj = JSON.parse(rawConfigText)
                          const allowed = ['pair_whitelist','pair_blacklist','pairlists','stake_currency','stake_amount','dry_run','dry_run_wallet','meta','trading_mode','margin_mode','liquidation_buffer','leverage','strategy','timeframe','fiat_display_currency','available_capital','entry_pricing','exit_pricing']
                          const patch: any = {}
                          for (const k of allowed) if (k in obj) patch[k] = obj[k]
                          await api.patch(`/config/bot/${selected.id}`, patch)
                          await refreshBotDetails(selected.id)
                          notifySuccess('Config updated')
                        } catch (e:any) { notifyError(extractError(e) || 'Failed to update config') }
                      }
                      const saveForm = async () => {
                        if (!userId) return
                        if (disabled) { notifyError('Stop the bot before updating config'); return }
                        try {
                          const pairs = formPairsText.split(/\r?\n|,\s*/).map(s => s.trim()).filter(s => s.length > 0)
                          const blacklist = formPairBlacklistText.split(/\r?\n|,\s*/).map(s => s.trim()).filter(s => s.length > 0)
                          const patch: any = {
                            stake_currency: formStakeCurrency,
                            stake_amount: isNaN(Number(formStakeAmount)) ? formStakeAmount : Number(formStakeAmount),
                            pair_whitelist: pairs,
                            pair_blacklist: blacklist.length > 0 ? blacklist : undefined,
                            pairlists: formPairlists.length > 0 ? formPairlists : undefined,
                            trading_mode: formTradingMode,
                            margin_mode: formTradingMode === 'futures' ? formMarginMode : undefined,
                            liquidation_buffer: formTradingMode === 'futures' ? Number(formLiquidationBuffer || 0) : undefined,
                            leverage: formTradingMode === 'futures' ? Number(formLeverage || 1) : undefined,
                            fiat_display_currency: formFiatDisplayCurrency,
                            strategy: formStrategyName || undefined,
                            entry_pricing: {
                              price_side: entryPriceSide,
                              use_order_book: entryUseOrderBook,
                              order_book_top: Number(entryOrderBookTop || 1),
                              price_last_balance: Number(entryPriceLastBalance || 0),
                              check_depth_of_market: { enabled: entryDepthEnabled, bids_to_ask_delta: Number(entryDepthBidsToAskDelta || 0) }
                            },
                            exit_pricing: {
                              price_side: exitPriceSide,
                              use_order_book: exitUseOrderBook,
                              order_book_top: Number(exitOrderBookTop || 1),
                              price_last_balance: Number(exitPriceLastBalance || 0),
                              check_depth_of_market: { enabled: exitDepthEnabled, bids_to_ask_delta: Number(exitDepthBidsToAskDelta || 0) }
                            },
                          }
                          // optional live-only config
                          if (formAvailableCapital && formAvailableCapital.trim().length > 0) {
                            const ac = Number(formAvailableCapital)
                            if (!isNaN(ac)) patch.available_capital = ac
                          }
                          if (formDryRunWallet && formDryRunWallet.trim().length) {
                            try {
                              const dwParsed = JSON.parse(formDryRunWallet)
                              patch.dry_run_wallet = dwParsed
                            } catch {
                              const num = Number(formDryRunWallet)
                              if (!isNaN(num)) patch.dry_run_wallet = num
                            }
                          }
                          await api.patch(`/config/bot/${selected.id}`, patch)
                          await refreshBotDetails(selected.id)
                          notifySuccess('Config updated')
                        } catch (e:any) { notifyError(extractError(e) || 'Failed to update config') }
                      }
                      return (
                        <div>
                          <div style={{ display:'flex', gap:8, borderBottom:'1px solid #e5e7eb', marginBottom:8 }}>
                            <button onClick={()=>setConfigSubTab('form')} style={{ padding:'6px 10px', borderRadius:'6px 6px 0 0', border:'1px solid #e5e7eb', borderBottom: configSubTab==='form' ? '2px solid #3b82f6' : '1px solid #e5e7eb', background: configSubTab==='form' ? '#f0f7ff' : '#fff' }}>Form</button>
                            <button onClick={()=>setConfigSubTab('raw')} style={{ padding:'6px 10px', borderRadius:'6px 6px 0 0', border:'1px solid #e5e7eb', borderBottom: configSubTab==='raw' ? '2px solid #3b82f6' : '1px solid #e5e7eb', background: configSubTab==='raw' ? '#f0f7ff' : '#fff' }}>Raw JSON</button>
                            {disabled && <div style={{ marginLeft:'auto', fontSize:12, color:'#dc2626' }}>Bot is running — config is read-only</div>}
                          </div>
                          {configSubTab === 'raw' ? (
                            <div>
                              <textarea value={rawConfigText} onChange={e=>setRawConfigText(e.target.value)} disabled={disabled} style={{ width:'100%', minHeight: 280, border:'1px solid #e5e7eb', borderRadius:8, padding:8, fontFamily:'monospace' }} />
                              <div style={{ marginTop:8 }}>
                                <button onClick={saveRaw} disabled={disabled} style={{ padding:'6px 10px', borderRadius:6, border:'1px solid #2563eb', background: disabled ? '#e5e7eb' : '#2563eb', color:'#fff' }}>Save</button>
                                <button onClick={()=>{ try { setRawConfigText(JSON.stringify(cfg ?? {}, null, 2)) } catch {} }} style={{ marginLeft:8, padding:'6px 10px', borderRadius:6, border:'1px solid #6b7280', background:'#fff' }}>Reset</button>
                              </div>
                            </div>
                          ) : (
                            <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:10 }}>
                              <div>
                                <label style={{ display:'block', fontSize:12 }}>Stake Currency</label>
                                <input value={formStakeCurrency} onChange={e=>setFormStakeCurrency(e.target.value)} disabled={disabled} style={{ width:'100%', padding:6, border:'1px solid #e5e7eb', borderRadius:6 }} />
                              </div>
                              <div>
                                <label style={{ display:'block', fontSize:12 }}>Stake Amount</label>
                                <input value={formStakeAmount} onChange={e=>setFormStakeAmount(e.target.value)} disabled={disabled} style={{ width:'100%', padding:6, border:'1px solid #e5e7eb', borderRadius:6 }} />
                              </div>
                              <div style={{ gridColumn:'1 / span 2' }}>
                                <label style={{ display:'block', fontSize:12 }}>Pairs (one per line)</label>
                                <textarea value={formPairsText} onChange={e=>setFormPairsText(e.target.value)} disabled={disabled} style={{ width:'100%', minHeight: 120, border:'1px solid #e5e7eb', borderRadius:6, padding:6 }} />
                              </div>
                              <div style={{ gridColumn:'1 / span 2' }}>
                                <PairlistConfig 
                                  pairBlacklist={formPairBlacklistText}
                                  pairlists={formPairlists}
                                  onPairBlacklistChange={setFormPairBlacklistText}
                                  onPairlistsChange={setFormPairlists}
                                  disabled={disabled}
                                  userId={userId || undefined}
                                />
                              </div>
                              <div>
                                <label style={{ display:'block', fontSize:12 }}>Strategy</label>
                                <select value={formStrategyName} onChange={e=>setFormStrategyName(e.target.value)} disabled={disabled} style={{ width:'100%', padding:6, border:'1px solid #e5e7eb', borderRadius:6 }}>
                                  <option value="">(none)</option>
                                  {strategies.map(s => (<option key={s.name} value={s.name}>{s.name}</option>))}
                                </select>
                              </div>
                              <div>
                                <label style={{ display:'block', fontSize:12 }}>Fiat Display Currency</label>
                                <input value={formFiatDisplayCurrency} onChange={e=>setFormFiatDisplayCurrency(e.target.value)} disabled={disabled} style={{ width:'100%', padding:6, border:'1px solid #e5e7eb', borderRadius:6 }} />
                              </div>
                              <div>
                                <label style={{ display:'block', fontSize:12 }}>Trading Mode</label>
                                <select value={formTradingMode} onChange={e=>setFormTradingMode(e.target.value as any)} disabled={disabled} style={{ width:'100%', padding:6, border:'1px solid #e5e7eb', borderRadius:6 }}>
                                  <option value="spot">Spot</option>
                                  <option value="futures">Futures</option>
                                </select>
                              </div>
                              {formTradingMode === 'futures' && (
                                <>
                                  <div>
                                    <label style={{ display:'block', fontSize:12 }}>Margin Mode</label>
                                    <input value={formMarginMode} onChange={e=>setFormMarginMode(e.target.value)} disabled={disabled} style={{ width:'100%', padding:6, border:'1px solid #e5e7eb', borderRadius:6 }} />
                                  </div>
                                  <div>
                                    <label style={{ display:'block', fontSize:12 }}>Liquidation Buffer</label>
                                    <input value={formLiquidationBuffer} onChange={e=>setFormLiquidationBuffer(e.target.value)} disabled={disabled} style={{ width:'100%', padding:6, border:'1px solid #e5e7eb', borderRadius:6 }} />
                                  </div>
                                  <div>
                                    <label style={{ display:'block', fontSize:12 }}>Leverage</label>
                                    <input type="number" value={formLeverage} onChange={e=>setFormLeverage(Number(e.target.value))} disabled={disabled} style={{ width:'100%', padding:6, border:'1px solid #e5e7eb', borderRadius:6 }} />
                                  </div>
                                </>
                              )}
                              <div style={{ gridColumn:'1 / span 2' }}>
                                <label style={{ display:'block', fontSize:12 }}>Live available capital</label>
                                <input value={formAvailableCapital} onChange={e=>setFormAvailableCapital(e.target.value)} disabled={disabled} placeholder="e.g., 1000" style={{ width:'100%', padding:6, border:'1px solid #e5e7eb', borderRadius:6 }} />
                              </div>
                              <div style={{ gridColumn:'1 / span 2', border:'1px solid #e5e7eb', borderRadius:6, padding:8 }}>
                                <div style={{ fontWeight:600, marginBottom:6 }}>Entry Pricing</div>
                                <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:10 }}>
                                  <div>
                                    <label style={{ display:'block', fontSize:12 }}>Price Side</label>
                                    <select value={entryPriceSide} onChange={e=>setEntryPriceSide(e.target.value as any)} disabled={disabled} style={{ width:'100%', padding:6, border:'1px solid #e5e7eb', borderRadius:6 }}>
                                      <option value="ask">ask</option>
                                      <option value="bid">bid</option>
                                      <option value="same">same</option>
                                      <option value="other">other</option>
                                    </select>
                                  </div>
                                  <div style={{ display:'flex', alignItems:'center', gap:6 }}>
                                    <input type="checkbox" checked={entryUseOrderBook} onChange={e=>setEntryUseOrderBook(e.target.checked)} disabled={disabled} />
                                    <label style={{ fontSize:12 }}>Use Order Book</label>
                                  </div>
                                  <div>
                                    <label style={{ display:'block', fontSize:12 }}>Order Book Top</label>
                                    <input type="number" value={entryOrderBookTop} onChange={e=>setEntryOrderBookTop(Number(e.target.value))} disabled={disabled} style={{ width:'100%', padding:6, border:'1px solid #e5e7eb', borderRadius:6 }} />
                                  </div>
                                  <div>
                                    <label style={{ display:'block', fontSize:12 }}>Price Last Balance</label>
                                    <input type="number" value={entryPriceLastBalance} onChange={e=>setEntryPriceLastBalance(Number(e.target.value))} disabled={disabled} style={{ width:'100%', padding:6, border:'1px solid #e5e7eb', borderRadius:6 }} />
                                  </div>
                                  <div style={{ display:'flex', alignItems:'center', gap:6 }}>
                                    <input type="checkbox" checked={entryDepthEnabled} onChange={e=>setEntryDepthEnabled(e.target.checked)} disabled={disabled} />
                                    <label style={{ fontSize:12 }}>Check Depth of Market</label>
                                  </div>
                                  <div>
                                    <label style={{ display:'block', fontSize:12 }}>Bids to Ask Delta</label>
                                    <input type="number" value={entryDepthBidsToAskDelta} onChange={e=>setEntryDepthBidsToAskDelta(Number(e.target.value))} disabled={disabled} style={{ width:'100%', padding:6, border:'1px solid #e5e7eb', borderRadius:6 }} />
                                  </div>
                                </div>
                              </div>
                              <div style={{ gridColumn:'1 / span 2', border:'1px solid #e5e7eb', borderRadius:6, padding:8 }}>
                                <div style={{ fontWeight:600, marginBottom:6 }}>Exit Pricing</div>
                                <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:10 }}>
                                  <div>
                                    <label style={{ display:'block', fontSize:12 }}>Price Side</label>
                                    <select value={exitPriceSide} onChange={e=>setExitPriceSide(e.target.value as any)} disabled={disabled} style={{ width:'100%', padding:6, border:'1px solid #e5e7eb', borderRadius:6 }}>
                                      <option value="ask">ask</option>
                                      <option value="bid">bid</option>
                                      <option value="same">same</option>
                                      <option value="other">other</option>
                                    </select>
                                  </div>
                                  <div style={{ display:'flex', alignItems:'center', gap:6 }}>
                                    <input type="checkbox" checked={exitUseOrderBook} onChange={e=>setExitUseOrderBook(e.target.checked)} disabled={disabled} />
                                    <label style={{ fontSize:12 }}>Use Order Book</label>
                                  </div>
                                  <div>
                                    <label style={{ display:'block', fontSize:12 }}>Order Book Top</label>
                                    <input type="number" value={exitOrderBookTop} onChange={e=>setExitOrderBookTop(Number(e.target.value))} disabled={disabled} style={{ width:'100%', padding:6, border:'1px solid #e5e7eb', borderRadius:6 }} />
                                  </div>
                                  <div>
                                    <label style={{ display:'block', fontSize:12 }}>Price Last Balance</label>
                                    <input type="number" value={exitPriceLastBalance} onChange={e=>setExitPriceLastBalance(Number(e.target.value))} disabled={disabled} style={{ width:'100%', padding:6, border:'1px solid #e5e7eb', borderRadius:6 }} />
                                  </div>
                                  <div style={{ display:'flex', alignItems:'center', gap:6 }}>
                                    <input type="checkbox" checked={exitDepthEnabled} onChange={e=>setExitDepthEnabled(e.target.checked)} disabled={disabled} />
                                    <label style={{ fontSize:12 }}>Check Depth of Market</label>
                                  </div>
                                  <div>
                                    <label style={{ display:'block', fontSize:12 }}>Bids to Ask Delta</label>
                                    <input type="number" value={exitDepthBidsToAskDelta} onChange={e=>setExitDepthBidsToAskDelta(Number(e.target.value))} disabled={disabled} style={{ width:'100%', padding:6, border:'1px solid #e5e7eb', borderRadius:6 }} />
                                  </div>
                                </div>
                              </div>
                              <div style={{ gridColumn:'1 / span 2' }}>
                                <label style={{ display:'block', fontSize:12 }}>Dry Run Wallet (number or JSON)</label>
                                <textarea value={formDryRunWallet} onChange={e=>setFormDryRunWallet(e.target.value)} disabled={disabled} style={{ width:'100%', minHeight: 80, border:'1px solid #e5e7eb', borderRadius:6, padding:6 }} />
                              </div>
                              <div style={{ gridColumn:'1 / span 2', display:'flex', gap:8 }}>
                                <button onClick={saveForm} disabled={disabled} style={{ padding:'6px 10px', borderRadius:6, border:'1px solid #2563eb', background: disabled ? '#e5e7eb' : '#2563eb', color:'#fff' }}>Save</button>
                                <button onClick={()=>{ const cfg = details[selected.id]?.config || {}; setFormStakeCurrency(String(cfg?.stake_currency || 'USDT')); setFormStakeAmount(String(cfg?.stake_amount ?? '10')); const pairs = cfgPairs(cfg); setFormPairsText(Array.isArray(pairs) ? pairs.join('\n') : ''); const blacklist = cfg?.pair_blacklist; setFormPairBlacklistText(Array.isArray(blacklist) ? blacklist.join(', ') : ''); const pairlists = cfg?.pairlists; setFormPairlists(Array.isArray(pairlists) ? pairlists : []); const tm = String(cfg?.trading_mode || 'spot').toLowerCase(); setFormTradingMode(tm === 'futures' ? 'futures' : 'spot'); setFormMarginMode(String(cfg?.margin_mode || 'cross')); setFormLiquidationBuffer(String(cfg?.liquidation_buffer ?? '0.0')); try { setFormLeverage(Number(cfg?.leverage ?? 1) || 1) } catch { setFormLeverage(1) } const dw = cfg?.dry_run_wallet; if (typeof dw === 'object') { try { setFormDryRunWallet(JSON.stringify(dw)) } catch { setFormDryRunWallet('') } } else if (dw != null) { setFormDryRunWallet(String(dw)) } else { setFormDryRunWallet('') } setFormFiatDisplayCurrency(String(cfg?.fiat_display_currency || 'USD')); setFormAvailableCapital(cfg?.available_capital != null ? String(cfg?.available_capital) : ''); setFormStrategyName(String(cfg?.strategy || '')); const ep = (cfg?.entry_pricing || {}); setEntryPriceSide((ep?.price_side || 'same') as any); setEntryUseOrderBook(!!ep?.use_order_book); setEntryOrderBookTop(Number(ep?.order_book_top || 1)); setEntryPriceLastBalance(Number(ep?.price_last_balance || 0)); const ed = ep?.check_depth_of_market || {}; setEntryDepthEnabled(!!ed?.enabled); setEntryDepthBidsToAskDelta(Number(ed?.bids_to_ask_delta || 0)); const xp = (cfg?.exit_pricing || {}); setExitPriceSide((xp?.price_side || 'same') as any); setExitUseOrderBook(!!xp?.use_order_book); setExitOrderBookTop(Number(xp?.order_book_top || 1)); setExitPriceLastBalance(Number(xp?.price_last_balance || 0)); const xd = xp?.check_depth_of_market || {}; setExitDepthEnabled(!!xd?.enabled); setExitDepthBidsToAskDelta(Number(xd?.bids_to_ask_delta || 0)); }} style={{ padding:'6px 10px', borderRadius:6, border:'1px solid #6b7280', background:'#fff' }}>Reset</button>
                              </div>
                            </div>
                          )}
                        </div>
                      )
                    })()}
                  </div>
                </div>
              </div>

              <div style={{ marginTop: 16, paddingTop: 12, borderTop: '1px solid #e5e7eb' }}>
                <h4 style={{ margin: '0 0 8px 0' }}>Runtime Logs</h4>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8, flexWrap: 'wrap' }}>
                  <label>Tail:</label>
                  {[200, 500, 1000].map(n => (<button key={n} onClick={() => { setRtTail(n); fetchRuntimeLogs(selected.id, n) }} style={{ padding: '4px 8px', borderRadius: 6, border: rtTail === n ? '2px solid #3b82f6' : '1px solid #e5e7eb', background: rtTail === n ? '#eef2ff' : '#fff' }}>{n}</button>))}
                  <button onClick={() => fetchRuntimeLogs(selected.id)} style={{ padding: '4px 8px', borderRadius: 6, border: '1px solid #e5e7eb', background: '#fff' }}>Refresh</button>
                  <label style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                    <input type="checkbox" checked={autoRefreshLogs} onChange={(e) => setAutoRefreshLogs(e.target.checked)} />
                    Auto-refresh
                  </label>
                </div>
                <pre style={{ background: '#0b1020', color: '#d1d5db', padding: 8, borderRadius: 8, maxHeight: 240, overflow: 'auto' }}>{runtimeLogs.length ? runtimeLogs.join('\n') : 'No logs yet.'}</pre>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
