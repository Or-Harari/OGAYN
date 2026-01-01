import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { useEffect } from 'react'
import { useAuth } from '@/stores/auth'
import { useData } from '@/stores/data'
import { LoginForm } from '@/components/LoginForm'
import { Navigation } from '@/components/Navigation'
import { Dashboard } from '@/pages/Dashboard'
import { Bots } from '@/pages/Bots'
import Toaster from '@/components/Toaster'
import { BacktestConfig } from './BacktestConfig'
import { Settings } from './Settings'
import { RequireAuth } from '@/components/RequireAuth'

export default function App() {
  const token = useAuth((s) => s.token)
  const userId = useAuth((s) => s.userId)
  const loadAll = useData((s) => s.loadAll)

  useEffect(() => {
    if (token && userId) {
      loadAll(userId)
    }
  }, [token, userId, loadAll])
  return (
    <BrowserRouter>
      <Toaster />
      {token ? <Navigation /> : null}
      <div className="main-wrap">
        <Routes>
          <Route path="/" element={<RequireAuth><Dashboard /></RequireAuth>} />
          <Route path="/bots" element={<RequireAuth><Bots /></RequireAuth>} />
          <Route path="/backtest" element={<RequireAuth><BacktestConfig /></RequireAuth>} />
          <Route path="/settings" element={<RequireAuth><Settings /></RequireAuth>} />
          <Route path="/login" element={<LoginForm />} />
        </Routes>
      </div>
    </BrowserRouter>
  )
}
