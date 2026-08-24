"""POST /api/refresh, POST /api/trade, POST /api/trade/close.

Thin wrappers over data_pipeline.refresh_verified_live() and the
open_signal()/close_signal() pair in database_engine — no new business
logic. Refresh runs synchronously; for the full 200-stock universe this can
take a while, so point curl/React at it with a generous timeout for now.
Job-queue polling (as sketched in PHASE_1_FASTAPI_STARTER.md) can follow
once this round-trip is proven end to end.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

import data_pipeline as pipeline
import database_engine as db

from ._util import default_user_id
from models.schemas import RefreshRequest, TradeCloseRequest, TradeOpenRequest

router = APIRouter()


@router.post("/refresh")
def post_refresh(body: RefreshRequest):
    uid = default_user_id(body.user_id)
    result = pipeline.refresh_verified_live(
        tickers=body.tickers,
        user_id=uid,
        full_universe=body.full_universe,
        with_fundamentals=body.with_fundamentals,
    )
    return result


@router.post("/trade")
def post_open_trade(body: TradeOpenRequest):
    uid = default_user_id(body.user_id)
    # ATR seeds the chandelier trailing stop (see data_pipeline.compute_trailing_stop) —
    # looked up server-side from the cached leaderboard row so callers don't need to know it.
    row = db.get_ticker_row(body.ticker)
    atr = float(row["atr_value"]) if row is not None and row.get("atr_value") is not None else None
    ok, message = db.open_signal(
        user_id=uid,
        ticker=body.ticker,
        entry_price=body.entry_price,
        stop_loss=body.stop_loss,
        target=body.target,
        atr=atr,
    )
    if not ok:
        raise HTTPException(status_code=400, detail=message)
    return {"status": "OPEN", "message": message}


@router.post("/trade/close")
def post_close_trade(body: TradeCloseRequest):
    uid = default_user_id(body.user_id)
    ok, message, final_pnl = db.close_signal(
        user_id=uid,
        position_id=body.position_id,
        exit_price=body.exit_price,
        exit_status=body.exit_status,
    )
    if not ok:
        raise HTTPException(status_code=400, detail=message)
    return {"status": "CLOSED", "message": message, "final_pnl": round(final_pnl, 2)}
