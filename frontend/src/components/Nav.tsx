import { NavLink } from 'react-router-dom'
import { MedallionLogo } from './MedallionLogo'
import { UserProfileMenu } from './UserProfileMenu'

export function Nav({ onOpenCmdk }: { onOpenCmdk: () => void }) {
  const linkClass = ({ isActive }: { isActive: boolean }) => (isActive ? 'active' : '')

  return (
    <nav>
      <div className="brand">
        <MedallionLogo size={28} variant="icon" />
        <span>MEDALLION SWING</span>
      </div>
      <div className="navlinks" role="tablist" aria-label="Pages">
        <NavLink to="/screener/in" className={linkClass}>
          India Screener
        </NavLink>
        <NavLink to="/screener/us" className={linkClass}>
          US Screener
        </NavLink>
        <NavLink to="/profile" className={linkClass}>
          Search Profile
        </NavLink>
        <NavLink to="/forward-test" className={linkClass}>
          Forward-Test
        </NavLink>
      </div>
      <div className="navspacer" />
      <button className="cmdk-trigger" onClick={onOpenCmdk}>
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="11" cy="11" r="7" />
          <path d="m21 21-4.3-4.3" />
        </svg>
        <span className="cmdk-label">Jump to&hellip;</span> <span className="kbd">Ctrl K</span>
      </button>
      <UserProfileMenu />
    </nav>
  )
}
