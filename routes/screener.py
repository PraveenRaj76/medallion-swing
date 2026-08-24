"""GET /api/screener — leaderboard, wrapping database_engine + data_pipeline."""

from __future__ import annotations

from typing import Optional

import pandas as pd
from fastapi import APIRouter, Query

import data_pipeline as pipeline
import database_engine as db

from ._util import frame_to_records

router = APIRouter()


@router.get("/screener")
def get_screener(
    limit: int = Query(100, ge=1, le=500),
    min_score: float = Query(0.0, ge=0.0),
    sector: Optional[str] = None,
    ready_only: bool = Query(
        False, description="Only rows fully verified + refreshed today (see filter_display_ready)."
    ),
):
    full = db.get_leaderboard(limit=1000)
    ready = pipeline.filter_display_ready(full)
    frame = ready if ready_only else full

    if frame is not None and not frame.empty:
        if "composite_score" in frame.columns:
            frame = frame[pd.to_numeric(frame["composite_score"], errors="coerce").fillna(0) >= min_score]
        if sector:
            frame = frame[frame.get("sector", pd.Series(dtype=str)).astype(str).str.casefold() == sector.casefold()]
        if "composite_score" in frame.columns:
            frame = frame.sort_values("composite_score", ascending=False)
        frame = frame.head(limit)

    return {
        "as_of": db.screener_as_of(),
        "total_stocks": db.leaderboard_count(),
        "ready_count": len(ready),
        "returned": 0 if frame is None else len(frame),
        "data": frame_to_records(frame),
    }
