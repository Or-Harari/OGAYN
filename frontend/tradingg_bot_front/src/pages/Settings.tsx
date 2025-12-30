import { useEffect, useState } from 'react'
import { api } from '@/lib/api'
import Toaster from '@/components/Toaster'
import { useUI } from '@/stores/ui'

interface ExchangeView {
  name?: string
  sandbox?: boolean
  has_key?: boolean
  has_secret?: boolean
  has_password?: boolean
}

export function Settings() {
  const notifySuccess = useUI(s => s.notifySuccess)
  const notifyError = useUI(s => s.notifyError)
  const userId = ((): number | null => {
    try {
      const t = localStorage.getItem('auth_token')
      if (!t) return null
      const [, payload] = t.split('.')
      const json = JSON.parse(atob(payload.replace(/-/g, '+').replace(/_/g, '/')))
      return json?.sub ? Number(json.sub) : null
    } catch { return null }
  })()
  const [botsRunning, setBotsRunning] = useState(false)
  const [exchangeView, setExchangeView] = useState<ExchangeView | null>(null)
  const [name, setName] = useState('binance')
  const [sandbox, setSandbox] = useState(false)
  const [key, setKey] = useState('')
  const [secret, setSecret] = useState('')
  const [password, setPassword] = useState('')
  const [savingExchange, setSavingExchange] = useState(false)

  const [curPwd, setCurPwd] = useState('')
  const [newPwd, setNewPwd] = useState('')
  const [confirmPwd, setConfirmPwd] = useState('')
  const [changingPwd, setChangingPwd] = useState(false)

  useEffect(() => {
    (async () => {
      try {
        const res = await api.get('/config/user/exchange/view')
        const v = res.data as ExchangeView
        setExchangeView(v)
        if (v?.name) setName(v.name)
        setSandbox(!!v?.sandbox)
      } catch {}
    })()
  }, [])

  useEffect(() => {
    (async () => {
      if (!userId) return
      try {
        const res = await api.get(`/users/${userId}/bots`)
        const items = res.data as any[]
        const running = Array.isArray(items) && items.some(b => (b?.status || '').toLowerCase() !== 'stopped')
        setBotsRunning(!!running)
      } catch {}
    })()
  }, [userId])

  async function saveExchange() {
    if (botsRunning) {
      notifyError('Bots are running. Stop them to save settings.')
      return
    }
    setSavingExchange(true)
    try {
      const payload: any = { name, sandbox }
      if (key) payload.key = key
      if (secret) payload.secret = secret
      if (password) payload.password = password
      await api.put('/config/user/exchange', payload)
      setKey(''); setSecret(''); setPassword('')
      const vres = await api.get('/config/user/exchange/view')
      setExchangeView(vres.data)
      notifySuccess('Exchange settings saved')
    } catch (e: any) {
      notifyError(e?.response?.data?.detail || 'Failed to save exchange')
    } finally {
      setSavingExchange(false)
    }
  }

  async function changePassword() {
    if (botsRunning) {
      notifyError('Bots are running. Stop them to change password.')
      return
    }
    if (newPwd !== confirmPwd) {
      notifyError('New passwords do not match')
      return
    }
    setChangingPwd(true)
    try {
      await api.post('/auth/change-password', { current_password: curPwd, new_password: newPwd })
      setCurPwd(''); setNewPwd(''); setConfirmPwd('')
      notifySuccess('Password changed successfully')
    } catch (e: any) {
      notifyError(e?.response?.data?.detail || 'Failed to change password')
    } finally {
      setChangingPwd(false)
    }
  }

  return (
    <div className="content">
      <Toaster />
      <h2>Settings</h2>
      {botsRunning && (
        <div className="card" style={{ background: '#fff7ed', borderColor: '#f59e0b' }}>
          <div style={{ color: '#92400e' }}>
            Bots are currently running. Saving is disabled to prevent live changes.
          </div>
        </div>
      )}
      <div className="card">
        <h3>Exchange Credentials</h3>
        <div className="row">
          <label>Exchange Name</label>
          <input value={name} onChange={e => setName(e.target.value)} placeholder="binance | bybit" />
        </div>
        <div className="row">
          <label>Key</label>
          <input value={key} onChange={e => setKey(e.target.value)} placeholder="Enter API key" />
        </div>
        <div className="row">
          <label>Secret</label>
          <input value={secret} onChange={e => setSecret(e.target.value)} placeholder="Enter API secret" />
        </div>
        <div className="row">
          <label>Password/Passphrase (optional)</label>
          <input value={password} onChange={e => setPassword(e.target.value)} placeholder="Optional passphrase" />
        </div>
        <div className="row">
          <label>Sandbox/Testnet</label>
          <input type="checkbox" checked={sandbox} onChange={e => setSandbox(e.target.checked)} />
        </div>
        {exchangeView && (
          <div className="hint">
            Current: {exchangeView.name || 'n/a'} | Sandbox: {exchangeView.sandbox ? 'yes' : 'no'} | 
            Key: {exchangeView.has_key ? 'set' : 'missing'} | Secret: {exchangeView.has_secret ? 'set' : 'missing'}
          </div>
        )}
        <button className="button" onClick={saveExchange} disabled={savingExchange || botsRunning}>
          {savingExchange ? 'Saving...' : 'Save Exchange Settings'}
        </button>
      </div>

      <div className="card" style={{ marginTop: 20 }}>
        <h3>Change Password</h3>
        <div className="row">
          <label>Current Password</label>
          <input type="password" value={curPwd} onChange={e => setCurPwd(e.target.value)} />
        </div>
        <div className="row">
          <label>New Password</label>
          <input type="password" value={newPwd} onChange={e => setNewPwd(e.target.value)} />
        </div>
        <div className="row">
          <label>Confirm New Password</label>
          <input type="password" value={confirmPwd} onChange={e => setConfirmPwd(e.target.value)} />
        </div>
        <button className="button" onClick={changePassword} disabled={changingPwd || botsRunning}>
          {changingPwd ? 'Changing...' : 'Change Password'}
        </button>
      </div>
    </div>
  )
}
