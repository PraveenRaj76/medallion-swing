import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiError, login, register } from '../api/client'
import { useAuth } from '../context/AuthContext'
import { MedallionLogo } from '../components/MedallionLogo'

function EyeIcon({ off }: { off: boolean }) {
  if (off) {
    return (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M17.94 17.94A10.94 10.94 0 0 1 12 20c-7 0-11-8-11-8a18.6 18.6 0 0 1 5.06-5.94M9.9 4.24A10.94 10.94 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
        <line x1="1" y1="1" x2="23" y2="23" />
      </svg>
    )
  }
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  )
}

function PasswordField({
  id,
  label,
  value,
  onChange,
  autoComplete,
}: {
  id: string
  label: string
  value: string
  onChange: (v: string) => void
  autoComplete: string
}) {
  const [shown, setShown] = useState(false)
  return (
    <div className="login-field">
      <label htmlFor={id}>{label}</label>
      <div className="login-password-wrap">
        <input
          id={id}
          type={shown ? 'text' : 'password'}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          autoComplete={autoComplete}
          required
        />
        <button
          type="button"
          className="login-eye-toggle"
          onClick={() => setShown((s) => !s)}
          aria-label={shown ? 'Hide password' : 'Show password'}
          tabIndex={-1}
        >
          <EyeIcon off={shown} />
        </button>
      </div>
    </div>
  )
}

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
          <MedallionLogo size={190} variant="hero" />
          <div className="tag">NSE + US quantamental screener &amp; forward-test</div>
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
              required
            />
          </div>
          <PasswordField
            id="password"
            label="Password"
            value={password}
            onChange={setPassword}
            autoComplete={mode === 'signin' ? 'current-password' : 'new-password'}
          />
          {mode === 'signup' && (
            <PasswordField
              id="confirm"
              label="Confirm Password"
              value={confirm}
              onChange={setConfirm}
              autoComplete="new-password"
            />
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
