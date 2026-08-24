"""Pydantic request bodies for the FastAPI layer.

Responses are returned as plain dicts (the existing pipeline/db functions
already build well-shaped dicts and DataFrames) rather than re-modeled here,
per the Phase 1 goal of a thin wrapper — not a business-logic rewrite.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class RefreshRequest(BaseModel):
    tickers: Optional[list[str]] = Field(
        default=None, description="Specific tickers to refresh; omit for the full universe."
    )
    full_universe: bool = True
    with_fundamentals: bool = False
    user_id: Optional[int] = None


class TradeOpenRequest(BaseModel):
    ticker: str
    entry_price: float
    stop_loss: float
    target: float
    user_id: Optional[int] = None


class TradeCloseRequest(BaseModel):
    position_id: int
    exit_price: float
    exit_status: str
    user_id: Optional[int] = None


class RegisterRequest(BaseModel):
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str
