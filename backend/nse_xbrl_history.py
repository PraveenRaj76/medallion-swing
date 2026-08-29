"""
Point-in-time fundamental history from the NSE XBRL filing archive — the
data backbone Item 4 of the 2026-08-24 primary-source review asked to be
scoped: "130 real filings per large-cap, already dated and downloadable —
the actual data backbone the Decision Engine Blueprint's backtest plan
needed and didn't have for India."

VALIDATED (2026-08-24): fetched 5 real RELIANCE filings spread across
2018-2024 and confirmed values are genuinely differentiated and point-in-
time correct — revenue climbs Rs.1.46T (Sep-2018) -> Rs.2.44T (Dec-2024),
interest coverage moves realistically (2.72x in the Sep-2020 COVID/deleverage
dip vs 4-5x either side of it). One real caveat this surfaced: RELIANCE's
Oct-2024 1:1 bonus issue roughly halves reported EPS from that filing
onward — a genuine corporate action, not a data defect, but anyone
building ratios across bonus/split boundaries needs to adjust for it.
NSE's filing list goes back to 30-Jun-2014 for RELIANCE (46 consolidated
quarters) — comparable depth confirmed for other large-caps via the same
`corporates-financial-results` endpoint.

This module only fetches and dates the archive. It does not simulate
trades — see the module docstring note at the bottom for how a
backtest_engine.py would consume this.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import free_extra_sources as extra
import nse_xbrl_provider as prov

logger = logging.getLogger(__name__)


def fetch_fundamentals_history(
    symbol: str, num_quarters: int = 8, consolidated_only: bool = True
) -> List[Dict[str, Any]]:
    """Real, dated quarterly fundamentals for one ticker, oldest-last order
    matching NSE's own filing list (most recent first). Each entry carries
    the same self-computed fields as nse_xbrl_provider.fetch_latest_quarterly_xbrl
    (interest_coverage etc.) plus period_end / relating_to for slicing.

    Returns fewer than num_quarters if NSE has less history on file for
    this ticker, or [] if the symbol isn't found / the request is blocked.
    Never invents a value for a period the filing itself omits.
    """
    symbol = (symbol or "").strip().upper()
    session = extra._nse_session()
    filings = prov._fetch_filing_list(symbol, session)
    if not filings:
        return []

    pool = [f for f in filings if f.get("consolidated") == "Consolidated"] if consolidated_only else filings
    if not pool:
        pool = filings

    out: List[Dict[str, Any]] = []
    for filing in pool[:num_quarters]:
        xbrl_url = filing.get("xbrl")
        if not xbrl_url:
            continue
        parsed = prov._parse_filing(xbrl_url, session)
        if parsed is None:
            continue
        out.append(
            {
                "source": "nse_xbrl",
                "symbol": symbol,
                "period_end": filing.get("toDate"),
                "relating_to": filing.get("relatingTo"),
                "consolidated": filing.get("consolidated"),
                "broadcast_date": filing.get("broadCastDate"),
                "xbrl_url": xbrl_url,
                **parsed,
            }
        )
    return out


# ---------------------------------------------------------------------------
# Scoping note for backtest_engine.py (not yet built — this module proves
# the data exists and is fetchable; the simulator is separate future work)
# ---------------------------------------------------------------------------
#
# What this unlocks: a walk-forward backtest can now look up "what did this
# company's fundamentals actually say as of date D" for any historical D,
# instead of only ever having today's snapshot (which is what made
# fundamental backtesting for India "genuinely unsolvable free" per the
# Decision Engine Blueprint). The `broadcast_date` field is the key to
# point-in-time correctness: a backtest must only use a filing whose
# broadcast_date <= the simulated trade date, otherwise it's lookahead bias
# (using Q3 results that weren't public yet to score a trade placed during Q3).
#
# What backtest_engine.py would still need to add on top of this module:
#   1. Historical daily OHLCV per ticker (yfinance `history(period="5y")` —
#      already used live elsewhere in this codebase, no new sourcing needed).
#   2. A walk-forward loop: for each historical date, join (a) the OHLCV bar
#      for that date with (b) the most recent fundamentals filing whose
#      broadcast_date <= that date (via this module), then feed both into
#      the existing factor_engine.py scoring — the SAME scoring code paths
#      already validated live, not a reimplementation.
#   3. Trade simulation: entry/exit/stop-loss/target logic re-using the
#      existing Chandelier Exit trailing-stop and position-sizing logic
#      already in this codebase, applied to the historical OHLCV series.
#   4. Corporate-action awareness: bonus/split adjustment for EPS and
#      share-count-dependent ratios across boundaries like RELIANCE's
#      Oct-2024 bonus (see module docstring) — NOT yet handled here, since
#      fixing it requires a corporate-actions source, which is a separate
#      research task, not a code task.
#
# Deliberately not built this turn: items 1-3 above are a genuine new
# module (OHLCV alignment + trade simulation), materially larger than the
# data-sourcing validation this module completes, and item 4 needs a
# decision on a corporate-actions data source before it can be built
# honestly rather than guessed at.
