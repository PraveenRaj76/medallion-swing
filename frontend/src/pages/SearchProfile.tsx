import { useEffect, useState, type FormEvent } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { ApiError, getProfile, postCloseTrade, postOpenTrade } from '../api/client'
import type { ActivePosition, ChecklistGroup, PricePoint, ProfileResponse } from '../types'
import { useAuth } from '../context/AuthContext'
import { Pill, qualityPill } from '../components/Pill'

function num(raw: unknown): number | null {
  return typeof raw === 'number' && !Number.isNaN(raw) ? raw : null
}

function str(raw: unknown): string | null {
  return typeof raw === 'string' && raw ? raw : null
}

function fmt(v: number | null | undefined, decimals = 2): string {
  return v == null || Number.isNaN(v) ? '—' : v.toFixed(decimals)
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

function QuoteHero({ profile, currency }: { profile: ProfileResponse; currency: string }) {
  const q = profile.quote
  const changeClass = (q.day_change ?? 0) >= 0 ? 'gain' : 'loss'
  const rangePct =
    q.week52_high != null && q.week52_low != null && q.price != null && q.week52_high > q.week52_low
      ? ((q.price - q.week52_low) / (q.week52_high - q.week52_low)) * 100
      : null

  return (
    <div className="card">
      <div className="quote-hero">
        <div>
          <div className="quote-price-block">
            <div className="quote-price mono">
              {currency}
              {fmt(q.price)}
            </div>
            {q.day_change != null && (
              <div className={`quote-change ${changeClass}`}>
                {q.day_change >= 0 ? '▲' : '▼'} {currency}
                {fmt(Math.abs(q.day_change))} ({fmt(Math.abs(q.day_change_pct ?? 0))}%)
              </div>
            )}
          </div>
          <div className="quote-meta">
            {q.source ? q.source.toUpperCase() : 'YAHOO'} · {q.price_kind}
            {q.fetched_at ? ` · fetched ${q.fetched_at}` : ''}
          </div>
        </div>
      </div>
      <div className="quote-stats">
        <div className="quote-stat">
          <div className="l">Open</div>
          <div className="v">
            {currency}
            {fmt(q.open)}
          </div>
        </div>
        <div className="quote-stat">
          <div className="l">Day High</div>
          <div className="v">
            {currency}
            {fmt(q.day_high)}
          </div>
        </div>
        <div className="quote-stat">
          <div className="l">Day Low</div>
          <div className="v">
            {currency}
            {fmt(q.day_low)}
          </div>
        </div>
        <div className="quote-stat">
          <div className="l">Prev Close</div>
          <div className="v">
            {currency}
            {fmt(q.prev_close)}
          </div>
        </div>
        <div className="quote-stat">
          <div className="l">Volume</div>
          <div className="v">{q.volume != null ? Math.round(q.volume).toLocaleString() : '—'}</div>
        </div>
      </div>
      {q.week52_high != null && q.week52_low != null && (
        <div className="range-bar-wrap">
          <div className="range-bar-labels">
            <span>
              52W Low {currency}
              {fmt(q.week52_low)}
            </span>
            <span>
              52W High {currency}
              {fmt(q.week52_high)}
            </span>
          </div>
          <div className="range-bar">
            {rangePct != null && (
              <div className="range-bar-dot" style={{ left: `${Math.min(100, Math.max(0, rangePct))}%` }} />
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function BuyForm({
  profile,
  currency,
  market,
  userId,
}: {
  profile: ProfileResponse
  currency: string
  market: 'in' | 'us'
  userId: number | null
}) {
  const navigate = useNavigate()
  const levels = profile.trade_levels
  const currentPrice = profile.quote.price ?? profile.close_price ?? 0
  const [entry, setEntry] = useState(currentPrice || 0)
  const [stop, setStop] = useState(levels?.stop_loss ?? Math.round((currentPrice || 0) * 0.95 * 100) / 100)
  const [target, setTarget] = useState(levels?.target ?? Math.round((currentPrice || 0) * 1.1 * 100) / 100)
  const [submitting, setSubmitting] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [opened, setOpened] = useState<{ entry: number; stop: number; target: number } | null>(null)

  const risk = entry - stop
  const reward = target - entry
  const rrr = risk > 0 ? reward / risk : 0
  const gates = profile.buy_signal.gates
  const blockedCount = gates.filter((g) => !g.passed).length

  async function submit() {
    setSubmitting(true)
    setErr(null)
    try {
      const atr = num(profile.raw.atr_value)
      await postOpenTrade({
        ticker: profile.ticker,
        entry_price: entry,
        stop_loss: stop,
        target,
        atr: atr ?? undefined,
        market: market.toUpperCase() as 'IN' | 'US',
        user_id: userId ?? undefined,
      })
      // Deliberately not calling onDone() here — that re-fetches the whole
      // profile and would swap this card straight to PositionCard mid-flight
      // (the parent shows a full-page "Fetching…" state while that's in
      // flight), which would hide the success banner before it's readable.
      // The position is already open in the backend; the page just stays on
      // this confirmation until the user navigates via the CTA below, or
      // searches again (which naturally picks up the new position).
      setOpened({ entry, stop, target })
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : 'Could not open trade.')
    } finally {
      setSubmitting(false)
    }
  }

  if (opened) {
    return (
      <div className="card trade-card">
        <div className="trade-success-banner">
          <div className="trade-success-icon">✓</div>
          <div className="trade-success-body">
            <div className="trade-success-title">Trade opened — {profile.ticker} is now tracked</div>
            <div className="trade-success-detail">
              Entry {currency}
              {opened.entry.toFixed(2)} · Stop {currency}
              {opened.stop.toFixed(2)} · Target {currency}
              {opened.target.toFixed(2)}
            </div>
          </div>
          <button className="trade-success-cta" onClick={() => navigate('/forward-test')}>
            View in Forward-Test →
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="card trade-card">
      <div className="trade-head">
        <h3>Open a Forward-Test Signal</h3>
        {profile.buy_signal.signal === 'BUY' ? (
          <Pill kind="win">All gates clear</Pill>
        ) : (
          <Pill kind="neutral">
            {blockedCount} gate{blockedCount === 1 ? '' : 's'} not clear
          </Pill>
        )}
      </div>
      <div className="gate-strip">
        {gates.map((g) => (
          <span className={`gate-chip ${g.passed ? 'pass' : 'fail'}`} key={g.gate} title={g.detail}>
            <span className="d" /> {g.gate.replace(/_/g, ' ')}
          </span>
        ))}
      </div>
      <div className="trade-grid">
        <div className="trade-field">
          <div className="l">Entry</div>
          <input type="number" step="0.01" value={entry} onChange={(e) => setEntry(Number(e.target.value))} />
        </div>
        <div className="trade-field">
          <div className="l">Stop-Loss</div>
          <input type="number" step="0.01" value={stop} onChange={(e) => setStop(Number(e.target.value))} />
        </div>
        <div className="trade-field">
          <div className="l">Target</div>
          <input type="number" step="0.01" value={target} onChange={(e) => setTarget(Number(e.target.value))} />
        </div>
        <div className="trade-field">
          <div className="l">Risk : Reward</div>
          <div className={`static ${rrr >= 2 ? 'gain' : rrr > 0 ? '' : 'loss'}`}>
            {risk > 0 ? `1 : ${rrr.toFixed(2)}` : '—'}
          </div>
        </div>
      </div>
      <button className="action-btn buy" disabled={submitting || !entry || !stop || !target} onClick={submit}>
        {submitting ? 'Opening…' : `Buy — Track 1 Share @ ${currency}${entry.toFixed(2)}`}
      </button>
      {err && <div className="trade-err-banner">{err}</div>}
      {levels && (
        <p className="footnote">
          Suggested from 2.5×ATR stop / 6×ATR target (ATR {currency}
          {fmt(num(profile.raw.atr_value))}) — edit any field before opening. Every field above is editable; the
          checklist gates are shown for context, not enforced — this is your forward-test tracker, you decide.
        </p>
      )}
    </div>
  )
}

function PositionCard({
  profile,
  currency,
  userId,
}: {
  profile: ProfileResponse
  currency: string
  userId: number | null
}) {
  const navigate = useNavigate()
  const pos = profile.active_position as ActivePosition
  const livePrice = profile.quote.price ?? pos.current_price ?? pos.entry_price
  const liveUpnl = (livePrice - pos.entry_price) * pos.quantity
  const [exitPrice, setExitPrice] = useState(livePrice)
  const [exitStatus, setExitStatus] = useState('MANUAL EXIT')
  const [submitting, setSubmitting] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [closed, setClosed] = useState<{ pnl: number } | null>(null)

  async function submit() {
    setSubmitting(true)
    setErr(null)
    try {
      const res = await postCloseTrade({
        position_id: pos.position_id,
        exit_price: exitPrice,
        exit_status: exitStatus,
        user_id: userId ?? undefined,
      })
      // Same reasoning as BuyForm: no onDone() here, or the success banner
      // gets replaced mid-flight by the parent's full-page refetch/loading
      // state before it's readable.
      setClosed({ pnl: res.final_pnl })
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : 'Could not close trade.')
    } finally {
      setSubmitting(false)
    }
  }

  if (closed) {
    return (
      <div className="card trade-card">
        <div className={`trade-success-banner ${closed.pnl < 0 ? 'loss' : ''}`}>
          <div className="trade-success-icon">✓</div>
          <div className="trade-success-body">
            <div className="trade-success-title">Position closed — {profile.ticker}</div>
            <div className="trade-success-detail">
              Final P&amp;L {closed.pnl >= 0 ? '+' : ''}
              {currency}
              {closed.pnl.toFixed(2)}
            </div>
          </div>
          <button className="trade-success-cta" onClick={() => navigate('/forward-test')}>
            View in Forward-Test →
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="card trade-card">
      <div className="trade-head">
        <h3>You're in this trade</h3>
        <span className="position-badge">{pos.trail_phase ?? 'initial'} stop</span>
      </div>
      <div className="trade-grid">
        <div className="trade-field">
          <div className="l">Entry</div>
          <div className="static">
            {currency}
            {pos.entry_price.toFixed(2)}
          </div>
        </div>
        <div className="trade-field">
          <div className="l">Mark</div>
          <div className="static">
            {currency}
            {livePrice.toFixed(2)}
          </div>
        </div>
        <div className="trade-field">
          <div className="l">Stop</div>
          <div className="static loss">
            {currency}
            {pos.stop_loss.toFixed(2)}
          </div>
        </div>
        <div className="trade-field">
          <div className="l">Target</div>
          <div className="static gain">
            {currency}
            {pos.target.toFixed(2)}
          </div>
        </div>
        <div className="trade-field">
          <div className="l">Unrealized P&amp;L</div>
          <div className={`static ${liveUpnl >= 0 ? 'gain' : 'loss'}`}>
            {liveUpnl >= 0 ? '+' : ''}
            {currency}
            {liveUpnl.toFixed(2)}
          </div>
        </div>
      </div>
      <div className="trade-grid">
        <div className="trade-field">
          <div className="l">Exit Price</div>
          <input type="number" step="0.01" value={exitPrice} onChange={(e) => setExitPrice(Number(e.target.value))} />
        </div>
        <div className="trade-field">
          <div className="l">Exit Reason</div>
          <select className="exit-select" value={exitStatus} onChange={(e) => setExitStatus(e.target.value)}>
            <option value="MANUAL EXIT">Manual Exit</option>
            <option value="SUCCESSFUL TRADE">Successful Trade</option>
            <option value="BAD TRADE">Bad Trade</option>
          </select>
        </div>
      </div>
      <button className="action-btn sell" disabled={submitting} onClick={submit}>
        {submitting ? 'Closing…' : 'Close Position'}
      </button>
      {err && <div className="trade-err-banner">{err}</div>}
    </div>
  )
}

function PriceChart({ data, currency }: { data: PricePoint[]; currency: string }) {
  const clean = data.filter((d) => d.close != null)
  if (clean.length < 2) return null
  return (
    <div className="card chart-card">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={clean} margin={{ top: 10, right: 14, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="rgba(120,140,190,0.14)" strokeDasharray="3 3" vertical={false} />
          <XAxis
            dataKey="date"
            tick={{ fontSize: 10, fill: '#5c6584' }}
            minTickGap={50}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            domain={['auto', 'auto']}
            tick={{ fontSize: 10, fill: '#5c6584' }}
            axisLine={false}
            tickLine={false}
            width={56}
            tickFormatter={(v: number) => `${currency}${Math.round(v)}`}
          />
          <Tooltip
            contentStyle={{ background: '#0d1220', border: '1px solid rgba(120,140,190,0.26)', borderRadius: 10, fontSize: 12 }}
            labelStyle={{ color: '#9aa3bc' }}
            formatter={(v, name) => [typeof v === 'number' ? `${currency}${v.toFixed(2)}` : String(v), String(name)]}
          />
          <Line type="monotone" dataKey="close" stroke="#e4b75c" strokeWidth={2} dot={false} name="Close" />
          <Line type="monotone" dataKey="sma_50" stroke="#7fb3e8" strokeWidth={1.3} dot={false} name="SMA 50" />
          <Line type="monotone" dataKey="sma_200" stroke="#e8827a" strokeWidth={1.3} dot={false} name="SMA 200" />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

function FundamentalsPanel({ profile, currency, market }: { profile: ProfileResponse; currency: string; market: 'in' | 'us' }) {
  const raw = profile.raw
  const pe = num(raw.pe_ratio)
  const pb = num(raw.pb_ratio)
  const roe = num(raw.roe)
  const roic = num(raw.roic)
  const peg = num(raw.peg_ratio)
  const debtMetric = market === 'us' ? num(raw.debt_to_equity) : num(raw.net_debt_ebitda)
  const debtLabel = market === 'us' ? 'Debt / Equity' : 'Net Debt / EBITDA'
  const intCov = num(raw.interest_coverage)
  const growth = num(raw.yoy_profit_growth)
  const promoterHold = num(raw.promoter_holding_pct)
  const promoterPledge = num(raw.promoter_pledge_pct)
  const eps = num(raw.eps) ?? num(raw.xbrl_eps_basic)
  const relVol = num(raw.relative_volume)
  const deliveryPct = num(raw.delivery_pct_10d)

  const items: { l: string; v: string; cls?: string }[] = [
    { l: 'P/E', v: pe != null ? pe.toFixed(1) : '—' },
    { l: 'P/B', v: pb != null ? pb.toFixed(2) : '—' },
    { l: 'ROE', v: roe != null ? `${roe.toFixed(1)}%` : '—' },
    ...(market === 'in' ? [{ l: 'ROIC', v: roic != null ? `${roic.toFixed(1)}%` : '—' }] : []),
    { l: 'PEG Ratio', v: peg != null ? peg.toFixed(2) : '—' },
    { l: debtLabel, v: debtMetric != null ? `${debtMetric.toFixed(2)}x` : '—' },
    { l: 'Interest Coverage', v: intCov != null ? `${intCov.toFixed(1)}x` : '—' },
    {
      l: 'YoY Profit Growth',
      v: growth != null ? `${growth >= 0 ? '+' : ''}${growth.toFixed(1)}%` : '—',
      cls: growth != null ? (growth >= 0 ? 'gain' : 'loss') : undefined,
    },
    { l: 'EPS (TTM)', v: eps != null ? `${currency}${eps.toFixed(2)}` : '—' },
    ...(market === 'in'
      ? [{ l: 'Promoter Holding', v: promoterHold != null ? `${promoterHold.toFixed(1)}%` : '—' }]
      : []),
    ...(market === 'in'
      ? [
          {
            l: 'Promoter Pledge',
            v: promoterPledge != null ? `${promoterPledge.toFixed(1)}%` : '—',
            cls: promoterPledge != null && promoterPledge > 0 ? 'loss' : undefined,
          },
        ]
      : []),
    market === 'in'
      ? { l: 'Delivery % (10D)', v: deliveryPct != null ? `${deliveryPct.toFixed(1)}%` : '—' }
      : { l: 'Relative Volume', v: relVol != null ? `${relVol.toFixed(2)}×` : '—' },
  ]

  return (
    <div className="card fund-grid">
      {items.map((item) => (
        <div className="fund-item" key={item.l}>
          <div className="l">{item.l}</div>
          <div className={`v ${item.cls ?? ''}`}>{item.v}</div>
        </div>
      ))}
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

  async function runSearch(sym: string, mkt: 'in' | 'us' = market) {
    if (!sym.trim()) return
    setLoading(true)
    setError(null)
    setParams({ market: mkt, ticker: sym.toUpperCase() })
    try {
      const res = await getProfile(sym, true, userId ?? undefined, mkt.toUpperCase() as 'IN' | 'US')
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

  // Auto-run once for a ticker/market landed on via URL (e.g. a Screener row
  // click) — a real effect, not a render-time navigate() call, which React
  // Router warns about (setParams() inside runSearch calls navigate()).
  useEffect(() => {
    const t = params.get('ticker')
    if (t) runSearch(t, market)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function switchMarket(m: 'in' | 'us') {
    setMarket(m)
    setProfile(null)
    setError(null)
    const next = m === 'in' ? 'RELIANCE' : 'AAPL'
    setTicker(next)
    runSearch(next, m)
  }

  const currency = market === 'us' ? '$' : '₹'
  const raw = profile?.raw ?? {}
  const sources = (raw.fundamentals_sources as string[] | undefined) ?? []
  const xbrlRevenue = num(raw.xbrl_revenue)
  const xbrlProfit = num(raw.xbrl_profit_after_tax)
  const xbrlEps = num(raw.xbrl_eps_basic)
  const hasXbrl = market === 'in' && (xbrlRevenue !== null || xbrlProfit !== null || xbrlEps !== null)

  return (
    <>
      <div className="hero">
        <div className="eyebrow">Single-Stock Deep Dive</div>
        <h1>Why does this stock score what it scores?</h1>
        <p className="hero-sub">
          Live price, suggested trade levels, every checklist line and the marks it earned — so a score, and a buy,
          are never a black box.
        </p>
        <form className="searchbox" onSubmit={handleSubmit}>
          <input
            type="text"
            className="mono"
            value={ticker}
            onChange={(e) => setTicker(e.target.value.toUpperCase())}
            placeholder={market === 'in' ? 'e.g. RELIANCE' : 'e.g. AAPL'}
          />
          <button type="submit" disabled={loading}>
            {loading ? 'Fetching…' : 'Search'}
          </button>
        </form>
        <div className="segmented" style={{ marginTop: 16 }}>
          <button className={market === 'in' ? 'active' : ''} onClick={() => switchMarket('in')}>
            IN &middot; {market === 'in' ? ticker : 'RELIANCE'}
          </button>
          <button className={market === 'us' ? 'active' : ''} onClick={() => switchMarket('us')}>
            US &middot; {market === 'us' ? ticker : 'AAPL'}
          </button>
        </div>
      </div>

      {error && (
        <div className="section" style={{ marginTop: 32 }}>
          <span className="pill loss">{error}</span>
        </div>
      )}

      {loading && (
        <div className="section" style={{ marginTop: 32 }}>
          <p className="hero-sub">Fetching live {market === 'in' ? 'NSE' : 'US'} data for {ticker}…</p>
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
                    {profile.company_name} &middot; {profile.sector} &middot; {profile.industry} &middot; {currency}
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
                    {profile.active_position && <Pill kind="win">In position</Pill>}
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
                  <span className="k">Price</span> <span className="v">{market === 'in' ? 'Angel One / Yahoo' : 'Yahoo Finance'}</span>
                </div>
                {sources.map((s) => (
                  <div className="source-chip" key={s}>
                    <span className="k">Source</span> <span className="v">{s}</span>
                  </div>
                ))}
                {market === 'in' && hasXbrl && str(raw.xbrl_period_end) && (
                  <div className="source-chip">
                    <span className="k">XBRL filing</span> <span className="v">{str(raw.xbrl_period_end)}</span>
                  </div>
                )}
                {market === 'us' && (
                  <div className="source-chip">
                    <span className="k">Fundamentals</span> <span className="v">SEC EDGAR (TTM)</span>
                  </div>
                )}
              </div>
            </div>
          </div>

          <div className="section">
            <div className="section-head">
              <div className="section-title">Live Quote</div>
            </div>
            <QuoteHero profile={profile} currency={currency} />
          </div>

          <div className="section">
            <div className="section-head">
              <div className="section-title">{profile.active_position ? 'Position' : 'Trade'}</div>
            </div>
            {profile.active_position ? (
              <PositionCard
                key={profile.active_position.position_id}
                profile={profile}
                currency={currency}
                userId={userId}
              />
            ) : (
              <BuyForm key={profile.ticker} profile={profile} currency={currency} market={market} userId={userId} />
            )}
          </div>

          <div className="section">
            <div className="section-head">
              <div className="section-title">Price Chart — 1Y, 50/200 SMA</div>
            </div>
            <PriceChart data={profile.price_history} currency={currency} />
          </div>

          <div className="section">
            <div className="section-head">
              <div className="section-title">Fundamentals</div>
            </div>
            <FundamentalsPanel profile={profile} currency={currency} market={market} />
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
            <p className="footnote">
              Live from /api/profile/{profile.ticker}?market={market}&amp;live=true — every value above is what{' '}
              {market === 'in' ? 'factor_engine.py' : 'factor_engine_us.py'} actually computed for this row, just now.
            </p>
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
  )
}
