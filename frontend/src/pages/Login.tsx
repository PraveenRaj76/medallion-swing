import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiError, login, register } from '../api/client'
import { useAuth } from '../context/AuthContext'
import { MedallionLogo } from '../components/MedallionLogo'

export function Login() {
  const [mode, setMode] = useState<'signin' | 'signup'>('signin')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const { signIn } = useAuth()
  const navigate = useNavigate()

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)

    if (mode === 'signup' && password !== confirm) {
      setError('Passwords do not match.')
      return
    }

    setBusy(true)
    try {
      const result = mode === 'signin' ? await login(username, password) : await register(username, password)
      signIn(result.user_id, username)
      navigate('/screener')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not reach the API — is the backend running?')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="auth-shell starfield">
      <div className="auth-card">
        <div className="auth-hero">
          <MedallionLogo />
          <p className="tagline">NSE + US quantamental screener &amp; forward-test engine</p>
        </div>

        <div className="auth-panel">
          <div className="auth-toggle">
            <button className={mode === 'signin' ? 'active' : ''} onClick={() => setMode('signin')} type="button">
              Sign In
            </button>
            <button className={mode === 'signup' ? 'active' : ''} onClick={() => setMode('signup')} type="button">
              Create Account
            </button>
          </div>

          {error && <div className="error-banner">{error}</div>}

          <form onSubmit={handleSubmit}>
            <div className="form-field">
              <label htmlFor="username">Username</label>
              <input
                id="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                required
              />
            </div>
            <div className="form-field">
              <label htmlFor="password">Password</label>
              <input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete={mode === 'signin' ? 'current-password' : 'new-password'}
                required
              />
            </div>
            {mode === 'signup' && (
              <div className="form-field">
                <label htmlFor="confirm">Confirm Password</label>
                <input
                  id="confirm"
                  type="password"
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                  autoComplete="new-password"
                  required
                />
              </div>
            )}
            <button className="btn btn--full" type="submit" disabled={busy}>
              {busy ? 'Please wait…' : mode === 'signin' ? 'Sign In' : 'Create Account'}
            </button>
          </form>

          <p className="auth-quote">
            “We do data. We don't have opinions.” <cite>— Jim Simons</cite>
          </p>
        </div>
      </div>
    </div>
  )
}
