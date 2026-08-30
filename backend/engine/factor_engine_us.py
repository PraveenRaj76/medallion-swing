"""
US-equity checklist scoring — same weight/threshold philosophy as
factor_engine.py's India checklist, adapted for what's actually real and
free for US stocks (SEC EDGAR fundamentals, no promoter-pledge equivalent,
relative volume instead of NSE delivery %, S&P 500 as the benchmark
instead of Nifty).

Kept as a separate module rather than more branches inside factor_engine.py
because the input field set genuinely differs (debt_to_equity instead of
net_debt_ebitda, relative_volume instead of delivery_pct_10d) — mixing
both markets' conditionals into one function was making the India one
harder to read for no real benefit.
"""

from __future__ import annotations

from typing import Any, Dict, List

from engine.factor_engine import CONFIDENCE_MULTIPLIER, _f, _item, _optional, _quality


def _is_financial_us(row: Any) -> bool:
    blob = " ".join(str(row.get(k) or "") for k in ("sector", "industry")).lower()
    return any(w in blob for w in ("financ", "bank", "insurance", "capital markets"))


def evaluate_us_fundamental_checklist(row: Any) -> Dict[str, Any]:
    """Marks out of ~44 (financials) / ~49 (everything else) — one fewer
    real category than India's checklist (no promoter-pledge equivalent;
    SEC Form 3/4 insider-ownership aggregation is real but meaningfully
    more work to build correctly, so it's not faked in as a placeholder
    here — see us_data_provider.py's module docstring)."""
    items: List[Dict[str, Any]] = []
    quality = _quality(row)
    financial = _is_financial_us(row)

    if quality == "MISSING":
        items.append(
            _item(
                "Data quality gate",
                "MISSING",
                0.0,
                10,
                False,
                "SEC EDGAR had no usable filed fundamentals for this ticker — placeholder values blocked, nothing invented.",
            )
        )

    roe = _optional(row, "roic") or _optional(row, "roe")
    if roe is None or quality == "MISSING":
        items.append(_item("ROE (Return on Equity)", "—", 0.0, 10, False, "Capital return missing or unverified."))
    elif roe >= 20:
        items.append(_item("ROE (Return on Equity)", f"{roe:.1f}%", 10.0, 10, True, "Excellent capital efficiency (≥ 20%)."))
    elif roe >= 12:
        items.append(_item("ROE (Return on Equity)", f"{roe:.1f}%", 7.0, 10, True, "Solid capital return — quality franchise."))
    elif roe >= 8:
        items.append(_item("ROE (Return on Equity)", f"{roe:.1f}%", 4.0, 10, False, "Average returns on capital."))
    else:
        items.append(_item("ROE (Return on Equity)", f"{roe:.1f}%", 1.0, 10, False, "Weak capital return."))

    if financial:
        items.append(
            _item("Debt / Equity", "N/A (Financial pack)", 0.0, 0, True, "Skipped — not a valid leverage proxy for banks/insurers.")
        )
    else:
        dte = _optional(row, "debt_to_equity")
        if dte is None or quality == "MISSING":
            items.append(_item("Debt / Equity", "—", 0.0, 8, False, "Leverage unverified or not filed."))
        elif dte <= 0.3:
            items.append(_item("Debt / Equity", f"{dte:.2f}x", 8.0, 8, True, "Conservative leverage."))
        elif dte <= 0.8:
            items.append(_item("Debt / Equity", f"{dte:.2f}x", 5.0, 8, True, "Manageable leverage."))
        elif dte <= 1.5:
            items.append(_item("Debt / Equity", f"{dte:.2f}x", 2.0, 8, False, "Elevated leverage."))
        else:
            items.append(_item("Debt / Equity", f"{dte:.2f}x", 0.0, 8, False, "High leverage."))

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

    if financial:
        items.append(
            _item("Interest Coverage", "N/A (Financial pack)", 0.0, 0, True, "Skipped — not meaningful for a lender.")
        )
    else:
        ic = _optional(row, "interest_coverage")
        if ic is None:
            items.append(
                _item(
                    "Interest Coverage",
                    "N/A (not filed / not applicable)",
                    0.0,
                    0,
                    True,
                    "Skipped — this company's SEC filings didn't carry both operating income and interest expense; does not block the name.",
                )
            )
        elif quality == "MISSING":
            items.append(_item("Interest Coverage", "—", 0.0, 6, False, "Blocked — unverified."))
        elif ic >= 8:
            items.append(_item("Interest Coverage", f"{ic:.1f}x", 6.0, 6, True, "Strong interest coverage."))
        elif ic >= 4:
            items.append(_item("Interest Coverage", f"{ic:.1f}x", 4.0, 6, True, "Adequate interest coverage."))
        else:
            items.append(_item("Interest Coverage", f"{ic:.1f}x", 0.0, 6, False, "Weak interest coverage."))

    if growth is None or quality == "MISSING":
        items.append(_item("Profit Growth (YoY)", "—" if growth is None else f"{growth:.1f}%", 0.0, 7, False, "Growth unverified."))
    elif growth >= 20:
        items.append(_item("Profit Growth (YoY)", f"{growth:.1f}%", 7.0, 7, True, "Strong profit growth."))
    elif growth >= 10:
        items.append(_item("Profit Growth (YoY)", f"{growth:.1f}%", 5.0, 7, True, "Healthy double-digit growth."))
    elif growth >= 0:
        items.append(_item("Profit Growth (YoY)", f"{growth:.1f}%", 2.0, 7, False, "Low / flat profit growth."))
    else:
        items.append(_item("Profit Growth (YoY)", f"{growth:.1f}%", 0.0, 7, False, "Negative profit growth."))

    pe = _optional(row, "pe_ratio")
    pe_cap = 18 if financial else 30
    pe_mid = 28 if financial else 45
    if pe is None or pe <= 0 or quality == "MISSING":
        items.append(_item("Stock P/E", "—" if pe is None else f"{pe:.1f}", 0.0, 6, False, "P/E missing or not verified."))
    elif pe <= pe_cap:
        items.append(_item("Stock P/E", f"{pe:.1f}", 6.0, 6, True, "Reasonable PE for this pack."))
    elif pe <= pe_mid:
        items.append(_item("Stock P/E", f"{pe:.1f}", 3.0, 6, False, "Elevated PE."))
    else:
        items.append(_item("Stock P/E", f"{pe:.1f}", 0.5, 6, False, "Extremely rich PE — valuation danger."))

    pb = _optional(row, "pb_ratio")
    pb_cap = 2.5 if financial else 6.0
    if pb is None or quality == "MISSING":
        items.append(_item("P/B Ratio", "—", 0.0, 4, False, "Book value / P/B not available."))
    elif pb <= pb_cap * 0.6:
        items.append(_item("P/B Ratio", f"{pb:.2f}", 4.0, 4, True, "Cheap relative to book value."))
    elif pb <= pb_cap:
        items.append(_item("P/B Ratio", f"{pb:.2f}", 2.0, 4, True, "Reasonable P/B for this pack."))
    else:
        items.append(_item("P/B Ratio", f"{pb:.2f}", 0.5, 4, False, "Rich vs book value."))

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
        "sector_pack": "financials" if financial else "quality",
    }


def evaluate_us_technical_checklist(row: Any) -> Dict[str, Any]:
    """Marks out of 55 — identical structure to India's technical
    checklist, with Relative Volume replacing Delivery % (no NSE-bhavcopy
    equivalent exists for US equities) and alpha measured against S&P 500
    instead of Nifty."""
    items: List[Dict[str, Any]] = []
    close = _f(row, "close_price")
    sma50 = _f(row, "sma_50")
    sma200 = _f(row, "sma_200")
    rsi = _f(row, "rsi_14", 50)
    atr = _f(row, "atr_value")
    alpha = _f(row, "alpha_3m")
    rel_vol = _optional(row, "relative_volume")

    if close > sma200:
        m, ok, note = 10.0, True, "Price above 200-day SMA — primary uptrend intact."
    elif close > sma200 * 0.98:
        m, ok, note = 5.0, False, "Near 200 SMA — trend contested."
    else:
        m, ok, note = 0.0, False, "Below 200 SMA — primary trend down / weak."
    items.append(_item("Price vs 200 SMA", f"${close:.2f} vs ${sma200:.2f}", m, 10, ok, note))

    if sma50 > 0 and close > sma50:
        m, ok, note = 6.0, True, "Price above 50-day SMA — intermediate trend supportive."
    elif sma50 > 0:
        m, ok, note = 2.0, False, "Below 50 SMA — short-term weakness."
    else:
        m, ok, note = 3.0, True, "50 SMA unavailable — neutral."
    items.append(_item("Price vs 50 SMA", f"${close:.2f} vs ${sma50:.2f}", m, 6, ok, note))

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
    elif rsi > 65:
        m, ok, note = 0.0, False, "RSI > 65 — overextended; entry locked."
    else:
        m, ok, note = 3.0, False, "RSI weak / oversold — wait for reclaim."
    items.append(_item("RSI (14)", f"{rsi:.1f}", m, 10, ok, note))

    if alpha >= 10:
        m, ok, note = 8.0, True, "Strong 3M relative strength vs S&P 500."
    elif alpha >= 0:
        m, ok, note = 5.0, True, "In-line / mild outperformance vs S&P 500 (3M)."
    elif alpha >= -8:
        m, ok, note = 2.0, False, "Mild underperformance vs S&P 500."
    else:
        m, ok, note = 0.0, False, "Severe relative weakness vs S&P 500."
    items.append(_item("3M Alpha vs S&P 500", f"{alpha:+.1f}%", m, 8, ok, note))

    if rel_vol is None:
        items.append(
            _item(
                "Relative Volume",
                "N/A (insufficient history)",
                0.0,
                0,
                True,
                "Skipped — fewer than 20 days of trading history to compute a baseline; does not block the name.",
            )
        )
    elif rel_vol >= 1.5:
        items.append(_item("Relative Volume", f"{rel_vol:.2f}× 30D avg", 5.0, 5, True, "Strong participation — well above average volume."))
    elif rel_vol >= 0.8:
        items.append(_item("Relative Volume", f"{rel_vol:.2f}× 30D avg", 3.5, 5, True, "Acceptable participation."))
    else:
        items.append(_item("Relative Volume", f"{rel_vol:.2f}× 30D avg", 1.0, 5, False, "Weak participation — below-average volume."))

    atr_pct = (atr / close * 100.0) if close > 0 else 0.0
    if 1.0 <= atr_pct <= 4.5:
        m, ok, note = 5.0, True, "ATR% in tradeable swing band (not too quiet / chaotic)."
    elif atr_pct < 1.0:
        m, ok, note = 2.0, False, "Very low volatility — breakout may need volume."
    else:
        m, ok, note = 1.5, False, "High ATR% — wider stops, choppier path."
    items.append(_item("ATR % of Price", f"{atr_pct:.2f}%", m, 5, ok, note))

    mom_21 = _optional(row, "momentum_21d")
    if mom_21 is None:
        items.append(_item("21D Momentum", "—", 2.0, 5, True, "History short — neutral mark."))
    elif mom_21 >= 5:
        items.append(_item("21D Momentum", f"{mom_21:+.1f}%", 5.0, 5, True, f"Positive 21-session momentum ({mom_21:+.1f}%)."))
    elif mom_21 >= 0:
        items.append(_item("21D Momentum", f"{mom_21:+.1f}%", 3.0, 5, True, f"Flat-to-up 21-session momentum ({mom_21:+.1f}%)."))
    else:
        items.append(_item("21D Momentum", f"{mom_21:+.1f}%", 0.5, 5, False, f"Negative 21-session momentum ({mom_21:+.1f}%)."))

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


def full_us_factor_scorecard(row: Any) -> Dict[str, Any]:
    fund = evaluate_us_fundamental_checklist(row)
    tech = evaluate_us_technical_checklist(row)
    composite = round(fund["total_marks"] + tech["total_marks"], 1)
    composite_max = round(fund["max_marks"] + tech["max_marks"], 1)
    return {
        "fundamental": fund,
        "technical": tech,
        "composite_marks": composite,
        "composite_max": composite_max,
        "composite_pct": round(composite / composite_max * 100.0, 1) if composite_max else 0.0,
        "sector_pack": fund.get("sector_pack"),
    }
