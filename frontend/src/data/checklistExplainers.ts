/**
 * Beginner-facing explanations of every checklist filter — what it is, why
 * it matters, and how the marks are actually awarded. Every threshold and
 * weight here is copied from the real scoring logic (factor_engine.py's
 * evaluate_fundamental_checklist / evaluate_technical_checklist), not
 * paraphrased from memory — if the code changes, this file needs to move
 * with it.
 */

export interface ExplainerItem {
  name: string
  maxMarks: number
  what: string
  why: string
  scoring: string
}

export const FUNDAMENTAL_EXPLAINERS: ExplainerItem[] = [
  {
    name: 'ROCE / ROIC (or ROE for banks)',
    maxMarks: 10,
    what: 'Return on Capital Employed — how much profit a company squeezes out of every rupee it has invested in the business. Banks/NBFCs use Return on Equity instead, since "capital employed" doesn\'t mean the same thing for a lender.',
    why: 'This is the single best gauge of whether a business is genuinely good, not just cheap. A company that turns ₹100 of capital into ₹20 of profit every year is compounding value; one that turns it into ₹5 is treading water.',
    scoring: '≥20% → 10/10 (excellent) · 12–20% → 7/10 (solid) · 8–12% → 4/10 (average) · below 8% → 1/10 (weak, below cost of capital).',
  },
  {
    name: 'Net Debt / EBITDA',
    maxMarks: 8,
    what: "How many years of the company's core operating earnings it would take to pay off all its net debt. Skipped entirely for banks — leverage means something different for a lender.",
    why: "Debt itself isn't bad, but too much of it turns a normal bad quarter into a real crisis — lenders can force asset sales or dilution exactly when the stock is already down.",
    scoring: '≤1.0x → 8/8 · 1.0–2.0x → 5/8 · 2.0–3.5x → 2/8 · above 3.5x → 0/8. Shown as N/A (0/0, doesn\'t block the name) when this isn\'t published free for the stock.',
  },
  {
    name: 'PEG Ratio',
    maxMarks: 8,
    what: "P/E divided by the company's profit growth rate — a way of asking \"am I paying a fair price for this much growth?\" instead of judging P/E in isolation.",
    why: 'A stock on a P/E of 40 can still be a bargain if profit is growing 40% a year, and a stock on a P/E of 12 can be expensive if profit is shrinking. PEG folds growth into the valuation question.',
    scoring: '≤1.0 → 8/8 (growth attractively priced) · 1.0–1.5 → 6/8 · 1.5–2.5 → 3/8 (premium) · above 2.5 → 0.5/8 (expensive). Needs positive profit growth to count at all.',
  },
  {
    name: 'Interest Coverage',
    maxMarks: 6,
    what: "How many times over the company's operating profit could pay its annual interest bill. Self-computed from NSE's own quarterly XBRL filing, not a scraped estimate. Skipped for banks, where it isn't a meaningful ratio.",
    why: "Low coverage is an early-warning sign — a company that can barely afford its interest payments today has no cushion if profit dips or rates rise.",
    scoring: '≥8x → 6/6 (strong) · 4–8x → 4/6 (adequate) · below 4x → 0/6 (weak). Shown as N/A when the latest filing didn\'t report finance costs.',
  },
  {
    name: 'Promoter Pledge',
    maxMarks: 5,
    what: "What percentage of the founders'/promoters' own shareholding is pledged as collateral against a loan — sourced from NSE's own regulatory SAST disclosure.",
    why: 'Heavy pledging is one of the more reliable red flags in Indian markets — if the stock falls far enough, the lender can force-sell the pledged shares, which pushes the price down further in a vicious cycle.',
    scoring: '≤5% → 5/5 (low/no pledging) · 5–15% → 2.5/5 (moderate) · above 15% → 0/5 (high — red flag).',
  },
  {
    name: 'Profit Growth',
    maxMarks: 7,
    what: "Year-over-year growth in the company's net profit.",
    why: "A cheap stock attached to a shrinking business is a value trap, not a bargain. Growth is what makes today's valuation matter for tomorrow's return.",
    scoring: '≥20% → 7/7 (strong) · 10–20% → 5/7 (healthy double-digit) · 0–10% → 2/7 (low/flat) · negative → 0/7.',
  },
  {
    name: 'Stock P/E',
    maxMarks: 6,
    what: 'Price-to-Earnings — how many years of the current profit it would take to "earn back" what you paid for the stock. The pass/fail ceiling adjusts by sector (cyclicals get more room, since their earnings swing harder year to year).',
    why: "The most basic sanity check on price: is this stock priced like a reasonable business, or priced for perfection?",
    scoring: 'Within the sector-adjusted cap (25–35x depending on the pack) → 6/6 · up to the sector-adjusted mid-point (40–50x) → 3/6 · beyond that → 0.5/6.',
  },
  {
    name: 'P/B Ratio',
    maxMarks: 4,
    what: "Price-to-Book — the stock price relative to the company's net accounting assets per share. This is the PRIMARY valuation lens for banks (8 marks there, not 4) since book value is real, mark-to-market-ish capital for a lender.",
    why: "Earnings can swing wildly for cyclical or asset-heavy businesses year to year; book value is steadier, so it's a useful second cheapness check P/E alone can miss.",
    scoring: 'Cheap (≤60% of the sector cap) → full marks · within the cap → partial · rich → near-zero. The exact cap varies by sector pack (financials 2.5x, cyclicals 3.0x, others 5.0x).',
  },
  {
    name: 'PE vs Sector Peers',
    maxMarks: 4,
    what: "Where this stock's P/E ranks (0–100th percentile) against OTHER stocks in the same sector, in the live universe, right now.",
    why: 'The honest substitute for "is this cheap vs its own 10-year history" — getting a decade of quarterly P/E for free at 200-stock scale isn\'t realistic, so this compares against real peers instead. Only appears once enough peer data exists.',
    scoring: '≤25th percentile → 4/4 (cheaper than most peers) · 25th–60th → 2/4 (mid-pack) · above 60th → 0/4 (pricier than most peers).',
  },
]

export const TECHNICAL_EXPLAINERS: ExplainerItem[] = [
  {
    name: 'Price vs 200-Day SMA',
    maxMarks: 10,
    what: 'Is the current price above its 200-day (roughly 10-month) moving average?',
    why: 'The 200-day line is the classic dividing line between a long-term uptrend and downtrend — trading above it is the single most-used definition of "this stock is not broken."',
    scoring: 'Above → 10/10 · within 2% (contested) → 5/10 · below → 0/10.',
  },
  {
    name: 'Price vs 50-Day SMA',
    maxMarks: 6,
    what: 'Is price above its 50-day (roughly 2.5-month) moving average?',
    why: "A shorter-term trend check — confirms the stock isn't just in a long-term uptrend on paper, but has been genuinely strong recently too.",
    scoring: 'Above → 6/6 · below → 2/6 · unavailable → 3/6 (neutral).',
  },
  {
    name: 'SMA Stack (50 vs 200)',
    maxMarks: 6,
    what: 'Is the 50-day average itself trading above the 200-day average — a "golden cross" style alignment?',
    why: "When the faster average leads the slower one, it signals momentum is building, not just that price happens to be above a line today.",
    scoring: '50 > 200 → 6/6 (bullish stack) · 50 < 200 → 1/6 ("death cross" style, bearish) · incomplete data → 2/6 (neutral).',
  },
  {
    name: 'RSI (14)',
    maxMarks: 10,
    what: 'Relative Strength Index over 14 days — a 0–100 gauge of how "hot" or "cold" recent buying and selling pressure has been.',
    why: "Extremely overbought conditions often precede a pullback; the checklist's sweet spot (45–65) is a stock with real momentum that isn't stretched to the point of exhaustion.",
    scoring: '45–65 → 10/10 (healthy zone) · 35–45 → 6/10 (cooling, constructive) · above 65 → 0/10 (overextended, entry locked) · below 35 → 3/10 (oversold, wait for reclaim).',
  },
  {
    name: '3-Month Alpha vs Nifty',
    maxMarks: 8,
    what: 'How much this stock has outperformed — or lagged — the Nifty benchmark over the last three months.',
    why: "A stock beating the index shows real, stock-specific demand — capital is choosing this name, not just riding a market-wide rally that would lift almost anything.",
    scoring: '≥10% → 8/8 (strong) · 0–10% → 5/8 (mild outperform) · -8% to 0% → 2/8 (mild underperform) · below -8% → 0/8 (severe weakness).',
  },
  {
    name: '52-Week Range Position',
    maxMarks: 6,
    what: "Where the current price sits between its own 52-week low and high — specifically, is it at least 30% above the low AND within 25% of the high. Borrowed directly from Mark Minervini's Trend Template (conditions 6-7 of 8).",
    why: "A stock can be above its 200/50-day averages and still be limping along near its yearly low — moving averages alone don't catch that. A name still hugging its 52-week low isn't a confirmed uptrend no matter what the shorter averages say.",
    scoring: 'Both conditions met → 6/6 (stage-2 position) · one of the two → 3/6 (partial) · neither → 0/6 (too close to its low). Shown as N/A when 52-week high/low isn\'t available for this row yet.',
  },
  {
    name: 'Delivery %',
    maxMarks: 5,
    what: "What share of the day's traded volume was actually delivered (taken into demat) rather than squared off intraday — real data from NSE's own daily bhavcopy archive, not a proxy or estimate.",
    why: "High delivery suggests real investors are accumulating for the medium term; low delivery can mean the volume is mostly speculative day-trading churn with less conviction behind it.",
    scoring: '≥50% → 5/5 (strong conviction) · 40–50% → 3.5/5 (acceptable) · below 40% → 1/5 (weak). Skipped (doesn\'t block the name) when NSE genuinely has no delivery data for that ticker in the scan window.',
  },
  {
    name: 'ATR % of Price',
    maxMarks: 5,
    what: "Average True Range as a percentage of price — roughly how much the stock typically moves, up or down, on a normal day.",
    why: "Too quiet and a breakout may lack the energy to follow through; too wild and a normal stop-loss gets chopped out by noise before the real move even starts. This checklist wants a tradeable middle ground.",
    scoring: '1.0%–4.5% → 5/5 (tradeable swing band) · below 1.0% → 2/5 (too quiet) · above 4.5% → 1.5/5 (too choppy).',
  },
  {
    name: '21-Day Momentum',
    maxMarks: 5,
    what: "Price change over the last 21 trading sessions — roughly the last month.",
    why: "A faster, more responsive momentum check than the 3-month alpha figure — catches a stock that's recently accelerating (or stalling) before the longer window would show it.",
    scoring: '≥5% → 5/5 (positive) · 0–5% → 3/5 (flat-to-up) · negative → 0.5/5. Shows a neutral 2/5 when there isn\'t enough price history yet to compute it.',
  },
]

export const SECTOR_EXPLAINERS: ExplainerItem[] = [
  {
    name: 'ETF P/E',
    maxMarks: 0,
    what: "The trailing Price-to-Earnings ratio of that sector's own real, tradeable tracking ETF (e.g. BANKBEES for Financials, XLK for US Technology) — pulled live from Yahoo Finance, the same way every stock price in this app is sourced.",
    why: 'This is what actually ranks sectors "cheapest to priciest" on this page — a real, live number, not an estimate, and never compared across the India/US markets since currency and accounting differences make that comparison meaningless.',
    scoring: 'No pass/fail marks — sectors are simply ranked from lowest P/E (cheapest, shown first) to highest (most expensive, shown last), within one market at a time.',
  },
  {
    name: 'ETF P/B & Dividend Yield',
    maxMarks: 0,
    what: "The same tracking ETF's price-to-book ratio and trailing dividend yield, shown alongside P/E — real figures where the ETF publishes them, left blank (never guessed) where it doesn't.",
    why: 'A second and third independent read on "is this sector cheap right now" — P/E alone can be distorted by one-off earnings swings across a whole sector; book value and yield are steadier cross-checks.',
    scoring: 'Informational — no marks. Some India sector ETFs simply don\'t publish P/B or yield data; shown as "—" rather than a guessed number.',
  },
  {
    name: 'Momentum (RRG-style)',
    maxMarks: 0,
    what: 'Two real, price-derived numbers: Relative Strength (has this sector beaten the market benchmark over the last 3 months) and Relative Momentum (is that lead growing or shrinking over the last month) — classified into four zones borrowed from the Relative Rotation Graph technique used by professional sector-rotation desks.',
    why: 'A cheap sector can stay cheap for years with nothing happening — combining valuation with real price momentum shows whether money is actually starting to rotate into it right now, not just that it looks statistically cheap on paper.',
    scoring: 'Leading = ahead of the market and still accelerating (strongest). Improving = behind the market but catching up (early rotation candidate). Weakening = ahead of the market but losing steam. Lagging = behind and falling further behind (avoid).',
  },
  {
    name: 'Constituents / Buyable % / Median Composite',
    maxMarks: 0,
    what: 'How many stocks from this sector are in the live tracked universe, what fraction currently pass the technical "buyable" bar, and their median checklist composite score — the same real, individually-scored data used on the Leaderboard.',
    why: "Confirms the sector-level ETF story is backed by real, individually-scoring stocks underneath it, not just one ticker's valuation in isolation. Shown as \"—\" for sectors with no matching stock in the current universe yet, rather than fabricated.",
    scoring: 'Informational — no marks.',
  },
]
