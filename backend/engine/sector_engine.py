"""
Sector rotation / "Best Sector" ranking — Part 2 of the Decision Engine
Blueprint (2026-08-23).

Deliberately NOT built on scraped Nifty-sectoral-index PE data or a paid
feed — that data isn't reliably free/live (see the blueprint's honest gap
on this). Instead this aggregates the same per-stock rows the screener
already fetches and persists, grouped by `sector`. That keeps the sector
view self-consistent with the stock-level screener (same source, same
refresh cycle) and genuinely live instead of a static snapshot that goes
stale in a day.

What this can and can't honestly claim:
  - CAN say: how this sector's constituents are scoring and trading RIGHT
    NOW, relative to each other and to the rest of the current universe.
  - CANNOT say: whether the sector is cheap vs. its own 5/7/10-year PE
    history — that needs an external time series this pipeline doesn't
    have. Every ranking here is a within-universe snapshot, labelled as
    such, not a "vs. history" valuation call.
"""

from __future__ import annotations

import logging
import statistics
from typing import Any, Dict, List, Optional

import pandas as pd

from db import database_engine as db
from engine import sector_valuation

logger = logging.getLogger(__name__)

MIN_CONSTITUENTS_FOR_CONFIDENT_SCORE = 3

# Nifty-sectoral-index <-> US GICS crosswalk from the blueprint (2.1). Keyed
# by the `sector` string as Screener.in / the US provider actually label it
# on a row, since that's what's really grouped on below — not by the Nifty
# index name itself (no per-index feed exists to key against).
SECTOR_GICS_MAP: Dict[str, str] = {
    "Financial Services": "Financials",
    "Banking": "Financials",
    "Information Technology": "Information Technology",
    "Technology": "Information Technology",
    "Energy": "Energy",
    "Oil & Gas": "Energy",
    "Healthcare": "Health Care",
    "Pharmaceuticals": "Health Care",
    "Consumer Staples": "Consumer Staples",
    "FMCG": "Consumer Staples",
    "Consumer Discretionary": "Consumer Discretionary",
    "Automobile": "Consumer Discretionary",
    "Metals & Mining": "Materials",
    "Materials": "Materials",
    "Real Estate": "Real Estate",
    "Realty": "Real Estate",
    "Media": "Communication Services",
    "Communication Services": "Communication Services",
    "Industrials": "Industrials",
    "Utilities": "Utilities",
}


def _gics_for(sector: str) -> str:
    return SECTOR_GICS_MAP.get(sector, sector or "Unclassified")


def _median(values: List[float]) -> Optional[float]:
    clean = [v for v in values if v is not None]
    if not clean:
        return None
    return round(statistics.median(clean), 2)


def _why_to_buy(
    sector: str,
    n: int,
    buyable_n: int,
    median_composite: Optional[float],
    top_ticker: Optional[str],
    top_score: Optional[float],
) -> str:
    """Generated from the sector's actual current constituent stats — never
    a canned per-sector story. If the inputs are thin, the sentence says so."""
    if n < MIN_CONSTITUENTS_FOR_CONFIDENT_SCORE:
        return (
            f"Only {n} constituent{'s' if n != 1 else ''} in the current universe — "
            f"too small a sample to call sector-wide breadth. Read the stock(s) individually."
        )
    buyable_pct = round(buyable_n / n * 100) if n else 0
    parts = [f"{buyable_n} of {n} constituents ({buyable_pct}%) are currently buyable"]
    if median_composite is not None:
        parts.append(f"median composite score {median_composite}")
    if top_ticker:
        parts.append(f"led by {top_ticker}" + (f" at {top_score}" if top_score is not None else ""))
    return " — ".join(parts) + "."


def _valuation_read(median_pe: Optional[float], pe_vs_market_pct: Optional[float], median_peg: Optional[float]) -> str:
    """A real valuation signal computable TODAY with zero external history —
    relative to the rest of the current universe, not the sector's own past.
    That's a genuinely different (weaker) claim than "cheap vs. history," and
    the wording says so rather than implying more than the data supports."""
    if median_pe is None:
        return "No priced PE in this sample — can't read valuation."
    bits = []
    if pe_vs_market_pct is not None:
        if pe_vs_market_pct <= -15:
            bits.append(f"{abs(pe_vs_market_pct):.0f}% cheaper than the current universe median PE")
        elif pe_vs_market_pct >= 15:
            bits.append(f"{pe_vs_market_pct:.0f}% pricier than the current universe median PE")
        else:
            bits.append("roughly in line with the current universe median PE")
    if median_peg is not None:
        if median_peg <= 1.2:
            bits.append(f"PEG {median_peg} — growth not overpaid")
        elif median_peg <= 2.0:
            bits.append(f"PEG {median_peg} — fair growth pricing")
        else:
            bits.append(f"PEG {median_peg} — expensive vs. its own growth")
    if not bits:
        return f"PE {median_pe} — not enough data for a relative read yet."
    return ("; ".join(bits) + ". Snapshot only — not yet checked against this sector's own PE "
            "history (see sector_history once enough days have accumulated).")


def _etf_valuation_by_gics(market: str) -> Dict[str, Dict[str, Any]]:
    """Real sector-ETF valuation + RRG-style momentum (sector_valuation.py),
    ranked cheapest-to-priciest by ETF PE within this market only — never
    compared across markets, matching the Finviz/peer-group caution that
    PE is only meaningful within a comparable group. Keyed by the same
    GICS-equivalent label _gics_for() already normalizes stock rows onto,
    so it can be merged onto (or, for a market with no stock universe yet,
    stand in for) the per-sector rows below."""
    try:
        etf_rows = sector_valuation.get_sector_valuation_momentum(market)
    except Exception as exc:
        logger.warning("sector ETF valuation fetch failed (non-fatal): %s", exc)
        return {}

    priced = [r for r in etf_rows if r.get("etf_pe")]
    priced.sort(key=lambda r: r["etf_pe"])
    rank_by_ticker = {r["etf_ticker"]: i + 1 for i, r in enumerate(priced)}
    n_priced = len(priced)

    out: Dict[str, Dict[str, Any]] = {}
    for r in etf_rows:
        rank = rank_by_ticker.get(r["etf_ticker"])
        out[r["sector"]] = {
            **r,
            "etf_pe_rank": rank,
            "etf_pe_rank_of": n_priced if rank else None,
        }
    return out


def sector_pe_trend(market: str, sector: str, lookback_days: int = 30) -> Optional[Dict[str, Any]]:
    """The actual "vs. its own history" read — only returns once
    snapshot_sector_history() has been accumulating real data for a while.
    Returns None (not a fabricated number) when there isn't enough history
    yet; a UI should render that as "building history," not zero/blank."""
    hist = db.get_sector_pe_history(market, sector, limit_days=lookback_days + 5)
    if hist is None or len(hist) < 2:
        return None
    valid = hist.dropna(subset=["median_pe"])
    if len(valid) < 2:
        return None
    first = float(valid.iloc[0]["median_pe"])
    last = float(valid.iloc[-1]["median_pe"])
    if first <= 0:
        return None
    return {
        "days_tracked": len(valid),
        "first_date": str(valid.iloc[0]["as_of_date"]),
        "last_date": str(valid.iloc[-1]["as_of_date"]),
        "pe_change_pct": round((last - first) / first * 100, 1),
    }


def compute_sector_rankings(market: str = "IN") -> Dict[str, Any]:
    """Rank sectors within the current live universe for one market, plus
    real sector-ETF valuation/momentum (sector_valuation.py) merged in.

    Returns {"market", "as_of", "universe_size", "rankings": [...]}. Even
    when there's no per-stock universe for this market yet (US, until a
    full EDGAR-backed screener exists), `rankings` is not forced empty —
    the real ETF-level valuation/momentum rows still populate it, clearly
    marked as ETF-only (constituent_count 0) rather than stock aggregation.
    `note` explains what's missing without hiding real data behind it.
    """
    etf_by_gics = _etf_valuation_by_gics(market)

    frame = db.get_leaderboard(limit=2000)
    if frame is not None and not frame.empty:
        if "market" in frame.columns:
            frame = frame[frame["market"].fillna("IN").str.upper() == market.upper()]
        elif market.upper() != "IN":
            # Pre-migration rows have no market column at all — they're India-only.
            frame = frame.iloc[0:0]

    has_stock_universe = frame is not None and not frame.empty
    note = None
    if not has_stock_universe:
        note = (
            f"No {market.upper()} per-stock universe yet"
            + (" — the US screener needs a SEC EDGAR pipeline that hasn't been built (Phase 2, not a bug)."
               if market.upper() == "US" else " — run a refresh first.")
            + (" Sector rows below are real ETF-level valuation/momentum only — no per-stock"
               " breadth or quality score behind them yet." if etf_by_gics else "")
        )
        if not etf_by_gics:
            return {"market": market.upper(), "as_of": db.screener_as_of(), "universe_size": 0,
                    "rankings": [], "note": note}

    universe_size = len(frame) if has_stock_universe else 0
    rows: List[Dict[str, Any]] = []
    matched_gics: set = set()

    # Whole-universe median PE — the reference point for "cheap/pricey RIGHT
    # NOW relative to everything else," which is computable today with zero
    # external history. Different (weaker) claim than "vs. its own past."
    universe_median_pe = None
    if has_stock_universe:
        universe_pe = pd.to_numeric(frame.get("pe_ratio"), errors="coerce")
        universe_median_pe = _median([p for p in universe_pe.tolist() if p and p > 0])

    stock_groups = frame.groupby(frame["sector"].fillna("Unclassified")) if has_stock_universe else []
    for sector, grp in stock_groups:
        n = len(grp)
        buyable_n = int(grp["is_buyable"].fillna(0).astype(int).sum()) if "is_buyable" in grp else 0
        composite = pd.to_numeric(grp.get("composite_score"), errors="coerce").tolist()
        pe = pd.to_numeric(grp.get("pe_ratio"), errors="coerce").tolist()
        peg = pd.to_numeric(grp.get("peg_ratio"), errors="coerce").tolist()
        fundamental = pd.to_numeric(grp.get("fundamental_score"), errors="coerce").tolist()
        technical = pd.to_numeric(grp.get("technical_score"), errors="coerce").tolist()

        median_composite = _median(composite)
        median_pe = _median([p for p in pe if p and p > 0])
        median_peg = _median([p for p in peg if p and p > 0])
        median_fund = _median(fundamental)
        median_tech = _median(technical)
        buyable_ratio = (buyable_n / n) if n else 0.0

        pe_vs_market_pct = (
            round((median_pe - universe_median_pe) / universe_median_pe * 100, 1)
            if median_pe is not None and universe_median_pe else None
        )

        top_row = grp.loc[pd.to_numeric(grp["composite_score"], errors="coerce").idxmax()] if n and "composite_score" in grp else None
        top_ticker = str(top_row["ticker"]) if top_row is not None else None
        top_score = round(float(top_row["composite_score"]), 1) if top_row is not None and pd.notna(top_row.get("composite_score")) else None

        confident = n >= MIN_CONSTITUENTS_FOR_CONFIDENT_SCORE
        # Quality (median composite, within-universe) blended with breadth
        # (buyable ratio) — see module docstring for what this can't claim.
        sector_score = (
            round((median_composite or 0) * 0.7 + buyable_ratio * 100 * 0.3, 1)
            if confident else None
        )

        gics = _gics_for(str(sector))
        etf = etf_by_gics.get(gics)
        if etf:
            matched_gics.add(gics)

        rows.append({
            "sector": str(sector),
            "gics_equivalent": gics,
            "constituent_count": n,
            "buyable_count": buyable_n,
            "buyable_pct": round(buyable_ratio * 100, 1),
            "median_composite_score": median_composite,
            "median_fundamental_score": median_fund,
            "median_technical_score": median_tech,
            "median_pe": median_pe,
            "median_peg": median_peg,
            "pe_vs_universe_median_pct": pe_vs_market_pct,
            "sector_score": sector_score,
            "confident_sample": confident,
            "top_ticker": top_ticker,
            "top_ticker_score": top_score,
            "why": _why_to_buy(str(sector), n, buyable_n, median_composite, top_ticker, top_score),
            "valuation_read": _valuation_read(median_pe, pe_vs_market_pct, median_peg),
            "pe_vs_own_history": sector_pe_trend(market.upper(), str(sector)),
            "etf_ticker": etf.get("etf_ticker") if etf else None,
            "etf_pe": etf.get("etf_pe") if etf else None,
            "etf_pb": etf.get("etf_pb") if etf else None,
            "etf_dividend_yield": etf.get("etf_dividend_yield") if etf else None,
            "etf_pe_rank": etf.get("etf_pe_rank") if etf else None,
            "etf_pe_rank_of": etf.get("etf_pe_rank_of") if etf else None,
            "rel_strength_pct": etf.get("rel_strength_pct") if etf else None,
            "rel_momentum_pct": etf.get("rel_momentum_pct") if etf else None,
            "quadrant": etf.get("quadrant") if etf else None,
            "etf_only": False,
        })

    # ETF sectors with no matching stock-level row — either this market has
    # no per-stock universe at all yet (US), or the current universe just
    # doesn't happen to hold a stock in that GICS bucket. Appended rather
    # than dropped, so the undervalued-sector view is never missing a real
    # sector just because the stock screener hasn't caught up to it.
    for gics_label, etf in etf_by_gics.items():
        if gics_label in matched_gics:
            continue
        rows.append({
            "sector": gics_label,
            "gics_equivalent": gics_label,
            "constituent_count": 0,
            "buyable_count": 0,
            "buyable_pct": None,
            "median_composite_score": None,
            "median_fundamental_score": None,
            "median_technical_score": None,
            "median_pe": None,
            "median_peg": None,
            "pe_vs_universe_median_pct": None,
            "sector_score": None,
            "confident_sample": False,
            "top_ticker": None,
            "top_ticker_score": None,
            "why": "No stock in the current live universe falls in this sector yet — ETF-level valuation and momentum are real; sector-wide breadth/quality can't be read until the universe covers it.",
            "valuation_read": None,
            "pe_vs_own_history": sector_pe_trend(market.upper(), gics_label),
            "etf_ticker": etf.get("etf_ticker"),
            "etf_pe": etf.get("etf_pe"),
            "etf_pb": etf.get("etf_pb"),
            "etf_dividend_yield": etf.get("etf_dividend_yield"),
            "etf_pe_rank": etf.get("etf_pe_rank"),
            "etf_pe_rank_of": etf.get("etf_pe_rank_of"),
            "rel_strength_pct": etf.get("rel_strength_pct"),
            "rel_momentum_pct": etf.get("rel_momentum_pct"),
            "quadrant": etf.get("quadrant"),
            "etf_only": True,
        })

    # Cheapest sector-ETF PE first (real, peer-group-only comparison — see
    # module docstring) when that data exists; falls back to the older
    # confident-sample/composite-score sort for a market with no ETF data
    # at all. Undervaluation is the headline sort now, not a same-priority
    # tiebreaker, per the "undervalued sectors top to bottom" brief.
    def _sort_key(r: Dict[str, Any]):
        if r.get("etf_pe_rank") is not None:
            return (0, r["etf_pe_rank"])
        return (1, not r["confident_sample"], -(r["sector_score"] or -1))

    rows.sort(key=_sort_key)

    result = {
        "market": market.upper(),
        "as_of": db.screener_as_of(),
        "universe_size": universe_size,
        "universe_median_pe": universe_median_pe,
        "rankings": rows,
        "note": note,
    }
    try:
        db.snapshot_sector_history(market.upper(), rows)
    except Exception as exc:
        logger.warning("sector history snapshot failed (non-fatal): %s", exc)
    return result
