import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiError, getScreener, getSectors, postRefresh } from '../api/client'
import type { ScreenerResponse, ScreenerRow, SectorsResponse } from '../types'
import { useAuth } from '../context/AuthContext'
import { qualityPill, Pill } from '../components/Pill'
import { TrendBadge } from '../components/TrendBadge'
import { useSort } from '../hooks/useSort'

function median(nums: number[]): number | null {
  if (!nums.length) return null
  const s = [...nums].sort((a, b) => a - b)
  const mid = Math.floor(s.length / 2)
  return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2
}

export function ScreenerIndia() {
  const [view, setView] = useState<'leaderboard' | 'best-sector'>('leaderboard')
  const [data, setData] = useState<ScreenerResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [sectorFilter, setSectorFilter] = useState('')
  const [readyOnly, setReadyOnly] = useState(false)
  const { userId } = useAuth()
  const navigate = useNavigate()

  async function load() {
    setLoading(true)
    setError(null)
    try {
      const res = await getScreener({ limit: 500, ready_only: false })
      setData(res)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not load the screener.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  async function handleRefresh() {
    setRefreshing(true)
    setError(null)
    try {
      await postRefresh({ full_universe: true, with_fundamentals: true, user_id: userId ?? undefined })
      await load()
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : 'Refresh timed out or failed — a full 200-stock pull can take several minutes; try again.',
      )
    } finally {
      setRefreshing(false)
    }
  }

  const rows = data?.data ?? []
  const sectors = useMemo(() => Array.from(new Set(rows.map((r) => r.sector).filter(Boolean))).sort(), [rows])

  const filtered = useMemo(() => {
    return rows.filter((r) => {
      if (readyOnly && !(r.fundamentals_verified && r.ohlcv_ready)) return false
      if (sectorFilter && r.sector !== sectorFilter) return false
      if (search) {
        const s = search.toLowerCase()
        if (!r.ticker.toLowerCase().includes(s) && !(r.sector || '').toLowerCase().includes(s)) return false
      }
      return true
    })
  }, [rows, readyOnly, sectorFilter, search])

  const getVal = (row: ScreenerRow, key: string): string | number => {
    switch (key) {
      case 'ticker':
        return row.ticker
      case 'sector':
        return row.sector || ''
      case 'score':
        return row.composite_score ?? -1
      case 'fund':
        return row.fundamental_score ?? -1
      case 'tech':
        return row.technical_score ?? -1
      default:
        return ''
    }
  }
  const { sorted, toggle, arrow } = useSort(filtered, getVal, 'score', 'desc')

  const scores = rows.map((r) => r.composite_score).filter((v): v is number => typeof v === 'number')
  const buyableCount = rows.filter((r) => r.is_buyable).length

  return (
    <>
      <div className="hero">
        <div className="eyebrow">NIFTY 500 &middot; Quantamental Screener</div>
        <h1>Which names actually clear the bar?</h1>
        <p className="hero-sub">
          Midcap 150 + Smallcap 50 swing universe, scored on the fundamental + technical checklist. Every row shows
          exactly which filters passed — nothing is silently zeroed out.
        </p>

        <div className="northstar">
          <div>
            <div className="num mono">
              {data?.ready_count ?? 0}
              <span style={{ fontSize: 26, color: 'var(--text-faint)' }}>/{data?.total_stocks ?? 0}</span>
            </div>
            <div className="label">display-ready today</div>
          </div>
          <div className="sub">as of {data?.as_of ?? '—'}</div>
        </div>
        <div className="segmented" style={{ marginTop: 26 }}>
          <button className={view === 'leaderboard' ? 'active' : ''} onClick={() => setView('leaderboard')}>
            Leaderboard
          </button>
          <button className={view === 'best-sector' ? 'active' : ''} onClick={() => setView('best-sector')}>
            Best Sector
          </button>
        </div>
      </div>

      {error && (
        <div className="section" style={{ marginTop: 20 }}>
          <div className="pill loss">{error}</div>
        </div>
      )}

      {view === 'leaderboard' ? (
        <>
          <div className="kpi-row">
            <div className="kpi">
              <div className="kpi-label">Universe</div>
              <div className="kpi-val">{data?.total_stocks ?? '—'}</div>
              <div className="kpi-foot">Midcap 150 + Smallcap 50</div>
            </div>
            <div className="kpi">
              <div className="kpi-label">Ready Today</div>
              <div className="kpi-val gain">{data?.ready_count ?? '—'}</div>
              <div className="kpi-foot">refreshed &middot; verified &middot; in-universe</div>
            </div>
            <div className="kpi">
              <div className="kpi-label">Buyable Now</div>
              <div className="kpi-val">{buyableCount}</div>
              <div className="kpi-foot">close &gt; 200SMA &amp; RSI &le; 70</div>
            </div>
            <div className="kpi">
              <div className="kpi-label">Median Score</div>
              <div className="kpi-val">{median(scores)?.toFixed(1) ?? '—'}</div>
              <div className="kpi-foot">composite, out of ~109</div>
            </div>
          </div>

          <div className="section">
            <div className="section-head">
              <div className="section-title">
                Leaderboard <span className="count">{sorted.length} of {rows.length} shown</span>
              </div>
              <div className="filterbar">
                <input
                  type="text"
                  placeholder="Search ticker or sector…"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
                <select value={sectorFilter} onChange={(e) => setSectorFilter(e.target.value)}>
                  <option value="">All sectors</option>
                  {sectors.map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </select>
                <label className="toggle">
                  <input type="checkbox" checked={readyOnly} onChange={(e) => setReadyOnly(e.target.checked)} />
                  Ready only
                </label>
                <button
                  type="button"
                  className="toggle"
                  style={{ background: 'var(--gold)', color: 'var(--bg)', fontWeight: 700, border: 'none' }}
                  onClick={handleRefresh}
                  disabled={refreshing}
                >
                  {refreshing ? 'Refreshing…' : 'Refresh universe'}
                </button>
              </div>
            </div>
            <div className="card">
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th className="sortable" onClick={() => toggle('ticker')}>
                        Ticker<span className={`arrow ${arrow('ticker')}`} />
                      </th>
                      <th className="sortable" onClick={() => toggle('sector')}>
                        Sector<span className={`arrow ${arrow('sector')}`} />
                      </th>
                      <th className={`num sortable ${arrow('score')}`} onClick={() => toggle('score')}>
                        Score<span className={`arrow ${arrow('score')}`} />
                      </th>
                      <th>Trend</th>
                      <th>Data Quality</th>
                      <th className="num sortable" onClick={() => toggle('fund')}>
                        Fund.<span className={`arrow ${arrow('fund')}`} />
                      </th>
                      <th className="num sortable" onClick={() => toggle('tech')}>
                        Tech.<span className={`arrow ${arrow('tech')}`} />
                      </th>
                      <th>Buyable</th>
                    </tr>
                  </thead>
                  <tbody>
                    {loading ? (
                      <tr>
                        <td colSpan={8} style={{ textAlign: 'center', color: 'var(--text-faint)' }}>
                          Loading…
                        </td>
                      </tr>
                    ) : sorted.length === 0 ? (
                      <tr>
                        <td colSpan={8} style={{ textAlign: 'center', color: 'var(--text-faint)' }}>
                          No data yet — click Refresh universe to pull live data.
                        </td>
                      </tr>
                    ) : (
                      sorted.map((row) => (
                        <tr
                          key={row.ticker}
                          className="row-link"
                          onClick={() => navigate(`/profile?market=in&ticker=${row.ticker}`)}
                        >
                          <td className="ticker">
                            {row.ticker}
                            <div className="company">{row.company_name}</div>
                          </td>
                          <td>{row.sector}</td>
                          <td className="num">
                            {row.composite_score != null && (
                              <span className="barwrap">
                                <span className="bar" style={{ width: `${Math.min(100, row.composite_score)}%` }} />
                              </span>
                            )}
                            {row.composite_score?.toFixed(1) ?? '—'}
                          </td>
                          <td>
                            <TrendBadge
                              closePrice={row.close_price ?? null}
                              sma200={row.sma_200 ?? null}
                              alpha3m={row.alpha_3m ?? null}
                            />
                          </td>
                          <td>{qualityPill(row.data_quality)}</td>
                          <td className="num">{row.fundamental_score?.toFixed(1) ?? '—'}</td>
                          <td className="num">{row.technical_score?.toFixed(1) ?? '—'}</td>
                          <td>{row.is_buyable ? <Pill kind="win">Yes</Pill> : <Pill kind="neutral">No</Pill>}</td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
            <p className="footnote">
              Live from /api/screener — Trend replaces an illustrative sparkline with real price-vs-200SMA and 3M
              alpha, since no historical price series is exposed by the API yet.
            </p>
          </div>
        </>
      ) : (
        <BestSectorView />
      )}
    </>
  )
}

function BestSectorView() {
  const [data, setData] = useState<SectorsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getSectors('IN')
      .then(setData)
      .catch((err) => setError(err instanceof ApiError ? err.message : 'Could not load sector rankings.'))
      .finally(() => setLoading(false))
  }, [])

  const getVal = (row: SectorsResponse['rankings'][number], key: string): string | number => {
    switch (key) {
      case 'sector':
        return row.sector
      case 'n':
        return row.constituent_count
      case 'buyable':
        return row.buyable_pct
      case 'composite':
        return row.median_composite_score ?? -1
      case 'pe':
        return row.median_pe ?? -1
      case 'score':
        return row.sector_score ?? -1
      default:
        return ''
    }
  }
  const { sorted, toggle, arrow } = useSort(data?.rankings ?? [], getVal, 'score', 'desc')
  const top = sorted[0]

  if (loading) return <div className="section" style={{ marginTop: 32 }}><p className="hero-sub">Loading sector rankings…</p></div>
  if (error) return <div className="section" style={{ marginTop: 32 }}><span className="pill loss">{error}</span></div>
  if (!data || sorted.length === 0)
    return (
      <div className="section" style={{ marginTop: 32 }}>
        <p className="hero-sub">No sector data yet — run a Screener refresh first.</p>
      </div>
    )

  return (
    <>
      <div className="section" style={{ marginTop: 8 }}>
        <div className="card" style={{ padding: '26px 28px' }}>
          <div className="eyebrow" style={{ marginBottom: 10 }}>
            Best Sector Right Now
          </div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 16, flexWrap: 'wrap' }}>
            <div className="dd-ticker" style={{ fontSize: 26 }}>
              {top?.sector ?? '—'}
            </div>
            <div className="mono" style={{ fontSize: 32, fontWeight: 700, color: 'var(--gain)' }}>
              {top?.sector_score?.toFixed(1) ?? '—'}
            </div>
            <Pill kind={top?.confident_sample ? 'win' : 'neutral'}>
              {top?.confident_sample ? `Confident sample · n=${top.constituent_count}` : `Small sample · n=${top?.constituent_count}`}
            </Pill>
          </div>
          <p className="hero-sub" style={{ marginTop: 10, maxWidth: 640 }}>
            {top?.buyable_count} of {top?.constituent_count} constituents ({top?.buyable_pct.toFixed(0)}%) currently
            buyable — median composite score {top?.median_composite_score?.toFixed(1) ?? '—'} — led by{' '}
            {top?.top_ticker ?? '—'} at {top?.top_ticker_score?.toFixed(1) ?? '—'}.
          </p>
          <p className="hero-sub" style={{ marginTop: 6, maxWidth: 640, color: 'var(--text-faint)', fontStyle: 'italic' }}>
            {top?.valuation_read}
          </p>
        </div>
      </div>

      <div className="section">
        <div className="section-head">
          <div className="section-title">
            Sector Rankings <span className="count">within-universe, live</span>
          </div>
        </div>
        <div className="card">
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th className={`sortable ${arrow('score')}`} onClick={() => toggle('score')}>
                    Rank<span className={`arrow ${arrow('score')}`} />
                  </th>
                  <th className="sortable" onClick={() => toggle('sector')}>
                    Sector<span className={`arrow ${arrow('sector')}`} />
                  </th>
                  <th className="num sortable" onClick={() => toggle('n')}>
                    Constituents<span className={`arrow ${arrow('n')}`} />
                  </th>
                  <th className="num sortable" onClick={() => toggle('buyable')}>
                    Buyable %<span className={`arrow ${arrow('buyable')}`} />
                  </th>
                  <th className="num sortable" onClick={() => toggle('composite')}>
                    Median Composite<span className={`arrow ${arrow('composite')}`} />
                  </th>
                  <th className="num sortable" onClick={() => toggle('pe')}>
                    Median P/E<span className={`arrow ${arrow('pe')}`} />
                  </th>
                  <th className="num sortable" onClick={() => toggle('score')}>
                    Sector Score<span className={`arrow ${arrow('score')}`} />
                  </th>
                </tr>
              </thead>
              <tbody>
                {sorted.map((s, i) => (
                  <tr key={s.sector}>
                    <td>{s.confident_sample ? <Pill kind="win">#{i + 1}</Pill> : <Pill kind="neutral">n/a</Pill>}</td>
                    <td className="ticker">
                      {s.sector}
                      <div className="company">
                        {s.buyable_count} of {s.constituent_count} buyable — led by {s.top_ticker ?? '—'} at{' '}
                        {s.top_ticker_score?.toFixed(1) ?? '—'}
                      </div>
                    </td>
                    <td className="num">{s.constituent_count}</td>
                    <td className="num">{s.buyable_pct.toFixed(0)}%</td>
                    <td className="num">{s.median_composite_score?.toFixed(1) ?? '—'}</td>
                    <td className="num">{s.median_pe?.toFixed(1) ?? '—'}</td>
                    <td className="num">
                      {s.sector_score != null && (
                        <span className="barwrap">
                          <span className="bar" style={{ width: `${Math.min(100, s.sector_score)}%` }} />
                        </span>
                      )}
                      {s.sector_score?.toFixed(1) ?? '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
        <p className="footnote">
          Computed by aggregating the live universe's own stock-level scores, grouped by sector — not scraped
          index-level PE. Sectors under 3 constituents are shown but not score-ranked.
        </p>
      </div>
    </>
  )
}
