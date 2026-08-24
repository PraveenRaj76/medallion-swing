import { useEffect, useState } from 'react'
import { ApiError, getForwardTest } from '../api/client'
import type { ForwardTestResponse } from '../types'
import { useAuth } from '../context/AuthContext'

export function ForwardTest() {
  const [data, setData] = useState<ForwardTestResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const { userId } = useAuth()

  useEffect(() => {
    if (!userId) return
    getForwardTest(userId)
      .then(setData)
      .catch((err) => setError(err instanceof ApiError ? err.message : 'Could not load forward-test data.'))
      .finally(() => setLoading(false))
  }, [userId])

  return (
    <div className="page">
      <div className="page-header">
        <h1>Forward-Test Validation Engine</h1>
        <p>1 share / signal — audits predictive accuracy of the checklist against real forward outcomes.</p>
      </div>

      {error && <div className="error-banner">{error}</div>}

      {loading ? (
        <div className="loading-inline">
          <span className="spinner" /> Loading forward-test scorecard…
        </div>
      ) : (
        data && (
          <>
            <div className="stat-grid">
              <div className="stat-tile">
                <div className="n tabular">{data.total_signals_tracked}</div>
                <div className="l">Closed tests</div>
              </div>
              <div className="stat-tile good">
                <div className="n tabular">{data.win_rate_pct.toFixed(1)}%</div>
                <div className="l">
                  Win rate ({data.successful_trades} / {data.total_signals_tracked})
                </div>
              </div>
              <div className="stat-tile">
                <div className="n tabular">₹{data.total_realized_rupee_return.toFixed(2)}</div>
                <div className="l">Realized P&amp;L</div>
              </div>
              <div className="stat-tile">
                <div className="n tabular">₹{data.expectancy_rupee.toFixed(2)}</div>
                <div className="l">Expectancy / trade</div>
              </div>
              <div className="stat-tile">
                <div className="n tabular">{data.open_signals}</div>
                <div className="l">Open now</div>
              </div>
              <div className="stat-tile">
                <div className="n tabular">{data.avg_hold_days?.toFixed(1) ?? '—'}</div>
                <div className="l">Avg hold (days)</div>
              </div>
            </div>

            <div className="card">
              <h3>Active Signals</h3>
              {data.active_positions.length === 0 ? (
                <div className="empty-state">No active signals — take a Screener BUY to open one.</div>
              ) : (
                <div className="table-scroll">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Ticker</th>
                        <th>Entry</th>
                        <th>Stop Loss</th>
                        <th>Target</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.active_positions.map((p) => (
                        <tr key={p.position_id}>
                          <td className="ticker-cell">{p.ticker}</td>
                          <td className="tabular">₹{p.entry_price.toFixed(2)}</td>
                          <td className="tabular">₹{p.stop_loss.toFixed(2)}</td>
                          <td className="tabular">₹{p.target.toFixed(2)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            <div className="card">
              <h3>Velocity Mix</h3>
              <p className="card__muted">
                Fast: {data.velocity_buckets.FAST ?? 0} · Normal: {data.velocity_buckets.NORMAL ?? 0} · Slow:{' '}
                {data.velocity_buckets.SLOW ?? 0} · Other: {data.velocity_buckets.OTHER ?? 0}
              </p>
            </div>
          </>
        )
      )}
    </div>
  )
}
