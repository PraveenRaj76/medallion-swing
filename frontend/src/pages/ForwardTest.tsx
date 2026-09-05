import { useEffect, useState } from 'react'
import { ApiError, getForwardTest } from '../api/client'
import type { ForwardTestResponse, ForwardTestTrade } from '../types'
import { useAuth } from '../context/AuthContext'
import { Pill } from '../components/Pill'

type View = 'hub' | 'in' | 'us'
type Market = 'IN' | 'US'

function fmtMoney(v: number, currency: string): string {
  return `${v >= 0 ? '+' : ''}${currency}${v.toFixed(2)}`
}

/** Win rate meaning depends entirely on the number, not on whether it's
 * merely positive — a 45% win rate isn't "good" just because 45 > 0, and a
 * 0.0% with zero closed trades yet isn't "bad", it's just no data. The
 * previous `> 0 ? gain : (nothing)` logic conflated all three. */
function winRateColor(pct: number, closedCount: number): string {
  if (closedCount === 0) return 'var(--text-faint)'
  if (pct >= 90) return 'var(--gain)'
  if (pct < 60) return 'var(--loss)'
  return 'var(--warn)'
}

function HubCard({
  market,
  data,
  loading,
  error,
  onOpen,
}: {
  market: Market
  data: ForwardTestResponse | null
  loading: boolean
  error: string | null
  onOpen: () => void
}) {
  const label = market === 'IN' ? 'IN · NIFTY 500' : 'US · S&P 500'
  const title = market === 'IN' ? 'Indian Forward-Test' : 'US Forward-Test'

  if (error) {
    return (
      <div className="ft-card" style={{ opacity: 0.7 }}>
        <div className="market">{label}</div>
        <h3>{title}</h3>
        <div className="stat" style={{ color: 'var(--loss)', fontSize: 15 }}>
          Couldn't load
        </div>
        <div className="statlabel">{error}</div>
      </div>
    )
  }

  return (
    <button className="ft-card" onClick={onOpen} disabled={loading}>
      <div className="market">{label}</div>
      <h3>{title}</h3>
      {loading ? (
        <div className="stat" style={{ color: 'var(--text-faint)' }}>
          …
        </div>
      ) : (
        <div className="stat" style={{ color: winRateColor(data?.win_rate_pct ?? 0, data?.total_signals_tracked ?? 0) }}>
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
  )
}

function DeepDive({ trade, currency }: { trade: ForwardTestTrade; currency: string }) {
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
              {fmtMoney(trade.absolute_delta, currency)}
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

function DetailView({
  market,
  data,
  loading,
  error,
  onBack,
}: {
  market: Market
  data: ForwardTestResponse | null
  loading: boolean
  error: string | null
  onBack: () => void
}) {
  const currency = market === 'IN' ? '₹' : '$'
  const label = market === 'IN' ? 'India' : 'US'

  return (
    <>
      <button className="back-link" onClick={onBack}>
        &larr; Forward-Test overview
      </button>

      {error && <span className="pill loss">{error}</span>}
      {loading && !data && <p className="hero-sub">Loading {label} forward-test data…</p>}

      {data && (
        <>
          <div className="hero" style={{ paddingTop: 0 }}>
            <div className="eyebrow">
              {label} &middot; Forward-Test
            </div>
            <h1>
              {data.total_signals_tracked} closed test{data.total_signals_tracked === 1 ? '' : 's'}, {data.open_signals}{' '}
              tracking now.
            </h1>
            <div className="northstar">
              <div>
                <div className="num mono" style={{ color: winRateColor(data.win_rate_pct, data.total_signals_tracked) }}>
                  {data.win_rate_pct.toFixed(1)}%
                </div>
                <div className="label">
                  win rate · {data.total_signals_tracked} closed test{data.total_signals_tracked === 1 ? '' : 's'}
                </div>
              </div>
              <div className="sub">
                {data.successful_trades} success{data.successful_trades === 1 ? '' : 'es'} · {data.bad_trades} stopped out
                {data.total_signals_tracked > 0 && (
                  <>
                    {' '}
                    · 95% CI [{data.win_rate_ci_95.low.toFixed(1)}%, {data.win_rate_ci_95.high.toFixed(1)}%]
                  </>
                )}
              </div>
            </div>
          </div>

          <div className="kpi-row cols-5">
            <div className="kpi">
              <div className="kpi-label">Realized P&amp;L</div>
              <div className={`kpi-val ${data.total_realized_rupee_return >= 0 ? 'gain' : 'loss'}`}>
                {fmtMoney(data.total_realized_rupee_return, currency)}
              </div>
              <div className="kpi-foot">
                expectancy {currency}
                {data.expectancy_rupee.toFixed(2)} / trade
              </div>
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
              <div className="kpi-label">Profit Factor</div>
              <div className="kpi-val">{data.profit_factor != null ? data.profit_factor.toFixed(2) : '—'}</div>
              <div className="kpi-foot">gross win ÷ gross loss</div>
            </div>
            <div className="kpi">
              <div className="kpi-label">Max Drawdown</div>
              <div className="kpi-val" style={{ color: (data.max_drawdown_rupee ?? 0) > 0 ? 'var(--loss)' : undefined }}>
                {data.max_drawdown_rupee != null ? `${currency}${data.max_drawdown_rupee.toFixed(2)}` : '—'}
              </div>
              <div className="kpi-foot">{data.max_drawdown_pct != null ? `${data.max_drawdown_pct.toFixed(1)}% of peak` : 'worst peak-to-trough'}</div>
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
                          No active signals — buy from Search Profile or the Screener to open one.
                        </td>
                      </tr>
                    ) : (
                      data.active_positions.map((p) => (
                        <tr key={p.position_id}>
                          <td className="ticker">{p.ticker}</td>
                          <td className="num">
                            {currency}
                            {p.entry_price.toFixed(2)}
                          </td>
                          <td className="num">{p.current_price != null ? `${currency}${p.current_price.toFixed(2)}` : '—'}</td>
                          <td className="num" style={{ color: 'var(--loss)' }}>
                            {currency}
                            {p.stop_loss.toFixed(2)}
                          </td>
                          <td className="num" style={{ color: 'var(--gain)' }}>
                            {currency}
                            {p.target.toFixed(2)}
                          </td>
                          <td className={`num delta ${(p.unrealized_pnl ?? 0) >= 0 ? 'gain' : 'loss'}`}>
                            {p.unrealized_pnl != null ? fmtMoney(p.unrealized_pnl, currency) : '—'}
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
                      <th className="num">Abs Δ {currency}</th>
                      <th className="num">% Return</th>
                      <th>Velocity</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.trades.length === 0 ? (
                      <tr>
                        <td colSpan={5} style={{ textAlign: 'center', color: 'var(--text-faint)' }}>
                          No completed forward-tests yet — take a buy to build your real success ratio.
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
                          <td className={`num delta ${t.absolute_delta >= 0 ? 'gain' : 'loss'}`}>{fmtMoney(t.absolute_delta, currency)}</td>
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

          {data.trades.length > 0 && <DeepDive trade={data.trades[0]} currency={currency} />}
        </>
      )}
    </>
  )
}

export function ForwardTest() {
  const [view, setView] = useState<View>('hub')
  const [inData, setInData] = useState<ForwardTestResponse | null>(null)
  const [usData, setUsData] = useState<ForwardTestResponse | null>(null)
  const [inLoading, setInLoading] = useState(true)
  const [usLoading, setUsLoading] = useState(true)
  const [inError, setInError] = useState<string | null>(null)
  const [usError, setUsError] = useState<string | null>(null)
  const { userId } = useAuth()

  useEffect(() => {
    if (!userId) return
    getForwardTest(userId, 'IN')
      .then(setInData)
      .catch((err) => setInError(err instanceof ApiError ? err.message : 'Could not load India forward-test data.'))
      .finally(() => setInLoading(false))
    getForwardTest(userId, 'US')
      .then(setUsData)
      .catch((err) => setUsError(err instanceof ApiError ? err.message : 'Could not load US forward-test data.'))
      .finally(() => setUsLoading(false))
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
          <HubCard market="IN" data={inData} loading={inLoading} error={inError} onOpen={() => setView('in')} />
          <HubCard market="US" data={usData} loading={usLoading} error={usError} onOpen={() => setView('us')} />
        </div>
      </>
    )
  }

  const market: Market = view === 'us' ? 'US' : 'IN'
  return (
    <DetailView
      market={market}
      data={market === 'US' ? usData : inData}
      loading={market === 'US' ? usLoading : inLoading}
      error={market === 'US' ? usError : inError}
      onBack={() => setView('hub')}
    />
  )
}
