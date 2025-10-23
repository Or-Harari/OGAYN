import React from 'react'
import { useUI } from '@/stores/ui'

const typeStyles: Record<string, { bg: string; border: string; color: string }> = {
  success: { bg: '#ecfdf5', border: '#10b981', color: '#065f46' },
  error: { bg: '#fef2f2', border: '#ef4444', color: '#7f1d1d' },
  info: { bg: '#eff6ff', border: '#3b82f6', color: '#1e3a8a' },
}

export function Toaster() {
  const toasts = useUI((s) => s.toasts)
  const remove = useUI((s) => s.removeToast)

  return (
    <div style={{ position: 'fixed', right: 12, top: 12, zIndex: 60, display: 'flex', flexDirection: 'column', gap: 8 }}>
      {toasts.map((t) => {
        const s = typeStyles[t.type] || typeStyles.info
        return (
          <div
            key={t.id}
            style={{
              background: s.bg,
              border: `1px solid ${s.border}`,
              color: s.color,
              padding: '10px 12px',
              borderRadius: 8,
              minWidth: 240,
              boxShadow: '0 6px 18px rgba(0,0,0,0.08)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: 10,
            }}
          >
            <div style={{ fontSize: 14, lineHeight: 1.3 }}>{t.message}</div>
            <button
              onClick={() => remove(t.id)}
              style={{ border: 'none', background: 'transparent', color: s.color, cursor: 'pointer', fontSize: 18, lineHeight: 1 }}
              aria-label="Dismiss"
            >
              ×
            </button>
          </div>
        )
      })}
    </div>
  )
}

export default Toaster
