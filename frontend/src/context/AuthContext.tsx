import { createContext, useContext, useState, type ReactNode } from 'react'

export interface ProfileFields {
  firstName: string
  lastName: string
  username: string
  email: string
}

interface AuthState {
  userId: number | null
  username: string | null
  profile: ProfileFields | null
  signIn: (userId: number, username: string) => void
  signOut: () => void
  /**
   * Local-only profile edit — there is no PATCH /api/profile endpoint yet,
   * so this simulates a successful save (persisted to localStorage so it
   * survives a refresh) rather than actually writing to the users table.
   * Real backend persistence is a separate, later piece of work.
   */
  updateProfile: (fields: ProfileFields) => void
}

const AuthContext = createContext<AuthState | undefined>(undefined)

const STORAGE_KEY = 'medallion.auth'
const PROFILE_KEY = 'medallion.profile'

function loadStored(): { userId: number; username: string } | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

function loadProfile(username: string | null): ProfileFields | null {
  if (!username) return null
  try {
    const raw = localStorage.getItem(PROFILE_KEY)
    const all = raw ? JSON.parse(raw) : {}
    return all[username] ?? { firstName: username, lastName: '', username, email: '' }
  } catch {
    return { firstName: username, lastName: '', username, email: '' }
  }
}

function saveProfile(username: string, fields: ProfileFields) {
  try {
    const raw = localStorage.getItem(PROFILE_KEY)
    const all = raw ? JSON.parse(raw) : {}
    all[username] = fields
    localStorage.setItem(PROFILE_KEY, JSON.stringify(all))
  } catch {
    // localStorage unavailable — profile edits just won't persist across reloads
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const stored = loadStored()
  const [userId, setUserId] = useState<number | null>(stored?.userId ?? null)
  const [username, setUsername] = useState<string | null>(stored?.username ?? null)
  const [profile, setProfile] = useState<ProfileFields | null>(loadProfile(stored?.username ?? null))

  function signIn(id: number, name: string) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ userId: id, username: name }))
    setUserId(id)
    setUsername(name)
    setProfile(loadProfile(name))
  }

  function signOut() {
    localStorage.removeItem(STORAGE_KEY)
    setUserId(null)
    setUsername(null)
    setProfile(null)
  }

  function updateProfile(fields: ProfileFields) {
    if (!username) return
    saveProfile(username, fields)
    setProfile(fields)
  }

  return (
    <AuthContext.Provider value={{ userId, username, profile, signIn, signOut, updateProfile }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
