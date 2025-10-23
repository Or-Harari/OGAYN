import { useEffect, useState } from 'react'
import { api } from '@/lib/api'
import { useAuth } from '@/stores/auth'

export type ActiveStrategySpec = {
  name?: string
  clazz?: string
}

export type CreateBotFormValues = {
  name: string
  mode?: 'live' | 'dryrun' | 'backstage'
  active_strategy?: ActiveStrategySpec
}

export function CreateBotForm({
  initial,
  onSubmit,
  onCancel,
  submitting = false,
}: {
  initial?: Partial<CreateBotFormValues>
  onSubmit: (values: CreateBotFormValues) => void | Promise<void>
  onCancel?: () => void
  submitting?: boolean
}) {
  const [name, setName] = useState(initial?.name ?? '')
  const [mode, setMode] = useState<CreateBotFormValues['mode']>(initial?.mode ?? 'dryrun')
  const [strategyName, setStrategyName] = useState(initial?.active_strategy?.name ?? '')
  const [strategyClazz, setStrategyClazz] = useState(initial?.active_strategy?.clazz ?? '')
  const [error, setError] = useState<string | null>(null)
  const [strategies, setStrategies] = useState<string[]>([])
  const [loadingStrategies, setLoadingStrategies] = useState(false)
  const [strategiesError, setStrategiesError] = useState<string | null>(null)
  const userId = useAuth(s => s.userId)

  useEffect(() => {
    const fetchStrategies = async () => {
      if (!userId) return
      setLoadingStrategies(true)
      setStrategiesError(null)
      try {
        const res = await api.get(`/users/${userId}/strategies`)
        const list = Array.isArray(res.data) ? (res.data as string[]) : []
        setStrategies(list)
        // If initial has none and list exists, leave unselected to force explicit choice
      } catch (e: any) {
        const msg = e?.response?.data?.detail || e?.message || 'Failed to load strategies'
        setStrategiesError(String(msg))
      } finally {
        setLoadingStrategies(false)
      }
    }
    fetchStrategies()
  }, [userId])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    if (!name.trim()) {
      setError('Bot name is required')
      return
    }
    const payload: CreateBotFormValues = { name: name.trim() }
    if (mode) payload.mode = mode
    const active: ActiveStrategySpec = {}
    if (strategyName.trim()) active.name = strategyName.trim()
    if (strategyClazz.trim()) active.clazz = strategyClazz.trim()
    if (active.name || active.clazz) payload.active_strategy = active
    await onSubmit(payload)
  }

  return (
    <form onSubmit={handleSubmit} style={{ display: 'grid', gap: 12, minWidth: 320 }}>
      <div>
        <label style={{ display: 'block', fontWeight: 600, marginBottom: 4 }}>Bot Name</label>
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g., bot1"
          style={{ width: '100%', padding: '8px 10px', border: '1px solid #d1d5db', borderRadius: 6 }}
          disabled={submitting}
          required
        />
      </div>
      <div>
        <label style={{ display: 'block', fontWeight: 600, marginBottom: 4 }}>Mode</label>
        <select
          value={mode}
          onChange={(e) => setMode(e.target.value as CreateBotFormValues['mode'])}
          style={{ width: '100%', padding: '8px 10px', border: '1px solid #d1d5db', borderRadius: 6 }}
          disabled={submitting}
        >
          <option value="dryrun">Dry Run</option>
          <option value="live">Live</option>
          <option value="backstage">Backstage</option>
        </select>
      </div>
      <div style={{ display: 'grid', gap: 8 }}>
        <div style={{ fontWeight: 600 }}>Active Strategy</div>
        <select
          value={strategyName}
          onChange={(e) => setStrategyName(e.target.value)}
          style={{ width: '100%', padding: '8px 10px', border: '1px solid #d1d5db', borderRadius: 6 }}
          disabled={submitting || loadingStrategies}
        >
          <option value="">-- Select a strategy --</option>
          {strategies.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        {loadingStrategies && <div style={{ color: '#6b7280', fontSize: 12 }}>Loading strategies…</div>}
        {strategiesError && <div style={{ color: '#dc2626', fontSize: 12 }}>{strategiesError}</div>}
        <input
          type="text"
          value={strategyClazz}
          onChange={(e) => setStrategyClazz(e.target.value)}
          placeholder="Fully qualified class path (e.g., user.variants.Strategy4.Strategy4)"
          style={{ width: '100%', padding: '8px 10px', border: '1px solid #d1d5db', borderRadius: 6 }}
          disabled={submitting}
        />
        <div style={{ color: '#6b7280', fontSize: 12 }}>
          Choose a strategy from your workspace, or provide a custom class path. If both are provided, both will be stored.
        </div>
      </div>
      {error && <div style={{ color: '#dc2626' }}>{error}</div>}
      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
        {onCancel && (
          <button type="button" onClick={onCancel} disabled={submitting} style={{ padding: '8px 12px', borderRadius: 6, border: '1px solid #d1d5db', background: '#fff' }}>
            Cancel
          </button>
        )}
        <button type="submit" disabled={submitting} style={{ padding: '8px 12px', borderRadius: 6, border: '1px solid #2563eb', background: '#2563eb', color: '#fff' }}>
          {submitting ? 'Creating…' : 'Create Bot'}
        </button>
      </div>
    </form>
  )
}

export default CreateBotForm
