"""GET /api/profile/{ticker} — single-stock deep-dive: live quote, checklist
breakdown, suggested trade levels, any open forward-test position, and a
real price chart.

Wraps nse_data_provider.build_live_row() / us_data_provider.build_live_row()
(or the cached DB row) plus factor_engine.full_factor_scorecard() /
factor_engine_us.full_us_factor_scorecard() — no scoring logic lives here.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

import data_pipeline as pipeline
import database_engine as db
import factor_engine as factors
import factor_engine_us as factors_us
import nse_data_provider as nse
import us_data_provider as usdp

from ._util import default_user_id, series_to_dict

router = APIRouter()


def _build_quote(row: Dict[str, Any], market: str, ticker: str) -> Dict[str, Any]:
    """Real quote block. India tries the same Angel-One-first live feed the
    leaderboard batch refresh uses; US has no Angel One equivalent so it
    reads the day bar straight from the Yahoo OHLCV already fetched into
    `row` by build_live_row. Never fabricates a field — missing stays None."""
    close = row.get("close_price")
    quote: Dict[str, Any] = {
        "price": close,
        "prev_close": row.get("prev_close"),
        "open": row.get("day_open"),
        "day_high": row.get("day_high"),
        "day_low": row.get("day_low"),
        "volume": row.get("day_volume"),
        "week52_high": row.get("week52_high"),
        "week52_low": row.get("week52_low"),
        "day_change": None,
        "day_change_pct": None,
        "price_kind": row.get("price_kind") or "LAST",
        "source": row.get("price_source") or "yahoo",
        "fetched_at": None,
    }

    if market == "IN":
        try:
            import live_price_feed as lpf

            live = lpf.fetch_live_quote(ticker)
        except Exception:
            live = {"ok": False}
        if live.get("ok"):
            quote.update(
                {
                    "price": live.get("close_price", quote["price"]),
                    "prev_close": live.get("prev_close", quote["prev_close"]),
                    "open": live.get("open", quote["open"]),
                    "day_high": live.get("day_high", quote["day_high"]),
                    "day_low": live.get("day_low", quote["day_low"]),
                    "volume": live.get("volume", quote["volume"]),
                    "price_kind": live.get("price_kind") or quote["price_kind"],
                    "source": live.get("source") or quote["source"],
                    "fetched_at": live.get("fetched_at"),
                }
            )

    if quote["price"] is not None and quote["prev_close"]:
        try:
            price = float(quote["price"])
            prev = float(quote["prev_close"])
            quote["day_change"] = round(price - prev, 2)
            quote["day_change_pct"] = round((price - prev) / prev * 100.0, 2) if prev else None
        except (TypeError, ValueError):
            pass

    return quote


def _price_history(ticker: str, market: str) -> list[Dict[str, Any]]:
    """Real OHLCV for the chart — a second, deliberately separate fetch from
    build_live_row's own (which is used for technicals, not embedded here to
    avoid bloating the full-universe refresh payload). Empty list, not fake
    candles, if the fetch fails."""
    try:
        frame = (
            nse.fetch_chart_history(ticker, periods=260)
            if market == "IN"
            else usdp.fetch_ohlcv(ticker, period="1y", interval="1d")
        )
    except Exception:
        return []
    if frame is None or frame.empty:
        return []
    if "date" not in frame.columns:
        # us_data_provider.fetch_ohlcv returns a DatetimeIndex, not a "date"
        # column (nse_data_provider's own fetch already has one) — normalize.
        frame = frame.reset_index()
        frame = frame.rename(columns={frame.columns[0]: "date"})
    frame = frame.tail(260).copy()
    frame["sma_50"] = frame["close"].rolling(50).mean()
    frame["sma_200"] = frame["close"].rolling(200).mean()
    out = []
    for _, r in frame.iterrows():
        date_val = r.get("date")
        out.append(
            {
                "date": str(date_val)[:10] if date_val is not None else None,
                "close": round(float(r["close"]), 2) if pd.notna(r["close"]) else None,
                "sma_50": round(float(r["sma_50"]), 2) if pd.notna(r.get("sma_50")) else None,
                "sma_200": round(float(r["sma_200"]), 2) if pd.notna(r.get("sma_200")) else None,
            }
        )
    return out


@router.get("/profile/{ticker}")
def get_profile(
    ticker: str,
    live: bool = Query(
        False, description="Pull a fresh Angel One/Yahoo quote + fundamentals instead of the cached DB row."
    ),
    market: str = Query("IN", pattern="^(?i)(IN|US)$"),
    user_id: int = Query(None, description="For the BUY-signal position-budget gate; defaults to MEDALLION_DEFAULT_USER_ID."),
):
    market = market.upper()
    uid = default_user_id(user_id)

    if market == "US":
        ticker = usdp.normalize_ticker(ticker)
        prior_series = db.get_ticker_row(ticker, market="US")
        prior_dict = series_to_dict(prior_series) if prior_series is not None else None

        if live:
            row = usdp.build_live_row(ticker)
            if row is None:
                raise HTTPException(status_code=404, detail=f"No live data available for {ticker} right now.")
            source = "live"
        else:
            if prior_dict is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"{ticker} not found in the cached US leaderboard — try ?live=true or run a US refresh first.",
                )
            row = prior_dict
            source = "cached"

        scorecard = factors_us.full_us_factor_scorecard(row)
    else:
        ticker = nse.normalize_ticker(ticker)
        prior_series = db.get_ticker_row(ticker, market="IN")
        prior_dict = series_to_dict(prior_series) if prior_series is not None else None

        if live:
            row = nse.build_live_row(ticker, prior=prior_dict)
            if row is None:
                raise HTTPException(status_code=404, detail=f"No live data available for {ticker} right now.")
            source = "live"
        else:
            if prior_dict is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"{ticker} not found in the cached leaderboard — try ?live=true or run /api/refresh first.",
                )
            row = prior_dict
            source = "cached"

        scorecard = factors.full_factor_scorecard(row)

    buy_signal = pipeline.evaluate_buy_signal(row, scorecard, uid)

    atr = row.get("atr_value")
    close_price = row.get("close_price")
    trade_levels = None
    try:
        if atr and close_price and float(atr) > 0:
            trade_levels = pipeline.build_trade_levels(float(close_price), float(atr))
    except (TypeError, ValueError):
        trade_levels = None

    active = db.get_active_positions(uid, market=market)
    active_position = None
    if active is not None and not active.empty:
        match = active[active["ticker"].astype(str).str.upper() == ticker]
        if not match.empty:
            active_position = series_to_dict(match.iloc[0])

    return {
        "ticker": row.get("ticker", ticker),
        "company_name": row.get("company_name"),
        "sector": row.get("sector"),
        "industry": row.get("industry"),
        "market": market,
        "close_price": close_price,
        "data_quality": row.get("data_quality"),
        "fundamentals_verified": row.get("fundamentals_verified"),
        "source": source,
        "quote": _build_quote(row, market, ticker),
        "trade_levels": trade_levels,
        "active_position": active_position,
        "price_history": _price_history(ticker, market),
        "checklist": scorecard,
        "buy_signal": buy_signal,
        "raw": row,
    }
