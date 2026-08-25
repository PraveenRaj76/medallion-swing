import { useEffect, useState, type ReactNode } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import './App.css'
import { Nav } from './components/Nav'
import { Starfield } from './components/Starfield'
import { CommandPalette } from './components/CommandPalette'
import { useAuth } from './context/AuthContext'
import { Login } from './pages/Login'
import { ScreenerIndia } from './pages/ScreenerIndia'
import { ScreenerUS } from './pages/ScreenerUS'
import { SearchProfile } from './pages/SearchProfile'
import { ForwardTest } from './pages/ForwardTest'

function Protected({ children }: { children: ReactNode }) {
  const { userId } = useAuth()
  const [cmdkOpen, setCmdkOpen] = useState(false)

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setCmdkOpen(true)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  if (!userId) return <Navigate to="/login" replace />
  return (
    <div className="wrap">
      <Nav onOpenCmdk={() => setCmdkOpen(true)} />
      {children}
      <CommandPalette open={cmdkOpen} onClose={() => setCmdkOpen(false)} />
    </div>
  )
}

export default function App() {
  return (
    <>
      <Starfield />
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route
          path="/screener/in"
          element={
            <Protected>
              <ScreenerIndia />
            </Protected>
          }
        />
        <Route
          path="/screener/us"
          element={
            <Protected>
              <ScreenerUS />
            </Protected>
          }
        />
        <Route
          path="/profile"
          element={
            <Protected>
              <SearchProfile />
            </Protected>
          }
        />
        <Route
          path="/forward-test"
          element={
            <Protected>
              <ForwardTest />
            </Protected>
          }
        />
        <Route path="*" element={<Navigate to="/screener/in" replace />} />
      </Routes>
    </>
  )
}
