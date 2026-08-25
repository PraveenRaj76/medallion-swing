import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiError, login, register } from '../api/client'
import { useAuth } from '../context/AuthContext'
import logo from '../assets/medallion-logo.png'

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
      navigate('/screener/in')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not reach the API — is the backend running?')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div id="loginScreen">
      <div className="login-card">
        <div className="login-brand">
          <img src={logo} alt="Medallion Swing" />
          <div className="tag">NSE + US quantamental screener &amp; forward-test engine</div>
        </div>

        <div className="login-tabs" role="tablist">
          <button
            className={mode === 'signin' ? 'active' : ''}
            onClick={() => setMode('signin')}
            type="button"
            role="tab"
            aria-selected={mode === 'signin'}
          >
            Sign In
          </button>
          <button
            className={mode === 'signup' ? 'active' : ''}
            onClick={() => setMode('signup')}
            type="button"
            role="tab"
            aria-selected={mode === 'signup'}
          >
            Create Account
          </button>
        </div>

        {error && <div className="login-msg error show">{error}</div>}

        <form onSubmit={handleSubmit} autoComplete="off">
          <div className="login-field">
            <label htmlFor="username">Username</label>
            <input
              id="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
              placeholder="praveen76"
              required
            />
          </div>
          <div className="login-field">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete={mode === 'signin' ? 'current-password' : 'new-password'}
              placeholder="&#8226;&#8226;&#8226;&#8226;&#8226;&#8226;&#8226;&#8226;"
              required
            />
          </div>
          {mode === 'signup' && (
            <div className="login-field">
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
          <button className="login-submit" type="submit" disabled={busy}>
            {busy ? 'Please wait…' : mode === 'signin' ? 'Sign In' : 'Create Account'}
          </button>
        </form>

        <p className="login-foot">
          "We do data. We don't have opinions." <b>&mdash; Jim Simons</b>
        </p>
      </div>
    </div>
  )
}
