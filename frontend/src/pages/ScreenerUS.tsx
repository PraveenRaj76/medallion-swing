export function ScreenerUS() {
  return (
    <>
      <div className="hero">
        <div className="eyebrow">US Equities &middot; Quantamental Screener</div>
        <h1>Same checklist, official-filing data.</h1>
        <p className="hero-sub">
          Large, mid, and small-caps, ranked by self-computed market cap — fundamentals from SEC EDGAR's structured
          XBRL filings, not a scrape.
        </p>
      </div>

      <div className="section" style={{ marginTop: 32 }}>
        <div className="card not-built">
          <span className="pill neutral">Not built yet</span>
          <p>
            This page is real UI, but there is no US data pipeline behind it — no SEC EDGAR XBRL integration, no
            Alpaca market-cap ranking, no <code className="mono">/api/us/screener</code> endpoint. Building it means
            standing up an entirely separate fundamentals + price pipeline for US equities, not just wiring a new
            route. Rather than fill this page with more illustrative rows, it's left honestly empty until that work
            is actually done.
          </p>
        </div>
      </div>
    </>
  )
}
