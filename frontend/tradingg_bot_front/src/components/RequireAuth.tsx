import { ReactNode, useEffect, useMemo } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '@/stores/auth'
import { isJwtExpired } from '@/lib/jwt'

export function RequireAuth({ children }: { children: ReactNode }) {
  const token = useAuth((s) => s.token)
  const logout = useAuth((s) => s.logout)
  const location = useLocation()

  const valid = useMemo(() => !!token && !isJwtExpired(token), [token])

  useEffect(() => {
    if (!valid && token) {
      // Token invalid/expired: logout to clear state
      logout()
    }
  }, [valid, token, logout])

  if (!valid) {
    const to = '/login' + (location.pathname !== '/login' ? `?next=${encodeURIComponent(location.pathname + location.search)}` : '')
    return <Navigate to={to} replace />
  }
  return <>{children}</>
}
