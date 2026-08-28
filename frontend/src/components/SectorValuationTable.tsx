import type { SectorRow } from '../types'
import { Pill } from './Pill'

function quadrantPill(q: SectorRow['quadrant']) {
  if (!q) return <span style={{ color: 'var(--text-faint)' }}>—</span>
  if (q === 'Leading') return <Pill kind="win">Leading</Pill>
  if (q === 'Improving') return <Pill kind="info">Improving</Pill>
  if (q === 'Weakening') return <Pill kind="open">Weakening</Pill>
  return <Pill kind="loss">Lagging</Pill>
}

/**
 * Real sector-ETF valuation + RRG-style momentum, ranked cheapest-PE-first
 * within this market (see sector_valuation.py — SPDR sector ETFs for US,
 * Nifty sector BeES/ETFs for India, both via Yahoo Finance, live). Shows
 * stock-level breadth/quality columns only when this market actually has a
 * per-stock universe behind it — never fabricated for the ones that don't.
 */
export function SectorValuationTable({ rows, hasStockData }: { rows: SectorRow[]; hasStockData: boolean }) {
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Rank</th>
            <th>Sector</th>
            <th>ETF</th>
            <th className="num">ETF P/E</th>
            <th className="num">P/B</th>
            <th className="num">Div Yield</th>
            <th>Momentum (RRG)</th>
            {hasStockData && (
              <>
                <th className="num">Constituents</th>
                <th className="num">Buyable %</th>
                <th className="num">Median Composite</th>
              </>
            )}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.sector}>
              <td>
                {r.etf_pe_rank ? (
                  <Pill kind={r.etf_pe_rank <= 3 ? 'win' : 'neutral'}>
                    #{r.etf_pe_rank}/{r.etf_pe_rank_of}
                  </Pill>
                ) : (
                  <Pill kind="neutral">n/a</Pill>
                )}
              </td>
              <td className="ticker">
                {r.sector}
                {r.etf_only && hasStockData && <div className="company">ETF-level only — no stock in this bucket yet</div>}
                {!hasStockData && r.top_ticker && (
                  <div className="company">
                    Led by {r.top_ticker} at {r.top_ticker_score}
                  </div>
                )}
              </td>
              <td className="mono">{r.etf_ticker ?? '—'}</td>
              <td className="num">{r.etf_pe ?? '—'}</td>
              <td className="num">{r.etf_pb ?? '—'}</td>
              <td className="num">{r.etf_dividend_yield != null ? `${r.etf_dividend_yield.toFixed(2)}%` : '—'}</td>
              <td>
                {quadrantPill(r.quadrant)}
                {r.rel_strength_pct != null && (
                  <div className="company mono">
                    RS {r.rel_strength_pct >= 0 ? '+' : ''}
                    {r.rel_strength_pct}% · Δ{r.rel_momentum_pct != null ? (r.rel_momentum_pct >= 0 ? '+' : '') + r.rel_momentum_pct : '—'}%
                  </div>
                )}
              </td>
              {hasStockData && (
                <>
                  <td className="num">{r.constituent_count}</td>
                  <td className="num">{r.buyable_pct != null ? `${r.buyable_pct.toFixed(0)}%` : '—'}</td>
                  <td className="num">{r.median_composite_score?.toFixed(1) ?? '—'}</td>
                </>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
