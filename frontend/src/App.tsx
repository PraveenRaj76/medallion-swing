import { Navigate, Route, Routes } from 'react-router-dom'
import './App.css'
import { Nav } from './components/Nav'
import { useAuth } from './context/AuthContext'
import { Login } from './pages/Login'
import { Screener } from './pages/Screener'
import { SearchProfile } from './pages/SearchProfile'
import { Sectors } from './pages/Sectors'
import { ForwardTest } from './pages/ForwardTest'

function Protected({ children }: { children: React.ReactNode }) {
  const { userId } = useAuth()
  if (!userId) return <Navigate to="/login" replace />
  return (
    <div className="app-shell">
      <Nav />
      {children}
    </div>
  )
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        path="/screener"
        element={
          <Protected>
            <Screener />
          </Protected>
        }
      />
      <Route
        path="/search"
        element={
          <Protected>
            <SearchProfile />
          </Protected>
        }
      />
      <Route
        path="/sectors"
        element={
          <Protected>
            <Sectors />
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
      <Route path="*" element={<Navigate to="/screener" replace />} />
    </Routes>
  )
}
