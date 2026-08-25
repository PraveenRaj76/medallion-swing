import { useEffect, useState } from 'react'
import { ApiError, getSectors } from '../api/client'
import type { SectorsResponse } from '../types'
import { Pill } from '../components/Pill'
import { SectorValuationTable } from '../components/SectorValuationTable'

export function ScreenerUS() {
  const [data, setData] = useState<SectorsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getSectors('US')
      .then(setData)
      .catch((err) => setError(err instanceof ApiError ? err.message : 'Could not load sector rankings.'))
      .finally(() => setLoading(false))
  }, [])

  const rows = data?.rankings ?? []
  const cheapest = rows[0]

  return (
    <>
      <div className="hero">
        <div className="eyebrow">US Equities &middot; Quantamental Screener</div>
        <h1>Same checklist, official-filing data.</h1>
        <p className="hero-sub">
          The per-stock leaderboard below needs a SEC EDGAR + Alpaca pipeline that doesn't exist yet. Sector-level
          valuation and momentum, though, is real today — the 11 SPDR sector ETFs publish live P/E, P/B and dividend
          yield, no EDGAR required.
        </p>
      </div>

      {loading && (
        <div className="section" style={{ marginTop: 32 }}>
          <p className="hero-sub">Loading sector data…</p>
        </div>
      )}
      {error && (
        <div className="section" style={{ marginTop: 32 }}>
          <span className="pill loss">{error}</span>
        </div>
      )}

      {!loading && !error && rows.length > 0 && cheapest && (
        <>
          <div className="section" style={{ marginTop: 8 }}>
            <div className="card" style={{ padding: '26px 28px' }}>
              <div className="eyebrow" style={{ marginBottom: 10 }}>
                Most Undervalued US Sector Right Now
              </div>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 16, flexWrap: 'wrap' }}>
                <div className="dd-ticker" style={{ fontSize: 26 }}>
                  {cheapest.sector}
                </div>
                <div className="mono" style={{ fontSize: 32, fontWeight: 700, color: 'var(--gain)' }}>
                  {cheapest.etf_pe ?? '—'}
                  <span style={{ fontSize: 15, color: 'var(--text-faint)' }}> P/E</span>
                </div>
                {cheapest.quadrant && (
                  <Pill kind={cheapest.quadrant === 'Leading' ? 'win' : cheapest.quadrant === 'Lagging' ? 'loss' : 'info'}>
                    {cheapest.quadrant}
                  </Pill>
                )}
              </div>
              <p className="hero-sub" style={{ marginTop: 10, maxWidth: 640 }}>
                Cheapest P/E of the {cheapest.etf_pe_rank_of} S&amp;P sectors ranked (via {cheapest.etf_ticker}), real
                and live from Yahoo Finance.
                {cheapest.rel_strength_pct != null &&
                  ` 3-month relative strength vs S&P 500: ${cheapest.rel_strength_pct >= 0 ? '+' : ''}${cheapest.rel_strength_pct}%.`}
              </p>
            </div>
          </div>

          <div className="section">
            <div className="section-head">
              <div className="section-title">
                Undervalued Sectors — Cheapest First <span className="count">by real ETF P/E, live</span>
              </div>
            </div>
            <div className="card">
              <SectorValuationTable rows={rows} hasStockData={false} />
            </div>
            <p className="footnote">{data?.note}</p>
          </div>
        </>
      )}

      <div className="section">
        <div className="section-head">
          <div className="section-title">Per-Stock Leaderboard</div>
        </div>
        <div className="card not-built">
          <span className="pill neutral">Not built yet</span>
          <p>
            No SEC EDGAR XBRL integration or Alpaca market-cap ranking exists, so there's no real per-stock table to
            show here — that's a separate, larger backend build from the sector-level view above. Rather than fill
            this with more illustrative rows, it's left honestly empty until that work is actually done.
          </p>
        </div>
      </div>
    </>
  )
}
