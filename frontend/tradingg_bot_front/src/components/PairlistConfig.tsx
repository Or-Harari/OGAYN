import React, { useState, useEffect } from 'react'
import { api } from '@/lib/api'

interface PairlistHandler {
  method: string
  [key: string]: any
}

interface PairlistConfigProps {
  pairBlacklist: string
  pairlists: PairlistHandler[]
  onPairBlacklistChange: (value: string) => void
  onPairlistsChange: (value: PairlistHandler[]) => void
  disabled?: boolean
  userId?: number  // Optional userId for loading scanners
}

const PairlistConfig: React.FC<PairlistConfigProps> = ({
  pairBlacklist,
  pairlists,
  onPairBlacklistChange,
  onPairlistsChange,
  disabled = false,
  userId
}) => {
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null)
  const [scanners, setScanners] = useState<Array<{ id: number; name: string }>>([])
  const [scannersLoading, setScannersLoading] = useState(false)

  // Load scanners when component mounts if userId is provided
  useEffect(() => {
    if (userId) {
      setScannersLoading(true)
      api.get(`/scanners/users/${userId}/scanners`)
        .then(res => {
          const list = Array.isArray(res.data) ? res.data : []
          setScanners(list.map((s: any) => ({ id: s.id, name: s.name })))
        })
        .catch(err => {
          console.warn('Failed to load scanners:', err)
          setScanners([])
        })
        .finally(() => setScannersLoading(false))
    }
  }, [userId])

  const addPairlist = () => {
    onPairlistsChange([...pairlists, { method: 'StaticPairList' }])
    setExpandedIdx(pairlists.length)
  }

  const removePairlist = (idx: number) => {
    onPairlistsChange(pairlists.filter((_, i) => i !== idx))
    if (expandedIdx === idx) setExpandedIdx(null)
  }

  const updatePairlist = (idx: number, updates: Partial<PairlistHandler>) => {
    const updated = [...pairlists]
    updated[idx] = { ...updated[idx], ...updates }
    onPairlistsChange(updated)
  }

  const movePairlist = (idx: number, direction: 'up' | 'down') => {
    const newIdx = direction === 'up' ? idx - 1 : idx + 1
    if (newIdx < 0 || newIdx >= pairlists.length) return
    const updated = [...pairlists]
    ;[updated[idx], updated[newIdx]] = [updated[newIdx], updated[idx]]
    onPairlistsChange(updated)
    setExpandedIdx(newIdx)
  }

  const renderPairlistForm = (handler: PairlistHandler, idx: number) => {
    const method = handler.method

    return (
      <div style={{ marginTop: 8, paddingLeft: 12, borderLeft: '3px solid #3b82f6' }}>
        {/* RemotePairList */}
        {method === 'RemotePairList' && (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
            <div style={{ gridColumn: '1 / span 2' }}>
              <label style={{ display: 'block', fontSize: 11, color: '#6b7280' }}>
                Scanner Source *
              </label>
              {scannersLoading ? (
                <div style={{ fontSize: 11, color: '#6b7280', padding: 4 }}>Loading scanners...</div>
              ) : scanners.length > 0 ? (
                <select
                  value={handler.scanner_id || ''}
                  onChange={e => {
                    const scannerId = e.target.value ? parseInt(e.target.value) : null
                    const selectedScanner = scanners.find(s => s.id === scannerId)
                    if (scannerId && selectedScanner) {
                      // Construct URL from scanner: http://127.0.0.1:8000/api/scanners/users/{userId}/scanners/{scannerId}/pairlist
                      const url = `${window.location.origin}/api/scanners/users/${userId}/scanners/${scannerId}/pairlist`
                      updatePairlist(idx, { 
                        scanner_id: scannerId, 
                        scanner_name: selectedScanner.name,
                        pairlist_url: url 
                      })
                    } else {
                      updatePairlist(idx, { 
                        scanner_id: null, 
                        scanner_name: null,
                        pairlist_url: '' 
                      })
                    }
                  }}
                  disabled={disabled}
                  style={{ width: '100%', padding: 4, fontSize: 12, border: '1px solid #e5e7eb', borderRadius: 4 }}
                >
                  <option value="">-- Select Scanner --</option>
                  {scanners.map(s => (
                    <option key={s.id} value={s.id}>{s.name}</option>
                  ))}
                </select>
              ) : (
                <div style={{ fontSize: 11, color: '#ef4444', padding: 4 }}>
                  No scanners available. Please create a scanner first.
                </div>
              )}
              {handler.scanner_id && handler.scanner_name && (
                <div style={{ fontSize: 10, color: '#6b7280', marginTop: 4 }}>
                  Selected: {handler.scanner_name}
                </div>
              )}
            </div>
            <div style={{ gridColumn: '1 / span 2' }}>
              <label style={{ display: 'block', fontSize: 11, color: '#6b7280' }}>
                Generated URL (read-only)
              </label>
              <input
                value={handler.pairlist_url || ''}
                disabled
                placeholder="URL will be generated from scanner selection"
                style={{ 
                  width: '100%', 
                  padding: 4, 
                  fontSize: 11, 
                  border: '1px solid #e5e7eb', 
                  borderRadius: 4,
                  backgroundColor: '#f9fafb',
                  color: '#6b7280',
                  fontFamily: 'monospace'
                }}
              />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: 11, color: '#6b7280' }}>Mode</label>
              <select
                value={handler.mode || 'whitelist'}
                onChange={e => updatePairlist(idx, { mode: e.target.value })}
                disabled={disabled}
                style={{ width: '100%', padding: 4, fontSize: 12, border: '1px solid #e5e7eb', borderRadius: 4 }}
              >
                <option value="whitelist">Whitelist</option>
                <option value="blacklist">Blacklist</option>
              </select>
            </div>
            <div>
              <label style={{ display: 'block', fontSize: 11, color: '#6b7280' }}>Processing Mode</label>
              <select
                value={handler.processing_mode || 'filter'}
                onChange={e => updatePairlist(idx, { processing_mode: e.target.value })}
                disabled={disabled}
                style={{ width: '100%', padding: 4, fontSize: 12, border: '1px solid #e5e7eb', borderRadius: 4 }}
              >
                <option value="filter">Filter</option>
                <option value="append">Append</option>
              </select>
            </div>
            <div>
              <label style={{ display: 'block', fontSize: 11, color: '#6b7280' }}>Number of Assets</label>
              <input
                type="number"
                value={handler.number_assets || ''}
                onChange={e => updatePairlist(idx, { number_assets: parseInt(e.target.value) || undefined })}
                disabled={disabled}
                placeholder="50"
                style={{ width: '100%', padding: 4, fontSize: 12, border: '1px solid #e5e7eb', borderRadius: 4 }}
              />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: 11, color: '#6b7280' }}>Refresh Period (s)</label>
              <input
                type="number"
                value={handler.refresh_period || 1800}
                onChange={e => updatePairlist(idx, { refresh_period: parseInt(e.target.value) || 1800 })}
                disabled={disabled}
                style={{ width: '100%', padding: 4, fontSize: 12, border: '1px solid #e5e7eb', borderRadius: 4 }}
              />
            </div>
          </div>
        )}

        {/* StaticPairList */}
        {method === 'StaticPairList' && (
          <div style={{ fontSize: 11, color: '#6b7280', fontStyle: 'italic' }}>
            Uses pair_whitelist from config. No additional options needed.
          </div>
        )}

        {/* VolumePairList */}
        {method === 'VolumePairList' && (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
            <div>
              <label style={{ display: 'block', fontSize: 11, color: '#6b7280' }}>Number of Assets *</label>
              <input
                type="number"
                value={handler.number_assets || 20}
                onChange={e => updatePairlist(idx, { number_assets: parseInt(e.target.value) || 20 })}
                disabled={disabled}
                style={{ width: '100%', padding: 4, fontSize: 12, border: '1px solid #e5e7eb', borderRadius: 4 }}
              />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: 11, color: '#6b7280' }}>Min Value</label>
              <input
                type="number"
                value={handler.min_value !== undefined ? handler.min_value : 0}
                onChange={e => updatePairlist(idx, { min_value: parseFloat(e.target.value) || 0 })}
                disabled={disabled}
                style={{ width: '100%', padding: 4, fontSize: 12, border: '1px solid #e5e7eb', borderRadius: 4 }}
              />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: 11, color: '#6b7280' }}>Max Value</label>
              <input
                type="number"
                value={handler.max_value || ''}
                onChange={e => updatePairlist(idx, { max_value: e.target.value ? parseFloat(e.target.value) : undefined })}
                disabled={disabled}
                placeholder="Optional"
                style={{ width: '100%', padding: 4, fontSize: 12, border: '1px solid #e5e7eb', borderRadius: 4 }}
              />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: 11, color: '#6b7280' }}>Refresh Period (s)</label>
              <input
                type="number"
                value={handler.refresh_period || 1800}
                onChange={e => updatePairlist(idx, { refresh_period: parseInt(e.target.value) || 1800 })}
                disabled={disabled}
                style={{ width: '100%', padding: 4, fontSize: 12, border: '1px solid #e5e7eb', borderRadius: 4 }}
              />
            </div>
          </div>
        )}

        {/* PercentChangePairList */}
        {method === 'PercentChangePairList' && (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
            <div>
              <label style={{ display: 'block', fontSize: 11, color: '#6b7280' }}>Number of Assets *</label>
              <input
                type="number"
                value={handler.number_assets || 15}
                onChange={e => updatePairlist(idx, { number_assets: parseInt(e.target.value) || 15 })}
                disabled={disabled}
                style={{ width: '100%', padding: 4, fontSize: 12, border: '1px solid #e5e7eb', borderRadius: 4 }}
              />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: 11, color: '#6b7280' }}>Sort Direction</label>
              <select
                value={handler.sort_direction || 'desc'}
                onChange={e => updatePairlist(idx, { sort_direction: e.target.value })}
                disabled={disabled}
                style={{ width: '100%', padding: 4, fontSize: 12, border: '1px solid #e5e7eb', borderRadius: 4 }}
              >
                <option value="desc">Descending</option>
                <option value="asc">Ascending</option>
              </select>
            </div>
            <div>
              <label style={{ display: 'block', fontSize: 11, color: '#6b7280' }}>Min Value (%)</label>
              <input
                type="number"
                value={handler.min_value !== undefined ? handler.min_value : ''}
                onChange={e => updatePairlist(idx, { min_value: e.target.value ? parseFloat(e.target.value) : undefined })}
                disabled={disabled}
                placeholder="Optional"
                style={{ width: '100%', padding: 4, fontSize: 12, border: '1px solid #e5e7eb', borderRadius: 4 }}
              />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: 11, color: '#6b7280' }}>Max Value (%)</label>
              <input
                type="number"
                value={handler.max_value !== undefined ? handler.max_value : ''}
                onChange={e => updatePairlist(idx, { max_value: e.target.value ? parseFloat(e.target.value) : undefined })}
                disabled={disabled}
                placeholder="Optional"
                style={{ width: '100%', padding: 4, fontSize: 12, border: '1px solid #e5e7eb', borderRadius: 4 }}
              />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: 11, color: '#6b7280' }}>Refresh Period (s)</label>
              <input
                type="number"
                value={handler.refresh_period || 1800}
                onChange={e => updatePairlist(idx, { refresh_period: parseInt(e.target.value) || 1800 })}
                disabled={disabled}
                style={{ width: '100%', padding: 4, fontSize: 12, border: '1px solid #e5e7eb', borderRadius: 4 }}
              />
            </div>
          </div>
        )}

        {/* MarketCapPairList */}
        {method === 'MarketCapPairList' && (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
            <div>
              <label style={{ display: 'block', fontSize: 11, color: '#6b7280' }}>Number of Assets *</label>
              <input
                type="number"
                value={handler.number_assets || 20}
                onChange={e => updatePairlist(idx, { number_assets: parseInt(e.target.value) || 20 })}
                disabled={disabled}
                style={{ width: '100%', padding: 4, fontSize: 12, border: '1px solid #e5e7eb', borderRadius: 4 }}
              />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: 11, color: '#6b7280' }}>Max Rank</label>
              <input
                type="number"
                value={handler.max_rank || 50}
                onChange={e => updatePairlist(idx, { max_rank: parseInt(e.target.value) || 50 })}
                disabled={disabled}
                style={{ width: '100%', padding: 4, fontSize: 12, border: '1px solid #e5e7eb', borderRadius: 4 }}
              />
            </div>
            <div style={{ gridColumn: '1 / span 2' }}>
              <label style={{ display: 'block', fontSize: 11, color: '#6b7280' }}>Categories (comma-separated)</label>
              <input
                value={Array.isArray(handler.categories) ? handler.categories.join(', ') : ''}
                onChange={e => {
                  const cats = e.target.value.split(',').map(s => s.trim()).filter(s => s.length > 0)
                  updatePairlist(idx, { categories: cats.length > 0 ? cats : [] })
                }}
                disabled={disabled}
                placeholder="e.g., layer-1, defi"
                style={{ width: '100%', padding: 4, fontSize: 12, border: '1px solid #e5e7eb', borderRadius: 4 }}
              />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: 11, color: '#6b7280' }}>Refresh Period (s)</label>
              <input
                type="number"
                value={handler.refresh_period || 86400}
                onChange={e => updatePairlist(idx, { refresh_period: parseInt(e.target.value) || 86400 })}
                disabled={disabled}
                style={{ width: '100%', padding: 4, fontSize: 12, border: '1px solid #e5e7eb', borderRadius: 4 }}
              />
            </div>
          </div>
        )}
      </div>
    )
  }

  return (
    <div style={{ border: '1px solid #e5e7eb', borderRadius: 6, padding: 10 }}>
      <div style={{ fontWeight: 600, marginBottom: 8, fontSize: 13 }}>Pairlist Configuration</div>
      
      <div style={{ marginBottom: 12 }}>
        <label style={{ display: 'block', fontSize: 12, marginBottom: 4 }}>Pair Blacklist (comma-separated)</label>
        <textarea
          value={pairBlacklist}
          onChange={e => onPairBlacklistChange(e.target.value)}
          disabled={disabled}
          placeholder="BNB/USDT, BUSD/USDT"
          style={{ width: '100%', minHeight: 50, padding: 6, fontSize: 12, border: '1px solid #e5e7eb', borderRadius: 4 }}
        />
      </div>

      <div style={{ fontWeight: 500, fontSize: 12, marginBottom: 6 }}>Pairlist Handlers (executed in order)</div>
      
      {pairlists.length === 0 && (
        <div style={{ fontSize: 11, color: '#6b7280', fontStyle: 'italic', marginBottom: 8 }}>
          No pairlist handlers configured. Static pair_whitelist will be used.
        </div>
      )}

      {pairlists.map((handler, idx) => (
        <div key={idx} style={{ border: '1px solid #d1d5db', borderRadius: 4, padding: 8, marginBottom: 8 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
            <div style={{ flex: 1, fontWeight: 500, fontSize: 12 }}>
              {idx + 1}. {handler.method}
            </div>
            <button
              onClick={() => movePairlist(idx, 'up')}
              disabled={disabled || idx === 0}
              title="Move up"
              style={{
                padding: '2px 6px',
                fontSize: 11,
                border: '1px solid #d1d5db',
                borderRadius: 3,
                background: '#fff',
                cursor: disabled || idx === 0 ? 'not-allowed' : 'pointer',
                opacity: disabled || idx === 0 ? 0.5 : 1
              }}
            >
              ↑
            </button>
            <button
              onClick={() => movePairlist(idx, 'down')}
              disabled={disabled || idx === pairlists.length - 1}
              title="Move down"
              style={{
                padding: '2px 6px',
                fontSize: 11,
                border: '1px solid #d1d5db',
                borderRadius: 3,
                background: '#fff',
                cursor: disabled || idx === pairlists.length - 1 ? 'not-allowed' : 'pointer',
                opacity: disabled || idx === pairlists.length - 1 ? 0.5 : 1
              }}
            >
              ↓
            </button>
            <button
              onClick={() => setExpandedIdx(expandedIdx === idx ? null : idx)}
              disabled={disabled}
              style={{
                padding: '2px 8px',
                fontSize: 11,
                border: '1px solid #3b82f6',
                borderRadius: 3,
                background: '#fff',
                color: '#3b82f6',
                cursor: disabled ? 'not-allowed' : 'pointer'
              }}
            >
              {expandedIdx === idx ? 'Collapse' : 'Edit'}
            </button>
            <button
              onClick={() => removePairlist(idx)}
              disabled={disabled}
              style={{
                padding: '2px 8px',
                fontSize: 11,
                border: '1px solid #ef4444',
                borderRadius: 3,
                background: '#fff',
                color: '#ef4444',
                cursor: disabled ? 'not-allowed' : 'pointer'
              }}
            >
              Remove
            </button>
          </div>

          {/* Method selector */}
          <div style={{ marginBottom: 8 }}>
            <label style={{ display: 'block', fontSize: 11, color: '#6b7280' }}>Handler Type</label>
            <select
              value={handler.method}
              onChange={e => updatePairlist(idx, { method: e.target.value })}
              disabled={disabled}
              style={{ width: '100%', padding: 4, fontSize: 12, border: '1px solid #e5e7eb', borderRadius: 4 }}
            >
              <option value="RemotePairList">RemotePairList</option>
              <option value="StaticPairList">StaticPairList</option>
              <option value="VolumePairList">VolumePairList</option>
              <option value="PercentChangePairList">PercentChangePairList</option>
              <option value="MarketCapPairList">MarketCapPairList</option>
            </select>
          </div>

          {expandedIdx === idx && renderPairlistForm(handler, idx)}
        </div>
      ))}

      <button
        onClick={addPairlist}
        disabled={disabled}
        style={{
          padding: '6px 12px',
          fontSize: 12,
          border: '1px solid #3b82f6',
          borderRadius: 4,
          background: '#fff',
          color: '#3b82f6',
          cursor: disabled ? 'not-allowed' : 'pointer',
          width: '100%'
        }}
      >
        + Add Pairlist Handler
      </button>
    </div>
  )
}

export default PairlistConfig
