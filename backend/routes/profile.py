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

from db import database_engine as db
from engine import data_pipeline as pipeline
from engine import factor_engine as factors
from engine import factor_engine_us as factors_us
from providers import nse_data_provider as nse
from providers import us_data_provider as usdp

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
        "price_as_of": row.get("price_as_of"),
    }

    quote["price_cross_check"] = None
    if market == "IN":
        # The one place two genuinely independent LIVE price sources exist
        # in this app: Yahoo's OHLCV close (already in `close` above) and
        # Angel One's own live tick. Previously this just silently preferred
        # Angel One whenever it answered, with no check that the two
        # actually agreed — meaning a bug or stale cache on either side
        # could hand the user a wrong number with the same confident "LIVE"
        # label as a correct one. Recorded as a real cross-check result
        # rather than fabricated: fundamentals mostly have only one free
        # source (Screener.in) to check against, so this is scoped to what
        # genuinely has a second source, not a blanket "multi-source"
        # claim across fields that don't have one.
        ohlcv_price = close
        try:
            from providers import live_price_feed as lpf

            live = lpf.fetch_live_quote(ticker)
        except Exception:
            live = {"ok": False}
        if live.get("ok"):
            live_price = live.get("close_price")
            quote.update(
                {
                    "price": live_price if live_price is not None else quote["price"],
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
            # 2026-09-11: this used to fire on live.get("ok") alone. When
            # Angel One isn't configured/reachable, fetch_live_quote silently
            # falls back to live_price_feed._fetch_yahoo_quotes_batch — which
            # itself just calls nse_data_provider.fetch_ohlcv again, the same
            # underlying source as `close`/ohlcv_price above. That produced a
            # "cross-check" comparing Yahoo against Yahoo (two fetches at
            # different times, not two independent sources), labeled with a
            # confident agrees/disagrees verdict that was really just
            # reporting how stale the cached `row` price was — misleading in
            # the exact way this feature exists to prevent. Only build a
            # cross-check when the second reading is genuinely Angel One.
            if live.get("source") == "angelone" and ohlcv_price is not None and live_price is not None:
                try:
                    ohlcv_price_f = float(ohlcv_price)
                    live_price_f = float(live_price)
                    diff_pct = (
                        abs(live_price_f - ohlcv_price_f) / ohlcv_price_f * 100.0
                        if ohlcv_price_f
                        else None
                    )
                    quote["price_cross_check"] = {
                        "primary_source": quote["source"] or "angel_one",
                        "primary_price": round(live_price_f, 2),
                        "secondary_source": "yahoo",
                        "secondary_price": round(ohlcv_price_f, 2),
                        "diff_pct": round(diff_pct, 2) if diff_pct is not None else None,
                        # >1.5% apart between two live quotes on the same
                        # exchange is a real disagreement worth flagging,
                        # not routine timing noise between two feeds.
                        "agrees": diff_pct is not None and diff_pct <= 1.5,
                    }
                except (TypeError, ValueError):
                    quote["price_cross_check"] = None

    if quote["price"] is not None and quote["prev_close"]:
        try:
            price = float(quote["price"])
            prev = float(quote["prev_close"])
            quote["day_change"] = round(price - prev, 2)
            quote["day_change_pct"] = round((price - prev) / prev * 100.0, 2) if prev else None
        except (TypeError, ValueError):
            pass

    # Recheck logic: reconfirms the price is actually current instead of
    # letting a "LIVE"/"LAST" label imply it by default. A real timestamped
    # tick from the live feed (Angel One, India only) IS the market's
    # current price at fetch time — trust it outright, even if the
    # separate OHLCV history used for SMA/RSI/technicals happens to lag by
    # a session (a real, observed case: yfinance's history() can return a
    # most-recent bar with real volume but NaN OHLC before Yahoo's own
    # backend backfills it — see nse.price_freshness). Without a live
    # tick, fall back to how old that OHLCV bar actually is.
    if quote.get("fetched_at"):
        quote["is_stale"] = False
        quote["days_stale"] = 0
    else:
        freshness = nse.price_freshness(quote.get("price_as_of"))
        quote["is_stale"] = freshness["is_stale"]
        quote["days_stale"] = freshness["days_stale"]

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
            # pe_peer_percentile (see factor_engine.compute_peer_relative_valuation,
            # now run for the US universe too — us_data_provider.refresh_universe)
            # is a whole-batch ranking a single live-ticker fetch can't recompute
            # on its own — carry the last refresh's value forward, same as the
            # India branch below already does, so a live US search doesn't
            # silently drop the "PE vs sector peers" checklist item.
            if row.get("pe_peer_percentile") is None and prior_dict is not None:
                row["pe_peer_percentile"] = prior_dict.get("pe_peer_percentile")
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
            # pe_peer_percentile (see factor_engine.compute_peer_relative_valuation)
            # is a whole-universe ranking computed once per refresh, not
            # something a single live-ticker fetch can recompute on its own —
            # carry the last refresh's value forward so a live search doesn't
            # silently lose the "PE vs sector peers" checklist item.
            if row.get("pe_peer_percentile") is None and prior_dict is not None:
                row["pe_peer_percentile"] = prior_dict.get("pe_peer_percentile")
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

    buy_signal = pipeline.evaluate_buy_signal(row, scorecard, uid, market=market)

    atr = row.get("atr_value")
    close_price = row.get("close_price")
    trade_levels = None
    try:
        if atr and close_price and float(atr) > 0:
            levels = pipeline.build_trade_levels(float(close_price), float(atr))
            trade_levels = levels if levels.get("valid") else None
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
