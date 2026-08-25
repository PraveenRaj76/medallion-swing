import { useEffect, useState } from 'react'
import { ApiError, getForwardTest } from '../api/client'
import type { ForwardTestResponse, ForwardTestTrade } from '../types'
import { useAuth } from '../context/AuthContext'
import { Pill } from '../components/Pill'

type View = 'hub' | 'in' | 'us'

export function ForwardTest() {
  const [view, setView] = useState<View>('hub')
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

  if (view === 'hub') {
    return (
      <>
        <div className="hero" style={{ borderBottom: 'none', paddingBottom: 0 }}>
          <div className="eyebrow">Forward-Test Validation Engine</div>
          <h1>Does the checklist actually work?</h1>
          <p className="hero-sub">
            Every closed signal, tracked against its own entry, stop and target. No backtesting hindsight — only
            what would have really happened.
          </p>
          <p className="quote">
            "We do data. We don't have opinions." <b>— Jim Simons</b>
          </p>
        </div>

        <div className="ft-hub">
          <button className="ft-card" onClick={() => setView('in')} disabled={loading}>
            <div className="market">IN &middot; NIFTY 500</div>
            <h3>Indian Forward-Test</h3>
            {loading ? (
              <div className="stat" style={{ color: 'var(--text-faint)' }}>
                …
              </div>
            ) : (
              <div className={`stat ${(data?.win_rate_pct ?? 0) > 0 ? 'gain' : ''}`}>
                {data?.win_rate_pct.toFixed(1) ?? '0.0'}%
              </div>
            )}
            <div className="statlabel">
              win rate &middot; {data?.total_signals_tracked ?? 0} closed test
              {data?.total_signals_tracked === 1 ? '' : 's'} &middot; {data?.open_signals ?? 0} open signal
              {data?.open_signals === 1 ? '' : 's'}
            </div>
            <div className="go">
              View full scorecard <span className="arrow">→</span>
            </div>
          </button>
          <div className="ft-card" style={{ opacity: 0.6 }}>
            <div className="market">US &middot; Large / Mid / Small</div>
            <h3>US Forward-Test</h3>
            <div className="stat" style={{ color: 'var(--text-faint)', fontSize: 24 }}>
              Not built
            </div>
            <div className="statlabel">No US screener or price feed exists yet to generate signals from.</div>
          </div>
        </div>
      </>
    )
  }

  return (
    <>
      <button className="back-link" onClick={() => setView('hub')}>
        &larr; Forward-Test overview
      </button>

      {error && <span className="pill loss">{error}</span>}

      {data && (
        <>
          <div className="hero" style={{ paddingTop: 0 }}>
            <div className="eyebrow">India &middot; Forward-Test</div>
            <h1>
              {data.total_signals_tracked} closed test{data.total_signals_tracked === 1 ? '' : 's'}, {data.open_signals}{' '}
              tracking now.
            </h1>
            <div className="northstar">
              <div>
                <div className={`num mono ${data.win_rate_pct > 0 ? 'gain' : ''}`}>{data.win_rate_pct.toFixed(1)}%</div>
                <div className="label">win rate · {data.total_signals_tracked} closed test{data.total_signals_tracked === 1 ? '' : 's'}</div>
              </div>
              <div className="sub">
                {data.successful_trades} success{data.successful_trades === 1 ? '' : 'es'} · {data.bad_trades} stopped
                out
              </div>
            </div>
          </div>

          <div className="kpi-row">
            <div className="kpi">
              <div className="kpi-label">Realized P&amp;L</div>
              <div className={`kpi-val ${data.total_realized_rupee_return >= 0 ? 'gain' : 'loss'}`}>
                {data.total_realized_rupee_return >= 0 ? '+' : ''}₹{data.total_realized_rupee_return.toFixed(2)}
              </div>
              <div className="kpi-foot">expectancy ₹{data.expectancy_rupee.toFixed(2)} / trade</div>
            </div>
            <div className="kpi">
              <div className="kpi-label">Avg Hold Horizon</div>
              <div className="kpi-val">
                {data.avg_hold_days ?? '—'}
                {data.avg_hold_days != null && <span style={{ fontSize: 15, color: 'var(--text-faint)' }}>d</span>}
              </div>
              <div className="kpi-foot">entry → exit days</div>
            </div>
            <div className="kpi">
              <div className="kpi-label">Velocity Mix</div>
              <div className="kpi-val" style={{ fontSize: 16, paddingTop: 6 }}>
                {data.velocity_buckets.FAST ?? 0} fast · {data.velocity_buckets.NORMAL ?? 0} norm ·{' '}
                {data.velocity_buckets.SLOW ?? 0} slow
              </div>
              <div className="kpi-foot">exit speed distribution</div>
            </div>
            <div className="kpi">
              <div className="kpi-label">Open Signals</div>
              <div className="kpi-val">{data.open_signals}</div>
              <div className="kpi-foot">tracking now</div>
            </div>
          </div>

          <div className="section">
            <div className="section-head">
              <div className="section-title">
                Active Signals <span className="count">{data.active_positions.length} tracking</span>
              </div>
            </div>
            <div className="card">
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Ticker</th>
                      <th className="num">Entry</th>
                      <th className="num">Mark</th>
                      <th className="num">Stop</th>
                      <th className="num">Target</th>
                      <th className="num">uPNL</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.active_positions.length === 0 ? (
                      <tr>
                        <td colSpan={6} style={{ textAlign: 'center', color: 'var(--text-faint)' }}>
                          No active signals — take a Screener buy to open one.
                        </td>
                      </tr>
                    ) : (
                      data.active_positions.map((p) => (
                        <tr key={p.position_id}>
                          <td className="ticker">{p.ticker}</td>
                          <td className="num">₹{p.entry_price.toFixed(2)}</td>
                          <td className="num">{p.current_price != null ? `₹${p.current_price.toFixed(2)}` : '—'}</td>
                          <td className="num" style={{ color: 'var(--loss)' }}>
                            ₹{p.stop_loss.toFixed(2)}
                          </td>
                          <td className="num" style={{ color: 'var(--gain)' }}>
                            ₹{p.target.toFixed(2)}
                          </td>
                          <td className={`num delta ${(p.unrealized_pnl ?? 0) >= 0 ? 'gain' : 'loss'}`}>
                            {p.unrealized_pnl != null ? `${p.unrealized_pnl >= 0 ? '+' : ''}₹${p.unrealized_pnl.toFixed(2)}` : '—'}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          <div className="section">
            <div className="section-head">
              <div className="section-title">
                Closed Results <span className="count">{data.trades.length} test{data.trades.length === 1 ? '' : 's'}</span>
              </div>
            </div>
            <div className="card">
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Ticker</th>
                      <th>Result</th>
                      <th className="num">Abs Δ ₹</th>
                      <th className="num">% Return</th>
                      <th>Velocity</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.trades.length === 0 ? (
                      <tr>
                        <td colSpan={5} style={{ textAlign: 'center', color: 'var(--text-faint)' }}>
                          No completed forward-tests yet — take Screener buys to build your real success ratio.
                        </td>
                      </tr>
                    ) : (
                      data.trades.map((t, i) => (
                        <tr key={`${t.ticker}-${i}`}>
                          <td className="ticker">{t.ticker}</td>
                          <td>
                            <Pill kind={t.absolute_delta >= 0 ? 'win' : 'loss'}>
                              {t.absolute_delta >= 0 ? 'SUCCESSFUL' : 'STOPPED OUT'}
                            </Pill>
                          </td>
                          <td className={`num delta ${t.absolute_delta >= 0 ? 'gain' : 'loss'}`}>
                            {t.absolute_delta >= 0 ? '+' : ''}₹{t.absolute_delta.toFixed(2)}
                          </td>
                          <td className={`num delta ${t.pct_return >= 0 ? 'gain' : 'loss'}`}>
                            {t.pct_return >= 0 ? '+' : ''}
                            {t.pct_return.toFixed(2)}%
                          </td>
                          <td className="mono" style={{ color: 'var(--text-dim)', fontSize: 12.5 }}>
                            {t.velocity_label}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          {data.trades.length > 0 && <DeepDive trade={data.trades[0]} />}
        </>
      )}
    </>
  )
}

function DeepDive({ trade }: { trade: ForwardTestTrade }) {
  return (
    <div className="section">
      <div className="section-head">
        <div className="section-title">Trade Deep-Dive</div>
      </div>
      <div className="card deepdive">
        <div className="dd-head">
          <div className="dd-ticker">{trade.ticker}</div>
          <Pill kind={trade.absolute_delta >= 0 ? 'win' : 'loss'}>
            {trade.absolute_delta >= 0 ? 'SUCCESSFUL TRADE' : 'STOPPED-OUT TRADE'}
          </Pill>
        </div>
        <div className="dd-grid">
          <div className="dd-item">
            <div className="l">Absolute Value Delta</div>
            <div className={`v ${trade.absolute_delta >= 0 ? 'gain' : ''}`} style={{ color: trade.absolute_delta < 0 ? 'var(--loss)' : undefined }}>
              {trade.absolute_delta >= 0 ? '+' : ''}₹{trade.absolute_delta.toFixed(2)}
            </div>
          </div>
          <div className="dd-item">
            <div className="l">% P/L Return</div>
            <div className={`v ${trade.pct_return >= 0 ? 'gain' : ''}`} style={{ color: trade.pct_return < 0 ? 'var(--loss)' : undefined }}>
              {trade.pct_return >= 0 ? '+' : ''}
              {trade.pct_return.toFixed(2)}%
            </div>
          </div>
          <div className="dd-item">
            <div className="l">Velocity</div>
            <div className="v" style={{ fontSize: 16 }}>
              {trade.velocity_label}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
