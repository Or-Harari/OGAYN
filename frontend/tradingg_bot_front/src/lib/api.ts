import axios from 'axios'

export const API_BASE = ((): string => {
  // Simple runtime base selection. Adjust for emulator/device if needed.
  const env = (import.meta as any).env
  return env?.VITE_API_BASE || 'http://127.0.0.1:8000'
})()

export const api = axios.create({
  baseURL: API_BASE,
})

export function setAuthToken(token: string | null) {
  if (token) {
    api.defaults.headers.common['Authorization'] = `Bearer ${token}`
    localStorage.setItem('auth_token', token)
  } else {
    delete api.defaults.headers.common['Authorization']
    localStorage.removeItem('auth_token')
  }
}

// restore token on load
const existing = localStorage.getItem('auth_token')
if (existing) setAuthToken(existing)

// Global response interceptor: on 401/403, clear token and redirect to login
api.interceptors.response.use(
  (resp) => resp,
  (error) => {
    const status = error?.response?.status
    // Only treat 401 (unauthenticated) as a reason to log out and redirect.
    if (status === 401) {
      try {
        setAuthToken(null)
      } catch {}
      try {
        // Preserve current location in query for optional return-after-login
        const loc = typeof window !== 'undefined' ? window.location.pathname + window.location.search : ''
        const loginUrl = '/login' + (loc && loc !== '/login' ? `?next=${encodeURIComponent(loc)}` : '')
        if (typeof window !== 'undefined') window.location.assign(loginUrl)
      } catch {}
    }
    // 403 (forbidden) should not force logout; callers can handle per-view.
    return Promise.reject(error)
  }
)
