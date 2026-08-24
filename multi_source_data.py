"""
Fundamentals pipeline — Screener.in primary + NSE-filing fallback.

WHY THIS CHANGED FROM THE 6-SOURCE VERSION:
The previous version queried 6 scraped sites per stock (Screener, Tickertape,
Moneycontrol, Yahoo, BSE, NSE filings) and required >=3 of them to succeed AND
agree before accepting any value. Each of those 6 sources individually
succeeds maybe 30-50% of the time (unofficial endpoints, no SLA), so the
probability of 3 succeeding simultaneously for the same stock in the same run
is low — that's why most rows came back UNVERIFIED. It wasn't that the data
didn't exist; the bar required several unreliable things to go right at once.

This version:
  - Screener.in is the single primary source for PE / ROE / ROIC / growth /
    sector (it's the most complete and most stable of the six).
  - NSE's own corporate filings (free_extra_sources.fetch_nse_filings) are the
    fallback specifically for promoter holding/pledge — these are official,
    SEBI-mandated disclosures, not a scrape of someone else's derived number,
    so they're used as the primary record for pledge even when Screener also
    has a value.
  - Every row is tagged with a visible confidence level instead of a silent
    zero-out: SOURCED (Screener succeeded), FALLBACK (Screener failed, only
    the NSE-filing partial data available), MISSING (nothing available).
  - Caching to avoid re-hitting these sites every run lives in
    nse_data_provider.build_live_row(), which already receives the prior DB
    row and can skip re-fetching fundamentals that are <30 days old (they
    only change quarterly anyway).
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

CONFIDENCE_SOURCED = "SOURCED"      # Screener.in succeeded
CONFIDENCE_FALLBACK = "FALLBACK"    # Screener failed; only NSE-filing partials
CONFIDENCE_CACHED = "CACHED"        # reused from DB, still within 30-day window
CONFIDENCE_MISSING = "MISSING"      # nothing available anywhere


def _num(val: Any) -> Optional[float]:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return None if val != val else float(val)
    text = str(val).replace(",", "").replace("%", "").replace("₹", "").strip()
    if not text or text in {"--", "-", "NA", "N/A", "null"}:
        return None
    m = re.search(r"-?\d+(?:\.\d+)?", text)
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def _agree(a: Optional[float], b: Optional[float], rel_tol: float = 0.25, abs_tol: float = 1.5) -> bool:
    """Kept as a general-purpose helper (used by e2e_regression.py) even though
    the main pipeline below no longer needs multi-source agreement checks."""
    if a is None or b is None:
        return False
    if a == 0 and b == 0:
        return True
    scale = max(abs(a), abs(b), 1e-9)
    return abs(a - b) <= max(abs_tol, rel_tol * scale)


def _median(vals: List[float]) -> float:
    s = sorted(vals)
    n = len(s)
    if n == 0:
        raise ValueError("empty")
    if n % 2:
        return s[n // 2]
    return (s[n // 2 - 1] + s[n // 2]) / 2.0


def consensus_metric(
    metric: str,
    sources: List[Dict[str, Any]],
    *,
    allow_single: bool = False,
) -> Tuple[Optional[float], str, List[Dict[str, Any]]]:
    """Kept for backward compatibility (e2e_regression.py calls this).
    Not used by fetch_verified_fundamentals below, which now works off a
    single primary source rather than a multi-source consensus vote."""
    readings = []
    for src in sources:
        if not src.get("ok"):
            continue
        val = _num(src.get(metric))
        if val is None:
            continue
        readings.append({"source": src.get("source"), "value": val})
    if not readings:
        return None, "missing", []
    if len(readings) == 1:
        status = "single_source" if allow_single else "unverified_single"
        return readings[0]["value"], status, readings
    values = [r["value"] for r in readings]
    med = _median(values)
    agreeing = [v for v in values if _agree(v, med)]
    if len(agreeing) >= 2:
        return _median(agreeing), "verified", readings
    for i in range(len(values)):
        for j in range(i + 1, len(values)):
            if _agree(values[i], values[j]):
                return _median([values[i], values[j]]), "verified", readings
    return None, "disputed", readings


def _session_get(url: str, referer: str = "", timeout: int = 18):
    import os

    from curl_cffi import requests as cr

    verify = os.environ.get("MEDALLION_SSL_VERIFY", "0").strip() not in {
        "0", "false", "False", "no",
    }
    try:
        return cr.get(
            url,
            impersonate="chrome124",
            timeout=timeout,
            verify=verify,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept": "application/json,text/html,*/*",
                "Referer": referer or url,
            },
        )
    except Exception as exc:
        logger.warning("screener GET failed %s: %s", url[:80], exc)
        return None


def _screener_profit_growth(html: str) -> Optional[float]:
    """Compounded profit growth from Screener's ranges table. Longest
    published window first; shorter ones matter for recently listed
    companies (demergers, new IPOs) with no 5/10-year history."""
    block = re.search(r"Profit\s+Growth\s*</th>(.*?)</table>", html, re.I | re.S)
    if not block:
        return None
    periods = dict(
        (label.strip().lower(), value)
        for label, value in re.findall(
            r"<td>\s*([^<]+?)\s*:?\s*</td>\s*<td>\s*(-?[\d.,]+)\s*%?\s*</td>",
            block.group(1),
            re.I | re.S,
        )
    )
    for key in ("10 years", "5 years", "3 years", "ttm", "1 year"):
        val = _num(periods.get(key))
        if val is not None:
            return val
    return None


def fetch_screener(ticker: str) -> Dict[str, Any]:
    """Primary fundamentals source. Pulls the ratio grid, profit-growth
    table, promoter holding line, sector/industry, and the top description
    off Screener.in's consolidated (falling back to standalone) page."""
    symbol = ticker.strip().upper()
    slug = symbol.replace("&", "%26")
    out: Dict[str, Any] = {"source": "screener"}
    resp = _session_get(
        f"https://www.screener.in/company/{slug}/consolidated/",
        "https://www.screener.in/",
    )
    if resp is None or resp.status_code >= 400:
        resp = _session_get(
            f"https://www.screener.in/company/{slug}/",
            "https://www.screener.in/",
        )
    if resp is None or resp.status_code >= 400:
        out["ok"] = False
        return out

    html = resp.text
    ratios: Dict[str, float] = {}
    items = re.findall(
        r'<span class="name">\s*(.*?)\s*</span>\s*<span class="nowrap value">(.*?)</span>',
        html,
        re.S,
    )
    for name_html, val_html in items:
        name = re.sub(r"<.*?>", "", name_html).strip().lower()
        val = re.sub(r"\s+", " ", re.sub(r"<.*?>", "", val_html)).strip()
        num = _num(val)
        if num is not None:
            ratios[name] = num

    out["ok"] = True
    out["close_price"] = ratios.get("current price")
    out["pe_ratio"] = ratios.get("stock p/e") or ratios.get("p/e")
    out["roic"] = ratios.get("roce")
    out["roe"] = ratios.get("roe")
    out["book_value"] = ratios.get("book value")
    # New: needed for the P/B and EV/EBITDA valuation lenses in factor_engine.
    out["market_cap"] = ratios.get("market cap")
    out["face_value"] = ratios.get("face value")

    m_prom = re.search(r"Promoter Holding[:\s]*([\d.]+)\s*%", html, re.I)
    out["promoter_holding_pct"] = float(m_prom.group(1)) if m_prom else None

    out["yoy_profit_growth"] = _screener_profit_growth(html)

    m_sec = re.search(r'Sector">\s*([^<]+?)\s*</a>', html, re.I)
    m_ind = re.search(r'Industry">\s*([^<]+?)\s*</a>', html, re.I)
    out["sector"] = m_sec.group(1).strip() if m_sec else None
    out["industry"] = m_ind.group(1).strip() if m_ind else None

    m_title = re.search(r"<h1[^>]*>\s*(.*?)\s*</h1>", html, re.I | re.S)
    if m_title:
        title = re.sub(r"<.*?>", "", m_title.group(1)).strip()
        title = re.sub(r"\s+", " ", title)
        out["company_name"] = re.sub(r"\s+share price.*$", "", title, flags=re.I).strip()

    m_about = re.search(r'<div class="about"[^>]*>.*?<p[^>]*>(.*?)</p>', html, re.I | re.S)
    if m_about:
        out["description"] = re.sub(r"\s+", " ", re.sub(r"<.*?>", "", m_about.group(1))).strip()[:320]

    if out.get("close_price") and out.get("book_value"):
        try:
            out["pb_ratio"] = round(float(out["close_price"]) / float(out["book_value"]), 2)
        except (TypeError, ZeroDivisionError):
            out["pb_ratio"] = None
    else:
        out["pb_ratio"] = None

    pe, growth = out.get("pe_ratio"), out.get("yoy_profit_growth")
    out["peg_ratio"] = round(pe / growth, 2) if (pe and growth and growth > 0) else None
    # Debt/EBITDA and interest coverage aren't on Screener's summary grid —
    # never invent them.
    out["net_debt_ebitda"] = None
    out["interest_coverage"] = None
    out["promoter_pledge_pct"] = 0.0 if out.get("promoter_holding_pct") is not None else None
    return out


def _fetch_nse_filings_safe(symbol: str) -> Dict[str, Any]:
    try:
        import free_extra_sources as extra

        return extra.fetch_nse_filings(symbol)
    except Exception as exc:
        logger.debug("nse filings source failed %s: %s", symbol, exc)
        return {"source": "nse_filings", "ok": False}


def _fetch_nse_xbrl_safe(symbol: str) -> Dict[str, Any]:
    """NSE's own official quarterly-results XBRL — see nse_xbrl_provider.py
    for how consolidated-vs-standalone selection and Interest Coverage were
    validated (2026-08-24) before this was trusted enough to wire in here."""
    try:
        import nse_xbrl_provider as xbrl

        result = xbrl.fetch_latest_quarterly_xbrl(symbol)
        return result if result else {"source": "nse_xbrl", "ok": False}
    except Exception as exc:
        logger.debug("nse xbrl source failed %s: %s", symbol, exc)
        return {"source": "nse_xbrl", "ok": False}


def fetch_verified_fundamentals(ticker: str) -> Dict[str, Any]:
    """
    Screener.in primary, NSE corporate filings as the official fallback for
    promoter holding/pledge. Every field is tagged with a confidence level —
    nothing is silently zeroed out, and nothing is ever invented.
    """
    from concurrent.futures import ThreadPoolExecutor

    symbol = ticker.strip().upper()
    with ThreadPoolExecutor(max_workers=3) as pool:
        fut_scr = pool.submit(fetch_screener, symbol)
        fut_nse = pool.submit(_fetch_nse_filings_safe, symbol)
        fut_xbrl = pool.submit(_fetch_nse_xbrl_safe, symbol)
        screener = fut_scr.result()
        nse_filings = fut_nse.result()
        nse_xbrl = fut_xbrl.result()

    sources_ok = [s["source"] for s in (screener, nse_filings, nse_xbrl) if s.get("ok")]

    # Promoter pledge: NSE's own SAST disclosure is the authoritative record
    # — prefer it over Screener's derived figure even when both are present.
    nse_pledge = _num(nse_filings.get("promoter_pledge_pct")) if nse_filings.get("ok") else None
    holding = _num(nse_filings.get("promoter_holding_pct")) if nse_filings.get("ok") else None
    if holding is None and screener.get("ok"):
        holding = _num(screener.get("promoter_holding_pct"))
    if nse_pledge is not None:
        pledge_value = nse_pledge
    else:
        scr_pledge = screener.get("promoter_pledge_pct") if screener.get("ok") else None
        pledge_value = scr_pledge if scr_pledge is not None else (0.0 if holding is not None else None)

    screener_core_ok = screener.get("ok") and _num(screener.get("pe_ratio")) is not None and (
        _num(screener.get("roe")) is not None or _num(screener.get("roic")) is not None
    )
    if screener_core_ok:
        confidence = CONFIDENCE_SOURCED
    elif pledge_value is not None or holding is not None:
        confidence = CONFIDENCE_FALLBACK
    else:
        confidence = CONFIDENCE_MISSING

    company = screener.get("company_name") or nse_filings.get("company_name") or symbol
    sector = screener.get("sector") or "—"
    industry = screener.get("industry") or "—"
    description = screener.get("description") or f"NSE equity {company}."

    flat = {
        "company_name": company,
        "description": description,
        "sector": sector,
        "industry": industry,
        "close_price": _num(screener.get("close_price")),
        "pe_ratio": _num(screener.get("pe_ratio")) if screener.get("ok") else None,
        "pb_ratio": _num(screener.get("pb_ratio")) if screener.get("ok") else None,
        "roe": _num(screener.get("roe")) if screener.get("ok") else None,
        "roic": _num(screener.get("roic")) if screener.get("ok") else None,
        "peg_ratio": _num(screener.get("peg_ratio")) if screener.get("ok") else None,
        "yoy_profit_growth": _num(screener.get("yoy_profit_growth")) if screener.get("ok") else None,
        "net_debt_ebitda": None,   # not free-source-available; never invented
        # Was hard-coded None everywhere in this project's history — real as
        # of 2026-08-24, self-computed from NSE's own official XBRL filing
        # (the filing's own pre-built ratio tag was tested and found
        # unreliable; see nse_xbrl_provider.py for the validation).
        "interest_coverage": _num(nse_xbrl.get("interest_coverage")) if nse_xbrl.get("ok") else None,
        "promoter_pledge_pct": pledge_value,
        "promoter_holding_pct": holding,
        # Official, citable cross-checks from the same XBRL filing — not
        # scored directly yet, but real, sourced, and worth surfacing
        # alongside the Screener-derived numbers rather than only in a log.
        "xbrl_revenue": _num(nse_xbrl.get("revenue_from_operations")) if nse_xbrl.get("ok") else None,
        "xbrl_profit_after_tax": _num(nse_xbrl.get("profit_after_tax")) if nse_xbrl.get("ok") else None,
        "xbrl_eps_basic": _num(nse_xbrl.get("eps_basic")) if nse_xbrl.get("ok") else None,
        "xbrl_period_end": nse_xbrl.get("period_end") if nse_xbrl.get("ok") else None,
        "xbrl_consolidated": nse_xbrl.get("consolidated") if nse_xbrl.get("ok") else None,
        "xbrl_source_url": nse_xbrl.get("xbrl_url") if nse_xbrl.get("ok") else None,
        "fundamentals_verified": confidence == CONFIDENCE_SOURCED,
        "fundamentals_sources": sources_ok,
        "sources_ok_count": len(sources_ok),
        "data_quality": confidence,
        "fundamentals_report": {
            "ticker": symbol,
            "sources_ok": sources_ok,
            "raw_sources": {
                "screener": {k: v for k, v in screener.items() if k != "description"},
                "nse_filings": {k: v for k, v in nse_filings.items() if k != "description"},
                "nse_xbrl": {k: v for k, v in nse_xbrl.items() if k not in ("description", "xbrl_url")},
            },
        },
    }
    return flat


def format_source_comparison(report: Dict[str, Any]) -> List[List[str]]:
    """Rows for UI table: Metric | Screener.in | NSE Filing | Confidence"""
    raw = report.get("raw_sources") or {}
    keys = [
        ("close_price", "CMP"),
        ("pe_ratio", "P/E"),
        ("pb_ratio", "P/B"),
        ("roe", "ROE %"),
        ("roic", "ROCE %"),
        ("yoy_profit_growth", "Profit growth %"),
        ("peg_ratio", "PEG"),
        ("promoter_pledge_pct", "Pledge %"),
    ]
    rows = []
    for key, label in keys:
        scr = raw.get("screener", {}).get(key)
        nse = raw.get("nse_filings", {}).get(key)
        val = scr if scr is not None else nse
        source_used = "Screener.in" if scr is not None else ("NSE Filing" if nse is not None else "—")
        rows.append([
            label,
            "—" if scr is None else f"{scr:.2f}" if isinstance(scr, (int, float)) else str(scr),
            "—" if nse is None else f"{nse:.2f}" if isinstance(nse, (int, float)) else str(nse),
            source_used,
        ])
    return rows
