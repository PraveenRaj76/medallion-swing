import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiError, getScreener, postRefresh } from '../api/client'
import type { ScreenerResponse } from '../types'
import { useAuth } from '../context/AuthContext'

export function Screener() {
  const [data, setData] = useState<ScreenerResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [minScore, setMinScore] = useState(0)
  const [readyOnly, setReadyOnly] = useState(false)
  const { userId } = useAuth()
  const navigate = useNavigate()

  async function load() {
    setLoading(true)
    setError(null)
    try {
      const res = await getScreener({ limit: 200, min_score: minScore, ready_only: readyOnly })
      setData(res)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not load the screener.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [minScore, readyOnly])

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

  return (
    <div className="page">
      <div className="page-header">
        <h1>Smart Screener</h1>
        <p>
          Midcap 150 + Smallcap 50 (~200 swing names). Refresh pulls live price + fundamentals + technicals for the
          whole universe — this can take a few minutes.
        </p>
      </div>

      {error && <div className="error-banner">{error}</div>}

      <div className="card" style={{ display: 'flex', gap: '1.5rem', alignItems: 'flex-end', flexWrap: 'wrap' }}>
        <div className="form-field" style={{ marginBottom: 0 }}>
          <label htmlFor="minScore">Min composite score</label>
          <input
            id="minScore"
            type="number"
            min={0}
            max={100}
            value={minScore}
            onChange={(e) => setMinScore(Number(e.target.value))}
            style={{ width: 120 }}
          />
        </div>
        <div
          className="form-field form-field--inline"
          style={{ marginBottom: 0, flexDirection: 'row', alignItems: 'center', gap: '0.5rem' }}
        >
          <input
            id="readyOnly"
            type="checkbox"
            checked={readyOnly}
            onChange={(e) => setReadyOnly(e.target.checked)}
            style={{ width: 'auto' }}
          />
          <label htmlFor="readyOnly" style={{ marginBottom: 0 }}>
            Ready-only (fully verified today)
          </label>
        </div>
        <button className="btn" onClick={handleRefresh} disabled={refreshing}>
          {refreshing ? 'Refreshing (this can take a few minutes)…' : 'Refresh universe'}
        </button>
      </div>

      {data && (
        <div className="stat-grid">
          <div className="stat-tile">
            <div className="n tabular">{data.total_stocks}</div>
            <div className="l">Total tracked</div>
          </div>
          <div className="stat-tile good">
            <div className="n tabular">{data.ready_count}</div>
            <div className="l">Ready (fully verified today)</div>
          </div>
          <div className="stat-tile">
            <div className="n tabular">{data.returned}</div>
            <div className="l">Shown (this filter)</div>
          </div>
          <div className="stat-tile">
            <div className="n" style={{ fontSize: '1rem' }}>
              {data.as_of ?? '—'}
            </div>
            <div className="l">As of</div>
          </div>
        </div>
      )}

      <div className="card" style={{ padding: 0 }}>
        {loading ? (
          <div className="loading-inline" style={{ padding: '1.5rem' }}>
            <span className="spinner" /> Loading screener…
          </div>
        ) : !data || data.data.length === 0 ? (
          <div className="empty-state">No data yet — click Refresh universe to pull live data.</div>
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Ticker</th>
                  <th>Company</th>
                  <th>Sector</th>
                  <th>Composite</th>
                  <th>Fundamental</th>
                  <th>Technical</th>
                  <th>CMP</th>
                  <th>Data Quality</th>
                  <th>Buyable</th>
                </tr>
              </thead>
              <tbody>
                {data.data.map((row) => (
                  <tr key={row.ticker} className="clickable" onClick={() => navigate(`/search?ticker=${row.ticker}`)}>
                    <td className="ticker-cell">{row.ticker}</td>
                    <td>{row.company_name}</td>
                    <td>{row.sector}</td>
                    <td className="tabular">{row.composite_score?.toFixed(1) ?? '—'}</td>
                    <td className="tabular">{row.fundamental_score?.toFixed(1) ?? '—'}</td>
                    <td className="tabular">{row.technical_score?.toFixed(1) ?? '—'}</td>
                    <td className="tabular">{row.close_price ? `₹${row.close_price.toFixed(2)}` : '—'}</td>
                    <td>
                      <span
                        className={`chip ${
                          row.data_quality === 'SOURCED' ? 'good' : row.data_quality === 'FALLBACK' ? 'warn' : 'bad'
                        }`}
                      >
                        {row.data_quality}
                      </span>
                    </td>
                    <td>
                      {row.is_buyable ? <span className="chip good">BUY</span> : <span className="chip neutral">—</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
