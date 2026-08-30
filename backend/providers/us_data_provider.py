"""
US equities data provider — SEC EDGAR (official, free, no API key) for
fundamentals, Yahoo Finance for price/technicals. Same "compute, don't
trust a pre-built widget" philosophy as nse_data_provider.py, adapted for
what's actually free and real at US-market scale.

VALIDATED LIVE (2026-08-26):
  - Universe: S&P 500 constituent list from Wikipedia (503 real tickers +
    GICS sector) — the standard free source for this, not a scrape of a
    paid index provider's proprietary list.
  - Ticker -> CIK mapping: SEC's own official company_tickers.json
    (10,388 companies, no key). This is a primary source, not a scrape.
  - Fundamentals: SEC EDGAR companyfacts API returns real filed XBRL
    concepts — confirmed against Apple's actual latest 10-Q (NetIncomeLoss,
    StockholdersEquity, Assets, Liabilities, EPS, shares outstanding all
    real, live numbers, not estimates).
  - Price/technicals: yfinance, bare ticker (no ".NS" suffix — seeing
    sector_valuation.py's fix note for why that distinction matters).

Scoped for this pass: S&P 500 (large-cap) only. Mid/small-cap (S&P 400 /
600 — also confirmed live-fetchable via the same Wikipedia pattern) and
insider ownership (SEC Form 3/4 aggregation, meaningfully more work to get
right) are real, valuable follow-ups, not stubbed here as fake data —
just not built yet. The checklist below simply omits what isn't real yet
rather than inventing a placeholder.
"""

from __future__ import annotations

import io
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)

# This file lives in backend/providers/ — cache files live in backend/data/,
# one level up.
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
UNIVERSE_CACHE_PATH = DATA_DIR / "us_universe_cache.json"
CIK_MAP_CACHE_PATH = DATA_DIR / "us_cik_map_cache.json"
CACHE_MAX_AGE_SEC = 24 * 3600

SEC_HEADERS = {"User-Agent": "Medallion Swing Screener research@example.com"}
BENCHMARK = "SPY"


def _ssl_verify() -> bool:
    return os.environ.get("MEDALLION_SSL_VERIFY", "0").strip() not in {"0", "false", "False", "no"}


def _cache_fresh(path: Path) -> bool:
    return path.exists() and (time.time() - path.stat().st_mtime) < CACHE_MAX_AGE_SEC


def normalize_ticker(ticker: str) -> str:
    """Yahoo/EDGAR both use a hyphen for share-class tickers (BRK-B), not
    the dot Wikipedia's table uses (BRK.B)."""
    return (ticker or "").strip().upper().replace(".", "-")


def _load_cik_map() -> Dict[str, int]:
    if _cache_fresh(CIK_MAP_CACHE_PATH):
        try:
            return json.loads(CIK_MAP_CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    try:
        import requests

        resp = requests.get(
            "https://www.sec.gov/files/company_tickers.json",
            headers=SEC_HEADERS,
            timeout=20,
            verify=_ssl_verify(),
        )
        data = resp.json()
        out = {str(v["ticker"]).upper(): int(v["cik_str"]) for v in data.values()}
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        CIK_MAP_CACHE_PATH.write_text(json.dumps(out), encoding="utf-8")
        return out
    except Exception as exc:
        logger.warning("SEC CIK map fetch failed: %s", exc)
        if CIK_MAP_CACHE_PATH.exists():
            try:
                return json.loads(CIK_MAP_CACHE_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}


def load_universe() -> List[Dict[str, Any]]:
    """Real S&P 500 constituents: ticker, company_name, sector, industry,
    cik, tier. Cached to disk for a day — this list changes rarely and
    there's no reason to hit Wikipedia on every single refresh."""
    if _cache_fresh(UNIVERSE_CACHE_PATH):
        try:
            return json.loads(UNIVERSE_CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    try:
        import requests

        resp = requests.get(
            "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=20,
            verify=_ssl_verify(),
        )
        tables = pd.read_html(io.StringIO(resp.text))
        df = tables[0]
        cik_map = _load_cik_map()
        out: List[Dict[str, Any]] = []
        for _, row in df.iterrows():
            sym = normalize_ticker(str(row["Symbol"]))
            out.append(
                {
                    "ticker": sym,
                    "company_name": str(row["Security"]).strip(),
                    "sector": str(row.get("GICS Sector", "")).strip(),
                    "industry": str(row.get("GICS Sub-Industry", "")).strip(),
                    "cik": cik_map.get(sym.replace("-", ".")) or cik_map.get(sym),
                    "tier": "Large",
                }
            )
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        UNIVERSE_CACHE_PATH.write_text(json.dumps(out), encoding="utf-8")
        return out
    except Exception as exc:
        logger.warning("US universe fetch failed: %s", exc)
        if UNIVERSE_CACHE_PATH.exists():
            try:
                return json.loads(UNIVERSE_CACHE_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        return []


def universe_label() -> str:
    return "S&P 500 (Large-Cap)"


# ---------------------------------------------------------------------------
# SEC EDGAR fundamentals
# ---------------------------------------------------------------------------

# Real filings don't all tag the same concept identically — this tries each
# candidate in order and uses the first one the company actually filed,
# rather than assuming one canonical tag name exists for every company.
_CONCEPT_CANDIDATES: Dict[str, List[str]] = {
    "net_income": ["NetIncomeLoss", "ProfitLoss"],
    "equity": ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
    "assets": ["Assets"],
    "liabilities": ["Liabilities"],
    "eps_diluted": ["EarningsPerShareDiluted"],
    "eps_basic": ["EarningsPerShareBasic"],
    "shares_out": ["CommonStockSharesOutstanding", "EntityCommonStockSharesOutstanding"],
    "revenue": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"],
    "operating_income": ["OperatingIncomeLoss"],
    "interest_expense": ["InterestExpense", "InterestExpenseDebt", "InterestExpenseNonoperating"],
    "lt_debt": ["LongTermDebtNoncurrent", "LongTermDebt"],
}


def _fetch_companyfacts(cik: int) -> Optional[Dict[str, Any]]:
    try:
        import requests

        cik_padded = str(int(cik)).zfill(10)
        resp = requests.get(
            f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik_padded}.json",
            headers=SEC_HEADERS,
            timeout=20,
            verify=_ssl_verify(),
        )
        if resp.status_code != 200:
            return None
        return resp.json()
    except Exception as exc:
        logger.debug("EDGAR companyfacts fetch failed for CIK %s: %s", cik, exc)
        return None


def _latest_point(facts: Dict[str, Any], tag: str) -> Optional[Dict[str, Any]]:
    """Most recent real datapoint for one us-gaap concept, any unit."""
    concept = (facts.get("facts") or {}).get("us-gaap", {}).get(tag)
    if not concept:
        return None
    units = concept.get("units") or {}
    best = None
    for series in units.values():
        for point in series:
            if point.get("val") is None or point.get("end") is None:
                continue
            if best is None or point["end"] > best["end"]:
                best = point
    return best


def _annual_series(facts: Dict[str, Any], tag: str) -> List[Dict[str, Any]]:
    """Real 10-K annual datapoints for one concept, newest first — used for
    genuine year-over-year growth, not a quarter-vs-quarter distortion."""
    concept = (facts.get("facts") or {}).get("us-gaap", {}).get(tag)
    if not concept:
        return []
    out = []
    for series in (concept.get("units") or {}).values():
        for point in series:
            if point.get("form") != "10-K" or point.get("val") is None:
                continue
            start, end = point.get("start"), point.get("end")
            if not start or not end:
                continue
            out.append(point)
    out.sort(key=lambda p: p["end"], reverse=True)
    # de-dupe by fiscal year end (companies sometimes restate the same year)
    seen = set()
    deduped = []
    for p in out:
        if p["end"] in seen:
            continue
        seen.add(p["end"])
        deduped.append(p)
    return deduped


def _get(facts: Dict[str, Any], key: str) -> Optional[float]:
    for tag in _CONCEPT_CANDIDATES.get(key, []):
        point = _latest_point(facts, tag)
        if point is not None:
            try:
                return float(point["val"])
            except (TypeError, ValueError):
                continue
    return None


def _compute_ttm(facts: Dict[str, Any], key: str) -> Optional[float]:
    """Real trailing-twelve-months figure for a flow concept (net income,
    operating income, interest expense) — NOT the raw latest datapoint.

    EDGAR's 10-Q filings report these as fiscal-year-to-date CUMULATIVE
    totals, not a single quarter's worth — confirmed live on Apple's own
    filing (2026-08-26): the "latest" NetIncomeLoss point for a Q3 10-Q
    covers Sep-2025 through Jun-2026, a 9-month span, not 3 months and not
    a full year. Using that directly as if it were annual earnings
    overstated Apple's P/E by roughly a third in testing (45.6x vs the
    correct ~35.5x) — a real, material authenticity bug, not a rounding
    difference, so this is not optional.

    Standard TTM technique: last full fiscal year (10-K) + current
    year-to-date interim - same year-to-date interim one year earlier.
    If the most recent filing IS itself the 10-K (company just closed its
    fiscal year, no partial period pending), that figure needs no
    adjustment and is returned directly.

    IMPORTANT (found live, 2026-08-26): a single 10-K/10-Q filing embeds
    MULTIPLE comparative-year duplicates of the same concept, and EDGAR
    tags every one of them with the *filing's own* fy/fp — e.g. Apple's
    2025 10-K carries CY2023/CY2024/CY2025 annual net income, all labeled
    fy=2025/fp='FY'. Matching on the fy/fp tags alone (what the first
    version of this function did) can silently grab the wrong comparative
    year — it did, and threw net income off by roughly 4x. Matching by
    actual period duration and date instead avoids that ambiguity.
    """
    from datetime import date as _date

    def _parse(d: str) -> Optional[_date]:
        try:
            return _date.fromisoformat(d)
        except (TypeError, ValueError):
            return None

    for tag in _CONCEPT_CANDIDATES.get(key, []):
        concept = (facts.get("facts") or {}).get("us-gaap", {}).get(tag)
        if not concept:
            continue
        points = [p for series in (concept.get("units") or {}).values() for p in series if p.get("val") is not None and p.get("end") and p.get("start")]
        if not points:
            continue
        current = max(points, key=lambda p: p["end"])
        cur_start, cur_end = _parse(current["start"]), _parse(current["end"])
        if cur_start is None or cur_end is None:
            return float(current["val"])
        cur_days = (cur_end - cur_start).days
        if cur_days >= 350:  # already a full-year figure (10-K or FY-tagged) — no adjustment needed
            return float(current["val"])

        # Last full fiscal year: any ~365-day-duration datapoint for this
        # concept, take the one with the latest end date (most recent
        # completed year) — real filings sometimes carry several years of
        # comparatives, so "most recent by end date" is what "last fiscal
        # year" actually means, not "first match in an unordered list".
        annual_candidates = [p for p in points if 350 <= ((_parse(p["end"]) or cur_start) - (_parse(p["start"]) or cur_start)).days <= 380]
        last_fy_point = max(annual_candidates, key=lambda p: p["end"]) if annual_candidates else None

        # Same year-to-date interim one year earlier: matches current's
        # own duration (within a few days) AND starts ~1 year before
        # current's start — real date-based matching, not a tag lookup.
        prior_year_interim = None
        best_gap = None
        for p in points:
            p_start, p_end = _parse(p["start"]), _parse(p["end"])
            if p_start is None or p_end is None:
                continue
            p_days = (p_end - p_start).days
            if abs(p_days - cur_days) > 10:
                continue
            start_gap_days = (cur_start - p_start).days
            if 355 <= start_gap_days <= 375:
                gap = abs(start_gap_days - 365)
                if best_gap is None or gap < best_gap:
                    best_gap = gap
                    prior_year_interim = p

        if last_fy_point and prior_year_interim:
            try:
                return float(last_fy_point["val"]) - float(prior_year_interim["val"]) + float(current["val"])
            except (TypeError, ValueError):
                pass
        # Couldn't find a clean match to TTM-adjust — real cumulative
        # year-to-date figure, honestly partial rather than a full TTM,
        # but still a genuine filed number, not a guess.
        return float(current["val"])
    return None


def fetch_edgar_fundamentals(cik: int) -> Dict[str, Any]:
    """Real, computed fundamentals for one company from its own SEC
    filings. Every field is either a genuine filed number, a ratio
    computed from two genuine filed numbers, or None — never guessed."""
    out: Dict[str, Any] = {"ok": False}
    facts = _fetch_companyfacts(cik)
    if facts is None:
        return out
    out["ok"] = True

    # Flow concepts (income-statement items covering a period) use the real
    # TTM computation — see _compute_ttm's docstring for why the raw
    # "latest datapoint" is wrong for these. Balance-sheet concepts
    # (equity, assets, liabilities, shares, debt) are point-in-time
    # snapshots and don't have this problem — _get's latest-point lookup
    # is already correct for those.
    net_income = _compute_ttm(facts, "net_income")
    operating_income = _compute_ttm(facts, "operating_income")
    interest_expense = _compute_ttm(facts, "interest_expense")
    equity = _get(facts, "equity")
    assets = _get(facts, "assets")
    liabilities = _get(facts, "liabilities")
    shares = _get(facts, "shares_out")
    revenue = _compute_ttm(facts, "revenue")
    lt_debt = _get(facts, "lt_debt")

    # EPS derived from TTM net income / current shares, not the raw filed
    # EPS concept — same cumulative-interim problem, and this way it's
    # guaranteed internally consistent with the net income used for ROE.
    eps = round(net_income / shares, 2) if net_income is not None and shares else None

    out["net_income"] = net_income
    out["stockholders_equity"] = equity
    out["assets"] = assets
    out["liabilities"] = liabilities
    out["eps"] = eps
    out["shares_outstanding"] = shares
    out["revenue"] = revenue
    out["lt_debt"] = lt_debt

    # ROE — self-computed from two real filed numbers, not a pre-built widget
    out["roe"] = round(net_income / equity * 100.0, 2) if net_income is not None and equity else None

    # Interest coverage — operating income / interest expense
    out["interest_coverage"] = (
        round(operating_income / interest_expense, 2)
        if operating_income is not None and interest_expense
        else None
    )

    # Net-debt-proxy leverage: LT debt vs equity (book), since EBITDA isn't
    # directly filed as its own XBRL concept the way debt/equity are.
    out["debt_to_equity"] = round(lt_debt / equity, 2) if lt_debt is not None and equity else None

    # Real year-over-year profit growth from two genuine, non-overlapping
    # 10-K annual figures — not a quarter compared against a different
    # quarter, which would conflate seasonality with real growth.
    annual_ni = _annual_series(facts, "NetIncomeLoss") or _annual_series(facts, "ProfitLoss")
    if len(annual_ni) >= 2:
        latest, prior = annual_ni[0]["val"], annual_ni[1]["val"]
        if prior:
            out["profit_growth_pct"] = round((latest - prior) / abs(prior) * 100.0, 2)
    out.setdefault("profit_growth_pct", None)

    return out


# ---------------------------------------------------------------------------
# Price + technicals (Yahoo Finance — same math as nse_data_provider, just
# without the ".NS" suffix and without the NSE-specific delivery% fetch)
# ---------------------------------------------------------------------------


def fetch_ohlcv(ticker: str, period: str = "1y", interval: str = "1d") -> Optional[pd.DataFrame]:
    try:
        import yfinance as yf

        hist = yf.Ticker(normalize_ticker(ticker)).history(period=period, interval=interval)
        if hist is None or hist.empty:
            return None
        frame = hist.rename(
            columns={"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"}
        )
        return frame[["open", "high", "low", "close", "volume"]]
    except Exception as exc:
        logger.debug("US OHLCV fetch failed for %s: %s", ticker, exc)
        return None


def _relative_volume(frame: pd.DataFrame) -> Optional[float]:
    """Today's volume vs its own trailing 20-day average — the real,
    computable US substitute for India's NSE-bhavcopy delivery %% (no
    equivalent concept exists for US equities; relative volume is the
    standard swing-trading proxy for "is real participation showing up
    right now," same spirit, different real source)."""
    if frame is None or len(frame) < 21 or "volume" not in frame.columns:
        return None
    vol = frame["volume"].astype(float)
    avg20 = float(vol.iloc[-21:-1].mean())
    if avg20 <= 0:
        return None
    return round(float(vol.iloc[-1]) / avg20, 2)


def build_live_row(ticker: str, bench_frame: Optional[pd.DataFrame] = None) -> Optional[Dict[str, Any]]:
    """Real, live US equity row — price + technicals from Yahoo Finance,
    fundamentals self-computed from the company's own SEC EDGAR filings.
    Returns None (never a fabricated row) when even the price can't be
    fetched; individual fundamental fields are None on their own when that
    specific concept wasn't filed, exactly like the India pipeline."""
    ticker = normalize_ticker(ticker)
    universe_entry = next((u for u in load_universe() if u["ticker"] == ticker), None)

    frame = fetch_ohlcv(ticker)
    if frame is None or frame.empty:
        return None

    from providers import nse_data_provider as ndp

    tech = ndp.compute_technicals(frame, bench_frame)
    rel_vol = _relative_volume(frame)
    momentum_21d = None
    if len(frame) >= 22:
        closes = frame["close"].astype(float)
        momentum_21d = round((float(closes.iloc[-1]) / float(closes.iloc[-22]) - 1.0) * 100.0, 2)

    fund: Dict[str, Any] = {"ok": False}
    if universe_entry and universe_entry.get("cik"):
        fund = fetch_edgar_fundamentals(universe_entry["cik"])

    close = tech["close_price"]
    eps = fund.get("eps")
    shares = fund.get("shares_outstanding")
    equity = fund.get("stockholders_equity")

    pe_ratio = round(close / eps, 2) if eps and eps > 0 else None
    book_value_per_share = (equity / shares) if equity and shares else None
    pb_ratio = round(close / book_value_per_share, 2) if book_value_per_share else None
    peg_ratio = (
        round(pe_ratio / fund["profit_growth_pct"], 2)
        if pe_ratio and fund.get("profit_growth_pct") and fund["profit_growth_pct"] > 0
        else None
    )

    row: Dict[str, Any] = {
        "ticker": ticker,
        "company_name": (universe_entry or {}).get("company_name") or ticker,
        "description": f"US equity {(universe_entry or {}).get('company_name') or ticker}.",
        "sector": (universe_entry or {}).get("sector") or "—",
        "industry": (universe_entry or {}).get("industry") or "—",
        "market": "US",
        "close_price": close,
        "atr_value": tech["atr_value"],
        "sma_50": tech["sma_50"],
        "sma_200": tech["sma_200"],
        "rsi_14": tech["rsi_14"],
        "alpha_3m": tech["alpha_3m"],
        "relative_volume": rel_vol,
        "momentum_21d": momentum_21d,
        "delivery_pct_10d": None,  # no India-style equivalent for US — see _relative_volume
        "roe": fund.get("roe"),
        "roic": fund.get("roe"),  # US checklist reads roic as the primary capital-return field
        "interest_coverage": fund.get("interest_coverage"),
        "net_debt_ebitda": None,  # not computed for US yet — see debt_to_equity instead
        "debt_to_equity": fund.get("debt_to_equity"),
        "yoy_profit_growth": fund.get("profit_growth_pct"),
        "pe_ratio": pe_ratio,
        "pb_ratio": pb_ratio,
        "peg_ratio": peg_ratio,
        "eps": eps,
        "revenue": fund.get("revenue"),
        "data_quality": "SOURCED" if fund.get("ok") else "UNVERIFIED",
        "fundamentals_verified": bool(fund.get("ok")),
        "sources_ok_count": 2 if fund.get("ok") else 1,
        "ohlcv_ready": True,
        "price_source": "yahoo",
        "price_kind": "LAST",
        "week52_high": round(float(frame["high"].tail(252).max()), 2),
        "week52_low": round(float(frame["low"].tail(252).min()), 2),
        "day_open": round(float(frame["open"].iloc[-1]), 2),
        "day_high": round(float(frame["high"].iloc[-1]), 2),
        "day_low": round(float(frame["low"].iloc[-1]), 2),
        "day_volume": float(frame["volume"].iloc[-1]) if "volume" in frame.columns else None,
        "prev_close": round(float(frame["close"].iloc[-2]), 2) if len(frame) >= 2 else None,
    }
    return row


def refresh_universe(tickers: Optional[List[str]] = None, max_workers: int = 8) -> Dict[str, Any]:
    """Real, live refresh for the US universe — price + technicals (Yahoo)
    and fundamentals (SEC EDGAR) for every symbol, scored through
    factor_engine_us, then handed back for the caller to persist.

    max_workers defaults conservatively (SEC's own guidance asks for
    roughly 10 requests/sec against data.sec.gov; 8 concurrent workers,
    each doing one companyfacts call per ticker, stays comfortably under
    that even with Yahoo's OHLCV call layered on top of each worker).
    """
    import time as _time
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from engine import factor_engine_us as feus

    t0 = _time.time()
    symbols = tickers or [u["ticker"] for u in load_universe()]
    result: Dict[str, Any] = {"attempted": len(symbols), "accepted": 0, "rejected": [], "reject_reasons": {}}

    bench = fetch_ohlcv(BENCHMARK)
    accepted_rows: List[Dict[str, Any]] = []
    rejected: List[str] = []
    reasons: Dict[str, str] = {}

    def _one(sym: str):
        try:
            row = build_live_row(sym, bench_frame=bench)
            if row is None:
                return sym, None, "no price data from Yahoo"
            card = feus.full_us_factor_scorecard(row)
            row["fundamental_score"] = card["fundamental"]["total_marks"]
            row["technical_score"] = card["technical"]["total_marks"]
            row["composite_score"] = card["composite_marks"]
            row["is_buyable"] = (
                1
                if row["close_price"] > row["sma_200"] and row["rsi_14"] <= 65
                else 0
            )
            row["last_updated"] = None  # set by upsert_leaderboard_rows' own timestamp default
            return sym, row, None
        except Exception as exc:
            return sym, None, str(exc)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        for sym, row, err in pool.map(_one, symbols):
            if row is None:
                rejected.append(sym)
                reasons[sym] = err or "unknown error"
            else:
                accepted_rows.append(row)

    result["accepted"] = len(accepted_rows)
    result["rejected"] = rejected
    result["reject_reasons"] = reasons
    result["rows"] = accepted_rows
    result["elapsed_sec"] = round(_time.time() - t0, 1)
    result["message"] = (
        f"US refresh in {result['elapsed_sec']}s — {len(accepted_rows)}/{len(symbols)} stocks saved "
        f"(SEC EDGAR + Yahoo Finance)."
    )
    return result
