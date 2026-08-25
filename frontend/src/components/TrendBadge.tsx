/**
 * Replaces the mockup's illustrative 30D sparkline (fabricated OHLC shape —
 * no historical price series is available from the current API, only point
 * values). Shows a real, honestly-derived trend read instead: price vs
 * 200-SMA (primary trend) and 3M alpha vs Nifty, both real fields already
 * on the row.
 */
export function TrendBadge({
  closePrice,
  sma200,
  alpha3m,
}: {
  closePrice: number | null
  sma200: number | null
  alpha3m: number | null
}) {
  if (closePrice == null || sma200 == null) {
    return <span style={{ color: 'var(--text-faint)', fontSize: 12 }}>—</span>
  }
  const above = closePrice > sma200
  const distPct = ((closePrice / sma200 - 1) * 100).toFixed(1)
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 2, fontSize: 11 }}>
      <span className="mono" style={{ color: above ? 'var(--gain)' : 'var(--loss)' }}>
        {above ? '▲' : '▼'} {distPct}% vs 200SMA
      </span>
      {alpha3m != null && (
        <span className="mono" style={{ color: 'var(--text-faint)' }}>
          {alpha3m >= 0 ? '+' : ''}
          {alpha3m.toFixed(1)}% 3M alpha
        </span>
      )}
    </div>
  )
}
