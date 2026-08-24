"""
NSE official XBRL quarterly-results filings — the same primary source
Screener.in itself is built on (their own support docs describe normalizing
"annual reports" and "reported numbers", not a private feed — see the Data
Authenticity Audit, 2026-08-24).

This isn't a scrape of a rendered page: `corporates-financial-results` is
NSE's own JSON API listing every filing a company has made, each with a
direct link to the actual XBRL (XML) document submitted to the exchange —
the same regulatory filing Screener parses. Confirmed live against
RELIANCE and TCS: real revenue, profit, and EPS in every filing; debt-ratio
tags (DebtEquityRatio, InterestServiceCoverageRatio) present only for
companies that actually carry debt to report — TCS's near-debt-free filing
omits them, which is correct filing behavior, not missing data.

This is what finally makes Interest Coverage real instead of a hard-coded
None — see multi_source_data.py.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional

import free_extra_sources as extra

logger = logging.getLogger(__name__)

NSE_RESULTS_API = "https://www.nseindia.com/api/corporates-financial-results"
RESULTS_REFERER = "https://www.nseindia.com/companies-listing/corporate-filings-financial-results"

# in-bse-fin: is the XBRL taxonomy namespace NSE filings use regardless of
# exchange name — confirmed present in both RELIANCE's and TCS's filings.
_TAG_NS = "in-bse-fin"


def _extract_tag(xml: str, tag: str) -> Optional[float]:
    """First occurrence of a tag's numeric value — filings list the current
    period before the comparative prior period, so this is "latest reported",
    matching how the rest of this pipeline treats a single row."""
    m = re.search(rf"<{_TAG_NS}:{tag}[^>]*>([^<]+)</{_TAG_NS}:{tag}>", xml)
    if not m:
        return None
    try:
        return float(m.group(1))
    except (TypeError, ValueError):
        return None


def fetch_latest_quarterly_xbrl(symbol: str) -> Optional[Dict[str, Any]]:
    """Real quarterly-results facts for one ticker, or None if NSE has
    nothing on file / the request is blocked. Never invents a value for a
    tag the filing itself omits — see module docstring on TCS's debt ratios.
    """
    symbol = (symbol or "").strip().upper()
    session = extra._nse_session()
    list_resp = extra._get(
        f"{NSE_RESULTS_API}?index=equities&symbol={symbol}&period=Quarterly",
        RESULTS_REFERER,
        session=session,
    )
    if list_resp is None or getattr(list_resp, "status_code", 0) != 200:
        return None
    try:
        filings = list_resp.json()
    except Exception:
        try:
            import json as _json

            filings = _json.loads(list_resp.text)
        except Exception:
            return None
    if not isinstance(filings, list) or not filings:
        return None

    latest = filings[0]
    xbrl_url = latest.get("xbrl")
    if not xbrl_url:
        return None

    xbrl_resp = extra._get(xbrl_url, RESULTS_REFERER, session=session)
    if xbrl_resp is None or getattr(xbrl_resp, "status_code", 0) != 200:
        return None
    xml = xbrl_resp.text

    revenue = _extract_tag(xml, "RevenueFromOperations")
    profit_before_tax = _extract_tag(xml, "ProfitBeforeTax")
    profit_after_tax = _extract_tag(xml, "ProfitLossForPeriod")
    eps_basic = _extract_tag(xml, "BasicEarningsLossPerShareFromContinuingOperations")
    debt_equity_ratio = _extract_tag(xml, "DebtEquityRatio")
    interest_coverage_ratio = _extract_tag(xml, "InterestServiceCoverageRatio")

    return {
        "source": "nse_xbrl",
        "ok": True,
        "symbol": symbol,
        "period_end": latest.get("toDate"),
        "relating_to": latest.get("relatingTo"),
        "consolidated": latest.get("consolidated"),
        "xbrl_url": xbrl_url,
        "revenue_from_operations": revenue,
        "profit_before_tax": profit_before_tax,
        "profit_after_tax": profit_after_tax,
        "eps_basic": eps_basic,
        "debt_equity_ratio": debt_equity_ratio,
        # Only field this project has ever had real access to for this ratio —
        # every prior India source had it hard-coded None (not free-source-available).
        "interest_coverage": interest_coverage_ratio,
    }
