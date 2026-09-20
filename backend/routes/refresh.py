"""POST /api/refresh, GET /api/refresh/status, POST /api/trade, POST /api/trade/close.

Refresh now runs as a background job (engine/refresh_jobs.py), not a single
long-lived HTTP request — see that module's docstring for the root cause
this fixes (a client disconnect, a tab navigation, or a hosting platform's
own proxy timeout used to silently kill a still-progressing refresh, with
the "Refreshing…" state living only in local React state so navigating away
and back made a genuinely-still-running refresh look like it had done
nothing). POST /api/refresh returns immediately once the job is started (or
immediately reports one is already running); GET /api/refresh/status is what
the frontend polls for real progress and an ETA, independent of who
started the job or which page is currently open.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from engine import data_pipeline as pipeline
from engine import refresh_jobs
from db import database_engine as db

from ._util import default_user_id
from models.schemas import RefreshRequest, TradeCloseRequest, TradeOpenRequest

router = APIRouter()


def _estimate_total(body: RefreshRequest) -> int:
    """Best-effort ticker count for the initial ETA denominator — refined
    automatically once refresh_jobs sees real progress (see get_status's
    done/elapsed rate), so an approximate starting guess here is fine."""
    if body.tickers:
        return len(body.tickers)
    try:
        if body.market.upper() == "US":
            from providers import us_data_provider as usdp

            return len(usdp.load_universe())
        from providers import nse_data_provider as nse

        return len(nse.load_universe()) if body.full_universe else len(nse.BOOTSTRAP_TICKERS)
    except Exception:
        return 200  # generic fallback — only affects the ETA display, not the refresh itself


@router.post("/refresh")
def post_refresh(body: RefreshRequest):
    uid = default_user_id(body.user_id)
    market = body.market.upper()

    # refresh_jobs.start() is itself race-safe (atomic check-and-set under
    # its own lock) — this is_running() check is purely a fast path to skip
    # _estimate_total()'s real I/O (load_universe()) when it isn't needed,
    # not something correctness depends on.
    if not refresh_jobs.is_running(market):
        total_estimate = _estimate_total(body)
        if market == "US":
            refresh_jobs.start(
                market, total_estimate, pipeline.refresh_us_verified_live, tickers=body.tickers, user_id=uid,
            )
        else:
            refresh_jobs.start(
                market,
                total_estimate,
                pipeline.refresh_verified_live,
                tickers=body.tickers,
                user_id=uid,
                full_universe=body.full_universe,
                with_fundamentals=body.with_fundamentals,
            )
    # By the time start() returns, the job's own status is already "running"
    # (set synchronously before the background thread is spawned) whether it
    # was just started or was already running — that single field is enough
    # for the frontend to know "go start polling", no separate started/
    # already_running wrapper needed.
    return refresh_jobs.get_status(market)


@router.get("/refresh/status")
def get_refresh_status(market: str = Query("IN", pattern="^(?i)(IN|US)$")):
    return refresh_jobs.get_status(market.upper())


@router.post("/trade")
def post_open_trade(body: TradeOpenRequest):
    uid = default_user_id(body.user_id)
    market = (body.market or "IN").upper()
    # ATR seeds the chandelier trailing stop (see data_pipeline.compute_trailing_stop).
    # Prefer whatever the caller just fetched live (Search Profile always sends this —
    # it's the same ATR the suggested stop/target were built from); fall back to a
    # cached leaderboard lookup only for older/other callers that don't pass one.
    # NOTE: get_ticker_row is market-scoped since India and US share one leaderboard
    # table keyed by ticker — without it a US ticker's ATR lookup could silently read
    # an unrelated India row (or vice versa) if the same string ever existed in both.
    # Sector is always looked up server-side (never client-supplied) — it's not
    # something a caller should be trusted to set, and evaluate_buy_signal's
    # sector_concentration gate needs the real value to mean anything. Always
    # fetch the row (previously only fetched when ATR was missing) since
    # sector is needed regardless.
    row = db.get_ticker_row(body.ticker, market=market)
    atr = body.atr
    if atr is None:
        atr = float(row["atr_value"]) if row is not None and row.get("atr_value") is not None else None
    sector = row.get("sector") if row is not None else None
    ok, message = db.open_signal(
        user_id=uid,
        ticker=body.ticker,
        entry_price=body.entry_price,
        stop_loss=body.stop_loss,
        target=body.target,
        atr=atr,
        market=market,
        sector=sector,
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
