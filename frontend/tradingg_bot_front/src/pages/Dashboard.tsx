import React, { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '@/lib/api'
import { useAuth } from '@/stores/auth'
import { StatCard } from '@/components/StatCard'

interface BotItem { id: number; name: string; status: string; userdir: string; mode?: string }

export function Dashboard() {
  const navigate = useNavigate()
  const userId = useAuth(s => s.userId)
  const [bots, setBots] = useState<BotItem[]>([])
  const [balances, setBalances] = useState<Record<number, number | null>>({})
  const [profits, setProfits] = useState<Record<number, { live: { total: number; p24h: number; p7d: number; count: number; openCount: number }, dryrun: { total: number; p24h: number; p7d: number; count: number; openCount: number } }>>({})
  const [exchangeConnected, setExchangeConnected] = useState<boolean | null>(null)
  const [viewMode, setViewMode] = useState<'live' | 'dryrun'>('live')
  const [openStats, setOpenStats] = useState<Record<number, { count: number; profitAbs: number | null; profitPct: number | null }>>({})

  useEffect(() => {
    (async () => {
      if (!userId) return
      try {
        const res = await api.get(`/users/${userId}/bots`)
        const items = res.data as BotItem[]
        setBots(items || [])
      } catch {}
      try {
        const ex = await api.get(`/config/user/exchange/view`)
        const has = Boolean(ex?.data?.has_key) && Boolean(ex?.data?.has_secret)
        setExchangeConnected(has)
      } catch {
        setExchangeConnected(null)
      }
    })()
  }, [userId])

  useEffect(() => {
    (async () => {
      for (const b of bots) {
        // Balance: fetch for dryrun regardless; for live only if account connected
        const shouldFetchBalance = viewMode === 'dryrun' || (viewMode === 'live' && !!exchangeConnected)
        if (shouldFetchBalance) {
          try {
            const r = await api.get(`/users/${userId}/bots/${b.id}/balance`)
            const total = Number(r?.data?.total || r?.data?.balance_total || r?.data?.data?.total || 0)
            setBalances(prev => ({ ...prev, [b.id]: isFinite(total) ? total : null }))
          } catch {
            setBalances(prev => ({ ...prev, [b.id]: null }))
          }
        } else {
          setBalances(prev => ({ ...prev, [b.id]: null }))
        }
        // Profit from trades-history (compute live and dryrun separately)
        const compute = async (mode: 'live' | 'dryrun') => {
          try {
            const r = await api.get(`/users/${userId}/bots/${b.id}/trades-history`, { params: { mode, limit: 1000 } })
            const rows = Array.isArray(r.data) ? r.data : []
            let total = 0, p24h = 0, p7d = 0
            const now = Date.now()
            const ms24h = 24 * 60 * 60 * 1000
            const ms7d = 7 * ms24h
            let openCount = 0
            for (const t of rows) {
              const pa = Number(t.profit_abs ?? t.close_profit_abs ?? t.realized_profit ?? 0)
              total += pa
              const closed = Number(t.close_date || t.sell_date || 0)
              const ts = closed ? new Date(closed).getTime() : (t.date ? new Date(t.date).getTime() : 0)
              if (ts && now - ts <= ms24h) p24h += pa
              if (ts && now - ts <= ms7d) p7d += pa
              const st = String(t.status || '').toLowerCase()
              if (st === 'open' || !t.close_date) openCount += 1
            }
            setProfits(prev => ({
              ...prev,
              [b.id]: {
                live: mode === 'live' ? { total, p24h, p7d, count: rows.length, openCount } : (prev[b.id]?.live ?? { total: 0, p24h: 0, p7d: 0, count: 0, openCount: 0 }),
                dryrun: mode === 'dryrun' ? { total, p24h, p7d, count: rows.length, openCount } : (prev[b.id]?.dryrun ?? { total: 0, p24h: 0, p7d: 0, count: 0, openCount: 0 }),
              },
            }))
          } catch {
            setProfits(prev => ({
              ...prev,
              [b.id]: {
                live: mode === 'live' ? { total: 0, p24h: 0, p7d: 0, count: 0, openCount: 0 } : (prev[b.id]?.live ?? { total: 0, p24h: 0, p7d: 0, count: 0, openCount: 0 }),
                dryrun: mode === 'dryrun' ? { total: 0, p24h: 0, p7d: 0, count: 0, openCount: 0 } : (prev[b.id]?.dryrun ?? { total: 0, p24h: 0, p7d: 0, count: 0, openCount: 0 }),
              },
            }))
          }
        }
        await compute('live')
        await compute('dryrun')

        // Open trades profit/count (only when running) via Freqtrade /status
        const running = (b.status || '').toLowerCase() !== 'stopped'
        if (running) {
          try {
            const statusRes = await api.get(`/users/${userId}/bots/${b.id}/proxy/freqtrade/status`)
            const rows = Array.isArray(statusRes?.data?.open_trades)
              ? statusRes.data.open_trades
              : (Array.isArray(statusRes?.data) ? statusRes.data : [])
            const count = rows.length
            let abs = 0
            let pct = 0
            for (const t of rows) {
              abs += Number(
                t.current_profit_abs ??
                t.unrealized_profit_abs ??
                t.total_profit_abs ??
                t.profit_abs ??
                0
              )
              pct += Number(
                t.current_profit ??
                t.unrealized_profit ??
                t.total_profit_ratio ??
                t.profit_ratio ??
                0
              )
            }
            // Prefer aggregated open profit from /profit (profit_all_coin - profit_closed_coin)
            try {
              const pr = await api.get(`/users/${userId}/bots/${b.id}/proxy/freqtrade/profit`)
              const allCoin = Number(pr?.data?.profit_all_coin ?? NaN)
              const closedCoin = Number(pr?.data?.profit_closed_coin ?? NaN)
              if (!isNaN(allCoin) && !isNaN(closedCoin)) {
                abs = allCoin - closedCoin
              }
            } catch {}
            setOpenStats(prev => ({ ...prev, [b.id]: { count, profitAbs: isFinite(abs) ? abs : null, profitPct: isFinite(pct) ? pct : null } }))
          } catch {
            // Fallback: use openCount from history if available
            const pf = profits[b.id]
            const oc = viewMode === 'live' ? (pf?.live.openCount ?? 0) : (pf?.dryrun.openCount ?? 0)
            setOpenStats(prev => ({ ...prev, [b.id]: { count: oc, profitAbs: null, profitPct: null } }))
          }
        } else {
          // Bot not running: count can be derived from history; profit unavailable
          const pf = profits[b.id]
          const oc = viewMode === 'live' ? (pf?.live.openCount ?? 0) : (pf?.dryrun.openCount ?? 0)
          setOpenStats(prev => ({ ...prev, [b.id]: { count: oc, profitAbs: null, profitPct: null } }))
        }
      }
    })()
  }, [bots, userId, exchangeConnected, viewMode])

  const aggregate = useMemo(() => {
    let total = 0, p24h = 0, p7d = 0
    for (const b of bots) {
      const pf = profits[b.id]
      if (!pf) continue
      if (viewMode === 'live') {
        total += pf.live.total; p24h += pf.live.p24h; p7d += pf.live.p7d
      } else {
        total += pf.dryrun.total; p24h += pf.dryrun.p24h; p7d += pf.dryrun.p7d
      }
    }
    return { total, p24h, p7d }
  }, [bots, profits, viewMode])

  const displayBots = useMemo(() => {
    return bots.filter(b => {
      const pf = profits[b.id]
      const running = (b.status || '').toLowerCase() !== 'stopped'
      const hasDataForMode = viewMode === 'live' ? ((pf?.live.count ?? 0) > 0) : ((pf?.dryrun.count ?? 0) > 0)
      const runningForMode = running && (String(b.mode).toLowerCase() === viewMode)
      return runningForMode || hasDataForMode
    })
  }, [bots, profits])

  return (
    <div className="content">
      <h2>Dashboard</h2>
      <div style={{ marginBottom: 12 }}>
        <div style={{ display: 'inline-flex', gap: 8, background: '#111827', borderRadius: 999, padding: 4 }}>
          {(['live', 'dryrun'] as const).map(m => (
            <button
              key={m}
              onClick={() => setViewMode(m)}
              style={{
                padding: '6px 12px', borderRadius: 999,
                background: viewMode === m ? '#2563eb' : 'transparent',
                color: viewMode === m ? '#fff' : '#9ca3af', border: 'none', cursor: 'pointer'
              }}
            >{m === 'live' ? 'Live' : 'Dryrun'}</button>
          ))}
        </div>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 14 }}>
        <StatCard title="Total Profit" value={`${aggregate.total.toFixed(2)} USDT`} accent={aggregate.total >= 0 ? 'green' : 'red'} />
        <StatCard title="Last 24h" value={`${aggregate.p24h.toFixed(2)} USDT`} accent={aggregate.p24h >= 0 ? 'green' : 'red'} />
        <StatCard title="Last 7d" value={`${aggregate.p7d.toFixed(2)} USDT`} accent={aggregate.p7d >= 0 ? 'green' : 'red'} />
      </div>

      <h3 style={{ marginTop: 20 }}>Bots</h3>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 12 }}>
        {displayBots.map(b => {
          const bal = balances[b.id]
          const pf = profits[b.id]
          const sel = viewMode === 'live' ? pf?.live : pf?.dryrun
          const os = openStats[b.id]
          return (
            <div key={b.id} style={{ border: '1px solid #374151', borderRadius: 12, padding: 12, cursor: 'pointer' }} onClick={() => {
              try { localStorage.setItem('selected_bot_id', String(b.id)) } catch {}
              navigate('/bots')
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <div style={{ fontSize: 16, fontWeight: 600 }}>{b.name}</div>
                  {b.mode && (
                    <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 999, background: b.mode === 'live' ? '#064e3b' : '#1f2937', color: '#e5e7eb' }}>
                      {b.mode === 'live' ? 'Live' : b.mode === 'dryrun' ? 'Dryrun' : b.mode}
                    </span>
                  )}
                </div>
                <span style={{ fontSize: 12, color: (b.status || '').toLowerCase() === 'stopped' ? '#9ca3af' : '#10b981' }}>
                  {(b.status || '').toLowerCase() === 'stopped' ? 'stopped' : 'running'} {b.mode ? `(${b.mode})` : ''}
                  {(() => {
                    const pf = profits[b.id]
                    const histOpen = viewMode === 'live' ? (pf?.live.openCount ?? 0) : (pf?.dryrun.openCount ?? 0)
                    const cnt = os?.count ?? histOpen
                    return cnt > 0 ? ` • ${cnt} open` : ''
                  })()}
                </span>
              </div>
              <div style={{ marginTop: 10, display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 10 }}>
                <StatCard title={viewMode === 'live' ? 'Live Balance' : 'Dryrun Balance'} value={
                  viewMode === 'live'
                    ? (exchangeConnected === false ? "User's Live Account Not Connected" : ((bal ?? null) !== null ? `${bal!.toFixed(2)} USDT` : '—'))
                    : ((bal ?? null) !== null ? `${bal!.toFixed(2)} USDT` : '—')
                } />
                <StatCard title={viewMode === 'live' ? 'Live Profit' : 'Dryrun Profit'} value={`${(sel?.total ?? 0).toFixed(2)} USDT`} accent={(sel?.total ?? 0) >= 0 ? 'green' : 'red'} />
                <StatCard title={viewMode === 'live' ? '24h (Live)' : '24h (Dryrun)'} value={`${(sel?.p24h ?? 0).toFixed(2)} USDT`} accent={(sel?.p24h ?? 0) >= 0 ? 'green' : 'red'} />
                <StatCard title="Open Profit" value={
                  os && (os.profitAbs ?? null) !== null
                    ? `${(os.profitAbs ?? 0).toFixed(2)} USDT`
                    : (os && (os.profitPct ?? null) !== null ? `${(os.profitPct ?? 0).toFixed(2)} %` : '—')
                } accent={(os?.profitAbs ?? os?.profitPct ?? 0) >= 0 ? 'green' : 'red'} />
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
