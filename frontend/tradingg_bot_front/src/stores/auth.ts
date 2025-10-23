import { create } from 'zustand'
import { api, setAuthToken } from '@/lib/api'

interface AuthState {
  token: string | null
  userId: number | null
  setToken: (t: string | null) => void
  login: (email: string, password: string) => Promise<void>
  logout: () => void
}

export const useAuth = create<AuthState>((set) => ({
  token: localStorage.getItem('auth_token'),
  userId: ((): number | null => {
    const t = localStorage.getItem('auth_token')
    if (!t) return null
    try {
      const [, payload] = t.split('.')
      const json = JSON.parse(atob(payload.replace(/-/g, '+').replace(/_/g, '/')))
      const sub = json?.sub
      return sub ? Number(sub) : null
    } catch { return null }
  })(),
  setToken: (t: string | null) => set(() => ({ token: t })),
  async login(email: string, password: string) {
    const body = new URLSearchParams()
    body.set('username', email)
    body.set('password', password)
    const res = await api.post('/auth/login', body, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    })
    const token = res.data?.access_token as string
    setAuthToken(token)
    let userId: number | null = null
    try {
      const [, payload] = token.split('.')
      const json = JSON.parse(atob(payload.replace(/-/g, '+').replace(/_/g, '/')))
      const sub = json?.sub
      userId = sub ? Number(sub) : null
    } catch {}
    set(() => ({ token, userId }))
    // Decode or fetch user; here we skip and let user select later or store separately
  },
  logout() {
    setAuthToken(null)
    set(() => ({ token: null, userId: null }))
  },
}))
