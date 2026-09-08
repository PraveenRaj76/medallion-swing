import { useState } from 'react'
import { NavLink } from 'react-router-dom'
import { MedallionLogo } from './MedallionLogo'
import { UserProfileMenu } from './UserProfileMenu'
import { AboutModal } from './AboutModal'

export function Nav() {
  const linkClass = ({ isActive }: { isActive: boolean }) => (isActive ? 'active' : '')
  const [aboutOpen, setAboutOpen] = useState(false)

  return (
    <nav>
      <button className="brand" onClick={() => setAboutOpen(true)} aria-label="About Medallion Swing">
        <MedallionLogo size={34} variant="icon" />
        <span>MEDALLION SWING</span>
      </button>
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
      <UserProfileMenu />
      {aboutOpen && <AboutModal onClose={() => setAboutOpen(false)} />}
    </nav>
  )
}
