import React from 'react'

export function BalanceBar({ total, currency }: { total: number | null; currency?: string }) {
  const t = total ?? null
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
      <div style={{ fontSize: 12, color: '#9ca3af' }}>Balance</div>
      <div style={{ fontSize: 18, fontWeight: 600 }}>{t !== null ? `${t.toFixed(2)}${currency ? ' ' + currency : ''}` : '—'}</div>
    </div>
  )
}
