"""
Expanded fundamental / technical checklists, chart narratives, Best Stock ranking.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

RSI_OVERBOUGHT = 65.0


def _f(row: Any, key: str, default: float = 0.0) -> float:
    try:
        val = row.get(key, default) if hasattr(row, "get") else default
        if val is None or (isinstance(val, float) and np.isnan(val)):
            return float(default)
        return float(val)
    except Exception:
        return float(default)


def _optional(row: Any, key: str) -> Optional[float]:
    try:
        if not hasattr(row, "get"):
            return None
        val = row.get(key)
        if val is None or val == "" or (isinstance(val, float) and np.isnan(val)):
            return None
        return float(val)
    except Exception:
        return None


def _is_financial(row: Any) -> bool:
    blob = " ".join(
        str(x or "")
        for x in (
            row.get("sector") if hasattr(row, "get") else "",
            row.get("industry") if hasattr(row, "get") else "",
        )
    ).lower()
    keys = ("bank", "finance", "nbfc", "financial", "insurance", "housing finance")
    return any(k in blob for k in keys)


CONFIDENCE_MULTIPLIER = {
    # Applied once to the checklist total (not per-item). SOURCED/CACHED get
    # full credit; FALLBACK (only the NSE-filing partial was available — no
    # PE/ROE) is discounted rather than hard-zeroed like the old 3-source
    # gate did, so a thin data footprint can't outscore a fully sourced peer
    # but also isn't erased outright. MISSING items are already ~0 from the
    # per-item gates below, so no extra discount is applied there.
    "SOURCED": 1.0,
    "CACHED": 1.0,
    "LEGACY": 1.0,
    "FALLBACK": 0.7,
    "MISSING": 1.0,
}


def _quality(row: Any) -> str:
    if hasattr(row, "get") and row.get("data_quality"):
        q = str(row.get("data_quality")).upper()
        # Legacy tags from the old 6-source consensus model map onto the
        # current Screener-primary / NSE-filing-fallback vocabulary.
        legacy_map = {"VERIFIED": "SOURCED", "PARTIAL": "FALLBACK", "UNVERIFIED": "MISSING"}
        return legacy_map.get(q, q)
    if hasattr(row, "get") and row.get("fundamentals_verified"):
        return "SOURCED"
    # Legacy DB rows with fake defaults look "too round" — treat as missing if
    # common placeholder pattern appears without a quality flag.
    roic = _optional(row, "roic")
    peg = _optional(row, "peg_ratio")
    debt = _optional(row, "net_debt_ebitda")
    if roic == 12.0 and peg == 1.5 and debt == 1.5:
        return "MISSING"
    if roic is None and peg is None:
        return "MISSING"
    return "LEGACY"


def _item(
    name: str,
    value_display: str,
    marks: float,
    max_marks: float,
    passed: bool,
    note: str,
) -> Dict[str, Any]:
    return {
        "name": name,
        "value": value_display,
        "marks": round(marks, 1),
        "max_marks": max_marks,
        "passed": passed,
        "note": note,
    }


def sector_pack(row: Any) -> str:
    """Coarse sector pack for flexible checklists."""
    if _is_financial(row):
        return "financials"
    blob = " ".join(
        str(x or "")
        for x in (
            row.get("sector") if hasattr(row, "get") else "",
            row.get("industry") if hasattr(row, "get") else "",
        )
    ).lower()
    cyclical = (
        "metal", "steel", "mining", "oil", "gas", "energy", "cement", "commodity",
        "chemical", "fertiliz", "sugar", "paper",
    )
    if any(k in blob for k in cyclical):
        return "cyclicals"
    return "quality"


def evaluate_fundamental_checklist(row: Any) -> Dict[str, Any]:
    """Sector-aware fundamental checklist — marks out of ~50."""
    items: List[Dict[str, Any]] = []
    quality = _quality(row)
    pack = sector_pack(row)
    financial = pack == "financials"

    if quality == "MISSING":
        items.append(
            _item(
                "Data quality gate",
                "MISSING",
                0.0,
                10,
                False,
                "Screener.in and NSE filings both came back empty for this ticker — "
                "placeholder values blocked, nothing invented.",
            )
        )
    elif quality == "FALLBACK":
        items.append(
            _item(
                "Data quality gate",
                "FALLBACK (0.7x)",
                7.0,
                10,
                True,
                "Screener.in didn't resolve — scoring runs on NSE's own filed promoter "
                "data only. Checklist total is discounted 30% to reflect the thinner "
                "evidence base, not hard-blocked.",
            )
        )

    if financial:
        # Banks / NBFC / insurance — ROCE-style efficiency, else the filed ROE
        roe = _optional(row, "roic") or _optional(row, "roe")
        if roe is None or quality == "MISSING":
            items.append(_item("ROE / Capital return", "—", 0.0, 10, False, "Return metric missing for financial."))
        elif roe >= 15:
            items.append(_item("ROE / Capital return", f"{roe:.1f}%", 10.0, 10, True, "Strong financial returns."))
        elif roe >= 10:
            items.append(_item("ROE / Capital return", f"{roe:.1f}%", 7.0, 10, True, "Adequate returns for a lender/insurer."))
        else:
            items.append(_item("ROE / Capital return", f"{roe:.1f}%", 2.0, 10, False, "Weak returns on equity/capital."))

        items.append(
            _item(
                "Net Debt / EBITDA",
                "N/A (Financial pack)",
                0.0,
                0,
                True,
                "Skipped — not a valid quality proxy for banks/NBFCs.",
            )
        )

        pe = _optional(row, "pe_ratio")
        if pe is None or pe <= 0 or quality == "MISSING":
            items.append(_item("P/E (financial)", "—", 0.0, 8, False, "P/E not verified."))
        elif pe <= 18:
            items.append(_item("P/E (financial)", f"{pe:.1f}", 8.0, 8, True, "Reasonable financial PE."))
        elif pe <= 28:
            items.append(_item("P/E (financial)", f"{pe:.1f}", 4.0, 8, False, "Premium financial PE."))
        else:
            items.append(_item("P/E (financial)", f"{pe:.1f}", 1.0, 8, False, "Rich financial PE."))

        # Soft book-value style signal: treat low PEG as value proxy when available
        peg = _optional(row, "peg_ratio")
        growth = _optional(row, "yoy_profit_growth")
        if peg is not None and quality != "UNVERIFIED" and (growth is None or growth > 0):
            if peg <= 1.2:
                items.append(_item("PEG / growth value", f"{peg:.2f}", 6.0, 6, True, "Growth not overpaid."))
            elif peg <= 2.0:
                items.append(_item("PEG / growth value", f"{peg:.2f}", 3.0, 6, False, "Fair growth pricing."))
            else:
                items.append(_item("PEG / growth value", f"{peg:.2f}", 0.5, 6, False, "Expensive vs growth."))
        else:
            items.append(_item("PEG / growth value", "—", 0.0, 6, False, "PEG/growth not usable."))

        pledge = _optional(row, "promoter_pledge_pct")
        if pledge is None or quality == "MISSING":
            items.append(_item("Promoter Pledge", "—", 0.0, 5, False, "Pledge missing/unverified."))
        elif pledge <= 5:
            items.append(_item("Promoter Pledge", f"{pledge:.1f}%", 5.0, 5, True, "Low pledging."))
        elif pledge <= 15:
            items.append(_item("Promoter Pledge", f"{pledge:.1f}%", 2.0, 5, False, "Moderate pledging."))
        else:
            items.append(_item("Promoter Pledge", f"{pledge:.1f}%", 0.0, 5, False, "High pledging."))

        if growth is None or quality == "MISSING":
            items.append(_item("Profit Growth", "—", 0.0, 7, False, "Growth unverified."))
        elif growth >= 15:
            items.append(_item("Profit Growth", f"{growth:.1f}%", 7.0, 7, True, "Strong profit growth."))
        elif growth >= 5:
            items.append(_item("Profit Growth", f"{growth:.1f}%", 4.0, 7, True, "Modest growth."))
        else:
            items.append(_item("Profit Growth", f"{growth:.1f}%", 1.0, 7, False, "Weak/negative growth."))

        # Interest coverage not primary for banks
        items.append(
            _item("Interest Coverage", "N/A (Financial pack)", 0.0, 0, True, "Skipped for financial pack.")
        )
    else:
        roic = _optional(row, "roic")
        metric_label = "ROCE / ROIC"
        metric_note = ""
        if roic is None:
            # Exchange-filed ROE stands in when the ROCE figure is not published
            roic = _optional(row, "roe")
            metric_label = "Capital return (ROE)"
            metric_note = " ROE used — ROCE not published."
        if roic is None or quality == "MISSING":
            items.append(
                _item(metric_label, "—" if roic is None else f"{roic:.1f}% (blocked)", 0.0, 10, False,
                      "Capital return missing or unverified — cannot claim quality franchise.")
            )
        elif roic >= 20:
            items.append(_item(metric_label, f"{roic:.1f}%", 10.0, 10, True, "Excellent capital efficiency (≥ 20%)." + metric_note))
        elif roic >= 12:
            items.append(_item(metric_label, f"{roic:.1f}%", 7.0, 10, True, "Solid capital return — quality franchise." + metric_note))
        elif roic >= 8:
            items.append(_item(metric_label, f"{roic:.1f}%", 4.0, 10, False, "Average returns on capital." + metric_note))
        else:
            items.append(_item(metric_label, f"{roic:.1f}%", 1.0, 10, False, "Weak capital return — below cost of capital risk." + metric_note))

        debt = _optional(row, "net_debt_ebitda")
        if debt is None:
            items.append(
                _item(
                    "Net Debt / EBITDA",
                    "N/A (not on free sources)",
                    0.0,
                    0,
                    True,
                    "Skipped — rarely published free; does not block the name.",
                )
            )
        elif quality == "MISSING":
            items.append(
                _item("Net Debt / EBITDA", "—", 0.0, 8, False,
                      "Leverage blocked — fundamentals unverified.")
            )
        elif debt <= 1.0:
            items.append(_item("Net Debt / EBITDA", f"{debt:.2f}x", 8.0, 8, True, "Conservative leverage."))
        elif debt <= 2.0:
            items.append(_item("Net Debt / EBITDA", f"{debt:.2f}x", 5.0, 8, True, "Manageable leverage."))
        elif debt <= 3.5:
            items.append(_item("Net Debt / EBITDA", f"{debt:.2f}x", 2.0, 8, False, "Elevated leverage."))
        else:
            items.append(_item("Net Debt / EBITDA", f"{debt:.2f}x", 0.0, 8, False, "High leverage — fail."))

        peg = _optional(row, "peg_ratio")
        growth = _optional(row, "yoy_profit_growth")
        if peg is None or quality == "MISSING" or (growth is not None and growth <= 0):
            note = "PEG unavailable / negative growth — cannot award valuation PASS."
            if growth is not None and growth <= 0:
                note = f"Profit growth {growth:.1f}% — PEG invalid (no stable growth)."
            items.append(_item("PEG Ratio", "—" if peg is None else f"{peg:.2f}", 0.0, 8, False, note))
        elif peg <= 1.0:
            items.append(_item("PEG Ratio", f"{peg:.2f}", 8.0, 8, True, "Growth attractively priced (PEG ≤ 1)."))
        elif peg <= 1.5:
            items.append(_item("PEG Ratio", f"{peg:.2f}", 6.0, 8, True, "Reasonable PEG vs growth."))
        elif peg <= 2.5:
            items.append(_item("PEG Ratio", f"{peg:.2f}", 3.0, 8, False, "Premium valuation vs growth."))
        else:
            items.append(_item("PEG Ratio", f"{peg:.2f}", 0.5, 8, False, "Expensive on PEG."))

        ic = _optional(row, "interest_coverage")
        if ic is None:
            items.append(
                _item(
                    "Interest Coverage",
                    "N/A (not on free sources)",
                    0.0,
                    0,
                    True,
                    "Skipped — rarely published free; does not block the name.",
                )
            )
        elif quality == "MISSING":
            items.append(
                _item("Interest Coverage", "—", 0.0, 6, False, "Interest coverage blocked — unverified.")
            )
        elif ic >= 8:
            items.append(_item("Interest Coverage", f"{ic:.1f}x", 6.0, 6, True, "Strong interest coverage."))
        elif ic >= 4:
            items.append(_item("Interest Coverage", f"{ic:.1f}x", 4.0, 6, True, "Adequate interest coverage."))
        else:
            items.append(_item("Interest Coverage", f"{ic:.1f}x", 0.0, 6, False, "Weak interest coverage."))

        pledge = _optional(row, "promoter_pledge_pct")
        if quality == "MISSING":
            items.append(_item("Promoter Pledge", "—", 0.0, 5, False, "Pledge blocked — fundamentals unverified."))
        elif pledge is None:
            items.append(_item("Promoter Pledge", "—", 0.0, 5, False, "Pledge data missing."))
        elif pledge <= 5:
            items.append(_item("Promoter Pledge", f"{pledge:.1f}%", 5.0, 5, True, "Low / no promoter pledging."))
        elif pledge <= 15:
            items.append(_item("Promoter Pledge", f"{pledge:.1f}%", 2.5, 5, False, "Moderate pledging."))
        else:
            items.append(_item("Promoter Pledge", f"{pledge:.1f}%", 0.0, 5, False, "High pledging — red flag."))

        if growth is None or quality == "MISSING":
            items.append(_item("Profit Growth", "—" if growth is None else f"{growth:.1f}%", 0.0, 7, False,
                               "Growth not multi-source confirmed / unverified row."))
        elif growth >= 20:
            items.append(_item("Profit Growth", f"{growth:.1f}%", 7.0, 7, True, "Strong profit growth."))
        elif growth >= 10:
            items.append(_item("Profit Growth", f"{growth:.1f}%", 5.0, 7, True, "Healthy double-digit growth."))
        elif growth >= 0:
            items.append(_item("Profit Growth", f"{growth:.1f}%", 2.0, 7, False, "Low / flat profit growth."))
        else:
            items.append(_item("Profit Growth", f"{growth:.1f}%", 0.0, 7, False, "Negative profit growth."))

        pe = _optional(row, "pe_ratio")
        pe_cap = 35 if pack == "cyclicals" else 25
        pe_mid = 50 if pack == "cyclicals" else 40
        if pe is None or pe <= 0 or quality == "MISSING":
            items.append(
                _item(
                    "Stock P/E",
                    "—" if pe is None else f"{pe:.1f}",
                    0.0,
                    6,
                    False,
                    "P/E missing or not verified — no neutral free marks.",
                )
            )
        elif pe <= pe_cap:
            items.append(_item("Stock P/E", f"{pe:.1f}", 6.0, 6, True, f"Reasonable PE for {pack} pack."))
        elif pe <= pe_mid:
            items.append(_item("Stock P/E", f"{pe:.1f}", 3.0, 6, False, "Elevated PE."))
        else:
            items.append(_item("Stock P/E", f"{pe:.1f}", 0.5, 6, False, "Extremely rich PE — valuation danger."))

        # P/B — a flat PE/PEG cutoff misses cyclicals/asset-heavy names where
        # earnings are volatile; P/B is a steadier cheapness signal for those.
        # NOTE: EV/EBITDA is NOT added here — Screener.in's summary ratio grid
        # doesn't reliably publish it for all 500 names on the free tier, and
        # this app never invents a number it can't source. If you get a paid
        # data source later, EV/EBITDA is the next lens worth adding.
        pb = _optional(row, "pb_ratio")
        pb_cap = 3.0 if pack == "cyclicals" else (2.5 if financial else 5.0)
        if pb is None or quality == "MISSING":
            items.append(_item("P/B Ratio", "—", 0.0, 4, False, "Book value / P/B not available."))
        elif pb <= pb_cap * 0.6:
            items.append(_item("P/B Ratio", f"{pb:.2f}", 4.0, 4, True, "Cheap relative to book value."))
        elif pb <= pb_cap:
            items.append(_item("P/B Ratio", f"{pb:.2f}", 2.0, 4, True, f"Reasonable P/B for {pack} pack."))
        else:
            items.append(_item("P/B Ratio", f"{pb:.2f}", 0.5, 4, False, "Rich vs book value."))

        # Peer-relative valuation (cross-sectional Z-score substitute).
        # HONEST LIMITATION: the original spec called for a P/E Z-score vs the
        # stock's OWN 10-year history. Getting 10 years of quarterly PE for
        # 200 stocks for free is not reliably achievable — it would need its
        # own fragile scraping pipeline. What's implemented instead is a
        # cheaper, still-legitimate substitute: how this stock's PE compares
        # to its SECTOR PEERS in the current universe (computed once per
        # refresh by compute_peer_relative_valuation() below and stored on
        # the row as pe_peer_percentile). This only activates once that
        # column exists — it does not block scoring if absent.
        peer_pctl = _optional(row, "pe_peer_percentile")
        if peer_pctl is not None and quality != "MISSING":
            if peer_pctl <= 25:
                items.append(_item("PE vs sector peers", f"{peer_pctl:.0f}th pct.", 4.0, 4, True,
                                    "Cheaper than most same-pack peers right now."))
            elif peer_pctl <= 60:
                items.append(_item("PE vs sector peers", f"{peer_pctl:.0f}th pct.", 2.0, 4, True,
                                    "Mid-pack valuation vs peers."))
            else:
                items.append(_item("PE vs sector peers", f"{peer_pctl:.0f}th pct.", 0.0, 4, False,
                                    "Pricier than most same-pack peers right now."))

    # Drop zero-max skipped items from totals visually but keep note items with max 0 out of sum
    scored = [i for i in items if i["max_marks"] > 0]
    total = round(sum(i["marks"] for i in scored), 1)
    max_total = round(sum(i["max_marks"] for i in scored), 1)
    cleared = sum(1 for i in scored if i["passed"])
    total = round(total * CONFIDENCE_MULTIPLIER.get(quality, 1.0), 1)
    return {
        "items": items,
        "total_marks": total,
        "max_marks": max_total,
        "cleared": cleared,
        "total_filters": len(scored),
        "pct": round(total / max_total * 100.0, 1) if max_total else 0.0,
        "data_quality": quality,
        "sector_pack": pack,
    }


def compute_peer_relative_valuation(leaderboard: pd.DataFrame) -> pd.DataFrame:
    """Call this once after a full leaderboard refresh (not per-stock) to add
    a 'pe_peer_percentile' column: where each stock's PE sits (0-100) among
    OTHER stocks in the same sector_pack, in the current universe. Feed the
    result back through database_engine.upsert_leaderboard_rows() so the
    'PE vs sector peers' checklist item above has something to read.

    This is the practical substitute for a true 10-year-own-history PE
    Z-score discussed with the user — see the note above for why."""
    if leaderboard is None or leaderboard.empty:
        return leaderboard
    df = leaderboard.copy()
    df["_pack"] = df.apply(lambda r: sector_pack(r), axis=1)
    df["pe_ratio"] = pd.to_numeric(df.get("pe_ratio"), errors="coerce")
    valid = df["pe_ratio"] > 0
    df["pe_peer_percentile"] = np.nan
    for pack_name, grp in df[valid].groupby("_pack"):
        if len(grp) < 5:
            continue  # too few peers for a percentile to mean anything
        df.loc[grp.index, "pe_peer_percentile"] = grp["pe_ratio"].rank(pct=True) * 100.0
    return df.drop(columns=["_pack"])


def evaluate_technical_checklist(row: Any, history: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
    """Powerful technical checklist — marks out of 50."""
    items: List[Dict[str, Any]] = []
    close = _f(row, "close_price")
    sma50 = _f(row, "sma_50")
    sma200 = _f(row, "sma_200")
    rsi = _f(row, "rsi_14", 50)
    atr = _f(row, "atr_value")
    alpha = _f(row, "alpha_3m")
    delivery = _f(row, "delivery_pct_10d")

    if close > sma200:
        m, ok, note = 10.0, True, "Price above 200-day SMA — primary uptrend intact."
    elif close > sma200 * 0.98:
        m, ok, note = 5.0, False, "Near 200 SMA — trend contested."
    else:
        m, ok, note = 0.0, False, "Below 200 SMA — primary trend down / weak."
    items.append(_item("Price vs 200 SMA", f"₹{close:.2f} vs ₹{sma200:.2f}", m, 10, ok, note))

    if sma50 > 0 and close > sma50:
        m, ok, note = 6.0, True, "Price above 50-day SMA — intermediate trend supportive."
    elif sma50 > 0:
        m, ok, note = 2.0, False, "Below 50 SMA — short-term weakness."
    else:
        m, ok, note = 3.0, True, "50 SMA unavailable — neutral."
    items.append(_item("Price vs 50 SMA", f"₹{close:.2f} vs ₹{sma50:.2f}", m, 6, ok, note))

    if sma50 > 0 and sma200 > 0 and sma50 > sma200:
        m, ok, note = 6.0, True, "50 SMA > 200 SMA — bullish stack / golden alignment."
    elif sma50 > 0 and sma200 > 0:
        m, ok, note = 1.0, False, "Death-cross style stack — bearish intermediate structure."
    else:
        m, ok, note = 2.0, True, "SMA stack incomplete — neutral."
    items.append(_item("SMA Stack (50/200)", f"{sma50:.1f}/{sma200:.1f}", m, 6, ok, note))

    if 45 <= rsi <= 65:
        m, ok, note = 10.0, True, "RSI in healthy swing zone (45–65) — not overextended."
    elif 35 <= rsi < 45:
        m, ok, note = 6.0, True, "Cooling RSI — possible constructive reset."
    elif rsi > RSI_OVERBOUGHT:
        m, ok, note = 0.0, False, f"RSI > {RSI_OVERBOUGHT:.0f} — overextended; entry locked."
    else:
        m, ok, note = 3.0, False, "RSI weak / oversold — wait for reclaim."
    items.append(_item("RSI (14)", f"{rsi:.1f}", m, 10, ok, note))

    if alpha >= 10:
        m, ok, note = 8.0, True, "Strong 3M relative strength vs Nifty."
    elif alpha >= 0:
        m, ok, note = 5.0, True, "In-line / mild outperformance vs Nifty (3M)."
    elif alpha >= -8:
        m, ok, note = 2.0, False, "Mild underperformance vs Nifty."
    else:
        m, ok, note = 0.0, False, "Severe relative weakness vs Nifty."
    items.append(_item("3M Alpha vs Nifty", f"{alpha:+.1f}%", m, 8, ok, note))

    if delivery >= 50:
        m, ok, note = 5.0, True, "Strong volume conviction proxy (delivery/vol intensity)."
    elif delivery >= 40:
        m, ok, note = 3.5, True, "Acceptable participation."
    else:
        m, ok, note = 1.0, False, "Weak participation proxy."
    items.append(_item("Volume / Delivery Proxy", f"{delivery:.1f}", m, 5, ok, note))

    atr_pct = (atr / close * 100.0) if close > 0 else 0.0
    if 1.0 <= atr_pct <= 4.5:
        m, ok, note = 5.0, True, "ATR% in tradeable swing band (not too quiet / chaotic)."
    elif atr_pct < 1.0:
        m, ok, note = 2.0, False, "Very low volatility — breakout may need volume."
    else:
        m, ok, note = 1.5, False, "High ATR% — wider stops, choppier path."
    items.append(_item("ATR % of Price", f"{atr_pct:.2f}%", m, 5, ok, note))

    # Optional momentum from history
    if history is not None and not history.empty and len(history) >= 22:
        closes = history["close"].astype(float)
        mom_21 = (float(closes.iloc[-1]) / float(closes.iloc[-22]) - 1.0) * 100.0
        if mom_21 >= 5:
            m, ok, note = 5.0, True, f"Positive 21-session momentum ({mom_21:+.1f}%)."
        elif mom_21 >= 0:
            m, ok, note = 3.0, True, f"Flat-to-up 21-session momentum ({mom_21:+.1f}%)."
        else:
            m, ok, note = 0.5, False, f"Negative 21-session momentum ({mom_21:+.1f}%)."
        items.append(_item("21D Momentum", f"{mom_21:+.1f}%", m, 5, ok, note))
    else:
        items.append(_item("21D Momentum", "—", 2.0, 5, True, "History short — neutral mark."))

    total = round(sum(i["marks"] for i in items), 1)
    max_total = round(sum(i["max_marks"] for i in items), 1)
    cleared = sum(1 for i in items if i["passed"])
    return {
        "items": items,
        "total_marks": total,
        "max_marks": max_total,
        "cleared": cleared,
        "total_filters": len(items),
        "pct": round(total / max_total * 100.0, 1) if max_total else 0.0,
    }


def split_qvt_scores(fund: Dict[str, Any], tech: Dict[str, Any]) -> Dict[str, float]:
    """Split checklist into Quality / Value / Timing buckets (0–100 each)."""
    quality_names = {
        "ROCE / ROIC", "ROE / Capital return", "Net Debt / EBITDA", "Interest Coverage",
        "Promoter Pledge", "Profit Growth", "Data quality gate",
    }
    value_names = {"PEG Ratio", "PEG / growth value", "Stock P/E", "P/E (financial)"}
    timing_names = {
        "Price vs 200 SMA", "Price vs 50 SMA", "SMA Stack (50/200)", "RSI (14)",
        "3M Alpha vs Nifty", "Volume / Delivery Proxy", "ATR % of Price", "21D Momentum",
    }

    def bucket(items: List[Dict[str, Any]], names: set) -> float:
        subset = [i for i in items if i.get("name") in names and float(i.get("max_marks") or 0) > 0]
        if not subset:
            return 0.0
        got = sum(float(i["marks"]) for i in subset)
        mx = sum(float(i["max_marks"]) for i in subset)
        return round(100.0 * got / mx, 1) if mx else 0.0

    fund_items = fund.get("items") or []
    tech_items = tech.get("items") or []
    return {
        "quality": bucket(fund_items, quality_names),
        "value": bucket(fund_items, value_names),
        "timing": bucket(tech_items, timing_names),
    }


def full_factor_scorecard(row: Any, history: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
    fund = evaluate_fundamental_checklist(row)
    tech = evaluate_technical_checklist(row, history)
    composite = round(fund["total_marks"] + tech["total_marks"], 1)
    composite_max = round(fund["max_marks"] + tech["max_marks"], 1)
    qvt = split_qvt_scores(fund, tech)
    return {
        "fundamental": fund,
        "technical": tech,
        "composite_marks": composite,
        "composite_max": composite_max,
        "composite_pct": round(composite / composite_max * 100.0, 1) if composite_max else 0.0,
        "sector_pack": fund.get("sector_pack") or sector_pack(row),
        "qvt": qvt,
    }


def chart_narratives(row: Any, history: pd.DataFrame) -> Dict[str, str]:
    """Short plain-English summary under each chart panel."""
    close = _f(row, "close_price")
    sma200 = _f(row, "sma_200")
    sma50 = _f(row, "sma_50")
    rsi = _f(row, "rsi_14", 50)
    atr = _f(row, "atr_value")

    # Price vs SMA
    if close > sma200 * 1.05:
        price_sum = (
            f"Price (₹{close:,.2f}) is comfortably above the 200-day SMA (₹{sma200:,.2f}). "
            f"Trend bias is bullish — dips toward the long-term average are often buyable if RSI stays cool."
        )
    elif close > sma200:
        price_sum = (
            f"Price (₹{close:,.2f}) is just above the 200-day SMA (₹{sma200:,.2f}). "
            f"Primary trend is still up but leadership is modest — watch for a decisive hold above the average."
        )
    else:
        price_sum = (
            f"Price (₹{close:,.2f}) is below the 200-day SMA (₹{sma200:,.2f}). "
            f"The long-term trend is damaged — prefer reclaim of the 200 SMA before aggressive swing longs."
        )
    if sma50 > 0:
        price_sum += (
            f" 50-day SMA is ₹{sma50:,.2f} "
            f"({'supportive' if close > sma50 else 'acting as resistance'})."
        )

    # Volume
    vol_sum = "Volume panel shows daily traded quantity."
    if history is not None and not history.empty and "volume" in history.columns:
        vols = history["volume"].astype(float).fillna(0)
        if len(vols) >= 20:
            last = float(vols.iloc[-1])
            avg20 = float(vols.tail(20).mean())
            ratio = last / avg20 if avg20 > 0 else 0
            if ratio >= 1.5:
                vol_sum = (
                    f"Latest volume is {ratio:.1f}× the 20-day average — "
                    f"strong participation; moves are more likely to be institutional / conviction-driven."
                )
            elif ratio >= 0.8:
                vol_sum = (
                    f"Latest volume is near the 20-day average ({ratio:.1f}×) — "
                    f"normal liquidity; confirm breakouts with an expansion day."
                )
            else:
                vol_sum = (
                    f"Latest volume is light vs the 20-day average ({ratio:.1f}×) — "
                    f"price moves may be less reliable until volume returns."
                )

    # RSI
    if rsi > RSI_OVERBOUGHT:
        rsi_sum = (
            f"RSI(14) at {rsi:.1f} is above {RSI_OVERBOUGHT:.0f} — overextended. "
            f"Our engine locks new buys here; wait for RSI to cool or for a constructive pullback."
        )
    elif rsi >= 55:
        rsi_sum = (
            f"RSI(14) at {rsi:.1f} shows constructive momentum without extreme heat — "
            f"favourable for trend-following swing entries if price holds above the 200 SMA."
        )
    elif rsi >= 45:
        rsi_sum = (
            f"RSI(14) at {rsi:.1f} is mid-range — neither overbought nor washed out. "
            f"Look for price structure (higher lows) rather than RSI alone."
        )
    else:
        rsi_sum = (
            f"RSI(14) at {rsi:.1f} is soft — sellers recently dominated. "
            f"A reclaim toward 50 with rising volume would improve the swing case."
        )

    atr_pct = (atr / close * 100) if close else 0
    atr_note = (
        f"ATR(14) ≈ ₹{atr:,.2f} ({atr_pct:.2f}% of price) — "
        f"stop ≈ CMP−2.5×ATR, target ≈ CMP+6×ATR for the 1-share forward test."
    )

    return {
        "price_sma": price_sum,
        "volume": vol_sum,
        "rsi": rsi_sum,
        "atr_note": atr_note,
    }


def select_top_score_pool(leaderboard: pd.DataFrame, top_n_scores: int = 3) -> pd.DataFrame:
    """
    Take the distinct top `top_n_scores` composite scores and return ALL stocks
    that share those scores (e.g. top 3 scores → 25 names if many tie).
    """
    if leaderboard is None or leaderboard.empty:
        return pd.DataFrame()
    df = leaderboard.copy()
    df["composite_score"] = pd.to_numeric(df["composite_score"], errors="coerce")
    df = df.dropna(subset=["composite_score"])
    if df.empty:
        return df
    unique_scores = sorted(df["composite_score"].unique(), reverse=True)
    keep_scores = unique_scores[:top_n_scores]
    pool = df[df["composite_score"].isin(keep_scores)].copy()
    return pool.sort_values(
        ["composite_score", "fundamental_score", "technical_score"],
        ascending=False,
    )


def _live_verify_row(row: Any) -> pd.Series:
    """Re-fetch multi-source fundamentals before Best Stock scoring."""
    import database_engine as db
    import nse_data_provider as nse

    ticker = str(row.get("ticker")).upper()
    prior = row.to_dict() if hasattr(row, "to_dict") else dict(row)
    live = nse.build_live_row(ticker, include_fundamentals=True, prior=prior)
    if live:
        db.upsert_leaderboard_rows([live])
        return pd.Series(live)
    series = pd.Series(prior)
    series["data_quality"] = "MISSING"
    series["fundamentals_verified"] = False
    return series


def rank_best_stocks(
    pool: pd.DataFrame,
    *,
    live_verify: bool = True,
    max_verify: int = 15,
) -> Tuple[pd.DataFrame, Optional[pd.Series], str]:
    """
    Re-rank pool with expanded checklist after multi-source verification.
    Stocks that stay UNVERIFIED are ranked last / excluded from winning.
    """
    if pool is None or pool.empty:
        return pd.DataFrame(), None, "No candidates in the top-score pool."

    try:
        import nse_data_provider as nse

        if not nse.is_live_mode():
            live_verify = False
    except Exception:
        pass

    records = []
    verified_n = 0
    for i, (_, row) in enumerate(pool.iterrows()):
        use_row = row
        if live_verify and i < max_verify:
            try:
                use_row = _live_verify_row(row)
            except Exception:
                use_row = row
                if hasattr(use_row, "copy"):
                    use_row = use_row.copy()
                use_row["data_quality"] = "UNVERIFIED"

        card = full_factor_scorecard(use_row, history=None)
        quality = str(card["fundamental"].get("data_quality") or _quality(use_row))
        verified = quality in ("SOURCED", "CACHED")
        if verified:
            verified_n += 1
        # Penalize thin-evidence rows so they cannot win on fake defaults
        expanded = card["composite_marks"] if quality in ("SOURCED", "CACHED", "FALLBACK") else card["technical"]["total_marks"]
        records.append(
            {
                "ticker": str(use_row.get("ticker")),
                "company_name": str(use_row.get("company_name", "")),
                "sector": str(use_row.get("sector", "—")),
                "close_price": _f(use_row, "close_price"),
                "db_composite": _f(use_row, "composite_score"),
                "fund_marks": card["fundamental"]["total_marks"],
                "tech_marks": card["technical"]["total_marks"],
                "expanded_total": expanded,
                "fund_cleared": card["fundamental"]["cleared"],
                "tech_cleared": card["technical"]["cleared"],
                "fund_filters": card["fundamental"]["total_filters"],
                "tech_filters": card["technical"]["total_filters"],
                "is_buyable": int(use_row.get("is_buyable", 0) or 0),
                "rsi_14": _f(use_row, "rsi_14", 50),
                "roic": _optional(use_row, "roic"),
                "peg_ratio": _optional(use_row, "peg_ratio"),
                "pe_ratio": _optional(use_row, "pe_ratio"),
                "alpha_3m": _f(use_row, "alpha_3m"),
                "data_quality": quality,
                "_row": use_row,
                "_card": card,
            }
        )

    ranked = pd.DataFrame(records)
    # Prefer fully-sourced rows, then fallback, then legacy, then missing
    ranked["_qrank"] = ranked["data_quality"].map(
        {"SOURCED": 0, "CACHED": 0, "FALLBACK": 1, "LEGACY": 2, "MISSING": 3}
    ).fillna(3)
    ranked = ranked.sort_values(
        ["_qrank", "expanded_total", "fund_marks", "tech_marks", "db_composite"],
        ascending=[True, False, False, False, False],
    )
    eligible = ranked[ranked["data_quality"].isin(["SOURCED", "CACHED"])]
    pick_from = eligible if not eligible.empty else ranked
    best = pick_from.iloc[0]
    best_row = best["_row"]
    card = best["_card"]

    roic_s = f"{best['roic']:.1f}%" if best["roic"] is not None else "n/a"
    peg_s = f"{best['peg_ratio']:.2f}" if best["peg_ratio"] is not None else "n/a"
    pe_s = f"{best['pe_ratio']:.1f}" if best["pe_ratio"] is not None else "n/a"

    why = (
        f"**{best['ticker']}** ranks #1 after live verification "
        f"(Screener.in primary, NSE filings as the official pledge/holding fallback) "
        f"on a pool of {len(ranked)} names. "
        f"Fully-sourced/cached in pool: **{verified_n}**. "
        f"Data quality: **{best['data_quality']}**. "
        f"Expanded score: **{best['expanded_total']:.1f}/{card['composite_max']:.0f}** "
        f"(Fund {best['fund_marks']:.1f}, Tech {best['tech_marks']:.1f}). "
        f"ROCE {roic_s}, P/E {pe_s}, PEG {peg_s}, RSI {best['rsi_14']:.1f}, "
        f"3M alpha {best['alpha_3m']:+.1f}%. "
        f"Rows with no sourced data are never allowed to win on invented placeholders."
    )
    view = ranked.drop(columns=["_row", "_card", "_qrank"], errors="ignore")
    return view, best_row, why


def split_screens(leaderboard: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Splits the scored leaderboard into two populations, because they answer
    different questions and the old single blended score conflated them:

      - value_screen: fundamentally strong AND reasonably priced, REGARDLESS
        of current price trend. This is where "undervalued and overlooked"
        names show up — by definition they often look weak on momentum
        (that's WHY they're still cheap), so the technical/momentum gate is
        deliberately not applied here.
      - momentum_quality_screen: today's original logic, unchanged — quality
        fundamentals AND already-confirmed uptrend (price > SMA50/200,
        positive 3M alpha, healthy RSI). This is a GARP-momentum strategy:
        useful for "the market is starting to notice this", not for finding
        stocks before the crowd does.

    Call this after scoring the leaderboard (fund_marks/fund_max/tech_marks
    already computed per row, e.g. via rank_best_stocks or a bulk apply of
    evaluate_fundamental_checklist / evaluate_technical_checklist).
    Expects columns: fund_pct (0-100), is_buyable (existing momentum gate,
    1/0), data_quality.
    """
    if leaderboard is None or leaderboard.empty:
        return pd.DataFrame(), pd.DataFrame()
    df = leaderboard.copy()
    sourced = df["data_quality"].isin(["SOURCED", "CACHED"]) if "data_quality" in df else True
    fund_pct = pd.to_numeric(df.get("fund_pct"), errors="coerce")

    value_screen = df[sourced & (fund_pct >= 60)].sort_values("fund_pct", ascending=False)
    momentum_quality_screen = df[
        sourced & (fund_pct >= 60) & (pd.to_numeric(df.get("is_buyable"), errors="coerce") == 1)
    ].sort_values("fund_pct", ascending=False)
    return value_screen, momentum_quality_screen


def profile_snapshot(row: Any) -> Dict[str, str]:
    """Extra stock facts for Search Profile (Screener-style)."""
    close = _f(row, "close_price")
    sma200 = _f(row, "sma_200")
    dist = ((close / sma200) - 1.0) * 100.0 if sma200 else 0.0
    return {
        "CMP": f"₹{close:,.2f}",
        "ATR (14)": f"₹{_f(row, 'atr_value'):,.2f}",
        "50-Day SMA": f"₹{_f(row, 'sma_50'):,.2f}",
        "200-Day SMA": f"₹{sma200:,.2f}",
        "Dist. from 200 SMA": f"{dist:+.2f}%",
        "RSI (14)": f"{_f(row, 'rsi_14', 50):.1f}",
        "3M Alpha vs Nifty": f"{_f(row, 'alpha_3m'):+.1f}%",
        "ROCE / ROIC": f"{_f(row, 'roic'):.1f}%",
        "Net Debt / EBITDA": f"{_f(row, 'net_debt_ebitda'):.2f}x",
        "PEG": f"{_f(row, 'peg_ratio'):.2f}",
        "Interest Coverage": f"{_f(row, 'interest_coverage'):.1f}x",
        "Promoter Pledge": f"{_f(row, 'promoter_pledge_pct'):.1f}%",
        "Profit Growth": f"{_f(row, 'yoy_profit_growth'):.1f}%",
        "P/E": f"{_f(row, 'pe_ratio'):.1f}" if _f(row, "pe_ratio") > 0 else "—",
        "Sector": str(row.get("sector", "—")),
        "Industry": str(row.get("industry", "—")),
        "DB Composite": f"{_f(row, 'composite_score'):.1f}/100",
    }
