"""GET /api/forward-test — validation scorecard (win rate, expectancy, open/closed signals).

Wraps data_pipeline.compute_forward_test_scorecard() and
database_engine.get_active_positions() — this is the page that answers
whether the checklist actually has positive expectancy.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from engine import data_pipeline as pipeline
from db import database_engine as db

from ._util import default_user_id, frame_to_records

router = APIRouter()


@router.get("/forward-test")
def get_forward_test(
    user_id: Optional[int] = Query(None),
    market: str = Query("IN", pattern="^(?i)(IN|US)$"),
):
    uid = default_user_id(user_id)
    market = market.upper()
    scorecard = pipeline.compute_forward_test_scorecard(uid, market=market)
    active = db.get_active_positions(uid, market=market)
    return {
        "user_id": uid,
        "market": market,
        **scorecard,
        "active_positions": frame_to_records(active),
    }
