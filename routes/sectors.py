"""GET /api/sectors — Best Sector rankings, wrapping sector_engine.py."""

from __future__ import annotations

from fastapi import APIRouter, Query

import sector_engine

router = APIRouter()


@router.get("/sectors")
def get_sectors(market: str = Query("IN", pattern="^(?i)(IN|US)$")):
    return sector_engine.compute_sector_rankings(market=market.upper())
