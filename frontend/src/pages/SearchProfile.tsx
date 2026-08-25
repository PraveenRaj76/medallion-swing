import { useState, type FormEvent } from 'react'
import { useSearchParams } from 'react-router-dom'
import { ApiError, getProfile } from '../api/client'
import type { ChecklistGroup, ProfileResponse } from '../types'
import { useAuth } from '../context/AuthContext'
import { Pill, qualityPill } from '../components/Pill'

function num(raw: unknown): number | null {
  return typeof raw === 'number' && !Number.isNaN(raw) ? raw : null
}

function str(raw: unknown): string | null {
  return typeof raw === 'string' && raw ? raw : null
}

function ChecklistCard({ title, group }: { title: string; group: ChecklistGroup }) {
  return (
    <div className="card">
      <div className="checklist-card-head">
        <div className="t">{title}</div>
        <div className="s">
          {group.total_marks.toFixed(1)} / {group.max_marks}
        </div>
      </div>
      {group.items.map((item) => {
        const dotClass = item.max_marks === 0 ? 'skip' : item.passed ? 'pass' : 'fail'
        const dotChar = item.max_marks === 0 ? '·' : item.passed ? '✓' : '✕'
        return (
          <div className="check-item" key={item.name}>
            <div className={`check-dot ${dotClass}`}>{dotChar}</div>
            <div className="check-body">
              <div className="check-top">
                <div className="check-name">{item.name}</div>
                <div className={`check-marks ${item.max_marks === 0 ? '' : item.passed ? 'pass' : 'fail'}`}>
                  {item.marks.toFixed(1)} / {item.max_marks}
                </div>
              </div>
              <div className="check-val">{item.value}</div>
              <div className="check-note">{item.note}</div>
            </div>
          </div>
        )
      })}
    </div>
  )
}

export function SearchProfile() {
  const [params, setParams] = useSearchParams()
  const [market, setMarket] = useState<'in' | 'us'>((params.get('market') as 'in' | 'us') || 'in')
  const [ticker, setTicker] = useState(params.get('ticker') ?? 'RELIANCE')
  const [profile, setProfile] = useState<ProfileResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { userId } = useAuth()

  async function runSearch(sym: string) {
    if (!sym.trim()) return
    setLoading(true)
    setError(null)
    setParams({ market, ticker: sym.toUpperCase() })
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
    if (market === 'in') runSearch(ticker)
  }

  const initialTicker = params.get('ticker')
  const [autoRan, setAutoRan] = useState(false)
  if (initialTicker && market === 'in' && !autoRan && !loading && !profile) {
    setAutoRan(true)
    runSearch(initialTicker)
  }

  function switchMarket(m: 'in' | 'us') {
    setMarket(m)
    setProfile(null)
    setError(null)
    setTicker(m === 'in' ? 'RELIANCE' : 'AAPL')
  }

  const raw = profile?.raw ?? {}
  const sources = (raw.fundamentals_sources as string[] | undefined) ?? []
  const xbrlRevenue = num(raw.xbrl_revenue)
  const xbrlProfit = num(raw.xbrl_profit_after_tax)
  const xbrlEps = num(raw.xbrl_eps_basic)
  const hasXbrl = xbrlRevenue !== null || xbrlProfit !== null || xbrlEps !== null

  return (
    <>
      <div className="hero">
        <div className="eyebrow">Single-Stock Deep Dive</div>
        <h1>Why does this stock score what it scores?</h1>
        <p className="hero-sub">Every checklist line, its raw value, and the marks it earned — so a score is never a black box.</p>
        <form className="searchbox" onSubmit={handleSubmit}>
          <input
            type="text"
            className="mono"
            value={ticker}
            onChange={(e) => setTicker(e.target.value.toUpperCase())}
            placeholder={market === 'in' ? 'e.g. RELIANCE' : 'e.g. AAPL'}
            disabled={market === 'us'}
          />
          <button type="submit" disabled={loading || market === 'us'}>
            {loading ? 'Fetching…' : 'Search'}
          </button>
        </form>
        <div className="segmented" style={{ marginTop: 16 }}>
          <button className={market === 'in' ? 'active' : ''} onClick={() => switchMarket('in')}>
            IN &middot; {market === 'in' ? ticker : 'RELIANCE'}
          </button>
          <button className={market === 'us' ? 'active' : ''} onClick={() => switchMarket('us')}>
            US &middot; AAPL
          </button>
        </div>
      </div>

      {market === 'us' ? (
        <div className="section" style={{ marginTop: 32 }}>
          <div className="card not-built">
            <span className="pill neutral">Not built yet</span>
            <p>
              No SEC EDGAR / Alpaca pipeline exists for US tickers, so there's no real data to profile here yet — see
              the US Screener page for the same note.
            </p>
          </div>
        </div>
      ) : (
        <>
          {error && (
            <div className="section" style={{ marginTop: 32 }}>
              <span className="pill loss">{error}</span>
            </div>
          )}

          {loading && (
            <div className="section" style={{ marginTop: 32 }}>
              <p className="hero-sub">Fetching live NSE data for {ticker}…</p>
            </div>
          )}

          {profile && !loading && (
            <>
              <div className="section" style={{ marginTop: 32 }}>
                <div className="card">
                  <div className="profile-head">
                    <div className="profile-id">
                      <div className="tk mono">{profile.ticker}</div>
                      <div className="nm">
                        {profile.company_name} &middot; {profile.sector} &middot; {profile.industry} &middot; ₹
                        {profile.close_price?.toFixed(2) ?? '—'}
                      </div>
                      <div className="tags">
                        {qualityPill(profile.data_quality)}
                        <Pill kind="neutral">{profile.checklist.sector_pack} pack</Pill>
                        {profile.buy_signal.signal === 'BUY' ? (
                          <Pill kind="open">Buyable</Pill>
                        ) : (
                          <Pill kind="neutral">{profile.buy_signal.signal.replace('_', ' ')}</Pill>
                        )}
                      </div>
                    </div>
                    <div className="profile-score">
                      <div className="v">
                        {profile.checklist.composite_pct.toFixed(1)}
                        <span style={{ fontSize: 18 }}>%</span>
                      </div>
                      <div className="l">Composite</div>
                      <div className="split">
                        Fund {profile.checklist.fundamental.total_marks.toFixed(1)}/{profile.checklist.fundamental.max_marks}{' '}
                        &middot; Tech {profile.checklist.technical.total_marks.toFixed(1)}/{profile.checklist.technical.max_marks}
                      </div>
                    </div>
                  </div>
                  <div className="source-strip">
                    <div className="source-chip">
                      <span className="k">Price</span> <span className="v">Yahoo Finance</span>
                    </div>
                    {sources.map((s) => (
                      <div className="source-chip" key={s}>
                        <span className="k">Source</span> <span className="v">{s}</span>
                      </div>
                    ))}
                    {hasXbrl && str(raw.xbrl_period_end) && (
                      <div className="source-chip">
                        <span className="k">XBRL filing</span> <span className="v">{str(raw.xbrl_period_end)}</span>
                      </div>
                    )}
                  </div>
                </div>
              </div>

              {hasXbrl && (
                <div className="section">
                  <div className="section-head">
                    <div className="section-title">NSE XBRL — Latest Quarterly Filing</div>
                  </div>
                  <div className="card" style={{ padding: '20px 24px', display: 'flex', gap: 40, flexWrap: 'wrap' }}>
                    <div>
                      <div className="kpi-label">Revenue</div>
                      <div className="kpi-val">{xbrlRevenue !== null ? `₹${(xbrlRevenue / 1e7).toFixed(1)} Cr` : '—'}</div>
                    </div>
                    <div>
                      <div className="kpi-label">Net Profit</div>
                      <div className="kpi-val">{xbrlProfit !== null ? `₹${(xbrlProfit / 1e7).toFixed(1)} Cr` : '—'}</div>
                    </div>
                    <div>
                      <div className="kpi-label">EPS Basic</div>
                      <div className="kpi-val">{xbrlEps !== null ? `₹${xbrlEps.toFixed(2)}` : '—'}</div>
                    </div>
                  </div>
                </div>
              )}

              <div className="section">
                <div className="section-head">
                  <div className="section-title">Checklist Breakdown</div>
                </div>
                <div className="checklist-grid">
                  <ChecklistCard title="Fundamental · Risk & Quality Screen" group={profile.checklist.fundamental} />
                  <ChecklistCard title="Technical · Trade Timing" group={profile.checklist.technical} />
                </div>
                <p className="footnote">Live from /api/profile/{profile.ticker}?live=true — every value above is what factor_engine.py actually computed for this row, just now.</p>
              </div>

              <div className="section">
                <div className="section-head">
                  <div className="section-title">Signal Gates</div>
                </div>
                <div className="card" style={{ padding: '10px 4px' }}>
                  {profile.buy_signal.gates.map((g) => (
                    <div className="check-item" key={g.gate}>
                      <div className={`check-dot ${g.passed ? 'pass' : 'fail'}`}>{g.passed ? '✓' : '✕'}</div>
                      <div className="check-body">
                        <div className="check-top">
                          <div className="check-name">{g.gate.replace(/_/g, ' ')}</div>
                        </div>
                        <div className="check-val">{g.detail}</div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </>
          )}

          {!profile && !loading && !error && (
            <div className="section" style={{ marginTop: 32 }}>
              <p className="hero-sub">Search a ticker above to pull its live checklist.</p>
            </div>
          )}
        </>
      )}
    </>
  )
}
