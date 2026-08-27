/**
 * Beginner-facing explanations of the US checklist filters — mirrors
 * checklistExplainers.ts's approach but for factor_engine_us.py's actual
 * field set, which genuinely differs from India's: SEC EDGAR fundamentals
 * instead of Screener.in/NSE, Debt/Equity instead of Net Debt/EBITDA, no
 * promoter-pledge equivalent, Relative Volume instead of Delivery %, S&P
 * 500 as the benchmark instead of Nifty. Every threshold here is copied
 * from factor_engine_us.py, not paraphrased.
 */

import type { ExplainerItem } from './checklistExplainers'

export const US_FUNDAMENTAL_EXPLAINERS: ExplainerItem[] = [
  {
    name: 'ROE (Return on Equity)',
    maxMarks: 10,
    what: "Net income divided by shareholder equity — self-computed from the company's own real, trailing-twelve-month SEC filings (not a pre-built ratio), showing how much profit it generates per dollar shareholders have invested.",
    why: 'The single best gauge of whether a business is genuinely good, not just cheap. A high ROE means the company compounds shareholder capital efficiently.',
    scoring: '≥20% → 10/10 (excellent) · 12–20% → 7/10 (solid) · 8–12% → 4/10 (average) · below 8% → 1/10 (weak).',
  },
  {
    name: 'Debt / Equity',
    maxMarks: 8,
    what: 'Long-term debt divided by shareholder equity, both real figures from the same SEC filing. Skipped entirely for banks/insurers — leverage means something structurally different for a lender.',
    why: "Too much debt turns an ordinary bad quarter into a real crisis. This is the US equivalent of India's Net Debt/EBITDA check, using what's actually filed for US companies.",
    scoring: '≤0.3x → 8/8 · 0.3–0.8x → 5/8 · 0.8–1.5x → 2/8 · above 1.5x → 0/8.',
  },
  {
    name: 'PEG Ratio',
    maxMarks: 8,
    what: "P/E divided by trailing profit growth — \"am I paying a fair price for this much growth?\" instead of judging P/E alone.",
    why: 'A high P/E can still be a bargain if profit is growing fast enough; PEG folds growth into the valuation question.',
    scoring: '≤1.0 → 8/8 · 1.0–1.5 → 6/8 · 1.5–2.5 → 3/8 · above 2.5 → 0.5/8. Needs positive profit growth to count.',
  },
  {
    name: 'Interest Coverage',
    maxMarks: 6,
    what: "Operating income divided by interest expense, both real trailing-twelve-month SEC figures — how many times over the company could pay its annual interest bill. Skipped for financials, where it isn't a meaningful ratio the way most banks file it.",
    why: 'Low coverage is an early-warning sign — a company that can barely afford its interest payments has no cushion if profit dips.',
    scoring: '≥8x → 6/6 (strong) · 4–8x → 4/6 (adequate) · below 4x → 0/6 (weak).',
  },
  {
    name: 'Profit Growth (YoY)',
    maxMarks: 7,
    what: "Year-over-year growth in net income, computed from two genuine, non-overlapping annual 10-K filings — not a quarter compared against a different-length prior period.",
    why: "A cheap stock attached to a shrinking business is a value trap. Growth is what makes today's price matter for tomorrow's return.",
    scoring: '≥20% → 7/7 · 10–20% → 5/7 · 0–10% → 2/7 · negative → 0/7.',
  },
  {
    name: 'Stock P/E',
    maxMarks: 6,
    what: "Price divided by trailing-twelve-month EPS — EPS itself derived from real TTM net income (see the note below on why this needed a custom calculation), not a single quarter's figure mistaken for a full year.",
    why: 'The most basic sanity check on price: is this priced like a reasonable business, or priced for perfection? The pass/fail ceiling is lower for financials (18x) than other sectors (30x), matching how the market actually prices the two differently.',
    scoring: 'Within the sector-adjusted cap → 6/6 · up to the mid-point → 3/6 · beyond that → 0.5/6.',
  },
  {
    name: 'P/B Ratio',
    maxMarks: 4,
    what: 'Price divided by book value per share (shareholder equity ÷ shares outstanding), both real filed figures.',
    why: 'A steadier cheapness signal than P/E for asset-heavy or highly cyclical businesses where earnings swing hard year to year.',
    scoring: 'Cheap (≤60% of the sector cap) → full marks · within the cap → partial · rich → near-zero. Cap is 2.5x for financials, 6.0x otherwise.',
  },
]

export const US_TECHNICAL_EXPLAINERS: ExplainerItem[] = [
  {
    name: 'Price vs 200-Day SMA',
    maxMarks: 10,
    what: 'Is the current price above its 200-day (roughly 10-month) moving average?',
    why: 'The classic dividing line between a long-term uptrend and downtrend.',
    scoring: 'Above → 10/10 · within 2% (contested) → 5/10 · below → 0/10.',
  },
  {
    name: 'Price vs 50-Day SMA',
    maxMarks: 6,
    what: 'Is price above its 50-day (roughly 2.5-month) moving average?',
    why: "Confirms the stock isn't just in a long-term uptrend on paper, but has been genuinely strong recently too.",
    scoring: 'Above → 6/6 · below → 2/6 · unavailable → 3/6 (neutral).',
  },
  {
    name: 'SMA Stack (50 vs 200)',
    maxMarks: 6,
    what: 'Is the 50-day average itself trading above the 200-day average — a "golden cross" style alignment?',
    why: 'When the faster average leads the slower one, it signals building momentum, not just that price happens to sit above a line today.',
    scoring: '50 > 200 → 6/6 · 50 < 200 → 1/6 (bearish, "death cross" style) · incomplete → 2/6 (neutral).',
  },
  {
    name: 'RSI (14)',
    maxMarks: 10,
    what: 'Relative Strength Index over 14 days — a 0–100 gauge of how "hot" or "cold" recent buying and selling has been.',
    why: "The checklist's sweet spot (45–65) is a stock with real momentum that isn't stretched to the point of exhaustion.",
    scoring: '45–65 → 10/10 · 35–45 → 6/10 (cooling) · above 65 → 0/10 (overextended) · below 35 → 3/10 (oversold).',
  },
  {
    name: '3-Month Alpha vs S&P 500',
    maxMarks: 8,
    what: 'How much this stock has outperformed — or lagged — the S&P 500 over the last three months.',
    why: 'A stock beating the index shows real, stock-specific demand, not just a market-wide rally lifting almost everything.',
    scoring: '≥10% → 8/8 · 0–10% → 5/8 · -8% to 0% → 2/8 · below -8% → 0/8.',
  },
  {
    name: 'Relative Volume',
    maxMarks: 5,
    what: "Today's trading volume divided by its own trailing 20-day average — real, computed from the same Yahoo Finance OHLCV series used for price. There's no US equivalent of NSE's delivery-percentage disclosure, so this is the standard swing-trading substitute for \"is real participation showing up right now.\"",
    why: 'High relative volume suggests a genuine shift in interest — new buyers or sellers are actively engaging with the stock, not just quiet drift.',
    scoring: '≥1.5× → 5/5 (strong participation) · 0.8–1.5× → 3.5/5 (acceptable) · below 0.8× → 1/5 (weak).',
  },
  {
    name: 'ATR % of Price',
    maxMarks: 5,
    what: 'Average True Range as a percentage of price — roughly how much the stock typically moves on a normal day.',
    why: "Too quiet and a breakout may lack energy to follow through; too wild and a normal stop-loss gets chopped out by noise. This checklist wants a tradeable middle ground.",
    scoring: '1.0%–4.5% → 5/5 (tradeable) · below 1.0% → 2/5 (too quiet) · above 4.5% → 1.5/5 (too choppy).',
  },
  {
    name: '21-Day Momentum',
    maxMarks: 5,
    what: 'Price change over the last 21 trading sessions — roughly the last month, computed from the same real OHLCV series.',
    why: 'A faster, more responsive momentum check than the 3-month alpha figure — catches a stock accelerating or stalling sooner.',
    scoring: '≥5% → 5/5 · 0–5% → 3/5 · negative → 0.5/5.',
  },
]
