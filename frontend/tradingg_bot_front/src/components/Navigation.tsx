import { NavLink } from 'react-router-dom'
import { useAuth } from '@/stores/auth'
import './navigation.css'

export function Navigation() {
  const token = useAuth(s => s.token)
  const logout = useAuth(s => s.logout)

  return (
    <nav className="nav">
      <div className="nav-logo">FT Bot</div>
      <ul className="nav-list">
        <li><NavLink to="/" end className={({isActive}) => isActive ? 'active' : ''}>Overview</NavLink></li>
        <li><NavLink to="/bots" className={({isActive}) => isActive ? 'active' : ''}>Bots</NavLink></li>
      </ul>
      <div className="nav-footer">
        {token ? (
          <button className="button secondary" onClick={logout}>Logout</button>
        ) : (
          <NavLink to="/login" className={({isActive}) => isActive ? 'active' : ''}>Login</NavLink>
        )}
      </div>
    </nav>
  )
}
