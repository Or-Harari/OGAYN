import React, { useState } from 'react'
import { api } from '@/lib/api'
import { useUI } from '@/stores/ui'

export default function BotControls({ userId, botId }: { userId: number; botId: number }) {
  const [loading, setLoading] = useState<string | null>(null)
  const notifySuccess = useUI(s => s.notifySuccess)
  const notifyError = useUI(s => s.notifyError)

  const call = async (path: string, method: 'post' | 'delete' = 'post') => {
    if (!userId || !botId) return
    setLoading(path)
    try {
      const url = `/users/${userId}/bots/${botId}/proxy/freqtrade${path}`
      if (method === 'post') await api.post(url)
      else await api.delete(url)
      notifySuccess(`Executed ${path.replace('/', '')}`)
    } catch (e: any) {
      notifyError(e?.response?.data?.detail || e?.message || `Failed ${path}`)
    } finally {
      setLoading(null)
    }
  }

  return (
    <div style={{ display: 'inline-flex', gap: 6, flexWrap: 'wrap' }}>
      <button
        onClick={() => call('/start')}
        disabled={!!loading}
        style={{ padding: '6px 10px', borderRadius: 6, border: '1px solid #16a34a', background: loading === '/start' ? '#dcfce7' : '#16a34a', color: '#fff' }}
      >
        {loading === '/start' ? 'Starting…' : 'Start'}
      </button>
      <button
        onClick={() => call('/pause')}
        disabled={!!loading}
        style={{ padding: '6px 10px', borderRadius: 6, border: '1px solid #f59e0b', background: loading === '/pause' ? '#fef3c7' : '#f59e0b', color: '#111827' }}
      >
        {loading === '/pause' ? 'Pausing…' : 'Pause'}
      </button>
      <button
        onClick={() => call('/stop')}
        disabled={!!loading}
        style={{ padding: '6px 10px', borderRadius: 6, border: '1px solid #ef4444', background: loading === '/stop' ? '#fee2e2' : '#ef4444', color: '#fff' }}
      >
        {loading === '/stop' ? 'Stopping…' : 'Stop'}
      </button>
      <button
        onClick={() => call('/stopbuy')}
        disabled={!!loading}
        style={{ padding: '6px 10px', borderRadius: 6, border: '1px solid #6b7280', background: loading === '/stopbuy' ? '#f3f4f6' : '#fff', color: '#374151' }}
      >
        {loading === '/stopbuy' ? 'Stopping buy…' : 'Stop Buy'}
      </button>
    </div>
  )
}
