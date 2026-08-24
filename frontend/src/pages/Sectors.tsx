import { useEffect, useState } from 'react'
import { ApiError, getSectors } from '../api/client'
import type { SectorsResponse } from '../types'

export function Sectors() {
  const [data, setData] = useState<SectorsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getSectors('IN')
      .then(setData)
      .catch((err) => setError(err instanceof ApiError ? err.message : 'Could not load sector rankings.'))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="page">
      <div className="page-header">
        <h1>Sector Rankings</h1>
        <p>Self-owned within-universe aggregation — built from the tracked 200-stock swing universe, not scraped index data.</p>
      </div>

      {error && <div className="error-banner">{error}</div>}

      {loading ? (
        <div className="loading-inline">
          <span className="spinner" /> Loading sector rankings…
        </div>
      ) : !data || data.rankings.length === 0 ? (
        <div className="empty-state">No sector data yet — run a Screener refresh first.</div>
      ) : (
        <>
          <div className="stat-grid">
            <div className="stat-tile">
              <div className="n tabular">{data.universe_size}</div>
              <div className="l">Universe size</div>
            </div>
            <div className="stat-tile">
              <div className="n tabular">{data.universe_median_pe?.toFixed(1) ?? '—'}</div>
              <div className="l">Universe median P/E</div>
            </div>
            <div className="stat-tile">
              <div className="n" style={{ fontSize: '1rem' }}>
                {data.as_of ?? '—'}
              </div>
              <div className="l">As of</div>
            </div>
          </div>

          <div className="sector-grid">
            {data.rankings.map((s) => (
              <div key={s.sector} className="sector-card">
                <h3>{s.sector}</h3>
                <div className="score">{s.median_composite_score?.toFixed(1) ?? '—'}</div>
                <div className="meta-line">
                  {s.constituent_count} constituent{s.constituent_count === 1 ? '' : 's'} · {s.buyable_count} buyable (
                  {s.buyable_pct.toFixed(0)}%)
                  <br />
                  Median P/E {s.median_pe?.toFixed(1) ?? '—'} · PEG {s.median_peg?.toFixed(2) ?? '—'}
                  <br />
                  Top: <strong>{s.top_ticker ?? '—'}</strong> ({s.top_ticker_score?.toFixed(1) ?? '—'})
                  {!s.confident_sample && (
                    <>
                      <br />
                      <span className="chip warn" style={{ marginTop: '0.4rem' }}>
                        small sample
                      </span>
                    </>
                  )}
                  <br />
                  <span style={{ display: 'block', marginTop: '0.5rem' }}>{s.why}</span>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
