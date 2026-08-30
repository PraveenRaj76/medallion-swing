"""
Sector-level valuation and momentum, sourced from real sector ETFs — not
per-stock aggregation (that's sector_engine.py's job for India) and not a
scrape of a blocked index-history page. This is the piece neither had: a
genuine relative-strength/momentum read, and a real valuation source for
US sectors, without needing a SEC EDGAR pipeline.

VALIDATED LIVE (2026-08-25): every ticker below returns a real trailingPE
(or, for a few India ETFs, a real price history with PE genuinely absent
from that ETF's Yahoo listing — left None, not guessed) and real OHLCV
history through the same yfinance path already used elsewhere in this
codebase for stock prices.

Methodology, synthesized from a deep-research pass across how established
free/paid tools actually do this (not invented from scratch):
  - Finviz group screener: sector PE is only meaningful compared within a
    peer group, never across sectors (capital-intensive vs asset-light
    trade at structurally different multiples).
  - Morningstar Price/Fair-Value: aggregate a sector's valuation as a
    median across constituents, not a single blended number.
  - Yardeni Research: track a sector's PE over time and read today's level
    against its own history — mean reversion context, not a snapshot.
    (Handled by sector_engine.sector_pe_trend()/db.snapshot_sector_history
    already — not duplicated here.)
  - StockCharts / Julius de Kempenaer's Relative Rotation Graph (RRG)
    methodology: classify a sector by two real, independent axes —
    RS-Ratio (is it outperforming the benchmark right now) and
    RS-Momentum (is that outperformance accelerating or fading) — into
    four quadrants: Leading, Weakening, Lagging, Improving. The exact
    Kempenaer RS-Ratio involves a proprietary double-smoothing formula;
    what's implemented below is a simplified but honest proxy on the same
    two real axes (trailing relative return, and the change in that
    relative return), not a claim to replicate the licensed indicator.
  - Simply Wall St: one of several valuation checks compares a group's PE
    against the broader market's PE.
  - SPDR sector-ETF fact sheets / ETFdb: sector-level PE, P/B and dividend
    yield are themselves real, free, published numbers per sector ETF —
    confirmed live via yfinance for all 11 US Select Sector SPDRs and 8
    liquid India sector BeES/ETFs.
"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ticker -> (sector label, matches the GICS-equivalent labels sector_engine
# already normalizes stock rows onto, so the two can be merged by key)
US_SECTOR_ETFS: Dict[str, str] = {
    "XLK": "Information Technology",
    "XLF": "Financials",
    "XLV": "Health Care",
    "XLE": "Energy",
    "XLY": "Consumer Discretionary",
    "XLP": "Consumer Staples",
    "XLI": "Industrials",
    "XLB": "Materials",
    "XLRE": "Real Estate",
    "XLU": "Utilities",
    "XLC": "Communication Services",
}
US_BENCHMARK = "SPY"

IN_SECTOR_ETFS: Dict[str, str] = {
    "BANKBEES.NS": "Financials",
    "ITBEES.NS": "Information Technology",
    "PHARMABEES.NS": "Health Care",
    "PSUBNKBEES.NS": "PSU Banking",
    "AUTOBEES.NS": "Consumer Discretionary",
    "METALIETF.NS": "Materials",
    "FMCGIETF.NS": "Consumer Staples",
    "MOREALTY.NS": "Real Estate",
}
IN_BENCHMARK = "^NSEI"


def _fetch_info(symbol: str) -> Dict[str, Optional[float]]:
    """Real trailing PE / P/B / dividend yield straight from the ETF's own
    Yahoo listing — never invented when the field is genuinely absent."""
    try:
        import yfinance as yf

        info = yf.Ticker(symbol).info or {}
        return {
            "pe": info.get("trailingPE"),
            "pb": info.get("priceToBook"),
            "dividend_yield": info.get("dividendYield"),
        }
    except Exception as exc:
        logger.debug("sector ETF info fetch failed for %s: %s", symbol, exc)
        return {"pe": None, "pb": None, "dividend_yield": None}


def _fetch_closes(symbol: str):
    """Real 6-month daily close series straight from Yahoo — symbols here
    are already fully-qualified (".NS" for India ETFs, bare for US SPDRs),
    so this deliberately bypasses nse_data_provider.fetch_ohlcv, which
    appends ".NS" unconditionally and would silently 404 every US ticker."""
    try:
        import yfinance as yf

        hist = yf.Ticker(symbol).history(period="6mo", interval="1d")
        if hist is None or hist.empty:
            return None
        return hist["Close"].astype(float)
    except Exception as exc:
        logger.debug("sector ETF price fetch failed for %s: %s", symbol, exc)
        return None


def _pct_return(closes, lookback: int) -> Optional[float]:
    if closes is None or len(closes) <= lookback:
        return None
    try:
        start = float(closes.iloc[-lookback - 1])
        end = float(closes.iloc[-1])
        # A real gap day in the fetched price series (yfinance can return one
        # for a thinly-traded ETF) shows up as NaN here, not an exception —
        # float('nan') <= 0 is False, so the guard below silently let a NaN
        # through into the API response and crashed JSON serialization
        # (json.dumps correctly refuses NaN; found via a live /api/sectors
        # 500 while re-verifying this module after the backend/ restructure,
        # though the bug itself predates that move — this function's logic
        # was untouched by it). Treat NaN the same as any other unusable
        # input: None, not a fabricated 0.
        if math.isnan(start) or math.isnan(end) or start <= 0:
            return None
        return (end / start - 1.0) * 100.0
    except Exception:
        return None


def _relative_strength_and_momentum(
    etf_closes, bench_closes, trend_window: int = 63, momentum_window: int = 21
) -> Dict[str, Optional[float]]:
    """Real, price-derived proxy for RRG's RS-Ratio / RS-Momentum axes.

    rel_strength_pct: this ETF's return over `trend_window` trading days
    (~3 months) minus the benchmark's return over the same window — the
    same "alpha vs benchmark" convention already used for individual
    stocks elsewhere in this codebase (alpha_3m), just applied to a sector
    ETF instead of a stock.

    rel_momentum_pct: how much that relative strength has itself changed
    over the trailing `momentum_window` (~1 month) — is the outperformance
    accelerating (positive) or fading (negative). This is the real,
    computable analogue of RRG's momentum axis.
    """
    etf_ret = _pct_return(etf_closes, trend_window)
    bench_ret = _pct_return(bench_closes, trend_window)
    rel_strength = (etf_ret - bench_ret) if etf_ret is not None and bench_ret is not None else None

    rel_strength_prior = None
    if etf_closes is not None and bench_closes is not None and len(etf_closes) > trend_window + momentum_window:
        etf_ret_prior = _pct_return(etf_closes.iloc[:-momentum_window], trend_window)
        bench_ret_prior = _pct_return(bench_closes.iloc[:-momentum_window], trend_window)
        if etf_ret_prior is not None and bench_ret_prior is not None:
            rel_strength_prior = etf_ret_prior - bench_ret_prior

    rel_momentum = (rel_strength - rel_strength_prior) if rel_strength is not None and rel_strength_prior is not None else None

    quadrant = None
    if rel_strength is not None and rel_momentum is not None:
        if rel_strength >= 0 and rel_momentum >= 0:
            quadrant = "Leading"
        elif rel_strength >= 0 and rel_momentum < 0:
            quadrant = "Weakening"
        elif rel_strength < 0 and rel_momentum < 0:
            quadrant = "Lagging"
        else:
            quadrant = "Improving"

    return {
        "rel_strength_pct": round(rel_strength, 1) if rel_strength is not None else None,
        "rel_momentum_pct": round(rel_momentum, 1) if rel_momentum is not None else None,
        "quadrant": quadrant,
    }


def get_sector_valuation_momentum(market: str) -> List[Dict[str, Any]]:
    """Real sector-ETF valuation + RRG-style momentum for one market.

    Returns a list of {sector, etf_ticker, etf_pe, etf_pb,
    etf_dividend_yield, rel_strength_pct, rel_momentum_pct, quadrant} —
    every field is either a real fetched value or None; nothing here is
    ever fabricated or backfilled with a placeholder.
    """
    etf_map = US_SECTOR_ETFS if market.upper() == "US" else IN_SECTOR_ETFS
    benchmark = US_BENCHMARK if market.upper() == "US" else IN_BENCHMARK

    from concurrent.futures import ThreadPoolExecutor

    tickers = list(etf_map.keys())
    with ThreadPoolExecutor(max_workers=8) as pool:
        bench_future = pool.submit(_fetch_closes, benchmark)
        info_futures = {t: pool.submit(_fetch_info, t) for t in tickers}
        closes_futures = {t: pool.submit(_fetch_closes, t) for t in tickers}
        bench_closes = bench_future.result()
        infos = {t: f.result() for t, f in info_futures.items()}
        closes = {t: f.result() for t, f in closes_futures.items()}

    out: List[Dict[str, Any]] = []
    for ticker, sector in etf_map.items():
        info = infos[ticker]
        momentum = _relative_strength_and_momentum(closes[ticker], bench_closes)
        out.append(
            {
                "sector": sector,
                "etf_ticker": ticker,
                "etf_pe": round(info["pe"], 2) if info["pe"] else None,
                "etf_pb": round(info["pb"], 2) if info["pb"] else None,
                "etf_dividend_yield": round(info["dividend_yield"], 2) if info["dividend_yield"] else None,
                **momentum,
            }
        )
    return out
