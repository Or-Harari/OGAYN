import { useEffect, useState } from 'react'
import { api } from '@/lib/api'
import { useAuth } from '@/stores/auth'


export type CreateBotFormValues = {
  name: string
  mode?: 'live' | 'dryrun'
  leverage?: number
  strategy?: string
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
  const [strategyName, setStrategyName] = useState(initial?.strategy ?? '')
  const [leverage, setLeverage] = useState<number>(typeof initial?.leverage === 'number' ? initial!.leverage : 1)
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
  if (leverage && leverage > 0) payload.leverage = leverage
    if (strategyName.trim()) payload.strategy = strategyName.trim()
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
          {/* Backstage mode removed per revert */}
        </select>
      </div>
      <div>
        <label style={{ display: 'block', fontWeight: 600, marginBottom: 4 }}>Leverage (1-25)</label>
        <input
          type="number"
          min={1}
          max={25}
          step={1}
          value={leverage}
          onChange={(e) => setLeverage(Math.max(1, Math.min(25, Number(e.target.value) || 1)))}
          placeholder="e.g. 5"
          style={{ width: '100%', padding: '8px 10px', border: '1px solid #d1d5db', borderRadius: 6 }}
          disabled={submitting}
        />
        <div style={{ color: '#6b7280', fontSize: 12, marginTop: 4 }}>
          Applies only in futures mode. Higher leverage magnifies both gains and losses. Strategy stop distances are not auto-scaled.
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
