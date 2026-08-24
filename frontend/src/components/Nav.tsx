import { NavLink } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

export function Nav() {
  const { username, signOut } = useAuth()

  const linkClass = ({ isActive }: { isActive: boolean }) =>
    'navbar__link' + (isActive ? ' navbar__link--active' : '')

  return (
    <nav className="navbar">
      <div className="navbar__brand">
        <span>🪐</span> Medallion Swing
      </div>
      <div className="navbar__links">
        <NavLink to="/screener" className={linkClass}>
          Screener
        </NavLink>
        <NavLink to="/search" className={linkClass}>
          Search Profile
        </NavLink>
        <NavLink to="/sectors" className={linkClass}>
          Sectors
        </NavLink>
        <NavLink to="/forward-test" className={linkClass}>
          Forward-Test
        </NavLink>
      </div>
      <div className="navbar__meta">
        <span>{username}</span>
        <button className="navbar__logout" onClick={signOut}>
          Log Out
        </button>
      </div>
    </nav>
  )
}
