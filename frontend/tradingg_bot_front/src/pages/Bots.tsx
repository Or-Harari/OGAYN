import { useEffect, useMemo, useState } from 'react'
import { useAuth } from '@/stores/auth'
import { useData } from '@/stores/data'
import { api } from '@/lib/api'
import CreateBotForm, { CreateBotFormValues } from '@/components/CreateBotForm'
import { useUI } from '@/stores/ui'
import './Bots.css'

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
  const [strategies, setStrategies] = useState<Array<{ name: string; clazz?: string }>>([])
  const [formStrategyName, setFormStrategyName] = useState<string>('')
  const [formStrategyClazz, setFormStrategyClazz] = useState<string>('')

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

  useEffect(() => {
    if (userId && bots.length === 0) {
      loadBots(userId)
    }
  }, [userId])

  // Initialize selected tab when bots first load
  useEffect(() => {
    if (!selectedId && bots.length > 0) {
      setSelectedId(bots[0].id)
    }
  }, [bots, selectedId])

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
    const act = b.active_strategy as any
    setFormStrategyName(String(act?.name ?? ''))
    setFormStrategyClazz(String(act?.clazz ?? ''))
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
      const pending: Promise<any>[] = []
      if (bot && (bot.mode || 'dryrun') !== formMode) {
        pending.push(api.patch(`/users/${userId}/bots/${botId}/mode`, { mode: formMode }))
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
      }
      pending.push(api.patch(`/users/${userId}/bots/${botId}/config`, payload))
      // Strategy update if changed
      const botAct = (bot as any)?.active_strategy || {}
      const curName = botAct?.name || ''
      const curClazz = botAct?.clazz || ''
      if (formStrategyName !== curName || (formStrategyClazz || '') !== (curClazz || '')) {
        const body = { active_strategy: { name: formStrategyName || null, clazz: formStrategyClazz || null } }
        pending.push(api.patch(`/users/${userId}/bots/${botId}/strategy`, body))
      }
      await Promise.all(pending)
      await refreshBotDetails(botId)
      notifySuccess('Configuration saved')
    } catch (e: any) {
      notifyError(extractError(e) || 'Failed to save configuration')
    }
  }

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
              {/* Actions */}
              <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginBottom: 10, flexWrap: 'wrap' }}>
                <div>{selected.id}-{selected.name}</div><div></div>

                {(() => {
                  const d = details[selected.id]
                  const running = !!d?.runtime?.running
                  const starting = !!d?.starting
                  const stopping = !!d?.stopping
                  const deleting = !!d?.deleting
                  return (
                    <>
                      {!running ? (
                        <button
                          onClick={() => handleStartBot(selected.id)}
                          disabled={starting || deleting}
                          style={{ padding: '6px 10px', borderRadius: 6, border: '1px solid #16a34a', background: starting ? '#dcfce7' : '#16a34a', color: '#fff', cursor: starting || deleting ? 'not-allowed' : 'pointer' }}
                        >
                          {starting ? 'Starting…' : 'Start'}
                        </button>
                      ) : (
                        <button
                          onClick={() => handleStopBot(selected.id)}
                          disabled={stopping || deleting}
                          style={{ padding: '6px 10px', borderRadius: 6, border: '1px solid #ef4444', background: stopping ? '#fee2e2' : '#ef4444', color: '#fff', cursor: stopping || deleting ? 'not-allowed' : 'pointer' }}
                        >
                          {stopping ? 'Stopping…' : 'Stop'}
                        </button>
                      )}
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
                {/* <div><strong>Userdir</strong></div><div>{selected.userdir}</div> */}
                <div><strong>Mode</strong></div><div>{selected.mode ?? '-'}</div>
                {/* Live runtime/status from backend */}
                <div><strong>Status</strong></div><div>{details[selected.id]?.status?.status ?? selected.status}</div>
                <div><strong>PID</strong></div><div>{details[selected.id]?.status?.pid ?? selected.pid ?? '-'}</div>
                <div><strong>Container</strong></div><div>{details[selected.id]?.status?.container ?? '-'}</div>
      
                {/* Config summary */}
                <div><strong>Strategy</strong></div>
                <div>{selected.active_strategy?.name}</div>
                {/* <div><strong>Strategy Path</strong></div> */}
                <div><strong>Trading Mode</strong></div><div>{String(details[selected.id]?.config?.trading_mode ?? '-')}</div>
                <div><strong>Stake Currency</strong></div><div>{String(details[selected.id]?.config?.stake_currency ?? '-')}</div>
                <div><strong>Pairs</strong></div>
                <div>{Array.isArray(details[selected.id]?.config?.pairs) ? (details[selected.id]?.config?.pairs as string[]).join(', ') : '-'}</div>
              </div>
              {/* Configuration editor */}
              <div style={{ marginTop: 16, paddingTop: 12, borderTop: '1px solid #e5e7eb' }}>
                <h4 style={{ margin: '0 0 8px 0' }}>Configuration</h4>
                <div style={{ display: 'grid', gridTemplateColumns: '160px 1fr', rowGap: 8, columnGap: 12 }}>
                  {/* Strategy selection */}
                  <label><strong>Strategy</strong></label>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                    <select value={formStrategyName} onChange={(e) => setFormStrategyName(e.target.value)} style={{ padding: 6, borderRadius: 6, border: '1px solid #e5e7eb' }}>
                      <option value="">-- select by name --</option>
                      {strategies ? strategies.map((s) => (
                        <option className='sss' key={s.name} value={s.name}>{s.name}</option>
                      )) : null}
                    </select>
                    <input
                      placeholder="or enter class path"
                      value={formStrategyClazz}
                      onChange={(e) => setFormStrategyClazz(e.target.value)}
                      style={{ padding: 6, borderRadius: 6, border: '1px solid #e5e7eb', flex: 1 }}
                    />
                  </div>

                  <label><strong>Mode</strong></label>
                  <select value={formMode} onChange={(e) => setFormMode(e.target.value)} style={{ padding: 6, borderRadius: 6, border: '1px solid #e5e7eb' }}>
                    <option value="live">live</option>
                    <option value="dryrun">dryrun</option>
                    <option value="backstage">backstage</option>
                  </select>

                  <label><strong>Trading Mode</strong></label>
                  <select value={formTradingMode} onChange={(e) => setFormTradingMode(e.target.value as any)} style={{ padding: 6, borderRadius: 6, border: '1px solid #e5e7eb' }}>
                    <option value="spot">spot</option>
                    <option value="futures">futures</option>
                  </select>

                  {formTradingMode === 'futures' && (
                    <>
                      <label><strong>Margin Mode</strong></label>
                      <select value={formMarginMode} onChange={(e) => setFormMarginMode(e.target.value)} style={{ padding: 6, borderRadius: 6, border: '1px solid #e5e7eb' }}>
                        <option value="cross">cross</option>
                        <option value="isolated">isolated</option>
                      </select>

                      <label><strong>Liquidation Buffer</strong></label>
                      <input value={formLiquidationBuffer} onChange={(e) => setFormLiquidationBuffer(e.target.value)} style={{ padding: 6, borderRadius: 6, border: '1px solid #e5e7eb' }} />
                    </>
                  )}

                  <label><strong>Stake Currency</strong></label>
                  <input value={formStakeCurrency} onChange={(e) => setFormStakeCurrency(e.target.value)} style={{ padding: 6, borderRadius: 6, border: '1px solid #e5e7eb' }} />

                  <label><strong>Stake Amount</strong></label>
                  <input value={formStakeAmount} onChange={(e) => setFormStakeAmount(e.target.value)} style={{ padding: 6, borderRadius: 6, border: '1px solid #e5e7eb' }} />

                  <label><strong>Pair Whitelist</strong></label>
                  <textarea value={formPairsText} onChange={(e) => setFormPairsText(e.target.value)} rows={3} placeholder="BTC/USDT, ETH/USDT" style={{ padding: 6, borderRadius: 6, border: '1px solid #e5e7eb', resize: 'vertical' }} />
                </div>
                <div style={{ marginTop: 10, display: 'flex', justifyContent: 'flex-end' }}>
                  <button onClick={() => handleSaveConfig(selected.id)} style={{ padding: '8px 12px', borderRadius: 6, border: '1px solid #2563eb', background: '#2563eb', color: '#fff', cursor: 'pointer' }}>
                    Save Configuration
                  </button>
                </div>
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
