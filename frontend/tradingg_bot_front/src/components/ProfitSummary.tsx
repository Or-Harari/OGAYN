import React from 'react'

export type ProfitWindow = {
  label: string
  profitAbs: number
  profitRatio: number | null
}

export function ProfitSummary({ items }: { items: ProfitWindow[] }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 12 }}>
      {items.map((it) => (
        <div key={it.label} style={{ border: '1px solid #374151', borderRadius: 12, padding: 12 }}>
          <div style={{ fontSize: 12, color: '#9ca3af' }}>{it.label}</div>
          <div style={{ fontSize: 18, fontWeight: 600 }}>
            {it.profitAbs.toFixed(2)}
            {it.profitRatio !== null ? <span style={{ marginLeft: 8, color: it.profitRatio >= 0 ? '#10b981' : '#ef4444' }}>({(it.profitRatio * 100).toFixed(2)}%)</span> : null}
          </div>
        </div>
      ))}
    </div>
  )
}
