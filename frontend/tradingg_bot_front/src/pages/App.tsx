import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { useEffect } from 'react'
import { useAuth } from '@/stores/auth'
import { useData } from '@/stores/data'
import { LoginForm } from '@/components/LoginForm'
import { Navigation } from '@/components/Navigation'
import { Overview } from '@/pages/Overview'
import { Bots } from '@/pages/Bots'
import Toaster from '@/components/Toaster'
import { BacktestConfig } from './BacktestConfig'
import { Settings } from './Settings'

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
      <Navigation />
      <div className="main-wrap">
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/bots" element={<Bots />} />
          <Route path="/backtest" element={<BacktestConfig />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/login" element={<LoginForm />} />
        </Routes>
      </div>
    </BrowserRouter>
  )
}
