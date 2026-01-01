import { create } from 'zustand'
import { api, setAuthToken } from '@/lib/api'
import { decodeJwtPayload } from '@/lib/jwt'

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
    const payload = decodeJwtPayload(t)
    const sub = payload?.sub
    return sub ? Number(sub) : null
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
    const payload = decodeJwtPayload(token)
    const sub = payload?.sub
    userId = sub ? Number(sub) : null
    set(() => ({ token, userId }))
    // Decode or fetch user; here we skip and let user select later or store separately
  },
  logout() {
    setAuthToken(null)
    set(() => ({ token: null, userId: null }))
  },
}))
