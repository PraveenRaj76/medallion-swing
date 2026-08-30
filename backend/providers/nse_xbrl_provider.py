"""
NSE official XBRL quarterly-results filings — the same primary source
Screener.in itself is built on (their own support docs describe normalizing
"annual reports" and "reported numbers", not a private feed — see the Data
Authenticity Audit, 2026-08-24).

This isn't a scrape of a rendered page: `corporates-financial-results` is
NSE's own JSON API listing every filing a company has made, each with a
direct link to the actual XBRL (XML) document submitted to the exchange —
the same regulatory filing Screener parses.

VALIDATED, not assumed (2026-08-24 follow-up):
  - Consolidated vs. Non-Consolidated: both exist for most large caps and
    were pulled side by side for RELIANCE. Revenue/profit scale correctly
    between them (consolidated ~2x standalone, as expected for a group with
    large subsidiaries) — confirming BOTH filing types are individually
    trustworthy on their raw line items. Consolidated is preferred here
    because it matches Screener's own stated methodology (their support
    docs: "we calculate ratios on consolidated numbers where available"),
    keeping this source consistent with the rest of the pipeline.
  - The filing's OWN pre-computed InterestServiceCoverageRatio and
    DebtEquityRatio tags are NOT trustworthy: they returned the same
    implausible values (0.05-0.06x interest coverage, 0.00x debt/equity)
    in BOTH the consolidated and non-consolidated filings, despite those
    filings' revenue/profit correctly differing by ~2x. A ratio that
    doesn't move when its inputs do is broken, not the standalone/
    consolidated selection this project's session started out trying to
    fix. Deliberately not exposed.
  - Interest Coverage is instead SELF-COMPUTED from raw, individually
    verified components: (ProfitBeforeTax + FinanceCosts) / FinanceCosts
    — the standard EBIT-proxy coverage formula, same "compute, don't trust
    a pre-built widget" approach already used for Profit Growth elsewhere
    in this codebase. Validated: RELIANCE comes back 5.64x (consolidated)
    / 5.89x (standalone) — sensible, close to each other as expected, and
    a world away from the broken 0.06x the filing's own tag reported.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional

from providers import free_extra_sources as extra

logger = logging.getLogger(__name__)

NSE_RESULTS_API = "https://www.nseindia.com/api/corporates-financial-results"
RESULTS_REFERER = "https://www.nseindia.com/companies-listing/corporate-filings-financial-results"

# in-bse-fin: is the XBRL taxonomy namespace NSE industrial-company filings
# use — confirmed present in both RELIANCE's and TCS's filings. Banking-
# taxonomy filings (BANKING_ prefix in the XBRL filename) use a different
# schema entirely — see nse_xbrl_banking_provider.py.
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


def _fetch_filing_list(symbol: str, session: Any) -> list:
    resp = extra._get(
        f"{NSE_RESULTS_API}?index=equities&symbol={symbol}&period=Quarterly",
        RESULTS_REFERER,
        session=session,
    )
    if resp is None or getattr(resp, "status_code", 0) != 200:
        return []
    try:
        filings = resp.json()
    except Exception:
        try:
            import json as _json

            filings = _json.loads(resp.text)
        except Exception:
            return []
    return filings if isinstance(filings, list) else []


def _parse_filing(xbrl_url: str, session: Any) -> Optional[Dict[str, Optional[float]]]:
    resp = extra._get(xbrl_url, RESULTS_REFERER, session=session)
    if resp is None or getattr(resp, "status_code", 0) != 200:
        return None
    xml = resp.text

    revenue = _extract_tag(xml, "RevenueFromOperations")
    profit_before_tax = _extract_tag(xml, "ProfitBeforeTax")
    profit_after_tax = _extract_tag(xml, "ProfitLossForPeriod")
    eps_basic = _extract_tag(xml, "BasicEarningsLossPerShareFromContinuingOperations")
    finance_costs = _extract_tag(xml, "FinanceCosts")

    interest_coverage = None
    if profit_before_tax is not None and finance_costs and finance_costs > 0:
        interest_coverage = round((profit_before_tax + finance_costs) / finance_costs, 2)

    return {
        "revenue_from_operations": revenue,
        "profit_before_tax": profit_before_tax,
        "profit_after_tax": profit_after_tax,
        "eps_basic": eps_basic,
        "finance_costs": finance_costs,
        "interest_coverage": interest_coverage,
    }


def fetch_latest_quarterly_xbrl(symbol: str) -> Optional[Dict[str, Any]]:
    """Real quarterly-results facts for one ticker, or None if NSE has
    nothing on file / the request is blocked. Never invents a value for a
    tag the filing itself omits.

    Prefers the latest Consolidated filing; falls back to Non-Consolidated
    only when no consolidated filing exists for this ticker (e.g. a company
    with no subsidiaries) — see module docstring for why.
    """
    symbol = (symbol or "").strip().upper()
    session = extra._nse_session()
    filings = _fetch_filing_list(symbol, session)
    if not filings:
        return None

    consolidated = [f for f in filings if f.get("consolidated") == "Consolidated"]
    chosen = consolidated[0] if consolidated else filings[0]
    xbrl_url = chosen.get("xbrl")
    if not xbrl_url:
        return None

    parsed = _parse_filing(xbrl_url, session)
    if parsed is None:
        return None

    return {
        "source": "nse_xbrl",
        "ok": True,
        "symbol": symbol,
        "period_end": chosen.get("toDate"),
        "relating_to": chosen.get("relatingTo"),
        "consolidated": chosen.get("consolidated"),
        "xbrl_url": xbrl_url,
        **parsed,
    }
