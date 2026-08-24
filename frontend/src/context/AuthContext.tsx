import { createContext, useContext, useState, type ReactNode } from 'react'

interface AuthState {
  userId: number | null
  username: string | null
  signIn: (userId: number, username: string) => void
  signOut: () => void
}

const AuthContext = createContext<AuthState | undefined>(undefined)

const STORAGE_KEY = 'medallion.auth'

function loadStored(): { userId: number; username: string } | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const stored = loadStored()
  const [userId, setUserId] = useState<number | null>(stored?.userId ?? null)
  const [username, setUsername] = useState<string | null>(stored?.username ?? null)

  function signIn(id: number, name: string) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ userId: id, username: name }))
    setUserId(id)
    setUsername(name)
  }

  function signOut() {
    localStorage.removeItem(STORAGE_KEY)
    setUserId(null)
    setUsername(null)
  }

  return (
    <AuthContext.Provider value={{ userId, username, signIn, signOut }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
