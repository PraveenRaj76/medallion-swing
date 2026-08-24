import { useState, type FormEvent } from 'react'
import { useSearchParams } from 'react-router-dom'
import { ApiError, getProfile } from '../api/client'
import type { ProfileResponse } from '../types'
import { useAuth } from '../context/AuthContext'
import { ChecklistTable } from '../components/ChecklistTable'

function num(raw: unknown): number | null {
  return typeof raw === 'number' && !Number.isNaN(raw) ? raw : null
}

export function SearchProfile() {
  const [params, setParams] = useSearchParams()
  const [ticker, setTicker] = useState(params.get('ticker') ?? '')
  const [profile, setProfile] = useState<ProfileResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { userId } = useAuth()

  async function runSearch(sym: string) {
    if (!sym.trim()) return
    setLoading(true)
    setError(null)
    setParams({ ticker: sym.toUpperCase() })
    try {
      const res = await getProfile(sym, true, userId ?? undefined)
      setProfile(res)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not fetch live data for this ticker.')
      setProfile(null)
    } finally {
      setLoading(false)
    }
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    runSearch(ticker)
  }

  // auto-run once if arriving with ?ticker= from the Screener table
  const initialTicker = params.get('ticker')
  const [autoRan, setAutoRan] = useState(false)
  if (initialTicker && !autoRan && !loading && !profile) {
    setAutoRan(true)
    runSearch(initialTicker)
  }

  const raw = profile?.raw ?? {}
  const xbrlRevenue = num(raw.xbrl_revenue)
  const xbrlProfit = num(raw.xbrl_profit_after_tax)
  const xbrlEps = num(raw.xbrl_eps_basic)
  const hasXbrl = xbrlRevenue !== null || xbrlProfit !== null || xbrlEps !== null

  return (
    <div className="page">
      <div className="page-header">
        <h1>Search Profile</h1>
        <p>Live NSE profile — fundamentals + technicals, pulled independently of the Screener universe load.</p>
      </div>

      <div className="card">
        <form className="ticker-search" onSubmit={handleSubmit}>
          <div className="form-field">
            <label htmlFor="ticker">Ticker</label>
            <input
              id="ticker"
              value={ticker}
              onChange={(e) => setTicker(e.target.value.toUpperCase())}
              placeholder="TCS, RELIANCE, INFY, HDFCBANK"
            />
          </div>
          <button className="btn" type="submit" disabled={loading}>
            {loading ? 'Fetching…' : 'Refresh latest'}
          </button>
        </form>
      </div>

      {error && <div className="error-banner">{error}</div>}

      {loading && (
        <div className="loading-inline">
          <span className="spinner" /> Fetching live NSE data for {ticker}…
        </div>
      )}

      {profile && !loading && (
        <>
          <div className="card">
            <div className="profile-head">
              <div>
                <h2>
                  {profile.company_name} ({profile.ticker})
                </h2>
                <div className="sub">
                  {profile.sector} · {profile.industry} · source: {profile.source}
                </div>
              </div>
              <span className={`signal-badge ${profile.buy_signal.signal}`}>
                {profile.buy_signal.signal.replace('_', ' ')}
              </span>
            </div>

            <div className="kv-grid" style={{ marginTop: '1.25rem' }}>
              <div className="kv">
                <div className="l">CMP</div>
                <div className="v">₹{profile.close_price?.toFixed(2) ?? '—'}</div>
              </div>
              <div className="kv">
                <div className="l">Data Quality</div>
                <div className="v" style={{ fontSize: '0.95rem' }}>
                  {profile.data_quality}
                </div>
              </div>
              <div className="kv">
                <div className="l">Composite</div>
                <div className="v">
                  {profile.checklist.composite_marks.toFixed(1)}/{profile.checklist.composite_max} (
                  {profile.checklist.composite_pct.toFixed(1)}%)
                </div>
              </div>
              <div className="kv">
                <div className="l">Sector Pack</div>
                <div className="v" style={{ fontSize: '0.95rem' }}>
                  {profile.checklist.sector_pack}
                </div>
              </div>
            </div>
          </div>

          <div className="card">
            <h3>Signal Gates</h3>
            <p className="card__muted">What is blocking (or clearing) a BUY signal right now.</p>
            <div className="gate-list">
              {profile.buy_signal.gates.map((g) => (
                <div key={g.gate} className={`gate-row ${g.passed ? 'passed' : 'failed'}`}>
                  <span className="gate-name">{g.gate.replace(/_/g, ' ')}</span>
                  <span className={`chip ${g.passed ? 'good' : 'bad'}`}>{g.passed ? 'PASS' : 'FAIL'}</span>
                  <span className="gate-detail">{g.detail}</span>
                </div>
              ))}
            </div>
          </div>

          {hasXbrl && (
            <div className="card">
              <h3>NSE XBRL — Latest Quarterly Filing</h3>
              <p className="card__muted">
                {typeof raw.xbrl_period_end === 'string' ? raw.xbrl_period_end : '—'} (
                {typeof raw.xbrl_consolidated === 'string' ? raw.xbrl_consolidated : 'Standalone'})
              </p>
              <div className="kv-grid">
                <div className="kv">
                  <div className="l">Revenue</div>
                  <div className="v">{xbrlRevenue !== null ? `₹${(xbrlRevenue / 1e7).toFixed(1)} Cr` : '—'}</div>
                </div>
                <div className="kv">
                  <div className="l">Net Profit</div>
                  <div className="v">{xbrlProfit !== null ? `₹${(xbrlProfit / 1e7).toFixed(1)} Cr` : '—'}</div>
                </div>
                <div className="kv">
                  <div className="l">EPS Basic</div>
                  <div className="v">{xbrlEps !== null ? `₹${xbrlEps.toFixed(2)}` : '—'}</div>
                </div>
              </div>
            </div>
          )}

          <ChecklistTable title="Fundamental Filters" group={profile.checklist.fundamental} />
          <ChecklistTable title="Technical Filters" group={profile.checklist.technical} />
        </>
      )}

      {!profile && !loading && !error && (
        <div className="empty-state">Search a ticker above to pull its live checklist.</div>
      )}
    </div>
  )
}
