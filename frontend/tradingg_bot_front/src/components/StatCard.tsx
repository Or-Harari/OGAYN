import React from 'react'

export function StatCard({ title, value, subtitle, accent }: { title: string; value: React.ReactNode; subtitle?: string; accent?: 'green' | 'red' | 'blue' | 'amber' }) {
  const colors: Record<string, string> = {
    green: '#10b981',
    red: '#ef4444',
    blue: '#3b82f6',
    amber: '#f59e0b',
  }
  const border = accent ? colors[accent] : '#d1d5db'
  return (
    <div style={{ border: `1px solid ${border}`, borderRadius: 12, padding: 14, background: '#0b0d12', color: '#e5e7eb', boxShadow: '0 6px 18px rgba(0,0,0,0.12)' }}>
      <div style={{ fontSize: 12, color: '#9ca3af', marginBottom: 8 }}>{title}</div>
      <div style={{ fontSize: 24, fontWeight: 600 }}>{value}</div>
      {subtitle ? <div style={{ fontSize: 12, color: '#9ca3af', marginTop: 6 }}>{subtitle}</div> : null}
    </div>
  )
}
