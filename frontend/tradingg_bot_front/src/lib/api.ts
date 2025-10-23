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
