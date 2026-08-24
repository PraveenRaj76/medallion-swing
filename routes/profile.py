"""GET /api/profile/{ticker} — single-stock checklist deep-dive.

Wraps nse_data_provider.build_live_row() (or the cached DB row) plus
factor_engine.full_factor_scorecard() — no scoring logic lives here.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

import data_pipeline as pipeline
import database_engine as db
import factor_engine as factors
import nse_data_provider as nse

from ._util import default_user_id, series_to_dict

router = APIRouter()


@router.get("/profile/{ticker}")
def get_profile(
    ticker: str,
    live: bool = Query(
        False, description="Pull a fresh Angel One quote + Screener/BSE fundamentals instead of the cached DB row."
    ),
    user_id: int = Query(None, description="For the BUY-signal position-budget gate; defaults to MEDALLION_DEFAULT_USER_ID."),
):
    ticker = nse.normalize_ticker(ticker)
    prior_series = db.get_ticker_row(ticker)
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
    buy_signal = pipeline.evaluate_buy_signal(row, scorecard, default_user_id(user_id))

    return {
        "ticker": row.get("ticker", ticker),
        "company_name": row.get("company_name"),
        "sector": row.get("sector"),
        "industry": row.get("industry"),
        "close_price": row.get("close_price"),
        "data_quality": row.get("data_quality"),
        "fundamentals_verified": row.get("fundamentals_verified"),
        "source": source,
        "checklist": scorecard,
        "buy_signal": buy_signal,
        "raw": row,
    }
